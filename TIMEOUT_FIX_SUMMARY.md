# SSH Timeout Fix Summary

## Problem
SSH commands were hardcoded to use a 30-second timeout, regardless of the skill's configured timeout value. This caused skills with longer timeouts (e.g., `timeout: 120`) to fail prematurely when executing SSH commands.

## Root Cause
The timeout value was not propagated through the execution chain:
```
SkillExecutor (120s) → SkillContext → host_executor → SSHService (30s hardcoded)
```

## Solution
Modified the execution chain to propagate timeout values from the skill configuration down to the SSH layer.

## Changes Made

### 1. SkillContext (`backend/skills/context.py`)
- Added `timeout` parameter to `__init__()` to store the execution timeout
- Updated `execute_command()` to accept optional timeout and use context timeout as fallback
- Updated `execute_host_command()` to accept optional timeout and pass it to host_executor

```python
def __init__(self, ..., timeout: Optional[int] = None):
    self.timeout = timeout  # Store timeout for use in execute_command

async def execute_command(self, command: str, datasource_id: int, timeout: int = None):
    exec_timeout = timeout if timeout is not None else self.timeout
    return await self.execute_host_command(..., timeout=exec_timeout)

async def execute_host_command(self, ..., timeout: int = None):
    exec_timeout = timeout if timeout is not None else self.timeout
    result = await execute_host_command(..., timeout=exec_timeout)
```

### 2. host_executor (`backend/utils/host_executor.py`)
- Added `timeout` parameter to `execute_host_command()` with default value of 30s
- Pass timeout to SSHService.execute()

```python
async def execute_host_command(..., timeout: int = None):
    exec_timeout = timeout if timeout is not None else 30
    output = await loop.run_in_executor(None, ssh_service.execute, command, exec_timeout)
```

### 3. conversation_skills (`backend/agent/conversation_skills.py`)
- Calculate final timeout before creating SkillContext (following same priority logic as SkillExecutor)
- Pass timeout to SkillContext constructor

```python
# Determine final timeout (same logic as SkillExecutor)
# Priority: dynamic timeout > skill timeout > default timeout
if timeout is None:
    timeout = skill.timeout if skill.timeout else SkillExecutor.DEFAULT_TIMEOUT
timeout = min(timeout, SkillExecutor.MAX_TIMEOUT)

context = SkillContext(..., timeout=timeout)
```

### 4. API skills endpoint (`backend/api/skills.py`)
- Updated test endpoint to pass timeout to SkillContext

```python
timeout = skill.timeout if skill.timeout else SkillExecutor.DEFAULT_TIMEOUT
context = SkillContext(..., timeout=timeout)
```

## Timeout Flow (After Fix)

```
User Request
    ↓
AI Agent (conversation_skills.py)
    ↓
Calculate final timeout:
  1. Dynamic timeout (from arguments)
  2. Skill.timeout (from YAML)
  3. DEFAULT_TIMEOUT (30s)
    ↓
Cap at MAX_TIMEOUT (3600s)
    ↓
Create SkillContext(timeout=calculated_timeout)
    ↓
SkillExecutor.execute(skill, params, context, timeout)
    ↓
asyncio.wait_for(execute_code(), timeout)
    ↓
Skill code executes
    ↓
context.execute_command(cmd, datasource_id)
  → Uses context.timeout if no explicit timeout
    ↓
host_executor.execute_host_command(..., timeout=context.timeout)
    ↓
SSHService.execute(command, timeout=context.timeout)  ✓ Now respects skill timeout!
    ↓
paramiko.exec_command(command, timeout=context.timeout)
```

## Timeout Priority

The timeout resolution follows this priority (highest to lowest):

1. **Explicit timeout in execute_command()** - If skill code passes timeout explicitly
2. **Context timeout** - Set when SkillContext is created
3. **Default (30s)** - Fallback in host_executor if no timeout provided

The context timeout itself is determined by:
1. **Dynamic timeout** - Passed via AI agent arguments (30s-3600s range)
2. **Skill timeout** - Defined in YAML (e.g., `timeout: 120`)
3. **DEFAULT_TIMEOUT** - 30 seconds (SkillExecutor.DEFAULT_TIMEOUT)

All timeouts are capped at **MAX_TIMEOUT (3600s)** for safety.

## Testing

Created `test_timeout_propagation.py` to verify:
- ✓ Skills with `timeout: 120` are correctly loaded
- ✓ SkillContext accepts and stores timeout parameter
- ✓ Timeout priority logic works correctly
- ✓ Dynamic timeout overrides skill timeout
- ✓ Context timeout is used as fallback

All tests passed successfully.

## Impact

Skills that require longer SSH command execution times (e.g., slow diagnostic queries, large log file processing) will now work correctly:

- `get_os_metrics` (timeout: 120s) - Can now run commands that take up to 2 minutes
- `execute_os_command` (timeout: 120s) - Can now execute longer diagnostic commands
- `execute_any_os_command` (timeout: 120s) - Can now handle longer operations

## Backward Compatibility

The changes are fully backward compatible:
- All timeout parameters are optional with sensible defaults
- Existing code that doesn't pass timeout will use default values
- Skills without explicit timeout configuration will use DEFAULT_TIMEOUT (30s)

## Related Files

- `backend/skills/context.py` - Context API with timeout support
- `backend/utils/host_executor.py` - SSH command execution wrapper
- `backend/agent/conversation_skills.py` - Timeout calculation and context creation
- `backend/api/skills.py` - Test endpoint with timeout support
- `backend/services/ssh_service.py` - Low-level SSH operations (unchanged)
- `test_timeout_propagation.py` - Verification tests
