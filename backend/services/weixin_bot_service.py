import asyncio
import hashlib
import json
import logging
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import async_session
from backend.models.chat_channel_binding import ChatChannelBinding
from backend.models.chat_event_dedup import ChatEventDedup
from backend.models.diagnostic_session import ChatMessage, DiagnosticSession
from backend.models.integration import Integration
from backend.models.integration_bot_binding import IntegrationBotBinding
from backend.models.soft_delete import alive_filter
from backend.services.chat_orchestration_service import prepare_user_turn, process_stream_events, resolve_pending_approval
from backend.services.feishu_service import format_reply_text
from backend.services.weixin_service import weixin_service
from backend.utils.encryption import decrypt_value
from backend.utils.datetime_helper import now

logger = logging.getLogger(__name__)

PENDING_APPROVALS: dict[int, dict[str, dict[str, Any]]] = {}
BOT_HISTORY_WINDOW_HOURS = 24
_POLLING_TASK: asyncio.Task | None = None
_CONSUMER_TASK: asyncio.Task | None = None
_STOP_EVENT: asyncio.Event | None = None
_PROCESSING_BINDINGS: set[int] = set()
# 消息队列：将收到的微信消息排队，串行处理避免丢失/乱序
_MESSAGE_QUEUE: asyncio.Queue[tuple[IntegrationBotBinding, dict[str, Any]]] = asyncio.Queue()


class _SuppressWeixinPollingHttpxFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if record.name != "httpx" or record.levelno > logging.INFO:
            return True
        try:
            message = record.getMessage()
        except Exception:
            message = str(record.msg)
        return "/ilink/bot/getupdates" not in message


def _configure_weixin_polling_logging() -> logging.Logger:
    httpx_logger = logging.getLogger("httpx")
    if not any(isinstance(log_filter, _SuppressWeixinPollingHttpxFilter) for log_filter in httpx_logger.filters):
        httpx_logger.addFilter(_SuppressWeixinPollingHttpxFilter())
    return httpx_logger


class WeixinBotService:
    @staticmethod
    async def get_bot_integration(db: AsyncSession) -> Optional[Integration]:
        result = await db.execute(
            select(Integration).where(
                Integration.integration_id == "builtin_weixin_bot",
                Integration.is_enabled == True,
                alive_filter(Integration),
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def get_bot_binding(db: AsyncSession) -> Optional[IntegrationBotBinding]:
        result = await db.execute(
            select(IntegrationBotBinding).where(
                IntegrationBotBinding.code == "weixin_bot",
                IntegrationBotBinding.is_enabled == True,
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    def _decrypt_bot_token(params: dict[str, Any] | None) -> str:
        token = str((params or {}).get("bot_token") or "")
        if token.startswith("encrypted:"):
            return decrypt_value(token[len("encrypted:"):])
        return token

    @staticmethod
    def _extract_text_from_message(message: dict[str, Any]) -> str:
        item_list = message.get("item_list") or []
        for item in item_list:
            if item.get("type") == 1:
                text_item = item.get("text_item") or {}
                text = str(text_item.get("text") or "").strip()
                if text:
                    return text
        return ""

    @staticmethod
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

    @staticmethod
    def _build_fallback_event_id(message: dict[str, Any], text: str) -> str:
        source = "|".join([
            str(message.get("from_user_id") or ""),
            str(message.get("to_user_id") or ""),
            str(message.get("context_token") or ""),
            str(message.get("group_id") or ""),
            text,
        ])
        return hashlib.sha256(source.encode("utf-8")).hexdigest()

    @staticmethod
    async def is_duplicate_event(db: AsyncSession, *, event_id: str | None, message_id: str | None, event_type: str) -> bool:
        if not event_id and not message_id:
            return False
        result = await db.execute(
            select(ChatEventDedup)
            .where(
                ChatEventDedup.channel_type == "weixin",
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
        if await WeixinBotService.is_duplicate_event(db, event_id=event_id, message_id=message_id, event_type=event_type):
            return
        db.add(ChatEventDedup(
            channel_type="weixin",
            external_event_id=event_id,
            external_message_id=message_id,
            event_type=event_type,
        ))
        await db.commit()

    @staticmethod
    async def get_or_create_binding(
        db: AsyncSession,
        *,
        chat_id: str,
        user_id: str | None,
        integration: Integration | None,
        title: str,
    ) -> ChatChannelBinding:
        result = await db.execute(
            select(ChatChannelBinding).where(
                ChatChannelBinding.channel_type == "weixin",
                ChatChannelBinding.external_chat_id == chat_id,
            )
        )
        binding = result.scalar_one_or_none()
        if binding:
            binding.external_user_id = user_id
            binding.last_message_at = now()
            await db.commit()
            return binding

        session = DiagnosticSession(user_id=None, title=title)
        db.add(session)
        await db.commit()
        await db.refresh(session)

        binding = ChatChannelBinding(
            channel_type="weixin",
            external_chat_id=chat_id,
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
    async def _send_text_reply(
        binding: IntegrationBotBinding,
        *,
        to_user_id: str,
        context_token: str,
        text: str,
    ) -> dict[str, Any]:
        if not text:
            return {}
        params = binding.params or {}
        api_baseurl = str(params.get("api_baseurl") or params.get("gateway_url") or "").strip()
        bot_token = WeixinBotService._decrypt_bot_token(params)
        if not api_baseurl or not bot_token:
            logger.warning("微信 Bot 未配置 api_baseurl 或 bot_token，跳过回复")
            return {}
        logger.debug(f"[微信发送] to={to_user_id[:30]}, context={context_token[:20]}")
        resp = await weixin_service.send_text_message(
            baseurl=api_baseurl,
            bot_token=bot_token,
            to_user_id=to_user_id,
            context_token=context_token,
            text=text,
        )
        logger.debug(f"[微信发送] resp={resp}")
        return resp

    @staticmethod
    async def _handle_approval_command(
        db: AsyncSession,
        *,
        binding: ChatChannelBinding,
        bot_binding: IntegrationBotBinding,
        sender_user_id: str,
        context_token: str,
        text: str,
    ) -> bool:
        command = WeixinBotService._approval_command(text)
        if not command:
            return False

        action, approval_id = command
        chunks: list[str] = []

        async def on_event(event_obj: dict[str, Any]) -> None:
            event_type_local = event_obj.get("type")
            # 忽略 thinking 相关事件
            if event_type_local in ("thinking_start", "thinking_phase", "thinking_complete"):
                return
            if event_type_local == "content":
                chunks.append(event_obj.get("content", ""))

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
            await WeixinBotService._send_text_reply(
                bot_binding,
                to_user_id=sender_user_id,
                context_token=context_token,
                text=f"审批处理失败：{str(exc)}",
            )
            return True

        if result["status"] == "rejected":
            await WeixinBotService._send_text_reply(
                bot_binding,
                to_user_id=sender_user_id,
                context_token=context_token,
                text="已拒绝执行该操作。",
            )
            return True

        final_text = format_reply_text("".join(chunks)) or "已批准执行。"
        await WeixinBotService._send_text_reply(
            bot_binding,
            to_user_id=sender_user_id,
            context_token=context_token,
            text=final_text,
        )
        return True

    @staticmethod
    async def handle_message(db: AsyncSession, *, bot_binding: IntegrationBotBinding, message: dict[str, Any]) -> None:
        text = WeixinBotService._extract_text_from_message(message)
        if not text:
            return

        sender_user_id = str(message.get("from_user_id") or "").strip()
        receiver_user_id = str(message.get("to_user_id") or "").strip()
        context_token = str(message.get("context_token") or "").strip()
        group_id = str(message.get("group_id") or "").strip()
        raw_message_id = str(message.get("message_id") or message.get("msg_id") or "").strip()
        event_id = raw_message_id or WeixinBotService._build_fallback_event_id(message, text)
        event_type = "weixin.message"

        if not sender_user_id or not context_token:
            return

        if await WeixinBotService.is_duplicate_event(db, event_id=event_id, message_id=raw_message_id or None, event_type=event_type):
            return

        integration = await WeixinBotService.get_bot_integration(db)
        external_chat_id = group_id or sender_user_id
        title = "微信会话" if not group_id else f"微信群会话 {group_id}"
        binding = await WeixinBotService.get_or_create_binding(
            db,
            chat_id=external_chat_id,
            user_id=sender_user_id,
            integration=integration,
            title=title,
        )

        handled = await WeixinBotService._handle_approval_command(
            db,
            binding=binding,
            bot_binding=bot_binding,
            sender_user_id=sender_user_id,
            context_token=context_token,
            text=text,
        )
        if handled:
            await WeixinBotService.mark_event_processed(db, event_id=event_id, message_id=raw_message_id or None, event_type=event_type)
            return

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

        async def on_event(event_obj: dict[str, Any]) -> None:
            event_type_local = event_obj.get("type")
            # 忽略 thinking 相关事件
            if event_type_local in ("thinking_start", "thinking_phase", "thinking_complete"):
                return
            if event_type_local == "content":
                chunks.append(event_obj.get("content", ""))

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

        await WeixinBotService.mark_event_processed(db, event_id=event_id, message_id=raw_message_id or None, event_type=event_type)

        final_text = format_reply_text("".join(chunks))
        reply_text = final_text or "已收到消息。"
        # outbound 的 to_user_id 应为消息发送者（用户），而非 bot 自己的 ID
        reply_to = sender_user_id if not group_id else receiver_user_id or sender_user_id
        logger.debug(f"[微信回复] to={reply_to[:30]}, context={context_token[:20]}")

        resp = await WeixinBotService._send_text_reply(
            bot_binding,
            to_user_id=reply_to,
            context_token=context_token,
            text=reply_text,
        )
        if resp:
            ret = resp.get("ret")
            if ret is not None and ret != 0:
                logger.warning(f"[微信回复] 发送失败: ret={ret}")
        # 发送后等待较长间隔，避免微信对连续 bot 消息的频率限制
        await asyncio.sleep(5)

    @staticmethod
    async def poll_once(db: AsyncSession, binding: IntegrationBotBinding) -> None:
        params = binding.params or {}
        api_baseurl = str(params.get("api_baseurl") or params.get("gateway_url") or "").strip()
        bot_token = WeixinBotService._decrypt_bot_token(params)
        qrcode_status = str(params.get("login_status") or "")
        logger.debug(
            f"[微信轮询] api_baseurl={api_baseurl[:30] if api_baseurl else 'None'}, "
            f"has_token={bool(bot_token)}, status={qrcode_status}"
        )
        if not api_baseurl or not bot_token or qrcode_status != "confirmed":
            return

        timeout_seconds = int(params.get("receive_timeout_seconds") or 40)
        cursor = str(params.get("get_updates_buf") or "")
        logger.debug(f"[微信轮询] 开始调用get_updates, cursor='{cursor[:20]}', token_len={len(bot_token)}")
        response = await weixin_service.get_updates(
            baseurl=api_baseurl,
            bot_token=bot_token,
            get_updates_buf=cursor,
            timeout_seconds=timeout_seconds,
        )
        msgs = response.get("msgs") or []
        new_cursor = str(response.get("get_updates_buf") or cursor)
        logger.debug(f"[微信轮询] get_updates返回: msgs_count={len(msgs)}, cursor_changed={new_cursor != cursor}")

        for msg in msgs:
            # 入队而非直接处理，避免 AI 处理阻塞轮询
            await _MESSAGE_QUEUE.put((binding, msg))

        if msgs:
            logger.info(f"[微信轮询] 收到 {len(msgs)} 条新消息，当前队列长度={_MESSAGE_QUEUE.qsize()}")

        if new_cursor != cursor:
            params["get_updates_buf"] = new_cursor
            binding.params = params
            from sqlalchemy.orm.attributes import flag_modified
            flag_modified(binding, "params")
            await db.commit()
            logger.debug("[微信轮询] cursor已更新并保存")
            await db.commit()


async def _polling_loop() -> None:
    global _STOP_EVENT
    stop_event = _STOP_EVENT
    while stop_event and not stop_event.is_set():
        try:
            async with async_session() as db:
                binding = await WeixinBotService.get_bot_binding(db)
                if binding is None:
                    await asyncio.sleep(3)
                    continue
                if binding.id in _PROCESSING_BINDINGS:
                    await asyncio.sleep(1)
                    continue
                _PROCESSING_BINDINGS.add(binding.id)
                try:
                    await WeixinBotService.poll_once(db, binding)
                finally:
                    _PROCESSING_BINDINGS.discard(binding.id)
        except Exception:
            logger.exception("微信 Bot 轮询失败")
            await asyncio.sleep(5)
            continue
        await asyncio.sleep(1)


async def _consumer_loop() -> None:
    """消息消费者：从队列取消息，串行处理并回复。"""
    global _STOP_EVENT
    stop_event = _STOP_EVENT
    logger.info("[微信消费者] 启动")
    while stop_event and not stop_event.is_set():
        try:
            binding, msg = await asyncio.wait_for(_MESSAGE_QUEUE.get(), timeout=5)
        except asyncio.TimeoutError:
            continue
        except Exception:
            logger.exception("[微信消费者] 队列获取异常")
            continue

        text = str(msg.get("item_list", [{}])[0].get("text_item", {}).get("text") or msg.get("message_id", ""))
        logger.debug(f"[微信消费者] 取到消息: text='{text}', queue_len={_MESSAGE_QUEUE.qsize()}")
        try:
            async with async_session() as db:
                await WeixinBotService.handle_message(db, bot_binding=binding, message=msg)
        except Exception:
            logger.exception("[微信消费者] 处理消息失败")


async def start_weixin_bot_poller() -> None:
    global _POLLING_TASK, _CONSUMER_TASK, _STOP_EVENT
    if _POLLING_TASK and not _POLLING_TASK.done():
        return
    _configure_weixin_polling_logging()
    _STOP_EVENT = asyncio.Event()
    _POLLING_TASK = asyncio.create_task(_polling_loop())
    _CONSUMER_TASK = asyncio.create_task(_consumer_loop())
    logger.info("Weixin bot poller & consumer started")


async def stop_weixin_bot_poller() -> None:
    global _POLLING_TASK, _CONSUMER_TASK, _STOP_EVENT
    if _STOP_EVENT:
        _STOP_EVENT.set()
    for task in (_POLLING_TASK, _CONSUMER_TASK):
        if task:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
    _POLLING_TASK = None
    _CONSUMER_TASK = None
    _STOP_EVENT = None
