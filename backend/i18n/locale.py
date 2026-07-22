"""Locale parsing and backend message catalogs.

The browser sends an exact X-DBClaw-Locale value. Accept-Language remains
supported for API clients that do not use the DBClaw web console.
"""

from __future__ import annotations

import re
from typing import Any

from fastapi import Request

DEFAULT_LOCALE = "zh-CN"
SUPPORTED_LOCALES = ("zh-CN", "en-US")

_ALIASES = {
    "zh": "zh-CN",
    "zh-cn": "zh-CN",
    "zh-hans": "zh-CN",
    "zh-hans-cn": "zh-CN",
    "en": "en-US",
    "en-us": "en-US",
}

MESSAGES: dict[str, dict[str, str]] = {
    "zh-CN": {
        "request.failed": "请求失败",
        "request.validation_error": "请求参数校验失败",
        "request.internal_error": "服务器内部错误",
        "auth.not_authenticated": "请先登录",
        "auth.session_expired": "会话已过期，请重新登录",
        "auth.user_not_found": "用户不存在",
        "auth.account_disabled": "账户已被禁用",
        "auth.admin_required": "需要管理员权限",
        "auth.invalid_credentials": "用户名或密码错误",
        "auth.invalid_current_password": "当前密码不正确",
        "auth.username_exists": "用户名已存在",
        "auth.cannot_delete_self": "不能删除自己",
        "auth.cannot_change_own_status": "不能修改自己的状态",
        "auth.admin_password_self_only": "admin 密码只能由本人修改",
        "auth.locale_invalid": "不支持的语言：{locale}",
        "resource.not_found": "资源不存在",
        "datasource.not_found": "数据源不存在",
        "host.not_found": "主机不存在",
        "model.not_found": "模型不存在",
        "skill.not_found": "技能不存在",
        "report.not_found": "报告不存在",
        "config.not_found": "配置不存在",
        "task.not_found": "任务不存在",
        "alert.not_found": "告警不存在",
        "subscription.not_found": "订阅不存在",
        "integration.not_found": "集成不存在",
        "document.not_found": "文档不存在",
        "operation.not_allowed": "不允许执行此操作",
        "operation.failed": "操作失败",
        "query.cancelled": "查询已取消",
        "query.read_only": "仅允许执行只读查询，DML/DDL 语句已被阻止。",
        "upload.too_large": "文件过大（最大 {max_size}）",
        "upload.unsupported_type": "不支持的文件类型",
        "ai.model_not_configured": "尚未配置 AI 模型，请先在 AI 模型管理页面添加模型。",
        "ai.intent.analyzing": "正在分析您的问题...",
        "ai.intent.diagnostic": "检测到诊断意图，正在分析数据库问题...",
        "ai.intent.informational": "检测到查询意图，正在准备信息检索...",
        "ai.intent.administrative": "检测到操作意图，正在准备执行任务...",
        "ai.intent.category": "{message} 当前更像{category}。",
        "ai.context.building": "正在构建诊断上下文...",
        "ai.context.building_detail": "正在构建诊断上下文... {detail}",
        "ai.skills.selected": "已选中 {count} 个诊断技能",
        "ai.diagnosis.starting": "开始诊断...",
        "ai.response.partial_timeout": "[AI 响应超时，以上为部分结果]",
        "ai.response.timeout": "AI 响应超时（{seconds}秒），请稍后重试或简化问题。",
        "ai.response.error": "AI 响应出错：{error}",
        "ai.response.max_rounds": "已达到最大工具执行轮数（{rounds}）。当前诊断可能过于复杂或需要人工介入，请将问题拆分后重试。",
        "ai.session.busy": "AI 正在生成中，请等待完成或点击停止按钮。",
        "ai.session.generating": "AI 正在生成中...",
        "ai.session.cancelled": "[用户已停止生成]",
        "ai.session.error": "AI 会话出错：{error}",
        "ai.session.partial_timeout": "[会话超时，以上为部分结果]",
        "ai.session.timeout": "AI 会话超时（{seconds}秒），请稍后重试或简化问题。",
        "ai.approval.not_found": "确认请求不存在或已失效",
        "ai.report.title": "{trigger_type}巡检 - {datasource}",
        "ai.report.missing_datasource": "报告生成失败：数据源不存在或已删除。",
        "ai.report.failed": "报告生成失败，未产出有效内容。",
        "ai.report.footer.generated": "报告由 DBClaw 智能诊断引擎生成",
        "ai.report.footer.datasource": "数据源：{datasource}（{db_type}）| 生成时间：{generated_at}",
    },
    "en-US": {
        "request.failed": "Request failed",
        "request.validation_error": "Request validation failed",
        "request.internal_error": "Internal server error",
        "auth.not_authenticated": "Please sign in first",
        "auth.session_expired": "Your session has expired. Please sign in again",
        "auth.user_not_found": "User not found",
        "auth.account_disabled": "This account is disabled",
        "auth.admin_required": "Administrator privileges are required",
        "auth.invalid_credentials": "Incorrect username or password",
        "auth.invalid_current_password": "The current password is incorrect",
        "auth.username_exists": "Username already exists",
        "auth.cannot_delete_self": "You cannot delete your own account",
        "auth.cannot_change_own_status": "You cannot change your own status",
        "auth.admin_password_self_only": "Only the admin user can change the admin password",
        "auth.locale_invalid": "Unsupported language: {locale}",
        "resource.not_found": "Resource not found",
        "datasource.not_found": "Datasource not found",
        "host.not_found": "Host not found",
        "model.not_found": "Model not found",
        "skill.not_found": "Skill not found",
        "report.not_found": "Report not found",
        "config.not_found": "Configuration not found",
        "task.not_found": "Task not found",
        "alert.not_found": "Alert not found",
        "subscription.not_found": "Subscription not found",
        "integration.not_found": "Integration not found",
        "document.not_found": "Document not found",
        "operation.not_allowed": "This operation is not allowed",
        "operation.failed": "Operation failed",
        "query.cancelled": "Query cancelled",
        "query.read_only": "Only read-only queries are allowed. DML/DDL statements are blocked.",
        "upload.too_large": "The file is too large (maximum {max_size})",
        "upload.unsupported_type": "Unsupported file type",
        "ai.model_not_configured": "No AI model is configured. Add one on the AI Model Management page.",
        "ai.intent.analyzing": "Analyzing your question...",
        "ai.intent.diagnostic": "Diagnostic intent detected. Analyzing the database issue...",
        "ai.intent.informational": "Information request detected. Preparing retrieval...",
        "ai.intent.administrative": "Operational request detected. Preparing the task...",
        "ai.intent.category": "{message} It most closely matches: {category}.",
        "ai.context.building": "Building diagnostic context...",
        "ai.context.building_detail": "Building diagnostic context... {detail}",
        "ai.skills.selected": "Selected {count} diagnostic skills",
        "ai.diagnosis.starting": "Starting diagnosis...",
        "ai.response.partial_timeout": "[The AI response timed out; the partial result is shown above]",
        "ai.response.timeout": "The AI response timed out after {seconds} seconds. Try again later or simplify the question.",
        "ai.response.error": "AI response error: {error}",
        "ai.response.max_rounds": "The maximum number of tool execution rounds ({rounds}) was reached. The diagnosis may be too complex or require manual intervention; split the question into smaller parts and try again.",
        "ai.session.busy": "The AI is still generating. Wait for it to finish or select Stop.",
        "ai.session.generating": "The AI is generating...",
        "ai.session.cancelled": "[Generation stopped by the user]",
        "ai.session.error": "AI conversation error: {error}",
        "ai.session.partial_timeout": "[The conversation timed out; the partial result is shown above]",
        "ai.session.timeout": "The AI conversation timed out after {seconds} seconds. Try again later or simplify the question.",
        "ai.approval.not_found": "The confirmation request does not exist or has expired",
        "ai.report.title": "{trigger_type} Inspection - {datasource}",
        "ai.report.missing_datasource": "Report generation failed because the datasource does not exist or was deleted.",
        "ai.report.failed": "Report generation failed without producing valid content.",
        "ai.report.footer.generated": "Generated by the DBClaw intelligent diagnostics engine",
        "ai.report.footer.datasource": "Datasource: {datasource} ({db_type}) | Generated: {generated_at}",
    },
}

# Exact legacy messages are mapped while routers are incrementally converted to
# ApiError. This also localizes errors raised by older service code.
LEGACY_ERROR_CODES = {
    "User not found": "auth.user_not_found",
    "用户不存在": "auth.user_not_found",
    "Account is disabled": "auth.account_disabled",
    "账户已被禁用": "auth.account_disabled",
    "Session expired": "auth.session_expired",
    "Not authenticated": "auth.not_authenticated",
    "Admin privileges required": "auth.admin_required",
    "需要管理员权限": "auth.admin_required",
    "用户名或密码错误": "auth.invalid_credentials",
    "当前密码不正确": "auth.invalid_current_password",
    "用户名已存在": "auth.username_exists",
    "不能删除自己": "auth.cannot_delete_self",
    "Cannot change your own status": "auth.cannot_change_own_status",
    "admin 密码只能由本人修改": "auth.admin_password_self_only",
    "Datasource not found": "datasource.not_found",
    "数据源不存在": "datasource.not_found",
    "SSH host not found": "host.not_found",
    "主机不存在": "host.not_found",
    "模型不存在": "model.not_found",
    "Skill not found": "skill.not_found",
    "报告不存在": "report.not_found",
    "Configuration not found": "config.not_found",
    "任务不存在": "task.not_found",
    "Alert not found": "alert.not_found",
    "Event not found": "alert.not_found",
    "Subscription not found": "subscription.not_found",
    "Integration 不存在": "integration.not_found",
    "Document not found": "document.not_found",
    "查询已取消": "query.cancelled",
    "Only read-only queries are allowed. DML/DDL statements are blocked.": "query.read_only",
    "不支持的文件类型": "upload.unsupported_type",
}


def normalize_locale(value: str | None) -> str | None:
    if not value:
        return None
    normalized = value.strip().replace("_", "-").lower()
    return _ALIASES.get(normalized)


def parse_accept_language(value: str | None) -> str | None:
    if not value:
        return None
    choices: list[tuple[float, int, str]] = []
    for index, raw_item in enumerate(value.split(",")):
        parts = [part.strip() for part in raw_item.split(";")]
        locale = normalize_locale(parts[0])
        if not locale:
            continue
        quality = 1.0
        for part in parts[1:]:
            match = re.fullmatch(r"q=([01](?:\.\d{1,3})?)", part, re.IGNORECASE)
            if match:
                quality = float(match.group(1))
        if quality > 0:
            choices.append((quality, -index, locale))
    return max(choices)[2] if choices else None


def resolve_request_locale(request: Request) -> tuple[str, str]:
    explicit = normalize_locale(request.headers.get("X-DBClaw-Locale"))
    if explicit:
        return explicit, "explicit"
    accepted = parse_accept_language(request.headers.get("Accept-Language"))
    if accepted:
        return accepted, "accept-language"
    return DEFAULT_LOCALE, "default"


def get_request_locale(request: Request | None) -> str:
    if request is None:
        return DEFAULT_LOCALE
    return normalize_locale(getattr(request.state, "locale", None)) or DEFAULT_LOCALE


def apply_user_locale(request: Request, locale: str | None) -> None:
    """Use the account locale unless the caller sent an explicit app locale."""
    if getattr(request.state, "locale_source", "default") != "explicit":
        normalized = normalize_locale(locale)
        if normalized:
            request.state.locale = normalized
            request.state.locale_source = "account"


def translate(locale: str, key: str, params: dict[str, Any] | None = None) -> str:
    normalized = normalize_locale(locale) or DEFAULT_LOCALE
    template = MESSAGES.get(normalized, MESSAGES[DEFAULT_LOCALE]).get(key)
    if template is None:
        template = MESSAGES[DEFAULT_LOCALE].get(key, key)
    try:
        return template.format(**(params or {}))
    except (KeyError, ValueError):
        return template


def legacy_error_code(detail: str) -> str | None:
    exact = LEGACY_ERROR_CODES.get(detail)
    if exact:
        return exact

    lowered = detail.lower()
    not_found = "不存在" in detail or "not found" in lowered
    if not_found:
        resource_patterns = (
            (("数据源", "datasource"), "datasource.not_found"),
            (("主机", "host"), "host.not_found"),
            (("模型", "model"), "model.not_found"),
            (("技能", "skill"), "skill.not_found"),
            (("报告", "report"), "report.not_found"),
            (("配置", "configuration", "config"), "config.not_found"),
            (("任务", "task"), "task.not_found"),
            (("告警", "alert", "event"), "alert.not_found"),
            (("订阅", "subscription"), "subscription.not_found"),
            (("集成", "integration"), "integration.not_found"),
            (("文档", "document"), "document.not_found"),
            (("用户", "user"), "auth.user_not_found"),
        )
        for keywords, code in resource_patterns:
            if any(keyword in lowered for keyword in keywords):
                return code
        return "resource.not_found"

    if "管理员" in detail or "admin" in lowered or "权限" in detail or "privilege" in lowered:
        return "auth.admin_required"
    if "只读" in detail or "read-only" in lowered:
        return "query.read_only"
    if "取消" in detail and "查询" in detail:
        return "query.cancelled"
    if "不支持" in detail or "not supported" in lowered or "not allowed" in lowered or "cannot" in lowered:
        return "operation.not_allowed"
    if "失败" in detail or "failed" in lowered or "error" in lowered:
        return "operation.failed"
    if "不能为空" in detail or "必须" in detail or "invalid" in lowered or "required" in lowered:
        return "request.validation_error"
    return None
