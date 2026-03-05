import logging
import uuid
from pathlib import Path
from typing import List
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.responses import FileResponse
from sqlalchemy import select, func, delete
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_db
from backend.models.knowledge_base import KnowledgeBase, Document
from backend.schemas.knowledge_base import (
    KnowledgeBaseCreate,
    KnowledgeBaseUpdate,
    KnowledgeBaseResponse,
    DocumentResponse,
    DocumentUploadResponse,
)
from backend.config import get_settings
from backend.dependencies import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/knowledge-bases", tags=["knowledge-bases"], dependencies=[Depends(get_current_user)])

# Allowed file extensions
ALLOWED_EXTENSIONS = {".md", ".pdf", ".docx", ".pptx", ".txt", ".html"}
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB


@router.get("", response_model=List[KnowledgeBaseResponse])
async def list_knowledge_bases(db: AsyncSession = Depends(get_db)):
    """List all knowledge bases with document counts."""
    result = await db.execute(select(KnowledgeBase))
    kbs = result.scalars().all()

    # Get document counts
    response = []
    for kb in kbs:
        count_result = await db.execute(
            select(func.count(Document.id)).where(Document.kb_id == kb.id)
        )
        doc_count = count_result.scalar()

        kb_dict = {
            "id": kb.id,
            "name": kb.name,
            "description": kb.description,
            "collection_name": kb.collection_name,
            "is_active": kb.is_active,
            "created_at": kb.created_at,
            "updated_at": kb.updated_at,
            "document_count": doc_count,
        }
        response.append(KnowledgeBaseResponse(**kb_dict))

    return response


@router.post("", response_model=KnowledgeBaseResponse)
async def create_knowledge_base(
    kb_data: KnowledgeBaseCreate, db: AsyncSession = Depends(get_db)
):
    """Create a new knowledge base."""
    # Generate unique collection name
    collection_name = f"kb_{uuid.uuid4().hex[:12]}"

    kb = KnowledgeBase(
        name=kb_data.name,
        description=kb_data.description,
        collection_name=collection_name,
        is_active=kb_data.is_active,
    )

    db.add(kb)
    await db.commit()
    await db.refresh(kb)

    # Create ChromaDB collection
    from backend.services.vector_store import VectorStore

    settings = get_settings()
    vector_store = VectorStore(
        persist_dir=settings.chroma_persist_dir,
        embedding_model=settings.embedding_model,
    )
    vector_store.create_collection(collection_name)

    logger.info(f"Created knowledge base: {kb.name} (ID: {kb.id})")

    return KnowledgeBaseResponse(
        id=kb.id,
        name=kb.name,
        description=kb.description,
        collection_name=kb.collection_name,
        is_active=kb.is_active,
        created_at=kb.created_at,
        updated_at=kb.updated_at,
        document_count=0,
    )


@router.get("/{kb_id}", response_model=KnowledgeBaseResponse)
async def get_knowledge_base(kb_id: int, db: AsyncSession = Depends(get_db)):
    """Get knowledge base details."""
    result = await db.execute(select(KnowledgeBase).where(KnowledgeBase.id == kb_id))
    kb = result.scalar_one_or_none()

    if not kb:
        raise HTTPException(status_code=404, detail="Knowledge base not found")

    # Get document count
    count_result = await db.execute(
        select(func.count(Document.id)).where(Document.kb_id == kb_id)
    )
    doc_count = count_result.scalar()

    return KnowledgeBaseResponse(
        id=kb.id,
        name=kb.name,
        description=kb.description,
        collection_name=kb.collection_name,
        is_active=kb.is_active,
        created_at=kb.created_at,
        updated_at=kb.updated_at,
        document_count=doc_count,
    )


@router.put("/{kb_id}", response_model=KnowledgeBaseResponse)
async def update_knowledge_base(
    kb_id: int, kb_data: KnowledgeBaseUpdate, db: AsyncSession = Depends(get_db)
):
    """Update knowledge base."""
    result = await db.execute(select(KnowledgeBase).where(KnowledgeBase.id == kb_id))
    kb = result.scalar_one_or_none()

    if not kb:
        raise HTTPException(status_code=404, detail="Knowledge base not found")

    if kb_data.name is not None:
        kb.name = kb_data.name
    if kb_data.description is not None:
        kb.description = kb_data.description
    if kb_data.is_active is not None:
        kb.is_active = kb_data.is_active

    await db.commit()
    await db.refresh(kb)

    # Get document count
    count_result = await db.execute(
        select(func.count(Document.id)).where(Document.kb_id == kb_id)
    )
    doc_count = count_result.scalar()

    return KnowledgeBaseResponse(
        id=kb.id,
        name=kb.name,
        description=kb.description,
        collection_name=kb.collection_name,
        is_active=kb.is_active,
        created_at=kb.created_at,
        updated_at=kb.updated_at,
        document_count=doc_count,
    )


@router.delete("/{kb_id}")
async def delete_knowledge_base(kb_id: int, db: AsyncSession = Depends(get_db)):
    """Delete knowledge base and all documents."""
    result = await db.execute(select(KnowledgeBase).where(KnowledgeBase.id == kb_id))
    kb = result.scalar_one_or_none()

    if not kb:
        raise HTTPException(status_code=404, detail="Knowledge base not found")

    # Delete ChromaDB collection
    from backend.services.vector_store import VectorStore

    settings = get_settings()
    vector_store = VectorStore(
        persist_dir=settings.chroma_persist_dir,
        embedding_model=settings.embedding_model,
    )
    try:
        vector_store.delete_collection(kb.collection_name)
    except Exception as e:
        logger.warning(f"Error deleting ChromaDB collection: {e}")

    # Delete document files
    result = await db.execute(select(Document).where(Document.kb_id == kb_id))
    docs = result.scalars().all()
    for doc in docs:
        try:
            Path(doc.file_path).unlink(missing_ok=True)
        except Exception as e:
            logger.warning(f"Error deleting file {doc.file_path}: {e}")

    # Delete documents from database
    await db.execute(delete(Document).where(Document.kb_id == kb_id))

    # Delete knowledge base
    await db.delete(kb)
    await db.commit()

    logger.info(f"Deleted knowledge base {kb_id}")
    return {"message": "Knowledge base deleted successfully"}


@router.get("/{kb_id}/documents", response_model=List[DocumentResponse])
async def list_documents(kb_id: int, db: AsyncSession = Depends(get_db)):
    """List documents in knowledge base."""
    # Verify KB exists
    result = await db.execute(select(KnowledgeBase).where(KnowledgeBase.id == kb_id))
    kb = result.scalar_one_or_none()
    if not kb:
        raise HTTPException(status_code=404, detail="Knowledge base not found")

    # Get documents
    result = await db.execute(
        select(Document).where(Document.kb_id == kb_id).order_by(Document.created_at.desc())
    )
    docs = result.scalars().all()

    return [DocumentResponse.model_validate(doc) for doc in docs]


@router.post("/{kb_id}/documents", response_model=DocumentUploadResponse)
async def upload_document(
    kb_id: int, file: UploadFile = File(...), db: AsyncSession = Depends(get_db)
):
    """Upload a document to knowledge base."""
    # Verify KB exists
    result = await db.execute(select(KnowledgeBase).where(KnowledgeBase.id == kb_id))
    kb = result.scalar_one_or_none()
    if not kb:
        raise HTTPException(status_code=404, detail="Knowledge base not found")

    # Validate file extension
    file_ext = Path(file.filename).suffix.lower()
    if file_ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"File type not allowed. Allowed types: {', '.join(ALLOWED_EXTENSIONS)}",
        )

    # Read file content
    content = await file.read()
    file_size = len(content)

    # Validate file size
    if file_size > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=400, detail=f"File too large. Maximum size: 50MB"
        )

    # Create storage directory
    settings = get_settings()
    kb_dir = Path(settings.knowledge_base_dir) / str(kb_id)
    kb_dir.mkdir(parents=True, exist_ok=True)

    # Save file with UUID prefix
    file_uuid = uuid.uuid4().hex[:8]
    safe_filename = f"{file_uuid}_{file.filename}"
    file_path = kb_dir / safe_filename

    with open(file_path, "wb") as f:
        f.write(content)

    # Create document record
    doc = Document(
        kb_id=kb_id,
        filename=file.filename,
        file_type=file_ext[1:],  # Remove leading dot
        file_path=str(file_path),
        file_size=file_size,
        status="pending",
    )

    db.add(doc)
    await db.commit()
    await db.refresh(doc)

    logger.info(f"Uploaded document {doc.filename} to KB {kb_id}")

    # Trigger background processing
    from backend.app import kb_processor
    import asyncio

    asyncio.create_task(kb_processor.process_pending_documents())

    return DocumentUploadResponse(
        id=doc.id, filename=doc.filename, status=doc.status
    )


@router.delete("/{kb_id}/documents/{doc_id}")
async def delete_document(
    kb_id: int, doc_id: int, db: AsyncSession = Depends(get_db)
):
    """Delete a document from knowledge base."""
    result = await db.execute(
        select(Document).where(Document.id == doc_id, Document.kb_id == kb_id)
    )
    doc = result.scalar_one_or_none()

    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    # Get KB for collection name
    result = await db.execute(select(KnowledgeBase).where(KnowledgeBase.id == kb_id))
    kb = result.scalar_one_or_none()

    if kb:
        # Delete from vector store
        from backend.services.vector_store import VectorStore

        settings = get_settings()
        vector_store = VectorStore(
            persist_dir=settings.chroma_persist_dir,
            embedding_model=settings.embedding_model,
        )
        try:
            vector_store.delete_document(kb.collection_name, doc_id)
        except Exception as e:
            logger.warning(f"Error deleting document from vector store: {e}")

    # Delete file
    try:
        Path(doc.file_path).unlink(missing_ok=True)
    except Exception as e:
        logger.warning(f"Error deleting file {doc.file_path}: {e}")

    # Delete from database
    await db.delete(doc)
    await db.commit()

    logger.info(f"Deleted document {doc_id} from KB {kb_id}")
    return {"message": "Document deleted successfully"}


@router.get("/{kb_id}/documents/{doc_id}/content")
async def get_document_content(kb_id: int, doc_id: int, db: AsyncSession = Depends(get_db)):
    """Get document content for preview."""
    result = await db.execute(
        select(Document).where(Document.id == doc_id, Document.kb_id == kb_id)
    )
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    file_path = Path(doc.file_path)
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found on disk")

    if doc.file_type == "pdf":
        return FileResponse(file_path, media_type="application/pdf")

    try:
        content = file_path.read_text(encoding="utf-8")
        return {"content": content, "file_type": doc.file_type, "filename": doc.filename}
    except UnicodeDecodeError:
        try:
            content = file_path.read_text(encoding="latin-1")
            return {"content": content, "file_type": doc.file_type, "filename": doc.filename}
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to read file: {str(e)}")
