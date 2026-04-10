import ipaddress
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.routers.instances import _json_safe, _normalize_session


def test_json_safe_serializes_ipaddress_objects():
    payload = {
        "client_addr": ipaddress.IPv4Address("192.168.2.10"),
        "nested": {
            "network": ipaddress.IPv4Network("192.168.2.0/24"),
        },
    }

    result = _json_safe(payload)

    assert result == {
        "client_addr": "192.168.2.10",
        "nested": {
            "network": "192.168.2.0/24",
        },
    }


def test_normalize_session_converts_opengauss_client_addr_to_string_in_raw():
    raw = {
        "pid": 12345,
        "usename": "dbguard",
        "client_addr": ipaddress.IPv4Address("192.168.2.10"),
        "datname": "postgres",
        "state": "active",
        "query": "select 1",
    }

    session = _normalize_session(raw, can_terminate=True)

    assert session.client == "192.168.2.10"
    assert session.raw["client_addr"] == "192.168.2.10"
