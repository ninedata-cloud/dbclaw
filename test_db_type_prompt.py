"""
Test script to verify database type is correctly included in system prompt
"""
import asyncio
from backend.database import async_session
from backend.models.connection import Connection
from sqlalchemy import select


async def test_connection_info():
    """Test that we can retrieve connection info correctly"""
    async with async_session() as db:
        result = await db.execute(select(Connection).filter(Connection.is_active == True))
        connections = result.scalars().all()

        print("Active Connections:")
        print("-" * 60)
        for conn in connections:
            print(f"ID: {conn.id}")
            print(f"Name: {conn.name}")
            print(f"Type: {conn.db_type}")
            print(f"Host: {conn.host}:{conn.port}")
            print()

            # Simulate what the system prompt would say
            skill_prefix_map = {
                'mysql': 'mysql',
                'postgresql': 'pg',
                'sqlserver': 'mssql',
                'oracle': 'oracle'
            }
            skill_prefix = skill_prefix_map.get(conn.db_type, conn.db_type)

            system_msg = f"The user is currently working with database connection ID: {conn.id} (Type: {conn.db_type.upper()}, Name: {conn.name}). Use this ID when calling tools unless they specify otherwise."
            system_msg += f"\n\nIMPORTANT: This is a {conn.db_type.upper()} database. You MUST use {skill_prefix}_* skills (e.g., {skill_prefix}_get_db_status, {skill_prefix}_get_slow_queries, {skill_prefix}_get_table_stats, etc.). Do NOT use skills for other database types like mysql_*, pg_*, mssql_*, or oracle_* unless they match this database type."

            print("System Prompt Addition:")
            print(system_msg)
            print("-" * 60)
            print()


if __name__ == "__main__":
    asyncio.run(test_connection_info())
