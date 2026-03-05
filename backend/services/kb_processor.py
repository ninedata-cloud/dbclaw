import logging
import asyncio
from datetime import datetime
from sqlalchemy import select
from backend.database import async_session
from backend.models.knowledge_base import Document, KnowledgeBase
from backend.services.document_parser import DocumentParser
from backend.services.document_chunker import DocumentChunker
from backend.services.vector_store import VectorStore
from backend.config import get_settings

logger = logging.getLogger(__name__)


class KBProcessor:
    """Background processor for knowledge base documents."""

    def __init__(self, vector_store: VectorStore):
        self.vector_store = vector_store
        self.chunker = DocumentChunker(chunk_size=1000, overlap=200)
        self._running = False

    async def process_pending_documents(self):
        """Process all pending documents."""
        async with async_session() as db:
            result = await db.execute(
                select(Document).where(Document.status == "pending")
            )
            pending_docs = result.scalars().all()

            for doc in pending_docs:
                try:
                    await self._process_document(doc)
                except Exception as e:
                    logger.error(f"Error processing document {doc.id}: {e}")
                    # Update status to failed
                    async with async_session() as db2:
                        result = await db2.execute(
                            select(Document).where(Document.id == doc.id)
                        )
                        doc_obj = result.scalar_one_or_none()
                        if doc_obj:
                            doc_obj.status = "failed"
                            doc_obj.error_message = str(e)
                            doc_obj.processed_at = datetime.now()
                            await db2.commit()

    async def _process_document(self, doc: Document):
        """Process a single document: parse -> chunk -> embed -> store."""
        logger.info(f"Processing document {doc.id}: {doc.filename}")

        # Update status to processing
        async with async_session() as db:
            result = await db.execute(
                select(Document).where(Document.id == doc.id)
            )
            doc_obj = result.scalar_one_or_none()
            if not doc_obj:
                return
            doc_obj.status = "processing"
            await db.commit()

        try:
            # Get knowledge base
            async with async_session() as db:
                result = await db.execute(
                    select(KnowledgeBase).where(KnowledgeBase.id == doc.kb_id)
                )
                kb = result.scalar_one_or_none()
                if not kb:
                    raise ValueError(f"Knowledge base {doc.kb_id} not found")

            # Parse document
            text = await DocumentParser.parse(doc.file_path, doc.file_type)
            if not text or not text.strip():
                raise ValueError("Document is empty or could not be parsed")

            # Chunk text
            chunks = self.chunker.chunk_text(text, doc.filename, doc.file_type)
            if not chunks:
                raise ValueError("No chunks generated from document")

            # Store in vector database
            self.vector_store.add_documents(kb.collection_name, chunks, doc.id)

            # Update document status
            async with async_session() as db:
                result = await db.execute(
                    select(Document).where(Document.id == doc.id)
                )
                doc_obj = result.scalar_one_or_none()
                if doc_obj:
                    doc_obj.status = "completed"
                    doc_obj.chunk_count = len(chunks)
                    doc_obj.processed_at = datetime.now()
                    doc_obj.error_message = None
                    await db.commit()

            logger.info(f"Successfully processed document {doc.id} with {len(chunks)} chunks")

        except Exception as e:
            logger.error(f"Failed to process document {doc.id}: {e}")
            # Update status to failed
            async with async_session() as db:
                result = await db.execute(
                    select(Document).where(Document.id == doc.id)
                )
                doc_obj = result.scalar_one_or_none()
                if doc_obj:
                    doc_obj.status = "failed"
                    doc_obj.error_message = str(e)
                    doc_obj.processed_at = datetime.now()
                    await db.commit()
            raise

    async def start_background_processing(self):
        """Start background processing loop."""
        self._running = True
        while self._running:
            try:
                await self.process_pending_documents()
            except Exception as e:
                logger.error(f"Error in background processing: {e}")
            await asyncio.sleep(30)  # Check every 30 seconds

    def stop(self):
        """Stop background processing."""
        self._running = False
