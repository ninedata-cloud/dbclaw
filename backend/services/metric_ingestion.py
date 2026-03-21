"""
指标摄入服务 - 批量写入第三方适配器采集的指标
"""
from typing import List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from backend.adapters.adapter import MetricPoint
from backend.models.metric_snapshot import MetricSnapshot
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


class MetricIngestionService:
    """指标摄入服务"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def ingest_batch(self, metrics: List[MetricPoint]) -> int:
        """
        批量写入指标数据

        Args:
            metrics: 指标数据点列表

        Returns:
            成功写入的指标数量
        """
        if not metrics:
            return 0

        try:
            # 批量插入到 metric_snapshots 表
            # 使用现有的表结构：metric_type 和 data (JSON)
            snapshots = []
            for metric in metrics:
                # 将指标数据封装到 JSON 中
                data = {
                    "metric_name": metric.metric_name,
                    "value": metric.value,
                    "labels": metric.labels,
                    "unit": metric.unit
                }

                snapshot = MetricSnapshot(
                    datasource_id=metric.datasource_id,
                    metric_type="adapter_metric",  # 标记为适配器采集的指标
                    data=data,
                    collected_at=metric.timestamp
                )
                snapshots.append(snapshot)

            self.db.add_all(snapshots)
            await self.db.commit()

            logger.info(f"Successfully ingested {len(metrics)} metrics")
            return len(metrics)

        except Exception as e:
            await self.db.rollback()
            logger.error(f"Failed to ingest metrics: {e}")
            raise

    async def ingest_single(self, metric: MetricPoint) -> bool:
        """
        写入单个指标数据

        Args:
            metric: 指标数据点

        Returns:
            是否成功
        """
        try:
            data = {
                "metric_name": metric.metric_name,
                "value": metric.value,
                "labels": metric.labels,
                "unit": metric.unit
            }

            snapshot = MetricSnapshot(
                datasource_id=metric.datasource_id,
                metric_type="adapter_metric",
                data=data,
                collected_at=metric.timestamp
            )
            self.db.add(snapshot)
            await self.db.commit()
            return True
        except Exception as e:
            await self.db.rollback()
            logger.error(f"Failed to ingest single metric: {e}")
            return False

    async def get_latest_metrics(
        self,
        datasource_id: int,
        metric_names: List[str] = None,
        limit: int = 100
    ) -> List[MetricSnapshot]:
        """
        获取最新的指标数据

        Args:
            datasource_id: 数据源 ID
            metric_names: 指标名称列表（可选）
            limit: 返回数量限制

        Returns:
            指标快照列表
        """
        query = text("""
            SELECT * FROM metric_snapshots
            WHERE datasource_id = :datasource_id
            AND metric_type = 'adapter_metric'
            ORDER BY collected_at DESC
            LIMIT :limit
        """)

        result = await self.db.execute(
            query,
            {
                "datasource_id": datasource_id,
                "limit": limit
            }
        )

        return result.fetchall()
