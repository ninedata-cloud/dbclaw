# DbGuard System Management Skills Design

**Date**: 2026-03-15  
**Status**: Draft  
**Implementation Approach**: Pure Skill Implementation (方案A)

## Overview

Design and implement 7 system management skills for DbGuard, enabling AI-driven management of datasources, hosts, skills, monitoring data, inspection reports, and system metadata through natural language interaction.

## Requirements

### User Requirements
- **Usage Scenario**: AI conversation only (natural language invocation)
- **Skill Management**: List, create, modify, enable/disable skills
- **Metadata Query**: System config, statistics, user/permissions, health status, SQL query capability

### Functional Requirements

1. **Datasource Management** - CRUD operations for database connections
2. **Host Management** - CRUD operations for SSH hosts
3. **Skill Management** - List, create, modify, enable/disable skills
4. **Monitoring Data Query** - View historical metrics
5. **Inspection Reports Query** - View AI diagnosis reports
6. **Trigger Inspection** - Manually trigger database inspection
7. **System Metadata Query** - Query internal system data via SQL

## Architecture Decision

**Selected Approach**: Pure Skill Implementation (方案A)

**Rationale**:
- Aligns with "AI conversation only" requirement
- Leverages existing Skills system architecture
- Automatic permission control, timeout management, execution audit
- Lowest development cost (7 YAML files)
- Existing APIs (datasources.py, hosts.py) remain for frontend use

**Trade-offs**:
- Skills cannot be called directly by frontend (acceptable per requirements)
- Complex CRUD logic embedded in YAML Python code (manageable with proper structure)

## Skill Specifications

### 1. manage_datasource

**ID**: `manage_datasource`  
**Category**: `system`  
**Tags**: `[datasource, management, crud]`

**Parameters**:
- `action` (string, required): Operation type - `list`, `get`, `create`, `update`, `delete`, `test`
- `datasource_id` (integer, optional): Required for get/update/delete/test
- `name` (string, optional): Required for create
- `db_type` (string, optional): Required for create (mysql, postgresql, oracle, sqlserver, dm, mongodb, redis)
- `host` (string, optional): Required for create
- `port` (integer, optional): Required for create
- `username` (string, optional): Optional for create/update
- `password` (string, optional): Optional for create/update
- `database` (string, optional): Optional for create/update
- `host_id` (integer, optional): Optional for create/update (SSH tunnel)
- `importance_level` (string, optional): Optional for create/update (core, production, development, temporary)
- `monitoring_interval` (integer, optional): Optional for create/update (seconds)

**Permissions**: `[]` (operates on system database)

**Implementation**:
- Direct database operations using SQLAlchemy models
- Password encryption via `backend.utils.encryption.encrypt_value()`
- Test action uses `backend.services.db_connector.get_connector()`

**Return Format**:
```python
{
    "success": True,
    "action": "create",
    "datasource": {...},  # For get/create/update
    "datasources": [...],  # For list
    "message": "...",     # For delete/test
    "version": "..."      # For test
}
```

---

### 2. manage_host

**ID**: `manage_host`  
**Category**: `system`  
**Tags**: `[host, ssh, management, crud]`

**Parameters**:
- `action` (string, required): Operation type - `list`, `get`, `create`, `update`, `delete`, `test`
- `host_id` (integer, optional): Required for get/update/delete/test
- `name` (string, optional): Required for create
- `host` (string, optional): Required for create
- `port` (integer, optional): Optional for create/update (default 22)
- `username` (string, optional): Required for create
- `auth_type` (string, optional): Optional for create/update (password or key, default password)
- `password` (string, optional): Optional for create/update (required if auth_type=password)
- `private_key` (string, optional): Optional for create/update (required if auth_type=key)

**Permissions**: `[]`

**Implementation**:
- Direct database operations using Host model
- Credential encryption via `backend.utils.encryption.encrypt_value()`
- Test action uses `backend.services.ssh_service.SSHService`

**Return Format**:
```python
{
    "success": True,
    "action": "create",
    "host": {...},      # For get/create/update
    "hosts": [...],     # For list
    "message": "..."    # For delete/test
}
```

---

### 3. manage_skill

**ID**: `manage_skill`  
**Category**: `system`  
**Tags**: `[skill, management, registry]`

**Parameters**:
- `action` (string, required): Operation type - `list`, `get`, `create`, `update`, `enable`, `disable`
- `skill_id` (string, optional): Required for get/update/enable/disable
- `name` (string, optional): Required for create
- `version` (string, optional): Optional for create (default "1.0.0")
- `category` (string, optional): Optional for create/update
- `description` (string, optional): Optional for create/update
- `tags` (array, optional): Optional for create/update
- `parameters` (array, optional): Optional for create/update
- `permissions` (array, optional): Optional for create/update
- `timeout` (integer, optional): Optional for create/update
- `code` (string, optional): Required for create

**Permissions**: `[]`

**Implementation**:
- Direct database operations using Skill model
- Validation via `backend.skills.validator.SkillValidator`
- List action supports filtering by category/tags
- Create action validates YAML structure and code safety

**Return Format**:
```python
{
    "success": True,
    "action": "list",
    "skill": {...},       # For get/create/update
    "skills": [...],      # For list
    "message": "..."      # For enable/disable
}
```

**Security Considerations**:
- Code validation must check for forbidden imports/builtins
- Only allow creating custom skills (is_builtin=False)
- Builtin skills cannot be modified or disabled

---

### 4. query_monitoring_data

**ID**: `query_monitoring_data`  
**Category**: `monitoring`  
**Tags**: `[monitoring, metrics, query]`

**Parameters**:
- `datasource_id` (integer, optional): Filter by datasource (if omitted, return all)
- `metric_type` (string, optional): Filter by metric type (db_status, os_metrics)
- `minutes` (integer, optional): Time range in minutes (default 60)
- `limit` (integer, optional): Max records to return (default 100, max 1000)

**Permissions**: `[]`

**Implementation**:
- Query MetricSnapshot table with filters
- Use `context.get_metrics()` for datasource-specific queries
- Return aggregated statistics (avg, min, max) for numeric metrics

**Return Format**:
```python
{
    "success": True,
    "metrics": [...],
    "count": 100,
    "time_range": "60 minutes",
    "statistics": {
        "cpu_usage": {"avg": 45.2, "min": 20.1, "max": 89.5},
        ...
    }
}
```

---

### 5. query_inspection_reports

**ID**: `query_inspection_reports`  
**Category**: `inspection`  
**Tags**: `[inspection, report, query]`

**Parameters**:
- `datasource_id` (integer, optional): Filter by datasource
- `report_id` (integer, optional): Get specific report detail
- `trigger_type` (string, optional): Filter by trigger type (manual, scheduled, threshold, anomaly)
- `status` (string, optional): Filter by status (pending, running, completed, failed)
- `limit` (integer, optional): Max records to return (default 20)

**Permissions**: `[]`

**Implementation**:
- Query Report table with filters
- If report_id provided, return full report content (content_md)
- Otherwise return list with summary info

**Return Format**:
```python
{
    "success": True,
    "reports": [...],     # List mode
    "report": {...},      # Detail mode (when report_id provided)
    "count": 20
}
```

---

### 6. trigger_inspection

**ID**: `trigger_inspection`  
**Category**: `inspection`  
**Tags**: `[inspection, trigger, diagnosis]`

**Parameters**:
- `datasource_id` (integer, required): Target datasource
- `reason` (string, optional): Trigger reason description (default "Manual inspection via AI")

**Permissions**: `[]`

**Implementation**:
- Call `backend.services.inspection_service.InspectionService.trigger_inspection()`
- Create InspectionTrigger record
- Return trigger_id and report_id (when available)

**Return Format**:
```python
{
    "success": True,
    "trigger_id": 123,
    "report_id": 456,
    "message": "Inspection triggered successfully"
}
```

---

### 7. query_system_metadata

**ID**: `query_system_metadata`  
**Category**: `system`  
**Tags**: `[metadata, query, sql, statistics]`

**Parameters**:
- `query_type` (string, required): Query type - `sql`, `config`, `statistics`, `users`, `health`
- `sql` (string, optional): Required when query_type=sql (SELECT only)
- `table` (string, optional): Optional for sql queries (whitelist validation)

**Permissions**: `[]`

**Implementation**:

**SQL Query Mode** (query_type=sql):
- Execute read-only SQL against system database (dbguard.db)
- Whitelist allowed tables: datasources, hosts, skills, metric_snapshots, diagnostic_sessions, reports, users, knowledge_bases
- Reject non-SELECT statements
- Apply row limit (max 1000)

**Config Mode** (query_type=config):
- Return system configuration (AI models, knowledge bases, inspection configs)

**Statistics Mode** (query_type=statistics):
- Return counts: datasources, hosts, skills, sessions, reports, executions

**Users Mode** (query_type=users):
- Return user list with basic info (no passwords)

**Health Mode** (query_type=health):
- Return service status: metric_collector, inspection_service, background tasks

**Return Format**:
```python
{
    "success": True,
    "query_type": "sql",
    "results": [...],     # For sql/users
    "config": {...},      # For config
    "statistics": {...},  # For statistics
    "health": {...}       # For health
}
```

**Security Considerations**:
- SQL injection prevention via parameterized queries
- Table whitelist enforcement
- Read-only operations only
- No access to encrypted password fields

## Implementation Plan

### Phase 1: Core Skills (Priority 1)
1. `manage_datasource` - Most frequently used
2. `manage_host` - Dependency for datasource SSH tunnels
3. `query_monitoring_data` - Essential for diagnostics

### Phase 2: Inspection Skills (Priority 2)
4. `query_inspection_reports` - View diagnosis results
5. `trigger_inspection` - Initiate diagnostics

### Phase 3: Advanced Skills (Priority 3)
6. `manage_skill` - Self-management capability
7. `query_system_metadata` - Advanced queries

### Testing Strategy

**Unit Tests**:
- Parameter validation for each action
- Database operations (CRUD)
- Error handling (missing params, invalid IDs)

**Integration Tests**:
- End-to-end skill execution via SkillExecutor
- AI conversation flow with skill selection
- Permission and timeout enforcement

**Test Data**:
- Mock datasources, hosts, skills
- Sample metric snapshots
- Sample inspection reports

## Security Considerations

1. **Credential Encryption**: All passwords/keys encrypted with Fernet
2. **SQL Injection Prevention**: Parameterized queries, table whitelist
3. **Permission Model**: Skills operate with system privileges (no user-level restrictions in v1)
4. **Audit Trail**: All executions logged in skill_executions table
5. **Timeout Protection**: Default 30s, max 300s per skill
6. **Code Validation**: Forbidden imports/builtins check for custom skills

## Future Enhancements

1. **User-Level Permissions**: Restrict skill access by user role
2. **Batch Operations**: Support bulk create/update/delete
3. **Export/Import**: Skill definitions export to YAML
4. **Skill Marketplace**: Share custom skills across instances
5. **Advanced Filtering**: Complex queries with multiple conditions
6. **Real-time Monitoring**: WebSocket-based metric streaming

## Success Criteria

- [ ] All 7 skills implemented and tested
- [ ] AI can successfully manage datasources via natural language
- [ ] AI can query monitoring data and inspection reports
- [ ] AI can trigger inspections on demand
- [ ] SQL query capability works with security constraints
- [ ] All operations logged in skill_executions table
- [ ] No security vulnerabilities (SQL injection, code injection)

## Open Questions

None - all requirements clarified with user.

