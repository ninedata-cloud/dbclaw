import asyncio
import importlib.util
import logging
import re
import threading
from types import SimpleNamespace
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from backend.database import async_session
from backend.services.feishu_bot_service import (
    FeishuBotService,
    _extract_feishu_bot_config,
    _toast_response,
)

logger = logging.getLogger(__name__)

_WS_THREAD: threading.Thread | None = None
_WS_STOP_EVENT: threading.Event | None = None
_APP_LOOP: asyncio.AbstractEventLoop | None = None
_URL_RE = re.compile(r"(wss?://[^\s\]]+|https?://[^\s\]]+)")


def _sanitize_log_message(message: str) -> str:
    def _replace(match: re.Match[str]) -> str:
        raw_url = match.group(0)
        parts = urlsplit(raw_url)
        if not parts.query:
            return raw_url
        return urlunsplit((parts.scheme, parts.netloc, parts.path, "redacted", parts.fragment))

    return _URL_RE.sub(_replace, message)


class _SensitiveLogFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = _sanitize_log_message(str(record.msg))
        if isinstance(record.args, tuple):
            record.args = tuple(
                _sanitize_log_message(arg) if isinstance(arg, str) else arg
                for arg in record.args
            )
        elif isinstance(record.args, dict):
            record.args = {
                key: _sanitize_log_message(value) if isinstance(value, str) else value
                for key, value in record.args.items()
            }
        elif isinstance(record.args, str):
            record.args = _sanitize_log_message(record.args)
        return True


def _configure_lark_logger(level: int) -> logging.Logger:
    sdk_logger = logging.getLogger("Lark")
    sdk_logger.setLevel(level)
    sdk_logger.propagate = False
    if not any(isinstance(log_filter, _SensitiveLogFilter) for log_filter in sdk_logger.filters):
        sdk_logger.addFilter(_SensitiveLogFilter())
    return sdk_logger


async def _update_binding_status(*, login_status: str, last_error: str = "") -> None:
    async with async_session() as db:
        await FeishuBotService.update_binding_status(db, login_status=login_status, last_error=last_error)


def _set_binding_status(*, login_status: str, last_error: str = "") -> None:
    if _APP_LOOP is None:
        return
    future = asyncio.run_coroutine_threadsafe(
        _update_binding_status(login_status=login_status, last_error=last_error),
        _APP_LOOP,
    )
    try:
        future.result(timeout=15)
    except Exception:
        logger.exception("更新飞书机器人绑定状态失败")


def _as_dict(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, dict):
        return value
    return dict(value)


def _normalize_message_event(data: Any) -> dict[str, Any]:
    header = getattr(data, "header", None) or SimpleNamespace()
    event = getattr(data, "event", None) or SimpleNamespace()
    sender = getattr(event, "sender", None) or SimpleNamespace()
    sender_id = getattr(sender, "sender_id", None) or SimpleNamespace()
    message = getattr(event, "message", None) or SimpleNamespace()
    return {
        "header": {
            "event_id": getattr(header, "event_id", None),
            "event_type": getattr(header, "event_type", "im.message.receive_v1"),
        },
        "event": {
            "sender": {
                "sender_id": {
                    "open_id": getattr(sender_id, "open_id", None),
                    "user_id": getattr(sender_id, "user_id", None),
                    "union_id": getattr(sender_id, "union_id", None),
                },
                "sender_type": getattr(sender, "sender_type", None),
                "tenant_key": getattr(sender, "tenant_key", None),
            },
            "message": {
                "chat_id": getattr(message, "chat_id", None),
                "message_id": getattr(message, "message_id", None),
                "message_type": getattr(message, "message_type", None),
                "content": getattr(message, "content", None),
                "chat_type": getattr(message, "chat_type", None),
                "mentions": getattr(message, "mentions", None),
            },
        },
    }


def _normalize_action_event(data: Any) -> dict[str, Any]:
    header = getattr(data, "header", None) or SimpleNamespace()
    event = getattr(data, "event", None) or SimpleNamespace()
    action = getattr(event, "action", None) or SimpleNamespace()
    operator = getattr(event, "operator", None) or SimpleNamespace()
    context = getattr(event, "context", None) or SimpleNamespace()
    return {
        "header": {
            "event_id": getattr(header, "event_id", None),
            "event_type": getattr(header, "event_type", "card.action.trigger"),
        },
        "action": {
            "tag": getattr(action, "tag", None),
            "value": _as_dict(getattr(action, "value", None)),
            "option": getattr(action, "option", None),
            "timezone": getattr(action, "timezone", None),
            "name": getattr(action, "name", None),
            "form_value": _as_dict(getattr(action, "form_value", None)),
            "input_value": getattr(action, "input_value", None),
            "options": getattr(action, "options", None),
            "checked": getattr(action, "checked", None),
            "open_message_id": getattr(context, "open_message_id", None),
        },
        "operator": {
            "operator_id": {
                "open_id": getattr(operator, "open_id", None),
                "user_id": getattr(operator, "user_id", None),
                "union_id": getattr(operator, "union_id", None),
            }
        },
        "open_message_id": getattr(context, "open_message_id", None),
    }


async def _process_message_payload(payload: dict[str, Any]) -> None:
    async with async_session() as db:
        await FeishuBotService.handle_message_event(db, payload)


async def _process_action_payload(payload: dict[str, Any]) -> dict[str, Any]:
    async with async_session() as db:
        return await FeishuBotService.handle_action_event(db, payload)


def _log_future_exception(future) -> None:
    try:
        future.result()
    except Exception:
        logger.exception("飞书长连接事件处理失败")


def _handle_sdk_message(data: Any) -> None:
    if _APP_LOOP is None:
        logger.warning("飞书长连接主事件循环尚未就绪，忽略消息事件")
        return
    payload = _normalize_message_event(data)
    future = asyncio.run_coroutine_threadsafe(_process_message_payload(payload), _APP_LOOP)
    future.add_done_callback(_log_future_exception)


def _handle_sdk_action(data: Any) -> dict[str, Any]:
    if _APP_LOOP is None:
        return _toast_response("服务尚未就绪，请稍后重试。", "warning")
    payload = _normalize_action_event(data)
    future = asyncio.run_coroutine_threadsafe(_process_action_payload(payload), _APP_LOOP)
    try:
        return future.result(timeout=120)
    except Exception as exc:
        logger.exception("飞书长连接卡片回调处理失败")
        return _toast_response(f"处理失败：{str(exc)}", "error")


def _ws_thread_main(*, app_id: str, app_secret: str) -> None:
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    stop_event = _WS_STOP_EVENT or threading.Event()

    client = None
    try:
        import lark_oapi as lark
        _configure_lark_logger(lark.LogLevel.WARNING.value)

        event_handler = (
            lark.EventDispatcherHandler.builder("", "", lark.LogLevel.WARNING)
            .register_p2_im_message_receive_v1(_handle_sdk_message)
            .register_p2_card_action_trigger(_handle_sdk_action)
            .build()
        )

        client = lark.ws.Client(
            app_id=app_id,
            app_secret=app_secret,
            log_level=lark.LogLevel.WARNING,
            event_handler=event_handler,
            auto_reconnect=True,
        )

        async def runner() -> None:
            try:
                await client._connect()
            except Exception:
                if getattr(client, "_auto_reconnect", False):
                    await client._reconnect()
                else:
                    raise

            _set_binding_status(login_status="confirmed", last_error="")

            ping_task = asyncio.create_task(client._ping_loop())
            try:
                await asyncio.to_thread(stop_event.wait)
            finally:
                ping_task.cancel()
                try:
                    await ping_task
                except asyncio.CancelledError:
                    pass
                client._auto_reconnect = False
                await client._disconnect()

        loop.run_until_complete(runner())
    except Exception as exc:
        logger.exception("飞书长连接客户端退出异常")
        _set_binding_status(login_status="error", last_error=str(exc))
    finally:
        try:
            pending = [task for task in asyncio.all_tasks(loop) if not task.done()]
            for task in pending:
                task.cancel()
            if pending:
                loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
            loop.run_until_complete(loop.shutdown_asyncgens())
        except Exception:
            logger.exception("飞书长连接事件循环清理失败")
        finally:
            loop.close()
            logger.info("Feishu long connection client stopped")


async def start_feishu_longconn_client() -> None:
    global _WS_THREAD, _WS_STOP_EVENT, _APP_LOOP

    if _WS_THREAD and _WS_THREAD.is_alive():
        return

    _APP_LOOP = asyncio.get_running_loop()

    async with async_session() as db:
        integration = await FeishuBotService.get_bot_integration(db)
        await FeishuBotService.ensure_bot_binding(db, integration=integration)

    if importlib.util.find_spec("lark_oapi") is None:
        logger.warning("未安装 lark-oapi，跳过飞书长连接启动")
        await _update_binding_status(
            login_status="error",
            last_error="未安装 lark-oapi，请先执行 pip install -r requirements.txt",
        )
        return

    config = _extract_feishu_bot_config(integration)
    app_id = (config.get("app_id") or "").strip()
    app_secret = (config.get("app_secret") or "").strip()

    if not app_id or not app_secret:
        logger.info("飞书机器人未配置 APP_ID/APP_SECRET，跳过长连接启动")
        await _update_binding_status(login_status="not_ready", last_error="")
        return

    _WS_STOP_EVENT = threading.Event()
    _WS_THREAD = threading.Thread(
        target=_ws_thread_main,
        kwargs={"app_id": app_id, "app_secret": app_secret},
        name="feishu-longconn",
        daemon=True,
    )
    _WS_THREAD.start()
    logger.info("Feishu long connection client started")


async def stop_feishu_longconn_client() -> None:
    global _WS_THREAD, _WS_STOP_EVENT

    if _WS_STOP_EVENT:
        _WS_STOP_EVENT.set()

    if _WS_THREAD:
        await asyncio.to_thread(_WS_THREAD.join, 10)
        if _WS_THREAD.is_alive():
            logger.warning("飞书长连接线程未在超时时间内退出，将等待进程结束时回收")

    _WS_THREAD = None
    _WS_STOP_EVENT = None
