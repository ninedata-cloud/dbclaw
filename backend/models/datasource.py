from sqlalchemy import Column, Integer, String, DateTime, Text, Boolean, JSON
from sqlalchemy.sql import func
from backend.database import Base
from backend.models.soft_delete import SoftDeleteMixin


class Datasource(SoftDeleteMixin, Base):
    __tablename__ = "datasource"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False)
    db_type = Column(String(20), nullable=False)  # mysql, postgresql, sqlserver, oracle, tdsql-c-mysql, opengauss, hana
    host = Column(String(255), nullable=False)
    port = Column(Integer, nullable=False)
    username = Column(String(100), nullable=True)
    password_encrypted = Column(Text, nullable=True)
    database = Column(String(100), nullable=True)
    host_id = Column(Integer, nullable=True)
    extra_params = Column(JSON, nullable=True)  # Structured connection-specific params
    tags = Column(JSON, nullable=False, default=list)
    is_active = Column(Boolean, default=True)

    # 用户配置的重要等级
    importance_level = Column(String(20), default='production')  # core, production, development, temporary

    # 备注信息
    remark = Column(Text, nullable=True)  # 备注，帮助 AI 诊断时理解数据源背景

    # 监控数据来源配置
    metric_source = Column(String(20), default='system', nullable=False)  # system, integration
    external_instance_id = Column(String(255), nullable=True)  # 外部系统实例 ID（如阿里云 RDS 实例 ID）
    inbound_source = Column(JSON, nullable=True)  # integration binding + params

    # 临时静默配置（用于临时关闭监控和告警）
    silence_until = Column(DateTime(timezone=True), nullable=True)  # 静默截止时间，为空表示未静默
    silence_reason = Column(String(500), nullable=True)  # 静默原因

    # 版本信息
    db_version = Column(String(255), nullable=True)  # 数据库版本信息

    # 连接状态
    connection_status = Column(String(20), default='unknown')  # normal, warning, failed, unknown
    connection_error = Column(Text, nullable=True)  # 连接失败时的错误信息
    connection_checked_at = Column(DateTime(timezone=True), nullable=True)  # 最后一次检测时间

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
