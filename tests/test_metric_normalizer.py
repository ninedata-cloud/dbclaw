from datetime import datetime, timedelta
from unittest.mock import patch

from backend.services.metric_normalizer import MetricNormalizer


def test_normalize_opengauss_uses_postgresql_rate_calculation():
    MetricNormalizer._last_values.clear()

    first = {
        "xact_commit": 200,
        "xact_rollback": 5,
        "tup_fetched": 100,
        "tup_inserted": 10,
        "tup_updated": 5,
        "tup_deleted": 5,
    }
    second = {
        "xact_commit": 260,
        "xact_rollback": 10,
        "tup_fetched": 150,
        "tup_inserted": 12,
        "tup_updated": 8,
        "tup_deleted": 10,
    }

    start = datetime(2026, 4, 13, 12, 0, 0)
    later = start + timedelta(seconds=10)

    with patch(
        "backend.services.metric_normalizer.now",
        side_effect=[start, start, later, later],
    ):
        initial = MetricNormalizer.normalize("opengauss", 378, first)
        normalized = MetricNormalizer.normalize("opengauss", 378, second)

    assert "qps" not in initial
    assert "tps" not in initial
    assert normalized["qps"] == 6.0
    assert normalized["tps"] == 6.5
