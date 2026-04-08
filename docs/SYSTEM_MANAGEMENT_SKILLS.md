# System Management Skills

DbGuard provides 7 system management skills that enable AI-driven management of system resources through natural language. These skills are designed for AI conversation use only.

## Overview

| Skill ID | Category | Description |
|----------|----------|-------------|
| `manage_datasource` | system | Manage database datasources (CRUD + test) |
| `manage_host` | system | Manage SSH hosts (CRUD + test) |
| `manage_skill` | system | Manage custom skills (list, create, update, enable/disable) |
| `query_monitoring_data` | monitoring | Query historical metrics with statistics |
| `query_inspection_reports` | inspection | Query AI inspection reports |
| `trigger_inspection` | inspection | Manually trigger database inspection |
| `query_system_metadata` | system | Query system metadata (5 modes) |

---

## 1. manage_datasource

Manage database datasources with full CRUD operations and connection testing.

### Actions

- **list**: List all datasources
- **get**: Get datasource details by ID
- **create**: Create new datasource
- **update**: Update datasource configuration
- **delete**: Delete datasource
- **test**: Test database connection

### Natural Language Examples

```
创建一个MySQL数据源，名称是prod-db，地址是192.168.1.100:3306，用户名root，密码secret，数据库mydb

列出所有数据源

查看数据源ID为5的详细信息

测试数据源ID为5的连接

更新数据源ID为5的监控间隔为30秒

删除数据源ID为10
```

### Direct Parameters (for reference)

```python
# Create datasource
{
    "action": "create",
    "name": "prod-db",
    "db_type": "mysql",
    "host": "192.168.1.100",
    "port": 3306,
    "username": "root",
    "password": "secret",
    "database": "mydb",
    "importance_level": "production",
    "monitoring_interval": 60
}

# Test connection
{
    "action": "test",
    "datasource_id": 5
}
```

### Supported Database Types

- mysql
- postgresql
- oracle
- sqlserver
- dm (DM Database)
- mongodb
- redis
- tidb
- oceanbase
- opengauss

---

## 2. manage_host

Manage SSH hosts for database tunneling with password or key-based authentication.

### Actions

- **list**: List all SSH hosts
- **get**: Get host details by ID
- **create**: Create new SSH host
- **update**: Update host configuration
- **delete**: Delete SSH host
- **test**: Test SSH connection

### Natural Language Examples

```
创建一个SSH主机，名称是jump-server，地址是10.0.0.1，端口22，用户名admin，密码pass123

创建一个SSH主机，使用密钥认证，名称是bastion，地址是10.0.0.2，用户名ubuntu，私钥是[key content]

列出所有SSH主机

测试SSH主机ID为3的连接

删除SSH主机ID为5
```

### Direct Parameters

```python
# Create with password auth
{
    "action": "create",
    "name": "jump-server",
    "host": "10.0.0.1",
    "port": 22,
    "username": "admin",
    "auth_type": "password",
    "password": "pass123"
}

# Create with key auth
{
    "action": "create",
    "name": "bastion",
    "host": "10.0.0.2",
    "port": 22,
    "username": "ubuntu",
    "auth_type": "key",
    "private_key": "-----BEGIN RSA PRIVATE KEY-----\n..."
}
```

---

## 3. manage_skill

Manage custom skills with validation and builtin protection.

### Actions

- **list**: List all skills (with optional filters)
- **get**: Get skill details by ID
- **create**: Create new custom skill
- **update**: Update skill configuration (not code)
- **enable**: Enable a disabled skill
- **disable**: Disable a skill

### Natural Language Examples

```
列出所有技能

列出category为system的技能

查看技能manage_datasource的详细信息

创建一个自定义技能，ID是my_custom_skill，名称是My Custom Skill，代码是[code]

禁用技能my_custom_skill

启用技能my_custom_skill
```

### Important Notes

- **Builtin skills cannot be modified or disabled**
- Custom skills require code validation (forbidden imports/builtins check)
- Only configuration can be updated, not code (for safety)
- Skills are automatically loaded on server startup

### Direct Parameters

```python
# Create custom skill
{
    "action": "create",
    "skill_id": "my_custom_skill",
    "name": "My Custom Skill",
    "version": "1.0.0",
    "category": "custom",
    "description": "My custom diagnostic skill",
    "tags": ["custom", "diagnostic"],
    "parameters": [
        {
            "name": "param1",
            "type": "string",
            "required": true,
            "description": "Parameter description"
        }
    ],
    "permissions": [],
    "code": "async def execute(context, params):\n    return {'success': True}"
}

# List with filters
{
    "action": "list",
    "category": "system",
    "tags": ["management"]
}
```

---

## 4. query_monitoring_data

Query historical monitoring metrics with automatic statistics calculation.

### Parameters

- **datasource_id** (optional): Filter by datasource
- **metric_type** (optional): Filter by metric type
- **minutes** (optional): Time range in minutes (default 60, max 10080)
- **limit** (optional): Max records (default 100, max 1000)

### Natural Language Examples

```
查询数据源ID为5最近60分钟的监控数据

查询所有数据源最近24小时的监控数据

查询数据源ID为3的db_status类型指标，最近30分钟

查看最近1小时的监控统计信息
```

### Direct Parameters

```python
# Query specific datasource
{
    "datasource_id": 5,
    "minutes": 60,
    "limit": 100
}

# Query all datasources with metric type filter
{
    "metric_type": "db_status",
    "minutes": 1440,  # 24 hours
    "limit": 500
}
```

### Response Format

```python
{
    "success": True,
    "metrics": [...],  # List of metric snapshots
    "count": 100,
    "time_range": "60 minutes",
    "statistics": {
        "cpu_usage": {"avg": 45.2, "min": 20.1, "max": 89.5, "count": 100},
        "memory_usage": {"avg": 62.3, "min": 55.0, "max": 75.8, "count": 100}
    }
}
```

---

## 5. query_inspection_reports

Query AI inspection reports with list and detail modes.

### Parameters

- **report_id** (optional): Get specific report detail (full content)
- **datasource_id** (optional): Filter by datasource
- **trigger_type** (optional): Filter by trigger type (manual, scheduled, threshold, anomaly)
- **status** (optional): Filter by status (pending, running, completed, failed)
- **limit** (optional): Max records (default 20, max 100)

### Natural Language Examples

```
查看报告ID为123的详细内容

列出数据源ID为5的所有诊断报告

查看最近20个手动触发的诊断报告

列出状态为completed的诊断报告

查看最近的诊断报告
```

### Direct Parameters

```python
# Get report detail
{
    "report_id": 123
}

# List with filters
{
    "datasource_id": 5,
    "trigger_type": "manual",
    "status": "completed",
    "limit": 20
}
```

### Response Modes

**Detail Mode** (when report_id provided):
```python
{
    "success": True,
    "mode": "detail",
    "report": {
        "id": 123,
        "datasource_name": "prod-db",
        "title": "Database Performance Inspection",
        "content_md": "# Full markdown content...",
        "status": "completed",
        ...
    }
}
```

**List Mode**:
```python
{
    "success": True,
    "mode": "list",
    "reports": [
        {
            "id": 123,
            "datasource_name": "prod-db",
            "title": "...",
            "trigger_type": "manual",
            "status": "completed",
            ...
        }
    ],
    "count": 20
}
```

---

## 6. trigger_inspection

Manually trigger database inspection for a datasource.

### Parameters

- **datasource_id** (required): Target datasource ID
- **reason** (optional): Trigger reason (default "Manual inspection via AI")

### Natural Language Examples

```
触发数据源ID为5的诊断

对prod-db数据源执行诊断

手动触发数据源ID为3的性能检查，原因是用户报告慢查询

立即诊断数据源ID为7
```

### Direct Parameters

```python
{
    "datasource_id": 5,
    "reason": "User reported slow queries"
}
```

### Response Format

```python
{
    "success": True,
    "trigger_id": 456,
    "report_id": 789,
    "datasource_id": 5,
    "datasource_name": "prod-db",
    "message": "Inspection triggered successfully for datasource 'prod-db'"
}
```

---

## 7. query_system_metadata

Query system metadata with 5 different modes.

### Query Modes

1. **sql**: Execute safe SELECT queries
2. **config**: Get system configuration (AI models, document categories, inspection configs)
3. **statistics**: Get system statistics (counts, breakdowns)
4. **users**: Get user list
5. **health**: Check service health status

### Natural Language Examples

```
查询系统统计信息

查看系统配置

列出所有用户

检查系统健康状态

执行SQL查询：SELECT db_type, COUNT(*) as count FROM datasources GROUP BY db_type

查询最近10个诊断报告：SELECT id, title, status, created_at FROM reports ORDER BY created_at DESC LIMIT 10

统计技能执行情况：SELECT skill_id, COUNT(*) as executions FROM skill_executions GROUP BY skill_id
```

### SQL Mode Security

**Allowed**:
- SELECT queries only
- Whitelisted tables: datasources, hosts, skills, metric_snapshots, diagnostic_sessions, reports, users, doc_categories, doc_documents, skill_executions, inspection_configs, inspection_triggers, ai_models, host_metrics, login_logs
- Max 1000 rows

**Forbidden**:
- UPDATE, DELETE, DROP, INSERT, ALTER, CREATE, TRUNCATE, GRANT, REVOKE
- Non-whitelisted tables
- SQL injection attempts

### Direct Parameters

```python
# SQL mode
{
    "query_type": "sql",
    "sql": "SELECT db_type, COUNT(*) as count FROM datasources GROUP BY db_type"
}

# Config mode
{
    "query_type": "config"
}

# Statistics mode
{
    "query_type": "statistics"
}

# Users mode
{
    "query_type": "users"
}

# Health mode
{
    "query_type": "health"
}
```

### SQL Query Examples

```sql
-- Count datasources by type
SELECT db_type, COUNT(*) as count FROM datasources GROUP BY db_type;

-- Recent inspection reports
SELECT id, title, status, created_at FROM reports 
ORDER BY created_at DESC LIMIT 10;

-- Skill execution statistics
SELECT skill_id, COUNT(*) as executions, AVG(execution_time_ms) as avg_time 
FROM skill_executions 
GROUP BY skill_id;

-- Active datasources
SELECT id, name, db_type, host, port FROM datasources WHERE is_active = 1;

-- Failed reports
SELECT id, datasource_id, title, error_message, created_at 
FROM reports 
WHERE status = 'failed' 
ORDER BY created_at DESC;

-- User activity
SELECT username, email, is_active, created_at FROM users;

-- Monitoring data summary
SELECT datasource_id, metric_type, COUNT(*) as count 
FROM metric_snapshots 
GROUP BY datasource_id, metric_type;
```

---

## Security Considerations

### Password Encryption
- All passwords and private keys are encrypted using Fernet encryption
- Encryption happens automatically in create/update actions
- Decryption only occurs during test actions

### SQL Injection Prevention
- Table whitelist enforcement
- Keyword blacklist (DROP, DELETE, UPDATE, etc.)
- Parameterized queries
- Row limit (max 1000)

### Builtin Skill Protection
- Builtin skills cannot be modified or disabled
- Only custom skills (is_builtin=False) can be managed
- Code validation for custom skills (forbidden imports/builtins)

### Audit Trail
- All skill executions logged in skill_executions table
- Includes parameters, results, errors, execution time
- Automatic logging by Skills system

---

## Troubleshooting

### Skills Not Loading

**Problem**: New skills don't appear in AI tool selection

**Solution**:
1. Check YAML syntax: `python -m yaml backend/skills/builtin/manage_datasource.yaml`
2. Check server logs for skill loading errors
3. Restart server to reload skills
4. Verify skills in database: `SELECT id, name FROM skills WHERE id LIKE 'manage_%'`

### Connection Test Fails

**Problem**: Datasource or host test action fails

**Solution**:
1. Verify credentials are correct
2. Check network connectivity
3. Verify firewall rules
4. Check encryption key is set in .env
5. Review error message for specific issue

### SQL Query Rejected

**Problem**: query_system_metadata sql mode rejects query

**Solution**:
1. Ensure query starts with SELECT
2. Check table name is in whitelist
3. Remove forbidden keywords (UPDATE, DELETE, etc.)
4. Verify query syntax is valid SQLite

### Custom Skill Validation Fails

**Problem**: manage_skill create action fails validation

**Solution**:
1. Check for forbidden imports (os, subprocess, etc.)
2. Verify code syntax is valid Python
3. Ensure parameters are properly defined
4. Check skill ID doesn't already exist

---

## Performance Tips

1. **Monitoring Queries**: Use appropriate time ranges and limits to avoid large result sets
2. **SQL Queries**: Add WHERE clauses to filter data, use LIMIT to restrict rows
3. **Report Queries**: Use filters (datasource_id, status) to narrow results
4. **Statistics Mode**: Faster than SQL queries for simple counts

---

## Examples: Complex Workflows

### Workflow 1: Setup New Database Monitoring

```
1. 创建SSH主机jump-server，地址10.0.0.1，用户admin，密码pass123
2. 创建MySQL数据源prod-db，地址192.168.1.100:3306，通过SSH主机ID为1
3. 测试数据源连接
4. 触发首次诊断
5. 查看诊断报告
```

### Workflow 2: Investigate Performance Issue

```
1. 查询数据源ID为5最近2小时的监控数据
2. 查看统计信息，识别异常指标
3. 触发诊断，原因是CPU使用率异常
4. 查看诊断报告详情
5. 执行SQL查询分析慢查询：SELECT * FROM metric_snapshots WHERE datasource_id=5 AND metric_type='db_status' ORDER BY collected_at DESC LIMIT 50
```

### Workflow 3: System Health Check

```
1. 查询系统统计信息
2. 检查系统健康状态
3. 列出所有数据源
4. 查看最近的诊断报告
5. 执行SQL查询检查失败的报告：SELECT * FROM reports WHERE status='failed' ORDER BY created_at DESC
```

---

## API Integration

These skills are designed for AI conversation use only. For programmatic access, use the existing REST APIs:

- Datasources: `/api/datasources`
- Hosts: `/api/hosts`
- Metrics: `/api/metrics`
- Inspections: `/api/inspections`

---

## Version History

- **1.0.0** (2026-03-15): Initial release with 7 system management skills
