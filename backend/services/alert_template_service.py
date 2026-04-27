from __future__ import annotations

from types import SimpleNamespace
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.alert_template import AlertTemplate
from backend.services.alert_ai_service import normalize_alert_engine_mode
from backend.services.baseline_service import DEFAULT_BASELINE_CONFIG, normalize_baseline_config
from backend.services.alert_service import DEFAULT_EVENT_AI_CONFIG, normalize_event_ai_config


DEFAULT_THRESHOLD_RULES = {
    "cpu_usage": {
        "levels": [
            {"severity": "low", "threshold": 60, "duration": 300},
            {"severity": "medium", "threshold": 80, "duration": 60},
            {"severity": "high", "threshold": 85, "duration": 60},
            {"severity": "critical", "threshold": 90, "duration": 60},
        ]
    },
    "disk_usage": {
        "levels": [
            {"severity": "low", "threshold": 80, "duration": 0},
            {"severity": "medium", "threshold": 85, "duration": 0},
            {"severity": "high", "threshold": 90, "duration": 0},
            {"severity": "critical", "threshold": 95, "duration": 0},
        ]
    },
    "connections": {
        "levels": [
            {"severity": "low", "threshold": 20, "duration": 60},
            {"severity": "medium", "threshold": 30, "duration": 60},
            {"severity": "high", "threshold": 40, "duration": 60},
            {"severity": "critical", "threshold": 50, "duration": 60},
        ]
    },
}

VALID_SEVERITIES = {"critical", "high", "medium", "low"}


def _validate_multi_level_threshold(metric_name: str, rule: dict) -> dict:
    """
    Validate and normalize multi-level threshold configuration.

    Args:
        metric_name: Name of the metric
        rule: Rule configuration with "levels" array

    Returns:
        Normalized rule configuration

    Raises:
        ValueError: If validation fails
    """
    if "levels" not in rule or not isinstance(rule["levels"], list):
        raise ValueError(f"Metric '{metric_name}': must have 'levels' array configuration")

    levels = rule["levels"]
    if not levels:
        raise ValueError(f"Metric '{metric_name}': levels array cannot be empty")

    seen_severities = set()
    normalized_levels = []

    for idx, level in enumerate(levels):
        if not isinstance(level, dict):
            raise ValueError(f"Metric '{metric_name}': level {idx} must be a dictionary")

        severity = level.get("severity")
        if not severity:
            raise ValueError(f"Metric '{metric_name}': level {idx} missing 'severity' field")

        if severity not in VALID_SEVERITIES:
            raise ValueError(
                f"Metric '{metric_name}': invalid severity '{severity}'. "
                f"Must be one of: {', '.join(VALID_SEVERITIES)}"
            )

        if severity in seen_severities:
            raise ValueError(f"Metric '{metric_name}': duplicate severity '{severity}'")
        seen_severities.add(severity)

        threshold = level.get("threshold")
        if threshold is None:
            raise ValueError(f"Metric '{metric_name}': level {idx} missing 'threshold' field")

        try:
            threshold = float(threshold)
            if threshold <= 0:
                raise ValueError(f"Metric '{metric_name}': threshold must be positive")
        except (TypeError, ValueError) as e:
            raise ValueError(f"Metric '{metric_name}': invalid threshold value: {e}")

        duration = level.get("duration", 60)

        normalized_levels.append({
            "severity": severity,
            "threshold": threshold,
            "duration": int(duration)
        })

    # Validate threshold ordering (lower severity should have lower threshold)
    severity_order = {"low": 1, "medium": 2, "high": 3, "critical": 4}
    sorted_by_severity = sorted(normalized_levels, key=lambda x: severity_order[x["severity"]])

    for i in range(len(sorted_by_severity) - 1):
        current = sorted_by_severity[i]
        next_level = sorted_by_severity[i + 1]
        if current["threshold"] > next_level["threshold"]:
            raise ValueError(
                f"Metric '{metric_name}': threshold for '{current['severity']}' "
                f"({current['threshold']}) must be less than '{next_level['severity']}' "
                f"({next_level['threshold']})"
            )

    return {"levels": normalized_levels}


def normalize_alert_template_config(config: Optional[dict[str, Any]]) -> dict[str, Any]:
    payload = config if isinstance(config, dict) else {}
    threshold_rules = payload.get("threshold_rules")

    # Validate and normalize threshold rules (including multi-level)
    normalized_threshold_rules = {}
    if isinstance(threshold_rules, dict):
        for metric_name, rule in threshold_rules.items():
            if isinstance(rule, dict):
                try:
                    normalized_threshold_rules[metric_name] = _validate_multi_level_threshold(metric_name, rule)
                except ValueError as e:
                    # Log validation error but don't fail - use default instead
                    import logging
                    logging.getLogger(__name__).warning(f"Threshold validation failed: {e}")
                    normalized_threshold_rules[metric_name] = rule
            else:
                normalized_threshold_rules[metric_name] = rule
    else:
        normalized_threshold_rules = dict(DEFAULT_THRESHOLD_RULES)

    alert_engine_mode = normalize_alert_engine_mode(payload.get("alert_engine_mode"))
    ai_policy_text = (payload.get("ai_policy_text") or "").strip() or None
    alert_ai_model_id = payload.get("alert_ai_model_id")
    ai_shadow_enabled = bool(payload.get("ai_shadow_enabled", False))

    if alert_engine_mode != "ai":
        ai_policy_text = None
        alert_ai_model_id = None
        ai_shadow_enabled = False

    normalized = {
        "alert_engine_mode": alert_engine_mode,
        "threshold_rules": normalized_threshold_rules,
        "baseline_config": normalize_baseline_config(payload.get("baseline_config") or DEFAULT_BASELINE_CONFIG),
        "event_ai_config": normalize_event_ai_config(payload.get("event_ai_config") or DEFAULT_EVENT_AI_CONFIG),
        "ai_policy_text": ai_policy_text,
        "alert_ai_model_id": alert_ai_model_id,
        "ai_shadow_enabled": ai_shadow_enabled,
    }
    return normalized


DEFAULT_ALERT_TEMPLATES: list[dict[str, Any]] = [
    {
        "name": "标准生产告警",
        "description": "适合大多数生产库，启用阈值告警、实例基线和事件级 AI 诊断。",
        "enabled": True,
        "is_default": True,
        "template_config": {
            "alert_engine_mode": "threshold",
            "threshold_rules": {
                "cpu_usage": {
                    "levels": [
                        {"severity": "low", "threshold": 70, "duration": 60},
                        {"severity": "medium", "threshold": 70, "duration": 60},
                        {"severity": "high", "threshold": 75, "duration": 60},
                        {"severity": "critical", "threshold": 80, "duration": 60},
                    ]
                },
                "disk_usage": {
                    "levels": [
                        {"severity": "low", "threshold": 85, "duration": 0},
                        {"severity": "medium", "threshold": 85, "duration": 0},
                        {"severity": "high", "threshold": 90, "duration": 0},
                        {"severity": "critical", "threshold": 95, "duration": 0},
                    ]
                },
                "connections": {
                    "levels": [
                        {"severity": "low", "threshold": 20, "duration": 60},
                        {"severity": "medium", "threshold": 20, "duration": 60},
                        {"severity": "high", "threshold": 30, "duration": 60},
                        {"severity": "critical", "threshold": 40, "duration": 60},
                    ]
                },
            },
            "baseline_config": {
                "enabled": True,
                "learning_days": 14,
                "min_samples": 24,
                "deviation_ratio": 3,
                "min_absolute_delta": 10,
                "metrics": {
                    "cpu_usage": {"enabled": True},
                    "disk_usage": {"enabled": True},
                    "connections": {"enabled": True},
                },
            },
            "event_ai_config": {
                "enabled": True,
                "trigger_on_create": True,
                "trigger_on_severity_upgrade": True,
                "trigger_on_recovery": False,
                "stale_recheck_minutes": 30,
            },
        },
    },
    {
        "name": "AI 智能判警",
        "description": "适合希望减少硬编码阈值的场景，由 AI 结合趋势与上下文做最终判警。",
        "enabled": True,
        "is_default": False,
        "template_config": {
            "alert_engine_mode": "ai",
            "threshold_rules": {
                "cpu_usage": {
                    "levels": [
                        {"severity": "low", "threshold": 70, "duration": 60},
                        {"severity": "medium", "threshold": 70, "duration": 60},
                        {"severity": "high", "threshold": 75, "duration": 60},
                        {"severity": "critical", "threshold": 80, "duration": 60},
                    ]
                },
                "disk_usage": {
                    "levels": [
                        {"severity": "low", "threshold": 85, "duration": 0},
                        {"severity": "medium", "threshold": 85, "duration": 0},
                        {"severity": "high", "threshold": 90, "duration": 0},
                        {"severity": "critical", "threshold": 95, "duration": 0},
                    ]
                },
                "connections": {
                    "levels": [
                        {"severity": "low", "threshold": 20, "duration": 60},
                        {"severity": "medium", "threshold": 20, "duration": 60},
                        {"severity": "high", "threshold": 30, "duration": 60},
                        {"severity": "critical", "threshold": 40, "duration": 60},
                    ]
                },
            },
            "baseline_config": {
                "enabled": True,
                "learning_days": 14,
                "min_samples": 24,
                "deviation_ratio": 2,
                "min_absolute_delta": 8,
                "metrics": {
                    "cpu_usage": {"enabled": True},
                    "disk_usage": {"enabled": True},
                    "connections": {"enabled": True},
                },
            },
            "event_ai_config": {
                "enabled": True,
                "trigger_on_create": True,
                "trigger_on_severity_upgrade": True,
                "trigger_on_recovery": False,
                "stale_recheck_minutes": 30,
            },
            "ai_policy_text": "请结合 CPU、磁盘使用率、活跃连接数及最近 15 分钟趋势判断该实例是否处于明显异常状态。只有在异常持续、影响扩大或风险较高时才触发告警；若只是短时抖动或接近阈值但证据不足，则不触发告警。",
        },
    },
    {
        "name": "轻量开发告警",
        "description": "适合测试/开发环境，阈值更宽松，默认关闭基线。",
        "enabled": True,
        "is_default": False,
        "template_config": {
            "alert_engine_mode": "threshold",
            "threshold_rules": {
                "cpu_usage": {
                    "levels": [
                        {"severity": "low", "threshold": 80, "duration": 300},
                        {"severity": "medium", "threshold": 85, "duration": 300},
                        {"severity": "high", "threshold": 90, "duration": 300},
                        {"severity": "critical", "threshold": 95, "duration": 300},
                    ]
                },
                "disk_usage": {
                    "levels": [
                        {"severity": "low", "threshold": 90, "duration": 0},
                        {"severity": "medium", "threshold": 90, "duration": 0},
                        {"severity": "high", "threshold": 95, "duration": 0},
                        {"severity": "critical", "threshold": 97, "duration": 0},
                    ]
                },
                "connections": {
                    "levels": [
                        {"severity": "low", "threshold": 20, "duration": 300},
                        {"severity": "medium", "threshold": 20, "duration": 300},
                        {"severity": "high", "threshold": 30, "duration": 300},
                        {"severity": "critical", "threshold": 40, "duration": 300},
                    ]
                },
            },
            "baseline_config": {"enabled": False},
            "event_ai_config": {
                "enabled": True,
                "trigger_on_create": True,
                "trigger_on_severity_upgrade": False,
                "trigger_on_recovery": False,
                "stale_recheck_minutes": 60,
            },
        },
    },
]


async def ensure_default_alert_template(db: AsyncSession) -> None:
    result = await db.execute(select(AlertTemplate))
    existing_items = result.scalars().all()
    existing_names = {item.name for item in existing_items}
    created = False
    for item in DEFAULT_ALERT_TEMPLATES:
        if item["name"] in existing_names:
            continue
        db.add(
            AlertTemplate(
                name=item["name"],
                description=item.get("description"),
                enabled=bool(item.get("enabled", True)),
                is_default=bool(item.get("is_default", False)),
                template_config=normalize_alert_template_config(item.get("template_config")),
            )
        )
        created = True
    if created:
        await db.commit()


async def get_alert_template_by_id(db: AsyncSession, template_id: Optional[int]) -> Optional[AlertTemplate]:
    if not template_id:
        return None
    await ensure_default_alert_template(db)
    result = await db.execute(select(AlertTemplate).where(AlertTemplate.id == template_id))
    return result.scalar_one_or_none()


async def get_default_alert_template(db: AsyncSession) -> Optional[AlertTemplate]:
    await ensure_default_alert_template(db)
    result = await db.execute(
        select(AlertTemplate)
        .where(AlertTemplate.is_enabled == True)
        .order_by(AlertTemplate.is_default.desc(), AlertTemplate.id.asc())
        .limit(1)
    )
    return result.scalar_one_or_none()


def reset_inspection_config_to_template(config, template: Optional[AlertTemplate]) -> bool:
    if not config or not template:
        return False

    changed = False
    desired_values = {
        "alert_template_id": template.id,
        "threshold_rules": {},
        "alert_engine_mode": "inherit",
        "ai_policy_source": "inline",
        "ai_policy_text": None,
        "ai_policy_id": None,
        "alert_ai_model_id": None,
        "ai_shadow_enabled": False,
        "baseline_config": {},
        "event_ai_config": {},
    }

    for field_name, desired_value in desired_values.items():
        current_value = getattr(config, field_name, None)
        if current_value != desired_value:
            setattr(config, field_name, desired_value)
            changed = True

    return changed


async def bind_default_template_to_all_inspection_config(db: AsyncSession) -> int:
    template = await get_default_alert_template(db)
    if not template:
        return 0

    from backend.models.inspection_config import InspectionConfig

    configs_result = await db.execute(select(InspectionConfig))
    configs = configs_result.scalars().all()
    changed_count = 0
    for config in configs:
        if reset_inspection_config_to_template(config, template):
            changed_count += 1

    if changed_count:
        await db.commit()
    return changed_count


def summarize_alert_template_config(config: Optional[dict[str, Any]]) -> str:
    normalized = normalize_alert_template_config(config)
    parts: list[str] = []
    mode = normalized.get("alert_engine_mode")
    parts.append("AI 判警" if mode == "ai" else "阈值判警")
    threshold_rules = normalized.get("threshold_rules") or {}
    if isinstance(threshold_rules, dict) and threshold_rules:
        custom_expression = threshold_rules.get("custom_expression")
        if isinstance(custom_expression, dict) and (custom_expression.get("expression") or "").strip():
            expr = str(custom_expression.get("expression") or "").strip()
            compact = expr if len(expr) <= 40 else f"{expr[:40]}..."
            parts.append(f"表达式 {compact}")
        else:
            short_rules = []
            for metric_name in ("cpu_usage", "disk_usage", "connections"):
                rule = threshold_rules.get(metric_name)
                if isinstance(rule, dict):
                    # Check if multi-level configuration
                    if "levels" in rule and isinstance(rule["levels"], list):
                        level_count = len(rule["levels"])
                        short_rules.append(f"{metric_name}({level_count}级)")
                    elif rule.get("threshold") is not None:
                        short_rules.append(f"{metric_name}:{rule.get('threshold')}")
            if short_rules:
                parts.append("阈值 " + " / ".join(short_rules))
    if mode == "ai" and normalized.get("ai_policy_text"):
        parts.append("内置 AI 规则")
    baseline_enabled = bool((normalized.get("baseline_config") or {}).get("enabled"))
    parts.append("启用基线" if baseline_enabled else "关闭基线")
    event_ai_enabled = bool((normalized.get("event_ai_config") or {}).get("enabled", True))
    parts.append("事件 AI 开启" if event_ai_enabled else "事件 AI 关闭")
    return "，".join(parts)


async def resolve_effective_inspection_config(db: AsyncSession, config) -> SimpleNamespace:
    await ensure_default_alert_template(db)
    bound_template = await get_alert_template_by_id(db, getattr(config, "alert_template_id", None))
    template = bound_template if bound_template is not None and bool(getattr(bound_template, "enabled", False)) else await get_default_alert_template(db)
    uses_template = template is not None
    template_config = normalize_alert_template_config(getattr(template, "template_config", None) if uses_template else None)

    if uses_template:
        alert_engine_mode = template_config["alert_engine_mode"]
        threshold_rules = template_config["threshold_rules"]
        baseline_config = template_config["baseline_config"]
        event_ai_config = template_config["event_ai_config"]
        ai_policy_source = "inline"
        ai_policy_text = template_config["ai_policy_text"]
        ai_policy_id = None
        alert_ai_model_id = template_config["alert_ai_model_id"]
        ai_shadow_enabled = template_config["ai_shadow_enabled"]
    else:
        alert_engine_mode = normalize_alert_engine_mode(getattr(config, "alert_engine_mode", None))
        threshold_rules = getattr(config, "threshold_rules", None) or {}
        baseline_config = normalize_baseline_config(getattr(config, "baseline_config", None))
        event_ai_config = normalize_event_ai_config(getattr(config, "event_ai_config", None))
        ai_policy_source = getattr(config, "ai_policy_source", None) or "inline"
        ai_policy_text = getattr(config, "ai_policy_text", None)
        ai_policy_id = getattr(config, "ai_policy_id", None)
        alert_ai_model_id = getattr(config, "alert_ai_model_id", None)
        ai_shadow_enabled = bool(getattr(config, "ai_shadow_enabled", False))

    return SimpleNamespace(
        datasource_id=getattr(config, "datasource_id", None),
        enabled=bool(getattr(config, "enabled", False)),
        schedule_interval=int(getattr(config, "schedule_interval", 86400) or 86400),
        use_ai_analysis=bool(getattr(config, "use_ai_analysis", True)),
        ai_model_id=getattr(config, "ai_model_id", None),
        kb_ids=list(getattr(config, "kb_ids", []) or []),
        alert_template_id=getattr(template, "id", None) if template else getattr(config, "alert_template_id", None),
        alert_template_name=getattr(template, "name", None) if template else None,
        uses_template=uses_template,
        alert_engine_mode=alert_engine_mode,
        threshold_rules=threshold_rules,
        baseline_config=baseline_config,
        event_ai_config=event_ai_config,
        ai_policy_source=ai_policy_source,
        ai_policy_text=ai_policy_text,
        ai_policy_id=ai_policy_id,
        alert_ai_model_id=alert_ai_model_id,
        ai_shadow_enabled=ai_shadow_enabled,
        template_summary=summarize_alert_template_config(template_config if uses_template else {
            "alert_engine_mode": alert_engine_mode,
            "threshold_rules": threshold_rules,
            "baseline_config": baseline_config,
            "event_ai_config": event_ai_config,
        }),
    )
