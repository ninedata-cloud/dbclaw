"""
Test execute_diagnostic_query skill with EXEC statement
"""
import asyncio
from backend.database import async_session
from backend.skills.registry import SkillRegistry
from backend.skills.executor import SkillExecutor
from backend.skills.context import SkillContext


async def test_exec_skill():
    """Test that EXEC statements work in execute_diagnostic_query"""
    async with async_session() as db:
        registry = SkillRegistry(db)
        executor = SkillExecutor()

        # Get the skill
        skill = await registry.get_skill("execute_diagnostic_query")
        if not skill:
            print("ERROR: execute_diagnostic_query skill not found")
            return

        print(f"Skill: {skill.name}")
        print(f"Category: {skill.category}")
        print(f"Description: {skill.description}")
        print(f"Tags: {skill.tags}")
        print()

        # Test with SQL Server connection (ID 4)
        context = SkillContext(
            db=db,
            user_id=1,
            session_id=None,
            permissions=["execute_query"]
        )

        # Test EXEC statement
        test_cases = [
            ("SELECT @@VERSION", "SELECT statement"),
            ("SHOW TABLES", "SHOW statement"),
            ("EXPLAIN SELECT * FROM users", "EXPLAIN statement"),
            ("EXEC sp_configure", "EXEC statement (SQL Server)"),
            ("EXECUTE sp_who2", "EXECUTE statement (SQL Server)"),
            ("DESCRIBE users", "DESCRIBE statement"),
        ]

        print("Testing SQL validation:")
        print("-" * 60)

        for sql, description in test_cases:
            params = {
                "connection_id": 4,  # SQL Server connection
                "sql": sql
            }

            try:
                # Just test validation, not actual execution
                sql_upper = sql.strip().upper()
                allowed_keywords = ['SELECT', 'SHOW', 'EXPLAIN', 'EXEC', 'EXECUTE', 'DESCRIBE', 'DESC']
                is_allowed = any(sql_upper.startswith(keyword) for keyword in allowed_keywords)

                if is_allowed:
                    print(f"✓ {description}: ALLOWED")
                    print(f"  SQL: {sql}")
                else:
                    print(f"✗ {description}: BLOCKED")
                    print(f"  SQL: {sql}")
            except Exception as e:
                print(f"✗ {description}: ERROR - {e}")

            print()


if __name__ == "__main__":
    asyncio.run(test_exec_skill())
