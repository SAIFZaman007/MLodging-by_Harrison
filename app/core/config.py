"""
Centralized application configuration.

All runtime config comes from environment variables (see `.env.example`).
Nothing here is hard-coded to a specific environment — the same image/process
runs in dev, staging, and prod purely by swapping env vars.
"""
from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --- App ---
    APP_NAME: str = "8888 Masters API"
    ENVIRONMENT: Literal["development", "staging", "production"] = "development"
    DEBUG: bool = True
    API_V1_PREFIX: str = "/api/v1"
    
    # Enable/disable demo data seeding safety guard
    ALLOW_DEMO_SEED: bool = True

    # --- Database ---
    DATABASE_URL: str = Field(
        default="postgresql+asyncpg://postgres:postgres@localhost:5432/masters_lodging"
    )

    # --- Auth ---
    SECRET_KEY: str = Field(
        default="CHANGE_ME_dev_only_insecure_key",
        description="Used to sign JWTs. MUST be overridden in staging/production.",
    )
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    REFRESH_TOKEN_EXPIRE_DAYS: int = 14

    # --- CORS ---
    CORS_ORIGINS: str = "http://localhost:5173,http://localhost:5174"

    # --- Business info ---
    BUSINESS_NAME: str = "8888 Masters"
    BUSINESS_PHONE: str = "+16024788888"
    BUSINESS_EMAIL: str = "chris_stocks@yahoo.com"
    SITE_URL: str = "https://8888masters.com"

    # --- Rate limiting ---
    RATE_LIMIT_DEFAULT: str = "120/minute"
    RATE_LIMIT_INQUIRY: str = "5/minute"

    @field_validator("SECRET_KEY")
    @classmethod
    def warn_on_insecure_secret(cls, v: str) -> str:
        return v

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]

    @property
    def is_production(self) -> bool:
        return self.ENVIRONMENT == "production"


@lru_cache
def get_settings() -> "Settings":
    """Cached settings singleton — env is only parsed once per process."""
    return Settings()


settings = get_settings()