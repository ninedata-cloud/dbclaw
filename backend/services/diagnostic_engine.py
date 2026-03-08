import logging
from typing import Any, Dict, List

logger = logging.getLogger(__name__)


class Finding:
    def __init__(self, severity: str, category: str, title: str, detail: str, recommendation: str):
        self.severity = severity  # CRITICAL, WARNING, INFO
        self.category = category
        self.title = title
        self.detail = detail
        self.recommendation = recommendation

    def to_dict(self):
        return {
            "severity": self.severity,
            "category": self.category,
            "title": self.title,
            "detail": self.detail,
            "recommendation": self.recommendation,
        }


class DiagnosticEngine:
    """Rule-based diagnostic engine for database health checks."""

    def __init__(self):
        self.findings: List[Finding] = []

    def analyze(self, db_type: str, status: Dict, variables: Dict = None,
                slow_queries: List = None, table_stats: List = None,
                replication: Dict = None, os_metrics: Dict = None) -> List[Dict]:
        self.findings = []

        self._check_connections(db_type, status)
        self._check_cache_hit_rate(db_type, status)
        self._check_slow_queries(db_type, status, slow_queries)
        self._check_locks(db_type, status)
        self._check_replication(db_type, replication)

        if variables:
            self._check_configuration(db_type, variables)
        if table_stats:
            self._check_table_health(db_type, table_stats)
        if os_metrics:
            self._check_os_resources(os_metrics)

        return [f.to_dict() for f in self.findings]

    def _check_connections(self, db_type: str, status: Dict):
        if db_type == "mysql":
            active = status.get("threads_connected", 0)
            if active > 200:
                self.findings.append(Finding(
                    "CRITICAL", "Connections",
                    "High number of active connections",
                    f"Currently {active} threads connected. High connection count can exhaust resources.",
                    "Consider using a connection pooler (ProxySQL, PgBouncer). Review max_connections setting and application connection pool configuration."
                ))
            elif active > 100:
                self.findings.append(Finding(
                    "WARNING", "Connections",
                    "Elevated connection count",
                    f"Currently {active} threads connected.",
                    "Monitor connection trends and ensure applications properly close connections."
                ))
        elif db_type == "postgresql":
            active = status.get("connections_active", 0)
            total = status.get("connections_total", 0)
            if active > 50:
                self.findings.append(Finding(
                    "WARNING", "Connections",
                    "High active connections",
                    f"{active} active connections out of {total} total.",
                    "Consider using PgBouncer for connection pooling. Review application connection settings."
                ))
        elif db_type == "redis":
            clients = status.get("connected_clients", 0)
            if clients > 500:
                self.findings.append(Finding(
                    "WARNING", "Connections",
                    "High number of Redis clients",
                    f"{clients} connected clients.",
                    "Review client timeout settings and ensure applications close connections."
                ))

    def _check_cache_hit_rate(self, db_type: str, status: Dict):
        if db_type == "mysql":
            hit_rate = status.get("buffer_pool_hit_rate", 100)
            if hit_rate < 95:
                self.findings.append(Finding(
                    "CRITICAL" if hit_rate < 90 else "WARNING",
                    "Performance",
                    "Low InnoDB buffer pool hit rate",
                    f"Buffer pool hit rate is {hit_rate}%. Data is being read from disk too frequently.",
                    "Increase innodb_buffer_pool_size. Recommended: 70-80% of available RAM for dedicated MySQL servers."
                ))
        elif db_type == "postgresql":
            hit_rate = status.get("cache_hit_rate", 100)
            if hit_rate < 95:
                self.findings.append(Finding(
                    "CRITICAL" if hit_rate < 90 else "WARNING",
                    "Performance",
                    "Low cache hit rate",
                    f"Cache hit rate is {hit_rate}%. Consider increasing shared_buffers.",
                    "Increase shared_buffers (typically 25% of RAM) and effective_cache_size (50-75% of RAM)."
                ))
        elif db_type == "redis":
            hit_rate = status.get("hit_rate", 100)
            if hit_rate < 80:
                self.findings.append(Finding(
                    "WARNING", "Performance",
                    "Low Redis hit rate",
                    f"Keyspace hit rate is {hit_rate}%.",
                    "Review key expiration policies and maxmemory-policy setting."
                ))

    def _check_slow_queries(self, db_type: str, status: Dict, slow_queries: List = None):
        if db_type == "mysql":
            slow_count = status.get("slow_queries", 0)
            if slow_count > 100:
                self.findings.append(Finding(
                    "WARNING", "Queries",
                    "High slow query count",
                    f"{slow_count} slow queries recorded.",
                    "Enable slow query log, review and optimize slow queries. Add appropriate indexes."
                ))
        if slow_queries and isinstance(slow_queries, list) and len(slow_queries) > 0:
            first = slow_queries[0]
            if not isinstance(first, dict) or "message" not in first:
                self.findings.append(Finding(
                    "INFO", "Queries",
                    "Slow queries detected",
                    f"Found {len(slow_queries)} slow queries in the log.",
                    "Review the slow queries and consider adding indexes or rewriting queries."
                ))

    def _check_locks(self, db_type: str, status: Dict):
        if db_type == "mysql":
            lock_waits = status.get("innodb_row_lock_waits", 0)
            if lock_waits > 1000:
                self.findings.append(Finding(
                    "WARNING", "Locking",
                    "High InnoDB row lock waits",
                    f"{lock_waits} row lock waits detected.",
                    "Review transaction isolation levels and long-running transactions. Consider optimizing queries to reduce lock contention."
                ))
        elif db_type == "postgresql":
            deadlocks = status.get("deadlocks", 0)
            if deadlocks > 0:
                self.findings.append(Finding(
                    "WARNING", "Locking",
                    "Deadlocks detected",
                    f"{deadlocks} deadlocks recorded.",
                    "Review application logic for lock ordering. Consider using advisory locks or adjusting transaction scope."
                ))

    def _check_replication(self, db_type: str, replication: Dict = None):
        if not replication:
            return
        status_val = replication.get("status")
        if status_val and status_val != "not configured":
            self.findings.append(Finding(
                "INFO", "Replication",
                "Replication configured",
                f"Replication status: {status_val}",
                "Ensure replication lag is monitored and alerting is configured."
            ))

    def _check_configuration(self, db_type: str, variables: Dict):
        if db_type == "mysql":
            bp_size = variables.get("innodb_buffer_pool_size", "0")
            try:
                bp_bytes = int(bp_size)
                if bp_bytes < 128 * 1024 * 1024:
                    self.findings.append(Finding(
                        "WARNING", "Configuration",
                        "Small InnoDB buffer pool",
                        f"innodb_buffer_pool_size is {bp_bytes // (1024*1024)}MB.",
                        "Increase innodb_buffer_pool_size to at least 1GB for production workloads."
                    ))
            except (ValueError, TypeError):
                pass

    def _check_table_health(self, db_type: str, table_stats: List):
        if db_type == "postgresql" and isinstance(table_stats, list):
            for t in table_stats:
                if not isinstance(t, dict):
                    continue
                dead = t.get("n_dead_tup", 0)
                live = t.get("n_live_tup", 0)
                if live > 0 and dead > 0:
                    ratio = dead / (live + dead)
                    if ratio > 0.2:
                        self.findings.append(Finding(
                            "WARNING", "Maintenance",
                            f"High dead tuple ratio in {t.get('relname', 'unknown')}",
                            f"{dead} dead tuples vs {live} live tuples ({ratio*100:.1f}% dead).",
                            f"Run VACUUM ANALYZE on the table: VACUUM ANALYZE {t.get('relname')};"
                        ))

    def _check_os_resources(self, os_metrics: Dict):
        cpu = os_metrics.get("cpu_usage_percent", 0)
        if cpu > 90:
            self.findings.append(Finding(
                "CRITICAL", "OS Resources",
                "Critical CPU usage",
                f"CPU usage is {cpu}%.",
                "Investigate high CPU processes. Consider scaling up or optimizing workload."
            ))
        elif cpu > 70:
            self.findings.append(Finding(
                "WARNING", "OS Resources",
                "High CPU usage",
                f"CPU usage is {cpu}%.",
                "Monitor CPU trends and identify resource-intensive queries."
            ))

        mem_pct = os_metrics.get("memory_usage_percent", 0)
        if mem_pct > 90:
            self.findings.append(Finding(
                "CRITICAL", "OS Resources",
                "Critical memory usage",
                f"Memory usage is {mem_pct}%.",
                "Review memory allocation. Consider adding RAM or optimizing database memory settings."
            ))

        disk_pct = os_metrics.get("disk_usage_percent", 0)
        if disk_pct > 85:
            self.findings.append(Finding(
                "CRITICAL" if disk_pct > 95 else "WARNING",
                "OS Resources",
                "High disk usage",
                f"Disk usage is {disk_pct}%.",
                "Free disk space urgently. Review log rotation, archive old data, or expand storage."
            ))
