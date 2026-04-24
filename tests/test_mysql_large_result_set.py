"""
测试 MySQL 大结果集查询是否正确使用 SQL_SELECT_LIMIT，避免缓冲所有数据到内存
"""
import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, patch, MagicMock, call
from backend.services.mysql_service import MySQLConnector


@pytest.mark.asyncio
async def test_mysql_execute_query_uses_sql_select_limit():
    """验证 execute_query 使用 SQL_SELECT_LIMIT 限制结果"""
    connector = MySQLConnector(
        host="localhost",
        port=3306,
        username="test",
        password="test",
        database="testdb"
    )

    # Mock aiomysql
    mock_conn = AsyncMock()
    mock_cursor = AsyncMock()

    # 模拟游标返回的数据
    mock_cursor.description = [("id",), ("name",)]
    mock_cursor.fetchall = AsyncMock(return_value=[
        (1, "row1"), (2, "row2"), (3, "row3")
    ])
    mock_cursor.rowcount = 3
    mock_cursor.__aenter__ = AsyncMock(return_value=mock_cursor)
    mock_cursor.__aexit__ = AsyncMock(return_value=None)

    mock_conn.cursor = Mock(return_value=mock_cursor)
    mock_conn.close = Mock()

    with patch.object(connector, '_connect', new_callable=AsyncMock) as mock_connect:
        mock_connect.return_value = mock_conn

        # 执行查询
        result = await connector.execute_query("SELECT * FROM large_table", max_rows=10000)

        # 验证：
        # 1. _connect 被调用（不带参数）
        mock_connect.assert_called_once_with()

        # 2. 执行了 SET SQL_SELECT_LIMIT
        execute_calls = [call[0][0] for call in mock_cursor.execute.call_args_list]
        assert "SET SQL_SELECT_LIMIT = 10001" in execute_calls
        assert "SELECT * FROM large_table" in execute_calls
        assert "SET SQL_SELECT_LIMIT = DEFAULT" in execute_calls

        # 3. 返回结果正确
        assert result["columns"] == ["id", "name"]
        assert len(result["rows"]) == 3
        assert result["truncated"] is False


@pytest.mark.asyncio
async def test_mysql_sql_select_limit_reset_on_error():
    """验证即使查询失败，SQL_SELECT_LIMIT 也会被重置"""
    connector = MySQLConnector(
        host="localhost",
        port=3306,
        username="test",
        password="test",
        database="testdb"
    )

    mock_conn = AsyncMock()
    mock_cursor = AsyncMock()

    # 模拟查询失败
    async def mock_execute(sql):
        if "SELECT" in sql and "large_table" in sql:
            raise Exception("Table not found")

    mock_cursor.execute = AsyncMock(side_effect=mock_execute)
    mock_cursor.__aenter__ = AsyncMock(return_value=mock_cursor)
    mock_cursor.__aexit__ = AsyncMock(return_value=None)

    mock_conn.cursor = Mock(return_value=mock_cursor)
    mock_conn.close = Mock()

    with patch.object(connector, '_connect', new_callable=AsyncMock) as mock_connect:
        mock_connect.return_value = mock_conn

        # 执行查询（应该失败）
        with pytest.raises(Exception, match="Table not found"):
            await connector.execute_query("SELECT * FROM large_table", max_rows=10000)

        # 验证：即使失败，也尝试重置 SQL_SELECT_LIMIT
        execute_calls = [call[0][0] for call in mock_cursor.execute.call_args_list]
        assert "SET SQL_SELECT_LIMIT = 10001" in execute_calls
        assert "SET SQL_SELECT_LIMIT = DEFAULT" in execute_calls


@pytest.mark.asyncio
async def test_mysql_truncation_detection():
    """验证正确检测结果被截断"""
    connector = MySQLConnector(
        host="localhost",
        port=3306,
        username="test",
        password="test",
        database="testdb"
    )

    mock_conn = AsyncMock()
    mock_cursor = AsyncMock()

    # 模拟返回 11 行（max_rows=10）
    mock_cursor.description = [("id",)]
    mock_cursor.fetchall = AsyncMock(return_value=[(i,) for i in range(11)])
    mock_cursor.__aenter__ = AsyncMock(return_value=mock_cursor)
    mock_cursor.__aexit__ = AsyncMock(return_value=None)

    mock_conn.cursor = Mock(return_value=mock_cursor)
    mock_conn.close = Mock()

    with patch.object(connector, '_connect', new_callable=AsyncMock) as mock_connect:
        mock_connect.return_value = mock_conn

        result = await connector.execute_query("SELECT * FROM table", max_rows=10)

        # 验证：检测到截断
        assert result["truncated"] is True
        assert result["row_count"] == 10  # 只返回 10 行
        assert len(result["rows"]) == 10


if __name__ == "__main__":
    asyncio.run(test_mysql_execute_query_uses_sql_select_limit())
    asyncio.run(test_mysql_sql_select_limit_reset_on_error())
    asyncio.run(test_mysql_truncation_detection())
    print("✅ 所有测试通过")
