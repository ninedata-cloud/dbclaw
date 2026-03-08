"""
Baseline Learner Service
自动学习健康基线，无需人工配置
"""
import asyncio
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_db
from backend.models.baseline import MetricBaseline
from backend.models.metric_snapshot import MetricSnapshot
from backend.models.datasource import Datasource


class BaselineLearner:
    """自动学习健康基线"""

    def __init__(self):
        self.learning_period_days = 30  # 学习周期
        self.min_samples = 100  # 最小样本数
        self.confidence_threshold = 0.7  # 置信度阈值

    async def start_learning(self):
        """启动基线学习（后台任务）"""
        while True:
            try:
                await self.learn_all_baselines()
                await asyncio.sleep(3600)  # 每小时更新一次
            except Exception as e:
                print(f"❌ Baseline learning error: {e}")
                await asyncio.sleep(300)  # 错误后等待 5 分钟

    async def learn_all_baselines(self):
        """为所有数据源学习基线"""
        async for db in get_db():
            result = await db.execute(select(Datasource).where(Datasource.is_active == True))
            datasources = result.scalars().all()

            for datasource in datasources:
                await self.learn_baselines(db, datasource.id)
            break

    async def learn_baselines(self, db: AsyncSession, datasource_id: int):
        """分析历史数据，建立基线"""
        print(f"📊 Learning baselines for datasource {datasource_id}...")

        # 1. 获取历史指标数据
        metrics = await self.get_historical_metrics(db, datasource_id, days=self.learning_period_days)

        if not metrics:
            print(f"⚠️  No historical data for datasource {datasource_id}")
            return

        # 2. 为每个指标计算基线
        for metric_name, values in metrics.items():
            if len(values) < self.min_samples:
                continue

            # 3. 计算统计基线
            baseline = self.calculate_baseline(values)

            # 4. 计算置信度
            confidence = self.calculate_confidence(values)

            # 5. 保存或更新基线
            await self.save_baseline(
                db, datasource_id, metric_name, baseline, confidence, len(values)
            )

        await db.commit()
        print(f"✅ Baselines learned for datasource {datasource_id}")

    async def get_historical_metrics(
        self, db: AsyncSession, datasource_id: int, days: int
    ) -> Dict[str, List[float]]:
        """获取历史指标数据"""
        since = datetime.utcnow() - timedelta(days=days)

        result = await db.execute(
            select(MetricSnapshot)
            .where(
                and_(
                    MetricSnapshot.datasource_id == datasource_id,
                    MetricSnapshot.collected_at >= since,
                    MetricSnapshot.metric_type == 'db_status'
                )
            )
            .order_by(MetricSnapshot.collected_at)
        )
        snapshots = result.scalars().all()

        # 组织数据：{metric_name: [values]}
        metrics = {}
        for snapshot in snapshots:
            if not snapshot.data:
                continue

            # 从 JSON data 字段中提取指标
            data = snapshot.data
            if isinstance(data, str):
                import json
                data = json.loads(data)

            # 提取常见指标（标准化后的字段）
            if 'cpu_usage' in data and data['cpu_usage'] is not None:
                metrics.setdefault('cpu_usage', []).append(float(data['cpu_usage']))
            if 'memory_usage' in data and data['memory_usage'] is not None:
                metrics.setdefault('memory_usage', []).append(float(data['memory_usage']))
            if 'disk_usage' in data and data['disk_usage'] is not None:
                metrics.setdefault('disk_usage', []).append(float(data['disk_usage']))
            if 'connections' in data and data['connections'] is not None:
                metrics.setdefault('connections', []).append(float(data['connections']))
            if 'qps' in data and data['qps'] is not None:
                metrics.setdefault('qps', []).append(float(data['qps']))
            if 'tps' in data and data['tps'] is not None:
                metrics.setdefault('tps', []).append(float(data['tps']))

            # OS 系统指标
            if 'load_avg_1min' in data and data['load_avg_1min'] is not None:
                metrics.setdefault('load_avg_1min', []).append(float(data['load_avg_1min']))
            if 'load_avg_5min' in data and data['load_avg_5min'] is not None:
                metrics.setdefault('load_avg_5min', []).append(float(data['load_avg_5min']))
            if 'load_avg_15min' in data and data['load_avg_15min'] is not None:
                metrics.setdefault('load_avg_15min', []).append(float(data['load_avg_15min']))
            if 'disk_reads_per_sec' in data and data['disk_reads_per_sec'] is not None:
                metrics.setdefault('disk_reads_per_sec', []).append(float(data['disk_reads_per_sec']))
            if 'disk_writes_per_sec' in data and data['disk_writes_per_sec'] is not None:
                metrics.setdefault('disk_writes_per_sec', []).append(float(data['disk_writes_per_sec']))

            # 数据库特定指标
            if 'cache_hit_rate' in data and data['cache_hit_rate'] is not None:
                metrics.setdefault('cache_hit_rate', []).append(float(data['cache_hit_rate']))
            if 'connections_active' in data and data['connections_active'] is not None:
                metrics.setdefault('connections_active', []).append(float(data['connections_active']))

        return metrics

    def calculate_baseline(self, values: List[float]) -> Dict:
        """计算统计基线"""
        arr = np.array(values)

        # 移除异常值（使用 IQR 方法）
        q1, q3 = np.percentile(arr, [25, 75])
        iqr = q3 - q1
        lower_bound = q1 - 1.5 * iqr
        upper_bound = q3 + 1.5 * iqr
        filtered = arr[(arr >= lower_bound) & (arr <= upper_bound)]

        if len(filtered) == 0:
            filtered = arr

        # 计算统计量
        mean = float(np.mean(filtered))
        stddev = float(np.std(filtered))

        baseline = {
            'p50': float(np.percentile(filtered, 50)),
            'p95': float(np.percentile(filtered, 95)),
            'p99': float(np.percentile(filtered, 99)),
            'mean': mean,
            'stddev': stddev,
            # 动态阈值：3-sigma 规则
            'upper_threshold': mean + 3 * stddev,
            'lower_threshold': max(0, mean - 3 * stddev),
        }

        return baseline

    def calculate_confidence(self, values: List[float]) -> float:
        """计算基线置信度"""
        n = len(values)

        # 样本数越多，置信度越高
        sample_score = min(1.0, n / 1000)

        # 变异系数越小，置信度越高
        arr = np.array(values)
        cv = np.std(arr) / (np.mean(arr) + 1e-6)  # 变异系数
        stability_score = max(0, 1 - cv)

        # 综合评分
        confidence = (sample_score * 0.6 + stability_score * 0.4)

        return float(confidence)

    async def save_baseline(
        self,
        db: AsyncSession,
        datasource_id: int,
        metric_name: str,
        baseline: Dict,
        confidence: float,
        sample_count: int
    ):
        """保存或更新基线"""
        result = await db.execute(
            select(MetricBaseline).where(
                and_(
                    MetricBaseline.datasource_id == datasource_id,
                    MetricBaseline.metric_name == metric_name,
                    MetricBaseline.time_window == 'daily'
                )
            )
        )
        existing = result.scalar_one_or_none()

        if existing:
            # 更新现有基线
            existing.p50 = baseline['p50']
            existing.p95 = baseline['p95']
            existing.p99 = baseline['p99']
            existing.mean = baseline['mean']
            existing.stddev = baseline['stddev']
            existing.upper_threshold = baseline['upper_threshold']
            existing.lower_threshold = baseline['lower_threshold']
            existing.sample_count = sample_count
            existing.confidence_score = confidence
            existing.last_updated = datetime.utcnow()
        else:
            # 创建新基线
            new_baseline = MetricBaseline(
                datasource_id=datasource_id,
                metric_name=metric_name,
                time_window='daily',
                p50=baseline['p50'],
                p95=baseline['p95'],
                p99=baseline['p99'],
                mean=baseline['mean'],
                stddev=baseline['stddev'],
                upper_threshold=baseline['upper_threshold'],
                lower_threshold=baseline['lower_threshold'],
                sample_count=sample_count,
                confidence_score=confidence
            )
            db.add(new_baseline)

    async def detect_anomaly(
        self, db: AsyncSession, datasource_id: int, metric_name: str, current_value: float
    ) -> Dict:
        """基于基线检测异常"""
        result = await db.execute(
            select(MetricBaseline).where(
                and_(
                    MetricBaseline.datasource_id == datasource_id,
                    MetricBaseline.metric_name == metric_name,
                    MetricBaseline.time_window == 'daily'
                )
            )
        )
        baseline = result.scalar_one_or_none()

        if not baseline:
            return {'is_anomaly': False, 'reason': 'no_baseline'}

        # 置信度太低，不触发告警
        if baseline.confidence_score < self.confidence_threshold:
            return {'is_anomaly': False, 'reason': 'low_confidence'}

        # 检测异常
        if current_value > baseline.upper_threshold:
            deviation = (current_value - baseline.mean) / (baseline.stddev + 1e-6)
            return {
                'is_anomaly': True,
                'type': 'spike',
                'severity': 'CRITICAL' if deviation > 5 else 'WARNING',
                'deviation_percent': float(deviation * 100),
                'baseline_value': baseline.mean,
                'current_value': current_value,
                'threshold': baseline.upper_threshold
            }
        elif current_value < baseline.lower_threshold:
            deviation = (baseline.mean - current_value) / (baseline.stddev + 1e-6)
            return {
                'is_anomaly': True,
                'type': 'drop',
                'severity': 'WARNING',
                'deviation_percent': float(deviation * 100),
                'baseline_value': baseline.mean,
                'current_value': current_value,
                'threshold': baseline.lower_threshold
            }

        return {'is_anomaly': False}

    async def get_baseline(
        self, db: AsyncSession, datasource_id: int, metric_name: str
    ) -> Optional[MetricBaseline]:
        """获取基线"""
        result = await db.execute(
            select(MetricBaseline).where(
                and_(
                    MetricBaseline.datasource_id == datasource_id,
                    MetricBaseline.metric_name == metric_name,
                    MetricBaseline.time_window == 'daily'
                )
            )
        )
        return result.scalar_one_or_none()
