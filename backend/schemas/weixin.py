from typing import Any, Optional

from pydantic import BaseModel, Field


class WeixinLoginQrcodeResponse(BaseModel):
    success: bool = True
    qrcode: str = Field(..., description="二维码内容标识")
    qrcode_img_content: Optional[str] = Field(default=None, description="二维码 base64 图片内容")
    expires_in: Optional[int] = None
    raw: dict[str, Any] = Field(default_factory=dict)


class WeixinLoginStatusResponse(BaseModel):
    success: bool = True
    status: str
    bot_token: Optional[str] = None
    api_baseurl: Optional[str] = None
    raw: dict[str, Any] = Field(default_factory=dict)


class WeixinBotBindingStatusResponse(BaseModel):
    code: str
    enabled: bool
    login_status: str
    has_token: bool
    api_baseurl: Optional[str] = None
    qrcode_img_content: Optional[str] = None
    last_error: Optional[str] = None
    raw: dict[str, Any] = Field(default_factory=dict)
