"""
Utility functions for skill execution
"""
from typing import Dict, Any
from backend.models.connection import Connection
from backend.services.mysql_service import MySQLConnector
from backend.services.postgres_service import PostgreSQLConnector
from backend.services.mongo_service import MongoDBConnector
from backend.services.redis_service import RedisConnector
from backend.services.sqlserver_service import SQLServerConnector
from backend.services.oracle_service import OracleConnector
from backend.utils.encryption import decrypt_value


async def execute_query(conn: Connection, query: str) -> Dict[str, Any]:
    """Execute a query on a database connection"""
    try:
        # Decrypt password
        password = decrypt_value(conn.password_encrypted) if conn.password_encrypted else None

        # Get appropriate service
        if conn.db_type == "mysql":
            service = MySQLConnector(
                host=conn.host,
                port=conn.port,
                username=conn.username,
                password=password,
                database=conn.database,
            )
        elif conn.db_type == "postgresql":
            service = PostgreSQLConnector(
                host=conn.host,
                port=conn.port,
                username=conn.username,
                password=password,
                database=conn.database,
            )
        elif conn.db_type == "mongodb":
            service = MongoDBConnector(
                host=conn.host,
                port=conn.port,
                username=conn.username,
                password=password,
                database=conn.database,
            )
        elif conn.db_type == "redis":
            service = RedisConnector(
                host=conn.host,
                port=conn.port,
                username=conn.username,
                password=password,
                database=conn.database,
            )
        elif conn.db_type == "sqlserver":
            service = SQLServerConnector(
                host=conn.host,
                port=conn.port,
                username=conn.username,
                password=password,
                database=conn.database,
            )
        elif conn.db_type == "oracle":
            service = OracleConnector(
                host=conn.host,
                port=conn.port,
                username=conn.username,
                password=password,
                database=conn.database,
            )
        else:
            return {"success": False, "error": f"Unsupported database type: {conn.db_type}"}

        # Execute query
        result = await service.execute_query(query)
        # Add success flag if not present
        if "success" not in result:
            result["success"] = True
        # Convert to data format expected by skills
        if "rows" in result and "columns" in result:
            result["data"] = result["rows"]
        return result

    except Exception as e:
        return {"success": False, "error": str(e)}
