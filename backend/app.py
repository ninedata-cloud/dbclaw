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

    # Run migrations for new columns
    try:
        from backend.migrations.add_datasource_connection_status import migrate as migrate_conn_status
        await migrate_conn_status()
    except Exception as e:
        logger.warning(f"Connection status migration: {e}")

    try:
        from backend.migrations.add_alert_notified_at import migrate as migrate_alert_notified
        await migrate_alert_notified()
    except Exception as e:
        logger.warning(f"Alert notified_at migration: {e}")

    # Seed default system configs
    from backend.database import async_session as _async_session
    from backend.services import config_service as _config_service
    async with _async_session() as _db:
        await _config_service.set_config(
            _db,
            key="inspection_dedup_window_minutes",
            value=str(settings.inspection_dedup_window_minutes),
            value_type="integer",
            description="巡检触发去重窗口（分钟），同一数据源在此时间内不重复触发巡检",
            category="inspection"
        ) if not await _config_service.get_config(_db, "inspection_dedup_window_minutes") else None

        # Seed default SMTP notification configs
        smtp_defaults = [
            ("smtp_host", "", "string", "SMTP服务器地址"),
            ("smtp_port", "587", "integer", "SMTP服务器端口（默认587，SSL使用465）"),
            ("smtp_username", "", "string", "SMTP登录用户名"),
            ("smtp_password", "", "string", "SMTP登录密码"),
            ("smtp_from_email", "", "string", "发件人邮箱地址"),
            ("smtp_use_tls", "true", "boolean", "是否启用STARTTLS加密"),
        ]

        # Seed default Aliyun configs
        aliyun_defaults = [
            ("aliyun_access_key_id", "", "string", "阿里云 AccessKey ID（用于 RDS 监控数据采集）"),
            ("aliyun_access_key_secret", "", "string", "阿里云 AccessKey Secret（用于 RDS 监控数据采集）"),
        ]

        from sqlalchemy import select as _select
        from backend.models.system_config import SystemConfig as _SystemConfig

        # Seed SMTP configs
        for key, default_val, val_type, desc in smtp_defaults:
            _exists = await _db.execute(_select(_SystemConfig).where(_SystemConfig.key == key))
            if not _exists.scalar_one_or_none():
                await _config_service.set_config(
                    _db, key=key, value=default_val,
                    value_type=val_type, description=desc,
                    category="notification"
                )

        # Seed Aliyun configs
        for key, default_val, val_type, desc in aliyun_defaults:
            _exists = await _db.execute(_select(_SystemConfig).where(_SystemConfig.key == key))
            if not _exists.scalar_one_or_none():
                await _config_service.set_config(
                    _db, key=key, value=default_val,
                    value_type=val_type, description=desc,
                    category="integration"
                )
    logger.info("Default system configs seeded")

    # Start SSH connection pool
    from backend.services.ssh_connection_pool import start_ssh_pool
    await start_ssh_pool()
    logger.info("SSH connection pool started")

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

    # Start notification dispatcher
    from backend.services.notification_dispatcher import start_notification_dispatcher
    asyncio.create_task(start_notification_dispatcher())
    logger.info("🔔 Notification dispatcher started")

    # Load builtin integration templates
    from backend.services.integration_service import IntegrationService
    async with async_session() as _db:
        await IntegrationService.load_builtin_templates(_db)
    logger.info("📦 Integration templates loaded")

    # Start integration scheduler
    from backend.services.integration_scheduler import start_integration_scheduler
    asyncio.create_task(start_integration_scheduler())
    logger.info("🔄 Integration scheduler started")

    yield

    # Shutdown
    from backend.services.metric_collector import stop_scheduler
    from backend.services.ssh_connection_pool import stop_ssh_pool
    from backend.services.integration_scheduler import stop_integration_scheduler

    stop_scheduler()
    stop_integration_scheduler()
    if kb_processor:
        kb_processor.stop()
    await inspection_service.stop()
    await stop_ssh_pool()
    logger.info("Application shutdown complete")


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title=settings.app_name,
        lifespan=lifespan,
    )

    # Global exception handler for detailed logging
    @app.exception_handler(Exception)
    async def global_exception_handler(request, exc):
        from fastapi.responses import JSONResponse
        import traceback

        # Log detailed error information
        logger.error(f"Unhandled exception in {request.method} {request.url.path}")
        logger.error(f"Exception type: {type(exc).__name__}")
        logger.error(f"Exception message: {str(exc)}")
        logger.error(f"Traceback:\n{traceback.format_exc()}")

        # Log request details
        logger.error(f"Request headers: {dict(request.headers)}")
        try:
            body = await request.body()
            if body:
                logger.error(f"Request body: {body.decode('utf-8')}")
        except:
            pass

        return JSONResponse(
            status_code=500,
            content={
                "detail": f"Internal server error: {str(exc)}",
                "type": type(exc).__name__
            }
        )

    @app.get("/health")
    async def health_check():
        return {"status": "ok"}

    # Register routers
    from backend.routers import datasources, hosts, metrics, monitor_ws, chat, query, ai_models, knowledge_bases, auth, users, inspections, system_configs, alerts, integrations
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
    app.include_router(system_configs.router)
    app.include_router(alerts.router)
    app.include_router(integrations.router)

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
