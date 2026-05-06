"""将 public schema 中仍为 PostgreSQL json 类型的列迁移为 jsonb。

幂等：仅当 information_schema 中 udt_name = 'json' 时执行 ALTER；已为 jsonb 则跳过。
历史数据通过 USING col::jsonb 无损转换；若某单元格非合法 JSON，迁移会失败，需先修复脏数据。
"""
import logging

from sqlalchemy import text

from backend.database import get_engine

logger = logging.getLogger(__name__)


def _quote_ident(name: str) -> str:
    """Quote a PostgreSQL identifier (table/column name)."""
    return '"' + name.replace('"', '""') + '"'


async def upgrade():
    engine = get_engine()

    async with engine.begin() as conn:
        result = await conn.execute(
            text(
                """
                SELECT table_name, column_name
                FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND udt_name = 'json'
                ORDER BY table_name, column_name
                """
            )
        )
        rows = result.fetchall()

        if not rows:
            logger.info("convert_json_columns_to_jsonb: no json columns found; nothing to do")
            return

        logger.info(
            "convert_json_columns_to_jsonb: converting %d column(s) from json to jsonb",
            len(rows),
        )

        for table_name, column_name in rows:
            t = _quote_ident(table_name)
            c = _quote_ident(column_name)
            sql = (
                f"ALTER TABLE {t} ALTER COLUMN {c} TYPE jsonb USING {c}::jsonb"
            )
            await conn.execute(text(sql))
            logger.info(
                "convert_json_columns_to_jsonb: altered %s.%s -> jsonb",
                table_name,
                column_name,
            )


async def downgrade():
    """未实现：将 jsonb 改回 json 需按表逐列执行，且一般不需要回滚。"""
    logger.warning(
        "convert_json_columns_to_jsonb: downgrade is a no-op; "
        "to revert, run per column: ALTER TABLE t ALTER COLUMN c TYPE json USING c::json"
    )


if __name__ == "__main__":
    import asyncio

    async def main():
        await upgrade()
        print("Migration completed successfully")

    asyncio.run(main())
