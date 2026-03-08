"""
Guardian API Router
AI 守护系统 API 端点
"""
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, and_, desc, func
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_db
from backend.models.baseline import MetricBaseline
from backend.models.datasource import Datasource
from backend.models.anomaly import Anomaly
from backend.services.baseline_learner import BaselineLearner

router = APIRouter(prefix="/api/guardian", tags=["guardian"])


@router.get("/baselines/{datasource_id}")
async def get_baselines(
    datasource_id: int,
    db: AsyncSession = Depends(get_db)
):
    """获取数据源的基线数据"""
    result = await db.execute(
        select(MetricBaseline).where(
            MetricBaseline.datasource_id == datasource_id
        )
    )
    baselines = result.scalars().all()

    return {
        "datasource_id": datasource_id,
        "baselines": [
            {
                "metric_name": b.metric_name,
                "time_window": b.time_window,
                "mean": b.mean,
                "stddev": b.stddev,
                "p50": b.p50,
                "p95": b.p95,
                "p99": b.p99,
                "upper_threshold": b.upper_threshold,
                "lower_threshold": b.lower_threshold,
                "confidence_score": b.confidence_score,
                "sample_count": b.sample_count,
                "last_updated": b.last_updated.isoformat() if b.last_updated else None
            }
            for b in baselines
        ]
    }


@router.get("/importance/{datasource_id}")
async def get_importance(
    datasource_id: int,
    db: AsyncSession = Depends(get_db)
):
    """获取数据源的重要性配置"""
    result = await db.execute(
        select(Datasource).where(Datasource.id == datasource_id)
    )
    datasource = result.scalar_one_or_none()

    if not datasource:
        raise HTTPException(status_code=404, detail="Datasource not found")

    importance_levels = {
        'core': {'tier': 'CRITICAL', 'label': '核心系统'},
        'production': {'tier': 'IMPORTANT', 'label': '生产系统'},
        'development': {'tier': 'NORMAL', 'label': '开发测试'},
        'temporary': {'tier': 'NORMAL', 'label': '临时'}
    }

    level_info = importance_levels.get(datasource.importance_level, importance_levels['production'])

    return {
        "datasource_id": datasource_id,
        "importance_level": datasource.importance_level,
        "importance_tier": level_info['tier'],
        "importance_label": level_info['label'],
        "monitoring_interval": datasource.monitoring_interval,
        "strategy": {
            "collection_interval": datasource.monitoring_interval,
            "anomaly_detection_mode": "realtime" if datasource.importance_level == 'core' else "neartime"
        }
    }


@router.get("/anomalies/{datasource_id}")
async def get_anomalies(
    datasource_id: int,
    status: Optional[str] = None,
    limit: int = 50,
    db: AsyncSession = Depends(get_db)
):
    """获取数据源的异常记录"""
    query = select(Anomaly).where(Anomaly.datasource_id == datasource_id)

    if status:
        query = query.where(Anomaly.status == status)

    query = query.order_by(desc(Anomaly.detected_at)).limit(limit)

    result = await db.execute(query)
    anomalies = result.scalars().all()

    return {
        "datasource_id": datasource_id,
        "count": len(anomalies),
        "anomalies": [
            {
                "id": a.id,
                "detected_at": a.detected_at.isoformat() if a.detected_at else None,
                "anomaly_type": a.anomaly_type,
                "severity": a.severity,
                "confidence": a.confidence,
                "baseline_value": a.baseline_value,
                "current_value": a.current_value,
                "deviation_percent": a.deviation_percent,
                "status": a.status,
                "was_auto_fixed": a.was_auto_fixed,
                "resolved_at": a.resolved_at.isoformat() if a.resolved_at else None,
                "ai_diagnosis": a.ai_diagnosis,
                "root_cause": a.root_cause,
                "recommended_actions": a.recommended_actions
            }
            for a in anomalies
        ]
    }


@router.get("/anomalies/{datasource_id}/{anomaly_id}")
async def get_anomaly_detail(
    datasource_id: int,
    anomaly_id: int,
    db: AsyncSession = Depends(get_db)
):
    """获取单个异常的详细信息"""
    result = await db.execute(
        select(Anomaly).where(
            and_(
                Anomaly.id == anomaly_id,
                Anomaly.datasource_id == datasource_id
            )
        )
    )
    anomaly = result.scalar_one_or_none()

    if not anomaly:
        raise HTTPException(status_code=404, detail="Anomaly not found")

    return {
        "id": anomaly.id,
        "datasource_id": anomaly.datasource_id,
        "detected_at": anomaly.detected_at.isoformat() if anomaly.detected_at else None,
        "anomaly_type": anomaly.anomaly_type,
        "affected_metrics": anomaly.affected_metrics,
        "severity": anomaly.severity,
        "confidence": anomaly.confidence,
        "baseline_value": anomaly.baseline_value,
        "current_value": anomaly.current_value,
        "deviation_percent": anomaly.deviation_percent,
        "context_snapshot": anomaly.context_snapshot,
        "ai_diagnosis": anomaly.ai_diagnosis,
        "root_cause": anomaly.root_cause,
        "recommended_actions": anomaly.recommended_actions,
        "status": anomaly.status,
        "resolved_at": anomaly.resolved_at.isoformat() if anomaly.resolved_at else None,
        "resolution_actions": anomaly.resolution_actions,
        "was_auto_fixed": anomaly.was_auto_fixed
    }


@router.post("/baselines/{datasource_id}/recalculate")
async def recalculate_baselines(
    datasource_id: int,
    db: AsyncSession = Depends(get_db)
):
    """手动触发基线重新计算"""
    learner = BaselineLearner()
    await learner.learn_baselines(db, datasource_id)
    await db.commit()

    return {"message": "Baselines recalculated successfully"}


@router.post("/anomalies/{datasource_id}/{anomaly_id}/diagnose")
async def trigger_diagnosis(
    datasource_id: int,
    anomaly_id: int,
    db: AsyncSession = Depends(get_db)
):
    """手动触发异常的 AI 诊断"""
    # 验证异常存在
    result = await db.execute(
        select(Anomaly).where(
            and_(
                Anomaly.id == anomaly_id,
                Anomaly.datasource_id == datasource_id
            )
        )
    )
    anomaly = result.scalar_one_or_none()

    if not anomaly:
        raise HTTPException(status_code=404, detail="Anomaly not found")

    # 触发诊断
    from backend.services.proactive_diagnosis import ProactiveDiagnosisService
    diagnosis_service = ProactiveDiagnosisService()

    result = await diagnosis_service.diagnose_anomaly(db, anomaly_id, auto_fix=False)

    if result.get("success"):
        return {
            "success": True,
            "message": "AI diagnosis completed",
            "diagnosis": result.get("diagnosis"),
            "root_cause": result.get("root_cause"),
            "recommended_actions": result.get("recommended_actions")
        }
    else:
        raise HTTPException(status_code=500, detail=result.get("error", "Diagnosis failed"))


@router.get("/dashboard/overview")
async def get_dashboard_overview(db: AsyncSession = Depends(get_db)):
    """获取守护系统总览"""
    # 统计各重要性级别的数据源数量
    result = await db.execute(select(Datasource).where(Datasource.is_active == True))
    datasources = result.scalars().all()

    level_counts = {"core": 0, "production": 0, "development": 0, "temporary": 0}
    for ds in datasources:
        level = ds.importance_level or 'production'
        level_counts[level] = level_counts.get(level, 0) + 1

    # 统计异常数量
    result = await db.execute(
        select(Anomaly).where(Anomaly.status == 'detected')
    )
    active_anomalies = result.scalars().all()

    severity_counts = {"CRITICAL": 0, "WARNING": 0, "INFO": 0}
    for anomaly in active_anomalies:
        severity_counts[anomaly.severity] = severity_counts.get(anomaly.severity, 0) + 1

    return {
        "datasources": {
            "total": len(datasources),
            "by_level": level_counts
        },
        "anomalies": {
            "active": len(active_anomalies),
            "by_severity": severity_counts
        }
    }
