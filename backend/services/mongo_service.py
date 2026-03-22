import time
from typing import Any, Dict, List
from backend.services.db_connector import DBConnector


class MongoDBConnector(DBConnector):
    """MongoDB connector using motor (async pymongo)."""

    def _get_client(self):
        from motor.motor_asyncio import AsyncIOMotorClient
        uri = f"mongodb://"
        if self.username and self.password:
            uri += f"{self.username}:{self.password}@"
        uri += f"{self.host}:{self.port}"
        if self.database:
            uri += f"/{self.database}"
        return AsyncIOMotorClient(uri, serverSelectionTimeoutMS=5000, connectTimeoutMS=5000)

    async def test_connection(self) -> str:
        client = self._get_client()
        try:
            info = await client.server_info()
            return f"MongoDB {info.get('version', 'unknown')}"
        finally:
            client.close()

    async def get_status(self) -> Dict[str, Any]:
        client = self._get_client()
        try:
            db = client.admin
            status = await db.command("serverStatus")
            return {
                "connections_current": status.get("connections", {}).get("current", 0),
                "connections_available": status.get("connections", {}).get("available", 0),
                "opcounters_insert": status.get("opcounters", {}).get("insert", 0),
                "opcounters_query": status.get("opcounters", {}).get("query", 0),
                "opcounters_update": status.get("opcounters", {}).get("update", 0),
                "opcounters_delete": status.get("opcounters", {}).get("delete", 0),
                "mem_resident_mb": status.get("mem", {}).get("resident", 0),
                "mem_virtual_mb": status.get("mem", {}).get("virtual", 0),
                "uptime": status.get("uptime", 0),
                "network_bytes_in": status.get("network", {}).get("bytesIn", 0),
                "network_bytes_out": status.get("network", {}).get("bytesOut", 0),
            }
        finally:
            client.close()

    async def get_variables(self) -> Dict[str, Any]:
        client = self._get_client()
        try:
            db = client.admin
            params = await db.command("getParameter", "*")
            return {k: str(v) for k, v in params.items() if not k.startswith("$")}
        finally:
            client.close()

    async def get_process_list(self) -> List[Dict[str, Any]]:
        client = self._get_client()
        try:
            db = client.admin
            result = await db.command("currentOp")
            ops = result.get("inprog", [])
            return [
                {
                    "opid": op.get("opid"),
                    "active": op.get("active"),
                    "op": op.get("op"),
                    "ns": op.get("ns"),
                    "secs_running": op.get("secs_running", 0),
                    "desc": op.get("desc"),
                }
                for op in ops[:50]
            ]
        finally:
            client.close()

    async def get_slow_queries(self) -> List[Dict[str, Any]]:
        client = self._get_client()
        try:
            db = client[self.database or "admin"]
            try:
                cursor = db.system.profile.find().sort("ts", -1).limit(20)
                results = []
                async for doc in cursor:
                    results.append({
                        "op": doc.get("op"),
                        "ns": doc.get("ns"),
                        "millis": doc.get("millis"),
                        "ts": str(doc.get("ts")),
                        "query": str(doc.get("command", doc.get("query", "")))[:200],
                    })
                return results
            except Exception:
                return [{"message": "Profiling not enabled"}]
        finally:
            client.close()

    async def execute_query(self, sql: str, max_rows: int = 1000) -> Dict[str, Any]:
        """For MongoDB, sql is expected to be a JSON command string."""
        import json
        client = self._get_client()
        try:
            db = client[self.database or "test"]
            start = time.time()
            try:
                cmd = json.loads(sql)
            except json.JSONDecodeError:
                # Treat as collection.find() style
                if sql.strip().startswith("db."):
                    return {"columns": ["error"], "rows": [["Use JSON command format for MongoDB"]], "row_count": 1, "execution_time_ms": 0}
                cmd = {"ping": 1}

            result = await db.command(cmd)
            elapsed = round((time.time() - start) * 1000, 2)
            # Flatten result
            if isinstance(result, dict):
                return {
                    "columns": list(result.keys()),
                    "rows": [list(str(v) for v in result.values())],
                    "row_count": 1,
                    "execution_time_ms": elapsed,
                }
            return {"columns": ["result"], "rows": [[str(result)]], "row_count": 1, "execution_time_ms": elapsed}
        finally:
            client.close()

    async def explain_query(self, sql: str) -> Dict[str, Any]:
        import json
        client = self._get_client()
        try:
            db = client[self.database or "test"]
            try:
                cmd = json.loads(sql)
                result = await db.command("explain", cmd)
                return {"plan": str(result)}
            except Exception as e:
                return {"error": str(e)}
        finally:
            client.close()

    async def get_table_stats(self) -> List[Dict[str, Any]]:
        client = self._get_client()
        try:
            db = client[self.database or "test"]
            collections = await db.list_collection_names()
            stats = []
            for col_name in collections[:50]:
                try:
                    col_stats = await db.command("collStats", col_name)
                    stats.append({
                        "collection": col_name,
                        "count": col_stats.get("count", 0),
                        "size": col_stats.get("size", 0),
                        "storageSize": col_stats.get("storageSize", 0),
                        "totalIndexSize": col_stats.get("totalIndexSize", 0),
                        "nindexes": col_stats.get("nindexes", 0),
                    })
                except Exception:
                    pass
            return stats
        finally:
            client.close()

    async def get_replication_status(self) -> Dict[str, Any]:
        client = self._get_client()
        try:
            db = client.admin
            try:
                result = await db.command("replSetGetStatus")
                members = result.get("members", [])
                return {
                    "set": result.get("set"),
                    "members": [
                        {"name": m.get("name"), "state": m.get("stateStr"),
                         "health": m.get("health")}
                        for m in members
                    ],
                }
            except Exception:
                return {"status": "not a replica set"}
        finally:
            client.close()

    async def get_db_size(self) -> Dict[str, Any]:
        client = self._get_client()
        try:
            db = client[self.database or "test"]
            stats = await db.command("dbStats")
            return {
                "database": self.database,
                "total_size_bytes": stats.get("storageSize", 0),
                "data_size_bytes": stats.get("dataSize", 0),
                "index_size_bytes": stats.get("indexSize", 0),
            }
        finally:
            client.close()
