from fastapi import APIRouter, Depends, Query, HTTPException, Body
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc, or_
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta

from backend.database import get_db
from backend.models.metric_snapshot import MetricSnapshot
from backend.models.inspection_config import InspectionConfig
from backend.schemas.metrics import MetricResponse
from backend.dependencies import get_current_user
from backend.utils.datetime_helper import now
from backend.services.threshold_checker import ThresholdChecker
from backend.services import metric_collector

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
    # 检查数据源是否使用集成采集
    from backend.models.datasource import Datasource
    ds_result = await db.execute(
        select(Datasource).where(Datasource.id == conn_id)
    )
    datasource = ds_result.scalar_one_or_none()

    # 如果请求 db_status 但数据源使用集成采集，则查询 integration_metric
    actual_metric_type = metric_type
    need_conversion = False
    if datasource and datasource.metric_source == 'integration' and metric_type == 'db_status':
        actual_metric_type = 'integration_metric'
        need_conversion = True

    query = select(MetricSnapshot).where(MetricSnapshot.datasource_id == conn_id)

    if actual_metric_type:
        query = query.where(MetricSnapshot.metric_type == actual_metric_type)

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

    # 如果需要转换，获取更多原始记录（每个时间戳约15个指标）
    actual_limit = limit * 15 if need_conversion else limit
    query = query.order_by(desc(MetricSnapshot.collected_at)).limit(actual_limit)
    result = await db.execute(query)
    snapshots = result.scalars().all()

    # 如果是集成指标，需要转换为前端期望的格式
    if need_conversion:
        snapshots = _convert_integration_metrics_to_db_status(snapshots)
        # 转换后再限制数量
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
        select(Datasource).where(Datasource.id == conn_id)
    )
    datasource = ds_result.scalar_one_or_none()

    # 如果请求 db_status 但数据源使用集成采集，则查询 integration_metric
    actual_metric_type = metric_type
    if datasource and datasource.metric_source == 'integration' and metric_type == 'db_status':
        actual_metric_type = 'integration_metric'

    result = await db.execute(
        select(MetricSnapshot)
        .where(
            MetricSnapshot.datasource_id == conn_id,
            MetricSnapshot.metric_type == actual_metric_type,
        )
        .order_by(desc(MetricSnapshot.collected_at))
        .limit(100 if actual_metric_type == 'integration_metric' else 1)
    )

    if actual_metric_type == 'integration_metric':
        # 获取最近的所有指标并转换
        snapshots = result.scalars().all()
        if snapshots:
            converted = _convert_integration_metrics_to_db_status(snapshots)
            return converted[0] if converted else None
        return None
    else:
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
        select(Datasource).where(Datasource.id.in_(conn_ids))
    )
    datasources = {ds.id: ds for ds in ds_result.scalars().all()}

    # 批量查询巡检配置
    config_result = await db.execute(
        select(InspectionConfig).where(InspectionConfig.datasource_id.in_(conn_ids))
    )
    configs = {c.datasource_id: c for c in config_result.scalars().all()}

    # 分类：哪些用集成采集、哪些用 db_status
    integration_ids = [cid for cid in conn_ids if datasources.get(cid) and datasources[cid].metric_source == 'integration']
    normal_ids = [cid for cid in conn_ids if cid not in integration_ids]

    latest_metrics: Dict[int, Any] = {}  # conn_id -> MetricSnapshot or None

    # 批量查询普通数据源最新 db_status（每个数据源取1条）
    if normal_ids:
        # 用子查询取每个 datasource_id 的最新一条
        from sqlalchemy import func
        subq = (
            select(
                MetricSnapshot.datasource_id,
                func.max(MetricSnapshot.collected_at).label('max_ts')
            )
            .where(
                MetricSnapshot.datasource_id.in_(normal_ids),
                MetricSnapshot.metric_type == 'db_status'
            )
            .group_by(MetricSnapshot.datasource_id)
            .subquery()
        )
        rows = await db.execute(
            select(MetricSnapshot).join(
                subq,
                (MetricSnapshot.datasource_id == subq.c.datasource_id) &
                (MetricSnapshot.collected_at == subq.c.max_ts)
            )
        )
        for snap in rows.scalars().all():
            latest_metrics[snap.datasource_id] = snap

    # 批量查询集成数据源最新 integration_metric（每个取最近100条用于转换）
    if integration_ids:
        int_rows = await db.execute(
            select(MetricSnapshot)
            .where(
                MetricSnapshot.datasource_id.in_(integration_ids),
                MetricSnapshot.metric_type == 'integration_metric'
            )
            .order_by(desc(MetricSnapshot.collected_at))
        )
        int_snaps: Dict[int, List] = {}
        for snap in int_rows.scalars().all():
            int_snaps.setdefault(snap.datasource_id, []).append(snap)
            if len(int_snaps[snap.datasource_id]) >= 100:
                continue
        for cid, snaps in int_snaps.items():
            converted = _convert_integration_metrics_to_db_status(snaps)
            latest_metrics[cid] = converted[0] if converted else None

    # 组装结果
    result = {}
    stale_threshold = 300  # 5分钟
    for cid in conn_ids:
        snap = latest_metrics.get(cid)

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
        if not snap:
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
        select(Datasource).where(Datasource.id == conn_id)
    )
    datasource = ds_result.scalar_one_or_none()

    # 确定实际的指标类型
    actual_metric_type = "db_status"
    if datasource and datasource.metric_source == 'integration':
        actual_metric_type = 'integration_metric'

    # Get latest metric
    metric_result = await db.execute(
        select(MetricSnapshot)
        .where(
            MetricSnapshot.datasource_id == conn_id,
            MetricSnapshot.metric_type == actual_metric_type,
        )
        .order_by(desc(MetricSnapshot.collected_at))
        .limit(100 if actual_metric_type == 'integration_metric' else 1)
    )

    if actual_metric_type == 'integration_metric':
        # 转换集成指标
        snapshots = metric_result.scalars().all()
        if snapshots:
            converted = _convert_integration_metrics_to_db_status(snapshots)
            latest_metric = converted[0] if converted else None
        else:
            latest_metric = None
    else:
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


def _convert_integration_metrics_to_db_status(snapshots: List[MetricSnapshot]) -> List[MetricSnapshot]:
    """
    将集成采集的指标转换为 db_status 格式

    集成指标格式: 每个 snapshot 包含一个指标
    {
        "metric_name": "cpu_usage",
        "value": 0.82,
        "labels": {...}
    }

    db_status 格式: 每个 snapshot 包含所有指标
    {
        "cpu_usage": 0.82,
        "memory_usage": 45.2,
        ...
    }
    """
    # 按时间戳分组
    grouped = {}
    for snapshot in snapshots:
        timestamp = snapshot.collected_at
        if timestamp not in grouped:
            grouped[timestamp] = {
                'datasource_id': snapshot.datasource_id,
                'metric_type': 'db_status',
                'collected_at': timestamp,
                'data': {}
            }

        # 提取指标名和值
        metric_name = snapshot.data.get('metric_name')
        metric_value = snapshot.data.get('value')
        if metric_name and metric_value is not None:
            grouped[timestamp]['data'][metric_name] = metric_value

    # 转换为 MetricSnapshot 对象
    result = []
    for timestamp in sorted(grouped.keys(), reverse=True):
        item = grouped[timestamp]
        snapshot = MetricSnapshot(
            datasource_id=item['datasource_id'],
            metric_type=item['metric_type'],
            collected_at=item['collected_at'],
            data=item['data']
        )
        # 设置 ID（用于响应）
        snapshot.id = hash(timestamp)
        result.append(snapshot)

    return result


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
    result = await db.execute(
        select(Datasource).where(Datasource.id == conn_id)
    )
    datasource = result.scalar_one_or_none()

    if not datasource:
        raise HTTPException(status_code=404, detail="数据源不存在")

    if not datasource.is_active:
        raise HTTPException(status_code=400, detail="数据源未激活")

    # Trigger metric collection
    try:
        await metric_collector.collect_metrics_for_connection(conn_id)
        return {"success": True, "message": "指标采集已触发"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"采集失败: {str(e)}")
