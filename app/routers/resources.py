"""Estimativas de recursos: cálculo de tonelagem e metal contido."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.common import paginar
from app.database import get_db
from app.deps import Contexto, exige, exigir_empresa
from app.models import GeologicalModel, Project, ResourceEstimate, agora
from app.schemas import (
    EstimativaActualizar, EstimativaCriar, EstimativaSaida, Pagina,
)
from app.services.auditoria import auditar, serializar
from app.services.geo import calcular_estimativa

router = APIRouter(prefix="/resources", tags=["Estimativa de recursos"])


def _obter(db: Session, company_id: str, estimate_id: str) -> ResourceEstimate:
    estimativa = db.get(ResourceEstimate, estimate_id)
    if estimativa is None or estimativa.company_id != company_id:
        raise HTTPException(404, "Estimativa de recursos não encontrada")
    return estimativa


def _validar_projecto(db: Session, company_id: str, project_id: str) -> Project:
    projeto = db.get(Project, project_id)
    if projeto is None or projeto.company_id != company_id or projeto.eliminado_em is not None:
        raise HTTPException(422, "O projecto indicado não existe na empresa")
    return projeto


def _validar_modelo(db: Session, company_id: str, project_id: str,
                    model_id: str | None) -> GeologicalModel | None:
    if not model_id:
        return None
    modelo = db.get(GeologicalModel, model_id)
    if modelo is None or modelo.company_id != company_id or modelo.eliminado_em is not None:
        raise HTTPException(422, "O modelo indicado não existe na empresa")
    if modelo.project_id != project_id:
        raise HTTPException(422, "O modelo não pertence ao projecto indicado")
    return modelo


def _recalcular(valores: dict) -> None:
    tonelagem, metal = calcular_estimativa(
        valores.get("volume_m3"), valores.get("densidade"), valores.get("teor_corte"),
        valores.get("unidade_teor") or "ppm",
    )
    if tonelagem is not None:
        valores["tonelagem"] = tonelagem
    if metal is not None:
        valores["metal_contido"] = metal


@router.get("", response_model=Pagina[EstimativaSaida], summary="Listar estimativas")
def listar(project_id: str | None = None, estado: str | None = None,
           commodity: str | None = None, skip: int = 0, limit: int = 50,
           ctx: Contexto = Depends(exige("resources", "view")), db: Session = Depends(get_db)):
    company_id = exigir_empresa(ctx)
    consulta = select(ResourceEstimate).where(ResourceEstimate.company_id == company_id)
    if project_id:
        consulta = consulta.where(ResourceEstimate.project_id == project_id)
    if estado:
        consulta = consulta.where(ResourceEstimate.estado == estado)
    if commodity:
        consulta = consulta.where(ResourceEstimate.commodity == commodity)
    total, items = paginar(db, consulta.order_by(ResourceEstimate.criado_em.desc()), skip, limit)
    return {"total": total, "items": items}


@router.post("", response_model=EstimativaSaida, status_code=201, summary="Criar estimativa")
def criar(dados: EstimativaCriar, ctx: Contexto = Depends(exige("resources", "create")),
          db: Session = Depends(get_db)):
    company_id = exigir_empresa(ctx)
    _validar_projecto(db, company_id, dados.project_id)
    _validar_modelo(db, company_id, dados.project_id, dados.model_id)
    if dados.estado in ("validado", "aprovado") and not ctx.superadmin \
            and ("resources", "validate") not in ctx.permissoes:
        raise HTTPException(403, "Sem permissão para validar estimativas")
    valores = dados.model_dump()
    _recalcular(valores)
    estimativa = ResourceEstimate(company_id=company_id, criado_por=ctx.utilizador.id, **valores)
    if dados.estado in ("validado", "aprovado"):
        estimativa.validado_por = ctx.utilizador.id
        estimativa.validado_em = agora()
    db.add(estimativa)
    db.flush()
    auditar(db, ctx, "criar", "resource_estimate", estimativa.id, depois=serializar(estimativa))
    db.commit()
    return estimativa


@router.get("/{estimate_id}", response_model=EstimativaSaida, summary="Consultar estimativa")
def obter(estimate_id: str, ctx: Contexto = Depends(exige("resources", "view")),
          db: Session = Depends(get_db)):
    return _obter(db, exigir_empresa(ctx), estimate_id)


@router.patch("/{estimate_id}", response_model=EstimativaSaida, summary="Actualizar estimativa")
def actualizar(estimate_id: str, dados: EstimativaActualizar,
               ctx: Contexto = Depends(exige("resources", "edit")), db: Session = Depends(get_db)):
    company_id = exigir_empresa(ctx)
    estimativa = _obter(db, company_id, estimate_id)
    alteracoes = dados.model_dump(exclude_unset=True)
    if "model_id" in alteracoes:
        _validar_modelo(db, company_id, estimativa.project_id, alteracoes["model_id"])
    if alteracoes.get("estado") in ("validado", "aprovado") and not ctx.superadmin \
            and ("resources", "validate") not in ctx.permissoes:
        raise HTTPException(403, "Sem permissão para validar estimativas")
    combinado = {
        "volume_m3": alteracoes.get("volume_m3", estimativa.volume_m3),
        "densidade": alteracoes.get("densidade", estimativa.densidade),
        "teor_corte": alteracoes.get("teor_corte", estimativa.teor_corte),
        "unidade_teor": alteracoes.get("unidade_teor", estimativa.unidade_teor),
    }
    _recalcular(combinado)
    for campo in ("tonelagem", "metal_contido"):
        if campo in combinado:
            alteracoes[campo] = combinado[campo]
    estado = alteracoes.get("estado")
    antes = serializar(estimativa)
    for campo, valor in alteracoes.items():
        setattr(estimativa, campo, valor)
    if estado in ("validado", "aprovado"):
        estimativa.validado_por = ctx.utilizador.id
        estimativa.validado_em = agora()
    elif estado is not None:
        estimativa.validado_por = None
        estimativa.validado_em = None
    auditar(db, ctx, "actualizar", "resource_estimate", estimativa.id, antes=antes,
            depois=serializar(estimativa))
    db.commit()
    return estimativa


@router.post("/{estimate_id}/validate", response_model=EstimativaSaida,
             summary="Validar estimativa")
def validar(estimate_id: str, ctx: Contexto = Depends(exige("resources", "validate")),
            db: Session = Depends(get_db)):
    estimativa = _obter(db, exigir_empresa(ctx), estimate_id)
    antes = serializar(estimativa)
    estimativa.estado = "validado"
    estimativa.validado_por = ctx.utilizador.id
    estimativa.validado_em = agora()
    auditar(db, ctx, "validar", "resource_estimate", estimativa.id, antes=antes,
            depois=serializar(estimativa))
    db.commit()
    return estimativa


@router.delete("/{estimate_id}", status_code=204, summary="Apagar estimativa")
def eliminar(estimate_id: str, ctx: Contexto = Depends(exige("resources", "delete")),
             db: Session = Depends(get_db)):
    estimativa = _obter(db, exigir_empresa(ctx), estimate_id)
    auditar(db, ctx, "eliminar", "resource_estimate", estimativa.id, antes=serializar(estimativa))
    db.delete(estimativa)
    db.commit()
