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
from backend.services.builtin_docs.oceanbase_mysql_docs import OCEANBASE_MYSQL_DOCS
from backend.services.builtin_docs.english_docs import ENGLISH_DOCS_MAP

logger = logging.getLogger(__name__)

# 一级分类（数据库类型）
DB_TYPES = [
    {"db_type": "mysql",      "name": "MySQL"},
    {"db_type": "oceanbase-mysql", "name": "OceanBase MySQL"},
    {"db_type": "postgresql", "name": "PostgreSQL"},
    {"db_type": "oracle",     "name": "Oracle"},
    {"db_type": "sqlserver",  "name": "SQL Server"},
]

# 二级分类（诊断场景）
SCENARIO_CATEGORIES = [
    "综合诊断", "性能诊断", "故障排查", "配置与会话", "安全与权限", "技术参考"
]
SCENARIO_CODES = {
    "综合诊断": "general-diagnostics",
    "性能诊断": "performance-diagnostics",
    "故障排查": "troubleshooting",
    "配置与会话": "configuration-sessions",
    "安全与权限": "security-permissions",
    "技术参考": "technical-reference",
}
SCENARIO_NAMES = {
    "zh-CN": {code: name for name, code in SCENARIO_CODES.items()},
    "en-US": {
        "general-diagnostics": "General diagnostics",
        "performance-diagnostics": "Performance diagnostics",
        "troubleshooting": "Troubleshooting",
        "configuration-sessions": "Configuration and sessions",
        "security-permissions": "Security and permissions",
        "technical-reference": "Technical reference",
    },
}

DOCS_MAP = {
    "mysql":      MYSQL_DOCS,
    "oceanbase-mysql": OCEANBASE_MYSQL_DOCS,
    "postgresql": POSTGRESQL_DOCS,
    "oracle":     ORACLE_DOCS,
    "sqlserver":  SQLSERVER_DOCS,
}

ISSUE_CATEGORIES = {
    "general-diagnostics": ["general", "performance"],
    "performance-diagnostics": ["performance", "sql", "resource"],
    "troubleshooting": ["error", "connectivity", "locking", "replication"],
    "configuration-sessions": ["configuration", "connectivity"],
    "security-permissions": ["error", "configuration"],
    "technical-reference": ["general"],
}


async def seed_builtin_docs(db: AsyncSession):
    """Idempotently seed independent Chinese and English built-in documents."""
    logger.info("Synchronizing bilingual built-in docs...")
    category_map = {}  # (db_type, scenario_code) -> category_id

    for sort_i, db_type_def in enumerate(DB_TYPES):
        db_type = db_type_def["db_type"]
        root_result = await db.execute(
            select(DocCategory).where(
                DocCategory.db_type == db_type,
                DocCategory.parent_id.is_(None),
            ).order_by(DocCategory.id.asc())
        )
        root_cat = root_result.scalars().first()
        if root_cat is None:
            root_cat = DocCategory(db_type=db_type, parent_id=None)
            db.add(root_cat)
        root_cat.name = db_type_def["name"]
        root_cat.code = f"database.{db_type}"
        root_cat.sort_order = sort_i
        await db.flush()

        for sort_j, scenario in enumerate(SCENARIO_CATEGORIES):
            scenario_code = SCENARIO_CODES[scenario]
            child_result = await db.execute(
                select(DocCategory).where(
                    DocCategory.db_type == db_type,
                    DocCategory.parent_id == root_cat.id,
                    DocCategory.code == f"scenario.{scenario_code}",
                ).order_by(DocCategory.id.asc())
            )
            child_cat = child_result.scalars().first()
            if child_cat is None:
                # Compatibility with categories created before stable codes.
                legacy_result = await db.execute(
                    select(DocCategory).where(
                        DocCategory.db_type == db_type,
                        DocCategory.parent_id == root_cat.id,
                        DocCategory.name == scenario,
                    ).order_by(DocCategory.id.asc())
                )
                child_cat = legacy_result.scalars().first()
            if child_cat is None:
                child_cat = DocCategory(db_type=db_type, parent_id=root_cat.id)
                db.add(child_cat)
            child_cat.name = scenario
            child_cat.code = f"scenario.{scenario_code}"
            child_cat.sort_order = sort_j
            await db.flush()
            category_map[(db_type, scenario_code)] = child_cat.id

    synchronized = 0
    for locale, localized_map in (("zh-CN", DOCS_MAP), ("en-US", ENGLISH_DOCS_MAP)):
        for db_type, docs in localized_map.items():
            expected_count = len(DOCS_MAP[db_type])
            if len(docs) != expected_count:
                raise ValueError(f"Incomplete {locale} built-in document set for {db_type}")
            for sort_k, doc_def in enumerate(docs):
                scenario_code = doc_def.get("category_code") or SCENARIO_CODES[doc_def["category"]]
                cat_id = category_map[(db_type, scenario_code)]
                group_id = f"builtin:{db_type}:{sort_k}"
                existing_result = await db.execute(
                    select(DocDocument).where(
                        DocDocument.is_builtin == True,
                        DocDocument.translation_group_id == group_id,
                        DocDocument.content_locale == locale,
                    ).order_by(DocDocument.id.asc())
                )
                doc = existing_result.scalars().first()
                if doc is None and locale == "zh-CN":
                    legacy_result = await db.execute(
                        select(DocDocument).where(
                            DocDocument.is_builtin == True,
                            DocDocument.category_id == cat_id,
                            DocDocument.sort_order == sort_k,
                            DocDocument.content_locale == "zh-CN",
                        ).order_by(DocDocument.id.asc())
                    )
                    doc = legacy_result.scalars().first()
                if doc is None:
                    doc = DocDocument(is_builtin=True)
                    db.add(doc)

                content = doc_def["content"]
                doc.category_id = cat_id
                doc.title = doc_def["title"]
                doc.content = content
                doc.content_locale = locale
                doc.translation_group_id = group_id
                doc.summary = auto_summary(content)
                doc.is_active = True
                doc.scope = "builtin"
                doc.doc_kind = "reference" if scenario_code == "technical-reference" else ("sop" if scenario_code == "general-diagnostics" else "runbook")
                doc.db_types = [db_type]
                doc.issue_categories = ISSUE_CATEGORIES[scenario_code]
                doc.tags = [db_type, SCENARIO_NAMES[locale][scenario_code]]
                doc.freshness_level = "stable"
                doc.enabled_in_diagnosis = True
                doc.sort_order = sort_k
                synchronized += 1

    await db.commit()
    logger.info("Synchronized %s bilingual built-in document records", synchronized)
