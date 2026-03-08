"""
AI-powered report generation service with real-time streaming
"""
import json
import logging
from datetime import datetime
from typing import AsyncGenerator, Dict, Any, Optional, List

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from fastapi import WebSocket

from backend.models.datasource import Datasource
from backend.models.report import Report
from backend.agent.conversation_skills import run_conversation_with_skills
from backend.agent.prompts import DIAGNOSTIC_PROMPT, REPORT_GENERATION_PROMPT
from backend.services.diagnostic_engine import DiagnosticEngine

logger = logging.getLogger(__name__)


async def generate_ai_report(
    report_id: int,
    datasource_id: int,
    report_type: str,
    model_id: Optional[int] = None,
    kb_ids: Optional[List[int]] = None,
    db: AsyncSession = None,
    user_id: Optional[int] = None,
    websocket: Optional[WebSocket] = None
) -> AsyncGenerator[Dict[str, Any], None]:
    """
    Generate an AI-powered diagnostic report with real-time streaming.

    Yields events:
    - {"type": "status", "message": "..."}
    - {"type": "content", "content": "..."}
    - {"type": "tool_call", "tool_name": "...", "tool_args": {...}}
    - {"type": "tool_result", "tool_name": "...", "result": {...}, "execution_time_ms": 123}
    - {"type": "section_complete", "section": "...", "summary": "..."}
    - {"type": "finding", "severity": "...", "title": "...", "detail": "...", "recommendation": "..."}
    - {"type": "report_complete", "report_id": 123, "summary": "..."}
    - {"type": "done"}
    - {"type": "error", "message": "..."}
    """

    try:
        # Phase 1: Initialization
        yield {"type": "status", "message": "Initializing diagnostic session..."}

        # Load datasource configuration
        datasource_result = await db.execute(select(Datasource).where(Datasource.id == datasource_id))
        datasource = datasource_result.scalar_one_or_none()

        if not datasource:
            yield {"type": "error", "message": "Datasource not found"}
            await _update_report_status(db, report_id, "failed", error_message="Datasource not found")
            return

        # Determine database type and skill prefix
        skill_prefix_map = {
            'mysql': 'mysql',
            'postgresql': 'pg',
            'sqlserver': 'mssql',
            'oracle': 'oracle'
        }
        skill_prefix = skill_prefix_map.get(datasource.db_type, datasource.db_type)

        yield {
            "type": "status",
            "message": f"Connected to {datasource.db_type.upper()} database: {datasource.name}"
        }

        # Phase 2: AI Diagnostic Analysis
        yield {"type": "status", "message": "Starting AI diagnostic analysis..."}

        # Build system prompt combining diagnostic and report generation prompts
        system_prompt = DIAGNOSTIC_PROMPT + "\n\n" + REPORT_GENERATION_PROMPT

        # Create initial diagnostic message
        initial_message = f"""Generate a comprehensive diagnostic report for this {datasource.db_type.upper()} database.

Database: {datasource.name}
Type: {datasource.db_type.upper()}
Report Type: {report_type}

Follow the report structure outlined in your instructions. Call diagnostic skills systematically to gather data, then provide detailed analysis and recommendations."""

        messages = [{"role": "user", "content": initial_message}]

        # Collect AI analysis and tool results
        ai_analysis_parts = []
        collected_data = {}

        # Stream AI conversation
        async for event in run_conversation_with_skills(
            messages=messages,
            datasource_id=datasource_id,
            model_id=model_id,
            kb_ids=kb_ids,
            db=db,
            user_id=user_id,
            session_id=None
        ):
            # Handle error events from conversation
            if event["type"] == "error":
                yield event
                await _update_report_status(db, report_id, "failed", error_message=event.get("message", "Unknown error"))
                return

            # Forward all events to client
            yield event

            # Collect AI analysis text
            if event["type"] == "content":
                ai_analysis_parts.append(event["content"])

            # Collect tool results for rule-based validation
            if event["type"] == "tool_result":
                tool_name = event.get("tool_name", "")
                try:
                    result_data = json.loads(event.get("result", "{}"))

                    # Extract actual data from wrapped response
                    if isinstance(result_data, dict) and result_data.get("success"):
                        # Unwrap the data from the success wrapper
                        if "metrics" in result_data:
                            actual_data = result_data["metrics"]
                        elif "data" in result_data:
                            actual_data = result_data["data"]
                        elif "tables" in result_data:
                            actual_data = result_data["tables"]
                        elif "indexes" in result_data:
                            actual_data = result_data["indexes"]
                        elif "connections" in result_data:
                            actual_data = result_data["connections"]
                        else:
                            actual_data = result_data
                    else:
                        actual_data = result_data

                    # Map tool results to data categories with field normalization
                    if "get_db_status" in tool_name:
                        # Normalize field names for DiagnosticEngine
                        if isinstance(actual_data, dict):
                            normalized = {}
                            # PostgreSQL field mapping
                            if "active_connections" in actual_data:
                                normalized["connections_active"] = actual_data["active_connections"]
                            if "total_connections" in actual_data:
                                normalized["connections_total"] = actual_data["total_connections"]
                            # Parse cache_hit_ratio percentage string to float
                            if "cache_hit_ratio" in actual_data:
                                ratio_str = actual_data["cache_hit_ratio"]
                                if isinstance(ratio_str, str) and "%" in ratio_str:
                                    normalized["cache_hit_rate"] = float(ratio_str.rstrip("%"))
                                else:
                                    normalized["cache_hit_rate"] = actual_data["cache_hit_ratio"]
                            # Copy other fields
                            for key in ["transactions_committed", "transactions_rolled_back", "deadlocks",
                                       "threads_connected", "buffer_pool_hit_rate", "slow_queries",
                                       "innodb_row_lock_waits", "connected_clients", "hit_rate"]:
                                if key in actual_data:
                                    normalized[key] = actual_data[key]
                            collected_data["status"] = normalized
                        else:
                            collected_data["status"] = actual_data
                    elif "get_db_variables" in tool_name:
                        collected_data["variables"] = actual_data
                    elif "get_slow_queries" in tool_name:
                        # For slow queries, check if extension is enabled
                        if isinstance(result_data, dict) and not result_data.get("extension_enabled", True):
                            collected_data["slow_queries"] = []
                        else:
                            collected_data["slow_queries"] = actual_data
                    elif "get_table_stats" in tool_name:
                        collected_data["table_stats"] = actual_data
                    elif "get_replication_status" in tool_name:
                        collected_data["replication"] = actual_data
                    elif "get_process_list" in tool_name or "list_connections" in tool_name:
                        collected_data["processes"] = actual_data
                    elif "get_os_metrics" in tool_name:
                        # Normalize OS metrics
                        if isinstance(actual_data, dict):
                            normalized_os = {}
                            # Parse CPU usage
                            if "cpu_usage" in actual_data:
                                cpu_str = actual_data["cpu_usage"]
                                if isinstance(cpu_str, str):
                                    normalized_os["cpu_usage_percent"] = float(cpu_str)
                                else:
                                    normalized_os["cpu_usage_percent"] = cpu_str
                            # Parse memory usage from text output
                            if "memory" in actual_data:
                                mem_text = actual_data["memory"]
                                if isinstance(mem_text, str) and "Mem:" in mem_text:
                                    # Extract memory values from output
                                    lines = mem_text.split("\n")
                                    for line in lines:
                                        if line.strip().startswith("Mem:"):
                                            parts = line.split()
                                            if len(parts) >= 3:
                                                total = float(parts[1])
                                                used = float(parts[2])
                                                if total > 0:
                                                    normalized_os["memory_usage_percent"] = (used / total) * 100
                            # Parse disk usage from text output
                            if "disk" in actual_data:
                                disk_text = actual_data["disk"]
                                if isinstance(disk_text, str):
                                    # Find highest disk usage percentage
                                    max_usage = 0
                                    for line in disk_text.split("\n"):
                                        if "%" in line and not line.startswith("Filesystem"):
                                            parts = line.split()
                                            for part in parts:
                                                if "%" in part:
                                                    try:
                                                        usage = int(part.rstrip("%"))
                                                        max_usage = max(max_usage, usage)
                                                    except:
                                                        pass
                                    if max_usage > 0:
                                        normalized_os["disk_usage_percent"] = max_usage
                            collected_data["os_metrics"] = normalized_os
                        else:
                            collected_data["os_metrics"] = actual_data
                except json.JSONDecodeError:
                    pass

            # Check if conversation is done
            if event["type"] == "done":
                break

        # Combine AI analysis
        full_ai_analysis = "".join(ai_analysis_parts)

        # Phase 3: Rule-Based Validation
        yield {"type": "status", "message": "Running rule-based validation..."}

        engine = DiagnosticEngine()
        rule_based_findings = engine.analyze(
            db_type=datasource.db_type,
            status=collected_data.get("status", {}),
            variables=collected_data.get("variables"),
            slow_queries=collected_data.get("slow_queries"),
            table_stats=collected_data.get("table_stats"),
            replication=collected_data.get("replication"),
            os_metrics=collected_data.get("os_metrics"),
        )

        # Yield each finding
        for finding in rule_based_findings:
            yield {
                "type": "finding",
                "severity": finding["severity"],
                "category": finding["category"],
                "title": finding["title"],
                "detail": finding["detail"],
                "recommendation": finding["recommendation"]
            }

        # Phase 4: Report Assembly
        yield {"type": "status", "message": "Assembling final report..."}

        # Generate markdown content
        md_content = _build_markdown_report(
            datasource=datasource,
            ai_analysis=full_ai_analysis,
            findings=rule_based_findings,
            report_type=report_type
        )

        # Generate HTML content
        html_content = _build_html_report(
            datasource=datasource,
            ai_analysis=full_ai_analysis,
            findings=rule_based_findings,
            report_type=report_type
        )

        # Count severities
        critical_count = sum(1 for f in rule_based_findings if f["severity"] == "CRITICAL")
        warning_count = sum(1 for f in rule_based_findings if f["severity"] == "WARNING")
        info_count = sum(1 for f in rule_based_findings if f["severity"] == "INFO")

        summary = f"AI analysis completed. Found {len(rule_based_findings)} issues: {critical_count} critical, {warning_count} warnings, {info_count} informational."

        # Update report in database
        await _update_report_status(
            db=db,
            report_id=report_id,
            status="completed",
            summary=summary,
            content_md=md_content,
            content_html=html_content,
            findings=rule_based_findings,
            ai_analysis=full_ai_analysis,
            ai_model_id=model_id,
            kb_ids=kb_ids,
            generation_method="ai"
        )

        yield {
            "type": "report_complete",
            "report_id": report_id,
            "summary": summary
        }

        yield {"type": "done"}

    except Exception as e:
        logger.error(f"AI report generation failed for report {report_id}: {e}", exc_info=True)
        error_msg = f"{type(e).__name__}: {str(e)}"
        yield {"type": "error", "message": error_msg}
        try:
            await _update_report_status(
                db=db,
                report_id=report_id,
                status="failed",
                error_message=error_msg
            )
        except Exception as update_error:
            logger.error(f"Failed to update report status: {update_error}")


async def _update_report_status(
    db: AsyncSession,
    report_id: int,
    status: str,
    **kwargs
):
    """Update report status and fields in database"""
    result = await db.execute(select(Report).where(Report.id == report_id))
    report = result.scalar_one_or_none()

    if report:
        report.status = status
        if status == "completed":
            report.completed_at = datetime.utcnow()

        for k, v in kwargs.items():
            if hasattr(report, k):
                setattr(report, k, v)

        await db.commit()


def _build_markdown_report(
    datasource: Datasource,
    ai_analysis: str,
    findings: List[Dict[str, Any]],
    report_type: str
) -> str:
    """Build markdown report content"""

    md = f"""# Database Diagnostic Report

**Database:** {datasource.name}
**Type:** {datasource.db_type.upper()}
**Report Type:** {report_type}
**Generated:** {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}
**Generation Method:** AI-Powered Analysis

---

## AI Diagnostic Analysis

{ai_analysis}

---

## Rule-Based Findings

"""

    # Group findings by severity
    critical = [f for f in findings if f["severity"] == "CRITICAL"]
    warnings = [f for f in findings if f["severity"] == "WARNING"]
    info = [f for f in findings if f["severity"] == "INFO"]

    if critical:
        md += "### 🔴 Critical Issues\n\n"
        for f in critical:
            md += f"**{f['title']}**\n\n"
            md += f"{f['detail']}\n\n"
            md += f"*Recommendation:* {f['recommendation']}\n\n"
            md += "---\n\n"

    if warnings:
        md += "### 🟡 Warnings\n\n"
        for f in warnings:
            md += f"**{f['title']}**\n\n"
            md += f"{f['detail']}\n\n"
            md += f"*Recommendation:* {f['recommendation']}\n\n"
            md += "---\n\n"

    if info:
        md += "### 🔵 Informational\n\n"
        for f in info:
            md += f"**{f['title']}**\n\n"
            md += f"{f['detail']}\n\n"
            md += f"*Recommendation:* {f['recommendation']}\n\n"
            md += "---\n\n"

    return md


def _build_html_report(
    datasource: Datasource,
    ai_analysis: str,
    findings: List[Dict[str, Any]],
    report_type: str
) -> str:
    """Build HTML report content"""

    # Convert markdown AI analysis to HTML (simple conversion)
    ai_html = ai_analysis.replace("\n\n", "</p><p>").replace("\n", "<br>")
    ai_html = f"<p>{ai_html}</p>"

    # Build findings HTML
    findings_html = ""

    critical = [f for f in findings if f["severity"] == "CRITICAL"]
    warnings = [f for f in findings if f["severity"] == "WARNING"]
    info = [f for f in findings if f["severity"] == "INFO"]

    if critical:
        findings_html += '<h3 style="color: #dc3545;">🔴 Critical Issues</h3>'
        for f in critical:
            findings_html += f'''
            <div style="border-left: 4px solid #dc3545; padding-left: 15px; margin-bottom: 20px;">
                <h4>{f['title']}</h4>
                <p>{f['detail']}</p>
                <p><strong>Recommendation:</strong> {f['recommendation']}</p>
            </div>
            '''

    if warnings:
        findings_html += '<h3 style="color: #ffc107;">🟡 Warnings</h3>'
        for f in warnings:
            findings_html += f'''
            <div style="border-left: 4px solid #ffc107; padding-left: 15px; margin-bottom: 20px;">
                <h4>{f['title']}</h4>
                <p>{f['detail']}</p>
                <p><strong>Recommendation:</strong> {f['recommendation']}</p>
            </div>
            '''

    if info:
        findings_html += '<h3 style="color: #17a2b8;">🔵 Informational</h3>'
        for f in info:
            findings_html += f'''
            <div style="border-left: 4px solid #17a2b8; padding-left: 15px; margin-bottom: 20px;">
                <h4>{f['title']}</h4>
                <p>{f['detail']}</p>
                <p><strong>Recommendation:</strong> {f['recommendation']}</p>
            </div>
            '''

    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <title>Database Diagnostic Report - {datasource.name}</title>
        <style>
            body {{ font-family: Arial, sans-serif; margin: 40px; line-height: 1.6; }}
            h1 {{ color: #333; border-bottom: 3px solid #007bff; padding-bottom: 10px; }}
            h2 {{ color: #555; margin-top: 30px; }}
            h3 {{ color: #666; margin-top: 25px; }}
            .metadata {{ background: #f8f9fa; padding: 15px; border-radius: 5px; margin-bottom: 30px; }}
            .metadata p {{ margin: 5px 0; }}
            .ai-analysis {{ background: #e7f3ff; padding: 20px; border-radius: 5px; margin: 20px 0; }}
            hr {{ border: 0; border-top: 1px solid #ddd; margin: 30px 0; }}
        </style>
    </head>
    <body>
        <h1>Database Diagnostic Report</h1>

        <div class="metadata">
            <p><strong>Database:</strong> {datasource.name}</p>
            <p><strong>Type:</strong> {datasource.db_type.upper()}</p>
            <p><strong>Report Type:</strong> {report_type}</p>
            <p><strong>Generated:</strong> {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}</p>
            <p><strong>Generation Method:</strong> AI-Powered Analysis</p>
        </div>

        <h2>AI Diagnostic Analysis</h2>
        <div class="ai-analysis">
            {ai_html}
        </div>

        <hr>

        <h2>Rule-Based Findings</h2>
        {findings_html}

    </body>
    </html>
    """

    return html
