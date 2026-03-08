"""
Embeddings utility for knowledge base search
"""
from typing import List, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from backend.models.knowledge_base import KnowledgeBase


async def search_similar_chunks(db: AsyncSession, kb_id: int, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
    """
    Search for similar chunks in a knowledge base using vector similarity.
    """
    # Get knowledge base to get collection name
    result = await db.execute(
        select(KnowledgeBase).where(KnowledgeBase.id == kb_id)
    )
    kb = result.scalar_one_or_none()
    if not kb:
        return []

    # Search using vector store
    from backend.services.vector_store import VectorStore
    from backend.config import get_settings

    settings = get_settings()
    vector_store = VectorStore(
        persist_dir=settings.chroma_persist_dir,
        embedding_model=settings.embedding_model
    )

    # Search the collection
    search_results = vector_store.search(kb.collection_name, query, top_k)

    # Convert to expected format with similarity scores
    chunks = []
    for result in search_results:
        # Convert distance to similarity (lower distance = higher similarity)
        # ChromaDB returns cosine distance, convert to similarity
        similarity = 1.0 - result["distance"]

        chunk = type('Chunk', (), {
            'content': result["content"],
            'metadata': result["metadata"],
            'similarity': similarity
        })()
        chunks.append(chunk)

    return chunks
