"""Consulta e exportação do registo de auditoria."""
import csv
import io
from datetime import date, datetime

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.common import paginar
from app.database import get_db
from app.deps import Contexto, exige
from app.models import AuditLog
from app.schemas import AuditoriaSaida, Pagina

router = APIRouter(prefix="/audit", tags=["Auditoria"])


def _consulta(ctx: Contexto, company_id: str | None, accao: str | None, entidade: str | None,
              user_id: str | None, desde: date | None, ate: date | None):
    consulta = select(AuditLog)
    if ctx.company_id:
        consulta = consulta.where(AuditLog.company_id == ctx.company_id)
    elif company_id:
        consulta = consulta.where(AuditLog.company_id == company_id)
    if accao:
        consulta = consulta.where(AuditLog.accao == accao)
    if entidade:
        consulta = consulta.where(AuditLog.entidade == entidade)
    if user_id:
        consulta = consulta.where(AuditLog.user_id == user_id)
    if desde:
        consulta = consulta.where(AuditLog.criado_em >= datetime.combine(desde, datetime.min.time()))
    if ate:
        consulta = consulta.where(AuditLog.criado_em <= datetime.combine(ate, datetime.max.time()))
    return consulta


@router.get("", response_model=Pagina[AuditoriaSaida], summary="Consultar auditoria")
def listar(accao: str | None = None, entidade: str | None = None, user_id: str | None = None,
           company_id: str | None = None, desde: date | None = None, ate: date | None = None,
           skip: int = 0, limit: int = 100,
           ctx: Contexto = Depends(exige("audit", "view")), db: Session = Depends(get_db)):
    consulta = _consulta(ctx, company_id, accao, entidade, user_id, desde, ate)
    total, items = paginar(db, consulta.order_by(AuditLog.criado_em.desc()), skip, limit)
    return {"total": total, "items": items}


@router.get("/export", summary="Exportar auditoria em CSV")
def exportar(accao: str | None = None, entidade: str | None = None, user_id: str | None = None,
             company_id: str | None = None, desde: date | None = None, ate: date | None = None,
             ctx: Contexto = Depends(exige("audit", "export")), db: Session = Depends(get_db)):
    consulta = _consulta(ctx, company_id, accao, entidade, user_id, desde, ate)
    registos = list(db.scalars(consulta.order_by(AuditLog.criado_em.desc()).limit(50_000)))
    buffer = io.StringIO()
    escritor = csv.writer(buffer, delimiter=";")
    escritor.writerow(["id", "company_id", "user_id", "accao", "entidade", "entidade_id",
                       "criado_em", "ip", "dados_antes", "dados_depois"])
    for registo in registos:
        escritor.writerow([
            registo.id, registo.company_id, registo.user_id, registo.accao, registo.entidade,
            registo.entidade_id, registo.criado_em.isoformat() if registo.criado_em else "",
            registo.ip, registo.dados_antes, registo.dados_depois,
        ])
    conteudo = buffer.getvalue().encode("utf-8-sig")
    return StreamingResponse(
        io.BytesIO(conteudo), media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=auditoria.csv"},
    )
