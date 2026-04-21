"""
批量更新数据源数据库版本信息

遍历所有数据源，通过数据库连接采集版本信息并更新到数据库。

运行方式：
source .venv/bin/activate && PYTHONPATH=. python backend/migrations/batch_update_datasource_db_version.py
"""

import asyncio
import logging
from backend.database import async_session
from backend.models.datasource import Datasource
from backend.models.soft_delete import alive_select
from backend.utils.encryption import decrypt_value
from backend.services.connection_diagnostic_service import ConnectionDiagnosticService

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def batch_update_db_versions():
    """批量更新所有数据源的数据库版本"""
    async with async_session() as db:
        result = await db.execute(alive_select(Datasource))
        datasource = result.scalars().all()

        if not datasource:
            logger.info("No datasource found")
            return

        logger.info(f"Found {len(datasource)} datasource, starting DB version collection...")

        success_count = 0
        fail_count = 0

        for ds in datasource:
            try:
                # 获取密码
                password = decrypt_value(ds.password_encrypted) if ds.password_encrypted else None

                # 诊断连接并获取版本
                diagnostic_service = ConnectionDiagnosticService(db)
                result = await diagnostic_service.diagnose_connection_params(
                    db_type=ds.db_type,
                    host=ds.host,
                    port=ds.port,
                    username=ds.username,
                    password=password,
                    database=ds.database,
                    extra_params=ds.extra_params,
                    datasource_id=ds.id,
                    include_host_checks=False,
                    include_tcp_checks=False,
                )

                if result.get('success') and result.get('version'):
                    ds.db_version = result.get('version')
                    logger.info(f"[{ds.id}] {ds.name} ({ds.db_type}): {result.get('version')}")
                    success_count += 1
                else:
                    logger.warning(f"[{ds.id}] {ds.name}: Failed to get DB version - {result.get('message')}")
                    fail_count += 1

            except Exception as e:
                logger.warning(f"[{ds.id}] {ds.name}: Exception - {str(e)}")
                fail_count += 1

        await db.commit()

        logger.info(f"Batch update complete: {success_count} success, {fail_count} failed")


if __name__ == "__main__":
    asyncio.run(batch_update_db_versions())
