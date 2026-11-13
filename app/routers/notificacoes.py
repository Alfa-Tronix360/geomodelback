"""Sino de notificações do utilizador autenticado."""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, field_validator
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import Contexto, contexto_actual
from app.models import Notificacao, agora

router = APIRouter(prefix="/notifications", tags=["Notificações"])


class NotificacaoSaida(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    tipo: str
    titulo: str
    mensagem: str | None
    link: str | None
    lida_em: datetime | None
    criado_em: datetime

    @field_validator("lida_em", "criado_em")
    @classmethod
    def _utc(cls, valor: datetime | None) -> datetime | None:
        # o SQLite devolve a hora sem fuso: é UTC (gravada com agora()), e o navegador tem de o saber
        return valor.replace(tzinfo=timezone.utc) if valor is not None and valor.tzinfo is None else valor


class ListaNotificacoes(BaseModel):
    nao_lidas: int
    items: list[NotificacaoSaida]


def _minhas(ctx: Contexto):
    condicoes = [Notificacao.user_id == ctx.utilizador.id]
    if ctx.company_id:
        condicoes.append(Notificacao.company_id == ctx.company_id)
    return condicoes


@router.get("", response_model=ListaNotificacoes, summary="As minhas notificações (mais recentes primeiro)")
def listar(apenas_nao_lidas: bool = False, limit: int = 30, ctx: Contexto = Depends(contexto_actual),
           db: Session = Depends(get_db)):
    condicoes = _minhas(ctx)
    nao_lidas = db.scalar(select(func.count()).select_from(Notificacao).where(
        *condicoes, Notificacao.lida_em.is_(None))) or 0
    consulta = select(Notificacao).where(*condicoes)
    if apenas_nao_lidas:
        consulta = consulta.where(Notificacao.lida_em.is_(None))
    items = db.scalars(consulta.order_by(Notificacao.criado_em.desc()).limit(min(max(limit, 1), 100))).all()
    return {"nao_lidas": nao_lidas, "items": items}


@router.post("/{notificacao_id}/read", response_model=NotificacaoSaida, summary="Marcar como lida")
def marcar_lida(notificacao_id: str, ctx: Contexto = Depends(contexto_actual), db: Session = Depends(get_db)):
    n = db.scalar(select(Notificacao).where(Notificacao.id == notificacao_id, *_minhas(ctx)))
    if not n:
        raise HTTPException(404, "Notificação não encontrada")
    if n.lida_em is None:
        n.lida_em = agora()
        db.commit()
    return n


@router.post("/read-all", summary="Marcar todas como lidas")
def marcar_todas(ctx: Contexto = Depends(contexto_actual), db: Session = Depends(get_db)) -> dict:
    r = db.execute(update(Notificacao).where(*_minhas(ctx), Notificacao.lida_em.is_(None)).values(lida_em=agora()))
    db.commit()
    return {"marcadas": r.rowcount}
