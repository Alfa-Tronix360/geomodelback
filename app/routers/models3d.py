"""Modelação geológica 3D: modelos, domínios e versões de ficheiro."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.common import paginar
from app.database import get_db
from app.deps import Contexto, exige, exigir_empresa
from app.models import (
    GeologicalDomain, GeologicalModel, Lithology, ModelVersion, Project, agora,
)
from app.schemas import (
    DominioActualizar, DominioCriar, DominioSaida, ModeloActualizar, ModeloCriar, ModeloSaida,
    Pagina, VersaoCriar, VersaoSaida,
)
from app.services.auditoria import auditar, serializar

router = APIRouter(prefix="/models", tags=["Modelação 3D"])


def _obter(db: Session, company_id: str, model_id: str) -> GeologicalModel:
    modelo = db.get(GeologicalModel, model_id)
    if modelo is None or modelo.company_id != company_id or modelo.eliminado_em is not None:
        raise HTTPException(404, "Modelo geológico não encontrado")
    return modelo


def _projecto(db: Session, company_id: str, project_id: str) -> Project:
    projeto = db.get(Project, project_id)
    if projeto is None or projeto.company_id != company_id or projeto.eliminado_em is not None:
        raise HTTPException(422, "O projecto indicado não existe na empresa")
    return projeto


def _dominio(db: Session, company_id: str, model_id: str, domain_id: str) -> GeologicalDomain:
    dominio = db.get(GeologicalDomain, domain_id)
    if dominio is None or dominio.company_id != company_id or dominio.model_id != model_id:
        raise HTTPException(404, "Domínio geológico não encontrado")
    return dominio


def _versao(db: Session, company_id: str, model_id: str, version_id: str) -> ModelVersion:
    versao = db.get(ModelVersion, version_id)
    if versao is None or versao.company_id != company_id or versao.model_id != model_id:
        raise HTTPException(404, "Versão do modelo não encontrada")
    return versao


def _validar_litologia(db: Session, company_id: str, lithology_id: str | None) -> None:
    if not lithology_id:
        return
    litologia = db.get(Lithology, lithology_id)
    if litologia is None or litologia.company_id != company_id:
        raise HTTPException(422, "A litologia indicada não existe na empresa")


@router.get("", response_model=Pagina[ModeloSaida], summary="Listar modelos geológicos")
def listar(project_id: str | None = None, estado: str | None = None, q: str | None = None,
           skip: int = 0, limit: int = 50,
           ctx: Contexto = Depends(exige("models", "view")), db: Session = Depends(get_db)):
    company_id = exigir_empresa(ctx)
    consulta = select(GeologicalModel).where(
        GeologicalModel.company_id == company_id, GeologicalModel.eliminado_em.is_(None))
    if project_id:
        consulta = consulta.where(GeologicalModel.project_id == project_id)
    if estado:
        consulta = consulta.where(GeologicalModel.estado == estado)
    if q:
        consulta = consulta.where(GeologicalModel.nome.ilike(f"%{q.strip()}%"))
    total, items = paginar(db, consulta.order_by(GeologicalModel.nome), skip, limit)
    return {"total": total, "items": items}


@router.post("", response_model=ModeloSaida, status_code=201, summary="Criar modelo geológico")
def criar(dados: ModeloCriar, ctx: Contexto = Depends(exige("models", "create")),
          db: Session = Depends(get_db)):
    company_id = exigir_empresa(ctx)
    _projecto(db, company_id, dados.project_id)
    if db.scalar(select(GeologicalModel).where(
            GeologicalModel.project_id == dados.project_id, GeologicalModel.nome == dados.nome)):
        raise HTTPException(409, "Já existe um modelo com este nome no projecto")
    modelo = GeologicalModel(company_id=company_id, criado_por=ctx.utilizador.id, **dados.model_dump())
    db.add(modelo)
    db.flush()
    auditar(db, ctx, "criar", "geological_model", modelo.id, depois=serializar(modelo))
    db.commit()
    return modelo


@router.get("/{model_id}", response_model=ModeloSaida, summary="Consultar modelo geológico")
def obter(model_id: str, ctx: Contexto = Depends(exige("models", "view")),
          db: Session = Depends(get_db)):
    return _obter(db, exigir_empresa(ctx), model_id)


@router.patch("/{model_id}", response_model=ModeloSaida, summary="Actualizar modelo geológico")
def actualizar(model_id: str, dados: ModeloActualizar,
               ctx: Contexto = Depends(exige("models", "edit")), db: Session = Depends(get_db)):
    company_id = exigir_empresa(ctx)
    modelo = _obter(db, company_id, model_id)
    alteracoes = dados.model_dump(exclude_unset=True)
    if "nome" in alteracoes and alteracoes["nome"] != modelo.nome:
        if db.scalar(select(GeologicalModel).where(
                GeologicalModel.project_id == modelo.project_id,
                GeologicalModel.nome == alteracoes["nome"])):
            raise HTTPException(409, "Já existe um modelo com este nome no projecto")
    antes = serializar(modelo)
    for campo, valor in alteracoes.items():
        setattr(modelo, campo, valor)
    auditar(db, ctx, "actualizar", "geological_model", modelo.id, antes=antes,
            depois=serializar(modelo))
    db.commit()
    return modelo


@router.delete("/{model_id}", status_code=204, summary="Eliminar modelo (soft delete)")
def eliminar(model_id: str, ctx: Contexto = Depends(exige("models", "delete")),
             db: Session = Depends(get_db)):
    modelo = _obter(db, exigir_empresa(ctx), model_id)
    antes = serializar(modelo)
    modelo.eliminado_em = agora()
    auditar(db, ctx, "eliminar", "geological_model", modelo.id, antes=antes)
    db.commit()


# ---------------------------------------------------------------- domínios
@router.get("/{model_id}/domains", response_model=list[DominioSaida], summary="Domínios do modelo")
def listar_dominios(model_id: str, ctx: Contexto = Depends(exige("models", "view")),
                    db: Session = Depends(get_db)):
    modelo = _obter(db, exigir_empresa(ctx), model_id)
    return list(db.scalars(select(GeologicalDomain).where(
        GeologicalDomain.model_id == modelo.id).order_by(GeologicalDomain.codigo)))


@router.post("/{model_id}/domains", response_model=DominioSaida, status_code=201,
             summary="Criar domínio geológico")
def criar_dominio(model_id: str, dados: DominioCriar,
                  ctx: Contexto = Depends(exige("models", "edit")), db: Session = Depends(get_db)):
    company_id = exigir_empresa(ctx)
    modelo = _obter(db, company_id, model_id)
    _validar_litologia(db, company_id, dados.lithology_id)
    if db.scalar(select(GeologicalDomain).where(
            GeologicalDomain.model_id == modelo.id, GeologicalDomain.codigo == dados.codigo)):
        raise HTTPException(409, "Já existe um domínio com este código no modelo")
    dominio = GeologicalDomain(company_id=company_id, model_id=modelo.id, **dados.model_dump())
    db.add(dominio)
    db.flush()
    auditar(db, ctx, "criar", "geological_domain", dominio.id, depois=serializar(dominio))
    db.commit()
    return dominio


@router.patch("/{model_id}/domains/{domain_id}", response_model=DominioSaida,
              summary="Actualizar domínio geológico")
def actualizar_dominio(model_id: str, domain_id: str, dados: DominioActualizar,
                       ctx: Contexto = Depends(exige("models", "edit")),
                       db: Session = Depends(get_db)):
    company_id = exigir_empresa(ctx)
    _obter(db, company_id, model_id)
    dominio = _dominio(db, company_id, model_id, domain_id)
    alteracoes = dados.model_dump(exclude_unset=True)
    if "lithology_id" in alteracoes:
        _validar_litologia(db, company_id, alteracoes["lithology_id"])
    if "codigo" in alteracoes and alteracoes["codigo"] != dominio.codigo:
        if db.scalar(select(GeologicalDomain).where(
                GeologicalDomain.model_id == model_id,
                GeologicalDomain.codigo == alteracoes["codigo"])):
            raise HTTPException(409, "Já existe um domínio com este código no modelo")
    antes = serializar(dominio)
    for campo, valor in alteracoes.items():
        setattr(dominio, campo, valor)
    auditar(db, ctx, "actualizar", "geological_domain", dominio.id, antes=antes,
            depois=serializar(dominio))
    db.commit()
    return dominio


@router.delete("/{model_id}/domains/{domain_id}", status_code=204, summary="Apagar domínio")
def apagar_dominio(model_id: str, domain_id: str,
                   ctx: Contexto = Depends(exige("models", "edit")), db: Session = Depends(get_db)):
    company_id = exigir_empresa(ctx)
    _obter(db, company_id, model_id)
    dominio = _dominio(db, company_id, model_id, domain_id)
    auditar(db, ctx, "eliminar", "geological_domain", dominio.id, antes=serializar(dominio))
    db.delete(dominio)
    db.commit()


# ---------------------------------------------------------------- versões
@router.get("/{model_id}/versions", response_model=list[VersaoSaida], summary="Versões do modelo")
def listar_versoes(model_id: str, ctx: Contexto = Depends(exige("models", "view")),
                   db: Session = Depends(get_db)):
    modelo = _obter(db, exigir_empresa(ctx), model_id)
    return list(db.scalars(select(ModelVersion).where(
        ModelVersion.model_id == modelo.id).order_by(ModelVersion.numero_versao.desc())))


@router.post("/{model_id}/versions", response_model=VersaoSaida, status_code=201,
             summary="Criar versão do modelo")
def criar_versao(model_id: str, dados: VersaoCriar,
                 ctx: Contexto = Depends(exige("models", "edit")), db: Session = Depends(get_db)):
    company_id = exigir_empresa(ctx)
    modelo = _obter(db, company_id, model_id)
    numero = dados.numero_versao or (modelo.versao_actual + 1)
    if db.scalar(select(ModelVersion).where(
            ModelVersion.model_id == modelo.id, ModelVersion.numero_versao == numero)):
        raise HTTPException(409, f"Já existe a versão {numero} para este modelo")
    if dados.estado == "validado" and not ctx.superadmin \
            and ("models", "validate") not in ctx.permissoes:
        raise HTTPException(403, "Sem permissão para validar versões do modelo")
    valores = dados.model_dump(exclude={"numero_versao"})
    versao = ModelVersion(company_id=company_id, model_id=modelo.id, numero_versao=numero,
                          criado_por=ctx.utilizador.id, **valores)
    if dados.estado == "validado":
        versao.validado_por = ctx.utilizador.id
        versao.validado_em = agora()
        modelo.estado = "validado"
    modelo.versao_actual = max(modelo.versao_actual, numero)
    db.add(versao)
    db.flush()
    auditar(db, ctx, "criar", "model_version", versao.id, depois=serializar(versao))
    db.commit()
    return versao


@router.post("/{model_id}/versions/{version_id}/validate", response_model=VersaoSaida,
             summary="Validar versão do modelo")
def validar_versao(model_id: str, version_id: str,
                   ctx: Contexto = Depends(exige("models", "validate")),
                   db: Session = Depends(get_db)):
    company_id = exigir_empresa(ctx)
    modelo = _obter(db, company_id, model_id)
    versao = _versao(db, company_id, model_id, version_id)
    antes = serializar(versao)
    versao.estado = "validado"
    versao.validado_por = ctx.utilizador.id
    versao.validado_em = agora()
    modelo.estado = "validado"
    auditar(db, ctx, "validar", "model_version", versao.id, antes=antes,
            depois=serializar(versao))
    db.commit()
    return versao


@router.delete("/{model_id}/versions/{version_id}", status_code=204, summary="Apagar versão")
def apagar_versao(model_id: str, version_id: str,
                  ctx: Contexto = Depends(exige("models", "delete")),
                  db: Session = Depends(get_db)):
    company_id = exigir_empresa(ctx)
    modelo = _obter(db, company_id, model_id)
    versao = _versao(db, company_id, model_id, version_id)
    if versao.estado == "validado":
        raise HTTPException(409, "Versões validadas não podem ser apagadas")
    auditar(db, ctx, "eliminar", "model_version", versao.id, antes=serializar(versao))
    db.delete(versao)
    if modelo.versao_actual == versao.numero_versao:
        maximo = db.scalar(select(func.max(ModelVersion.numero_versao)).where(
            ModelVersion.model_id == modelo.id, ModelVersion.id != versao.id))
        modelo.versao_actual = int(maximo or 0)
    db.commit()
