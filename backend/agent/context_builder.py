import json
import logging
from typing import Any, Dict, Optional

from sqlalchemy import select, desc
from backend.database import async_session
from backend.models.datasource import Datasource
from backend.models.host import Host
from backend.models.soft_delete import alive_filter
from backend.models.datasource_metric import DatasourceMetric
from backend.services.db_connector import get_connector
from backend.services.ssh_service import SSHService
from backend.services.os_metrics_service import OSMetricsService
from backend.utils.command_safety import STRICTLY_BLOCKED_COMMAND_PATTERNS, first_matching_command_pattern
from backend.utils.db_connector import _is_read_only_query
from backend.utils.encryption import decrypt_value

logger = logging.getLogger(__name__)


async def _get_connection(datasource_id: int):
    async with async_session() as db:
        result = await db.execute(select(Datasource).where(Datasource.id == datasource_id, alive_filter(Datasource)))
        return result.scalar_one_or_none()


async def _get_connector_for(datasource_id: int):
    datasource = await _get_connection(datasource_id)
    if not datasource:
        raise ValueError(f"Datasource {datasource_id} not found")
    password = decrypt_value(datasource.password_encrypted) if datasource.password_encrypted else None
    return get_connector(
        db_type=datasource.db_type, host=datasource.host, port=datasource.port,
        username=datasource.username, password=password, database=datasource.database,
        extra_params=datasource.extra_params,
    ), datasource


async def execute_tool(tool_name: str, arguments: Dict[str, Any]) -> str:
    """Execute a tool and return the result as a JSON string."""
    try:
        result = await _dispatch_tool(tool_name, arguments)
        return json.dumps(result, default=str, ensure_ascii=False)
    except Exception as e:
        logger.error(f"Tool execution error [{tool_name}]: {e}")
        return json.dumps({"error": str(e)})


async def _dispatch_tool(tool_name: str, args: Dict[str, Any]) -> Any:
    handlers = {
        "get_db_status": _tool_get_db_status,
        "get_db_variables": _tool_get_db_variables,
        "get_process_list": _tool_get_process_list,
        "get_slow_queries": _tool_get_slow_queries,
        "get_table_stats": _tool_get_table_stats,
        "get_replication_status": _tool_get_replication_status,
        "get_db_size": _tool_get_db_size,
        "execute_diagnostic_query": _tool_execute_query,
        "explain_query": _tool_explain_query,
        "get_os_metrics": _tool_get_os_metrics,
        "execute_os_command": _tool_execute_os_command,
        "get_metric_history": _tool_get_metric_history,
        "list_connections": _tool_list_connections,
        "list_documents": _tool_list_documents,
        "read_document": _tool_read_document,
    }

    handler = handlers.get(tool_name)
    if not handler:
        return {"error": f"Unknown tool: {tool_name}"}
    return await handler(args)


async def _tool_get_db_status(args):
    connector, _ = await _get_connector_for(args["datasource_id"])
    try:
        return await connector.get_status()
    finally:
        await connector.close()


async def _tool_get_db_variables(args):
    connector, _ = await _get_connector_for(args["datasource_id"])
    try:
        variables = await connector.get_variables()
        # Return subset of important variables to avoid token overflow
        important_keys_mysql = [
            "innodb_buffer_pool_size", "max_connections", "query_cache_size",
            "innodb_log_file_size", "innodb_flush_log_at_trx_commit",
            "slow_query_log", "long_query_time", "binlog_format",
            "innodb_file_per_table", "character_set_server",
        ]
        if len(variables) > 50:
            filtered = {k: v for k, v in variables.items()
                       if any(ik in k.lower() for ik in ["buffer", "cache", "max_conn", "timeout",
                              "slow", "log", "innodb", "shared_buffer", "work_mem", "wal"])}
            if len(filtered) < 10:
                return dict(list(variables.items())[:50])
            return filtered
        return variables
    finally:
        await connector.close()


async def _tool_get_process_list(args):
    connector, _ = await _get_connector_for(args["datasource_id"])
    try:
        return await connector.get_process_list()
    finally:
        await connector.close()


async def _tool_get_slow_queries(args):
    connector, _ = await _get_connector_for(args["datasource_id"])
    try:
        return await connector.get_slow_queries()
    finally:
        await connector.close()


async def _tool_get_table_stats(args):
    connector, _ = await _get_connector_for(args["datasource_id"])
    try:
        return await connector.get_table_stats()
    finally:
        await connector.close()


async def _tool_get_replication_status(args):
    connector, _ = await _get_connector_for(args["datasource_id"])
    try:
        return await connector.get_replication_status()
    finally:
        await connector.close()


async def _tool_get_db_size(args):
    connector, _ = await _get_connector_for(args["datasource_id"])
    try:
        return await connector.get_db_size()
    finally:
        await connector.close()


async def _tool_execute_query(args):
    sql = args.get("sql", "").strip()
    if not _is_read_only_query(sql):
        return {"error": "Only SELECT/SHOW/EXPLAIN queries are allowed for diagnostics"}
    connector, _ = await _get_connector_for(args["datasource_id"])
    try:
        return await connector.execute_query(sql, max_rows=100)
    finally:
        await connector.close()


async def _tool_explain_query(args):
    sql = args.get("sql", "").strip()
    if not _is_read_only_query(sql):
        return {"error": "Only read-only queries can be explained during diagnostics"}
    connector, _ = await _get_connector_for(args["datasource_id"])
    try:
        return await connector.explain_query(sql)
    finally:
        await connector.close()


async def _tool_get_os_metrics(args):
    datasource = await _get_connection(args["datasource_id"])
    if not datasource or not datasource.host_id:
        return {"error": "No SSH host configured for this datasource"}

    async with async_session() as db:
        result = await db.execute(select(Host).where(Host.id == datasource.host_id))
        host = result.scalar_one_or_none()
        if not host:
            return {"error": "SSH host not found"}

    password = decrypt_value(host.password_encrypted) if host.password_encrypted else None
    private_key = decrypt_value(host.private_key_encrypted) if host.private_key_encrypted else None
    ssh = SSHService(
        host=host.host, port=host.port, username=host.username,
        password=password, private_key=private_key,
    )
    os_svc = OSMetricsService(ssh)
    return os_svc.collect()


async def _tool_execute_os_command(args):
    """Execute a shell command on the DB host via SSH with safety checks."""
    datasource = await _get_connection(args["datasource_id"])
    if not datasource or not datasource.host_id:
        return {"error": "No SSH host configured for this datasource"}

    command = args.get("command", "").strip()
    if not command:
        return {"error": "No command provided"}

    # Block destructive commands
    blocked_pattern = first_matching_command_pattern(command, STRICTLY_BLOCKED_COMMAND_PATTERNS)
    if blocked_pattern:
        return {"error": f"Command blocked for safety: contains '{blocked_pattern}'. Only read-only diagnostic commands are allowed."}

    async with async_session() as db:
        result = await db.execute(select(Host).where(Host.id == datasource.host_id))
        host = result.scalar_one_or_none()
        if not host:
            return {"error": "SSH host not found"}

    password = decrypt_value(host.password_encrypted) if host.password_encrypted else None
    private_key = decrypt_value(host.private_key_encrypted) if host.private_key_encrypted else None
    ssh = SSHService(
        host=host.host, port=host.port, username=host.username,
        password=password, private_key=private_key,
    )

    try:
        output = ssh.execute(command, timeout=15)
        # Truncate very long output
        if len(output) > 8000:
            output = output[:8000] + "\n... [output truncated]"
        return {"command": command, "output": output}
    except Exception as e:
        return {"command": command, "error": str(e)}


async def _tool_get_metric_history(args):
    datasource_id = args["datasource_id"]
    metric_type = args.get("metric_type", "db_status")
    limit = args.get("limit", 20)

    async with async_session() as db:
        result = await db.execute(
            select(DatasourceMetric)
            .where(
                DatasourceMetric.datasource_id == datasource_id,
                DatasourceMetric.metric_type == metric_type,
            )
            .order_by(desc(DatasourceMetric.collected_at))
            .limit(limit)
        )
        snapshots = result.scalars().all()
        return [{"data": s.data, "collected_at": s.collected_at.isoformat() if s.collected_at else None}
                for s in snapshots]


async def _tool_list_connections(args):
    async with async_session() as db:
        result = await db.execute(select(Datasource).where(Datasource.is_active == True, alive_filter(Datasource)))
        conns = result.scalars().all()
        return [
            {"id": c.id, "name": c.name, "db_type": c.db_type,
             "host": c.host, "port": c.port, "database": c.database}
            for c in conns
        ]


async def _tool_list_documents(args):
    """列出文档目录，供 AI 决策读哪篇文档"""
    db_type = args.get("db_type")
    from backend.database import async_session
    from backend.services.document_service import list_documents_for_ai
    async with async_session() as db:
        return await list_documents_for_ai(db, db_type)


async def _tool_read_document(args):
    """读取指定文档完整内容"""
    doc_id = args.get("doc_id")
    if not doc_id:
        return {"error": "doc_id is required"}
    from backend.database import async_session
    from backend.models.document import DocDocument, DocCategory
    from sqlalchemy import select
    async with async_session() as db:
        result = await db.execute(
            select(DocDocument, DocCategory.name.label("cat_name"))
            .join(DocCategory, DocDocument.category_id == DocCategory.id)
            .where(DocDocument.id == doc_id, DocDocument.is_active == True)
        )
        row = result.one_or_none()
        if not row:
            return {"error": f"Document {doc_id} not found"}
        doc, cat_name = row.DocDocument, row.cat_name
        return {
            "id": doc.id,
            "title": doc.title,
            "category_name": cat_name,
            "content": doc.content,
            "quality_status": doc.quality_status,
            "compiled_snapshot_summary": doc.compiled_snapshot_summary,
            "diagnosis_profile": doc.diagnosis_profile or {},
        }
