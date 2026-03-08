from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from typing import List

from backend.database import get_db
from backend.models.ai_model import AIModel
from backend.schemas.ai_model import AIModelCreate, AIModelUpdate, AIModelResponse
from backend.dependencies import get_current_user
from backend.utils.encryption import encrypt_value, decrypt_value

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
    result = await db.execute(select(AIModel).filter(AIModel.is_active == True))
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
        raise HTTPException(status_code=400, detail="Model name already exists")

    model = AIModel(
        name=data.name,
        provider=data.provider,
        api_key_encrypted=encrypt_api_key(data.api_key),
        base_url=data.base_url,
        model_name=data.model_name
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
        raise HTTPException(status_code=404, detail="Model not found")

    if data.name:
        model.name = data.name
    if data.provider:
        model.provider = data.provider
    if data.api_key:
        model.api_key_encrypted = encrypt_api_key(data.api_key)
    if data.base_url:
        model.base_url = data.base_url
    if data.model_name:
        model.model_name = data.model_name

    await db.commit()
    await db.refresh(model)

    return AIModelResponse(
        **{**model.__dict__, "api_key_masked": mask_api_key(decrypt_api_key(model.api_key_encrypted))}
    )


@router.delete("/{model_id}")
async def delete_model(model_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(AIModel).filter(AIModel.id == model_id))
    model = result.scalar_one_or_none()
    if not model:
        raise HTTPException(status_code=404, detail="Model not found")

    model.is_active = False
    await db.commit()
    return {"message": "Model deleted"}


@router.post("/{model_id}/set-default")
async def set_default_model(model_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(AIModel).filter(AIModel.id == model_id))
    model = result.scalar_one_or_none()
    if not model:
        raise HTTPException(status_code=404, detail="Model not found")

    await db.execute(update(AIModel).values(is_default=False))
    model.is_default = True
    await db.commit()

    return {"message": "Default model updated"}

