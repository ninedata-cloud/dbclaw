"""
Integration 管理服务
"""

import logging
from typing import List, Optional, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_
from datetime import datetime

from backend.models.integration import Integration, AlertChannel
from backend.schemas.integration import IntegrationCreate, IntegrationUpdate, AlertChannelCreate
from backend.services.integration_executor import IntegrationExecutor

logger = logging.getLogger(__name__)


class IntegrationService:
    """Integration 管理服务"""

    @staticmethod
    async def create_integration(
        db: AsyncSession,
        data: IntegrationCreate
    ) -> Integration:
        """创建 Integration"""
        # 检查 integration_id 是否已存在
        result = await db.execute(
            select(Integration).where(Integration.integration_id == data.integration_id)
        )
        existing = result.scalar_one_or_none()

        if existing:
            raise ValueError(f"Integration ID '{data.integration_id}' 已存在")

        integration = Integration(
            integration_id=data.integration_id,
            name=data.name,
            description=data.description,
            integration_type=data.integration_type,
            category=data.category,
            is_builtin=data.is_builtin,
            code=data.code,
            config_schema=data.config_schema,
            enabled=data.enabled
        )

        db.add(integration)
        await db.commit()
        await db.refresh(integration)

        logger.info(f"创建 Integration: {integration.name} (ID: {integration.integration_id})")
        return integration

    @staticmethod
    async def update_integration(
        db: AsyncSession,
        integration_id: int,
        data: IntegrationUpdate
    ) -> Integration:
        """更新 Integration"""
        integration = await db.get(Integration, integration_id)
        if not integration:
            raise ValueError("Integration 不存在")

        # 内置模板不允许修改某些字段
        if integration.is_builtin:
            # 只允许修改 enabled 状态
            if data.enabled is not None:
                integration.enabled = data.enabled
        else:
            # 自定义 Integration 可以修改所有字段
            if data.name is not None:
                integration.name = data.name
            if data.description is not None:
                integration.description = data.description
            if data.code is not None:
                integration.code = data.code
            if data.config_schema is not None:
                integration.config_schema = data.config_schema
            if data.enabled is not None:
                integration.enabled = data.enabled

        integration.updated_at = datetime.utcnow()
        await db.commit()
        await db.refresh(integration)

        logger.info(f"更新 Integration: {integration.name}")
        return integration

    @staticmethod
    async def delete_integration(db: AsyncSession, integration_id: int):
        """删除 Integration"""
        integration = await db.get(Integration, integration_id)
        if not integration:
            raise ValueError("Integration 不存在")

        if integration.is_builtin:
            raise ValueError("不能删除内置模板")

        # 检查是否有关联的 Channel
        result = await db.execute(
            select(AlertChannel).where(AlertChannel.integration_id == integration_id)
        )
        channels = result.scalars().all()

        if channels:
            raise ValueError(f"该 Integration 有 {len(channels)} 个关联的 Channel，请先删除这些 Channel")

        await db.delete(integration)
        await db.commit()

        logger.info(f"删除 Integration: {integration.name}")

    @staticmethod
    async def list_integrations(
        db: AsyncSession,
        integration_type: Optional[str] = None,
        category: Optional[str] = None,
        enabled: Optional[bool] = None,
        is_builtin: Optional[bool] = None
    ) -> List[Integration]:
        """查询 Integration 列表"""
        query = select(Integration)
        conditions = []

        if integration_type:
            conditions.append(Integration.integration_type == integration_type)
        if category:
            conditions.append(Integration.category == category)
        if enabled is not None:
            conditions.append(Integration.enabled == enabled)
        if is_builtin is not None:
            conditions.append(Integration.is_builtin == is_builtin)

        if conditions:
            query = query.where(and_(*conditions))

        query = query.order_by(
            Integration.is_builtin.desc(),
            Integration.created_at.desc()
        )

        result = await db.execute(query)
        return result.scalars().all()

    @staticmethod
    async def get_integration(
        db: AsyncSession,
        integration_id: int
    ) -> Optional[Integration]:
        """获取单个 Integration"""
        return await db.get(Integration, integration_id)

    @staticmethod
    async def get_integration_by_integration_id(
        db: AsyncSession,
        integration_id: str
    ) -> Optional[Integration]:
        """通过 integration_id 获取 Integration"""
        result = await db.execute(
            select(Integration).where(Integration.integration_id == integration_id)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def test_integration(
        db: AsyncSession,
        integration_id: int,
        test_params: Dict[str, Any],
        test_payload: Optional[Dict[str, Any]] = None,
        datasource_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """测试 Integration"""
        integration = await db.get(Integration, integration_id)
        if not integration:
            raise ValueError("Integration 不存在")

        if not integration.enabled:
            raise ValueError("Integration 已禁用")

        executor = IntegrationExecutor(db, logger)

        if integration.integration_type == "outbound_notification":
            # 测试出站通知
            if not test_payload:
                test_payload = {
                    "title": "测试通知",
                    "content": "这是一条测试通知消息",
                    "severity": "info",
                    "datasource_name": "测试数据源",
                    "alert_id": 0,
                    "timestamp": datetime.utcnow().isoformat()
                }

            result = await executor.execute_notification(
                integration.code,
                test_params,
                test_payload
            )

            return result

        elif integration.integration_type == "inbound_metric":
            # 测试入站指标
            from backend.models.datasource import Datasource

            # 如果指定了数据源 ID，使用指定的数据源
            if datasource_id:
                test_datasource = await db.get(Datasource, datasource_id)
                if not test_datasource:
                    return {
                        "success": False,
                        "message": f"数据源 ID {datasource_id} 不存在"
                    }
            else:
                # 否则查询一个测试数据源
                ds_result = await db.execute(select(Datasource).limit(1))
                test_datasource = ds_result.scalar_one_or_none()

                if not test_datasource:
                    return {
                        "success": False,
                        "message": "没有可用的测试数据源，请先创建数据源或在测试时指定 datasource_id"
                    }

            datasources = [{
                "id": test_datasource.id,
                "name": test_datasource.name,
                "db_type": test_datasource.db_type,
                "external_instance_id": getattr(test_datasource, "external_instance_id", None)
            }]

            try:
                metrics = await executor.execute_metric_collection(
                    integration.code,
                    test_params,
                    datasources
                )

                return {
                    "success": True,
                    "message": f"采集到 {len(metrics)} 条指标",
                    "data": {"metrics": metrics[:10]}  # 只返回前 10 条
                }

            except Exception as e:
                return {
                    "success": False,
                    "message": f"测试失败: {str(e)}"
                }

        else:
            return {
                "success": False,
                "message": f"不支持的 Integration 类型: {integration.integration_type}"
            }

    @staticmethod
    async def load_builtin_templates(db: AsyncSession):
        """加载内置模板"""
        from backend.utils.integration_templates import BUILTIN_TEMPLATES

        loaded_count = 0
        updated_count = 0

        for template in BUILTIN_TEMPLATES:
            # 检查是否已存在
            result = await db.execute(
                select(Integration).where(
                    Integration.integration_id == template["integration_id"]
                )
            )
            existing = result.scalar_one_or_none()

            if existing:
                # 更新代码（保持用户的 enabled 状态）
                existing.code = template["code"]
                existing.config_schema = template["config_schema"]
                existing.description = template["description"]
                existing.name = template["name"]
                existing.updated_at = datetime.utcnow()
                updated_count += 1
                logger.info(f"更新内置模板: {template['name']}")
            else:
                # 创建新模板
                integration = Integration(
                    integration_id=template["integration_id"],
                    name=template["name"],
                    description=template["description"],
                    integration_type=template["integration_type"],
                    category=template["category"],
                    is_builtin=True,
                    code=template["code"],
                    config_schema=template["config_schema"],
                    enabled=True
                )
                db.add(integration)
                loaded_count += 1
                logger.info(f"加载内置模板: {template['name']}")

        await db.commit()
        logger.info(f"内置模板加载完成: 新增 {loaded_count} 个，更新 {updated_count} 个")

    # ===== AlertChannel 管理 =====

    @staticmethod
    async def create_channel(
        db: AsyncSession,
        data: AlertChannelCreate,
        user_id: Optional[int] = None
    ) -> AlertChannel:
        """创建 Channel"""
        # 检查 Integration 是否存在且启用
        integration = await db.get(Integration, data.integration_id)
        if not integration:
            raise ValueError("Integration 不存在")
        if not integration.enabled:
            raise ValueError("Integration 已禁用")

        # 加密敏感参数
        from backend.utils.encryption import encrypt_value

        encrypted_params = {}
        for key, value in data.params.items():
            if isinstance(value, str) and value.startswith("ENCRYPT:"):
                # 需要加密
                plaintext = value[8:]  # 去掉前缀
                encrypted_params[key] = "encrypted:" + encrypt_value(plaintext)
            else:
                encrypted_params[key] = value

        channel = AlertChannel(
            name=data.name,
            description=data.description,
            integration_id=data.integration_id,
            params=encrypted_params,
            enabled=data.enabled,
            user_id=user_id
        )

        db.add(channel)
        await db.commit()
        await db.refresh(channel)

        logger.info(f"创建 Channel: {channel.name}")
        return channel

    @staticmethod
    async def update_channel(
        db: AsyncSession,
        channel_id: int,
        data: Dict[str, Any]
    ) -> AlertChannel:
        """更新 Channel"""
        channel = await db.get(AlertChannel, channel_id)
        if not channel:
            raise ValueError("Channel 不存在")

        # 更新字段
        if "name" in data:
            channel.name = data["name"]
        if "description" in data:
            channel.description = data["description"]
        if "enabled" in data:
            channel.enabled = data["enabled"]

        if "params" in data:
            # 加密敏感参数
            from backend.utils.encryption import encrypt_value

            encrypted_params = {}
            for key, value in data["params"].items():
                if isinstance(value, str) and value.startswith("ENCRYPT:"):
                    plaintext = value[8:]
                    encrypted_params[key] = "encrypted:" + encrypt_value(plaintext)
                else:
                    encrypted_params[key] = value

            channel.params = encrypted_params

        channel.updated_at = datetime.utcnow()
        await db.commit()
        await db.refresh(channel)

        logger.info(f"更新 Channel: {channel.name}")
        return channel

    @staticmethod
    async def delete_channel(db: AsyncSession, channel_id: int):
        """删除 Channel"""
        channel = await db.get(AlertChannel, channel_id)
        if not channel:
            raise ValueError("Channel 不存在")

        await db.delete(channel)
        await db.commit()

        logger.info(f"删除 Channel: {channel.name}")

    @staticmethod
    async def list_channels(
        db: AsyncSession,
        integration_id: Optional[int] = None,
        enabled: Optional[bool] = None,
        user_id: Optional[int] = None
    ) -> List[AlertChannel]:
        """查询 Channel 列表"""
        query = select(AlertChannel)
        conditions = []

        if integration_id:
            conditions.append(AlertChannel.integration_id == integration_id)
        if enabled is not None:
            conditions.append(AlertChannel.enabled == enabled)
        if user_id is not None:
            conditions.append(
                or_(
                    AlertChannel.user_id == user_id,
                    AlertChannel.user_id.is_(None)  # 公共 Channel
                )
            )

        if conditions:
            query = query.where(and_(*conditions))

        query = query.order_by(AlertChannel.created_at.desc())

        result = await db.execute(query)
        return result.scalars().all()

    @staticmethod
    async def get_channel(
        db: AsyncSession,
        channel_id: int
    ) -> Optional[AlertChannel]:
        """获取单个 Channel"""
        return await db.get(AlertChannel, channel_id)
