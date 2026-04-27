from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional


class DBConnector(ABC):
    """Abstract base class for all database connectors."""

    def __init__(self, host: str, port: int, username: str = None,
                 password: str = None, database: str = None):
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.database = database

    @abstractmethod
    async def test_connection(self) -> str:
        """Test connection and return version string."""
        pass

    @abstractmethod
    async def get_status(self) -> Dict[str, Any]:
        """Get database status metrics."""
        pass

    @abstractmethod
    async def get_variables(self) -> Dict[str, Any]:
        """Get database configuration variables."""
        pass

    @abstractmethod
    async def get_process_list(self) -> List[Dict[str, Any]]:
        """Get active processes/sessions."""
        pass

    @abstractmethod
    async def get_slow_queries(self) -> List[Dict[str, Any]]:
        """Get recent slow queries."""
        pass

    @abstractmethod
    async def execute_query(
        self,
        sql: str,
        max_rows: int = 1000,
        execution_state: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """Execute a read-only query and return results."""
        pass

    @abstractmethod
    async def explain_query(self, sql: str) -> Dict[str, Any]:
        """Get query execution plan."""
        pass

    @abstractmethod
    async def get_table_stats(self) -> List[Dict[str, Any]]:
        """Get table-level statistics."""
        pass

    @abstractmethod
    async def get_replication_status(self) -> Dict[str, Any]:
        """Get replication/cluster status."""
        pass

    async def get_db_size(self) -> Dict[str, Any]:
        """Get database size information."""
        return {}

    async def get_index_stats(self) -> List[Dict[str, Any]]:
        """Get index usage statistics."""
        return []

    async def get_lock_waits(self) -> List[Dict[str, Any]]:
        """Get current lock waits and deadlocks."""
        return []

    async def get_table_fragmentation(self) -> List[Dict[str, Any]]:
        """Get table fragmentation information."""
        return []

    async def terminate_session(self, session_id: int) -> Dict[str, Any]:
        """Terminate a database session/process when supported."""
        raise NotImplementedError("terminate_session is not supported for this database type")

    async def cancel_query(self, session_id: int) -> Dict[str, Any]:
        """Cancel the currently running statement when supported."""
        raise NotImplementedError("cancel_query is not supported for this database type")

    @abstractmethod
    async def get_schemas(self) -> List[str]:
        """Get list of schema/database names."""
        pass

    @abstractmethod
    async def get_tables(self, schema: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get list of tables with metadata."""
        pass

    @abstractmethod
    async def get_columns(self, table: str, schema: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get list of columns for a table with types and constraints."""
        pass

    async def close(self):
        """Clean up connections."""
        pass


def get_connector(db_type: str, host: str, port: int, username: str = None,
                  password: str = None, database: str = None,
                  extra_params: Any = None, **kwargs) -> DBConnector:
    """Factory function to create appropriate connector."""
    connectors = {
        "mysql": "backend.services.mysql_service.MySQLConnector",
        "tdsql-c-mysql": "backend.services.mysql_service.MySQLConnector",
        "postgresql": "backend.services.postgres_service.PostgreSQLConnector",
        "sqlserver": "backend.services.sqlserver_service.SQLServerConnector",
        "oracle": "backend.services.oracle_service.OracleConnector",
        "opengauss": "backend.services.opengauss_service.OpenGaussConnector",
        "hana": "backend.services.hana_service.HANAConnector",
    }

    if db_type not in connectors:
        raise ValueError(f"Unsupported database type: {db_type}")

    # 解析 extra_params JSON，将其中的参数传递给 connector
    if extra_params:
        import json

        if isinstance(extra_params, dict):
            kwargs.update(extra_params)
        else:
            try:
                parsed = json.loads(extra_params)
                if isinstance(parsed, dict):
                    kwargs.update(parsed)
            except (json.JSONDecodeError, TypeError):
                pass

    module_path, class_name = connectors[db_type].rsplit(".", 1)
    import importlib
    module = importlib.import_module(module_path)
    connector_class = getattr(module, class_name)
    return connector_class(host=host, port=port, username=username,
                           password=password, database=database, **kwargs)
