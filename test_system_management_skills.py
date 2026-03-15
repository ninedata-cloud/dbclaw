"""
Test suite for system management skills
Run with: python test_system_management_skills.py
"""
import asyncio
import sys
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent))

async def test_skill_loading():
    """Test that all 7 skills can be loaded"""
    from backend.skills.loader import SkillLoader
    from backend.database import async_session

    print("Testing skill loading...")

    async with async_session() as db:
        loader = SkillLoader(db)
        
        # Load builtin skills
        await loader.load_builtin_skills()
        
        # Check if our 7 skills are loaded
        expected_skills = [
            'manage_datasource',
            'manage_host',
            'manage_skill',
            'query_monitoring_data',
            'query_inspection_reports',
            'trigger_inspection',
            'query_system_metadata'
        ]
        
        from backend.skills.models import Skill
        from sqlalchemy import select
        
        for skill_id in expected_skills:
            result = await db.execute(
                select(Skill).where(Skill.id == skill_id)
            )
            skill = result.scalar_one_or_none()
            
            if skill:
                print(f"✓ {skill_id}: Loaded successfully")
                print(f"  Name: {skill.name}")
                print(f"  Category: {skill.category}")
                print(f"  Parameters: {len(skill.parameters) if skill.parameters else 0}")
            else:
                print(f"✗ {skill_id}: NOT FOUND")
                return False
        
        print(f"\nAll {len(expected_skills)} skills loaded successfully!")
        return True

async def test_skill_validation():
    """Test skill parameter validation"""
    from backend.skills.validator import SkillValidator
    
    print("\nTesting skill validation...")
    
    validator = SkillValidator()
    
    # Test valid skill
    valid_skill = {
        "id": "test_skill",
        "name": "Test Skill",
        "version": "1.0.0",
        "category": "test",
        "description": "Test skill",
        "tags": ["test"],
        "parameters": [
            {
                "name": "param1",
                "type": "string",
                "required": True,
                "description": "Test parameter"
            }
        ],
        "permissions": [],
        "code": "async def execute(context, params):\n    return {'success': True}"
    }
    
    result = validator.validate(valid_skill)
    if result.is_valid:
        print("✓ Valid skill passed validation")
    else:
        print(f"✗ Valid skill failed: {result.errors}")
        return False
    
    # Test invalid skill (forbidden import)
    invalid_skill = {
        "id": "bad_skill",
        "name": "Bad Skill",
        "version": "1.0.0",
        "code": "import os\nasync def execute(context, params):\n    os.system('ls')"
    }
    
    result = validator.validate(invalid_skill)
    if not result.is_valid:
        print(f"✓ Invalid skill rejected: {result.errors[0]}")
    else:
        print("✗ Invalid skill passed validation (should have failed)")
        return False
    
    print("\nValidation tests passed!")
    return True

async def test_skill_execution():
    """Test basic skill execution"""
    from backend.skills.executor import SkillExecutor
    from backend.skills.context import SkillContext
    from backend.database import async_session

    print("\nTesting skill execution...")

    async with async_session() as db:
        context = SkillContext(db=db)
        executor = SkillExecutor()
        
        # Test manage_datasource list action
        try:
            result = await executor.execute(
                'manage_datasource',
                {'action': 'list'},
                context
            )
            
            if result.get('success'):
                print(f"✓ manage_datasource list: {result.get('count', 0)} datasources")
            else:
                print(f"✗ manage_datasource list failed: {result.get('error')}")
                return False
        except Exception as e:
            print(f"✗ manage_datasource execution error: {str(e)}")
            return False
        
        # Test query_system_metadata statistics
        try:
            result = await executor.execute(
                'query_system_metadata',
                {'query_type': 'statistics'},
                context
            )
            
            if result.get('success'):
                stats = result.get('statistics', {})
                print(f"✓ query_system_metadata statistics: {len(stats)} metrics")
                print(f"  Datasources: {stats.get('datasources', 0)}")
                print(f"  Skills: {stats.get('skills', 0)}")
            else:
                print(f"✗ query_system_metadata failed: {result.get('error')}")
                return False
        except Exception as e:
            print(f"✗ query_system_metadata execution error: {str(e)}")
            return False
        
        print("\nExecution tests passed!")
        return True

async def main():
    """Run all tests"""
    print("=" * 60)
    print("System Management Skills Test Suite")
    print("=" * 60)
    
    try:
        # Test 1: Skill loading
        if not await test_skill_loading():
            print("\n❌ Skill loading test FAILED")
            return False
        
        # Test 2: Skill validation
        if not await test_skill_validation():
            print("\n❌ Skill validation test FAILED")
            return False
        
        # Test 3: Skill execution
        if not await test_skill_execution():
            print("\n❌ Skill execution test FAILED")
            return False
        
        print("\n" + "=" * 60)
        print("✅ ALL TESTS PASSED")
        print("=" * 60)
        return True
        
    except Exception as e:
        print(f"\n❌ Test suite error: {str(e)}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == '__main__':
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
