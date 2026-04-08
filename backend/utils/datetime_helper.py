"""
DateTime helper utilities - use local timezone consistently
"""
from datetime import datetime
from typing import Optional


def now() -> datetime:
    """Get current local time (without timezone info)"""
    return datetime.now()


def normalize_local_datetime(dt: Optional[datetime]) -> Optional[datetime]:
    """Normalize query datetimes to local naive values for TIMESTAMP columns."""
    if dt is None:
        return None

    if dt.tzinfo is None or dt.tzinfo.utcoffset(dt) is None:
        return dt

    return dt.astimezone().replace(tzinfo=None)


def format_datetime(dt: datetime, fmt: str = "%Y-%m-%d %H:%M:%S") -> str:
    """Format datetime to string"""
    if dt is None:
        return ""
    return dt.strftime(fmt)
