# Bug Fix: threshold_checker.py Variable Name Conflict

**Date**: 2026-03-15  
**Issue**: UnboundLocalError in threshold_checker.py  
**Status**: ✅ Fixed

## Problem

```
UnboundLocalError: cannot access local variable 'now' where it is not associated with a value
```

**Root Cause**: Variable name conflict in `backend/services/threshold_checker.py`

- Line 9: Imported `now` function from `backend.utils.datetime_helper`
- Line 64: Used `now = now()` which creates a local variable `now`
- Line 346: Same issue in `get_violation_status` method

When Python sees `now = now()`, it treats `now` as a local variable throughout the function scope, causing the function call `now()` to fail because the local variable hasn't been assigned yet.

## Solution

Renamed the imported function to avoid conflict:

```python
# Before
from backend.utils.datetime_helper import now

def check_thresholds(...):
    now = now()  # ❌ Error: local variable 'now' referenced before assignment

# After
from backend.utils.datetime_helper import now as get_now

def check_thresholds(...):
    now = get_now()  # ✅ Works: calls get_now() function
```

## Changes Made

**File**: `backend/services/threshold_checker.py`

1. **Line 9**: Changed import statement
   ```python
   from backend.utils.datetime_helper import now as get_now
   ```

2. **Line 64**: Updated function call
   ```python
   now = get_now()
   ```

3. **Line 346**: Updated function call in `get_violation_status`
   ```python
   now = get_now()
   ```

## Verification

```bash
python -c "
from backend.services.threshold_checker import ThresholdChecker
checker = ThresholdChecker()
violations = checker.check_thresholds(
    datasource_id=1,
    metrics={'cpu_usage': 90.0},
    threshold_rules={'cpu_usage': {'threshold': 80, 'duration': 60}}
)
print('✓ Fixed successfully')
"
```

**Result**: ✅ No errors

## Impact

- **Affected Component**: Metric collector threshold checking
- **Severity**: High (prevented threshold-based inspection triggers)
- **Users Affected**: All users with threshold rules configured
- **Downtime**: None (hot fix applied)

## Testing

- [x] Import test passed
- [x] Basic functionality test passed
- [x] No syntax errors
- [x] Server restart successful

## Related Files

- `backend/services/threshold_checker.py` (fixed)
- `backend/services/metric_collector.py` (caller, no changes needed)
- `backend/utils/datetime_helper.py` (no changes needed)

## Prevention

This type of error can be prevented by:
1. Using more descriptive variable names (e.g., `current_time` instead of `now`)
2. Avoiding shadowing imported names
3. Running static analysis tools (pylint, mypy) that catch these issues

## Notes

This bug was introduced when the `datetime_helper.now()` function was added to provide timezone-aware datetime objects. The original code likely used `datetime.now()` directly without the naming conflict.


---

## Additional Fix: inspection_service.py

**Date**: 2026-03-15  
**Issue**: Same UnboundLocalError in inspection_service.py

### Problem

Same variable name conflict in `backend/services/inspection_service.py`:
- Line 14: Imported `now` function
- Line 64: Used `now()` in `initialize_all_configs`
- Line 101: Used `now = now()` in `_scheduler_loop`

### Solution

Applied the same fix:

```python
# Line 14
from backend.utils.datetime_helper import now as get_now

# Line 64
next_scheduled_at=get_now() + timedelta(seconds=86400)

# Line 101
now = get_now()
```

### Verification

```bash
python -c "from backend.services.inspection_service import InspectionService"
```

**Result**: ✅ No errors

### Files Fixed

1. `backend/services/threshold_checker.py` ✅
2. `backend/services/inspection_service.py` ✅

### Remaining Files Using `now`

The following files import `now` but don't have the shadowing issue:
- backend/agent/conversation_skills.py
- backend/skills/context.py
- backend/services/kb_processor.py
- backend/services/ai_report_generator.py
- backend/services/metric_normalizer.py
- backend/services/report_generator.py
- backend/services/metric_collector.py

These files either:
1. Don't assign to a variable named `now`
2. Use different variable names (e.g., `current_time`)

### Prevention Recommendation

Consider renaming the `now()` function in `backend/utils/datetime_helper.py` to something more descriptive like `get_current_time()` or `utcnow()` to avoid future shadowing issues.


---

## Bug #3: metric_normalizer.py

**Date**: 2026-03-15  
**Issue**: `unsupported operand type(s) for -: 'function' and 'function'`

### Problem

In `backend/services/metric_normalizer.py`, the `_calculate_rate` method had two bugs:

**Line 163**: Correctly called `timestamp = now()`  
**Line 169**: Missing parentheses - `'timestamp': now` (should be `now()`)  
**Line 178**: Used function reference - `(now - last_time)` (should be `(timestamp - last_time)`)  
**Line 196**: Missing parentheses - `'timestamp': now` (should be `timestamp`)

This caused the error when trying to subtract two function references instead of datetime objects.

### Root Cause

1. Line 169 stored the function reference `now` instead of calling it
2. Line 178 tried to subtract `now` (function) from `last_time` (datetime)
3. Line 196 stored the function reference again

### Solution

```python
# Line 163 - Already correct
timestamp = now()

# Line 169 - Fixed
'timestamp': timestamp  # Use the timestamp variable

# Line 178 - Fixed  
time_diff = (timestamp - last_time).total_seconds()  # Use timestamp variable

# Line 196 - Fixed
'timestamp': timestamp  # Use the timestamp variable
```

### Verification

```bash
python3 -c "
from backend.services.metric_normalizer import MetricNormalizer
result = MetricNormalizer.normalize('mysql', 1, {'connections': 10})
print('✓ Fixed successfully')
"
```

**Result**: ✅ No errors

### Impact

- **Affected Component**: Metric rate calculation (QPS, TPS)
- **Severity**: High (prevented rate metrics from being calculated)
- **Users Affected**: All users monitoring QPS/TPS metrics
- **Symptoms**: Error in metric collection logs

---

## Summary of All Fixes

| File | Issue | Lines Fixed | Status |
|------|-------|-------------|--------|
| threshold_checker.py | Variable shadowing `now` | 9, 64, 346 | ✅ |
| inspection_service.py | Variable shadowing `now` | 14, 64, 101 | ✅ |
| metric_normalizer.py | Missing parentheses & wrong variable | 169, 178, 196 | ✅ |

### Common Pattern

All three bugs involved the `now` function from `backend.utils.datetime_helper`:
1. **threshold_checker.py & inspection_service.py**: Variable name shadowing
2. **metric_normalizer.py**: Missing function call parentheses

### Prevention

1. Rename `now()` function to `get_now()` or `utcnow()` to avoid shadowing
2. Use linters (pylint, mypy) to catch these issues
3. Add type hints to catch function vs value mismatches
4. Add unit tests for rate calculation logic

