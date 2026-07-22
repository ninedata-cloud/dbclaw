import logging
import re
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.chat_channel_binding import ChatChannelBinding
from backend.models.chat_event_dedup import ChatEventDedup
from backend.models.diagnostic_session import ChatMessage, DiagnosticSession
from backend.models.integration import Integration
from backend.models.integration_bot_binding import IntegrationBotBinding
from backend.models.soft_delete import alive_filter, alive_select
from backend.services.chat_orchestration_service import prepare_user_turn, process_stream_events, resolve_pending_approval
from backend.services.feishu_service import feishu_service, format_reply_text
from backend.utils.datetime_helper import now
from backend.i18n.locale import resolve_background_preferences, translate

logger = logging.getLogger(__name__)

PENDING_APPROVALS: dict[int, dict[str, dict[str, Any]]] = {}
PROCESSING_APPROVALS: set[str] = set()
BOT_HISTORY_WINDOW_HOURS = 24

_CONFIG_VAR_PATTERNS = {
    "app_id": re.compile(r'^\s*APP_ID\s*=\s*(["\'])(.*?)\1\s*$', re.MULTILINE),
    "app_secret": re.compile(r'^\s*APP_SECRET\s*=\s*(["\'])(.*?)\1\s*$', re.MULTILINE),
    "signing_secret": re.compile(r'^\s*SIGNING_SECRET\s*=\s*(["\'])(.*?)\1\s*$', re.MULTILINE),
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


def _toast_response(content: str, toast_type: str = "info") -> dict[str, Any]:
    return {
        "toast": {
            "type": toast_type,
            "content": content,
            "i18n": {
                "zh_cn": content,
                "en_us": content,
            },
        }
    }


def _extract_feishu_bot_config(integration: Integration | None) -> dict[str, str]:
    """从 builtin_feishu_bot 的 Integration 代码中解析飞书凭据。

    约定在代码中定义：
    - APP_ID = "..."
    - APP_SECRET = "..."
    - SIGNING_SECRET = "..."

    只做字符串常量解析，不执行用户代码。
    """

    if not integration or not integration.code:
        return {"app_id": "", "app_secret": "", "signing_secret": ""}

    code = integration.code
    config: dict[str, str] = {"app_id": "", "app_secret": "", "signing_secret": ""}

    for key, pattern in _CONFIG_VAR_PATTERNS.items():
        match = pattern.search(code)
        if match:
            config[key] = match.group(2)

    return config


def _tool_display_name(tool_name: str | None, locale: str) -> str:
    if not tool_name:
        return translate(locale, "bot.approval.default_tool")
    return TOOL_LABELS.get(tool_name, tool_name) if locale == "zh-CN" else tool_name


def _normalize_card_markdown(text: str, locale: str = "zh-CN") -> str:
    content = (text or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    if not content:
        return ""

    content = re.sub(
        r"```(\w+)?\n([\s\S]*?)\n```",
        lambda match: _replace_card_code_block(match, locale),
        content,
    )
    content = re.sub(r"\n{3,}", "\n\n", content)
    return content


def _replace_card_code_block(match: re.Match[str], locale: str = "zh-CN") -> str:
    language = (match.group(1) or "").strip()
    code = (match.group(2) or "").rstrip("\n")
    label = "代码块" if locale == "zh-CN" else "Code block"
    title = f"**{label}{f'（{language}）' if language and locale == 'zh-CN' else f' ({language})' if language else ''}**"
    code_lines = code.splitlines() or [""]
    rendered = "\n".join(f"    {line}" if line else "    " for line in code_lines)
    return f"{title}\n{rendered}"


def _build_approval_card(event_obj: dict[str, Any], session_id: int, locale: str = "zh-CN") -> dict[str, Any]:
    approval_id = str(event_obj.get("approval_id") or "")
    tool_name = str(event_obj.get("tool_name") or "")
    summary = str(event_obj.get("summary") or translate(locale, "bot.approval.default_summary"))
    plan_markdown = _normalize_card_markdown(str(event_obj.get("plan_markdown") or ""), locale)
    risk_code = str(event_obj.get("risk_level") or "high")
    risk_level = translate(locale, f"bot.risk.{risk_code}")
    risk_reason = str(event_obj.get("risk_reason") or translate(locale, "bot.approval.default_risk_reason"))
    tool_label = _tool_display_name(tool_name, locale)

    elements: list[dict[str, Any]] = [
        {
            "tag": "div",
            "text": {
                "tag": "lark_md",
                "content": "\n".join([
                    summary,
                    f"**{translate(locale, 'bot.approval.risk_level', {'level': risk_level})}**",
                    f"**{translate(locale, 'bot.approval.risk_reason', {'reason': risk_reason})}**",
                ]),
            },
        }
    ]
    if plan_markdown:
        elements.extend([
            {"tag": "hr"},
            {
                "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": f"**{translate(locale, 'bot.approval.plan')}**",
                },
            },
            {
                "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": plan_markdown,
                },
            },
        ])

    elements.append(
        {
            "tag": "action",
            "actions": [
                {
                    "tag": "button",
                    "text": {"tag": "plain_text", "content": translate(locale, "bot.approval.approve")},
                    "type": "primary",
                    "value": {
                        "session_id": str(session_id),
                        "approval_id": approval_id,
                        "action": "approved",
                    },
                },
                {
                    "tag": "button",
                    "text": {"tag": "plain_text", "content": translate(locale, "bot.approval.reject")},
                    "type": "default",
                    "value": {
                        "session_id": str(session_id),
                        "approval_id": approval_id,
                        "action": "rejected",
                    },
                },
            ],
        }
    )

    return {
        "config": {"wide_screen_mode": True},
        "header": {
            "template": "orange",
            "title": {"tag": "plain_text", "content": translate(locale, "bot.approval.required", {"tool": tool_label})},
        },
        "elements": elements,
    }


def _finalize_reply_text(chunks: list[str]) -> str:
    return format_reply_text("".join(chunks))


def _create_reply_state() -> dict[str, Any]:
    return {
        "chunks": [],
        "errors": [],
        "approval_sent": False,
    }


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


async def _reply_normal_message(
    *,
    text: str,
    app_id: str,
    app_secret: str,
    message_id: str | None,
    open_id: str | None,
    chat_id: str | None,
) -> None:
    if not text:
        return
    await feishu_service.reply_text(
        text,
        message_id=message_id,
        open_id=open_id,
        chat_id=chat_id,
        app_id=app_id,
        app_secret=app_secret,
    )


def _build_reply_event_handler(
    *,
    session_id: int,
    app_id: str,
    app_secret: str,
    message_id: str | None,
    open_id: str | None,
    chat_id: str | None,
    locale: str = "zh-CN",
) -> tuple[dict[str, Any], Any]:
    state = _create_reply_state()

    async def on_event(event_obj: dict[str, Any]) -> None:
        event_type_local = event_obj.get("type")
        # 忽略 thinking 相关事件
        if event_type_local in ("thinking_start", "thinking_phase", "thinking_complete"):
            return
        if event_type_local == "content":
            state["chunks"].append(event_obj.get("content", ""))
            return
        if event_type_local == "approval_request":
            state["approval_sent"] = True
            try:
                await feishu_service.send_interactive_card(
                    _build_approval_card(event_obj, session_id, locale),
                    message_id=message_id,
                    open_id=open_id,
                    chat_id=chat_id,
                    app_id=app_id,
                    app_secret=app_secret,
                )
            except Exception:
                logger.exception(
                    "Failed to send Feishu approval card: session_id=%s approval_id=%s",
                    session_id,
                    event_obj.get("approval_id"),
                )
                state["errors"].append(translate(locale, "bot.approval.card_failed"))
            return
        if event_type_local == "tool_call":
            logger.info("Running tool after Feishu approval: session_id=%s tool=%s args=%s", session_id, event_obj.get("tool_name"), event_obj.get("tool_args"))
        elif event_type_local == "tool_result":
            logger.info("Tool completed after Feishu approval: session_id=%s tool=%s", session_id, event_obj.get("tool_name"))
        elif event_type_local == "error":
            error_text = str(event_obj.get("content") or event_obj.get("message") or "").strip()
            if error_text:
                state["errors"].append(error_text)
                logger.error("Feishu session processing failed: session_id=%s error=%s", session_id, error_text)

    return state, on_event


def _build_followup_event_handler(
    *,
    session_id: int,
    app_id: str,
    app_secret: str,
    message_id: str | None,
    open_id: str | None,
    chat_id: str | None,
    locale: str = "zh-CN",
) -> tuple[dict[str, Any], Any]:
    return _build_reply_event_handler(
        session_id=session_id,
        app_id=app_id,
        app_secret=app_secret,
        message_id=message_id,
        open_id=open_id,
        chat_id=chat_id,
        locale=locale,
    )


async def _get_latest_approval_request(db: AsyncSession, session_id: int, approval_id: str) -> ChatMessage | None:
    result = await db.execute(
        alive_select(ChatMessage)
        .where(
            ChatMessage.session_id == session_id,
            ChatMessage.role == "approval_request",
            ChatMessage.content.contains(approval_id),
        )
        .order_by(ChatMessage.created_at.desc())
    )
    return result.scalars().first()


class FeishuBotService:
    @staticmethod
    async def get_bot_integration(db: AsyncSession) -> Optional[Integration]:
        result = await db.execute(
            select(Integration).where(
                Integration.integration_id == "builtin_feishu_bot",
                Integration.is_enabled == True,
                alive_filter(Integration),
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def ensure_bot_binding(db: AsyncSession, integration: Integration | None = None) -> Optional[IntegrationBotBinding]:
        integration = integration or await FeishuBotService.get_bot_integration(db)
        if not integration:
            return None

        result = await db.execute(
            select(IntegrationBotBinding).where(IntegrationBotBinding.code == "feishu_bot")
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
            code="feishu_bot",
            name="飞书机器人",
            enabled=False,
            params={},
        )
        db.add(binding)
        await db.commit()
        await db.refresh(binding)
        return binding

    @staticmethod
    async def update_binding_status(db: AsyncSession, *, login_status: str, last_error: str = "") -> None:
        integration = await FeishuBotService.get_bot_integration(db)
        binding = await FeishuBotService.ensure_bot_binding(db, integration=integration)
        if not binding:
            return

        params = dict(binding.params or {})
        params["login_status"] = login_status
        params["last_error"] = last_error
        binding.params = params
        binding.is_enabled = login_status == "confirmed"
        await db.commit()

    @staticmethod
    async def is_duplicate_event(db: AsyncSession, *, event_id: str | None, message_id: str | None, event_type: str) -> bool:
        if not event_id and not message_id:
            return False
        result = await db.execute(
            select(ChatEventDedup)
            .where(
                ChatEventDedup.channel_type == "feishu",
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
        if await FeishuBotService.is_duplicate_event(db, event_id=event_id, message_id=message_id, event_type=event_type):
            return
        record = ChatEventDedup(
            channel_type="feishu",
            external_event_id=event_id,
            external_message_id=message_id,
            event_type=event_type,
        )
        db.add(record)
        await db.commit()

    @staticmethod
    async def get_or_create_binding(
        db: AsyncSession,
        *,
        chat_id: str,
        user_open_id: str | None,
        integration: Integration | None,
    ) -> ChatChannelBinding:
        result = await db.execute(
            select(ChatChannelBinding).where(
                ChatChannelBinding.channel_type == "feishu",
                ChatChannelBinding.external_chat_id == chat_id,
                ChatChannelBinding.external_user_id == user_open_id,
            )
        )
        binding = result.scalar_one_or_none()
        if binding:
            binding.last_message_at = now()
            await db.commit()
            return binding

        locale, _timezone = await resolve_background_preferences(db)
        session = DiagnosticSession(
            user_id=None,
            title="飞书会话",
            default_locale=locale,
        )
        db.add(session)
        await db.commit()
        await db.refresh(session)

        binding = ChatChannelBinding(
            channel_type="feishu",
            external_chat_id=chat_id,
            external_user_id=user_open_id,
            session_id=session.id,
            integration_id=integration.id if integration else None,
            last_message_at=now(),
        )
        db.add(binding)
        await db.commit()
        await db.refresh(binding)
        return binding

    @staticmethod
    async def handle_message_event(db: AsyncSession, payload: dict[str, Any]) -> dict[str, Any]:
        header = payload.get("header") or {}
        event = payload.get("event") or {}
        message = event.get("message") or {}
        sender = event.get("sender") or {}
        chat_id = message.get("chat_id")
        message_id = message.get("message_id")
        event_id = header.get("event_id")
        event_type = header.get("event_type") or "im.message.receive_v1"
        content = message.get("content")
        if isinstance(content, str):
            try:
                content = __import__("json").loads(content)
            except Exception:
                content = {"text": content}
        text = (content or {}).get("text", "").strip()
        if not chat_id or not text:
            return {"ok": True, "ignored": True}

        if await FeishuBotService.is_duplicate_event(db, event_id=event_id, message_id=message_id, event_type=event_type):
            return {"ok": True, "duplicate": True}

        integration = await FeishuBotService.get_bot_integration(db)
        sender_open_id = (sender.get("sender_id") or {}).get("open_id")
        binding = await FeishuBotService.get_or_create_binding(
            db,
            chat_id=chat_id,
            user_open_id=sender_open_id,
            integration=integration,
        )
        locale, _timezone = await resolve_background_preferences(
            db,
            locale=getattr(binding, "locale", None),
            timezone=getattr(binding, "timezone", None),
        )

        config = _extract_feishu_bot_config(integration)
        app_id = (config.get("app_id") or "").strip()
        app_secret = (config.get("app_secret") or "").strip()

        if app_id and app_secret:
            try:
                await _reply_normal_message(
                    text=translate(locale, "bot.acknowledgement"),
                    message_id=message_id,
                    open_id=sender_open_id,
                    chat_id=chat_id,
                    app_id=app_id,
                    app_secret=app_secret,
                )
            except Exception:
                logger.exception("Failed to send Feishu acknowledgement: session_id=%s message_id=%s", binding.session_id, message_id)
        else:
            logger.warning("The Feishu bot is missing APP_ID/APP_SECRET; cannot send reply for session_id=%s", binding.session_id)

        messages, effective_datasource_id, effective_host_id, model_id, kb_ids, knowledge_context, skill_authorizations = await prepare_user_turn(
            db,
            session_id=binding.session_id,
            user_id=None,
            user_message=text,
            attachments=[],
            payload_datasource_id=None,
            model_id=None,
            history_window_hours=BOT_HISTORY_WINDOW_HOURS,
            content_locale=locale,
        )

        reply_state, on_event = _build_reply_event_handler(
            session_id=binding.session_id,
            app_id=app_id,
            app_secret=app_secret,
            message_id=message_id,
            open_id=sender_open_id,
            chat_id=chat_id,
            locale=locale,
        )

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
            locale=locale,
        )

        await FeishuBotService.mark_event_processed(db, event_id=event_id, message_id=message_id, event_type=event_type)

        final_text = _finalize_reply_text(reply_state["chunks"])
        error_text = _summarize_reply_errors(reply_state["errors"])
        if app_id and app_secret and final_text:
            await _reply_normal_message(
                text=final_text,
                message_id=message_id,
                open_id=sender_open_id,
                chat_id=chat_id,
                app_id=app_id,
                app_secret=app_secret,
            )
        elif app_id and app_secret and error_text:
            await _reply_normal_message(
                text=error_text,
                message_id=message_id,
                open_id=sender_open_id,
                chat_id=chat_id,
                app_id=app_id,
                app_secret=app_secret,
            )
        elif app_id and app_secret and reply_state["approval_sent"]:
            await _reply_normal_message(
                text=translate(locale, "bot.approval.card_hint"),
                message_id=message_id,
                open_id=sender_open_id,
                chat_id=chat_id,
                app_id=app_id,
                app_secret=app_secret,
            )
        elif app_id and app_secret:
            await _reply_normal_message(
                text=translate(locale, "bot.no_content"),
                message_id=message_id,
                open_id=sender_open_id,
                chat_id=chat_id,
                app_id=app_id,
                app_secret=app_secret,
            )

        return {"ok": True, "session_id": binding.session_id}

    @staticmethod
    async def handle_action_event(db: AsyncSession, payload: dict[str, Any]) -> dict[str, Any]:
        locale, _timezone = await resolve_background_preferences(db)
        header = payload.get("header") or {}
        event_type = header.get("event_type")
        event = payload.get("event") or {}
        action = payload.get("action") or event.get("action") or {}
        if not isinstance(action, dict):
            action = {}
        value = action.get("value") or {}
        if not isinstance(value, dict):
            value = {}
        logger.info("Processing Feishu card callback: event_type=%s action_tag=%s", event_type, action.get("tag"))
        session_id = value.get("session_id")
        approval_id = value.get("approval_id")
        decision = value.get("action")
        open_message_id = payload.get("open_message_id") or event.get("open_message_id") or action.get("open_message_id")
        sender = payload.get("operator") or payload.get("event", {}).get("sender") or {}
        sender_open_id = (sender.get("operator_id") or sender.get("sender_id") or {}).get("open_id")
        if not session_id or not approval_id or decision not in {"approved", "rejected"}:
            logger.info(
                "Ignoring Feishu card callback without approval parameters: event_type=%s action_tag=%s value_keys=%s",
                event_type,
                action.get("tag"),
                sorted(value.keys()),
            )
            return _toast_response(translate(locale, "bot.approval.received"), "success")

        approval_key = f"{session_id}:{approval_id}"
        if approval_key in PROCESSING_APPROVALS:
            logger.info("Ignoring duplicate Feishu approval callback: session_id=%s approval_id=%s event_type=%s", session_id, approval_id, event_type)
            return _toast_response(translate(locale, "bot.approval.processing"), "success")

        integration = await FeishuBotService.get_bot_integration(db)
        config = _extract_feishu_bot_config(integration)
        app_id = (config.get("app_id") or "").strip()
        app_secret = (config.get("app_secret") or "").strip()

        binding_result = await db.execute(
            select(ChatChannelBinding).where(
                ChatChannelBinding.channel_type == "feishu",
                ChatChannelBinding.session_id == int(session_id),
            )
        )
        binding = binding_result.scalar_one_or_none()
        if binding:
            locale, _timezone = await resolve_background_preferences(
                db,
                locale=getattr(binding, "locale", None),
                timezone=getattr(binding, "timezone", None),
            )

        followup_state = None
        followup_on_event = None
        if app_id and app_secret and binding:
            followup_state, followup_on_event = _build_followup_event_handler(
                session_id=int(session_id),
                app_id=app_id,
                app_secret=app_secret,
                message_id=open_message_id,
                open_id=sender_open_id,
                chat_id=binding.external_chat_id,
                locale=locale,
            )

        PROCESSING_APPROVALS.add(approval_key)
        try:
            result = await resolve_pending_approval(
                db,
                session_id=int(session_id),
                approval_id=str(approval_id),
                action=decision,
                comment=None,
                user_id=None,
                pending_approvals=PENDING_APPROVALS,
                on_event=followup_on_event,
                locale=locale,
            )
        except Exception:
            logger.exception("Failed to resume execution after Feishu approval: session_id=%s approval_id=%s", session_id, approval_id)
            return _toast_response(translate(locale, "bot.approval.failed"), "error")
        finally:
            PROCESSING_APPROVALS.discard(approval_key)

        if binding and app_id and app_secret:
            if decision == "rejected":
                await _reply_normal_message(
                    text=translate(locale, "bot.approval.rejected"),
                    message_id=open_message_id,
                    open_id=sender_open_id,
                    chat_id=binding.external_chat_id,
                    app_id=app_id,
                    app_secret=app_secret,
                )

            if decision == "approved":
                final_text = _finalize_reply_text((followup_state or {}).get("chunks", []))
                if final_text:
                    await _reply_normal_message(
                        text=final_text,
                        message_id=open_message_id,
                        open_id=sender_open_id,
                        chat_id=binding.external_chat_id,
                        app_id=app_id,
                        app_secret=app_secret,
                    )
                    return _toast_response(translate(locale, "bot.approval.result_returned"), "success")

                error_text = _summarize_reply_errors((followup_state or {}).get("errors", []))
                if error_text:
                    await _reply_normal_message(
                        text=error_text,
                        message_id=open_message_id,
                        open_id=sender_open_id,
                        chat_id=binding.external_chat_id,
                        app_id=app_id,
                        app_secret=app_secret,
                    )
                    return _toast_response(translate(locale, "bot.approval.completed_with_error"), "warning")

                if (followup_state or {}).get("approval_sent"):
                    await _reply_normal_message(
                        text=translate(locale, "bot.approval.more_required"),
                        message_id=open_message_id,
                        open_id=sender_open_id,
                        chat_id=binding.external_chat_id,
                        app_id=app_id,
                        app_secret=app_secret,
                    )
                    return _toast_response(translate(locale, "bot.approval.confirm_more"), "success")

                latest_approval = await _get_latest_approval_request(db, int(session_id), str(approval_id))
                follow_up_result = await db.execute(
                    alive_select(ChatMessage)
                    .where(
                        ChatMessage.session_id == int(session_id),
                        ChatMessage.role == "assistant",
                    )
                    .order_by(ChatMessage.created_at.desc())
                )
                latest_assistant = follow_up_result.scalars().first()
                if latest_assistant and (not latest_approval or latest_assistant.created_at >= latest_approval.created_at):
                    await _reply_normal_message(
                        text=format_reply_text(latest_assistant.content),
                        message_id=open_message_id,
                        open_id=sender_open_id,
                        chat_id=binding.external_chat_id,
                        app_id=app_id,
                        app_secret=app_secret,
                    )
                    return _toast_response(translate(locale, "bot.approval.result_returned"), "success")

                await _reply_normal_message(
                    text=translate(locale, "bot.approval.no_result"),
                    message_id=open_message_id,
                    open_id=sender_open_id,
                    chat_id=binding.external_chat_id,
                    app_id=app_id,
                    app_secret=app_secret,
                )
                return _toast_response(translate(locale, "bot.approval.no_return_content"), "warning")

        return _toast_response(
            translate(locale, "bot.approval.continuing")
            if result["status"] == "approved"
            else translate(locale, "bot.approval.rejected"),
            "success",
        )
