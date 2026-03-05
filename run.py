import uvicorn
from backend.app import create_app
from backend.config import get_settings

app = create_app()

if __name__ == "__main__":
    settings = get_settings()
    uvicorn.run(
        "run:app",
        host=settings.app_host,
        port=settings.app_port,
        reload=settings.debug,
    )
