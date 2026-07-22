import re
from typing import List, Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.document import DocCategory, DocDocument
from backend.models.soft_delete import alive_filter, get_alive_by_id
from backend.schemas.document import DocDocumentCreate, DocDocumentUpdate
from backend.services.knowledge_compiler import compile_document_knowledge, normalize_diagnosis_profile
from backend.skills.registry import SkillRegistry
from backend.i18n.locale import DEFAULT_LOCALE, get_active_locale
from backend.i18n.errors import ApiError


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


async def _get_valid_skill_ids(db: AsyncSession) -> set[str]:
    registry = SkillRegistry(db)
    skills = await registry.list_skills(is_enabled=True)
    valid_skill_ids = {skill.id for skill in skills}
    valid_skill_ids.update({"list_documents", "read_document", "list_connections"})
    return valid_skill_ids


def _document_needs_compilation(doc: DocDocument) -> bool:
    if not doc.compiled_snapshot or not doc.compiled_at:
        return True
    if not doc.quality_status:
        return True
    if not doc.diagnosis_profile:
        return True
    return False


def _apply_compiled_fields(doc: DocDocument, compiled: dict) -> None:
    doc.diagnosis_profile = compiled["diagnosis_profile"]
    doc.compiled_snapshot = compiled["compiled_snapshot"]
    doc.compiled_at = compiled["compiled_at"]
    doc.quality_status = compiled["quality_status"]


async def compile_document_record(
    db: AsyncSession,
    doc: DocDocument,
    *,
    valid_skill_ids: set[str] | None = None,
    commit: bool = False,
) -> DocDocument:
    valid_skill_ids = valid_skill_ids or await _get_valid_skill_ids(db)
    compiled = compile_document_knowledge(
        title=doc.title,
        content=doc.content,
        diagnosis_profile=doc.diagnosis_profile,
        tags=doc.tags,
        db_types=doc.db_types,
        freshness_level=doc.freshness_level,
        valid_skill_ids=valid_skill_ids,
    )
    _apply_compiled_fields(doc, compiled)
    if commit:
        await db.commit()
        await db.refresh(doc)
    return doc


async def ensure_document_compiled(
    db: AsyncSession,
    doc: DocDocument,
    *,
    valid_skill_ids: set[str] | None = None,
    commit: bool = False,
) -> DocDocument:
    if not _document_needs_compilation(doc):
        doc.diagnosis_profile = normalize_diagnosis_profile(doc.diagnosis_profile)
        return doc
    return await compile_document_record(db, doc, valid_skill_ids=valid_skill_ids, commit=commit)


async def backfill_document_compilation(db: AsyncSession, limit: int = 200) -> int:
    valid_skill_ids = await _get_valid_skill_ids(db)
    result = await db.execute(
        select(DocDocument)
        .where(DocDocument.is_active == True, alive_filter(DocDocument))
        .order_by(DocDocument.id.asc())
        .limit(limit)
    )
    docs = result.scalars().all()
    updated = 0
    for doc in docs:
        if not _document_needs_compilation(doc):
            continue
        await compile_document_record(db, doc, valid_skill_ids=valid_skill_ids, commit=False)
        updated += 1
    if updated:
        await db.commit()
    return updated


async def list_documents_by_category(db: AsyncSession, category_id: int):
    result = await db.execute(
        select(DocDocument)
        .where(DocDocument.category_id == category_id, DocDocument.is_active == True, alive_filter(DocDocument))
        .order_by(DocDocument.sort_order)
    )
    docs = select_document_translations(result.scalars().all(), get_active_locale())
    valid_skill_ids = await _get_valid_skill_ids(db)
    dirty = False
    for doc in docs:
        if _document_needs_compilation(doc):
            await compile_document_record(db, doc, valid_skill_ids=valid_skill_ids, commit=False)
            dirty = True
        else:
            doc.diagnosis_profile = normalize_diagnosis_profile(doc.diagnosis_profile)
    if dirty:
        await db.commit()
    return docs


def select_document_translations(documents, locale: str):
    """Choose one built-in translation per group; user documents remain untouched."""
    documents = list(documents)
    grouped: dict[str, list] = {}
    for doc in documents:
        group_id = getattr(doc, "translation_group_id", None)
        if getattr(doc, "is_builtin", False) and group_id:
            grouped.setdefault(group_id, []).append(doc)
    choices = {}
    for group_id, variants in grouped.items():
        preferred = next((doc for doc in variants if doc.content_locale == locale), None)
        fallback = next((doc for doc in variants if doc.content_locale == DEFAULT_LOCALE), None)
        choices[group_id] = preferred or fallback or variants[0]

    selected = []
    emitted = set()
    for doc in documents:
        group_id = getattr(doc, "translation_group_id", None)
        if group_id in choices:
            if group_id not in emitted:
                selected.append(choices[group_id])
                emitted.add(group_id)
        else:
            selected.append(doc)
    return selected


async def list_documents_for_ai(
    db: AsyncSession,
    db_type: Optional[str] = None,
    locale: Optional[str] = None,
) -> List[dict]:
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
    docs = []
    valid_skill_ids = await _get_valid_skill_ids(db)
    dirty = False
    rows = result.all()
    selected_ids = {
        doc.id for doc in select_document_translations(
            [row.DocDocument for row in rows], locale or get_active_locale()
        )
    }
    for row in rows:
        doc = row.DocDocument
        if doc.id not in selected_ids:
            continue
        if _document_needs_compilation(doc):
            await compile_document_record(db, doc, valid_skill_ids=valid_skill_ids, commit=False)
            dirty = True
        else:
            doc.diagnosis_profile = normalize_diagnosis_profile(doc.diagnosis_profile)
        docs.append(
            {
                "id": doc.id,
                "title": doc.title,
                "summary": doc.summary or "",
                "category_name": row.cat_name,
                "db_type": row.cat_db_type,
                "scope": doc.scope or "builtin",
                "doc_kind": doc.doc_kind or "reference",
                "issue_categories": doc.issue_categories or [],
                "priority": doc.priority or 0,
                "quality_status": doc.quality_status or "draft",
                "diagnosis_profile": doc.diagnosis_profile or normalize_diagnosis_profile(None),
                "compiled_snapshot_summary": doc.compiled_snapshot_summary,
            }
        )
    if dirty:
        await db.commit()
    return docs


async def get_document(db: AsyncSession, doc_id: int) -> DocDocument:
    doc = await get_alive_by_id(db, DocDocument, doc_id)
    if not doc:
            raise ApiError(404, "document.not_found")
    return await ensure_document_compiled(db, doc, commit=True)


async def create_document(db: AsyncSession, data: DocDocumentCreate, user_id: int) -> DocDocument:
    summary = data.summary or auto_summary(data.content)
    category_result = await db.execute(select(DocCategory).where(DocCategory.id == data.category_id))
    category = category_result.scalar_one_or_none()
    doc = DocDocument(
        category_id=data.category_id,
        title=data.title,
        content=data.content,
        content_locale=data.content_locale,
        translation_group_id=data.translation_group_id,
        summary=summary,
        scope=data.scope or "tenant",
        doc_kind=data.doc_kind or "reference",
        db_types=data.db_types or ([category.db_type] if category and category.db_type else None),
        issue_categories=data.issue_categories,
        datasource_ids=data.datasource_ids,
        host_ids=data.host_ids,
        tags=data.tags,
        priority=data.priority,
        freshness_level=data.freshness_level or "stable",
        enabled_in_diagnosis=data.enabled_in_diagnosis,
        diagnosis_profile=normalize_diagnosis_profile(data.diagnosis_profile),
        sort_order=data.sort_order,
        created_by=user_id,
    )
    db.add(doc)
    await db.flush()
    await compile_document_record(db, doc, commit=False)
    await db.commit()
    await db.refresh(doc)
    return doc


async def update_document(db: AsyncSession, doc_id: int, data: DocDocumentUpdate) -> DocDocument:
    doc = await get_document(db, doc_id)
    update_data = data.model_dump(exclude_none=True)
    for field, value in update_data.items():
        if field == "diagnosis_profile":
            value = normalize_diagnosis_profile(value)
        setattr(doc, field, value)
    if 'content' in update_data and 'summary' not in update_data:
        doc.summary = auto_summary(update_data['content'])
    if 'diagnosis_profile' not in update_data:
        doc.diagnosis_profile = normalize_diagnosis_profile(doc.diagnosis_profile)
    await compile_document_record(db, doc, commit=False)
    await db.commit()
    await db.refresh(doc)
    return doc


async def recompile_document(db: AsyncSession, doc_id: int) -> DocDocument:
    doc = await get_document(db, doc_id)
    await compile_document_record(db, doc, commit=False)
    await db.commit()
    await db.refresh(doc)
    return doc


async def delete_document(db: AsyncSession, doc_id: int, user_id: int | None = None):
    doc = await get_document(db, doc_id)
    if doc.is_builtin:
            raise ApiError(403, "operation.not_allowed")
    doc.soft_delete(user_id)
    await db.commit()
