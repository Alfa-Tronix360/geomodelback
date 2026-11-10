"""Indicadores do dashboard, calculados a partir dos dados de cada empresa."""
from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import Contexto, exige, exigir_empresa
from app.models import (
    AssayResult, DrillHole, GeologicalModel, Project, ResourceEstimate, Sample,
)
from app.schemas import DashboardSaida

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])


def _contar(db: Session, consulta) -> int:
    return int(db.scalar(select(func.count()).select_from(consulta.subquery())) or 0)


@router.get("", response_model=DashboardSaida, summary="Indicadores do dashboard")
def indicadores(ctx: Contexto = Depends(exige("dashboard", "view")), db: Session = Depends(get_db)):
    company_id = exigir_empresa(ctx)

    projectos_activos = _contar(db, select(Project.id).where(
        Project.company_id == company_id, Project.eliminado_em.is_(None),
        Project.estado == "activo"))
    area = db.scalar(select(func.coalesce(func.sum(Project.area_km2), 0.0)).where(
        Project.company_id == company_id, Project.eliminado_em.is_(None))) or 0.0

    furos = select(DrillHole.id).where(
        DrillHole.company_id == company_id, DrillHole.eliminado_em.is_(None))
    sondagens = _contar(db, furos)
    metros = db.scalar(select(func.coalesce(func.sum(DrillHole.profundidade_final), 0.0)).where(
        DrillHole.company_id == company_id, DrillHole.eliminado_em.is_(None))) or 0.0

    amostras = _contar(db, select(Sample.id).where(
        Sample.company_id == company_id, Sample.eliminado_em.is_(None)))
    resultados = _contar(db, select(AssayResult.id).where(AssayResult.company_id == company_id))
    validados = _contar(db, select(AssayResult.id).where(
        AssayResult.company_id == company_id, AssayResult.estado == "validado"))
    modelos = _contar(db, select(GeologicalModel.id).where(
        GeologicalModel.company_id == company_id, GeologicalModel.eliminado_em.is_(None)))
    estimativas = _contar(db, select(ResourceEstimate.id).where(
        ResourceEstimate.company_id == company_id))

    tonelagem = db.scalar(select(func.coalesce(func.sum(ResourceEstimate.tonelagem), 0.0)).where(
        ResourceEstimate.company_id == company_id,
        ResourceEstimate.estado.in_(("validado", "aprovado")))) or 0.0
    metal = db.scalar(select(func.coalesce(func.sum(ResourceEstimate.metal_contido), 0.0)).where(
        ResourceEstimate.company_id == company_id,
        ResourceEstimate.estado.in_(("validado", "aprovado")))) or 0.0

    estados = db.execute(
        select(DrillHole.estado, func.count(DrillHole.id)).where(
            DrillHole.company_id == company_id, DrillHole.eliminado_em.is_(None))
        .group_by(DrillHole.estado)
    ).all()

    minerais = db.execute(
        select(
            Project.mineral,
            func.count(Project.id),
            func.coalesce(func.sum(Project.area_km2), 0.0),
        ).where(Project.company_id == company_id, Project.eliminado_em.is_(None))
        .group_by(Project.mineral)
        .order_by(func.count(Project.id).desc())
    ).all()

    return DashboardSaida(
        projectos_activos=projectos_activos,
        area_explorada_km2=round(float(area), 2),
        sondagens=sondagens,
        metros_perfurados=round(float(metros), 2),
        amostras=amostras,
        resultados_laboratoriais=resultados,
        resultados_validados=validados,
        modelos_geologicos=modelos,
        estimativas=estimativas,
        tonelagem_total=round(float(tonelagem), 2),
        metal_contido_total=round(float(metal), 4),
        por_estado_sondagem={estado: int(total) for estado, total in estados},
        por_mineral=[
            {"mineral": mineral or "não especificado", "projectos": int(total),
             "area_km2": round(float(area_mineral or 0), 2)}
            for mineral, total, area_mineral in minerais
        ],
    )
