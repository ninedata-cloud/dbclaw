import logging
from datetime import datetime

from sqlalchemy import select

from backend.models.datasource import Datasource
from backend.models.report import Report
from backend.models.host import Host
from backend.agent.prompts import REPORT_GENERATION_PROMPT
from backend.database import async_session
from backend.utils.encryption import decrypt_value
from backend.services.db_connector import get_connector
from backend.services.ssh_service import SSHService
from backend.services.os_metrics_service import OSMetricsService
from backend.agent.conversation_skills import generate_report_with_skills

logger = logging.getLogger(__name__)


async def generate_report(report_id: int, datasource_id: int, report_type: str = "comprehensive"):
    """Generate a comprehensive diagnostic report for a database datasource."""
    try:
        async with async_session() as db:
            datasource_result = await db.execute(select(Datasource).where(Datasource.id == datasource_id))
            datasource = datasource_result.scalar_one_or_none()
            if not datasource:
                await _update_report_status(report_id, "failed", summary="Datasource not found")
                return

            password = decrypt_value(datasource.password_encrypted) if datasource.password_encrypted else None
            connector = get_connector(
                db_type=datasource.db_type, host=datasource.host, port=datasource.port,
                username=datasource.username, password=password, database=datasource.database,
            )

            # Collect data
            data = {}
            try:
                data["version"] = await connector.test_connection()
            except Exception as e:
                data["version"] = "Unknown"

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

            try:
                data["index_stats"] = await connector.get_index_stats()
            except Exception as e:
                data["index_stats"] = []

            try:
                data["lock_waits"] = await connector.get_lock_waits()
            except Exception as e:
                data["lock_waits"] = []

            try:
                data["fragmentation"] = await connector.get_table_fragmentation()
            except Exception as e:
                data["fragmentation"] = []

            # OS metrics if SSH is configured
            os_metrics = None
            if datasource.host_id:
                try:
                    ssh_result = await db.execute(select(Host).where(Host.id == datasource.host_id))
                    host = ssh_result.scalar_one_or_none()
                    if host:
                        ssh_pwd = decrypt_value(host.password_encrypted) if host.password_encrypted else None
                        ssh_key = decrypt_value(host.private_key_encrypted) if host.private_key_encrypted else None
                        ssh = SSHService(host=host.host, port=host.port, username=host.username,
                                        password=ssh_pwd, private_key=ssh_key)
                        os_svc = OSMetricsService(ssh)
                        os_metrics = os_svc.collect()
                        data["os_metrics"] = os_metrics
                except Exception as e:
                    logger.warning(f"Failed to collect OS metrics: {e}")

            # Run diagnostic engine
            engine = DiagnosticEngine()
            findings = engine.analyze(
                db_type=datasource.db_type,
                status=data.get("status", {}),
                variables=data.get("variables"),
                slow_queries=data.get("slow_queries"),
                table_stats=data.get("table_stats"),
                replication=data.get("replication"),
                os_metrics=os_metrics,
                index_stats=data.get("index_stats"),
                lock_waits=data.get("lock_waits"),
                fragmentation=data.get("fragmentation"),
            )

            # Generate markdown report
            md_content = _build_markdown_report(datasource, data, findings)

            # Generate HTML report
            html_content = _build_html_report(datasource, data, findings)

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


def _build_markdown_report(datasource, data: dict, findings: list) -> str:
    status = data.get("status", {})
    db_size = data.get("db_size", {})
    os_metrics = data.get("os_metrics", {})
    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")

    md = f"""# Database Diagnostic Report

**Generated:** {now}
**Datasource:** {datasource.name} ({datasource.db_type})
**Host:** {datasource.host}:{datasource.port}
**Database:** {datasource.database or 'N/A'}

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

    md += "---\n\n## Database Configuration\n\n"
    variables = data.get("variables", {})
    version = data.get("version", "Unknown")

    md += f"- **Version:** {version}\n"

    if datasource.db_type == "postgresql":
        md += f"- **Uptime:** {status.get('uptime', 'N/A')} seconds\n"
        md += f"- **Max Connections:** {variables.get('max_connections', 'N/A')}\n"
        md += f"- **Shared Buffers:** {variables.get('shared_buffers', 'N/A')}\n"
        md += f"- **Work Mem:** {variables.get('work_mem', 'N/A')}\n"
    elif datasource.db_type == "mysql":
        md += f"- **Uptime:** {status.get('uptime', 'N/A')} seconds\n"
        md += f"- **Max Connections:** {variables.get('max_connections', 'N/A')}\n"
        md += f"- **InnoDB Buffer Pool Size:** {variables.get('innodb_buffer_pool_size', 'N/A')}\n"
        md += f"- **Query Cache Size:** {variables.get('query_cache_size', 'N/A')}\n"
    else:
        md += f"- **Uptime:** {status.get('uptime', 'N/A')}\n"
        md += f"- **Max Connections:** {variables.get('max_connections', 'N/A')}\n"
    md += "\n"

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

    # Index Analysis
    index_stats = data.get("index_stats", [])
    if index_stats:
        md += "\n---\n\n## Index Analysis\n\n"
        tables_with_indexes = {}
        for idx in index_stats:
            table = idx.get("tablename") or idx.get("table")
            if table not in tables_with_indexes:
                tables_with_indexes[table] = []
            tables_with_indexes[table].append(idx)

        md += f"**Total Indexes:** {len(index_stats)}\n\n"
        for table, indexes in list(tables_with_indexes.items())[:10]:
            md += f"### Table: {table}\n"
            for idx in indexes[:5]:
                idx_name = idx.get('indexname') or idx.get('index')
                column = idx.get('column') or 'N/A'
                cardinality = idx.get('cardinality') or idx.get('idx_scan') or 0
                md += f"- **{idx_name}** (scans: {cardinality})\n"
            md += "\n"

    # Lock Waits
    lock_waits = data.get("lock_waits", [])
    if lock_waits:
        md += "\n---\n\n## Lock Waits\n\n"
        md += f"**Active Lock Waits:** {len(lock_waits)}\n\n"
        for lock in lock_waits[:10]:
            md += f"- Waiting Thread {lock.get('waiting_thread')} blocked by Thread {lock.get('blocking_thread')}\n"
            md += f"  Query: `{lock.get('waiting_query', 'N/A')[:100]}...`\n\n"

    # Table Fragmentation
    fragmentation = data.get("fragmentation", [])
    if fragmentation:
        md += "\n---\n\n## Table Fragmentation\n\n"
        md += "| Table | Dead Tuples | Live Tuples | Dead Ratio % |\n|-------|-------------|-------------|-------------|\n"
        for frag in fragmentation[:10]:
            table = frag.get('tablename') or frag.get('table')
            dead = frag.get('n_dead_tup') or frag.get('data_free', 0)
            live = frag.get('n_live_tup') or frag.get('data_length', 0)
            ratio = frag.get('dead_ratio') or frag.get('fragmentation_pct', 0)
            md += f"| {table} | {dead} | {live} | {ratio}% |\n"
        md += "\n"

    md += "\n---\n\n## Findings\n\n"
    for f in findings:
        icon = {"CRITICAL": "🔴", "WARNING": "🟡", "INFO": "🔵"}.get(f["severity"], "⚪")
        md += f"### {icon} [{f['severity']}] {f['title']}\n\n"
        md += f"**Category:** {f['category']}\n\n"
        md += f"{f['detail']}\n\n"
        md += f"**Recommendation:** {f['recommendation']}\n\n"

    md += "---\n\n*Report generated by NineData DBMaster*\n"
    return md


def _build_html_report(datasource, data: dict, findings: list) -> str:
    try:
        with open("templates/report_template.html", "r") as f:
            template_str = f.read()
        template = Template(template_str)
        return template.render(
            conn=datasource,
            data=data,
            findings=findings,
            generated_at=datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC"),
            format_bytes=_format_bytes,
        )
    except Exception as e:
        logger.warning(f"Failed to render HTML template: {e}")
        # Fallback: simple HTML
        md = _build_markdown_report(datasource, data, findings)
        return f"<html><body><pre>{md}</pre></body></html>"


class ReportGenerator:
    """Generate inspection reports"""

    def __init__(self, db):
        self.db = db

    async def generate_inspection_report(self, trigger_id: int) -> int:
        """Generate AI-driven inspection report from trigger"""
        from backend.models.inspection_trigger import InspectionTrigger
        from backend.models.inspection_config import InspectionConfig
        from backend.agent.conversation_skills import generate_report_with_skills

        result = await self.db.execute(select(InspectionTrigger).where(InspectionTrigger.id == trigger_id))
        trigger = result.scalar_one()

        result = await self.db.execute(select(Datasource).where(Datasource.id == trigger.datasource_id))
        datasource = result.scalar_one()

        result = await self.db.execute(select(InspectionConfig).where(InspectionConfig.datasource_id == trigger.datasource_id))
        config = result.scalar_one_or_none()

        # Create report
        report = Report(
            datasource_id=trigger.datasource_id,
            title=f"{trigger.trigger_type.capitalize()} Inspection - {datasource.name}",
            report_type="inspection",
            status="generating",
            trigger_type=trigger.trigger_type,
            trigger_id=trigger.id,
            trigger_reason=trigger.trigger_reason,
            generation_method="ai"
        )
        self.db.add(report)
        await self.db.flush()

        try:
            # Generate AI report
            content_md, skill_executions = await generate_report_with_skills(
                datasource_id=datasource.id,
                datasource_name=datasource.name,
                datasource_type=datasource.db_type,
                trigger_reason=trigger.trigger_reason or "Inspection requested",
                system_prompt=REPORT_GENERATION_PROMPT,
                db=self.db,
                model_id=config.ai_model_id if config else None,
                timeout_seconds=300
            )

            # Generate HTML from markdown
            from markdown_it import MarkdownIt
            md = MarkdownIt("commonmark", {"breaks": True, "html": True})
            md.enable('table')
            content_html_body = md.render(content_md)

            # Wrap in styled HTML document
            content_html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>数据库巡检报告 - {datasource.name}</title>
    <style>
        * {{ box-sizing: border-box; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, 'Microsoft YaHei', sans-serif;
            margin: 0;
            padding: 40px;
            line-height: 1.6;
            background: #f5f7fa;
            color: #333;
        }}
        .container {{
            max-width: 1200px;
            margin: 0 auto;
            background: white;
            padding: 40px;
            border-radius: 8px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.1);
        }}
        h1 {{
            color: #1a1a1a;
            font-size: 32px;
            margin-bottom: 20px;
            border-bottom: 3px solid #007bff;
            padding-bottom: 15px;
        }}
        h2 {{
            color: #2c3e50;
            margin-top: 40px;
            font-size: 24px;
            border-left: 4px solid #007bff;
            padding-left: 15px;
        }}
        h3 {{
            color: #34495e;
            margin-top: 30px;
            font-size: 20px;
        }}
        h4 {{
            color: #555;
            margin-top: 20px;
            font-size: 16px;
        }}
        table {{
            border-collapse: collapse;
            width: 100%;
            margin: 20px 0;
            background: white;
            box-shadow: 0 1px 3px rgba(0,0,0,0.1);
        }}
        th {{
            background: #007bff;
            color: white;
            padding: 12px;
            text-align: left;
            font-weight: 600;
        }}
        td {{
            padding: 10px 12px;
            border-bottom: 1px solid #e9ecef;
        }}
        tr:hover {{
            background: #f8f9fa;
        }}
        code {{
            background: #f4f4f4;
            padding: 2px 6px;
            border-radius: 3px;
            font-family: 'Monaco', 'Menlo', 'Courier New', monospace;
            font-size: 13px;
            color: #e83e8c;
        }}
        pre {{
            background: #2d2d2d;
            color: #f8f8f2;
            padding: 15px;
            border-radius: 5px;
            overflow-x: auto;
            margin: 15px 0;
        }}
        pre code {{
            background: none;
            padding: 0;
            color: #f8f8f2;
        }}
        ul, ol {{
            margin: 10px 0;
            padding-left: 30px;
        }}
        li {{
            margin: 5px 0;
        }}
        blockquote {{
            border-left: 4px solid #007bff;
            padding-left: 15px;
            margin: 15px 0;
            color: #666;
            background: #f8f9fa;
            padding: 10px 15px;
            border-radius: 4px;
        }}
        hr {{
            border: 0;
            border-top: 2px solid #e9ecef;
            margin: 40px 0;
        }}
        .footer {{
            text-align: center;
            margin-top: 50px;
            padding-top: 20px;
            border-top: 1px solid #e9ecef;
            color: #6c757d;
            font-size: 14px;
        }}
    </style>
</head>
<body>
    <div class="container">
        {content_html_body}
        <div class="footer">
            <p>报告由 <strong>SmartDBA 智能诊断引擎</strong> 生成</p>
            <p>数据源: {datasource.name} ({datasource.db_type.upper()}) | 生成时间: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}</p>
        </div>
    </div>
</body>
</html>
"""

            report.content_md = content_md
            report.content_html = content_html
            report.skill_executions = skill_executions
            report.status = "completed"
            report.completed_at = datetime.utcnow()

        except Exception as e:
            logger.error(f"Error generating inspection report: {e}", exc_info=True)
            report.status = "failed"
            report.error_message = str(e)

        await self.db.commit()
        return report.id
