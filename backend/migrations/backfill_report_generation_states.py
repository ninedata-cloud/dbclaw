"""Backfill historical report generation states for empty/invalid completed report."""

import asyncio
import logging
import re
from sqlalchemy import text
from backend.database import engine

logger = logging.getLogger(__name__)


def _strip_markdown(text_value: str) -> str:
    if not text_value:
        return ""
    cleaned = re.sub(r"```[\s\S]*?```", " ", text_value)
    cleaned = re.sub(r"`([^`]*)`", r"\1", cleaned)
    cleaned = re.sub(r"^#{1,6}\s*", "", cleaned, flags=re.MULTILINE)
    cleaned = re.sub(r"\*\*([^*]+)\*\*", r"\1", cleaned)
    cleaned = re.sub(r"\*([^*]+)\*", r"\1", cleaned)
    cleaned = re.sub(r"\[([^\]]+)\]\([^\)]+\)", r"\1", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned.strip()


def _extract_summary(text_value: str) -> str:
    plain = _strip_markdown(text_value)
    return plain[:220].strip() if plain else ""


def _is_error_like_content(text_value: str) -> bool:
    plain = _strip_markdown(text_value)
    if not plain:
        return False
    lower_plain = plain.lower()
    return (
        plain.startswith("⚠️")
        or "未生成任何内容" in plain
        or "报告生成失败" in plain
        or "报告生成超时" in plain
        or "需要人工确认" in plain
        or ("timeout" in lower_plain and len(plain) < 160)
    )


async def migrate():
    async with engine.begin() as conn:
        result = await conn.execute(text(
            "SELECT id, status, summary, content_md, error_message, created_at, completed_at "
            "FROM report"
        ))
        rows = result.mappings().all()

        fixed_count = 0
        review_candidates = []

        for row in rows:
            report_id = row["id"]
            status = row["status"]
            summary = row["summary"]
            content_md = row["content_md"] or ""
            error_message = row["error_message"]
            completed_at = row["completed_at"]
            created_at = row["created_at"]

            plain = _strip_markdown(content_md)
            has_content = bool(plain)
            is_error_like = _is_error_like_content(content_md)

            new_status = status
            new_summary = summary
            new_content_md = content_md
            new_error_message = error_message
            changed = False

            if status == "completed" and not has_content:
                timeout_hint = (error_message or "").lower()
                new_status = "timed_out" if ("timeout" in timeout_hint or "超时" in (error_message or "")) else "failed"
                new_summary = "报告生成失败，未产出有效内容。"
                new_error_message = error_message or "Historical backfill: completed without content"
                new_content_md = ""
                changed = True
            elif status == "completed" and error_message:
                if has_content and not is_error_like:
                    new_status = "partial"
                    new_summary = summary or _extract_summary(content_md) or "报告生成部分成功"
                    changed = True
                else:
                    timeout_hint = error_message.lower()
                    new_status = "timed_out" if ("timeout" in timeout_hint or "超时" in error_message) else "failed"
                    new_summary = "报告生成失败，未产出有效内容。"
                    new_content_md = ""
                    changed = True
            elif status == "failed" and has_content and is_error_like:
                new_error_message = error_message or plain
                new_content_md = ""
                new_summary = summary or "报告生成失败，未产出有效内容。"
                changed = True
            elif not summary and has_content and not is_error_like:
                new_summary = _extract_summary(content_md)
                changed = True

            if status == "failed" and has_content and not is_error_like and len(plain) >= 200:
                review_candidates.append(report_id)

            if changed or (status != "generating" and completed_at is None):
                await conn.execute(
                    text(
                        "UPDATE report SET status=:status, summary=:summary, content_md=:content_md, "
                        "error_message=:error_message, completed_at=COALESCE(completed_at, :completed_at) "
                        "WHERE id=:id"
                    ),
                    {
                        "id": report_id,
                        "status": new_status,
                        "summary": new_summary,
                        "content_md": new_content_md,
                        "error_message": new_error_message,
                        "completed_at": created_at,
                    }
                )
                fixed_count += 1

        logger.info("Backfill complete: updated %s report", fixed_count)
        if review_candidates:
            logger.info("Manual review candidates: %s", ", ".join(str(item) for item in review_candidates[:100]))


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(migrate())
