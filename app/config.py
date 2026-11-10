"""Configuração da aplicação, lida do ambiente ou do ficheiro .env."""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_nome: str = "CLACS GeoModel"
    ambiente: str = "desenvolvimento"
    database_url: str = "sqlite:///./geomodel.db"
    jwt_secret: str = "mudar-este-segredo-em-producao-com-pelo-menos-32-bytes"
    jwt_expira_minutos: int = 480
    cors_origins: str = "*"
    admin_email: str = "admin@clacs.ao"
    admin_password: str = "admin123"
    auto_criar_tabelas: bool = True

    @property
    def origens(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
