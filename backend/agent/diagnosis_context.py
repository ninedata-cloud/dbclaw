from __future__ import annotations

from typing import Any

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.alert_message import AlertMessage
from backend.models.datasource import Datasource
from backend.models.diagnosis_conclusion import DiagnosisConclusion
from backend.models.host import Host
from backend.models.datasource_metric import DatasourceMetric
from backend.models.report import Report
from backend.models.soft_delete import alive_filter


def _safe_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _iter_flat_items(data: Any, prefix: str = "", depth: int = 0):
    if depth > 2 or not isinstance(data, dict):
        return
    for key, value in data.items():
        full_key = f"{prefix}.{key}" if prefix else str(key)
        if isinstance(value, dict):
            yield from _iter_flat_items(value, full_key, depth + 1)
        else:
            yield full_key.lower(), value


def extract_metric_signals(metric_type: str, data: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not isinstance(data, dict):
        return []

    signals: list[dict[str, Any]] = []
    flat_items = dict(_iter_flat_items(data))

    def add_signal(source: str, label: str, value: Any, severity: str, reason: str) -> None:
        signals.append({
            "source": source,
            "label": label,
            "value": value,
            "severity": severity,
            "reason": reason,
        })

    connection_ratio = None
    current_connections = _safe_float(flat_items.get("current_connections") or flat_items.get("threads_connected"))
    max_connections = _safe_float(flat_items.get("max_connections"))
    if current_connections is not None and max_connections and max_connections > 0:
        connection_ratio = current_connections / max_connections * 100
    else:
        connection_ratio = _safe_float(flat_items.get("connection_usage_pct") or flat_items.get("connections_used_pct"))
    if connection_ratio is not None and connection_ratio >= 75:
        severity = "high" if connection_ratio >= 90 else "medium"
        add_signal(metric_type, "连接使用率", f"{connection_ratio:.1f}%", severity, "连接数接近上限，可能引发连接失败或排队")

    cpu_usage = _safe_float(flat_items.get("cpu_usage") or flat_items.get("cpu.usage") or flat_items.get("cpu.percent"))
    if cpu_usage is not None and cpu_usage >= 70:
        severity = "high" if cpu_usage >= 85 else "medium"
        add_signal(metric_type, "CPU 使用率", f"{cpu_usage:.1f}%", severity, "CPU 持续偏高，可能存在热点 SQL、并发过高或主机资源瓶颈")

    load_avg = _safe_float(flat_items.get("load_avg") or flat_items.get("load_average") or flat_items.get("load.1m"))
    cpu_cores = _safe_float(flat_items.get("cpu_cores") or flat_items.get("cpu.cores"))
    if load_avg is not None and cpu_cores and cpu_cores > 0 and load_avg >= cpu_cores * 0.8:
        severity = "high" if load_avg >= cpu_cores * 1.2 else "medium"
        add_signal(metric_type, "系统负载", f"{load_avg:.2f}/{int(cpu_cores)} cores", severity, "系统负载偏高，存在 CPU 或 I/O 等待压力")

    memory_usage = _safe_float(flat_items.get("memory_usage") or flat_items.get("memory_usage_pct") or flat_items.get("memory.percent"))
    if memory_usage is not None and memory_usage >= 80:
        severity = "high" if memory_usage >= 90 else "medium"
        add_signal(metric_type, "内存使用率", f"{memory_usage:.1f}%", severity, "主机内存紧张，可能触发换页或影响缓存命中")

    swap_usage = _safe_float(flat_items.get("swap_usage") or flat_items.get("swap_used_pct") or flat_items.get("swap.percent"))
    if swap_usage is not None and swap_usage > 0:
        severity = "high" if swap_usage >= 20 else "medium"
        add_signal(metric_type, "Swap 使用率", f"{swap_usage:.1f}%", severity, "系统已经使用交换分区，数据库响应可能显著抖动")

    iowait = _safe_float(flat_items.get("iowait") or flat_items.get("cpu.iowait"))
    if iowait is not None and iowait >= 10:
        severity = "high" if iowait >= 20 else "medium"
        add_signal(metric_type, "I/O Wait", f"{iowait:.1f}%", severity, "I/O 等待偏高，可能存在磁盘延迟或刷盘压力")

    disk_usage = _safe_float(flat_items.get("disk_usage") or flat_items.get("disk_usage_pct") or flat_items.get("filesystem.usage_pct"))
    if disk_usage is not None and disk_usage >= 75:
        severity = "high" if disk_usage >= 90 else "medium"
        add_signal(metric_type, "磁盘使用率", f"{disk_usage:.1f}%", severity, "磁盘空间紧张，需检查数据目录、日志和增长趋势")

    cache_hit_rate = _safe_float(flat_items.get("cache_hit_rate") or flat_items.get("buffer_pool_hit_rate") or flat_items.get("hit_rate"))
    if cache_hit_rate is not None and cache_hit_rate <= 95:
        severity = "high" if cache_hit_rate <= 90 else "medium"
        add_signal(metric_type, "缓存命中率", f"{cache_hit_rate:.1f}%", severity, "缓存命中率偏低，可能有内存不足或访问模式不合理")

    slow_queries = _safe_float(flat_items.get("slow_queries"))
    if slow_queries is not None and slow_queries > 0:
        severity = "medium" if slow_queries >= 10 else "info"
        add_signal(metric_type, "慢查询数量", int(slow_queries), severity, "近期出现慢查询，建议结合 Top SQL 和执行计划继续下钻")

    replication_lag = _safe_float(flat_items.get("replication_lag") or flat_items.get("lag_seconds") or flat_items.get("seconds_behind_master"))
    if replication_lag is not None and replication_lag > 0:
        severity = "high" if replication_lag >= 60 else "medium"
        add_signal(metric_type, "复制延迟", f"{replication_lag:.0f}s", severity, "复制延迟异常，需检查上游写入压力、网络和备库负载")

    lock_waits = _safe_float(flat_items.get("innodb_row_lock_waits") or flat_items.get("lock_waits") or flat_items.get("blocked_sessions"))
    if lock_waits is not None and lock_waits > 0:
        severity = "high" if lock_waits >= 10 else "medium"
        add_signal(metric_type, "锁等待", int(lock_waits), severity, "检测到锁等待或阻塞，需进一步分析会话和事务")

    return signals[:8]


def build_focus_areas(
    issue_category: str | None,
    abnormal_signals: list[dict[str, Any]],
    active_alerts: list[dict[str, Any]],
) -> list[str]:
    focus_areas: list[str] = []
    category_focus = {
        "performance": ["先看整体负载与连接压力", "聚焦慢 SQL / 执行计划 / 锁等待", "结合主机 CPU、内存、I/O 判断瓶颈层"],
        "connectivity": ["核对连接数与认证错误", "检查主机网络和监听状态", "确认连接池或客户端超时设置"],
        "locking": ["优先检查阻塞链和长事务", "定位持锁会话与被阻塞 SQL", "评估是否存在热点表或事务顺序问题"],
        "replication": ["确认复制状态和延迟区间", "检查主库写入压力与备库回放能力", "关注网络抖动和日志积压"],
        "capacity": ["检查数据库/表增长与磁盘空间", "确认日志或归档占用", "评估短期扩容或清理窗口"],
        "resource": ["优先对齐数据库指标与主机资源", "检查 CPU、内存、Swap、I/O Wait", "定位是否由少量热点 SQL 拉高资源"],
        "sql": ["先锁定最慢或最重的 SQL", "获取执行计划并判断索引/扫描问题", "结合统计信息和返回行数评估优化收益"],
        "configuration": ["核对关键参数是否与负载匹配", "关注连接、缓存、日志、并行度参数", "判断是参数问题还是业务流量变化"],
        "error": ["先明确错误码和出现时段", "结合告警与主机资源还原触发条件", "确认是否为重复性故障或已知问题"],
        "general": ["先看整体健康摘要", "依据异常信号选择数据库或主机侧下钻", "尽量先排除高风险根因"],
    }
    focus_areas.extend(category_focus.get(issue_category or "general", category_focus["general"]))

    for signal in abnormal_signals[:3]:
        focus_areas.append(f"关注 {signal['label']}：{signal['reason']}")
    for alert in active_alerts[:2]:
        focus_areas.append(f"关注告警 {alert['title']}（{alert['severity']}）")

    seen: set[str] = set()
    deduped: list[str] = []
    for item in focus_areas:
        if item in seen:
            continue
        seen.add(item)
        deduped.append(item)
    return deduped[:6]


def render_diagnostic_brief_for_prompt(brief: dict[str, Any]) -> str:
    lines = ["System pre-diagnosis brief:"]
    datasource = brief.get("datasource") or {}
    if datasource:
        lines.append(
            f"- datasource: {datasource.get('name')} ({datasource.get('db_type')}) @ {datasource.get('host')}:{datasource.get('port')}"
        )
    if brief.get("issue_category"):
        lines.append(f"- likely_issue_category: {brief['issue_category']}")
    if brief.get("user_symptoms"):
        lines.append(f"- user_symptoms: {', '.join(brief['user_symptoms'])}")
    for signal in brief.get("abnormal_signals", [])[:6]:
        lines.append(f"- abnormal_signal: [{signal['severity']}] {signal['label']}={signal['value']} | {signal['reason']}")
    for alert in brief.get("active_alerts", [])[:3]:
        lines.append(f"- recent_alert: [{alert['severity']}] {alert['title']} | {alert['status']}")
    if brief.get("recent_conclusion"):
        lines.append(f"- latest_related_conclusion: {brief['recent_conclusion']['summary']}")
    if brief.get("recent_report"):
        lines.append(f"- latest_report_summary: {brief['recent_report']['summary']}")
    for focus in brief.get("focus_areas", [])[:5]:
        lines.append(f"- investigation_focus: {focus}")
    lines.append("- Use this brief as starting context, but verify every hypothesis with tools before concluding.")
    return "\n".join(lines)


async def build_diagnostic_brief(
    db: AsyncSession,
    *,
    datasource_id: int | None,
    user_message: str,
    issue_category: str | None,
) -> dict[str, Any] | None:
    if not datasource_id:
        return None

    ds_result = await db.execute(
        select(Datasource).where(Datasource.id == datasource_id, alive_filter(Datasource))
    )
    datasource = ds_result.scalar_one_or_none()
    if not datasource:
        return None

    host = None
    if datasource.host_id:
        host_result = await db.execute(select(Host).where(Host.id == datasource.host_id, alive_filter(Host)))
        host = host_result.scalar_one_or_none()

    metric_result = await db.execute(
        select(DatasourceMetric)
        .where(DatasourceMetric.datasource_id == datasource_id)
        .order_by(desc(DatasourceMetric.collected_at))
        .limit(8)
    )
    snapshots = metric_result.scalars().all()
    abnormal_signals: list[dict[str, Any]] = []
    seen_labels: set[tuple[str, str]] = set()
    for snapshot in snapshots:
        for signal in extract_metric_signals(snapshot.metric_type, snapshot.data):
            key = (signal["source"], signal["label"])
            if key in seen_labels:
                continue
            seen_labels.add(key)
            abnormal_signals.append(signal)

    alert_result = await db.execute(
        select(AlertMessage)
        .where(AlertMessage.datasource_id == datasource_id)
        .order_by(desc(AlertMessage.created_at))
        .limit(5)
    )
    alerts = alert_result.scalars().all()
    active_alerts = [
        {
            "id": alert.id,
            "severity": alert.severity,
            "title": alert.title,
            "status": alert.status,
            "metric_name": alert.metric_name,
            "trigger_reason": alert.trigger_reason or alert.content[:120],
        }
        for alert in alerts
    ]

    report_result = await db.execute(
        select(Report)
        .where(Report.datasource_id == datasource_id, alive_filter(Report))
        .order_by(desc(Report.created_at))
        .limit(1)
    )
    report = report_result.scalars().first()

    conclusion_result = await db.execute(
        select(DiagnosisConclusion)
        .where(DiagnosisConclusion.datasource_id == datasource_id)
        .order_by(desc(DiagnosisConclusion.updated_at), desc(DiagnosisConclusion.id))
        .limit(1)
    )
    conclusion = conclusion_result.scalars().first()

    focus_areas = build_focus_areas(issue_category, abnormal_signals, active_alerts)
    triage_parts = []
    if abnormal_signals:
        triage_parts.append(f"检测到 {len(abnormal_signals)} 个优先关注信号")
    if active_alerts:
        triage_parts.append(f"最近有 {len(active_alerts)} 条相关告警")
    if conclusion and conclusion.summary:
        triage_parts.append("存在历史诊断结论可参考")
    if not triage_parts:
        triage_parts.append("暂无明显异常快照，需要依赖实时工具进一步收集证据")

    return {
        "datasource": {
            "id": datasource.id,
            "name": datasource.name,
            "db_type": datasource.db_type,
            "host": datasource.host,
            "port": datasource.port,
            "database": datasource.database,
            "remark": datasource.remark,
            "host_name": getattr(host, "name", None),
            "host_os_version": getattr(host, "os_version", None),
        },
        "issue_category": issue_category,
        "user_symptoms": [part.strip() for part in user_message.splitlines() if part.strip()][:4] or [user_message[:120]],
        "abnormal_signals": abnormal_signals[:8],
        "active_alerts": active_alerts[:5],
        "recent_report": {
            "id": report.id,
            "summary": report.summary or (report.title if report else ""),
            "status": report.status,
            "created_at": report.created_at.isoformat() if report and report.created_at else None,
        } if report else None,
        "recent_conclusion": {
            "id": conclusion.id,
            "summary": conclusion.summary,
            "confidence": conclusion.confidence,
            "updated_at": conclusion.updated_at.isoformat() if conclusion and conclusion.updated_at else None,
        } if conclusion and conclusion.summary else None,
        "focus_areas": focus_areas,
        "triage_summary": "；".join(triage_parts),
    }
