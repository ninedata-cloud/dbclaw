# Report Generation Bug Fixes

## Date: 2026-03-08

## Issues Fixed

### 1. DiagnosticEngine Crash on Non-List Data (diagnostic_engine.py)

**Problem:**
- `_check_slow_queries()` tried to access `slow_queries[0]` without checking if it's a list
- `_check_table_health()` tried to call `.get()` on string items in the list
- Caused `KeyError: 0` and `AttributeError: 'str' object has no attribute 'get'`

**Fix:**
- Added `isinstance(slow_queries, list)` check before accessing as list
- Added `isinstance(table_stats, list)` check and `isinstance(t, dict)` check for each item
- Prevents crashes when data is in unexpected format

**Files Modified:**
- `backend/services/diagnostic_engine.py` (lines 130, 187)

---

### 2. MetricSnapshot Field Name Mismatch (skills/context.py)

**Problem:**
- Code used `MetricSnapshot.created_at` but the actual column name is `collected_at`
- Caused `AttributeError: type object 'MetricSnapshot' has no attribute 'created_at'`

**Fix:**
- Changed all references from `created_at` to `collected_at` in the `get_metrics()` method

**Files Modified:**
- `backend/skills/context.py` (lines 133, 135, 143)

---

### 3. Data Structure Mismatch Between Skills and DiagnosticEngine

**Problem:**
- Skills return wrapped data: `{"success": true, "metrics": {...}}`
- DiagnosticEngine expects direct data dictionaries
- Field names don't match:
  - Skill returns: `active_connections`, `cache_hit_ratio` (string "96.68%")
  - Engine expects: `connections_active`, `cache_hit_rate` (float)
- Result: 0 findings generated even when issues exist

**Fix:**
- Added data unwrapping logic in `ai_report_generator.py`
- Added field name normalization:
  - `active_connections` → `connections_active`
  - `total_connections` → `connections_total`
  - `cache_hit_ratio` (string) → `cache_hit_rate` (float)
- Added OS metrics parsing:
  - Extract CPU usage from string
  - Parse memory usage from `free` command output
  - Parse disk usage from `df` command output

**Files Modified:**
- `backend/services/ai_report_generator.py` (lines 118-180)
- `backend/skills/builtin/pg_get_db_status.yaml` (added `total_connections` field)

---

## Test Results

**Before Fix:**
- Reports generated with 0 findings
- AI analysis present but rule-based validation failed
- Crashes on certain data types

**After Fix:**
- Reports generate successfully with findings
- Example: "Found 1 issues: 0 critical, 1 warnings, 0 informational"
- Finding: "High active connections - 61 active connections out of 100 total"
- No crashes on edge cases

---

## Technical Details

### Data Flow

1. **Skill Execution** → Returns wrapped data:
   ```json
   {
     "success": true,
     "metrics": {
       "active_connections": 60,
       "cache_hit_ratio": "96.68%"
     }
   }
   ```

2. **Data Collection** (ai_report_generator.py) → Unwraps and normalizes:
   ```python
   {
     "connections_active": 60,
     "connections_total": 100,
     "cache_hit_rate": 96.68
   }
   ```

3. **DiagnosticEngine** → Analyzes normalized data:
   ```python
   if status.get("connections_active", 0) > 50:
       # Generate finding
   ```

### Field Mapping Table

| Skill Field | Engine Field | Transformation |
|-------------|--------------|----------------|
| `active_connections` | `connections_active` | Direct copy |
| `total_connections` | `connections_total` | Direct copy |
| `cache_hit_ratio` | `cache_hit_rate` | Parse "96.68%" → 96.68 |
| `cpu_usage` | `cpu_usage_percent` | Parse string to float |
| `memory` (text) | `memory_usage_percent` | Parse `free` output |
| `disk` (text) | `disk_usage_percent` | Parse `df` output |

---

## Remaining Considerations

1. **MySQL/Oracle/SQL Server**: May need similar field mappings for other database types
2. **Error Handling**: JSON parsing errors are silently caught - consider logging
3. **Data Validation**: Could add schema validation before passing to DiagnosticEngine
4. **Performance**: Multiple string parsing operations - consider caching

---

## Files Changed

1. `backend/services/diagnostic_engine.py`
2. `backend/skills/context.py`
3. `backend/services/ai_report_generator.py`
4. `backend/skills/builtin/pg_get_db_status.yaml`

## Test Files Created

1. `test_report_generation.py` - Comprehensive test script for debugging report generation
