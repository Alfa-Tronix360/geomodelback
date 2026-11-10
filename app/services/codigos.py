"""Geração automática de códigos sequenciais (PR-001, FUR-001, ...)."""
from __future__ import annotations

import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import DrillHole, Project

PREFIXO_PROJECTO = "PR"
PREFIXO_FURO = "FUR"


def _seguinte(codigos: list[str], prefixo: str) -> str:
    padrao = re.compile(rf"^{re.escape(prefixo)}-(\d+)$", re.IGNORECASE)
    maior = 0
    for codigo in codigos:
        encontrado = padrao.match((codigo or "").strip())
        if encontrado:
            maior = max(maior, int(encontrado.group(1)))
    return f"{prefixo}-{maior + 1:03d}"


def proximo_codigo_projecto(db: Session, company_id: str) -> str:
    # inclui projectos eliminados: o código continua reservado pela restrição única
    codigos = db.scalars(select(Project.codigo).where(Project.company_id == company_id)).all()
    return _seguinte(list(codigos), PREFIXO_PROJECTO)


def proximo_codigo_furo(db: Session, project_id: str) -> str:
    codigos = db.scalars(select(DrillHole.codigo).where(DrillHole.project_id == project_id)).all()
    return _seguinte(list(codigos), PREFIXO_FURO)
