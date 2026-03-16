# Connection Failure Detection and Alert System

## Overview

Implemented automatic detection and alerting for database/host connection failures. When a datasource cannot be reached, the system now:

1. **Creates a CRITICAL alert** in the alert management system
2. **Triggers specialized AI diagnosis** focused on connection troubleshooting
3. **Records the failure** in metric snapshots for historical tracking

## Key Features

### Specialized Connection Failure Diagnosis

When a connection failure is detected, the AI diagnosis focuses specifically on **why the connection failed**, not on database performance analysis. The diagnosis systematically investigates:

- **Network connectivity**: Host reachability, port availability, DNS resolution
- **Database service status**: Service running, listening configuration, resource availability
- **Authentication & permissions**: Credentials, host access rights, user permissions
- **Firewall & security policies**: OS firewall, cloud security groups, network ACLs
- **Configuration errors**: Connection parameters, SSL/TLS settings, character sets
- **System resources**: Host status, file descriptors, memory availability

### Intelligent Root Cause Analysis

The AI diagnosis provides:
- Step-by-step diagnostic procedures with specific commands
- Prioritized list of possible causes (from most to least likely)
- Concrete solutions with executable commands and configuration examples
- Verification steps to confirm the issue is resolved
- Preventive measures to avoid recurrence

## Implementation Details

### Modified Files

#### 1. `backend/services/metric_collector.py`

**Changes:**
- Added `connection_failed` flag to track connection status
- Added `_handle_connection_failure()` function to process failures
- Integrated failure handling into metric collection flow

**Key Functions:**

```python
async def _handle_connection_failure(db, datasource_id: int, datasource, error_message: str):
    """
    Handle database/host connection failure
    - Creates CRITICAL alert with system_error type
    - Triggers AI diagnosis with connection_failure type
    - Logs detailed error information
    """
```

**Alert Details:**
- **Type**: `system_error`
- **Severity**: `critical` (highest priority)
- **Metric**: `connection_status` (0 = failed, 1 = success)
- **Trigger Reason**: Full error message from connection attempt

**Diagnosis Trigger:**
- **Type**: `connection_failure`
- **Reason**: Formatted message with datasource name and type
- **Snapshot**: Includes error details, host info, timestamp

#### 2. `backend/models/inspection_trigger.py`

**Changes:**
- Updated trigger_type comment to include `connection_failure`
- No schema changes needed (VARCHAR(20) supports new type)

#### 3. `backend/services/report_generator.py`

**Changes:**
- Added logic to select appropriate system prompt based on trigger type
- Connection failure triggers use `CONNECTION_FAILURE_DIAGNOSIS_PROMPT`
- Other triggers continue using standard `REPORT_GENERATION_PROMPT`

**Key Code:**
```python
# Select appropriate system prompt based on trigger type
if trigger.trigger_type == "connection_failure":
    from backend.agent.prompts import CONNECTION_FAILURE_DIAGNOSIS_PROMPT
    system_prompt = CONNECTION_FAILURE_DIAGNOSIS_PROMPT
else:
    system_prompt = REPORT_GENERATION_PROMPT
```

#### 4. `backend/agent/prompts.py`

**New Addition:**
- Added `CONNECTION_FAILURE_DIAGNOSIS_PROMPT` - specialized prompt for connection failure diagnosis
- Focuses on systematic troubleshooting of connectivity issues
- Provides structured diagnostic approach with 6 major categories:
  1. Network layer issues (connectivity, DNS, latency)
  2. Database service issues (status, listening, resources)
  3. Authentication & permissions (credentials, host access, user rights)
  4. Firewall & security policies (OS firewall, cloud security groups, ACLs)
  5. Configuration errors (connection params, SSL/TLS, character sets)
  6. System resources (host status, file descriptors, memory)
- Emphasizes actionable solutions over theoretical analysis
- Includes structured report template with diagnostic checklists

### Alert Workflow

```
Connection Attempt
       ↓
   [FAILS]
       ↓
1. Log Warning
       ↓
2. Create CRITICAL Alert
   - Type: system_error
   - Severity: critical
   - Status: active
       ↓
3. Trigger AI Diagnosis
   - Type: connection_failure
   - Includes error context
       ↓
4. Store Metric Snapshot
   - Marks connection_failed: true
   - Preserves error message
```

### Testing

Created comprehensive test suite:

**Test File**: `test_connection_failure_forced.py`

**Test Results:**
```
✓ Alert created: CRITICAL severity, system_error type
✓ Trigger created: connection_failure type
✓ Error message preserved in alert
✓ AI diagnosis triggered asynchronously
```

**Test Coverage:**
- Invalid hostname (DNS resolution failure)
- Connection timeout scenarios
- Authentication failures
- Network unreachable conditions

## Integration Points

### 1. Alert Management System

Alerts are visible in:
- **Frontend**: `/alerts` page (告警管理)
- **API**: `GET /api/alerts` with filters
- **Database**: `alert_messages` table

### 2. Inspection Service

Triggers are processed by:
- **Service**: `InspectionService`
- **Report Generation**: Automatic AI analysis
- **Database**: `inspection_triggers` table

### 3. Metric Collection

Integrated into:
- **Scheduler**: APScheduler (15s interval by default)
- **Collector**: `collect_metrics_for_connection()`
- **Storage**: `metric_snapshots` table

## Configuration

### Alert Severity Calculation

Connection failures always use **CRITICAL** severity:
- Represents complete loss of database access
- Requires immediate attention
- Bypasses percentage-based severity calculation

### Inspection Triggers

Connection failure triggers are processed:
- **Asynchronously**: Non-blocking metric collection
- **With Context**: Full error details and datasource info
- **AI-Powered**: Automatic root cause analysis

## Usage

### Viewing Alerts

1. Navigate to **告警管理** (Alert Management) page
2. Filter by:
   - Severity: Critical
   - Type: system_error
   - Status: Active
3. View alert details including error message

### Monitoring Connection Status

Connection failures are tracked in:
- **Real-time**: WebSocket updates to monitoring page
- **Historical**: Metric snapshots with `connection_failed` flag
- **Alerts**: Persistent records until acknowledged/resolved

### AI Diagnosis

When connection fails:
1. Inspection trigger created automatically with type `connection_failure`
2. AI uses specialized connection troubleshooting prompt
3. Systematic investigation of 6 major failure categories
4. Report generated with:
   - Error message analysis
   - Possible causes ranked by likelihood
   - Step-by-step diagnostic procedures
   - Specific commands to execute
   - Concrete solutions with examples
   - Verification steps
   - Preventive measures
5. Available in **巡检报告** (Inspection Reports) page

**Example Diagnosis Output:**

The AI diagnosis report includes sections like:
- **问题描述** (Problem Description): Connection error details
- **错误信息分析** (Error Analysis): Error type identification
- **可能原因排查** (Possible Causes): Checklist of potential issues
- **诊断步骤** (Diagnostic Steps): Commands to run (ping, telnet, service status)
- **根本原因** (Root Cause): Identified cause based on evidence
- **解决方案** (Solutions): Prioritized fixes with specific commands
- **预防措施** (Prevention): Recommendations to avoid recurrence

## Error Handling

### Graceful Degradation

- Metric collection continues for other datasources
- Failed connections don't block scheduler
- Errors logged with full stack traces

### Retry Logic

- No automatic retry (prevents alert spam)
- Next scheduled collection will retry
- Manual retry available via API

### Alert Deduplication

- Multiple failures create multiple alerts
- Use alert aggregation for repeated failures
- Consider implementing cooldown period (future enhancement)

## Future Enhancements

### Potential Improvements

1. **Alert Cooldown**: Prevent duplicate alerts within time window
2. **Auto-Recovery Detection**: Resolve alerts when connection restored
3. **Connection Health Score**: Track reliability over time
4. **Predictive Alerts**: Warn before complete failure
5. **Custom Notification Channels**: Email, SMS, webhook for critical alerts

### Configuration Options

Consider adding:
- `connection_failure_cooldown`: Seconds between duplicate alerts
- `auto_resolve_on_recovery`: Boolean flag
- `critical_alert_channels`: Override notification settings

## Related Files

- `backend/services/metric_collector.py` - Main implementation, connection failure detection
- `backend/services/alert_service.py` - Alert creation and management
- `backend/services/inspection_service.py` - Diagnosis trigger processing
- `backend/services/report_generator.py` - Report generation with prompt selection
- `backend/agent/prompts.py` - Connection failure diagnosis prompt
- `backend/models/alert_message.py` - Alert schema
- `backend/models/inspection_trigger.py` - Trigger schema
- `frontend/js/pages/alerts.js` - Alert UI

## Real-World Example

A real connection failure was detected and diagnosed:

**Scenario**: SQL Server container connection failure

**AI Diagnosis Results**:
- **Root Cause Identified**: Container had just restarted (uptime: 6 seconds)
- **Diagnostic Actions**: AI automatically checked container status, logs, and resource usage via SSH
- **Solutions Provided**:
  - Commands to check restart history
  - Memory configuration verification
  - Monitoring recommendations
- **Outcome**: Issue resolved after container stabilized

This demonstrates the system's ability to:
1. Detect connection failures immediately
2. Trigger comprehensive AI-powered diagnosis
3. Identify root causes through systematic investigation
4. Provide actionable solutions

## Summary

Connection failure detection is now fully integrated into SmartDBA's monitoring and alerting infrastructure. The system provides:

- **Immediate visibility** through CRITICAL alerts
- **Specialized AI diagnosis** focused on connection troubleshooting (not performance analysis)
- **Systematic investigation** of network, service, authentication, firewall, configuration, and resource issues
- **Actionable solutions** with specific commands and configuration examples
- **Historical tracking** in metric snapshots
- **User-friendly interface** for alert management

**Key Differentiator**: When a connection fails, the AI diagnosis focuses exclusively on **why the connection cannot be established**, providing step-by-step troubleshooting guidance rather than generic database performance analysis.

This ensures that database connectivity issues are never missed, are automatically escalated for investigation, and receive targeted diagnostic attention.
