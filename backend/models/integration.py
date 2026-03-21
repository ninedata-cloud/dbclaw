"""统一外部集成管理数据模型"""
from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime, JSON
from sqlalchemy.sql import func
from backend.database import Base


class Integration(Base):
    """外部集成配置表"""
    __tablename__ = "integrations"

    id = Column(Integer, primary_key=True, index=True)
    integration_id = Column(String(100), unique=True, nullable=True, index=True)  # 唯一标识符
    name = Column(String(200), nullable=False)
    description = Column(String(500))
    # 集成类型: outbound_notification, inbound_metric
    integration_type = Column(String(50), nullable=False, index=True)
    # 分类: webhook, email, sms, im, monitoring, custom 等
    category = Column(String(50), nullable=False, default="custom")
    # 是否为内置模板（内置模板不可删除）
    is_builtin = Column(Boolean, nullable=False, default=False)
    # 可编程脚本
    code = Column(Text, nullable=False)
    # 参数 Schema（JSON Schema 格式）
    config_schema = Column(JSON, nullable=True)
    enabled = Column(Boolean, nullable=False, default=True, index=True)
    # 上次执行信息
    last_run_at = Column(DateTime, nullable=True)
    last_error = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    updated_at = Column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now())


class AlertChannel(Base):
    """告警通知渠道（引用集成实例）"""
    __tablename__ = "alert_channels"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(200), nullable=False)
    description = Column(String(500))
    # 引用的集成 ID
    integration_id = Column(Integer, nullable=False, index=True)
    # 渠道参数（实例化参数）
    params = Column(JSON, nullable=False, default=dict)
    enabled = Column(Boolean, nullable=False, default=True, index=True)
    # 关联用户（用于权限控制）
    user_id = Column(Integer, nullable=True, index=True)
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    updated_at = Column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now())


class IntegrationExecutionLog(Base):
    """集成执行日志"""
    __tablename__ = "integration_execution_logs"

    id = Column(Integer, primary_key=True, index=True)
    integration_id = Column(Integer, nullable=False, index=True)
    # 可选关联：alert_channel_id 或 datasource_id
    channel_id = Column(Integer, nullable=True, index=True)
    # 触发来源: alert_dispatch, manual, scheduler
    trigger_source = Column(String(50), nullable=False, default="manual")
    # 关联对象 ID（如 alert_id）
    trigger_ref_id = Column(String(100), nullable=True)
    status = Column(String(20), nullable=False, default="pending")  # pending/success/failed
    execution_time_ms = Column(Integer, nullable=True)
    result = Column(JSON, nullable=True)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, server_default=func.now())
