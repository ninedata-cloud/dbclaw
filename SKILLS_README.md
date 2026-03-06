# SmartDBA Skill Management System

## Overview

The Skill Management System transforms SmartDBA from a hardcoded tool system into a dynamic, extensible platform where users can create, share, and manage custom diagnostic skills.

## Features

- **Dynamic Skill Loading**: Skills are loaded at runtime from YAML definitions
- **Sandboxed Execution**: Skills run in a restricted environment with permission controls
- **AI Integration**: Skills automatically become available as AI agent tools
- **Import/Export**: Share skills as YAML files
- **Version Management**: Track skill versions and dependencies
- **Execution Logging**: Audit trail of all skill executions
- **Rating System**: Community feedback on skill quality

## Architecture

```
backend/
├── skills/
│   ├── models.py              # Database models
│   ├── schema.py              # Pydantic schemas
│   ├── registry.py            # Skill registry
│   ├── executor.py            # Execution engine
│   ├── context.py             # Execution context
│   ├── validator.py           # Security validation
│   ├── loader.py              # YAML loader
│   ├── builtin_loader.py      # Built-in skill loader
│   └── builtin/               # Built-in skills (14 YAML files)
├── agent/
│   ├── conversation_skills.py # Updated conversation handler
│   └── skill_selector.py      # Dynamic skill selection
└── api/
    └── skills.py              # REST API endpoints
```

## Skill Definition Format

Skills are defined in YAML format:

```yaml
id: mysql_deadlock_analyzer
name: MySQL Deadlock Analyzer
version: 1.0.0
author: admin
category: mysql
description: Analyzes InnoDB deadlock information and provides resolution recommendations
tags: [mysql, deadlock, innodb, transaction]

parameters:
  - name: connection_id
    type: integer
    required: true
    description: Database connection ID
  - name: lookback_minutes
    type: integer
    required: false
    default: 60
    description: How far back to look for deadlock logs

permissions:
  - execute_query
  - read_logs

code: |
  async def execute(context, params):
      conn = await context.get_connection(params['connection_id'])
      result = await context.execute_query(
          "SHOW ENGINE INNODB STATUS",
          params['connection_id']
      )
      return {
          "success": True,
          "deadlock_info": result
      }
```

## Permission System

Skills must declare required permissions:

- `execute_query` - Run SQL queries on databases
- `execute_command` - Execute OS commands via SSH
- `read_logs` - Access log files
- `modify_config` - Change database configuration
- `access_kb` - Search knowledge bases

## Execution Context API

Skills have access to a secure context API:

```python
# Get database connection
conn = await context.get_connection(connection_id)

# Execute SQL query
result = await context.execute_query(query, connection_id)

# Search knowledge base
results = await context.search_kb(query, kb_ids, top_k=5)

# Get historical metrics
metrics = await context.get_metrics(connection_id, minutes=60)

# Execute OS command
result = await context.execute_command(command, connection_id)

# Call another skill
result = await context.call_skill(skill_id, params)
```

## API Endpoints

### List Skills
```
GET /api/skills?category=mysql&is_enabled=true
```

### Get Skill
```
GET /api/skills/{skill_id}
```

### Create Skill
```
POST /api/skills
{
  "skill": { ... },
  "is_enabled": true
}
```

### Update Skill
```
PUT /api/skills/{skill_id}
{
  "name": "Updated Name",
  "is_enabled": false
}
```

### Delete Skill
```
DELETE /api/skills/{skill_id}
```

### Test Skill
```
POST /api/skills/{skill_id}/test
{
  "skill_id": "mysql_deadlock_analyzer",
  "parameters": {
    "connection_id": 1,
    "lookback_minutes": 30
  }
}
```

### Import Skill
```
POST /api/skills/import
Content-Type: multipart/form-data
file: skill.yaml
```

### Export Skill
```
GET /api/skills/{skill_id}/export
```

### Rate Skill
```
POST /api/skills/{skill_id}/rate
{
  "rating": 5,
  "comment": "Very useful!"
}
```

### Get Execution History
```
GET /api/skills/{skill_id}/executions?limit=50
```

## Usage Examples

### Creating a Custom Skill

1. Navigate to Skills page in the UI
2. Click "Create Skill"
3. Define skill in YAML format
4. Test execution with sample parameters
5. Save and enable

### Using Skills in AI Diagnosis

Skills are automatically available to the AI agent:

```
User: "Check for deadlocks in the last hour"
AI: [Calls mysql_deadlock_analyzer skill]
AI: "I found 2 deadlocks in the last hour..."
```

### Importing Community Skills

1. Download skill YAML file
2. Click "Import Skill" in UI
3. Select file
4. Review and enable

## Security

### Code Validation

Skills are validated for security issues:
- Forbidden imports (os, sys, subprocess, etc.)
- Forbidden builtins (eval, exec, compile, etc.)
- Dangerous attribute access (__globals__, __code__, etc.)

### Sandboxed Execution

Skills run with:
- Restricted globals (only safe builtins)
- No file system access (except via context API)
- No network access (except via context API)
- CPU and memory limits
- Execution timeout (default 30s)

### Permission Checks

All context API calls are permission-checked at runtime.

## Built-in Skills

The system includes 14 built-in skills converted from the original tool system:

1. `get_db_status` - Database status metrics
2. `get_db_variables` - Configuration variables
3. `get_process_list` - Active processes
4. `get_slow_queries` - Slow query analysis
5. `get_table_stats` - Table statistics
6. `get_replication_status` - Replication status
7. `get_db_size` - Database sizes
8. `execute_diagnostic_query` - Execute SQL queries
9. `explain_query` - Query execution plans
10. `get_os_metrics` - OS-level metrics
11. `execute_os_command` - Execute shell commands
12. `get_metric_history` - Historical metrics
13. `list_connections` - List connections
14. `search_knowledge_base` - Search knowledge bases

## Testing

Run the test suite:

```bash
python test_skills.py
```

This validates:
- All built-in skills load correctly
- Code validation works
- YAML parsing is correct

## Future Enhancements

- **Skill Marketplace**: Public repository of community skills
- **Skill SDK**: Python package for local development
- **Skill CI/CD**: GitHub Actions integration
- **Multi-Language Support**: Skills in JavaScript, Go, etc.
- **Skill Monitoring**: Real-time performance dashboards
- **Skill Recommendations**: AI-powered suggestions
- **Skill Templates**: Pre-built templates for common patterns

## Migration from Old System

The old hardcoded tool system in `backend/agent/tools.py` is still available for backward compatibility. The new skill system runs in parallel. To fully migrate:

1. All 14 tools are now available as built-in skills
2. Update `backend/routers/chat.py` to use `run_conversation_with_skills`
3. The AI agent will automatically use the new skill system
4. Old tool definitions can be deprecated once migration is complete

## Troubleshooting

### Skill won't load
- Check YAML syntax
- Verify all required fields are present
- Check code validation errors

### Skill execution fails
- Verify permissions are granted
- Check parameter types match definitions
- Review execution logs in database

### Skill not appearing in AI tools
- Ensure skill is enabled
- Check it's not in disabled_tools list
- Verify skill is registered in database

## Support

For issues or questions:
- Check execution logs: `SELECT * FROM skill_executions ORDER BY created_at DESC`
- Review skill ratings: `SELECT * FROM skill_ratings WHERE skill_id = 'your_skill'`
- Test skill independently: Use `/api/skills/{skill_id}/test` endpoint
