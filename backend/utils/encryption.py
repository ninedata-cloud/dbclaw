from cryptography.fernet import Fernet
from backend.config import get_settings


def _get_fernet() -> Fernet:
    key = get_settings().encryption_key
    if not key or key == "your-fernet-key-here":
        raise ValueError("ENCRYPTION_KEY is not configured. Set a valid Fernet key in your environment.")
    if isinstance(key, str):
        key = key.encode()
    return Fernet(key)


def encrypt_value(value: str) -> str:
    if not value:
        return ""
    f = _get_fernet()
    return f.encrypt(value.encode()).decode()


def decrypt_value(encrypted: str) -> str:
    if not encrypted:
        return ""
    f = _get_fernet()
    return f.decrypt(encrypted.encode()).decode()
