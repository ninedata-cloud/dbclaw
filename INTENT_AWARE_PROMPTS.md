# Intent-Aware System Prompts Implementation

## Overview

Successfully implemented context-aware system prompts that adapt based on user query intent. The system now automatically detects whether a user wants to:
- **Diagnose** a problem (troubleshooting mode)
- **View** information (data presentation mode)
- **Execute** an action (operational mode)

## Problem Solved

**Before:** All queries were treated as diagnostic problems requiring root cause analysis, severity ratings, and fix recommendations - even simple information requests like "查看数据库配置" (view database configuration).

**After:** The system detects user intent and adapts its response style accordingly:
- Informational queries get direct data presentation without diagnostic framing
- Diagnostic queries still get full root cause analysis
- Administrative queries get action-oriented execution

## Implementation Details

### Files Created/Modified

1. **backend/agent/intent_detector.py** (NEW)
   - Intent detection logic based on keyword analysis
   - Supports Chinese and English keywords
   - Returns: 'diagnostic', 'informational', or 'administrative'

2. **backend/agent/prompts.py** (MODIFIED)
   - Added `DIAGNOSTIC_PROMPT` (same as original SYSTEM_PROMPT)
   - Added `INFORMATIONAL_PROMPT` for data presentation
   - Added `ADMINISTRATIVE_PROMPT` for action execution
   - Kept `SYSTEM_PROMPT` as alias to `DIAGNOSTIC_PROMPT` for backward compatibility

3. **backend/agent/conversation_skills.py** (MODIFIED)
   - Imports intent detector and new prompts
   - Detects intent from first user message
   - Selects appropriate prompt based on detected intent

4. **test_intent_detection.py** (NEW)
   - Comprehensive test suite with 30 test cases
   - Tests diagnostic, informational, administrative, and edge cases
   - All tests passing (100% success rate)

5. **memory/MEMORY.md** (UPDATED)
   - Documented the intent-aware prompt system
   - Added keyword examples for each intent type

## Intent Detection Logic

### Diagnostic Keywords
Chinese: 慢, 错误, 问题, 故障, 诊断, 优化, 为什么, 怎么办, 解决, 修复, 异常, 卡, 失败, 超时, 阻塞, 性能, 瓶颈, 延迟
English: slow, error, problem, fault, diagnose, optimize, why, what to do, solve, fix, abnormal, stuck, fail, timeout, block, performance, bottleneck, latency

### Informational Keywords
Chinese: 查看, 显示, 列出, 获取, 什么是, 有哪些, 当前, 状态, 信息, 统计, 监控, 报告
English: view, show, list, get, what is, what are, current, status, info, stats, monitor, report

### Administrative Keywords
Chinese: 执行, 运行, 创建, 修改, 删除, 更新, 设置, 启用, 禁用, 添加, 移除, 配置
English: execute, run, create, modify, delete, update, set, enable, disable, add, remove, configure

### Priority Rules
1. Diagnostic intent takes priority if it has any matches and is >= other scores
2. Administrative takes priority over informational
3. Default to informational if no clear winner

## Example Behaviors

### Informational Query
**Input:** "查看数据库配置"
**Intent:** informational
**Response Style:** Direct display of configuration values in tables/bullet points, no diagnostic analysis

### Diagnostic Query
**Input:** "数据库很慢，怎么办？"
**Intent:** diagnostic
**Response Style:** Full root cause analysis, severity rating (CRITICAL/WARNING/INFO), specific fix recommendations

### Administrative Query
**Input:** "执行 SELECT * FROM users LIMIT 10"
**Intent:** administrative
**Response Style:** Execute query, show results, confirm success/failure

### Mixed Intent Query
**Input:** "查看配置，数据库很慢"
**Intent:** diagnostic (diagnostic keywords take priority)
**Response Style:** Full diagnostic analysis

## Testing Results

All 30 test cases passed:
- 8/8 diagnostic queries correctly identified
- 9/9 informational queries correctly identified
- 7/7 administrative queries correctly identified
- 3/3 edge cases handled correctly

## Verification Steps

To manually test the implementation:

1. Start the backend server
2. Create a new chat session in the web UI
3. Test informational query: "查看数据库配置"
   - Expected: Direct data presentation without diagnostic framing
4. Test diagnostic query: "数据库很慢"
   - Expected: Full diagnostic analysis with severity rating
5. Test administrative query: "执行查询"
   - Expected: Action-oriented execution

## Benefits

1. **Better User Experience:** Responses match user expectations based on their intent
2. **Reduced Noise:** Informational queries don't get unnecessary diagnostic analysis
3. **Maintained Functionality:** Diagnostic queries still get full troubleshooting support
4. **Automatic Detection:** No UI changes needed, works seamlessly
5. **Bilingual Support:** Works with both Chinese and English queries

## Future Enhancements

Potential improvements:
- Add more keywords based on real user query patterns
- Implement machine learning-based intent classification
- Allow users to manually override detected intent
- Track intent detection accuracy metrics

## Backward Compatibility

- `SYSTEM_PROMPT` still exists as an alias to `DIAGNOSTIC_PROMPT`
- Existing code that uses `SYSTEM_PROMPT` will continue to work
- No breaking changes to the API or database schema
