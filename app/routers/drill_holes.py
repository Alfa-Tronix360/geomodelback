"""Sondagens: furos, trajectórias, intervalos geológicos e validações."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.common import paginar
from app.database import get_db
from app.deps import Contexto, exige, exigir_empresa
from app.models import (
    CompanyUser, DrillHole, DrillInterval, DrillSurvey, Lithology, Project, Sample, User, agora,
)
from app.schemas import (
    FuroActualizar, FuroCriar, FuroDetalhe, FuroSaida, IntervaloActualizar, IntervaloCriar,
    IntervaloSaida, Pagina, SurveyCriar, SurveySaida, TrajectoriaSaida,
)
from app.services.auditoria import auditar, serializar
from app.services.geo import trajectoria
from app.services.codigos import proximo_codigo_furo
from app.services.coordenadas import completar_coordenadas

router = APIRouter(prefix="/drill-holes", tags=["Sondagens"])


def _obter_furo(db: Session, company_id: str, hole_id: str) -> DrillHole:
    furo = db.get(DrillHole, hole_id)
    if furo is None or furo.company_id != company_id or furo.eliminado_em is not None:
        raise HTTPException(404, "Furo de sondagem não encontrado")
    return furo


def _validar_projecto(db: Session, company_id: str, project_id: str) -> Project:
    projeto = db.get(Project, project_id)
    if projeto is None or projeto.company_id != company_id or projeto.eliminado_em is not None:
        raise HTTPException(422, "O projecto indicado não existe na empresa")
    return projeto


def _validar_utilizador(db: Session, company_id: str, user_id: str | None) -> None:
    if not user_id:
        return
    if db.get(User, user_id) is None or db.scalar(select(CompanyUser).where(
            CompanyUser.company_id == company_id, CompanyUser.user_id == user_id)) is None:
        raise HTTPException(422, "O geólogo indicado não pertence à empresa")


def _max_profundidade(db: Session, furo: DrillHole) -> float:
    surveys = db.scalar(select(func.max(DrillSurvey.profundidade)).where(
        DrillSurvey.drill_hole_id == furo.id)) or 0
    intervalos = db.scalar(select(func.max(DrillInterval.ate)).where(
        DrillInterval.drill_hole_id == furo.id)) or 0
    return max(float(surveys), float(intervalos))


def _validar_survey(db: Session, furo: DrillHole, profundidade: float, ignorar_id: str | None = None) -> None:
    if profundidade < 0:
        raise HTTPException(422, "A profundidade do survey não pode ser negativa")
    if furo.profundidade_final is not None and profundidade > furo.profundidade_final:
        raise HTTPException(422, f"A profundidade do survey excede a profundidade final ({furo.profundidade_final} m)")
    consulta = select(DrillSurvey).where(DrillSurvey.drill_hole_id == furo.id,
                                         DrillSurvey.profundidade == profundidade)
    if ignorar_id:
        consulta = consulta.where(DrillSurvey.id != ignorar_id)
    if db.scalar(consulta.limit(1)):
        raise HTTPException(409, "Já existe um survey nesta profundidade")


def _validar_intervalo(db: Session, furo: DrillHole, de: float, ate: float,
                       ignorar_id: str | None = None) -> None:
    if ate <= de:
        raise HTTPException(422, "O fim do intervalo tem de ser maior do que o início")
    if furo.profundidade_final is not None and ate > furo.profundidade_final:
        raise HTTPException(422, f"O intervalo excede a profundidade final ({furo.profundidade_final} m)")
    condicoes = [DrillInterval.drill_hole_id == furo.id, DrillInterval.de < ate, DrillInterval.ate > de]
    if ignorar_id:
        condicoes.append(DrillInterval.id != ignorar_id)
    conflito = db.scalar(select(DrillInterval).where(*condicoes).limit(1))
    if conflito:
        raise HTTPException(409, f"O intervalo sobrepõe-se a outro ({conflito.de}–{conflito.ate} m)")


def _validar_litologia(db: Session, company_id: str, lithology_id: str | None) -> None:
    if not lithology_id:
        return
    litologia = db.get(Lithology, lithology_id)
    if litologia is None or litologia.company_id != company_id:
        raise HTTPException(422, "A litologia indicada não existe na empresa")


@router.get("", response_model=Pagina[FuroSaida], summary="Listar furos de sondagem")
def listar(project_id: str | None = None, estado: str | None = None, q: str | None = None,
           skip: int = 0, limit: int = 50, ctx: Contexto = Depends(exige("drill_holes", "view")),
           db: Session = Depends(get_db)):
    company_id = exigir_empresa(ctx)
    consulta = select(DrillHole).where(DrillHole.company_id == company_id, DrillHole.eliminado_em.is_(None))
    if project_id:
        consulta = consulta.where(DrillHole.project_id == project_id)
    if estado:
        consulta = consulta.where(DrillHole.estado == estado)
    if q:
        termo = f"%{q.strip()}%"
        consulta = consulta.where(or_(DrillHole.codigo.ilike(termo), DrillHole.nome.ilike(termo)))
    total, items = paginar(db, consulta.order_by(DrillHole.codigo), skip, limit)
    return {"total": total, "items": items}


@router.get("/proximo-codigo", summary="Próximo código automático de furo no projecto")
def proximo_codigo(project_id: str, ctx: Contexto = Depends(exige("drill_holes", "create")),
                   db: Session = Depends(get_db)):
    _validar_projecto(db, exigir_empresa(ctx), project_id)
    return {"codigo": proximo_codigo_furo(db, project_id)}


@router.post("", response_model=FuroDetalhe, status_code=201, summary="Criar furo de sondagem")
def criar(dados: FuroCriar, ctx: Contexto = Depends(exige("drill_holes", "create")),
          db: Session = Depends(get_db)):
    company_id = exigir_empresa(ctx)
    _validar_projecto(db, company_id, dados.project_id)
    _validar_utilizador(db, company_id, dados.geologo_id)
    dados.codigo = (dados.codigo or "").strip() or proximo_codigo_furo(db, dados.project_id)
    if db.scalar(select(DrillHole).where(DrillHole.project_id == dados.project_id,
                                         DrillHole.codigo == dados.codigo)):
        raise HTTPException(409, "Já existe um furo com este código no projecto")
    furo = DrillHole(company_id=company_id, **completar_coordenadas(dados.model_dump()))
    db.add(furo)
    db.flush()
    auditar(db, ctx, "criar", "drill_hole", furo.id, depois=serializar(furo))
    db.commit()
    return _detalhe(db, furo)


def _detalhe(db: Session, furo: DrillHole) -> FuroDetalhe:
    projeto = db.get(Project, furo.project_id)
    saida = FuroDetalhe.model_validate(furo)
    saida.projecto_codigo = projeto.codigo if projeto else None
    saida.projecto_nome = projeto.nome if projeto else None
    saida.num_surveys = db.scalar(select(func.count()).select_from(DrillSurvey).where(
        DrillSurvey.drill_hole_id == furo.id)) or 0
    saida.num_intervalos = db.scalar(select(func.count()).select_from(DrillInterval).where(
        DrillInterval.drill_hole_id == furo.id)) or 0
    saida.num_amostras = db.scalar(select(func.count()).select_from(Sample).where(
        Sample.drill_hole_id == furo.id)) or 0
    return saida


@router.get("/{hole_id}", response_model=FuroDetalhe, summary="Consultar furo de sondagem")
def obter(hole_id: str, ctx: Contexto = Depends(exige("drill_holes", "view")),
          db: Session = Depends(get_db)):
    return _detalhe(db, _obter_furo(db, exigir_empresa(ctx), hole_id))


@router.patch("/{hole_id}", response_model=FuroDetalhe, summary="Actualizar furo de sondagem")
def actualizar(hole_id: str, dados: FuroActualizar,
               ctx: Contexto = Depends(exige("drill_holes", "edit")), db: Session = Depends(get_db)):
    company_id = exigir_empresa(ctx)
    furo = _obter_furo(db, company_id, hole_id)
    alteracoes = dados.model_dump(exclude_unset=True)
    if "codigo" in alteracoes and alteracoes["codigo"] != furo.codigo:
        if db.scalar(select(DrillHole).where(DrillHole.project_id == furo.project_id,
                                             DrillHole.codigo == alteracoes["codigo"])):
            raise HTTPException(409, "Já existe um furo com este código no projecto")
    if "geologo_id" in alteracoes:
        _validar_utilizador(db, company_id, alteracoes["geologo_id"])
    if "profundidade_final" in alteracoes or "profundidade_prevista" in alteracoes:
        final = alteracoes.get("profundidade_final", furo.profundidade_final)
        prevista = alteracoes.get("profundidade_prevista", furo.profundidade_prevista)
        if final is not None and prevista is not None and final > prevista:
            raise HTTPException(422, "A profundidade final não pode exceder a profundidade prevista")
        if final is not None:
            maxima = _max_profundidade(db, furo)
            if maxima > final:
                raise HTTPException(
                    422, f"A profundidade final ({final} m) é inferior a registos existentes ({maxima} m)")
    inicio = alteracoes.get("data_inicio", furo.data_inicio)
    fim = alteracoes.get("data_fim", furo.data_fim)
    if inicio and fim and fim < inicio:
        raise HTTPException(422, "data_fim não pode ser anterior a data_inicio")
    if ("latitude" in alteracoes or "longitude" in alteracoes)             and "x" not in alteracoes and "y" not in alteracoes:
        # a posição geográfica mudou e o X/Y não foi indicado: recalcula o UTM
        geo = {"latitude": alteracoes.get("latitude", furo.latitude),
               "longitude": alteracoes.get("longitude", furo.longitude)}
        if completar_coordenadas(geo).get("x") is not None:
            alteracoes["x"], alteracoes["y"] = geo["x"], geo["y"]
    antes = serializar(furo)
    for campo, valor in alteracoes.items():
        setattr(furo, campo, valor)
    auditar(db, ctx, "actualizar", "drill_hole", furo.id, antes=antes, depois=serializar(furo))
    db.commit()
    return _detalhe(db, furo)


@router.delete("/{hole_id}", status_code=204, summary="Eliminar furo (soft delete)")
def eliminar(hole_id: str, ctx: Contexto = Depends(exige("drill_holes", "delete")),
             db: Session = Depends(get_db)):
    furo = _obter_furo(db, exigir_empresa(ctx), hole_id)
    antes = serializar(furo)
    furo.eliminado_em = agora()
    auditar(db, ctx, "eliminar", "drill_hole", furo.id, antes=antes)
    db.commit()


# ---------------------------------------------------------------- surveys (trajectória)
@router.get("/{hole_id}/surveys", response_model=list[SurveySaida], summary="Surveys do furo")
def listar_surveys(hole_id: str, ctx: Contexto = Depends(exige("drill_holes", "view")),
                   db: Session = Depends(get_db)):
    furo = _obter_furo(db, exigir_empresa(ctx), hole_id)
    return list(db.scalars(select(DrillSurvey).where(DrillSurvey.drill_hole_id == furo.id)
                           .order_by(DrillSurvey.profundidade)))


@router.post("/{hole_id}/surveys", response_model=SurveySaida, status_code=201, summary="Registar survey")
def criar_survey(hole_id: str, dados: SurveyCriar,
                 ctx: Contexto = Depends(exige("drill_holes", "edit")), db: Session = Depends(get_db)):
    company_id = exigir_empresa(ctx)
    furo = _obter_furo(db, company_id, hole_id)
    _validar_survey(db, furo, dados.profundidade)
    survey = DrillSurvey(company_id=company_id, drill_hole_id=furo.id, **dados.model_dump())
    db.add(survey)
    db.flush()
    auditar(db, ctx, "criar", "drill_survey", survey.id, depois=serializar(survey))
    db.commit()
    return survey


@router.patch("/{hole_id}/surveys/{survey_id}", response_model=SurveySaida, summary="Corrigir survey")
def actualizar_survey(hole_id: str, survey_id: str, dados: SurveyCriar,
                      ctx: Contexto = Depends(exige("drill_holes", "edit")),
                      db: Session = Depends(get_db)):
    company_id = exigir_empresa(ctx)
    furo = _obter_furo(db, company_id, hole_id)
    survey = db.get(DrillSurvey, survey_id)
    if survey is None or survey.drill_hole_id != furo.id:
        raise HTTPException(404, "Survey não encontrado")
    _validar_survey(db, furo, dados.profundidade, ignorar_id=survey.id)
    antes = serializar(survey)
    for campo, valor in dados.model_dump().items():
        setattr(survey, campo, valor)
    auditar(db, ctx, "actualizar", "drill_survey", survey.id, antes=antes, depois=serializar(survey))
    db.commit()
    return survey


@router.delete("/{hole_id}/surveys/{survey_id}", status_code=204, summary="Apagar survey")
def apagar_survey(hole_id: str, survey_id: str, ctx: Contexto = Depends(exige("drill_holes", "edit")),
                  db: Session = Depends(get_db)):
    furo = _obter_furo(db, exigir_empresa(ctx), hole_id)
    survey = db.get(DrillSurvey, survey_id)
    if survey is None or survey.drill_hole_id != furo.id:
        raise HTTPException(404, "Survey não encontrado")
    auditar(db, ctx, "eliminar", "drill_survey", survey.id, antes=serializar(survey))
    db.delete(survey)
    db.commit()


@router.get("/{hole_id}/trajectory", response_model=TrajectoriaSaida, summary="Trajectória 3D do furo")
def obter_trajectoria(hole_id: str, ctx: Contexto = Depends(exige("drill_holes", "view")),
                      db: Session = Depends(get_db)):
    furo = _obter_furo(db, exigir_empresa(ctx), hole_id)
    surveys = list(db.scalars(select(DrillSurvey).where(DrillSurvey.drill_hole_id == furo.id)))
    return trajectoria(furo, surveys)


# ---------------------------------------------------------------- intervalos geológicos
@router.get("/{hole_id}/intervals", response_model=list[IntervaloSaida], summary="Intervalos do furo")
def listar_intervalos(hole_id: str, ctx: Contexto = Depends(exige("drill_holes", "view")),
                      db: Session = Depends(get_db)):
    furo = _obter_furo(db, exigir_empresa(ctx), hole_id)
    return list(db.scalars(select(DrillInterval).where(DrillInterval.drill_hole_id == furo.id)
                           .order_by(DrillInterval.de)))


@router.post("/{hole_id}/intervals", response_model=IntervaloSaida, status_code=201,
             summary="Registar intervalo geológico")
def criar_intervalo(hole_id: str, dados: IntervaloCriar,
                    ctx: Contexto = Depends(exige("drill_holes", "edit")), db: Session = Depends(get_db)):
    company_id = exigir_empresa(ctx)
    furo = _obter_furo(db, company_id, hole_id)
    _validar_intervalo(db, furo, dados.de, dados.ate)
    _validar_litologia(db, company_id, dados.lithology_id)
    intervalo = DrillInterval(company_id=company_id, drill_hole_id=furo.id, **dados.model_dump())
    db.add(intervalo)
    db.flush()
    auditar(db, ctx, "criar", "drill_interval", intervalo.id, depois=serializar(intervalo))
    db.commit()
    return intervalo


@router.patch("/{hole_id}/intervals/{interval_id}", response_model=IntervaloSaida,
              summary="Actualizar intervalo geológico")
def actualizar_intervalo(hole_id: str, interval_id: str, dados: IntervaloActualizar,
                         ctx: Contexto = Depends(exige("drill_holes", "edit")),
                         db: Session = Depends(get_db)):
    company_id = exigir_empresa(ctx)
    furo = _obter_furo(db, company_id, hole_id)
    intervalo = db.get(DrillInterval, interval_id)
    if intervalo is None or intervalo.drill_hole_id != furo.id:
        raise HTTPException(404, "Intervalo não encontrado")
    alteracoes = dados.model_dump(exclude_unset=True)
    de = alteracoes.get("de", intervalo.de)
    ate = alteracoes.get("ate", intervalo.ate)
    _validar_intervalo(db, furo, de, ate, ignorar_id=intervalo.id)
    if "lithology_id" in alteracoes:
        _validar_litologia(db, company_id, alteracoes["lithology_id"])
    antes = serializar(intervalo)
    for campo, valor in alteracoes.items():
        setattr(intervalo, campo, valor)
    auditar(db, ctx, "actualizar", "drill_interval", intervalo.id, antes=antes, depois=serializar(intervalo))
    db.commit()
    return intervalo


@router.delete("/{hole_id}/intervals/{interval_id}", status_code=204, summary="Apagar intervalo")
def apagar_intervalo(hole_id: str, interval_id: str, ctx: Contexto = Depends(exige("drill_holes", "edit")),
                     db: Session = Depends(get_db)):
    furo = _obter_furo(db, exigir_empresa(ctx), hole_id)
    intervalo = db.get(DrillInterval, interval_id)
    if intervalo is None or intervalo.drill_hole_id != furo.id:
        raise HTTPException(404, "Intervalo não encontrado")
    auditar(db, ctx, "eliminar", "drill_interval", intervalo.id, antes=serializar(intervalo))
    db.delete(intervalo)
    db.commit()
