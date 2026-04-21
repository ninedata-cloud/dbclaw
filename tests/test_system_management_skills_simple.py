"""
Simple test to verify system management skills are loaded
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

async def main():
    from backend.database import async_session, init_db
    from backend.models.skill import Skill
    from sqlalchemy import select
    
    print("=" * 60)
    print("System Management Skills Verification")
    print("=" * 60)
    
    # Initialize database and load skills
    print("\nInitializing database and loading skills...")
    await init_db()
    
    # Check if our 7 skills are loaded
    expected_skills = [
        'manage_datasource',
        'manage_host',
        'manage_skill',
        'query_monitoring_data',
        'query_inspection_report',
        'trigger_inspection',
        'query_system_metadata'
    ]
    
    async with async_session() as db:
        print(f"\nChecking for {len(expected_skills)} system management skills...")
        
        all_found = True
        for skill_id in expected_skills:
            result = await db.execute(
                select(Skill).where(Skill.id == skill_id)
            )
            skill = result.scalar_one_or_none()
            
            if skill:
                print(f"✓ {skill_id}")
                print(f"  Name: {skill.name}")
                print(f"  Category: {skill.category}")
                print(f"  Parameters: {len(skill.parameters) if skill.parameters else 0}")
                print(f"  Builtin: {skill.is_builtin}")
            else:
                print(f"✗ {skill_id}: NOT FOUND")
                all_found = False
        
        if all_found:
            print("\n" + "=" * 60)
            print("✅ ALL 7 SKILLS LOADED SUCCESSFULLY")
            print("=" * 60)
            return True
        else:
            print("\n" + "=" * 60)
            print("❌ SOME SKILLS MISSING")
            print("=" * 60)
            return False

if __name__ == '__main__':
    try:
        success = asyncio.run(main())
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"\n❌ Error: {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
