import asyncio
import json
import logging
from datetime import datetime
from urllib.parse import urlparse
from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect, UploadFile, File, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from typing import List

from backend.database import get_db, async_session
from backend.config import get_settings
from backend.agent.skill_authorization import (
    build_skill_authorization_catalog,
    normalize_skill_authorizations,
)
from backend.models.diagnostic_session import DiagnosticSession, ChatMessage
from backend.models.user import User
from backend.models.soft_delete import alive_filter, alive_select, get_alive_by_id
from backend.schemas.chat import ChatSessionCreate, ChatSessionResponse, ChatMessageResponse, ChatApprovalResolveRequest
from backend.skills.registry import SkillRegistry

from backend.dependencies import get_current_user
from backend.utils.datetime_helper import now
from backend.services.chat_orchestration_service import (
    apply_render_segments_event,
    clone_render_segments,
    continue_conversation_after_tool,
    get_session_insights,
    prepare_user_turn,
    process_stream_events,
    rebuild_llm_messages,
    resolve_pending_approval,
)
from backend.services.config_service import get_config
from backend.services.session_service import SessionService
from backend.utils.json_sanitizer import sanitize_for_json

logger = logging.getLogger(__name__)
router = APIRouter(tags=["chat"])
ACTIVE_CHAT_SOCKETS: dict[int, list[WebSocket]] = {}
PENDING_APPROVALS: dict[int, dict[str, dict]] = {}
# session_id -> running asyncio.Task for AI stream
ACTIVE_STREAM_TASKS: dict[int, asyncio.Task] = {}
ACTIVE_STREAM_STATES: dict[int, dict[str, object | None]] = {}


def _serialize_chat_session(session: DiagnosticSession) -> ChatSessionResponse:
    return ChatSessionResponse.model_validate(
        {
            "id": session.id,
            "datasource_id": session.datasource_id,
            "host_id": session.host_id,
            "ai_model_id": session.ai_model_id,
            "title": session.title,
            "kb_ids": session.kb_ids,
            "knowledge_snapshot": session.knowledge_snapshot,
            "disabled_tools": session.disabled_tools,
            "skill_authorizations": normalize_skill_authorizations(
                getattr(session, "skill_authorizations", None),
                getattr(session, "disabled_tools", None),
            ),
            "input_tokens": session.input_tokens,
            "output_tokens": session.output_tokens,
            "total_tokens": session.total_tokens,
            "created_at": session.created_at,
            "updated_at": session.updated_at,
        }
    )


def _register_socket(session_id: int, websocket: WebSocket) -> None:
    ACTIVE_CHAT_SOCKETS.setdefault(session_id, []).append(websocket)


def _unregister_socket(session_id: int, websocket: WebSocket) -> None:
    sockets = ACTIVE_CHAT_SOCKETS.get(session_id)
    if not sockets:
        return
    ACTIVE_CHAT_SOCKETS[session_id] = [ws for ws in sockets if ws is not websocket]
    if not ACTIVE_CHAT_SOCKETS[session_id]:
        ACTIVE_CHAT_SOCKETS.pop(session_id, None)


async def _broadcast_to_session(session_id: int, payload: dict) -> None:
    sockets = ACTIVE_CHAT_SOCKETS.get(session_id, [])
    stale = []
    for ws in sockets:
        try:
            await ws.send_json(payload)
        except Exception:
            logger.warning(
                "Failed to broadcast chat event for session %s: type=%s phase=%s",
                session_id,
                payload.get("type"),
                payload.get("phase"),
                exc_info=True,
            )
            stale.append(ws)
    for ws in stale:
        _unregister_socket(session_id, ws)


def _start_stream_state(session_id: int) -> None:
    ACTIVE_STREAM_STATES[session_id] = {
        "content": "",
        "thinking_phase": None,
        "thinking_message": "",
        "render_segments": [],
        "run_id": None,
        "status": "partial",
    }


def _clear_stream_state(session_id: int) -> None:
    ACTIVE_STREAM_STATES.pop(session_id, None)


def _update_stream_state(session_id: int, payload: dict) -> None:
    state = ACTIVE_STREAM_STATES.get(session_id)
    if state is None:
        return

    payload_type = payload.get("type")
    if payload.get("run_id"):
        state["run_id"] = payload.get("run_id")
    if payload_type in {"thinking_start", "thinking_phase", "thinking_complete"}:
        state["thinking_phase"] = payload.get("phase")
        state["thinking_message"] = payload.get("message") or ""
        return

    if payload_type == "plan_step_status":
        if payload.get("status") == "running":
            tool_name = payload.get("tool_name") or "工具"
            state["thinking_phase"] = "tool_execution"
            state["thinking_message"] = f"正在执行 {tool_name}..."
        else:
            state["thinking_phase"] = None
            state["thinking_message"] = ""
        return

    if payload_type == "content":
        chunk = payload.get("content") or ""
        if chunk:
            state["content"] = f"{state.get('content', '')}{chunk}"
        state["render_segments"] = apply_render_segments_event(state.get("render_segments"), payload)
        state["status"] = "partial"
        state["thinking_phase"] = None
        state["thinking_message"] = ""
        return

    if payload_type in {"tool_call", "tool_result", "approval_request"}:
        state["render_segments"] = apply_render_segments_event(state.get("render_segments"), payload)
        if payload_type == "approval_request":
            state["status"] = "awaiting_approval"
            state["thinking_phase"] = None
            state["thinking_message"] = ""
        else:
            state["status"] = "partial"
        return

    if payload_type == "done":
        state["status"] = "complete"
        state["thinking_phase"] = None
        state["thinking_message"] = ""
        return

    if payload_type == "error":
        state["status"] = "error"
        state["thinking_phase"] = None
        state["thinking_message"] = ""
        return


async def _emit_session_event(session_id: int, payload: dict) -> None:
    safe_payload = sanitize_for_json(payload)
    _update_stream_state(session_id, safe_payload)
    await _broadcast_to_session(session_id, safe_payload)


async def _rebuild_llm_messages(all_msgs):
    return await rebuild_llm_messages(all_msgs)


async def _continue_conversation_after_tool(
    session_id: int,
    user_id: int,
    datasource_id: int | None,
    model_id: int | None,
    kb_ids,
    knowledge_context,
    skill_authorizations,
    run_id: str | None = None,
):
    async with async_session() as db:
        await continue_conversation_after_tool(
            db,
            session_id=session_id,
            user_id=user_id,
            datasource_id=datasource_id,
            model_id=model_id,
            kb_ids=kb_ids,
            knowledge_context=knowledge_context,
            skill_authorizations=skill_authorizations,
            pending_approvals=PENDING_APPROVALS,
            on_event=lambda payload: _emit_session_event(session_id, payload),
            run_id=run_id,
        )


async def _get_owned_session(db: AsyncSession, session_id: int, user: User) -> DiagnosticSession:
    result = await db.execute(
        alive_select(DiagnosticSession).where(DiagnosticSession.id == session_id, DiagnosticSession.user_id == user.id)
    )
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")
    return session


async def _validate_websocket_origin(websocket: WebSocket) -> bool:
    origin = websocket.headers.get("origin")
    if not origin:
        return True

    allowed_host = {websocket.headers.get("host", "")}
    async with async_session() as db:
        external_base_url = await get_config(db, "app_external_base_url", default="")

    if external_base_url:
        parsed = urlparse(external_base_url)
        if parsed.netloc:
            allowed_host.add(parsed.netloc)

    parsed_origin = urlparse(origin)
    return bool(parsed_origin.scheme in {"http", "https"} and parsed_origin.netloc in allowed_host)


async def _authenticate_websocket_session(websocket: WebSocket, session_id: int) -> tuple[User, DiagnosticSession] | tuple[None, None]:
    session_cookie = websocket.cookies.get(get_settings().session_cookie_name)
    async with async_session() as db:
        user_session = await SessionService.get_active_session(db, session_cookie)
        if not user_session:
            return None, None
        user_result = await db.execute(select(User).where(User.id == user_session.user_id, alive_filter(User)))
        user = user_result.scalar_one_or_none()
        if not user or not user.is_active:
            return None, None
        chat_session_result = await db.execute(
            alive_select(DiagnosticSession).where(DiagnosticSession.id == session_id, DiagnosticSession.user_id == user.id)
        )
        chat_session = chat_session_result.scalar_one_or_none()
        if not chat_session:
            return None, None
        await SessionService.touch_session(db, user_session)
        await db.commit()
        return user, chat_session


@router.get("/api/chat/skill-authorizations")
async def get_skill_authorization_catalog(
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    registry = SkillRegistry(db)
    skills = await registry.list_skills(is_enabled=True, is_builtin=True)
    return {
        "groups": build_skill_authorization_catalog(skills),
    }


@router.get("/api/chat/sessions", response_model=List[ChatSessionResponse])
async def list_sessions(
    datasource_id: int | None = Query(None),
    host_id: int | None = Query(None),
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    query = (
        alive_select(DiagnosticSession)
        .where(
            DiagnosticSession.user_id == user.id,
            DiagnosticSession.is_hidden == False  # Exclude system-generated hidden sessions
        )
        .order_by(desc(DiagnosticSession.updated_at))
    )
    if datasource_id is not None:
        query = query.where(DiagnosticSession.datasource_id == datasource_id)
    if host_id is not None:
        query = query.where(DiagnosticSession.host_id == host_id)

    result = await db.execute(query)
    return [_serialize_chat_session(session) for session in result.scalars().all()]


@router.post("/api/chat/sessions", response_model=ChatSessionResponse)
async def create_session(data: ChatSessionCreate, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)):
    skill_authorizations = normalize_skill_authorizations(
        data.skill_authorizations.model_dump() if data.skill_authorizations else None,
        data.disabled_tools,
    )
    session = DiagnosticSession(
        user_id=user.id,
        datasource_id=data.datasource_id,
        host_id=data.host_id,
        title=data.title or "New Session",
        ai_model_id=data.ai_model_id,
        disabled_tools=data.disabled_tools,
        skill_authorizations=skill_authorizations,
    )
    db.add(session)
    await db.commit()
    await db.refresh(session)
    return _serialize_chat_session(session)


@router.post("/api/chat/sessions/{session_id}/upload")
async def upload_attachment(
    session_id: int,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user)
):
    """Upload file attachment for chat session"""
    from backend.utils.attachment_handler import AttachmentHandler

    await _get_owned_session(db, session_id, user)

    # Check file size
    file_content = await file.read()
    if len(file_content) > AttachmentHandler.MAX_FILE_SIZE:
        raise HTTPException(status_code=400, detail="文件过大（最大 10MB）")

    # Check file type
    if not AttachmentHandler.is_allowed_file(file.filename):
        raise HTTPException(status_code=400, detail="不支持的文件类型")

    # Save attachment
    try:
        metadata = await AttachmentHandler.save_attachment(file_content, file.filename, session_id)
        return metadata
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"保存附件失败: {str(e)}")


@router.get("/api/chat/sessions/{session_id}/messages", response_model=List[ChatMessageResponse])
async def get_messages(session_id: int, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)):
    await _get_owned_session(db, session_id, user)
    result = await db.execute(
        alive_select(ChatMessage)
        .where(ChatMessage.session_id == session_id)
        .order_by(ChatMessage.id)
    )
    return result.scalars().all()


@router.get("/api/chat/sessions/{session_id}/insights")
async def get_session_diagnostic_insights(session_id: int, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)):
    await _get_owned_session(db, session_id, user)
    return await get_session_insights(db, session_id=session_id, user_id=user.id)


@router.delete("/api/chat/sessions/{session_id}")
async def delete_session(session_id: int, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)):
    """Delete a chat session and all its messages."""
    session = await _get_owned_session(db, session_id, user)
    result = await db.execute(
        alive_select(ChatMessage).where(ChatMessage.session_id == session_id)
    )
    for msg in result.scalars().all():
        msg.soft_delete(user.id)
    session.soft_delete(user.id)
    PENDING_APPROVALS.pop(session_id, None)
    await db.commit()
    return {"message": "Session deleted"}


@router.delete("/api/chat/sessions/{session_id}/messages")
async def clear_session_messages(session_id: int, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)):
    """Clear all messages in a session but keep the session itself."""
    session = await _get_owned_session(db, session_id, user)
    result = await db.execute(
        alive_select(ChatMessage).where(ChatMessage.session_id == session_id)
    )
    for msg in result.scalars().all():
        msg.soft_delete(user.id)
    session.title = "新建会话"
    session.input_tokens = 0
    session.output_tokens = 0
    session.total_tokens = 0
    session.updated_at = now()
    PENDING_APPROVALS.pop(session_id, None)
    await db.commit()
    return {"message": "Messages cleared"}


@router.post("/api/chat/sessions/{session_id}/approvals/{approval_id}/resolve")
async def resolve_chat_approval(
    session_id: int,
    approval_id: str,
    payload: ChatApprovalResolveRequest,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    await _get_owned_session(db, session_id, user)
    current_task = asyncio.current_task()
    if current_task is not None:
        ACTIVE_STREAM_TASKS[session_id] = current_task
    _start_stream_state(session_id)
    try:
        result = await resolve_pending_approval(
            db,
            session_id=session_id,
            approval_id=approval_id,
            action=payload.action,
            comment=payload.comment,
            user_id=user.id,
            pending_approvals=PENDING_APPROVALS,
            on_event=lambda event: _emit_session_event(session_id, event),
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    finally:
        ACTIVE_STREAM_TASKS.pop(session_id, None)
        _clear_stream_state(session_id)

    return {"approval_id": approval_id, "status": result["status"]}


@router.websocket("/ws/chat/{session_id}")
async def chat_websocket(websocket: WebSocket, session_id: int):
    if not await _validate_websocket_origin(websocket):
        await websocket.close(code=1008, reason="Invalid origin")
        return

    user, owned_session = await _authenticate_websocket_session(websocket, session_id)
    if not user or not owned_session:
        await websocket.close(code=1008, reason="Invalid or expired session")
        return

    await websocket.accept()
    _register_socket(session_id, websocket)
    logger.info(f"Chat WebSocket connected for session {session_id}, user {user.id}")

    # If there's an active stream task for this session, notify the client
    active_task = ACTIVE_STREAM_TASKS.get(session_id)
    if active_task and not active_task.done():
        stream_state = ACTIVE_STREAM_STATES.get(session_id, {})
        try:
            await websocket.send_json({
                "type": "stream_resuming",
                "message": stream_state.get("thinking_message") or "AI 正在生成中...",
                "content": stream_state.get("content") or "",
                "thinking_phase": stream_state.get("thinking_phase"),
                "thinking_message": stream_state.get("thinking_message") or "",
                "render_segments": clone_render_segments(stream_state.get("render_segments")),
                "run_id": stream_state.get("run_id"),
                "status": stream_state.get("status"),
            })
        except Exception:
            pass

    try:
        while True:
            data = await websocket.receive_json()

            # Handle cancel command
            msg_type = data.get("type")
            if msg_type == "cancel":
                task = ACTIVE_STREAM_TASKS.get(session_id)
                if task and not task.done():
                    task.cancel()
                    logger.info(f"Stream task cancel requested for session {session_id}")
                    try:
                        await websocket.send_json({"type": "cancel_ack"})
                    except Exception:
                        pass
                continue

            refreshed_user, refreshed_session = await _authenticate_websocket_session(websocket, session_id)
            if not refreshed_user or not refreshed_session:
                await websocket.close(code=1008, reason="Session expired")
                return
            user = refreshed_user
            user_message = data.get("message", "")
            payload_datasource_id = data.get("datasource_id")
            payload_host_id = data.get("host_id")
            model_id = data.get("model_id")
            attachments = data.get("attachments", [])  # List of attachment IDs
            payload_skill_authorizations = data.get("skill_authorizations")  # Skill authorizations from frontend

            if not user_message and not attachments:
                continue

            # If there's already a running task for this session, reject new messages
            existing_task = ACTIVE_STREAM_TASKS.get(session_id)
            if existing_task and not existing_task.done():
                try:
                    await websocket.send_json({
                        "type": "error",
                        "content": "AI 正在生成中，请等待完成或点击停止按钮。",
                    })
                except Exception:
                    pass
                continue

            async def _run_stream(
                sid=session_id,
                uid=user.id,
                msg=user_message,
                atts=attachments,
                ds_id=payload_datasource_id,
                h_id=payload_host_id,
                m_id=model_id,
                skill_auths=payload_skill_authorizations,
            ):
                _start_stream_state(sid)
                try:
                    async with async_session() as db:
                        messages, effective_datasource_id, effective_host_id, m_id_resolved, kb_ids, knowledge_context, skill_authorizations = await prepare_user_turn(
                            db,
                            session_id=sid,
                            user_id=uid,
                            user_message=msg,
                            attachments=atts,
                            payload_datasource_id=ds_id,
                            payload_host_id=h_id,
                            model_id=m_id,
                            payload_skill_authorizations=skill_auths,
                        )

                        await process_stream_events(
                            db,
                            session_id=sid,
                            user_id=uid,
                            messages=messages,
                            datasource_id=effective_datasource_id,
                            model_id=m_id_resolved,
                            kb_ids=kb_ids,
                            knowledge_context=knowledge_context,
                            skill_authorizations=skill_authorizations,
                            pending_approvals=PENDING_APPROVALS,
                            on_event=lambda payload: _emit_session_event(sid, payload),
                        )
                except asyncio.CancelledError:
                    logger.info(f"Stream task cancelled for session {sid}")
                    try:
                        await _emit_session_event(sid, {
                            "type": "content",
                            "content": "\n\n[用户已停止生成]",
                        })
                        await _emit_session_event(sid, {"type": "done"})
                    except Exception:
                        pass
                except Exception as e:
                    logger.error(f"Stream task error for session {sid}: {e}", exc_info=True)
                    await _emit_session_event(sid, {
                        "type": "error",
                        "content": f"AI 会话出错: {str(e)}",
                    })
                finally:
                    ACTIVE_STREAM_TASKS.pop(sid, None)
                    _clear_stream_state(sid)

            task = asyncio.create_task(_run_stream())
            ACTIVE_STREAM_TASKS[session_id] = task

    except WebSocketDisconnect:
        _unregister_socket(session_id, websocket)
        logger.info(f"Chat WebSocket disconnected for session {session_id} (task continues in background)")
    except Exception as e:
        _unregister_socket(session_id, websocket)
        logger.error(f"Chat WebSocket error: {e}", exc_info=True)
        try:
            await websocket.send_json({"type": "error", "content": str(e)})
            await websocket.close(code=1011, reason=f"Server error: {str(e)[:100]}")
        except Exception as e:
            logger.debug("Failed to send error message to WebSocket: %s", e)
