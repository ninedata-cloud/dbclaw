from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from datetime import datetime
from backend.schemas.base import TimestampSerializerMixin


class HostSummaryResponse(BaseModel):
    """主机概览响应"""
    host: Dict[str, Any]  # Host 基本信息
    latest_metric: Optional[Dict[str, Any]]  # 最新指标
    process_count: Optional[int] = None
    connection_count: Optional[int] = None
    uptime_seconds: Optional[int] = None


class HostProcessItem(BaseModel):
    """主机进程项"""
    pid: int
    user: str
    cpu_percent: float
    memory_percent: float
    command: str
    state: str
    start_time: Optional[str] = None


class HostConnectionItem(BaseModel):
    """主机网络连接项"""
    local_ip: str
    local_port: int
    remote_ip: str
    remote_port: int
    state: str
    process_name: Optional[str] = None
    pid: Optional[int] = None


class HostNetworkTopologyResponse(BaseModel):
    """主机网络拓扑响应"""
    host: Dict[str, Any]
    connections: List[Dict[str, Any]]  # 聚合后的连接数据
    stats: Dict[str, int]  # 总连接数、各状态统计


class HostConfigResponse(TimestampSerializerMixin, BaseModel):
    """主机配置响应"""
    cpu: Dict[str, Any]  # CPU 信息
    memory: Dict[str, Any]  # 内存信息
    disk: List[Dict[str, Any]]  # 磁盘信息
    network: List[Dict[str, Any]]  # 网络接口信息
    system: Dict[str, Any]  # 系统信息（内核、发行版等）
    collected_at: datetime  # 采集时间
