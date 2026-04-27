import logging

import uvicorn
from backend.app import create_app
from backend.config import get_settings
from backend.logging_config import configure_logging
from backend.services.startup_self_check import run_startup_self_check_sync

app = create_app()

if __name__ == "__main__":
    settings = get_settings()
    configure_logging(settings)
    logger = logging.getLogger(__name__)
    startup_report = run_startup_self_check_sync(settings, include_app_port_check=True)
    if not startup_report.ok:
        logger.error("\n%s", startup_report.to_console_text())
        raise SystemExit(1)
    if startup_report.warning_count:
        logger.warning("\n%s", startup_report.to_console_text(include_passes=False))
    uvicorn.run(
        "run:app",
        host=settings.app_host,
        port=settings.app_port,
        reload=settings.debug,
        access_log=settings.access_log_enabled,
        log_config=None,
    )
