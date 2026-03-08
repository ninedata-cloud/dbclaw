"""
Models package - Import all models to ensure SQLAlchemy relationships work
"""
from backend.models.user import User
from backend.models.ssh_host import SSHHost
from backend.models.datasource import Datasource
from backend.models.ai_model import AIModel
from backend.models.knowledge_base import KnowledgeBase
from backend.models.diagnostic_session import DiagnosticSession, ChatMessage
from backend.models.report import Report
from backend.models.metric_snapshot import MetricSnapshot
from backend.models.importance import DatasourceImportance
from backend.models.baseline import MetricBaseline
from backend.models.anomaly import Anomaly
from backend.models.diagnostic_case import DiagnosticCase
from backend.models.guardian_rule import GuardianRule
from backend.models.scheduled_report_config import ScheduledReportConfig
from backend.models.scheduled_report_history import ScheduledReportHistory

__all__ = [
    "User",
    "SSHHost",
    "Datasource",
    "AIModel",
    "KnowledgeBase",
    "DiagnosticSession",
    "ChatMessage",
    "Report",
    "MetricSnapshot",
    "DatasourceImportance",
    "MetricBaseline",
    "Anomaly",
    "DiagnosticCase",
    "GuardianRule",
    "ScheduledReportConfig",
    "ScheduledReportHistory",
]
