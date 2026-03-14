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
from markdown_it import MarkdownIt

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
    """Build markdown report content with rich formatting"""

    # Count findings by severity
    critical_count = sum(1 for f in findings if f["severity"] == "CRITICAL")
    warning_count = sum(1 for f in findings if f["severity"] == "WARNING")
    info_count = sum(1 for f in findings if f["severity"] == "INFO")

    # Determine health status
    if critical_count > 0:
        health_status = "🔴 Poor"
    elif warning_count > 3:
        health_status = "🟡 Fair"
    elif warning_count > 0:
        health_status = "🟢 Good"
    else:
        health_status = "✅ Excellent"

    md = f"""# 📋 Database Diagnostic Report

## Report Metadata

| Attribute | Value |
|-----------|-------|
| **Database** | {datasource.name} |
| **Type** | {datasource.db_type.upper()} |
| **Report Type** | {report_type.title()} |
| **Generated** | {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')} |
| **Generation Method** | AI-Powered Analysis |
| **Health Status** | {health_status} |

---

## 📊 Quick Summary

| Metric | Count |
|--------|-------|
| 🔴 Critical Issues | {critical_count} |
| 🟡 Warnings | {warning_count} |
| 🔵 Informational | {info_count} |
| **Total Findings** | **{len(findings)}** |

---

## 🤖 AI Diagnostic Analysis

{ai_analysis}

---

## 🔍 Rule-Based Findings

"""

    # Group findings by severity
    critical = [f for f in findings if f["severity"] == "CRITICAL"]
    warnings = [f for f in findings if f["severity"] == "WARNING"]
    info = [f for f in findings if f["severity"] == "INFO"]

    if critical:
        md += f"### 🔴 Critical Issues ({len(critical)} found)\n\n"
        md += "> ⚠️ **These issues require immediate attention!**\n\n"
        for idx, f in enumerate(critical, 1):
            md += f"#### {idx}. {f['title']}\n\n"
            md += f"**Category:** {f.get('category', 'General')}\n\n"
            md += f"**Details:**\n{f['detail']}\n\n"
            md += f"**💡 Recommendation:**\n{f['recommendation']}\n\n"
            md += "---\n\n"

    if warnings:
        md += f"### 🟡 Warnings ({len(warnings)} found)\n\n"
        md += "> These issues should be addressed soon to prevent potential problems.\n\n"
        for idx, f in enumerate(warnings, 1):
            md += f"#### {idx}. {f['title']}\n\n"
            md += f"**Category:** {f.get('category', 'General')}\n\n"
            md += f"**Details:**\n{f['detail']}\n\n"
            md += f"**💡 Recommendation:**\n{f['recommendation']}\n\n"
            md += "---\n\n"

    if info:
        md += f"### 🔵 Informational ({len(info)} found)\n\n"
        md += "> General observations and optimization opportunities.\n\n"
        for idx, f in enumerate(info, 1):
            md += f"#### {idx}. {f['title']}\n\n"
            md += f"**Category:** {f.get('category', 'General')}\n\n"
            md += f"**Details:**\n{f['detail']}\n\n"
            md += f"**💡 Recommendation:**\n{f['recommendation']}\n\n"
            md += "---\n\n"

    # Add action items section
    md += "## ✅ Recommended Action Items\n\n"

    if critical:
        md += "### 🚨 Immediate Actions (Within 24 hours)\n\n"
        for idx, f in enumerate(critical, 1):
            md += f"- [ ] **{f['title']}**: {f['recommendation'][:100]}...\n"
        md += "\n"

    if warnings:
        md += "### 📅 Short-term Actions (Within 1 week)\n\n"
        for idx, f in enumerate(warnings[:5], 1):  # Top 5 warnings
            md += f"- [ ] **{f['title']}**: {f['recommendation'][:100]}...\n"
        md += "\n"

    if info:
        md += "### 🎯 Long-term Optimizations\n\n"
        for idx, f in enumerate(info[:3], 1):  # Top 3 info items
            md += f"- [ ] **{f['title']}**: {f['recommendation'][:100]}...\n"
        md += "\n"

    md += "---\n\n"
    md += "*Report generated by SmartDBA AI-Powered Diagnostic Engine*\n"

    return md


def _build_html_report(
    datasource: Datasource,
    ai_analysis: str,
    findings: List[Dict[str, Any]],
    report_type: str
) -> str:
    """Build HTML report content with enhanced styling"""

    # Convert markdown AI analysis to HTML using markdown-it-py with table support
    md = MarkdownIt("commonmark", {"breaks": True, "html": True})
    md.enable('table')
    ai_html = md.render(ai_analysis)

    # Count findings by severity
    critical_count = sum(1 for f in findings if f["severity"] == "CRITICAL")
    warning_count = sum(1 for f in findings if f["severity"] == "WARNING")
    info_count = sum(1 for f in findings if f["severity"] == "INFO")

    # Determine health status
    if critical_count > 0:
        health_status = "🔴 Poor"
        health_color = "#dc3545"
    elif warning_count > 3:
        health_status = "🟡 Fair"
        health_color = "#ffc107"
    elif warning_count > 0:
        health_status = "🟢 Good"
        health_color = "#28a745"
    else:
        health_status = "✅ Excellent"
        health_color = "#28a745"

    # Build summary cards HTML
    summary_cards = f"""
    <div class="summary-cards">
        <div class="summary-card critical">
            <div class="card-icon">🔴</div>
            <div class="card-content">
                <div class="card-number">{critical_count}</div>
                <div class="card-label">Critical Issues</div>
            </div>
        </div>
        <div class="summary-card warning">
            <div class="card-icon">🟡</div>
            <div class="card-content">
                <div class="card-number">{warning_count}</div>
                <div class="card-label">Warnings</div>
            </div>
        </div>
        <div class="summary-card info">
            <div class="card-icon">🔵</div>
            <div class="card-content">
                <div class="card-number">{info_count}</div>
                <div class="card-label">Informational</div>
            </div>
        </div>
        <div class="summary-card total">
            <div class="card-icon">📊</div>
            <div class="card-content">
                <div class="card-number">{len(findings)}</div>
                <div class="card-label">Total Findings</div>
            </div>
        </div>
    </div>
    """

    # Build findings HTML
    findings_html = ""

    critical = [f for f in findings if f["severity"] == "CRITICAL"]
    warnings = [f for f in findings if f["severity"] == "WARNING"]
    info = [f for f in findings if f["severity"] == "INFO"]

    if critical:
        findings_html += f'<h3 class="findings-header critical">🔴 Critical Issues ({len(critical)} found)</h3>'
        findings_html += '<div class="alert alert-critical">⚠️ <strong>These issues require immediate attention!</strong></div>'
        for idx, f in enumerate(critical, 1):
            findings_html += f'''
            <div class="finding-card critical">
                <div class="finding-number">{idx}</div>
                <div class="finding-content">
                    <h4 class="finding-title">{f['title']}</h4>
                    <div class="finding-category">Category: {f.get('category', 'General')}</div>
                    <div class="finding-detail">{f['detail']}</div>
                    <div class="finding-recommendation">
                        <strong>💡 Recommendation:</strong> {f['recommendation']}
                    </div>
                </div>
            </div>
            '''

    if warnings:
        findings_html += f'<h3 class="findings-header warning">🟡 Warnings ({len(warnings)} found)</h3>'
        findings_html += '<div class="alert alert-warning">These issues should be addressed soon to prevent potential problems.</div>'
        for idx, f in enumerate(warnings, 1):
            findings_html += f'''
            <div class="finding-card warning">
                <div class="finding-number">{idx}</div>
                <div class="finding-content">
                    <h4 class="finding-title">{f['title']}</h4>
                    <div class="finding-category">Category: {f.get('category', 'General')}</div>
                    <div class="finding-detail">{f['detail']}</div>
                    <div class="finding-recommendation">
                        <strong>💡 Recommendation:</strong> {f['recommendation']}
                    </div>
                </div>
            </div>
            '''

    if info:
        findings_html += f'<h3 class="findings-header info">🔵 Informational ({len(info)} found)</h3>'
        findings_html += '<div class="alert alert-info">General observations and optimization opportunities.</div>'
        for idx, f in enumerate(info, 1):
            findings_html += f'''
            <div class="finding-card info">
                <div class="finding-number">{idx}</div>
                <div class="finding-content">
                    <h4 class="finding-title">{f['title']}</h4>
                    <div class="finding-category">Category: {f.get('category', 'General')}</div>
                    <div class="finding-detail">{f['detail']}</div>
                    <div class="finding-recommendation">
                        <strong>💡 Recommendation:</strong> {f['recommendation']}
                    </div>
                </div>
            </div>
            '''

    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <title>Database Diagnostic Report - {datasource.name}</title>
        <style>
            * {{ box-sizing: border-box; }}
            body {{
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
                margin: 0;
                padding: 40px;
                line-height: 1.6;
                background: #f5f7fa;
                color: #333;
            }}
            .container {{ max-width: 1200px; margin: 0 auto; background: white; padding: 40px; border-radius: 8px; box-shadow: 0 2px 8px rgba(0,0,0,0.1); }}
            h1 {{
                color: #1a1a1a;
                font-size: 32px;
                margin-bottom: 10px;
                border-bottom: 3px solid #007bff;
                padding-bottom: 15px;
            }}
            h2 {{ color: #2c3e50; margin-top: 40px; font-size: 24px; border-left: 4px solid #007bff; padding-left: 15px; }}
            h3 {{ color: #34495e; margin-top: 30px; font-size: 20px; }}
            h4 {{ color: #555; margin-top: 15px; font-size: 16px; }}

            .metadata {{
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: white;
                padding: 25px;
                border-radius: 8px;
                margin-bottom: 30px;
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
                gap: 15px;
            }}
            .metadata-item {{ display: flex; flex-direction: column; }}
            .metadata-label {{ font-size: 12px; opacity: 0.9; text-transform: uppercase; letter-spacing: 0.5px; }}
            .metadata-value {{ font-size: 18px; font-weight: bold; margin-top: 5px; }}
            .health-status {{
                display: inline-block;
                padding: 8px 16px;
                background: rgba(255,255,255,0.2);
                border-radius: 20px;
                font-size: 16px;
            }}

            .summary-cards {{
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
                gap: 20px;
                margin: 30px 0;
            }}
            .summary-card {{
                background: white;
                border-radius: 8px;
                padding: 20px;
                display: flex;
                align-items: center;
                gap: 15px;
                box-shadow: 0 2px 8px rgba(0,0,0,0.1);
                border-left: 4px solid #ddd;
            }}
            .summary-card.critical {{ border-left-color: #dc3545; }}
            .summary-card.warning {{ border-left-color: #ffc107; }}
            .summary-card.info {{ border-left-color: #17a2b8; }}
            .summary-card.total {{ border-left-color: #6c757d; }}
            .card-icon {{ font-size: 32px; }}
            .card-number {{ font-size: 32px; font-weight: bold; color: #333; }}
            .card-label {{ font-size: 14px; color: #666; }}

            .ai-analysis {{
                background: #f8f9fa;
                padding: 25px;
                border-radius: 8px;
                margin: 20px 0;
                border: 1px solid #e9ecef;
            }}
            .ai-analysis table {{
                border-collapse: collapse;
                width: 100%;
                margin: 15px 0;
                background: white;
                box-shadow: 0 1px 3px rgba(0,0,0,0.1);
            }}
            .ai-analysis th {{
                background: #007bff;
                color: white;
                padding: 12px;
                text-align: left;
                font-weight: 600;
            }}
            .ai-analysis td {{
                padding: 10px 12px;
                border-bottom: 1px solid #e9ecef;
            }}
            .ai-analysis tr:hover {{ background: #f8f9fa; }}
            .ai-analysis code {{
                background: #f4f4f4;
                padding: 2px 6px;
                border-radius: 3px;
                font-family: 'Monaco', 'Menlo', 'Courier New', monospace;
                font-size: 13px;
                color: #e83e8c;
            }}
            .ai-analysis pre {{
                background: #2d2d2d;
                color: #f8f8f2;
                padding: 15px;
                border-radius: 5px;
                overflow-x: auto;
                margin: 15px 0;
            }}
            .ai-analysis pre code {{
                background: none;
                padding: 0;
                color: #f8f8f2;
            }}
            .ai-analysis ul, .ai-analysis ol {{ margin: 10px 0; padding-left: 30px; }}
            .ai-analysis li {{ margin: 5px 0; }}
            .ai-analysis blockquote {{
                border-left: 4px solid #007bff;
                padding-left: 15px;
                margin: 15px 0;
                color: #666;
                background: #f8f9fa;
                padding: 10px 15px;
                border-radius: 4px;
            }}

            .alert {{
                padding: 12px 20px;
                border-radius: 6px;
                margin: 15px 0;
                font-size: 14px;
            }}
            .alert-critical {{ background: #f8d7da; color: #721c24; border-left: 4px solid #dc3545; }}
            .alert-warning {{ background: #fff3cd; color: #856404; border-left: 4px solid #ffc107; }}
            .alert-info {{ background: #d1ecf1; color: #0c5460; border-left: 4px solid #17a2b8; }}

            .findings-header {{
                margin-top: 40px;
                padding: 10px 15px;
                border-radius: 6px;
                font-size: 20px;
            }}
            .findings-header.critical {{ background: #f8d7da; color: #721c24; }}
            .findings-header.warning {{ background: #fff3cd; color: #856404; }}
            .findings-header.info {{ background: #d1ecf1; color: #0c5460; }}

            .finding-card {{
                display: flex;
                gap: 20px;
                background: white;
                border-radius: 8px;
                padding: 20px;
                margin: 15px 0;
                box-shadow: 0 2px 4px rgba(0,0,0,0.1);
                border-left: 4px solid #ddd;
            }}
            .finding-card.critical {{ border-left-color: #dc3545; }}
            .finding-card.warning {{ border-left-color: #ffc107; }}
            .finding-card.info {{ border-left-color: #17a2b8; }}
            .finding-number {{
                flex-shrink: 0;
                width: 40px;
                height: 40px;
                background: #007bff;
                color: white;
                border-radius: 50%;
                display: flex;
                align-items: center;
                justify-content: center;
                font-weight: bold;
                font-size: 18px;
            }}
            .finding-content {{ flex: 1; }}
            .finding-title {{ margin: 0 0 10px 0; color: #1a1a1a; font-size: 18px; }}
            .finding-category {{
                font-size: 12px;
                color: #666;
                text-transform: uppercase;
                letter-spacing: 0.5px;
                margin-bottom: 10px;
            }}
            .finding-detail {{
                color: #555;
                margin-bottom: 15px;
                line-height: 1.6;
            }}
            .finding-recommendation {{
                background: #f8f9fa;
                padding: 12px;
                border-radius: 6px;
                border-left: 3px solid #28a745;
            }}

            hr {{ border: 0; border-top: 2px solid #e9ecef; margin: 40px 0; }}

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
            <h1>📋 Database Diagnostic Report</h1>

            <div class="metadata">
                <div class="metadata-item">
                    <div class="metadata-label">Database</div>
                    <div class="metadata-value">{datasource.name}</div>
                </div>
                <div class="metadata-item">
                    <div class="metadata-label">Type</div>
                    <div class="metadata-value">{datasource.db_type.upper()}</div>
                </div>
                <div class="metadata-item">
                    <div class="metadata-label">Report Type</div>
                    <div class="metadata-value">{report_type.title()}</div>
                </div>
                <div class="metadata-item">
                    <div class="metadata-label">Health Status</div>
                    <div class="metadata-value">
                        <span class="health-status">{health_status}</span>
                    </div>
                </div>
                <div class="metadata-item">
                    <div class="metadata-label">Generated</div>
                    <div class="metadata-value">{datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}</div>
                </div>
                <div class="metadata-item">
                    <div class="metadata-label">Method</div>
                    <div class="metadata-value">AI-Powered</div>
                </div>
            </div>

            {summary_cards}

            <h2>🤖 AI Diagnostic Analysis</h2>
            <div class="ai-analysis">
                {ai_html}
            </div>

            <hr>

            <h2>🔍 Rule-Based Findings</h2>
            {findings_html}

            <div class="footer">
                <p>Report generated by <strong>SmartDBA AI-Powered Diagnostic Engine</strong></p>
            </div>
        </div>
    </body>
    </html>
    """

    return html
