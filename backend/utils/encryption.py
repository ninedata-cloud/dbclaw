from cryptography.fernet import Fernet, InvalidToken
from backend.config import get_settings


def _get_fernet() -> Fernet:
    key = get_settings().encryption_key
    if not key or key == "your-fernet-key-here":
        raise ValueError("ENCRYPTION_KEY is not configured. Set a valid Fernet key in your environment.")
    if isinstance(key, str):
        key = key.encode()
    return Fernet(key)


def _get_legacy_fernets() -> list[Fernet]:
    """Get legacy Fernet instances for backward compatibility during upgrades."""
    settings = get_settings()
    if not settings.legacy_encryption_keys:
        return []

    fernets = []
    for key in settings.legacy_encryption_keys.split(","):
        key = key.strip()
        if key:
            fernets.append(Fernet(key.encode() if isinstance(key, str) else key))
    return fernets


def encrypt_value(value: str) -> str:
    if not value:
        return ""
    f = _get_fernet()
    return f.encrypt(value.encode()).decode()


def decrypt_value(encrypted: str) -> str:
    if not encrypted:
        return ""

    # Try current key first
    f = _get_fernet()
    try:
        return f.decrypt(encrypted.encode()).decode()
    except InvalidToken:
        pass

    # Try legacy keys
    for legacy_f in _get_legacy_fernets():
        try:
            return legacy_f.decrypt(encrypted.encode()).decode()
        except InvalidToken:
            continue

    # All keys failed
    raise InvalidToken("Unable to decrypt value with current or legacy keys")
