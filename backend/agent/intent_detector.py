"""
Intent and issue classification for AI diagnosis flows.
"""

from __future__ import annotations

import logging
import re
from dataclasses import asdict, dataclass

logger = logging.getLogger(__name__)

INTENT_KEYWORDS = {
    "diagnostic": [
        "慢", "slow", "错误", "error", "问题", "problem", "故障", "fault",
        "诊断", "diagnose", "优化", "optimize", "为什么", "why", "怎么办",
        "解决", "solve", "修复", "fix", "异常", "abnormal", "卡", "stuck",
        "失败", "fail", "超时", "timeout", "阻塞", "block", "性能", "performance",
        "瓶颈", "bottleneck", "延迟", "latency", "告警", "报警", "不通", "崩",
        "cpu", "内存", "memory", "磁盘", "disk", "io", "负载", "load",
    ],
    "informational": [
        "查看", "view", "显示", "show", "列出", "list", "获取", "get", "什么是",
        "what is", "有哪些", "current", "当前", "状态", "status", "信息", "info",
        "统计", "stats", "监控", "monitor", "报告", "report", "有哪些表", "参数",
    ],
    "administrative": [
        "执行", "execute", "运行", "run", "创建", "create", "修改", "modify",
        "删除", "delete", "更新", "update", "设置", "set", "启用", "enable",
        "禁用", "disable", "添加", "add", "移除", "remove", "配置", "configure",
        "建索引", "kill ", "flush ", "grant ", "revoke ",
    ],
}

ISSUE_CATEGORY_KEYWORDS = {
    "performance": [
        "慢", "slow", "performance", "性能", "延迟", "latency", "qps", "tps",
        "吞吐", "响应慢", "卡顿", "抖动",
    ],
    "connectivity": [
        "连接", "connect", "connection", "登录", "login", "认证", "auth",
        "timeout", "超时", "拒绝", "refused", "不通", "无法访问",
    ],
    "locking": [
        "锁", "lock", "阻塞", "blocking", "死锁", "deadlock", "等待", "wait event",
        "hang", "hang住",
    ],
    "replication": [
        "复制", "replication", "主从", "从库", "备库", "延迟", "lag", "同步",
        "standby", "replica", "failover",
    ],
    "capacity": [
        "磁盘", "disk", "空间", "space", "容量", "capacity", "满了", "增长", "膨胀",
        "表太大", "归档", "存储",
    ],
    "sql": [
        "sql", "query", "查询", "执行计划", "explain", "索引", "index", "top sql",
        "慢查询", "scan", "全表扫描",
    ],
    "resource": [
        "cpu", "内存", "memory", "swap", "iowait", "io", "负载", "load", "network",
        "网络", "带宽", "磁盘 io", "宿主机", "主机",
    ],
    "configuration": [
        "配置", "parameter", "参数", "setting", "变量", "variable", "buffer",
        "max_connections", "work_mem", "shared_buffers",
    ],
    "error": [
        "错误", "error", "异常", "exception", "报错", "崩溃", "panic", "corrupt",
        "损坏", "失败", "fail",
    ],
}


@dataclass
class IntentAnalysis:
    intent: str
    issue_category: str | None
    confidence: float
    symptoms: list[str]
    needs_clarification: bool

    def to_dict(self) -> dict:
        return asdict(self)


def _count_matches(message_lower: str, keywords: list[str]) -> int:
    return sum(1 for keyword in keywords if keyword in message_lower)


def _extract_symptoms(message: str, issue_category: str | None) -> list[str]:
    text = (message or "").strip()
    if not text:
        return []

    chunks = re.split(r"[，,。；;！？!?/\n]+", text)
    cleaned = [chunk.strip() for chunk in chunks if chunk.strip()]
    if not cleaned:
        return []

    symptoms = cleaned[:4]
    if issue_category and all(issue_category not in symptom.lower() for symptom in symptoms):
        symptoms.insert(0, issue_category)
    return symptoms[:5]


def analyze_query_intent(message: str) -> IntentAnalysis:
    """
    Classify user intent and, for diagnostic requests, infer a likely issue category.
    """
    message_lower = (message or "").lower()
    if not message_lower.strip():
        return IntentAnalysis(
            intent="informational",
            issue_category=None,
            confidence=0.4,
            symptoms=[],
            needs_clarification=True,
        )

    scores = {
        intent: _count_matches(message_lower, keywords)
        for intent, keywords in INTENT_KEYWORDS.items()
    }
    action_request = bool(re.search(r"\b(execute|run|create|modify|delete|update|set|enable|disable|add|remove|configure|kill)\b", message_lower)) or any(
        token in message_lower for token in ["执行", "运行", "创建", "修改", "删除", "更新", "设置", "启用", "禁用", "添加", "移除"]
    )
    info_request = bool(re.match(r"^\s*(查看|显示|列出|获取|show|view|list|get)\b", message_lower))

    sql_write_hint = bool(
        re.search(r"\b(insert|update|delete|drop|alter|truncate|create|grant|revoke|kill)\b", message_lower)
    )
    sql_read_hint = bool(re.search(r"\b(select|show|describe|desc|explain)\b", message_lower))
    if action_request:
        scores["administrative"] += 2
    if info_request:
        scores["informational"] += 2
    if sql_write_hint:
        scores["administrative"] += 2
    elif sql_read_hint:
        scores["informational"] += 1

    intent = max(scores.items(), key=lambda item: item[1])[0]
    max_score = max(scores.values())

    if max_score <= 0:
        intent = "informational"

    if scores["diagnostic"] > 0 and scores["diagnostic"] >= scores["informational"] and scores["diagnostic"] >= scores["administrative"]:
        intent = "diagnostic"
    elif scores["administrative"] > 0 and scores["administrative"] >= scores["informational"] and action_request:
        intent = "administrative"

    issue_category = None
    category_score = 0
    if intent == "diagnostic":
        category_scores = {
            category: _count_matches(message_lower, keywords)
            for category, keywords in ISSUE_CATEGORY_KEYWORDS.items()
        }
        issue_category, category_score = max(category_scores.items(), key=lambda item: item[1])
        if category_score <= 0:
            issue_category = "general"
    else:
        category_scores = {
            category: _count_matches(message_lower, keywords)
            for category, keywords in ISSUE_CATEGORY_KEYWORDS.items()
        }
        category, category_score = max(category_scores.items(), key=lambda item: item[1])
        if category_score > 0 and intent == "informational" and not info_request and scores["informational"] == 0:
            intent = "diagnostic"
            issue_category = category

    confidence = 0.55
    if max_score >= 3:
        confidence = 0.9
    elif max_score == 2:
        confidence = 0.78
    elif max_score == 1:
        confidence = 0.66

    if intent == "diagnostic" and category_score >= 2:
        confidence = min(confidence + 0.05, 0.95)

    needs_clarification = len(message_lower.strip()) < 8 and max_score <= 1

    return IntentAnalysis(
        intent=intent,
        issue_category=issue_category,
        confidence=confidence,
        symptoms=_extract_symptoms(message, issue_category),
        needs_clarification=needs_clarification,
    )


def detect_query_intent(message: str) -> str:
    """Backward compatible helper returning only the top-level intent."""
    return analyze_query_intent(message).intent


async def detect_intent_with_llm(message: str) -> str:
    """
    Use AI to detect intent for ambiguous or short queries.
    Fallback when rule matching is uncertain.
    """
    from backend.services.ai_agent import get_ai_client

    base_analysis = analyze_query_intent(message)
    if base_analysis.confidence >= 0.75 and not base_analysis.needs_clarification:
        return base_analysis.intent

    client = get_ai_client()
    if not client:
        return base_analysis.intent

    prompt = f"""你是一个数据库助手意图分类器。根据用户的问题，判断其意图是哪种类型：

- diagnostic（诊断）: 用户遇到问题需要分析根因，如"数据库变慢了"、"连接失败"、"有错误"
- informational（查询）: 用户想查看或了解某些信息，如"查看状态"、"列出慢查询"、"有什么表"
- administrative（操作）: 用户想执行某种操作，如"创建索引"、"删除数据"、"修改配置"

用户问题：{message}

只回答一个词：diagnostic、informational 或 administrative。

回答："""

    try:
        if client.protocol == "anthropic":
            response = await client.client.messages.create(
                model=client.model_name,
                max_tokens=10,
                messages=[{"role": "user", "content": prompt}],
            )
            intent = response.content[0].text.strip().lower()
        else:
            response = await client.client.chat.completions.create(
                model=client.model_name,
                max_tokens=10,
                messages=[{"role": "user", "content": prompt}],
            )
            intent = response.choices[0].message.content.strip().lower()

        if intent in {"diagnostic", "informational", "administrative"}:
            logger.debug("LLM intent detection: %r -> %s", message[:30], intent)
            return intent
        return base_analysis.intent
    except Exception as exc:
        logger.warning("LLM intent detection failed, using rule fallback: %s", exc)
        return base_analysis.intent
