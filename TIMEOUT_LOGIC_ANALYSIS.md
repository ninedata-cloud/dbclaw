# SmartDBA Skills System - Timeout Logic Analysis

## Overview

The SmartDBA skills system implements a multi-layered timeout mechanism to prevent long-running operations from blocking the system. This document provides a comprehensive analysis of the timeout logic flow.

## Timeout Hierarchy

### 1. Skill Definition Level (YAML)
**Location**: `backend/skills/builtin/*.yaml`

Skills can define their own timeout in the YAML definition:

```yaml
id: get_os_metrics
timeout: 120  # seconds
```

**Default values observed**:
- Most database query skills: `30s`
- OS command execution skills: `120s` (e.g., `get_os_metrics`, `execute_os_command`)
- No timeout specified: Falls back to executor default

### 2. Executor Level (Python)
**Location**: `backend/skills/executor.py`

```python
class SkillExecutor:
    DEFAULT_TIMEOUT = 30  # seconds
    MAX_TIMEOUT = 3600  # 1 hour (safety cap)
```

**Priority logic** (line 62-66):
```python
# Priority: dynamic timeout > skill timeout > default timeout
if timeout is None:
    timeout = skill.timeout if skill.timeout else self.DEFAULT_TIMEOUT
# Cap at MAX_TIMEOUT for safety
timeout = min(timeout, self.MAX_TIMEOUT)
```

**Enforcement**: Uses `asyncio.wait_for()` to enforce timeout:
```python
result = await asyncio.wait_for(
    self._execute_code(skill.code, params, context),
    timeout=timeout,
)
```

### 3. Conversation/API Level
**Location**: `backend/agent/conversation_skills.py`

The `execute_skill_call()` function allows dynamic timeout override:

```python
# Extract timeout from arguments if provided
timeout = arguments.pop('timeout', None)
if timeout:
    timeout = max(30, min(int(timeout), 3600))  # Clamp between 30s and 1h

executor = SkillExecutor()
result = await executor.execute(skill, arguments, context, timeout=timeout)
```

**Clamping logic**: 
- Minimum: 30 seconds
- Maximum: 3600 seconds (1 hour)

### 4. SSH Command Level
**Location**: `backend/services/ssh_service.py`

The SSH service has its own timeout for command execution:

```python
def execute(self, command: str, timeout: int = 30) -> str:
    stdin, stdout, stderr = client.exec_command(command, timeout=timeout)
```

**Connection timeout**: 10 seconds (hardcoded in `_get_client()`)

**Issue**: The SSH timeout is NOT connected to the skill timeout!

## Timeout Flow Diagram

```
User Request
    ↓
AI Agent (conversation_skills.py)
    ↓
Extract timeout from arguments (optional)
    ↓ (clamped 30s-3600s)
SkillExecutor.execute(skill, params, context, timeout)
    ↓
Determine final timeout:
  1. Dynamic timeout (from arguments)
  2. Skill.timeout (from YAML)
  3. DEFAULT_TIMEOUT (30s)
    ↓
Cap at MAX_TIMEOUT (3600s)
    ↓
asyncio.wait_for(execute_code(), timeout)
    ↓
Skill code executes
    ↓
context.execute_command(cmd, datasource_id)
    ↓
host_executor.execute_host_command()
    ↓
SSHService.execute(command, timeout=30)  ← FIXED 30s!
    ↓
paramiko.exec_command(command, timeout=30)
```

## Issues Identified

### 1. SSH Timeout Disconnect
**Problem**: The SSH service always uses a hardcoded 30-second timeout, regardless of the skill's configured timeout.

**Example scenario**:
- Skill YAML defines `timeout: 120`
- SkillExecutor enforces 120s timeout
- But SSH command times out at 30s
- Result: SSH timeout occurs before skill timeout

**Impact**: Skills that need longer SSH command execution (e.g., slow diagnostic queries, large log file processing) will fail prematurely.

### 2. No Timeout Propagation
**Problem**: The timeout value doesn't propagate from the skill executor down to the SSH layer.

**Current flow**:
```
SkillExecutor (120s) → context.execute_command() → host_executor → SSHService (30s)
```

**Missing**: Timeout parameter passing through the chain.

### 3. Connection Timeout vs Execution Timeout
**SSH has two timeouts**:
- Connection timeout: 10s (for establishing SSH connection)
- Execution timeout: 30s (for command execution)

Both are hardcoded and not configurable.

## Recommendations

### Fix 1: Propagate Timeout Through Context
Modify `SkillContext.execute_host_command()` to accept and pass timeout:

```python
async def execute_host_command(
    self, 
    command: str, 
    datasource_id: int, 
    allow_write: bool = False,
    timeout: int = None  # Add timeout parameter
) -> Dict[str, Any]:
    # ... existing code ...
    result = await execute_host_command(
        self.db, 
        datasource.host_id, 
        command, 
        allow_write=allow_write,
        timeout=timeout  # Pass timeout
    )
```

### Fix 2: Update host_executor
```python
async def execute_host_command(
    db: AsyncSession, 
    host_id: int, 
    command: str, 
    allow_write: bool = False,
    timeout: int = 30  # Add timeout parameter with default
) -> Dict[str, Any]:
    # ... existing code ...
    output = await loop.run_in_executor(
        None, 
        ssh_service.execute, 
        command,
        timeout  # Pass timeout to SSH service
    )
```

### Fix 3: Make SSH Timeouts Configurable
```python
class SSHService:
    def __init__(
        self, 
        host: str, 
        port: int = 22, 
        username: str = "",
        password: str = None, 
        private_key: str = None,
        connection_timeout: int = 10,  # Add parameter
        execution_timeout: int = 30    # Add parameter
    ):
        self.connection_timeout = connection_timeout
        self.execution_timeout = execution_timeout
```

### Fix 4: Pass Timeout from Executor to Context
Modify `SkillExecutor.execute()` to pass timeout to context methods:

```python
# Store timeout in context for use by execute_command
context._timeout = timeout

# Or pass explicitly in each call
result = await context.execute_command(
    command, 
    datasource_id,
    timeout=timeout
)
```

## Current Timeout Values Summary

| Layer | Default | Max | Configurable |
|-------|---------|-----|--------------|
| Skill YAML | 30s | N/A | Yes (per skill) |
| SkillExecutor | 30s | 3600s | Yes (via arguments) |
| SSH Connection | 10s | N/A | No (hardcoded) |
| SSH Execution | 30s | N/A | No (hardcoded) |

## Testing Recommendations

1. **Test timeout propagation**: Create a skill that runs a long command (e.g., `sleep 60`) with different timeout values
2. **Test timeout hierarchy**: Verify that dynamic > skill > default priority works correctly
3. **Test SSH timeout**: Verify that SSH commands respect the skill timeout
4. **Test timeout capping**: Verify that MAX_TIMEOUT (3600s) is enforced
5. **Test timeout error handling**: Verify that timeout errors are properly logged and returned

## Related Files

- `backend/skills/schema.py` - Skill definition schema with timeout field
- `backend/skills/executor.py` - Timeout enforcement logic
- `backend/skills/context.py` - Context API for skill execution
- `backend/agent/conversation_skills.py` - Dynamic timeout from AI arguments
- `backend/utils/host_executor.py` - SSH command execution wrapper
- `backend/services/ssh_service.py` - Low-level SSH operations
- `backend/skills/builtin/*.yaml` - Individual skill timeout configurations
