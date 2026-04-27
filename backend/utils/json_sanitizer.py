from __future__ import annotations

from datetime import date, datetime, time
from decimal import Decimal
from typing import Any


def sanitize_for_json(value: Any) -> Any:
    """Recursively convert values into JSON-serializable primitives."""
    if isinstance(value, dict):
        return {key: sanitize_for_json(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [sanitize_for_json(item) for item in value]
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (datetime, date, time)):
        return value.isoformat()
    return value
