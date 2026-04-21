"""
Models package - Import all models to ensure SQLAlchemy relationships work
"""
from backend.models.user import User
from backend.models.user_session import UserSession
from backend.models.host import Host
from backend.models.datasource import Datasource
from backend.models.ai_model import AIModel
from backend.models.document import DocCategory, DocDocument
from backend.models.diagnostic_session import DiagnosticSession, ChatMessage
from backend.models.diagnosis_event import DiagnosisEvent
from backend.models.diagnosis_conclusion import DiagnosisConclusion
from backend.models.report import Report
from backend.models.datasource_metric import DatasourceMetric
from backend.models.metric_baseline_profile import MetricBaselineProfile
from backend.models.host_metric import HostMetric
from backend.models.system_config import SystemConfig
from backend.models.alert_event import AlertEvent
from backend.models.alert_message import AlertMessage
from backend.models.alert_delivery_log import AlertDeliveryLog
from backend.models.alert_subscription import AlertSubscription
from backend.models.alert_ai_policy import AlertAIPolicy
from backend.models.alert_template import AlertTemplate
from backend.models.alert_ai_evaluation_log import AlertAIEvaluationLog
from backend.models.alert_ai_runtime_state import AlertAIRuntimeState
from backend.models.integration import Integration, IntegrationExecutionLog
from backend.models.integration_bot_binding import IntegrationBotBinding
from backend.models.chat_channel_binding import ChatChannelBinding
from backend.models.chat_event_dedup import ChatEventDedup
from backend.models.login_log import LoginLog
from backend.models.inspection_config import InspectionConfig
from backend.models.inspection_trigger import InspectionTrigger
from backend.models.skill import Skill, SkillExecution, SkillRating

__all__ = [
    "User",
    "UserSession",
    "Host",
    "Datasource",
    "AIModel",
    "DocCategory",
    "DocDocument",
    "DiagnosticSession",
    "ChatMessage",
    "DiagnosisEvent",
    "DiagnosisConclusion",
    "Report",
    "DatasourceMetric",
    "MetricBaselineProfile",
    "HostMetric",
    "SystemConfig",
    "AlertEvent",
    "AlertMessage",
    "AlertDeliveryLog",
    "AlertSubscription",
    "AlertAIPolicy",
    "AlertTemplate",
    "AlertAIEvaluationLog",
    "AlertAIRuntimeState",
    "Integration",
    "IntegrationExecutionLog",
    "IntegrationBotBinding",
    "ChatChannelBinding",
    "ChatEventDedup",
    "LoginLog",
    "InspectionConfig",
    "InspectionTrigger",
    "Skill",
    "SkillExecution",
    "SkillRating",
]
