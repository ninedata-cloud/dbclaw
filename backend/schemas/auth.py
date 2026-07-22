from pydantic import BaseModel, Field, field_validator
from typing import Optional
from datetime import datetime
from backend.schemas.base import TimestampSerializerMixin
from backend.i18n.locale import DEFAULT_LOCALE, DEFAULT_TIMEZONE, normalize_locale, normalize_timezone


class PreferenceFields(BaseModel):
    locale: str = DEFAULT_LOCALE
    timezone: str = DEFAULT_TIMEZONE

    @field_validator("locale")
    @classmethod
    def validate_locale(cls, value: str) -> str:
        normalized = normalize_locale(value)
        if not normalized:
            raise ValueError("Unsupported locale")
        return normalized

    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, value: str) -> str:
        normalized = normalize_timezone(value)
        if not normalized:
            raise ValueError("Invalid IANA time zone")
        return normalized


class LoginRequest(BaseModel):
    username: str
    password: str


class UserResponse(TimestampSerializerMixin, PreferenceFields):
    id: int
    username: str
    display_name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    is_active: bool
    is_admin: bool
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class LoginResponse(BaseModel):
    user: UserResponse


class ChangePasswordRequest(BaseModel):
    old_password: str
    new_password: str = Field(..., min_length=6)


class CurrentUserUpdateRequest(BaseModel):
    display_name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    locale: Optional[str] = None
    timezone: Optional[str] = None

    _validate_locale = field_validator("locale")(PreferenceFields.validate_locale.__func__)
    _validate_timezone = field_validator("timezone")(PreferenceFields.validate_timezone.__func__)


class LocaleUpdateRequest(BaseModel):
    locale: str
    timezone: Optional[str] = None

    _validate_locale = field_validator("locale")(PreferenceFields.validate_locale.__func__)
    _validate_timezone = field_validator("timezone")(PreferenceFields.validate_timezone.__func__)


class UserCreate(BaseModel):
    username: str = Field(..., min_length=1, max_length=50)
    password: str = Field(..., min_length=6)
    display_name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    is_admin: bool = False
    locale: str = DEFAULT_LOCALE
    timezone: str = DEFAULT_TIMEZONE

    _validate_locale = field_validator("locale")(PreferenceFields.validate_locale.__func__)
    _validate_timezone = field_validator("timezone")(PreferenceFields.validate_timezone.__func__)


class UserUpdate(BaseModel):
    display_name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    is_admin: Optional[bool] = None
    locale: Optional[str] = None
    timezone: Optional[str] = None

    _validate_locale = field_validator("locale")(PreferenceFields.validate_locale.__func__)
    _validate_timezone = field_validator("timezone")(PreferenceFields.validate_timezone.__func__)


class ResetPasswordRequest(BaseModel):
    new_password: str = Field(..., min_length=6)


class LoginLogResponse(TimestampSerializerMixin, BaseModel):
    id: int
    user_id: int
    login_time: Optional[datetime] = None
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    success: bool

    class Config:
        from_attributes = True
