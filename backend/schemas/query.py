from pydantic import BaseModel, Field
from typing import Optional, List, Any


class QueryExecuteRequest(BaseModel):
    datasource_id: int
    sql: str = Field(..., min_length=1)
    max_rows: int = Field(1000, gt=0, le=10000)


class QueryExplainRequest(BaseModel):
    datasource_id: int
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
    datasource_id: int
    sql: str
    execution_time_ms: float
    row_count: int
    executed_at: Optional[str] = None


class SchemaInfo(BaseModel):
    name: str


class TableInfo(BaseModel):
    name: str
    schema: Optional[str] = None
    type: str
    engine: Optional[str] = None
    tablespace: Optional[str] = None
    comment: Optional[str] = None


class ColumnInfo(BaseModel):
    name: str
    type: str
    nullable: bool
    default: Optional[str] = None
    full_type: Optional[str] = None
    key: Optional[str] = None
    extra: Optional[str] = None
    comment: Optional[str] = None
    udt_name: Optional[str] = None
    max_length: Optional[int] = None
    length: Optional[int] = None
    precision: Optional[int] = None
    scale: Optional[int] = None

