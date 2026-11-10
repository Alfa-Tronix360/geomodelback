"""Perfis iniciais e matriz de permissões, semeados por empresa."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Permission, Role, RolePermission

MODULOS = {
    "companies": "Empresas",
    "users": "Utilizadores e permissões",
    "projects": "Projectos",
    "drill_holes": "Sondagens",
    "samples": "Amostras",
    "laboratories": "Laboratórios",
    "assays": "Resultados laboratoriais",
    "models": "Modelação 3D",
    "resources": "Estimativa de recursos",
    "dashboard": "Dashboard",
    "audit": "Auditoria",
    "imports": "Importação de dados",
}
ACCOES = ("view", "create", "edit", "delete", "validate", "import", "export")

DESCRICOES_ACCao = {
    "view": "consultar", "create": "criar", "edit": "editar", "delete": "apagar",
    "validate": "validar", "import": "importar", "export": "exportar",
}


def _p(modulo: str, *accoes: str) -> set[str]:
    return {f"{modulo}:{a}" for a in accoes}


TUDO = {"*"}

PERFIS: dict[str, dict] = {
    "super_admin": {"nome": "Super Administrador CLACS", "permissoes": TUDO},
    "company_admin": {"nome": "Administrador da empresa", "permissoes": TUDO},
    "project_manager": {
        "nome": "Gestor de projecto",
        "permissoes": _p("projects", "view", "create", "edit", "delete", "export")
        | _p("drill_holes", "view", "create", "edit", "delete", "import", "export")
        | _p("samples", "view", "create", "edit", "delete", "export")
        | _p("laboratories", "view") | _p("assays", "view", "export")
        | _p("models", "view", "create", "edit", "delete")
        | _p("resources", "view", "export") | _p("dashboard", "view")
        | _p("imports", "view", "import") | _p("users", "view"),
    },
    "geologist": {
        "nome": "Geólogo",
        "permissoes": _p("projects", "view")
        | _p("drill_holes", "view", "create", "edit", "delete", "import", "export")
        | _p("samples", "view", "create", "edit", "delete")
        | _p("laboratories", "view") | _p("assays", "view")
        | _p("models", "view", "create", "edit", "delete", "validate")
        | _p("resources", "view") | _p("dashboard", "view") | _p("imports", "view", "import"),
    },
    "drill_technician": {
        "nome": "Técnico de sondagem",
        "permissoes": _p("projects", "view") | _p("drill_holes", "view", "create", "edit", "import")
        | _p("samples", "view", "create") | _p("dashboard", "view") | _p("imports", "view", "import"),
    },
    "lab_technician": {
        "nome": "Técnico de laboratório",
        "permissoes": _p("projects", "view") | _p("drill_holes", "view") | _p("samples", "view")
        | _p("laboratories", "view", "create", "edit")
        | _p("assays", "view", "create", "edit", "delete", "validate", "import", "export")
        | _p("dashboard", "view") | _p("imports", "view", "import"),
    },
    "mining_engineer": {
        "nome": "Engenheiro de minas",
        "permissoes": _p("projects", "view") | _p("drill_holes", "view") | _p("samples", "view")
        | _p("assays", "view") | _p("models", "view", "validate")
        | _p("resources", "view", "create", "edit", "delete", "validate", "export")
        | _p("dashboard", "view") | _p("imports", "view", "import"),
    },
    "resource_analyst": {
        "nome": "Analista de recursos",
        "permissoes": _p("projects", "view") | _p("drill_holes", "view") | _p("samples", "view")
        | _p("assays", "view") | _p("models", "view")
        | _p("resources", "view", "create", "edit", "delete", "validate", "export")
        | _p("dashboard", "view") | _p("imports", "view", "import"),
    },
    "auditor": {
        "nome": "Auditor",
        "permissoes": _p("companies", "view") | _p("users", "view")
        | _p("projects", "view", "export") | _p("drill_holes", "view", "export")
        | _p("samples", "view", "export") | _p("laboratories", "view") | _p("assays", "view", "export")
        | _p("models", "view", "export") | _p("resources", "view", "export")
        | _p("dashboard", "view") | _p("audit", "view", "export") | _p("imports", "view"),
    },
    "viewer": {
        "nome": "Utilizador de consulta",
        "permissoes": _p("projects", "view") | _p("drill_holes", "view") | _p("samples", "view")
        | _p("laboratories", "view") | _p("assays", "view") | _p("models", "view")
        | _p("resources", "view") | _p("dashboard", "view"),
    },
}


def semear_permissoes(db: Session) -> dict[tuple[str, str], Permission]:
    existentes = {(p.modulo, p.accao): p for p in db.scalars(select(Permission))}
    for modulo in MODULOS:
        for accao in ACCOES:
            if (modulo, accao) not in existentes:
                p = Permission(modulo=modulo, accao=accao,
                               descricao=f"Permite {DESCRICOES_ACCao[accao]} {MODULOS[modulo].lower()}")
                db.add(p)
                existentes[(modulo, accao)] = p
    db.flush()
    return existentes


def criar_perfis_empresa(db: Session, company_id: str) -> list[Role]:
    """Cria (ou actualiza) os perfis padrão de uma empresa e as suas permissões."""
    permissoes = semear_permissoes(db)
    perfis: list[Role] = []
    for codigo, definicao in PERFIS.items():
        role = db.scalar(select(Role).where(Role.company_id == company_id, Role.codigo == codigo))
        if role is None:
            role = Role(company_id=company_id, codigo=codigo, nome=definicao["nome"],
                        descricao=f"Perfil padrão: {definicao['nome']}", sistema=True)
            db.add(role)
            db.flush()
        # Reaplica a matriz padrão (idempotente) para não deixar perfis de sistema sem permissões.
        for rp in list(db.scalars(select(RolePermission).where(RolePermission.role_id == role.id))):
            db.delete(rp)
        db.flush()
        desejadas = definicao["permissoes"]
        for (modulo, accao), permissao in permissoes.items():
            if "*" in desejadas or f"{modulo}:{accao}" in desejadas:
                db.add(RolePermission(role_id=role.id, permission_id=permissao.id))
        perfis.append(role)
    db.flush()
    return perfis


def permissoes_do_papel(db: Session, role_id: str) -> list[str]:
    linhas = db.execute(
        select(Permission.modulo, Permission.accao)
        .join(RolePermission, RolePermission.permission_id == Permission.id)
        .where(RolePermission.role_id == role_id)
    ).all()
    return sorted(f"{m}:{a}" for m, a in linhas)
