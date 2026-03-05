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

    metric_interval: int = 15

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


@lru_cache
def get_settings() -> Settings:
    return Settings()
