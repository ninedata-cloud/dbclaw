import logging
import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from backend.config import get_settings
from backend.database import init_db

logger = logging.getLogger(__name__)

# Global KB processor instance
kb_processor = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    settings = get_settings()
    logging.basicConfig(
        level=logging.DEBUG if settings.debug else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    logger.info(f"Starting {settings.app_name}...")

    # Initialize database
    await init_db()
    logger.info("Database initialized")

    # Start metric collector
    from backend.services.metric_collector import start_scheduler
    start_scheduler(settings.metric_interval)

    # Initialize KB processor
    from backend.services.vector_store import VectorStore
    from backend.services.kb_processor import KBProcessor

    global kb_processor
    vector_store = VectorStore(
        persist_dir=settings.chroma_persist_dir,
        embedding_model=settings.embedding_model,
    )
    kb_processor = KBProcessor(vector_store)

    # Start background processing
    asyncio.create_task(kb_processor.start_background_processing())
    logger.info("KB processor initialized")

    yield

    # Shutdown
    from backend.services.metric_collector import stop_scheduler
    stop_scheduler()
    if kb_processor:
        kb_processor.stop()
    logger.info("Application shutdown complete")


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title=settings.app_name,
        lifespan=lifespan,
    )

    # Register routers
    from backend.routers import connections, ssh_hosts, metrics, monitor_ws, chat, query, reports, ai_models, knowledge_bases, auth, users
    app.include_router(auth.router)
    app.include_router(users.router)
    app.include_router(connections.router)
    app.include_router(ssh_hosts.router)
    app.include_router(metrics.router)
    app.include_router(monitor_ws.router)
    app.include_router(chat.router)
    app.include_router(query.router)
    app.include_router(reports.router)
    app.include_router(ai_models.router)
    app.include_router(knowledge_bases.router)

    # Serve frontend static files
    app.mount("/css", StaticFiles(directory="frontend/css"), name="css")
    app.mount("/js", StaticFiles(directory="frontend/js"), name="js")
    app.mount("/assets", StaticFiles(directory="frontend/assets"), name="assets")

    @app.get("/")
    async def serve_index():
        return FileResponse("frontend/index.html")

    return app
