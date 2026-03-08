# API Method Naming Fix

## Issue
Login page was throwing "API.getConnections is not a function" error after successful authentication.

## Root Cause
The API method was renamed from `getConnections()` to `getDatasources()` to match the backend endpoint `/api/datasources`, but several frontend files were still using the old method name and variable names.

## Solution
Updated all references from `connections` to `datasources` for consistency.

### Changes Made

1. **Login Page** (`frontend/js/pages/login.js`):
   - Changed `API.getConnections()` → `API.getDatasources()`
   - Changed `Store.set('connections', connections)` → `Store.set('datasources', datasources)`

2. **Query Page** (`frontend/js/pages/query.js`):
   - Changed variable name `connections` → `datasources`
   - Changed `Store.set('connections', connections)` → `Store.set('datasources', datasources)`

3. **Dashboard Page** (`frontend/js/pages/dashboard.js`):
   - Changed variable name `connections` → `datasources` throughout
   - Changed `Store.set('connections', connections)` → `Store.set('datasources', datasources)`

4. **Diagnosis Page** (`frontend/js/pages/diagnosis.js`):
   - Changed variable name `connections` → `datasources` throughout
   - Changed `Store.set('connections', connections)` → `Store.set('datasources', datasources)`

5. **Monitor Page** (`frontend/js/pages/monitor.js`):
   - Changed `Store.set('connections', conns)` → `Store.set('datasources', conns)`

## Result
✅ Login now works correctly
✅ Datasources load properly after authentication
✅ Consistent naming across frontend and backend
✅ All pages use the correct API method

## Verification
```bash
# No remaining references to old method
grep -r "API.getConnections" frontend/js/
# Returns: (empty)

grep -r "Store.set('connections'" frontend/js/
# Returns: (empty)
```

## Note
The backend uses "datasources" terminology consistently:
- Endpoint: `/api/datasources`
- Model: `Datasource`
- Router: `datasources.py`

Frontend now matches this naming convention.
