# AI-Driven Inspection Module Rewrite

**Date:** 2026-03-14
**Status:** Design Phase
**Author:** AI Assistant

## Overview

Complete rewrite of the Inspection module to use AI-generated diagnostic reports where the AI agent autonomously selects and invokes skills to gather information.

## Requirements

Based on user input and clarifying questions:

1. **Report Format:** Hybrid approach - Required sections + AI can add additional analysis
2. **Skill Selection:** Iterative approach - AI starts with basic skills, then decides additional skills based on findings
3. **Fallback:** Remove rule-based DiagnosticEngine completely - AI-only approach
4. **Error Handling:** Show partial results if generation fails

## Current State

### Existing Components
- `InspectionConfig` - Configuration with threshold rules and scheduling
- `InspectionTrigger` - Audit trail of inspection events
- `InspectionService` - Scheduler that triggers inspections
- `ReportGenerator` - Generates reports by directly calling database connectors
- `DiagnosticEngine` - Rule-based analysis (to be removed)

### Current Flow
```
InspectionService → ReportGenerator → Database Connectors → DiagnosticEngine → Markdown Report
```

### Problems
- Rule-based approach lacks intelligence
- Fixed analysis patterns
- No adaptive skill selection
- Duplicate code with conversation system

## Proposed Architecture

### New Flow
```
InspectionService → AI Report Generator → AI Agent → Skills System → Markdown Report
```

### Core Design Decisions

**1. Reuse Conversation Infrastructure**
- Leverage existing `conversation_skills.py`
- Add inspection-specific system prompt
- Use existing skill selection and execution

**2. Iterative Skill Execution**
- AI starts with basic skills (status, variables, connections)
- Analyzes results to identify issues
- Calls additional skills as needed (slow queries, locks, replication)
- Builds report incrementally

**3. Structured Output**
- System prompt enforces required sections
- AI adds additional analysis beyond required sections
- Markdown format for consistency

## Detailed Design

### 1. System Prompt

**File:** `backend/agent/prompts.py`

Add new constant:
```python
INSPECTION_REPORT_PROMPT = """
You are a database inspection specialist generating a comprehensive diagnostic report.

REQUIRED SECTIONS (must include):
1. Database Configuration - version, uptime, key parameters
2. Database Load Metrics - QPS, TPS, connections, cache hit rate
3. Host Load Metrics - CPU, memory, disk usage
4. TOP SQL - slowest queries with execution times
5. Space Usage - largest tables and their sizes

ITERATIVE ANALYSIS APPROACH:
1. Start by calling basic skills: get_db_status, get_db_variables, get_connections
2. Analyze the results to identify issues or areas needing deeper investigation
3. Call additional skills as needed (slow queries, locks, replication, etc.)
4. Generate findings and recommendations based on all collected data

ADDITIONAL ANALYSIS (add as needed):
- Performance bottlenecks
- Configuration issues
- Resource constraints
- Optimization opportunities

Use markdown format. Be concise but thorough.
"""
```

### 2. Report Model Updates

**File:** `backend/models/report.py`

Add fields:
```python
skill_executions = Column(JSON, default=list)  # Audit trail of skills called
ai_conversation_id = Column(Integer, nullable=True)  # Link to diagnostic_session
```

**Migration:** `backend/migrations/add_ai_inspection_fields.py`

### 3. AI Report Generator

**File:** `backend/services/report_generator.py`

Replace `generate_inspection_report()` method:

```python
async def generate_ai_inspection_report(self, trigger_id: int) -> int:
    """Generate AI-driven inspection report"""
    # 1. Get trigger, datasource, config
    # 2. Create report record (status='generating')
    # 3. Build context message with datasource info
    # 4. Call AI agent with INSPECTION_REPORT_PROMPT
    # 5. Collect markdown output and skill executions
    # 6. Save to report (status='completed')
    # 7. Handle errors → partial results
```

Key implementation details:
- Use `conversation_skills.chat()` with report_mode=True
- Pass datasource context (name, type, host, trigger reason)
- Collect all skill execution results for audit
- Timeout after 5 minutes → save partial results
- On error → save collected data with error message

### 4. Conversation Skills Integration

**File:** `backend/agent/conversation_skills.py`

Add `report_mode` parameter to `chat()`:
- When True, return complete markdown instead of streaming
- Collect skill execution audit trail
- Return tuple: (markdown_content, skill_executions)

### 5. Files to Remove

- `backend/services/diagnostic_engine.py` - Rule-based logic
- `_build_markdown_report()` function in report_generator.py
- `_build_html_report()` function in report_generator.py
- HTML template rendering (keep template file for future use)

### 6. Files to Modify

**backend/services/report_generator.py:**
- Remove old `generate_inspection_report()` implementation
- Add new `generate_ai_inspection_report()` method
- Remove `_build_inspection_markdown()` method
- Keep `ReportGenerator` class structure

**backend/services/inspection_service.py:**
- Update `_generate_report()` to call new AI method
- No other changes needed

**backend/agent/prompts.py:**
- Add `INSPECTION_REPORT_PROMPT`

**backend/agent/conversation_skills.py:**
- Add `report_mode` parameter support
- Return markdown + skill executions when in report mode

**backend/models/report.py:**
- Add `skill_executions` JSON field
- Add `ai_conversation_id` Integer field

### 7. Files Unchanged

- `backend/routers/inspections.py` - API stays same
- `backend/models/inspection_config.py`
- `backend/models/inspection_trigger.py`
- All frontend files

## Implementation Steps

1. Add migration for Report model fields
2. Add INSPECTION_REPORT_PROMPT to prompts.py
3. Modify conversation_skills.py for report_mode
4. Rewrite ReportGenerator.generate_inspection_report()
5. Remove DiagnosticEngine and old functions
6. Test manual trigger endpoint
7. Test scheduled inspections
8. Verify error handling and partial results

## Error Handling

### Partial Results Strategy

When AI generation fails or times out:
1. Save all skill execution results collected so far
2. Generate minimal markdown from skill results
3. Add note: "⚠️ Report generation incomplete - showing partial results"
4. Set status to 'completed_with_errors'
5. Store error in report.error_message

### Timeout Handling

- Max generation time: 5 minutes
- If timeout, save partial report
- Include all skill results in skill_executions field
- User can see what was analyzed

## Testing Strategy

1. **Manual Trigger Test:** Call `/api/inspections/trigger/{datasource_id}` and verify AI report
2. **Scheduled Test:** Wait for scheduled inspection, verify it uses AI
3. **Error Test:** Simulate AI failure, verify partial results saved
4. **Timeout Test:** Mock slow AI response, verify timeout handling
5. **Skill Audit:** Verify skill_executions field contains all called skills

## Success Criteria

- ✅ AI generates reports with all required sections
- ✅ AI iteratively selects skills based on findings
- ✅ No rule-based code remains (DiagnosticEngine removed)
- ✅ Partial results shown on failure
- ✅ Skill execution audit trail saved
- ✅ Manual and scheduled triggers both work
- ✅ Frontend displays AI-generated reports correctly

## Risks and Mitigations

**Risk:** AI generation takes too long
**Mitigation:** 5-minute timeout with partial results

**Risk:** AI doesn't follow required sections
**Mitigation:** Strong system prompt enforcement, validate output structure

**Risk:** Skill selection is inefficient
**Mitigation:** Monitor skill_executions, optimize prompt if needed

**Risk:** Higher cost due to AI calls
**Mitigation:** Acceptable tradeoff for better analysis quality

## Future Enhancements

- Save AI conversation to diagnostic_session for review
- Add user feedback on report quality
- Fine-tune system prompt based on feedback
- Add report templates for different database types
- Support custom sections in InspectionConfig
