# System Configuration Module Design Specification

**Date**: 2026-03-15  
**Author**: DbGuard Development Team  
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

**Implementation Pattern**: Stateless async functions (following project service patterns).

**Key Functions**:
```python
import json
from typing import Any, List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from backend.models.system_config import SystemConfig

async def get_config(db: AsyncSession, key: str, default: Any = None) -> Any:
    """Retrieve and parse configuration value"""
    result = await db.execute(
        select(SystemConfig).where(
            SystemConfig.key == key,
            SystemConfig.is_active == True
        )
    )
    config = result.scalar_one_or_none()
    if not config:
        return default
    return _parse_value(config.value, config.value_type)

async def get_all_configs(db: AsyncSession, category: Optional[str] = None) -> List[SystemConfig]:
    """List configurations"""
    query = select(SystemConfig).where(SystemConfig.is_active == True)
    if category:
        query = query.where(SystemConfig.category == category)
    result = await db.execute(query)
    return result.scalars().all()

async def set_config(
    db: AsyncSession,
    key: str,
    value: str,
    value_type: str,
    description: Optional[str] = None,
    category: Optional[str] = None
) -> SystemConfig:
    """Create or update configuration"""
    result = await db.execute(select(SystemConfig).where(SystemConfig.key == key))
    config = result.scalar_one_or_none()

    if config:
        config.value = value
        config.value_type = value_type
        if description is not None:
            config.description = description
        if category is not None:
            config.category = category
    else:
        config = SystemConfig(
            key=key,
            value=value,
            value_type=value_type,
            description=description,
            category=category
        )
        db.add(config)

    await db.commit()
    await db.refresh(config)
    return config

async def delete_config(db: AsyncSession, key: str) -> bool:
    """Soft delete configuration"""
    result = await db.execute(select(SystemConfig).where(SystemConfig.key == key))
    config = result.scalar_one_or_none()
    if not config:
        return False
    config.is_active = False
    await db.commit()
    return True

def _parse_value(value: str, value_type: str) -> Any:
    """Parse string value to appropriate type with error handling"""
    try:
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
    except (ValueError, json.JSONDecodeError) as e:
        raise ValueError(f"Cannot convert value '{value}' to {value_type}: {str(e)}")
```

#### 3. Router (`backend/routers/system_configs.py`)

**Endpoints**:
- `GET /api/system-configs`: List all configurations (with optional category filter)
- `GET /api/system-configs/{id}`: Get single configuration
- `POST /api/system-configs`: Create new configuration
- `PUT /api/system-configs/{id}`: Update configuration
- `DELETE /api/system-configs/{id}`: Delete configuration

**Authentication**: All endpoints require admin role via `get_current_admin` dependency (from `backend/dependencies.py`).

**Schemas** (`backend/schemas/system_config.py`):
```python
from pydantic import BaseModel
from typing import Optional, Literal
from datetime import datetime

class SystemConfigCreate(BaseModel):
    key: str
    value: str
    value_type: Literal["string", "integer", "float", "boolean", "json"]
    description: Optional[str] = None
    category: Optional[str] = None

class SystemConfigUpdate(BaseModel):
    value: Optional[str] = None
    value_type: Optional[Literal["string", "integer", "float", "boolean", "json"]] = None
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

    class Config:
        from_attributes = True
```

**Router Implementation Example**:
```python
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError
from backend.database import get_db
from backend.dependencies import get_current_admin
from backend.models.user import User
from backend.models.system_config import SystemConfig
from backend.schemas.system_config import SystemConfigCreate, SystemConfigUpdate, SystemConfigResponse
from backend.services import config_service

router = APIRouter(prefix="/api/system-configs", tags=["system-configs"])

@router.get("", response_model=List[SystemConfigResponse])
async def list_configs(
    category: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin)
):
    """List all configurations"""
    configs = await config_service.get_all_configs(db, category)
    return configs

@router.post("", response_model=SystemConfigResponse)
async def create_config(
    data: SystemConfigCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin)
):
    """Create new configuration"""
    try:
        config = await config_service.set_config(
            db, data.key, data.value, data.value_type, data.description, data.category
        )
        return config
    except IntegrityError:
        raise HTTPException(status_code=400, detail="Configuration key already exists")

@router.delete("/{id}")
async def delete_config(
    id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin)
):
    """Soft delete configuration by setting is_active=False"""
    config = await db.get(SystemConfig, id)
    if not config:
        raise HTTPException(status_code=404, detail="Configuration not found")

    config.is_active = False
    await db.commit()
    return {"message": "Configuration deleted successfully"}
```

**Router Registration** (in `backend/app.py`):
```python
# Add to imports:
from backend.routers import system_configs

# In create_app(), add after other routers:
app.include_router(system_configs.router)
```

#### 4. Migration (`backend/migrations/add_system_configs.py`)

**Purpose**: Create table and initialize default configurations.

**Implementation**:
```python
"""Add system_configs table and initialize default configurations"""
import asyncio
from sqlalchemy import text
from backend.database import async_session

async def migrate():
    async with async_session() as db:
        # Check if table exists
        result = await db.execute(text(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='system_configs'"
        ))
        if result.scalar_one_or_none():
            print("Table system_configs already exists")
            return

        # Create table
        await db.execute(text("""
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
            )
        """))

        # Create indexes
        await db.execute(text(
            "CREATE INDEX idx_system_configs_key ON system_configs(key)"
        ))
        await db.execute(text(
            "CREATE INDEX idx_system_configs_category ON system_configs(category)"
        ))

        # Insert initial configurations
        await db.execute(text("""
            INSERT INTO system_configs (key, value, value_type, description, category)
            VALUES
            ('bocha_api_key', 'sk-66d203942a6c404b89eff2adb494febc', 'string', 'Bocha AI Web Search API Key', 'external_api'),
            ('bocha_api_url', 'https://api.bochaai.com/v1/web-search', 'string', 'Bocha AI Web Search API URL', 'external_api')
        """))

        await db.commit()
        print("Successfully created system_configs table and initialized default configurations")

if __name__ == "__main__":
    asyncio.run(migrate())
```

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

**API Integration** (using centralized `api.js`):
```javascript
async function loadConfigs() {
    const response = await API.get('/api/system-configs');
    renderConfigTable(response);
}

async function saveConfig(data) {
    if (editingId) {
        await API.put(`/api/system-configs/${editingId}`, data);
    } else {
        await API.post('/api/system-configs', data);
    }
}
```

#### Navigation

**Location**: System Management group (after Skills Management)

**Integration**: Add to `frontend/js/components/sidebar.js` navigation configuration:

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
from backend.services import config_service

api_key = await config_service.get_config(context.db, 'bocha_api_key')
api_url = await config_service.get_config(context.db, 'bocha_api_url')
```

**Context Note**: The skill execution context already provides database session access via `context.db` (an `AsyncSession` instance). No changes to `SkillContext` are required.

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

**Test Files**: `test_system_config_service.py`, `test_system_config_router.py`

1. **Model Tests**:
   - Create/read/update/delete operations
   - Unique key constraint
   - Timestamp auto-update

2. **Service Tests**:
   - Type conversion for all supported types (string, integer, float, boolean, json)
   - Default value handling when key not found
   - Category filtering
   - Error handling for invalid type conversions
   - ValueError raised for malformed JSON

3. **Router Tests**:
   - Admin authentication enforcement (401 for non-admin)
   - CRUD endpoint functionality
   - Request validation (Pydantic schema validation)
   - IntegrityError handling for duplicate keys
   - 404 for non-existent configurations

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
- [ ] `backend/schemas/system_config.py` - Pydantic schemas
- [ ] `backend/services/config_service.py` - Service layer
- [ ] `backend/routers/system_configs.py` - API endpoints
- [ ] `backend/migrations/add_system_configs.py` - Database migration
- [ ] `backend/models/__init__.py` - Add SystemConfig import
- [ ] `backend/app.py` - Register router
- [ ] `backend/skills/builtin/web_search_bocha.yaml` - Update to use config_service

### Frontend Files
- [ ] `frontend/js/pages/system-configs.js` - Page implementation
- [ ] `frontend/css/system-configs.css` - Page styles (optional, can reuse existing)
- [ ] `frontend/index.html` - Add script tag: `<script src="/js/pages/system-configs.js"></script>`
- [ ] `frontend/js/components/sidebar.js` - Add navigation item

### Test Files
- [ ] `test_system_config_service.py` - Service layer tests
- [ ] `test_system_config_router.py` - API endpoint tests

### Documentation
- [x] `docs/superpowers/specs/2026-03-15-system-config-module-design.md` - This document

## Conclusion

This design provides a flexible, type-safe configuration management system that meets all stated requirements. The architecture follows DbGuard's existing patterns (SQLAlchemy async, FastAPI routers, vanilla JavaScript frontend) and integrates seamlessly with the skills system. The implementation is straightforward with clear separation of concerns and comprehensive error handling.
