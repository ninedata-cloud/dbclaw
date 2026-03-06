# SmartDBA Skill Management - Quick Start Guide

## What is the Skill System?

The Skill Management System allows you to create custom diagnostic capabilities for SmartDBA without modifying code. Skills are defined in YAML format and executed in a secure sandbox.

## Creating Your First Skill

### 1. Basic Skill Structure

Create a file `my_skill.yaml`:

```yaml
id: my_first_skill
name: My First Skill
version: 1.0.0
category: custom
description: A simple example skill
tags: [example, tutorial]

parameters:
  - name: connection_id
    type: integer
    required: true
    description: Database connection ID

permissions:
  - execute_query

code: |
  async def execute(context, params):
      # Your skill logic here
      result = await context.execute_query(
          "SELECT VERSION()",
          params['connection_id']
      )
      return {
          "success": True,
          "version": result
      }
```

### 2. Import the Skill

1. Open SmartDBA UI
2. Navigate to Skills page
3. Click "Import Skill"
4. Select your YAML file
5. Click Import

### 3. Test the Skill

1. Find your skill in the grid
2. Click "Test"
3. Enter `connection_id: 1`
4. Click Execute
5. View the result

### 4. Use in AI Diagnosis

The skill is now automatically available to the AI agent:

```
User: "What database version am I running?"
AI: [Calls my_first_skill]
AI: "You're running MySQL 8.0.32"
```

## Common Skill Patterns

### Query Database

```yaml
code: |
  async def execute(context, params):
      result = await context.execute_query(
          "SELECT * FROM information_schema.tables LIMIT 10",
          params['connection_id']
      )
      return result
```

### Execute OS Command

```yaml
permissions:
  - execute_command

code: |
  async def execute(context, params):
      result = await context.execute_command(
          "df -h",
          params['connection_id']
      )
      return result
```

### Search Knowledge Base

```yaml
permissions:
  - access_kb

code: |
  async def execute(context, params):
      results = await context.search_kb(
          params['query'],
          kb_ids=None,  # Use session KBs
          top_k=5
      )
      return {"results": results}
```

### Combine Multiple Operations

```yaml
code: |
  async def execute(context, params):
      # Get database status
      status = await context.execute_query(
          "SHOW GLOBAL STATUS",
          params['connection_id']
      )

      # Get OS metrics
      os_metrics = await context.execute_command(
          "free -m",
          params['connection_id']
      )

      return {
          "db_status": status,
          "os_metrics": os_metrics
      }
```

## Parameter Types

- `string` - Text values
- `integer` - Whole numbers
- `boolean` - true/false
- `array` - Lists
- `object` - Dictionaries

## Available Permissions

- `execute_query` - Run SQL queries
- `execute_command` - Run OS commands via SSH
- `access_kb` - Search knowledge bases
- `read_logs` - Access log files
- `modify_config` - Change configurations

## Tips

1. **Start Simple**: Begin with read-only queries
2. **Test Thoroughly**: Use the test feature before enabling
3. **Add Descriptions**: Help the AI understand when to use your skill
4. **Use Tags**: Make skills discoverable
5. **Handle Errors**: Wrap operations in try/except

## Example: MySQL Slow Query Analyzer

```yaml
id: mysql_slow_query_analyzer
name: MySQL Slow Query Analyzer
version: 1.0.0
category: mysql
description: Analyzes slow queries and provides optimization recommendations
tags: [mysql, performance, slow-queries]

parameters:
  - name: connection_id
    type: integer
    required: true
    description: Database connection ID
  - name: min_duration
    type: integer
    required: false
    default: 1
    description: Minimum query duration in seconds

permissions:
  - execute_query

code: |
  async def execute(context, params):
      min_duration = params.get('min_duration', 1)

      # Get slow queries from performance_schema
      query = f"""
      SELECT
          DIGEST_TEXT as query,
          COUNT_STAR as exec_count,
          AVG_TIMER_WAIT/1000000000000 as avg_time_sec,
          MAX_TIMER_WAIT/1000000000000 as max_time_sec
      FROM performance_schema.events_statements_summary_by_digest
      WHERE AVG_TIMER_WAIT/1000000000000 > {min_duration}
      ORDER BY AVG_TIMER_WAIT DESC
      LIMIT 10
      """

      result = await context.execute_query(query, params['connection_id'])

      if not result.get('success'):
          return result

      # Analyze and provide recommendations
      recommendations = []
      for row in result.get('data', []):
          if 'SELECT *' in str(row[0]):
              recommendations.append("Avoid SELECT *, specify columns explicitly")
          if 'WHERE' not in str(row[0]):
              recommendations.append("Add WHERE clause to filter results")

      return {
          "success": True,
          "slow_queries": result.get('data', []),
          "recommendations": list(set(recommendations))
      }
```

## Next Steps

- Explore built-in skills for examples
- Create skills for your specific use cases
- Share skills with your team
- Rate and review community skills

## Need Help?

- Check the full documentation in SKILLS_README.md
- Review built-in skills in `backend/skills/builtin/`
- Test skills using the API: `POST /api/skills/{skill_id}/test`
