"""Application configuration using Pydantic Settings."""

from functools import lru_cache
from typing import Any

from pydantic import PostgresDsn, RedisDsn, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Application
    app_name: str = "UFC Prediction API"
    app_env: str = "development"
    debug: bool = False
    api_v1_prefix: str = "/api/v1"

    # Server
    host: str = "0.0.0.0"
    port: int = 8000

    # Database
    database_url: PostgresDsn
    database_echo: bool = False

    # Redis
    redis_url: RedisDsn = "redis://localhost:6379/0"  # type: ignore

    # Authentication
    jwt_secret_key: str
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 7

    # External APIs
    the_odds_api_key: str = ""
    espn_api_base_url: str = "https://site.api.espn.com/apis/site/v2/sports/mma/ufc"

    # Rate Limiting (requests per minute)
    rate_limit_anonymous: int = 30
    rate_limit_authenticated: int = 100
    rate_limit_premium: int = 500

    # CORS
    cors_origins: list[str] = ["http://localhost:3000", "http://localhost:8080"]

    # Logging
    log_level: str = "INFO"
    log_format: str = "json"  # "json" or "console"

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, v: Any) -> list[str]:
        """Parse CORS origins from string or list."""
        if isinstance(v, str):
            # Handle JSON-encoded list
            if v.startswith("["):
                import json

                return json.loads(v)
            # Handle comma-separated string
            return [origin.strip() for origin in v.split(",")]
        return v

    @property
    def is_development(self) -> bool:
        """Check if running in development mode."""
        return self.app_env == "development"

    @property
    def is_production(self) -> bool:
        """Check if running in production mode."""
        return self.app_env == "production"

    @property
    def database_url_sync(self) -> str:
        """Get synchronous database URL for Alembic migrations."""
        return str(self.database_url).replace("+asyncpg", "")


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()  # type: ignore


# Convenience alias
settings = get_settings()
