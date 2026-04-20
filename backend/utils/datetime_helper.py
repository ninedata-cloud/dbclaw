"""
DateTime helper utilities - use UTC naive timestamps consistently.
"""
from datetime import datetime, timezone
from typing import Optional


def now() -> datetime:
    """Get current UTC time without timezone info."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def normalize_local_datetime(dt: Optional[datetime]) -> Optional[datetime]:
    """Normalize datetimes to UTC naive values for TIMESTAMP columns."""
    if dt is None:
        return None

    if dt.tzinfo is None or dt.tzinfo.utcoffset(dt) is None:
        return dt

    return dt.astimezone(timezone.utc).replace(tzinfo=None)


def format_datetime(dt: datetime, fmt: str = "%Y-%m-%d %H:%M:%S") -> str:
    """Format datetime to string"""
    if dt is None:
        return ""
    return dt.strftime(fmt)


def to_utc_isoformat(dt: Optional[datetime]) -> Optional[str]:
    """Convert naive UTC datetime to ISO format string with 'Z' suffix for JSON serialization.

    Args:
        dt: Naive datetime assumed to be in UTC

    Returns:
        ISO format string with 'Z' suffix (e.g., '2026-04-20T12:34:56Z'), or None if dt is None
    """
    if dt is None:
        return None
    return dt.isoformat() + 'Z'
