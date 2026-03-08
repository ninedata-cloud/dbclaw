"""
Importance Classifier Service
数据库重要性自动分级
"""
import asyncio
from datetime import datetime, timedelta
from typing import Dict, List
from sqlalchemy import select, and_, func
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_db
from backend.models.importance import DatasourceImportance
from backend.models.datasource import Datasource
from backend.models.metric_snapshot import MetricSnapshot
from backend.models.diagnostic_session import DiagnosticSession


class ImportanceClassifier:
    """自动评估数据库重要性"""

    def __init__(self):
        self.evaluation_window_days = 7  # 评估窗口

    async def start_classification(self):
        """启动重要性分类（后台任务）"""
        while True:
            try:
                await self.recalculate_all()
                await asyncio.sleep(3600)  # 每小时重新评估
            except Exception as e:
                print(f"❌ Importance classification error: {e}")
                await asyncio.sleep(300)

    async def recalculate_all(self):
        """重新计算所有数据源的重要性"""
        async for db in get_db():
            result = await db.execute(select(Datasource).where(Datasource.is_active == True))
            datasources = result.scalars().all()

            for datasource in datasources:
                await self.calculate_importance(db, datasource.id)

            await db.commit()
            break

    async def calculate_importance(self, db: AsyncSession, datasource_id: int) -> float:
        """计算重要性评分 0-100"""
        print(f"🎯 Calculating importance for datasource {datasource_id}...")

        # 1. 采集评分因子
        factors = await self.collect_factors(db, datasource_id)

        # 2. 加权计算
        score = (
            factors['connection_frequency'] * 0.25 +
            factors['query_volume'] * 0.20 +
            factors['business_hours_activity'] * 0.15 +
            factors['data_change_rate'] * 0.10 +
            factors['downstream_dependencies'] * 0.10 +
            factors['historical_incidents'] * 0.10 +
            factors['user_interaction_count'] * 0.10
        )

        # 3. 确定分级和策略
        tier, strategy = self.determine_tier_and_strategy(score)

        # 4. 保存或更新
        await self.save_importance(db, datasource_id, score, tier, strategy, factors)

        print(f"✅ Datasource {datasource_id}: score={score:.2f}, tier={tier}")
        return score

    async def collect_factors(self, db: AsyncSession, datasource_id: int) -> Dict[str, float]:
        """采集评分因子"""
        since = datetime.utcnow() - timedelta(days=self.evaluation_window_days)

        # 1. 连接频率（基于指标快照数量）
        result = await db.execute(
            select(func.count(MetricSnapshot.id))
            .where(
                and_(
                    MetricSnapshot.datasource_id == datasource_id,
                    MetricSnapshot.collected_at >= since
                )
            )
        )
        snapshot_count = result.scalar() or 0
        connection_frequency = min(100, (snapshot_count / (self.evaluation_window_days * 24 * 4)) * 100)

        # 2. 查询量（基于平均 QPS）- 从 JSON data 中提取
        result = await db.execute(
            select(MetricSnapshot.data)
            .where(
                and_(
                    MetricSnapshot.datasource_id == datasource_id,
                    MetricSnapshot.collected_at >= since,
                    MetricSnapshot.metric_type == 'db_status'
                )
            )
        )
        snapshots_data = result.scalars().all()

        qps_values = []
        tps_values = []
        business_hours_qps = []

        for data in snapshots_data:
            if not data:
                continue

            if isinstance(data, str):
                import json
                data = json.loads(data)

            if 'qps' in data and data['qps'] is not None:
                qps_values.append(float(data['qps']))
            if 'tps' in data and data['tps'] is not None:
                tps_values.append(float(data['tps']))

        avg_qps = sum(qps_values) / len(qps_values) if qps_values else 0
        query_volume = min(100, (avg_qps / 1000) * 100)  # 假设 1000 QPS 为满分

        # 3. 业务时间活跃度（9:00-18:00 的活跃度）
        result = await db.execute(
            select(MetricSnapshot.collected_at, MetricSnapshot.data)
            .where(
                and_(
                    MetricSnapshot.datasource_id == datasource_id,
                    MetricSnapshot.collected_at >= since,
                    MetricSnapshot.metric_type == 'db_status'
                )
            )
        )
        snapshots = result.all()

        for collected_at, data in snapshots:
            if 9 <= collected_at.hour < 18 and data:
                if isinstance(data, str):
                    import json
                    data = json.loads(data)
                if 'qps' in data and data['qps'] is not None:
                    business_hours_qps.append(float(data['qps']))

        if business_hours_qps:
            business_hours_activity = min(100, (sum(business_hours_qps) / len(business_hours_qps) / 1000) * 100)
        else:
            business_hours_activity = 0

        # 4. 数据变化率（基于 TPS）
        avg_tps = sum(tps_values) / len(tps_values) if tps_values else 0
        data_change_rate = min(100, (avg_tps / 500) * 100)  # 假设 500 TPS 为满分

        # 5. 用户交互次数（基于诊断会话）
        result = await db.execute(
            select(func.count(DiagnosticSession.id))
            .where(
                and_(
                    DiagnosticSession.datasource_id == datasource_id,
                    DiagnosticSession.created_at >= since
                )
            )
        )
        interaction_count = result.scalar() or 0
        user_interaction_score = min(100, (interaction_count / 10) * 100)  # 10 次交互为满分

        # 6. 下游依赖（暂时设为 0，需要额外配置）
        downstream_dependencies = 0

        # 7. 历史事件（暂时设为 0，后续从 anomalies 表统计）
        historical_incidents = 0

        return {
            'connection_frequency': connection_frequency,
            'query_volume': query_volume,
            'business_hours_activity': business_hours_activity,
            'data_change_rate': data_change_rate,
            'downstream_dependencies': downstream_dependencies,
            'historical_incidents': historical_incidents,
            'user_interaction_count': user_interaction_score
        }

    def determine_tier_and_strategy(self, score: float) -> tuple:
        """确定分级和监控策略"""
        if score >= 80:
            tier = 'CRITICAL'
            strategy = {
                'collection_interval': 5,
                'anomaly_detection_mode': 'realtime',
                'auto_fix_enabled': True
            }
        elif score >= 50:
            tier = 'IMPORTANT'
            strategy = {
                'collection_interval': 15,
                'anomaly_detection_mode': 'neartime',
                'auto_fix_enabled': False
            }
        else:
            tier = 'NORMAL'
            strategy = {
                'collection_interval': 60,
                'anomaly_detection_mode': 'batch',
                'auto_fix_enabled': False
            }

        return tier, strategy

    async def save_importance(
        self,
        db: AsyncSession,
        datasource_id: int,
        score: float,
        tier: str,
        strategy: Dict,
        factors: Dict
    ):
        """保存或更新重要性评分"""
        result = await db.execute(
            select(DatasourceImportance).where(
                DatasourceImportance.datasource_id == datasource_id
            )
        )
        existing = result.scalar_one_or_none()

        if existing:
            # 更新现有记录
            existing.importance_score = score
            existing.importance_tier = tier
            existing.connection_frequency = factors['connection_frequency']
            existing.query_volume = factors['query_volume']
            existing.business_hours_activity = factors['business_hours_activity']
            existing.data_change_rate = factors['data_change_rate']
            existing.downstream_dependencies = factors['downstream_dependencies']
            existing.historical_incidents = factors['historical_incidents']
            existing.user_interaction_count = factors['user_interaction_count']
            existing.collection_interval = strategy['collection_interval']
            existing.anomaly_detection_mode = strategy['anomaly_detection_mode']
            existing.auto_fix_enabled = strategy['auto_fix_enabled']
            existing.last_recalculated = datetime.utcnow()
        else:
            # 创建新记录
            new_importance = DatasourceImportance(
                datasource_id=datasource_id,
                importance_score=score,
                importance_tier=tier,
                connection_frequency=factors['connection_frequency'],
                query_volume=factors['query_volume'],
                business_hours_activity=factors['business_hours_activity'],
                data_change_rate=factors['data_change_rate'],
                downstream_dependencies=factors['downstream_dependencies'],
                historical_incidents=factors['historical_incidents'],
                user_interaction_count=factors['user_interaction_count'],
                collection_interval=strategy['collection_interval'],
                anomaly_detection_mode=strategy['anomaly_detection_mode'],
                auto_fix_enabled=strategy['auto_fix_enabled']
            )
            db.add(new_importance)

    async def get_importance(
        self, db: AsyncSession, datasource_id: int
    ) -> DatasourceImportance:
        """获取重要性评分"""
        result = await db.execute(
            select(DatasourceImportance).where(
                DatasourceImportance.datasource_id == datasource_id
            )
        )
        importance = result.scalar_one_or_none()

        # 如果不存在，创建默认评分
        if not importance:
            await self.calculate_importance(db, datasource_id)
            result = await db.execute(
                select(DatasourceImportance).where(
                    DatasourceImportance.datasource_id == datasource_id
                )
            )
            importance = result.scalar_one_or_none()

        return importance
