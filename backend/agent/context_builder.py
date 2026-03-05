import json
import logging
from typing import Any, Dict, Optional

from sqlalchemy import select, desc
from backend.database import async_session
from backend.models.connection import Connection
from backend.models.metric_snapshot import MetricSnapshot
from backend.models.ssh_host import SSHHost
from backend.services.db_connector import get_connector
from backend.services.ssh_service import SSHService
from backend.services.os_metrics_service import OSMetricsService
from backend.utils.encryption import decrypt_value

logger = logging.getLogger(__name__)


async def _get_connection(conn_id: int):
    async with async_session() as db:
        result = await db.execute(select(Connection).where(Connection.id == conn_id))
        return result.scalar_one_or_none()


async def _get_connector_for(conn_id: int):
    conn = await _get_connection(conn_id)
    if not conn:
        raise ValueError(f"Connection {conn_id} not found")
    password = decrypt_value(conn.password_encrypted) if conn.password_encrypted else None
    return get_connector(
        db_type=conn.db_type, host=conn.host, port=conn.port,
        username=conn.username, password=password, database=conn.database,
    ), conn


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
        "search_knowledge_base": _tool_search_knowledge_base,
    }

    handler = handlers.get(tool_name)
    if not handler:
        return {"error": f"Unknown tool: {tool_name}"}
    return await handler(args)


async def _tool_get_db_status(args):
    connector, _ = await _get_connector_for(args["connection_id"])
    try:
        return await connector.get_status()
    finally:
        await connector.close()


async def _tool_get_db_variables(args):
    connector, _ = await _get_connector_for(args["connection_id"])
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
    connector, _ = await _get_connector_for(args["connection_id"])
    try:
        return await connector.get_process_list()
    finally:
        await connector.close()


async def _tool_get_slow_queries(args):
    connector, _ = await _get_connector_for(args["connection_id"])
    try:
        return await connector.get_slow_queries()
    finally:
        await connector.close()


async def _tool_get_table_stats(args):
    connector, _ = await _get_connector_for(args["connection_id"])
    try:
        return await connector.get_table_stats()
    finally:
        await connector.close()


async def _tool_get_replication_status(args):
    connector, _ = await _get_connector_for(args["connection_id"])
    try:
        return await connector.get_replication_status()
    finally:
        await connector.close()


async def _tool_get_db_size(args):
    connector, _ = await _get_connector_for(args["connection_id"])
    try:
        return await connector.get_db_size()
    finally:
        await connector.close()


async def _tool_execute_query(args):
    sql = args.get("sql", "").strip()
    upper = sql.upper()
    if not upper.startswith("SELECT") and not upper.startswith("SHOW") and not upper.startswith("EXPLAIN"):
        return {"error": "Only SELECT/SHOW/EXPLAIN queries are allowed for diagnostics"}
    connector, _ = await _get_connector_for(args["connection_id"])
    try:
        return await connector.execute_query(sql, max_rows=100)
    finally:
        await connector.close()


async def _tool_explain_query(args):
    connector, _ = await _get_connector_for(args["connection_id"])
    try:
        return await connector.explain_query(args["sql"])
    finally:
        await connector.close()


async def _tool_get_os_metrics(args):
    conn = await _get_connection(args["connection_id"])
    if not conn or not conn.ssh_host_id:
        return {"error": "No SSH host configured for this connection"}

    async with async_session() as db:
        result = await db.execute(select(SSHHost).where(SSHHost.id == conn.ssh_host_id))
        ssh_host = result.scalar_one_or_none()
        if not ssh_host:
            return {"error": "SSH host not found"}

    password = decrypt_value(ssh_host.password_encrypted) if ssh_host.password_encrypted else None
    private_key = decrypt_value(ssh_host.private_key_encrypted) if ssh_host.private_key_encrypted else None
    ssh = SSHService(
        host=ssh_host.host, port=ssh_host.port, username=ssh_host.username,
        password=password, private_key=private_key,
    )
    os_svc = OSMetricsService(ssh)
    return os_svc.collect()


async def _tool_execute_os_command(args):
    """Execute a shell command on the DB host via SSH with safety checks."""
    conn = await _get_connection(args["connection_id"])
    if not conn or not conn.ssh_host_id:
        return {"error": "No SSH host configured for this connection"}

    command = args.get("command", "").strip()
    if not command:
        return {"error": "No command provided"}

    # Block destructive commands
    blocked = ["rm ", "rmdir", "mkfs", "dd ", "shutdown", "reboot", "poweroff",
               "init ", "halt", "kill -9", "killall", "pkill", "mv ", "cp ",
               "chmod", "chown", "useradd", "userdel", "passwd", "iptables",
               "systemctl stop", "systemctl disable", "service stop",
               "> /dev/", "format", "fdisk", "parted", "wipefs"]
    cmd_lower = command.lower()
    for b in blocked:
        if b in cmd_lower:
            return {"error": f"Command blocked for safety: contains '{b.strip()}'. Only read-only diagnostic commands are allowed."}

    async with async_session() as db:
        result = await db.execute(select(SSHHost).where(SSHHost.id == conn.ssh_host_id))
        ssh_host = result.scalar_one_or_none()
        if not ssh_host:
            return {"error": "SSH host not found"}

    password = decrypt_value(ssh_host.password_encrypted) if ssh_host.password_encrypted else None
    private_key = decrypt_value(ssh_host.private_key_encrypted) if ssh_host.private_key_encrypted else None
    ssh = SSHService(
        host=ssh_host.host, port=ssh_host.port, username=ssh_host.username,
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
    conn_id = args["connection_id"]
    metric_type = args.get("metric_type", "db_status")
    limit = args.get("limit", 20)

    async with async_session() as db:
        result = await db.execute(
            select(MetricSnapshot)
            .where(
                MetricSnapshot.connection_id == conn_id,
                MetricSnapshot.metric_type == metric_type,
            )
            .order_by(desc(MetricSnapshot.collected_at))
            .limit(limit)
        )
        snapshots = result.scalars().all()
        return [{"data": s.data, "collected_at": s.collected_at.isoformat() if s.collected_at else None}
                for s in snapshots]


async def _tool_list_connections(args):
    async with async_session() as db:
        result = await db.execute(select(Connection).where(Connection.is_active == True))
        conns = result.scalars().all()
        return [
            {"id": c.id, "name": c.name, "db_type": c.db_type,
             "host": c.host, "port": c.port, "database": c.database}
            for c in conns
        ]


async def _tool_search_knowledge_base(args):
    """Search knowledge bases for relevant documentation."""
    from backend.models.knowledge_base import KnowledgeBase
    from backend.services.vector_store import VectorStore
    from backend.config import get_settings

    query = args.get("query", "").strip()
    if not query:
        return {"error": "Query is required"}

    kb_ids = args.get("kb_ids")
    top_k = args.get("top_k", 5)

    # Get session context if available (passed via args)
    session_kb_ids = args.get("session_kb_ids")

    # Determine which KBs to search
    if kb_ids:
        search_kb_ids = kb_ids
    elif session_kb_ids:
        search_kb_ids = session_kb_ids
    else:
        # Search all active KBs
        async with async_session() as db:
            result = await db.execute(
                select(KnowledgeBase.id).where(KnowledgeBase.is_active == True)
            )
            search_kb_ids = [row[0] for row in result.all()]

    if not search_kb_ids:
        return {"message": "No knowledge bases available to search"}

    # Get KBs
    async with async_session() as db:
        result = await db.execute(
            select(KnowledgeBase).where(KnowledgeBase.id.in_(search_kb_ids))
        )
        kbs = result.scalars().all()

    if not kbs:
        return {"message": "No knowledge bases found"}

    # Search each KB
    settings = get_settings()
    vector_store = VectorStore(
        persist_dir=settings.chroma_persist_dir,
        embedding_model=settings.embedding_model,
    )

    all_results = []
    for kb in kbs:
        try:
            results = vector_store.search(kb.collection_name, query, top_k=top_k)
            for result in results:
                all_results.append({
                    "content": result["content"][:2000],  # Truncate to avoid token overflow
                    "filename": result["metadata"].get("filename", "unknown"),
                    "file_type": result["metadata"].get("file_type", "unknown"),
                    "document_id": result["metadata"].get("document_id"),
                    "kb_id": kb.id,
                    "kb_name": kb.name,
                    "distance": result["distance"],
                    "chunk_index": result["metadata"].get("chunk_index", 0),
                })
        except Exception as e:
            logger.warning(f"Error searching KB {kb.id}: {e}")

    # Sort by distance (lower is better) and take top_k
    all_results.sort(key=lambda x: x["distance"])
    all_results = all_results[:top_k]

    if not all_results:
        return {"message": "No relevant documentation found"}

    return {"results": all_results, "query": query}
