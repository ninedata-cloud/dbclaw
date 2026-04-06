import re
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.agent.intent_detector import analyze_query_intent
from backend.models.datasource import Datasource
from backend.models.document import DocCategory, DocDocument
from backend.models.soft_delete import alive_filter


ISSUE_KEYWORDS: dict[str, list[str]] = {
    "performance": ["慢", "性能", "cpu", "负载", "卡", "吞吐", "qps", "tps", "高负载", "响应慢"],
    "connectivity": ["连接", "连不上", "timeout", "认证", "拒绝", "connection"],
    "locking": ["锁", "阻塞", "死锁", "等待", "metadata lock", "lock"],
    "replication": ["复制", "主从", "延迟", "同步", "replica", "slave", "standby"],
    "capacity": ["空间", "磁盘", "容量", "表空间", "满", "增长"],
    "sql": ["sql", "查询", "索引", "执行计划", "explain", "慢查询"],
    "resource": ["内存", "iowait", "磁盘io", "network", "网络", "主机", "cpu"],
    "configuration": ["配置", "参数", "变量", "buffer", "max_connections"],
    "error": ["报错", "错误", "异常", "失败", "error", "crash"],
    "general": ["诊断", "巡检", "检查", "分析"],
}


def infer_issue_categories_from_text(text: str, issue_category: Optional[str] = None) -> list[str]:
    categories: list[str] = []
    if issue_category:
        categories.append(issue_category)
    lowered = (text or "").lower()
    for category, keywords in ISSUE_KEYWORDS.items():
        if category in categories:
            continue
        if any(keyword.lower() in lowered for keyword in keywords):
            categories.append(category)
    if not categories:
        categories.append("general")
    return categories


def _normalize_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, list):
        return " ".join(_normalize_text(item) for item in value)
    return str(value).lower()


def _ensure_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _dedupe_preserve_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        output.append(value)
    return output


def compute_document_route(
    *,
    doc: dict[str, Any],
    user_message: str,
    datasource_id: Optional[int],
    host_id: Optional[int],
    db_type: Optional[str],
    issue_categories: list[str],
) -> dict[str, Any]:
    score = 0
    reasons: list[str] = []

    doc_db_types = [item.lower() for item in _ensure_list(doc.get("db_types")) if item]
    if db_type:
        db_type_lower = db_type.lower()
        if doc_db_types:
            if db_type_lower in doc_db_types:
                score += 30
                reasons.append(f"匹配数据库类型 {db_type}")
            elif "general" not in doc_db_types:
                score -= 15
        elif _normalize_text(doc.get("category_db_type")) == db_type_lower:
            score += 25
            reasons.append(f"匹配数据库类型 {db_type}")

    doc_datasource_ids = [int(item) for item in _ensure_list(doc.get("datasource_ids")) if str(item).isdigit()]
    if datasource_id and doc_datasource_ids:
        if datasource_id in doc_datasource_ids:
            score += 60
            reasons.append("绑定当前数据源")
        else:
            score -= 40

    doc_host_ids = [int(item) for item in _ensure_list(doc.get("host_ids")) if str(item).isdigit()]
    if host_id and doc_host_ids:
        if host_id in doc_host_ids:
            score += 40
            reasons.append("绑定当前主机")
        else:
            score -= 20

    if (doc.get("scope") or "builtin") == "tenant":
        score += 25
        reasons.append("私有运维知识优先")

    doc_issue_categories = [item.lower() for item in _ensure_list(doc.get("issue_categories")) if item]
    matched_issue_categories = [item for item in issue_categories if item.lower() in doc_issue_categories]
    if matched_issue_categories:
        score += 35
        reasons.append(f"匹配问题类别 {matched_issue_categories[0]}")
    elif doc_issue_categories and "general" not in doc_issue_categories:
        score -= 10

    doc_kind = (doc.get("doc_kind") or "").lower()
    if doc_kind in {"runbook", "known_issue", "case"}:
        score += 12
        reasons.append(f"{doc_kind} 类型知识更适合诊断")
    elif doc_kind == "reference":
        score -= 5

    freshness = (doc.get("freshness_level") or "stable").lower()
    if freshness == "stable":
        score += 8
    elif freshness == "needs_review":
        score -= 5
    elif freshness == "expired":
        score -= 100

    text_blob = " ".join([
        _normalize_text(doc.get("title")),
        _normalize_text(doc.get("summary")),
        _normalize_text(doc.get("tags")),
        _normalize_text(doc.get("category_name")),
    ])
    for category in issue_categories:
        if category.lower() in text_blob:
            score += 8
            reasons.append(f"标题/摘要命中 {category}")
            break

    tokens = [token for token in re.split(r"[\s,，。:：;；/\\()（）\[\]<>\"'`]+", (user_message or "").lower()) if len(token) >= 2]
    keyword_hits = 0
    for token in tokens[:12]:
        if token in text_blob:
            keyword_hits += 1
    if keyword_hits:
        score += min(keyword_hits * 4, 20)
        reasons.append(f"命中 {keyword_hits} 个问题关键词")

    score += int(doc.get("priority") or 0) * 3
    return {
        "score": score,
        "reasons": _dedupe_preserve_order(reasons),
    }


async def build_knowledge_context(
    db: AsyncSession,
    *,
    datasource_id: Optional[int],
    user_message: str,
    issue_category: Optional[str] = None,
    limit: int = 10,
) -> dict[str, Any]:
    datasource = None
    host_id = None
    db_type = None

    if datasource_id:
        result = await db.execute(
            select(Datasource).where(Datasource.id == datasource_id, alive_filter(Datasource))
        )
        datasource = result.scalar_one_or_none()
        if datasource:
            host_id = datasource.host_id
            db_type = datasource.db_type

    if issue_category is None:
        intent = analyze_query_intent(user_message or "")
        issue_category = intent.issue_category
    issue_categories = infer_issue_categories_from_text(user_message, issue_category)

    query = (
        select(DocDocument, DocCategory.name.label("category_name"), DocCategory.db_type.label("category_db_type"))
        .join(DocCategory, DocDocument.category_id == DocCategory.id)
        .where(
            DocDocument.is_active == True,
            alive_filter(DocDocument),
            DocDocument.enabled_in_diagnosis == True,
        )
    )
    if db_type:
        query = query.where(DocCategory.db_type.in_([db_type, "general"]))

    result = await db.execute(query)
    ranked: list[dict[str, Any]] = []
    for row in result.all():
        doc = row.DocDocument
        route = compute_document_route(
            doc={
                "id": doc.id,
                "title": doc.title,
                "summary": doc.summary,
                "scope": doc.scope,
                "doc_kind": doc.doc_kind,
                "db_types": doc.db_types,
                "issue_categories": doc.issue_categories,
                "datasource_ids": doc.datasource_ids,
                "host_ids": doc.host_ids,
                "tags": doc.tags,
                "priority": doc.priority,
                "freshness_level": doc.freshness_level,
                "category_name": row.category_name,
                "category_db_type": row.category_db_type,
            },
            user_message=user_message,
            datasource_id=datasource_id,
            host_id=host_id,
            db_type=db_type,
            issue_categories=issue_categories,
        )
        if route["score"] < 0:
            continue
        ranked.append({
            "document_id": doc.id,
            "title": doc.title,
            "summary": doc.summary or "",
            "category_name": row.category_name,
            "db_type": row.category_db_type,
            "scope": doc.scope or "builtin",
            "doc_kind": doc.doc_kind or "reference",
            "score": route["score"],
            "reason": "；".join(route["reasons"][:3]) if route["reasons"] else "匹配当前诊断上下文",
            "reasons": route["reasons"],
        })

    ranked.sort(key=lambda item: (-item["score"], item["title"]))
    recommended = ranked[:limit]
    return {
        "datasource_id": datasource_id,
        "datasource_name": datasource.name if datasource else None,
        "db_type": db_type,
        "issue_category": issue_category,
        "issue_categories": issue_categories,
        "recommended_documents": recommended,
        "knowledge_brief": recommended[:5],
    }
