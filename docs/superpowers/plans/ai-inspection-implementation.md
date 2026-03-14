# AI-Driven Inspection Module Implementation Plan

**Spec:** docs/superpowers/specs/ai-inspection-rewrite.md
**Date:** 2026-03-14

## Overview

Rewrite Inspection module to use AI-generated diagnostic reports with autonomous skill selection.

## Implementation Steps

### Step 1: Database Migration
**File:** `backend/migrations/add_ai_inspection_fields.py`

Add fields to Report model:
- `skill_executions` (JSON) - Audit trail of skills called during report generation
- `ai_conversation_id` (Integer, nullable) - Link to diagnostic_session if conversation saved

**Acceptance:**
- Migration script created
- Fields added to Report model in backend/models/report.py
- Migration runs successfully without errors

---

### Step 2: Add Inspection System Prompt
**File:** `backend/agent/prompts.py`

Add `INSPECTION_REPORT_PROMPT` constant with:
- Required sections (Config, Load Metrics, Host Metrics, TOP SQL, Space Usage)
- Iterative analysis instructions
- Skill calling guidance
- Markdown formatting requirements

**Acceptance:**
- INSPECTION_REPORT_PROMPT added to prompts.py
- Prompt includes all required sections
- Prompt instructs AI to call skills iteratively

---

### Step 3: Add Report Mode to Conversation Skills
**File:** `backend/agent/conversation_skills.py`

Create new function `generate_report_with_skills()`:
- Non-streaming version of run_conversation_with_skills()
- Collects all skill executions with timestamps
- Returns tuple: (markdown_content, skill_executions_list)
- Handles timeout (5 minutes max)
- Returns partial results on error

**Acceptance:**
- New function added to conversation_skills.py
- Function returns markdown + skill executions
- Timeout handling works correctly
- Partial results returned on failure

---

### Step 4: Rewrite Report Generator
**File:** `backend/services/report_generator.py`

Replace `ReportGenerator.generate_inspection_report()`:
- Get trigger, datasource, config from database
- Create Report record with status='generating'
- Build context message with datasource info and trigger reason
- Call generate_report_with_skills() with INSPECTION_REPORT_PROMPT
- Save markdown to report.content_md
- Save skill executions to report.skill_executions
- Update status to 'completed' or 'completed_with_errors'
- Handle errors gracefully with partial results

**Acceptance:**
- generate_inspection_report() rewritten to use AI
- Report created with correct status transitions
- Skill executions saved to database
- Error handling returns partial results
- Timeout handling works (5 min max)

---

### Step 5: Remove Old Diagnostic Code
**Files to modify:**
- `backend/services/report_generator.py`
- `backend/services/diagnostic_engine.py` (delete entire file)

Remove:
- `_build_markdown_report()` function
- `_build_html_report()` function
- `_build_inspection_markdown()` function
- Delete `backend/services/diagnostic_engine.py`
- Remove DiagnosticEngine imports from report_generator.py

**Acceptance:**
- diagnostic_engine.py deleted
- Old report building functions removed
- No references to DiagnosticEngine remain
- Code still compiles without errors

---

### Step 6: Update Inspection Service
**File:** `backend/services/inspection_service.py`

Update `_generate_report()` method:
- Ensure it calls the new AI-driven generate_inspection_report()
- No other changes needed (method signature stays same)

**Acceptance:**
- _generate_report() calls new AI method
- Manual and scheduled triggers both work
- No breaking changes to API

---

### Step 7: Testing
**Manual tests to perform:**

1. **Manual Trigger Test:**
   - Call POST `/api/inspections/trigger/{datasource_id}`
   - Verify report generated with AI
   - Check skill_executions field populated
   - Verify all required sections present

2. **Scheduled Inspection Test:**
   - Wait for or trigger scheduled inspection
   - Verify AI report generated
   - Check status transitions correctly

3. **Error Handling Test:**
   - Simulate AI failure (invalid API key)
   - Verify partial results saved
   - Check error_message field populated

4. **Timeout Test:**
   - Mock slow AI response
   - Verify timeout after 5 minutes
   - Check partial results returned

**Acceptance:**
- All manual tests pass
- Reports display correctly in frontend
- No errors in backend logs
- Skill executions audit trail visible

---

## Critical Files

**Modified:**
- backend/models/report.py
- backend/agent/prompts.py
- backend/agent/conversation_skills.py
- backend/services/report_generator.py
- backend/services/inspection_service.py

**Deleted:**
- backend/services/diagnostic_engine.py

**Unchanged:**
- backend/routers/inspections.py
- backend/models/inspection_config.py
- backend/models/inspection_trigger.py
- All frontend files

## Rollback Plan

If implementation fails:
1. Revert migration (remove new fields)
2. Restore diagnostic_engine.py from git
3. Restore old report_generator.py functions
4. Remove INSPECTION_REPORT_PROMPT
5. Remove generate_report_with_skills() function

## Success Criteria

- ✅ AI generates reports with all 5 required sections
- ✅ AI iteratively calls skills based on findings
- ✅ skill_executions field contains audit trail
- ✅ Manual triggers work correctly
- ✅ Scheduled inspections work correctly
- ✅ Error handling shows partial results
- ✅ Timeout handling works (5 min max)
- ✅ Frontend displays reports without changes
- ✅ No DiagnosticEngine code remains
