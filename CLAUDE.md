# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

SmartDBA is an AI-powered database operations platform that provides intelligent diagnostics, proactive monitoring, and automated maintenance for multiple database types (MySQL, PostgreSQL, Oracle, SQL Server, DM, MongoDB, Redis).

**Architecture**: FastAPI backend + vanilla JavaScript frontend + SQLite metadata storage + ChromaDB vector store

## Development Commands

### Running the Application

```bash
# Start the backend server (with auto-reload in debug mode)
python run.py

# The server runs on http://0.0.0.0:8000 by default
# Frontend is served from /frontend directory
```

### Testing

```bash
# Run individual test files
python test_skills.py
python test_intent_detection.py
python test_extended_validation.py

# Run specific test scripts
python test_diagnosis_decision.py
python test_enhanced_report.py
```

### Database Migrations

```bash
# Migrations run automatically on startup via backend/app.py lifespan
# Manual migration scripts are in backend/migrations/

# Example: Add new fields
python backend/migrations/add_diagnosis_decision_fields.py
```

### Environment Setup

```bash
# Copy example environment file
cp .env.example .env

# Generate encryption key for database passwords
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

# Set required environment variables in .env:
# - ENCRYPTION_KEY (for encrypting database credentials)
# - OPENAI_API_KEY (for AI features)
# - OPENAI_BASE_URL (optional, defaults to OpenAI)
# - OPENAI_MODEL (optional, defaults to gpt-4o)
```

## Architecture Overview

### Backend Structure

**Core Application Flow**:
1. `run.py` → `backend/app.py` → Creates FastAPI app with lifespan management
2. Lifespan startup: Initializes database, starts metric collector, KB processor, AI Guardian, scheduled reports
3. Routers handle API endpoints, services contain business logic, models define database schema

**Key Architectural Patterns**:

- **Skills System** (`backend/skills/`): Dynamic, extensible diagnostic skill execution framework
  - Skills defined in YAML (`backend/skills/builtin/*.yaml`)
  - Registry → Validator → Executor → Context pipeline
  - Sandboxed execution with permission controls
  - Skills automatically become AI agent tools

- **Intent-Aware AI** (`backend/agent/`): System prompts adapt based on user query intent
  - `intent_detector.py`: Detects diagnostic/informational/administrative intent
  - `prompts.py`: Three prompt variants (DIAGNOSTIC_PROMPT, INFORMATIONAL_PROMPT, ADMINISTRATIVE_PROMPT)
  - `conversation_skills.py`: Orchestrates AI conversations with skill selection

- **AI Guardian System** (`backend/services/`): Proactive anomaly detection and diagnosis
  - `baseline_learner.py`: Learns normal metric patterns
  - `importance_classifier.py`: Classifies anomaly severity (Critical/High/Medium/Low)
  - `proactive_diagnosis.py`: Auto-triggers AI diagnosis for important anomalies
  - Runs as background tasks started in app lifespan

- **Scheduled Reports** (`backend/services/scheduled_report_service.py`):
  - APScheduler-based report generation
  - Supports daily/weekly/monthly schedules
  - AI-powered report analysis and summarization

### Database Schema

**SQLite with SQLAlchemy async**: `data/smartdba.db`

**Key tables**:
- `datasources`: Database connections (encrypted credentials)
- `ssh_hosts`: SSH connection info for OS metrics
- `metric_snapshots`: Time-series performance metrics
- `diagnostic_sessions`: AI chat history
- `skills`: Dynamic skill definitions (JSON columns for metadata)
- `skill_executions`: Audit trail of skill runs
- `baselines`, `anomalies`, `importance_levels`: AI Guardian data
- `scheduled_reports`: Report configurations and history
- `knowledge_bases`: Vector store metadata

**Important**: Use JSON columns with SQLite LIKE patterns for array filtering (e.g., `tags LIKE '%"mysql"%'` for tag contains)

### Frontend Structure

**Vanilla JavaScript SPA** (`frontend/`):
- `index.html`: Main entry point with navigation
- `js/pages/`: Page-specific logic (diagnosis.js, guardian-dashboard.js, reports.js, etc.)
- `js/components/`: Reusable components (chat-widget.js, query-editor.js)
- `js/api.js`: Centralized API client
- `css/`: Page-specific styles
- `lib/`: Third-party libraries (CodeMirror, marked, highlight.js)

**No build step required** - all files served statically

## Skills System

The Skills System is the core extensibility mechanism. When adding database diagnostic capabilities:

1. **Create skill YAML** in `backend/skills/builtin/` with:
   - Unique ID, name, version, category, tags
   - Parameter definitions with type validation
   - Required permissions (execute_query, execute_command, read_logs, etc.)
   - Python async code using context API

2. **Context API** available in skills:
   ```python
   await context.get_connection(connection_id)
   await context.execute_query(query, connection_id)
   await context.execute_command(command, connection_id)
   await context.search_kb(query, kb_ids, top_k=5)
   await context.get_metrics(connection_id, minutes=60)
   await context.call_skill(skill_id, params)
   ```

3. **Security**: Skills are validated for forbidden imports/builtins and run in sandboxed environment with timeout limits (default 30s, max 300s)

4. **Testing**: Skills auto-load on startup. Test via `/api/skills/{skill_id}/test` endpoint or through AI agent

## AI Agent Integration

**Conversation Flow**:
1. User message → `backend/routers/chat.py`
2. Intent detection → Select appropriate system prompt
3. Context building → Gather relevant datasource info, metrics, KB results
4. Skill selection → AI chooses from available skills based on query
5. Skill execution → Run selected skills with parameters
6. Response generation → AI synthesizes results

**Key files**:
- `backend/agent/conversation_skills.py`: Main conversation orchestration
- `backend/agent/skill_selector.py`: Dynamic skill-to-tool conversion
- `backend/agent/context_builder.py`: Builds context for AI
- `backend/agent/tools.py`: Legacy tool definitions (being phased out)

## Database Connection Handling

**Multi-database support** via `backend/utils/db_connector.py`:
- Detects database type from connection string
- Returns appropriate async driver (aiomysql, asyncpg, oracledb, pymssql, dmPython, motor, redis)
- Handles connection pooling and error handling
- SSH tunneling support via `backend/utils/ssh_executor.py`

**Adding new database type**:
1. Add detection logic in `db_connector.py`
2. Install required async driver
3. Create database-specific skills in `backend/skills/builtin/`
4. Update frontend datasource form if needed

## Common Patterns

### Adding a New API Endpoint

1. Create router in `backend/routers/` or add to existing router
2. Define Pydantic schemas in `backend/schemas/`
3. Create/update models in `backend/models/`
4. Implement business logic in `backend/services/`
5. Register router in `backend/app.py` create_app()

### Adding a New Background Task

Add to `backend/app.py` lifespan startup:
```python
asyncio.create_task(your_background_function())
```

### Working with Encrypted Credentials

Use `backend/utils/encryption.py`:
```python
from backend.utils.encryption import encrypt_password, decrypt_password
encrypted = encrypt_password(plain_password)
plain = decrypt_password(encrypted)
```

### Parameter Validation in Skills

Skills support extended validation:
- `min`/`max`: Range validation for integers
- `pattern`: Regex validation for strings
- `enum`: Allowed values list
- `items`: Type validation for array elements

## Important Notes

- **Async everywhere**: All database operations use async/await
- **Session management**: Use `get_db()` dependency for database sessions
- **Error handling**: Services should raise HTTPException with appropriate status codes
- **Logging**: Use Python logging module, configured in app.py lifespan
- **Security**: Database passwords encrypted with Fernet, JWT for authentication
- **WebSocket**: Real-time metrics via `/ws/monitor` endpoint

## Configuration

All settings in `backend/config.py` loaded from `.env`:
- Database URL (SQLite by default)
- OpenAI API configuration
- Metric collection interval (default 15s)
- JWT secret and expiration
- ChromaDB and embedding model settings

## Troubleshooting

**Skills not loading**: Check `backend/skills/builtin/` YAML syntax and validation errors in logs

**AI Guardian not detecting anomalies**: Ensure metric_collector is running and baseline_learner has collected enough data (needs historical metrics)

**Frontend not loading**: Check that static file mounts in `app.py` match directory structure

**Database connection fails**: Verify encryption key is set and credentials are properly encrypted

**Tests failing**: Ensure test database is initialized and all dependencies are installed
