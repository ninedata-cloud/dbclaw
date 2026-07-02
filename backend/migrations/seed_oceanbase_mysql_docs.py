"""Seed OceanBase MySQL built-in documents for existing installations."""

import logging

from sqlalchemy import select

from backend.database import async_session
from backend.models.document import DocCategory, DocDocument
from backend.services.builtin_docs.oceanbase_mysql_docs import OCEANBASE_MYSQL_DOCS
from backend.services.builtin_docs.seeder import SCENARIO_CATEGORIES
from backend.services.document_service import auto_summary

logger = logging.getLogger(__name__)

DB_TYPE = "oceanbase-mysql"
ROOT_NAME = "OceanBase MySQL"


async def _get_or_create_category(db, name: str, parent_id: int | None, sort_order: int) -> DocCategory:
    result = await db.execute(
        select(DocCategory).where(
            DocCategory.db_type == DB_TYPE,
            DocCategory.name == name,
            DocCategory.parent_id.is_(None) if parent_id is None else DocCategory.parent_id == parent_id,
        )
    )
    category = result.scalar_one_or_none()
    if category:
        return category

    category = DocCategory(
        name=name,
        db_type=DB_TYPE,
        parent_id=parent_id,
        sort_order=sort_order,
    )
    db.add(category)
    await db.flush()
    return category


async def upgrade():
    async with async_session() as db:
        root = await _get_or_create_category(db, ROOT_NAME, None, 40)
        category_map: dict[str, int] = {}
        for sort_order, scenario in enumerate(SCENARIO_CATEGORIES):
            category = await _get_or_create_category(db, scenario, root.id, sort_order)
            category_map[scenario] = category.id

        inserted = 0
        updated = 0
        for sort_order, doc_def in enumerate(OCEANBASE_MYSQL_DOCS):
            existing = await db.execute(
                select(DocDocument).where(
                    DocDocument.is_builtin == True,
                    DocDocument.title == doc_def["title"],
                )
            )
            existing_doc = existing.scalar_one_or_none()
            category = doc_def["category"]
            if existing_doc:
                existing_doc.category_id = category_map[category]
                existing_doc.content = doc_def["content"]
                existing_doc.summary = auto_summary(doc_def["content"])
                existing_doc.db_types = [DB_TYPE, "oceanbase"]
                existing_doc.tags = [DB_TYPE, "oceanbase", category]
                existing_doc.compiled_snapshot = None
                existing_doc.compiled_at = None
                existing_doc.enabled_in_diagnosis = True
                existing_doc.sort_order = sort_order
                updated += 1
                continue

            doc = DocDocument(
                category_id=category_map[category],
                title=doc_def["title"],
                content=doc_def["content"],
                summary=auto_summary(doc_def["content"]),
                is_builtin=True,
                is_active=True,
                scope="builtin",
                doc_kind="reference" if category == "技术参考" else ("sop" if category == "综合诊断" else "runbook"),
                db_types=[DB_TYPE, "oceanbase"],
                issue_categories={
                    "综合诊断": ["general", "performance"],
                    "性能诊断": ["performance", "sql", "resource"],
                    "故障排查": ["error", "connectivity", "locking", "replication"],
                    "配置与会话": ["configuration", "connectivity"],
                    "安全与权限": ["error", "configuration"],
                    "技术参考": ["general"],
                }.get(category, ["general"]),
                tags=[DB_TYPE, "oceanbase", category],
                freshness_level="stable",
                enabled_in_diagnosis=True,
                sort_order=sort_order,
            )
            db.add(doc)
            inserted += 1

        await db.commit()
        logger.info("Seeded %d and updated %d OceanBase MySQL builtin docs", inserted, updated)


async def downgrade():
    async with async_session() as db:
        result = await db.execute(
            select(DocDocument).where(
                DocDocument.is_builtin == True,
                DocDocument.db_types.contains([DB_TYPE]),
            )
        )
        for doc in result.scalars().all():
            await db.delete(doc)
        await db.commit()


if __name__ == "__main__":
    import asyncio

    async def main():
        await upgrade()
        print("Migration completed successfully")

    asyncio.run(main())
