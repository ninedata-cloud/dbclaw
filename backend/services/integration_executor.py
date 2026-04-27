"""
Integration 执行引擎

提供 IntegrationContext API 和执行环境
"""

import asyncio
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime
import aiohttp
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from concurrent.futures import ThreadPoolExecutor

from backend.utils.encryption import decrypt_value

logger = logging.getLogger(__name__)

# 线程池用于执行同步代码（如 smtplib）
_thread_pool = ThreadPoolExecutor(max_workers=4)


class IntegrationContext:
    """提供给 Integration 代码的上下文对象"""

    def __init__(self, db_session: AsyncSession, logger_instance: logging.Logger):
        self.db = db_session
        self.logger = logger_instance
        self._http_session: Optional[aiohttp.ClientSession] = None

    async def http_request(self, method: str, url: str, **kwargs):
        """
        发送 HTTP 请求

        Args:
            method: HTTP 方法（GET/POST/PUT/DELETE）
            url: 请求 URL
            **kwargs: 传递给 aiohttp 的其他参数

        Returns:
            Response 对象，包含 status_code、text、json() 方法
        """
        if not self._http_session:
            timeout = aiohttp.ClientTimeout(total=30)
            self._http_session = aiohttp.ClientSession(timeout=timeout)

        try:
            async with self._http_session.request(method, url, **kwargs) as response:
                # 创建一个简化的响应对象
                class SimpleResponse:
                    def __init__(self, status, text_content, json_content, headers):
                        self.status_code = status
                        self.text = text_content
                        self._json_content = json_content
                        self.headers = dict(headers or {})

                    def json(self):
                        return self._json_content

                    def header(self, name: str, default=None):
                        for key, value in self.headers.items():
                            if key.lower() == name.lower():
                                return value
                        return default

                text_content = await response.text()
                json_content = None
                try:
                    json_content = await response.json()
                except (ValueError, aiohttp.ContentTypeError):
                    pass

                return SimpleResponse(response.status, text_content, json_content, response.headers)

        except Exception as e:
            self.logger.error(f"HTTP 请求失败: {str(e)}")
            raise

    async def get_system_config(self, key: str) -> Optional[str]:
        """
        读取系统配置

        Args:
            key: 配置键名

        Returns:
            配置值，如果不存在返回 None
        """
        from backend.models.system_config import SystemConfig

        result = await self.db.execute(
            select(SystemConfig).where(SystemConfig.key == key)
        )
        config = result.scalar_one_or_none()

        if config:
            if config.is_encrypted and config.value:
                from backend.utils.encryption import decrypt_value
                return decrypt_value(config.value)
            return config.value
        return None

    async def encrypt(self, plaintext: str) -> str:
        """
        加密敏感信息

        Args:
            plaintext: 明文

        Returns:
            加密后的密文
        """
        from backend.utils.encryption import encrypt_value
        return encrypt_value(plaintext)

    async def decrypt(self, ciphertext: str) -> str:
        """
        解密敏感信息

        Args:
            ciphertext: 密文

        Returns:
            解密后的明文
        """
        return decrypt_value(ciphertext)

    async def log(self, level: str, message: str):
        """
        记录日志

        Args:
            level: 日志级别（debug/info/warning/error）
            message: 日志消息
        """
        log_func = getattr(self.logger, level.lower(), self.logger.info)
        log_func(f"[Integration] {message}")

    async def get_datasource(self, datasource_id: int) -> Optional[Dict[str, Any]]:
        """
        查询数据源信息

        Args:
            datasource_id: 数据源 ID

        Returns:
            数据源信息字典，如果不存在返回 None
        """
        from backend.models.datasource import Datasource
        from backend.models.soft_delete import alive_filter

        result = await self.db.execute(
            select(Datasource).where(Datasource.id == datasource_id, alive_filter(Datasource))
        )
        ds = result.scalar_one_or_none()

        if ds:
            return {
                "id": ds.id,
                "name": ds.name,
                "db_type": ds.db_type,
                "host": ds.host,
                "port": ds.port,
                "database": ds.database,
                "external_instance_id": getattr(ds, "external_instance_id", None)
            }
        return None

    async def close(self):
        """关闭资源"""
        if self._http_session:
            await self._http_session.close()
            self._http_session = None


class IntegrationExecutor:
    """Integration 执行引擎"""

    # 执行超时时间（秒）
    EXECUTION_TIMEOUT = 60  # 增加到 60 秒，因为邮件发送可能较慢

    def __init__(self, db_session: AsyncSession, logger_instance: logging.Logger = None):
        self.db = db_session
        self.logger = logger_instance or logger

    async def execute_notification(
        self,
        integration_code: str,
        params: Dict[str, Any],
        payload: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        执行出站通知 Integration

        Args:
            integration_code: Integration Python 代码
            params: 实例化参数（来自 alert_channels.params）
            payload: 通知内容
                - title: str
                - content: str
                - severity: str (critical/warning/info)
                - datasource_name: str
                - alert_id: int
                - timestamp: str

        Returns:
            执行结果 {"success": bool, "message": str, "data": dict}
        """
        context = IntegrationContext(self.db, self.logger)

        try:
            # 解密敏感参数
            decrypted_params = await self._decrypt_params(context, params)

            # 执行用户代码（带超时）
            result = await asyncio.wait_for(
                self._execute_notification_internal(
                    context, integration_code, decrypted_params, payload
                ),
                timeout=self.EXECUTION_TIMEOUT
            )

            return result

        except asyncio.TimeoutError:
            error_msg = f"执行超时（超过 {self.EXECUTION_TIMEOUT} 秒）"
            self.logger.error(error_msg)
            return {"success": False, "message": error_msg}

        except Exception as e:
            error_msg = f"执行失败: {str(e)}"
            self.logger.error(error_msg, exc_info=True)
            return {"success": False, "message": error_msg}

        finally:
            await context.close()

    async def _execute_notification_internal(
        self,
        context: IntegrationContext,
        integration_code: str,
        params: Dict[str, Any],
        payload: Dict[str, Any]
    ) -> Dict[str, Any]:
        """内部执行方法"""
        # 执行用户代码，允许导入标准库模块
        # 使用同一个字典作为全局和局部命名空间，这样 import 的模块对函数可见
        namespace = {
            "__builtins__": __builtins__,
            "_thread_pool": _thread_pool  # 提供线程池给用户代码
        }
        exec(integration_code, namespace, namespace)

        if "send_notification" not in namespace:
            return {"success": False, "message": "代码中未定义 send_notification 函数"}

        send_notification = namespace["send_notification"]

        # 调用用户函数
        try:
            result = await send_notification(context, params, payload)
        except KeyError as e:
            missing_key = e.args[0] if e.args else "unknown"
            return {
                "success": False,
                "message": f"Integration 参数缺失: {missing_key}",
                "data": {"missing_param": missing_key},
            }

        # 确保返回格式正确
        if not isinstance(result, dict):
            return {"success": False, "message": "send_notification 必须返回字典"}

        if "success" not in result:
            result["success"] = False

        return result

    async def execute_metric_collection(
        self,
        integration_code: str,
        params: Dict[str, Any],
        datasource: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        执行入站指标 Integration

        Args:
            integration_code: Integration Python 代码
            params: 实例化参数（来自 alert_channels.params）
            datasource: 关联的数据源列表

        Returns:
            MetricPoint 列表
                - datasource_id: int
                - metric_name: str
                - metric_value: float
                - timestamp: str (ISO 8601)
                - labels: dict (可选)
        """
        context = IntegrationContext(self.db, self.logger)

        try:
            # 解密敏感参数
            decrypted_params = await self._decrypt_params(context, params)

            # 执行用户代码（带超时）
            metrics = await asyncio.wait_for(
                self._execute_metric_collection_internal(
                    context, integration_code, decrypted_params, datasource
                ),
                timeout=self.EXECUTION_TIMEOUT
            )

            return metrics

        except asyncio.TimeoutError:
            error_msg = f"执行超时（超过 {self.EXECUTION_TIMEOUT} 秒）"
            self.logger.error(error_msg)
            raise RuntimeError(error_msg)

        except Exception as e:
            error_msg = f"执行失败: {str(e)}"
            self.logger.error(error_msg, exc_info=True)
            raise

        finally:
            await context.close()

    async def _execute_metric_collection_internal(
        self,
        context: IntegrationContext,
        integration_code: str,
        params: Dict[str, Any],
        datasource: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """内部执行方法"""
        # 执行用户代码，允许导入标准库模块
        # 使用同一个字典作为全局和局部命名空间，这样 import 的模块对函数可见
        namespace = {"__builtins__": __builtins__}
        exec(integration_code, namespace, namespace)

        if "fetch_metrics" not in namespace:
            raise ValueError("代码中未定义 fetch_metrics 函数")

        fetch_metrics = namespace["fetch_metrics"]

        # 调用用户函数
        metrics = await fetch_metrics(context, params, datasource)

        # 验证返回格式
        if not isinstance(metrics, list):
            raise ValueError("fetch_metrics 必须返回列表")

        return metrics

    async def _decrypt_params(
        self,
        context: IntegrationContext,
        params: Dict[str, Any]
    ) -> Dict[str, Any]:
        """解密敏感参数"""
        decrypted_params = {}

        for key, value in params.items():
            if isinstance(value, str) and value.startswith("encrypted:"):
                # 解密
                decrypted_params[key] = await context.decrypt(value[10:])
            else:
                decrypted_params[key] = value

        return decrypted_params
