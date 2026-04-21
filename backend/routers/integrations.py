"""
Integration API 端点
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional, Dict, Any

from backend.database import get_db
from backend.models.user import User
from backend.schemas.integration import (
    IntegrationCreate,
    IntegrationUpdate,
    IntegrationResponse,
)
from backend.services.integration_service import IntegrationService
from backend.routers.auth import get_current_user

router = APIRouter(prefix="/api", tags=["integration"])


@router.post("/integrations", response_model=IntegrationResponse)
async def create_integration(
    data: IntegrationCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """创建 Integration（仅管理员）"""
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="需要管理员权限")

    if data.is_builtin:
        raise HTTPException(status_code=400, detail="不能创建内置模板")

    try:
        integration = await IntegrationService.create_integration(db, data)
        return integration
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/integrations", response_model=List[IntegrationResponse])
async def list_integration(
    integration_type: Optional[str] = Query(None, description="集成类型过滤"),
    category: Optional[str] = Query(None, description="分类过滤"),
    enabled: Optional[bool] = Query(None, description="启用状态过滤"),
    is_builtin: Optional[bool] = Query(None, description="是否内置过滤"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """查询 Integration 列表"""
    integration = await IntegrationService.list_integration(
        db,
        integration_type=integration_type,
        category=category,
        enabled=enabled,
        is_builtin=is_builtin
    )
    return integration


@router.get("/integrations/{integration_id}", response_model=IntegrationResponse)
async def get_integration(
    integration_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """获取单个 Integration"""
    integration = await IntegrationService.get_integration(db, integration_id)
    if not integration:
        raise HTTPException(status_code=404, detail="Integration 不存在")
    return integration


@router.put("/integrations/{integration_id}", response_model=IntegrationResponse)
async def update_integration(
    integration_id: int,
    data: IntegrationUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """更新 Integration"""
    integration = await IntegrationService.get_integration(db, integration_id)
    if not integration:
        raise HTTPException(status_code=404, detail="Integration 不存在")

    if integration.is_builtin and not current_user.is_admin:
        raise HTTPException(status_code=403, detail="需要管理员权限")

    if not integration.is_builtin and not current_user.is_admin:
        pass

    try:
        updated = await IntegrationService.update_integration(db, integration_id, data)
        return updated
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/integrations/{integration_id}")
async def delete_integration(
    integration_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """删除 Integration（仅管理员）"""
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="需要管理员权限")

    try:
        await IntegrationService.delete_integration(db, integration_id)
        return {"message": "删除成功"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/integrations/{integration_id}/test")
async def test_integration(
    integration_id: int,
    test_data: Dict[str, Any],
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """测试 Integration"""
    test_params = test_data.get("params", {})
    test_payload = test_data.get("payload")
    datasource_id = test_data.get("datasource_id")

    try:
        result = await IntegrationService.test_integration(
            db,
            integration_id,
            test_params,
            test_payload,
            datasource_id
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/integrations/load-builtin")
async def load_builtin_templates(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """加载内置模板（仅管理员）"""
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="需要管理员权限")

    await IntegrationService.load_builtin_templates(db)
    return {"message": "内置模板加载成功"}
