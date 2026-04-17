# backend/routers/documents.py
import logging
from typing import List, Optional
from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_db
from backend.dependencies import get_current_user
from backend.models.user import User
from backend.models.document import DocCategory, DocDocument
from backend.models.soft_delete import alive_filter
from backend.services import document_service
from backend.schemas.document import (
    DocCategoryResponse, DocCategoryCreate,
    DocDocumentCreate, DocDocumentUpdate,
    DocDocumentListItem, DocDocumentResponse,
)

logger = logging.getLogger(__name__)
router = APIRouter(
    prefix="/api/docs",
    tags=["documents"],
    dependencies=[Depends(get_current_user)],
)


@router.get("/categories", response_model=List[DocCategoryResponse])
async def get_categories(
    db_type: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    roots = await document_service.get_category_tree(db, db_type)
    response = []
    for cat in roots:
        children = getattr(cat, '_children', [])
        children_resp = []
        for ch in children:
            count_result = await db.execute(
                select(func.count(DocDocument.id))
                .where(DocDocument.category_id == ch.id, DocDocument.is_active == True, alive_filter(DocDocument))
            )
            ch_count = count_result.scalar() or 0
            children_resp.append(DocCategoryResponse.model_validate({
                **{c.key: getattr(ch, c.key) for c in ch.__table__.columns},
                "children": [], "document_count": ch_count,
            }))
        count_result = await db.execute(
            select(func.count(DocDocument.id))
            .where(DocDocument.category_id == cat.id, DocDocument.is_active == True, alive_filter(DocDocument))
        )
        cat_count = count_result.scalar() or 0
        response.append(DocCategoryResponse.model_validate({
            **{c.key: getattr(cat, c.key) for c in cat.__table__.columns},
            "children": children_resp, "document_count": cat_count,
        }))
    return response


@router.get("/categories/{category_id}/documents", response_model=List[DocDocumentListItem])
async def list_documents(category_id: int, db: AsyncSession = Depends(get_db)):
    return await document_service.list_documents_by_category(db, category_id)


@router.get("/{doc_id}/export")
async def export_document(doc_id: int, db: AsyncSession = Depends(get_db)):
    doc = await document_service.get_document(db, doc_id)
    filename = doc.title.replace('/', '_') + ".md"
    return Response(
        content=doc.content.encode('utf-8'),
        media_type="text/markdown",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/{doc_id}", response_model=DocDocumentResponse)
async def get_document(doc_id: int, db: AsyncSession = Depends(get_db)):
    return await document_service.get_document(db, doc_id)


@router.post("", response_model=DocDocumentResponse)
async def create_document(
    data: DocDocumentCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await document_service.create_document(db, data, current_user.id)


@router.put("/{doc_id}", response_model=DocDocumentResponse)
async def update_document(
    doc_id: int,
    data: DocDocumentUpdate,
    db: AsyncSession = Depends(get_db),
):
    return await document_service.update_document(db, doc_id, data)


@router.post("/{doc_id}/recompile", response_model=DocDocumentResponse)
async def recompile_document(
    doc_id: int,
    db: AsyncSession = Depends(get_db),
):
    return await document_service.recompile_document(db, doc_id)


@router.delete("/{doc_id}")
async def delete_document(
    doc_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await document_service.delete_document(db, doc_id, current_user.id)
    return {"message": "文档已删除"}
