"""
Reload all built-in skills from YAML files
"""
import asyncio
from backend.database import init_db


async def main():
    print("Initializing database and loading skills...")
    await init_db()
    print("Done!")


if __name__ == "__main__":
    asyncio.run(main())
