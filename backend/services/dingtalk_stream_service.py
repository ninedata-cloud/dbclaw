import asyncio
import importlib.util
import json
import logging
import threading
import urllib.parse
from typing import Any

from backend.database import async_session
from backend.services.dingtalk_bot_service import DingTalkBotService, _extract_dingtalk_bot_config

logger = logging.getLogger(__name__)

_WS_THREAD: threading.Thread | None = None
_WS_STOP_EVENT: threading.Event | None = None
_APP_LOOP: asyncio.AbstractEventLoop | None = None


async def _update_binding_status(*, login_status: str, last_error: str = "") -> None:
    async with async_session() as db:
        await DingTalkBotService.update_binding_status(db, login_status=login_status, last_error=last_error)


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
        logger.exception("更新钉钉机器人绑定状态失败")


async def _process_message_payload(
    *,
    message: dict[str, Any],
    send_reply,
) -> dict[str, Any]:
    async with async_session() as db:
        return await DingTalkBotService.handle_message(db, message=message, send_reply=send_reply)


def _ws_thread_main(*, client_id: str, client_secret: str) -> None:
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    stop_event = _WS_STOP_EVENT or threading.Event()

    try:
        import dingtalk_stream
        import websockets

        class _DingTalkChatbotHandler(dingtalk_stream.chatbot.AsyncChatbotHandler):
            def process(self, callback_message):
                if _APP_LOOP is None:
                    logger.warning("钉钉长连接主事件循环尚未就绪，忽略消息")
                    return

                incoming_message = dingtalk_stream.chatbot.ChatbotMessage.from_dict(callback_message.data or {})
                payload = incoming_message.to_dict()

                async def send_reply(text: str) -> None:
                    if not text:
                        return
                    await asyncio.to_thread(self.reply_text, text, incoming_message)

                future = asyncio.run_coroutine_threadsafe(
                    _process_message_payload(message=payload, send_reply=send_reply),
                    _APP_LOOP,
                )
                try:
                    future.result(timeout=600)
                except Exception:
                    logger.exception("钉钉消息处理失败")

        credential = dingtalk_stream.Credential(client_id, client_secret)
        client = dingtalk_stream.DingTalkStreamClient(credential)
        client.register_callback_handler(
            dingtalk_stream.chatbot.ChatbotMessage.TOPIC,
            _DingTalkChatbotHandler(),
        )

        async def runner() -> None:
            client.pre_start()
            while not stop_event.is_set():
                connection = await asyncio.to_thread(client.open_connection)
                if not connection:
                    logger.error("钉钉长连接 open_connection 失败")
                    _set_binding_status(login_status="error", last_error="钉钉 Stream open_connection 失败")
                    await asyncio.to_thread(stop_event.wait, 10)
                    continue

                _set_binding_status(login_status="confirmed", last_error="")
                logger.info("DingTalk stream endpoint: %s", connection)

                uri = "%s?ticket=%s" % (
                    connection["endpoint"],
                    urllib.parse.quote_plus(connection["ticket"]),
                )

                try:
                    async with websockets.connect(uri) as websocket:
                        client.websocket = websocket
                        while not stop_event.is_set():
                            try:
                                raw_message = await asyncio.wait_for(websocket.recv(), timeout=1)
                            except asyncio.TimeoutError:
                                continue
                            except websockets.exceptions.ConnectionClosed:
                                break

                            json_message = json.loads(raw_message)
                            route_result = await client.route_message(json_message)
                            if route_result == dingtalk_stream.DingTalkStreamClient.TAG_DISCONNECT:
                                break
                except Exception as exc:
                    if stop_event.is_set():
                        break
                    logger.exception("钉钉长连接 websocket 异常")
                    _set_binding_status(login_status="error", last_error=str(exc))
                    await asyncio.to_thread(stop_event.wait, 5)

                finally:
                    client.websocket = None

        loop.run_until_complete(runner())
    except Exception as exc:
        logger.exception("钉钉长连接客户端退出异常")
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
            logger.exception("钉钉长连接事件循环清理失败")
        finally:
            loop.close()
            logger.info("DingTalk stream client stopped")


async def start_dingtalk_stream_client() -> None:
    global _WS_THREAD, _WS_STOP_EVENT, _APP_LOOP

    if _WS_THREAD and _WS_THREAD.is_alive():
        return

    _APP_LOOP = asyncio.get_running_loop()

    async with async_session() as db:
        integration = await DingTalkBotService.get_bot_integration(db)
        await DingTalkBotService.ensure_bot_binding(db, integration=integration)

    if importlib.util.find_spec("dingtalk_stream") is None:
        logger.warning("未安装 dingtalk-stream，跳过钉钉长连接启动")
        await _update_binding_status(
            login_status="error",
            last_error="未安装 dingtalk-stream，请先执行 pip install -r requirements.txt",
        )
        return

    config = _extract_dingtalk_bot_config(integration)
    client_id = (config.get("client_id") or "").strip()
    client_secret = (config.get("client_secret") or "").strip()

    if not client_id or not client_secret:
        logger.info("钉钉机器人未配置 CLIENT_ID/CLIENT_SECRET，跳过长连接启动")
        await _update_binding_status(login_status="not_ready", last_error="")
        return

    _WS_STOP_EVENT = threading.Event()
    _WS_THREAD = threading.Thread(
        target=_ws_thread_main,
        kwargs={"client_id": client_id, "client_secret": client_secret},
        name="dingtalk-stream",
        daemon=True,
    )
    _WS_THREAD.start()
    logger.info("DingTalk stream client started")


async def stop_dingtalk_stream_client() -> None:
    global _WS_THREAD, _WS_STOP_EVENT

    if _WS_STOP_EVENT:
        _WS_STOP_EVENT.set()

    if _WS_THREAD:
        await asyncio.to_thread(_WS_THREAD.join, 10)
        if _WS_THREAD.is_alive():
            logger.warning("钉钉长连接线程未在超时时间内退出，将等待进程结束时回收")

    _WS_THREAD = None
    _WS_STOP_EVENT = None
