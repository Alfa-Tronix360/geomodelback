"""Notificações do sino: avisam quem tem de agir no passo seguinte do fluxo.

Fluxo e destinatários (pelas permissões do perfil, não pelo nome do perfil; quem fez a acção não é avisado):

  furo concluído               → quem regista amostras        (samples:create)
  amostra enviada ao lab.      → laboratório                  (assays:create)
  resultado lançado            → quem valida resultados       (assays:validate)
  resultado validado           → quem trabalha os modelos     (models:create)
  versão de modelo carregada   → quem valida modelos          (models:validate)
  versão de modelo validada    → quem estima recursos         (resources:create)
  estimativa criada            → quem valida estimativas      (resources:validate)
  estimativa validada          → gestão do projecto           (projects:edit)

Avisos repetidos do mesmo tipo no mesmo projecto (ex.: 20 resultados por validar) juntam-se num só
enquanto não forem lidos.
"""
from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    AssayResult, CompanyUser, DrillHole, GeologicalModel, Notificacao, Permission, Project, RolePermission,
    Sample, User, agora,
)

log = logging.getLogger("geomodel.notificacoes")


def destinatarios(db: Session, company_id: str, modulo: str, accao: str, excluir: str | None = None) -> list[str]:
    consulta = (select(CompanyUser.user_id).distinct()
                .join(RolePermission, RolePermission.role_id == CompanyUser.role_id)
                .join(Permission, Permission.id == RolePermission.permission_id)
                .join(User, User.id == CompanyUser.user_id)
                .where(CompanyUser.company_id == company_id, CompanyUser.activo.is_(True), User.activo.is_(True),
                       Permission.modulo == modulo, Permission.accao == accao))
    return [uid for uid in db.scalars(consulta) if uid != excluir]


def notificar(db: Session, company_id: str, permissao: tuple[str, str], tipo: str, titulo: str,
              mensagem: str, link: str | None, chave: str | None = None, excluir: str | None = None) -> int:
    enviados = 0
    for uid in destinatarios(db, company_id, *permissao, excluir=excluir):
        existente = None
        if chave:
            existente = db.scalar(select(Notificacao).where(
                Notificacao.user_id == uid, Notificacao.chave == chave, Notificacao.lida_em.is_(None)))
        if existente:
            existente.titulo, existente.mensagem, existente.link, existente.criado_em = titulo, mensagem, link, agora()
        else:
            db.add(Notificacao(company_id=company_id, user_id=uid, tipo=tipo, titulo=titulo,
                               mensagem=mensagem, link=link, chave=chave))
        enviados += 1
    return enviados


def _projecto(db: Session, project_id: str | None) -> str:
    p = db.get(Project, project_id) if project_id else None
    return f"{p.codigo} · {p.nome}" if p else "projecto"


def _pendentes_validacao(db: Session, project_id: str) -> int:
    return len(db.scalars(select(AssayResult.id).join(Sample, Sample.id == AssayResult.sample_id).where(
        Sample.project_id == project_id, AssayResult.estado == "preliminar")).all())


# ---------------------------------------------------------------- eventos (chamado pela auditoria)
def apos_auditoria(db: Session, company_id: str | None, autor: str | None, accao: str, entidade: str,
                   antes: dict | None, depois: dict | None) -> None:
    if not company_id or not depois:
        return
    try:
        _eventos(db, company_id, autor, accao, entidade, antes or {}, depois)
    except Exception:  # noqa: BLE001 — um aviso nunca pode impedir a operação principal
        log.exception("Falha a criar notificações (%s %s)", accao, entidade)


def _eventos(db: Session, cid: str, autor: str | None, accao: str, entidade: str, antes: dict, depois: dict) -> None:
    estado, estado_antes = depois.get("estado"), antes.get("estado")

    if entidade == "sample" and estado == "enviada" and estado_antes != "enviada":
        pid = depois.get("project_id")
        notificar(db, cid, ("assays", "create"), "amostra_enviada",
                  f"Amostras enviadas para análise · {_projecto(db, pid)}",
                  f"A amostra {depois.get('codigo')} foi enviada ao laboratório. Registe os resultados quando chegarem.",
                  "/resultados", chave=f"amostra_enviada:{pid}", excluir=autor)

    elif entidade == "assay_result" and accao == "criar" and estado != "validado":
        amostra = db.get(Sample, depois.get("sample_id"))
        pid = amostra.project_id if amostra else None
        n = _pendentes_validacao(db, pid) if pid else 1
        notificar(db, cid, ("assays", "validate"), "resultado_por_validar",
                  f"Resultados por validar · {_projecto(db, pid)}",
                  f"{n} resultado(s) laboratorial(is) aguarda(m) validação. Último: {depois.get('parametro')} "
                  f"da amostra {amostra.codigo if amostra else ''}.",
                  "/resultados", chave=f"resultado_por_validar:{pid}", excluir=autor)

    elif entidade == "assay_result" and accao == "validar" and estado == "validado":
        amostra = db.get(Sample, depois.get("sample_id"))
        pid = amostra.project_id if amostra else None
        notificar(db, cid, ("models", "create"), "resultado_validado",
                  f"Resultados validados · {_projecto(db, pid)}",
                  "Há resultados laboratoriais validados. Pode actualizar o modelo geológico do projecto.",
                  f"/projectos/{pid}" if pid else "/modelos", chave=f"resultado_validado:{pid}", excluir=autor)

    elif entidade == "model_version" and accao == "criar":
        modelo = db.get(GeologicalModel, depois.get("model_id"))
        nome = modelo.nome if modelo else "modelo"
        notificar(db, cid, ("models", "validate"), "versao_por_validar",
                  f"Nova versão por validar · {nome}",
                  f"Foi carregada a versão {depois.get('numero_versao')} do modelo {nome}. Reveja e valide.",
                  f"/modelos/{depois.get('model_id')}", chave=f"versao_por_validar:{depois.get('model_id')}",
                  excluir=autor)

    elif entidade == "model_version" and accao == "validar":
        modelo = db.get(GeologicalModel, depois.get("model_id"))
        nome = modelo.nome if modelo else "modelo"
        notificar(db, cid, ("resources", "create"), "modelo_validado",
                  f"Modelo validado · {nome}",
                  f"A versão {depois.get('numero_versao')} do modelo {nome} foi validada. Pode avançar com a "
                  "estimativa de recursos.", "/recursos", chave=f"modelo_validado:{depois.get('model_id')}",
                  excluir=autor)

    elif entidade == "resource_estimate" and accao == "criar":
        notificar(db, cid, ("resources", "validate"), "estimativa_por_validar",
                  f"Estimativa por validar · {depois.get('nome')}",
                  f"Foi criada a estimativa {depois.get('nome')} ({_projecto(db, depois.get('project_id'))}). "
                  "Reveja e valide.", "/recursos", excluir=autor)

    elif entidade == "resource_estimate" and accao == "validar":
        pid = depois.get("project_id")
        notificar(db, cid, ("projects", "edit"), "estimativa_validada",
                  f"Estimativa validada · {depois.get('nome')}",
                  f"A estimativa {depois.get('nome')} do projecto {_projecto(db, pid)} foi validada.",
                  f"/projectos/{pid}", excluir=autor)


def furo_concluido(db: Session, furo: DrillHole) -> None:
    """Chamado pelos estados automáticos quando um furo passa a concluído."""
    try:
        notificar(db, furo.company_id, ("samples", "create"), "furo_concluido",
                  f"Furo concluído · {furo.codigo}",
                  f"O furo {furo.codigo} ({_projecto(db, furo.project_id)}) foi concluído. Registe as amostras "
                  "e envie-as ao laboratório.", f"/sondagens/{furo.id}", chave=f"furo_concluido:{furo.id}")
    except Exception:  # noqa: BLE001
        log.exception("Falha a notificar o furo concluído %s", furo.id)
