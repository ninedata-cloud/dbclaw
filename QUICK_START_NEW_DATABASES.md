# Quick Start Guide: New Database Support

## Supported Databases (New)

| Database | Type | Driver | Port | Status |
|----------|------|--------|------|--------|
| TiDB | MySQL-compatible | aiomysql ✅ | 4000 | Ready |
| openGauss | PostgreSQL-compatible | asyncpg ✅ | 5432 | Ready |
| OceanBase | MySQL-compatible | aiomysql ✅ | 2881 | Ready |
| DM (Dameng) | Oracle-compatible | dmPython ⚠️ | 5236 | Needs dmPython |

## Installation

### For TiDB, openGauss, OceanBase
No additional installation needed - uses existing drivers.

### For DM (Dameng)
```bash
pip install dmPython
```

## Quick Test

### 1. Restart Backend
```bash
cd /Users/william/prog2/temp/smartdba
# Restart your backend server to load new connectors
```

### 2. Create Test Datasource (TiDB Example)
```bash
curl -X POST http://localhost:8000/api/datasources \
  -H "Content-Type: application/json" \
  -d '{
    "name": "TiDB Test",
    "db_type": "tidb",
    "host": "localhost",
    "port": 4000,
    "username": "root",
    "password": "",
    "database": "test"
  }'
```

### 3. Test Connection
```bash
curl -X POST http://localhost:8000/api/datasources/{id}/test
```

### 4. List Available Skills
```bash
curl http://localhost:8000/api/skills?tags=tidb
```

## Connection Strings

### TiDB
- Host: TiDB server address
- Port: 4000 (default)
- Username: root or custom user
- Database: database name

### openGauss
- Host: openGauss server address
- Port: 5432 (default)
- Username: gaussdb or custom user
- Database: postgres or custom database

### OceanBase
- Host: OceanBase server address
- Port: 2881 (default)
- Username: root@sys (tenant format)
- Database: database name

### DM (Dameng)
- Host: DM server address
- Port: 5236 (default)
- Username: SYSDBA or custom user
- Database: DAMENG or custom database

## Available Skills Per Database

### TiDB (10 skills)
- tidb_get_db_status
- tidb_get_slow_queries
- tidb_get_table_stats
- tidb_list_connections
- tidb_get_db_size
- tidb_explain_query
- tidb_get_cluster_info
- tidb_get_region_info
- tidb_get_hot_regions
- tidb_get_index_usage

### openGauss (9 skills)
- opengauss_get_db_status
- opengauss_get_slow_queries
- opengauss_get_table_stats
- opengauss_list_connections
- opengauss_get_db_size
- opengauss_explain_query
- opengauss_get_index_usage
- opengauss_get_vacuum_stats
- opengauss_get_audit_logs

### OceanBase (10 skills)
- oceanbase_get_db_status
- oceanbase_get_slow_queries
- oceanbase_get_table_stats
- oceanbase_list_connections
- oceanbase_get_db_size
- oceanbase_explain_query
- oceanbase_get_tenant_usage
- oceanbase_get_server_info
- oceanbase_get_replica_status
- oceanbase_get_partition_info

### DM (9 skills)
- dm_get_db_status
- dm_get_slow_queries
- dm_get_table_stats
- dm_list_sessions
- dm_get_db_size
- dm_explain_query
- dm_get_tablespace_usage
- dm_get_wait_events
- dm_get_index_stats

## Troubleshooting

### "Unsupported database type" error
- Restart backend server to load new connectors

### "dmPython not found" error
- Install dmPython: `pip install dmPython`

### Connection timeout
- Check firewall rules
- Verify host/port are correct
- Ensure database server is running

### Permission denied
- Verify username/password
- Check user has required permissions
- For OceanBase, use tenant format: `user@tenant`

## Next Steps

1. ✅ Implementation complete (45 files)
2. ⚠️ Install dmPython if using DM
3. 🔄 Restart backend server
4. 🧪 Test with actual database instances
5. 📝 Update user documentation
