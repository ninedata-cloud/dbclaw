from pydantic import BaseModel, Field
from typing import Optional, List, Any


class QueryExecuteRequest(BaseModel):
    connection_id: int
    sql: str = Field(..., min_length=1)
    max_rows: int = Field(1000, gt=0, le=10000)


class QueryExplainRequest(BaseModel):
    connection_id: int
    sql: str = Field(..., min_length=1)


class QueryResult(BaseModel):
    columns: List[str] = []
    rows: List[List[Any]] = []
    row_count: int = 0
    execution_time_ms: float = 0
    truncated: bool = False
    message: Optional[str] = None


class QueryHistoryItem(BaseModel):
    id: int
    connection_id: int
    sql: str
    execution_time_ms: float
    row_count: int
    executed_at: Optional[str] = None
