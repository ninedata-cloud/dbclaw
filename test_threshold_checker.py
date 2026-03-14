"""
Tests for ThresholdChecker service with custom expression evaluation
"""
import asyncio
from datetime import datetime, timedelta
from backend.services.threshold_checker import ThresholdChecker


def test_simple_threshold_rules():
    """Test backward compatibility with simple threshold rules"""
    checker = ThresholdChecker()
    
    # Test CPU threshold violation
    metrics = {"cpu_usage": 85.5}
    rules = {"cpu_usage": {"threshold": 80, "duration": 60}}
    
    violations = checker.check_thresholds(1, metrics, rules)
    assert len(violations) == 0, "Should not trigger immediately"
    
    # Wait for duration to pass (simulate)
    checker._violation_start_times[1]["cpu_usage"] = datetime.utcnow() - timedelta(seconds=61)
    violations = checker.check_thresholds(1, metrics, rules)
    assert len(violations) == 1, "Should trigger after duration"
    assert violations[0]["metric_name"] == "cpu_usage"
    assert violations[0]["current_value"] == 85.5
    assert violations[0]["threshold"] == 80
    
    print("✓ Simple threshold rules work correctly")


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
    checker._violation_start_times[1]["custom_expression"] = datetime.utcnow() - timedelta(seconds=61)
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
            "duration": 120
        }
    }
    
    # First check - violation starts
    violations = checker.check_thresholds(1, metrics, rules)
    assert len(violations) == 0, "Should not trigger immediately"
    assert "custom_expression" in checker._violation_start_times[1]
    
    # Second check - duration not met yet (simulate 60s passed)
    checker._violation_start_times[1]["custom_expression"] = datetime.utcnow() - timedelta(seconds=60)
    violations = checker.check_thresholds(1, metrics, rules)
    assert len(violations) == 0, "Should not trigger before duration"
    
    # Third check - duration met (simulate 121s passed)
    checker._violation_start_times[1]["custom_expression"] = datetime.utcnow() - timedelta(seconds=121)
    violations = checker.check_thresholds(1, metrics, rules)
    assert len(violations) == 1, "Should trigger after duration"
    
    print("✓ Duration tracking for custom expression works correctly")


def test_cooldown_period():
    """Test that cooldown period prevents duplicate triggers"""
    checker = ThresholdChecker()
    
    metrics = {"cpu_usage": 85}
    rules = {"cpu_usage": {"threshold": 80, "duration": 60}}
    
    # First trigger
    checker._violation_start_times[1]["cpu_usage"] = datetime.utcnow() - timedelta(seconds=61)
    violations = checker.check_thresholds(1, metrics, rules)
    assert len(violations) == 1, "Should trigger first time"
    
    # Second check immediately - should be in cooldown
    violations = checker.check_thresholds(1, metrics, rules)
    assert len(violations) == 0, "Should not trigger during cooldown"
    
    # Third check after cooldown (simulate 3601s passed)
    checker._last_trigger_times[1]["cpu_usage"] = datetime.utcnow() - timedelta(seconds=3601)
    violations = checker.check_thresholds(1, metrics, rules)
    assert len(violations) == 1, "Should trigger after cooldown"
    
    print("✓ Cooldown period works correctly")


def test_backward_compatibility():
    """Test that existing configs with simple rules still work"""
    checker = ThresholdChecker()
    
    # Old format with multiple simple rules
    metrics = {
        "cpu_usage": 85,
        "disk_usage": 90,
        "connections": 25
    }
    rules = {
        "cpu_usage": {"threshold": 80, "duration": 60},
        "disk_usage": {"threshold": 85, "duration": 300},
        "connections": {"threshold": 20, "duration": 120}
    }
    
    # Simulate all durations passed
    now = datetime.utcnow()
    checker._violation_start_times[1]["cpu_usage"] = now - timedelta(seconds=61)
    checker._violation_start_times[1]["disk_usage"] = now - timedelta(seconds=301)
    checker._violation_start_times[1]["connections"] = now - timedelta(seconds=121)
    
    violations = checker.check_thresholds(1, metrics, rules)
    assert len(violations) == 3, "Should trigger all three violations"
    
    metric_names = [v["metric_name"] for v in violations]
    assert "cpu_usage" in metric_names
    assert "disk_usage" in metric_names
    assert "connections" in metric_names
    
    print("✓ Backward compatibility maintained")


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


def run_all_tests():
    """Run all tests"""
    print("\n=== Running ThresholdChecker Tests ===\n")
    
    test_simple_threshold_rules()
    test_custom_expression_evaluation()
    test_expression_returns_true_triggers()
    test_expression_syntax_error()
    test_duration_tracking_custom_expression()
    test_cooldown_period()
    test_backward_compatibility()
    test_empty_threshold_rules()
    test_prepare_eval_context()
    test_complex_expressions()
    
    print("\n=== All Tests Passed ✓ ===\n")


if __name__ == "__main__":
    run_all_tests()
