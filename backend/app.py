import logging
import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from backend.config import get_settings
from backend.database import init_db

logger = logging.getLogger(__name__)


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
        from backend.migrations.add_datasource_tags import migrate as migrate_datasource_tags
        await migrate_datasource_tags()
    except Exception as e:
        logger.warning(f"Datasource tags migration: {e}")

    try:
        from backend.migrations.add_alert_notified_at import migrate as migrate_alert_notified
        await migrate_alert_notified()
    except Exception as e:
        logger.warning(f"Alert notified_at migration: {e}")

    try:
        from backend.migrations.replace_knowledge_base_with_documents import migrate as migrate_docs
        await migrate_docs()
    except Exception as e:
        logger.warning(f"Document migration: {e}")

    try:
        from backend.migrations.add_ai_model_context_window import migrate as migrate_ai_model_context_window
        await migrate_ai_model_context_window()
    except Exception as e:
        logger.warning(f"AI model context_window migration: {e}")

    try:
        from backend.migrations.add_diagnostic_session_token_usage import migrate as migrate_diagnostic_session_token_usage
        await migrate_diagnostic_session_token_usage()
    except Exception as e:
        logger.warning(f"Diagnostic session token usage migration: {e}")

    try:
        from backend.migrations.add_chat_message_token_usage import migrate as migrate_chat_message_token_usage
        await migrate_chat_message_token_usage()
    except Exception as e:
        logger.warning(f"Chat message token usage migration: {e}")

    try:
        from backend.migrations.add_report_alert_link import migrate as migrate_report_alert_link
        await migrate_report_alert_link()
    except Exception as e:
        logger.warning(f"Report alert link migration: {e}")

    try:
        from backend.migrations.add_trigger_alert_link import migrate as migrate_trigger_alert_link
        await migrate_trigger_alert_link()
    except Exception as e:
        logger.warning(f"Trigger alert link migration: {e}")

    try:
        from backend.migrations.add_user_session_security import migrate as migrate_user_session_security
        await migrate_user_session_security()
    except Exception as e:
        logger.warning(f"User session security migration: {e}")

    try:
        from backend.migrations.add_feishu_chat_tables import migrate as migrate_feishu_chat_tables
        await migrate_feishu_chat_tables()
    except Exception as e:
        logger.warning(f"Feishu chat tables migration: {e}")

    try:
        from backend.migrations.fix_feishu_chat_event_dedup_duplicates import migrate as fix_feishu_chat_event_dedup_duplicates
        await fix_feishu_chat_event_dedup_duplicates()
    except Exception as e:
        logger.warning(f"Feishu chat event dedup fix migration: {e}")

    # P1 migrations: structured recommended actions + action run audit
    try:
        from backend.migrations.add_report_recommended_actions import migrate as migrate_report_recommended_actions
        await migrate_report_recommended_actions()
    except Exception as e:
        logger.warning(f"Report recommended_actions migration: {e}")

    try:
        from backend.migrations.create_action_runs import migrate as migrate_action_runs
        await migrate_action_runs()
    except Exception as e:
        logger.warning(f"Action runs migration: {e}")

    try:
        from backend.migrations.add_subscription_integration_targets import migrate as migrate_subscription_integration_targets
        await migrate_subscription_integration_targets()
    except Exception as e:
        logger.warning(f"Subscription integration_targets migration: {e}")

    try:
        from backend.migrations.add_datasource_inbound_source import migrate as migrate_datasource_inbound_source
        await migrate_datasource_inbound_source()
    except Exception as e:
        logger.warning(f"Datasource inbound_source migration: {e}")

    try:
        from backend.migrations.add_bot_bindings import migrate as migrate_bot_bindings
        await migrate_bot_bindings()
    except Exception as e:
        logger.warning(f"Bot bindings migration: {e}")

    try:
        from backend.migrations.extend_integration_execution_logs_for_targets import migrate as migrate_integration_execution_log_targets
        await migrate_integration_execution_log_targets()
    except Exception as e:
        logger.warning(f"Integration execution log targets migration: {e}")

    try:
        from backend.migrations.extend_alert_delivery_log_targets import migrate as migrate_alert_delivery_log_targets
        await migrate_alert_delivery_log_targets()
    except Exception as e:
        logger.warning(f"Alert delivery log targets migration: {e}")

    try:
        from backend.migrations.migrate_alert_channels_to_subscription_targets import migrate as migrate_alert_channels_to_subscription_targets
        await migrate_alert_channels_to_subscription_targets()
    except Exception as e:
        logger.warning(f"Alert channel to subscription target migration: {e}")

    try:
        from backend.migrations.migrate_inbound_integrations_to_datasource_sources import migrate as migrate_inbound_integrations_to_datasource_sources
        await migrate_inbound_integrations_to_datasource_sources()
    except Exception as e:
        logger.warning(f"Inbound integration to datasource source migration: {e}")

    try:
        from backend.migrations.migrate_feishu_bot_channel_to_bot_binding import migrate as migrate_feishu_bot_channel_to_bot_binding
        await migrate_feishu_bot_channel_to_bot_binding()
    except Exception as e:
        logger.warning(f"Feishu bot channel to bot binding migration: {e}")

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

        # Seed network probe config
        _probe_exists = await _db.execute(_select(_SystemConfig).where(_SystemConfig.key == "network_probe_host"))
        if not _probe_exists.scalar_one_or_none():
            await _config_service.set_config(
                _db,
                key="network_probe_host",
                value="127.0.0.1",
                value_type="string",
                description="网络探针目标地址，采集前用于检测网络连通性（默认 127.0.0.1，可改为网关 IP）",
                category="monitoring"
            )

        _external_base_exists = await _db.execute(_select(_SystemConfig).where(_SystemConfig.key == "app_external_base_url"))
        if not _external_base_exists.scalar_one_or_none():
            await _config_service.set_config(
                _db,
                key="app_external_base_url",
                value="",
                value_type="string",
                description="外部访问基础地址，用于生成飞书等通知中的免登录详情链接，例如 https://dbguard.example.com",
                category="notification"
            )
    logger.info("Default system configs seeded")

    # Start SSH connection pool
    from backend.services.ssh_connection_pool import start_ssh_pool
    await start_ssh_pool()
    logger.info("SSH connection pool started")

    # Start metric collector
    from backend.services.metric_collector import start_scheduler
    start_scheduler(settings.metric_interval)

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

    # Start Weixin bot poller
    from backend.services.weixin_bot_service import start_weixin_bot_poller
    await start_weixin_bot_poller()

    yield

    # Shutdown
    from backend.services.metric_collector import stop_scheduler
    from backend.services.ssh_connection_pool import stop_ssh_pool
    from backend.services.integration_scheduler import stop_integration_scheduler
    from backend.services.weixin_bot_service import stop_weixin_bot_poller

    stop_scheduler()
    stop_integration_scheduler()
    await stop_weixin_bot_poller()
    await inspection_service.stop()
    await stop_ssh_pool()
    logger.info("Application shutdown complete")


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title=settings.app_name,
        lifespan=lifespan,
    )

    @app.exception_handler(Exception)
    async def global_exception_handler(request, exc):
        from fastapi.responses import JSONResponse
        import traceback

        logger.error(
            "Unhandled exception in %s %s [%s]: %s\n%s",
            request.method,
            request.url.path,
            type(exc).__name__,
            str(exc),
            traceback.format_exc(),
        )

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
    from backend.routers import datasources, hosts, metrics, monitor_ws, chat, query, ai_models, auth, users, inspections, system_configs, alerts, integrations, documents, feishu_bot, integration_bots, weixin_bot
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
    app.include_router(documents.router)
    app.include_router(skills.router)
    app.include_router(inspections.router)
    app.include_router(system_configs.router)
    app.include_router(alerts.router)
    app.include_router(integrations.router)
    app.include_router(integration_bots.router)
    app.include_router(feishu_bot.router)
    app.include_router(weixin_bot.router)

    # Serve frontend static files
    app.mount("/css", StaticFiles(directory="frontend/css"), name="css")
    app.mount("/js", StaticFiles(directory="frontend/js"), name="js")
    app.mount("/assets", StaticFiles(directory="frontend/assets"), name="assets")
    app.mount("/lib", StaticFiles(directory="frontend/lib"), name="lib")

    @app.get("/")
    async def serve_index():
        return FileResponse("frontend/index.html")

    @app.get("/public/alerts/{alert_id}")
    async def serve_public_alert_entry(alert_id: int):
        return FileResponse("frontend/index.html")

    @app.get("/public/reports/{report_id}")
    async def serve_public_report_entry(report_id: int):
        return FileResponse("frontend/index.html")

    return app


# Create app instance
app = create_app()
