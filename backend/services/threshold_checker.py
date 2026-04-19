"""
Threshold checker for anomaly detection
Tracks metric violations and triggers inspections when thresholds are exceeded
"""
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List
from collections import defaultdict
from backend.utils.datetime_helper import now as get_now

logger = logging.getLogger(__name__)

# Severity order for multi-level threshold checking (highest to lowest)
SEVERITY_ORDER = {
    "critical": 4,
    "high": 3,
    "medium": 2,
    "low": 1
}


class ThresholdChecker:
    """
    Monitors metrics against configured thresholds and tracks violation duration.
    Triggers inspection when a metric exceeds threshold for the configured duration.
    """

    def __init__(self):
        # Track violation start times: {datasource_id: {metric_key: start_time}}
        # metric_key format: "metric_name" or "metric_name:severity" for multi-level
        self._violation_start_times: Dict[int, Dict[str, datetime]] = defaultdict(dict)
        # Track last trigger times to avoid duplicate triggers: {datasource_id: {metric_key: trigger_time}}
        self._last_trigger_times: Dict[int, Dict[str, datetime]] = defaultdict(dict)
        # Track consecutive confirmation counts: {datasource_id: {metric_key: count}}
        self._violation_counts: Dict[int, Dict[str, int]] = defaultdict(lambda: defaultdict(int))
        # Cooldown period after triggering (seconds) - avoid repeated triggers
        self._trigger_cooldown = 3600  # 1 hour

    def check_thresholds(
        self,
        datasource_id: int,
        metrics: Dict[str, Any],
        threshold_rules: Dict[str, Dict[str, float]]
    ) -> List[Dict[str, Any]]:
        """
        Check if metrics violate configured thresholds.

        Args:
            datasource_id: Database datasource ID
            metrics: Current metric values (normalized)
            threshold_rules: Threshold configuration from InspectionConfig
                Example (multi-level): {
                    "cpu_usage": {
                        "levels": [
                            {"severity": "medium", "threshold": 70, "duration": 300},
                            {"severity": "high", "threshold": 85, "duration": 180},
                            {"severity": "critical", "threshold": 95, "duration": 60}
                        ]
                    }
                }
                Example (custom expression): {
                    "custom_expression": {
                        "expression": "cpu_usage > 50 and connections > 20",
                        "duration": 60
                    }
                }

        Returns:
            List of violations that should trigger inspection:
            [
                {
                    "metric_name": "cpu_usage",
                    "severity": "high",
                    "current_value": 95.5,
                    "threshold": 85,
                    "duration": 180,
                    "violation_duration": 200
                }
            ]
        """
        now = get_now()
        violations_to_trigger = []

        if not threshold_rules:
            return violations_to_trigger

        # Check if custom expression is used
        if "custom_expression" in threshold_rules:
            return self._check_custom_expression(datasource_id, metrics, threshold_rules["custom_expression"], now)

        # Check multi-level threshold rules
        for metric_name, rule in threshold_rules.items():
            if "levels" in rule and isinstance(rule["levels"], list):
                violations = self._check_multi_level_threshold(
                    datasource_id, metric_name, metrics, rule["levels"], now
                )
                violations_to_trigger.extend(violations)

        return violations_to_trigger

    def _check_multi_level_threshold(
        self,
        datasource_id: int,
        metric_name: str,
        metrics: Dict[str, Any],
        levels: List[Dict[str, Any]],
        now: datetime
    ) -> List[Dict[str, Any]]:
        """
        Check multi-level threshold configuration.

        Args:
            datasource_id: Database datasource ID
            metric_name: Metric name (e.g., "cpu_usage")
            metrics: Current metric values
            levels: List of level configurations, each with:
                {
                    "severity": "critical|high|medium|low",
                    "threshold": 95,
                    "duration": 60,
                    "confirmations": 1
                }
            now: Current timestamp

        Returns:
            List of violations (at most one per metric, matching the highest severity level)
        """
        current_value = self._extract_metric_value(metrics, metric_name)
        if current_value is None:
            # Metric not available, clear all level tracking for this metric
            keys_to_remove = [k for k in self._violation_start_times[datasource_id].keys()
                            if k == metric_name or k.startswith(f"{metric_name}:")]
            for key in keys_to_remove:
                del self._violation_start_times[datasource_id][key]
                self._violation_counts[datasource_id][key] = 0
                self._last_trigger_times[datasource_id].pop(key, None)
            return []

        # Sort levels by severity (highest first)
        sorted_levels = sorted(
            levels,
            key=lambda x: SEVERITY_ORDER.get(x.get("severity", "low"), 1),
            reverse=True
        )

        # Find the highest severity level that is violated
        matched_level = None
        for level in sorted_levels:
            threshold = level.get("threshold")
            if threshold is not None and current_value > threshold:
                matched_level = level
                break

        if matched_level:
            severity = matched_level.get("severity", "medium")
            threshold = matched_level["threshold"]
            required_duration = matched_level.get("duration", 60)

            # Use metric_key to track this specific level
            metric_key = f"{metric_name}:{severity}"

            # Track violation start time
            if metric_key not in self._violation_start_times[datasource_id]:
                self._violation_start_times[datasource_id][metric_key] = now
                logger.info(
                    f"Multi-level threshold violation started for datasource {datasource_id}: "
                    f"{metric_name}={current_value:.2f} > {threshold} (severity={severity})"
                )

            # Calculate violation duration
            violation_start = self._violation_start_times[datasource_id][metric_key]
            violation_duration = (now - violation_start).total_seconds()

            # Check if violation duration exceeds required duration
            if violation_duration >= required_duration:
                # Check cooldown period
                last_trigger = self._last_trigger_times[datasource_id].get(metric_key)
                if last_trigger:
                    time_since_last_trigger = (now - last_trigger).total_seconds()
                    if time_since_last_trigger < self._trigger_cooldown:
                        logger.debug(
                            f"Skipping trigger for {metric_key} on datasource {datasource_id}: "
                            f"in cooldown period ({time_since_last_trigger:.0f}s < {self._trigger_cooldown}s)"
                        )
                        return []

                # Increment violation count
                self._violation_counts[datasource_id][metric_key] += 1

                # Trigger inspection
                violation = {
                    "metric_name": metric_name,
                    "severity": severity,
                    "current_value": current_value,
                    "threshold": threshold,
                    "duration": required_duration,
                    "violation_duration": violation_duration
                }

                # Reset confirmation count and update last trigger time
                self._violation_counts[datasource_id][metric_key] = 0
                self._last_trigger_times[datasource_id][metric_key] = now

                logger.warning(
                    f"Multi-level threshold violation trigger for datasource {datasource_id}: "
                    f"{metric_name}={current_value:.2f} > {threshold} (severity={severity}) "
                    f"for {violation_duration:.0f}s"
                )

                # Clear tracking for lower severity levels of the same metric
                for level in sorted_levels:
                    if level != matched_level:
                        lower_key = f"{metric_name}:{level.get('severity', 'low')}"
                        if lower_key in self._violation_start_times[datasource_id]:
                            del self._violation_start_times[datasource_id][lower_key]
                        self._violation_counts[datasource_id][lower_key] = 0

                return [violation]

        else:
            # No level violated, clear all tracking for this metric
            keys_to_remove = [k for k in self._violation_start_times[datasource_id].keys()
                            if k.startswith(f"{metric_name}:")]
            if keys_to_remove:
                for key in keys_to_remove:
                    violation_start = self._violation_start_times[datasource_id][key]
                    violation_duration = (now - violation_start).total_seconds()
                    logger.info(
                        f"Multi-level threshold violation ended for datasource {datasource_id}: "
                        f"{key} (was violated for {violation_duration:.0f}s)"
                    )
                    del self._violation_start_times[datasource_id][key]
                    self._violation_counts[datasource_id][key] = 0
                    self._last_trigger_times[datasource_id].pop(key, None)

        return []

    def _check_custom_expression(
        self,
        datasource_id: int,
        metrics: Dict[str, Any],
        custom_rule: Dict[str, Any],
        now: datetime
    ) -> List[Dict[str, Any]]:
        """
        Check custom expression threshold.

        Args:
            datasource_id: Database datasource ID
            metrics: Current metric values (normalized)
            custom_rule: Custom expression rule with "expression" and "duration"
            now: Current timestamp

        Returns:
            List with single violation if expression evaluates to True and duration exceeded
        """
        expression = custom_rule.get("expression")
        required_duration = custom_rule.get("duration", 60)

        if not expression:
            return []

        # Prepare metrics context for eval
        eval_context = self._prepare_eval_context(metrics)

        # Evaluate expression
        is_violated = self._evaluate_custom_expression(expression, eval_context)

        metric_name = "custom_expression"

        if is_violated:
            # Track violation start time
            if metric_name not in self._violation_start_times[datasource_id]:
                self._violation_start_times[datasource_id][metric_name] = now
                logger.info(
                    f"Custom expression violation started for datasource {datasource_id}: {expression}"
                )

            # Calculate violation duration
            violation_start = self._violation_start_times[datasource_id][metric_name]
            violation_duration = (now - violation_start).total_seconds()

            # Check if violation duration exceeds required duration
            if violation_duration >= required_duration:
                # Check cooldown period
                last_trigger = self._last_trigger_times[datasource_id].get(metric_name)
                if last_trigger:
                    time_since_last_trigger = (now - last_trigger).total_seconds()
                    if time_since_last_trigger < self._trigger_cooldown:
                        logger.debug(
                            f"Skipping trigger for custom expression on datasource {datasource_id}: "
                            f"in cooldown period ({time_since_last_trigger:.0f}s < {self._trigger_cooldown}s)"
                        )
                        return []

                # Increment violation count
                self._violation_counts[datasource_id][metric_name] += 1

                # Trigger inspection
                violation = {
                    "metric_name": metric_name,
                    "expression": expression,
                    "duration": required_duration,
                    "violation_duration": violation_duration,
                    "metrics": eval_context
                }

                # Reset confirmation count and update last trigger time
                self._violation_counts[datasource_id][metric_name] = 0
                self._last_trigger_times[datasource_id][metric_name] = now

                logger.warning(
                    f"Custom expression violation trigger for datasource {datasource_id}: "
                    f"{expression} for {violation_duration:.0f}s"
                )

                return [violation]

        else:
            # Expression not violated, clear violation tracking
            if metric_name in self._violation_start_times[datasource_id]:
                violation_start = self._violation_start_times[datasource_id][metric_name]
                violation_duration = (now - violation_start).total_seconds()
                logger.info(
                    f"Custom expression violation ended for datasource {datasource_id}: "
                    f"{expression} (was violated for {violation_duration:.0f}s)"
                )
                del self._violation_start_times[datasource_id][metric_name]
                self._violation_counts[datasource_id][metric_name] = 0
                self._last_trigger_times[datasource_id].pop(metric_name, None)

        return []

    def _prepare_eval_context(self, metrics: Dict[str, Any]) -> Dict[str, float]:
        """
        Prepare metrics context for expression evaluation.
        Extracts common metric names and converts to float values.

        Args:
            metrics: Raw metrics dictionary

        Returns:
            Dictionary with metric names as keys and float values
        """
        context = {}

        # Extract common metrics
        metric_names = ["cpu_usage", "memory_usage", "disk_usage", "connections", "qps", "tps"]

        for metric_name in metric_names:
            value = self._extract_metric_value(metrics, metric_name)
            if value is not None:
                context[metric_name] = value

        return context

    def _evaluate_custom_expression(self, expression: str, metrics: Dict[str, float]) -> bool:
        """
        Evaluate custom expression using Python's eval().

        Args:
            expression: Python expression string (e.g., "cpu_usage > 50 and connections > 20")
            metrics: Dictionary with metric names as keys and float values

        Returns:
            True if expression evaluates to True, False otherwise
        """
        try:
            # Evaluate expression with restricted builtins and metrics as local variables
            result = eval(expression, {"__builtins__": {}}, metrics)
            # Only True triggers, everything else is False
            return result is True
        except Exception as e:
            logger.error(f"Expression evaluation failed: {e} | Expression: {expression}")
            return False

    def _extract_metric_value(self, metrics: Dict[str, Any], metric_name: str) -> Optional[float]:
        """
        Extract metric value from normalized metrics dictionary.

        Supports both direct keys and nested paths (e.g., "cpu.usage_percent")
        """
        # Try direct key first
        if metric_name in metrics:
            value = metrics[metric_name]
            return self._to_float(value)

        # Try nested path (e.g., "cpu.usage_percent")
        if "." in metric_name:
            parts = metric_name.split(".")
            current = metrics
            for part in parts:
                if isinstance(current, dict) and part in current:
                    current = current[part]
                else:
                    return None
            return self._to_float(current)

        # Common metric name mappings
        mappings = {
            "cpu_usage": ["cpu_usage_percent", "cpu.usage_percent", "cpu_percent"],
            "memory_usage": ["memory_usage_percent", "memory.usage_percent", "mem_percent"],
            "disk_usage": ["disk_usage_percent", "disk.usage_percent", "disk_percent"],
            "connections": ["threads_running", "connections_active", "active_connections", "connection_count"],
        }

        if metric_name in mappings:
            for alt_name in mappings[metric_name]:
                value = self._extract_metric_value(metrics, alt_name)
                if value is not None:
                    return value

        return None

    def _to_float(self, value: Any) -> Optional[float]:
        """Convert value to float, handling various formats"""
        if value is None:
            return None
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str):
            try:
                # Handle percentage strings like "85.5%"
                if value.endswith("%"):
                    return float(value[:-1])
                return float(value)
            except ValueError:
                return None
        return None

    def clear_datasource(self, datasource_id: int):
        """Clear all tracking data for a datasource (e.g., when datasource is deleted)"""
        if datasource_id in self._violation_start_times:
            del self._violation_start_times[datasource_id]
        if datasource_id in self._last_trigger_times:
            del self._last_trigger_times[datasource_id]
        if datasource_id in self._violation_counts:
            del self._violation_counts[datasource_id]

    def get_violation_status(self, datasource_id: int) -> Dict[str, Dict[str, Any]]:
        """Get current violation status for a datasource (for debugging/monitoring)"""
        now = get_now()
        status = {}

        for metric_name, start_time in self._violation_start_times.get(datasource_id, {}).items():
            duration = (now - start_time).total_seconds()
            last_trigger = self._last_trigger_times.get(datasource_id, {}).get(metric_name)
            confirmation_count = self._violation_counts.get(datasource_id, {}).get(metric_name, 0)

            status[metric_name] = {
                "violation_start": start_time.isoformat(),
                "violation_duration": duration,
                "last_trigger": last_trigger.isoformat() if last_trigger else None,
                "confirmation_count": confirmation_count
            }

        return status
