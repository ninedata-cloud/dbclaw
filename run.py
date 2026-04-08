import sys

import uvicorn
from backend.app import create_app
from backend.config import get_settings
from backend.services.startup_self_check import run_startup_self_check_sync

app = create_app()

if __name__ == "__main__":
    settings = get_settings()
    startup_report = run_startup_self_check_sync(settings, include_app_port_check=True)
    if not startup_report.ok:
        print(startup_report.to_console_text(), file=sys.stderr)
        raise SystemExit(1)
    if startup_report.warning_count:
        print(startup_report.to_console_text(include_passes=False), file=sys.stderr)
    uvicorn.run(
        "run:app",
        host=settings.app_host,
        port=settings.app_port,
        reload=settings.debug,
    )
