"""Estados automáticos de furos e projectos.

Os estados deixam de ser escolhidos à mão: são deduzidos dos dados registados, sempre que se grava
um furo, um survey, um intervalo, uma amostra ou um projecto (e ao listar projectos, para as datas).

Furo
  - abandonado  → só manual (fica até o utilizador o retirar);
  - concluído   → tem data de fim;
  - em sondagem → tem data de início, profundidade final, surveys, intervalos ou amostras;
  - planeado    → nenhum dos anteriores.

Projecto
  - suspenso    → só manual (fica até o utilizador o retirar);
  - encerrado   → a data de fim já chegou;
  - activo      → a data de início já chegou, ou algum furo está em sondagem ou concluído;
  - planeado    → nenhum dos anteriores.
"""
from __future__ import annotations

from datetime import date

from sqlalchemy import event, func, select
from sqlalchemy.orm import Session

from app.models import DrillHole, DrillInterval, DrillSurvey, Project, Sample

MANUAL_FURO = {"abandonado"}
MANUAL_PROJECTO = {"suspenso"}
_CHAVE = "estados_pendentes"


def estado_furo(db: Session, furo: DrillHole) -> str:
    if furo.estado in MANUAL_FURO:
        return furo.estado
    if furo.data_fim is not None:
        return "concluido"
    if furo.data_inicio is not None or furo.profundidade_final is not None:
        return "em_sondagem"
    for modelo in (DrillSurvey, DrillInterval, Sample):
        if db.scalar(select(func.count()).select_from(modelo).where(modelo.drill_hole_id == furo.id)):
            return "em_sondagem"
    return "planeado"


def estado_projecto(db: Session, projecto: Project, hoje: date | None = None) -> str:
    if projecto.estado in MANUAL_PROJECTO:
        return projecto.estado
    hoje = hoje or date.today()
    if projecto.data_fim is not None and projecto.data_fim <= hoje:
        return "encerrado"
    if projecto.data_inicio is not None and projecto.data_inicio <= hoje:
        return "activo"
    em_curso = db.scalar(select(func.count()).select_from(DrillHole).where(
        DrillHole.project_id == projecto.id, DrillHole.eliminado_em.is_(None),
        DrillHole.estado.in_(("em_sondagem", "concluido"))))
    return "activo" if em_curso else "planeado"


def recalcular(db: Session, furos: set[str] = frozenset(), projectos: set[str] = frozenset()) -> bool:
    """Recalcula os furos e projectos indicados (e os projectos dos furos). Devolve True se algo mudou."""
    mudou = False
    projectos = set(projectos)
    for fid in furos:
        furo = db.get(DrillHole, fid)
        if furo is None:
            continue
        projectos.add(furo.project_id)
        novo = estado_furo(db, furo)
        if novo != furo.estado:
            furo.estado = novo
            mudou = True
    if mudou:
        db.flush()  # o estado dos furos conta para o do projecto
    for pid in projectos:
        projecto = db.get(Project, pid)
        if projecto is None:
            continue
        novo = estado_projecto(db, projecto)
        if novo != projecto.estado:
            projecto.estado = novo
            mudou = True
    return mudou


def recalcular_empresa(db: Session, company_id: str | None = None, com_furos: bool = False) -> bool:
    """Para transições que dependem só da data (início/fim a chegar). Usado ao listar projectos e,
    com ``com_furos``, no arranque (acerta os estados escolhidos à mão antes de serem automáticos)."""
    consulta = select(Project.id).where(Project.eliminado_em.is_(None))
    if company_id:
        consulta = consulta.where(Project.company_id == company_id)
    furos: set[str] = set()
    if com_furos:
        furos = set(db.scalars(select(DrillHole.id).where(DrillHole.eliminado_em.is_(None))))
    return recalcular(db, furos=furos, projectos=set(db.scalars(consulta)))


# ---------------------------------------------------------------- ligação automática à sessão
def _pendentes(sessao: Session) -> dict[str, set[str]]:
    return sessao.info.setdefault(_CHAVE, {"furos": set(), "projectos": set()})


@event.listens_for(Session, "after_flush")
def _recolher(sessao: Session, _contexto) -> None:
    if sessao.info.get("a_recalcular_estados"):
        return
    pend = _pendentes(sessao)
    for obj in list(sessao.new) + list(sessao.dirty) + list(sessao.deleted):
        if isinstance(obj, DrillHole):
            pend["furos"].add(obj.id)
        elif isinstance(obj, (DrillSurvey, DrillInterval)):
            pend["furos"].add(obj.drill_hole_id)
        elif isinstance(obj, Sample):
            if obj.drill_hole_id:
                pend["furos"].add(obj.drill_hole_id)
            pend["projectos"].add(obj.project_id)
        elif isinstance(obj, Project):
            pend["projectos"].add(obj.id)


@event.listens_for(Session, "before_commit")
def _aplicar(sessao: Session) -> None:
    if sessao.new or sessao.dirty or sessao.deleted:
        sessao.flush()
    pend = sessao.info.pop(_CHAVE, None)
    if not pend or not (pend["furos"] or pend["projectos"]):
        return
    sessao.info["a_recalcular_estados"] = True
    try:
        if recalcular(sessao, pend["furos"], pend["projectos"]):
            sessao.flush()
    finally:
        sessao.info.pop("a_recalcular_estados", None)


@event.listens_for(Session, "after_rollback")
def _limpar(sessao: Session) -> None:
    sessao.info.pop(_CHAVE, None)
