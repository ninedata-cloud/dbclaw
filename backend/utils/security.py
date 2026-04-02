from datetime import datetime, timedelta, timezone
from html import escape as _escape


def escape_html(s: str | None) -> str:
    """Escape HTML special characters to prevent XSS."""
    if s is None:
        return ''
    return _escape(str(s), quote=True)
import hashlib
import secrets
import uuid
from passlib.context import CryptContext
from jose import jwt, JWTError
from backend.config import get_settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def generate_session_id() -> str:
    return secrets.token_urlsafe(32)


def hash_session_id(raw_session_id: str) -> str:
    return hashlib.sha256(raw_session_id.encode("utf-8")).hexdigest()


def create_public_share_token(resource_type: str, resource_id: int, expires_delta: timedelta | None = None) -> str:
    settings = get_settings()
    now = datetime.now(timezone.utc)
    expire = now + (expires_delta or timedelta(minutes=settings.public_share_expire_minutes))
    payload = {
        "typ": "public_share",
        "aud": "public",
        "jti": str(uuid.uuid4()),
        "iat": now,
        "resource_type": resource_type,
        "resource_id": resource_id,
        "exp": expire,
    }
    return jwt.encode(payload, settings.public_share_secret_key, algorithm=settings.jwt_algorithm)


def decode_public_share_token(token: str, resource_type: str, resource_id: int) -> dict:
    settings = get_settings()
    payload = jwt.decode(token, settings.public_share_secret_key, algorithms=[settings.jwt_algorithm], audience="public")
    if payload.get("typ") != "public_share":
        raise JWTError("Invalid token type")
    if payload.get("resource_type") != resource_type:
        raise JWTError("Invalid resource type")
    if int(payload.get("resource_id", -1)) != int(resource_id):
        raise JWTError("Invalid resource id")
    return payload
