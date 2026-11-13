"""Preparação mínima da base de dados no arranque: permissões e super administrador.

Garante que uma instalação nova (ex.: PostgreSQL vazio no Render) tem sempre um utilizador
para entrar, mesmo que o comando de arranque não corra ``scripts/seed.py``.
"""
from __future__ import annotations

import logging

from sqlalchemy import select

from app.config import get_settings
from app.database import SessionLocal
from app.models import User
from app.security import hash_senha
from app.services.perfis import semear_permissoes

log = logging.getLogger("geomodel.arranque")


def preparar_base_de_dados() -> None:
    settings = get_settings()
    email = settings.admin_email.strip().lower()
    db = SessionLocal()
    try:
        semear_permissoes(db)
        admin = db.scalar(select(User).where(User.email == email))
        if admin is None:
            db.add(User(nome="Administrador", email=email,
                        senha_hash=hash_senha(settings.admin_password),
                        superadmin=True, activo=True))
            log.warning("Super administrador criado: %s", email)
        elif settings.admin_repor_senha:
            # recuperação de acesso: ADMIN_REPOR_SENHA=true repõe a senha a partir de ADMIN_PASSWORD
            admin.senha_hash = hash_senha(settings.admin_password)
            admin.superadmin = True
            admin.activo = True
            log.warning("Senha do super administrador reposta: %s", email)
        # estados automáticos: actualiza os que dependem da data (início/fim a chegar)
        from app.services.estados import recalcular_empresa
        recalcular_empresa(db, com_furos=True)
        db.commit()
    except Exception:
        db.rollback()
        log.exception("Falha a preparar a base de dados no arranque")
    finally:
        db.close()
