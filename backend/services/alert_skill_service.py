from __future__ import annotations

from datetime import timedelta
from typing import Any

from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.alert_subscription import AlertSubscription
from backend.models.alert_template import AlertTemplate
from backend.models.datasource import Datasource
from backend.models.inspection_config import InspectionConfig
from backend.models.soft_delete import alive_filter, alive_select, get_alive_by_id
from backend.models.user import User
from backend.routers.inspections import AlertTemplateSchema, InspectionConfigSchema
from backend.schemas.alert import (
    AlertSubscriptionCreate,
    AlertSubscriptionResponse,
    AlertSubscriptionUpdate,
)
from backend.schemas.datasource import DatasourceSilenceRequest, DatasourceSilenceResponse
from backend.services.alert_service import AlertService
from backend.services.alert_template_service import (
    get_alert_template_by_id,
    get_default_alert_template,
    normalize_alert_template_config,
    resolve_effective_inspection_config,
    summarize_alert_template_config,
)
from backend.utils.datetime_helper import now


def _error_payload(target: str, action: str, error: str) -> dict[str, Any]:
    return {
        "success": False,
        "target": target,
        "action": action,
        "error": error,
    }


def _require_param(params: dict[str, Any], name: str, *, target: str, action: str):
    value = params.get(name)
    if value is None:
        raise ValueError(f"{name} is required for {target}.{action}")
    return value


def _serialize_subscription(subscription: AlertSubscription) -> dict[str, Any]:
    return AlertSubscriptionResponse.model_validate(subscription).model_dump(mode="json")


def _serialize_template(template: AlertTemplate) -> dict[str, Any]:
    normalized = normalize_alert_template_config(template.template_config)
    return {
        "id": template.id,
        "name": template.name,
        "description": template.description,
        "enabled": template.enabled,
        "is_default": template.is_default,
        "template_config": normalized,
        "summary": summarize_alert_template_config(normalized),
        "created_at": template.created_at.isoformat() if template.created_at else None,
        "updated_at": template.updated_at.isoformat() if template.updated_at else None,
    }


def _serialize_effective_config(config, datasource_id: int) -> dict[str, Any]:
    return {
        "id": getattr(config, "id", None),
        "datasource_id": datasource_id,
        "enabled": bool(getattr(config, "enabled", False)),
        "schedule_interval": int(getattr(config, "schedule_interval", 86400) or 86400),
        "use_ai_analysis": bool(getattr(config, "use_ai_analysis", True)),
        "ai_model_id": getattr(config, "ai_model_id", None),
        "kb_ids": list(getattr(config, "kb_ids", []) or []),
        "alert_template_id": getattr(config, "alert_template_id", None),
        "alert_template_name": getattr(config, "alert_template_name", None),
        "uses_template": bool(getattr(config, "uses_template", False)),
        "template_summary": getattr(config, "template_summary", None),
        "threshold_rules": getattr(config, "threshold_rules", {}) or {},
        "alert_engine_mode": getattr(config, "alert_engine_mode", "inherit"),
        "ai_policy_source": getattr(config, "ai_policy_source", "inline"),
        "ai_policy_text": getattr(config, "ai_policy_text", None),
        "ai_policy_id": getattr(config, "ai_policy_id", None),
        "alert_ai_model_id": getattr(config, "alert_ai_model_id", None),
        "ai_shadow_enabled": bool(getattr(config, "ai_shadow_enabled", False)),
        "baseline_config": getattr(config, "baseline_config", {}) or {},
        "event_ai_config": getattr(config, "event_ai_config", {}) or {},
        "last_scheduled_at": getattr(config, "last_scheduled_at", None).isoformat()
        if getattr(config, "last_scheduled_at", None)
        else None,
        "next_scheduled_at": getattr(config, "next_scheduled_at", None).isoformat()
        if getattr(config, "next_scheduled_at", None)
        else None,
    }


def _serialize_silence_response(response: DatasourceSilenceResponse) -> dict[str, Any]:
    return response.model_dump(mode="json")


async def _get_current_user(db: AsyncSession, user_id: int) -> User:
    result = await db.execute(
        select(User).where(User.id == user_id, alive_filter(User))
    )
    user = result.scalar_one_or_none()
    if not user:
        raise ValueError(f"user {user_id} not found")
    return user


def _require_admin(current_user: User, target: str, action: str) -> None:
    if not current_user.is_admin:
        raise PermissionError(f"{target}.{action} requires admin privileges")


def _resolve_subscription_user_id(
    requested_user_id: int | None,
    current_user: User,
) -> int:
    if requested_user_id is None or requested_user_id == current_user.id:
        return current_user.id
    if current_user.is_admin:
        return requested_user_id
    raise PermissionError("cannot access subscriptions owned by another user")


async def _get_subscription_for_user(
    db: AsyncSession,
    subscription_id: int,
    current_user: User,
) -> AlertSubscription:
    subscription = await get_alive_by_id(db, AlertSubscription, subscription_id)
    if not subscription:
        raise ValueError(f"subscription {subscription_id} not found")
    if not current_user.is_admin and subscription.user_id != current_user.id:
        raise PermissionError("cannot operate on subscriptions owned by another user")
    return subscription


async def _ensure_datasource_exists(db: AsyncSession, datasource_id: int) -> Datasource:
    datasource = await get_alive_by_id(db, Datasource, datasource_id)
    if not datasource:
        raise ValueError(f"datasource {datasource_id} not found")
    return datasource


async def _load_or_create_inspection_config(
    db: AsyncSession,
    datasource_id: int,
) -> InspectionConfig:
    await _ensure_datasource_exists(db, datasource_id)
    result = await db.execute(
        select(InspectionConfig).where(InspectionConfig.datasource_id == datasource_id)
    )
    config = result.scalar_one_or_none()
    if config:
        return config

    default_template = await get_default_alert_template(db)
    config = InspectionConfig(
        datasource_id=datasource_id,
        enabled=False,
        schedule_interval=86400,
        use_ai_analysis=True,
        alert_template_id=default_template.id if default_template else None,
        threshold_rules={},
        alert_engine_mode="inherit",
        ai_policy_source="inline",
        ai_policy_text=None,
        ai_policy_id=None,
        alert_ai_model_id=None,
        ai_shadow_enabled=False,
        baseline_config={},
        event_ai_config={},
        kb_ids=[],
    )
    config.next_scheduled_at = now() + timedelta(seconds=config.schedule_interval)
    db.add(config)
    await db.commit()
    await db.refresh(config)
    return config


async def _get_effective_inspection_config_payload(
    db: AsyncSession,
    datasource_id: int,
) -> dict[str, Any]:
    config = await _load_or_create_inspection_config(db, datasource_id)
    effective = await resolve_effective_inspection_config(db, config)
    effective.id = config.id
    effective.last_scheduled_at = config.last_scheduled_at
    effective.next_scheduled_at = config.next_scheduled_at
    return _serialize_effective_config(effective, datasource_id)


async def _handle_subscription_target(
    db: AsyncSession,
    current_user: User,
    action: str,
    params: dict[str, Any],
) -> dict[str, Any]:
    if action == "list":
        owner_user_id = _resolve_subscription_user_id(params.get("user_id"), current_user)
        subscriptions = await AlertService.get_user_subscriptions(db, owner_user_id)
        return {
            "success": True,
            "target": "subscription",
            "action": action,
            "subscriptions": [_serialize_subscription(item) for item in subscriptions],
            "count": len(subscriptions),
            "user_id": owner_user_id,
        }

    if action == "get":
        subscription_id = _require_param(params, "subscription_id", target="subscription", action=action)
        subscription = await _get_subscription_for_user(db, int(subscription_id), current_user)
        return {
            "success": True,
            "target": "subscription",
            "action": action,
            "subscription": _serialize_subscription(subscription),
        }

    if action == "create":
        owner_user_id = _resolve_subscription_user_id(params.get("user_id"), current_user)
        payload = AlertSubscriptionCreate(
            user_id=owner_user_id,
            datasource_ids=params.get("datasource_ids") or [],
            severity_levels=params.get("severity_levels") or [],
            time_ranges=params.get("time_ranges") or [],
            integration_targets=params.get("integration_targets") or [],
            enabled=params.get("enabled", True),
            aggregation_script=params.get("aggregation_script"),
        )
        subscription = await AlertService.create_subscription(db, payload)
        return {
            "success": True,
            "target": "subscription",
            "action": action,
            "subscription": _serialize_subscription(subscription),
            "message": f"subscription {subscription.id} created",
        }

    if action == "update":
        subscription_id = _require_param(params, "subscription_id", target="subscription", action=action)
        existing = await _get_subscription_for_user(db, int(subscription_id), current_user)
        update_payload = {
            key: params[key]
            for key in (
                "datasource_ids",
                "severity_levels",
                "time_ranges",
                "integration_targets",
                "enabled",
                "aggregation_script",
            )
            if key in params
        }
        payload = AlertSubscriptionUpdate(**update_payload)
        updated = await AlertService.update_subscription(
            db,
            existing.id,
            payload.model_dump(exclude_unset=True),
        )
        if not updated:
            raise ValueError(f"subscription {subscription_id} not found")
        return {
            "success": True,
            "target": "subscription",
            "action": action,
            "subscription": _serialize_subscription(updated),
            "message": f"subscription {updated.id} updated",
        }

    if action == "delete":
        subscription_id = _require_param(params, "subscription_id", target="subscription", action=action)
        existing = await _get_subscription_for_user(db, int(subscription_id), current_user)
        deleted = await AlertService.delete_subscription(db, existing.id, current_user.id)
        if not deleted:
            raise ValueError(f"subscription {subscription_id} not found")
        return {
            "success": True,
            "target": "subscription",
            "action": action,
            "subscription_id": existing.id,
            "message": f"subscription {existing.id} deleted",
        }

    if action == "test":
        from backend.services.notification_service import NotificationService

        subscription_id = _require_param(params, "subscription_id", target="subscription", action=action)
        subscription = await _get_subscription_for_user(db, int(subscription_id), current_user)

        datasource_id = None
        if subscription.datasource_ids:
            datasource_id = int(subscription.datasource_ids[0])
        else:
            result = await db.execute(alive_select(Datasource).order_by(Datasource.id.asc()).limit(1))
            datasource = result.scalar_one_or_none()
            if datasource:
                datasource_id = datasource.id

        if datasource_id is None:
            raise ValueError("no datasource available for subscription test")

        test_alert = await AlertService.create_alert(
            db=db,
            datasource_id=datasource_id,
            alert_type="system_error",
            severity="low",
            metric_name="test",
            metric_value=0.0,
            threshold_value=0.0,
            trigger_reason="Test notification",
        )
        delivery_logs = await NotificationService.send_notifications(db, test_alert, subscription)
        return {
            "success": True,
            "target": "subscription",
            "action": action,
            "subscription_id": subscription.id,
            "alert_id": test_alert.id,
            "deliveries": [
                {
                    "channel": log.channel,
                    "recipient": log.recipient,
                    "status": log.status,
                    "error_message": log.error_message,
                }
                for log in delivery_logs
            ],
            "count": len(delivery_logs),
        }

    raise ValueError(f"unsupported subscription action: {action}")


async def _handle_template_target(
    db: AsyncSession,
    current_user: User,
    action: str,
    params: dict[str, Any],
) -> dict[str, Any]:
    if action == "list":
        result = await db.execute(
            select(AlertTemplate).order_by(AlertTemplate.is_default.desc(), AlertTemplate.name.asc())
        )
        templates = result.scalars().all()
        return {
            "success": True,
            "target": "template",
            "action": action,
            "templates": [_serialize_template(item) for item in templates],
            "count": len(templates),
        }

    if action == "get":
        template_id = _require_param(params, "template_id", target="template", action=action)
        template = await get_alert_template_by_id(db, int(template_id))
        if not template:
            raise ValueError(f"template {template_id} not found")
        return {
            "success": True,
            "target": "template",
            "action": action,
            "template": _serialize_template(template),
        }

    _require_admin(current_user, "template", action)

    if action == "create":
        schema = AlertTemplateSchema(
            name=_require_param(params, "name", target="template", action=action),
            description=params.get("description"),
            enabled=params.get("enabled", True),
            is_default=params.get("is_default", False),
            template_config=params.get("template_config") or {},
        )
        if schema.is_default:
            result = await db.execute(select(AlertTemplate))
            for item in result.scalars().all():
                item.is_default = False
        template = AlertTemplate(
            name=schema.name,
            description=schema.description,
            enabled=schema.enabled,
            is_default=schema.is_default,
            template_config=schema.template_config,
        )
        db.add(template)
        await db.commit()
        await db.refresh(template)
        return {
            "success": True,
            "target": "template",
            "action": action,
            "template": _serialize_template(template),
            "message": f"template {template.id} created",
        }

    template_id = _require_param(params, "template_id", target="template", action=action)
    template = await get_alert_template_by_id(db, int(template_id))
    if not template:
        raise ValueError(f"template {template_id} not found")

    if action == "update":
        schema = AlertTemplateSchema(
            name=str(params.get("name") or template.name).strip(),
            description=params.get("description", template.description),
            enabled=params.get("enabled", template.enabled),
            is_default=params.get("is_default", template.is_default),
            template_config=params.get("template_config", template.template_config),
        )
        if schema.is_default:
            result = await db.execute(select(AlertTemplate))
            for item in result.scalars().all():
                item.is_default = False
        template.name = schema.name
        template.description = schema.description
        template.enabled = schema.enabled
        template.is_default = schema.is_default
        template.template_config = schema.template_config
        await db.commit()
        await db.refresh(template)
        return {
            "success": True,
            "target": "template",
            "action": action,
            "template": _serialize_template(template),
            "message": f"template {template.id} updated",
        }

    if action == "toggle":
        enabled = _require_param(params, "enabled", target="template", action=action)
        template.enabled = bool(enabled)
        await db.commit()
        await db.refresh(template)
        return {
            "success": True,
            "target": "template",
            "action": action,
            "template": _serialize_template(template),
            "message": f"template {template.id} {'enabled' if template.enabled else 'disabled'}",
        }

    if action == "set_default":
        result = await db.execute(select(AlertTemplate))
        for item in result.scalars().all():
            item.is_default = item.id == template.id
        await db.commit()
        await db.refresh(template)
        return {
            "success": True,
            "target": "template",
            "action": action,
            "template": _serialize_template(template),
            "message": f"template {template.id} set as default",
        }

    raise ValueError(f"unsupported template action: {action}")


async def _handle_datasource_config_target(
    db: AsyncSession,
    action: str,
    params: dict[str, Any],
) -> dict[str, Any]:
    datasource_id = int(_require_param(params, "datasource_id", target="datasource_config", action=action))

    if action == "get":
        return {
            "success": True,
            "target": "datasource_config",
            "action": action,
            "config": await _get_effective_inspection_config_payload(db, datasource_id),
        }

    if action != "update":
        raise ValueError(f"unsupported datasource_config action: {action}")

    config = await _load_or_create_inspection_config(db, datasource_id)

    if "alert_template_id" in params and params.get("alert_template_id") is not None:
        template = await get_alert_template_by_id(db, int(params["alert_template_id"]))
        if not template or not template.enabled:
            raise ValueError(f"template {params['alert_template_id']} not found or disabled")

    merged_payload = {
        "enabled": params.get("enabled", config.enabled),
        "schedule_interval": params.get("schedule_interval", config.schedule_interval),
        "use_ai_analysis": params.get("use_ai_analysis", config.use_ai_analysis),
        "ai_model_id": config.ai_model_id,
        "kb_ids": list(config.kb_ids or []),
        "alert_template_id": params.get("alert_template_id", config.alert_template_id),
        "threshold_rules": config.threshold_rules or {},
        "alert_engine_mode": config.alert_engine_mode or "inherit",
        "ai_policy_source": config.ai_policy_source or "inline",
        "ai_policy_text": config.ai_policy_text,
        "ai_policy_id": config.ai_policy_id,
        "alert_ai_model_id": config.alert_ai_model_id,
        "ai_shadow_enabled": bool(config.ai_shadow_enabled),
        "baseline_config": config.baseline_config or {},
        "event_ai_config": config.event_ai_config or {},
    }
    schema = InspectionConfigSchema(**merged_payload)
    payload = schema.model_dump()
    for key, value in payload.items():
        setattr(config, key, value)
    config.next_scheduled_at = now() + timedelta(seconds=config.schedule_interval)
    await db.commit()
    await db.refresh(config)

    return {
        "success": True,
        "target": "datasource_config",
        "action": action,
        "config": await _get_effective_inspection_config_payload(db, datasource_id),
        "message": f"datasource {datasource_id} inspection config updated",
    }


async def _handle_silence_target(
    db: AsyncSession,
    action: str,
    params: dict[str, Any],
) -> dict[str, Any]:
    datasource_id = int(_require_param(params, "datasource_id", target="silence", action=action))
    datasource = await _ensure_datasource_exists(db, datasource_id)

    if action == "get":
        is_silenced = False
        remaining_hours = None
        if datasource.silence_until:
            current_time = now()
            if current_time < datasource.silence_until:
                is_silenced = True
                remaining_hours = round((datasource.silence_until - current_time).total_seconds() / 3600, 2)
            else:
                datasource.silence_until = None
                datasource.silence_reason = None
                await db.commit()
                await db.refresh(datasource)

        response = DatasourceSilenceResponse(
            datasource_id=datasource.id,
            silence_until=datasource.silence_until,
            silence_reason=datasource.silence_reason,
            is_silenced=is_silenced,
            remaining_hours=remaining_hours,
        )
        return {
            "success": True,
            "target": "silence",
            "action": action,
            "silence": _serialize_silence_response(response),
        }

    if action == "set":
        request = DatasourceSilenceRequest(
            hours=params.get("hours"),
            reason=params.get("reason"),
        )
        datasource.silence_until = now() + timedelta(hours=float(request.hours))
        datasource.silence_reason = request.reason
        await db.commit()
        await db.refresh(datasource)
        response = DatasourceSilenceResponse(
            datasource_id=datasource.id,
            silence_until=datasource.silence_until,
            silence_reason=datasource.silence_reason,
            is_silenced=True,
            remaining_hours=round(float(request.hours), 2),
        )
        return {
            "success": True,
            "target": "silence",
            "action": action,
            "silence": _serialize_silence_response(response),
            "message": f"datasource {datasource.id} silenced for {request.hours} hours",
        }

    if action == "cancel":
        datasource.silence_until = None
        datasource.silence_reason = None
        await db.commit()
        await db.refresh(datasource)
        response = DatasourceSilenceResponse(
            datasource_id=datasource.id,
            silence_until=None,
            silence_reason=None,
            is_silenced=False,
            remaining_hours=None,
        )
        return {
            "success": True,
            "target": "silence",
            "action": action,
            "silence": _serialize_silence_response(response),
            "message": f"datasource {datasource.id} silence cancelled",
        }

    raise ValueError(f"unsupported silence action: {action}")


async def execute_manage_alert_settings(
    db: AsyncSession,
    current_user_id: int,
    params: dict[str, Any],
) -> dict[str, Any]:
    target = str(params.get("target") or "").strip()
    action = str(params.get("action") or "").strip()
    if not target:
        return _error_payload("unknown", action or "unknown", "target is required")
    if not action:
        return _error_payload(target, "unknown", "action is required")

    try:
        current_user = await _get_current_user(db, current_user_id)

        if target == "subscription":
            return await _handle_subscription_target(db, current_user, action, params)
        if target == "template":
            return await _handle_template_target(db, current_user, action, params)
        if target == "datasource_config":
            return await _handle_datasource_config_target(db, action, params)
        if target == "silence":
            return await _handle_silence_target(db, action, params)
        raise ValueError(f"unsupported target: {target}")
    except (ValidationError, HTTPException) as exc:
        message = getattr(exc, "detail", None) or str(exc)
        return _error_payload(target, action, str(message))
    except (PermissionError, ValueError) as exc:
        return _error_payload(target, action, str(exc))
