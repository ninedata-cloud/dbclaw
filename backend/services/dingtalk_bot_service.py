import asyncio
import logging
import re
from datetime import datetime
from typing import Any, Awaitable, Callable, Optional

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.chat_channel_binding import ChatChannelBinding
from backend.models.chat_event_dedup import ChatEventDedup
from backend.models.diagnostic_session import DiagnosticSession
from backend.models.integration import Integration
from backend.models.integration_bot_binding import IntegrationBotBinding
from backend.models.soft_delete import alive_filter
from backend.services import config_service
from backend.services.chat_orchestration_service import prepare_user_turn, process_stream_events, resolve_pending_approval
from backend.services.feishu_service import format_reply_text
from backend.utils.datetime_helper import now

logger = logging.getLogger(__name__)

PENDING_APPROVALS: dict[int, dict[str, dict[str, Any]]] = {}
BOT_HISTORY_WINDOW_HOURS = 24
_MESSAGE_LOCKS: dict[str, asyncio.Lock] = {}
DINGTALK_CLIENT_ID_KEY = "dingtalk_client_id"
DINGTALK_CLIENT_SECRET_KEY = "dingtalk_client_secret"

_CONFIG_VAR_PATTERNS = {
    "client_id": [
        re.compile(r'^\s*CLIENT_ID\s*=\s*(["\'])(.*?)\1\s*$', re.MULTILINE),
        re.compile(r'^\s*APP_KEY\s*=\s*(["\'])(.*?)\1\s*$', re.MULTILINE),
    ],
    "client_secret": [
        re.compile(r'^\s*CLIENT_SECRET\s*=\s*(["\'])(.*?)\1\s*$', re.MULTILINE),
        re.compile(r'^\s*APP_SECRET\s*=\s*(["\'])(.*?)\1\s*$', re.MULTILINE),
    ],
}

TOOL_LABELS = {
    "Bash": "执行终端命令",
    "Edit": "修改文件",
    "Write": "写入文件",
    "NotebookEdit": "修改 Notebook",
    "TaskStop": "停止任务",
}

RISK_LEVEL_LABELS = {
    "low": "低",
    "medium": "中",
    "high": "高",
}


def _extract_dingtalk_bot_config(integration: Integration | None) -> dict[str, str]:
    if not integration or not integration.code:
        return {"client_id": "", "client_secret": ""}

    code = integration.code
    config = {"client_id": "", "client_secret": ""}
    for key, patterns in _CONFIG_VAR_PATTERNS.items():
        for pattern in patterns:
            match = pattern.search(code)
            if match:
                config[key] = match.group(2)
                break
    return config


async def get_dingtalk_bot_credentials(db: AsyncSession, integration: Integration | None = None) -> dict[str, str]:
    """优先从系统参数读取，兼容旧版 Integration 代码内配置。"""
    client_id = str(await config_service.get_config(db, DINGTALK_CLIENT_ID_KEY, "") or "").strip()
    client_secret = str(await config_service.get_config(db, DINGTALK_CLIENT_SECRET_KEY, "") or "").strip()
    if client_id and client_secret:
        return {"client_id": client_id, "client_secret": client_secret}

    # 向后兼容：旧版本仍可能把凭据写在 Integration 代码顶部
    legacy_config = _extract_dingtalk_bot_config(integration)
    return {
        "client_id": str(legacy_config.get("client_id") or "").strip(),
        "client_secret": str(legacy_config.get("client_secret") or "").strip(),
    }


def _extract_text_from_message(message: dict[str, Any]) -> str:
    text = message.get("text")
    if isinstance(text, dict):
        content = str(text.get("content") or "").strip()
        if content:
            return content
    if isinstance(text, str):
        return text.strip()
    return ""


def _approval_command(text: str) -> tuple[str, str] | None:
    normalized = (text or "").strip()
    if not normalized:
        return None
    parts = normalized.split(maxsplit=1)
    if len(parts) != 2:
        return None
    action_text, approval_id = parts
    if action_text in {"批准", "同意", "approve"}:
        return "approved", approval_id.strip()
    if action_text in {"拒绝", "驳回", "reject"}:
        return "rejected", approval_id.strip()
    return None


def _tool_display_name(tool_name: str | None) -> str:
    if not tool_name:
        return "执行操作"
    return TOOL_LABELS.get(tool_name, tool_name)


def _build_approval_prompt(event_obj: dict[str, Any]) -> str:
    approval_id = str(event_obj.get("approval_id") or "")
    summary = str(event_obj.get("summary") or "需要确认后才能继续执行该操作。").strip()
    risk_level = RISK_LEVEL_LABELS.get(str(event_obj.get("risk_level") or "high"), "高")
    risk_reason = str(event_obj.get("risk_reason") or "该操作存在潜在风险。").strip()
    tool_name = _tool_display_name(str(event_obj.get("tool_name") or ""))
    plan_markdown = format_reply_text(str(event_obj.get("plan_markdown") or "").strip())

    lines = [
        f"需要确认：{tool_name}",
        summary,
        f"风险级别：{risk_level}",
        f"风险说明：{risk_reason}",
        f"审批ID：{approval_id}",
    ]
    if plan_markdown:
        lines.extend([
            "",
            "执行计划：",
            plan_markdown,
        ])
    lines.extend([
        "",
        f"继续执行请回复：批准 {approval_id}",
        f"拒绝执行请回复：拒绝 {approval_id}",
    ])
    return "\n".join(line for line in lines if line is not None).strip()


def _finalize_reply_text(chunks: list[str]) -> str:
    return format_reply_text("".join(chunks))


def _summarize_reply_errors(errors: list[str]) -> str:
    rendered: list[str] = []
    seen: set[str] = set()
    for raw in errors:
        text = format_reply_text(str(raw or "").strip())
        if not text or text in seen:
            continue
        seen.add(text)
        rendered.append(text)
    return "\n\n".join(rendered[:3])


def _sender_user_id(message: dict[str, Any]) -> str:
    return str(message.get("senderStaffId") or message.get("senderId") or "").strip()


def _message_lock_key(message: dict[str, Any]) -> str:
    return "|".join([
        str(message.get("conversationId") or "").strip(),
        _sender_user_id(message),
    ])


class DingTalkBotService:
    @staticmethod
    async def get_bot_integration(db: AsyncSession) -> Optional[Integration]:
        result = await db.execute(
            select(Integration).where(
                Integration.integration_id == "builtin_dingtalk_bot",
                Integration.is_enabled == True,
                alive_filter(Integration),
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def ensure_bot_binding(db: AsyncSession, integration: Integration | None = None) -> Optional[IntegrationBotBinding]:
        integration = integration or await DingTalkBotService.get_bot_integration(db)
        if not integration:
            return None

        result = await db.execute(
            select(IntegrationBotBinding).where(IntegrationBotBinding.code == "dingtalk_bot")
        )
        binding = result.scalar_one_or_none()
        if binding:
            if binding.integration_id != integration.id:
                binding.integration_id = integration.id
                await db.commit()
                await db.refresh(binding)
            return binding

        binding = IntegrationBotBinding(
            integration_id=integration.id,
            code="dingtalk_bot",
            name="钉钉机器人",
            enabled=False,
            params={},
        )
        db.add(binding)
        await db.commit()
        await db.refresh(binding)
        return binding

    @staticmethod
    async def update_binding_status(db: AsyncSession, *, login_status: str, last_error: str = "") -> None:
        integration = await DingTalkBotService.get_bot_integration(db)
        binding = await DingTalkBotService.ensure_bot_binding(db, integration=integration)
        if not binding:
            return
        params = dict(binding.params or {})
        params["login_status"] = login_status
        params["last_error"] = last_error
        binding.params = params
        if login_status == "confirmed":
            binding.is_enabled = True
        await db.commit()

    @staticmethod
    async def is_duplicate_event(db: AsyncSession, *, event_id: str | None, message_id: str | None, event_type: str) -> bool:
        if not event_id and not message_id:
            return False
        result = await db.execute(
            select(ChatEventDedup)
            .where(
                ChatEventDedup.channel_type == "dingtalk",
                ChatEventDedup.event_type == event_type,
                or_(
                    ChatEventDedup.external_event_id == event_id if event_id else False,
                    ChatEventDedup.external_message_id == message_id if message_id else False,
                ),
            )
            .order_by(ChatEventDedup.id.desc())
            .limit(1)
        )
        return result.scalars().first() is not None

    @staticmethod
    async def mark_event_processed(db: AsyncSession, *, event_id: str | None, message_id: str | None, event_type: str) -> None:
        if await DingTalkBotService.is_duplicate_event(db, event_id=event_id, message_id=message_id, event_type=event_type):
            return
        db.add(ChatEventDedup(
            channel_type="dingtalk",
            external_event_id=event_id,
            external_message_id=message_id,
            event_type=event_type,
        ))
        await db.commit()

    @staticmethod
    async def get_or_create_binding(
        db: AsyncSession,
        *,
        conversation_id: str,
        user_id: str | None,
        integration: Integration | None,
        title: str,
    ) -> ChatChannelBinding:
        result = await db.execute(
            select(ChatChannelBinding).where(
                ChatChannelBinding.channel_type == "dingtalk",
                ChatChannelBinding.external_chat_id == conversation_id,
                ChatChannelBinding.external_user_id == user_id,
            )
        )
        binding = result.scalar_one_or_none()
        if binding:
            binding.last_message_at = now()
            await db.commit()
            return binding

        session = DiagnosticSession(user_id=None, title=title)
        db.add(session)
        await db.commit()
        await db.refresh(session)

        binding = ChatChannelBinding(
            channel_type="dingtalk",
            external_chat_id=conversation_id,
            external_user_id=user_id,
            session_id=session.id,
            integration_id=integration.id if integration else None,
            last_message_at=now(),
        )
        db.add(binding)
        await db.commit()
        await db.refresh(binding)
        return binding

    @staticmethod
    async def _handle_approval_command(
        db: AsyncSession,
        *,
        binding: ChatChannelBinding,
        text: str,
        send_reply: Callable[[str], Awaitable[None]],
    ) -> bool:
        command = _approval_command(text)
        if not command:
            return False

        action, approval_id = command
        chunks: list[str] = []
        errors: list[str] = []
        approval_prompts: list[str] = []

        async def on_event(event_obj: dict[str, Any]) -> None:
            event_type_local = event_obj.get("type")
            # 忽略 thinking 相关事件
            if event_type_local in ("thinking_start", "thinking_phase", "thinking_complete"):
                return
            if event_type_local == "content":
                chunks.append(event_obj.get("content", ""))
            elif event_type_local == "approval_request":
                approval_prompts.append(_build_approval_prompt(event_obj))
            elif event_type_local == "error":
                error_text = str(event_obj.get("content") or event_obj.get("message") or "").strip()
                if error_text:
                    errors.append(error_text)

        try:
            result = await resolve_pending_approval(
                db,
                session_id=binding.session_id,
                approval_id=approval_id,
                action=action,
                comment=None,
                user_id=None,
                pending_approvals=PENDING_APPROVALS,
                on_event=on_event,
            )
        except Exception as exc:
            await send_reply(f"审批处理失败：{str(exc)}")
            return True

        if result["status"] == "rejected":
            await send_reply("已拒绝执行该操作。")
            return True

        if approval_prompts:
            await send_reply(approval_prompts[-1])
            return True

        error_text = _summarize_reply_errors(errors)
        if error_text:
            await send_reply(error_text)
            return True

        await send_reply(_finalize_reply_text(chunks) or "已批准执行。")
        return True

    @staticmethod
    async def handle_message(
        db: AsyncSession,
        *,
        message: dict[str, Any],
        send_reply: Callable[[str], Awaitable[None]],
    ) -> dict[str, Any]:
        text = _extract_text_from_message(message)
        conversation_id = str(message.get("conversationId") or "").strip()
        sender_user_id = _sender_user_id(message)
        message_id = str(message.get("msgId") or message.get("messageId") or "").strip()
        conversation_type = str(message.get("conversationType") or "").strip()
        is_in_at_list = message.get("isInAtList")
        event_type = "dingtalk.message"

        if not conversation_id or not sender_user_id or not text:
            return {"ok": True, "ignored": True}

        if conversation_type == "2" and is_in_at_list is False and not _approval_command(text):
            return {"ok": True, "ignored": True}

        if await DingTalkBotService.is_duplicate_event(db, event_id=message_id or None, message_id=message_id or None, event_type=event_type):
            return {"ok": True, "duplicate": True}

        integration = await DingTalkBotService.get_bot_integration(db)
        title = str(message.get("conversationTitle") or "").strip()
        if not title:
            title = "钉钉会话" if conversation_type != "2" else f"钉钉群会话 {conversation_id}"

        binding = await DingTalkBotService.get_or_create_binding(
            db,
            conversation_id=conversation_id,
            user_id=sender_user_id,
            integration=integration,
            title=title,
        )

        lock = _MESSAGE_LOCKS.setdefault(_message_lock_key(message), asyncio.Lock())
        async with lock:
            handled = await DingTalkBotService._handle_approval_command(
                db,
                binding=binding,
                text=text,
                send_reply=send_reply,
            )
            if handled:
                await DingTalkBotService.mark_event_processed(
                    db,
                    event_id=message_id or None,
                    message_id=message_id or None,
                    event_type=event_type,
                )
                return {"ok": True, "session_id": binding.session_id, "approval": True}

            messages, effective_datasource_id, effective_host_id, model_id, kb_ids, knowledge_context, skill_authorizations = await prepare_user_turn(
                db,
                session_id=binding.session_id,
                user_id=None,
                user_message=text,
                attachments=[],
                payload_datasource_id=None,
                model_id=None,
                history_window_hours=BOT_HISTORY_WINDOW_HOURS,
            )

            chunks: list[str] = []
            errors: list[str] = []
            approval_prompts: list[str] = []

            async def on_event(event_obj: dict[str, Any]) -> None:
                event_type_local = event_obj.get("type")
                # 忽略 thinking 相关事件
                if event_type_local in ("thinking_start", "thinking_phase", "thinking_complete"):
                    return
                if event_type_local == "content":
                    chunks.append(event_obj.get("content", ""))
                elif event_type_local == "approval_request":
                    approval_prompts.append(_build_approval_prompt(event_obj))
                elif event_type_local == "error":
                    error_text = str(event_obj.get("content") or event_obj.get("message") or "").strip()
                    if error_text:
                        errors.append(error_text)

            await process_stream_events(
                db,
                session_id=binding.session_id,
                user_id=None,
                messages=messages,
                datasource_id=effective_datasource_id,
                model_id=model_id,
                kb_ids=kb_ids,
                knowledge_context=knowledge_context,
                skill_authorizations=skill_authorizations,
                pending_approvals=PENDING_APPROVALS,
                on_event=on_event,
                history_window_hours=BOT_HISTORY_WINDOW_HOURS,
            )

            await DingTalkBotService.mark_event_processed(
                db,
                event_id=message_id or None,
                message_id=message_id or None,
                event_type=event_type,
            )

            if approval_prompts:
                await send_reply(approval_prompts[-1])
                return {"ok": True, "session_id": binding.session_id, "approval": True}

            error_text = _summarize_reply_errors(errors)
            if error_text:
                await send_reply(error_text)
                return {"ok": True, "session_id": binding.session_id, "error": True}

            await send_reply(_finalize_reply_text(chunks) or "已收到消息。")
            return {"ok": True, "session_id": binding.session_id}
