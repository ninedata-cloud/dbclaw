import logging

from sqlalchemy import text

from backend.database import get_engine

logger = logging.getLogger(__name__)


FOREIGN_KEYS = [
    {
        "table": "user_sessions",
        "column": "user_id",
        "name": "user_sessions_user_id_fkey",
        "reference": "users(id)",
        "on_delete": "CASCADE",
    },
    {
        "table": "doc_categories",
        "column": "parent_id",
        "name": "doc_categories_parent_id_fkey",
        "reference": "doc_categories(id)",
        "on_delete": "SET NULL",
    },
    {
        "table": "doc_documents",
        "column": "category_id",
        "name": "doc_documents_category_id_fkey",
        "reference": "doc_categories(id)",
        "on_delete": "RESTRICT",
    },
]


async def _table_exists(conn, table_name: str) -> bool:
    result = await conn.execute(
        text(
            """
            SELECT EXISTS (
                SELECT 1
                FROM information_schema.tables
                WHERE table_schema = current_schema() AND table_name = :table_name
            )
            """
        ),
        {"table_name": table_name},
    )
    return bool(result.scalar_one())


async def _get_fk_constraints(conn, table_name: str, column_name: str) -> list[tuple[str, str]]:
    result = await conn.execute(
        text(
            """
            SELECT tc.constraint_name,
                   pg_get_constraintdef(c.oid) AS definition
            FROM information_schema.table_constraints tc
            JOIN information_schema.key_column_usage kcu
              ON tc.constraint_name = kcu.constraint_name
             AND tc.table_schema = kcu.table_schema
            JOIN pg_constraint c
              ON c.conname = tc.constraint_name
            JOIN pg_namespace n
              ON n.oid = c.connamespace
             AND n.nspname = tc.table_schema
            WHERE tc.table_schema = current_schema()
              AND tc.table_name = :table_name
              AND tc.constraint_type = 'FOREIGN KEY'
              AND kcu.column_name = :column_name
            ORDER BY tc.constraint_name
            """
        ),
        {"table_name": table_name, "column_name": column_name},
    )
    return [(row[0], row[1]) for row in result.fetchall()]


async def _ensure_foreign_key(conn, spec: dict[str, str]) -> None:
    if not await _table_exists(conn, spec["table"]):
        logger.info("Skip foreign key for %s because table is missing", spec["table"])
        return

    existing = await _get_fk_constraints(conn, spec["table"], spec["column"])
    expected_fragment = f"FOREIGN KEY ({spec['column']}) REFERENCES {spec['reference']} ON DELETE {spec['on_delete']}"

    if any(expected_fragment in definition for _, definition in existing):
        return

    for constraint_name, _ in existing:
        logger.info("Dropping outdated foreign key %s.%s", spec["table"], constraint_name)
        await conn.execute(
            text(
                f'ALTER TABLE "{spec["table"]}" DROP CONSTRAINT IF EXISTS "{constraint_name}"'
            )
        )

    logger.info("Creating foreign key %s on %s.%s", spec["name"], spec["table"], spec["column"])
    await conn.execute(
        text(
            f'''
            ALTER TABLE "{spec["table"]}"
            ADD CONSTRAINT "{spec["name"]}"
            FOREIGN KEY ({spec["column"]})
            REFERENCES {spec["reference"]}
            ON DELETE {spec["on_delete"]}
            '''
        )
    )


async def migrate():
    async with get_engine().begin() as conn:
        for spec in FOREIGN_KEYS:
            await _ensure_foreign_key(conn, spec)

    logger.info("Core foreign keys normalized")
