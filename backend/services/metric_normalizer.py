"""
Metric Normalizer Service
指标标准化服务 - 将不同数据库的指标映射到统一格式
"""
from decimal import Decimal
from typing import Dict, Any, Optional
from datetime import datetime
from backend.utils.datetime_helper import now


class MetricNormalizer:
    """指标标准化器"""

    _POSTGRES_FAMILY_DB_TYPES = {"postgresql", "opengauss"}

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
        - qps: 每秒查询数
        - tps: 每秒事务数
        """
        normalized = raw_metrics.copy()

        if db_type in cls._POSTGRES_FAMILY_DB_TYPES:
            normalized.update(cls._normalize_postgresql(datasource_id, raw_metrics))
        elif db_type in {'mysql', 'tdsql-c-mysql'}:
            normalized.update(cls._normalize_mysql(datasource_id, raw_metrics))
        elif db_type == 'sqlserver':
            normalized.update(cls._normalize_sqlserver(datasource_id, raw_metrics))
        elif db_type == 'oracle':
            normalized.update(cls._normalize_oracle(datasource_id, raw_metrics))
        elif db_type == 'hana':
            normalized.update(cls._normalize_hana(datasource_id, raw_metrics))

        return cls._convert_decimals(normalized)

    @classmethod
    def _convert_decimals(cls, data: Any) -> Any:
        """递归将 Dict 中的 Decimal 转换为 float，确保 JSON 可序列化"""
        if isinstance(data, dict):
            return {k: cls._convert_decimals(v) for k, v in data.items()}
        elif isinstance(data, (list, tuple)):
            return [cls._convert_decimals(item) for item in data]
        elif isinstance(data, Decimal):
            return float(data)
        return data

    @classmethod
    def _normalize_postgresql(cls, datasource_id: int, metrics: Dict[str, Any]) -> Dict[str, Any]:
        """PostgreSQL 指标标准化"""
        normalized = {}

        # 计算 QPS — 基于 tup_fetched + tup_inserted + tup_updated + tup_deleted 增量
        # tup_returned 是 seq scan 返回的行数（含内部过滤前），不适合作为 QPS
        fetched = metrics.get('tup_fetched', 0)
        inserted = metrics.get('tup_inserted', 0)
        updated = metrics.get('tup_updated', 0)
        deleted = metrics.get('tup_deleted', 0)
        total_ops = fetched + inserted + updated + deleted
        if total_ops > 0:
            qps = cls._calculate_rate(
                datasource_id, 'pg_total_ops', total_ops
            )
            if qps is not None:
                normalized['qps'] = qps

        # 计算 TPS — 基于 xact_commit + xact_rollback 增量
        xact_commit = metrics.get('xact_commit', 0)
        xact_rollback = metrics.get('xact_rollback', 0)
        total_xact = xact_commit + xact_rollback
        if total_xact > 0:
            tps = cls._calculate_rate(
                datasource_id, 'pg_total_xact', total_xact
            )
            if tps is not None:
                normalized['tps'] = tps

        # 缓存命中率
        if 'cache_hit_rate' in metrics:
            normalized['cache_hit_rate'] = metrics['cache_hit_rate']

        # 磁盘块读取速率
        if 'blks_read' in metrics:
            blks_read_sec = cls._calculate_rate(
                datasource_id, 'blks_read', metrics['blks_read']
            )
            if blks_read_sec is not None:
                normalized['disk_reads_per_sec'] = blks_read_sec

        return normalized

    @classmethod
    def _normalize_mysql(cls, datasource_id: int, metrics: Dict[str, Any]) -> Dict[str, Any]:
        """MySQL 指标标准化"""
        normalized = {}

        # QPS — 基于 questions 累积值计算实时速率
        if 'questions' in metrics:
            qps = cls._calculate_rate(
                datasource_id, 'questions', metrics['questions']
            )
            if qps is not None:
                normalized['qps'] = qps

        # TPS — 基于 com_commit + com_rollback 累积值（与 PostgreSQL/Oracle 对齐）
        com_commit = metrics.get('com_commit', 0)
        com_rollback = metrics.get('com_rollback', 0)
        total_xact = com_commit + com_rollback
        if total_xact > 0:
            tps = cls._calculate_rate(
                datasource_id, 'mysql_total_xact', total_xact
            )
            if tps is not None:
                normalized['tps'] = tps

        # 缓存命中率
        if 'cache_hit_rate' in metrics:
            normalized['cache_hit_rate'] = metrics['cache_hit_rate']

        # 磁盘 IO 速率（基于 InnoDB data reads/writes 累积值）
        if 'innodb_data_reads' in metrics:
            reads_sec = cls._calculate_rate(
                datasource_id, 'innodb_data_reads', metrics['innodb_data_reads']
            )
            if reads_sec is not None:
                normalized['disk_reads_per_sec'] = reads_sec

        if 'innodb_data_writes' in metrics:
            writes_sec = cls._calculate_rate(
                datasource_id, 'innodb_data_writes', metrics['innodb_data_writes']
            )
            if writes_sec is not None:
                normalized['disk_writes_per_sec'] = writes_sec

        # 网络 IO 速率（基于 bytes_received/bytes_sent 累积值）
        if 'bytes_received' in metrics:
            net_rx = cls._calculate_rate(
                datasource_id, 'bytes_received', metrics['bytes_received']
            )
            if net_rx is not None:
                normalized['network_rx_rate'] = net_rx

        if 'bytes_sent' in metrics:
            net_tx = cls._calculate_rate(
                datasource_id, 'bytes_sent', metrics['bytes_sent']
            )
            if net_tx is not None:
                normalized['network_tx_rate'] = net_tx

        # 锁等待速率
        if 'innodb_row_lock_waits' in metrics:
            lock_waits_sec = cls._calculate_rate(
                datasource_id, 'innodb_row_lock_waits', metrics['innodb_row_lock_waits']
            )
            if lock_waits_sec is not None:
                normalized['lock_waits_per_sec'] = lock_waits_sec

        return normalized

    @classmethod
    def _normalize_sqlserver(cls, datasource_id: int, metrics: Dict[str, Any]) -> Dict[str, Any]:
        """SQL Server 指标标准化"""
        normalized = {}

        # 计算 QPS（基于 batch_requests_total 累积值）
        if 'batch_requests_total' in metrics:
            qps = cls._calculate_rate(
                datasource_id, 'batch_requests_total', metrics['batch_requests_total']
            )
            if qps is not None:
                normalized['qps'] = qps

        # 计算 TPS（基于 transactions_total 累积值）
        if 'transactions_total' in metrics:
            tps = cls._calculate_rate(
                datasource_id, 'transactions_total', metrics['transactions_total']
            )
            if tps is not None:
                normalized['tps'] = tps

        # 缓存命中率（已经是百分比，直接映射）
        if 'buffer_cache_hit_ratio' in metrics:
            normalized['cache_hit_rate'] = metrics['buffer_cache_hit_ratio']

        # 计算死锁速率
        if 'deadlocks_total' in metrics:
            deadlocks_sec = cls._calculate_rate(
                datasource_id, 'deadlocks_total', metrics['deadlocks_total']
            )
            if deadlocks_sec is not None:
                normalized['deadlocks_per_sec'] = deadlocks_sec

        # 计算锁等待速率
        if 'lock_waits_total' in metrics:
            lock_waits_sec = cls._calculate_rate(
                datasource_id, 'lock_waits_total', metrics['lock_waits_total']
            )
            if lock_waits_sec is not None:
                normalized['lock_waits_per_sec'] = lock_waits_sec

        # 计算磁盘 I/O 速率（从累积值计算）
        if 'disk_reads_total' in metrics:
            reads_per_sec = cls._calculate_rate(
                datasource_id, 'disk_reads_total', metrics['disk_reads_total']
            )
            if reads_per_sec is not None:
                normalized['disk_reads_per_sec'] = reads_per_sec

        if 'disk_writes_total' in metrics:
            writes_per_sec = cls._calculate_rate(
                datasource_id, 'disk_writes_total', metrics['disk_writes_total']
            )
            if writes_per_sec is not None:
                normalized['disk_writes_per_sec'] = writes_per_sec

        # 计算网络 I/O 速率（从累积值计算）
        if 'network_reads_total' in metrics:
            net_rx = cls._calculate_rate(
                datasource_id, 'network_reads_total', metrics['network_reads_total']
            )
            if net_rx is not None:
                normalized['network_rx_rate'] = net_rx

        if 'network_writes_total' in metrics:
            net_tx = cls._calculate_rate(
                datasource_id, 'network_writes_total', metrics['network_writes_total']
            )
            if net_tx is not None:
                normalized['network_tx_rate'] = net_tx

        return normalized

    @classmethod
    def _normalize_oracle(cls, datasource_id: int, metrics: Dict[str, Any]) -> Dict[str, Any]:
        """Oracle 指标标准化"""
        normalized = {}

        # 计算 QPS — 基于 execute_count 累积值（比 user_calls 更准确反映实际 SQL 执行量）
        if 'execute_count' in metrics:
            qps = cls._calculate_rate(
                datasource_id, 'execute_count', metrics['execute_count']
            )
            if qps is not None:
                normalized['qps'] = qps

        # 计算 TPS — 基于 user_commits + user_rollbacks
        user_commits = metrics.get('user_commits', 0)
        user_rollbacks = metrics.get('user_rollbacks', 0)
        total_xact = user_commits + user_rollbacks
        if total_xact > 0:
            tps = cls._calculate_rate(
                datasource_id, 'ora_total_xact', total_xact
            )
            if tps is not None:
                normalized['tps'] = tps

        # 缓存命中率（已经是百分比）
        if 'cache_hit_rate' in metrics:
            normalized['cache_hit_rate'] = metrics['cache_hit_rate']

        # 磁盘 IO 速率
        if 'physical_reads' in metrics:
            reads_sec = cls._calculate_rate(
                datasource_id, 'physical_reads', metrics['physical_reads']
            )
            if reads_sec is not None:
                normalized['disk_reads_per_sec'] = reads_sec

        if 'physical_writes' in metrics:
            writes_sec = cls._calculate_rate(
                datasource_id, 'physical_writes', metrics['physical_writes']
            )
            if writes_sec is not None:
                normalized['disk_writes_per_sec'] = writes_sec

        # 网络 IO 速率
        if 'network_bytes_sent' in metrics:
            net_tx = cls._calculate_rate(
                datasource_id, 'network_bytes_sent', metrics['network_bytes_sent']
            )
            if net_tx is not None:
                normalized['network_tx_rate'] = net_tx

        if 'network_bytes_received' in metrics:
            net_rx = cls._calculate_rate(
                datasource_id, 'network_bytes_received', metrics['network_bytes_received']
            )
            if net_rx is not None:
                normalized['network_rx_rate'] = net_rx

        return normalized

    @classmethod
    def _normalize_hana(cls, datasource_id: int, metrics: Dict[str, Any]) -> Dict[str, Any]:
        """SAP HANA 指标标准化"""
        normalized = {}

        # HANA 的 cache_hit_rate 已经是百分比，直接使用
        if 'cache_hit_rate' in metrics:
            normalized['cache_hit_rate'] = metrics['cache_hit_rate']

        # 计算 TPS（基于 xact_commit + xact_rollback 累积值）
        xact_commit = metrics.get('xact_commit', 0)
        xact_rollback = metrics.get('xact_rollback', 0)
        total_xact = xact_commit + xact_rollback
        if total_xact > 0:
            tps = cls._calculate_rate(
                datasource_id, 'hana_total_xact', total_xact
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
        timestamp = now()

        if key not in cls._last_values:
            # 第一次采集，保存值
            cls._last_values[key] = {
                'value': current_value,
                'timestamp': timestamp
            }
            return None

        last_data = cls._last_values[key]
        last_value = last_data['value']
        last_time = last_data['timestamp']

        # 计算时间差（秒）
        time_diff = (timestamp - last_time).total_seconds()

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
            'timestamp': timestamp
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
