"""Test skills with datasources that have no host configured"""
import asyncio
import sys
from sqlalchemy import select
from backend.database import async_session
from backend.models.datasource import Datasource
from backend.skills.registry import SkillRegistry
from backend.skills.executor import SkillExecutor
from backend.skills.context import SkillContext


async def test_get_os_metrics_no_host():
    """Test get_os_metrics skill with a datasource that has no host"""
    async with async_session() as db:
        # Find a datasource without host_id
        result = await db.execute(
            select(Datasource).where(Datasource.host_id == None)
        )
        datasource = result.scalars().first()

        if not datasource:
            print("❌ No datasource without host_id found. Creating a test datasource...")
            # For testing purposes, we'll just use any datasource and test the logic
            result = await db.execute(select(Datasource))
            datasource = result.scalars().first()
            if not datasource:
                print("❌ No datasources found in database")
                return False

            # Temporarily clear host_id for testing
            original_host_id = datasource.host_id
            datasource.host_id = None
            await db.commit()
            print(f"✓ Using datasource {datasource.id} ({datasource.name}) with host_id temporarily set to None")
        else:
            original_host_id = None
            print(f"✓ Found datasource {datasource.id} ({datasource.name}) without host_id")

        try:
            # Get the skill
            registry = SkillRegistry(db)
            skill = await registry.get_skill("get_os_metrics")

            if not skill:
                print("❌ Skill 'get_os_metrics' not found")
                return False

            print(f"✓ Loaded skill: {skill.name}")

            # Create context
            context = SkillContext(
                db=db,
                user_id=1,
                permissions=skill.permissions or []
            )

            # Execute skill
            executor = SkillExecutor()
            params = {"datasource_id": datasource.id}

            print(f"Executing skill with params: {params}")
            result = await executor.execute(skill, params, context)

            print(f"\nResult:")
            print(f"  success: {result.get('success')}")
            print(f"  error: {result.get('error')}")
            print(f"  message: {result.get('message')}")

            # Verify the result
            if result.get("success") is False and result.get("error") == "no_host_configured":
                print("\n✅ Test PASSED: Skill correctly handled datasource without host")
                return True
            else:
                print("\n❌ Test FAILED: Expected success=False and error='no_host_configured'")
                return False

        finally:
            # Restore original host_id if we modified it
            if original_host_id is not None:
                datasource.host_id = original_host_id
                await db.commit()
                print(f"\n✓ Restored host_id to {original_host_id}")


async def test_diagnose_high_cpu_no_host():
    """Test diagnose_high_cpu skill with a datasource that has no host"""
    async with async_session() as db:
        # Find a datasource without host_id
        result = await db.execute(
            select(Datasource).where(Datasource.host_id == None)
        )
        datasource = result.scalars().first()

        if not datasource:
            # Use any datasource and temporarily clear host_id
            result = await db.execute(select(Datasource))
            datasource = result.scalars().first()
            if not datasource:
                print("❌ No datasources found in database")
                return False

            original_host_id = datasource.host_id
            datasource.host_id = None
            await db.commit()
            print(f"✓ Using datasource {datasource.id} ({datasource.name}) with host_id temporarily set to None")
        else:
            original_host_id = None
            print(f"✓ Found datasource {datasource.id} ({datasource.name}) without host_id")

        try:
            # Get the skill
            registry = SkillRegistry(db)
            skill = await registry.get_skill("diagnose_high_cpu")

            if not skill:
                print("❌ Skill 'diagnose_high_cpu' not found")
                return False

            print(f"✓ Loaded skill: {skill.name}")

            # Create context
            context = SkillContext(
                db=db,
                user_id=1,
                permissions=skill.permissions or []
            )

            # Execute skill
            executor = SkillExecutor()
            params = {"datasource_id": datasource.id}

            print(f"Executing skill with params: {params}")
            result = await executor.execute(skill, params, context)

            print(f"\nResult:")
            print(f"  success: {result.get('success')}")
            print(f"  error: {result.get('error')}")
            print(f"  message: {result.get('message')}")

            # Verify the result
            if result.get("success") is False and result.get("error") == "no_host_configured":
                print("\n✅ Test PASSED: Skill correctly handled datasource without host")
                return True
            else:
                print("\n❌ Test FAILED: Expected success=False and error='no_host_configured'")
                return False

        finally:
            # Restore original host_id if we modified it
            if original_host_id is not None:
                datasource.host_id = original_host_id
                await db.commit()
                print(f"\n✓ Restored host_id to {original_host_id}")


async def main():
    print("=" * 60)
    print("Testing skills with datasources that have no host configured")
    print("=" * 60)

    print("\n[Test 1] get_os_metrics skill")
    print("-" * 60)
    test1_passed = await test_get_os_metrics_no_host()

    print("\n\n[Test 2] diagnose_high_cpu skill")
    print("-" * 60)
    test2_passed = await test_diagnose_high_cpu_no_host()

    print("\n" + "=" * 60)
    print("Test Summary")
    print("=" * 60)
    print(f"get_os_metrics: {'✅ PASSED' if test1_passed else '❌ FAILED'}")
    print(f"diagnose_high_cpu: {'✅ PASSED' if test2_passed else '❌ FAILED'}")

    if test1_passed and test2_passed:
        print("\n🎉 All tests PASSED!")
        return 0
    else:
        print("\n❌ Some tests FAILED")
        return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
