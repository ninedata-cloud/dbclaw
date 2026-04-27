#!/usr/bin/env python3
"""Reload builtin skills from YAML files"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.database import get_db
from backend.skills.builtin_loader import load_builtin_skills

async def main():
    async for db in get_db():
        print("Reloading builtin skills...")
        await load_builtin_skills(db)
        print("Done!")
        break

if __name__ == "__main__":
    asyncio.run(main())
