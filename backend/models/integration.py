"""统一外部集成管理数据模型"""
from sqlalchemy import BigInteger, Column, Integer, String, Text, Boolean, DateTime, JSON
from sqlalchemy.orm import synonym
from sqlalchemy.sql import func
from backend.database import Base
from backend.models.soft_delete import SoftDeleteMixin


class Integration(SoftDeleteMixin, Base):
    """外部集成配置表"""
    __tablename__ = "integration"

    id = Column(BigInteger, primary_key=True, index=True)
    integration_code = Column("integration_id", String(100), unique=True, nullable=True, index=True)  # 唯一业务标识符
    integration_id = synonym("integration_code")  # Backward-compatible alias for legacy code paths.
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
    is_enabled = Column("is_enabled", Boolean, nullable=False, default=True, index=True)
    # 上次执行信息
    last_run_at = Column(DateTime(timezone=True), nullable=True)
    last_error = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())
    enabled = synonym("is_enabled")


class IntegrationExecutionLog(Base):
    """集成执行日志"""
    __tablename__ = "integration_execution_log"

    id = Column(Integer, primary_key=True, index=True)
    integration_id = Column(Integer, nullable=False, index=True)
    target_type = Column(String(50), nullable=True, index=True)
    target_ref = Column(String(100), nullable=True, index=True)
    subscription_id = Column(Integer, nullable=True, index=True)
    datasource_id = Column(Integer, nullable=True, index=True)
    target_name = Column(String(255), nullable=True)
    params_snapshot = Column(JSON, nullable=True)
    payload_summary = Column(JSON, nullable=True)
    # 触发来源: alert_dispatch, manual, scheduler
    trigger_source = Column(String(50), nullable=False, default="manual")
    # 关联对象 ID（如 alert_id）
    trigger_ref_id = Column(String(100), nullable=True)
    status = Column(String(20), nullable=False, default="pending")  # pending/success/failed
    execution_time_ms = Column(Integer, nullable=True)
    result = Column(JSON, nullable=True)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())
