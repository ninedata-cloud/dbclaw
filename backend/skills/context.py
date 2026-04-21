"""
Skill execution context - provides safe API for skills to access system resources
"""
from typing import Dict, Any, List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from backend.utils.datetime_helper import now
from backend.models.soft_delete import alive_filter


class SkillContext:
    """
    Execution context provided to skills with controlled access to system resources.
    All operations are permission-checked and logged.
    """

    def __init__(
        self,
        db: AsyncSession,
        user_id: int,
        session_id: Optional[int] = None,
        permissions: List[str] = None,
        timeout: Optional[int] = None,
    ):
        self.db = db
        self.user_id = user_id
        self.session_id = session_id
        self.permissions = permissions or []
        self.timeout = timeout  # Store timeout for use in execute_command
        self._skill_registry = None

    def _check_permission(self, permission: str):
        """Check if the skill has the required permission"""
        if permission not in self.permissions:
            raise PermissionError(f"Skill does not have permission: {permission}")

    async def get_connection(self, datasource_id: int):
        """Get a database datasource object from the local meta-database.

        Note: This method only reads metadata from the local meta-database.
        It does not connect to or query the target datasource itself,
        so no execute_query permission is required.
        """
        from backend.models.datasource import Datasource
        from backend.models.soft_delete import alive_filter
        from sqlalchemy import select

        result = await self.db.execute(
            select(Datasource).where(Datasource.id == datasource_id, alive_filter(Datasource))
        )
        datasource = result.scalar_one_or_none()
        if not datasource:
            raise ValueError(f"Datasource {datasource_id} not found")
        return datasource

    async def execute_query(self, query: str, datasource_id: int, allow_write: bool = False) -> Dict[str, Any]:
        """Execute a SQL query on a database datasource"""
        if allow_write:
            self._check_permission("execute_any_sql")
        else:
            self._check_permission("execute_query")

        from backend.utils.db_connector import execute_query as db_execute_query

        datasource = await self.get_connection(datasource_id)
        result = await db_execute_query(datasource, query, allow_write=allow_write)
        return result

    async def execute_host_command(self, command: str, datasource_id: int, allow_write: bool = False, timeout: int = None) -> Dict[str, Any]:
        """Execute an OS command via host connection

        Args:
            command: Shell command to execute
            datasource_id: Database connection ID (must have host configured)
            allow_write: If False (default), only read-only commands are allowed
            timeout: Command execution timeout in seconds (uses context timeout if not specified)
        """
        if allow_write:
            self._check_permission("execute_any_os_command")
        else:
            self._check_permission("execute_command")

        from backend.utils.host_executor import execute_host_command

        datasource = await self.get_connection(datasource_id)
        if not datasource.host_id:
            raise ValueError(f"Datasource {datasource_id} has no host configured")

        # Use provided timeout, or fall back to context timeout
        exec_timeout = timeout if timeout is not None else self.timeout
        result = await execute_host_command(self.db, datasource.host_id, command, allow_write=allow_write, timeout=exec_timeout)
        return result

    async def get_metrics(
        self, datasource_id: int, minutes: int = 60
    ) -> List[Dict[str, Any]]:
        """Get historical metrics for a datasource"""
        from backend.models.datasource_metric import DatasourceMetric
        from sqlalchemy import select
        from datetime import datetime, timedelta

        cutoff = now() - timedelta(minutes=minutes)
        result = await self.db.execute(
            select(DatasourceMetric)
            .where(
                DatasourceMetric.datasource_id == datasource_id,
                DatasourceMetric.collected_at >= cutoff,
            )
            .order_by(DatasourceMetric.collected_at.desc())
        )
        snapshots = result.scalars().all()

        return [
            {
                "metric_type": s.metric_type,
                "data": s.data,
                "collected_at": s.collected_at.isoformat(),
            }
            for s in snapshots
        ]

    async def execute_command(self, command: str, datasource_id: int, timeout: int = None) -> Dict[str, Any]:
        """Execute an OS command via host connection (backward compatibility wrapper)

        Args:
            command: Shell command to execute
            datasource_id: Database connection ID (must have host configured)
            timeout: Command execution timeout in seconds (uses context timeout if not specified)
        """
        # Use provided timeout, or fall back to context timeout
        exec_timeout = timeout if timeout is not None else self.timeout
        return await self.execute_host_command(command, datasource_id, allow_write=False, timeout=exec_timeout)

    async def execute_command_on_host(self, command: str, host_id: int, allow_write: bool = False, timeout: int = None) -> Dict[str, Any]:
        """Execute an OS command directly on a host by host_id

        Args:
            command: Shell command to execute
            host_id: SSH host ID to execute the command on
            allow_write: If False (default), only read-only commands are allowed
            timeout: Command execution timeout in seconds (uses context timeout if not specified)
        """
        if allow_write:
            self._check_permission("execute_any_os_command")
        else:
            self._check_permission("execute_command")

        from backend.utils.host_executor import execute_host_command

        # Use provided timeout, or fall back to context timeout
        exec_timeout = timeout if timeout is not None else self.timeout
        result = await execute_host_command(self.db, host_id, command, allow_write=allow_write, timeout=exec_timeout)
        return result

    async def call_skill(self, skill_id: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """Call another skill (for skill composition)"""
        if not self._skill_registry:
            from backend.skills.registry import get_skill_registry

            self._skill_registry = get_skill_registry()

        from backend.skills.executor import SkillExecutor

        skill = await self._skill_registry.get_skill(skill_id)
        executor = SkillExecutor()
        result = await executor.execute(skill, params, self)
        return result
