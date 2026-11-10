"""Esquemas de entrada e saída da API (Pydantic v2)."""
from __future__ import annotations

from datetime import date, datetime
from typing import Generic, Literal, TypeVar

from pydantic import BaseModel, ConfigDict, Field, model_validator

T = TypeVar("T")

EstadoProjecto = Literal["planeado", "activo", "suspenso", "encerrado"]
EstadoFuro = Literal["planeado", "em_sondagem", "concluido", "abandonado"]
TipoFuro = Literal["diamantado", "rc", "percussao", "rotativo", "outro"]
TipoAmostra = Literal["testemunho", "rocha", "solo", "sedimento", "outro"]
EstadoAmostra = Literal["registada", "enviada", "recebida", "analisada", "rejeitada"]
EstadoResultado = Literal["preliminar", "validado", "rejeitado"]
EstadoModelo = Literal["rascunho", "validado", "arquivado"]
TipoModelo = Literal["superficie", "solido", "bloco", "combinado"]
FormatoModelo = Literal["obj", "stl", "las", "geojson", "dxf", "shp", "outro"]
EstadoEstimativa = Literal["rascunho", "validado", "aprovado", "rejeitado"]
MetodoEstimativa = Literal["idw", "kriging", "vizinho_mais_proximo", "manual"]


class Entrada(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Saida(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class Pagina(BaseModel, Generic[T]):
    total: int
    items: list[T]


# ---------------------------------------------------------------- autenticação e empresas
class LoginIn(Entrada):
    email: str = Field(min_length=3, max_length=160)
    senha: str = Field(min_length=1, max_length=200)


class EmpresaResumo(Saida):
    id: str
    nome: str
    slug: str


class EmpresaCriar(Entrada):
    nome: str = Field(min_length=2, max_length=160)
    slug: str = Field(min_length=2, max_length=80, pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    nif: str | None = None
    pais: str = "Angola"
    provincia: str | None = None
    cidade: str | None = None
    moeda: str = "AOA"
    fuso_horario: str = "Africa/Luanda"


class EmpresaActualizar(Entrada):
    nome: str | None = Field(None, min_length=2, max_length=160)
    nif: str | None = None
    pais: str | None = None
    provincia: str | None = None
    cidade: str | None = None
    moeda: str | None = None
    fuso_horario: str | None = None
    activa: bool | None = None


class EmpresaSaida(EmpresaResumo):
    nif: str | None
    pais: str
    provincia: str | None
    cidade: str | None
    moeda: str
    fuso_horario: str
    activa: bool
    criado_em: datetime
    actualizado_em: datetime


class UtilizadorSaida(Saida):
    id: str
    nome: str
    email: str
    telefone: str | None
    activo: bool
    superadmin: bool
    ultimo_acesso: datetime | None
    criado_em: datetime


class SessaoSaida(Saida):
    access_token: str
    token_type: str = "bearer"
    utilizador: UtilizadorSaida
    empresas: list[EmpresaResumo]
    empresa_actual: EmpresaResumo | None = None


class PerfilSessao(BaseModel):
    utilizador: UtilizadorSaida
    empresas: list[EmpresaResumo]
    empresa_actual: EmpresaResumo | None
    papel: str | None
    permissoes: list[str]


class MembroSaida(Saida):
    id: str
    user_id: str
    nome: str
    email: str
    role_id: str
    role_codigo: str
    role_nome: str
    activo: bool
    criado_em: datetime


class UtilizadorCriar(Entrada):
    nome: str = Field(min_length=2, max_length=160)
    email: str = Field(min_length=3, max_length=160)
    senha: str = Field(min_length=8, max_length=200)
    telefone: str | None = None
    role_id: str
    activo: bool = True
    superadmin: bool = False


class UtilizadorActualizar(Entrada):
    nome: str | None = Field(None, min_length=2, max_length=160)
    telefone: str | None = None
    senha: str | None = Field(None, min_length=8, max_length=200)
    activo: bool | None = None


class MembroActualizar(Entrada):
    role_id: str | None = None
    activo: bool | None = None


class AlterarSenhaIn(Entrada):
    senha_actual: str
    senha_nova: str = Field(min_length=8, max_length=200)


class PermissaoSaida(Saida):
    id: str
    modulo: str
    accao: str
    descricao: str | None


class PerfilCriar(Entrada):
    codigo: str = Field(min_length=2, max_length=60, pattern=r"^[a-z0-9_]+$")
    nome: str = Field(min_length=2, max_length=120)
    descricao: str | None = None
    permissoes: list[str] = Field(default_factory=list, description="Códigos modulo:accao")


class PerfilActualizar(Entrada):
    nome: str | None = Field(None, min_length=2, max_length=120)
    descricao: str | None = None
    permissoes: list[str] | None = None


class PerfilSaida(Saida):
    id: str
    codigo: str
    nome: str
    descricao: str | None
    sistema: bool
    permissoes: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------- projectos, áreas e litologias
class ProjectoCriar(Entrada):
    codigo: str | None = Field(None, max_length=60, description="Vazio = gerado automaticamente (PR-001, ...)")
    nome: str = Field(min_length=2, max_length=180)
    descricao: str | None = None
    mineral: str | None = None
    concessao: str | None = None
    pais: str = "Angola"
    provincia: str | None = None
    municipio: str | None = None
    area_km2: float | None = Field(None, ge=0)
    geometria: dict | None = Field(None, description="Geometria GeoJSON da área do projecto")
    estado: EstadoProjecto = "planeado"
    data_inicio: date | None = None
    data_fim: date | None = None
    gestor_id: str | None = None

    @model_validator(mode="after")
    def _datas(self):
        if self.data_inicio and self.data_fim and self.data_fim < self.data_inicio:
            raise ValueError("data_fim não pode ser anterior a data_inicio")
        return self


class ProjectoActualizar(Entrada):
    codigo: str | None = Field(None, min_length=1, max_length=60)
    nome: str | None = Field(None, min_length=2, max_length=180)
    descricao: str | None = None
    mineral: str | None = None
    concessao: str | None = None
    pais: str | None = None
    provincia: str | None = None
    municipio: str | None = None
    area_km2: float | None = Field(None, ge=0)
    geometria: dict | None = None
    estado: EstadoProjecto | None = None
    data_inicio: date | None = None
    data_fim: date | None = None
    gestor_id: str | None = None


class ProjectoSaida(Saida):
    id: str
    company_id: str
    codigo: str
    nome: str
    descricao: str | None
    mineral: str | None
    concessao: str | None
    pais: str
    provincia: str | None
    municipio: str | None
    area_km2: float | None
    geometria: dict | None
    estado: str
    data_inicio: date | None
    data_fim: date | None
    gestor_id: str | None
    criado_em: datetime
    actualizado_em: datetime
    eliminado_em: datetime | None


class AreaProjetoCriar(Entrada):
    nome: str = Field(min_length=2, max_length=120)
    descricao: str | None = None
    area_km2: float | None = Field(None, ge=0)
    geometria: dict | None = None


class AreaProjectoActualizar(Entrada):
    nome: str | None = Field(None, min_length=2, max_length=120)
    descricao: str | None = None
    area_km2: float | None = Field(None, ge=0)
    geometria: dict | None = None


class AreaProjectoSaida(Saida):
    id: str
    company_id: str
    project_id: str
    nome: str
    descricao: str | None
    area_km2: float | None
    geometria: dict | None
    criado_em: datetime
    actualizado_em: datetime


class LitologiaCriar(Entrada):
    codigo: str = Field(min_length=1, max_length=40)
    nome: str = Field(min_length=2, max_length=120)
    descricao: str | None = None
    cor: str | None = None
    activo: bool = True


class LitologiaActualizar(Entrada):
    codigo: str | None = Field(None, min_length=1, max_length=40)
    nome: str | None = Field(None, min_length=2, max_length=120)
    descricao: str | None = None
    cor: str | None = None
    activo: bool | None = None


class LitologiaSaida(Saida):
    id: str
    company_id: str
    codigo: str
    nome: str
    descricao: str | None
    cor: str | None
    activo: bool
    criado_em: datetime
    actualizado_em: datetime


# ---------------------------------------------------------------- sondagens
class FuroCriar(Entrada):
    project_id: str
    codigo: str | None = Field(None, max_length=60, description="Vazio = gerado automaticamente (FUR-001, ...)")
    nome: str | None = None
    tipo: TipoFuro = "diamantado"
    estado: EstadoFuro = "planeado"
    x: float | None = None
    y: float | None = None
    z: float | None = None
    latitude: float | None = Field(None, ge=-90, le=90)
    longitude: float | None = Field(None, ge=-180, le=180)
    azimute: float | None = Field(None, ge=0, le=360)
    inclinacao: float | None = Field(None, ge=-90, le=90)
    profundidade_prevista: float | None = Field(None, ge=0)
    profundidade_final: float | None = Field(None, ge=0)
    data_inicio: date | None = None
    data_fim: date | None = None
    sonda: str | None = None
    geologo_id: str | None = None
    notas: str | None = None

    @model_validator(mode="after")
    def _validar(self):
        if self.profundidade_prevista is not None and self.profundidade_final is not None \
                and self.profundidade_final > self.profundidade_prevista:
            raise ValueError("profundidade_final não pode exceder a profundidade_prevista")
        if self.data_inicio and self.data_fim and self.data_fim < self.data_inicio:
            raise ValueError("data_fim não pode ser anterior a data_inicio")
        return self


class FuroActualizar(Entrada):
    codigo: str | None = Field(None, min_length=1, max_length=60)
    nome: str | None = None
    tipo: TipoFuro | None = None
    estado: EstadoFuro | None = None
    x: float | None = None
    y: float | None = None
    z: float | None = None
    latitude: float | None = Field(None, ge=-90, le=90)
    longitude: float | None = Field(None, ge=-180, le=180)
    azimute: float | None = Field(None, ge=0, le=360)
    inclinacao: float | None = Field(None, ge=-90, le=90)
    profundidade_prevista: float | None = Field(None, ge=0)
    profundidade_final: float | None = Field(None, ge=0)
    data_inicio: date | None = None
    data_fim: date | None = None
    sonda: str | None = None
    geologo_id: str | None = None
    notas: str | None = None


class FuroSaida(Saida):
    id: str
    company_id: str
    project_id: str
    codigo: str
    nome: str | None
    tipo: str
    estado: str
    x: float | None
    y: float | None
    z: float | None
    latitude: float | None
    longitude: float | None
    azimute: float | None
    inclinacao: float | None
    profundidade_prevista: float | None
    profundidade_final: float | None
    data_inicio: date | None
    data_fim: date | None
    sonda: str | None
    geologo_id: str | None
    notas: str | None
    criado_em: datetime
    actualizado_em: datetime
    eliminado_em: datetime | None


class FuroDetalhe(FuroSaida):
    projecto_codigo: str | None = None
    projecto_nome: str | None = None
    num_surveys: int = 0
    num_intervalos: int = 0
    num_amostras: int = 0


class SurveyCriar(Entrada):
    profundidade: float = Field(ge=0)
    azimute: float = Field(ge=0, le=360)
    inclinacao: float = Field(ge=-90, le=90)
    metodo: str | None = None


class SurveySaida(Saida):
    id: str
    company_id: str
    drill_hole_id: str
    profundidade: float
    azimute: float
    inclinacao: float
    metodo: str | None
    criado_em: datetime


class IntervaloCriar(Entrada):
    de: float = Field(ge=0)
    ate: float = Field(gt=0)
    lithology_id: str | None = None
    alteracao: str | None = None
    descricao: str | None = None
    recuperacao_pct: float | None = Field(None, ge=0, le=100)
    rqd_pct: float | None = Field(None, ge=0, le=100)

    @model_validator(mode="after")
    def _ordem(self):
        if self.ate <= self.de:
            raise ValueError("ate tem de ser maior do que de")
        return self


class IntervaloActualizar(Entrada):
    de: float | None = Field(None, ge=0)
    ate: float | None = Field(None, gt=0)
    lithology_id: str | None = None
    alteracao: str | None = None
    descricao: str | None = None
    recuperacao_pct: float | None = Field(None, ge=0, le=100)
    rqd_pct: float | None = Field(None, ge=0, le=100)


class IntervaloSaida(Saida):
    id: str
    company_id: str
    drill_hole_id: str
    de: float
    ate: float
    lithology_id: str | None
    alteracao: str | None
    descricao: str | None
    recuperacao_pct: float | None
    rqd_pct: float | None
    criado_em: datetime
    actualizado_em: datetime


class PontoTrajectoria(BaseModel):
    profundidade: float
    x: float
    y: float
    z: float


class TrajectoriaSaida(BaseModel):
    drill_hole_id: str
    collar: PontoTrajectoria | None
    comprimento: float
    pontos: list[PontoTrajectoria]


# ---------------------------------------------------------------- amostras, laboratórios e análises
class AmostraCriar(Entrada):
    project_id: str
    drill_hole_id: str | None = None
    drill_interval_id: str | None = None
    codigo: str = Field(min_length=1, max_length=60)
    tipo: TipoAmostra = "testemunho"
    de: float | None = Field(None, ge=0)
    ate: float | None = Field(None, ge=0)
    peso_kg: float | None = Field(None, ge=0)
    estado: EstadoAmostra = "registada"
    data_recolha: date | None = None
    recolhido_por: str | None = None
    notas: str | None = None

    @model_validator(mode="after")
    def _intervalo(self):
        if self.de is not None and self.ate is not None and self.ate <= self.de:
            raise ValueError("ate tem de ser maior do que de")
        return self


class AmostraActualizar(Entrada):
    drill_hole_id: str | None = None
    drill_interval_id: str | None = None
    codigo: str | None = Field(None, min_length=1, max_length=60)
    tipo: TipoAmostra | None = None
    de: float | None = Field(None, ge=0)
    ate: float | None = Field(None, ge=0)
    peso_kg: float | None = Field(None, ge=0)
    estado: EstadoAmostra | None = None
    data_recolha: date | None = None
    recolhido_por: str | None = None
    notas: str | None = None


class AmostraSaida(Saida):
    id: str
    company_id: str
    project_id: str
    drill_hole_id: str | None
    drill_interval_id: str | None
    codigo: str
    tipo: str
    de: float | None
    ate: float | None
    peso_kg: float | None
    estado: str
    data_recolha: date | None
    recolhido_por: str | None
    notas: str | None
    criado_em: datetime
    actualizado_em: datetime
    eliminado_em: datetime | None


class LaboratorioCriar(Entrada):
    codigo: str = Field(min_length=1, max_length=40)
    nome: str = Field(min_length=2, max_length=160)
    contacto: str | None = None
    email: str | None = None
    telefone: str | None = None
    pais: str | None = None
    acreditacao: str | None = None
    activo: bool = True


class LaboratorioActualizar(Entrada):
    codigo: str | None = Field(None, min_length=1, max_length=40)
    nome: str | None = Field(None, min_length=2, max_length=160)
    contacto: str | None = None
    email: str | None = None
    telefone: str | None = None
    pais: str | None = None
    acreditacao: str | None = None
    activo: bool | None = None


class LaboratorioSaida(Saida):
    id: str
    company_id: str
    codigo: str
    nome: str
    contacto: str | None
    email: str | None
    telefone: str | None
    pais: str | None
    acreditacao: str | None
    activo: bool
    criado_em: datetime
    actualizado_em: datetime


class ResultadoCriar(Entrada):
    sample_id: str
    laboratory_id: str
    parametro: str = Field(min_length=1, max_length=40)
    valor: float = Field(ge=0)
    unidade: str = Field(default="ppm", min_length=1, max_length=20)
    metodo: str | None = None
    limite_deteccao: float | None = Field(None, ge=0)
    data_resultado: date | None = None
    estado: EstadoResultado = "preliminar"


class ResultadoActualizar(Entrada):
    parametro: str | None = Field(None, min_length=1, max_length=40)
    valor: float | None = Field(None, ge=0)
    unidade: str | None = Field(None, min_length=1, max_length=20)
    metodo: str | None = None
    limite_deteccao: float | None = Field(None, ge=0)
    data_resultado: date | None = None
    estado: EstadoResultado | None = None


class ResultadoSaida(Saida):
    id: str
    company_id: str
    sample_id: str
    laboratory_id: str
    parametro: str
    valor: float
    unidade: str
    metodo: str | None
    limite_deteccao: float | None
    data_resultado: date | None
    estado: str
    validado_por: str | None
    validado_em: datetime | None
    criado_em: datetime
    actualizado_em: datetime


# ---------------------------------------------------------------- modelação 3D
class ModeloCriar(Entrada):
    project_id: str
    nome: str = Field(min_length=2, max_length=160)
    descricao: str | None = None
    tipo: TipoModelo = "combinado"
    estado: EstadoModelo = "rascunho"


class ModeloActualizar(Entrada):
    nome: str | None = Field(None, min_length=2, max_length=160)
    descricao: str | None = None
    tipo: TipoModelo | None = None
    estado: EstadoModelo | None = None


class ModeloSaida(Saida):
    id: str
    company_id: str
    project_id: str
    nome: str
    descricao: str | None
    tipo: str
    estado: str
    versao_actual: int
    criado_por: str | None
    criado_em: datetime
    actualizado_em: datetime
    eliminado_em: datetime | None


class DominioCriar(Entrada):
    codigo: str = Field(min_length=1, max_length=40)
    nome: str = Field(min_length=2, max_length=120)
    descricao: str | None = None
    cor: str | None = None
    lithology_id: str | None = None


class DominioActualizar(Entrada):
    codigo: str | None = Field(None, min_length=1, max_length=40)
    nome: str | None = Field(None, min_length=2, max_length=120)
    descricao: str | None = None
    cor: str | None = None
    lithology_id: str | None = None


class DominioSaida(Saida):
    id: str
    company_id: str
    model_id: str
    codigo: str
    nome: str
    descricao: str | None
    cor: str | None
    lithology_id: str | None
    criado_em: datetime
    actualizado_em: datetime


class VersaoCriar(Entrada):
    numero_versao: int | None = Field(None, ge=1)
    nome: str | None = None
    descricao: str | None = None
    estado: EstadoModelo = "rascunho"
    ficheiro_chave: str | None = None
    ficheiro_url: str | None = None
    formato: FormatoModelo | None = None
    metadados: dict | None = None


class VersaoSaida(Saida):
    id: str
    company_id: str
    model_id: str
    numero_versao: int
    nome: str | None
    descricao: str | None
    estado: str
    ficheiro_chave: str | None
    ficheiro_url: str | None
    formato: str | None
    metadados: dict | None
    criado_por: str | None
    validado_por: str | None
    validado_em: datetime | None
    criado_em: datetime
    actualizado_em: datetime


# ---------------------------------------------------------------- recursos
class EstimativaCriar(Entrada):
    project_id: str
    model_id: str | None = None
    nome: str = Field(min_length=2, max_length=160)
    metodo: MetodoEstimativa = "idw"
    commodity: str = Field(min_length=1, max_length=40)
    teor_corte: float | None = Field(None, ge=0)
    unidade_teor: str = Field(default="ppm", min_length=1, max_length=20)
    densidade: float | None = Field(None, gt=0)
    estado: EstadoEstimativa = "rascunho"
    volume_m3: float | None = Field(None, ge=0)
    tonelagem: float | None = Field(None, ge=0)
    metal_contido: float | None = Field(None, ge=0)
    parametros: dict | None = None
    versao: int = Field(1, ge=1)


class EstimativaActualizar(Entrada):
    model_id: str | None = None
    nome: str | None = Field(None, min_length=2, max_length=160)
    metodo: MetodoEstimativa | None = None
    commodity: str | None = Field(None, min_length=1, max_length=40)
    teor_corte: float | None = Field(None, ge=0)
    unidade_teor: str | None = Field(None, min_length=1, max_length=20)
    densidade: float | None = Field(None, gt=0)
    estado: EstadoEstimativa | None = None
    volume_m3: float | None = Field(None, ge=0)
    tonelagem: float | None = Field(None, ge=0)
    metal_contido: float | None = Field(None, ge=0)
    parametros: dict | None = None
    versao: int | None = Field(None, ge=1)


class EstimativaSaida(Saida):
    id: str
    company_id: str
    project_id: str
    model_id: str | None
    nome: str
    metodo: str
    commodity: str
    teor_corte: float | None
    unidade_teor: str
    densidade: float | None
    estado: str
    volume_m3: float | None
    tonelagem: float | None
    metal_contido: float | None
    parametros: dict | None
    versao: int
    criado_por: str | None
    validado_por: str | None
    validado_em: datetime | None
    criado_em: datetime
    actualizado_em: datetime


# ---------------------------------------------------------------- auditoria, dashboard e importação
class AuditoriaSaida(Saida):
    id: str
    company_id: str | None
    user_id: str | None
    accao: str
    entidade: str
    entidade_id: str | None
    dados_antes: dict | None
    dados_depois: dict | None
    ip: str | None
    criado_em: datetime


class DashboardSaida(BaseModel):
    projectos_activos: int
    area_explorada_km2: float
    sondagens: int
    metros_perfurados: float
    amostras: int
    resultados_laboratoriais: int
    resultados_validados: int
    modelos_geologicos: int
    estimativas: int
    tonelagem_total: float
    metal_contido_total: float
    por_estado_sondagem: dict[str, int]
    por_mineral: list[dict]


class ErroImportacao(BaseModel):
    linha: int
    mensagem: str


class ImportacaoSaida(BaseModel):
    validos: int
    criados: int
    ignorados: int
    previa: list[dict] = Field(default_factory=list)
    erros: list[ErroImportacao] = Field(default_factory=list)
