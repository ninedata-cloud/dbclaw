#!/usr/bin/env python3
"""Regression tests for db_connector error formatting."""
import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).parent))

from backend.utils.db_connector import execute_query


class EmptyMessageError(Exception):
    def __str__(self):
        return ""


class FakePostgresError(Exception):
    def __init__(self):
        self.sqlstate = "42P01"
        self.detail = "relation \"missing_table\" does not exist"
        self.hint = "Check the table name and schema."

    def __str__(self):
        return ""


async def test_empty_error_message_fallback():
    datasource = SimpleNamespace(
        id=1,
        name="test-postgres",
        db_type="postgresql",
        host="127.0.0.1",
        port=5432,
        username="tester",
        password_encrypted=None,
        database="postgres",
    )

    mock_service = SimpleNamespace(execute_query=AsyncMock(side_effect=EmptyMessageError()))

    with patch("backend.utils.db_connector.PostgreSQLConnector", return_value=mock_service):
        result = await execute_query(datasource, "SELECT 1")

    assert result["success"] is False, result
    assert result.get("error"), result
    assert result.get("error_type") == "EmptyMessageError", result


async def test_postgres_error_details_are_exposed():
    datasource = SimpleNamespace(
        id=2,
        name="test-postgres",
        db_type="postgresql",
        host="127.0.0.1",
        port=5432,
        username="tester",
        password_encrypted=None,
        database="postgres",
    )

    mock_service = SimpleNamespace(execute_query=AsyncMock(side_effect=FakePostgresError()))

    with patch("backend.utils.db_connector.PostgreSQLConnector", return_value=mock_service):
        result = await execute_query(datasource, "SELECT * FROM missing_table")

    assert result["success"] is False, result
    assert result.get("error"), result
    assert result.get("error_type") == "FakePostgresError", result
    assert result.get("sqlstate") == "42P01", result
    assert result.get("detail") == 'relation "missing_table" does not exist', result
    assert result.get("hint") == "Check the table name and schema.", result


async def main():
    tests = [
        ("empty error message fallback", test_empty_error_message_fallback),
        ("postgres error details are exposed", test_postgres_error_details_are_exposed),
    ]

    failures = []
    for name, test in tests:
        try:
            await test()
            print(f"✓ {name}")
        except AssertionError as e:
            failures.append((name, str(e)))
            print(f"✗ {name}: {e}")
        except Exception as e:
            failures.append((name, str(e)))
            print(f"✗ {name}: unexpected error: {e}")

    if failures:
        print(f"\n{len(failures)} test(s) failed")
        return 1

    print("\nAll tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
