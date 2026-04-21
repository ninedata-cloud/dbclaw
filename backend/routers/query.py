import time
import logging
import asyncio
import inspect
from collections import defaultdict, deque
from uuid import uuid4
from typing import Optional, List, Dict
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from backend.database import get_db
from backend.models.datasource import Datasource
from backend.models.soft_delete import alive_filter
from backend.schemas.query import (
    QueryExecuteRequest, QueryExplainRequest, QueryResult,
    QueryCancelRequest, QueryCancelResponse, SchemaInfo,
    TableInfo, ColumnInfo, QueryContextResponse
)
from backend.services.db_connector import get_connector
from backend.services.asyncpg_query_executor import execute_asyncpg_query
from backend.services.query_execution_state import QueryExecutionState, QueryCancelledError
from backend.utils.encryption import decrypt_value
from backend.utils.db_connector import _is_read_only_query

from backend.dependencies import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/query", tags=["query"], dependencies=[Depends(get_current_user)])

# Keep a small per-user in-memory history to avoid cross-user data leakage.
_query_history_by_user: dict[int, deque] = defaultdict(lambda: deque(maxlen=100))
_active_queries_by_request_id: dict[str, QueryExecutionState] = {}
_active_queries_lock = asyncio.Lock()
_DB_TYPES_WITH_DATABASE_LIST_FROM_SCHEMAS = {"mysql", "tdsql-c-mysql"}
_DB_TYPES_WITH_SCHEMA_SELECTOR = {"postgresql", "sqlserver", "hana"}
_DEFAULT_SCHEMA_BY_DB_TYPE = {
    "postgresql": "public",
    "sqlserver": "dbo",
    "hana": "SYS",
}


def _normalize_optional_text(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None


def _resolve_current_value(requested: Optional[str], fallback: Optional[str], available: List[str]) -> Optional[str]:
    if requested and (not available or requested in available):
        return requested
    if fallback and (not available or fallback in available):
        return fallback
    return available[0] if available else fallback


def _quote_postgres_identifier(identifier: str) -> str:
    escaped = identifier.replace('"', '""')
    return f'"{escaped}"'


async def _register_active_query(state: QueryExecutionState) -> None:
    async with _active_queries_lock:
        _active_queries_by_request_id[state.request_id] = state


async def _get_active_query(request_id: str, user_id: int) -> Optional[QueryExecutionState]:
    async with _active_queries_lock:
        state = _active_queries_by_request_id.get(request_id)
    if state and state.user_id == user_id:
        return state
    return None


async def _remove_active_query(request_id: str) -> None:
    async with _active_queries_lock:
        _active_queries_by_request_id.pop(request_id, None)


async def _get_connector_for(datasource_id: int, db: AsyncSession, database_override: Optional[str] = None):
    result = await db.execute(select(Datasource).where(Datasource.id == datasource_id, alive_filter(Datasource)))
    datasource = result.scalar_one_or_none()
    if not datasource:
        raise HTTPException(status_code=404, detail="Datasource not found")
    password = decrypt_value(datasource.password_encrypted) if datasource.password_encrypted else None
    target_database = database_override if database_override is not None else datasource.database
    return get_connector(
        db_type=datasource.db_type, host=datasource.host, port=datasource.port,
        username=datasource.username, password=password, database=target_database,
        extra_params=datasource.extra_params,
    ), datasource


async def _get_postgresql_databases(connector) -> List[str]:
    conn = await connector._connect()
    try:
        rows = await conn.fetch(
            "SELECT datname "
            "FROM pg_database "
            "WHERE datistemplate = false AND datallowconn = true "
            "ORDER BY datname"
        )
        return [row["datname"] for row in rows]
    finally:
        await conn.close()


async def _get_sqlserver_databases(connector) -> List[str]:
    def _load():
        conn = connector._connect()
        try:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT name "
                "FROM sys.databases "
                "WHERE state_desc = 'ONLINE' "
                "ORDER BY CASE WHEN database_id > 4 THEN 0 ELSE 1 END, name"
            )
            return [row[0] for row in cursor.fetchall()]
        finally:
            conn.close()

    return await asyncio.get_running_loop().run_in_executor(None, _load)


async def _get_database_options(datasource: Datasource, connector) -> List[str]:
    if datasource.db_type in _DB_TYPES_WITH_DATABASE_LIST_FROM_SCHEMAS:
        return await connector.get_schemas()
    if datasource.db_type == "postgresql":
        return await _get_postgresql_databases(connector)
    if datasource.db_type == "sqlserver":
        return await _get_sqlserver_databases(connector)
    return [datasource.database] if datasource.database else []


async def _execute_postgresql_query_with_context(
    connector,
    sql: str,
    max_rows: int,
    schema: Optional[str],
    execution_state: Optional[QueryExecutionState] = None,
) -> Dict:
    conn = await connector._connect()
    try:
        if execution_state is not None:
            row = await conn.fetchrow("SELECT pg_backend_pid() AS pid")
            execution_state.session_id = str(row["pid"]) if row and row["pid"] is not None else None
            if execution_state.cancel_requested:
                raise QueryCancelledError("查询已取消")

        if schema:
            quoted_schema = _quote_postgres_identifier(schema)
            await conn.execute(f"SET search_path TO {quoted_schema}, public")
        if execution_state is not None and execution_state.cancel_requested:
            raise QueryCancelledError("查询已取消")
        return await execute_asyncpg_query(conn, sql, max_rows=max_rows, explain_uses_fetch=False)
    except QueryCancelledError:
        raise
    except Exception as exc:
        if execution_state is not None and execution_state.cancel_requested:
            raise QueryCancelledError("查询已取消") from exc
        raise
    finally:
        await conn.close()


async def _explain_postgresql_query_with_context(connector, sql: str, schema: Optional[str]) -> Dict:
    conn = await connector._connect()
    try:
        if schema:
            quoted_schema = _quote_postgres_identifier(schema)
            await conn.execute(f"SET search_path TO {quoted_schema}, public")
        rows = await conn.fetch(f"EXPLAIN (FORMAT JSON) {sql}")
        return {"plan": [dict(r) for r in rows]}
    finally:
        await conn.close()


@router.get("/context", response_model=QueryContextResponse)
async def get_query_context(
    datasource_id: int,
    database: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    requested_database = _normalize_optional_text(database)
    listing_connector, datasource = await _get_connector_for(datasource_id, db, requested_database)
    try:
        databases = await _get_database_options(datasource, listing_connector)
    finally:
        await listing_connector.close()

    current_database = _resolve_current_value(requested_database, datasource.database, databases)
    supports_schema = datasource.db_type in _DB_TYPES_WITH_SCHEMA_SELECTOR
    schemas: List[str] = []
    current_schema: Optional[str] = None

    if supports_schema:
        schema_connector, _ = await _get_connector_for(datasource_id, db, current_database)
        try:
            schemas = await schema_connector.get_schemas()
        finally:
            await schema_connector.close()
        current_schema = _resolve_current_value(
            None,
            _DEFAULT_SCHEMA_BY_DB_TYPE.get(datasource.db_type),
            schemas,
        )

    return QueryContextResponse(
        db_type=datasource.db_type,
        supports_database=bool(databases),
        supports_schema=supports_schema,
        current_database=current_database,
        current_schema=current_schema,
        databases=databases,
        schemas=schemas,
    )


@router.post("/execute", response_model=QueryResult)
async def execute_query(
    req: QueryExecuteRequest,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    if not _is_read_only_query(req.sql):
        raise HTTPException(status_code=400, detail="Only read-only queries are allowed. DML/DDL statements are blocked.")

    history = _query_history_by_user[current_user.id]
    selected_database = _normalize_optional_text(req.database)
    selected_schema = _normalize_optional_text(req.schema_name)
    connector, datasource = await _get_connector_for(req.datasource_id, db, selected_database)
    request_id = (req.request_id or str(uuid4())).strip()
    execution_state = QueryExecutionState(
        request_id=request_id,
        datasource_id=req.datasource_id,
        user_id=current_user.id,
        db_type=datasource.db_type,
        sql=req.sql,
    )
    await _register_active_query(execution_state)
    try:
        if datasource.db_type == "postgresql":
            result = await _execute_postgresql_query_with_context(
                connector,
                req.sql,
                req.max_rows,
                selected_schema,
                execution_state=execution_state,
            )
        else:
            result = await connector.execute_query(
                req.sql,
                max_rows=req.max_rows,
                execution_state=execution_state,
            )

        if execution_state.cancel_requested:
            raise QueryCancelledError("查询已取消")

        history.append({
            "id": len(history) + 1,
            "datasource_id": req.datasource_id,
            "sql": req.sql,
            "execution_time_ms": result.get("execution_time_ms", 0),
            "row_count": result.get("row_count", 0),
            "executed_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        })
        # Serialize any non-JSON-compatible values
        rows = []
        for row in result.get("rows", []):
            rows.append([str(v) if not isinstance(v, (str, int, float, bool, type(None))) else v for v in row])
        return QueryResult(
            columns=result.get("columns", []),
            rows=rows,
            row_count=result.get("row_count", 0),
            execution_time_ms=result.get("execution_time_ms", 0),
            truncated=result.get("truncated", False),
            message=result.get("message"),
        )
    except QueryCancelledError:
        raise HTTPException(status_code=409, detail="查询已取消")
    except Exception as e:
        if execution_state.cancel_requested:
            raise HTTPException(status_code=409, detail="查询已取消") from e
        logger.error(f"Query execute failed: datasource_id={req.datasource_id}, sql={req.sql!r}, error={e}", exc_info=True)
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        await _remove_active_query(request_id)
        await connector.close()


@router.post("/cancel", response_model=QueryCancelResponse)
async def cancel_query(
    req: QueryCancelRequest,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    execution_state = await _get_active_query(req.request_id, current_user.id)
    if not execution_state or execution_state.datasource_id != req.datasource_id:
        return QueryCancelResponse(success=True, message="查询已结束或未找到对应执行任务")

    execution_state.cancel_requested = True

    if not execution_state.session_id:
        return QueryCancelResponse(success=True, message="已收到取消请求，正在等待数据库会话就绪")

    if execution_state.cancel_callback is not None:
        try:
            cancel_result = execution_state.cancel_callback()
            if inspect.isawaitable(cancel_result):
                await cancel_result
            return QueryCancelResponse(success=True, message="已发送取消请求")
        except Exception as exc:
            logger.warning(
                "Cancel callback failed: request_id=%s, datasource_id=%s, session_id=%s, error=%s",
                req.request_id,
                req.datasource_id,
                execution_state.session_id,
                exc,
                exc_info=True,
            )
            raise HTTPException(status_code=400, detail=f"取消查询失败: {exc}") from exc

    connector, _ = await _get_connector_for(execution_state.datasource_id, db)
    try:
        result = await connector.cancel_query(execution_state.session_id)
        if isinstance(result, dict) and result.get("success") is False:
            raise HTTPException(status_code=400, detail=result.get("message") or "取消查询失败")

        message = result.get("message") if isinstance(result, dict) else None
        return QueryCancelResponse(success=True, message=message or "已发送取消请求")
    except NotImplementedError as exc:
        raise HTTPException(status_code=400, detail="当前数据源暂不支持取消 SQL 执行") from exc
    except HTTPException:
        raise
    except Exception as exc:
        logger.warning(
            "Cancel query failed: request_id=%s, datasource_id=%s, session_id=%s, error=%s",
            req.request_id,
            req.datasource_id,
            execution_state.session_id,
            exc,
            exc_info=True,
        )
        raise HTTPException(status_code=400, detail=f"取消查询失败: {exc}") from exc
    finally:
        await connector.close()


@router.post("/explain")
async def explain_query(req: QueryExplainRequest, db: AsyncSession = Depends(get_db)):
    if not _is_read_only_query(req.sql):
        raise HTTPException(status_code=400, detail="Only read-only queries can be explained.")

    selected_database = _normalize_optional_text(req.database)
    selected_schema = _normalize_optional_text(req.schema_name)
    connector, datasource = await _get_connector_for(req.datasource_id, db, selected_database)
    try:
        if datasource.db_type == "postgresql":
            result = await _explain_postgresql_query_with_context(connector, req.sql, selected_schema)
        else:
            result = await connector.explain_query(req.sql)
        return result
    except Exception as e:
        logger.error(f"Query explain failed: datasource_id={req.datasource_id}, sql={req.sql!r}, error={e}", exc_info=True)
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        await connector.close()


@router.get("/history")
async def get_query_history(current_user=Depends(get_current_user)):
    history = _query_history_by_user[current_user.id]
    return list(reversed(history))


@router.get("/schema/databases", response_model=List[SchemaInfo])
async def get_databases(datasource_id: int, database: Optional[str] = None, db: AsyncSession = Depends(get_db)):
    """Get list of schemas/databases for autocomplete."""
    selected_database = _normalize_optional_text(database)
    connector, datasource = await _get_connector_for(datasource_id, db, selected_database)
    try:
        schemas = await connector.get_schemas()
        return [SchemaInfo(name=s) for s in schemas]
    except Exception as e:
        logger.error(f"Error fetching schemas: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        await connector.close()


@router.get("/schema/tables", response_model=List[TableInfo])
async def get_tables(
    datasource_id: int,
    schema: Optional[str] = None,
    database: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    """Get list of tables for autocomplete."""
    selected_database = _normalize_optional_text(database)
    connector, datasource = await _get_connector_for(datasource_id, db, selected_database)
    try:
        tables = await connector.get_tables(_normalize_optional_text(schema))
        return [TableInfo(**t) for t in tables]
    except Exception as e:
        logger.error(f"Error fetching tables: {e}", exc_info=True)
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        await connector.close()


@router.get("/schema/columns", response_model=List[ColumnInfo])
async def get_columns(
    datasource_id: int,
    table: str,
    schema: Optional[str] = None,
    database: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    """Get list of columns for a specific table."""
    selected_database = _normalize_optional_text(database)
    connector, datasource = await _get_connector_for(datasource_id, db, selected_database)
    try:
        columns = await connector.get_columns(table, _normalize_optional_text(schema))
        return [ColumnInfo(**c) for c in columns]
    except Exception as e:
        logger.error(f"Error fetching columns: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        await connector.close()
