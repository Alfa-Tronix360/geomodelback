"""Resultados laboratoriais: registo, correcção e validação."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.common import paginar
from app.database import get_db
from app.deps import Contexto, exige, exigir_empresa
from app.models import AssayResult, Laboratory, Sample, agora
from app.schemas import (
    Pagina, ResultadoActualizar, ResultadoCriar, ResultadoSaida,
)
from app.services.auditoria import auditar, serializar

router = APIRouter(prefix="/assays", tags=["Resultados laboratoriais"])


def _obter(db: Session, company_id: str, result_id: str) -> AssayResult:
    resultado = db.get(AssayResult, result_id)
    if resultado is None or resultado.company_id != company_id:
        raise HTTPException(404, "Resultado laboratorial não encontrado")
    return resultado


def _validar_amostra(db: Session, company_id: str, sample_id: str) -> Sample:
    amostra = db.get(Sample, sample_id)
    if amostra is None or amostra.company_id != company_id or amostra.eliminado_em is not None:
        raise HTTPException(422, "A amostra indicada não existe na empresa")
    return amostra


def _validar_laboratorio(db: Session, company_id: str, laboratory_id: str) -> Laboratory:
    laboratorio = db.get(Laboratory, laboratory_id)
    if laboratorio is None or laboratorio.company_id != company_id:
        raise HTTPException(422, "O laboratório indicado não existe na empresa")
    if not laboratorio.activo:
        raise HTTPException(422, "O laboratório indicado está inactivo")
    return laboratorio


def _duplicado(db: Session, sample_id: str, laboratory_id: str, parametro: str,
               metodo: str | None, ignorar_id: str | None = None) -> bool:
    condicoes = [
        AssayResult.sample_id == sample_id,
        AssayResult.laboratory_id == laboratory_id,
        AssayResult.parametro == parametro,
        AssayResult.metodo.is_(None) if metodo is None else AssayResult.metodo == metodo,
    ]
    if ignorar_id:
        condicoes.append(AssayResult.id != ignorar_id)
    return db.scalar(select(AssayResult).where(*condicoes).limit(1)) is not None


def _pode_validar(ctx: Contexto) -> bool:
    return ctx.superadmin or ("assays", "validate") in ctx.permissoes


def _aplicar_estado(resultado: AssayResult, estado: str, ctx: Contexto) -> None:
    if estado == "validado":
        if not _pode_validar(ctx):
            raise HTTPException(403, "Sem permissão para validar resultados laboratoriais")
        resultado.validado_por = ctx.utilizador.id
        resultado.validado_em = agora()
    else:
        resultado.validado_por = None
        resultado.validado_em = None


@router.get("", response_model=Pagina[ResultadoSaida], summary="Listar resultados")
def listar(sample_id: str | None = None, laboratory_id: str | None = None,
           parametro: str | None = None, estado: str | None = None,
           skip: int = 0, limit: int = 50,
           ctx: Contexto = Depends(exige("assays", "view")), db: Session = Depends(get_db)):
    company_id = exigir_empresa(ctx)
    consulta = select(AssayResult).where(AssayResult.company_id == company_id)
    if sample_id:
        consulta = consulta.where(AssayResult.sample_id == sample_id)
    if laboratory_id:
        consulta = consulta.where(AssayResult.laboratory_id == laboratory_id)
    if parametro:
        consulta = consulta.where(AssayResult.parametro == parametro)
    if estado:
        consulta = consulta.where(AssayResult.estado == estado)
    total, items = paginar(db, consulta.order_by(AssayResult.criado_em.desc()), skip, limit)
    return {"total": total, "items": items}


@router.post("", response_model=ResultadoSaida, status_code=201, summary="Registar resultado")
def criar(dados: ResultadoCriar, ctx: Contexto = Depends(exige("assays", "create")),
          db: Session = Depends(get_db)):
    company_id = exigir_empresa(ctx)
    _validar_amostra(db, company_id, dados.sample_id)
    _validar_laboratorio(db, company_id, dados.laboratory_id)
    if _duplicado(db, dados.sample_id, dados.laboratory_id, dados.parametro, dados.metodo):
        raise HTTPException(409, "Já existe um resultado para esta amostra, laboratório, parâmetro e método")
    if dados.estado == "validado" and not _pode_validar(ctx):
        raise HTTPException(403, "Sem permissão para validar resultados laboratoriais")
    resultado = AssayResult(company_id=company_id, **dados.model_dump(exclude={"estado"}))
    resultado.estado = dados.estado
    _aplicar_estado(resultado, dados.estado, ctx)
    db.add(resultado)
    db.flush()
    auditar(db, ctx, "criar", "assay_result", resultado.id, depois=serializar(resultado))
    db.commit()
    return resultado


@router.get("/{result_id}", response_model=ResultadoSaida, summary="Consultar resultado")
def obter(result_id: str, ctx: Contexto = Depends(exige("assays", "view")),
          db: Session = Depends(get_db)):
    return _obter(db, exigir_empresa(ctx), result_id)


@router.patch("/{result_id}", response_model=ResultadoSaida, summary="Actualizar resultado")
def actualizar(result_id: str, dados: ResultadoActualizar,
               ctx: Contexto = Depends(exige("assays", "edit")), db: Session = Depends(get_db)):
    company_id = exigir_empresa(ctx)
    resultado = _obter(db, company_id, result_id)
    alteracoes = dados.model_dump(exclude_unset=True)
    parametro = alteracoes.get("parametro", resultado.parametro)
    metodo = alteracoes.get("metodo", resultado.metodo)
    if _duplicado(db, resultado.sample_id, resultado.laboratory_id, parametro, metodo,
                  ignorar_id=resultado.id):
        raise HTTPException(409, "Já existe um resultado para esta amostra, laboratório, parâmetro e método")
    estado = alteracoes.get("estado")
    antes = serializar(resultado)
    for campo, valor in alteracoes.items():
        if campo == "estado":
            continue
        setattr(resultado, campo, valor)
    if estado is not None:
        resultado.estado = estado
        _aplicar_estado(resultado, estado, ctx)
    auditar(db, ctx, "actualizar", "assay_result", resultado.id, antes=antes,
            depois=serializar(resultado))
    db.commit()
    return resultado


@router.post("/{result_id}/validate", response_model=ResultadoSaida, summary="Validar resultado")
def validar(result_id: str, ctx: Contexto = Depends(exige("assays", "validate")),
            db: Session = Depends(get_db)):
    resultado = _obter(db, exigir_empresa(ctx), result_id)
    antes = serializar(resultado)
    resultado.estado = "validado"
    resultado.validado_por = ctx.utilizador.id
    resultado.validado_em = agora()
    auditar(db, ctx, "validar", "assay_result", resultado.id, antes=antes,
            depois=serializar(resultado))
    db.commit()
    return resultado


@router.delete("/{result_id}", status_code=204, summary="Apagar resultado")
def eliminar(result_id: str, ctx: Contexto = Depends(exige("assays", "delete")),
             db: Session = Depends(get_db)):
    resultado = _obter(db, exigir_empresa(ctx), result_id)
    auditar(db, ctx, "eliminar", "assay_result", resultado.id, antes=serializar(resultado))
    db.delete(resultado)
    db.commit()
