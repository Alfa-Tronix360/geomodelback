"""Utilizadores da empresa, perfis e permissões."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import Contexto, exige, exigir_empresa
from app.models import CompanyUser, Permission, Role, RolePermission, User
from app.schemas import (
    MembroActualizar, MembroSaida, PerfilActualizar, PerfilCriar, PerfilSaida, PermissaoSaida,
    UtilizadorActualizar, UtilizadorCriar, UtilizadorSaida,
)
from app.security import hash_senha
from app.services.auditoria import auditar, serializar
from app.services.perfis import permissoes_do_papel

router = APIRouter(tags=["Utilizadores e permissões"])


def _membro(db: Session, company_id: str, user_id: str) -> CompanyUser:
    membro = db.scalar(select(CompanyUser).where(
        CompanyUser.company_id == company_id, CompanyUser.user_id == user_id))
    if membro is None:
        raise HTTPException(404, "Utilizador não pertence a esta empresa")
    return membro


def _saida(db: Session, membro: CompanyUser) -> MembroSaida:
    utilizador = db.get(User, membro.user_id)
    papel = db.get(Role, membro.role_id)
    return MembroSaida(
        id=membro.id, user_id=utilizador.id, nome=utilizador.nome, email=utilizador.email,
        role_id=papel.id, role_codigo=papel.codigo, role_nome=papel.nome, activo=membro.activo,
        criado_em=membro.criado_em,
    )


def _perfil(db: Session, papel: Role) -> PerfilSaida:
    return PerfilSaida(
        id=papel.id, codigo=papel.codigo, nome=papel.nome, descricao=papel.descricao,
        sistema=papel.sistema, permissoes=permissoes_do_papel(db, papel.id),
    )


def _permissoes(db: Session, codigos: list[str]) -> list[Permission]:
    if not codigos:
        return []
    validas = {(p.modulo, p.accao): p for p in db.scalars(select(Permission))}
    resultado = []
    for codigo in codigos:
        if ":" not in codigo:
            raise HTTPException(422, f"Permissão inválida: {codigo} (use modulo:accao)")
        modulo, accao = codigo.split(":", 1)
        permissao = validas.get((modulo, accao))
        if permissao is None:
            raise HTTPException(422, f"Permissão desconhecida: {codigo}")
        resultado.append(permissao)
    return resultado


@router.get("/users", response_model=list[MembroSaida], summary="Utilizadores da empresa")
def listar_utilizadores(activo: bool | None = None, ctx: Contexto = Depends(exige("users", "view")),
                        db: Session = Depends(get_db)):
    company_id = exigir_empresa(ctx)
    consulta = select(CompanyUser).where(CompanyUser.company_id == company_id)
    if activo is not None:
        consulta = consulta.where(CompanyUser.activo.is_(activo))
    membros = list(db.scalars(consulta))
    return [_saida(db, m) for m in sorted(membros, key=lambda m: (db.get(User, m.user_id).nome or ""))]


@router.post("/users", response_model=MembroSaida, status_code=201, summary="Criar ou associar utilizador")
def criar_utilizador(dados: UtilizadorCriar, ctx: Contexto = Depends(exige("users", "create")),
                     db: Session = Depends(get_db)):
    company_id = exigir_empresa(ctx)
    papel = db.get(Role, dados.role_id)
    if papel is None or papel.company_id != company_id:
        raise HTTPException(422, "O perfil indicado não pertence à empresa")
    if dados.superadmin and not ctx.superadmin:
        raise HTTPException(403, "Só o super administrador pode criar outro super administrador")

    email = dados.email.strip().lower()
    utilizador = db.scalar(select(User).where(User.email == email))
    if utilizador is None:
        utilizador = User(nome=dados.nome, email=email, senha_hash=hash_senha(dados.senha),
                          telefone=dados.telefone, activo=dados.activo, superadmin=dados.superadmin)
        db.add(utilizador)
        db.flush()
    else:
        if db.scalar(select(CompanyUser).where(
                CompanyUser.company_id == company_id, CompanyUser.user_id == utilizador.id)):
            raise HTTPException(409, "Este utilizador já pertence à empresa")
        if dados.superadmin and not utilizador.superadmin:
            utilizador.superadmin = True
        utilizador.activo = utilizador.activo or dados.activo

    membro = CompanyUser(company_id=company_id, user_id=utilizador.id, role_id=papel.id, activo=dados.activo)
    db.add(membro)
    db.flush()
    auditar(db, ctx, "criar", "company_user", membro.id, depois=serializar(membro))
    db.commit()
    return _saida(db, membro)


@router.patch("/users/{user_id}", response_model=UtilizadorSaida, summary="Actualizar dados do utilizador")
def actualizar_utilizador(user_id: str, dados: UtilizadorActualizar,
                          ctx: Contexto = Depends(exige("users", "edit")),
                          db: Session = Depends(get_db)):
    company_id = exigir_empresa(ctx)
    _membro(db, company_id, user_id)
    utilizador = db.get(User, user_id)
    antes = serializar(utilizador)
    alteracoes = dados.model_dump(exclude_unset=True)
    senha = alteracoes.pop("senha", None)
    for campo, valor in alteracoes.items():
        setattr(utilizador, campo, valor)
    if senha:
        utilizador.senha_hash = hash_senha(senha)
    auditar(db, ctx, "actualizar", "user", utilizador.id, antes=antes, depois=serializar(utilizador))
    db.commit()
    return utilizador


@router.patch("/users/{user_id}/membro", response_model=MembroSaida, summary="Alterar perfil ou estado do membro")
def actualizar_membro(user_id: str, dados: MembroActualizar,
                      ctx: Contexto = Depends(exige("users", "edit")), db: Session = Depends(get_db)):
    company_id = exigir_empresa(ctx)
    membro = _membro(db, company_id, user_id)
    if dados.role_id is not None:
        papel = db.get(Role, dados.role_id)
        if papel is None or papel.company_id != company_id:
            raise HTTPException(422, "O perfil indicado não pertence à empresa")
        membro.role_id = papel.id
    if dados.activo is not None:
        membro.activo = dados.activo
    auditar(db, ctx, "actualizar", "company_user", membro.id, depois=serializar(membro))
    db.commit()
    return _saida(db, membro)


@router.delete("/users/{user_id}", status_code=204, summary="Desactivar utilizador na empresa")
def remover_utilizador(user_id: str, ctx: Contexto = Depends(exige("users", "delete")),
                       db: Session = Depends(get_db)):
    company_id = exigir_empresa(ctx)
    membro = _membro(db, company_id, user_id)
    membro.activo = False
    auditar(db, ctx, "desactivar", "company_user", membro.id)
    db.commit()


@router.get("/roles", response_model=list[PerfilSaida], summary="Perfis da empresa")
def listar_perfis(ctx: Contexto = Depends(exige("users", "view")), db: Session = Depends(get_db)):
    company_id = exigir_empresa(ctx)
    papeis = db.scalars(select(Role).where(Role.company_id == company_id).order_by(Role.nome))
    return [_perfil(db, p) for p in papeis]


@router.post("/roles", response_model=PerfilSaida, status_code=201, summary="Criar perfil")
def criar_perfil(dados: PerfilCriar, ctx: Contexto = Depends(exige("users", "edit")),
                 db: Session = Depends(get_db)):
    company_id = exigir_empresa(ctx)
    if db.scalar(select(Role).where(Role.company_id == company_id, Role.codigo == dados.codigo)):
        raise HTTPException(409, "Já existe um perfil com este código")
    papel = Role(company_id=company_id, codigo=dados.codigo, nome=dados.nome, descricao=dados.descricao)
    db.add(papel)
    db.flush()
    for permissao in _permissoes(db, dados.permissoes):
        db.add(RolePermission(role_id=papel.id, permission_id=permissao.id))
    auditar(db, ctx, "criar", "role", papel.id, depois=serializar(papel))
    db.commit()
    return _perfil(db, papel)


@router.patch("/roles/{role_id}", response_model=PerfilSaida, summary="Actualizar perfil e permissões")
def actualizar_perfil(role_id: str, dados: PerfilActualizar,
                      ctx: Contexto = Depends(exige("users", "edit")), db: Session = Depends(get_db)):
    company_id = exigir_empresa(ctx)
    papel = db.get(Role, role_id)
    if papel is None or papel.company_id != company_id:
        raise HTTPException(404, "Perfil não encontrado")
    antes = serializar(papel)
    alteracoes = dados.model_dump(exclude_unset=True)
    permissoes = alteracoes.pop("permissoes", None)
    for campo, valor in alteracoes.items():
        setattr(papel, campo, valor)
    if permissoes is not None:
        for rp in list(db.scalars(select(RolePermission).where(RolePermission.role_id == papel.id))):
            db.delete(rp)
        db.flush()
        for permissao in _permissoes(db, permissoes):
            db.add(RolePermission(role_id=papel.id, permission_id=permissao.id))
    auditar(db, ctx, "actualizar", "role", papel.id, antes=antes, depois=serializar(papel))
    db.commit()
    return _perfil(db, papel)


@router.delete("/roles/{role_id}", status_code=204, summary="Apagar perfil personalizado")
def apagar_perfil(role_id: str, ctx: Contexto = Depends(exige("users", "edit")),
                  db: Session = Depends(get_db)):
    company_id = exigir_empresa(ctx)
    papel = db.get(Role, role_id)
    if papel is None or papel.company_id != company_id:
        raise HTTPException(404, "Perfil não encontrado")
    if papel.sistema:
        raise HTTPException(409, "Os perfis de sistema não podem ser apagados")
    if db.scalar(select(CompanyUser).where(CompanyUser.role_id == papel.id).limit(1)):
        raise HTTPException(409, "O perfil está atribuído a utilizadores")
    auditar(db, ctx, "eliminar", "role", papel.id, antes=serializar(papel))
    db.delete(papel)
    db.commit()


@router.get("/permissions", response_model=list[PermissaoSaida], summary="Catálogo de permissões")
def listar_permissoes(ctx: Contexto = Depends(exige("users", "view")), db: Session = Depends(get_db)):
    return list(db.scalars(select(Permission).order_by(Permission.modulo, Permission.accao)))
