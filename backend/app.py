import logging
import asyncio
import json
import re
from pathlib import Path
from contextlib import asynccontextmanager
from fastapi import Depends, FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from fastapi.responses import JSONResponse
from urllib.parse import parse_qs, parse_qsl, urlencode, urlsplit, urlunsplit

from backend.config import get_settings
from backend.dependencies import get_current_admin
from backend.database import init_db
from backend.services.startup_self_check import (
    get_last_startup_report,
    run_readiness_self_check,
    run_startup_self_check,
    set_last_startup_report,
)
from backend.services.monitoring_scheduler_service import (
    DEFAULT_MONITORING_COLLECTION_INTERVAL_SECONDS,
    MONITORING_COLLECTION_INTERVAL_CONFIG_KEY,
    get_monitoring_collection_interval_seconds,
)

logger = logging.getLogger(__name__)

FRONTEND_INDEX_PATH = Path("frontend/index.html")
STATIC_ASSET_PATTERN = re.compile(r'(?P<prefix>\b(?:href|src)=["\'])(?P<url>/(?:css|js|lib|assets)/[^"\']+)(?P<suffix>["\'])')


class VersionedStaticFiles(StaticFiles):
    async def get_response(self, path, scope):
        response = await super().get_response(path, scope)
        query = parse_qs(scope.get("query_string", b"").decode("latin-1"))
        if "build" in query:
            response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        else:
            response.headers["Cache-Control"] = "no-cache, max-age=0, must-revalidate"
        return response


def get_app_info_payload(settings):
    return {
        "app_name": settings.app_name,
        "app_version": settings.app_version,
        "build_commit": settings.build_commit,
        "build_time": settings.build_time,
        "frontend_asset_version": settings.frontend_asset_version,
    }


def add_asset_version_to_url(url: str, asset_version: str) -> str:
    parts = urlsplit(url)
    query_params = [
        (key, value)
        for key, value in parse_qsl(parts.query, keep_blank_values=True)
        if key != "build"
    ]
    query = urlencode(query_params)
    version_query = f"build={asset_version}"
    query = f"{query}&{version_query}" if query else version_query
    return urlunsplit((parts.scheme, parts.netloc, parts.path, query, parts.fragment))


def render_frontend_index(settings) -> str:
    app_info = get_app_info_payload(settings)
    html = FRONTEND_INDEX_PATH.read_text(encoding="utf-8")

    def replace_static_asset(match):
        return (
            f"{match.group('prefix')}"
            f"{add_asset_version_to_url(match.group('url'), settings.frontend_asset_version)}"
            f"{match.group('suffix')}"
        )

    html = STATIC_ASSET_PATTERN.sub(replace_static_asset, html)
    app_info_script = (
        "<script>\n"
        f"        window.DBCLAW_APP_INFO = {json.dumps(app_info, ensure_ascii=False)};\n"
        f"        window.DBCLAW_ASSET_VERSION = {json.dumps(settings.frontend_asset_version)};\n"
        "    </script>\n"
    )
    return html.replace("    <!-- App JS -->", f"    {app_info_script}\n    <!-- App JS -->")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    settings = get_settings()
    logger.info(f"Starting {settings.app_name}...")

    # 初始化任务管理器
    from backend.services.task_manager import get_task_manager
    task_manager = get_task_manager()
    app.state.task_manager = task_manager
    logger.info("Task manager initialized")

    startup_report = await run_startup_self_check(settings, include_app_port_check=False)
    set_last_startup_report(startup_report)
    app.state.startup_self_check_report = startup_report.to_dict()
    if not startup_report.ok:
        logger.error("\n%s", startup_report.to_console_text())
        raise RuntimeError("启动自检失败，请根据上方中文诊断结果修复后重试。")

    # Initialize database
    await init_db()
    logger.info("Database initialized")

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

        ai_alert_defaults = [
            ("default_alert_engine_mode", "threshold", "string", "默认告警引擎模式：threshold 或 ai", "alerting"),
            ("ai_alert_timeout_seconds", "3", "integer", "AI 判警请求超时时间（秒）", "alerting"),
            ("ai_alert_confidence_threshold", "0.7", "float", "AI 判警最低置信度阈值（0-1）", "alerting"),
            ("notification_cooldown_minutes", "60", "integer", "通知冷却窗口（分钟），同一类告警在窗口内默认不重复发送；若严重等级提升则立即发送", "alerting"),
        ]

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

        # Seed default Huawei Cloud configs
        huaweicloud_defaults = [
            ("huaweicloud_access_key_id", "", "string", "华为云 Access Key ID（用于 RDS 监控数据采集）"),
            ("huaweicloud_access_key_secret", "", "string", "华为云 Access Key Secret（用于 RDS 监控数据采集）"),
            ("huaweicloud_iam_username", "", "string", "华为云 IAM 用户名（用于 RDS 监控数据采集）"),
            ("huaweicloud_iam_password", "", "string", "华为云 IAM 用户密码（用于 RDS 监控数据采集）"),
            ("huaweicloud_domain_name", "", "string", "华为云账号名或 IAM 用户所属账号名（旧版 IAM 鉴权兼容配置）"),
            ("huaweicloud_project_name", "", "string", "华为云项目名称（AK/SK 自动查找项目 ID 时可选，默认使用 region_id）"),
        ]

        # Seed default Tencent Cloud configs
        tencentcloud_defaults = [
            ("tencentcloud_secret_id", "", "string", "腾讯云 SecretId（用于 RDS/TDSQL-C 监控数据采集）", True),
            ("tencentcloud_secret_key", "", "string", "腾讯云 SecretKey（用于 RDS/TDSQL-C 监控数据采集）", True),
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

        # Seed Huawei Cloud configs
        for key, default_val, val_type, desc in huaweicloud_defaults:
            _exists = await _db.execute(_select(_SystemConfig).where(_SystemConfig.key == key))
            if not _exists.scalar_one_or_none():
                await _config_service.set_config(
                    _db, key=key, value=default_val,
                    value_type=val_type, description=desc,
                    category="integration"
                )

        # Seed Tencent Cloud configs
        for key, default_val, val_type, desc, encrypted in tencentcloud_defaults:
            _exists = await _db.execute(_select(_SystemConfig).where(_SystemConfig.key == key))
            if not _exists.scalar_one_or_none():
                await _config_service.set_config(
                    _db, key=key, value=default_val,
                    value_type=val_type, description=desc,
                    category="integration",
                    is_encrypted=encrypted,
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

        _monitoring_interval_exists = await _db.execute(
            _select(_SystemConfig).where(_SystemConfig.key == MONITORING_COLLECTION_INTERVAL_CONFIG_KEY)
        )
        if not _monitoring_interval_exists.scalar_one_or_none():
            await _config_service.set_config(
                _db,
                key=MONITORING_COLLECTION_INTERVAL_CONFIG_KEY,
                value=str(settings.metric_interval or DEFAULT_MONITORING_COLLECTION_INTERVAL_SECONDS),
                value_type="integer",
                description="全局监控采集周期（秒），系统直连采集与外部集成采集统一使用该周期",
                category="monitoring"
            )

        _external_base_exists = await _db.execute(_select(_SystemConfig).where(_SystemConfig.key == "app_external_base_url"))
        if not _external_base_exists.scalar_one_or_none():
            await _config_service.set_config(
                _db,
                key="app_external_base_url",
                value="",
                value_type="string",
                description="外部访问基础地址，用于生成飞书等通知中的免登录详情链接，例如 https://dbclaw.example.com",
                category="notification"
            )

        for key, value, value_type, description, category in ai_alert_defaults:
            if not await _config_service.get_config(_db, key):
                await _config_service.set_config(
                    _db,
                    key=key,
                    value=value,
                    value_type=value_type,
                    description=description,
                    category=category,
                )
    logger.info("Default system configs seeded")

    # Start SSH connection pool
    from backend.services.ssh_connection_pool import start_ssh_pool
    await start_ssh_pool()
    logger.info("SSH connection pool started")

    # Start metric collector
    from backend.services.metric_collector import start_scheduler
    async with _async_session() as _db:
        monitoring_interval_seconds = await get_monitoring_collection_interval_seconds(
            _db,
            fallback=settings.metric_interval,
        )
    start_scheduler(monitoring_interval_seconds)

    # Start Inspection Service
    from backend.services.inspection_service import InspectionService
    from backend.services import metric_collector
    from backend.database import async_session

    inspection_service = InspectionService(async_session)
    await inspection_service.start()
    metric_collector.set_inspection_service(inspection_service)
    logger.info("Inspection Service activated")

    # Start SSH host metrics collector
    from backend.services.host_collector import collect_host_metric
    await task_manager.register_task("host_metrics_collector", collect_host_metric())
    logger.info("Host metrics collector started")

    # Start notification dispatcher
    from backend.services.notification_dispatcher import start_notification_dispatcher
    await task_manager.register_task("notification_dispatcher", start_notification_dispatcher())
    logger.info("Notification dispatcher started")

    # Load builtin integration templates
    from backend.services.integration_service import IntegrationService
    async with async_session() as _db:
        await IntegrationService.load_builtin_templates(_db)
    logger.info("ntegration templates loaded")

    # Start integration scheduler
    from backend.services.integration_scheduler import start_integration_scheduler
    await task_manager.register_task("integration_scheduler", start_integration_scheduler())
    logger.info("Integration scheduler started")

    # Start user-managed scheduled task scheduler
    from backend.services.scheduled_task_scheduler import start_scheduled_task_scheduler
    await start_scheduled_task_scheduler()
    logger.info("Scheduled task scheduler started")

    # Start Feishu bot long connection client
    from backend.services.feishu_longconn_service import start_feishu_longconn_client
    await start_feishu_longconn_client()

    # Start DingTalk bot stream client
    from backend.services.dingtalk_stream_service import start_dingtalk_stream_client
    await start_dingtalk_stream_client()

    # Start Weixin bot poller
    from backend.services.weixin_bot_service import start_weixin_bot_poller
    await start_weixin_bot_poller()

    yield

    # Shutdown
    logger.info("Starting graceful shutdown...")

    # 取消所有后台任务
    await task_manager.cancel_all(timeout=10.0)
    logger.info("Background tasks cancelled")

    from backend.services.metric_collector import stop_scheduler
    from backend.services.ssh_connection_pool import stop_ssh_pool
    from backend.services.integration_scheduler import stop_integration_scheduler
    from backend.services.scheduled_task_scheduler import stop_scheduled_task_scheduler
    from backend.services.dingtalk_stream_service import stop_dingtalk_stream_client
    from backend.services.feishu_longconn_service import stop_feishu_longconn_client
    from backend.services.weixin_bot_service import stop_weixin_bot_poller

    stop_scheduler()
    stop_integration_scheduler()
    stop_scheduled_task_scheduler()
    await stop_dingtalk_stream_client()
    await stop_feishu_longconn_client()
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
    app.state.startup_self_check_report = get_last_startup_report()

    @app.exception_handler(Exception)
    async def global_exception_handler(request, exc):
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
                "detail": "Internal server error",
            }
        )

    @app.get("/health")
    async def health_check():
        return {"status": "ok"}

    @app.get("/health/live")
    async def health_live():
        return {"status": "ok"}

    @app.get("/health/ready")
    async def health_ready():
        readiness_report = await run_readiness_self_check(settings)
        app.state.last_readiness_report = readiness_report.to_dict()
        status_code = 200 if readiness_report.ok else 503
        return JSONResponse(status_code=status_code, content=readiness_report.to_dict())

    @app.get("/health/checks")
    async def health_checks(_current_user=Depends(get_current_admin)):
        current_report = await run_startup_self_check(settings, phase="health_checks", include_app_port_check=False)
        return {
            "startup": app.state.startup_self_check_report or get_last_startup_report(),
            "current": current_report.to_dict(),
        }

    @app.get("/api/app/info")
    async def app_info():
        return JSONResponse(
            content=get_app_info_payload(settings),
            headers={
                "Cache-Control": "no-store",
                "X-DBClaw-Asset-Version": settings.frontend_asset_version,
            },
        )

    # Register routers
    from backend.routers import (
        ai_models as ai_model,
        alerts,
        auth,
        chat,
        datasources as datasource,
        documents,
        feishu_bot,
        host_detail,
        hosts as host,
        inspections,
        instances,
        integration_bots,
        integrations as integration,
        metrics,
        monitor_ws,
        query,
        scheduled_tasks,
        system_configs as system_config,
        terminal_ws,
        users as user,
        weixin_bot,
    )
    from backend.api import skills
    app.include_router(auth.router)
    app.include_router(user.router)
    app.include_router(datasource.router)
    app.include_router(host.router)
    app.include_router(host_detail.router)
    app.include_router(terminal_ws.router)
    app.include_router(metrics.router)
    app.include_router(monitor_ws.router)
    app.include_router(chat.router)
    app.include_router(query.router)
    app.include_router(scheduled_tasks.router)
    app.include_router(instances.router)
    app.include_router(ai_model.router)
    app.include_router(documents.router)
    app.include_router(skills.router)
    app.include_router(inspections.router)
    app.include_router(system_config.router)
    app.include_router(alerts.router)
    app.include_router(integration.router)
    app.include_router(integration_bots.router)
    app.include_router(feishu_bot.router)
    app.include_router(weixin_bot.router)
    # Serve frontend static files
    app.mount("/css", VersionedStaticFiles(directory="frontend/css"), name="css")
    app.mount("/js", VersionedStaticFiles(directory="frontend/js"), name="js")
    app.mount("/assets", VersionedStaticFiles(directory="frontend/assets"), name="assets")
    app.mount("/lib", VersionedStaticFiles(directory="frontend/lib"), name="lib")

    @app.get("/")
    async def serve_index():
        return HTMLResponse(
            content=render_frontend_index(settings),
            headers={
                "Cache-Control": "no-store",
                "X-DBClaw-Asset-Version": settings.frontend_asset_version,
            },
        )

    @app.get("/public/alerts/{alert_id}")
    async def serve_public_alert_entry(alert_id: int):
        return HTMLResponse(
            content=render_frontend_index(settings),
            headers={
                "Cache-Control": "no-store",
                "X-DBClaw-Asset-Version": settings.frontend_asset_version,
            },
        )

    @app.get("/public/report/{report_id}")
    async def serve_public_report_entry(report_id: int):
        return HTMLResponse(
            content=render_frontend_index(settings),
            headers={
                "Cache-Control": "no-store",
                "X-DBClaw-Asset-Version": settings.frontend_asset_version,
            },
        )

    return app


# Create app instance
app = create_app()
