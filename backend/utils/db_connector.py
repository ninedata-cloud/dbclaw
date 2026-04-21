"""
Utility functions for skill execution
"""
from typing import Dict, Any
import logging
import re
from backend.models.datasource import Datasource
from backend.services.mysql_service import MySQLConnector
from backend.services.postgres_service import PostgreSQLConnector
from backend.services.sqlserver_service import SQLServerConnector
from backend.services.oracle_service import OracleConnector
from backend.services.opengauss_service import OpenGaussConnector
from backend.services.hana_service import HANAConnector
from backend.utils.encryption import decrypt_value

logger = logging.getLogger(__name__)


def _get_non_empty_error_message(error: Exception) -> str:
    """Extract a non-empty error message from an exception."""
    message = str(error).strip()
    if message:
        return message

    representation = repr(error).strip()
    if representation:
        return representation

    return error.__class__.__name__


def _normalize_sql_for_readonly_check(query: str) -> str:
    """Remove comments and quoted strings for lightweight read-only checks."""
    normalized = re.sub(r"/\*.*?\*/", " ", query, flags=re.DOTALL)
    normalized = re.sub(r"--.*?$", " ", normalized, flags=re.MULTILINE)
    normalized = re.sub(r"'(?:''|[^'])*'", "''", normalized)
    normalized = re.sub(r'"(?:""|[^"])*"', '""', normalized)
    # Remove trailing semicolon (statement terminator) for read-only checks
    normalized = normalized.strip().rstrip(';').strip()
    return normalized.upper()


def _is_explain_write_query(query_upper: str) -> bool:
    """Detect EXPLAIN statements that wrap write operations."""
    if not query_upper.startswith('EXPLAIN'):
        return False

    explain_body = re.sub(
        r'^EXPLAIN\s*(?:\((?:[^()]|\([^()]*\))*\)\s*)*(?:ANALYZE\s+)?',
        '',
        query_upper,
        count=1,
    ).lstrip()
    return bool(re.match(r'^(UPDATE|DELETE|INSERT|MERGE)\b', explain_body))



def _is_read_only_query(query: str) -> bool:
    query_upper = _normalize_sql_for_readonly_check(query)
    simple_allowed_keywords = ['SELECT', 'SHOW', 'EXPLAIN', 'DESCRIBE', 'DESC']

    if query_upper.startswith('EXPLAIN'):
        return not _is_explain_write_query(query_upper)

    if query_upper.startswith('WITH'):
        return not re.search(r'\b(INSERT|UPDATE|DELETE|MERGE)\b', query_upper)

    if any(query_upper.startswith(keyword) for keyword in simple_allowed_keywords):
        # 单条语句末尾的分号是合法的，只读查询仍然允许
        # 多条语句（分号分隔）则拒绝
        if ';' in query_upper:
            return False
        return True

    if ';' in query_upper:
        return False

    return False


async def execute_query(datasource: Datasource, query: str, allow_write: bool = False) -> Dict[str, Any]:
    """Execute a query on a database datasource

    Args:
        datasource: The datasource to execute against
        query: The SQL query to execute
        allow_write: If False (default), only SELECT/SHOW/EXPLAIN queries are allowed.
                     If True, all queries including DDL/DML are allowed.
    """
    try:
        # Validate query if write operations are not allowed
        if not allow_write:
            if not _is_read_only_query(query):
                return {
                    "success": False,
                    "error": "Only read-only queries (SELECT, SHOW, EXPLAIN, DESCRIBE) are allowed. Enable 'Execute Any SQL' permission for write operations."
                }

        # Decrypt password
        password = decrypt_value(datasource.password_encrypted) if datasource.password_encrypted else None

        # Get appropriate service
        if datasource.db_type in {"mysql", "tdsql-c-mysql"}:
            service = MySQLConnector(
                host=datasource.host,
                port=datasource.port,
                username=datasource.username,
                password=password,
                database=datasource.database,
            )
        elif datasource.db_type == "postgresql":
            service = PostgreSQLConnector(
                host=datasource.host,
                port=datasource.port,
                username=datasource.username,
                password=password,
                database=datasource.database,
            )
        elif datasource.db_type == "sqlserver":
            service = SQLServerConnector(
                host=datasource.host,
                port=datasource.port,
                username=datasource.username,
                password=password,
                database=datasource.database,
                **(datasource.extra_params or {}),
            )
        elif datasource.db_type == "oracle":
            service = OracleConnector(
                host=datasource.host,
                port=datasource.port,
                username=datasource.username,
                password=password,
                database=datasource.database,
                **(datasource.extra_params or {}),
            )
        elif datasource.db_type == "opengauss":
            service = OpenGaussConnector(
                host=datasource.host,
                port=datasource.port,
                username=datasource.username,
                password=password,
                database=datasource.database,
            )
        elif datasource.db_type == "hana":
            service = HANAConnector(
                host=datasource.host,
                port=datasource.port,
                username=datasource.username,
                password=password,
                database=datasource.database,
                **(datasource.extra_params or {}),
            )
        else:
            return {"success": False, "error": f"Unsupported database type: {datasource.db_type}"}

        # Execute query
        result = await service.execute_query(query)
        # Add success flag if not present
        if "success" not in result:
            result["success"] = True
        # Convert to data format expected by skills
        if "rows" in result and "data" not in result:
            result["data"] = result["rows"]
        return result

    except Exception as e:
        error_message = _get_non_empty_error_message(e)
        logger.error(
            f"Failed to execute query on datasource {datasource.id} ({datasource.name}): {error_message}",
            exc_info=True,
        )
        return {
            "success": False,
            "error": error_message,
            "error_type": e.__class__.__name__,
        }
