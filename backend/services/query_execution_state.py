import time
from dataclasses import dataclass, field
from typing import Any, Callable, Optional


class QueryCancelledError(Exception):
    """Raised when a running query has been cancelled."""


@dataclass
class QueryExecutionState:
    request_id: str
    datasource_id: int
    user_id: int
    db_type: str
    sql: str
    created_at: float = field(default_factory=time.time)
    session_id: Optional[str] = None
    cancel_requested: bool = False
    cancel_callback: Optional[Callable[[], Any]] = None
