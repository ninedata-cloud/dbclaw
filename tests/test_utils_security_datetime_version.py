from datetime import datetime, timezone

import pytest
from jose import JWTError

from backend.utils import datetime_helper
from backend.utils import security
from backend.utils.version_parser import simplify_version


@pytest.mark.unit
def test_escape_and_password_hashing():
    assert security.escape_html("<x>") == "&lt;x&gt;"
    hashed = security.hash_password("secret123")
    assert security.verify_password("secret123", hashed) is True
    assert security.verify_password("bad", hashed) is False


@pytest.mark.unit
def test_session_id_hashing_is_stable():
    sid = "abc"
    assert security.hash_session_id(sid) == security.hash_session_id(sid)


@pytest.mark.unit
def test_public_share_token_create_and_decode():
    token = security.create_public_share_token("alert", 1)
    payload = security.decode_public_share_token(token, "alert", 1)
    assert payload["resource_type"] == "alert"


@pytest.mark.unit
def test_decode_public_share_token_rejects_mismatch():
    token = security.create_public_share_token("alert", 1)
    with pytest.raises(JWTError):
        security.decode_public_share_token(token, "report", 1)


@pytest.mark.unit
def test_datetime_helpers_roundtrip():
    dt = datetime(2026, 1, 1, 0, 0, 0)
    normalized = datetime_helper.normalize_local_datetime(dt)
    assert normalized.tzinfo == timezone.utc
    assert datetime_helper.to_utc_isoformat(dt).endswith("Z")
    assert datetime_helper.format_datetime(dt, "%Y-%m-%d") == "2026-01-01"
    assert datetime_helper.to_local_time(normalized, 8) is not None
    assert datetime_helper.format_local_datetime(normalized, "%Y-%m-%d", 8) == "2026-01-01"


@pytest.mark.unit
def test_datetime_helpers_none_and_empty_outputs():
    assert datetime_helper.normalize_local_datetime(None) is None
    assert datetime_helper.to_utc_isoformat(None) is None
    assert datetime_helper.format_datetime(None, "%Y") == ""
    assert datetime_helper.to_local_time(None, 8) is None
    assert datetime_helper.format_local_datetime(None, "%Y-%m-%d", 8) == ""


@pytest.mark.unit
def test_datetime_helpers_aware_input_preserved_in_normalize():
    aware = datetime(2026, 6, 15, 12, 0, 0, tzinfo=timezone.utc)
    out = datetime_helper.normalize_local_datetime(aware)
    assert out == aware


@pytest.mark.unit
def test_simplify_version_for_postgresql_and_fallback():
    pg = simplify_version("PostgreSQL 16.2 on x86_64", "postgresql")
    assert pg["short"] == "PostgreSQL 16.2"
    assert "x86_64" in pg["details"]

    fallback = simplify_version("X" * 70, "unknown")
    assert fallback["short"].endswith("...")
    assert fallback["full"] == "X" * 70
