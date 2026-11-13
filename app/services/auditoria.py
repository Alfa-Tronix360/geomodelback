"""Auditoria de alterações: quem, quando, o quê e os valores antes/depois."""
from __future__ import annotations

from datetime import date, datetime
from typing import Any

from sqlalchemy.orm import Session

from app.deps import Contexto
from app.models import AuditLog


def serializar(obj: Any) -> dict:
    if obj is None:
        return {}
    resultado: dict[str, Any] = {}
    for coluna in obj.__table__.columns:
        valor = getattr(obj, coluna.name)
        if isinstance(valor, (datetime, date)):
            valor = valor.isoformat()
        resultado[coluna.name] = valor
    return resultado


def auditar(
    db: Session,
    ctx: Contexto,
    accao: str,
    entidade: str,
    entidade_id: str | None,
    antes: dict | None = None,
    depois: dict | None = None,
    ip: str | None = None,
) -> None:
    db.add(AuditLog(
        company_id=ctx.company_id,
        user_id=ctx.utilizador.id,
        accao=accao,
        entidade=entidade,
        entidade_id=entidade_id,
        dados_antes=antes,
        dados_depois=depois,
        ip=ip,
    ))
    # avisa (sino) quem tem de agir no passo seguinte do fluxo
    from app.services.notificacoes import apos_auditoria
    apos_auditoria(db, ctx.company_id, ctx.utilizador.id, accao, entidade, antes, depois)
