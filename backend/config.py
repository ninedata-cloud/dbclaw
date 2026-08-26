from pathlib import Path

from functools import lru_cache
from urllib.parse import quote

from pydantic_settings import BaseSettings, SettingsConfigDict

from backend.version import APP_VERSION, load_build_info


_BUILD_INFO = load_build_info()
PROJECT_ROOT = Path(__file__).resolve().parent.parent
ENV_FILE = PROJECT_ROOT / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=ENV_FILE,
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "DBClaw"
    app_version: str = _BUILD_INFO.get("APP_VERSION") or APP_VERSION
    build_commit: str = _BUILD_INFO.get("BUILD_COMMIT") or ""
    build_time: str = _BUILD_INFO.get("BUILD_TIME") or ""
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
    # Legacy encryption keys for decryption only (comma-separated)
    legacy_encryption_keys: str = ""
    initial_admin_password: str = "admin1234"

    database_url: str = "postgresql+asyncpg://dbclaw:dbclaw@localhost:5432/dbclaw"
    database_pool_size: int = 30
    database_max_overflow: int = 60
    database_pool_timeout_seconds: float = 10.0
    database_pool_recycle_seconds: int = 1800
    readiness_database_timeout_seconds: float = 5.0

    # TimescaleDB（PostgreSQL 扩展）：时序表 hypertable / 压缩 / 可选保留策略
    timescale_enable: bool = True
    timescale_require_extension: bool = False
    timescale_chunk_interval: str = "1 day"
    timescale_compress_after: str = "7 days"
    timescale_retention_interval: str = ""

    metric_interval: int = 60
    datasource_collection_concurrency: int = 24
    datasource_operation_timeout_seconds: float = 30.0
    datasource_probe_timeout_seconds: float = 10.0
    connector_close_timeout_seconds: float = 5.0
    host_collection_concurrency: int = 15
    host_collection_overrun_backoff_seconds: float = 5.0
    host_metric_max_age_seconds: int = 180
    ssh_failure_backoff_base_seconds: float = 30.0
    ssh_failure_backoff_max_seconds: float = 300.0
    integration_collection_concurrency: int = 12
    metadata_write_concurrency: int = 9

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

    @property
    def resolved_app_version(self) -> str:
        return self.app_version.strip() or APP_VERSION

    @property
    def resolved_build_commit(self) -> str:
        return self.build_commit.strip()

    @property
    def resolved_build_time(self) -> str:
        return self.build_time.strip()

    @property
    def frontend_asset_version(self) -> str:
        raw_version = self.resolved_build_commit
        if not raw_version:
            app_version = self.resolved_app_version
            build_time = self.resolved_build_time
            raw_version = f"{app_version}-{build_time}" if build_time else app_version
        return quote(raw_version, safe="-._~")


@lru_cache
def get_settings() -> Settings:
    return Settings()


# Export commonly used settings as module-level constants
settings = get_settings()
DATABASE_URL = settings.database_url
ALERT_AGGREGATION_TIME_WINDOW_MINUTES = settings.alert_aggregation_time_window_minutes
