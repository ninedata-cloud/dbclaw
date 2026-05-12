"""Bootstrap a built-in 'MySQL standard suite' on first startup."""
from __future__ import annotations

import logging

from sqlalchemy import select

from backend.evaluation.case_loader import load_all_cases
from backend.models.evaluation import EvalSuite

logger = logging.getLogger(__name__)

BUILTIN_SUITE_NAME = "MySQL 标准套件"
BUILTIN_SUITE_DESCRIPTION = (
    "覆盖 MySQL 慢查询、索引、锁、CPU、内存、磁盘、复制、连接等核心故障类别的标准评测套件。"
)


async def ensure_builtin_suite(db) -> EvalSuite:
    """Create or refresh the built-in suite (synchronizes case_ids with disk)."""
    cases = load_all_cases()
    case_ids = sorted([cid for cid, c in cases.items() if c.db_type == "mysql"])

    result = await db.execute(
        select(EvalSuite).filter(EvalSuite.name == BUILTIN_SUITE_NAME)
    )
    suite = result.scalar_one_or_none()
    if suite is None:
        suite = EvalSuite(
            name=BUILTIN_SUITE_NAME,
            description=BUILTIN_SUITE_DESCRIPTION,
            case_ids=case_ids,
            is_builtin="yes",
        )
        db.add(suite)
        await db.commit()
        await db.refresh(suite)
        logger.info("Created built-in eval suite with %d cases", len(case_ids))
        return suite

    if list(suite.case_ids or []) != case_ids:
        suite.case_ids = case_ids
        suite.description = BUILTIN_SUITE_DESCRIPTION
        await db.commit()
        logger.info("Refreshed built-in eval suite case list (%d cases)", len(case_ids))

    return suite
