import json
import logging
from datetime import datetime
from typing import Any, AsyncGenerator, Awaitable, Callable, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.agent.conversation_skills import execute_skill_call, run_conversation_with_skills
from backend.models.diagnostic_session import ChatMessage, DiagnosticSession
from backend.models.soft_delete import alive_filter, alive_select

logger = logging.getLogger(__name__)

PendingApprovalsStore = dict[int, dict[str, dict[str, Any]]]
EventCallback = Optional[Callable[[dict[str, Any]], Awaitable[None]]]


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


async def _emit(event: dict[str, Any], on_event: EventCallback = None):
    if on_event:
        await on_event(event)


async def _store_tool_call(db: AsyncSession, session_id: int, event: dict[str, Any]) -> None:
    tool_msg = ChatMessage(
        session_id=session_id,
        role="tool_call",
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
        content=json.dumps({
            "tool_name": event["tool_name"],
            "result": event["result"],
            "execution_time_ms": event.get("execution_time_ms"),
            "tool_call_id": event.get("tool_call_id"),
            "skill_execution_id": event.get("skill_execution_id"),
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
    disabled_tools,
    user_id: int | None,
) -> None:
    approval_id = event["approval_id"]
    pending_approvals.setdefault(session_id, {})[approval_id] = {
        "approval_id": approval_id,
        "tool_name": event["tool_name"],
        "tool_args": event["tool_args"],
        "tool_call_id": event.get("tool_call_id"),
        "datasource_id": datasource_id,
        "model_id": model_id,
        "kb_ids": kb_ids,
        "disabled_tools": disabled_tools,
        "user_id": user_id,
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
        content=json.dumps({
            "approval_id": approval_id,
            "tool_name": event["tool_name"],
            "tool_args": event["tool_args"],
            "tool_call_id": event.get("tool_call_id"),
            "summary": event.get("summary"),
            "plan_markdown": event.get("plan_markdown"),
            "risk_level": event.get("risk_level", "high"),
            "risk_reason": event.get("risk_reason"),
            "suppressible": event.get("suppressible", False),
            "confirmation_key": event.get("confirmation_key"),
            "status": "pending",
            "action_run_id": event.get("action_run_id"),
            "recommendation_id": event.get("recommendation_id"),
            "action_title": event.get("action_title"),
            "phase": event.get("phase"),
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
        "tool_name": data.get("tool_name"),
        "tool_args": data.get("tool_args") or {},
        "tool_call_id": data.get("tool_call_id"),
        "datasource_id": session.datasource_id if session else None,
        "model_id": session.ai_model_id if session else None,
        "kb_ids": session.kb_ids if session else None,
        "disabled_tools": session.disabled_tools if session else None,
        "user_id": user_id,
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
        session.updated_at = datetime.utcnow()
        await db.commit()


async def process_stream_events(
    db: AsyncSession,
    *,
    session_id: int,
    user_id: int | None,
    messages: list[dict[str, Any]],
    datasource_id: int | None,
    model_id: int | None,
    kb_ids,
    disabled_tools,
    pending_approvals: PendingApprovalsStore,
    on_event: EventCallback = None,
) -> tuple[str, dict[str, int], bool]:
    full_response = ""
    usage_totals = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
    paused_for_approval = False

    async for event in run_conversation_with_skills(
        messages,
        datasource_id,
        model_id,
        kb_ids,
        db,
        user_id=user_id,
        session_id=session_id,
        disabled_tools=disabled_tools,
    ):
        event_type = event.get("type")

        if event_type == "content":
            full_response += event["content"]
            await _emit({"type": "content", "content": event["content"]}, on_event)
        elif event_type == "tool_call":
            await _store_tool_call(db, session_id, event)
            await _emit({
                "type": "tool_call",
                "tool_name": event["tool_name"],
                "tool_args": event["tool_args"],
                "tool_call_id": event.get("tool_call_id"),
            }, on_event)
        elif event_type == "tool_result":
            await _store_tool_result(db, session_id, event)
            await _emit({
                "type": "tool_result",
                "tool_name": event["tool_name"],
                "result": event["result"],
                "execution_time_ms": event.get("execution_time_ms"),
                "tool_call_id": event.get("tool_call_id"),
                "skill_execution_id": event.get("skill_execution_id"),
            }, on_event)
        elif event_type == "usage":
            usage = event.get("usage", {}) or {}
            usage_totals["input_tokens"] += int(usage.get("input_tokens") or 0)
            usage_totals["output_tokens"] += int(usage.get("output_tokens") or 0)
            usage_totals["total_tokens"] += int(usage.get("total_tokens") or 0)
            await _accumulate_usage(db, session_id, user_id, usage)
            await _emit({"type": "usage", "usage": usage}, on_event)
        elif event_type == "done":
            await _emit({"type": "done"}, on_event)
        elif event_type == "error":
            await _emit({
                "type": "error",
                "content": event.get("content") or event.get("message", "Unknown error"),
            }, on_event)

    if full_response and not paused_for_approval:
        assistant_msg = ChatMessage(
            session_id=session_id,
            role="assistant",
            content=full_response,
            input_tokens=usage_totals["input_tokens"],
            output_tokens=usage_totals["output_tokens"],
            total_tokens=usage_totals["total_tokens"],
        )
        db.add(assistant_msg)
        await db.commit()

    return full_response, usage_totals, paused_for_approval


async def prepare_user_turn(
    db: AsyncSession,
    *,
    session_id: int,
    user_id: int | None,
    user_message: str,
    attachments: Optional[list[dict[str, Any]]] = None,
    payload_datasource_id: int | None = None,
    model_id: int | None = None,
) -> tuple[list[dict[str, Any]], int | None, int | None, Any, Any]:
    attachments = attachments or []
    effective_datasource_id = payload_datasource_id
    kb_ids = None
    disabled_tools = None

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

        if session.title in ("New Session", "新建会话"):
            session.title = user_message[:80] if user_message else "[Attachment]"
        if model_id and not session.ai_model_id:
            session.ai_model_id = model_id
        session.updated_at = datetime.utcnow()
        kb_ids = session.kb_ids
        disabled_tools = session.disabled_tools

    await db.commit()

    msgs_result = await db.execute(
        alive_select(ChatMessage)
        .where(ChatMessage.session_id == session_id)
        .order_by(ChatMessage.created_at)
    )
    all_msgs = msgs_result.scalars().all()
    messages = await rebuild_llm_messages(all_msgs)
    return messages, effective_datasource_id, model_id, kb_ids, disabled_tools


async def continue_conversation_after_tool(
    db: AsyncSession,
    *,
    session_id: int,
    user_id: int | None,
    datasource_id: int | None,
    model_id: int | None,
    kb_ids,
    disabled_tools,
    pending_approvals: PendingApprovalsStore,
    on_event: EventCallback = None,
) -> tuple[str, dict[str, int], bool]:
    msgs_result = await db.execute(
        alive_select(ChatMessage)
        .where(ChatMessage.session_id == session_id)
        .order_by(ChatMessage.created_at)
    )
    all_msgs = msgs_result.scalars().all()
    messages = await rebuild_llm_messages(all_msgs)
    return await process_stream_events(
        db,
        session_id=session_id,
        user_id=user_id,
        messages=messages,
        datasource_id=datasource_id,
        model_id=model_id,
        kb_ids=kb_ids,
        disabled_tools=disabled_tools,
        pending_approvals=pending_approvals,
        on_event=on_event,
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
        "action_run_id": pending.get("action_run_id"),
        "recommendation_id": pending.get("recommendation_id"),
        "action_title": pending.get("action_title"),
        "phase": pending.get("phase"),
    }
    await _emit(resolved_event, on_event)

    session_pending.pop(approval_id, None)
    if not session_pending:
        pending_approvals.pop(session_id, None)

    if action == "rejected":
        return {"approval_id": approval_id, "status": "rejected", "pending": pending}

    tool_call_event = {
        "type": "tool_call",
        "tool_name": pending["tool_name"],
        "tool_args": pending["tool_args"],
        "tool_call_id": pending.get("tool_call_id"),
        "action_run_id": pending.get("action_run_id"),
        "recommendation_id": pending.get("recommendation_id"),
        "action_title": pending.get("action_title"),
        "phase": pending.get("phase"),
    }
    await _store_tool_call(db, session_id, tool_call_event)
    await _emit(tool_call_event, on_event)

    tool_result, execution_time_ms, skill_execution_id = await execute_skill_call(
        pending["tool_name"],
        dict(pending["tool_args"]),
        db,
        user_id,
        session_id,
    )
    tool_result_event = {
        "type": "tool_result",
        "tool_name": pending["tool_name"],
        "result": tool_result,
        "execution_time_ms": execution_time_ms,
        "tool_call_id": pending.get("tool_call_id"),
        "skill_execution_id": skill_execution_id,
        "action_run_id": pending.get("action_run_id"),
        "recommendation_id": pending.get("recommendation_id"),
        "action_title": pending.get("action_title"),
        "phase": pending.get("phase"),
    }
    await _store_tool_result(db, session_id, tool_result_event)
    await _emit(tool_result_event, on_event)

    await continue_conversation_after_tool(
        db,
        session_id=session_id,
        user_id=user_id,
        datasource_id=pending.get("datasource_id"),
        model_id=pending.get("model_id"),
        kb_ids=pending.get("kb_ids"),
        disabled_tools=pending.get("disabled_tools"),
        pending_approvals=pending_approvals,
        on_event=on_event,
    )
    return {"approval_id": approval_id, "status": "approved", "pending": pending}
