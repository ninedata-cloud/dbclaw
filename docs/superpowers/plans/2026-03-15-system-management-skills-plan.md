# Implementation Plan: DbGuard System Management Skills

**Spec**: [2026-03-15-system-management-skills-design.md](../specs/2026-03-15-system-management-skills-design.md)  
**Created**: 2026-03-15  
**Estimated Complexity**: Medium (7 YAML files, ~1500 lines of Python code)

## Overview

Implement 7 system management skills as YAML files in `backend/skills/builtin/`, enabling AI-driven management of DbGuard system resources through natural language.

## Prerequisites

- [x] Design specification approved
- [x] Existing Skills system architecture understood
- [x] Database models and encryption utilities reviewed
- [x] Example skills analyzed (list_datasources.yaml, search_knowledge_base.yaml)

## Implementation Steps

### Step 1: Create manage_datasource.yaml

**File**: `backend/skills/builtin/manage_datasource.yaml`

**Tasks**:
- Define skill metadata (id, name, version, category, tags, description)
- Define 13 parameters with proper types and validation
- Implement 6 action handlers: list, get, create, update, delete, test
- Use `backend.models.datasource.Datasource` model
- Use `backend.utils.encryption.encrypt_value()` for password encryption
- Use `backend.services.db_connector.get_connector()` for test action
- Handle errors gracefully with descriptive messages

**Key Implementation Details**:
```python
# List action
result = await context.db.execute(select(Datasource).order_by(Datasource.id.desc()))
datasources = result.scalars().all()

# Create action
datasource = Datasource(
    name=params['name'],
    db_type=params['db_type'],
    host=params['host'],
    port=params['port'],
    password_encrypted=encrypt_value(params['password']) if params.get('password') else None,
    ...
)
context.db.add(datasource)
await context.db.commit()
await context.db.refresh(datasource)

# Test action
connector = get_connector(db_type, host, port, username, password, database)
version = await connector.test_connection()
```

**Validation**:
- Verify all 6 actions work correctly
- Test password encryption/decryption
- Test connection validation
- Verify error handling for invalid datasource_id

---

### Step 2: Create manage_host.yaml

**File**: `backend/skills/builtin/manage_host.yaml`

**Tasks**:
- Define skill metadata
- Define 9 parameters (action, host_id, name, host, port, username, auth_type, password, private_key)
- Implement 6 action handlers: list, get, create, update, delete, test
- Use `backend.models.host.Host` model
- Encrypt both password and private_key fields
- Use `backend.services.ssh_service.SSHService` for test action

**Key Implementation Details**:
```python
# Create with password auth
host = Host(
    name=params['name'],
    host=params['host'],
    port=params.get('port', 22),
    username=params['username'],
    auth_type=params.get('auth_type', 'password'),
    password_encrypted=encrypt_value(params['password']) if params.get('password') else None,
    private_key_encrypted=encrypt_value(params['private_key']) if params.get('private_key') else None,
)

# Test SSH connection
ssh = SSHService(host=host.host, port=host.port, username=host.username, 
                 password=decrypted_password, private_key=decrypted_key)
output = ssh.execute("echo 'SSH connection successful'")
```

**Validation**:
- Test both password and key-based authentication
- Verify SSH connection test works
- Test update operations for both auth types

---

### Step 3: Create query_monitoring_data.yaml

**File**: `backend/skills/builtin/query_monitoring_data.yaml`

**Tasks**:
- Define skill metadata
- Define 4 parameters (datasource_id, metric_type, minutes, limit)
- Query `backend.models.metric_snapshot.MetricSnapshot` table
- Calculate statistics (avg, min, max) for numeric metrics
- Support filtering by datasource_id and metric_type

**Key Implementation Details**:
```python
from backend.models.metric_snapshot import MetricSnapshot
from sqlalchemy import select, desc, func
from datetime import datetime, timedelta

# Build query with filters
query = select(MetricSnapshot)
if datasource_id:
    query = query.where(MetricSnapshot.datasource_id == datasource_id)
if metric_type:
    query = query.where(MetricSnapshot.metric_type == metric_type)

# Time range filter
time_threshold = datetime.now() - timedelta(minutes=minutes)
query = query.where(MetricSnapshot.collected_at >= time_threshold)
query = query.order_by(desc(MetricSnapshot.collected_at)).limit(limit)

# Calculate statistics from metric_data JSON field
statistics = {}
for metric in metrics:
    data = metric.metric_data
    for key, value in data.items():
        if isinstance(value, (int, float)):
            if key not in statistics:
                statistics[key] = {"values": []}
            statistics[key]["values"].append(value)

# Compute avg/min/max
for key, stat in statistics.items():
    values = stat["values"]
    stat["avg"] = sum(values) / len(values)
    stat["min"] = min(values)
    stat["max"] = max(values)
    del stat["values"]
```

**Validation**:
- Query metrics for specific datasource
- Query all datasources
- Verify statistics calculation
- Test time range filtering

---

### Step 4: Create query_inspection_reports.yaml

**File**: `backend/skills/builtin/query_inspection_reports.yaml`

**Tasks**:
- Define skill metadata
- Define 5 parameters (datasource_id, report_id, trigger_type, status, limit)
- Query `backend.models.report.Report` table
- Support two modes: list (summary) and detail (full content_md)
- Join with Datasource table to get datasource name

**Key Implementation Details**:
```python
from backend.models.report import Report
from backend.models.datasource import Datasource

# Detail mode (when report_id provided)
if report_id:
    result = await context.db.execute(
        select(Report).where(Report.id == report_id)
    )
    report = result.scalar_one_or_none()
    if not report:
        return {"success": False, "error": "Report not found"}
    
    return {
        "success": True,
        "report": {
            "id": report.id,
            "title": report.title,
            "trigger_type": report.trigger_type,
            "trigger_reason": report.trigger_reason,
            "content_md": report.content_md,
            "status": report.status,
            "created_at": report.created_at.isoformat() if report.created_at else None,
            "completed_at": report.completed_at.isoformat() if report.completed_at else None
        }
    }

# List mode with filters
query = select(Report, Datasource.name.label('datasource_name')).join(
    Datasource, Report.datasource_id == Datasource.id, isouter=True
)
if datasource_id:
    query = query.where(Report.datasource_id == datasource_id)
if trigger_type:
    query = query.where(Report.trigger_type == trigger_type)
if status:
    query = query.where(Report.status == status)

query = query.order_by(desc(Report.created_at)).limit(limit)
```

**Validation**:
- Get specific report by ID
- List reports with various filters
- Verify datasource name join works
- Test empty result handling

---

### Step 5: Create trigger_inspection.yaml

**File**: `backend/skills/builtin/trigger_inspection.yaml`

**Tasks**:
- Define skill metadata
- Define 2 parameters (datasource_id, reason)
- Access InspectionService from metric_collector module
- Create InspectionTrigger record
- Return trigger_id and report_id

**Key Implementation Details**:
```python
from backend.services import metric_collector
from backend.models.inspection_trigger import InspectionTrigger

# Get inspection service instance
inspection_service = metric_collector._inspection_service
if not inspection_service:
    return {
        "success": False,
        "error": "Inspection service not available"
    }

# Trigger inspection
datasource_id = params['datasource_id']
reason = params.get('reason', 'Manual inspection via AI')

trigger_id = await inspection_service.trigger_inspection(
    context.db, datasource_id, "manual", reason
)

# Get trigger details
result = await context.db.execute(
    select(InspectionTrigger).where(InspectionTrigger.id == trigger_id)
)
trigger = result.scalar_one()

return {
    "success": True,
    "trigger_id": trigger_id,
    "report_id": trigger.report_id,
    "message": "Inspection triggered successfully"
}
```

**Validation**:
- Trigger inspection for valid datasource
- Verify trigger record created
- Test with custom reason message
- Handle invalid datasource_id

---

### Step 6: Create manage_skill.yaml

**File**: `backend/skills/builtin/manage_skill.yaml`

**Tasks**:
- Define skill metadata
- Define 10 parameters (action, skill_id, name, version, category, description, tags, parameters, permissions, timeout, code)
- Implement 6 action handlers: list, get, create, update, enable, disable
- Use `backend.skills.models.Skill` model
- Validate code using `backend.skills.validator.SkillValidator`
- Prevent modification of builtin skills

**Key Implementation Details**:
```python
from backend.skills.models import Skill
from backend.skills.validator import SkillValidator

# List action with filters
query = select(Skill)
if category:
    query = query.where(Skill.category == category)
if tags:
    # SQLite JSON filtering
    for tag in tags:
        query = query.where(Skill.tags.like(f'%"{tag}"%'))
query = query.order_by(Skill.created_at.desc())

# Create action with validation
validator = SkillValidator()
skill_dict = {
    "id": params['skill_id'],
    "name": params['name'],
    "version": params.get('version', '1.0.0'),
    "code": params['code'],
    ...
}

# Validate skill definition
validation_result = validator.validate(skill_dict)
if not validation_result.is_valid:
    return {
        "success": False,
        "error": f"Validation failed: {', '.join(validation_result.errors)}"
    }

# Create skill (is_builtin=False for custom skills)
skill = Skill(
    id=params['skill_id'],
    name=params['name'],
    is_builtin=False,
    is_enabled=True,
    ...
)

# Enable/disable action
if action in ['enable', 'disable']:
    if skill.is_builtin:
        return {"success": False, "error": "Cannot modify builtin skills"}
    skill.is_enabled = (action == 'enable')
```

**Validation**:
- Create custom skill with valid code
- Reject skill with forbidden imports
- Test enable/disable on custom skill
- Verify builtin skills cannot be modified
- Test list filtering by category and tags

---

### Step 7: Create query_system_metadata.yaml

**File**: `backend/skills/builtin/query_system_metadata.yaml`

**Tasks**:
- Define skill metadata
- Define 3 parameters (query_type, sql, table)
- Implement 5 query modes: sql, config, statistics, users, health
- SQL mode: whitelist tables, reject non-SELECT, limit rows
- Config mode: query AI models, knowledge bases, inspection configs
- Statistics mode: count records in key tables
- Users mode: return user list without passwords
- Health mode: check service status

**Key Implementation Details**:
```python
from sqlalchemy import select, func, text

# SQL mode with security
if query_type == 'sql':
    sql = params['sql'].strip().upper()
    
    # Reject non-SELECT
    if not sql.startswith('SELECT'):
        return {"success": False, "error": "Only SELECT queries allowed"}
    
    # Table whitelist
    allowed_tables = [
        'datasources', 'hosts', 'skills', 'metric_snapshots',
        'diagnostic_sessions', 'reports', 'users', 'knowledge_bases',
        'skill_executions', 'inspection_configs', 'inspection_triggers'
    ]
    
    # Check if query references allowed tables (simple check)
    sql_lower = params['sql'].lower()
    has_allowed_table = any(table in sql_lower for table in allowed_tables)
    if not has_allowed_table:
        return {"success": False, "error": "Query must reference allowed tables"}
    
    # Execute with row limit
    query = text(params['sql'])
    result = await context.db.execute(query)
    rows = result.fetchmany(1000)  # Max 1000 rows
    
    # Convert to dict list
    results = [dict(row._mapping) for row in rows]
    
    return {
        "success": True,
        "query_type": "sql",
        "results": results,
        "count": len(results)
    }

# Config mode
if query_type == 'config':
    from backend.models.ai_model import AIModel
    from backend.models.knowledge_base import KnowledgeBase
    from backend.models.inspection_config import InspectionConfig
    
    ai_models = await context.db.execute(select(AIModel))
    kbs = await context.db.execute(select(KnowledgeBase))
    configs = await context.db.execute(select(InspectionConfig))
    
    return {
        "success": True,
        "query_type": "config",
        "config": {
            "ai_models": [model_to_dict(m) for m in ai_models.scalars()],
            "knowledge_bases": [kb_to_dict(k) for k in kbs.scalars()],
            "inspection_configs": [cfg_to_dict(c) for c in configs.scalars()]
        }
    }

# Statistics mode
if query_type == 'statistics':
    from backend.models.datasource import Datasource
    from backend.models.host import Host
    from backend.models.diagnostic_session import DiagnosticSession
    from backend.models.report import Report
    from backend.skills.models import Skill, SkillExecution
    
    stats = {}
    stats['datasources'] = await context.db.scalar(select(func.count()).select_from(Datasource))
    stats['hosts'] = await context.db.scalar(select(func.count()).select_from(Host))
    stats['skills'] = await context.db.scalar(select(func.count()).select_from(Skill))
    stats['sessions'] = await context.db.scalar(select(func.count()).select_from(DiagnosticSession))
    stats['reports'] = await context.db.scalar(select(func.count()).select_from(Report))
    stats['executions'] = await context.db.scalar(select(func.count()).select_from(SkillExecution))
    
    return {
        "success": True,
        "query_type": "statistics",
        "statistics": stats
    }

# Users mode
if query_type == 'users':
    from backend.models.user import User
    
    result = await context.db.execute(select(User))
    users = result.scalars().all()
    
    return {
        "success": True,
        "query_type": "users",
        "results": [
            {
                "id": u.id,
                "username": u.username,
                "email": u.email,
                "is_active": u.is_active,
                "created_at": u.created_at.isoformat() if u.created_at else None
            }
            for u in users
        ]
    }

# Health mode
if query_type == 'health':
    from backend.services import metric_collector
    
    health = {
        "metric_collector": metric_collector._running if hasattr(metric_collector, '_running') else False,
        "inspection_service": metric_collector._inspection_service is not None if hasattr(metric_collector, '_inspection_service') else False,
    }
    
    return {
        "success": True,
        "query_type": "health",
        "health": health
    }
```

**Validation**:
- Execute safe SELECT query
- Reject UPDATE/DELETE/DROP queries
- Test table whitelist enforcement
- Query config, statistics, users, health modes
- Verify 1000 row limit

---

### Step 8: Test All Skills

**File**: `test_system_management_skills.py`

**Tasks**:
- Create comprehensive test suite
- Test each skill's all actions
- Test error handling (invalid IDs, missing params)
- Test security constraints (SQL injection, builtin skill protection)
- Test integration with AI conversation flow

**Test Structure**:
```python
import pytest
from backend.skills.executor import SkillExecutor
from backend.skills.context import SkillContext

class TestManageDatasource:
    async def test_list_datasources(self):
        # Test list action
        
    async def test_create_datasource(self):
        # Test create with encryption
        
    async def test_update_datasource(self):
        # Test update operation
        
    async def test_delete_datasource(self):
        # Test delete operation
        
    async def test_test_connection(self):
        # Test connection validation
        
    async def test_invalid_action(self):
        # Test error handling

class TestManageHost:
    # Similar structure for host management

class TestQueryMonitoringData:
    # Test metric queries and statistics

class TestQueryInspectionReports:
    # Test report queries

class TestTriggerInspection:
    # Test inspection triggering

class TestManageSkill:
    # Test skill management and validation

class TestQuerySystemMetadata:
    # Test all 5 query modes
    # Test SQL security constraints
```

**Validation**:
- All tests pass
- Code coverage > 80%
- No security vulnerabilities found

---

### Step 9: Update Skills Loader

**File**: `backend/skills/loader.py`

**Tasks**:
- Verify new skills are automatically loaded on startup
- Check skill registration in database
- Verify skills appear in AI tool selection

**Validation**:
- Start server and check logs for skill loading
- Query skills table to verify 7 new skills exist
- Test AI conversation can discover and use new skills

---

### Step 10: Documentation and Examples

**File**: `docs/SYSTEM_MANAGEMENT_SKILLS.md`

**Tasks**:
- Document each skill with examples
- Provide natural language examples for AI invocation
- Document security considerations
- Add troubleshooting guide

**Example Content**:
```markdown
# System Management Skills

## manage_datasource

**Natural Language Examples**:
- "创建一个MySQL数据源，名称是prod-db，地址是192.168.1.100:3306"
- "列出所有数据源"
- "测试数据源ID为5的连接"
- "删除数据源ID为10"

**Direct Invocation**:
```python
{
    "action": "create",
    "name": "prod-db",
    "db_type": "mysql",
    "host": "192.168.1.100",
    "port": 3306,
    "username": "root",
    "password": "secret",
    "database": "mydb"
}
```

## query_system_metadata

**SQL Query Examples**:
```sql
-- Count datasources by type
SELECT db_type, COUNT(*) as count FROM datasources GROUP BY db_type

-- Recent inspection reports
SELECT id, title, status, created_at FROM reports ORDER BY created_at DESC LIMIT 10

-- Skill execution statistics
SELECT skill_id, COUNT(*) as executions, AVG(execution_time_ms) as avg_time 
FROM skill_executions GROUP BY skill_id
```
```

---

## Critical Files

### New Files (7 skills)
- `backend/skills/builtin/manage_datasource.yaml`
- `backend/skills/builtin/manage_host.yaml`
- `backend/skills/builtin/query_monitoring_data.yaml`
- `backend/skills/builtin/query_inspection_reports.yaml`
- `backend/skills/builtin/trigger_inspection.yaml`
- `backend/skills/builtin/manage_skill.yaml`
- `backend/skills/builtin/query_system_metadata.yaml`

### Test Files
- `test_system_management_skills.py`

### Documentation
- `docs/SYSTEM_MANAGEMENT_SKILLS.md`

### Modified Files
- None (skills auto-load via existing loader)

---

## Testing Strategy

### Unit Tests
- Parameter validation for each action
- Database CRUD operations
- Encryption/decryption
- Error handling

### Integration Tests
- End-to-end skill execution
- AI conversation flow
- Permission enforcement
- Timeout handling

### Security Tests
- SQL injection attempts
- Code injection in custom skills
- Builtin skill protection
- Password encryption verification

### Manual Testing
- AI natural language invocation
- Complex multi-skill workflows
- Error recovery scenarios

---

## Rollback Plan

If issues arise:
1. Remove problematic YAML files from `backend/skills/builtin/`
2. Restart server (skills will not load)
3. Fix issues and redeploy
4. No database rollback needed (skills table is append-only)

---

## Success Criteria

- [ ] All 7 YAML files created and validated
- [ ] All skills load successfully on server startup
- [ ] All unit tests pass (>80% coverage)
- [ ] AI can invoke skills via natural language
- [ ] Security constraints enforced (SQL whitelist, builtin protection)
- [ ] All operations logged in skill_executions table
- [ ] Documentation complete with examples
- [ ] No regressions in existing skills

---

## Timeline Estimate

- Step 1-2 (manage_datasource, manage_host): 2-3 hours
- Step 3-5 (monitoring, reports, trigger): 2-3 hours
- Step 6-7 (manage_skill, metadata): 3-4 hours
- Step 8 (testing): 2-3 hours
- Step 9-10 (integration, docs): 1-2 hours

**Total**: 10-15 hours

---

## Notes

- Skills use direct database access via `context.db` (AsyncSession)
- Password encryption uses existing `backend.utils.encryption` module
- No new API endpoints needed (skills are AI tools only)
- Skills automatically appear in AI tool selection via skill_selector.py
- All operations audited in skill_executions table automatically

