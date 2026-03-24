import json
import asyncio
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
from backend.schemas.chat import ChatSessionCreate, ChatSessionResponse, ChatMessageResponse
from backend.agent.conversation import run_conversation
from backend.agent.conversation_skills import run_conversation_with_skills
from backend.agent.tools import HIGH_RISK_TOOLS

from backend.dependencies import get_current_user
from backend.services.config_service import get_config
from backend.services.session_service import SessionService

logger = logging.getLogger(__name__)
router = APIRouter(tags=["chat"])


async def _get_owned_session(db: AsyncSession, session_id: int, user: User) -> DiagnosticSession:
    result = await db.execute(
        select(DiagnosticSession).where(DiagnosticSession.id == session_id, DiagnosticSession.user_id == user.id)
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
        user_result = await db.execute(select(User).where(User.id == user_session.user_id))
        user = user_result.scalar_one_or_none()
        if not user or not user.is_active:
            return None, None
        chat_session_result = await db.execute(
            select(DiagnosticSession).where(DiagnosticSession.id == session_id, DiagnosticSession.user_id == user.id)
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
        select(DiagnosticSession)
        .where(DiagnosticSession.user_id == user.id)
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
        select(ChatMessage)
        .where(ChatMessage.session_id == session_id)
        .order_by(ChatMessage.created_at)
    )
    return result.scalars().all()


@router.delete("/api/chat/sessions/{session_id}")
async def delete_session(session_id: int, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)):
    """Delete a chat session and all its messages."""
    await _get_owned_session(db, session_id, user)
    result = await db.execute(
        select(ChatMessage).where(ChatMessage.session_id == session_id)
    )
    for msg in result.scalars().all():
        await db.delete(msg)
    # Delete session
    result = await db.execute(
        select(DiagnosticSession).where(DiagnosticSession.id == session_id, DiagnosticSession.user_id == user.id)
    )
    session = result.scalar_one_or_none()
    if session:
        await db.delete(session)
    await db.commit()
    return {"message": "Session deleted"}


@router.delete("/api/chat/sessions/{session_id}/messages")
async def clear_session_messages(session_id: int, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)):
    """Clear all messages in a session but keep the session itself."""
    await _get_owned_session(db, session_id, user)
    result = await db.execute(
        select(ChatMessage).where(ChatMessage.session_id == session_id)
    )
    for msg in result.scalars().all():
        await db.delete(msg)
    # Reset session title
    result = await db.execute(
        select(DiagnosticSession).where(DiagnosticSession.id == session_id, DiagnosticSession.user_id == user.id)
    )
    session = result.scalar_one_or_none()
    if session:
        session.title = "新建会话"
        session.input_tokens = 0
        session.output_tokens = 0
        session.total_tokens = 0
        session.updated_at = datetime.utcnow()
    await db.commit()
    return {"message": "Messages cleared"}


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

            effective_datasource_id = payload_datasource_id
            kb_ids = None
            disabled_tools = None

            # Save user message
            async with async_session() as db:
                msg = ChatMessage(
                    session_id=session_id,
                    role="user",
                    content=user_message or "[Attachment]",
                    attachments=attachments,
                )
                db.add(msg)

                # Update session title/model_id and lock datasource_id from first turn
                session_result = await db.execute(
                    select(DiagnosticSession).where(DiagnosticSession.id == session_id, DiagnosticSession.user_id == user.id)
                )
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

                    # Update title if it's still the default (support both Chinese and English)
                    if session.title in ("New Session", "新建会话"):
                        session.title = user_message[:80] if user_message else "[Attachment]"
                    if model_id and not session.ai_model_id:
                        session.ai_model_id = model_id
                    session.updated_at = datetime.utcnow()
                    kb_ids = session.kb_ids
                    disabled_tools = session.disabled_tools

                await db.commit()

                # Load conversation history
                msgs_result = await db.execute(
                    select(ChatMessage)
                    .where(ChatMessage.session_id == session_id)
                    .order_by(ChatMessage.created_at)
                )
                all_msgs = msgs_result.scalars().all()

            # Build messages for LLM
            messages = []
            from backend.utils.attachment_handler import AttachmentHandler

            for m in all_msgs:
                # Convert custom roles to standard OpenAI format
                if m.role == "tool_call":
                    # Convert tool_call to assistant message with tool_calls
                    try:
                        data = json.loads(m.content)
                        msg_dict = {
                            "role": "assistant",
                            "content": None,
                            "tool_calls": [{
                                "id": f"call_{data['tool_name']}_{m.id}",
                                "type": "function",
                                "function": {
                                    "name": data["tool_name"],
                                    "arguments": json.dumps(data["tool_args"])
                                }
                            }]
                        }
                        messages.append(msg_dict)
                    except Exception as e:
                        logger.error(f"Error parsing tool_call message: {e}")
                    continue
                elif m.role == "tool_result":
                    # Convert tool_result to tool message
                    try:
                        data = json.loads(m.content)
                        msg_dict = {
                            "role": "tool",
                            "tool_call_id": f"call_{data['tool_name']}_{m.id - 1}",  # Match the tool_call id
                            "content": data["result"]
                        }
                        messages.append(msg_dict)
                    except Exception as e:
                        logger.error(f"Error parsing tool_result message: {e}")
                    continue

                # Handle standard roles
                # Handle attachments
                if m.attachments:
                    # Build content array for multimodal messages
                    content_parts = []
                    if m.content and m.content != "[Attachment]":
                        content_parts.append({"type": "text", "text": m.content})

                    # Add attachments
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

            # Stream AI response using skill-based system
            full_response = ""
            usage_totals = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
            async with async_session() as db:
                async for event in run_conversation_with_skills(
                    messages,
                    effective_datasource_id,
                    model_id,
                    kb_ids,
                    db,
                    user_id=user.id,
                    session_id=session_id,
                    disabled_tools=disabled_tools
                ):
                    event_type = event.get("type")

                    if event_type == "content":
                        full_response += event["content"]
                        await websocket.send_json({
                            "type": "content",
                            "content": event["content"],
                        })
                    elif event_type == "tool_call":
                        # Save tool_call to database
                        async with async_session() as tool_db:
                            tool_msg = ChatMessage(
                                session_id=session_id,
                                role="tool_call",
                                content=json.dumps({
                                    "tool_name": event["tool_name"],
                                    "tool_args": event["tool_args"]
                                }),
                                tool_calls=[{
                                    "name": event["tool_name"],
                                    "arguments": event["tool_args"]
                                }]
                            )
                            tool_db.add(tool_msg)
                            await tool_db.commit()

                        await websocket.send_json({
                            "type": "tool_call",
                            "tool_name": event["tool_name"],
                            "tool_args": event["tool_args"],
                        })
                    elif event_type == "tool_result":
                        # Save tool_result to database
                        async with async_session() as tool_db:
                            result_msg = ChatMessage(
                                session_id=session_id,
                                role="tool_result",
                                content=json.dumps({
                                    "tool_name": event["tool_name"],
                                    "result": event["result"],
                                    "execution_time_ms": event.get("execution_time_ms")
                                })
                            )
                            tool_db.add(result_msg)
                            await tool_db.commit()

                        await websocket.send_json({
                            "type": "tool_result",
                            "tool_name": event["tool_name"],
                            "result": event["result"],
                            "execution_time_ms": event.get("execution_time_ms"),
                        })
                    elif event_type == "usage":
                        usage = event.get("usage", {}) or {}
                        usage_totals["input_tokens"] += int(usage.get("input_tokens") or 0)
                        usage_totals["output_tokens"] += int(usage.get("output_tokens") or 0)
                        usage_totals["total_tokens"] += int(usage.get("total_tokens") or 0)

                        session_result = await db.execute(
                            select(DiagnosticSession).where(DiagnosticSession.id == session_id, DiagnosticSession.user_id == user.id)
                        )
                        session = session_result.scalar_one_or_none()
                        if session:
                            session.input_tokens += int(usage.get("input_tokens") or 0)
                            session.output_tokens += int(usage.get("output_tokens") or 0)
                            session.total_tokens += int(usage.get("total_tokens") or 0)
                            session.updated_at = datetime.utcnow()
                            await db.commit()

                        await websocket.send_json({
                            "type": "usage",
                            "usage": usage,
                        })
                    elif event_type == "done":
                        full_response = event.get("content", full_response)
                        await websocket.send_json({"type": "done"})
                    elif event_type == "error":
                        await websocket.send_json({
                            "type": "error",
                            "content": event.get("content") or event.get("message", "Unknown error"),
                        })

            # Save assistant response
            if full_response:
                async with async_session() as db:
                    assistant_msg = ChatMessage(
                        session_id=session_id,
                        role="assistant",
                        content=full_response,
                    )
                    db.add(assistant_msg)
                    await db.commit()

    except WebSocketDisconnect:
        logger.info(f"Chat WebSocket disconnected for session {session_id}")
    except Exception as e:
        logger.error(f"Chat WebSocket error: {e}", exc_info=True)
        try:
            # Try to send error message first
            await websocket.send_json({"type": "error", "content": str(e)})
            # Then close with error code and reason
            await websocket.close(code=1011, reason=f"Server error: {str(e)[:100]}")
        except Exception:
            pass
