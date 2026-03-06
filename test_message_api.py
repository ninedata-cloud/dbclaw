#!/usr/bin/env python3
"""Test message API endpoint"""
import asyncio
import sys
sys.path.insert(0, '.')

from backend.database import async_session
from backend.models.diagnostic_session import ChatMessage
from backend.schemas.chat import ChatMessageResponse
from sqlalchemy import select


async def test_message_api():
    """Test if messages can be serialized correctly"""
    async with async_session() as db:
        # Get messages for session 4
        result = await db.execute(
            select(ChatMessage)
            .where(ChatMessage.session_id == 4)
            .order_by(ChatMessage.created_at)
        )
        messages = result.scalars().all()

        print(f"Found {len(messages)} messages for session 4\n")

        # Try to serialize each message
        for msg in messages:
            try:
                response = ChatMessageResponse.model_validate(msg)
                print(f"✓ Message {msg.id} serialized successfully")
                print(f"  Role: {response.role}")
                print(f"  Content: {response.content[:50]}...")
                print(f"  Attachments: {response.attachments}")
                print()
            except Exception as e:
                print(f"✗ Message {msg.id} failed to serialize: {e}")
                print(f"  Raw data: {msg.__dict__}")
                print()


if __name__ == "__main__":
    asyncio.run(test_message_api())
