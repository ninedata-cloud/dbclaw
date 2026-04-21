from pydantic import BaseModel, ConfigDict, Field
from typing import Optional, List, Any


class QueryExecuteRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    datasource_id: int
    request_id: Optional[str] = Field(None, min_length=1, max_length=128)
    sql: str = Field(..., min_length=1)
    max_rows: int = Field(1000, gt=0, le=10000)
    database: Optional[str] = None
    schema_name: Optional[str] = Field(None, alias="schema")


class QueryExplainRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    datasource_id: int
    sql: str = Field(..., min_length=1)
    database: Optional[str] = None
    schema_name: Optional[str] = Field(None, alias="schema")


class QueryCancelRequest(BaseModel):
    datasource_id: int
    request_id: str = Field(..., min_length=1, max_length=128)


class QueryCancelResponse(BaseModel):
    success: bool = True
    message: str


class QueryResult(BaseModel):
    columns: List[str] = Field(default_factory=list)
    rows: List[List[Any]] = Field(default_factory=list)
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


class QueryContextResponse(BaseModel):
    db_type: str
    supports_database: bool = False
    supports_schema: bool = False
    current_database: Optional[str] = None
    current_schema: Optional[str] = None
    databases: List[str] = Field(default_factory=list)
    schemas: List[str] = Field(default_factory=list)


class TableInfo(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    name: str
    schema_name: Optional[str] = Field(None, alias="schema")
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
