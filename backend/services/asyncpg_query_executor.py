import re
import time
from typing import Any, Dict
from inspect import isawaitable


def _strip_leading_comments(sql: str) -> str:
    text = sql.lstrip()
    while True:
        if text.startswith("/*"):
            end = text.find("*/")
            if end == -1:
                return ""
            text = text[end + 2 :].lstrip()
            continue
        if text.startswith("--"):
            end = text.find("\n")
            if end == -1:
                return ""
            text = text[end + 1 :].lstrip()
            continue
        return text


def _extract_row_count(command_tag: str) -> int:
    numbers = re.findall(r"\d+", command_tag or "")
    return int(numbers[-1]) if numbers else 0


def _record_to_list(row: Any) -> list[Any]:
    if hasattr(row, "values"):
        return list(row.values())
    if isinstance(row, (list, tuple)):
        return list(row)
    return [row]


async def execute_asyncpg_query(
    conn,
    sql: str,
    *,
    max_rows: int = 1000,
    explain_uses_fetch: bool = False,
) -> Dict[str, Any]:
    start = time.time()
    prepared = await conn.prepare(sql)
    columns = [attr.name for attr in (prepared.get_attributes() or [])]

    if columns:
        leading = _strip_leading_comments(sql).upper()
        if explain_uses_fetch and leading.startswith("EXPLAIN"):
            rows = await conn.fetch(sql)
        else:
            transaction = conn.transaction()
            if isawaitable(transaction):
                transaction = await transaction
            async with transaction:
                cursor = conn.cursor(sql)
                if isawaitable(cursor):
                    cursor = await cursor
                rows = await cursor.fetch(max_rows + 1)

        elapsed = round((time.time() - start) * 1000, 2)
        truncated = len(rows) > max_rows
        visible_rows = rows[:max_rows]
        return {
            "columns": columns,
            "rows": [_record_to_list(row) for row in visible_rows],
            "row_count": len(visible_rows),
            "execution_time_ms": elapsed,
            "truncated": truncated,
        }

    command_tag = await conn.execute(sql)
    elapsed = round((time.time() - start) * 1000, 2)
    return {
        "columns": [],
        "rows": [],
        "row_count": _extract_row_count(command_tag),
        "execution_time_ms": elapsed,
        "truncated": False,
        "message": command_tag,
    }
