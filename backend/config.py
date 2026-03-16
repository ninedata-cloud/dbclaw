from pydantic_settings import BaseSettings
from functools import lru_cache
import os


class Settings(BaseSettings):
    app_name: str = "NineData DBMaster"
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    debug: bool = True

    encryption_key: str = ""

    openai_api_key: str = ""
    openai_base_url: str = "https://api.openai.com/v1"
    openai_model: str = "gpt-4o"

    database_url: str = "sqlite+aiosqlite:///./data/smartdba.db"

    metric_interval: int = 60

    # Inspection trigger deduplication window (in minutes)
    inspection_dedup_window_minutes: int = 60

    # JWT settings
    jwt_secret_key: str = "change-me-to-a-random-secret-key"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 1440

    # Knowledge Base settings
    chroma_persist_dir: str = "./data/chroma"
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    knowledge_base_dir: str = "./data/knowledge_bases"

    # Bocha AI Web Search API
    bocha_api_key: str = "sk-66d203942a6c404b89eff2adb494febc"
    bocha_api_url: str = "https://api.bochaai.com/v1/web-search"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


@lru_cache
def get_settings() -> Settings:
    return Settings()
