# backend/routers/documents.py
import logging
from typing import List, Optional
from urllib.parse import quote
from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from sqlalchemy import select
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
from backend.i18n.locale import get_active_locale, message_payload

logger = logging.getLogger(__name__)
router = APIRouter(
    prefix="/api/docs",
    tags=["documents"],
    dependencies=[Depends(get_current_user)],
)

CATEGORY_NAMES = {
    "zh-CN": {
        "scenario.general-diagnostics": "综合诊断",
        "scenario.performance-diagnostics": "性能诊断",
        "scenario.troubleshooting": "故障排查",
        "scenario.configuration-sessions": "配置与会话",
        "scenario.security-permissions": "安全与权限",
        "scenario.technical-reference": "技术参考",
    },
    "en-US": {
        "scenario.general-diagnostics": "General diagnostics",
        "scenario.performance-diagnostics": "Performance diagnostics",
        "scenario.troubleshooting": "Troubleshooting",
        "scenario.configuration-sessions": "Configuration and sessions",
        "scenario.security-permissions": "Security and permissions",
        "scenario.technical-reference": "Technical reference",
    },
}


def _category_name(category: DocCategory) -> str:
    return CATEGORY_NAMES.get(get_active_locale(), {}).get(category.code, category.name)


async def _localized_document_count(db: AsyncSession, category_id: int) -> int:
    result = await db.execute(
        select(DocDocument).where(
            DocDocument.category_id == category_id,
            DocDocument.is_active == True,
            alive_filter(DocDocument),
        )
    )
    return len(document_service.select_document_translations(result.scalars().all(), get_active_locale()))


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
            ch_count = await _localized_document_count(db, ch.id)
            children_resp.append(DocCategoryResponse.model_validate({
                **{c.key: getattr(ch, c.key) for c in ch.__table__.columns},
                "name": _category_name(ch), "children": [], "document_count": ch_count,
            }))
        cat_count = await _localized_document_count(db, cat.id)
        response.append(DocCategoryResponse.model_validate({
            **{c.key: getattr(cat, c.key) for c in cat.__table__.columns},
            "name": _category_name(cat), "children": children_resp, "document_count": cat_count,
        }))
    return response


@router.get("/categories/{category_id}/documents", response_model=List[DocDocumentListItem])
async def list_documents(category_id: int, response: Response, db: AsyncSession = Depends(get_db)):
    documents = await document_service.list_documents_by_category(db, category_id)
    locales = {doc.content_locale for doc in documents}
    response.headers["Content-Language"] = next(iter(locales)) if len(locales) == 1 else "und"
    return documents


@router.get("/{doc_id}/export")
async def export_document(doc_id: int, db: AsyncSession = Depends(get_db)):
    doc = await document_service.get_document(db, doc_id)
    filename = doc.title.replace('/', '_') + ".md"
    encoded_filename = quote(filename, safe="")
    return Response(
        content=doc.content.encode('utf-8'),
        media_type="text/markdown",
        headers={
            "Content-Disposition": (
                f'attachment; filename="document_{doc.id}.md"; '
                f"filename*=UTF-8''{encoded_filename}"
            ),
            "Content-Language": doc.content_locale,
        },
    )


@router.get("/{doc_id}", response_model=DocDocumentResponse)
async def get_document(doc_id: int, response: Response, db: AsyncSession = Depends(get_db)):
    document = await document_service.get_document(db, doc_id)
    response.headers["Content-Language"] = document.content_locale
    return document


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
    return message_payload("document.deleted")
