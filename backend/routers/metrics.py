from fastapi import APIRouter, Depends, Query, HTTPException, Body
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta

from backend.database import get_db
from backend.models.datasource_metric import DatasourceMetric
from backend.models.soft_delete import alive_filter, get_alive_by_id
from backend.models.inspection_config import InspectionConfig
from backend.schemas.metrics import MetricResponse
from backend.dependencies import get_current_user
from backend.utils.datetime_helper import now, normalize_local_datetime, to_utc_isoformat
from backend.services import metric_collector
from backend.services.integration_scheduler import execute_integration
from backend.services.alert_template_service import resolve_effective_inspection_config

router = APIRouter(prefix="/api/metrics", tags=["metrics"], dependencies=[Depends(get_current_user)])


def _build_connection_failure_health(datasource) -> Dict[str, Any]:
    error_message = (getattr(datasource, "connection_error", None) or "").strip()
    message = f"数据库连接失败: {error_message}" if error_message else "数据库连接失败"
    violation: Dict[str, Any] = {
        "type": "connection_failure",
        "metric": "connection_status",
        "value": 0,
        "threshold": 1,
    }
    return {
        "healthy": False,
        "status": "critical",
        "violations": [violation],
        "message": message,
        "alert_engine": "system"
    }


def _healthy_payload(message: str, *, alert_engine: str) -> Dict[str, Any]:
    return {
        "healthy": True,
        "status": "healthy",
        "violations": [],
        "message": message,
        "alert_engine": alert_engine,
    }


def _unhealthy_payload(message: str, violations: list[dict[str, Any]], *, status: str = "critical", alert_engine: str) -> Dict[str, Any]:
    return {
        "healthy": False,
        "status": status,
        "violations": violations,
        "message": message,
        "alert_engine": alert_engine,
    }


def _merge_health_payloads(primary: Dict[str, Any], secondary: Dict[str, Any], *, alert_engine: str) -> Dict[str, Any]:
    primary_healthy = bool(primary.get("healthy", False))
    secondary_healthy = bool(secondary.get("healthy", False))

    if primary_healthy and secondary_healthy:
        return {
            **primary,
            "alert_engine": alert_engine,
        }

    if not primary_healthy and secondary_healthy:
        return {
            **primary,
            "alert_engine": alert_engine,
        }

    if primary_healthy and not secondary_healthy:
        return {
            **secondary,
            "alert_engine": alert_engine,
        }

    primary_violations = list(primary.get("violations") or [])
    secondary_violations = list(secondary.get("violations") or [])
    primary_message = str(primary.get("message") or "").strip()
    secondary_message = str(secondary.get("message") or "").strip()

    merged_messages = [message for message in [primary_message, secondary_message] if message]
    return {
        "healthy": False,
        "status": "critical",
        "violations": primary_violations + secondary_violations,
        "message": "；".join(dict.fromkeys(merged_messages)) if merged_messages else "检测到指标异常",
        "alert_engine": alert_engine,
    }


def _build_threshold_health(config, metrics: Dict[str, Any]) -> Dict[str, Any]:
    violations = []

    if not config or not config.threshold_rules:
        return _healthy_payload("正常（未配置阈值）", alert_engine="threshold")

    if "custom_expression" in config.threshold_rules:
        custom_rule = config.threshold_rules["custom_expression"]
        expression = custom_rule.get("expression", "")
        eval_context = _prepare_eval_context(metrics)
        try:
            if eval(expression, {"__builtins__": {}}, eval_context):
                violations.append({"type": "custom_expression", "expression": expression, "metrics": eval_context})
        except Exception:
            pass
    else:
        for metric_name, rule in config.threshold_rules.items():
            if "levels" not in rule or not isinstance(rule["levels"], list):
                continue

            current_value = _extract_metric_value(metrics, metric_name)
            if current_value is None:
                continue

            # Find the highest severity level that is violated
            from backend.services.threshold_checker import SEVERITY_ORDER
            sorted_levels = sorted(
                rule["levels"],
                key=lambda x: SEVERITY_ORDER.get(x.get("severity", "low"), 1),
                reverse=True
            )

            for level in sorted_levels:
                threshold = level.get("threshold")
                if threshold is not None and current_value > threshold:
                    violations.append({
                        "type": "threshold",
                        "metric": metric_name,
                        "value": current_value,
                        "threshold": threshold,
                        "severity": level.get("severity", "medium"),
                    })
                    break

    if not violations:
        return _healthy_payload("正常", alert_engine="threshold")
    return _unhealthy_payload(f"检测到 {len(violations)} 个指标异常", violations, alert_engine="threshold")


async def _build_ai_health(db: AsyncSession, datasource_id: int, config) -> Dict[str, Any]:
    from backend.services.alert_ai_service import (
        get_latest_runtime_state_for_config,
        resolve_configured_alert_ai_policy_binding,
    )

    binding = await resolve_configured_alert_ai_policy_binding(db, config)
    if not binding:
        return _healthy_payload("正常（未配置 AI 告警规则）", alert_engine="ai")

    runtime_state = await get_latest_runtime_state_for_config(db, datasource_id, config)
    if not runtime_state or not runtime_state.is_active:
        last_reason = getattr(runtime_state, "last_reason", None) if runtime_state else None
        return _healthy_payload(last_reason or "正常", alert_engine="ai")

    return _unhealthy_payload(
        runtime_state.last_reason or f"AI 判定命中规则：{binding.display_name}",
        violations=[
            {
                "type": "ai_policy",
                "policy": binding.display_name,
                "decision": runtime_state.last_decision,
                "confidence": runtime_state.last_confidence,
                "evidence": runtime_state.last_evidence or [],
            }
        ],
        alert_engine="ai",
    )


async def _build_effective_health(
    db: AsyncSession,
    *,
    datasource_id: int,
    config,
    metrics: Dict[str, Any],
) -> Dict[str, Any]:
    threshold_health = _build_threshold_health(config, metrics)

    from backend.services.alert_ai_service import resolve_effective_alert_engine_mode
    effective_mode = await resolve_effective_alert_engine_mode(db, config) if config else "threshold"
    if effective_mode != "ai":
        return threshold_health

    ai_health = await _build_ai_health(db, datasource_id, config)
    return _merge_health_payloads(
        threshold_health,
        ai_health,
        alert_engine="ai",
    )


async def _get_db_status_snapshots(
    db: AsyncSession,
    conn_id: int,
    limit: int,
    datasource=None,
) -> List[DatasourceMetric]:
    result = await db.execute(
        select(DatasourceMetric)
        .where(
            DatasourceMetric.datasource_id == conn_id,
            DatasourceMetric.metric_type == 'db_status',
        )
        .order_by(desc(DatasourceMetric.id))
        .limit(limit)
    )
    return result.scalars().all()


@router.get("/{conn_id}", response_model=List[MetricResponse])
async def get_metrics(
    conn_id: int,
    metric_type: Optional[str] = None,
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None,
    minutes: Optional[int] = None,
    limit: int = Query(1000, le=10000),
    db: AsyncSession = Depends(get_db),
):
    """
    获取指标数据

    参数:
    - start_time: 开始时间 (ISO格式)
    - end_time: 结束时间 (ISO格式)
    - minutes: 最近N分钟 (优先级高于start_time/end_time)
    - limit: 最大返回数量
    """
    start_time = normalize_local_datetime(start_time)
    end_time = normalize_local_datetime(end_time)

    # 检查数据源是否使用集成采集
    from backend.models.datasource import Datasource
    ds_result = await db.execute(
        select(Datasource).where(Datasource.id == conn_id, alive_filter(Datasource))
    )
    datasource = ds_result.scalar_one_or_none()

    query = select(DatasourceMetric).where(DatasourceMetric.datasource_id == conn_id)

    if metric_type and metric_type != 'db_status':
        query = query.where(DatasourceMetric.metric_type == metric_type)

    # 时间范围过滤
    if minutes:
        # 使用 minutes 参数
        start = now() - timedelta(minutes=minutes)
        query = query.where(DatasourceMetric.collected_at >= start)
    elif start_time or end_time:
        # 使用 start_time/end_time 参数
        if start_time:
            query = query.where(DatasourceMetric.collected_at >= start_time)
        if end_time:
            query = query.where(DatasourceMetric.collected_at <= end_time)

    query = query.order_by(desc(DatasourceMetric.collected_at)).limit(limit)
    result = await db.execute(query)
    snapshots = result.scalars().all()

    if metric_type == 'db_status':
        snapshots = await _get_db_status_snapshots(db, conn_id, limit, datasource)

        if minutes:
            start = now() - timedelta(minutes=minutes)
            snapshots = [snapshot for snapshot in snapshots if snapshot.collected_at >= start]
        elif start_time or end_time:
            if start_time:
                snapshots = [snapshot for snapshot in snapshots if snapshot.collected_at >= start_time]
            if end_time:
                snapshots = [snapshot for snapshot in snapshots if snapshot.collected_at <= end_time]

        snapshots = snapshots[:limit]

    return snapshots


@router.get("/{conn_id}/latest", response_model=Optional[MetricResponse])
async def get_latest_metric(
    conn_id: int,
    metric_type: str = "db_status",
    db: AsyncSession = Depends(get_db),
):
    # 检查数据源是否使用集成采集
    from backend.models.datasource import Datasource
    ds_result = await db.execute(
        select(Datasource).where(Datasource.id == conn_id, alive_filter(Datasource))
    )
    datasource = ds_result.scalar_one_or_none()

    if metric_type == 'db_status':
        snapshots = await _get_db_status_snapshots(db, conn_id, 1, datasource)
        return snapshots[0] if snapshots else None

    result = await db.execute(
        select(DatasourceMetric)
        .where(
            DatasourceMetric.datasource_id == conn_id,
            DatasourceMetric.metric_type == metric_type,
        )
        .order_by(desc(DatasourceMetric.id))
        .limit(1)
    )
    return result.scalar_one_or_none()


@router.post("/batch/dashboard")
async def get_batch_dashboard(
    conn_ids: List[int] = Body(..., embed=True),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """
    批量获取多个数据源的健康状态和最新指标，减少前端请求数量。
    返回: { conn_id: { health: {...}, metric: {...} } }
    """
    if not conn_ids:
        return {}

    from backend.models.datasource import Datasource

    # 批量查询数据源配置（metric_source 字段）
    ds_result = await db.execute(
        select(Datasource).where(Datasource.id.in_(conn_ids), alive_filter(Datasource))
    )
    datasource_map = {ds.id: ds for ds in ds_result.scalars().all()}

    # 批量查询巡检配置
    config_result = await db.execute(
        select(InspectionConfig).where(InspectionConfig.datasource_id.in_(conn_ids))
    )
    configs = {c.datasource_id: c for c in config_result.scalars().all()}

    latest_metrics: Dict[int, Any] = {}  # conn_id -> DatasourceMetric or None

    for cid in conn_ids:
        latest_snaps = await _get_db_status_snapshots(db, cid, 1, datasource_map.get(cid))
        latest_metrics[cid] = latest_snaps[0] if latest_snaps else None

    # 组装结果
    result = {}
    stale_threshold = 300  # 5分钟
    for cid in conn_ids:
        snap = latest_metrics.get(cid)
        datasource = datasource_map.get(cid)

        # --- 构建 metric 部分 ---
        if snap:
            metric_data = {
                "id": snap.id,
                "datasource_id": snap.datasource_id,
                "metric_type": snap.metric_type,
                "data": snap.data,
                "collected_at": to_utc_isoformat(snap.collected_at),
            }
        else:
            metric_data = None

        # --- 构建 health 部分 ---
        if datasource and datasource.connection_status == "failed":
            health = _build_connection_failure_health(datasource)
        elif not snap:
            health = {"healthy": False, "status": "unknown", "violations": [], "message": "无监控数据"}
        else:
            metric_age = (now() - snap.collected_at).total_seconds()
            if metric_age > stale_threshold:
                health = {"healthy": False, "status": "unknown", "violations": [], "message": f"监控数据过期 ({int(metric_age/60)}分钟前)"}
            else:
                config = configs.get(cid)
                effective_config = await resolve_effective_inspection_config(db, config) if config else None
                health = await _build_effective_health(
                    db,
                    datasource_id=cid,
                    config=effective_config,
                    metrics=snap.data or {},
                )

        result[str(cid)] = {"health": health, "metric": metric_data}

    return result


@router.get("/{conn_id}/health")
async def get_datasource_health(
    conn_id: int,
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """
    检查数据源健康状态

    基于巡检配置的阈值规则判断数据源是否健康
    返回: {
        "healthy": true/false,
        "status": "healthy"/"warning"/"critical"/"unknown",
        "violations": [...],
        "message": "状态描述"
    }
    """
    # 检查数据源是否使用集成采集
    from backend.models.datasource import Datasource
    ds_result = await db.execute(
        select(Datasource).where(Datasource.id == conn_id, alive_filter(Datasource))
    )
    datasource = ds_result.scalar_one_or_none()

    if datasource and datasource.connection_status == "failed":
        return _build_connection_failure_health(datasource)

    latest_snaps = await _get_db_status_snapshots(db, conn_id, 1, datasource)
    latest_metric = latest_snaps[0] if latest_snaps else None

    if not latest_metric:
        return {
            "healthy": False,
            "status": "unknown",
            "violations": [],
            "message": "无监控数据"
        }

    # Check if metric is stale (older than 5 minutes)
    metric_age = (now() - latest_metric.collected_at).total_seconds()
    if metric_age > 300:  # 5 minutes
        return {
            "healthy": False,
            "status": "unknown",
            "violations": [],
            "message": f"监控数据过期 ({int(metric_age/60)}分钟前)"
        }

    # Get inspection config for threshold rules
    config_result = await db.execute(
        select(InspectionConfig).where(InspectionConfig.datasource_id == conn_id)
    )
    config = config_result.scalar_one_or_none()
    effective_config = await resolve_effective_inspection_config(db, config) if config else None

    return await _build_effective_health(
        db,
        datasource_id=conn_id,
        config=effective_config,
        metrics=latest_metric.data or {},
    )


def _prepare_eval_context(metrics: Dict[str, Any]) -> Dict[str, float]:
    """Prepare metrics context for expression evaluation"""
    context = {}
    metric_names = ["cpu_usage", "memory_usage", "disk_usage", "connections", "qps", "tps"]

    for metric_name in metric_names:
        value = _extract_metric_value(metrics, metric_name)
        if value is not None:
            context[metric_name] = value

    return context


def _extract_metric_value(metrics: Dict[str, Any], metric_name: str) -> Optional[float]:
    """Extract metric value from metrics dictionary"""
    # Try direct key first
    if metric_name in metrics:
        value = metrics[metric_name]
        return _to_float(value)

    # Common metric name mappings
    mappings = {
        "cpu_usage": ["cpu_usage_percent", "cpu_percent"],
        "memory_usage": ["memory_usage_percent", "mem_percent"],
        "disk_usage": ["disk_usage_percent", "disk_percent"],
        "connections": ["connections_active", "threads_running", "active_connections", "connection_count"],
    }

    if metric_name in mappings:
        for alt_name in mappings[metric_name]:
            if alt_name in metrics:
                return _to_float(metrics[alt_name])

    return None


def _to_float(value: Any) -> Optional[float]:
    """Convert value to float"""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            if value.endswith("%"):
                return float(value[:-1])
            return float(value)
        except ValueError:
            return None
    return None


@router.post("/{conn_id}/refresh")
async def refresh_metrics(
    conn_id: int,
    db: AsyncSession = Depends(get_db),
):
    """
    手动触发指标采集

    立即采集指定数据源的监控指标，不等待定时任务
    """
    # Verify datasource exists
    from backend.models.datasource import Datasource
    datasource = await get_alive_by_id(db, Datasource, conn_id)

    if not datasource:
        raise HTTPException(status_code=404, detail="数据源不存在")

    if not datasource.is_active:
        raise HTTPException(status_code=400, detail="数据源未激活")

    # Trigger metric collection
    try:
        if datasource.metric_source == 'integration':
            await execute_integration(conn_id)
        else:
            await metric_collector.collect_metrics_for_connection(conn_id)
        return {"success": True, "message": "指标采集已触发"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"采集失败: {str(e)}")
