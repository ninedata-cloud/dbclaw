# Alert Aggregation System Implementation Summary

## Overview

Successfully implemented a comprehensive alert aggregation system that groups related alerts into events, reducing noise and improving alert management.

## Implementation Completed

### 1. Database Schema ✓

**New Table: `alert_events`**
- Stores aggregated alert events with metadata
- Tracks event start/end times, alert count, status, severity
- Supports two aggregation strategies: by metric_name or by alert_type
- Includes proper indexes for performance

**Modified Table: `alert_messages`**
- Added `event_id` foreign key column
- Links individual alerts to their parent event

**Migration**: `backend/migrations/add_alert_events.py`
- Creates tables and indexes
- Performs retroactive aggregation of existing alerts
- Successfully processed 136 existing alerts into 11 events

### 2. Backend Models ✓

**New Model**: `backend/models/alert_event.py`
- AlertEvent model with relationships to Datasource and AlertMessage
- Proper SQLAlchemy configuration with lazy loading

**Updated Models**:
- `backend/models/alert_message.py`: Added event_id field and relationship
- `backend/models/datasource.py`: Added alert_events relationship
- `backend/models/__init__.py`: Registered new models

### 3. Service Layer ✓

**New Service**: `backend/services/alert_event_service.py`

Key methods:
- `process_new_alert()`: Core aggregation logic with dynamic time window
- `get_events()`: Query events with filters (datasource, status, severity, time range, search)
- `get_alerts_in_event()`: Retrieve all alerts in an event
- `acknowledge_event()`: Acknowledge event and all its alerts
- `resolve_event()`: Resolve event and all its alerts

**Aggregation Algorithm**:
1. Calculate aggregation key (prefer metric_name, fallback to alert_type)
2. Find recent events within time window (default 5 minutes)
3. If found and gap < threshold: add to existing event
4. Otherwise: create new event
5. Update event metadata (count, end time, status, severity)

**Updated Service**: `backend/services/alert_service.py`
- Integrated event processing into `create_alert()` method
- Automatically processes new alerts into events

### 4. API Endpoints ✓

**New Endpoints** (in `backend/routers/alerts.py`):
- `GET /api/alerts/events`: List aggregated events with filters
- `GET /api/alerts/events/{event_id}/alerts`: Get all alerts in an event
- `POST /api/alerts/events/{event_id}/acknowledge`: Acknowledge event
- `POST /api/alerts/events/{event_id}/resolve`: Resolve event

**Route Ordering**: Event routes placed before `/{alert_id}` to avoid conflicts

### 5. Schemas ✓

**New Schemas** (in `backend/schemas/alert.py`):
- `AlertEventBase`: Base event fields
- `AlertEventResponse`: Event response with ID and timestamps
- `AlertEventQueryParams`: Query parameters for filtering events
- `AlertEventAcknowledgeRequest`: Request body for acknowledgment

### 6. Configuration ✓

**New Setting** (in `backend/config.py`):
- `alert_aggregation_time_window_minutes`: Configurable time window (default 5 minutes)
- Exported as module-level constant for easy access

### 7. Frontend ✓

**Updated**: `frontend/js/pages/alerts.js`

New features:
- View toggle: Switch between "事件视图" (Events View) and "告警视图" (Alerts View)
- Event list with expand/collapse functionality
- Nested alerts table showing individual alerts within an event
- Event-level acknowledge and resolve actions
- Automatic filter synchronization for both views

New methods:
- `loadEvents()`: Fetch aggregated events
- `loadEventAlerts(eventId)`: Fetch alerts for specific event
- `renderEventsList()`: Render events table with expansion
- `toggleEventExpansion(eventId)`: Expand/collapse event details
- `acknowledgeEvent(eventId)`: Acknowledge event via API
- `resolveEvent(eventId)`: Resolve event via API
- `switchViewMode(mode)`: Toggle between views

**Updated**: `frontend/css/alerts.css`

New styles:
- `.view-toggle`: View mode toggle buttons
- `.events-table`: Event table styling
- `.event-row`: Expandable event rows
- `.expanded-row`: Expanded state styling
- `.event-alerts-container`: Nested alerts container
- `.nested-alerts-table`: Nested alerts table
- `.count-badge`: Alert count badge
- `.btn-icon`: Icon button styling
- `.expand-icon`: Expand/collapse icon with rotation

## Key Features

### Dynamic Time Window
- Configurable via environment variable `ALERT_AGGREGATION_TIME_WINDOW_MINUTES`
- Default: 5 minutes
- Alerts within the time window are grouped into the same event

### Intelligent Aggregation
- **Primary strategy**: Group by `datasource_id + metric_name` (fine-grained)
- **Fallback strategy**: Group by `datasource_id + alert_type` (coarse-grained)
- Automatically selects the best strategy based on available data

### Status Inheritance
- Event status reflects the latest alert's status
- Acknowledging/resolving an event updates all associated alerts
- Severity tracks the highest severity across all alerts

### Backward Compatibility
- Existing `/api/alerts` endpoints unchanged
- Frontend provides view toggle for seamless transition
- No breaking changes to existing functionality

## Testing Results

### Migration
```
✓ Created alert_events table with indexes
✓ Added event_id column to alert_messages
✓ Processed 136 existing alerts into 11 events
```

### API Endpoints
```
✓ GET /api/alerts/events - Returns aggregated events
✓ GET /api/alerts/events/{id}/alerts - Returns alerts in event
✓ POST /api/alerts/events/{id}/acknowledge - Acknowledges event
✓ POST /api/alerts/events/{id}/resolve - Resolves event
```

### Event Aggregation
- Successfully groups alerts by metric_name
- Respects time window configuration
- Properly inherits status and severity
- Maintains accurate alert counts

## Performance Considerations

1. **Indexing**: All critical query fields indexed
   - `datasource_id`, `aggregation_key`, `status`, `event_start_time`, `event_end_time`

2. **Caching**: Frontend caches expanded event alerts

3. **Pagination**: Both events and nested alerts support pagination

4. **Query Optimization**: SQLAlchemy eager loading for related datasources

## Configuration

Add to `.env` file:
```
ALERT_AGGREGATION_TIME_WINDOW_MINUTES=5
```

## Usage

### Backend
```python
# Alerts are automatically processed into events
alert = await AlertService.create_alert(
    db=db,
    datasource_id=1,
    alert_type="threshold_violation",
    severity="high",
    metric_name="cpu_usage",
    metric_value=85.0,
    threshold_value=80.0
)
# Alert is automatically linked to an event
```

### Frontend
1. Navigate to "告警管理" (Alert Management)
2. Use view toggle to switch between:
   - "事件视图" (Events View): Aggregated events
   - "告警视图" (Alerts View): Individual alerts
3. Click expand icon (▶) to view alerts within an event
4. Use ✓ to acknowledge or ✓✓ to resolve events

## Future Enhancements

1. **Custom Aggregation Rules**: Per-datasource aggregation strategies
2. **Cross-Datasource Correlation**: Detect related alerts across datasources
3. **Alert Patterns**: ML-based pattern detection for recurring issues
4. **Event Timeline**: Visual timeline showing alert frequency
5. **Notification Aggregation**: Send aggregated notifications instead of per-alert

## Files Modified/Created

### Backend
- ✓ `backend/migrations/add_alert_events.py` (new)
- ✓ `backend/models/alert_event.py` (new)
- ✓ `backend/models/alert_message.py` (modified)
- ✓ `backend/models/datasource.py` (modified)
- ✓ `backend/models/__init__.py` (modified)
- ✓ `backend/services/alert_event_service.py` (new)
- ✓ `backend/services/alert_service.py` (modified)
- ✓ `backend/schemas/alert.py` (modified)
- ✓ `backend/routers/alerts.py` (modified)
- ✓ `backend/config.py` (modified)

### Frontend
- ✓ `frontend/js/pages/alerts.js` (modified)
- ✓ `frontend/css/alerts.css` (modified)

## Conclusion

The alert aggregation system is fully implemented and operational. It successfully reduces alert noise by grouping related alerts into events, provides a clean UI for managing aggregated events, and maintains full backward compatibility with existing functionality.
