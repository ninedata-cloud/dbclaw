# AI Guardian 诊断功能修复

## 问题描述

在 AI Guardian 系统中，展开异常（anomalies）详情时，AI 诊断信息显示为 "AI diagnosis pending..."，没有自动生成诊断结果。

检查数据库发现：
- 有多个异常状态为 `diagnosing`（诊断中）
- 但 `ai_diagnosis` 字段为空
- 说明诊断任务启动了但没有完成

## 根本原因

**数据库会话冲突问题**

在 `backend/services/anomaly_detector.py` 中，当检测到异常后会使用 `asyncio.create_task()` 异步触发 AI 诊断：

```python
asyncio.create_task(self._trigger_proactive_diagnosis(db, anomaly.id, auto_fix))
```

问题在于：
1. 传递的 `db` 会话对象来自 `metric_collector.py` 的 `collect_metrics_for_connection()` 函数
2. 该会话在指标采集完成后会被 commit 并关闭
3. 异步诊断任务尝试使用已关闭的会话时失败
4. 导致 `anomaly.ai_diagnosis` 字段始终为空

## 修复方案

### 1. 修复异常检测器的会话管理

**文件**: `backend/services/anomaly_detector.py`

**修改内容**:
- 不再将 `db` 会话传递给异步诊断任务
- 在 `_trigger_proactive_diagnosis()` 方法内部创建新的数据库会话
- 确保诊断任务使用独立的会话，避免冲突

```python
# 修改前
asyncio.create_task(self._trigger_proactive_diagnosis(
    db, anomaly.id, importance.auto_fix_enabled
))

# 修改后
asyncio.create_task(self._trigger_proactive_diagnosis(
    anomaly.id, importance.auto_fix_enabled
))

# _trigger_proactive_diagnosis 方法内部创建新会话
async with async_session() as db:
    result = await self._proactive_diagnosis_service.diagnose_anomaly(
        db, anomaly_id, auto_fix
    )
```

### 2. 添加手动触发诊断 API

**文件**: `backend/routers/guardian.py`

**新增端点**: `POST /api/guardian/anomalies/{datasource_id}/{anomaly_id}/diagnose`

功能：
- 允许用户手动触发 AI 诊断
- 验证异常存在性
- 调用 `ProactiveDiagnosisService` 执行诊断
- 返回诊断结果

### 3. 前端添加手动触发按钮

**文件**: `frontend/js/pages/guardian-dashboard.js`

**修改内容**:
- 在异常详情弹窗中，当 `ai_diagnosis` 为空时显示"Trigger AI Diagnosis"按钮
- 添加 `triggerDiagnosis()` 方法调用后端 API
- 诊断完成后自动刷新显示结果

## 修复效果

### 自动诊断
- 当检测到 CRITICAL 或 IMPORTANT 级别的异常时，自动触发 AI 诊断
- 诊断任务使用独立的数据库会话，不会因会话冲突而失败
- 诊断结果自动保存到 `anomaly.ai_diagnosis` 字段

### 手动诊断
- 用户可以在异常详情页面手动触发诊断
- 适用于自动诊断失败或需要重新诊断的场景
- 提供即时反馈和结果展示

## 测试建议

1. **自动诊断测试**:
   - 创建一个 CRITICAL 或 IMPORTANT 级别的数据源
   - 等待指标采集触发异常检测
   - 检查日志确认诊断任务被触发
   - 在 Guardian Dashboard 中查看异常详情，确认 AI 诊断内容显示

2. **手动诊断测试**:
   - 在 Guardian Dashboard 中找到一个没有 AI 诊断的异常
   - 点击"Trigger AI Diagnosis"按钮
   - 等待诊断完成
   - 确认诊断结果正确显示

3. **日志检查**:
   ```bash
   # 查看诊断相关日志
   tail -f logs/smartdba.log | grep -E "Proactive diagnosis|diagnose_anomaly"
   ```

## 相关文件

- `backend/services/anomaly_detector.py` - 异常检测器（已修复）
- `backend/services/proactive_diagnosis.py` - 主动诊断服务
- `backend/routers/guardian.py` - Guardian API 路由（新增端点）
- `frontend/js/pages/guardian-dashboard.js` - Guardian 前端页面（新增按钮）

## 注意事项

1. **异步任务执行时间**: AI 诊断可能需要 30-120 秒，取决于需要调用的技能数量
2. **并发控制**: 当前没有限制并发诊断任���数量，高负载时可能需要添加队列机制
3. **错误处理**: 诊断失败时会记录日志，但不会影响指标采集流程
4. **会话管理**: 确保所有异步任务都使用独立的数据库会话

## 修复验证

### 重置卡住的异常

如果有异常状态卡在 `diagnosing`，可以运行：

```bash
sqlite3 data/smartdba.db "UPDATE anomalies SET status = 'detected' WHERE status = 'diagnosing';"
```

### 手动触发诊断测试

使用提供的测试脚本：

```bash
# 测试最新的未诊断异常
python manual_trigger_diagnosis.py

# 测试指定的异常 ID
python manual_trigger_diagnosis.py 194
```

### 检查诊断结果

```bash
# 查看最近的异常及诊断状态
sqlite3 data/smartdba.db "SELECT id, datasource_id, severity, status,
  LENGTH(ai_diagnosis) as diagnosis_length,
  LENGTH(root_cause) as root_cause_length
FROM anomalies ORDER BY detected_at DESC LIMIT 10;"
```

## 已知问题和解决方案

### 问题 1: 异常状态卡在 diagnosing

**原因**: 诊断任务异常退出，没有恢复状态

**解决方案**:
- 已在 `proactive_diagnosis.py` 第 136-149 行添加异常恢复逻辑
- 如果诊断失败，会自动将状态恢复为 `detected`

### 问题 2: 数据库会话已关闭

**原因**: 异步任务使用了父函数的数据库会话

**解决方案**:
- 修改 `anomaly_detector.py`，让诊断任务创建自己的会话
- 使用 `async with async_session() as db:` 确保会话独立

### 问题 3: 诊断任务超时

**原因**: AI 诊断可能需要较长时间（调用多个技能）

**解决方案**:
- 在 `proactive_diagnosis.py` 第 25 行设置了 120 秒超时
- 可以根据需要调整 `self.diagnosis_timeout`

## 后续优化建议

1. **添加诊断任务队列**，避免并发过多
2. **在前端实时显示诊断进度**（使用 WebSocket）
3. **添加诊断历史记录**，支持查看历史诊断结果
4. **优化诊断提示词**，提高诊断质量
5. **添加诊断超时重试机制**
6. **记录诊断失败原因**到数据库，便于排查问题
7. **添加诊断任务监控**，及时发现卡住的任务
