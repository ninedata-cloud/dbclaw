"""
iLink Bot 微信协议客户端

直接连接微信 iLink Bot API，负责：
1. 获取登录二维码（扫码登录）
2. 轮询扫码状态，获取 bot_token
3. 长轮询收消息（getupdates）
4. 发送消息（sendmessage）

API 文档：https://github.com/hao-ji-xing/openclaw-weixin
"""

import base64
import io
import logging
import random
import uuid
from typing import Any

import httpx

logger = logging.getLogger(__name__)


class WeixinService:
    # iLink Bot 官方 API 地址（用户也可自行部署网关代理）
    DEFAULT_API_BASE = "https://ilinkai.weixin.qq.com"

    def _build_headers(self, bot_token: str) -> dict[str, str]:
        random_uin = base64.b64encode(str(random.randint(1, 2**32 - 1)).encode("utf-8")).decode("utf-8")
        return {
            "Content-Type": "application/json",
            "AuthorizationType": "ilink_bot_token",
            "Authorization": f"Bearer {bot_token}",
            "X-WECHAT-UIN": random_uin,
        }

    async def get_bot_qrcode(
        self,
        api_base: str | None = None,
    ) -> dict[str, Any]:
        """获取微信登录二维码。"""
        base = (api_base or self.DEFAULT_API_BASE).rstrip("/")
        url = f"{base}/ilink/bot/get_bot_qrcode"
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.get(url, params={"bot_type": 3})
            response.raise_for_status()
            return response.json()

    async def fetch_qrcode_image_as_base64(self, image_url: str) -> str:
        """下载二维码图片并转为 base64（用于绕过前端 CORS）。"""
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.get(image_url)
            response.raise_for_status()
            content_type = response.headers.get("content-type", "image/png")
            data = base64.b64encode(response.content).decode("ascii")
            return f"data:{content_type};base64,{data}"

    def generate_qrcode_as_base64(self, qrcode_string: str, size: int = 8) -> str:
        """用 Python qrcode 库从字符串生成 QR 码图片 base64（绕过 CORS）。"""
        try:
            import qrcode
        except ImportError:
            logger.error("qrcode 库未安装，无法生成二维码图片。请运行: pip install qrcode")
            raise ImportError("qrcode 库未安装，请运行: pip install qrcode")

        qr = qrcode.QRCode(version=1, error_correction=qrcode.constants.ERROR_CORRECT_L, box_size=size, border=2)
        qr.add_data(qrcode_string)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        buf.seek(0)
        return f"data:image/png;base64,{base64.b64encode(buf.read()).decode('ascii')}"

    async def get_qrcode_status(
        self,
        qrcode: str,
        api_base: str | None = None,
    ) -> dict[str, Any]:
        """轮询扫码状态。长轮询等待用户扫码，最多等待 150s。status=confirmed 时返回 bot_token 和 baseurl。"""
        base = (api_base or self.DEFAULT_API_BASE).rstrip("/")
        url = f"{base}/ilink/bot/get_qrcode_status"
        # 长轮询：QR 有效期约 120s，多给一些余量
        async with httpx.AsyncClient(timeout=150) as client:
            response = await client.get(url, params={"qrcode": qrcode})
            response.raise_for_status()
            return response.json()

    async def get_updates(
        self,
        *,
        bot_token: str,
        baseurl: str,
        get_updates_buf: str = "",
        channel_version: str = "1.0.2",
        timeout_seconds: int = 40,
    ) -> dict[str, Any]:
        """长轮询收消息。服务端最多 hold 35 秒。"""
        payload = {
            "get_updates_buf": get_updates_buf,
            "base_info": {"channel_version": channel_version},
        }
        headers = self._build_headers(bot_token)
        async with httpx.AsyncClient(timeout=timeout_seconds + 5) as client:
            response = await client.post(
                f"{baseurl.rstrip('/')}/ilink/bot/getupdates",
                json=payload,
                headers=headers,
            )
            response.raise_for_status()
            return response.json()

    async def send_text_message(
        self,
        *,
        bot_token: str,
        baseurl: str,
        to_user_id: str,
        context_token: str,
        text: str,
    ) -> dict[str, Any]:
        """发送文本消息。必须携带 context_token 才能正确关联会话。"""
        payload = {
            "msg": {
                "from_user_id": "",
                "to_user_id": to_user_id,
                "client_id": f"dbclaw-{uuid.uuid4()}",
                "message_type": 2,   # BOT outbound
                "message_state": 2,  # FINISH
                "context_token": context_token,
                "item_list": [
                    {"type": 1, "text_item": {"text": text}}
                ],
            }
        }
        headers = self._build_headers(bot_token)
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.post(
                f"{baseurl.rstrip('/')}/ilink/bot/sendmessage",
                json=payload,
                headers=headers,
            )
            response.raise_for_status()
            resp_data = response.json() if response.content else {}
            ret = resp_data.get("ret") if resp_data else None
            if ret is not None and ret != 0:
                logger.warning(f"WeChat sendmessage返回错误: ret={ret}, data={resp_data}")
            return resp_data


weixin_service = WeixinService()
