import asyncio
import errno
import logging
import os
import socket
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from cryptography.fernet import Fernet
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError
from sqlalchemy.ext.asyncio import create_async_engine

from backend.config import Settings
from backend.utils.security import verify_password

logger = logging.getLogger(__name__)

DEFAULT_ENCRYPTION_KEY = "temporary-encryption-key"
DEFAULT_PUBLIC_SHARE_SECRET_KEY = "change-me-to-a-random-public-share-secret"
DEFAULT_ADMIN_PASSWORD = "admin1234"
POSTGRES_DRIVERS = ("postgresql", "postgresql+asyncpg", "postgres")
STARTUP_DATA_PATHS = [
    Path("data"),
    Path("uploads"),
    Path("uploads/chat_attachments"),
]

_last_startup_report: dict[str, Any] | None = None


@dataclass(slots=True)
class CheckResult:
    name: str
    status: str
    severity: str
    summary: str
    detail: str = ""
    suggestion: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "status": self.status,
            "severity": self.severity,
            "summary": self.summary,
            "detail": self.detail,
            "suggestion": self.suggestion,
        }


@dataclass(slots=True)
class SelfCheckReport:
    phase: str
    checks: list[CheckResult]
    generated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    @property
    def blocker_count(self) -> int:
        return sum(1 for check in self.checks if check.status == "fail" and check.severity == "blocker")

    @property
    def warning_count(self) -> int:
        return sum(1 for check in self.checks if check.status == "warn")

    @property
    def pass_count(self) -> int:
        return sum(1 for check in self.checks if check.status == "pass")

    @property
    def ok(self) -> bool:
        return self.blocker_count == 0

    @property
    def status(self) -> str:
        if not self.ok:
            return "fail"
        if self.warning_count:
            return "warn"
        return "pass"

    def to_dict(self) -> dict[str, Any]:
        return {
            "phase": self.phase,
            "status": self.status,
            "ok": self.ok,
            "generated_at": self.generated_at,
            "summary": {
                "total": len(self.checks),
                "passed": self.pass_count,
                "warnings": self.warning_count,
                "blockers": self.blocker_count,
            },
            "checks": [check.to_dict() for check in self.checks],
        }

    def to_console_text(self, title: str | None = None, include_passes: bool = False) -> str:
        report_title = title or {
            "fail": "DBClaw 启动自检失败",
            "warn": "DBClaw 启动自检通过（含警告）",
            "pass": "DBClaw 启动自检通过",
        }[self.status]
        lines = [
            report_title,
            f"检查阶段: {self.phase}",
            f"结果汇总: {self.pass_count} 通过, {self.warning_count} 警告, {self.blocker_count} 阻断",
        ]

        visible_checks = [
            check for check in self.checks
            if include_passes or check.status != "pass"
        ]
        if not visible_checks:
            return "\n".join(lines)

        for check in visible_checks:
            lines.append("")
            lines.append(f"[{check.status.upper()}] {check.name}")
            lines.append(f"  结论: {check.summary}")
            if check.detail:
                detail_lines = check.detail.splitlines() or [check.detail]
                lines.append("  详情:")
                lines.extend(f"    {line}" for line in detail_lines)
            if check.suggestion:
                suggestion_lines = check.suggestion.splitlines() or [check.suggestion]
                lines.append("  建议:")
                lines.extend(f"    {line}" for line in suggestion_lines)

        return "\n".join(lines)


class StartupSelfCheckError(RuntimeError):
    def __init__(self, report: SelfCheckReport):
        self.report = report
        super().__init__("启动自检失败，请根据日志中的中文诊断结果修复后重试。")


def set_last_startup_report(report: SelfCheckReport) -> None:
    global _last_startup_report
    _last_startup_report = report.to_dict()


def get_last_startup_report() -> dict[str, Any] | None:
    return _last_startup_report


async def run_startup_self_check(
    settings: Settings,
    *,
    phase: str = "startup",
    include_app_port_check: bool = False,
) -> SelfCheckReport:
    checks = [
        _check_encryption_key(settings),
        _check_public_share_secret(settings),
    ]
    checks.append(await _check_initial_admin_password(settings))
    checks.extend(_check_runtime_paths())
    if include_app_port_check:
        checks.append(_check_app_port(settings))
    checks.append(await _check_metadata_database(settings))
    return SelfCheckReport(phase=phase, checks=checks)


async def run_readiness_self_check(settings: Settings) -> SelfCheckReport:
    checks = _check_runtime_paths()
    checks.append(await _check_metadata_database(settings))
    return SelfCheckReport(phase="readiness", checks=checks)


def run_startup_self_check_sync(
    settings: Settings,
    *,
    include_app_port_check: bool = False,
) -> SelfCheckReport:
    return asyncio.run(
        run_startup_self_check(
            settings,
            include_app_port_check=include_app_port_check,
        )
    )


def _check_encryption_key(settings: Settings) -> CheckResult:
    if not settings.encryption_key or settings.encryption_key == DEFAULT_ENCRYPTION_KEY:
        return CheckResult(
            name="ENCRYPTION_KEY",
            status="fail",
            severity="blocker",
            summary="未配置数据库凭据加密密钥。",
            detail="当前仍在使用默认占位值，启动后无法安全处理数据库密码等敏感信息。",
            suggestion=(
                "请在 .env 或环境变量中设置 ENCRYPTION_KEY。\n"
                "可执行: python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\""
            ),
        )

    try:
        Fernet(settings.encryption_key.encode())
    except Exception as exc:
        return CheckResult(
            name="ENCRYPTION_KEY",
            status="fail",
            severity="blocker",
            summary="ENCRYPTION_KEY 格式无效。",
            detail=f"无法解析为合法的 Fernet key: {exc}",
            suggestion=(
                "请重新生成合法的 Fernet key 后写入 ENCRYPTION_KEY。\n"
                "可执行: python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\""
            ),
        )

    return CheckResult(
        name="ENCRYPTION_KEY",
        status="pass",
        severity="info",
        summary="数据库凭据加密密钥可用。",
    )


def _check_public_share_secret(settings: Settings) -> CheckResult:
    if not settings.public_share_secret_key or settings.public_share_secret_key == DEFAULT_PUBLIC_SHARE_SECRET_KEY:
        return CheckResult(
            name="PUBLIC_SHARE_SECRET_KEY",
            status="fail",
            severity="blocker",
            summary="未配置公开分享签名密钥。",
            detail="当前仍在使用默认占位值，公开分享链接的签名校验无法安全工作。",
            suggestion="请在 .env 或环境变量中设置一个强随机字符串到 PUBLIC_SHARE_SECRET_KEY。",
        )

    return CheckResult(
        name="PUBLIC_SHARE_SECRET_KEY",
        status="pass",
        severity="info",
        summary="公开分享签名密钥可用。",
    )


async def _check_initial_admin_password(settings: Settings) -> CheckResult:
    initial_admin_password = settings.initial_admin_password or DEFAULT_ADMIN_PASSWORD
    admin_password_hash, query_error = await _fetch_admin_password_hash(settings.database_url)

    if query_error:
        logger.warning("Failed to compare admin password with INITIAL_ADMIN_PASSWORD: %s", query_error)
        return CheckResult(
            name="INITIAL_ADMIN_PASSWORD",
            status="pass",
            severity="info",
            summary="无法自动校验管理员密码与 INITIAL_ADMIN_PASSWORD 是否一致。",
            detail="元数据库连接或 app_user 查询失败，已跳过该项比对。",
            suggestion="请确认 DATABASE_URL 可访问，且已完成数据库初始化后重试自检。",
        )

    if not admin_password_hash:
        return CheckResult(
            name="INITIAL_ADMIN_PASSWORD",
            status="pass",
            severity="info",
            summary="未检测到管理员账号，跳过 INITIAL_ADMIN_PASSWORD 比对。",
            detail="当前数据库中不存在 admin 用户记录。",
        )

    try:
        is_same_as_admin_password = verify_password(initial_admin_password, admin_password_hash)
    except Exception as exc:
        logger.warning("Failed to verify admin password hash during self-check: %s", exc)
        return CheckResult(
            name="INITIAL_ADMIN_PASSWORD",
            status="pass",
            severity="info",
            summary="无法自动校验管理员密码与 INITIAL_ADMIN_PASSWORD 是否一致。",
            detail=f"密码哈希校验失败: {exc}",
            suggestion="请确认管理员密码哈希格式有效，必要时重置管理员密码后重试。",
        )

    if is_same_as_admin_password:
        return CheckResult(
            name="INITIAL_ADMIN_PASSWORD",
            status="warn",
            severity="warning",
            summary="管理员密码与 INITIAL_ADMIN_PASSWORD 当前值一致。",
            detail="共享或弱口令配置可能带来额外风险，建议避免将运行中管理员密码长期与初始化配置保持一致。",
            suggestion="建议定期通过系统内密码修改流程更新管理员密码。",
        )

    return CheckResult(
        name="INITIAL_ADMIN_PASSWORD",
        status="pass",
        severity="info",
        summary="管理员密码与 INITIAL_ADMIN_PASSWORD 不一致。",
        detail="说明管理员账号密码已独立于当前初始化配置。",
    )


async def _fetch_admin_password_hash(database_url: str) -> tuple[str | None, str | None]:
    if not (database_url or "").strip():
        return None, "DATABASE_URL 未配置"

    engine = None
    try:
        engine = create_async_engine(
            database_url,
            echo=False,
            pool_pre_ping=True,
            connect_args={"ssl": False},
        )
        async with engine.connect() as conn:
            result = await conn.execute(
                text("SELECT password_hash FROM app_user WHERE username = :username ORDER BY id ASC LIMIT 1"),
                {"username": "admin"},
            )
            row = result.first()
            return (str(row[0]), None) if row and row[0] else (None, None)
    except Exception as exc:
        return None, _format_exception_detail(exc)
    finally:
        if engine is not None:
            await engine.dispose()


def _check_runtime_paths() -> list[CheckResult]:
    return [_check_single_path(path) for path in STARTUP_DATA_PATHS]


def _check_single_path(path: Path) -> CheckResult:
    try:
        existing_parent = path if path.exists() else _find_existing_parent(path)
    except FileNotFoundError:
        existing_parent = Path.cwd()

    if path.exists() and not path.is_dir():
        return CheckResult(
            name=f"目录 {path}",
            status="fail",
            severity="blocker",
            summary=f"{path} 不是目录。",
            detail="当前路径已存在，但类型不是目录，系统无法在其下写入运行数据。",
            suggestion=f"请移除或重命名该路径，然后重新启动服务。",
        )

    if not os.access(existing_parent, os.W_OK):
        return CheckResult(
            name=f"目录 {path}",
            status="fail",
            severity="blocker",
            summary=f"{path} 不可写。",
            detail=f"最近的已存在父目录是 {existing_parent}，当前进程没有写入权限。",
            suggestion=f"请修复 {existing_parent} 的写权限，或切换到有权限的工作目录后重试。",
        )

    detail = f"最近的可写父目录: {existing_parent}"
    if path.exists():
        try:
            probe_file = path / ".dbclaw_write_probe"
            probe_file.write_text("ok", encoding="utf-8")
            probe_file.unlink()
            detail = f"{path} 已存在且可写。"
        except Exception as exc:
            return CheckResult(
                name=f"目录 {path}",
                status="fail",
                severity="blocker",
                summary=f"{path} 存在但不可写。",
                detail=f"尝试写入测试文件失败: {exc}",
                suggestion=f"请检查 {path} 的目录权限。",
            )
    else:
        detail = f"{path} 当前不存在，但其父目录可写，首次使用时可以创建。"

    return CheckResult(
        name=f"目录 {path}",
        status="pass",
        severity="info",
        summary=f"{path} 可用于运行时数据存储。",
        detail=detail,
    )


def _find_existing_parent(path: Path) -> Path:
    current = path
    while not current.exists():
        if current.parent == current:
            raise FileNotFoundError(path)
        current = current.parent
    return current


def _check_app_port(settings: Settings) -> CheckResult:
    host = settings.app_host or "0.0.0.0"
    port = int(settings.app_port)
    sock: socket.socket | None = None
    try:
        family = socket.AF_INET6 if ":" in host else socket.AF_INET
        sock = socket.socket(family, socket.SOCK_STREAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        bind_host = host if host not in {"localhost", ""} else "127.0.0.1"
        sock.bind((bind_host, port))
    except OSError as exc:
        if exc.errno == errno.EADDRINUSE:
            return CheckResult(
                name="APP_PORT",
                status="fail",
                severity="blocker",
                summary=f"应用端口 {port} 已被占用。",
                detail=f"当前配置监听地址为 {host}:{port}，绑定端口时返回 Address already in use。",
                suggestion=f"请释放端口 {port}，或修改 APP_PORT 后重试。",
            )
        if exc.errno == errno.EADDRNOTAVAIL:
            return CheckResult(
                name="APP_PORT",
                status="fail",
                severity="blocker",
                summary=f"监听地址 {host}:{port} 无法绑定。",
                detail=f"系统返回 {exc}，通常表示 APP_HOST 配置的地址不存在。",
                suggestion="请检查 APP_HOST 是否是当前机器可用的监听地址，例如 0.0.0.0 或 127.0.0.1。",
            )
        return CheckResult(
            name="APP_PORT",
            status="fail",
            severity="blocker",
            summary=f"无法绑定应用端口 {host}:{port}。",
            detail=str(exc),
            suggestion="请检查 APP_HOST / APP_PORT 配置以及本机网络环境。",
        )
    finally:
        if sock is not None:
            sock.close()

    return CheckResult(
        name="APP_PORT",
        status="pass",
        severity="info",
        summary=f"应用端口 {host}:{port} 可用。",
    )


async def _check_metadata_database(settings: Settings) -> CheckResult:
    database_url = (settings.database_url or "").strip()
    if not database_url:
        return CheckResult(
            name="元数据库",
            status="fail",
            severity="blocker",
            summary="DATABASE_URL 未配置。",
            detail="系统无法确定元数据库连接地址。",
            suggestion="请在 .env 或环境变量中设置 DATABASE_URL。",
        )

    try:
        url = make_url(database_url)
    except ArgumentError as exc:
        return CheckResult(
            name="元数据库",
            status="fail",
            severity="blocker",
            summary="DATABASE_URL 格式无效。",
            detail=str(exc),
            suggestion=(
                "请检查 DATABASE_URL 格式是否正确。\n"
                "PostgreSQL 示例: postgresql+asyncpg://dbclaw:password@127.0.0.1:5432/dbclaw"
            ),
        )

    driver = url.drivername
    if driver.startswith(POSTGRES_DRIVERS):
        return await _check_postgres_database(database_url, url)

    return CheckResult(
        name="元数据库",
        status="fail",
        severity="blocker",
        summary=f"不支持的元数据库驱动: {driver}",
        detail="当前系统只支持 PostgreSQL 作为元数据库。",
        suggestion="请将 DATABASE_URL 调整为 PostgreSQL 连接串。",
    )


async def _check_postgres_database(database_url: str, url: Any) -> CheckResult:
    host = url.host or "localhost"
    port = int(url.port or 5432)
    database = url.database or "(未指定数据库)"
    tcp_result = await _probe_postgres_endpoint(host, port, database)
    if tcp_result is not None:
        return tcp_result

    engine = None
    try:
        engine = create_async_engine(
            database_url,
            echo=False,
            pool_pre_ping=True,
            connect_args={"ssl": False},
        )
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception as exc:
        return _classify_postgres_connection_error(exc, host, port, database)
    finally:
        if engine is not None:
            await engine.dispose()

    return CheckResult(
        name="元数据库",
        status="pass",
        severity="info",
        summary="PostgreSQL 元数据库连接正常。",
        detail=f"地址: {host}:{port} / 数据库: {database}",
    )


async def _probe_postgres_endpoint(host: str, port: int, database: str) -> CheckResult | None:
    try:
        reader, writer = await asyncio.wait_for(asyncio.open_connection(host, port), timeout=3)
        writer.close()
        await writer.wait_closed()
    except socket.gaierror as exc:
        return CheckResult(
            name="元数据库",
            status="fail",
            severity="blocker",
            summary="元数据库主机名无法解析。",
            detail=f"地址: {host}:{port} / 数据库: {database}\n底层错误: {exc}",
            suggestion="请检查 DATABASE_URL 中的主机名是否正确，或确认 DNS / host 配置可解析该地址。",
        )
    except ConnectionRefusedError as exc:
        return CheckResult(
            name="元数据库",
            status="fail",
            severity="blocker",
            summary="元数据库端口拒绝连接。",
            detail=f"地址: {host}:{port} / 数据库: {database}\n底层错误: {exc}",
            suggestion=(
                "请确认 PostgreSQL 服务已启动，并检查 DATABASE_URL 中的 host/port 是否正确。\n"
                f"可先执行: pg_isready -h {host} -p {port}"
            ),
        )
    except TimeoutError:
        return CheckResult(
            name="元数据库",
            status="fail",
            severity="blocker",
            summary="连接元数据库超时。",
            detail=f"地址: {host}:{port} / 数据库: {database}\n3 秒内未建立 TCP 连接。",
            suggestion="请检查网络连通性、防火墙和安全组配置。",
        )
    except OSError as exc:
        return CheckResult(
            name="元数据库",
            status="fail",
            severity="blocker",
            summary="无法与元数据库建立网络连接。",
            detail=f"地址: {host}:{port} / 数据库: {database}\n底层错误: {exc}",
            suggestion="请检查 DATABASE_URL、网络连通性以及 PostgreSQL 服务监听地址。",
        )
    return None


def _classify_postgres_connection_error(exc: Exception, host: str, port: int, database: str) -> CheckResult:
    detail = f"地址: {host}:{port} / 数据库: {database}\n底层错误: {_format_exception_detail(exc)}"
    lowered = detail.lower()

    if "password authentication failed" in lowered or "invalidpassworderror" in lowered:
        return CheckResult(
            name="元数据库",
            status="fail",
            severity="blocker",
            summary="元数据库认证失败。",
            detail=detail,
            suggestion="请检查 DATABASE_URL 中的用户名和密码是否正确。",
        )

    if "does not exist" in lowered and "database" in lowered:
        return CheckResult(
            name="元数据库",
            status="fail",
            severity="blocker",
            summary="元数据库不存在。",
            detail=detail,
            suggestion=f"请先创建数据库 {database}，或修改 DATABASE_URL 指向已存在的数据库。",
        )

    if "ssl" in lowered:
        return CheckResult(
            name="元数据库",
            status="fail",
            severity="blocker",
            summary="元数据库 SSL 配置不兼容。",
            detail=detail,
            suggestion="请检查 PostgreSQL 的 SSL 配置，并确认应用连接参数与服务端要求一致。",
        )

    return CheckResult(
        name="元数据库",
        status="fail",
        severity="blocker",
        summary="元数据库连接失败。",
        detail=detail,
        suggestion="请检查 DATABASE_URL、数据库账号权限，以及 PostgreSQL 服务状态。",
    )


def _format_exception_detail(exc: Exception) -> str:
    current: BaseException | None = exc
    seen: set[int] = set()
    parts: list[str] = []
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        parts.append(f"{type(current).__name__}: {current}")
        next_exc = getattr(current, "orig", None) or current.__cause__ or current.__context__
        current = next_exc if isinstance(next_exc, BaseException) else None
    return " | ".join(parts)
