"""Cena 3D de um projecto: furos com trajectória, intervalos litológicos e teores das amostras.

Um único pedido devolve tudo o que o visualizador precisa, sempre filtrado pela empresa activa.
"""
from collections import defaultdict

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import Contexto, exige, exigir_empresa
from app.models import AssayResult, DrillHole, DrillInterval, DrillSurvey, Lithology, Project, Sample
from app.schemas import PontoTrajectoria
from app.services.geo import _passo, trajectoria

router = APIRouter(tags=["Visualização 3D"])


class IntervaloCena(BaseModel):
    de: float
    ate: float
    litologia_codigo: str | None = None
    litologia_nome: str | None = None
    cor: str | None = None


class AmostraCena(BaseModel):
    id: str
    codigo: str
    de: float
    ate: float
    teores: dict[str, float]


class FuroCena(BaseModel):
    id: str
    codigo: str
    estado: str
    tipo: str
    profundidade: float
    pontos: list[PontoTrajectoria]
    intervalos: list[IntervaloCena]
    amostras: list[AmostraCena]


class ParametroCena(BaseModel):
    parametro: str
    unidade: str
    minimo: float
    maximo: float


class CenaProjecto(BaseModel):
    project_id: str
    furos: list[FuroCena]
    sem_coordenadas: list[str]
    parametros: list[ParametroCena]


def _profundidade(furo: DrillHole, comprimento: float, intervalos: list[DrillInterval],
                  amostras: list[Sample]) -> float:
    # profundidade final quando existe; senão a prevista (furo em curso ou planeado)
    referencia = furo.profundidade_final if furo.profundidade_final is not None else furo.profundidade_prevista
    candidatos = [referencia or 0, comprimento]
    candidatos += [i.ate for i in intervalos] + [a.ate for a in amostras if a.ate is not None]
    return float(max(candidatos))


def _estender(pontos: list[PontoTrajectoria], furo: DrillHole, ate: float) -> list[PontoTrajectoria]:
    """Prolonga a trajectória até à profundidade total com a última orientação conhecida
    (ou a do collar, quando não há surveys), para que o furo inteiro seja desenhado."""
    ultimo = pontos[-1]
    if ate <= ultimo.profundidade + 1e-6:
        return pontos
    if len(pontos) >= 2:
        anterior = pontos[-2]
        passo = ultimo.profundidade - anterior.profundidade or 1.0
        dx, dy, dz = ((ultimo.x - anterior.x) / passo, (ultimo.y - anterior.y) / passo,
                      (ultimo.z - anterior.z) / passo)
    else:
        nx, ny, nz = _passo(0.0, 0.0, 0.0, 1.0, furo.azimute or 0.0,
                            furo.inclinacao if furo.inclinacao is not None else -90.0)
        dx, dy, dz = nx, ny, nz
    delta = ate - ultimo.profundidade
    final = PontoTrajectoria(profundidade=ate, x=round(ultimo.x + dx * delta, 4),
                             y=round(ultimo.y + dy * delta, 4), z=round(ultimo.z + dz * delta, 4))
    return [*pontos, final]


@router.get("/projects/{project_id}/scene-3d", response_model=CenaProjecto,
            summary="Dados para a visualização 3D do projecto")
def cena_projecto(project_id: str, ctx: Contexto = Depends(exige("drill_holes", "view")),
                  db: Session = Depends(get_db)):
    company_id = exigir_empresa(ctx)
    projecto = db.get(Project, project_id)
    if projecto is None or projecto.company_id != company_id or projecto.eliminado_em is not None:
        raise HTTPException(404, "Projecto não encontrado")

    furos = list(db.scalars(select(DrillHole).where(
        DrillHole.company_id == company_id, DrillHole.project_id == project_id,
        DrillHole.eliminado_em.is_(None)).order_by(DrillHole.codigo)))
    ids = [f.id for f in furos]

    surveys: dict[str, list[DrillSurvey]] = defaultdict(list)
    intervalos: dict[str, list[DrillInterval]] = defaultdict(list)
    amostras: dict[str, list[Sample]] = defaultdict(list)
    teores: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    unidades: dict[str, str] = {}
    litologias: dict[str, Lithology] = {}

    if ids:
        for s in db.scalars(select(DrillSurvey).where(DrillSurvey.company_id == company_id,
                                                      DrillSurvey.drill_hole_id.in_(ids))):
            surveys[s.drill_hole_id].append(s)
        for i in db.scalars(select(DrillInterval).where(DrillInterval.company_id == company_id,
                                                        DrillInterval.drill_hole_id.in_(ids))
                            .order_by(DrillInterval.de)):
            intervalos[i.drill_hole_id].append(i)
        litologias = {l.id: l for l in db.scalars(select(Lithology).where(Lithology.company_id == company_id))}
        lista_amostras = list(db.scalars(select(Sample).where(
            Sample.company_id == company_id, Sample.drill_hole_id.in_(ids), Sample.eliminado_em.is_(None),
            Sample.de.is_not(None), Sample.ate.is_not(None))))
        for a in lista_amostras:
            amostras[a.drill_hole_id].append(a)
        if lista_amostras:
            for r in db.scalars(select(AssayResult).where(
                    AssayResult.company_id == company_id,
                    AssayResult.sample_id.in_([a.id for a in lista_amostras]),
                    AssayResult.estado != "rejeitado")):
                teores[r.sample_id][r.parametro].append(r.valor)
                unidades.setdefault(r.parametro, r.unidade)

    saida: list[FuroCena] = []
    sem_coordenadas: list[str] = []
    gamas: dict[str, list[float]] = defaultdict(list)
    for furo in furos:
        if furo.x is None or furo.y is None or furo.z is None:
            sem_coordenadas.append(furo.codigo)
            continue
        traj = trajectoria(furo, surveys[furo.id])
        profundidade = _profundidade(furo, traj.comprimento, intervalos[furo.id], amostras[furo.id])
        lista_amostras_furo = []
        for a in sorted(amostras[furo.id], key=lambda a: a.de):
            medias = {p: round(sum(v) / len(v), 4) for p, v in teores[a.id].items()}
            for p, v in medias.items():
                gamas[p].append(v)
            lista_amostras_furo.append(AmostraCena(id=a.id, codigo=a.codigo, de=a.de, ate=a.ate, teores=medias))
        saida.append(FuroCena(
            id=furo.id, codigo=furo.codigo, estado=furo.estado, tipo=furo.tipo,
            profundidade=profundidade,
            pontos=_estender(traj.pontos, furo, profundidade),
            intervalos=[IntervaloCena(
                de=i.de, ate=i.ate,
                litologia_codigo=litologias[i.lithology_id].codigo if i.lithology_id in litologias else None,
                litologia_nome=litologias[i.lithology_id].nome if i.lithology_id in litologias else None,
                cor=litologias[i.lithology_id].cor if i.lithology_id in litologias else None,
            ) for i in intervalos[furo.id]],
            amostras=lista_amostras_furo,
        ))

    parametros = [ParametroCena(parametro=p, unidade=unidades.get(p, ""), minimo=min(v), maximo=max(v))
                  for p, v in sorted(gamas.items())]
    return CenaProjecto(project_id=project_id, furos=saida, sem_coordenadas=sem_coordenadas,
                        parametros=parametros)
