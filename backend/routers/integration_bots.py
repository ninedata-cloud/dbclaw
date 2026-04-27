from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_db
from backend.dependencies import get_current_user
from backend.models.integration import Integration
from backend.models.integration_bot_binding import IntegrationBotBinding
from backend.models.user import User
from backend.models.soft_delete import alive_filter
from backend.schemas.integration import IntegrationBotBindingResponse, IntegrationBotBindingUpdate
from backend.services.integration_service import IntegrationService

router = APIRouter(prefix="/api/integration-bots", tags=["integration-bots"])


SUPPORTED_BOT_BINDINGS = {
    "feishu_bot": {
        "integration_id": "builtin_feishu_bot",
        "default_name": "飞书机器人",
    },
    "dingtalk_bot": {
        "integration_id": "builtin_dingtalk_bot",
        "default_name": "钉钉机器人",
    },
    "weixin_bot": {
        "integration_id": "builtin_weixin_bot",
        "default_name": "微信机器人",
    },
}


def _mask_sensitive_params(params: dict | None) -> dict:
    masked = dict(params or {})
    if "bot_token" in masked and masked["bot_token"]:
        masked["bot_token"] = "***"
    return masked


async def _get_or_create_binding(db: AsyncSession, code: str) -> IntegrationBotBinding:
    metadata = SUPPORTED_BOT_BINDINGS.get(code)
    if not metadata:
        raise HTTPException(status_code=404, detail="Bot binding 不存在")

    integration_result = await db.execute(
        select(Integration).where(
            Integration.integration_id == metadata["integration_id"],
            Integration.is_enabled == True,
            alive_filter(Integration),
        )
    )
    integration = integration_result.scalar_one_or_none()
    if not integration:
        raise HTTPException(status_code=404, detail=f"{code} 对应的 Integration 不存在或未启用")

    binding_result = await db.execute(select(IntegrationBotBinding).where(IntegrationBotBinding.code == code))
    binding = binding_result.scalar_one_or_none()
    if binding:
        if binding.integration_id != integration.id:
            binding.integration_id = integration.id
            await db.commit()
            await db.refresh(binding)
        return binding

    binding = IntegrationBotBinding(
        integration_id=integration.id,
        code=code,
        name=metadata["default_name"],
        enabled=False,
        params={},
    )
    db.add(binding)
    await db.commit()
    await db.refresh(binding)
    return binding


@router.get("", response_model=list[IntegrationBotBindingResponse])
async def list_integration_bots(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    bindings: list[IntegrationBotBindingResponse] = []
    for code in SUPPORTED_BOT_BINDINGS:
        try:
            binding = await _get_or_create_binding(db, code)
        except HTTPException:
            continue
        response = IntegrationBotBindingResponse.model_validate(binding)
        response.params = _mask_sensitive_params(response.params)
        bindings.append(response)
    return bindings


@router.put("/{code}", response_model=IntegrationBotBindingResponse)
async def update_integration_bot(
    code: str,
    data: IntegrationBotBindingUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="需要管理员权限")

    binding = await _get_or_create_binding(db, code)

    update_data = data.model_dump(exclude_unset=True)
    if "params" in update_data and update_data["params"] is not None:
        update_data["params"] = IntegrationService.encrypt_sensitive_params(update_data["params"])

    for key, value in update_data.items():
        setattr(binding, key, value)

    await db.commit()
    await db.refresh(binding)

    response = IntegrationBotBindingResponse.model_validate(binding)
    response.params = _mask_sensitive_params(response.params)
    return response
