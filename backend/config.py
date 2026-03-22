from pydantic_settings import BaseSettings
from functools import lru_cache
import os


class Settings(BaseSettings):
    app_name: str = "NineData DBGuard"
    app_host: str = "0.0.0.0"
    app_port: int = 9939
    debug: bool = True

    encryption_key: str = "temporary-encryption-key"

    openai_api_key: str = ""
    openai_base_url: str = "https://api.openai.com/v1"
    openai_model: str = ""

    database_url: str = "postgresql+asyncpg://dbguard:dbguard@localhost:5432/dbguard"

    metric_interval: int = 60

    # Inspection trigger deduplication window (in minutes)
    inspection_dedup_window_minutes: int = 60

    # Alert aggregation time window (in minutes)
    alert_aggregation_time_window_minutes: int = 5

    # JWT settings
    jwt_secret_key: str = "change-me-to-a-random-secret-key"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 1440

    # Bocha AI Web Search API
    bocha_api_key: str = "sk-66d203942a6c404b89eff2adb494febc"
    bocha_api_url: str = "https://api.bochaai.com/v1/web-search"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


@lru_cache
def get_settings() -> Settings:
    return Settings()


# Export commonly used settings as module-level constants
settings = get_settings()
DATABASE_URL = settings.database_url
ALERT_AGGREGATION_TIME_WINDOW_MINUTES = settings.alert_aggregation_time_window_minutes

