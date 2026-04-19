"""
Tests for ThresholdChecker service with custom expression evaluation
"""
import asyncio
from datetime import datetime, timedelta
from backend.services.threshold_checker import ThresholdChecker
from backend.utils.datetime_helper import now




def test_custom_expression_evaluation():
    """Test custom expression evaluation"""
    checker = ThresholdChecker()

    # Test custom expression: cpu_usage > 50 and connections > 20
    metrics = {"cpu_usage": 60, "connections": 25}
    rules = {
        "custom_expression": {
            "expression": "cpu_usage > 50 and connections > 20",
            "duration": 60
        }
    }

    violations = checker.check_thresholds(1, metrics, rules)
    assert len(violations) == 0, "Should not trigger immediately"

    # Simulate duration passing
    checker._violation_start_times[1]["custom_expression"] = now() - timedelta(seconds=61)
    violations = checker.check_thresholds(1, metrics, rules)
    assert len(violations) == 1, "Should trigger after duration"
    assert violations[0]["metric_name"] == "custom_expression"
    assert violations[0]["expression"] == "cpu_usage > 50 and connections > 20"

    print("✓ Custom expression evaluation works correctly")


def test_expression_returns_true_triggers():
    """Test that only True triggers inspection"""
    checker = ThresholdChecker()
    
    # Expression returns True
    metrics = {"cpu_usage": 60}
    result = checker._evaluate_custom_expression("cpu_usage > 50", metrics)
    assert result is True, "Expression should return True"
    
    # Expression returns False
    result = checker._evaluate_custom_expression("cpu_usage > 70", metrics)
    assert result is False, "Expression should return False"
    
    # Expression returns non-boolean (should be treated as False)
    result = checker._evaluate_custom_expression("cpu_usage", metrics)
    assert result is False, "Non-True value should be treated as False"
    
    print("✓ Expression True/False behavior works correctly")


def test_expression_syntax_error():
    """Test that syntax errors don't crash and return False"""
    checker = ThresholdChecker()
    
    metrics = {"cpu_usage": 60}
    
    # Invalid syntax
    result = checker._evaluate_custom_expression("cpu_usage > 50 and", metrics)
    assert result is False, "Syntax error should return False"
    
    # Undefined variable
    result = checker._evaluate_custom_expression("undefined_var > 50", metrics)
    assert result is False, "Undefined variable should return False"
    
    print("✓ Expression error handling works correctly")


def test_duration_tracking_custom_expression():
    """Test that duration tracking works for custom expressions"""
    checker = ThresholdChecker()
    
    metrics = {"cpu_usage": 60, "connections": 25}
    rules = {
        "custom_expression": {
            "expression": "cpu_usage > 50 and connections > 20",
            "duration": 120,
            "confirmations": 1
        }
    }
    violations = checker.check_thresholds(1, metrics, rules)
    assert len(violations) == 0, "Should not trigger immediately"
    assert "custom_expression" in checker._violation_start_times[1]
    
    # Second check - duration not met yet (simulate 60s passed)
    checker._violation_start_times[1]["custom_expression"] = now() - timedelta(seconds=60)
    violations = checker.check_thresholds(1, metrics, rules)
    assert len(violations) == 0, "Should not trigger before duration"
    
    # Third check - duration met (simulate 121s passed)
    checker._violation_start_times[1]["custom_expression"] = now() - timedelta(seconds=121)
    violations = checker.check_thresholds(1, metrics, rules)
    assert len(violations) == 1, "Should trigger after duration"
    
    print("✓ Duration tracking for custom expression works correctly")






def test_custom_expression_retrigger_after_recovery():
    """Test that custom expression cooldown is cleared after recovery"""
    checker = ThresholdChecker()

    metrics = {"cpu_usage": 60, "connections": 25}
    recovered_metrics = {"cpu_usage": 40, "connections": 10}
    rules = {
        "custom_expression": {
            "expression": "cpu_usage > 50 and connections > 20",
            "duration": 60
        }
    }

    checker._violation_start_times[1]["custom_expression"] = now() - timedelta(seconds=61)
    violations = checker.check_thresholds(1, metrics, rules)
    assert len(violations) == 1, "Should trigger first custom expression violation"
    assert "custom_expression" in checker._last_trigger_times[1]

    violations = checker.check_thresholds(1, recovered_metrics, rules)
    assert len(violations) == 0, "Recovered expression should not trigger"
    assert "custom_expression" not in checker._last_trigger_times[1], "Recovery should clear custom expression cooldown"

    checker._violation_start_times[1]["custom_expression"] = now() - timedelta(seconds=61)
    violations = checker.check_thresholds(1, metrics, rules)
    assert len(violations) == 1, "Should trigger custom expression again after recovery"

    print("✓ Recovery clears cooldown for custom expression")




def test_empty_threshold_rules():
    """Test that empty threshold_rules doesn't crash"""
    checker = ThresholdChecker()
    
    metrics = {"cpu_usage": 85}
    rules = {}
    
    violations = checker.check_thresholds(1, metrics, rules)
    assert len(violations) == 0, "Empty rules should return no violations"
    
    print("✓ Empty threshold rules handled correctly")


def test_prepare_eval_context():
    """Test that eval context is prepared correctly"""
    checker = ThresholdChecker()
    
    # Test with various metric formats
    metrics = {
        "cpu_usage_percent": 85.5,
        "memory_usage_percent": 70.2,
        "disk_usage_percent": 90.0,
        "active_connections": 25,
        "qps": 1000,
        "tps": 500
    }
    
    context = checker._prepare_eval_context(metrics)
    
    assert "cpu_usage" in context
    assert context["cpu_usage"] == 85.5
    assert "memory_usage" in context
    assert context["memory_usage"] == 70.2
    assert "disk_usage" in context
    assert context["disk_usage"] == 90.0
    assert "connections" in context
    assert context["connections"] == 25
    assert "qps" in context
    assert context["qps"] == 1000
    assert "tps" in context
    assert context["tps"] == 500
    
    print("✓ Eval context preparation works correctly")


def test_complex_expressions():
    """Test complex custom expressions"""
    checker = ThresholdChecker()
    
    metrics = {"cpu_usage": 60, "memory_usage": 75, "connections": 25, "qps": 1000}
    
    # Test AND expression
    result = checker._evaluate_custom_expression(
        "cpu_usage > 50 and memory_usage > 70",
        checker._prepare_eval_context(metrics)
    )
    assert result is True
    
    # Test OR expression
    result = checker._evaluate_custom_expression(
        "cpu_usage > 80 or memory_usage > 70",
        checker._prepare_eval_context(metrics)
    )
    assert result is True
    
    # Test complex expression with multiple conditions
    result = checker._evaluate_custom_expression(
        "(cpu_usage > 50 and memory_usage > 70) or (connections > 30 and qps > 500)",
        checker._prepare_eval_context(metrics)
    )
    assert result is True
    
    # Test expression that should be False
    result = checker._evaluate_custom_expression(
        "cpu_usage > 80 and memory_usage > 80",
        checker._prepare_eval_context(metrics)
    )
    assert result is False
    
    print("✓ Complex expressions work correctly")


def test_multi_level_threshold():
    """Test multi-level threshold configuration"""
    checker = ThresholdChecker()

    # Multi-level configuration for CPU
    metrics = {"cpu_usage": 92}
    rules = {
        "cpu_usage": {
            "levels": [
                {"severity": "medium", "threshold": 70, "duration": 300},
                {"severity": "high", "threshold": 85, "duration": 180},
                {"severity": "critical", "threshold": 95, "duration": 60},
            ]
        }
    }

    # Should match "high" level (92 > 85 but < 95)
    violations = checker.check_thresholds(1, metrics, rules)
    assert len(violations) == 0, "Should not trigger immediately"

    # Simulate duration passing for high level
    checker._violation_start_times[1]["cpu_usage:high"] = now() - timedelta(seconds=181)

    # Should trigger now
    violations = checker.check_thresholds(1, metrics, rules)
    assert len(violations) == 1, "Should trigger after duration passes"
    assert violations[0]["metric_name"] == "cpu_usage"
    assert violations[0]["severity"] == "high"
    assert violations[0]["threshold"] == 85
    assert violations[0]["current_value"] == 92

    print("✓ Multi-level threshold works correctly")


def test_multi_level_severity_matching():
    """Test that multi-level matches the highest severity level"""
    checker = ThresholdChecker()

    # CPU at 96 should match critical level
    metrics = {"cpu_usage": 96}
    rules = {
        "cpu_usage": {
            "levels": [
                {"severity": "medium", "threshold": 70, "duration": 300},
                {"severity": "high", "threshold": 85, "duration": 180},
                {"severity": "critical", "threshold": 95, "duration": 60},
            ]
        }
    }

    # Simulate duration passing
    checker._violation_start_times[1]["cpu_usage:critical"] = now() - timedelta(seconds=61)
    violations = checker.check_thresholds(1, metrics, rules)

    assert len(violations) == 1
    assert violations[0]["severity"] == "critical"
    assert violations[0]["threshold"] == 95

    print("✓ Multi-level severity matching works correctly")


def test_multi_level_different_durations():
    """Test that different levels can have different durations and confirmations"""
    checker = ThresholdChecker()

    metrics = {"cpu_usage": 88}
    rules = {
        "cpu_usage": {
            "levels": [
                {"severity": "medium", "threshold": 70, "duration": 300},
                {"severity": "high", "threshold": 85, "duration": 180},
                {"severity": "critical", "threshold": 95, "duration": 60},
            ]
        }
    }

    # Should match high level (88 > 85)
    # First check - starts tracking
    violations = checker.check_thresholds(1, metrics, rules)
    assert len(violations) == 0

    # After 180 seconds should trigger
    checker._violation_start_times[1]["cpu_usage:high"] = now() - timedelta(seconds=181)
    violations = checker.check_thresholds(1, metrics, rules)
    assert len(violations) == 1, "Should trigger after duration passes"
    assert violations[0]["severity"] == "high"
    assert violations[0]["duration"] == 180

    print("✓ Multi-level different durations work correctly")


def test_multi_level_recovery():
    """Test that recovery clears all level tracking"""
    checker = ThresholdChecker()

    metrics_high = {"cpu_usage": 88}
    metrics_normal = {"cpu_usage": 60}
    rules = {
        "cpu_usage": {
            "levels": [
                {"severity": "medium", "threshold": 70, "duration": 300, "confirmations": 1},
                {"severity": "high", "threshold": 85, "duration": 180, "confirmations": 1},
            ]
        }
    }

    # Start violation
    checker._violation_start_times[1]["cpu_usage:high"] = now() - timedelta(seconds=181)
    violations = checker.check_thresholds(1, metrics_high, rules)
    assert len(violations) == 1

    # Recovery
    violations = checker.check_thresholds(1, metrics_normal, rules)
    assert len(violations) == 0
    assert "cpu_usage:high" not in checker._violation_start_times[1]
    assert "cpu_usage:medium" not in checker._violation_start_times[1]

    print("✓ Multi-level recovery works correctly")


def test_multi_level_upgrade():
    """Test upgrading from medium to high severity"""
    checker = ThresholdChecker()

    rules = {
        "cpu_usage": {
            "levels": [
                {"severity": "medium", "threshold": 70, "duration": 300, "confirmations": 1},
                {"severity": "high", "threshold": 85, "duration": 180, "confirmations": 1},
            ]
        }
    }

    # Start at medium level
    metrics_medium = {"cpu_usage": 75}
    checker._violation_start_times[1]["cpu_usage:medium"] = now() - timedelta(seconds=301)
    violations = checker.check_thresholds(1, metrics_medium, rules)
    assert len(violations) == 1
    assert violations[0]["severity"] == "medium"

    # Upgrade to high level
    metrics_high = {"cpu_usage": 88}
    checker._violation_start_times[1]["cpu_usage:high"] = now() - timedelta(seconds=181)
    violations = checker.check_thresholds(1, metrics_high, rules)
    assert len(violations) == 1
    assert violations[0]["severity"] == "high"

    # Medium level tracking should be cleared
    assert "cpu_usage:medium" not in checker._violation_start_times[1]

    print("✓ Multi-level upgrade works correctly")




def test_confirmation_count_cleared_on_clear_datasource():
    """Test that clear_datasource clears confirmation counts"""
    checker = ThresholdChecker()

    metrics = {"cpu_usage": 85}
    rules = {"cpu_usage": {"threshold": 80, "duration": 60}}

    checker._violation_start_times[1]["cpu_usage"] = now() - timedelta(seconds=61)
    checker.check_thresholds(1, metrics, rules)

    checker.clear_datasource(1)

    # After clearing, count should be gone
    assert 1 not in checker._violation_counts, "Confirmation counts should be cleared"

    print("✓ clear_datasource clears confirmation counts")


def run_all_tests():
    """Run all tests"""
    print("\n=== Running ThresholdChecker Tests ===\n")

    test_custom_expression_evaluation()
    test_expression_returns_true_triggers()
    test_expression_syntax_error()
    test_duration_tracking_custom_expression()
    test_custom_expression_retrigger_after_recovery()
    test_empty_threshold_rules()
    test_prepare_eval_context()
    test_complex_expressions()
    test_confirmation_count_cleared_on_clear_datasource()
    test_multi_level_threshold()
    test_multi_level_severity_matching()
    test_multi_level_different_durations()
    test_multi_level_recovery()
    test_multi_level_upgrade()

    print("\n=== All Tests Passed ✓ ===\n")


if __name__ == "__main__":
    run_all_tests()
