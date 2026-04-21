"""
Base schemas with unified datetime serialization
"""
from pydantic import BaseModel, field_serializer
from datetime import datetime
from typing import Any


class UTCDateTimeSerializerMixin:
    """Mixin to serialize datetime fields with 'Z' suffix for UTC"""

    @field_serializer('*', check_fields=False)
    def serialize_datetime(self, value: Any, _info) -> Any:
        """Serialize datetime fields to ISO format with 'Z' suffix"""
        if isinstance(value, datetime):
            return value.isoformat() + 'Z'
        return value


class TimestampSerializerMixin(UTCDateTimeSerializerMixin):
    """Backward-compatible alias for existing schema imports."""
    pass


class BaseSchema(BaseModel, UTCDateTimeSerializerMixin):
    """Base schema with UTC datetime serialization and from_attributes support"""

    class Config:
        from_attributes = True
