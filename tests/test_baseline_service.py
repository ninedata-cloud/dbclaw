from datetime import timedelta
from types import SimpleNamespace

from backend.services.baseline_service import (
    BaselineSignalDetector,
    build_profile_stats,
    compute_upper_bound,
    normalize_baseline_config,
)
from backend.utils.datetime_helper import now


def test_normalize_baseline_config_merges_defaults():
    config = normalize_baseline_config({
        "enabled": True,
        "learning_days": 21,
        "metrics": {
            "cpu_usage": {"enabled": False},
            "connections": {"enabled": True, "duration": 600, "severity": "high"},
        },
    })

    assert config["enabled"] is True
    assert config["learning_days"] == 21
    assert config["metrics"]["cpu_usage"]["enabled"] is False
    assert config["metrics"]["connections"]["duration"] == 600
    assert config["metrics"]["connections"]["severity"] == "high"


def test_build_profile_stats_and_upper_bound():
    stats = build_profile_stats([20.0, 22.0, 24.0, 30.0, 35.0])
    assert stats["sample_count"] == 5
    assert stats["avg_value"] == 26.2
    assert stats["p95_value"] is not None

    upper_bound = compute_upper_bound(stats, normalize_baseline_config({"deviation_ratio": 1.2, "min_absolute_delta": 3}))
    assert upper_bound is not None
    assert upper_bound >= stats["p95_value"]


def test_baseline_detector_requires_duration_and_sample_count():
    detector = BaselineSignalDetector()
    config = normalize_baseline_config({
        "enabled": True,
        "min_samples": 24,
        "deviation_ratio": 1.2,
        "min_absolute_delta": 5,
        "metrics": {"cpu_usage": {"enabled": True, "duration": 300, "severity": "medium", "minimum": 20}},
    })
    profile = SimpleNamespace(
        metric_name="cpu_usage",
        weekday=0,
        hour=10,
        sample_count=48,
        avg_value=40.0,
        p95_value=50.0,
        updated_at=now(),
    )

    violations = detector.check_baselines(1, {"cpu_usage": 70.0}, {"cpu_usage": profile}, config)
    assert violations == []

    detector._violation_start_times[1]["cpu_usage"] = now() - timedelta(seconds=301)
    violations = detector.check_baselines(1, {"cpu_usage": 70.0}, {"cpu_usage": profile}, config)
    assert len(violations) == 0

    violations = detector.check_baselines(1, {"cpu_usage": 70.0}, {"cpu_usage": profile}, config)
    assert len(violations) == 1
    assert violations[0]["metric_name"] == "cpu_usage"
    assert violations[0]["severity"] == "medium"
