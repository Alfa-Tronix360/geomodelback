"""Modelo de dados do MVP (20 tabelas), multiempresa.

Regras transversais:
- chaves primárias UUID guardadas como texto (compatível com SQLite e PostgreSQL);
- `company_id` em todos os dados de negócio, com índice, para isolamento entre clientes;
- chaves estrangeiras explícitas e `ON DELETE` definido;
- soft delete (`eliminado_em`) nas entidades críticas;
- datas em UTC e JSON para metadados/geometrias (GeoJSON).
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timezone

from sqlalchemy import (
    JSON, Boolean, Date, DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


def novo_id() -> str:
    return str(uuid.uuid4())


def agora() -> datetime:
    return datetime.now(timezone.utc)


class CriacaoMixin:
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=agora, nullable=False)
    actualizado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=agora, onupdate=agora, nullable=False,
    )


class EliminacaoMixin:
    eliminado_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


# ---------------------------------------------------------------- 1-6. empresas, utilizadores e permissões
class Company(CriacaoMixin, Base):
    __tablename__ = "companies"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=novo_id)
    nome: Mapped[str] = mapped_column(String(160), nullable=False)
    slug: Mapped[str] = mapped_column(String(80), nullable=False, unique=True)
    nif: Mapped[str | None] = mapped_column(String(40))
    pais: Mapped[str] = mapped_column(String(80), default="Angola", nullable=False)
    provincia: Mapped[str | None] = mapped_column(String(80))
    cidade: Mapped[str | None] = mapped_column(String(80))
    moeda: Mapped[str] = mapped_column(String(8), default="AOA", nullable=False)
    fuso_horario: Mapped[str] = mapped_column(String(60), default="Africa/Luanda", nullable=False)
    activa: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    eliminado_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class User(CriacaoMixin, Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=novo_id)
    nome: Mapped[str] = mapped_column(String(160), nullable=False)
    email: Mapped[str] = mapped_column(String(160), nullable=False, unique=True)
    senha_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    telefone: Mapped[str | None] = mapped_column(String(40))
    activo: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    superadmin: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    ultimo_acesso: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Role(CriacaoMixin, Base):
    __tablename__ = "roles"
    __table_args__ = (UniqueConstraint("company_id", "codigo", name="uq_roles_company_codigo"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=novo_id)
    company_id: Mapped[str] = mapped_column(String(36), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False)
    codigo: Mapped[str] = mapped_column(String(60), nullable=False)
    nome: Mapped[str] = mapped_column(String(120), nullable=False)
    descricao: Mapped[str | None] = mapped_column(Text)
    sistema: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class Permission(Base):
    __tablename__ = "permissions"
    __table_args__ = (UniqueConstraint("modulo", "accao", name="uq_permissions_modulo_accao"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=novo_id)
    modulo: Mapped[str] = mapped_column(String(60), nullable=False)
    accao: Mapped[str] = mapped_column(String(40), nullable=False)
    descricao: Mapped[str | None] = mapped_column(String(200))


class RolePermission(Base):
    __tablename__ = "role_permissions"

    role_id: Mapped[str] = mapped_column(String(36), ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True)
    permission_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("permissions.id", ondelete="CASCADE"), primary_key=True,
    )


class CompanyUser(CriacaoMixin, Base):
    __tablename__ = "company_users"
    __table_args__ = (
        UniqueConstraint("company_id", "user_id", name="uq_company_users_company_user"),
        Index("ix_company_users_company", "company_id"),
        Index("ix_company_users_user", "user_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=novo_id)
    company_id: Mapped[str] = mapped_column(String(36), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    role_id: Mapped[str] = mapped_column(String(36), ForeignKey("roles.id", ondelete="RESTRICT"), nullable=False)
    activo: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


# ---------------------------------------------------------------- 7-9. projectos e litologias
class Project(CriacaoMixin, EliminacaoMixin, Base):
    __tablename__ = "projects"
    __table_args__ = (
        UniqueConstraint("company_id", "codigo", name="uq_projects_company_codigo"),
        Index("ix_projects_company_estado", "company_id", "estado"),
        Index("ix_projects_company_nome", "company_id", "nome"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=novo_id)
    company_id: Mapped[str] = mapped_column(String(36), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False)
    codigo: Mapped[str] = mapped_column(String(60), nullable=False)
    nome: Mapped[str] = mapped_column(String(180), nullable=False)
    descricao: Mapped[str | None] = mapped_column(Text)
    mineral: Mapped[str | None] = mapped_column(String(80))
    concessao: Mapped[str | None] = mapped_column(String(120))
    pais: Mapped[str] = mapped_column(String(80), default="Angola", nullable=False)
    provincia: Mapped[str | None] = mapped_column(String(80))
    municipio: Mapped[str | None] = mapped_column(String(80))
    area_km2: Mapped[float | None] = mapped_column(Float)
    geometria: Mapped[dict | None] = mapped_column(JSON)
    estado: Mapped[str] = mapped_column(String(30), default="planeado", nullable=False)
    data_inicio: Mapped[date | None] = mapped_column(Date)
    data_fim: Mapped[date | None] = mapped_column(Date)
    gestor_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id", ondelete="SET NULL"))


class ProjectArea(CriacaoMixin, Base):
    __tablename__ = "project_areas"
    __table_args__ = (Index("ix_project_areas_company_project", "company_id", "project_id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=novo_id)
    company_id: Mapped[str] = mapped_column(String(36), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False)
    project_id: Mapped[str] = mapped_column(String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    nome: Mapped[str] = mapped_column(String(120), nullable=False)
    descricao: Mapped[str | None] = mapped_column(Text)
    area_km2: Mapped[float | None] = mapped_column(Float)
    geometria: Mapped[dict | None] = mapped_column(JSON)


class Lithology(CriacaoMixin, Base):
    __tablename__ = "lithologies"
    __table_args__ = (UniqueConstraint("company_id", "codigo", name="uq_lithologies_company_codigo"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=novo_id)
    company_id: Mapped[str] = mapped_column(String(36), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False)
    codigo: Mapped[str] = mapped_column(String(40), nullable=False)
    nome: Mapped[str] = mapped_column(String(120), nullable=False)
    descricao: Mapped[str | None] = mapped_column(Text)
    cor: Mapped[str | None] = mapped_column(String(20))
    activo: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


# ---------------------------------------------------------------- 10-12. sondagens
class DrillHole(CriacaoMixin, EliminacaoMixin, Base):
    __tablename__ = "drill_holes"
    __table_args__ = (
        UniqueConstraint("project_id", "codigo", name="uq_drill_holes_project_codigo"),
        Index("ix_drill_holes_company_project", "company_id", "project_id"),
        Index("ix_drill_holes_company_estado", "company_id", "estado"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=novo_id)
    company_id: Mapped[str] = mapped_column(String(36), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False)
    project_id: Mapped[str] = mapped_column(String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    codigo: Mapped[str] = mapped_column(String(60), nullable=False)
    nome: Mapped[str | None] = mapped_column(String(120))
    tipo: Mapped[str] = mapped_column(String(30), default="diamantado", nullable=False)
    estado: Mapped[str] = mapped_column(String(30), default="planeado", nullable=False)
    x: Mapped[float | None] = mapped_column(Float)
    y: Mapped[float | None] = mapped_column(Float)
    z: Mapped[float | None] = mapped_column(Float)
    latitude: Mapped[float | None] = mapped_column(Float)
    longitude: Mapped[float | None] = mapped_column(Float)
    azimute: Mapped[float | None] = mapped_column(Float)
    inclinacao: Mapped[float | None] = mapped_column(Float)
    profundidade_prevista: Mapped[float | None] = mapped_column(Float)
    profundidade_final: Mapped[float | None] = mapped_column(Float)
    data_inicio: Mapped[date | None] = mapped_column(Date)
    data_fim: Mapped[date | None] = mapped_column(Date)
    sonda: Mapped[str | None] = mapped_column(String(120))
    geologo_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id", ondelete="SET NULL"))
    notas: Mapped[str | None] = mapped_column(Text)


class DrillSurvey(CriacaoMixin, Base):
    __tablename__ = "drill_surveys"
    __table_args__ = (
        UniqueConstraint("drill_hole_id", "profundidade", name="uq_drill_surveys_hole_profundidade"),
        Index("ix_drill_surveys_company_hole", "company_id", "drill_hole_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=novo_id)
    company_id: Mapped[str] = mapped_column(String(36), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False)
    drill_hole_id: Mapped[str] = mapped_column(String(36), ForeignKey("drill_holes.id", ondelete="CASCADE"), nullable=False)
    profundidade: Mapped[float] = mapped_column(Float, nullable=False)
    azimute: Mapped[float] = mapped_column(Float, nullable=False)
    inclinacao: Mapped[float] = mapped_column(Float, nullable=False)
    metodo: Mapped[str | None] = mapped_column(String(60))


class DrillInterval(CriacaoMixin, Base):
    __tablename__ = "drill_intervals"
    __table_args__ = (Index("ix_drill_intervals_company_hole", "company_id", "drill_hole_id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=novo_id)
    company_id: Mapped[str] = mapped_column(String(36), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False)
    drill_hole_id: Mapped[str] = mapped_column(String(36), ForeignKey("drill_holes.id", ondelete="CASCADE"), nullable=False)
    de: Mapped[float] = mapped_column(Float, nullable=False)
    ate: Mapped[float] = mapped_column(Float, nullable=False)
    lithology_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("lithologies.id", ondelete="SET NULL"))
    alteracao: Mapped[str | None] = mapped_column(String(120))
    descricao: Mapped[str | None] = mapped_column(Text)
    recuperacao_pct: Mapped[float | None] = mapped_column(Float)
    rqd_pct: Mapped[float | None] = mapped_column(Float)


# ---------------------------------------------------------------- 13-15. amostras, laboratórios e resultados
class Sample(CriacaoMixin, EliminacaoMixin, Base):
    __tablename__ = "samples"
    __table_args__ = (
        UniqueConstraint("company_id", "codigo", name="uq_samples_company_codigo"),
        Index("ix_samples_company_project", "company_id", "project_id"),
        Index("ix_samples_company_hole", "company_id", "drill_hole_id"),
        Index("ix_samples_company_estado", "company_id", "estado"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=novo_id)
    company_id: Mapped[str] = mapped_column(String(36), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False)
    project_id: Mapped[str] = mapped_column(String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    drill_hole_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("drill_holes.id", ondelete="SET NULL"))
    drill_interval_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("drill_intervals.id", ondelete="SET NULL"))
    codigo: Mapped[str] = mapped_column(String(60), nullable=False)
    tipo: Mapped[str] = mapped_column(String(30), default="testemunho", nullable=False)
    de: Mapped[float | None] = mapped_column(Float)
    ate: Mapped[float | None] = mapped_column(Float)
    peso_kg: Mapped[float | None] = mapped_column(Float)
    estado: Mapped[str] = mapped_column(String(30), default="registada", nullable=False)
    data_recolha: Mapped[date | None] = mapped_column(Date)
    recolhido_por: Mapped[str | None] = mapped_column(String(120))
    notas: Mapped[str | None] = mapped_column(Text)


class Laboratory(CriacaoMixin, Base):
    __tablename__ = "laboratories"
    __table_args__ = (UniqueConstraint("company_id", "codigo", name="uq_laboratories_company_codigo"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=novo_id)
    company_id: Mapped[str] = mapped_column(String(36), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False)
    codigo: Mapped[str] = mapped_column(String(40), nullable=False)
    nome: Mapped[str] = mapped_column(String(160), nullable=False)
    contacto: Mapped[str | None] = mapped_column(String(120))
    email: Mapped[str | None] = mapped_column(String(160))
    telefone: Mapped[str | None] = mapped_column(String(40))
    pais: Mapped[str | None] = mapped_column(String(80))
    acreditacao: Mapped[str | None] = mapped_column(String(120))
    activo: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class AssayResult(CriacaoMixin, Base):
    __tablename__ = "assay_results"
    __table_args__ = (
        UniqueConstraint("sample_id", "laboratory_id", "parametro", "metodo", name="uq_assay_results_sample_lab_param_metodo"),
        Index("ix_assay_results_company_sample", "company_id", "sample_id"),
        Index("ix_assay_results_company_parametro", "company_id", "parametro"),
        Index("ix_assay_results_company_estado", "company_id", "estado"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=novo_id)
    company_id: Mapped[str] = mapped_column(String(36), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False)
    sample_id: Mapped[str] = mapped_column(String(36), ForeignKey("samples.id", ondelete="CASCADE"), nullable=False)
    laboratory_id: Mapped[str] = mapped_column(String(36), ForeignKey("laboratories.id", ondelete="RESTRICT"), nullable=False)
    parametro: Mapped[str] = mapped_column(String(40), nullable=False)
    valor: Mapped[float] = mapped_column(Float, nullable=False)
    unidade: Mapped[str] = mapped_column(String(20), default="ppm", nullable=False)
    metodo: Mapped[str | None] = mapped_column(String(80))
    limite_deteccao: Mapped[float | None] = mapped_column(Float)
    data_resultado: Mapped[date | None] = mapped_column(Date)
    estado: Mapped[str] = mapped_column(String(30), default="preliminar", nullable=False)
    validado_por: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id", ondelete="SET NULL"))
    validado_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


# ---------------------------------------------------------------- 16-18. modelação geológica 3D
class GeologicalModel(CriacaoMixin, EliminacaoMixin, Base):
    __tablename__ = "geological_models"
    __table_args__ = (
        UniqueConstraint("project_id", "nome", name="uq_geological_models_project_nome"),
        Index("ix_geological_models_company_project", "company_id", "project_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=novo_id)
    company_id: Mapped[str] = mapped_column(String(36), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False)
    project_id: Mapped[str] = mapped_column(String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    nome: Mapped[str] = mapped_column(String(160), nullable=False)
    descricao: Mapped[str | None] = mapped_column(Text)
    tipo: Mapped[str] = mapped_column(String(30), default="combinado", nullable=False)
    estado: Mapped[str] = mapped_column(String(30), default="rascunho", nullable=False)
    versao_actual: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    criado_por: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id", ondelete="SET NULL"))


class GeologicalDomain(CriacaoMixin, Base):
    __tablename__ = "geological_domains"
    __table_args__ = (
        UniqueConstraint("model_id", "codigo", name="uq_geological_domains_model_codigo"),
        Index("ix_geological_domains_company_model", "company_id", "model_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=novo_id)
    company_id: Mapped[str] = mapped_column(String(36), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False)
    model_id: Mapped[str] = mapped_column(String(36), ForeignKey("geological_models.id", ondelete="CASCADE"), nullable=False)
    codigo: Mapped[str] = mapped_column(String(40), nullable=False)
    nome: Mapped[str] = mapped_column(String(120), nullable=False)
    descricao: Mapped[str | None] = mapped_column(Text)
    cor: Mapped[str | None] = mapped_column(String(20))
    lithology_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("lithologies.id", ondelete="SET NULL"))


class ModelVersion(CriacaoMixin, Base):
    __tablename__ = "model_versions"
    __table_args__ = (
        UniqueConstraint("model_id", "numero_versao", name="uq_model_versions_model_numero"),
        Index("ix_model_versions_company_model", "company_id", "model_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=novo_id)
    company_id: Mapped[str] = mapped_column(String(36), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False)
    model_id: Mapped[str] = mapped_column(String(36), ForeignKey("geological_models.id", ondelete="CASCADE"), nullable=False)
    numero_versao: Mapped[int] = mapped_column(Integer, nullable=False)
    nome: Mapped[str | None] = mapped_column(String(160))
    descricao: Mapped[str | None] = mapped_column(Text)
    estado: Mapped[str] = mapped_column(String(30), default="rascunho", nullable=False)
    ficheiro_chave: Mapped[str | None] = mapped_column(String(255))
    ficheiro_url: Mapped[str | None] = mapped_column(String(500))
    formato: Mapped[str | None] = mapped_column(String(20))
    metadados: Mapped[dict | None] = mapped_column(JSON)
    criado_por: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id", ondelete="SET NULL"))
    validado_por: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id", ondelete="SET NULL"))
    validado_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


# ---------------------------------------------------------------- 19. estimativa de recursos
class ResourceEstimate(CriacaoMixin, Base):
    __tablename__ = "resource_estimates"
    __table_args__ = (
        Index("ix_resource_estimates_company_project", "company_id", "project_id"),
        Index("ix_resource_estimates_company_estado", "company_id", "estado"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=novo_id)
    company_id: Mapped[str] = mapped_column(String(36), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False)
    project_id: Mapped[str] = mapped_column(String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    model_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("geological_models.id", ondelete="SET NULL"))
    nome: Mapped[str] = mapped_column(String(160), nullable=False)
    metodo: Mapped[str] = mapped_column(String(40), default="idw", nullable=False)
    commodity: Mapped[str] = mapped_column(String(40), nullable=False)
    teor_corte: Mapped[float | None] = mapped_column(Float)
    unidade_teor: Mapped[str] = mapped_column(String(20), default="ppm", nullable=False)
    densidade: Mapped[float | None] = mapped_column(Float)
    estado: Mapped[str] = mapped_column(String(30), default="rascunho", nullable=False)
    volume_m3: Mapped[float | None] = mapped_column(Float)
    tonelagem: Mapped[float | None] = mapped_column(Float)
    metal_contido: Mapped[float | None] = mapped_column(Float)
    parametros: Mapped[dict | None] = mapped_column(JSON)
    versao: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    criado_por: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id", ondelete="SET NULL"))
    validado_por: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id", ondelete="SET NULL"))
    validado_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


# ---------------------------------------------------------------- 20. auditoria
class AuditLog(Base):
    __tablename__ = "audit_logs"
    __table_args__ = (
        Index("ix_audit_logs_company_criado", "company_id", "criado_em"),
        Index("ix_audit_logs_entidade", "entidade", "entidade_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=novo_id)
    company_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("companies.id", ondelete="SET NULL"))
    user_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id", ondelete="SET NULL"))
    accao: Mapped[str] = mapped_column(String(40), nullable=False)
    entidade: Mapped[str] = mapped_column(String(60), nullable=False)
    entidade_id: Mapped[str | None] = mapped_column(String(36))
    dados_antes: Mapped[dict | None] = mapped_column(JSON)
    dados_depois: Mapped[dict | None] = mapped_column(JSON)
    ip: Mapped[str | None] = mapped_column(String(60))
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=agora, nullable=False)


# ---------------------------------------------------------------- 21. notificações (sino)
class Notificacao(Base):
    """Aviso para quem tem de agir no passo seguinte do fluxo (amostra enviada, resultado por validar…)."""
    __tablename__ = "notifications"
    __table_args__ = (
        Index("ix_notifications_user_lida", "user_id", "lida_em"),
        Index("ix_notifications_user_chave", "user_id", "chave"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=novo_id)
    company_id: Mapped[str] = mapped_column(String(36), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    tipo: Mapped[str] = mapped_column(String(40), nullable=False)
    titulo: Mapped[str] = mapped_column(String(160), nullable=False)
    mensagem: Mapped[str | None] = mapped_column(Text)
    link: Mapped[str | None] = mapped_column(String(255))
    # agrupa avisos repetidos (ex.: vários resultados por validar no mesmo projecto) num só, enquanto não for lido
    chave: Mapped[str | None] = mapped_column(String(120))
    lida_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=agora, nullable=False)
