"""Autenticação: login, perfil e alteração de senha."""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import Contexto, contexto_actual
from app.models import Company, CompanyUser, User
from app.schemas import (
    AlterarSenhaIn, EmpresaResumo, LoginIn, PerfilSessao, SessaoSaida, UtilizadorSaida,
)
from app.security import criar_token, hash_senha, verificar_senha
from app.services.auditoria import auditar

router = APIRouter(prefix="/auth", tags=["Autenticação"])


def _empresas(db: Session, utilizador: User) -> list[Company]:
    if utilizador.superadmin:
        return list(db.scalars(select(Company).where(Company.eliminado_em.is_(None)).order_by(Company.nome)))
    return list(db.scalars(
        select(Company)
        .join(CompanyUser, CompanyUser.company_id == Company.id)
        .where(CompanyUser.user_id == utilizador.id, CompanyUser.activo.is_(True),
               Company.eliminado_em.is_(None))
        .order_by(Company.nome)))


def _resumo(empresa: Company) -> EmpresaResumo:
    return EmpresaResumo.model_validate(empresa)


@router.post("/login", response_model=SessaoSaida, summary="Iniciar sessão")
def login(dados: LoginIn, db: Session = Depends(get_db)):
    email = dados.email.strip().lower()
    utilizador = db.scalar(select(User).where(User.email == email))
    if utilizador is None or not verificar_senha(dados.senha, utilizador.senha_hash):
        raise HTTPException(401, "E-mail ou senha incorrectos")
    if not utilizador.activo:
        raise HTTPException(403, "Conta inactiva. Contacte o administrador.")
    utilizador.ultimo_acesso = datetime.now(timezone.utc)
    db.commit()
    empresas = _empresas(db, utilizador)
    actual = empresas[0] if len(empresas) == 1 else None
    return SessaoSaida(
        access_token=criar_token(utilizador.id),
        utilizador=UtilizadorSaida.model_validate(utilizador),
        empresas=[_resumo(e) for e in empresas],
        empresa_actual=_resumo(actual) if actual else None,
    )


@router.get("/me", response_model=PerfilSessao, summary="Perfil e permissões da sessão")
def me(ctx: Contexto = Depends(contexto_actual), db: Session = Depends(get_db)):
    empresas = _empresas(db, ctx.utilizador)
    return PerfilSessao(
        utilizador=UtilizadorSaida.model_validate(ctx.utilizador),
        empresas=[_resumo(e) for e in empresas],
        empresa_actual=_resumo(ctx.empresa) if ctx.empresa else None,
        papel=ctx.papel.codigo if ctx.papel else None,
        permissoes=sorted(f"{m}:{a}" for m, a in ctx.permissoes) if not ctx.superadmin else ["*"],
    )


@router.post("/alterar-senha", status_code=204, summary="Alterar a própria senha")
def alterar_senha(dados: AlterarSenhaIn, ctx: Contexto = Depends(contexto_actual),
                  db: Session = Depends(get_db)):
    if not verificar_senha(dados.senha_actual, ctx.utilizador.senha_hash):
        raise HTTPException(422, "A senha actual não confere")
    ctx.utilizador.senha_hash = hash_senha(dados.senha_nova)
    auditar(db, ctx, "alterar_senha", "user", ctx.utilizador.id)
    db.commit()
