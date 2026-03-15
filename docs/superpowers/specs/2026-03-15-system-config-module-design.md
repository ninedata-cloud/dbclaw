# System Configuration Module Design Specification

**Date**: 2026-03-15  
**Author**: SmartDBA Development Team  
**Status**: Draft

## Overview

This specification describes a custom parameter configuration module that allows administrators to manage system-wide configuration parameters through a web interface. The module provides full CRUD functionality, stores configurations in the database, and enables dynamic configuration access from skills and services.

## Goals

1. Provide a flexible, database-backed configuration system for runtime parameters
2. Enable administrators to add, modify, and delete configuration parameters without code changes
3. Support multiple data types (string, number, boolean, JSON)
4. Initialize with existing Bocha AI API credentials
5. Allow skills to read configuration from database instead of hardcoded Settings
6. Maintain type safety and validation throughout the system

## Non-Goals

- Configuration encryption (not required per user feedback)
- Configuration versioning or audit history (future enhancement)
- Configuration import/export functionality (future enhancement)
- Multi-tenant configuration isolation (single-tenant system)

## Architecture

### Database Schema

**Table**: `system_configs`

```sql
CREATE TABLE system_configs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    key VARCHAR(100) UNIQUE NOT NULL,
    value TEXT,
    value_type VARCHAR(20) NOT NULL,
    description TEXT,
    category VARCHAR(50),
    is_active BOOLEAN DEFAULT TRUE,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_system_configs_key ON system_configs(key);
CREATE INDEX idx_system_configs_category ON system_configs(category);
```

**Fields**:
- `id`: Auto-incrementing primary key
- `key`: Unique configuration key (e.g., "bocha_api_key")
- `value`: String representation of the value (all types stored as text)
- `value_type`: Type indicator ("string", "integer", "float", "boolean", "json")
- `description`: Human-readable description of the parameter
- `category`: Grouping category (e.g., "external_api", "system", "database")
- `is_active`: Soft delete flag
- `created_at`, `updated_at`: Timestamps

**Initial Data**:
```sql
INSERT INTO system_configs (key, value, value_type, description, category) VALUES
('bocha_api_key', 'sk-66d203942a6c404b89eff2adb494febc', 'string', 'Bocha AI Web Search API Key', 'external_api'),
('bocha_api_url', 'https://api.bochaai.com/v1/web-search', 'string', 'Bocha AI Web Search API URL', 'external_api');
```

### Backend Components

#### 1. Model (`backend/models/system_config.py`)

```python
from sqlalchemy import Column, Integer, String, DateTime, Text, Boolean
from sqlalchemy.sql import func
from backend.database import Base

class SystemConfig(Base):
    __tablename__ = "system_configs"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    key = Column(String(100), unique=True, nullable=False, index=True)
    value = Column(Text)
    value_type = Column(String(20), nullable=False)
    description = Column(Text)
    category = Column(String(50), index=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
```

#### 2. Service (`backend/services/config_service.py`)

**Purpose**: Provide type-safe configuration retrieval with automatic type conversion.

**Key Methods**:
- `get_config(key: str, default: Any = None) -> Any`: Retrieve and parse configuration value
- `get_all_configs(category: str = None) -> List[SystemConfig]`: List configurations
- `set_config(key: str, value: Any, value_type: str, description: str = None, category: str = None)`: Create/update configuration
- `delete_config(key: str)`: Soft delete configuration

**Type Conversion Logic**:
```python
def _parse_value(self, value: str, value_type: str) -> Any:
    if value_type == "string":
        return value
    elif value_type == "integer":
        return int(value)
    elif value_type == "float":
        return float(value)
    elif value_type == "boolean":
        return value.lower() in ("true", "1", "yes")
    elif value_type == "json":
        return json.loads(value)
    else:
        return value
```

#### 3. Router (`backend/routers/system_configs.py`)

**Endpoints**:
- `GET /api/system-configs`: List all configurations (with optional category filter)
- `GET /api/system-configs/{id}`: Get single configuration
- `POST /api/system-configs`: Create new configuration
- `PUT /api/system-configs/{id}`: Update configuration
- `DELETE /api/system-configs/{id}`: Delete configuration

**Authentication**: All endpoints require admin role via `get_current_admin_user` dependency.

**Request/Response Models**:
```python
class SystemConfigCreate(BaseModel):
    key: str
    value: str
    value_type: str  # "string", "integer", "float", "boolean", "json"
    description: Optional[str] = None
    category: Optional[str] = None

class SystemConfigUpdate(BaseModel):
    value: Optional[str] = None
    value_type: Optional[str] = None
    description: Optional[str] = None
    category: Optional[str] = None
    is_active: Optional[bool] = None

class SystemConfigResponse(BaseModel):
    id: int
    key: str
    value: str
    value_type: str
    description: Optional[str]
    category: Optional[str]
    is_active: bool
    created_at: datetime
    updated_at: datetime
```

#### 4. Migration (`backend/migrations/add_system_configs.py`)

**Purpose**: Create table and initialize default configurations.

**Steps**:
1. Check if table exists
2. Create table with indexes
3. Insert initial bocha_api_key and bocha_api_url
4. Verify insertion

### Frontend Components

#### Page (`frontend/js/pages/system-configs.js`)

**Layout**:
```
+--------------------------------------------------+
| System Configuration                    [+ Add]  |
+--------------------------------------------------+
| Search: [________]  Category: [All ▼]            |
+--------------------------------------------------+
| Key              | Value      | Type    | Actions |
|------------------|------------|---------|---------|
| bocha_api_key    | sk-66d2... | string  | ✏️ 🗑️  |
| bocha_api_url    | https://.. | string  | ✏️ 🗑️  |
+--------------------------------------------------+
```

**Features**:
- Table view with search and category filtering
- Add/Edit modal with dynamic input based on value_type
- Delete confirmation dialog
- Real-time validation
- Toast notifications for success/error

**Input Components by Type**:
- `string`: Text input
- `integer`: Number input (step=1)
- `float`: Number input (step=0.01)
- `boolean`: Checkbox
- `json`: Textarea with JSON validation

**API Integration**:
```javascript
async function loadConfigs() {
    const response = await api.get('/api/system-configs');
    renderConfigTable(response.data);
}

async function saveConfig(data) {
    if (editingId) {
        await api.put(`/api/system-configs/${editingId}`, data);
    } else {
        await api.post('/api/system-configs', data);
    }
}
```

#### Navigation

**Location**: System Management group (after Skills Management)

```javascript
{
    label: '系统管理',
    items: [
        { label: '技能管理', path: '/skills', icon: 'zap' },
        { label: '参数配置', path: '/system-configs', icon: 'settings' }
    ]
}
```

### Skill Integration

#### Modified `web_search_bocha.yaml`

**Current Code** (lines 48-51):
```python
# Get API configuration
settings = get_settings()
api_key = settings.bocha_api_key
api_url = settings.bocha_api_url
```

**New Code**:
```python
# Get API configuration from database
from backend.services.config_service import ConfigService
config_service = ConfigService(context.db)
api_key = await config_service.get_config('bocha_api_key')
api_url = await config_service.get_config('bocha_api_url')
```

**Context Enhancement**: The skill execution context must provide database session access via `context.db`.

## Data Flow

### Configuration Retrieval Flow

```
Skill/Service
    ↓
ConfigService.get_config(key)
    ↓
Query system_configs table
    ↓
Parse value based on value_type
    ↓
Return typed value
```

### Configuration Update Flow

```
Frontend Form
    ↓
POST /api/system-configs
    ↓
Validate admin authentication
    ↓
Validate request data
    ↓
ConfigService.set_config()
    ↓
Insert/Update database
    ↓
Return success response
```

## Error Handling

### Backend Errors

1. **Duplicate Key**: Return 400 with message "Configuration key already exists"
2. **Invalid Type**: Return 400 with message "Invalid value_type: {type}"
3. **Type Conversion Error**: Return 400 with message "Cannot convert value to {type}"
4. **Not Found**: Return 404 with message "Configuration not found"
5. **Unauthorized**: Return 401 with message "Admin access required"

### Frontend Errors

1. **Network Error**: Toast notification "Failed to load configurations"
2. **Validation Error**: Inline error message below input field
3. **JSON Parse Error**: "Invalid JSON format" message in textarea
4. **Delete Confirmation**: Modal dialog "Are you sure you want to delete this configuration?"

## Security Considerations

1. **Authentication**: All endpoints require admin role
2. **Input Validation**: Pydantic models validate all inputs
3. **SQL Injection**: SQLAlchemy ORM prevents SQL injection
4. **XSS Prevention**: Frontend escapes all user input
5. **No Encryption**: Per user requirement, values stored in plain text

**Note**: If sensitive values (API keys, passwords) need protection in the future, add an `is_encrypted` flag and use the existing `backend/utils/encryption.py` module.

## Testing Strategy

### Backend Tests

1. **Model Tests**:
   - Create/read/update/delete operations
   - Unique key constraint
   - Timestamp auto-update

2. **Service Tests**:
   - Type conversion for all supported types
   - Default value handling
   - Category filtering
   - Error handling for invalid types

3. **Router Tests**:
   - Admin authentication enforcement
   - CRUD endpoint functionality
   - Request validation
   - Error responses

### Frontend Tests

1. **Manual Testing**:
   - Add configuration with each value type
   - Edit existing configuration
   - Delete configuration
   - Search and filter functionality
   - Form validation

2. **Integration Testing**:
   - Verify web_search_bocha skill reads from database
   - Test configuration changes take effect immediately

## Migration Path

1. Run migration script to create table and insert initial data
2. Verify bocha_api_key and bocha_api_url are present
3. Update web_search_bocha.yaml to use ConfigService
4. Test web search functionality
5. Deploy frontend page
6. Verify admin can manage configurations

## Future Enhancements

1. **Configuration History**: Track changes with audit log
2. **Configuration Validation**: Add custom validation rules per key
3. **Configuration Groups**: Hierarchical configuration organization
4. **Import/Export**: Backup and restore configurations
5. **Environment Overrides**: Allow environment variables to override database values
6. **Configuration Templates**: Predefined configuration sets for common scenarios

## Appendix: File Checklist

### Backend Files
- [ ] `backend/models/system_config.py` - Model definition
- [ ] `backend/services/config_service.py` - Service layer
- [ ] `backend/routers/system_configs.py` - API endpoints
- [ ] `backend/migrations/add_system_configs.py` - Database migration
- [ ] `backend/models/__init__.py` - Add SystemConfig import
- [ ] `backend/app.py` - Register router
- [ ] `backend/skills/builtin/web_search_bocha.yaml` - Update to use ConfigService
- [ ] `backend/skills/context.py` - Add db session to context

### Frontend Files
- [ ] `frontend/js/pages/system-configs.js` - Page implementation
- [ ] `frontend/css/system-configs.css` - Page styles (optional, can reuse existing)
- [ ] `frontend/index.html` - Add script tag
- [ ] `frontend/js/components/sidebar.js` - Add navigation item

### Documentation
- [x] `docs/superpowers/specs/2026-03-15-system-config-module-design.md` - This document

## Conclusion

This design provides a flexible, type-safe configuration management system that meets all stated requirements. The architecture follows SmartDBA's existing patterns (SQLAlchemy async, FastAPI routers, vanilla JavaScript frontend) and integrates seamlessly with the skills system. The implementation is straightforward with clear separation of concerns and comprehensive error handling.
