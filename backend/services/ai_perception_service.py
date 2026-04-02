"""
AI Perception Service - Continuous health monitoring with AI-based anomaly detection

This service runs in the background and:
1. Collects metrics for all monitored datasources
2. Compares against learned baselines
3. Detects anomalies using AI analysis
4. Pushes proactive insights to WebSocket clients
5. Triggers auto-diagnosis when critical anomalies are found
"""
import asyncio
import logging
import json
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List
from collections import defaultdict

from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import async_session
from backend.models.datasource import Datasource
from backend.models.soft_delete import alive_filter
from backend.models.metric_snapshot import MetricSnapshot
from backend.services.ai_agent import get_ai_client
from backend.agent.prompts import (
    INFORMATIONAL_PROMPT,
)
from backend.utils.datetime_helper import now as get_now
from backend.config import get_settings

logger = logging.getLogger(__name__)

# Global perception state
_perception_running = False
_perception_subscribers: Dict[int, List[asyncio.Queue]] = defaultdict(list)

# Baselines cache: {datasource_id: {metric_name: {"avg": float, "std": float, "samples": int}}}
_baselines: Dict[int, Dict[str, Dict[str, Any]]] = defaultdict(dict)

# Health scores cache: {datasource_id: {"score": float, "status": str, "updated_at": datetime}}
_health_scores: Dict[int, Dict[str, Any]] = {}

# Recent anomalies: {datasource_id: [anomaly_dict]}
_recent_anomalies: Dict[int, List[Dict[str, Any]]] = defaultdict(list)


def subscribe(user_id: int) -> asyncio.Queue:
    """Subscribe to proactive insights for a user."""
    queue = asyncio.Queue(maxsize=50)
    _perception_subscribers.setdefault(user_id, []).append(queue)
    return queue


def unsubscribe(user_id: int, queue: asyncio.Queue):
    """Unsubscribe from proactive insights."""
    if user_id in _perception_subscribers:
        try:
            _perception_subscribers[user_id].remove(queue)
        except ValueError:
            pass
        if not _perception_subscribers[user_id]:
            del _perception_subscribers[user_id]


async def _push_insight_to_users(insight: Dict[str, Any]):
    """Push proactive insight to all subscribed users."""
    for user_id, queues in list(_perception_subscribers.items()):
        for queue in queues:
            try:
                queue.put_nowait(insight)
            except asyncio.QueueFull:
                pass


async def _get_recent_metrics(db: AsyncSession, datasource_id: int, minutes: int = 60) -> Dict[str, Any]:
    """Get most recent metrics for a datasource."""
    cutoff = get_now() - timedelta(minutes=minutes)
    result = await db.execute(
        select(MetricSnapshot)
        .where(
            MetricSnapshot.datasource_id == datasource_id,
            MetricSnapshot.collected_at >= cutoff
        )
        .order_by(MetricSnapshot.collected_at.desc())
    )
    snapshots = result.scalars().all()

    latest_metrics = {}
    for snapshot in snapshots:
        if snapshot.metric_type not in latest_metrics:
            latest_metrics[snapshot.metric_type] = snapshot.data

    return latest_metrics


async def _get_historical_metrics(
    db: AsyncSession,
    datasource_id: int,
    metric_type: str,
    days: int = 7
) -> List[Dict[str, Any]]:
    """Get historical metrics for baseline calculation."""
    cutoff = get_now() - timedelta(days=days)
    result = await db.execute(
        select(MetricSnapshot)
        .where(
            MetricSnapshot.datasource_id == datasource_id,
            MetricSnapshot.metric_type == metric_type,
            MetricSnapshot.collected_at >= cutoff
        )
        .order_by(MetricSnapshot.collected_at.asc())
    )
    return [
        {"data": s.data, "collected_at": s.collected_at}
        for s in result.scalars().all()
    ]


def _calculate_baseline(metrics_history: List[Dict[str, Any]], metric_name: str) -> Optional[Dict[str, float]]:
    """Calculate baseline (mean + std) for a specific metric from historical data."""
    values = []
    for record in metrics_history:
        data = record.get("data", {})
        # Try direct key, then nested
        value = data.get(metric_name)
        if value is None:
            # Try nested like data.cpu.usage_percent
            if "." in metric_name:
                parts = metric_name.split(".")
                current = data
                for part in parts:
                    if isinstance(current, dict) and part in current:
                        current = current[part]
                    else:
                        current = None
                        break
                value = current
        if value is not None:
            try:
                values.append(float(value))
            except (ValueError, TypeError):
                pass

    if len(values) < 10:
        return None

    avg = sum(values) / len(values)
    variance = sum((v - avg) ** 2 for v in values) / len(values)
    std = variance ** 0.5
    return {"avg": avg, "std": std, "samples": len(values)}


def _detect_anomalies(
    datasource_id: int,
    current_metrics: Dict[str, Any],
    baselines: Dict[str, Dict[str, float]]
) -> List[Dict[str, Any]]:
    """Detect anomalies by comparing current metrics against baselines."""
    anomalies = []

    for metric_name, baseline in baselines.items():
        # Extract current value
        current_value = None
        for metric_type_data in current_metrics.values():
            if isinstance(metric_type_data, dict):
                if metric_name in metric_type_data:
                    current_value = metric_type_data[metric_name]
                    break
                # Try nested
                if "." in metric_name:
                    parts = metric_name.split(".")
                    current = metric_type_data
                    for part in parts:
                        if isinstance(current, dict) and part in current:
                            current = current[part]
                        else:
                            current = None
                            break
                    if current is not None:
                        current_value = current
                        break

        if current_value is None:
            continue

        try:
            current_value = float(current_value)
        except (ValueError, TypeError):
            continue

        avg = baseline["avg"]
        std = baseline["std"]

        if std == 0:
            continue

        # Z-score based anomaly detection
        z_score = abs(current_value - avg) / std

        if z_score >= 2.0:  # Significant deviation
            severity = "critical" if z_score >= 3.0 else "high" if z_score >= 2.5 else "medium"
            deviation_pct = ((current_value - avg) / avg * 100) if avg != 0 else 0

            anomalies.append({
                "metric_name": metric_name,
                "current_value": round(current_value, 2),
                "baseline_avg": round(avg, 2),
                "baseline_std": round(std, 2),
                "z_score": round(z_score, 2),
                "deviation_pct": round(deviation_pct, 1),
                "severity": severity,
            })

    # Sort by severity
    severity_order = {"critical": 0, "high": 1, "medium": 2}
    anomalies.sort(key=lambda x: severity_order.get(x["severity"], 3))

    return anomalies


def _calculate_health_score(anomalies: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Calculate overall health score from anomalies."""
    if not anomalies:
        return {"score": 100, "status": "healthy"}

    max_z = max(a["z_score"] for a in anomalies)

    if max_z >= 3.0:
        score = max(0, 100 - max_z * 20)
        status = "critical"
    elif max_z >= 2.5:
        score = max(0, 100 - max_z * 15)
        status = "degraded"
    elif max_z >= 2.0:
        score = max(0, 100 - max_z * 10)
        status = "warning"
    else:
        score = max(0, 100 - max_z * 5)
        status = "warning"

    return {"score": round(score, 1), "status": status}


async def _ai_analyze_anomalies(
    datasource_name: str,
    db_type: str,
    anomalies: List[Dict[str, Any]],
    current_metrics: Dict[str, Any]
) -> str:
    """Use AI to generate a natural language analysis of anomalies."""
    if not anomalies:
        return "所有指标正常，未检测到异常波动。"

    settings = get_settings()
    client = get_ai_client()
    if not client:
        # Fallback to rule-based summary
        critical = [a for a in anomalies if a["severity"] == "critical"]
        high = [a for a in anomalies if a["severity"] == "high"]
        medium = [a for a in anomalies if a["severity"] == "medium"]

        summary_parts = []
        if critical:
            summary_parts.append(f"严重异常：{', '.join(a['metric_name'] for a in critical)}")
        if high:
            summary_parts.append(f"高风险：{', '.join(a['metric_name'] for a in high)}")
        if medium:
            summary_parts.append(f"需关注：{', '.join(a['metric_name'] for a in medium)}")
        return "；".join(summary_parts) if summary_parts else "检测到轻微异常波动。"

    # Build context for AI analysis
    anomaly_details = "\n".join([
        f"- {a['metric_name']}: 当前值 {a['current_value']}, 基线均值 {a['baseline_avg']}, 偏离 {a['deviation_pct']:+.1f}%, 严重程度: {a['severity']}"
        for a in anomalies[:10]
    ])

    prompt = f"""你是一个数据库健康分析助手。请简洁分析以下 {db_type} 数据库 ({datasource_name}) 的异常指标，用 2-3 句话给出专业判断和建议。

异常指标：
{anomaly_details}

请用中文回答，格式：问题描述 + 原因推测 + 建议行动。例如："CPU 使用率突增至 95%，远超基线 60%，可能存在慢查询堆积或热点竞争，建议检查活跃连接数和慢查询列表。"

回答："""

    try:
        if client.protocol == "anthropic":
            response = await client.client.messages.create(
                model=client.model_name,
                max_tokens=300,
                messages=[{"role": "user", "content": prompt}]
            )
            return response.content[0].text.strip()
        else:
            response = await client.client.chat.completions.create(
                model=client.model_name,
                max_tokens=300,
                messages=[{"role": "user", "content": prompt}]
            )
            return response.choices[0].message.content.strip()
    except Exception as e:
        logger.warning(f"AI analysis failed, using fallback: {e}")
        return f"检测到 {len(anomalies)} 项指标异常，建议进一步诊断。"


async def _run_perception_cycle():
    """Run one perception cycle: analyze all datasources."""
    global _baselines, _health_scores, _recent_anomalies

    async with async_session() as db:
        # Get all active datasources
        result = await db.execute(
            select(Datasource).where(Datasource.is_active == True, alive_filter(Datasource))
        )
        datasources = result.scalars().all()

        for ds in datasources:
            try:
                # Get recent metrics
                current_metrics = await _get_recent_metrics(db, ds.id, minutes=30)
                if not current_metrics:
                    continue

                # Get historical data for baseline
                historical = await _get_historical_metrics(db, ds.id, "db_status", days=7)

                # Update baselines if needed
                if ds.id not in _baselines or len(historical) > 100:
                    # Key metrics to track
                    key_metrics = ["cpu_usage", "memory_usage", "disk_usage", "connections",
                                   "qps", "tps", "cache_hit", "threads_running"]
                    for metric_name in key_metrics:
                        baseline = _calculate_baseline(historical, metric_name)
                        if baseline:
                            _baselines[ds.id][metric_name] = baseline

                # Detect anomalies
                baselines = _baselines.get(ds.id, {})
                anomalies = _detect_anomalies(ds.id, current_metrics, baselines)

                # Calculate health score
                health = _calculate_health_score(anomalies)
                _health_scores[ds.id] = {
                    "score": health["score"],
                    "status": health["status"],
                    "updated_at": get_now().isoformat()
                }

                # AI-powered analysis
                ai_summary = await _ai_analyze_anomalies(ds.name, ds.db_type, anomalies, current_metrics)

                # Update recent anomalies
                if anomalies:
                    _recent_anomalies[ds.id] = anomalies[:5]
                    # Push insight to users
                    insight = {
                        "type": "proactive_insight",
                        "datasource_id": ds.id,
                        "datasource_name": ds.name,
                        "datasource_type": ds.db_type,
                        "severity": anomalies[0]["severity"],
                        "health_score": health["score"],
                        "health_status": health["status"],
                        "anomaly_count": len(anomalies),
                        "top_anomalies": anomalies[:3],
                        "ai_summary": ai_summary,
                        "timestamp": get_now().isoformat(),
                    }
                    await _push_insight_to_users(insight)
                    logger.info(
                        f"Proactive insight for datasource {ds.id} ({ds.name}): "
                        f"score={health['score']}, anomalies={len(anomalies)}, top={ai_summary[:50]}"
                    )
            except Exception as e:
                logger.error(f"Perception cycle error for datasource {ds.id}: {e}", exc_info=True)


async def start_perception_service(interval_minutes: int = 5):
    """Start the AI perception service background loop."""
    global _perception_running
    _perception_running = True
    logger.info(f"AI Perception Service started (interval: {interval_minutes}m)")

    while _perception_running:
        try:
            await _run_perception_cycle()
        except Exception as e:
            logger.error(f"Perception cycle error: {e}", exc_info=True)

        await asyncio.sleep(interval_minutes * 60)


async def stop_perception_service():
    """Stop the AI perception service."""
    global _perception_running
    _perception_running = False
    logger.info("AI Perception Service stopped")


def get_perception_status() -> Dict[str, Any]:
    """Get current perception status for all datasources."""
    return {
        "health_scores": _health_scores.copy(),
        "recent_anomalies": {k: v.copy() for k, v in _recent_anomalies.items()},
        "baselines_loaded": len(_baselines),
    }


def get_datasource_health(datasource_id: int) -> Optional[Dict[str, Any]]:
    """Get health info for a specific datasource."""
    health = _health_scores.get(datasource_id)
    anomalies = _recent_anomalies.get(datasource_id, [])

    if health:
        return {
            "datasource_id": datasource_id,
            **health,
            "anomalies": anomalies,
        }
    return None