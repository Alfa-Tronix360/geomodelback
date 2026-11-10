"""Dependências de autenticação, empresa activa e permissões."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated

import jwt
from fastapi import Depends, Header, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Company, CompanyUser, Permission, Role, RolePermission, User
from app.security import descodificar_token

bearer = HTTPBearer(auto_error=False)


@dataclass
class Contexto:
    utilizador: User
    empresa: Company | None
    papel: Role | None
    permissoes: set[tuple[str, str]]
    superadmin: bool

    @property
    def company_id(self) -> str | None:
        return self.empresa.id if self.empresa else None


def utilizador_actual(
    credenciais: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: Session = Depends(get_db),
) -> User:
    if credenciais is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Autenticação necessária", headers={"WWW-Authenticate": "Bearer"})
    try:
        payload = descodificar_token(credenciais.credentials)
    except jwt.PyJWTError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Token inválido ou expirado",
                            headers={"WWW-Authenticate": "Bearer"})
    utilizador = db.get(User, payload.get("sub"))
    if utilizador is None or not utilizador.activo:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Utilizador inexistente ou inactivo")
    return utilizador


def _permissoes(db: Session, role_id: str) -> set[tuple[str, str]]:
    linhas = db.execute(
        select(Permission.modulo, Permission.accao)
        .join(RolePermission, RolePermission.permission_id == Permission.id)
        .where(RolePermission.role_id == role_id)
    ).all()
    return {(modulo, accao) for modulo, accao in linhas}


def contexto_actual(
    x_company_id: Annotated[str | None, Header(alias="X-Company-ID")] = None,
    utilizador: User = Depends(utilizador_actual),
    db: Session = Depends(get_db),
) -> Contexto:
    """Resolve a empresa activa.

    - com `X-Company-ID`, valida a pertença do utilizador;
    - sem cabeçalho e com uma única empresa, usa essa;
    - com várias, exige o cabeçalho;
    - o super administrador pode actuar sem empresa (gestão de clientes).
    """
    if x_company_id:
        empresa = db.get(Company, x_company_id)
        if empresa is None or empresa.eliminado_em is not None:
            raise HTTPException(404, "Empresa não encontrada")
        if not empresa.activa:
            raise HTTPException(403, "Empresa inactiva")
        membro = db.scalar(select(CompanyUser).where(
            CompanyUser.company_id == empresa.id, CompanyUser.user_id == utilizador.id,
            CompanyUser.activo.is_(True)))
        if membro is None and not utilizador.superadmin:
            raise HTTPException(403, "Não tem acesso a esta empresa")
        papel = db.get(Role, membro.role_id) if membro else None
        return Contexto(utilizador, empresa, papel, _permissoes(db, papel.id) if papel else set(),
                        utilizador.superadmin)

    if utilizador.superadmin:
        return Contexto(utilizador, None, None, set(), True)

    membros = list(db.scalars(select(CompanyUser).where(
        CompanyUser.user_id == utilizador.id, CompanyUser.activo.is_(True))))
    if not membros:
        raise HTTPException(403, "O utilizador não pertence a nenhuma empresa")
    if len(membros) > 1:
        raise HTTPException(400, "Pertence a várias empresas: indique X-Company-ID")
    membro = membros[0]
    empresa = db.get(Company, membro.company_id)
    if empresa is None or not empresa.activa or empresa.eliminado_em is not None:
        raise HTTPException(403, "Empresa inactiva ou indisponível")
    papel = db.get(Role, membro.role_id)
    return Contexto(utilizador, empresa, papel, _permissoes(db, papel.id) if papel else set(),
                    utilizador.superadmin)


def exigir_empresa(ctx: Contexto) -> str:
    if ctx.empresa is None:
        raise HTTPException(400, "Indique a empresa no cabeçalho X-Company-ID")
    return ctx.empresa.id


def exige(modulo: str, accao: str):
    def dependencia(ctx: Contexto = Depends(contexto_actual)) -> Contexto:
        if ctx.superadmin:
            return ctx
        if ctx.empresa is None:
            raise HTTPException(400, "Indique a empresa no cabeçalho X-Company-ID")
        if (modulo, accao) not in ctx.permissoes:
            raise HTTPException(403, f"Sem permissão para {accao} em {modulo}")
        return ctx
    return dependencia


def exige_superadmin(ctx: Contexto = Depends(contexto_actual)) -> Contexto:
    if not ctx.superadmin:
        raise HTTPException(403, "Reservado ao super administrador CLACS")
    return ctx
