from pydantic_settings import BaseSettings
from functools import lru_cache
from urllib.parse import quote


class Settings(BaseSettings):
    app_name: str = "DBClaw"
    app_version: str = "1.0.0"
    build_commit: str = ""
    build_time: str = "2026-04-15"
    app_host: str = "0.0.0.0"
    app_port: int = 9939
    debug: bool = True
    log_level: str = ""
    log_format: str = "text"
    access_log_enabled: bool = True
    log_file_enabled: bool = True
    log_dir: str = "data/logs"
    log_file_max_bytes: int = 104857600
    log_file_backup_count: int = 10

    encryption_key: str = "temporary-encryption-key"
    initial_admin_password: str = "admin1234"

    database_url: str = "postgresql+asyncpg://dbclaw:dbclaw@localhost:5432/dbclaw"

    metric_interval: int = 60

    # Inspection trigger deduplication window (in minutes)
    inspection_dedup_window_minutes: int = 60

    # Alert aggregation time window (in minutes)
    alert_aggregation_time_window_minutes: int = 5

    # Token settings
    jwt_algorithm: str = "HS256"
    public_share_secret_key: str = "change-me-to-a-random-public-share-secret"
    public_share_expire_minutes: int = 1440

    # Session settings
    session_cookie_name: str = "dbclaw_session"
    session_idle_timeout_minutes: int = 1440
    session_cookie_secure: bool = False
    session_cookie_samesite: str = "lax"

    # Bocha AI Web Search API
    bocha_api_key: str = ""
    bocha_api_url: str = "https://api.bochaai.com/v1/web-search"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"

    @property
    def frontend_asset_version(self) -> str:
        raw_version = self.build_commit.strip()
        if not raw_version:
            app_version = self.app_version.strip() or "dev"
            build_time = self.build_time.strip()
            raw_version = f"{app_version}-{build_time}" if build_time else app_version
        return quote(raw_version, safe="-._~")


@lru_cache
def get_settings() -> Settings:
    return Settings()


# Export commonly used settings as module-level constants
settings = get_settings()
DATABASE_URL = settings.database_url
ALERT_AGGREGATION_TIME_WINDOW_MINUTES = settings.alert_aggregation_time_window_minutes
