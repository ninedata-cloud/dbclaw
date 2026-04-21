"""
Integration 管理服务

仅保留 Integration(模板/驱动) 管理能力。
实例化参数由订阅(integration_targets)、数据源(inbound_source)、bot binding(params) 承载。
"""

import asyncio
import logging
from typing import List, Optional, Dict, Any
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_

from backend.models.integration import Integration
from backend.models.soft_delete import alive_filter, alive_select, get_alive_by_id
from backend.schemas.integration import IntegrationCreate, IntegrationUpdate
from backend.services.integration_executor import IntegrationExecutor
from backend.utils.encryption import encrypt_value
from backend.utils.datetime_helper import now

logger = logging.getLogger(__name__)


class IntegrationService:
    """Integration 管理服务"""

    @staticmethod
    def encrypt_sensitive_params(params: Dict[str, Any] | None) -> Dict[str, Any]:
        """对 params 中以 ENCRYPT: 开头的字符串做加密落库。"""
        encrypted_params: Dict[str, Any] = {}
        for key, value in (params or {}).items():
            if isinstance(value, str) and value.startswith("ENCRYPT:"):
                encrypted_params[key] = "encrypted:" + encrypt_value(value[8:])
            else:
                encrypted_params[key] = value
        return encrypted_params

    @staticmethod
    async def create_integration(db: AsyncSession, data: IntegrationCreate) -> Integration:
        """创建 Integration"""
        result = await db.execute(
            select(Integration).where(Integration.integration_code == data.integration_code, alive_filter(Integration))
        )
        existing = result.scalar_one_or_none()
        if existing:
            raise ValueError(f"Integration ID '{data.integration_code}' 已存在")

        integration = Integration(
            integration_code=data.integration_code,
            name=data.name,
            description=data.description,
            integration_type=data.integration_type,
            category=data.category,
            is_builtin=data.is_builtin,
            code=data.code,
            config_schema=data.config_schema,
            is_enabled=data.enabled,
        )

        db.add(integration)
        await db.commit()
        await db.refresh(integration)
        logger.info("创建 Integration: %s (ID: %s)", integration.name, integration.integration_code)
        return integration

    @staticmethod
    async def update_integration(db: AsyncSession, integration_id: int, data: IntegrationUpdate) -> Integration:
        """更新 Integration"""
        integration = await get_alive_by_id(db, Integration, integration_id)
        if not integration:
            raise ValueError("Integration 不存在")

        if integration.is_builtin:
            if integration.integration_id in {"builtin_feishu_bot", "builtin_dingtalk_bot"}:
                if data.name is not None:
                    integration.name = data.name
                if data.description is not None:
                    integration.description = data.description
                if data.code is not None:
                    integration.code = data.code
                if data.config_schema is not None:
                    integration.config_schema = data.config_schema
                if data.enabled is not None:
                    integration.is_enabled = data.enabled
            else:
                if data.enabled is not None:
                    integration.is_enabled = data.enabled
        else:
            if data.name is not None:
                integration.name = data.name
            if data.description is not None:
                integration.description = data.description
            if data.code is not None:
                integration.code = data.code
            if data.config_schema is not None:
                integration.config_schema = data.config_schema
            if data.enabled is not None:
                integration.is_enabled = data.enabled

        integration.updated_at = now()
        await db.commit()
        await db.refresh(integration)
        logger.info("更新 Integration: %s", integration.name)
        return integration

    @staticmethod
    async def delete_integration(db: AsyncSession, integration_id: int) -> None:
        """删除 Integration"""
        integration = await get_alive_by_id(db, Integration, integration_id)
        if not integration:
            raise ValueError("Integration 不存在")
        if integration.is_builtin:
            raise ValueError("不能删除内置模板")

        integration.soft_delete(None)
        await db.commit()
        logger.info("删除 Integration: %s", integration.name)

    @staticmethod
    async def list_integration(
        db: AsyncSession,
        integration_type: Optional[str] = None,
        category: Optional[str] = None,
        enabled: Optional[bool] = None,
        is_builtin: Optional[bool] = None,
    ) -> List[Integration]:
        """查询 Integration 列表"""
        query = alive_select(Integration)
        conditions = []

        if integration_type:
            conditions.append(Integration.integration_type == integration_type)
        if category:
            conditions.append(Integration.category == category)
        if enabled is not None:
            conditions.append(Integration.is_enabled == enabled)
        if is_builtin is not None:
            conditions.append(Integration.is_builtin == is_builtin)

        if conditions:
            query = query.where(and_(*conditions))

        query = query.order_by(Integration.is_builtin.desc(), Integration.created_at.desc())
        result = await db.execute(query)
        return result.scalars().all()

    @staticmethod
    async def get_integration(db: AsyncSession, integration_id: int) -> Optional[Integration]:
        return await get_alive_by_id(db, Integration, integration_id)

    @staticmethod
    async def get_integration_by_integration_id(db: AsyncSession, integration_id: str) -> Optional[Integration]:
        result = await db.execute(select(Integration).where(Integration.integration_id == integration_id, alive_filter(Integration)))
        return result.scalar_one_or_none()

    @staticmethod
    async def test_integration(
        db: AsyncSession,
        integration_id: int,
        test_params: Dict[str, Any],
        test_payload: Optional[Dict[str, Any]] = None,
        datasource_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        """测试 Integration"""
        integration = await get_alive_by_id(db, Integration, integration_id)
        if not integration:
            raise ValueError("Integration 不存在")
        if not integration.is_enabled:
            raise ValueError("Integration 已禁用")

        executor = IntegrationExecutor(db, logger)
        test_params = IntegrationService.encrypt_sensitive_params(test_params)

        if integration.integration_type == "outbound_notification":
            if not test_payload:
                test_payload = {
                    "title": "测试通知",
                    "content": "这是一条测试通知消息",
                    "severity": "info",
                    "datasource_name": "测试数据源",
                    "alert_id": 0,
                    "timestamp": now().isoformat(),
                }

            return await executor.execute_notification(integration.code, test_params, test_payload)

        if integration.integration_type == "inbound_metric":
            from backend.models.datasource import Datasource

            if datasource_id:
                test_datasource = await get_alive_by_id(db, Datasource, datasource_id)
                if not test_datasource:
                    return {"success": False, "message": f"数据源 ID {datasource_id} 不存在"}
            else:
                ds_result = await db.execute(alive_select(Datasource).limit(1))
                test_datasource = ds_result.scalar_one_or_none()
                if not test_datasource:
                    return {
                        "success": False,
                        "message": "没有可用的测试数据源，请先创建数据源或在测试时指定 datasource_id",
                    }

            datasource = [
                {
                    "id": test_datasource.id,
                    "name": test_datasource.name,
                    "db_type": test_datasource.db_type,
                    "external_instance_id": getattr(test_datasource, "external_instance_id", None),
                }
            ]

            try:
                metrics = await executor.execute_metric_collection(integration.code, test_params, datasource)
                return {"success": True, "message": f"采集到 {len(metrics)} 条指标", "data": {"metrics": metrics[:10]}}
            except Exception as e:
                return {"success": False, "message": f"测试失败: {str(e)}"}

        if integration.integration_type == "bot":
            if integration.integration_id == "builtin_feishu_bot":
                try:
                    from backend.services.feishu_service import feishu_service
                    from backend.services.feishu_bot_service import _extract_feishu_bot_config

                    config = _extract_feishu_bot_config(integration)
                    app_id = (config.get("app_id") or "").strip()
                    app_secret = (config.get("app_secret") or "").strip()
                    signing_secret = (config.get("signing_secret") or "").strip()
                    if not app_id or not app_secret:
                        return {"success": False, "message": "请先在 Integration 代码中配置 APP_ID 和 APP_SECRET"}

                    await feishu_service.get_tenant_access_token(app_id, app_secret)
                    return {
                        "success": True,
                        "message": "飞书机器人配置可用，tenant_access_token 获取成功，可用于长连接模式",
                        "data": {"app_id": app_id, "signing_secret_configured": bool(signing_secret)},
                    }
                except Exception as e:
                    return {"success": False, "message": f"飞书机器人测试失败: {str(e)}"}

            if integration.integration_id == "builtin_dingtalk_bot":
                try:
                    from backend.services.dingtalk_bot_service import _extract_dingtalk_bot_config

                    config = _extract_dingtalk_bot_config(integration)
                    client_id = (config.get("client_id") or "").strip()
                    client_secret = (config.get("client_secret") or "").strip()
                    if not client_id or not client_secret:
                        return {"success": False, "message": "请先在 Integration 代码中配置 CLIENT_ID 和 CLIENT_SECRET"}

                    try:
                        from dingtalk_stream import Credential, DingTalkStreamClient
                    except Exception:
                        return {"success": False, "message": "未安装 dingtalk-stream，请先执行 pip install -r requirements.txt"}

                    client = DingTalkStreamClient(Credential(client_id, client_secret))
                    access_token = await asyncio.to_thread(client.get_access_token)
                    return {
                        "success": bool(access_token),
                        "message": "钉钉机器人配置可用，access_token 获取成功，可用于 Stream 模式" if access_token else "钉钉机器人 access_token 获取失败",
                        "data": {"client_id": client_id, "has_access_token": bool(access_token)},
                    }
                except Exception as e:
                    return {"success": False, "message": f"钉钉机器人测试失败: {str(e)}"}

            if integration.integration_id == "builtin_weixin_bot":
                baseurl = str(test_params.get("baseurl") or "").strip()
                if not baseurl:
                    return {"success": False, "message": "请提供 baseurl 以测试微信扫码登录接口"}
                try:
                    from backend.services.weixin_service import weixin_service

                    resp = await weixin_service.get_bot_qrcode(baseurl)
                    qrcode = resp.get("qrcode") or resp.get("data", {}).get("qrcode")
                    return {
                        "success": bool(qrcode),
                        "message": "微信机器人登录接口可用" if qrcode else "微信机器人登录接口返回异常，未拿到 qrcode",
                        "data": {"has_qrcode": bool(qrcode), "raw": resp},
                    }
                except Exception as e:
                    return {"success": False, "message": f"微信机器人测试失败: {str(e)}"}

            return {"success": True, "message": "机器人 Integration 配置格式有效"}

        return {"success": False, "message": f"不支持的 Integration 类型: {integration.integration_type}"}

    @staticmethod
    async def load_builtin_templates(db: AsyncSession):
        from backend.utils.integration_templates import BUILTIN_TEMPLATES

        loaded_count = 0
        updated_count = 0

        for template in BUILTIN_TEMPLATES:
            result = await db.execute(select(Integration).where(Integration.integration_id == template["integration_id"]))
            existing = result.scalar_one_or_none()

            if existing:
                if existing.integration_id in {"builtin_feishu_bot", "builtin_dingtalk_bot"}:
                    if not existing.description:
                        existing.description = template["description"]
                    if existing.config_schema in (None, {}, {"type": "object", "properties": {}, "required": []}):
                        existing.config_schema = template["config_schema"]
                    preserve_marker = "APP_ID" if existing.integration_id == "builtin_feishu_bot" else "CLIENT_ID"
                    fallback_marker = None if existing.integration_id == "builtin_feishu_bot" else "APP_KEY"
                    if not existing.code or (
                        preserve_marker not in existing.code
                        and (fallback_marker is None or fallback_marker not in existing.code)
                    ):
                        existing.code = template["code"]
                else:
                    existing.code = template["code"]
                    existing.config_schema = template["config_schema"]
                    existing.description = template["description"]
                    existing.name = template["name"]
                existing.updated_at = now()
                updated_count += 1
            else:
                integration = Integration(
                    integration_id=template["integration_id"],
                    name=template["name"],
                    description=template["description"],
                    integration_type=template["integration_type"],
                    category=template["category"],
                    is_builtin=True,
                    code=template["code"],
                    config_schema=template["config_schema"],
                    is_enabled=True,
                )
                db.add(integration)
                loaded_count += 1

        await db.commit()
        logger.info("内置模板加载完成: 新增 %s 个，更新 %s 个", loaded_count, updated_count)
