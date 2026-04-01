#!/usr/bin/env python3
"""Tests for db connector error formatting."""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from backend.utils.db_connector import execute_query


async def test_timeout_error_message_not_empty():
    datasource = SimpleNamespace(
        id=1,
        name="test-postgres",
        db_type="postgresql",
        host="127.0.0.1",
        port=5432,
        username="postgres",
        password_encrypted=None,
        database="postgres",
    )

    mock_service = AsyncMock()
    mock_service.execute_query.side_effect = asyncio.TimeoutError()

    with patch("backend.utils.db_connector.PostgreSQLConnector", return_value=mock_service):
        result = await execute_query(datasource, "SELECT 1")

    assert result["success"] is False
    assert result["error"] == "TimeoutError"


async def main():
    await test_timeout_error_message_not_empty()
    print("✓ db connector timeout errors now return a non-empty message")


if __name__ == "__main__":
    asyncio.run(main())
