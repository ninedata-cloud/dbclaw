import time
import logging
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from backend.database import get_db
from backend.models.connection import Connection
from backend.schemas.query import QueryExecuteRequest, QueryExplainRequest, QueryResult
from backend.services.db_connector import get_connector
from backend.utils.encryption import decrypt_value

from backend.dependencies import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/query", tags=["query"], dependencies=[Depends(get_current_user)])

# In-memory query history (simple approach)
_query_history = []


def _is_safe_query(sql: str) -> bool:
    """Check if query is read-only (basic safety check)."""
    dangerous = ["DROP ", "DELETE ", "TRUNCATE ", "ALTER ", "CREATE ", "INSERT ", "UPDATE ", "GRANT ", "REVOKE "]
    upper = sql.strip().upper()
    for kw in dangerous:
        if upper.startswith(kw):
            return False
    return True


async def _get_connector_for(conn_id: int, db: AsyncSession):
    result = await db.execute(select(Connection).where(Connection.id == conn_id))
    conn = result.scalar_one_or_none()
    if not conn:
        raise HTTPException(status_code=404, detail="Connection not found")
    password = decrypt_value(conn.password_encrypted) if conn.password_encrypted else None
    return get_connector(
        db_type=conn.db_type, host=conn.host, port=conn.port,
        username=conn.username, password=password, database=conn.database,
    ), conn


@router.post("/execute", response_model=QueryResult)
async def execute_query(req: QueryExecuteRequest, db: AsyncSession = Depends(get_db)):
    if not _is_safe_query(req.sql):
        raise HTTPException(status_code=400, detail="Only read-only queries are allowed. DML/DDL statements are blocked.")

    connector, conn = await _get_connector_for(req.connection_id, db)
    try:
        result = await connector.execute_query(req.sql, max_rows=req.max_rows)
        _query_history.append({
            "id": len(_query_history) + 1,
            "connection_id": req.connection_id,
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
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        await connector.close()


@router.post("/explain")
async def explain_query(req: QueryExplainRequest, db: AsyncSession = Depends(get_db)):
    connector, conn = await _get_connector_for(req.connection_id, db)
    try:
        result = await connector.explain_query(req.sql)
        return result
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        await connector.close()


@router.get("/history")
async def get_query_history():
    return list(reversed(_query_history[-100:]))
