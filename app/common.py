"""Utilitários comuns: paginação e normalização de texto."""
from __future__ import annotations

import unicodedata
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session


def normalizar(texto: str) -> str:
    sem_acentos = unicodedata.normalize("NFKD", str(texto)).encode("ascii", "ignore").decode("ascii")
    return " ".join(sem_acentos.lower().split())


def paginar(db: Session, consulta, skip: int = 0, limit: int = 50) -> tuple[int, list[Any]]:
    total = db.scalar(select(func.count()).select_from(consulta.order_by(None).subquery())) or 0
    items = list(db.scalars(consulta.offset(skip).limit(limit)))
    return total, items


def texto_ou_none(valor: Any) -> str | None:
    if valor is None:
        return None
    texto = str(valor).strip()
    return texto or None
