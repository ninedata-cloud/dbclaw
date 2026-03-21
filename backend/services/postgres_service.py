import time
from typing import Any, Dict, List, Optional
from backend.services.db_connector import DBConnector


class PostgreSQLConnector(DBConnector):
    """PostgreSQL database connector using asyncpg."""

    async def _connect(self):
        import asyncpg
        return await asyncpg.connect(
            host=self.host, port=self.port,
            user=self.username, password=self.password or "",
            database=self.database or "postgres",
            timeout=5,
            ssl=False,
        )

    async def test_connection(self) -> str:
        conn = await self._connect()
        try:
            row = await conn.fetchrow("SELECT version()")
            return row[0] if row else "unknown"
        finally:
            await conn.close()

    async def get_status(self) -> Dict[str, Any]:
        conn = await self._connect()
        try:
            stats = await conn.fetchrow(
                "SELECT numbackends, xact_commit, xact_rollback, blks_read, "
                "blks_hit, tup_returned, tup_fetched, tup_inserted, "
                "tup_updated, tup_deleted, conflicts, deadlocks "
                "FROM pg_stat_database WHERE datname = current_database()"
            )
            activity = await conn.fetchrow(
                "SELECT count(*) as total, "
                "count(*) FILTER (WHERE state = 'active') as active, "
                "count(*) FILTER (WHERE state = 'idle') as idle, "
                "count(*) FILTER (WHERE wait_event_type IS NOT NULL "
                "  AND wait_event_type NOT IN ('Client', 'Activity')) as waiting "
                "FROM pg_stat_activity WHERE datname = current_database()"
            )
            size = await conn.fetchrow(
                "SELECT pg_database_size(current_database()) as db_size"
            )
            # Get database start time and max_connections
            start_time = await conn.fetchrow(
                "SELECT pg_postmaster_start_time() as start_time"
            )
            max_conn = await conn.fetchrow(
                "SELECT setting::int as max_conn FROM pg_settings WHERE name = 'max_connections'"
            )
            # 锁等待数
            lock_waiting = await conn.fetchrow(
                "SELECT count(*) as cnt FROM pg_stat_activity "
                "WHERE wait_event_type = 'Lock' AND datname = current_database()"
            )
            # 最长事务运行时间（秒）
            longest_tx = await conn.fetchrow(
                "SELECT EXTRACT(EPOCH FROM max(now() - xact_start))::int as seconds "
                "FROM pg_stat_activity "
                "WHERE xact_start IS NOT NULL AND state != 'idle' "
                "AND datname = current_database()"
            )

            hit_rate = 0
            if stats:
                total = (stats["blks_hit"] or 0) + (stats["blks_read"] or 0)
                if total > 0:
                    hit_rate = round((stats["blks_hit"] / total) * 100, 2)

            # Calculate uptime in seconds
            uptime = 0
            if start_time and start_time["start_time"]:
                from datetime import datetime, timezone
                boot_time = start_time["start_time"]
                if boot_time.tzinfo is None:
                    boot_time = boot_time.replace(tzinfo=timezone.utc)
                now_utc = datetime.now(timezone.utc)
                uptime = int((now_utc - boot_time).total_seconds())

            return {
                "connections_active": activity["active"] if activity else 0,
                "connections_total": activity["total"] if activity else 0,
                "connections_idle": activity["idle"] if activity else 0,
                "connections_waiting": activity["waiting"] if activity else 0,
                "max_connections": max_conn["max_conn"] if max_conn else 0,
                "lock_waiting": lock_waiting["cnt"] if lock_waiting else 0,
                "longest_transaction_sec": longest_tx["seconds"] if longest_tx and longest_tx["seconds"] else 0,
                "xact_commit": stats["xact_commit"] if stats else 0,
                "xact_rollback": stats["xact_rollback"] if stats else 0,
                "cache_hit_rate": hit_rate,
                "tup_returned": stats["tup_returned"] if stats else 0,
                "tup_fetched": stats["tup_fetched"] if stats else 0,
                "tup_inserted": stats["tup_inserted"] if stats else 0,
                "tup_updated": stats["tup_updated"] if stats else 0,
                "tup_deleted": stats["tup_deleted"] if stats else 0,
                "blks_read": stats["blks_read"] if stats else 0,
                "blks_hit": stats["blks_hit"] if stats else 0,
                "deadlocks": stats["deadlocks"] if stats else 0,
                "conflicts": stats["conflicts"] if stats else 0,
                "db_size_bytes": size["db_size"] if size else 0,
                "uptime": uptime,
                "boot_time": start_time["start_time"].isoformat() if start_time and start_time["start_time"] else None,
            }
        finally:
            await conn.close()

    async def get_variables(self) -> Dict[str, Any]:
        conn = await self._connect()
        try:
            rows = await conn.fetch("SHOW ALL")
            return {r["name"]: r["setting"] for r in rows}
        finally:
            await conn.close()

    async def get_process_list(self) -> List[Dict[str, Any]]:
        conn = await self._connect()
        try:
            rows = await conn.fetch(
                "SELECT pid, usename, client_addr, datname, state, "
                "query_start, wait_event_type, wait_event, query "
                "FROM pg_stat_activity WHERE datname = current_database() "
                "ORDER BY query_start DESC NULLS LAST LIMIT 50"
            )
            return [dict(r) for r in rows]
        finally:
            await conn.close()

    async def get_slow_queries(self) -> List[Dict[str, Any]]:
        conn = await self._connect()
        try:
            try:
                rows = await conn.fetch(
                    "SELECT query, calls, total_exec_time, mean_exec_time, rows "
                    "FROM pg_stat_statements ORDER BY mean_exec_time DESC LIMIT 20"
                )
                return [dict(r) for r in rows]
            except Exception:
                rows = await conn.fetch(
                    "SELECT pid, query, state, "
                    "EXTRACT(EPOCH FROM (now() - query_start)) as duration_sec "
                    "FROM pg_stat_activity WHERE state = 'active' "
                    "AND query NOT LIKE '%pg_stat_activity%' "
                    "ORDER BY query_start LIMIT 20"
                )
                return [dict(r) for r in rows]
        finally:
            await conn.close()

    async def execute_query(self, sql: str, max_rows: int = 1000) -> Dict[str, Any]:
        conn = await self._connect()
        try:
            start = time.time()
            rows = await conn.fetch(sql)
            elapsed = round((time.time() - start) * 1000, 2)
            columns = [k for k in rows[0].keys()] if rows else []
            truncated = len(rows) > max_rows
            limited = rows[:max_rows]
            return {
                "columns": columns,
                "rows": [list(r.values()) for r in limited],
                "row_count": len(limited),
                "execution_time_ms": elapsed,
                "truncated": truncated,
            }
        finally:
            await conn.close()

    async def explain_query(self, sql: str) -> Dict[str, Any]:
        conn = await self._connect()
        try:
            rows = await conn.fetch(f"EXPLAIN (FORMAT JSON) {sql}")
            return {"plan": [dict(r) for r in rows]}
        finally:
            await conn.close()

    async def get_table_stats(self) -> List[Dict[str, Any]]:
        conn = await self._connect()
        try:
            rows = await conn.fetch(
                "SELECT schemaname, relname, n_live_tup, n_dead_tup, "
                "seq_scan, idx_scan, n_tup_ins, n_tup_upd, n_tup_del, "
                "pg_total_relation_size(quote_ident(schemaname)||'.'||quote_ident(relname)) as total_size "
                "FROM pg_stat_user_tables ORDER BY n_live_tup DESC LIMIT 50"
            )
            return [dict(r) for r in rows]
        finally:
            await conn.close()

    async def get_replication_status(self) -> Dict[str, Any]:
        conn = await self._connect()
        try:
            rows = await conn.fetch(
                "SELECT client_addr, state, sent_lsn, write_lsn, flush_lsn, replay_lsn "
                "FROM pg_stat_replication"
            )
            if rows:
                return {"replicas": [dict(r) for r in rows]}
            return {"status": "not configured"}
        finally:
            await conn.close()

    async def get_db_size(self) -> Dict[str, Any]:
        conn = await self._connect()
        try:
            row = await conn.fetchrow(
                "SELECT pg_database_size(current_database()) as total_size, "
                "current_database() as database"
            )
            return {
                "database": row["database"],
                "total_size_bytes": row["total_size"],
            }
        finally:
            await conn.close()

    async def get_schemas(self) -> List[str]:
        conn = await self._connect()
        try:
            rows = await conn.fetch(
                "SELECT schema_name FROM information_schema.schemata "
                "WHERE schema_name NOT IN ('information_schema', 'pg_catalog', 'pg_toast') "
                "AND schema_name NOT LIKE 'pg_temp_%' AND schema_name NOT LIKE 'pg_toast_temp_%' "
                "ORDER BY schema_name"
            )
            return [row["schema_name"] for row in rows]
        finally:
            await conn.close()

    async def get_tables(self, schema: Optional[str] = None) -> List[Dict[str, Any]]:
        conn = await self._connect()
        try:
            target_schema = schema or "public"
            rows = await conn.fetch(
                "SELECT table_name, table_type "
                "FROM information_schema.tables "
                "WHERE table_schema = $1 "
                "ORDER BY table_name",
                target_schema
            )
            return [
                {
                    "name": row["table_name"],
                    "schema": target_schema,
                    "type": row["table_type"],
                }
                for row in rows
            ]
        finally:
            await conn.close()

    async def get_columns(self, table: str, schema: Optional[str] = None) -> List[Dict[str, Any]]:
        conn = await self._connect()
        try:
            target_schema = schema or "public"
            rows = await conn.fetch(
                "SELECT column_name, data_type, is_nullable, column_default, "
                "udt_name, character_maximum_length "
                "FROM information_schema.columns "
                "WHERE table_schema = $1 AND table_name = $2 "
                "ORDER BY ordinal_position",
                target_schema, table
            )
            return [
                {
                    "name": row["column_name"],
                    "type": row["data_type"],
                    "nullable": row["is_nullable"] == "YES",
                    "default": row["column_default"],
                    "udt_name": row["udt_name"],
                    "max_length": row["character_maximum_length"],
                }
                for row in rows
            ]
        finally:
            await conn.close()

    async def get_index_stats(self) -> List[Dict[str, Any]]:
        """Get index usage statistics."""
        conn = await self._connect()
        try:
            rows = await conn.fetch(
                "SELECT schemaname, relname as tablename, indexrelname as indexname, idx_scan, idx_tup_read, idx_tup_fetch "
                "FROM pg_stat_user_indexes ORDER BY idx_scan DESC LIMIT 50"
            )
            return [dict(r) for r in rows]
        finally:
            await conn.close()

    async def get_lock_waits(self) -> List[Dict[str, Any]]:
        """Get current lock waits."""
        conn = await self._connect()
        try:
            rows = await conn.fetch(
                "SELECT blocked.pid AS blocked_pid, blocked.query AS blocked_query, "
                "blocking.pid AS blocking_pid, blocking.query AS blocking_query "
                "FROM pg_stat_activity AS blocked "
                "JOIN pg_stat_activity AS blocking ON blocking.pid = ANY(pg_blocking_pids(blocked.pid)) "
                "WHERE blocked.pid != blocking.pid"
            )
            return [dict(r) for r in rows]
        finally:
            await conn.close()

    async def get_table_fragmentation(self) -> List[Dict[str, Any]]:
        """Get table bloat/fragmentation info."""
        conn = await self._connect()
        try:
            rows = await conn.fetch(
                "SELECT schemaname, relname as tablename, n_dead_tup, n_live_tup, "
                "CASE WHEN n_live_tup > 0 THEN ROUND(100.0 * n_dead_tup / (n_live_tup + n_dead_tup), 2) ELSE 0 END as dead_ratio "
                "FROM pg_stat_user_tables WHERE n_dead_tup > 1000 ORDER BY n_dead_tup DESC LIMIT 20"
            )
            return [dict(r) for r in rows]
        finally:
            await conn.close()

