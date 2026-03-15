"""
Test script for Bocha AI web search skill
"""
import asyncio
import sys
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent))

from backend.database import get_db
from backend.skills.registry import SkillRegistry
from backend.skills.executor import SkillExecutor
from backend.skills.context import SkillContext
from backend.skills.builtin_loader import load_builtin_skills


async def test_bocha_search():
    """Test the Bocha AI web search skill"""
    print("=" * 60)
    print("Testing Bocha AI Web Search Skill")
    print("=" * 60)
    
    # Get database session
    async for db in get_db():
        try:
            # Load built-in skills
            print("\nLoading built-in skills...")
            await load_builtin_skills(db)

            # Get skill registry
            registry = SkillRegistry(db)

            # Load skill
            skill = await registry.get_skill("web_search_bocha")
            print(f"\n✓ Loaded skill: {skill.name} v{skill.version}")
            print(f"  Description: {skill.description}")
            print(f"  Permissions: {skill.permissions}")
            print(f"  Timeout: {skill.timeout}s")
            
            # Create execution context
            context = SkillContext(
                db=db,
                user_id=1,
                permissions=["access_external_api"],
                timeout=30
            )
            
            # Test parameters
            test_cases = [
                {
                    "name": "Search in Chinese",
                    "params": {
                        "query": "数据库性能优化",
                        "max_results": 3,
                        "language": "zh"
                    }
                },
                {
                    "name": "Search in English",
                    "params": {
                        "query": "database performance tuning",
                        "max_results": 3,
                        "language": "en"
                    }
                }
            ]
            
            executor = SkillExecutor()
            
            for test_case in test_cases:
                print(f"\n{'=' * 60}")
                print(f"Test: {test_case['name']}")
                print(f"{'=' * 60}")
                print(f"Parameters: {test_case['params']}")
                
                try:
                    result = await executor.execute(skill, test_case['params'], context)
                    
                    if result.get('success'):
                        print(f"\n✓ Search successful!")
                        print(f"  Query: {result.get('query')}")
                        print(f"  Language: {result.get('language')}")
                        print(f"  Total results: {result.get('total_results')}")
                        
                        print(f"\n  Results:")
                        for item in result.get('results', []):
                            print(f"    {item['rank']}. {item['title']}")
                            print(f"       URL: {item['url']}")
                            print(f"       Snippet: {item['snippet'][:100]}...")
                            print()
                    else:
                        print(f"\n✗ Search failed:")
                        print(f"  Error: {result.get('error')}")
                        print(f"  Details: {result.get('details', result.get('message', 'N/A'))}")
                
                except Exception as e:
                    print(f"\n✗ Execution error: {str(e)}")
                    import traceback
                    traceback.print_exc()
            
            print(f"\n{'=' * 60}")
            print("Test completed")
            print(f"{'=' * 60}")
            
        finally:
            await db.close()
        break


if __name__ == "__main__":
    asyncio.run(test_bocha_search())
