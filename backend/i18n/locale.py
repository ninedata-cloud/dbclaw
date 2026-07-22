"""Locale parsing and backend message catalogs.

The browser sends an exact X-DBClaw-Locale value. Accept-Language remains
supported for API clients that do not use the DBClaw web console.
"""

from __future__ import annotations

import re
import logging
from collections import Counter
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import Request

DEFAULT_LOCALE = "zh-CN"
DEFAULT_TIMEZONE = "Asia/Shanghai"
logger = logging.getLogger(__name__)
_I18N_COUNTERS: Counter[str] = Counter()


@dataclass(frozen=True)
class LocaleDefinition:
    code: str
    aliases: tuple[str, ...]
    direction: str = "ltr"


LOCALE_REGISTRY = {
    "zh-CN": LocaleDefinition("zh-CN", ("zh", "zh-cn", "zh-hans", "zh-hans-cn")),
    "en-US": LocaleDefinition("en-US", ("en", "en-us")),
}
SUPPORTED_LOCALES = tuple(LOCALE_REGISTRY)
_active_locale: ContextVar[str] = ContextVar("dbclaw_active_locale", default=DEFAULT_LOCALE)
_system_default_locale = DEFAULT_LOCALE
_system_default_timezone = DEFAULT_TIMEZONE

_ALIASES = {
    alias: definition.code
    for definition in LOCALE_REGISTRY.values()
    for alias in definition.aliases
}

MESSAGES: dict[str, dict[str, str]] = {
    "zh-CN": {
        "request.failed": "请求失败",
        "request.validation_error": "请求参数校验失败",
        "request.validation.missing": "字段为必填项",
        "request.validation.string_too_short": "字符串长度不足",
        "request.validation.literal": "输入值不在允许范围内",
        "request.validation.invalid": "输入值无效",
        "request.internal_error": "服务器内部错误",
        "request.invalid_origin": "请求来源无效",
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
        "auth.timezone_invalid": "无效的 IANA 时区：{timezone}",
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
        "ai.session.error_safe": "AI 会话发生错误，请稍后重试。",
        "terminal.connection_error": "终端连接失败，请稍后重试。",
        "ai.session.partial_timeout": "[会话超时，以上为部分结果]",
        "ai.session.timeout": "AI 会话超时（{seconds}秒），请稍后重试或简化问题。",
        "ai.approval.not_found": "确认请求不存在或已失效",
        "ai.report.title": "{trigger_type}巡检 - {datasource}",
        "ai.report.missing_datasource": "报告生成失败：数据源不存在或已删除。",
        "ai.report.failed": "报告生成失败，未产出有效内容。",
        "ai.report.footer.generated": "报告由 DBClaw 智能诊断引擎生成",
        "ai.report.footer.datasource": "数据源：{datasource}（{db_type}）| 生成时间：{generated_at}",
        "alert.connection_failed.title": "数据库连接失败",
        "alert.connection_failed.status": "数据库连接失败",
        "alert.connection_recovered.status": "数据库连接已恢复",
        "alert.threshold.title": "{metric} 阈值告警",
        "alert.baseline.title": "{metric} 基线偏移告警",
        "alert.triggered": "告警已触发",
        "alert.ai.model_not_configured": "AI 判警失败：尚未配置 AI 判警模型",
        "alert.ai.evaluation_failed": "AI 判警失败，请查看服务日志",
        "alert.ai.severity_mismatch": "AI 返回等级 {actual} 与模板等级 {expected} 不一致",
        "alert.diagnosis.timeout_background": "诊断超时，正在后台继续分析...",
        "alert.diagnosis.failed": "诊断失败，请稍后重试",
        "alert.field.status": "状态",
        "alert.field.metric": "指标",
        "alert.field.threshold": "阈值",
        "alert.field.reason": "原因",
        "alert.field.error_detail": "错误详情",
        "alert.field.previous_error": "上一条错误",
        "alert.field.alert_type": "告警类型",
        "alert.field.severity": "严重程度",
        "alert.field.alert_time": "告警时间",
        "alert.field.recovery_time": "恢复时间",
        "alert.field.recovered_value": "恢复后值",
        "alert.field.ai_summary": "AI 总结",
        "alert.value.unknown": "未知",
        "notification.datasource.unknown": "未知数据源",
        "notification.alert.title": "【{severity}】{datasource} 告警",
        "notification.connection_failed.title": "【{severity}】{datasource} 数据库连接失败",
        "notification.recovery.title": "【已恢复】{datasource} 告警已恢复",
        "notification.connection_recovered.title": "【已恢复】{datasource} 数据库连接已恢复",
        "auth.logout.success": "已退出登录",
        "auth.logout_all.success": "已撤销所有会话",
        "auth.password_changed.success": "密码修改成功",
        "auth.user_deleted.success": "用户已删除",
        "auth.password_reset.success": "密码重置成功",
        "auth.user_enabled.success": "用户已启用",
        "auth.user_disabled.success": "用户已禁用",
        "skill.deleted": "技能已删除",
        "integration.deleted": "集成已删除",
        "integration.templates_loaded": "内置模板加载成功",
        "document.deleted": "文档已删除",
        "baseline.rebuilt": "基线已重建",
        "report.deleted": "报告已删除",
        "report.batch_deleted": "成功删除 {count} 个报告",
        "model.deleted": "模型已删除",
        "model.default_updated": "默认模型已更新",
        "task.deleted": "任务已删除",
        "datasource.deleted": "数据源已删除",
        "datasource.connection_test_failed": "数据源连接测试失败",
        "host.connection_test_success": "SSH 连接成功",
        "host.connection_test_failed": "SSH 连接测试失败",
        "process.terminated": "进程 {pid} 已终止",
        "chat.session_deleted": "会话已删除",
        "chat.messages_cleared": "消息已清空",
        "metric.collection_triggered": "指标采集已触发",
        "evaluation.deleted": "评测记录已删除",
        "subscription.deleted": "订阅已删除",
        "notification.test_sent": "测试通知已发送",
        "config.deleted": "配置已删除",
        "host.deleted": "主机已删除",
        "bot.message_received": "已收到消息。",
        "bot.acknowledgement": "收到，正在分析你的需求。",
        "bot.approval.required": "需要确认：{tool}",
        "bot.approval.default_tool": "执行操作",
        "bot.approval.default_summary": "需要确认后才能继续执行该操作。",
        "bot.approval.default_risk_reason": "该操作存在潜在风险。",
        "bot.approval.risk_level": "风险级别：{level}",
        "bot.approval.risk_reason": "风险说明：{reason}",
        "bot.approval.id": "审批ID：{approval_id}",
        "bot.approval.plan": "执行计划：",
        "bot.approval.reply_approve": "继续执行请回复：批准 {approval_id}",
        "bot.approval.reply_reject": "拒绝执行请回复：拒绝 {approval_id}",
        "bot.approval.approve": "批准执行",
        "bot.approval.reject": "拒绝执行",
        "bot.approval.card_hint": "请在上面的卡片中确认是否执行该操作。",
        "bot.approval.card_failed": "需要确认的操作未能发送审批卡片，请稍后重试。",
        "bot.approval.failed": "审批处理失败，请稍后重试。",
        "bot.approval.approved": "已批准执行。",
        "bot.approval.rejected": "已拒绝执行该操作。",
        "bot.approval.processing": "审批处理中，请勿重复点击。",
        "bot.approval.received": "操作已接收。",
        "bot.approval.result_returned": "已批准执行，结果已返回。",
        "bot.approval.completed_with_error": "已批准执行，但处理过程中出现错误。",
        "bot.approval.more_required": "后续还有高风险操作，请继续在新卡片中确认。",
        "bot.approval.confirm_more": "已批准执行，请继续确认后续操作。",
        "bot.approval.no_result": "已批准执行，但当前没有生成新的回复内容。请查看后端日志确认工具是否执行。",
        "bot.approval.no_return_content": "已批准执行，但未生成可返回内容。",
        "bot.approval.continuing": "已批准执行，继续处理中。",
        "bot.no_content": "本次请求已处理，但没有生成可返回内容。请查看后端日志确认执行情况。",
        "bot.risk.low": "低",
        "bot.risk.medium": "中",
        "bot.risk.high": "高",
    },
    "en-US": {
        "request.failed": "Request failed",
        "request.validation_error": "Request validation failed",
        "request.validation.missing": "Field required",
        "request.validation.string_too_short": "String is too short",
        "request.validation.literal": "Input must be one of the allowed values",
        "request.validation.invalid": "Invalid input",
        "request.internal_error": "Internal server error",
        "request.invalid_origin": "Invalid request origin",
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
        "auth.timezone_invalid": "Invalid IANA time zone: {timezone}",
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
        "ai.session.error_safe": "The AI conversation failed. Try again later.",
        "terminal.connection_error": "The terminal connection failed. Try again later.",
        "ai.session.partial_timeout": "[The conversation timed out; the partial result is shown above]",
        "ai.session.timeout": "The AI conversation timed out after {seconds} seconds. Try again later or simplify the question.",
        "ai.approval.not_found": "The confirmation request does not exist or has expired",
        "ai.report.title": "{trigger_type} Inspection - {datasource}",
        "ai.report.missing_datasource": "Report generation failed because the datasource does not exist or was deleted.",
        "ai.report.failed": "Report generation failed without producing valid content.",
        "ai.report.footer.generated": "Generated by the DBClaw intelligent diagnostics engine",
        "ai.report.footer.datasource": "Datasource: {datasource} ({db_type}) | Generated: {generated_at}",
        "alert.connection_failed.title": "Database connection failed",
        "alert.connection_failed.status": "Database connection failed",
        "alert.connection_recovered.status": "Database connection restored",
        "alert.threshold.title": "{metric} threshold alert",
        "alert.baseline.title": "{metric} baseline deviation alert",
        "alert.triggered": "Alert triggered",
        "alert.ai.model_not_configured": "AI alert evaluation failed: no AI alert model is configured",
        "alert.ai.evaluation_failed": "AI alert evaluation failed. Check the service logs",
        "alert.ai.severity_mismatch": "The AI severity {actual} does not match the template severity {expected}",
        "alert.diagnosis.timeout_background": "Diagnosis timed out and will continue in the background...",
        "alert.diagnosis.failed": "Diagnosis failed. Try again later",
        "alert.field.status": "Status",
        "alert.field.metric": "Metric",
        "alert.field.threshold": "Threshold",
        "alert.field.reason": "Reason",
        "alert.field.error_detail": "Error details",
        "alert.field.previous_error": "Previous error",
        "alert.field.alert_type": "Alert type",
        "alert.field.severity": "Severity",
        "alert.field.alert_time": "Alert time",
        "alert.field.recovery_time": "Recovery time",
        "alert.field.recovered_value": "Recovered value",
        "alert.field.ai_summary": "AI summary",
        "alert.value.unknown": "Unknown",
        "notification.datasource.unknown": "Unknown datasource",
        "notification.alert.title": "[{severity}] {datasource} alert",
        "notification.connection_failed.title": "[{severity}] {datasource} database connection failed",
        "notification.recovery.title": "[Resolved] {datasource} alert resolved",
        "notification.connection_recovered.title": "[Resolved] {datasource} database connection restored",
        "auth.logout.success": "Signed out",
        "auth.logout_all.success": "All sessions revoked",
        "auth.password_changed.success": "Password changed successfully",
        "auth.user_deleted.success": "User deleted",
        "auth.password_reset.success": "Password reset successfully",
        "auth.user_enabled.success": "User enabled",
        "auth.user_disabled.success": "User disabled",
        "skill.deleted": "Skill deleted",
        "integration.deleted": "Integration deleted",
        "integration.templates_loaded": "Built-in templates loaded",
        "document.deleted": "Document deleted",
        "baseline.rebuilt": "Baseline rebuilt",
        "report.deleted": "Report deleted",
        "report.batch_deleted": "Deleted {count} reports",
        "model.deleted": "Model deleted",
        "model.default_updated": "Default model updated",
        "task.deleted": "Task deleted",
        "datasource.deleted": "Datasource deleted",
        "datasource.connection_test_failed": "Datasource connection test failed",
        "host.connection_test_success": "SSH connection successful",
        "host.connection_test_failed": "SSH connection test failed",
        "process.terminated": "Process {pid} terminated",
        "chat.session_deleted": "Conversation deleted",
        "chat.messages_cleared": "Messages cleared",
        "metric.collection_triggered": "Metric collection triggered",
        "evaluation.deleted": "Evaluation record deleted",
        "subscription.deleted": "Subscription deleted",
        "notification.test_sent": "Test notification sent",
        "config.deleted": "Configuration deleted",
        "host.deleted": "Host deleted",
        "bot.message_received": "Message received.",
        "bot.acknowledgement": "Got it. I’m analyzing your request.",
        "bot.approval.required": "Confirmation required: {tool}",
        "bot.approval.default_tool": "Run operation",
        "bot.approval.default_summary": "Confirmation is required before this operation can continue.",
        "bot.approval.default_risk_reason": "This operation carries potential risk.",
        "bot.approval.risk_level": "Risk level: {level}",
        "bot.approval.risk_reason": "Risk details: {reason}",
        "bot.approval.id": "Approval ID: {approval_id}",
        "bot.approval.plan": "Execution plan:",
        "bot.approval.reply_approve": "To continue, reply: approve {approval_id}",
        "bot.approval.reply_reject": "To reject, reply: reject {approval_id}",
        "bot.approval.approve": "Approve",
        "bot.approval.reject": "Reject",
        "bot.approval.card_hint": "Use the card above to approve or reject this operation.",
        "bot.approval.card_failed": "The approval card could not be sent. Please try again later.",
        "bot.approval.failed": "Approval processing failed. Please try again later.",
        "bot.approval.approved": "Execution approved.",
        "bot.approval.rejected": "Execution rejected.",
        "bot.approval.processing": "Approval is already being processed. Do not click again.",
        "bot.approval.received": "Action received.",
        "bot.approval.result_returned": "Execution approved. The result has been returned.",
        "bot.approval.completed_with_error": "Execution was approved, but an error occurred during processing.",
        "bot.approval.more_required": "Another high-risk operation requires confirmation. Use the new card to continue.",
        "bot.approval.confirm_more": "Execution approved. Confirm the next operation to continue.",
        "bot.approval.no_result": "Execution was approved, but no new response was generated. Check the backend logs to confirm tool execution.",
        "bot.approval.no_return_content": "Execution was approved, but no content was generated for return.",
        "bot.approval.continuing": "Execution approved and processing continues.",
        "bot.no_content": "The request was processed, but no response content was generated. Check the backend logs for details.",
        "bot.risk.low": "Low",
        "bot.risk.medium": "Medium",
        "bot.risk.high": "High",
    },
}

def normalize_locale(value: str | None) -> str | None:
    if not value:
        return None
    normalized = value.strip().replace("_", "-").lower()
    return _ALIASES.get(normalized)


def normalize_timezone(value: str | None) -> str | None:
    """Return a canonical IANA time-zone name, or ``None`` when invalid."""
    if not value:
        return None
    candidate = value.strip()
    if not candidate:
        return None
    try:
        return ZoneInfo(candidate).key
    except (ZoneInfoNotFoundError, ValueError):
        return None


def set_system_defaults(locale: str | None = None, timezone: str | None = None) -> tuple[str, str]:
    """Update process-local defaults after persisted configuration changes."""
    global _system_default_locale, _system_default_timezone
    _system_default_locale = normalize_locale(locale) or DEFAULT_LOCALE
    _system_default_timezone = normalize_timezone(timezone) or DEFAULT_TIMEZONE
    return _system_default_locale, _system_default_timezone


def get_system_defaults() -> tuple[str, str]:
    return _system_default_locale, _system_default_timezone


def resolve_preferences(
    *,
    locale: str | None = None,
    timezone: str | None = None,
    fallback_locale: str | None = None,
    fallback_timezone: str | None = None,
) -> tuple[str, str]:
    """Resolve a complete locale/time-zone pair for background work."""
    return (
        normalize_locale(locale) or normalize_locale(fallback_locale) or _system_default_locale,
        normalize_timezone(timezone) or normalize_timezone(fallback_timezone) or _system_default_timezone,
    )


async def resolve_background_preferences(
    db,
    *,
    locale: str | None = None,
    timezone: str | None = None,
) -> tuple[str, str]:
    """Resolve background preferences with persisted system defaults."""
    fallback_locale = _system_default_locale
    fallback_timezone = _system_default_timezone
    try:
        from sqlalchemy import select
        from backend.models.system_config import SystemConfig

        result = await db.execute(
            select(SystemConfig).where(
                SystemConfig.key.in_(("i18n.default_locale", "i18n.default_timezone")),
                SystemConfig.is_active == True,
            )
        )
        values = {item.key: item.value for item in result.scalars().all()}
        fallback_locale = values.get("i18n.default_locale") or fallback_locale
        fallback_timezone = values.get("i18n.default_timezone") or fallback_timezone
    except Exception:
        # Startup migrations and lightweight test doubles may not expose the
        # system_config table. Deterministic built-in defaults remain safe.
        pass
    return resolve_preferences(
        locale=locale,
        timezone=timezone,
        fallback_locale=fallback_locale,
        fallback_timezone=fallback_timezone,
    )


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
    return _system_default_locale, "default"


def get_request_locale(request: Request | None) -> str:
    if request is None:
        return DEFAULT_LOCALE
    return normalize_locale(getattr(request.state, "locale", None)) or DEFAULT_LOCALE


def get_active_locale() -> str:
    """Return the current request locale, including account-preference updates."""
    return _active_locale.get()


def set_active_locale(locale: str | None):
    """Set the request-local locale and return a token suitable for reset."""
    return _active_locale.set(normalize_locale(locale) or DEFAULT_LOCALE)


def reset_active_locale(token) -> None:
    _active_locale.reset(token)


def apply_user_locale(request: Request, locale: str | None) -> None:
    """Use the account locale unless the caller sent an explicit app locale."""
    if getattr(request.state, "locale_source", "default") != "explicit":
        normalized = normalize_locale(locale)
        if normalized:
            request.state.locale = normalized
            request.state.locale_source = "account"
            set_active_locale(normalized)


def translate(locale: str, key: str, params: dict[str, Any] | None = None) -> str:
    normalized = normalize_locale(locale)
    if normalized is None:
        _I18N_COUNTERS["invalid_locale"] += 1
        logger.warning("i18n_invalid_locale locale=%r key=%s", locale, key)
        normalized = _system_default_locale
    template = MESSAGES.get(normalized, MESSAGES[DEFAULT_LOCALE]).get(key)
    if template is None:
        _I18N_COUNTERS["missing_key"] += 1
        logger.warning("i18n_missing_key locale=%s key=%s", normalized, key)
        template = MESSAGES[DEFAULT_LOCALE].get(key, key)
    try:
        return template.format(**(params or {}))
    except (KeyError, ValueError):
        _I18N_COUNTERS["format_error"] += 1
        logger.warning("i18n_format_error locale=%s key=%s params=%r", normalized, key, params)
        return template


def get_i18n_metrics() -> dict[str, int]:
    """Return process-local counters suitable for health/metrics reporting."""
    return dict(_I18N_COUNTERS)


def message_payload(
    key: str,
    params: dict[str, Any] | None = None,
    *,
    locale: str | None = None,
    **extra: Any,
) -> dict[str, Any]:
    """Build a backward-compatible localized success-message response."""
    resolved_locale = normalize_locale(locale) or get_active_locale()
    values = params or {}
    return {
        "message": translate(resolved_locale, key, values),
        "message_code": key,
        "params": values,
        **extra,
    }
