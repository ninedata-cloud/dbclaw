import json
import asyncio
import logging
from datetime import datetime
from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from typing import List

from backend.database import get_db, async_session
from backend.models.diagnostic_session import DiagnosticSession, ChatMessage
from backend.schemas.chat import ChatSessionCreate, ChatSessionResponse, ChatMessageResponse
from backend.agent.conversation import run_conversation

logger = logging.getLogger(__name__)
router = APIRouter(tags=["chat"])


@router.get("/api/chat/sessions", response_model=List[ChatSessionResponse])
async def list_sessions(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(DiagnosticSession).order_by(desc(DiagnosticSession.updated_at))
    )
    return result.scalars().all()


@router.post("/api/chat/sessions", response_model=ChatSessionResponse)
async def create_session(data: ChatSessionCreate, db: AsyncSession = Depends(get_db)):
    session = DiagnosticSession(
        connection_id=data.connection_id,
        title=data.title or "New Session",
    )
    db.add(session)
    await db.commit()
    await db.refresh(session)
    return session


@router.get("/api/chat/sessions/{session_id}/messages", response_model=List[ChatMessageResponse])
async def get_messages(session_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(ChatMessage)
        .where(ChatMessage.session_id == session_id)
        .order_by(ChatMessage.created_at)
    )
    return result.scalars().all()


@router.delete("/api/chat/sessions/{session_id}")
async def delete_session(session_id: int, db: AsyncSession = Depends(get_db)):
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
async def clear_session_messages(session_id: int, db: AsyncSession = Depends(get_db)):
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
async def chat_websocket(websocket: WebSocket, session_id: int):
    await websocket.accept()
    logger.info(f"Chat WebSocket connected for session {session_id}")

    try:
        while True:
            data = await websocket.receive_json()
            user_message = data.get("message", "")
            connection_id = data.get("connection_id")
            model_id = data.get("model_id")

            if not user_message:
                continue

            # Save user message
            async with async_session() as db:
                msg = ChatMessage(
                    session_id=session_id,
                    role="user",
                    content=user_message,
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
            for m in all_msgs:
                msg_dict = {"role": m.role, "content": m.content}
                if m.tool_calls:
                    msg_dict["tool_calls"] = m.tool_calls
                if m.tool_call_id:
                    msg_dict["tool_call_id"] = m.tool_call_id
                messages.append(msg_dict)

            # Stream AI response
            full_response = ""
            async with async_session() as db:
                async for event in run_conversation(messages, connection_id, model_id, db):
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
        logger.error(f"Chat WebSocket error: {e}")
        try:
            await websocket.send_json({"type": "error", "content": str(e)})
        except Exception:
            pass
