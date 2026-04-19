from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from datetime import datetime


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
