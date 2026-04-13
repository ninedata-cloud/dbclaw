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
from backend.models.action_run import ActionRun
from backend.models.metric_snapshot import MetricSnapshot
from backend.models.metric_baseline_profile import MetricBaselineProfile
from backend.models.host_metric import HostMetric
from backend.models.system_config import SystemConfig
from backend.models.alert_event import AlertEvent
from backend.models.alert_message import AlertMessage
from backend.models.alert_ai_policy import AlertAIPolicy
from backend.models.alert_template import AlertTemplate
from backend.models.alert_ai_evaluation_log import AlertAIEvaluationLog
from backend.models.alert_ai_runtime_state import AlertAIRuntimeState
from backend.models.integration_bot_binding import IntegrationBotBinding

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
    "ActionRun",
    "MetricSnapshot",
    "MetricBaselineProfile",
    "HostMetric",
    "SystemConfig",
    "AlertEvent",
    "AlertMessage",
    "AlertAIPolicy",
    "AlertTemplate",
    "AlertAIEvaluationLog",
    "AlertAIRuntimeState",
    "IntegrationBotBinding",
]
