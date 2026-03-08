"""
Anomaly Detector Service
异常检测器 - 集成基线学习和重要性分级
"""
import json
import asyncio
import logging
from datetime import datetime
from typing import Dict, Optional
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.anomaly import Anomaly
from backend.services.baseline_learner import BaselineLearner
from backend.services.importance_classifier import ImportanceClassifier

logger = logging.getLogger(__name__)


class AnomalyDetector:
    """异常检测器"""

    def __init__(self):
        self.baseline_learner = BaselineLearner()
        self.importance_classifier = ImportanceClassifier()
        self._proactive_diagnosis_service = None

    async def detect_and_record(
        self,
        db: AsyncSession,
        datasource_id: int,
        metric_name: str,
        current_value: float,
        context: Dict
    ) -> Optional[Anomaly]:
        """检测异常并记录"""

        # 1. 基于基线检测异常
        anomaly_result = await self.baseline_learner.detect_anomaly(
            db, datasource_id, metric_name, current_value
        )

        if not anomaly_result.get('is_anomaly'):
            return None

        # 2. 获取重要性评分
        importance = await self.importance_classifier.get_importance(db, datasource_id)

        # 3. 创建异常记录
        anomaly = Anomaly(
            datasource_id=datasource_id,
            anomaly_type='statistical',
            affected_metrics=json.dumps([metric_name]),
            severity=anomaly_result['severity'],
            confidence=0.85,  # 基于统计的置信度
            baseline_value=anomaly_result.get('baseline_value'),
            current_value=current_value,
            deviation_percent=anomaly_result.get('deviation_percent'),
            context_snapshot=json.dumps(context),
            status='detected'
        )

        db.add(anomaly)
        await db.commit()
        await db.refresh(anomaly)

        logger.info(f"🚨 Anomaly detected: datasource={datasource_id}, metric={metric_name}, "
                    f"severity={anomaly.severity}, deviation={anomaly.deviation_percent:.2f}%")

        # 4. 触发主动诊断（Phase 3）
        if importance and importance.importance_tier in ['CRITICAL', 'IMPORTANT']:
            # 异步触发诊断，不阻塞指标采集
            # 注意：不传递 db 会话，让诊断任务创建自己的会话
            asyncio.create_task(self._trigger_proactive_diagnosis(
                anomaly.id, importance.auto_fix_enabled
            ))
            logger.info(f"🔍 Proactive diagnosis triggered for anomaly {anomaly.id}")

        return anomaly

    async def _trigger_proactive_diagnosis(
        self,
        anomaly_id: int,
        auto_fix: bool = False
    ):
        """触发主动诊断（异步）"""
        try:
            # 延迟导入避免循环依赖
            if self._proactive_diagnosis_service is None:
                from backend.services.proactive_diagnosis import ProactiveDiagnosisService
                self._proactive_diagnosis_service = ProactiveDiagnosisService()

            # 创建新的数据库会话用于诊断任务
            from backend.database import async_session
            async with async_session() as db:
                # 执行诊断
                result = await self._proactive_diagnosis_service.diagnose_anomaly(
                    db, anomaly_id, auto_fix
                )

                if result.get("success"):
                    logger.info(f"✅ Proactive diagnosis completed for anomaly {anomaly_id}")
                else:
                    logger.error(f"❌ Proactive diagnosis failed for anomaly {anomaly_id}: {result.get('error')}")

        except Exception as e:
            logger.error(f"Error triggering proactive diagnosis for anomaly {anomaly_id}: {e}", exc_info=True)

    async def update_anomaly_status(
        self,
        db: AsyncSession,
        anomaly_id: int,
        status: str,
        resolution_actions: Optional[Dict] = None,
        was_auto_fixed: bool = False
    ):
        """更新异常状态"""
        result = await db.execute(
            select(Anomaly).where(Anomaly.id == anomaly_id)
        )
        anomaly = result.scalar_one_or_none()

        if anomaly:
            anomaly.status = status
            if status == 'resolved':
                anomaly.resolved_at = datetime.utcnow()
            if resolution_actions:
                anomaly.resolution_actions = json.dumps(resolution_actions)
            anomaly.was_auto_fixed = was_auto_fixed

            await db.commit()
