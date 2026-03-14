import json
import asyncio
import logging
from datetime import datetime
from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect, Query, UploadFile, File, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from typing import List

from backend.database import get_db, async_session
from backend.models.diagnostic_session import DiagnosticSession, ChatMessage
from backend.schemas.chat import ChatSessionCreate, ChatSessionResponse, ChatMessageResponse
from backend.agent.conversation import run_conversation
from backend.agent.conversation_skills import run_conversation_with_skills
from backend.agent.tools import HIGH_RISK_TOOLS

from backend.dependencies import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter(tags=["chat"])


@router.get("/api/chat/high-risk-tools")
async def get_high_risk_tools(user=Depends(get_current_user)):
    """Return the list of high-risk tools that users can toggle."""
    return [{"name": name, "description": description} for name, description in HIGH_RISK_TOOLS.items()]


@router.get("/api/chat/sessions", response_model=List[ChatSessionResponse])
async def list_sessions(db: AsyncSession = Depends(get_db), user=Depends(get_current_user)):
    result = await db.execute(
        select(DiagnosticSession).order_by(desc(DiagnosticSession.updated_at))
    )
    return result.scalars().all()


@router.post("/api/chat/sessions", response_model=ChatSessionResponse)
async def create_session(data: ChatSessionCreate, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)):
    session = DiagnosticSession(
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
    result = await db.execute(
        select(ChatMessage)
        .where(ChatMessage.session_id == session_id)
        .order_by(ChatMessage.created_at)
    )
    return result.scalars().all()


@router.delete("/api/chat/sessions/{session_id}")
async def delete_session(session_id: int, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)):
    """Delete a chat session and all its messages."""
    # Delete messages first
    result = await db.execute(
        select(ChatMessage).where(ChatMessage.session_id == session_id)
    )
    for msg in result.scalars().all():
        await db.delete(msg)
    # Delete session
    result = await db.execute(
        select(DiagnosticSession).where(DiagnosticSession.id == session_id)
    )
    session = result.scalar_one_or_none()
    if session:
        await db.delete(session)
    await db.commit()
    return {"message": "Session deleted"}


@router.delete("/api/chat/sessions/{session_id}/messages")
async def clear_session_messages(session_id: int, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)):
    """Clear all messages in a session but keep the session itself."""
    result = await db.execute(
        select(ChatMessage).where(ChatMessage.session_id == session_id)
    )
    for msg in result.scalars().all():
        await db.delete(msg)
    # Reset session title
    result = await db.execute(
        select(DiagnosticSession).where(DiagnosticSession.id == session_id)
    )
    session = result.scalar_one_or_none()
    if session:
        session.title = "New Session"
    await db.commit()
    return {"message": "Messages cleared"}


@router.websocket("/ws/chat/{session_id}")
async def chat_websocket(websocket: WebSocket, session_id: int, token: str = Query(default=None)):
    # Validate token for WebSocket connections
    if not token:
        await websocket.close(code=1008, reason="Missing token")
        return
    try:
        from backend.utils.security import decode_access_token
        payload = decode_access_token(token)
        if not payload.get("sub"):
            await websocket.close(code=1008, reason="Invalid token")
            return
    except Exception:
        await websocket.close(code=1008, reason="Invalid or expired token")
        return

    await websocket.accept()
    logger.info(f"Chat WebSocket connected for session {session_id}")

    try:
        while True:
            data = await websocket.receive_json()
            user_message = data.get("message", "")
            datasource_id = data.get("datasource_id")
            model_id = data.get("model_id")
            attachments = data.get("attachments", [])  # List of attachment IDs

            if not user_message and not attachments:
                continue

            # Save user message
            async with async_session() as db:
                msg = ChatMessage(
                    session_id=session_id,
                    role="user",
                    content=user_message or "[Attachment]",
                    attachments=attachments,
                )
                db.add(msg)

                # Update session title and model_id from first message
                session_result = await db.execute(
                    select(DiagnosticSession).where(DiagnosticSession.id == session_id)
                )
                session = session_result.scalar_one_or_none()
                if session:
                    if session.title == "New Session":
                        session.title = user_message[:80]
                    if model_id and not session.ai_model_id:
                        session.ai_model_id = model_id

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

            # Get session kb_ids and disabled_tools
            async with async_session() as db:
                session_result = await db.execute(
                    select(DiagnosticSession).where(DiagnosticSession.id == session_id)
                )
                session = session_result.scalar_one_or_none()
                kb_ids = session.kb_ids if session else None
                disabled_tools = session.disabled_tools if session else None

            # Stream AI response using skill-based system
            full_response = ""
            async with async_session() as db:
                # Get user_id from token (sub contains username, not user_id)
                username = payload.get("sub")
                from backend.models.user import User
                user_result = await db.execute(select(User).where(User.username == username))
                user = user_result.scalar_one_or_none()
                user_id = user.id if user else None

                async for event in run_conversation_with_skills(
                    messages,
                    datasource_id,
                    model_id,
                    kb_ids,
                    db,
                    user_id=user_id,
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
                        await websocket.send_json({
                            "type": "tool_call",
                            "tool_name": event["tool_name"],
                            "tool_args": event["tool_args"],
                        })
                    elif event_type == "tool_result":
                        await websocket.send_json({
                            "type": "tool_result",
                            "tool_name": event["tool_name"],
                            "result": event["result"],
                            "execution_time_ms": event.get("execution_time_ms"),
                        })
                    elif event_type == "done":
                        full_response = event.get("content", full_response)
                        await websocket.send_json({"type": "done"})
                    elif event_type == "error":
                        await websocket.send_json({
                            "type": "error",
                            "content": event["content"],
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
