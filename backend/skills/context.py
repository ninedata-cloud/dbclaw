"""
Skill execution context - provides safe API for skills to access system resources
"""
from typing import Dict, Any, List, Optional
from sqlalchemy.ext.asyncio import AsyncSession


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
    ):
        self.db = db
        self.user_id = user_id
        self.session_id = session_id
        self.permissions = permissions or []
        self._skill_registry = None

    def _check_permission(self, permission: str):
        """Check if the skill has the required permission"""
        if permission not in self.permissions:
            raise PermissionError(f"Skill does not have permission: {permission}")

    async def get_connection(self, connection_id: int, check_permission: bool = True):
        """Get a database connection object"""
        if check_permission:
            self._check_permission("execute_query")
        from backend.models.connection import Connection
        from sqlalchemy import select

        result = await self.db.execute(
            select(Connection).where(Connection.id == connection_id)
        )
        conn = result.scalar_one_or_none()
        if not conn:
            raise ValueError(f"Connection {connection_id} not found")
        return conn

    async def execute_query(self, query: str, connection_id: int) -> Dict[str, Any]:
        """Execute a SQL query on a database connection"""
        self._check_permission("execute_query")
        from backend.utils.db_connector import execute_query as db_execute_query

        conn = await self.get_connection(connection_id)
        result = await db_execute_query(conn, query)
        return result

    async def search_kb(
        self, query: str, kb_ids: Optional[List[int]] = None, top_k: int = 5
    ) -> List[Dict[str, Any]]:
        """Search knowledge bases for relevant information"""
        self._check_permission("access_kb")
        from backend.models.knowledge_base import KnowledgeBase, KnowledgeChunk
        from sqlalchemy import select

        # If no kb_ids provided, use session's active KBs
        if not kb_ids and self.session_id:
            from backend.models.diagnostic_session import DiagnosticSession

            result = await self.db.execute(
                select(DiagnosticSession).where(DiagnosticSession.id == self.session_id)
            )
            session = result.scalar_one_or_none()
            if session and session.kb_ids:
                import json

                kb_ids = json.loads(session.kb_ids)

        if not kb_ids:
            return []

        # Get knowledge bases
        result = await self.db.execute(
            select(KnowledgeBase).where(KnowledgeBase.id.in_(kb_ids))
        )
        kbs = result.scalars().all()

        # Search using embeddings
        from backend.utils.embeddings import search_similar_chunks

        results = []
        for kb in kbs:
            chunks = await search_similar_chunks(self.db, kb.id, query, top_k)
            results.extend(
                [
                    {
                        "kb_id": kb.id,
                        "kb_name": kb.name,
                        "content": chunk.content,
                        "metadata": chunk.metadata,
                        "similarity": chunk.similarity,
                    }
                    for chunk in chunks
                ]
            )

        # Sort by similarity and return top_k
        results.sort(key=lambda x: x.get("similarity", 0), reverse=True)
        return results[:top_k]

    async def get_metrics(
        self, connection_id: int, minutes: int = 60
    ) -> List[Dict[str, Any]]:
        """Get historical metrics for a connection"""
        from backend.models.metric_snapshot import MetricSnapshot
        from sqlalchemy import select
        from datetime import datetime, timedelta

        cutoff = datetime.utcnow() - timedelta(minutes=minutes)
        result = await self.db.execute(
            select(MetricSnapshot)
            .where(
                MetricSnapshot.connection_id == connection_id,
                MetricSnapshot.created_at >= cutoff,
            )
            .order_by(MetricSnapshot.created_at.desc())
        )
        snapshots = result.scalars().all()

        return [
            {
                "metric_type": s.metric_type,
                "data": s.data,
                "created_at": s.created_at.isoformat(),
            }
            for s in snapshots
        ]

    async def execute_command(self, command: str, connection_id: int) -> Dict[str, Any]:
        """Execute an OS command via SSH"""
        self._check_permission("execute_command")
        from backend.utils.ssh_executor import execute_ssh_command

        conn = await self.get_connection(connection_id, check_permission=False)
        if not conn.ssh_host_id:
            raise ValueError(f"Connection {connection_id} has no SSH host configured")

        result = await execute_ssh_command(self.db, conn.ssh_host_id, command)
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
