"""Simple test to verify skill behavior in AI conversation"""
import asyncio
import json
from backend.database import async_session
from backend.agent.conversation_skills import execute_skill_call


async def test_skill_in_conversation():
    """Test get_os_metrics skill call as it would be called by AI"""
    async with async_session() as db:
        # Test with datasource 7 (no host)
        print("Testing get_os_metrics with datasource 7 (no host)...")
        result_json, exec_time = await execute_skill_call(
            skill_id="get_os_metrics",
            arguments={"datasource_id": 7},
            db=db,
            user_id=1
        )

        result = json.loads(result_json)
        print(f"\nResult (execution time: {exec_time}ms):")
        print(json.dumps(result, indent=2, ensure_ascii=False))

        if result.get("success") is False and result.get("error") == "no_host_configured":
            print("\n✅ SUCCESS: Skill correctly returned no_host_configured error")
            print(f"Message: {result.get('message')}")
            return True
        else:
            print("\n❌ FAILED: Unexpected result")
            return False


async def main():
    success = await test_skill_in_conversation()
    return 0 if success else 1


if __name__ == "__main__":
    import sys
    sys.exit(asyncio.run(main()))
