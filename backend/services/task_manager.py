"""后台任务管理器

统一管理所有后台异步任务的生命周期，提供任务注册、取消、状态查询等功能。
"""
import asyncio
import logging
from datetime import datetime
from typing import Dict, Optional, Set
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class TaskInfo:
    """任务信息"""
    name: str
    task: asyncio.Task
    created_at: datetime = field(default_factory=datetime.now)
    status: str = "running"  # running, completed, failed, cancelled
    error: Optional[str] = None


class BackgroundTaskManager:
    """后台任务管理器"""

    def __init__(self):
        self._tasks: Dict[str, TaskInfo] = {}
        self._lock = asyncio.Lock()

    async def register_task(self, name: str, coro, replace_existing: bool = False) -> asyncio.Task:
        """
        注册并启动后台任务

        Args:
            name: 任务名称（唯一标识）
            coro: 协程对象
            replace_existing: 是否替换已存在的同名任务

        Returns:
            创建的 asyncio.Task 对象

        Raises:
            ValueError: 如果任务名称已存在且 replace_existing=False
        """
        async with self._lock:
            if name in self._tasks:
                if not replace_existing:
                    raise ValueError(f"Task '{name}' already exists")
                # 取消旧任务
                old_task = self._tasks[name].task
                if not old_task.done():
                    old_task.cancel()
                    try:
                        await old_task
                    except asyncio.CancelledError:
                        pass
                logger.info(f"Replaced existing task: {name}")

            # 包装协程以捕获异常
            task = asyncio.create_task(self._task_wrapper(name, coro))
            self._tasks[name] = TaskInfo(name=name, task=task)
            logger.info(f"Registered background task: {name}")
            return task

    async def _task_wrapper(self, name: str, coro):
        """
        任务包装器，统一处理异常和状态更新

        Args:
            name: 任务名称
            coro: 协程对象
        """
        try:
            await coro
            async with self._lock:
                if name in self._tasks:
                    self._tasks[name].status = "completed"
            logger.info(f"Task completed: {name}")
        except asyncio.CancelledError:
            async with self._lock:
                if name in self._tasks:
                    self._tasks[name].status = "cancelled"
            logger.info(f"Task cancelled: {name}")
            raise
        except Exception as e:
            async with self._lock:
                if name in self._tasks:
                    self._tasks[name].status = "failed"
                    self._tasks[name].error = str(e)
            logger.error(f"Task failed: {name}, error: {e}", exc_info=True)

    async def cancel_task(self, name: str) -> bool:
        """
        取消指定任务

        Args:
            name: 任务名称

        Returns:
            是否成功取消（任务存在且未完成）
        """
        async with self._lock:
            if name not in self._tasks:
                logger.warning(f"Task not found: {name}")
                return False

            task_info = self._tasks[name]
            if task_info.task.done():
                logger.info(f"Task already done: {name}")
                return False

            task_info.task.cancel()
            logger.info(f"Cancelled task: {name}")
            return True

    async def cancel_all(self, timeout: float = 10.0):
        """
        取消所有运行中的任务

        Args:
            timeout: 等待任务取消的超时时间（秒）
        """
        async with self._lock:
            running_tasks = [
                (name, info.task)
                for name, info in self._tasks.items()
                if not info.task.done()
            ]

        if not running_tasks:
            logger.info("No running tasks to cancel")
            return

        logger.info(f"Cancelling {len(running_tasks)} running tasks...")

        # 取消所有任务
        for name, task in running_tasks:
            task.cancel()

        # 等待所有任务完成（带超时）
        tasks = [task for _, task in running_tasks]
        try:
            await asyncio.wait_for(
                asyncio.gather(*tasks, return_exceptions=True),
                timeout=timeout
            )
            logger.info("All tasks cancelled successfully")
        except asyncio.TimeoutError:
            logger.warning(f"Some tasks did not cancel within {timeout}s timeout")

    async def wait_all(self, timeout: Optional[float] = None) -> bool:
        """
        等待所有任务完成

        Args:
            timeout: 超时时间（秒），None 表示无限等待

        Returns:
            是否所有任务都在超时前完成
        """
        async with self._lock:
            tasks = [info.task for info in self._tasks.values() if not info.task.done()]

        if not tasks:
            return True

        try:
            await asyncio.wait_for(
                asyncio.gather(*tasks, return_exceptions=True),
                timeout=timeout
            )
            return True
        except asyncio.TimeoutError:
            return False

    def get_status(self) -> Dict[str, dict]:
        """
        获取所有任务的状态

        Returns:
            任务状态字典，key 为任务名称，value 为状态信息
        """
        return {
            name: {
                "status": info.status,
                "created_at": info.created_at.isoformat(),
                "done": info.task.done(),
                "cancelled": info.task.cancelled(),
                "error": info.error,
            }
            for name, info in self._tasks.items()
        }

    def get_task_names(self) -> Set[str]:
        """获取所有任务名称"""
        return set(self._tasks.keys())

    def get_running_count(self) -> int:
        """获取运行中的任务数量"""
        return sum(1 for info in self._tasks.values() if not info.task.done())

    async def cleanup_completed(self):
        """清理已完成的任务记录"""
        async with self._lock:
            completed = [
                name for name, info in self._tasks.items()
                if info.task.done()
            ]
            for name in completed:
                del self._tasks[name]
            if completed:
                logger.info(f"Cleaned up {len(completed)} completed tasks")


# 全局任务管理器实例
_task_manager: Optional[BackgroundTaskManager] = None


def get_task_manager() -> BackgroundTaskManager:
    """获取全局任务管理器实例"""
    global _task_manager
    if _task_manager is None:
        _task_manager = BackgroundTaskManager()
    return _task_manager


def set_task_manager(manager: BackgroundTaskManager):
    """设置全局任务管理器实例（用于测试）"""
    global _task_manager
    _task_manager = manager
