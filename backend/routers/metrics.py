from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta

from backend.database import get_db
from backend.models.metric_snapshot import MetricSnapshot
from backend.models.inspection_config import InspectionConfig
from backend.schemas.metrics import MetricResponse
from backend.dependencies import get_current_user
from backend.utils.datetime_helper import now
from backend.services.threshold_checker import ThresholdChecker

router = APIRouter(prefix="/api/metrics", tags=["metrics"], dependencies=[Depends(get_current_user)])


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
    query = select(MetricSnapshot).where(MetricSnapshot.datasource_id == conn_id)

    if metric_type:
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
    return result.scalars().all()


@router.get("/{conn_id}/latest", response_model=Optional[MetricResponse])
async def get_latest_metric(
    conn_id: int,
    metric_type: str = "db_status",
    db: AsyncSession = Depends(get_db),
):
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
    # Get latest metric
    metric_result = await db.execute(
        select(MetricSnapshot)
        .where(
            MetricSnapshot.datasource_id == conn_id,
            MetricSnapshot.metric_type == "db_status",
        )
        .order_by(desc(MetricSnapshot.collected_at))
        .limit(1)
    )
    latest_metric = metric_result.scalar_one_or_none()

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
        "connections": ["connections_active", "active_connections", "connection_count", "threads_connected"],
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
