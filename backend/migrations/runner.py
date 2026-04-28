"""
数据库迁移脚本运行器

用于在 create_all() 前后执行必要的数据库迁移操作。
"""
import logging
from typing import List, Callable, Awaitable

logger = logging.getLogger(__name__)

# 在 create_all() 之前执行的迁移脚本
PRE_CREATE_MIGRATIONS: List[Callable[[], Awaitable[None]]] = [
    # 示例：
    # lambda: some_migration_function(),
]

# 在 create_all() 之后执行的迁移脚本
POST_CREATE_MIGRATIONS: List[Callable[[], Awaitable[None]]] = [
    # 添加 inspection_trigger.error_message 字段
    lambda: _run_add_inspection_trigger_error_message(),
    # 添加 ai_model.reasoning_effort 字段
    lambda: _run_add_ai_model_reasoning_effort(),
    # 添加 scheduled_task 运行结果通知字段
    lambda: _run_add_scheduled_task_notifications(),
    # 移除 scheduled_task 任务级参数配置字段
    lambda: _run_remove_scheduled_task_params(),
]


async def _run_add_inspection_trigger_error_message():
    """添加 inspection_trigger.error_message 字段"""
    from backend.migrations.add_inspection_trigger_error_message import upgrade
    await upgrade()


async def _run_add_ai_model_reasoning_effort():
    """添加 ai_model.reasoning_effort 字段"""
    from backend.migrations.add_ai_model_reasoning_effort import upgrade
    await upgrade()


async def _run_add_scheduled_task_notifications():
    """添加 scheduled_task 运行结果通知字段"""
    from backend.migrations.add_scheduled_task_notifications import upgrade
    await upgrade()


async def _run_remove_scheduled_task_params():
    """移除 scheduled_task 任务级参数配置字段"""
    from backend.migrations.remove_scheduled_task_params import upgrade
    await upgrade()



async def run_pre_create_migrations():
    """执行 create_all() 之前的迁移脚本"""
    if not PRE_CREATE_MIGRATIONS:
        logger.debug("No pre-create migrations to run")
        return

    logger.info(f"Running {len(PRE_CREATE_MIGRATIONS)} pre-create migrations...")
    for i, migration in enumerate(PRE_CREATE_MIGRATIONS, 1):
        try:
            logger.info(f"Running pre-create migration {i}/{len(PRE_CREATE_MIGRATIONS)}")
            await migration()
        except Exception as e:
            logger.error(f"Pre-create migration {i} failed: {e}", exc_info=True)
            raise
    logger.info("All pre-create migrations completed successfully")


async def run_post_create_migrations():
    """执行 create_all() 之后的迁移脚本"""
    if not POST_CREATE_MIGRATIONS:
        logger.debug("No post-create migrations to run")
        return

    logger.info(f"Running {len(POST_CREATE_MIGRATIONS)} post-create migrations...")
    for i, migration in enumerate(POST_CREATE_MIGRATIONS, 1):
        try:
            logger.info(f"Running post-create migration {i}/{len(POST_CREATE_MIGRATIONS)}")
            await migration()
        except Exception as e:
            logger.error(f"Post-create migration {i} failed: {e}", exc_info=True)
            raise
    logger.info("All post-create migrations completed successfully")
