from __future__ import annotations

import logging
import re
from ipaddress import IPv4Address, IPv4Interface, IPv4Network, IPv6Address, IPv6Interface, IPv6Network
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
from backend.models.datasource_metric import DatasourceMetric
from backend.models.report import Report
from backend.models.soft_delete import alive_filter, get_alive_by_id
from backend.schemas.instance import (
    InstanceCapabilities,
    InstanceInspectionSummary,
    InstanceSessionItem,
    InstanceSummaryResponse,
    InstanceTrafficClientItem,
    InstanceTrafficHistoryPoint,
    InstanceTrafficSnapshotResponse,
    InstanceVariableItem,
    TerminateSessionResponse,
)
from backend.services.db_connector import DBConnector, get_connector
from backend.utils.encryption import decrypt_value
from backend.utils.datetime_helper import to_utc_isoformat

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/instances", tags=["instances"], dependencies=[Depends(get_current_user)])
_LOCAL_CLIENT_LABEL = "LOCAL / Proxy"
_LOCAL_CLIENT_KEYS = {"127.0.0.1", "::1", "localhost", "local"}


def _as_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _json_safe(value: Any) -> Any:
    if isinstance(value, datetime):
        return to_utc_isoformat(value)
    if isinstance(value, (IPv4Address, IPv6Address, IPv4Interface, IPv6Interface, IPv4Network, IPv6Network)):
        return str(value)
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(v) for v in value]
    return value


@router.get("/alert-summary", response_model=dict)
async def get_instance_alert_summary(db: AsyncSession = Depends(get_db)):
    active_statuses = ["active", "acknowledged"]

    event_rows = await db.execute(
        select(AlertEvent.datasource_id, func.count(AlertEvent.id))
        .where(AlertEvent.status.in_(active_statuses))
        .group_by(AlertEvent.datasource_id)
    )
    alert_rows = await db.execute(
        select(AlertMessage.datasource_id, func.count(AlertMessage.id))
        .where(AlertMessage.status.in_(active_statuses))
        .group_by(AlertMessage.datasource_id)
    )

    event_counts = {int(datasource_id): int(count or 0) for datasource_id, count in event_rows.all()}
    alert_counts = {int(datasource_id): int(count or 0) for datasource_id, count in alert_rows.all()}
    datasource_ids = sorted(set(event_counts) | set(alert_counts))

    return {
        "items": [
            {
                "datasource_id": datasource_id,
                "active_alert_event_count": event_counts.get(datasource_id, 0),
                "active_alert_count": alert_counts.get(datasource_id, 0),
            }
            for datasource_id in datasource_ids
        ]
    }


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
    client = _pick(raw, "client", "client_addr", "client_net_address", "host", "host_name", "machine")

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


def _to_float(value: Any) -> Optional[float]:
    if value is None or value == "":
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed == parsed else None


def _seconds_between(current: Optional[datetime], previous: Optional[datetime]) -> Optional[float]:
    if current is None or previous is None:
        return None
    delta = current - previous
    seconds = delta.total_seconds()
    return seconds if seconds > 0 else None


def _extract_network_rates_from_snapshots(
    current_snapshot: Optional[DatasourceMetric],
    previous_snapshot: Optional[DatasourceMetric] = None,
) -> tuple[Optional[float], Optional[float], str]:
    if not current_snapshot:
        return None, None, "unavailable"

    payload = current_snapshot.data or {}

    direct_pairs = [
        ("network_rx_rate", "network_tx_rate", 1.0),
        ("network_in", "network_out", 1024.0),
        ("input_kbps", "output_kbps", 1024.0),
    ]
    for rx_key, tx_key, multiplier in direct_pairs:
        rx_value = _to_float(payload.get(rx_key))
        tx_value = _to_float(payload.get(tx_key))
        if rx_value is not None and tx_value is not None:
            return round(rx_value * multiplier, 2), round(tx_value * multiplier, 2), "measured"

    alias_rx = _to_float(payload.get("network_rx_bytes"))
    alias_tx = _to_float(payload.get("network_tx_bytes"))
    if alias_rx is not None and alias_tx is not None:
        looks_like_cumulative = alias_rx > 10 * 1024 * 1024 or alias_tx > 10 * 1024 * 1024
        if looks_like_cumulative and previous_snapshot:
            prev_payload = previous_snapshot.data or {}
            prev_rx = _to_float(prev_payload.get("network_rx_bytes"))
            prev_tx = _to_float(prev_payload.get("network_tx_bytes"))
            seconds = _seconds_between(current_snapshot.collected_at, previous_snapshot.collected_at)
            if prev_rx is not None and prev_tx is not None and seconds:
                return (
                    round(max(0.0, (alias_rx - prev_rx) / seconds), 2),
                    round(max(0.0, (alias_tx - prev_tx) / seconds), 2),
                    "measured",
                )
        if not looks_like_cumulative:
            return round(alias_rx * 1024.0, 2), round(alias_tx * 1024.0, 2), "measured"

    cumulative_pairs = [
        ("bytes_received", "bytes_sent"),
        ("network_bytes_received", "network_bytes_sent"),
        ("network_reads_total", "network_writes_total"),
        ("network_bytes_in", "network_bytes_out"),
    ]
    if previous_snapshot:
        previous_payload = previous_snapshot.data or {}
        seconds = _seconds_between(current_snapshot.collected_at, previous_snapshot.collected_at)
        if seconds:
            for rx_key, tx_key in cumulative_pairs:
                current_rx = _to_float(payload.get(rx_key))
                current_tx = _to_float(payload.get(tx_key))
                previous_rx = _to_float(previous_payload.get(rx_key))
                previous_tx = _to_float(previous_payload.get(tx_key))
                if None in (current_rx, current_tx, previous_rx, previous_tx):
                    continue
                return (
                    round(max(0.0, (current_rx - previous_rx) / seconds), 2),
                    round(max(0.0, (current_tx - previous_tx) / seconds), 2),
                    "measured",
                )

    return None, None, "unavailable"


def _build_traffic_history(snapshots: list[DatasourceMetric], limit: int = 24) -> list[InstanceTrafficHistoryPoint]:
    ordered = list(sorted(snapshots, key=lambda item: item.collected_at))
    history: list[InstanceTrafficHistoryPoint] = []

    for index, snapshot in enumerate(ordered):
        previous_snapshot = ordered[index - 1] if index > 0 else None
        rx_rate, tx_rate, mode = _extract_network_rates_from_snapshots(snapshot, previous_snapshot)
        if rx_rate is None and tx_rate is None:
            continue
        history.append(
            InstanceTrafficHistoryPoint(
                timestamp=snapshot.collected_at,
                rx_rate=rx_rate,
                tx_rate=tx_rate,
                total_rate=round((rx_rate or 0.0) + (tx_rate or 0.0), 2),
                mode=mode,
            )
        )

    return history[-limit:]


def _session_status_rank(status: Optional[str]) -> int:
    normalized = str(status or "").lower()
    if re.search(r"\binactive\b", normalized):
        return 2
    if re.search(r"\bidle in transaction\b|\bidle\b", normalized):
        return 1
    if re.search(r"\bsleep\b|\bsleeping\b", normalized):
        return 2
    if re.search(r"\bactive\b|\brunning\b|\bquery\b|\bexecute(?:d|ing)?\b|\blocked\b|lock wait", normalized):
        return 0
    return 3


def _normalize_client_identity(client: Optional[str]) -> tuple[str, str]:
    raw = str(client or "").strip()
    if not raw:
        return "local", _LOCAL_CLIENT_LABEL

    normalized = raw.replace("::ffff:", "").strip()
    if normalized.startswith("[") and "]:" in normalized:
        normalized = normalized[1:normalized.rfind("]:")]
    else:
        host_part, separator, port = normalized.rpartition(":")
        if separator and port.isdigit():
            normalized = host_part

    normalized = normalized.strip() or raw
    lowered = normalized.lower()
    if lowered in _LOCAL_CLIENT_KEYS:
        return "local", _LOCAL_CLIENT_LABEL

    return lowered, normalized


def _session_activity_weight(session: InstanceSessionItem) -> float:
    rank = _session_status_rank(session.status)
    duration_seconds = max(0, int(session.duration_seconds or 0))
    wait_bonus = 2.6 if session.wait_event else 0.0
    sql_bonus = 1.1 if session.sql_text else 0.0
    status_bonus = {0: 4.2, 1: 1.5, 2: 0.8}.get(rank, 1.0)
    duration_bonus = min(duration_seconds / 45.0, 14.0)
    return 1.0 + status_bonus + wait_bonus + sql_bonus + duration_bonus


def _aggregate_traffic_clients(
    sessions: list[InstanceSessionItem],
    *,
    total_rx_rate: Optional[float],
    total_tx_rate: Optional[float],
) -> dict[str, Any]:
    grouped: dict[str, dict[str, Any]] = {}
    active_session_count = 0
    waiting_session_count = 0
    idle_session_count = 0

    for session in sessions:
        client_id, client_label = _normalize_client_identity(session.client)
        bucket = grouped.setdefault(
            client_id,
            {
                "client_id": client_id,
                "client_label": client_label,
                "session_count": 0,
                "active_session_count": 0,
                "waiting_session_count": 0,
                "idle_session_count": 0,
                "user": set(),
                "databases": set(),
                "max_duration_seconds": 0,
                "sample_sql": None,
                "sql_samples": [],
                "weight": 0.0,
            },
        )

        bucket["session_count"] += 1
        bucket["weight"] += _session_activity_weight(session)

        session_rank = _session_status_rank(session.status)
        is_waiting = bool(session.wait_event)
        is_active = session_rank == 0

        if is_active:
            bucket["active_session_count"] += 1
            active_session_count += 1
        if is_waiting:
            bucket["waiting_session_count"] += 1
            waiting_session_count += 1
        if not is_active and not is_waiting:
            bucket["idle_session_count"] += 1
            idle_session_count += 1

        if session.user:
            bucket["user"].add(str(session.user))
        if session.database:
            bucket["databases"].add(str(session.database))

        duration_seconds = max(0, int(session.duration_seconds or 0))
        if duration_seconds >= bucket["max_duration_seconds"]:
            bucket["max_duration_seconds"] = duration_seconds

        sql_text = (session.sql_text or "").strip()
        if sql_text:
            if bucket["sample_sql"] is None:
                bucket["sample_sql"] = sql_text[:320]
            if sql_text not in bucket["sql_samples"] and len(bucket["sql_samples"]) < 3:
                bucket["sql_samples"].append(sql_text[:220])

    total_session_count = len(sessions)
    total_client_count = len(grouped)
    measured_mode = total_rx_rate is not None and total_tx_rate is not None

    distributed_rx_rate = total_rx_rate if measured_mode else None
    distributed_tx_rate = total_tx_rate if measured_mode else None
    rate_mode = "measured" if measured_mode else "unavailable"

    if measured_mode:
        rate_label = "链路带宽来自最近监控快照"
    elif total_session_count == 0:
        rate_label = "当前没有活跃客户端连接"
    else:
        rate_label = "当前数据库类型不支持网络流量采集"

    max_weight = max((bucket["weight"] for bucket in grouped.values()), default=0.0)
    total_weight = sum(max(bucket["weight"], 1.0) for bucket in grouped.values())

    clients: list[InstanceTrafficClientItem] = []
    for bucket in grouped.values():
        share = (max(bucket["weight"], 1.0) / total_weight) if total_weight else 0.0
        status = "idle"
        if bucket["active_session_count"] > 0:
            status = "active"
        elif bucket["waiting_session_count"] > 0:
            status = "waiting"
        elif bucket["idle_session_count"] == 0 and bucket["session_count"] > 0:
            status = "other"

        # 只有在有实测流量时才分配流量值
        estimated_rx_rate = round((distributed_rx_rate or 0.0) * share, 2) if distributed_rx_rate is not None else None
        estimated_tx_rate = round((distributed_tx_rate or 0.0) * share, 2) if distributed_tx_rate is not None else None
        estimated_total_rate = None
        if estimated_rx_rate is not None or estimated_tx_rate is not None:
            estimated_total_rate = round((estimated_rx_rate or 0.0) + (estimated_tx_rate or 0.0), 2)

        clients.append(
            InstanceTrafficClientItem(
                client_id=bucket["client_id"],
                client_label=bucket["client_label"],
                session_count=bucket["session_count"],
                active_session_count=bucket["active_session_count"],
                waiting_session_count=bucket["waiting_session_count"],
                idle_session_count=bucket["idle_session_count"],
                user_count=len(bucket["user"]),
                user=sorted(bucket["user"])[:6],
                databases=sorted(bucket["databases"])[:4],
                max_duration_seconds=bucket["max_duration_seconds"] or None,
                sample_sql=bucket["sample_sql"],
                sql_samples=bucket["sql_samples"],
                heat_score=round((bucket["weight"] / max_weight) * 100.0, 1) if max_weight else 0.0,
                status=status,
                estimated_rx_rate=estimated_rx_rate,
                estimated_tx_rate=estimated_tx_rate,
                estimated_total_rate=estimated_total_rate,
            )
        )

    # 排序：有流量时按流量排序，无流量时按热度排序
    clients.sort(
        key=lambda item: (
            item.estimated_total_rate if item.estimated_total_rate is not None else -1,
            item.heat_score,
            item.session_count,
            item.client_label.lower(),
        ),
        reverse=True,
    )

    total_rate = None
    if distributed_rx_rate is not None or distributed_tx_rate is not None:
        total_rate = round((distributed_rx_rate or 0.0) + (distributed_tx_rate or 0.0), 2)

    return {
        "rate_mode": rate_mode,
        "rate_label": rate_label,
        "total_client_count": total_client_count,
        "total_session_count": total_session_count,
        "active_session_count": active_session_count,
        "waiting_session_count": waiting_session_count,
        "idle_session_count": idle_session_count,
        "total_rx_rate": distributed_rx_rate,
        "total_tx_rate": distributed_tx_rate,
        "total_rate": total_rate,
        "clients": clients,
    }


def _extract_max_session_count(snapshot: Optional[DatasourceMetric]) -> Optional[int]:
    if not snapshot or not isinstance(snapshot.data, dict):
        return None

    for key in ("max_connections", "max_conn", "connection_limit", "max_sessions"):
        value = snapshot.data.get(key)
        if value is None:
            continue
        try:
            normalized = int(float(value))
        except (TypeError, ValueError):
            continue
        if normalized > 0:
            return normalized
    return None


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
        health=_json_safe(health) or {},
        active_alert_event_count=active_event_count,
        active_alert_count=active_alert_count,
        inspection=InstanceInspectionSummary(
            enabled=bool(inspection_config.is_enabled) if inspection_config else False,
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


@router.get("/{datasource_id}/traffic", response_model=InstanceTrafficSnapshotResponse)
async def get_instance_traffic(datasource_id: int, db: AsyncSession = Depends(get_db)):
    datasource, connector = await _get_datasource_and_connector(datasource_id, db)
    try:
        raw_sessions = await connector.get_process_list()
        if not isinstance(raw_sessions, list):
            raise HTTPException(status_code=400, detail="实例会话返回格式不正确")

        can_terminate = _supports_terminate(connector)
        sessions = [
            _normalize_session(session or {}, can_terminate=can_terminate)
            for session in raw_sessions
            if isinstance(session, dict)
        ]
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(
            "Failed to load traffic topology for datasource_id=%s db_type=%s: %s",
            datasource_id,
            datasource.db_type,
            exc,
            exc_info=True,
        )
        raise HTTPException(status_code=400, detail=f"加载实例流量失败: {exc}")
    finally:
        await connector.close()

    from backend.routers.metrics import _get_db_status_snapshots

    snapshots = await _get_db_status_snapshots(db, datasource_id, 25, datasource)
    latest_snapshot = snapshots[0] if snapshots else None
    previous_snapshot = snapshots[1] if len(snapshots) > 1 else None
    measured_rx_rate, measured_tx_rate, _ = _extract_network_rates_from_snapshots(latest_snapshot, previous_snapshot)

    aggregate = _aggregate_traffic_clients(
        sessions,
        total_rx_rate=measured_rx_rate,
        total_tx_rate=measured_tx_rate,
    )

    return InstanceTrafficSnapshotResponse(
        datasource=datasource,
        captured_at=_now_utc(),
        poll_interval_seconds=5,
        rate_mode=aggregate["rate_mode"],
        rate_label=aggregate["rate_label"],
        total_client_count=aggregate["total_client_count"],
        total_session_count=aggregate["total_session_count"],
        active_session_count=aggregate["active_session_count"],
        waiting_session_count=aggregate["waiting_session_count"],
        idle_session_count=aggregate["idle_session_count"],
        max_session_count=_extract_max_session_count(latest_snapshot),
        total_rx_rate=aggregate["total_rx_rate"],
        total_tx_rate=aggregate["total_tx_rate"],
        total_rate=aggregate["total_rate"],
        clients=aggregate["clients"],
        history=_build_traffic_history(snapshots),
    )


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
