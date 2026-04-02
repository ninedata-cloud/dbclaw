import json
import logging
from datetime import datetime
from urllib.parse import urlparse
from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect, UploadFile, File, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from typing import List

from backend.database import get_db, async_session
from backend.config import get_settings
from backend.models.diagnostic_session import DiagnosticSession, ChatMessage
from backend.models.user import User
from backend.models.soft_delete import alive_filter, alive_select, get_alive_by_id
from backend.schemas.chat import ChatSessionCreate, ChatSessionResponse, ChatMessageResponse, ChatApprovalResolveRequest
from backend.agent.tools import HIGH_RISK_TOOLS

from backend.dependencies import get_current_user
from backend.services.chat_orchestration_service import (
    continue_conversation_after_tool,
    prepare_user_turn,
    process_stream_events,
    rebuild_llm_messages,
    resolve_pending_approval,
)
from backend.services.config_service import get_config
from backend.services.session_service import SessionService

logger = logging.getLogger(__name__)
router = APIRouter(tags=["chat"])
ACTIVE_CHAT_SOCKETS: dict[int, list[WebSocket]] = {}
PENDING_APPROVALS: dict[int, dict[str, dict]] = {}


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
            stale.append(ws)
    for ws in stale:
        _unregister_socket(session_id, ws)


async def _rebuild_llm_messages(all_msgs):
    return await rebuild_llm_messages(all_msgs)


async def _continue_conversation_after_tool(
    session_id: int,
    user_id: int,
    datasource_id: int | None,
    model_id: int | None,
    kb_ids,
    disabled_tools,
):
    async with async_session() as db:
        await continue_conversation_after_tool(
            db,
            session_id=session_id,
            user_id=user_id,
            datasource_id=datasource_id,
            model_id=model_id,
            kb_ids=kb_ids,
            disabled_tools=disabled_tools,
            pending_approvals=PENDING_APPROVALS,
            on_event=lambda payload: _broadcast_to_session(session_id, payload),
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

    allowed_hosts = {websocket.headers.get("host", "")}
    async with async_session() as db:
        external_base_url = await get_config(db, "app_external_base_url", default="")

    if external_base_url:
        parsed = urlparse(external_base_url)
        if parsed.netloc:
            allowed_hosts.add(parsed.netloc)

    parsed_origin = urlparse(origin)
    return bool(parsed_origin.scheme in {"http", "https"} and parsed_origin.netloc in allowed_hosts)


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


@router.get("/api/chat/high-risk-tools")
async def get_high_risk_tools(user=Depends(get_current_user)):
    """Return the list of high-risk tools that users can toggle."""
    return [{"name": name, "description": description} for name, description in HIGH_RISK_TOOLS.items()]


@router.get("/api/chat/sessions", response_model=List[ChatSessionResponse])
async def list_sessions(db: AsyncSession = Depends(get_db), user=Depends(get_current_user)):
    result = await db.execute(
        alive_select(DiagnosticSession)
        .where(
            DiagnosticSession.user_id == user.id,
            DiagnosticSession.is_hidden == False  # Exclude system-generated hidden sessions
        )
        .order_by(desc(DiagnosticSession.updated_at))
    )
    return result.scalars().all()


@router.post("/api/chat/sessions", response_model=ChatSessionResponse)
async def create_session(data: ChatSessionCreate, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)):
    session = DiagnosticSession(
        user_id=user.id,
        datasource_id=data.datasource_id,
        title=data.title or "New Session",
        ai_model_id=data.ai_model_id,
        kb_ids=data.kb_ids,
        disabled_tools=data.disabled_tools,
    )
    db.add(session)
    await db.commit()
    await db.refresh(session)
    return session


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
        .order_by(ChatMessage.created_at)
    )
    return result.scalars().all()


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
    session.updated_at = datetime.utcnow()
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
    try:
        result = await resolve_pending_approval(
            db,
            session_id=session_id,
            approval_id=approval_id,
            action=payload.action,
            comment=payload.comment,
            user_id=user.id,
            pending_approvals=PENDING_APPROVALS,
            on_event=lambda event: _broadcast_to_session(session_id, event),
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

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

    try:
        while True:
            data = await websocket.receive_json()
            refreshed_user, refreshed_session = await _authenticate_websocket_session(websocket, session_id)
            if not refreshed_user or not refreshed_session:
                await websocket.close(code=1008, reason="Session expired")
                return
            user = refreshed_user
            user_message = data.get("message", "")
            payload_datasource_id = data.get("datasource_id")
            model_id = data.get("model_id")
            attachments = data.get("attachments", [])  # List of attachment IDs

            if not user_message and not attachments:
                continue

            async with async_session() as db:
                messages, effective_datasource_id, model_id, kb_ids, disabled_tools = await prepare_user_turn(
                    db,
                    session_id=session_id,
                    user_id=user.id,
                    user_message=user_message,
                    attachments=attachments,
                    payload_datasource_id=payload_datasource_id,
                    model_id=model_id,
                )

                await process_stream_events(
                    db,
                    session_id=session_id,
                    user_id=user.id,
                    messages=messages,
                    datasource_id=effective_datasource_id,
                    model_id=model_id,
                    kb_ids=kb_ids,
                    disabled_tools=disabled_tools,
                    pending_approvals=PENDING_APPROVALS,
                    on_event=websocket.send_json,
                )

    except WebSocketDisconnect:
        _unregister_socket(session_id, websocket)
        logger.info(f"Chat WebSocket disconnected for session {session_id}")
    except Exception as e:
        _unregister_socket(session_id, websocket)
        logger.error(f"Chat WebSocket error: {e}", exc_info=True)
        try:
            # Try to send error message first
            await websocket.send_json({"type": "error", "content": str(e)})
            # Then close with error code and reason
            await websocket.close(code=1011, reason=f"Server error: {str(e)[:100]}")
        except Exception as e:
            logger.debug("Failed to send error message to WebSocket: %s", e)
