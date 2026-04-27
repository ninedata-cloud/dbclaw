"""
DateTime helper utilities - use timezone-aware UTC timestamps consistently.
"""
from datetime import datetime, timezone
from typing import Optional


def now() -> datetime:
    """Get current UTC time with timezone info."""
    return datetime.now(timezone.utc)


def normalize_local_datetime(dt: Optional[datetime]) -> Optional[datetime]:
    """Normalize datetimes to UTC aware values for TIMESTAMP WITH TIME ZONE columns."""
    if dt is None:
        return None

    if dt.tzinfo is None or dt.tzinfo.utcoffset(dt) is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def format_datetime(dt: datetime, fmt: str = "%Y-%m-%d %H:%M:%S") -> str:
    """Format datetime to string"""
    if dt is None:
        return ""
    return dt.strftime(fmt)


def to_utc_isoformat(dt: Optional[datetime]) -> Optional[str]:
    """Convert UTC datetime to ISO format string with 'Z' suffix for JSON serialization.

    Args:
        dt: UTC datetime

    Returns:
        ISO format string with 'Z' suffix (e.g., '2026-04-20T12:34:56Z'), or None if dt is None
    """
    if dt is None:
        return None
    if dt.tzinfo is None or dt.tzinfo.utcoffset(dt) is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).replace(tzinfo=None).isoformat() + 'Z'


def to_local_time(dt: Optional[datetime], tz_offset_hours: int = 8) -> Optional[datetime]:
    """Convert UTC datetime to local time (default: Asia/Shanghai UTC+8).

    Args:
        dt: UTC datetime
        tz_offset_hours: Timezone offset in hours (default: 8 for Beijing/Shanghai)

    Returns:
        Local datetime with timezone info, or None if dt is None
    """
    if dt is None:
        return None

    # Ensure dt is timezone-aware UTC
    if dt.tzinfo is None or dt.tzinfo.utcoffset(dt) is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)

    # Convert to local timezone
    from datetime import timedelta
    local_tz = timezone(timedelta(hours=tz_offset_hours))
    return dt.astimezone(local_tz)


def format_local_datetime(dt: Optional[datetime], fmt: str = "%Y-%m-%d %H:%M:%S", tz_offset_hours: int = 8) -> str:
    """Format UTC datetime to local time string (default: Asia/Shanghai UTC+8).

    Args:
        dt: UTC datetime
        fmt: Format string (default: "%Y-%m-%d %H:%M:%S")
        tz_offset_hours: Timezone offset in hours (default: 8 for Beijing/Shanghai)

    Returns:
        Formatted local time string, or empty string if dt is None
    """
    if dt is None:
        return ""

    local_dt = to_local_time(dt, tz_offset_hours)
    return local_dt.strftime(fmt)
