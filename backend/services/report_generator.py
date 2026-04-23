import logging
import re

from sqlalchemy import select

from backend.models.datasource import Datasource
from backend.models.report import Report
from backend.models.soft_delete import alive_filter
from backend.agent.prompts import REPORT_GENERATION_PROMPT
from backend.agent.conversation_skills import generate_report_with_skills
from backend.utils.datetime_helper import now

logger = logging.getLogger(__name__)

TERMINAL_REPORT_STATUSES = {"completed", "partial", "timed_out", "awaiting_confirm", "failed"}


def _strip_markdown(text: str) -> str:
    if not text:
        return ""
    cleaned = re.sub(r"```[\s\S]*?```", " ", text)
    cleaned = re.sub(r"`([^`]*)`", r"\1", cleaned)
    cleaned = re.sub(r"^#{1,6}\s*", "", cleaned, flags=re.MULTILINE)
    cleaned = re.sub(r"\*\*([^*]+)\*\*", r"\1", cleaned)
    cleaned = re.sub(r"\*([^*]+)\*", r"\1", cleaned)
    cleaned = re.sub(r"\[([^\]]+)\]\([^\)]+\)", r"\1", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned.strip()


def _extract_report_summary(content_md: str) -> str:
    plain = _strip_markdown(content_md)
    if not plain:
        return ""
    return plain[:220].strip()


def _extract_recommended_action(content_md: str) -> str:
    if not content_md:
        return ""
    for raw_line in content_md.splitlines():
        line = raw_line.strip()
        normalized = line.lstrip("-•*1234567890. ")
        if any(keyword in normalized for keyword in ["建议", "处置", "操作", "下一步", "优化"]):
            return _strip_markdown(normalized)[:220]
    return ""


class ReportGenerator:
    """Generate inspection report"""

    def __init__(self, db):
        self.db = db

    async def generate_inspection_report(self, trigger_id: int) -> int:
        """Generate AI-driven inspection report from trigger"""
        from backend.models.inspection_trigger import InspectionTrigger
        from backend.models.inspection_config import InspectionConfig
        from backend.agent.conversation_skills import generate_report_with_skills

        result = await self.db.execute(select(InspectionTrigger).where(InspectionTrigger.id == trigger_id))
        trigger = result.scalar_one()

        result = await self.db.execute(select(Datasource).where(Datasource.id == trigger.datasource_id, alive_filter(Datasource)))
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
        report_id = report.id
        # Persist the initial row so rollback in later steps won't lose the report record.
        await self.db.commit()

        try:
            # Select appropriate system prompt based on trigger type
            if trigger.trigger_type == "connection_failure":
                from backend.agent.prompts import CONNECTION_FAILURE_DIAGNOSIS_PROMPT
                system_prompt = CONNECTION_FAILURE_DIAGNOSIS_PROMPT
            else:
                system_prompt = REPORT_GENERATION_PROMPT

            # Generate AI report (structured result)
            result = await generate_report_with_skills(
                datasource_id=datasource.id,
                datasource_name=datasource.name,
                datasource_type=datasource.db_type,
                trigger_reason=trigger.trigger_reason or "Inspection requested",
                system_prompt=system_prompt,
                db=self.db,
                model_id=config.ai_model_id if config else None,
                timeout_seconds=1800
            )

            report.status = result.get("status") or "failed"
            report.content_md = result.get("content_md") or ""
            report.summary = result.get("summary") or None
            report.error_message = result.get("error_message")
            report.skill_executions = result.get("skill_executions")
            if report.status in TERMINAL_REPORT_STATUSES and report.completed_at is None:
                report.completed_at = now()

            # Generate HTML only when we have content
            if report.content_md:
                try:
                    from markdown_it import MarkdownIt
                    md = MarkdownIt("commonmark", {"breaks": True, "html": True})
                    md.enable('table')
                    content_html_body = md.render(report.content_md)
                except Exception as e:
                    logger.warning(f"Markdown rendering failed, using plain text fallback: {e}")
                    import html as html_module
                    content_html_body = f"<pre>{html_module.escape(report.content_md)}</pre>"

                # Wrap in styled HTML document
                report.content_html = f"""<!DOCTYPE html>
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
            <p>报告由 <strong>DBClaw 智能诊断引擎</strong> 生成</p>
            <p>数据源: {datasource.name} ({datasource.db_type.upper()}) | 生成时间: {now().strftime('%Y-%m-%d %H:%M')}</p>
        </div>
    </div>
</body>
</html>
"""
            else:
                report.content_html = None

        except Exception as e:
            logger.error(f"Error generating inspection report: {e}", exc_info=True)
            # The upstream failure may leave current transaction aborted; rollback first.
            await self.db.rollback()
            result = await self.db.execute(select(Report).where(Report.id == report_id))
            report = result.scalar_one_or_none()
            if report:
                report.status = "failed"
                report.summary = report.summary or "报告生成失败，未产出有效内容。"
                report.content_md = report.content_md or ""
                report.content_html = report.content_html if report.content_html else None
                report.error_message = str(e)
                report.skill_executions = report.skill_executions or []
                if report.completed_at is None:
                    report.completed_at = now()
                await self.db.commit()
            else:
                raise

        return report_id
