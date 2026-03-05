import logging
import json
from datetime import datetime
from typing import Optional

from jinja2 import Template
from sqlalchemy import select

from backend.database import async_session
from backend.models.connection import Connection
from backend.models.report import Report
from backend.models.ssh_host import SSHHost
from backend.services.db_connector import get_connector
from backend.services.diagnostic_engine import DiagnosticEngine
from backend.services.ssh_service import SSHService
from backend.services.os_metrics_service import OSMetricsService
from backend.utils.encryption import decrypt_value

logger = logging.getLogger(__name__)


async def generate_report(report_id: int, connection_id: int, report_type: str = "comprehensive"):
    """Generate a comprehensive diagnostic report for a database connection."""
    try:
        async with async_session() as db:
            conn_result = await db.execute(select(Connection).where(Connection.id == connection_id))
            conn = conn_result.scalar_one_or_none()
            if not conn:
                await _update_report_status(report_id, "failed", summary="Connection not found")
                return

            password = decrypt_value(conn.password_encrypted) if conn.password_encrypted else None
            connector = get_connector(
                db_type=conn.db_type, host=conn.host, port=conn.port,
                username=conn.username, password=password, database=conn.database,
            )

            # Collect data
            data = {}
            try:
                data["status"] = await connector.get_status()
            except Exception as e:
                data["status"] = {"error": str(e)}

            try:
                data["variables"] = await connector.get_variables()
            except Exception as e:
                data["variables"] = {}

            try:
                data["slow_queries"] = await connector.get_slow_queries()
            except Exception as e:
                data["slow_queries"] = []

            try:
                data["table_stats"] = await connector.get_table_stats()
            except Exception as e:
                data["table_stats"] = []

            try:
                data["replication"] = await connector.get_replication_status()
            except Exception as e:
                data["replication"] = {}

            try:
                data["db_size"] = await connector.get_db_size()
            except Exception as e:
                data["db_size"] = {}

            try:
                data["processes"] = await connector.get_process_list()
            except Exception as e:
                data["processes"] = []

            # OS metrics if SSH is configured
            os_metrics = None
            if conn.ssh_host_id:
                try:
                    ssh_result = await db.execute(select(SSHHost).where(SSHHost.id == conn.ssh_host_id))
                    ssh_host = ssh_result.scalar_one_or_none()
                    if ssh_host:
                        ssh_pwd = decrypt_value(ssh_host.password_encrypted) if ssh_host.password_encrypted else None
                        ssh_key = decrypt_value(ssh_host.private_key_encrypted) if ssh_host.private_key_encrypted else None
                        ssh = SSHService(host=ssh_host.host, port=ssh_host.port, username=ssh_host.username,
                                        password=ssh_pwd, private_key=ssh_key)
                        os_svc = OSMetricsService(ssh)
                        os_metrics = os_svc.collect()
                        data["os_metrics"] = os_metrics
                except Exception as e:
                    logger.warning(f"Failed to collect OS metrics: {e}")

            # Run diagnostic engine
            engine = DiagnosticEngine()
            findings = engine.analyze(
                db_type=conn.db_type,
                status=data.get("status", {}),
                variables=data.get("variables"),
                slow_queries=data.get("slow_queries"),
                table_stats=data.get("table_stats"),
                replication=data.get("replication"),
                os_metrics=os_metrics,
            )

            # Generate markdown report
            md_content = _build_markdown_report(conn, data, findings)

            # Generate HTML report
            html_content = _build_html_report(conn, data, findings)

            # Count severities
            critical_count = sum(1 for f in findings if f["severity"] == "CRITICAL")
            warning_count = sum(1 for f in findings if f["severity"] == "WARNING")
            info_count = sum(1 for f in findings if f["severity"] == "INFO")

            summary = f"Found {len(findings)} issues: {critical_count} critical, {warning_count} warnings, {info_count} informational."

            await _update_report_status(
                report_id, "completed",
                summary=summary,
                content_md=md_content,
                content_html=html_content,
                findings=findings,
            )

            await connector.close()

    except Exception as e:
        logger.error(f"Report generation failed: {e}")
        await _update_report_status(report_id, "failed", summary=str(e))


async def _update_report_status(report_id: int, status: str, **kwargs):
    async with async_session() as db:
        result = await db.execute(select(Report).where(Report.id == report_id))
        report = result.scalar_one_or_none()
        if report:
            report.status = status
            if status == "completed":
                report.completed_at = datetime.utcnow()
            for k, v in kwargs.items():
                setattr(report, k, v)
            await db.commit()


def _format_bytes(b):
    if not b or b == 0:
        return "0 B"
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if abs(b) < 1024:
            return f"{b:.1f} {unit}"
        b /= 1024
    return f"{b:.1f} PB"


def _build_markdown_report(conn, data: dict, findings: list) -> str:
    status = data.get("status", {})
    db_size = data.get("db_size", {})
    os_metrics = data.get("os_metrics", {})
    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")

    md = f"""# Database Diagnostic Report

**Generated:** {now}
**Connection:** {conn.name} ({conn.db_type})
**Host:** {conn.host}:{conn.port}
**Database:** {conn.database or 'N/A'}

---

## Executive Summary

"""
    critical = [f for f in findings if f["severity"] == "CRITICAL"]
    warnings = [f for f in findings if f["severity"] == "WARNING"]
    infos = [f for f in findings if f["severity"] == "INFO"]

    if critical:
        md += f"**{len(critical)} Critical issues** require immediate attention.\n\n"
    if warnings:
        md += f"**{len(warnings)} Warnings** should be reviewed.\n\n"
    md += f"**{len(infos)} Informational** findings noted.\n\n"

    md += "---\n\n## Database Status\n\n"
    md += "| Metric | Value |\n|--------|-------|\n"
    for k, v in status.items():
        if k != "error":
            md += f"| {k.replace('_', ' ').title()} | {v} |\n"

    if db_size:
        md += f"\n### Database Size\n\n"
        for k, v in db_size.items():
            if "bytes" in k:
                md += f"- **{k.replace('_', ' ').title()}:** {_format_bytes(v)}\n"
            else:
                md += f"- **{k.replace('_', ' ').title()}:** {v}\n"

    if os_metrics:
        md += "\n---\n\n## OS Resource Usage\n\n"
        md += f"- **CPU Usage:** {os_metrics.get('cpu_usage_percent', 'N/A')}%\n"
        md += f"- **Memory Usage:** {os_metrics.get('memory_usage_percent', 'N/A')}%\n"
        md += f"- **Disk Usage:** {os_metrics.get('disk_usage_percent', 'N/A')}%\n"
        md += f"- **Load Average:** {os_metrics.get('load_1m', 'N/A')} / {os_metrics.get('load_5m', 'N/A')} / {os_metrics.get('load_15m', 'N/A')}\n"

    md += "\n---\n\n## Findings\n\n"
    for f in findings:
        icon = {"CRITICAL": "🔴", "WARNING": "🟡", "INFO": "🔵"}.get(f["severity"], "⚪")
        md += f"### {icon} [{f['severity']}] {f['title']}\n\n"
        md += f"**Category:** {f['category']}\n\n"
        md += f"{f['detail']}\n\n"
        md += f"**Recommendation:** {f['recommendation']}\n\n"

    md += "---\n\n*Report generated by NineData DBMaster*\n"
    return md


def _build_html_report(conn, data: dict, findings: list) -> str:
    try:
        with open("templates/report_template.html", "r") as f:
            template_str = f.read()
        template = Template(template_str)
        return template.render(
            conn=conn,
            data=data,
            findings=findings,
            generated_at=datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC"),
            format_bytes=_format_bytes,
        )
    except Exception as e:
        logger.warning(f"Failed to render HTML template: {e}")
        # Fallback: simple HTML
        md = _build_markdown_report(conn, data, findings)
        return f"<html><body><pre>{md}</pre></body></html>"
