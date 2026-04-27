"""
微信机器人管理路由

内置 iLink Bot 客户端直接连接微信服务器，无需外部网关。
登录流程：获取二维码 → 扫码 → 轮询状态 → 获得 token → 开始收消息
"""

import logging
from typing import Any

import httpx
from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_db
from backend.dependencies import get_current_user
from backend.models.integration import Integration
from backend.models.integration_bot_binding import IntegrationBotBinding
from backend.models.user import User
from backend.models.soft_delete import alive_filter
from backend.schemas.weixin import WeixinLoginQrcodeResponse, WeixinLoginStatusResponse, WeixinBotBindingStatusResponse
from backend.services.integration_service import IntegrationService
from backend.services.weixin_service import weixin_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/weixin/bot", tags=["weixin-bot"])

# iLink Bot API 地址（腾讯官方或自行部署的网关代理）
DEFAULT_ILINK_API = "https://ilinkai.weixin.qq.com"


def _mask_sensitive_params(params: dict[str, Any] | None) -> dict[str, Any]:
    masked = dict(params or {})
    if masked.get("bot_token"):
        masked["bot_token"] = "***"
    return masked


def _ilink_api_base(params: dict[str, Any] | None) -> str:
    return str((params or {}).get("ilink_api_base") or DEFAULT_ILINK_API)


async def _get_or_create_binding(db: AsyncSession) -> IntegrationBotBinding:
    result = await db.execute(
        select(Integration).where(
            Integration.integration_id == "builtin_weixin_bot",
            Integration.is_enabled == True,
            alive_filter(Integration),
        )
    )
    integration = result.scalar_one_or_none()
    if not integration:
        raise HTTPException(status_code=404, detail="微信 Bot Integration 不存在或未启用")

    binding_result = await db.execute(
        select(IntegrationBotBinding).where(IntegrationBotBinding.code == "weixin_bot")
    )
    binding = binding_result.scalar_one_or_none()
    if binding:
        if binding.integration_id != integration.id:
            binding.integration_id = integration.id
            await db.commit()
            await db.refresh(binding)
        return binding

    binding = IntegrationBotBinding(
        integration_id=integration.id,
        code="weixin_bot",
        name="微信机器人",
        enabled=False,
        params={"ilink_api_base": DEFAULT_ILINK_API},
    )
    db.add(binding)
    await db.commit()
    await db.refresh(binding)
    return binding


@router.get("/binding/status", response_model=WeixinBotBindingStatusResponse)
async def get_weixin_bot_status(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    binding = await _get_or_create_binding(db)
    params = binding.params or {}
    login_status = str(params.get("login_status") or "not_ready")

    # 如果保存的 qrcode_img_content 是外部 URL，由后端生成 QR 码图片
    qrcode_img = str(params.get("qrcode_img_content") or "") or None
    if qrcode_img and qrcode_img.startswith("http"):
        try:
            qrcode_img = weixin_service.generate_qrcode_as_base64(qrcode_img)
        except Exception:
            qrcode_img = None

    return WeixinBotBindingStatusResponse(
        code=binding.code,
        enabled=bool(binding.is_enabled),
        login_status=login_status,
        has_token=bool(params.get("bot_token")),
        api_baseurl=_ilink_api_base(params),
        qrcode_img_content=qrcode_img,
        last_error=str(params.get("last_error") or "") or None,
        raw={"params": _mask_sensitive_params(params)},
    )


@router.post("/login/qrcode", response_model=WeixinLoginQrcodeResponse)
async def create_weixin_login_qrcode(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取登录二维码。"""
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="需要管理员权限")

    binding = await _get_or_create_binding(db)
    params = binding.params or {}
    api_base = _ilink_api_base(params)

    try:
        resp = await weixin_service.get_bot_qrcode(api_base=api_base)
    except Exception as exc:
        logger.exception("获取微信登录二维码失败")
        params["login_status"] = "error"
        params["last_error"] = f"{type(exc).__name__}: {str(exc)}"
        binding.params = params
        await db.commit()
        raise HTTPException(status_code=502, detail=f"获取二维码失败: {exc}")

    # 优先取 qrcode_img_content（base64 图片）
    qrcode = str(resp.get("qrcode") or resp.get("data", {}).get("qrcode") or "")
    qrcode_img = str(resp.get("qrcode_img_content") or resp.get("data", {}).get("qrcode_img_content") or "")
    expires_in = resp.get("expires_in") or resp.get("data", {}).get("expires_in")

    if not qrcode:
        raise HTTPException(status_code=502, detail="上游未返回 qrcode")

    # 如果返回的是外部 URL（微信 liteapp 域名），由后端生成 QR 码图片规避 CORS
    # 必须用完整 URL 而非仅 qrcode 字符串，否则微信扫码无法识别为登录二维码
    qrcode_img_proxied: str | None = None
    if qrcode_img:
        if qrcode_img.startswith("http"):
            try:
                qrcode_img_proxied = weixin_service.generate_qrcode_as_base64(qrcode_img)
            except ImportError as exc:
                logger.error(f"生成二维码图片失败（缺少依赖）: {exc}")
                qrcode_img_proxied = None
            except Exception as exc:
                logger.warning(f"生成二维码图片失败，将使用原始 URL: {exc}")
                qrcode_img_proxied = qrcode_img
        else:
            qrcode_img_proxied = qrcode_img

    params["qrcode"] = qrcode
    if qrcode_img:
        params["qrcode_img_content"] = qrcode_img
    if expires_in is not None:
        params["qrcode_expires_in"] = expires_in
    params["login_status"] = "pending"
    params["last_error"] = ""
    binding.params = params
    await db.commit()

    return WeixinLoginQrcodeResponse(
        qrcode=qrcode,
        qrcode_img_content=qrcode_img_proxied,
        expires_in=expires_in,
        raw=resp,
    )


@router.post("/login/status", response_model=WeixinLoginStatusResponse)
async def poll_weixin_login_status(
    qrcode: str = Body(..., embed=True),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """轮询扫码状态。扫码成功后返回 bot_token 和 api_baseurl。"""
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="需要管理员权限")

    binding = await _get_or_create_binding(db)
    params = binding.params or {}
    api_base = _ilink_api_base(params)

    try:
        resp = await weixin_service.get_qrcode_status(qrcode, api_base=api_base)
    except httpx.ReadTimeout:
        # 长轮询超时 = 用户尚未扫码，这是正常状态，不算错误
        logger.info("扫码状态轮询超时（用户尚未扫码）")
        return WeixinLoginStatusResponse(
            status="pending",
            bot_token=None,
            api_baseurl=None,
            raw={"ret": -1, "message": "timeout"},
        )
    except Exception as exc:
        logger.exception("查询微信扫码状态失败")
        params["login_status"] = "error"
        err_msg = f"{type(exc).__name__}: {str(exc)}" or str(type(exc).__name__)
        params["last_error"] = err_msg
        binding.params = params
        await db.commit()
        raise HTTPException(status_code=502, detail=f"查询扫码状态失败: {err_msg}")

    status = str(resp.get("status") or resp.get("data", {}).get("status") or "")
    bot_token = resp.get("bot_token") or resp.get("data", {}).get("bot_token")
    api_baseurl = resp.get("baseurl") or resp.get("data", {}).get("baseurl")

    if status:
        params["login_status"] = status

    if bot_token:
        encrypted = IntegrationService.encrypt_sensitive_params({"bot_token": f"ENCRYPT:{bot_token}"})
        params["bot_token"] = encrypted.get("bot_token")
        params["login_status"] = "confirmed"
        params["last_error"] = ""
        binding.is_enabled = True

    # 后续 API 调用统一用返回的 baseurl（可能是反向代理地址）
    if api_baseurl:
        params["api_baseurl"] = api_baseurl
    else:
        params["api_baseurl"] = api_base

    binding.params = params
    from sqlalchemy.orm.attributes import flag_modified
    flag_modified(binding, "params")
    await db.commit()

    return WeixinLoginStatusResponse(
        status=params.get("login_status") or status or "unknown",
        bot_token="***" if bot_token else None,
        api_baseurl=str(api_baseurl or api_base) or None,
        raw=resp,
    )
