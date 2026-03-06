"""
Test SQL Server sql_variant type handling
"""
import asyncio
from backend.services.sqlserver_service import SQLServerConnector
from backend.database import async_session
from backend.models.connection import Connection
from backend.utils.encryption import decrypt_value
from sqlalchemy import select


async def test_sql_variant():
    """Test that sql_variant columns work correctly"""
    async with async_session() as db:
        # Get SQL Server connection (ID 4)
        result = await db.execute(select(Connection).filter(Connection.id == 4))
        conn = result.scalar_one_or_none()

        if not conn:
            print("ERROR: SQL Server connection (ID 4) not found")
            return

        print(f"Testing SQL Server connection: {conn.name}")
        print(f"Host: {conn.host}:{conn.port}")
        print()

        # Decrypt password
        password = decrypt_value(conn.password_encrypted) if conn.password_encrypted else None

        # Create connector
        service = SQLServerConnector(
            host=conn.host,
            port=conn.port,
            username=conn.username,
            password=password,
            database=conn.database,
        )

        # Test queries with sql_variant columns
        test_queries = [
            ("SELECT name, value, value_in_use, description FROM sys.configurations ORDER BY name",
             "sys.configurations (contains sql_variant columns)"),
            ("SELECT @@VERSION",
             "Simple SELECT"),
            ("SELECT name, CAST(value AS VARCHAR(100)) as value_str FROM sys.configurations WHERE name = 'max degree of parallelism'",
             "Explicit CAST of sql_variant"),
        ]

        for sql, description in test_queries:
            print(f"Testing: {description}")
            print(f"SQL: {sql}")
            print("-" * 60)

            try:
                result = await service.execute_query(sql, max_rows=5)

                if result.get("columns"):
                    print(f"✓ Success - Columns: {result['columns']}")
                    print(f"  Rows returned: {result.get('row_count', 0)}")
                    print(f"  Execution time: {result.get('execution_time_ms', 0)}ms")

                    # Show first row as sample
                    if result.get("rows") and len(result["rows"]) > 0:
                        print(f"  Sample row: {result['rows'][0]}")
                else:
                    print(f"✓ Success - {result.get('message', 'No results')}")

            except Exception as e:
                print(f"✗ Error: {e}")

            print()


if __name__ == "__main__":
    asyncio.run(test_sql_variant())
