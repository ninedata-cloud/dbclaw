import time
import logging
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from backend.database import get_db
from backend.models.datasource import Datasource
from backend.schemas.query import (
    QueryExecuteRequest, QueryExplainRequest, QueryResult,
    SchemaInfo, TableInfo, ColumnInfo
)
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


async def _get_connector_for(datasource_id: int, db: AsyncSession):
    result = await db.execute(select(Datasource).where(Datasource.id == datasource_id))
    datasource = result.scalar_one_or_none()
    if not datasource:
        raise HTTPException(status_code=404, detail="Datasource not found")
    password = decrypt_value(datasource.password_encrypted) if datasource.password_encrypted else None
    return get_connector(
        db_type=datasource.db_type, host=datasource.host, port=datasource.port,
        username=datasource.username, password=password, database=datasource.database,
        extra_params=datasource.extra_params,
    ), datasource


@router.post("/execute", response_model=QueryResult)
async def execute_query(req: QueryExecuteRequest, db: AsyncSession = Depends(get_db)):
    if not _is_safe_query(req.sql):
        raise HTTPException(status_code=400, detail="Only read-only queries are allowed. DML/DDL statements are blocked.")

    connector, datasource = await _get_connector_for(req.datasource_id, db)
    try:
        result = await connector.execute_query(req.sql, max_rows=req.max_rows)
        _query_history.append({
            "id": len(_query_history) + 1,
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
    except Exception as e:
        logger.error(f"Query execute failed: datasource_id={req.datasource_id}, sql={req.sql!r}, error={e}", exc_info=True)
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        await connector.close()


@router.post("/explain")
async def explain_query(req: QueryExplainRequest, db: AsyncSession = Depends(get_db)):
    connector, datasource = await _get_connector_for(req.datasource_id, db)
    try:
        result = await connector.explain_query(req.sql)
        return result
    except Exception as e:
        logger.error(f"Query explain failed: datasource_id={req.datasource_id}, sql={req.sql!r}, error={e}", exc_info=True)
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        await connector.close()


@router.get("/history")
async def get_query_history():
    return list(reversed(_query_history[-100:]))


@router.get("/schema/databases", response_model=List[SchemaInfo])
async def get_databases(datasource_id: int, db: AsyncSession = Depends(get_db)):
    """Get list of schemas/databases for autocomplete."""
    connector, datasource = await _get_connector_for(datasource_id, db)
    try:
        schemas = await connector.get_schemas()
        return [SchemaInfo(name=s) for s in schemas]
    except Exception as e:
        logger.error(f"Error fetching schemas: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        await connector.close()


@router.get("/schema/tables", response_model=List[TableInfo])
async def get_tables(datasource_id: int, schema: Optional[str] = None, db: AsyncSession = Depends(get_db)):
    """Get list of tables for autocomplete."""
    connector, datasource = await _get_connector_for(datasource_id, db)
    try:
        tables = await connector.get_tables(schema)
        return [TableInfo(**t) for t in tables]
    except Exception as e:
        logger.error(f"Error fetching tables: {e}", exc_info=True)
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        await connector.close()


@router.get("/schema/columns", response_model=List[ColumnInfo])
async def get_columns(datasource_id: int, table: str, schema: Optional[str] = None, db: AsyncSession = Depends(get_db)):
    """Get list of columns for a specific table."""
    connector, datasource = await _get_connector_for(datasource_id, db)
    try:
        columns = await connector.get_columns(table, schema)
        return [ColumnInfo(**c) for c in columns]
    except Exception as e:
        logger.error(f"Error fetching columns: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        await connector.close()

