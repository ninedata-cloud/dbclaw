"""
DateTime helper utilities - use local timezone consistently
"""
from datetime import datetime


def now() -> datetime:
    """Get current local time (without timezone info for SQLite compatibility)"""
    return datetime.now()


def format_datetime(dt: datetime, fmt: str = "%Y-%m-%d %H:%M:%S") -> str:
    """Format datetime to string"""
    if dt is None:
        return ""
    return dt.strftime(fmt)
