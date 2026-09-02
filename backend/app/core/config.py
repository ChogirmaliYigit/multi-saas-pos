from __future__ import annotations

from functools import lru_cache
from typing import Annotated, Literal

from pydantic import Field, PostgresDsn, computed_field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore", case_sensitive=True
    )

    PROJECT_NAME: str = "Multi-Tenant POS"
    API_V1_PREFIX: str = "/api/v1"
    ENVIRONMENT: Literal["development", "staging", "production"] = "development"
    DEBUG: bool = False
    LOG_LEVEL: str = "INFO"

    # --- security ---------------------------------------------------------
    # No default. A missing SECRET_KEY must crash the app at boot, not
    # silently sign tokens with a value an attacker can read on GitHub.
    SECRET_KEY: str
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 30
    # A cashier's token is short-lived; a terminal left unattended in a shop is
    # a bigger risk than an admin's laptop.
    POS_ACCESS_TOKEN_EXPIRE_MINUTES: int = 720
    MAX_FAILED_LOGINS: int = 5
    LOCKOUT_MINUTES: int = 15

    # --- database ---------------------------------------------------------
    # Two roles on purpose. PostgreSQL lets superusers and table owners bypass
    # RLS, so the API must NOT connect as either -- otherwise layer 3 of the
    # isolation story silently does nothing. POSTGRES_USER is the unprivileged
    # runtime role; the admin role only ever runs migrations.
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5432
    POSTGRES_USER: str = "pos_app"
    POSTGRES_PASSWORD: str = "pos_app"
    POSTGRES_DB: str = "pos"
    POSTGRES_ADMIN_USER: str = "pos"
    POSTGRES_ADMIN_PASSWORD: str = "pos"
    DB_POOL_SIZE: int = 10
    DB_MAX_OVERFLOW: int = 20
    DB_ECHO: bool = False

    # --- infra ------------------------------------------------------------
    REDIS_URL: str = "redis://localhost:6379/0"
    CELERY_BROKER_URL: str = "redis://localhost:6379/1"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/2"

    # --- tenancy / http ---------------------------------------------------
    # Subdomain host suffix: shop1.saas-pos.com -> slug "shop1".
    BASE_DOMAIN: str = "localhost"
    # NoDecode: pydantic-settings would otherwise try to JSON-parse this from
    # the environment before any validator runs, so the natural
    # `CORS_ORIGINS=http://a,http://b` form would crash at boot.
    CORS_ORIGINS: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["http://localhost:3000"]
    )
    # Allow *.BASE_DOMAIN through CORS so every tenant subdomain works without
    # enumerating them.
    CORS_ALLOW_SUBDOMAIN_WILDCARD: bool = True

    # Bootstrap platform operator, created by `python -m app.db.seed` when
    # both are set. Read through Settings rather than os.getenv, because
    # pydantic-settings loads .env into this object and NOT into the process
    # environment -- os.getenv would silently ignore a documented .env value.
    SUPER_ADMIN_EMAIL: str | None = None
    SUPER_ADMIN_PASSWORD: str | None = None

    REPORT_STORAGE_DIR: str = "/var/lib/pos/reports"
    REPORT_RETENTION_HOURS: int = 48

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def _split_origins(cls, v: object) -> object:
        if isinstance(v, str):
            return [o.strip() for o in v.split(",") if o.strip()]
        return v

    @field_validator("SECRET_KEY")
    @classmethod
    def _reject_weak_secret(cls, v: str) -> str:
        if len(v) < 32:
            raise ValueError("SECRET_KEY must be at least 32 characters")
        return v

    @computed_field  # type: ignore[prop-decorator]
    @property
    def SQLALCHEMY_DATABASE_URI(self) -> str:
        return str(
            PostgresDsn.build(
                scheme="postgresql+asyncpg",
                username=self.POSTGRES_USER,
                password=self.POSTGRES_PASSWORD,
                host=self.POSTGRES_HOST,
                port=self.POSTGRES_PORT,
                path=self.POSTGRES_DB,
            )
        )

    @computed_field  # type: ignore[prop-decorator]
    @property
    def CELERY_DATABASE_URI(self) -> str:
        """Celery workers: sync driver, same unprivileged role as the API."""
        return self.SQLALCHEMY_DATABASE_URI.replace("+asyncpg", "+psycopg")

    @computed_field  # type: ignore[prop-decorator]
    @property
    def SYNC_DATABASE_URI(self) -> str:
        """Alembic only. Owns the schema, and is deliberately the one
        connection in the system that RLS does not constrain."""
        return str(
            PostgresDsn.build(
                scheme="postgresql+psycopg",
                username=self.POSTGRES_ADMIN_USER,
                password=self.POSTGRES_ADMIN_PASSWORD,
                host=self.POSTGRES_HOST,
                port=self.POSTGRES_PORT,
                path=self.POSTGRES_DB,
            )
        )

    @computed_field  # type: ignore[prop-decorator]
    @property
    def is_production(self) -> bool:
        return self.ENVIRONMENT == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]


settings = get_settings()
