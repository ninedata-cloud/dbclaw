import json
import logging
import logging.config
import os
from datetime import datetime, timezone


class MaxLevelFilter(logging.Filter):
    def __init__(self, level: int | str):
        super().__init__()
        self.level = logging._checkLevel(level)

    def filter(self, record: logging.LogRecord) -> bool:
        return record.levelno <= self.level


class MinLevelFilter(logging.Filter):
    def __init__(self, level: int | str):
        super().__init__()
        self.level = logging._checkLevel(level)

    def filter(self, record: logging.LogRecord) -> bool:
        return record.levelno >= self.level


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).astimezone().isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)

        if record.stack_info:
            payload["stack_info"] = self.formatStack(record.stack_info)

        return json.dumps(payload, ensure_ascii=False)


def build_logging_config(settings) -> dict:
    log_level = (settings.log_level or "").strip().upper() or ("DEBUG" if settings.debug else "INFO")
    formatter_name = "json" if settings.log_format.lower() == "json" else "text"
    log_dir = os.path.abspath(settings.log_dir)

    handlers = {
        "stdout": {
            "class": "logging.StreamHandler",
            "level": log_level,
            "formatter": formatter_name,
            "stream": "ext://sys.stdout",
            "filters": ["warnings_and_below"],
        },
        "stderr": {
            "class": "logging.StreamHandler",
            "level": "ERROR",
            "formatter": formatter_name,
            "stream": "ext://sys.stderr",
            "filters": ["errors_and_above"],
        },
    }

    root_handlers = ["stdout", "stderr"]
    uvicorn_handlers = ["stdout", "stderr"]
    uvicorn_access_handlers = ["stdout"]

    if settings.log_file_enabled:
        os.makedirs(os.path.join(log_dir, "app"), exist_ok=True)
        handlers["app_file"] = {
            "class": "logging.handlers.RotatingFileHandler",
            "level": log_level,
            "formatter": formatter_name,
            "filename": os.path.join(log_dir, "app", "app.log"),
            "maxBytes": settings.log_file_max_bytes,
            "backupCount": settings.log_file_backup_count,
            "encoding": "utf-8",
        }
        handlers["error_file"] = {
            "class": "logging.handlers.RotatingFileHandler",
            "level": "ERROR",
            "formatter": formatter_name,
            "filename": os.path.join(log_dir, "app", "error.log"),
            "maxBytes": settings.log_file_max_bytes,
            "backupCount": settings.log_file_backup_count,
            "encoding": "utf-8",
        }
        root_handlers.extend(["app_file", "error_file"])
        uvicorn_handlers.extend(["app_file", "error_file"])
        uvicorn_access_handlers.append("app_file")

    return {
        "version": 1,
        "disable_existing_loggers": False,
        "filters": {
            "warnings_and_below": {
                "()": "backend.logging_config.MaxLevelFilter",
                "level": "WARNING",
            },
            "errors_and_above": {
                "()": "backend.logging_config.MinLevelFilter",
                "level": "ERROR",
            },
        },
        "formatters": {
            "text": {
                "format": "%(asctime)s %(levelname)s [%(name)s] %(message)s",
            },
            "json": {
                "()": "backend.logging_config.JsonFormatter",
            },
        },
        "handlers": handlers,
        "root": {
            "level": log_level,
            "handlers": root_handlers,
        },
        "loggers": {
            "uvicorn": {
                "level": log_level,
                "handlers": uvicorn_handlers,
                "propagate": False,
            },
            "uvicorn.error": {
                "level": log_level,
                "handlers": uvicorn_handlers,
                "propagate": False,
            },
            "uvicorn.access": {
                "level": "INFO",
                "handlers": uvicorn_access_handlers,
                "propagate": False,
            },
        },
    }


def configure_logging(settings) -> None:
    logging.config.dictConfig(build_logging_config(settings))
