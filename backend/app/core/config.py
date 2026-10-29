from functools import lru_cache

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEV_JWT_SECRET = "dev-only-insecure-secret-change-me"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file="../.env", extra="ignore")

    app_env: str = "development"
    log_level: str = "INFO"
    # Base URL put in email links. Use the PC's LAN IP so links open from a phone.
    public_base_url: str = "http://localhost:8000"

    postgres_user: str = "musicroom"
    postgres_password: str = "musicroom"
    postgres_db: str = "musicroom"
    postgres_host: str = "localhost"
    postgres_port: int = 5432

    # Per uvicorn worker. Keep workers × (pool + overflow) under Postgres max_connections (100).
    db_pool_size: int = 10
    db_max_overflow: int = 10

    redis_url: str = "redis://localhost:6379/0"

    jwt_secret: str = DEV_JWT_SECRET
    access_token_ttl_seconds: int = 900
    refresh_token_ttl_seconds: int = 1_209_600
    email_token_ttl_seconds: int = 86_400
    google_client_id_web: str = ""
    google_client_id_android: str = ""
    google_client_id_ios: str = ""

    smtp_host: str = "localhost"
    smtp_port: int = 1025
    smtp_from: str = "noreply@musicroom.local"

    # Comma-separated origins allowed by CORS (the mobile app doesn't need CORS).
    cors_origins: str = ""

    music_provider: str = "audius"
    audius_api_key: str = ""

    @property
    def database_url(self) -> str:
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def google_client_ids(self) -> list[str]:
        ids = [self.google_client_id_web, self.google_client_id_android, self.google_client_id_ios]
        return [i for i in ids if i]

    @model_validator(mode="after")
    def _refuse_weak_secret_in_production(self) -> "Settings":
        if self.app_env == "production" and (
            self.jwt_secret == DEV_JWT_SECRET or len(self.jwt_secret) < 32
        ):
            raise ValueError("JWT_SECRET must be set to 32+ random characters in production")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
