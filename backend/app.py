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

    # Start Inspection Service
    from backend.services.inspection_service import InspectionService
    from backend.services import metric_collector
    from backend.database import async_session

    inspection_service = InspectionService(async_session)
    await inspection_service.start()
    metric_collector.set_inspection_service(inspection_service)
    logger.info("🔍 Inspection Service activated")

    # Start SSH host metrics collector
    from backend.services.host_collector import collect_host_metrics
    asyncio.create_task(collect_host_metrics())
    logger.info("📊 Host metrics collector started")

    yield

    # Shutdown
    from backend.services.metric_collector import stop_scheduler
    stop_scheduler()
    if kb_processor:
        kb_processor.stop()
    await inspection_service.stop()
    logger.info("Application shutdown complete")


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title=settings.app_name,
        lifespan=lifespan,
    )

    # Register routers
    from backend.routers import datasources, hosts, metrics, monitor_ws, chat, query, ai_models, knowledge_bases, auth, users, inspections
    from backend.api import skills
    app.include_router(auth.router)
    app.include_router(users.router)
    app.include_router(datasources.router)
    app.include_router(hosts.router)
    app.include_router(metrics.router)
    app.include_router(monitor_ws.router)
    app.include_router(chat.router)
    app.include_router(query.router)
    app.include_router(ai_models.router)
    app.include_router(knowledge_bases.router)
    app.include_router(skills.router)
    app.include_router(inspections.router)

    # Serve frontend static files
    app.mount("/css", StaticFiles(directory="frontend/css"), name="css")
    app.mount("/js", StaticFiles(directory="frontend/js"), name="js")
    app.mount("/assets", StaticFiles(directory="frontend/assets"), name="assets")
    app.mount("/lib", StaticFiles(directory="frontend/lib"), name="lib")

    @app.get("/")
    async def serve_index():
        return FileResponse("frontend/index.html")

    return app


# Create app instance
app = create_app()
