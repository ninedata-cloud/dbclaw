import asyncio
from copy import deepcopy
import json
import logging
import re
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any, AsyncGenerator, Awaitable, Callable, Optional

from sqlalchemy import desc, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.agent.skill_authorization import normalize_skill_authorizations
from backend.agent.conversation_skills import execute_skill_call, run_conversation_with_skills
from backend.agent.intent_detector import analyze_query_intent
from backend.models.diagnosis_conclusion import DiagnosisConclusion
from backend.models.diagnosis_event import DiagnosisEvent
from backend.models.diagnostic_session import ChatMessage, DiagnosticSession
from backend.models.soft_delete import alive_filter, alive_select
from backend.services.knowledge_router import build_knowledge_context
from backend.utils.json_sanitizer import sanitize_for_json
from backend.utils.datetime_helper import now as local_now

logger = logging.getLogger(__name__)

PendingApprovalsStore = dict[int, dict[str, dict[str, Any]]]
EventCallback = Optional[Callable[[dict[str, Any]], Awaitable[None]]]
TRACKED_DIAGNOSIS_EVENTS = {
    "thinking_phase",
    "thinking_complete",
    "diagnosis_state",
    "plan_created",
    "knowledge_plan_created",
    "knowledge_unit_activated",
    "knowledge_replanned",
    "plan_step_status",
    "tool_call",
    "tool_result",
    "kb_document_selected",
    "kb_document_read",
    "approval_request",
    "diagnosis_conclusion",
}

ASSISTANT_STATUS_COMPLETE = "complete"
ASSISTANT_STATUS_AWAITING_APPROVAL = "awaiting_approval"
ASSISTANT_STATUS_CANCELLED = "cancelled"
ASSISTANT_STATUS_ERROR = "error"
ASSISTANT_STATUS_PARTIAL = "partial"

RENDER_SEGMENT_MARKDOWN = "markdown"
RENDER_SEGMENT_TOOL = "tool"
RENDER_SEGMENT_UNSET = object()


def clone_render_segments(segments: Any) -> list[dict[str, Any]]:
    if not isinstance(segments, list):
        return []
    return deepcopy(segments)


def _new_markdown_segment(content: str = "") -> dict[str, Any]:
    return {
        "id": f"seg_{uuid.uuid4().hex}",
        "type": RENDER_SEGMENT_MARKDOWN,
        "content": content,
    }


def _build_tool_segment_metadata(
    metadata: dict[str, Any] | None = None,
    *,
    skill_execution_id: Any = None,
    action_run_id: Any = None,
    action_title: Any = None,
    phase: Any = None,
    approval_id: Any = None,
    approval_status: Any = None,
    risk_level: Any = None,
    risk_reason: Any = None,
) -> dict[str, Any] | None:
    merged = dict(metadata or {})
    if skill_execution_id is not None:
        merged["skill_execution_id"] = skill_execution_id
    if action_run_id is not None:
        merged["action_run_id"] = action_run_id
    if action_title is not None:
        merged["action_title"] = action_title
    if phase is not None:
        merged["phase"] = phase
    if approval_id is not None:
        merged["approval_id"] = approval_id
    if approval_status is not None:
        merged["approval_status"] = approval_status
    if risk_level is not None:
        merged["risk_level"] = risk_level
    if risk_reason is not None:
        merged["risk_reason"] = risk_reason
    return merged or None


def _find_tool_segment(
    render_segments: list[dict[str, Any]],
    tool_call_id: str | None,
) -> dict[str, Any] | None:
    if not tool_call_id:
        return None
    for segment in render_segments:
        if (
            isinstance(segment, dict)
            and segment.get("type") == RENDER_SEGMENT_TOOL
            and segment.get("tool_call_id") == tool_call_id
        ):
            return segment
    return None


def append_markdown_render_segment(
    render_segments: list[dict[str, Any]] | None,
    content: str | None,
) -> list[dict[str, Any]]:
    segments = render_segments if isinstance(render_segments, list) else []
    text = str(content or "")
    if not text:
        return segments

    last_segment = segments[-1] if segments else None
    if isinstance(last_segment, dict) and last_segment.get("type") == RENDER_SEGMENT_MARKDOWN:
        last_segment["content"] = f"{last_segment.get('content') or ''}{text}"
    else:
        segments.append(_new_markdown_segment(text))
    return segments


def _parse_tool_result_summary(result: Any) -> tuple[str, str]:
    parsed = result
    if isinstance(result, str):
        try:
            parsed = json.loads(result)
        except Exception:
            parsed = result

    is_error = isinstance(parsed, dict) and (parsed.get("success") is False or parsed.get("error"))
    status = "failed" if is_error else "completed"
    fallback = "执行失败" if is_error else "执行完成"
    summary = _summarize_value(parsed) or fallback
    return status, summary


def upsert_tool_render_segment(
    render_segments: list[dict[str, Any]] | None,
    *,
    tool_call_id: str | None,
    tool_name: str | None = None,
    status: str | None = None,
    args: Any = RENDER_SEGMENT_UNSET,
    result: Any = RENDER_SEGMENT_UNSET,
    execution_time_ms: Any = RENDER_SEGMENT_UNSET,
    summary: Any = RENDER_SEGMENT_UNSET,
    metadata: dict[str, Any] | None = None,
    visualization: Any = RENDER_SEGMENT_UNSET,
) -> list[dict[str, Any]]:
    segments = render_segments if isinstance(render_segments, list) else []
    segment = _find_tool_segment(segments, tool_call_id)
    if segment is None:
        segment = {
            "id": tool_call_id or f"tool_{uuid.uuid4().hex}",
            "type": RENDER_SEGMENT_TOOL,
            "tool_call_id": tool_call_id,
            "tool_name": tool_name or "工具",
            "status": status or "running",
        }
        segments.append(segment)

    if tool_name:
        segment["tool_name"] = tool_name
    if status:
        segment["status"] = status
    if args is not RENDER_SEGMENT_UNSET:
        if args is None:
            segment.pop("args", None)
        else:
            segment["args"] = args
    if result is not RENDER_SEGMENT_UNSET:
        if result is None:
            segment.pop("result", None)
        else:
            segment["result"] = result
    if execution_time_ms is not RENDER_SEGMENT_UNSET:
        if execution_time_ms is None:
            segment.pop("execution_time_ms", None)
        else:
            segment["execution_time_ms"] = execution_time_ms
    if summary is not RENDER_SEGMENT_UNSET:
        if summary:
            segment["summary"] = summary
        else:
            segment.pop("summary", None)
    if metadata:
        segment["metadata"] = {
            **(segment.get("metadata") or {}),
            **metadata,
        }
    if visualization is not RENDER_SEGMENT_UNSET:
        if visualization is None:
            segment.pop("visualization", None)
        else:
            segment["visualization"] = visualization

    return segments


def apply_render_segments_event(
    render_segments: list[dict[str, Any]] | None,
    event: dict[str, Any],
) -> list[dict[str, Any]]:
    segments = clone_render_segments(render_segments)
    event_type = event.get("type")

    if event_type == "content":
        return append_markdown_render_segment(segments, event.get("content"))

    if event_type == "tool_call":
        return upsert_tool_render_segment(
            segments,
            tool_call_id=event.get("tool_call_id"),
            tool_name=event.get("tool_name"),
            status="running",
            args=event.get("tool_args"),
            summary="已发起调用，等待返回结果",
            metadata=_build_tool_segment_metadata(
                action_run_id=event.get("action_run_id"),
                action_title=event.get("action_title"),
                phase=event.get("phase"),
            ),
        )

    if event_type == "tool_result":
        inferred_status, inferred_summary = _parse_tool_result_summary(event.get("result"))
        return upsert_tool_render_segment(
            segments,
            tool_call_id=event.get("tool_call_id"),
            tool_name=event.get("tool_name"),
            status=inferred_status,
            result=event.get("result"),
            execution_time_ms=event.get("execution_time_ms"),
            summary=inferred_summary,
            metadata=_build_tool_segment_metadata(
                skill_execution_id=event.get("skill_execution_id"),
                action_run_id=event.get("action_run_id"),
                action_title=event.get("action_title"),
                phase=event.get("phase"),
            ),
            visualization=event.get("visualization"),
        )

    if event_type == "approval_request":
        return upsert_tool_render_segment(
            segments,
            tool_call_id=event.get("tool_call_id"),
            tool_name=event.get("tool_name"),
            status="waiting_approval",
            args=event.get("tool_args"),
            summary=event.get("summary"),
            metadata=_build_tool_segment_metadata(
                action_run_id=event.get("action_run_id"),
                action_title=event.get("action_title"),
                phase=event.get("phase"),
                approval_id=event.get("approval_id"),
                approval_status="pending",
                risk_level=event.get("risk_level"),
                risk_reason=event.get("risk_reason"),
            ),
        )

    if event_type == "confirmation_resolved":
        action = str(event.get("action") or "").strip().lower()
        if action == "approved":
            status = "running"
            approval_status = "approved"
            summary = "已批准，正在执行..."
        elif action == "rejected":
            status = "failed"
            approval_status = "rejected"
            summary = "用户已拒绝执行"
        else:
            status = None
            approval_status = action or None
            summary = None

        return upsert_tool_render_segment(
            segments,
            tool_call_id=event.get("tool_call_id"),
            tool_name=event.get("tool_name"),
            status=status,
            summary=summary,
            metadata=_build_tool_segment_metadata(
                approval_id=event.get("approval_id"),
                approval_status=approval_status,
                action_run_id=event.get("action_run_id"),
                action_title=event.get("action_title"),
                phase=event.get("phase"),
            ),
        )

    return segments


async def rebuild_llm_messages(all_msgs):
    messages = []
    from backend.utils.attachment_handler import AttachmentHandler

    for m in all_msgs:
        if m.role == "tool_call":
            try:
                data = json.loads(m.content)
                tool_call_id = data.get("tool_call_id") or m.tool_call_id or f"call_{data['tool_name']}_{m.id}"
                messages.append({
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [{
                        "id": tool_call_id,
                        "type": "function",
                        "function": {
                            "name": data["tool_name"],
                            "arguments": json.dumps(data["tool_args"])
                        }
                    }]
                })
            except Exception as e:
                logger.error(f"Error parsing tool_call message: {e}")
            continue
        if m.role == "tool_result":
            try:
                data = json.loads(m.content)
                tool_call_id = data.get("tool_call_id") or m.tool_call_id or f"call_{data['tool_name']}_{m.id - 1}"
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call_id,
                    "content": data["result"]
                })
            except Exception as e:
                logger.error(f"Error parsing tool_result message: {e}")
            continue
        if m.role in {"approval_request", "approval_response"}:
            continue

        if m.attachments:
            content_parts = []
            if m.content and m.content != "[Attachment]":
                content_parts.append({"type": "text", "text": m.content})

            for att in m.attachments:
                try:
                    att_content = await AttachmentHandler.format_attachment_for_llm(att)
                    content_parts.append(att_content)
                except Exception as e:
                    logger.error(f"Error processing attachment: {e}")
                    content_parts.append({
                        "type": "text",
                        "text": f"[Error loading attachment: {att.get('filename', 'unknown')}]"
                    })

            msg_dict = {"role": m.role, "content": content_parts}
        else:
            msg_dict = {"role": m.role, "content": m.content}

        if m.tool_calls:
            msg_dict["tool_calls"] = m.tool_calls
        if m.tool_call_id:
            msg_dict["tool_call_id"] = m.tool_call_id
        messages.append(msg_dict)

    return messages


async def load_session_messages_for_llm(
    db: AsyncSession,
    *,
    session_id: int,
    history_window_hours: int | None = None,
):
    query = (
        alive_select(ChatMessage)
        .where(ChatMessage.session_id == session_id)
        .order_by(ChatMessage.id)
    )
    if history_window_hours is not None:
        cutoff = local_now() - timedelta(hours=history_window_hours)
        query = query.where(ChatMessage.created_at >= cutoff)

    result = await db.execute(query)
    all_msgs = result.scalars().all()

    # Keep a Python-side safety filter so tests and non-standard DB responses stay consistent.
    if history_window_hours is not None:
        cutoff = local_now() - timedelta(hours=history_window_hours)
        all_msgs = [
            msg for msg in all_msgs
            if not getattr(msg, "created_at", None) or msg.created_at >= cutoff
        ]

    return all_msgs


async def _emit(event: dict[str, Any], on_event: EventCallback = None):
    if on_event:
        try:
            await on_event(event)
        except Exception:
            pass  # WebSocket may be disconnected; task continues in background


def _summarize_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        stripped = value.strip()
        return stripped[:240]
    if isinstance(value, list):
        return f"返回 {len(value)} 条记录"
    if isinstance(value, dict):
        if value.get("error"):
            return str(value["error"])[:240]
        if value.get("message"):
            return str(value["message"])[:240]
        parts = []
        for key, item in list(value.items())[:3]:
            rendered = item if isinstance(item, (str, int, float, bool)) else json.dumps(item, ensure_ascii=False)[:60]
            parts.append(f"{key}={rendered}")
        return "，".join(parts)[:240]
    return str(value)[:240]


def _build_diagnosis_event_payload(event_type: str, event: dict[str, Any]) -> dict[str, Any]:
    if event_type == "tool_call":
        return {
            "tool_name": event.get("tool_name"),
            "tool_call_id": event.get("tool_call_id"),
            "summary": f"调用 {event.get('tool_name')}",
        }
    if event_type == "tool_result":
        raw_result = event.get("result")
        parsed = raw_result
        if isinstance(raw_result, str):
            try:
                parsed = json.loads(raw_result)
            except Exception:
                parsed = raw_result
        return {
            "tool_name": event.get("tool_name"),
            "tool_call_id": event.get("tool_call_id"),
            "execution_time_ms": event.get("execution_time_ms"),
            "skill_execution_id": event.get("skill_execution_id"),
            "summary": _summarize_value(parsed),
            "success": not (isinstance(parsed, dict) and parsed.get("error")),
        }
    if event_type == "plan_step_status":
        return {
            "tool_name": event.get("tool_name"),
            "status": event.get("status"),
            "title": event.get("title"),
            "summary": event.get("summary"),
            "error": event.get("error"),
        }
    if event_type == "diagnosis_conclusion":
        return {
            "summary": event.get("summary"),
            "confidence": event.get("confidence"),
            "findings": event.get("findings", [])[:5],
            "action_items": event.get("action_items", [])[:5],
        }
    return {
        key: value
        for key, value in event.items()
        if key not in {"type", "content", "result"}
    }


async def _load_assistant_message_by_run_id(
    db: AsyncSession,
    *,
    session_id: int,
    run_id: str,
) -> ChatMessage | None:
    result = await db.execute(
        alive_select(ChatMessage)
        .where(
            ChatMessage.session_id == session_id,
            ChatMessage.role == "assistant",
            ChatMessage.run_id == run_id,
        )
        .order_by(ChatMessage.id.desc())
    )
    return result.scalars().first()


async def _persist_assistant_message(
    db: AsyncSession,
    *,
    session_id: int,
    run_id: str,
    content: str,
    render_segments: list[dict[str, Any]] | None,
    status: str,
    usage_totals: dict[str, int] | None = None,
) -> ChatMessage:
    assistant_msg = await _load_assistant_message_by_run_id(
        db,
        session_id=session_id,
        run_id=run_id,
    )
    if assistant_msg is None:
        assistant_msg = ChatMessage(
            session_id=session_id,
            role="assistant",
            content=content,
            run_id=run_id,
            render_segments=clone_render_segments(render_segments),
            status=status,
        )
        if usage_totals:
            assistant_msg.input_tokens = int(usage_totals.get("input_tokens") or 0)
            assistant_msg.output_tokens = int(usage_totals.get("output_tokens") or 0)
            assistant_msg.total_tokens = int(usage_totals.get("total_tokens") or 0)
        db.add(assistant_msg)
        await db.commit()
        await db.refresh(assistant_msg)
        return assistant_msg

    assistant_msg.content = content
    assistant_msg.render_segments = clone_render_segments(render_segments)
    assistant_msg.status = status
    if usage_totals:
        assistant_msg.input_tokens = int(usage_totals.get("input_tokens") or 0)
        assistant_msg.output_tokens = int(usage_totals.get("output_tokens") or 0)
        assistant_msg.total_tokens = int(usage_totals.get("total_tokens") or 0)
    await db.commit()
    return assistant_msg


async def _apply_assistant_event_to_run(
    db: AsyncSession,
    *,
    session_id: int,
    run_id: str | None,
    event: dict[str, Any],
    status: str = ASSISTANT_STATUS_PARTIAL,
) -> ChatMessage | None:
    if not run_id:
        return None

    assistant_msg = await _load_assistant_message_by_run_id(
        db,
        session_id=session_id,
        run_id=run_id,
    )
    if assistant_msg is None:
        return None

    render_segments = apply_render_segments_event(
        assistant_msg.render_segments,
        event,
    )
    return await _persist_assistant_message(
        db,
        session_id=session_id,
        run_id=run_id,
        content=assistant_msg.content or "",
        render_segments=render_segments,
        status=status,
    )


async def _store_diagnosis_event(
    db: AsyncSession,
    *,
    session_id: int,
    run_id: str,
    sequence_no: int,
    event_type: str,
    payload: dict[str, Any],
    step_id: str | None = None,
) -> None:
    event_row = DiagnosisEvent(
        session_id=session_id,
        run_id=run_id,
        event_type=event_type,
        sequence_no=sequence_no,
        step_id=step_id,
        payload=sanitize_for_json(payload),
    )
    db.add(event_row)
    try:
        await db.commit()
    except SQLAlchemyError as exc:
        await db.rollback()
        logger.warning(
            "Skip diagnosis_event persistence due to DB schema mismatch or write error: %s",
            exc,
        )


async def _store_tool_call(db: AsyncSession, session_id: int, event: dict[str, Any]) -> None:
    tool_msg = ChatMessage(
        session_id=session_id,
        role="tool_call",
        run_id=event.get("run_id"),
        content=json.dumps({
            "tool_name": event["tool_name"],
            "tool_args": event["tool_args"],
            "tool_call_id": event.get("tool_call_id"),
        }),
        tool_calls=[{
            "name": event["tool_name"],
            "arguments": event["tool_args"],
        }],
        tool_call_id=event.get("tool_call_id"),
    )
    db.add(tool_msg)
    await db.commit()


async def _store_tool_result(db: AsyncSession, session_id: int, event: dict[str, Any]) -> None:
    result_msg = ChatMessage(
        session_id=session_id,
        role="tool_result",
        run_id=event.get("run_id"),
        content=json.dumps({
            "tool_name": event["tool_name"],
            "result": event["result"],
            "execution_time_ms": event.get("execution_time_ms"),
            "tool_call_id": event.get("tool_call_id"),
            "skill_execution_id": event.get("skill_execution_id"),
            "action_run_id": event.get("action_run_id"),
            "action_title": event.get("action_title"),
            "phase": event.get("phase"),
            "visualization": event.get("visualization"),
        }),
        tool_call_id=event.get("tool_call_id"),
    )
    db.add(result_msg)
    await db.commit()


async def _store_approval_request(
    db: AsyncSession,
    session_id: int,
    event: dict[str, Any],
    pending_approvals: PendingApprovalsStore,
    datasource_id: int | None,
    model_id: int | None,
    kb_ids,
    knowledge_context,
    skill_authorizations,
    user_id: int | None,
    history_window_hours: int | None,
) -> None:
    approval_id = event["approval_id"]
    pending_approvals.setdefault(session_id, {})[approval_id] = {
        "approval_id": approval_id,
        "run_id": event.get("run_id"),
        "tool_name": event["tool_name"],
        "tool_args": event["tool_args"],
        "tool_call_id": event.get("tool_call_id"),
        "datasource_id": datasource_id,
        "model_id": model_id,
        "kb_ids": kb_ids,
        "knowledge_context": knowledge_context,
        "skill_authorizations": skill_authorizations,
        "user_id": user_id,
        "history_window_hours": history_window_hours,
        "risk_level": event.get("risk_level", "high"),
        "risk_reason": event.get("risk_reason"),
        "suppressible": event.get("suppressible", False),
        "confirmation_key": event.get("confirmation_key"),
        "action_run_id": event.get("action_run_id"),
        "recommendation_id": event.get("recommendation_id"),
        "action_title": event.get("action_title"),
        "phase": event.get("phase"),
    }
    approval_msg = ChatMessage(
        session_id=session_id,
        role="approval_request",
        run_id=event.get("run_id"),
        content=json.dumps({
            "approval_id": approval_id,
            "tool_name": event["tool_name"],
            "tool_args": event["tool_args"],
            "tool_call_id": event.get("tool_call_id"),
            "summary": event.get("summary"),
            "plan_markdown": event.get("plan_markdown"),
            "history_window_hours": history_window_hours,
            "risk_level": event.get("risk_level", "high"),
            "risk_reason": event.get("risk_reason"),
            "suppressible": event.get("suppressible", False),
            "confirmation_key": event.get("confirmation_key"),
            "status": "pending",
            "action_run_id": event.get("action_run_id"),
            "recommendation_id": event.get("recommendation_id"),
            "action_title": event.get("action_title"),
            "phase": event.get("phase"),
            "run_id": event.get("run_id"),
        }),
    )
    db.add(approval_msg)
    await db.commit()


async def _load_pending_approval_from_db(
    db: AsyncSession,
    *,
    session_id: int,
    approval_id: str,
    user_id: int | None,
) -> dict[str, Any] | None:
    result = await db.execute(
        alive_select(ChatMessage)
        .where(
            ChatMessage.session_id == session_id,
            ChatMessage.role == "approval_request",
            ChatMessage.content.contains(approval_id),
        )
        .order_by(ChatMessage.created_at.desc())
    )
    approval_msg = result.scalars().first()
    if not approval_msg:
        return None

    try:
        data = json.loads(approval_msg.content)
    except Exception:
        logger.exception("Failed to parse approval_request content for session=%s approval_id=%s", session_id, approval_id)
        return None

    if data.get("status") not in {None, "pending"}:
        return None

    session_result = await db.execute(
        alive_select(DiagnosticSession).where(DiagnosticSession.id == session_id)
    )
    session = session_result.scalar_one_or_none()

    return {
        "approval_id": approval_id,
        "run_id": data.get("run_id"),
        "tool_name": data.get("tool_name"),
        "tool_args": data.get("tool_args") or {},
        "tool_call_id": data.get("tool_call_id"),
        "datasource_id": session.datasource_id if session else None,
        "model_id": session.ai_model_id if session else None,
        "kb_ids": session.kb_ids if session else None,
        "knowledge_context": session.knowledge_snapshot if session else None,
        "skill_authorizations": normalize_skill_authorizations(
            getattr(session, "skill_authorizations", None) if session else None,
            getattr(session, "disabled_tools", None) if session else None,
        ),
        "user_id": user_id,
        "history_window_hours": data.get("history_window_hours"),
        "risk_level": data.get("risk_level", "high"),
        "risk_reason": data.get("risk_reason"),
        "suppressible": data.get("suppressible", False),
        "confirmation_key": data.get("confirmation_key"),
        "action_run_id": data.get("action_run_id"),
        "recommendation_id": data.get("recommendation_id"),
        "action_title": data.get("action_title"),
        "phase": data.get("phase"),
    }


async def _accumulate_usage(db: AsyncSession, session_id: int, user_id: int | None, usage: dict[str, Any]) -> None:
    query = alive_select(DiagnosticSession).where(DiagnosticSession.id == session_id)
    if user_id is not None:
        query = query.where(DiagnosticSession.user_id == user_id)
    session_result = await db.execute(query)
    session = session_result.scalar_one_or_none()
    if session:
        session.input_tokens += int(usage.get("input_tokens") or 0)
        session.output_tokens += int(usage.get("output_tokens") or 0)
        session.total_tokens += int(usage.get("total_tokens") or 0)
        session.updated_at = local_now()
        await db.commit()


def _strip_markdown_text(text: str) -> str:
    if not text:
        return ""
    text = re.sub(r"```[\s\S]*?```", " ", text)
    text = re.sub(r"`([^`]*)`", r"\1", text)
    text = re.sub(r"^#{1,6}\s*", "", text, flags=re.MULTILINE)
    text = re.sub(r"\*\*([^*]+)\*\*", r"\1", text)
    text = re.sub(r"\*([^*]+)\*", r"\1", text)
    text = re.sub(r"\[([^\]]+)\]\([^\)]+\)", r"\1", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _extract_section_lines(content: str, heading_keywords: list[str]) -> list[str]:
    lines = [line.rstrip() for line in (content or "").splitlines()]
    captured: list[str] = []
    in_section = False
    for line in lines:
        plain = _strip_markdown_text(line)
        if not plain:
            if in_section and captured:
                break
            continue
        is_heading = line.lstrip().startswith("#") or plain.endswith("：") or plain.endswith(":")
        if any(keyword in plain for keyword in heading_keywords) and is_heading:
            in_section = True
            continue
        if in_section and is_heading and captured:
            break
        if in_section:
            captured.append(plain.lstrip("-•*1234567890. ").strip())
    return [line for line in captured if line]


async def _upsert_diagnosis_conclusion(
    db: AsyncSession,
    *,
    session_id: int,
    user_id: int | None,
    run_id: str | None,
    content: str,
) -> dict[str, Any] | None:
    plain = _strip_markdown_text(content)
    if not plain:
        return None

    session_query = alive_select(DiagnosticSession).where(DiagnosticSession.id == session_id)
    if user_id is not None:
        session_query = session_query.where(DiagnosticSession.user_id == user_id)
    session_result = await db.execute(session_query)
    session = session_result.scalar_one_or_none()
    if not session:
        return None

    summary = plain[:220]
    findings = _extract_section_lines(content, ["问题判断", "结论", "诊断结论", "根因", "现象"])
    action_items = _extract_section_lines(content, ["建议动作", "建议", "处理建议", "行动建议", "下一步"])
    evidence_lines = _extract_section_lines(content, ["关键证据", "证据", "依据"])
    risk_lines = _extract_section_lines(content, ["风险提示", "风险", "注意事项"])

    evidence_refs = [{"type": "text", "detail": line} for line in evidence_lines[:10]]
    if risk_lines:
        evidence_refs.extend({"type": "risk", "detail": line} for line in risk_lines[:10])

    knowledge_refs: list[dict[str, Any]] = []
    if run_id:
        event_result = await db.execute(
            alive_select(DiagnosisEvent)
            .where(
                DiagnosisEvent.session_id == session_id,
                DiagnosisEvent.run_id == run_id,
                DiagnosisEvent.event_type.in_(["kb_document_selected", "kb_document_read", "knowledge_unit_activated"]),
            )
            .order_by(DiagnosisEvent.sequence_no)
        )
        seen_refs: set[tuple[Any, Any]] = set()
        for event in event_result.scalars().all():
            payload = event.payload or {}
            key = (
                payload.get("document_id"),
                payload.get("citation") or payload.get("title") or payload.get("document_title"),
            )
            if key in seen_refs:
                continue
            seen_refs.add(key)
            knowledge_refs.append({
                "document_id": payload.get("document_id"),
                "title": payload.get("citation") or payload.get("title") or payload.get("document_title") or "未命名文档",
                "reason": payload.get("reason"),
                "scope": payload.get("scope"),
                "document_kind": payload.get("document_kind"),
                "node_title": payload.get("node_title"),
            })

    result = await db.execute(
        select(DiagnosisConclusion)
        .where(DiagnosisConclusion.session_id == session_id)
        .order_by(DiagnosisConclusion.created_at.desc(), DiagnosisConclusion.id.desc())
    )
    conclusion = result.scalars().first()
    if conclusion is None:
        conclusion = DiagnosisConclusion(session_id=session_id)
        db.add(conclusion)

    conclusion.datasource_id = session.datasource_id
    conclusion.run_id = run_id
    conclusion.summary = summary
    conclusion.confidence = 0.8
    conclusion.final_markdown = content
    conclusion.findings = [{"description": item} for item in findings[:10]] if findings else []
    conclusion.action_items = [{"title": item, "priority": "medium", "description": item} for item in action_items[:10]] if action_items else []
    conclusion.evidence_refs = evidence_refs
    conclusion.knowledge_refs = knowledge_refs
    conclusion.updated_at = local_now()
    await db.commit()
    await db.refresh(conclusion)

    return {
        "id": conclusion.id,
        "session_id": conclusion.session_id,
        "datasource_id": conclusion.datasource_id,
        "run_id": conclusion.run_id,
        "summary": conclusion.summary,
        "confidence": conclusion.confidence,
        "final_markdown": conclusion.final_markdown,
        "findings": conclusion.findings or [],
        "action_items": conclusion.action_items or [],
        "evidence_refs": conclusion.evidence_refs or [],
        "knowledge_refs": conclusion.knowledge_refs or [],
        "created_at": conclusion.created_at.isoformat() if conclusion.created_at else None,
        "updated_at": conclusion.updated_at.isoformat() if conclusion.updated_at else None,
    }


def _serialize_diagnosis_event(event: DiagnosisEvent) -> dict[str, Any]:
    return {
        "id": event.id,
        "run_id": event.run_id,
        "event_type": event.event_type,
        "sequence_no": event.sequence_no,
        "step_id": event.step_id,
        "payload": event.payload or {},
        "created_at": event.created_at.isoformat() if event.created_at else None,
    }


async def get_session_insights(
    db: AsyncSession,
    *,
    session_id: int,
    user_id: int | None,
) -> dict[str, Any]:
    session_query = alive_select(DiagnosticSession).where(DiagnosticSession.id == session_id)
    if user_id is not None:
        session_query = session_query.where(DiagnosticSession.user_id == user_id)
    session_result = await db.execute(session_query)
    session = session_result.scalar_one_or_none()
    if not session:
        raise ValueError("会话不存在")

    conclusion_query = (
        select(DiagnosisConclusion)
        .where(DiagnosisConclusion.session_id == session_id)
        .order_by(desc(DiagnosisConclusion.updated_at), desc(DiagnosisConclusion.id))
    )
    conclusion_result = await db.execute(conclusion_query)
    latest_conclusion = conclusion_result.scalars().first()

    latest_event_query = (
        alive_select(DiagnosisEvent)
        .where(DiagnosisEvent.session_id == session_id)
        .order_by(DiagnosisEvent.created_at.desc(), DiagnosisEvent.id.desc())
    )
    latest_event_result = await db.execute(latest_event_query)
    latest_event = latest_event_result.scalars().first()

    run_id = None
    if latest_conclusion and latest_conclusion.run_id:
        run_id = latest_conclusion.run_id
    elif latest_event:
        run_id = latest_event.run_id

    events: list[DiagnosisEvent] = []
    if run_id:
        events_result = await db.execute(
            alive_select(DiagnosisEvent)
            .where(DiagnosisEvent.session_id == session_id, DiagnosisEvent.run_id == run_id)
            .order_by(DiagnosisEvent.sequence_no.asc(), DiagnosisEvent.id.asc())
        )
        events = events_result.scalars().all()

    latest_state = next((event.payload for event in reversed(events) if event.event_type == "diagnosis_state"), None)
    latest_plan = next(
        (
            event.payload
            for event in reversed(events)
            if event.event_type in {"knowledge_plan_created", "knowledge_replanned", "plan_created"}
        ),
        None,
    )
    knowledge_refs = []
    if latest_conclusion and latest_conclusion.knowledge_refs:
        knowledge_refs.extend(latest_conclusion.knowledge_refs)
    for event in events:
        if event.event_type in {"kb_document_selected", "kb_document_read", "knowledge_unit_activated"}:
            payload = event.payload or {}
            knowledge_refs.append({
                "document_id": payload.get("document_id"),
                "title": payload.get("citation") or payload.get("title") or payload.get("document_title"),
                "reason": payload.get("reason"),
                "scope": payload.get("scope"),
                "document_kind": payload.get("document_kind"),
                "node_title": payload.get("node_title"),
            })

    seen_refs: set[tuple[Any, Any]] = set()
    deduped_knowledge_refs = []
    for ref in knowledge_refs:
        key = (ref.get("document_id"), ref.get("title"))
        if key in seen_refs:
            continue
        seen_refs.add(key)
        deduped_knowledge_refs.append(ref)

    evidence = []
    if latest_conclusion and latest_conclusion.evidence_refs:
        evidence.extend(latest_conclusion.evidence_refs)
    elif latest_state and latest_state.get("abnormal_signals"):
        evidence.extend({
            "type": "signal",
            "detail": f"{signal.get('label')}: {signal.get('value')} ({signal.get('reason')})",
        } for signal in latest_state.get("abnormal_signals", [])[:8])

    return {
        "session_id": session_id,
        "run_id": run_id,
        "latest_state": latest_state,
        "latest_plan": latest_plan,
        "latest_conclusion": {
            "id": latest_conclusion.id,
            "summary": latest_conclusion.summary,
            "confidence": latest_conclusion.confidence,
            "final_markdown": latest_conclusion.final_markdown,
            "findings": latest_conclusion.findings or [],
            "action_items": latest_conclusion.action_items or [],
            "evidence_refs": latest_conclusion.evidence_refs or [],
            "knowledge_refs": latest_conclusion.knowledge_refs or [],
            "updated_at": latest_conclusion.updated_at.isoformat() if latest_conclusion and latest_conclusion.updated_at else None,
        } if latest_conclusion else None,
        "knowledge_refs": deduped_knowledge_refs[:10],
        "evidence": evidence[:10],
        "recent_events": [_serialize_diagnosis_event(event) for event in events[-30:]],
    }


async def process_stream_events(
    db: AsyncSession,
    *,
    session_id: int,
    user_id: int | None,
    messages: list[dict[str, Any]],
    datasource_id: int | None,
    model_id: int | None,
    kb_ids,
    knowledge_context,
    skill_authorizations,
    pending_approvals: PendingApprovalsStore,
    on_event: EventCallback = None,
    system_prompt_override: str | None = None,
    run_id: str | None = None,
    skip_approval: bool = False,
    history_window_hours: int | None = None,
) -> tuple[str, dict[str, int], bool]:
    usage_totals = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
    paused_for_approval = False
    run_id = run_id or f"chat_{local_now().strftime('%Y%m%d%H%M%S')}_{session_id}"
    sequence_no = 0
    terminal_status: str | None = None

    existing_assistant_msg = await _load_assistant_message_by_run_id(
        db,
        session_id=session_id,
        run_id=run_id,
    )
    full_response = existing_assistant_msg.content if existing_assistant_msg else ""
    render_segments = clone_render_segments(
        existing_assistant_msg.render_segments if existing_assistant_msg else None
    )
    if full_response and not render_segments:
        render_segments = append_markdown_render_segment([], full_response)

    async def _persist_current_assistant(
        status: str,
    ) -> ChatMessage | None:
        if not full_response and not render_segments:
            return None
        return await _persist_assistant_message(
            db,
            session_id=session_id,
            run_id=run_id,
            content=full_response,
            render_segments=render_segments,
            status=status,
            usage_totals=usage_totals,
        )

    try:
        async with asyncio.timeout(600):
            async for event in run_conversation_with_skills(
                messages,
                datasource_id,
                model_id,
                kb_ids,
                knowledge_context,
                db,
                user_id=user_id,
                session_id=session_id,
                skill_authorizations=skill_authorizations,
                system_prompt_override=system_prompt_override,
                skip_approval=skip_approval,
            ):
                event_type = event.get("type")
                if event_type in TRACKED_DIAGNOSIS_EVENTS:
                    sequence_no += 1
                    await _store_diagnosis_event(
                        db,
                        session_id=session_id,
                        run_id=run_id,
                        sequence_no=sequence_no,
                        event_type=event_type,
                        payload=_build_diagnosis_event_payload(event_type, event),
                        step_id=event.get("step_id") or event.get("tool_call_id"),
                    )

                if event_type == "content":
                    full_response += event["content"]
                    render_segments = apply_render_segments_event(render_segments, event)
                    await _emit({
                        "type": "content",
                        "content": event["content"],
                        "run_id": run_id,
                    }, on_event)
                elif event_type == "tool_call":
                    event_with_run = {**event, "run_id": run_id}
                    render_segments = apply_render_segments_event(render_segments, event_with_run)
                    await _store_tool_call(db, session_id, event_with_run)
                    await _emit({
                        "type": "tool_call",
                        "tool_name": event["tool_name"],
                        "tool_args": event["tool_args"],
                        "tool_call_id": event.get("tool_call_id"),
                        "run_id": run_id,
                    }, on_event)
                elif event_type == "tool_result":
                    event_with_run = {**event, "run_id": run_id}
                    render_segments = apply_render_segments_event(render_segments, event_with_run)
                    await _store_tool_result(db, session_id, event_with_run)
                    await _emit({
                        "type": "tool_result",
                        "tool_name": event["tool_name"],
                        "result": event["result"],
                        "execution_time_ms": event.get("execution_time_ms"),
                        "tool_call_id": event.get("tool_call_id"),
                        "skill_execution_id": event.get("skill_execution_id"),
                        "action_run_id": event.get("action_run_id"),
                        "action_title": event.get("action_title"),
                        "phase": event.get("phase"),
                        "visualization": event.get("visualization"),
                        "run_id": run_id,
                    }, on_event)
                elif event_type == "approval_request":
                    paused_for_approval = True
                    event_with_run = {**event, "run_id": run_id}
                    render_segments = apply_render_segments_event(render_segments, event_with_run)
                    await _persist_current_assistant(ASSISTANT_STATUS_AWAITING_APPROVAL)
                    await _store_approval_request(
                        db,
                        session_id,
                        event_with_run,
                        pending_approvals,
                        datasource_id,
                        model_id,
                        kb_ids,
                        knowledge_context,
                        skill_authorizations,
                        user_id,
                        history_window_hours,
                    )
                    await _emit(event_with_run, on_event)
                elif event_type == "usage":
                    usage = event.get("usage", {}) or {}
                    usage_totals["input_tokens"] += int(usage.get("input_tokens") or 0)
                    usage_totals["output_tokens"] += int(usage.get("output_tokens") or 0)
                    usage_totals["total_tokens"] += int(usage.get("total_tokens") or 0)
                    await _accumulate_usage(db, session_id, user_id, usage)
                    await _emit({"type": "usage", "usage": usage}, on_event)
                elif event_type in ("thinking_start", "thinking_phase", "thinking_complete"):
                    logger.info(f"[THINKING] Emitting thinking event: {event}")
                    await _emit(event, on_event)
                elif event_type in (
                    "diagnosis_state",
                    "plan_created",
                    "knowledge_plan_created",
                    "knowledge_unit_activated",
                    "knowledge_replanned",
                    "kb_document_selected",
                    "kb_document_read",
                ):
                    await _emit(event, on_event)
                elif event_type == "plan_step_status":
                    await _emit(event, on_event)
                elif event_type == "done":
                    await _emit({"type": "done", "run_id": run_id}, on_event)
                elif event_type == "error":
                    terminal_status = ASSISTANT_STATUS_ERROR
                    await _persist_current_assistant(ASSISTANT_STATUS_ERROR)
                    await _emit({
                        "type": "error",
                        "content": event.get("content") or event.get("message", "Unknown error"),
                        "run_id": run_id,
                    }, on_event)
    except TimeoutError:
        logger.error(f"Conversation stream timed out for session {session_id}")
        if full_response:
            timeout_note = "\n\n[会话超时，以上为部分结果]"
            full_response += timeout_note
            render_segments = apply_render_segments_event(
                render_segments,
                {"type": "content", "content": timeout_note},
            )
            await _emit({"type": "content", "content": timeout_note, "run_id": run_id}, on_event)
        terminal_status = ASSISTANT_STATUS_PARTIAL
        await _persist_current_assistant(ASSISTANT_STATUS_PARTIAL)
        await _emit({"type": "error", "content": "AI 会话超时（600秒），请稍后重试或简化问题。", "run_id": run_id}, on_event)
        await _emit({"type": "done", "run_id": run_id}, on_event)
    except asyncio.CancelledError:
        logger.info(f"Conversation stream cancelled for session {session_id}")
        if full_response:
            cancel_note = "\n\n[用户已停止生成]"
            full_response += cancel_note
            render_segments = apply_render_segments_event(
                render_segments,
                {"type": "content", "content": cancel_note},
            )
        if (full_response or render_segments) and not paused_for_approval:
            try:
                await _persist_assistant_message(
                    db,
                    session_id=session_id,
                    run_id=run_id,
                    content=full_response,
                    render_segments=render_segments,
                    status=ASSISTANT_STATUS_CANCELLED,
                    usage_totals=usage_totals,
                )
            except Exception as save_err:
                logger.error(f"Failed to save partial response on cancel: {save_err}")
        raise

    if (full_response or render_segments) and not paused_for_approval and terminal_status is None:
        await _persist_current_assistant(ASSISTANT_STATUS_COMPLETE)
        if full_response:
            conclusion_payload = await _upsert_diagnosis_conclusion(
                db,
                session_id=session_id,
                user_id=user_id,
                run_id=run_id,
                content=full_response,
            )
            if conclusion_payload:
                sequence_no += 1
                await _store_diagnosis_event(
                    db,
                    session_id=session_id,
                    run_id=run_id,
                    sequence_no=sequence_no,
                    event_type="diagnosis_conclusion",
                    payload=_build_diagnosis_event_payload("diagnosis_conclusion", conclusion_payload),
                )
                await _emit({"type": "diagnosis_conclusion", **conclusion_payload}, on_event)

    return full_response, usage_totals, paused_for_approval


async def prepare_user_turn(
    db: AsyncSession,
    *,
    session_id: int,
    user_id: int | None,
    user_message: str,
    attachments: Optional[list[dict[str, Any]]] = None,
    payload_datasource_id: int | None = None,
    payload_host_id: int | None = None,
    model_id: int | None = None,
    history_window_hours: int | None = None,
    payload_skill_authorizations: dict[str, Any] | None = None,
) -> tuple[list[dict[str, Any]], int | None, int | None, int | None, Any, Any, Any]:
    attachments = attachments or []
    effective_datasource_id = payload_datasource_id
    effective_host_id = payload_host_id
    effective_model_id = model_id
    kb_ids = None
    knowledge_context = None
    skill_authorizations = None

    msg = ChatMessage(
        session_id=session_id,
        role="user",
        content=user_message or "[Attachment]",
        attachments=attachments,
    )
    db.add(msg)

    query = alive_select(DiagnosticSession).where(DiagnosticSession.id == session_id)
    if user_id is not None:
        query = query.where(DiagnosticSession.user_id == user_id)
    session_result = await db.execute(query)
    session = session_result.scalar_one_or_none()
    if session:
        if session.datasource_id is not None:
            effective_datasource_id = session.datasource_id
            if payload_datasource_id is not None and payload_datasource_id != session.datasource_id:
                logger.warning(
                    "Ignoring mismatched datasource_id %s for chat session %s; using bound datasource_id %s",
                    payload_datasource_id,
                    session_id,
                    session.datasource_id,
                )
        elif payload_datasource_id is not None:
            session.datasource_id = payload_datasource_id
            effective_datasource_id = payload_datasource_id

        if session.host_id is not None:
            effective_host_id = session.host_id
            if payload_host_id is not None and payload_host_id != session.host_id:
                logger.warning(
                    "Ignoring mismatched host_id %s for chat session %s; using bound host_id %s",
                    payload_host_id,
                    session_id,
                    session.host_id,
                )
        elif payload_host_id is not None:
            session.host_id = payload_host_id
            effective_host_id = payload_host_id

        if session.title in ("New Session", "新建会话"):
            session.title = user_message[:80] if user_message else "[Attachment]"
        if model_id is not None and model_id != session.ai_model_id:
            session.ai_model_id = model_id
        effective_model_id = session.ai_model_id
        session.updated_at = datetime.now(UTC)
        kb_ids = session.kb_ids
        intent_analysis = analyze_query_intent(user_message or "")
        knowledge_context = await build_knowledge_context(
            db,
            datasource_id=effective_datasource_id,
            host_id=effective_host_id,
            user_message=user_message or "",
            issue_category=intent_analysis.issue_category,
        )

        # 如果有主机上下文，合并主机知识
        if effective_host_id:
            from backend.services.host_knowledge_service import build_host_knowledge_context
            host_context = await build_host_knowledge_context(db, effective_host_id)
            if host_context:
                if knowledge_context is None:
                    knowledge_context = {}
                knowledge_context["host_context"] = host_context

        session.knowledge_snapshot = sanitize_for_json(knowledge_context)
        # 优先使用 payload 中的授权配置，如果没有则从会话中读取
        if payload_skill_authorizations is not None:
            logger.debug(f"Using payload_skill_authorizations: {payload_skill_authorizations}")
            skill_authorizations = normalize_skill_authorizations(
                payload_skill_authorizations,
                getattr(session, "disabled_tools", None),
            )
        else:
            logger.debug(f"Using session skill_authorizations: {getattr(session, 'skill_authorizations', None)}")
            skill_authorizations = normalize_skill_authorizations(
                getattr(session, "skill_authorizations", None),
                getattr(session, "disabled_tools", None),
            )
        logger.debug(f"Final normalized skill_authorizations: {skill_authorizations}")

    await db.commit()

    all_msgs = await load_session_messages_for_llm(
        db,
        session_id=session_id,
        history_window_hours=history_window_hours,
    )
    messages = await rebuild_llm_messages(all_msgs)
    return messages, effective_datasource_id, effective_host_id, effective_model_id, kb_ids, knowledge_context, skill_authorizations


async def continue_conversation_after_tool(
    db: AsyncSession,
    *,
    session_id: int,
    user_id: int | None,
    datasource_id: int | None,
    model_id: int | None,
    kb_ids,
    knowledge_context,
    skill_authorizations,
    pending_approvals: PendingApprovalsStore,
    on_event: EventCallback = None,
    run_id: str | None = None,
    history_window_hours: int | None = None,
) -> tuple[str, dict[str, int], bool]:
    all_msgs = await load_session_messages_for_llm(
        db,
        session_id=session_id,
        history_window_hours=history_window_hours,
    )
    messages = await rebuild_llm_messages(all_msgs)
    return await process_stream_events(
        db,
        session_id=session_id,
        user_id=user_id,
        messages=messages,
        datasource_id=datasource_id,
        model_id=model_id,
        kb_ids=kb_ids,
        knowledge_context=knowledge_context,
        skill_authorizations=skill_authorizations,
        pending_approvals=pending_approvals,
        on_event=on_event,
        run_id=run_id or f"resume_{local_now().strftime('%Y%m%d%H%M%S')}_{session_id}",
        history_window_hours=history_window_hours,
    )


async def resolve_pending_approval(
    db: AsyncSession,
    *,
    session_id: int,
    approval_id: str,
    action: str,
    comment: str | None,
    user_id: int | None,
    pending_approvals: PendingApprovalsStore,
    on_event: EventCallback = None,
) -> dict[str, Any]:
    session_pending = pending_approvals.get(session_id, {})
    pending = session_pending.get(approval_id)
    if not pending:
        pending = await _load_pending_approval_from_db(
            db,
            session_id=session_id,
            approval_id=approval_id,
            user_id=user_id,
        )
        if pending:
            session_pending = pending_approvals.setdefault(session_id, {})
            session_pending[approval_id] = pending

    if not pending or pending.get("user_id") != user_id:
        raise ValueError("确认请求不存在或已失效")

    response_msg = ChatMessage(
        session_id=session_id,
        role="approval_response",
        run_id=pending.get("run_id"),
        content=json.dumps({
            "approval_id": approval_id,
            "action": action,
            "comment": comment,
            "status": action,
            "risk_level": pending.get("risk_level", "high"),
            "risk_reason": pending.get("risk_reason"),
        }),
    )
    db.add(response_msg)
    await db.commit()

    resolved_event = {
        "type": "confirmation_resolved",
        "approval_id": approval_id,
        "action": action,
        "comment": comment,
        "run_id": pending.get("run_id"),
        "tool_call_id": pending.get("tool_call_id"),
        "tool_name": pending.get("tool_name"),
        "action_run_id": pending.get("action_run_id"),
        "recommendation_id": pending.get("recommendation_id"),
        "action_title": pending.get("action_title"),
        "phase": pending.get("phase"),
    }
    await _apply_assistant_event_to_run(
        db,
        session_id=session_id,
        run_id=pending.get("run_id"),
        event=resolved_event,
    )
    await _emit(resolved_event, on_event)

    session_pending.pop(approval_id, None)
    if not session_pending:
        pending_approvals.pop(session_id, None)

    if action == "rejected":
        existing_assistant_msg = None
        if pending.get("run_id"):
            existing_assistant_msg = await _load_assistant_message_by_run_id(
                db,
                session_id=session_id,
                run_id=pending["run_id"],
            )
        if existing_assistant_msg:
            render_segments = clone_render_segments(existing_assistant_msg.render_segments)
            render_segments = upsert_tool_render_segment(
                render_segments,
                tool_call_id=pending.get("tool_call_id"),
                tool_name=pending.get("tool_name"),
                status="failed",
                args=pending.get("tool_args"),
                summary="用户已拒绝执行",
                metadata=_build_tool_segment_metadata(
                    approval_id=approval_id,
                    approval_status="rejected",
                    action_run_id=pending.get("action_run_id"),
                    action_title=pending.get("action_title"),
                    phase=pending.get("phase"),
                    risk_level=pending.get("risk_level"),
                    risk_reason=pending.get("risk_reason"),
                ),
            )
            await _persist_assistant_message(
                db,
                session_id=session_id,
                run_id=pending["run_id"],
                content=existing_assistant_msg.content or "",
                render_segments=render_segments,
                status=ASSISTANT_STATUS_PARTIAL,
            )
        return {"approval_id": approval_id, "status": "rejected", "pending": pending}

    tool_call_event = {
        "type": "tool_call",
        "run_id": pending.get("run_id"),
        "tool_name": pending["tool_name"],
        "tool_args": pending["tool_args"],
        "tool_call_id": pending.get("tool_call_id"),
        "action_run_id": pending.get("action_run_id"),
        "recommendation_id": pending.get("recommendation_id"),
        "action_title": pending.get("action_title"),
        "phase": pending.get("phase"),
    }
    await _store_tool_call(db, session_id, tool_call_event)
    await _apply_assistant_event_to_run(
        db,
        session_id=session_id,
        run_id=pending.get("run_id"),
        event=tool_call_event,
    )
    await _emit(tool_call_event, on_event)

    tool_result, execution_time_ms, skill_execution_id, visualization = await execute_skill_call(
        pending["tool_name"],
        dict(pending["tool_args"]),
        db,
        user_id,
        session_id,
    )
    tool_result_event = {
        "type": "tool_result",
        "run_id": pending.get("run_id"),
        "tool_name": pending["tool_name"],
        "result": tool_result,
        "execution_time_ms": execution_time_ms,
        "tool_call_id": pending.get("tool_call_id"),
        "skill_execution_id": skill_execution_id,
        "action_run_id": pending.get("action_run_id"),
        "recommendation_id": pending.get("recommendation_id"),
        "action_title": pending.get("action_title"),
        "phase": pending.get("phase"),
        "visualization": visualization,
    }
    await _store_tool_result(db, session_id, tool_result_event)
    await _apply_assistant_event_to_run(
        db,
        session_id=session_id,
        run_id=pending.get("run_id"),
        event=tool_result_event,
    )
    await _emit(tool_result_event, on_event)

    await continue_conversation_after_tool(
        db,
        session_id=session_id,
        user_id=user_id,
        datasource_id=pending.get("datasource_id"),
        model_id=pending.get("model_id"),
        kb_ids=pending.get("kb_ids"),
        knowledge_context=pending.get("knowledge_context"),
        skill_authorizations=normalize_skill_authorizations(
            pending.get("skill_authorizations"),
            pending.get("disabled_tools"),
        ),
        pending_approvals=pending_approvals,
        on_event=on_event,
        run_id=pending.get("run_id"),
        history_window_hours=pending.get("history_window_hours"),
    )
    return {"approval_id": approval_id, "status": "approved", "pending": pending}
