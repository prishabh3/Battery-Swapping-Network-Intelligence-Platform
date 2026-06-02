from functools import lru_cache
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql+asyncpg://bsip:bsip_secret@localhost:5432/battery_swapping"
    sync_database_url: str = "postgresql+psycopg2://bsip:bsip_secret@localhost:5432/battery_swapping"
    secret_key: str = "dev-secret-key-change-in-prod-32ch"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 480
    log_level: str = "INFO"
    environment: str = "development"

    model_config = {"env_file": ".env", "extra": "ignore"}


@lru_cache
def get_settings() -> Settings:
    return Settings()
