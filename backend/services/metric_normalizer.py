"""
Metric Normalizer Service
指标标准化服务 - 将不同数据库的指标映射到统一格式
"""
from typing import Dict, Any, Optional
from datetime import datetime


class MetricNormalizer:
    """指标标准化器"""

    # 上次采集的累积值（用于计算增量）
    _last_values: Dict[int, Dict[str, Any]] = {}

    @classmethod
    def normalize(cls, db_type: str, datasource_id: int, raw_metrics: Dict[str, Any]) -> Dict[str, Any]:
        """
        将数据库特定的指标标准化为通用格式

        标准字段：
        - cpu_usage: CPU使用率 (%)
        - memory_usage: 内存使用率 (%)
        - disk_usage: 磁盘使用率 (%)
        - connections: 活跃连接数
        - qps: 每秒查询数
        - tps: 每秒事务数
        """
        normalized = raw_metrics.copy()

        if db_type == 'postgresql':
            normalized.update(cls._normalize_postgresql(datasource_id, raw_metrics))
        elif db_type == 'mysql':
            normalized.update(cls._normalize_mysql(datasource_id, raw_metrics))
        elif db_type == 'sqlserver':
            normalized.update(cls._normalize_sqlserver(datasource_id, raw_metrics))
        elif db_type == 'oracle':
            normalized.update(cls._normalize_oracle(datasource_id, raw_metrics))

        return normalized

    @classmethod
    def _normalize_postgresql(cls, datasource_id: int, metrics: Dict[str, Any]) -> Dict[str, Any]:
        """PostgreSQL 指标标准化"""
        normalized = {}

        # 连接数
        if 'connections_active' in metrics:
            normalized['connections'] = metrics['connections_active']

        # 计算 QPS (基于 tup_returned 增量)
        if 'tup_returned' in metrics:
            qps = cls._calculate_rate(
                datasource_id, 'tup_returned', metrics['tup_returned']
            )
            if qps is not None:
                normalized['qps'] = qps

        # 计算 TPS (基于 xact_commit 增量)
        if 'xact_commit' in metrics:
            tps = cls._calculate_rate(
                datasource_id, 'xact_commit', metrics['xact_commit']
            )
            if tps is not None:
                normalized['tps'] = tps

        # 缓存命中率可以作为性能指标
        if 'cache_hit_rate' in metrics:
            normalized['cache_hit_rate'] = metrics['cache_hit_rate']

        # 磁盘使用率（基于数据库大小，需要配置最大容量）
        # 这里暂时不计算，因为需要知道磁盘总容量

        return normalized

    @classmethod
    def _normalize_mysql(cls, datasource_id: int, metrics: Dict[str, Any]) -> Dict[str, Any]:
        """MySQL 指标标准化"""
        normalized = {}

        # 连接数
        if 'threads_connected' in metrics:
            normalized['connections'] = metrics['threads_connected']

        # QPS
        if 'questions' in metrics:
            qps = cls._calculate_rate(
                datasource_id, 'questions', metrics['questions']
            )
            if qps is not None:
                normalized['qps'] = qps

        # TPS (基于 com_commit)
        if 'com_commit' in metrics:
            tps = cls._calculate_rate(
                datasource_id, 'com_commit', metrics['com_commit']
            )
            if tps is not None:
                normalized['tps'] = tps

        return normalized

    @classmethod
    def _normalize_sqlserver(cls, datasource_id: int, metrics: Dict[str, Any]) -> Dict[str, Any]:
        """SQL Server 指标标准化"""
        normalized = {}

        # 连接数
        if 'user_connections' in metrics:
            normalized['connections'] = metrics['user_connections']

        # 批处理请求数可以作为 QPS
        if 'batch_requests_per_sec' in metrics:
            normalized['qps'] = metrics['batch_requests_per_sec']

        # 事务数
        if 'transactions_per_sec' in metrics:
            normalized['tps'] = metrics['transactions_per_sec']

        return normalized

    @classmethod
    def _normalize_oracle(cls, datasource_id: int, metrics: Dict[str, Any]) -> Dict[str, Any]:
        """Oracle 指标标准化"""
        normalized = {}

        # 连接数
        if 'sessions_active' in metrics:
            normalized['connections'] = metrics['sessions_active']

        # 用户调用数可以作为 QPS
        if 'user_calls' in metrics:
            qps = cls._calculate_rate(
                datasource_id, 'user_calls', metrics['user_calls']
            )
            if qps is not None:
                normalized['qps'] = qps

        # 事务数
        if 'user_commits' in metrics:
            tps = cls._calculate_rate(
                datasource_id, 'user_commits', metrics['user_commits']
            )
            if tps is not None:
                normalized['tps'] = tps

        return normalized

    @classmethod
    def _calculate_rate(cls, datasource_id: int, metric_name: str, current_value: float) -> Optional[float]:
        """
        计算速率（每秒增量）

        Args:
            datasource_id: 数据源ID
            metric_name: 指标名称
            current_value: 当前累积值

        Returns:
            每秒增量，如果是第一次采集则返回 None
        """
        key = f"{datasource_id}:{metric_name}"
        now = datetime.utcnow()

        if key not in cls._last_values:
            # 第一次采集，保存值
            cls._last_values[key] = {
                'value': current_value,
                'timestamp': now
            }
            return None

        last_data = cls._last_values[key]
        last_value = last_data['value']
        last_time = last_data['timestamp']

        # 计算时间差（秒）
        time_diff = (now - last_time).total_seconds()

        if time_diff <= 0:
            return None

        # 计算增量
        value_diff = current_value - last_value

        # 处理计数器重置的情况（累积值减少）
        if value_diff < 0:
            value_diff = current_value

        # 计算每秒速率
        rate = value_diff / time_diff

        # 更新缓存
        cls._last_values[key] = {
            'value': current_value,
            'timestamp': now
        }

        return round(rate, 2)

    @classmethod
    def clear_cache(cls, datasource_id: Optional[int] = None):
        """清除缓存"""
        if datasource_id is None:
            cls._last_values.clear()
        else:
            # 清除特定数据源的缓存
            keys_to_remove = [k for k in cls._last_values.keys() if k.startswith(f"{datasource_id}:")]
            for key in keys_to_remove:
                del cls._last_values[key]
