import asyncio
import socket
import time
from typing import Any, Dict, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.datasource import Datasource
from backend.models.soft_delete import alive_filter
from backend.services.db_connector import get_connector
from backend.utils.encryption import decrypt_value
from backend.utils.host_executor import execute_host_command


class ConnectionDiagnosticService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def diagnose_datasource(
        self,
        datasource_id: int,
        include_host_checks: bool = True,
        include_tcp_checks: bool = True,
    ) -> Dict[str, Any]:
        result = await self.db.execute(select(Datasource).where(Datasource.id == datasource_id, alive_filter(Datasource)))
        datasource = result.scalar_one_or_none()
        if not datasource:
            return self._finalize_result(
                success=False,
                message=f"数据源 ID {datasource_id} 不存在",
                summary="数据库连接失败：数据源不存在",
                target={"datasource_id": datasource_id},
                classification=self._classification("config", "datasource_not_found", "DATASOURCE_NOT_FOUND"),
                checks=[self._check("config", "load_datasource", False, error=f"Datasource {datasource_id} not found")],
                diagnosis=self._diagnosis(
                    ["指定的数据源 ID 不存在或已被删除"],
                    ["确认 datasource_id 是否正确", "检查数据源是否已创建并仍处于有效状态"],
                ),
                raw_error=f"Datasource {datasource_id} not found",
                total_ms=0,
            )

        return await self.diagnose_connection_params(
            db_type=datasource.db_type,
            host=datasource.host,
            port=datasource.port,
            username=datasource.username,
            password=decrypt_value(datasource.password_encrypted) if datasource.password_encrypted else None,
            database=datasource.database,
            extra_params=datasource.extra_params,
            datasource_id=datasource.id,
            host_id=datasource.host_id,
            include_host_checks=include_host_checks,
            include_tcp_checks=include_tcp_checks,
        )

    async def diagnose_connection_params(
        self,
        db_type: str,
        host: str,
        port: int,
        username: Optional[str] = None,
        password: Optional[str] = None,
        database: Optional[str] = None,
        extra_params: Optional[str] = None,
        datasource_id: Optional[int] = None,
        host_id: Optional[int] = None,
        include_host_checks: bool = True,
        include_tcp_checks: bool = True,
    ) -> Dict[str, Any]:
        started_at = time.perf_counter()
        checks = []
        target = {
            "datasource_id": datasource_id,
            "host_id": host_id,
            "db_type": db_type,
            "host": host,
            "port": port,
            "database": database,
            "username": username,
        }

        config_error = self._validate_config(db_type=db_type, host=host, port=port)
        if config_error:
            checks.append(self._check("config", "validate_params", False, error=config_error))
            classification = self._classification("config", "invalid_config", "INVALID_CONFIG")
            return self._finalize_result(
                success=False,
                message=config_error,
                summary=f"数据库连接失败：{config_error}",
                target=target,
                classification=classification,
                checks=checks,
                diagnosis=self._diagnosis(
                    ["连接参数不完整或格式不合法"],
                    ["检查 db_type、host、port 是否填写正确", "确认端口范围在 1-65535 之间"],
                ),
                raw_error=config_error,
                total_ms=self._elapsed_ms(started_at),
            )
        checks.append(self._check("config", "validate_params", True, details="连接参数格式校验通过"))

        if include_host_checks and host_id:
            host_check = await self._run_host_check(host_id, host, port)
            checks.append(host_check)

        if include_tcp_checks:
            tcp_check = await self._run_tcp_check(host, port)
            checks.append(tcp_check)
            if not tcp_check["success"]:
                classification = self._classify_exception_message(tcp_check.get("error", "TCP connection failed"), layer_hint="tcp")
                diagnosis = self._build_diagnosis(classification)
                return self._finalize_result(
                    success=False,
                    message=tcp_check.get("error") or "TCP 连接失败",
                    summary=f"数据库连接失败：{diagnosis['probable_causes'][0] if diagnosis['probable_causes'] else 'TCP 连接失败'}",
                    target=target,
                    classification=classification,
                    checks=checks,
                    diagnosis=diagnosis,
                    raw_error=tcp_check.get("error"),
                    total_ms=self._elapsed_ms(started_at),
                )

        connector_started = time.perf_counter()
        try:
            connector = get_connector(
                db_type=db_type,
                host=host,
                port=port,
                username=username,
                password=password,
                database=database,
                extra_params=extra_params,
            )
            version = await connector.test_connection()
            checks.append(
                self._check(
                    "db_handshake",
                    "connector_test_connection",
                    True,
                    details=f"连接成功，版本：{version}",
                    latency_ms=self._elapsed_ms(connector_started),
                )
            )
            return self._finalize_result(
                success=True,
                message="Connection successful",
                summary="数据库连接成功",
                target=target,
                checks=checks,
                version=version,
                total_ms=self._elapsed_ms(started_at),
            )
        except Exception as exc:
            error_text = self._sanitize_error(exc)
            classification = self._classify_exception(exc)
            checks.append(
                self._check(
                    classification["layer"],
                    "connector_test_connection",
                    False,
                    error=error_text,
                    latency_ms=self._elapsed_ms(connector_started),
                )
            )
            diagnosis = self._build_diagnosis(classification)
            return self._finalize_result(
                success=False,
                message=error_text,
                summary=f"数据库连接失败：{diagnosis['probable_causes'][0] if diagnosis['probable_causes'] else error_text}",
                target=target,
                classification=classification,
                checks=checks,
                diagnosis=diagnosis,
                raw_error=error_text,
                total_ms=self._elapsed_ms(started_at),
            )

    def _validate_config(self, db_type: Optional[str], host: Optional[str], port: Optional[int]) -> Optional[str]:
        supported = {"mysql", "postgresql", "sqlserver", "oracle", "tdsql-c-mysql", "opengauss", "hana"}
        if not db_type or db_type not in supported:
            return f"不支持的数据库类型: {db_type}"
        if not host or not str(host).strip():
            return "数据库主机不能为空"
        if not isinstance(port, int) or port <= 0 or port > 65535:
            return "数据库端口必须在 1-65535 之间"
        return None

    async def _run_host_check(self, host_id: int, host: str, port: int) -> Dict[str, Any]:
        started_at = time.perf_counter()
        command = f"(command -v nc >/dev/null 2>&1 && nc -z -w 3 {host} {port}) || (command -v timeout >/dev/null 2>&1 && timeout 3 bash -lc '</dev/tcp/{host}/{port}')"
        result = await execute_host_command(self.db, host_id, command, allow_write=False, timeout=5)
        if result.get("success"):
            return self._check(
                "host",
                "ssh_reachability",
                True,
                details="关联主机 SSH 可用，已完成端口辅助探测",
                latency_ms=self._elapsed_ms(started_at),
            )
        return self._check(
            "host",
            "ssh_reachability",
            False,
            error=result.get("error") or "关联主机检查失败",
            latency_ms=self._elapsed_ms(started_at),
        )

    async def _run_tcp_check(self, host: str, port: int) -> Dict[str, Any]:
        started_at = time.perf_counter()
        try:
            reader, writer = await asyncio.wait_for(asyncio.open_connection(host, port), timeout=5)
            writer.close()
            await writer.wait_closed()
            return self._check("tcp", "tcp_connect", True, details="TCP 端口可达", latency_ms=self._elapsed_ms(started_at))
        except Exception as exc:
            return self._check(
                "tcp",
                "tcp_connect",
                False,
                error=self._sanitize_error(exc),
                latency_ms=self._elapsed_ms(started_at),
            )

    def _classify_exception(self, exc: Exception) -> Dict[str, Any]:
        if isinstance(exc, asyncio.TimeoutError) or isinstance(exc, TimeoutError):
            return self._classification("tcp", "connection_timeout", "TCP_TIMEOUT", retryable=True)
        if isinstance(exc, ConnectionRefusedError):
            return self._classification("tcp", "port_unreachable", "TCP_CONNECTION_REFUSED", retryable=True)
        if isinstance(exc, socket.gaierror):
            return self._classification("dns", "dns_resolution_failed", "DNS_RESOLUTION_FAILED")
        if isinstance(exc, ImportError):
            return self._classification("driver", "driver_not_installed", "DRIVER_IMPORT_ERROR")
        return self._classify_exception_message(self._sanitize_error(exc))

    def _classify_exception_message(self, message: str, layer_hint: Optional[str] = None) -> Dict[str, Any]:
        text = (message or "").lower()
        layer = layer_hint or "db_handshake"

        if any(token in text for token in ["name or service not known", "nodename nor servname provided", "temporary failure in name resolution", "getaddrinfo failed"]):
            return self._classification("dns", "dns_resolution_failed", "DNS_RESOLUTION_FAILED")
        if "connection refused" in text:
            return self._classification("tcp", "port_unreachable", "TCP_CONNECTION_REFUSED", retryable=True)
        if any(token in text for token in ["timed out", "timeout", "serverselectiontimeout"]):
            return self._classification(layer_hint or "tcp", "connection_timeout", "TCP_TIMEOUT", retryable=True)
        if any(token in text for token in ["no route to host", "network is unreachable", "host is unreachable"]):
            return self._classification("tcp", "host_unreachable", "HOST_UNREACHABLE", retryable=True)
        if any(token in text for token in ["access denied", "password authentication failed", "authentication failed", "wrongpass", "login failed", "ora-01017"]):
            return self._classification("auth", "authentication_failed", "DB_AUTH_FAILED")
        if any(token in text for token in ["unknown database", "database does not exist", "ora-12514", "listener does not currently know of service requested"]):
            return self._classification("database_state", "database_not_found", "DB_DATABASE_NOT_FOUND")
        if any(token in text for token in ["not open", "ora-01034", "ora-27101", "service unavailable"]):
            return self._classification("database_state", "database_not_open", "DB_INSTANCE_NOT_OPEN", retryable=True)
        if any(token in text for token in ["ssl", "tls", "certificate"]):
            return self._classification("protocol", "ssl_handshake_failed", "DB_SSL_HANDSHAKE_FAILED")
        if any(token in text for token in ["protocol", "packet", "unexpected response"]):
            return self._classification("protocol", "protocol_mismatch", "DB_PROTOCOL_ERROR")
        return self._classification(layer, "unknown_error", "UNKNOWN_ERROR")

    def _build_diagnosis(self, classification: Dict[str, Any]) -> Dict[str, Any]:
        mapping = {
            "dns_resolution_failed": (
                ["数据库主机名无法解析"],
                ["确认 host 是否填写正确", "检查 DNS 配置或改用 IP 地址"],
            ),
            "port_unreachable": (
                ["目标端口未监听或被防火墙拦截"],
                ["确认数据库实例已启动", "检查数据库监听端口和防火墙/安全组规则"],
            ),
            "connection_timeout": (
                ["网络链路超时或目标主机响应过慢"],
                ["检查网络连通性和链路丢包", "确认数据库主机负载与安全组设置"],
            ),
            "host_unreachable": (
                ["网络不可达或路由不通"],
                ["检查路由、网关、防火墙和跨网段访问策略"],
            ),
            "authentication_failed": (
                ["用户名或密码错误，或认证方式不匹配"],
                ["核对用户名密码", "确认数据库认证插件/认证方式与驱动兼容"],
            ),
            "database_not_found": (
                ["目标数据库/service name 不存在或配置错误"],
                ["检查 database/service name/SID 配置", "确认目标库已创建且名称正确"],
            ),
            "database_not_open": (
                ["数据库实例未启动或未 open"],
                ["检查数据库实例状态", "确认 listener/service 已正常注册并对外提供服务"],
            ),
            "ssl_handshake_failed": (
                ["SSL/TLS 握手失败或证书要求不匹配"],
                ["检查数据库 SSL 配置", "确认驱动参数与服务端 TLS 策略一致"],
            ),
            "protocol_mismatch": (
                ["目标端口上的协议与数据库类型不匹配"],
                ["确认 db_type 与端口对应服务一致", "检查是否连到了错误端口或代理"],
            ),
            "driver_not_installed": (
                ["当前环境缺少对应数据库驱动"],
                ["安装缺失驱动依赖", "确认运行环境包含对应数据库客户端库"],
            ),
            "unknown_error": (
                ["发生了未归类的连接异常"],
                ["查看 raw_error 获取原始信息", "根据异常内容进一步补充分类规则"],
            ),
        }
        probable_causes, recommendations = mapping.get(
            classification["category"],
            mapping["unknown_error"],
        )
        if (
            classification["category"] == "ssl_handshake_failed"
            and classification.get("code") == "DB_SSL_HANDSHAKE_FAILED"
        ):
            probable_causes = ["SQL Server SSL/TLS 握手失败"]
            recommendations = [
                "当前默认配置已兼容 SQL Server 2012（TrustServerCertificate=yes, Encrypt=no）",
                "如仍失败，请检查网络或数据库服务端配置",
            ]
        return self._diagnosis(probable_causes, recommendations)

    def _classification(
        self,
        layer: str,
        category: str,
        code: str,
        severity: str = "error",
        retryable: bool = False,
    ) -> Dict[str, Any]:
        return {
            "layer": layer,
            "category": category,
            "code": code,
            "severity": severity,
            "retryable": retryable,
        }

    def _check(
        self,
        layer: str,
        name: str,
        success: bool,
        details: Optional[str] = None,
        error: Optional[str] = None,
        latency_ms: Optional[float] = None,
        skipped: bool = False,
        reason: Optional[str] = None,
    ) -> Dict[str, Any]:
        return {
            "layer": layer,
            "name": name,
            "success": success,
            "details": details,
            "error": error,
            "latency_ms": latency_ms,
            "skipped": skipped,
            "reason": reason,
        }

    def _diagnosis(self, probable_causes: list[str], recommendations: list[str]) -> Dict[str, Any]:
        return {
            "probable_causes": probable_causes,
            "recommendations": recommendations,
        }

    def _finalize_result(
        self,
        success: bool,
        message: str,
        summary: str,
        target: Dict[str, Any],
        checks: list[Dict[str, Any]],
        total_ms: float,
        version: Optional[str] = None,
        classification: Optional[Dict[str, Any]] = None,
        diagnosis: Optional[Dict[str, Any]] = None,
        raw_error: Optional[str] = None,
    ) -> Dict[str, Any]:
        result: Dict[str, Any] = {
            "success": success,
            "message": message,
            "version": version,
            "summary": summary,
            "classification": classification,
            "checks": checks,
            "diagnosis": diagnosis,
            "raw_error": raw_error,
            "target": target,
            "timing": {"total_ms": total_ms},
        }
        return result

    def _elapsed_ms(self, started_at: float) -> float:
        return round((time.perf_counter() - started_at) * 1000, 2)

    def _sanitize_error(self, exc: Any) -> str:
        text = str(exc).strip() or type(exc).__name__ or "Connection failed"
        return text.replace("\n", " ")
