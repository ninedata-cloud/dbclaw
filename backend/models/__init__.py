"""
Models package - Import all models to ensure SQLAlchemy relationships work
"""
from backend.models.user import User
from backend.models.host import Host
from backend.models.datasource import Datasource
from backend.models.ai_model import AIModel
from backend.models.document import DocCategory, DocDocument
from backend.models.diagnostic_session import DiagnosticSession, ChatMessage
from backend.models.report import Report
from backend.models.metric_snapshot import MetricSnapshot
from backend.models.host_metric import HostMetric
from backend.models.system_config import SystemConfig
from backend.models.alert_event import AlertEvent
from backend.models.alert_message import AlertMessage

__all__ = [
    "User",
    "Host",
    "Datasource",
    "AIModel",
    "DocCategory",
    "DocDocument",
    "DiagnosticSession",
    "ChatMessage",
    "Report",
    "MetricSnapshot",
    "HostMetric",
    "SystemConfig",
    "AlertEvent",
    "AlertMessage",
]
