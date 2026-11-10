"""Amostras geológicas, com validação de furos, intervalos e profundidades."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.common import paginar
from app.database import get_db
from app.deps import Contexto, exige, exigir_empresa
from app.models import DrillHole, DrillInterval, Project, Sample, agora
from app.schemas import AmostraActualizar, AmostraCriar, AmostraSaida, Pagina
from app.services.auditoria import auditar, serializar

router = APIRouter(prefix="/samples", tags=["Amostras"])


def _obter(db: Session, company_id: str, sample_id: str, incluir_eliminados: bool = False) -> Sample:
    amostra = db.get(Sample, sample_id)
    if amostra is None or amostra.company_id != company_id:
        raise HTTPException(404, "Amostra não encontrada")
    if amostra.eliminado_em is not None and not incluir_eliminados:
        raise HTTPException(404, "Amostra não encontrada")
    return amostra


def _projecto(db: Session, company_id: str, project_id: str) -> Project:
    projeto = db.get(Project, project_id)
    if projeto is None or projeto.company_id != company_id or projeto.eliminado_em is not None:
        raise HTTPException(422, "O projecto indicado não existe na empresa")
    return projeto


def _validar_relacoes(
    db: Session,
    company_id: str,
    project_id: str,
    drill_hole_id: str | None,
    drill_interval_id: str | None,
    de: float | None,
    ate: float | None,
) -> tuple[str | None, DrillHole | None]:
    """Valida a amostra contra o projecto, o furo e o intervalo geológico."""
    _projecto(db, company_id, project_id)
    if de is not None and ate is not None and ate <= de:
        raise HTTPException(422, "O fim da amostra tem de ser maior do que o início")

    intervalo: DrillInterval | None = None
    if drill_interval_id:
        intervalo = db.get(DrillInterval, drill_interval_id)
        if intervalo is None or intervalo.company_id != company_id:
            raise HTTPException(422, "O intervalo indicado não existe na empresa")
        if drill_hole_id and intervalo.drill_hole_id != drill_hole_id:
            raise HTTPException(422, "O intervalo não pertence ao furo indicado")
        drill_hole_id = intervalo.drill_hole_id

    furo: DrillHole | None = None
    if drill_hole_id:
        furo = db.get(DrillHole, drill_hole_id)
        if furo is None or furo.company_id != company_id or furo.eliminado_em is not None:
            raise HTTPException(422, "O furo indicado não existe na empresa")
        if furo.project_id != project_id:
            raise HTTPException(422, "O furo não pertence ao projecto indicado")
        if ate is not None and furo.profundidade_final is not None and ate > furo.profundidade_final:
            raise HTTPException(
                422, f"A amostra excede a profundidade final do furo ({furo.profundidade_final} m)",
            )

    if intervalo is not None:
        if de is not None and de < intervalo.de:
            raise HTTPException(422, f"A amostra começa antes do intervalo ({intervalo.de} m)")
        if ate is not None and ate > intervalo.ate:
            raise HTTPException(422, f"A amostra termina depois do intervalo ({intervalo.ate} m)")

    return drill_hole_id, furo


@router.get("", response_model=Pagina[AmostraSaida], summary="Listar amostras")
def listar(project_id: str | None = None, drill_hole_id: str | None = None,
           estado: str | None = None, tipo: str | None = None, q: str | None = None,
           incluir_eliminados: bool = False, skip: int = 0, limit: int = 50,
           ctx: Contexto = Depends(exige("samples", "view")), db: Session = Depends(get_db)):
    company_id = exigir_empresa(ctx)
    consulta = select(Sample).where(Sample.company_id == company_id)
    if not incluir_eliminados:
        consulta = consulta.where(Sample.eliminado_em.is_(None))
    if project_id:
        consulta = consulta.where(Sample.project_id == project_id)
    if drill_hole_id:
        consulta = consulta.where(Sample.drill_hole_id == drill_hole_id)
    if estado:
        consulta = consulta.where(Sample.estado == estado)
    if tipo:
        consulta = consulta.where(Sample.tipo == tipo)
    if q:
        termo = f"%{q.strip()}%"
        consulta = consulta.where(or_(Sample.codigo.ilike(termo), Sample.notas.ilike(termo)))
    total, items = paginar(db, consulta.order_by(Sample.codigo), skip, limit)
    return {"total": total, "items": items}


@router.post("", response_model=AmostraSaida, status_code=201, summary="Registar amostra")
def criar(dados: AmostraCriar, ctx: Contexto = Depends(exige("samples", "create")),
          db: Session = Depends(get_db)):
    company_id = exigir_empresa(ctx)
    hole_id, _ = _validar_relacoes(db, company_id, dados.project_id, dados.drill_hole_id,
                                   dados.drill_interval_id, dados.de, dados.ate)
    if db.scalar(select(Sample).where(Sample.company_id == company_id, Sample.codigo == dados.codigo)):
        raise HTTPException(409, "Já existe uma amostra com este código na empresa")
    valores = dados.model_dump()
    valores["drill_hole_id"] = hole_id
    amostra = Sample(company_id=company_id, **valores)
    db.add(amostra)
    db.flush()
    auditar(db, ctx, "criar", "sample", amostra.id, depois=serializar(amostra))
    db.commit()
    return amostra


@router.get("/{sample_id}", response_model=AmostraSaida, summary="Consultar amostra")
def obter(sample_id: str, ctx: Contexto = Depends(exige("samples", "view")),
          db: Session = Depends(get_db)):
    return _obter(db, exigir_empresa(ctx), sample_id)


@router.patch("/{sample_id}", response_model=AmostraSaida, summary="Actualizar amostra")
def actualizar(sample_id: str, dados: AmostraActualizar,
               ctx: Contexto = Depends(exige("samples", "edit")), db: Session = Depends(get_db)):
    company_id = exigir_empresa(ctx)
    amostra = _obter(db, company_id, sample_id)
    alteracoes = dados.model_dump(exclude_unset=True)
    if "codigo" in alteracoes and alteracoes["codigo"] != amostra.codigo:
        if db.scalar(select(Sample).where(Sample.company_id == company_id,
                                          Sample.codigo == alteracoes["codigo"])):
            raise HTTPException(409, "Já existe uma amostra com este código na empresa")
    project_id = amostra.project_id
    hole_id = alteracoes.get("drill_hole_id", amostra.drill_hole_id)
    interval_id = alteracoes.get("drill_interval_id", amostra.drill_interval_id)
    de = alteracoes.get("de", amostra.de)
    ate = alteracoes.get("ate", amostra.ate)
    hole_id, _ = _validar_relacoes(db, company_id, project_id, hole_id, interval_id, de, ate)
    alteracoes["drill_hole_id"] = hole_id
    antes = serializar(amostra)
    for campo, valor in alteracoes.items():
        setattr(amostra, campo, valor)
    auditar(db, ctx, "actualizar", "sample", amostra.id, antes=antes, depois=serializar(amostra))
    db.commit()
    return amostra


@router.delete("/{sample_id}", status_code=204, summary="Eliminar amostra (soft delete)")
def eliminar(sample_id: str, ctx: Contexto = Depends(exige("samples", "delete")),
             db: Session = Depends(get_db)):
    amostra = _obter(db, exigir_empresa(ctx), sample_id)
    antes = serializar(amostra)
    amostra.eliminado_em = agora()
    auditar(db, ctx, "eliminar", "sample", amostra.id, antes=antes)
    db.commit()
