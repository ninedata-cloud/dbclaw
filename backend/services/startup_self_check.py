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
            "fail": "DBClaw startup self-check failed",
            "warn": "DBClaw startup self-check passed with warnings",
            "pass": "DBClaw startup self-check passed",
        }[self.status]
        lines = [
            report_title,
            f"Check phase: {self.phase}",
            f"Summary: {self.pass_count} passed, {self.warning_count} warnings, {self.blocker_count} blockers",
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
            lines.append(f"  Summary: {check.summary}")
            if check.detail:
                detail_lines = check.detail.splitlines() or [check.detail]
                lines.append("  Details:")
                lines.extend(f"    {line}" for line in detail_lines)
            if check.suggestion:
                suggestion_lines = check.suggestion.splitlines() or [check.suggestion]
                lines.append("  Suggested action:")
                lines.extend(f"    {line}" for line in suggestion_lines)

        return "\n".join(lines)


class StartupSelfCheckError(RuntimeError):
    def __init__(self, report: SelfCheckReport):
        self.report = report
        super().__init__("Startup self-check failed. Resolve the issues reported in the logs and try again.")


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
    from backend.database import get_engine

    checks.append(await _check_metadata_database(settings, shared_engine=get_engine()))
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
            summary="The database credential encryption key is not configured.",
            detail="The default placeholder is still in use, so database passwords and other sensitive data cannot be handled securely.",
            suggestion=(
                "Set ENCRYPTION_KEY in .env or as an environment variable.\n"
                "Generate one with: python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\""
            ),
        )

    try:
        Fernet(settings.encryption_key.encode())
    except Exception as exc:
        return CheckResult(
            name="ENCRYPTION_KEY",
            status="fail",
            severity="blocker",
            summary="ENCRYPTION_KEY has an invalid format.",
            detail=f"The value is not a valid Fernet key: {exc}",
            suggestion=(
                "Generate a valid Fernet key and assign it to ENCRYPTION_KEY.\n"
                "Generate one with: python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\""
            ),
        )

    return CheckResult(
        name="ENCRYPTION_KEY",
        status="pass",
        severity="info",
        summary="The database credential encryption key is valid.",
    )


def _check_public_share_secret(settings: Settings) -> CheckResult:
    if not settings.public_share_secret_key or settings.public_share_secret_key == DEFAULT_PUBLIC_SHARE_SECRET_KEY:
        return CheckResult(
            name="PUBLIC_SHARE_SECRET_KEY",
            status="fail",
            severity="blocker",
            summary="The public share signing key is not configured.",
            detail="The default placeholder is still in use, so public share link signatures cannot be verified securely.",
            suggestion="Set PUBLIC_SHARE_SECRET_KEY to a strong random string in .env or as an environment variable.",
        )

    return CheckResult(
        name="PUBLIC_SHARE_SECRET_KEY",
        status="pass",
        severity="info",
        summary="The public share signing key is valid.",
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
            summary="Could not determine whether the administrator password matches INITIAL_ADMIN_PASSWORD.",
            detail="The metadata database connection or app_user query failed, so this comparison was skipped.",
            suggestion="Verify that DATABASE_URL is reachable and the database is initialized, then run the self-check again.",
        )

    if not admin_password_hash:
        return CheckResult(
            name="INITIAL_ADMIN_PASSWORD",
            status="pass",
            severity="info",
            summary="No administrator account was found; skipping the INITIAL_ADMIN_PASSWORD comparison.",
            detail="The database does not contain an admin user record.",
        )

    try:
        is_same_as_admin_password = verify_password(initial_admin_password, admin_password_hash)
    except Exception as exc:
        logger.warning("Failed to verify admin password hash during self-check: %s", exc)
        return CheckResult(
            name="INITIAL_ADMIN_PASSWORD",
            status="pass",
            severity="info",
            summary="Could not determine whether the administrator password matches INITIAL_ADMIN_PASSWORD.",
            detail=f"Password hash verification failed: {exc}",
            suggestion="Verify that the administrator password hash is valid. Reset the administrator password if necessary, then try again.",
        )

    if is_same_as_admin_password:
        return CheckResult(
            name="INITIAL_ADMIN_PASSWORD",
            status="warn",
            severity="warning",
            summary="The administrator password currently matches INITIAL_ADMIN_PASSWORD.",
            detail="Reusing a shared or weak password increases risk. Avoid keeping the active administrator password equal to the initialization setting.",
            suggestion="Change the administrator password periodically using the in-product password change workflow.",
        )

    return CheckResult(
        name="INITIAL_ADMIN_PASSWORD",
        status="pass",
        severity="info",
        summary="The administrator password does not match INITIAL_ADMIN_PASSWORD.",
        detail="The administrator password is independent of the current initialization setting.",
    )


async def _fetch_admin_password_hash(database_url: str) -> tuple[str | None, str | None]:
    if not (database_url or "").strip():
        return None, "DATABASE_URL is not configured"

    engine = None
    try:
        engine = create_async_engine(
            database_url,
            echo=False,
            pool_pre_ping=True,
            connect_args={"ssl": False},
        )
        async with engine.connect() as conn:
            table_exists_result = await conn.execute(text("SELECT to_regclass('app_user')"))
            table_exists_row = table_exists_result.first()
            if not table_exists_row or not table_exists_row[0]:
                return None, None

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
            name=f"Directory {path}",
            status="fail",
            severity="blocker",
            summary=f"{path} is not a directory.",
            detail="The path exists but is not a directory, so runtime data cannot be written beneath it.",
            suggestion="Remove or rename the path, then restart the service.",
        )

    if not os.access(existing_parent, os.W_OK):
        return CheckResult(
            name=f"Directory {path}",
            status="fail",
            severity="blocker",
            summary=f"{path} is not writable.",
            detail=f"The nearest existing parent is {existing_parent}, and the current process cannot write to it.",
            suggestion=f"Grant write access to {existing_parent}, or run from a writable working directory and try again.",
        )

    detail = f"Nearest writable parent directory: {existing_parent}"
    if path.exists():
        try:
            probe_file = path / ".dbclaw_write_probe"
            probe_file.write_text("ok", encoding="utf-8")
            probe_file.unlink()
            detail = f"{path} exists and is writable."
        except Exception as exc:
            return CheckResult(
                name=f"Directory {path}",
                status="fail",
                severity="blocker",
                summary=f"{path} exists but is not writable.",
                detail=f"Writing a probe file failed: {exc}",
                suggestion=f"Check the directory permissions for {path}.",
            )
    else:
        detail = f"{path} does not exist, but its parent is writable and the directory can be created when first used."

    return CheckResult(
        name=f"Directory {path}",
        status="pass",
        severity="info",
        summary=f"{path} is available for runtime data storage.",
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
                summary=f"Application port {port} is already in use.",
                detail=f"Binding the configured address {host}:{port} returned 'Address already in use'.",
                suggestion=f"Release port {port}, or change APP_PORT and try again.",
            )
        if exc.errno == errno.EADDRNOTAVAIL:
            return CheckResult(
                name="APP_PORT",
                status="fail",
                severity="blocker",
                summary=f"Listen address {host}:{port} cannot be bound.",
                detail=f"The system returned {exc}, which usually means the address configured in APP_HOST is unavailable.",
                suggestion="Set APP_HOST to an address available on this machine, such as 0.0.0.0 or 127.0.0.1.",
            )
        return CheckResult(
            name="APP_PORT",
            status="fail",
            severity="blocker",
            summary=f"Application port {host}:{port} cannot be bound.",
            detail=str(exc),
            suggestion="Check APP_HOST, APP_PORT, and the local network configuration.",
        )
    finally:
        if sock is not None:
            sock.close()

    return CheckResult(
        name="APP_PORT",
        status="pass",
        severity="info",
        summary=f"Application port {host}:{port} is available.",
    )


async def _check_metadata_database(settings: Settings, *, shared_engine=None) -> CheckResult:
    database_url = (settings.database_url or "").strip()
    if not database_url:
        return CheckResult(
            name="Metadata database",
            status="fail",
            severity="blocker",
            summary="DATABASE_URL is not configured.",
            detail="The metadata database connection address cannot be determined.",
            suggestion="Set DATABASE_URL in .env or as an environment variable.",
        )

    try:
        url = make_url(database_url)
    except ArgumentError as exc:
        return CheckResult(
            name="Metadata database",
            status="fail",
            severity="blocker",
            summary="DATABASE_URL has an invalid format.",
            detail=str(exc),
            suggestion=(
                "Check the DATABASE_URL format.\n"
                "PostgreSQL example: postgresql+asyncpg://dbclaw:password@127.0.0.1:5432/dbclaw"
            ),
        )

    driver = url.drivername
    if driver.startswith(POSTGRES_DRIVERS):
        return await _check_postgres_database(
            database_url,
            url,
            shared_engine=shared_engine,
            timeout_seconds=settings.readiness_database_timeout_seconds if shared_engine is not None else None,
        )

    return CheckResult(
        name="Metadata database",
        status="fail",
        severity="blocker",
        summary=f"Unsupported metadata database driver: {driver}",
        detail="Only PostgreSQL is supported as the metadata database.",
        suggestion="Change DATABASE_URL to a PostgreSQL connection string.",
    )


async def _check_postgres_database(
    database_url: str,
    url: Any,
    *,
    shared_engine=None,
    timeout_seconds: float | None = None,
) -> CheckResult:
    host = url.host or "localhost"
    port = int(url.port or 5432)
    database = url.database or "(database not specified)"
    tcp_result = await _probe_postgres_endpoint(host, port, database)
    if tcp_result is not None:
        return tcp_result

    engine = shared_engine
    owns_engine = engine is None
    try:
        if engine is None:
            engine = create_async_engine(
                database_url,
                echo=False,
                pool_pre_ping=True,
                connect_args={"ssl": False},
            )

        async def _execute_probe():
            async with engine.connect() as conn:
                await conn.execute(text("SELECT 1"))

        if timeout_seconds is None:
            await _execute_probe()
        else:
            await asyncio.wait_for(_execute_probe(), timeout=max(0.1, timeout_seconds))
    except Exception as exc:
        return _classify_postgres_connection_error(exc, host, port, database)
    finally:
        if owns_engine and engine is not None:
            await engine.dispose()

    return CheckResult(
        name="Metadata database",
        status="pass",
        severity="info",
        summary="The PostgreSQL metadata database connection is healthy.",
        detail=f"Address: {host}:{port} / Database: {database}",
    )


async def _probe_postgres_endpoint(host: str, port: int, database: str) -> CheckResult | None:
    try:
        reader, writer = await asyncio.wait_for(asyncio.open_connection(host, port), timeout=3)
        writer.close()
        await writer.wait_closed()
    except socket.gaierror as exc:
        return CheckResult(
            name="Metadata database",
            status="fail",
            severity="blocker",
            summary="The metadata database hostname could not be resolved.",
            detail=f"Address: {host}:{port} / Database: {database}\nUnderlying error: {exc}",
            suggestion="Check the hostname in DATABASE_URL and verify that DNS or host configuration can resolve it.",
        )
    except ConnectionRefusedError as exc:
        return CheckResult(
            name="Metadata database",
            status="fail",
            severity="blocker",
            summary="The metadata database port refused the connection.",
            detail=f"Address: {host}:{port} / Database: {database}\nUnderlying error: {exc}",
            suggestion=(
                "Verify that PostgreSQL is running and that the host and port in DATABASE_URL are correct.\n"
                f"Check with: pg_isready -h {host} -p {port}"
            ),
        )
    except TimeoutError:
        return CheckResult(
            name="Metadata database",
            status="fail",
            severity="blocker",
            summary="The metadata database connection timed out.",
            detail=f"Address: {host}:{port} / Database: {database}\nNo TCP connection was established within 3 seconds.",
            suggestion="Check network connectivity, firewall rules, and security group settings.",
        )
    except OSError as exc:
        return CheckResult(
            name="Metadata database",
            status="fail",
            severity="blocker",
            summary="A network connection to the metadata database could not be established.",
            detail=f"Address: {host}:{port} / Database: {database}\nUnderlying error: {exc}",
            suggestion="Check DATABASE_URL, network connectivity, and the PostgreSQL listen address.",
        )
    return None


def _classify_postgres_connection_error(exc: Exception, host: str, port: int, database: str) -> CheckResult:
    detail = f"Address: {host}:{port} / Database: {database}\nUnderlying error: {_format_exception_detail(exc)}"
    lowered = detail.lower()

    if "password authentication failed" in lowered or "invalidpassworderror" in lowered:
        return CheckResult(
            name="Metadata database",
            status="fail",
            severity="blocker",
            summary="Metadata database authentication failed.",
            detail=detail,
            suggestion="Check the username and password in DATABASE_URL.",
        )

    if "does not exist" in lowered and "database" in lowered:
        return CheckResult(
            name="Metadata database",
            status="fail",
            severity="blocker",
            summary="The metadata database does not exist.",
            detail=detail,
            suggestion=f"Create database {database}, or update DATABASE_URL to reference an existing database.",
        )

    if "ssl" in lowered:
        return CheckResult(
            name="Metadata database",
            status="fail",
            severity="blocker",
            summary="The metadata database SSL configuration is incompatible.",
            detail=detail,
            suggestion="Check the PostgreSQL SSL configuration and ensure the application connection parameters match the server requirements.",
        )

    return CheckResult(
        name="Metadata database",
        status="fail",
        severity="blocker",
        summary="The metadata database connection failed.",
        detail=detail,
        suggestion="Check DATABASE_URL, database account permissions, and the PostgreSQL service status.",
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
