# Scheduler Initialization and Encryption Fix

## Problem 1: Scheduler Initialization

When updating scheduled report configurations, the application crashed with:

```
AttributeError: 'NoneType' object has no attribute 'get_job'
```

### Root Cause

The `scheduled_report_service` in `backend/routers/scheduled_reports.py` was initialized at module load time:

```python
from backend.services.metric_collector import scheduler
scheduled_report_service = ScheduledReportService(scheduler)
```

However, the `scheduler` object is `None` until `start_scheduler()` is called during app startup in `app.py`. This created a race condition where the router module loaded before the scheduler was initialized.

### Solution

Implemented lazy initialization pattern for the scheduled report service:

1. Changed the global service instance to `_scheduled_report_service = None`
2. Created a `get_scheduled_report_service()` function that:
   - Checks if the service is already initialized
   - Validates that the scheduler is available
   - Creates the service instance on first use
3. Updated all 5 usages in the router to call `get_scheduled_report_service()`

## Problem 2: API Key Decryption Failure

When triggering scheduled reports with AI analysis, the application crashed with:

```
cryptography.fernet.InvalidToken
```

### Root Cause

The `backend/routers/ai_models.py` was using its own encryption key:

```python
ENCRYPTION_KEY = os.getenv("ENCRYPTION_KEY")
cipher = Fernet(ENCRYPTION_KEY.encode())
```

This was different from the centralized encryption utility in `backend/utils/encryption.py` which uses `encryption_key` from settings. When API keys were encrypted with one key and decrypted with another, it caused `InvalidToken` errors.

### Solution

Refactored `ai_models.py` to use the centralized encryption utility:

```python
from backend.utils.encryption import encrypt_value, decrypt_value

def encrypt_api_key(api_key: str) -> str:
    return encrypt_value(api_key)

def decrypt_api_key(encrypted: str) -> str:
    return decrypt_value(encrypted)
```

This ensures all encryption/decryption uses the same key from `backend.config.get_settings().encryption_key`.

## Files Modified

- `backend/routers/scheduled_reports.py`: Implemented lazy initialization pattern
- `backend/routers/ai_models.py`: Switched to centralized encryption utility

## Testing

The fixes ensure that:
- The scheduler is fully initialized before the service tries to use it
- Clear error message if scheduler is not available
- All scheduled report operations work correctly after app startup
- API keys are encrypted/decrypted consistently across the application
- Scheduled reports with AI analysis can decrypt API keys successfully
