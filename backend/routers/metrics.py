from fastapi import APIRouter, Depends, Query, HTTPException, Body
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta

from backend.database import get_db
from backend.models.metric_snapshot import MetricSnapshot
from backend.models.soft_delete import alive_filter, get_alive_by_id
from backend.models.inspection_config import InspectionConfig
from backend.schemas.metrics import MetricResponse
from backend.dependencies import get_current_user
from backend.utils.datetime_helper import now, normalize_local_datetime
from backend.services import metric_collector
from backend.services.integration_scheduler import execute_integration

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
    if error_message:
        violation["detail"] = error_message

    return {
        "healthy": False,
        "status": "critical",
        "violations": [violation],
        "message": message,
    }


async def _get_db_status_snapshots(
    db: AsyncSession,
    conn_id: int,
    limit: int,
    datasource=None,
) -> List[MetricSnapshot]:
    result = await db.execute(
        select(MetricSnapshot)
        .where(
            MetricSnapshot.datasource_id == conn_id,
            MetricSnapshot.metric_type == 'db_status',
        )
        .order_by(desc(MetricSnapshot.collected_at))
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

    query = select(MetricSnapshot).where(MetricSnapshot.datasource_id == conn_id)

    if metric_type and metric_type != 'db_status':
        query = query.where(MetricSnapshot.metric_type == metric_type)

    # 时间范围过滤
    if minutes:
        # 使用 minutes 参数
        start = now() - timedelta(minutes=minutes)
        query = query.where(MetricSnapshot.collected_at >= start)
    elif start_time or end_time:
        # 使用 start_time/end_time 参数
        if start_time:
            query = query.where(MetricSnapshot.collected_at >= start_time)
        if end_time:
            query = query.where(MetricSnapshot.collected_at <= end_time)

    query = query.order_by(desc(MetricSnapshot.collected_at)).limit(limit)
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
        select(MetricSnapshot)
        .where(
            MetricSnapshot.datasource_id == conn_id,
            MetricSnapshot.metric_type == metric_type,
        )
        .order_by(desc(MetricSnapshot.collected_at))
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
    datasources = {ds.id: ds for ds in ds_result.scalars().all()}

    # 批量查询巡检配置
    config_result = await db.execute(
        select(InspectionConfig).where(InspectionConfig.datasource_id.in_(conn_ids))
    )
    configs = {c.datasource_id: c for c in config_result.scalars().all()}

    latest_metrics: Dict[int, Any] = {}  # conn_id -> MetricSnapshot or None

    for cid in conn_ids:
        latest_snaps = await _get_db_status_snapshots(db, cid, 1, datasources.get(cid))
        latest_metrics[cid] = latest_snaps[0] if latest_snaps else None

    # 组装结果
    result = {}
    stale_threshold = 300  # 5分钟
    for cid in conn_ids:
        snap = latest_metrics.get(cid)
        datasource = datasources.get(cid)

        # --- 构建 metric 部分 ---
        if snap:
            metric_data = {
                "id": snap.id,
                "datasource_id": snap.datasource_id,
                "metric_type": snap.metric_type,
                "data": snap.data,
                "collected_at": snap.collected_at.isoformat(),
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
                if not config or not config.threshold_rules:
                    health = {"healthy": True, "status": "healthy", "violations": [], "message": "正常（未配置阈值）"}
                else:
                    metrics_data = snap.data or {}
                    violations = []
                    if "custom_expression" in config.threshold_rules:
                        custom_rule = config.threshold_rules["custom_expression"]
                        expression = custom_rule.get("expression", "")
                        eval_context = _prepare_eval_context(metrics_data)
                        try:
                            if eval(expression, {"__builtins__": {}}, eval_context):
                                violations.append({"type": "custom_expression", "expression": expression, "metrics": eval_context})
                        except Exception:
                            pass
                    else:
                        for metric_name, rule in config.threshold_rules.items():
                            threshold = rule.get("threshold")
                            if threshold is None:
                                continue
                            current_value = _extract_metric_value(metrics_data, metric_name)
                            if current_value is not None and current_value > threshold:
                                violations.append({"type": "threshold", "metric": metric_name, "value": current_value, "threshold": threshold})
                    if not violations:
                        health = {"healthy": True, "status": "healthy", "violations": [], "message": "正常"}
                    else:
                        health = {"healthy": False, "status": "critical", "violations": violations, "message": f"检测到 {len(violations)} 个指标异常"}

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

    if not config or not config.threshold_rules:
        # No threshold rules configured, consider healthy
        return {
            "healthy": True,
            "status": "healthy",
            "violations": [],
            "message": "正常（未配置阈值）"
        }

    # Check thresholds using ThresholdChecker logic
    metrics = latest_metric.data or {}
    violations = []

    # Check custom expression if configured
    if "custom_expression" in config.threshold_rules:
        custom_rule = config.threshold_rules["custom_expression"]
        expression = custom_rule.get("expression", "")

        # Prepare eval context
        eval_context = _prepare_eval_context(metrics)

        # Evaluate expression
        try:
            is_violated = eval(expression, {"__builtins__": {}}, eval_context)
            if is_violated:
                violations.append({
                    "type": "custom_expression",
                    "expression": expression,
                    "metrics": eval_context
                })
        except Exception:
            pass
    else:
        # Check simple threshold rules
        for metric_name, rule in config.threshold_rules.items():
            threshold = rule.get("threshold")
            if threshold is None:
                continue

            current_value = _extract_metric_value(metrics, metric_name)
            if current_value is not None and current_value > threshold:
                violations.append({
                    "type": "threshold",
                    "metric": metric_name,
                    "value": current_value,
                    "threshold": threshold
                })

    # Determine status based on violations
    if not violations:
        return {
            "healthy": True,
            "status": "healthy",
            "violations": [],
            "message": "正常"
        }

    # Has violations - determine severity
    # For now, any violation is considered critical
    return {
        "healthy": False,
        "status": "critical",
        "violations": violations,
        "message": f"检测到 {len(violations)} 个指标异常"
    }


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
