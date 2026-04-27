from datetime import date, datetime, time
from decimal import Decimal

import pytest

from backend.utils.json_sanitizer import sanitize_for_json


@pytest.mark.unit
def test_sanitize_for_json_nested_dict_and_list():
    dt = datetime(2026, 4, 26, 12, 0, 0)
    payload = {
        "n": Decimal("1.5"),
        "d": dt,
        "inner": [{"x": True}, None],
    }
    out = sanitize_for_json(payload)
    assert out["n"] == 1.5
    assert out["d"] == dt.isoformat()
    assert out["inner"][0]["x"] is True
    assert out["inner"][1] is None


@pytest.mark.unit
def test_sanitize_for_json_date_time_tuple_set():
    d = date(2026, 1, 2)
    t = time(3, 4, 5)
    assert sanitize_for_json(d) == d.isoformat()
    assert sanitize_for_json(t) == t.isoformat()
    assert sanitize_for_json((1, 2)) == [1, 2]
    assert sorted(sanitize_for_json({1, 2})) == [1, 2]


@pytest.mark.unit
def test_sanitize_for_json_passes_through_primitives():
    assert sanitize_for_json("a") == "a"
    assert sanitize_for_json(42) == 42
    assert sanitize_for_json(3.14) == 3.14
