from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from typing import List
from time import perf_counter

from backend.database import get_db
from backend.models.ai_model import AIModel
from backend.schemas.ai_model import (
    AIModelCreate,
    AIModelUpdate,
    AIModelResponse,
    AIModelTestChatRequest,
    AIModelTestChatResponse,
)
from backend.dependencies import get_current_user
from backend.utils.encryption import encrypt_value, decrypt_value
from backend.services.ai_agent import get_ai_client, request_text_response

router = APIRouter(prefix="/api/ai-models", tags=["ai-models"], dependencies=[Depends(get_current_user)])


def encrypt_api_key(api_key: str) -> str:
    return encrypt_value(api_key)


def decrypt_api_key(encrypted: str) -> str:
    return decrypt_value(encrypted)


def mask_api_key(api_key: str) -> str:
    if len(api_key) <= 8:
        return "****"
    return api_key[:4] + "****" + api_key[-4:]


@router.get("", response_model=List[AIModelResponse])
async def list_models(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(AIModel).order_by(AIModel.name).filter(AIModel.is_active == True))
    models = result.scalars().all()
    response = []
    for model in models:
        try:
            api_key_masked = mask_api_key(decrypt_api_key(model.api_key_encrypted))
        except Exception:
            # If decryption fails (key mismatch), show placeholder
            api_key_masked = "****[invalid]"

        response.append(AIModelResponse(
            **{**model.__dict__, "api_key_masked": api_key_masked}
        ))
    return response


@router.post("", response_model=AIModelResponse)
async def create_model(data: AIModelCreate, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(AIModel).filter(AIModel.name == data.name))
    existing = result.scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=400, detail="模型名称已存在")

    model = AIModel(
        name=data.name,
        provider=data.provider,
        protocol=data.protocol,
        api_key_encrypted=encrypt_api_key(data.api_key),
        base_url=data.base_url,
        model_name=data.model_name,
        context_window=data.context_window,
        reasoning_effort=data.reasoning_effort,
    )
    db.add(model)
    await db.commit()
    await db.refresh(model)

    return AIModelResponse(
        **{**model.__dict__, "api_key_masked": mask_api_key(data.api_key)}
    )


@router.put("/{model_id}", response_model=AIModelResponse)
async def update_model(model_id: int, data: AIModelUpdate, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(AIModel).filter(AIModel.id == model_id))
    model = result.scalar_one_or_none()
    if not model:
        raise HTTPException(status_code=404, detail="模型不存在")

    if data.name:
        model.name = data.name
    if data.provider:
        model.provider = data.provider
    if data.protocol:
        model.protocol = data.protocol
    if data.api_key:
        model.api_key_encrypted = encrypt_api_key(data.api_key)
    if data.base_url:
        model.base_url = data.base_url
    if data.model_name:
        model.model_name = data.model_name
    if "context_window" in data.model_fields_set:
        model.context_window = data.context_window
    if "reasoning_effort" in data.model_fields_set:
        model.reasoning_effort = data.reasoning_effort

    await db.commit()
    await db.refresh(model)

    try:
        api_key_masked = mask_api_key(decrypt_api_key(model.api_key_encrypted))
    except Exception:
        api_key_masked = "****[invalid]"

    return AIModelResponse(
        **{**model.__dict__, "api_key_masked": api_key_masked}
    )


@router.delete("/{model_id}")
async def delete_model(model_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(AIModel).filter(AIModel.id == model_id))
    model = result.scalar_one_or_none()
    if not model:
        raise HTTPException(status_code=404, detail="模型不存在")

    model.is_active = False
    await db.commit()
    return {"message": "Model deleted"}


@router.post("/{model_id}/test-chat", response_model=AIModelTestChatResponse)
async def test_model_chat(model_id: int, data: AIModelTestChatRequest, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(AIModel).filter(AIModel.id == model_id, AIModel.is_active == True))
    model = result.scalar_one_or_none()
    if not model:
        raise HTTPException(status_code=404, detail="模型不存在或已停用")

    try:
        api_key = decrypt_api_key(model.api_key_encrypted)
    except Exception:
        raise HTTPException(status_code=400, detail="模型 API Key 解密失败，请检查加密配置")

    client = get_ai_client(
        api_key=api_key,
        base_url=model.base_url,
        model_name=model.model_name,
        protocol=model.protocol,
        reasoning_effort=getattr(model, "reasoning_effort", None),
    )
    if not client:
        raise HTTPException(status_code=400, detail="模型配置无效，请检查 API Key、Base URL 和模型名称")

    messages = [
        {"role": "system", "content": "你是一个用于模型连通性测试的 AI 助手，请简洁回答用户问题。"},
        *[{"role": message.role, "content": message.content} for message in data.messages],
    ]

    started_at = perf_counter()
    try:
        reply = await request_text_response(
            client,
            messages,
            temperature=data.temperature,
            max_tokens=data.max_tokens,
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"模型调用失败：{str(e)}")

    latency_ms = int((perf_counter() - started_at) * 1000)
    if not reply:
        raise HTTPException(status_code=502, detail="模型未返回有效回复")

    return AIModelTestChatResponse(
        reply=reply,
        model=model.model_name,
        provider=model.provider,
        latency_ms=latency_ms,
    )


@router.post("/{model_id}/set-default")
async def set_default_model(model_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(AIModel).filter(AIModel.id == model_id))
    model = result.scalar_one_or_none()
    if not model:
        raise HTTPException(status_code=404, detail="模型不存在")

    await db.execute(update(AIModel).values(is_default=False))
    model.is_default = True
    await db.commit()

    return {"message": "Default model updated"}



