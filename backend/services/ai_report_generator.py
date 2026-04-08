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
from backend.models.soft_delete import alive_filter, get_alive_by_id
from backend.agent.conversation_skills import run_conversation_with_skills
from backend.agent.prompts import DIAGNOSTIC_PROMPT, REPORT_GENERATION_PROMPT
from backend.services.knowledge_router import build_knowledge_context
from backend.utils.datetime_helper import now

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
        yield {"type": "status", "message": "正在初始化诊断会话..."}

        # Load datasource configuration
        datasource_result = await db.execute(select(Datasource).where(Datasource.id == datasource_id, alive_filter(Datasource)))
        datasource = datasource_result.scalar_one_or_none()

        if not datasource:
            yield {"type": "error", "message": "数据源未找到"}
            await _update_report_status(db, report_id, "failed", error_message="Datasource not found")
            return

        # Determine database type and skill prefix
        skill_prefix_map = {
            'mysql': 'mysql',
            'tdsql-c-mysql': 'mysql',
            'postgresql': 'pg',
            'sqlserver': 'mssql',
            'oracle': 'oracle'
        }
        skill_prefix = skill_prefix_map.get(datasource.db_type, datasource.db_type)

        yield {
            "type": "status",
            "message": f"已连接到 {datasource.db_type.upper()} 数据库：{datasource.name}"
        }

        # Phase 2: AI Diagnostic Analysis
        yield {"type": "status", "message": "正在启动 AI 诊断分析..."}

        # Build system prompt for professional DBA report generation
        system_prompt = REPORT_GENERATION_PROMPT

        # Create initial diagnostic message
        initial_message = f"""请为这个 {datasource.db_type.upper()} 数据库生成一份全面的诊断报告。

**数据库信息：**
- 名称：{datasource.name}
- 类型：{datasource.db_type.upper()}
- 主机：{datasource.host}:{datasource.port}
- 报告类型：{report_type}

作为一名资深 DBA，请系统地分析这个数据库，并撰写一份完整的专业诊断报告（markdown 格式）。使用可用的诊断技能收集数据，然后提供你的专家分析和建议。

**必须包含的重点分析（Top SQL / 异常 SQL 专项诊断）：**
1. 调用技能获取慢查询列表或 Top SQL（按总耗时或平均耗时排序，取前 10 条）
2. 对每条重要 SQL 调用技能执行 EXPLAIN 获取执行计划
3. 逐条分析：
   - 执行统计：执行次数、平均/最大耗时、扫描行数 vs 返回行数（行过滤效率）
   - 执行计划问题：全表扫描（type=ALL）、Using filesort、Using temporary、索引失效
   - 根本原因判定：索引缺失/失效、查询设计缺陷、统计信息陈旧、锁竞争等
   - 优化方案：提供可直接执行的 CREATE INDEX DDL 或改写后的 SQL
   - 预期收益：执行时间和扫描行数的预期改善比例
   - 风险提示：大表 DDL 需低峰期执行，建议使用 pt-osc 等工具

请撰写完整的报告 - 这将直接保存为最终的报告文档。**报告必须使用中文撰写。**"""

        messages = [{"role": "user", "content": initial_message}]

        # Collect AI analysis and tool results
        ai_analysis_parts = []
        collected_data = {}

        knowledge_context = await build_knowledge_context(
            db,
            datasource_id=datasource_id,
            user_message=initial_message,
        )

        # Stream AI conversation
        async for event in run_conversation_with_skills(
            messages=messages,
            datasource_id=datasource_id,
            model_id=model_id,
            kb_ids=kb_ids,
            knowledge_context=knowledge_context,
            db=db,
            user_id=user_id,
            session_id=None
        ):
            # Handle error events from conversation
            if event["type"] == "error":
                yield event
                await _update_report_status(db, report_id, "failed", error_message=event.get("message") or event.get("content") or "Unknown error")
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

        # Combine AI-generated report content
        full_report_markdown = "".join(ai_analysis_parts)

        # Phase 3: Rule-Based Validation (for supplementary validation)
        yield {"type": "status", "message": "正在运行补充验证..."}

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

        # Yield each finding for reference
        for finding in rule_based_findings:
            yield {
                "type": "finding",
                "severity": finding["severity"],
                "category": finding["category"],
                "title": finding["title"],
                "detail": finding["detail"],
                "recommendation": finding["recommendation"]
            }

        # Phase 4: Report Finalization
        yield {"type": "status", "message": "正在完成报告..."}

        # Use AI-generated markdown as the report content
        md_content = full_report_markdown

        # Convert markdown to HTML
        html_content = _markdown_to_html(
            markdown_content=full_report_markdown,
            datasource=datasource,
            report_type=report_type
        )

        # Generate summary
        critical_count = sum(1 for f in rule_based_findings if f["severity"] == "CRITICAL")
        warning_count = sum(1 for f in rule_based_findings if f["severity"] == "WARNING")
        info_count = sum(1 for f in rule_based_findings if f["severity"] == "INFO")

        summary = f"已生成专业 DBA 报告。验证发现 {len(rule_based_findings)} 个问题：{critical_count} 个严重，{warning_count} 个警告，{info_count} 个信息。"

        # Update report in database
        final_status = "completed" if full_report_markdown.strip() else "failed"
        final_error = None if final_status == "completed" else "AI 未生成任何有效报告内容。"

        await _update_report_status(
            db=db,
            report_id=report_id,
            status=final_status,
            summary=summary if final_status == "completed" else "报告生成失败，未产出有效内容。",
            content_md=md_content if final_status == "completed" else "",
            content_html=html_content if final_status == "completed" else None,
            findings=rule_based_findings if final_status == "completed" else None,
            ai_analysis=full_report_markdown,
            ai_model_id=model_id,
            kb_ids=kb_ids,
            knowledge_sources=(knowledge_context or {}).get("recommended_documents", [])[:10],
            generation_method="ai",
            error_message=final_error,
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
    report = await get_alive_by_id(db, Report, report_id)

    if report:
        report.status = status
        if status == "generating":
            report.completed_at = None
        else:
            report.completed_at = now()

        for k, v in kwargs.items():
            if hasattr(report, k):
                setattr(report, k, v)

        await db.commit()


def _markdown_to_html(
    markdown_content: str,
    datasource: Datasource,
    report_type: str
) -> str:
    """Convert AI-generated markdown report to styled HTML"""

    # Convert markdown to HTML using markdown-it-py with table support
    md = MarkdownIt("commonmark", {"breaks": True, "html": True})
    md.enable('table')
    content_html = md.render(markdown_content)

    # Wrap in styled HTML document
    html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>数据库诊断报告 - {datasource.name}</title>
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
        {content_html}
        <div class="footer">
            <p>报告由 <strong>DbGuard 智能诊断引擎</strong> 生成</p>
            <p>数据库：{datasource.name} ({datasource.db_type.upper()}) | 类型：{report_type.title()} | 生成时间：{now().strftime('%Y-%m-%d %H:%M')}</p>
        </div>
    </div>
</body>
</html>
"""

    return html
