from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_db
from backend.dependencies import get_current_user
from backend.models.alert_event import AlertEvent
from backend.models.alert_message import AlertMessage
from backend.models.datasource import Datasource
from backend.models.inspection_config import InspectionConfig
from backend.models.report import Report
from backend.models.soft_delete import alive_filter, get_alive_by_id
from backend.schemas.instance import (
    InstanceCapabilities,
    InstanceInspectionSummary,
    InstanceSessionItem,
    InstanceSummaryResponse,
    InstanceVariableItem,
    TerminateSessionResponse,
)
from backend.services.db_connector import DBConnector, get_connector
from backend.utils.encryption import decrypt_value

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/instances", tags=["instances"], dependencies=[Depends(get_current_user)])


def _as_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _json_safe(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(v) for v in value]
    return value


def _pick(raw: Dict[str, Any], *keys: str) -> Any:
    lowered = {str(key).lower(): value for key, value in raw.items()}
    for key in keys:
        key_lower = key.lower()
        if key_lower in lowered:
            return lowered[key_lower]
    return None


def _categorize_variable(key: str) -> str:
    lowered = key.lower()
    if any(token in lowered for token in ("buffer", "cache", "memory", "shared", "work_mem", "sort", "temp")):
        return "memory"
    if any(token in lowered for token in ("conn", "connect", "session", "thread", "pool")):
        return "connection"
    if any(token in lowered for token in ("log", "slow", "audit", "trace")):
        return "logging"
    if any(token in lowered for token in ("timeout", "idle", "wait", "latency")):
        return "timeout"
    if any(token in lowered for token in ("repl", "replica", "binlog", "wal")):
        return "replication"
    if any(token in lowered for token in ("io", "disk", "file", "tablespace")):
        return "storage"
    return "general"


def _resolve_duration_seconds(raw: Dict[str, Any]) -> Optional[int]:
    direct = _pick(raw, "time", "duration_seconds", "duration_sec", "idle_seconds", "elapsed_seconds")
    if direct is not None:
        try:
            return int(float(direct))
        except (TypeError, ValueError):
            return None

    started_at = _pick(raw, "query_start", "last_request_start_time", "state_change")
    if isinstance(started_at, datetime):
        return max(0, int((_now_utc() - _as_utc(started_at)).total_seconds()))

    return None


def _normalize_session(raw: Dict[str, Any], *, can_terminate: bool) -> InstanceSessionItem:
    session_id = _pick(raw, "session_id", "id", "pid")
    if session_id is None:
        session_id = str(_pick(raw, "spid", "sid") or "")

    status = _pick(raw, "status", "command", "state")
    wait_event = _pick(raw, "wait_event", "wait_type", "state")
    sql_text = _pick(raw, "sql_text", "current_sql", "query", "info")
    client = _pick(raw, "client", "client_addr", "client_net_address", "host", "host_name")

    return InstanceSessionItem(
        session_id=str(session_id),
        user=_pick(raw, "user", "usename", "login_name", "username"),
        database=_pick(raw, "database", "database_name", "db", "datname"),
        client=str(client) if client is not None else None,
        status=str(status) if status is not None else None,
        duration_seconds=_resolve_duration_seconds(raw),
        wait_event=str(wait_event) if wait_event is not None else None,
        sql_text=str(sql_text) if sql_text is not None else None,
        can_terminate=can_terminate and bool(session_id),
        raw=_json_safe(raw),
    )


async def _get_datasource_and_connector(datasource_id: int, db: AsyncSession) -> tuple[Datasource, Any]:
    datasource = await get_alive_by_id(db, Datasource, datasource_id)
    if not datasource:
        raise HTTPException(status_code=404, detail="数据源不存在")

    password = decrypt_value(datasource.password_encrypted) if datasource.password_encrypted else None
    connector = get_connector(
        db_type=datasource.db_type,
        host=datasource.host,
        port=datasource.port,
        username=datasource.username,
        password=password,
        database=datasource.database,
        extra_params=datasource.extra_params,
    )
    return datasource, connector


def _supports_terminate(connector: Any) -> bool:
    return type(connector).terminate_session is not DBConnector.terminate_session


@router.get("/{datasource_id}/summary", response_model=InstanceSummaryResponse)
async def get_instance_summary(datasource_id: int, db: AsyncSession = Depends(get_db)):
    datasource = await get_alive_by_id(db, Datasource, datasource_id)
    if not datasource:
        raise HTTPException(status_code=404, detail="数据源不存在")

    from backend.routers.metrics import _get_db_status_snapshots, get_datasource_health

    latest_snapshots = await _get_db_status_snapshots(db, datasource_id, 1, datasource)
    latest_metric = latest_snapshots[0] if latest_snapshots else None
    health = await get_datasource_health(datasource_id, db)

    active_event_count = await db.scalar(
        select(func.count()).select_from(AlertEvent).where(
            AlertEvent.datasource_id == datasource_id,
            AlertEvent.status.in_(["active", "acknowledged"]),
        )
    ) or 0

    active_alert_count = await db.scalar(
        select(func.count()).select_from(AlertMessage).where(
            AlertMessage.datasource_id == datasource_id,
            AlertMessage.status.in_(["active", "acknowledged"]),
        )
    ) or 0

    inspection_config_result = await db.execute(
        select(InspectionConfig).where(InspectionConfig.datasource_id == datasource_id)
    )
    inspection_config = inspection_config_result.scalar_one_or_none()

    latest_report_result = await db.execute(
        select(Report)
        .where(Report.datasource_id == datasource_id, alive_filter(Report))
        .order_by(Report.created_at.desc())
        .limit(1)
    )
    latest_report = latest_report_result.scalar_one_or_none()

    _, connector = await _get_datasource_and_connector(datasource_id, db)
    try:
        supports_terminate = _supports_terminate(connector)
    finally:
        await connector.close()

    return InstanceSummaryResponse(
        datasource=datasource,
        latest_metric=_json_safe(latest_metric.data if latest_metric else None),
        metric_collected_at=latest_metric.collected_at if latest_metric else None,
        health=_json_safe(health),
        active_alert_event_count=active_event_count,
        active_alert_count=active_alert_count,
        inspection=InstanceInspectionSummary(
            enabled=bool(inspection_config.enabled) if inspection_config else False,
            schedule_interval=inspection_config.schedule_interval if inspection_config else None,
            next_scheduled_at=inspection_config.next_scheduled_at if inspection_config else None,
            last_report_id=latest_report.id if latest_report else None,
            last_report_title=latest_report.title if latest_report else None,
            last_report_status=latest_report.status if latest_report else None,
            last_report_created_at=latest_report.created_at if latest_report else None,
        ),
        capabilities=InstanceCapabilities(
            supports_variables=True,
            supports_sessions=True,
            supports_terminate_session=supports_terminate,
            supports_os_metrics=bool(datasource.host_id),
        ),
    )


@router.get("/{datasource_id}/variables", response_model=list[InstanceVariableItem])
async def get_instance_variables(datasource_id: int, db: AsyncSession = Depends(get_db)):
    datasource, connector = await _get_datasource_and_connector(datasource_id, db)
    try:
        variables = await connector.get_variables()
        if not isinstance(variables, dict):
            raise HTTPException(status_code=400, detail="实例参数返回格式不正确")

        items = [
            InstanceVariableItem(
                key=str(key),
                value="" if value is None else str(value),
                category=_categorize_variable(str(key)),
                raw=_json_safe(value),
            )
            for key, value in sorted(variables.items(), key=lambda item: str(item[0]).lower())
        ]
        return items
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Failed to load variables for datasource_id=%s db_type=%s: %s", datasource_id, datasource.db_type, exc, exc_info=True)
        raise HTTPException(status_code=400, detail=f"加载实例配置失败: {exc}")
    finally:
        await connector.close()


@router.get("/{datasource_id}/sessions", response_model=list[InstanceSessionItem])
async def get_instance_sessions(datasource_id: int, db: AsyncSession = Depends(get_db)):
    datasource, connector = await _get_datasource_and_connector(datasource_id, db)
    try:
        raw_sessions = await connector.get_process_list()
        if not isinstance(raw_sessions, list):
            raise HTTPException(status_code=400, detail="实例会话返回格式不正确")

        can_terminate = _supports_terminate(connector)
        return [_normalize_session(session or {}, can_terminate=can_terminate) for session in raw_sessions if isinstance(session, dict)]
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Failed to load sessions for datasource_id=%s db_type=%s: %s", datasource_id, datasource.db_type, exc, exc_info=True)
        raise HTTPException(status_code=400, detail=f"加载实例会话失败: {exc}")
    finally:
        await connector.close()


@router.post("/{datasource_id}/sessions/{session_id}/terminate", response_model=TerminateSessionResponse)
async def terminate_instance_session(
    datasource_id: int,
    session_id: str,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    datasource, connector = await _get_datasource_and_connector(datasource_id, db)
    supports_terminate = _supports_terminate(connector)

    if not supports_terminate:
        await connector.close()
        raise HTTPException(status_code=400, detail="当前类型暂不支持终止会话")

    try:
        result = await connector.terminate_session(int(session_id))
        logger.info(
            "terminate_session success user_id=%s datasource_id=%s session_id=%s db_type=%s result=%s",
            current_user.id,
            datasource_id,
            session_id,
            datasource.db_type,
            _json_safe(result),
        )
        return TerminateSessionResponse(
            success=True,
            session_id=str(session_id),
            message=result.get("message") or f"会话 {session_id} 已终止",
            datasource_id=datasource_id,
            db_type=datasource.db_type,
            result=_json_safe(result),
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.warning(
            "terminate_session failed user_id=%s datasource_id=%s session_id=%s db_type=%s error=%s",
            current_user.id,
            datasource_id,
            session_id,
            datasource.db_type,
            exc,
            exc_info=True,
        )
        raise HTTPException(status_code=400, detail=f"终止会话失败: {exc}")
    finally:
        await connector.close()
