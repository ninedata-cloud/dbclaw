# backend/services/document_service.py
import re
from typing import List, Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import HTTPException

from backend.models.document import DocCategory, DocDocument
from backend.models.soft_delete import alive_filter, get_alive_by_id
from backend.schemas.document import DocDocumentCreate, DocDocumentUpdate


def auto_summary(content: str) -> str:
    """从 Markdown 内容自动提取摘要（取前 150 字可读文本）"""
    text = re.sub(r'```[\s\S]*?```', '', content)
    text = re.sub(r'#{1,6}\s+', '', text)
    text = re.sub(r'`[^`]+`', '', text)
    text = re.sub(r'\*{1,3}([^*]+)\*{1,3}', r'\1', text)
    text = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', text)
    text = re.sub(r'^[-*+>|\s]+', '', text, flags=re.MULTILINE)
    text = re.sub(r'\n+', ' ', text).strip()
    return (text[:150].rstrip() + '...') if len(text) > 150 else text


async def get_category_tree(db: AsyncSession, db_type: Optional[str] = None):
    q = select(DocCategory).where(DocCategory.parent_id == None).order_by(DocCategory.sort_order)
    if db_type:
        q = q.where(DocCategory.db_type == db_type)
    result = await db.execute(q)
    roots = list(result.scalars().all())
    for cat in roots:
        ch = await db.execute(
            select(DocCategory).where(DocCategory.parent_id == cat.id).order_by(DocCategory.sort_order)
        )
        cat._children = list(ch.scalars().all())
    return roots


async def list_documents_by_category(db: AsyncSession, category_id: int):
    result = await db.execute(
        select(DocDocument)
        .where(DocDocument.category_id == category_id, DocDocument.is_active == True, alive_filter(DocDocument))
        .order_by(DocDocument.sort_order)
    )
    return result.scalars().all()


async def list_documents_for_ai(db: AsyncSession, db_type: Optional[str] = None) -> List[dict]:
    """返回文档目录（不含完整 content），供 AI list_documents 工具使用"""
    q = (
        select(DocDocument, DocCategory.name.label("cat_name"), DocCategory.db_type.label("cat_db_type"))
        .join(DocCategory, DocDocument.category_id == DocCategory.id)
        .where(DocDocument.is_active == True, alive_filter(DocDocument))
    )
    if db_type:
        q = q.where(DocCategory.db_type == db_type)
    q = q.order_by(DocCategory.sort_order, DocDocument.sort_order)
    result = await db.execute(q)
    return [
        {
            "id": row.DocDocument.id,
            "title": row.DocDocument.title,
            "summary": row.DocDocument.summary or "",
            "category_name": row.cat_name,
            "db_type": row.cat_db_type,
        }
        for row in result.all()
    ]


async def get_document(db: AsyncSession, doc_id: int) -> DocDocument:
    doc = await get_alive_by_id(db, DocDocument, doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="文档不存在")
    return doc


async def create_document(db: AsyncSession, data: DocDocumentCreate, user_id: int) -> DocDocument:
    summary = data.summary or auto_summary(data.content)
    doc = DocDocument(
        category_id=data.category_id,
        title=data.title,
        content=data.content,
        summary=summary,
        sort_order=data.sort_order,
        created_by=user_id,
    )
    db.add(doc)
    await db.commit()
    await db.refresh(doc)
    return doc


async def update_document(db: AsyncSession, doc_id: int, data: DocDocumentUpdate) -> DocDocument:
    doc = await get_document(db, doc_id)
    update_data = data.model_dump(exclude_none=True)
    for field, value in update_data.items():
        setattr(doc, field, value)
    if 'content' in update_data and 'summary' not in update_data:
        doc.summary = auto_summary(update_data['content'])
    await db.commit()
    await db.refresh(doc)
    return doc


async def delete_document(db: AsyncSession, doc_id: int, user_id: int | None = None):
    doc = await get_document(db, doc_id)
    if doc.is_builtin:
        raise HTTPException(status_code=403, detail="内置文档不可删除")
    doc.soft_delete(user_id)
    await db.commit()
