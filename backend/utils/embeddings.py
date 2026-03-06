"""
Embeddings utility for knowledge base search
"""
from typing import List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from backend.models.knowledge_base import KnowledgeChunk


async def search_similar_chunks(db: AsyncSession, kb_id: int, query: str, top_k: int = 5) -> List[KnowledgeChunk]:
    """
    Search for similar chunks in a knowledge base.
    This is a simplified version - in production, use vector similarity search.
    """
    # For now, just return recent chunks from the KB
    # TODO: Implement proper vector similarity search using embeddings
    result = await db.execute(
        select(KnowledgeChunk)
        .where(KnowledgeChunk.kb_id == kb_id)
        .limit(top_k)
    )
    chunks = result.scalars().all()

    # Add dummy similarity score
    for chunk in chunks:
        chunk.similarity = 0.8

    return chunks
