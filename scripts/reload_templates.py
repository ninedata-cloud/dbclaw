#!/usr/bin/env python3
"""
重新加载内置模板
"""
import asyncio
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from backend.config import settings
from backend.services.integration_service import IntegrationService


async def reload_templates():
    """重新加载内置模板"""

    engine = create_async_engine(settings.database_url, echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    print("重新加载内置模板...")

    async with async_session() as db:
        await IntegrationService.load_builtin_templates(db)
        print("✓ 内置模板已重新加载")


if __name__ == "__main__":
    asyncio.run(reload_templates())
