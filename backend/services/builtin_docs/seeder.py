# backend/services/builtin_docs/seeder.py
import logging
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.document import DocCategory, DocDocument
from backend.services.document_service import auto_summary
from backend.services.builtin_docs.mysql_docs import MYSQL_DOCS
from backend.services.builtin_docs.postgresql_docs import POSTGRESQL_DOCS
from backend.services.builtin_docs.oracle_docs import ORACLE_DOCS
from backend.services.builtin_docs.sqlserver_docs import SQLSERVER_DOCS

logger = logging.getLogger(__name__)

# 一级分类（数据库类型）
DB_TYPES = [
    {"db_type": "mysql",      "name": "MySQL"},
    {"db_type": "postgresql", "name": "PostgreSQL"},
    {"db_type": "oracle",     "name": "Oracle"},
    {"db_type": "sqlserver",  "name": "SQL Server"},
]

# 二级分类（诊断场景）
SCENARIO_CATEGORIES = [
    "综合诊断", "性能诊断", "故障排查", "配置与会话", "安全与权限", "技术参考"
]

DOCS_MAP = {
    "mysql":      MYSQL_DOCS,
    "postgresql": POSTGRESQL_DOCS,
    "oracle":     ORACLE_DOCS,
    "sqlserver":  SQLSERVER_DOCS,
}


async def seed_builtin_docs(db: AsyncSession):
    """启动时写入内置文档，已存在则跳过（按是否已有内置文档判断）"""
    existing = await db.execute(
        select(DocDocument).where(DocDocument.is_builtin == True).limit(1)
    )
    if existing.scalar_one_or_none():
        logger.info("Builtin docs already seeded, skipping.")
        return

    logger.info("Seeding builtin docs...")
    category_map = {}  # (db_type, scenario_name) -> category_id

    # 创建一级分类（db 类型）和二级分类（场景）
    for sort_i, db_type_def in enumerate(DB_TYPES):
        db_type = db_type_def["db_type"]
        root_cat = DocCategory(
            name=db_type_def["name"],
            db_type=db_type,
            parent_id=None,
            sort_order=sort_i,
        )
        db.add(root_cat)
        await db.flush()  # 获取 root_cat.id

        for sort_j, scenario in enumerate(SCENARIO_CATEGORIES):
            child_cat = DocCategory(
                name=scenario,
                db_type=db_type,
                parent_id=root_cat.id,
                sort_order=sort_j,
            )
            db.add(child_cat)
            await db.flush()
            category_map[(db_type, scenario)] = child_cat.id

    # 写入文档
    doc_count = 0
    for db_type, docs in DOCS_MAP.items():
        for sort_k, doc_def in enumerate(docs):
            cat_id = category_map.get((db_type, doc_def["category"]))
            if not cat_id:
                logger.warning(f"Unknown category: {doc_def['category']} for {db_type}")
                continue
            content = doc_def["content"]
            doc = DocDocument(
                category_id=cat_id,
                title=doc_def["title"],
                content=content,
                summary=auto_summary(content),
                is_builtin=True,
                is_active=True,
                scope="builtin",
                doc_kind="reference" if doc_def["category"] == "技术参考" else ("sop" if doc_def["category"] == "综合诊断" else "runbook"),
                db_types=[db_type],
                issue_categories={
                    "综合诊断": ["general", "performance"],
                    "性能诊断": ["performance", "sql", "resource"],
                    "故障排查": ["error", "connectivity", "locking", "replication"],
                    "配置与会话": ["configuration", "connectivity"],
                    "安全与权限": ["error", "configuration"],
                    "技术参考": ["general"],
                }.get(doc_def["category"], ["general"]),
                tags=[db_type, doc_def["category"]],
                freshness_level="stable",
                enabled_in_diagnosis=True,
                sort_order=sort_k,
            )
            db.add(doc)
            doc_count += 1

    await db.commit()
    logger.info(f"Seeded {doc_count} builtin docs successfully.")
