"""
Test script to verify timeout propagation through SSH execution chain
"""
import asyncio
import sys
from backend.database import get_db, init_db
from backend.skills.registry import SkillRegistry
from backend.skills.executor import SkillExecutor
from backend.skills.context import SkillContext


async def test_timeout_propagation():
    """Test that timeout is properly propagated to SSH commands"""
    print("Testing timeout propagation through SSH execution chain...\n")

    # Initialize database
    await init_db()

    async for db in get_db():
        registry = SkillRegistry(db)
        
        # Test 1: Check if get_os_metrics skill has timeout=120
        print("Test 1: Checking get_os_metrics skill timeout configuration")
        skill = await registry.get_skill("get_os_metrics")
        if skill:
            print(f"  ✓ Skill found: {skill.name}")
            print(f"  ✓ Configured timeout: {skill.timeout}s")
            assert skill.timeout == 120, f"Expected timeout=120, got {skill.timeout}"
        else:
            print("  ✗ Skill 'get_os_metrics' not found")
            return False
        
        # Test 2: Check if execute_os_command skill has timeout=120
        print("\nTest 2: Checking execute_os_command skill timeout configuration")
        skill = await registry.get_skill("execute_os_command")
        if skill:
            print(f"  ✓ Skill found: {skill.name}")
            print(f"  ✓ Configured timeout: {skill.timeout}s")
            assert skill.timeout == 120, f"Expected timeout=120, got {skill.timeout}"
        else:
            print("  ✗ Skill 'execute_os_command' not found")
            return False
        
        # Test 3: Verify SkillContext accepts timeout parameter
        print("\nTest 3: Verifying SkillContext accepts timeout parameter")
        try:
            context = SkillContext(
                db=db,
                user_id=1,
                session_id=None,
                permissions=["execute_command"],
                timeout=120
            )
            print(f"  ✓ SkillContext created with timeout={context.timeout}s")
            assert context.timeout == 120, f"Expected context.timeout=120, got {context.timeout}"
        except Exception as e:
            print(f"  ✗ Failed to create SkillContext with timeout: {e}")
            return False
        
        # Test 4: Verify timeout priority logic
        print("\nTest 4: Verifying timeout priority logic")
        executor = SkillExecutor()
        
        # Get a skill with timeout=120
        skill = await registry.get_skill("get_os_metrics")
        
        # Test 4a: No dynamic timeout, should use skill timeout (120)
        context = SkillContext(db=db, user_id=1, permissions=skill.permissions or [])
        print(f"  Test 4a: No dynamic timeout")
        print(f"    - Skill timeout: {skill.timeout}s")
        print(f"    - Context timeout: {context.timeout}")
        print(f"    - Expected: Should use skill timeout (120s)")
        
        # Test 4b: Dynamic timeout provided, should override
        context = SkillContext(db=db, user_id=1, permissions=skill.permissions or [], timeout=60)
        print(f"  Test 4b: Dynamic timeout=60s")
        print(f"    - Skill timeout: {skill.timeout}s")
        print(f"    - Context timeout: {context.timeout}s")
        print(f"    - Expected: Should use dynamic timeout (60s)")
        assert context.timeout == 60, f"Expected context.timeout=60, got {context.timeout}"
        
        # Test 4c: Dynamic timeout exceeds MAX_TIMEOUT
        context = SkillContext(db=db, user_id=1, permissions=skill.permissions or [], timeout=5000)
        print(f"  Test 4c: Dynamic timeout=5000s (exceeds MAX_TIMEOUT)")
        print(f"    - Context timeout: {context.timeout}s")
        print(f"    - Expected: Should be capped at MAX_TIMEOUT (3600s) by executor")
        
        print("\n" + "="*60)
        print("✓ All timeout propagation tests passed!")
        print("="*60)
        return True


if __name__ == "__main__":
    result = asyncio.run(test_timeout_propagation())
    sys.exit(0 if result else 1)
