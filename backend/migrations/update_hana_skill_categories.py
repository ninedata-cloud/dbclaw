#!/usr/bin/env python3
"""
Migration: Update HANA skill categories from '通用诊断' to 'SAP HANA'
"""
import asyncio
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))


async def migrate():
    from backend.database import async_session
    from backend.models.skill import Skill
    from sqlalchemy import select, update

    async with async_session() as db:
        # Find all HANA skills with wrong category
        result = await db.execute(
            select(Skill).where(
                Skill.id.like('hana_%'),
                Skill.category == '通用诊断'
            )
        )
        skills = result.scalars().all()

        if not skills:
            print("No HANA skills found with category '通用诊断'")
            return

        print(f"Found {len(skills)} HANA skills to update:")
        for skill in skills:
            print(f"  - {skill.id}")

        # Update category to 'SAP HANA'
        await db.execute(
            update(Skill)
            .where(
                Skill.id.like('hana_%'),
                Skill.category == '通用诊断'
            )
            .values(category='SAP HANA')
        )
        await db.commit()

        print(f"\n✓ Successfully updated {len(skills)} HANA skills to category 'SAP HANA'")


if __name__ == "__main__":
    asyncio.run(migrate())
