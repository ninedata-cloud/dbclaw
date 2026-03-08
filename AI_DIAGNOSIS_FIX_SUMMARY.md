# AI Guardian 诊断功能修复总结

## 问题
AI Guardian 中异常展开后显示 "AI diagnosis pending..."，没有自动诊断结果。

## 根本原因
异步诊断任务使用了已关闭的数据库会话，导致诊断失败。

## 修复内容

### 1. 后端修复
- **backend/services/anomaly_detector.py**: 修改 `_trigger_proactive_diagnosis()` 方法，让诊断任务创建独立的数据库会话
- **backend/routers/guardian.py**: 新增 `POST /api/guardian/anomalies/{datasource_id}/{anomaly_id}/diagnose` 端点，支持手动触发诊断

### 2. 前端修复
- **frontend/js/pages/guardian-dashboard.js**:
  - 在异常详情弹窗中添加 "Trigger AI Diagnosis" 按钮
  - 实现 `triggerDiagnosis()` 方法调用后端 API

## 使用方法

### 自动诊断
- 系统会自动为 CRITICAL 和 IMPORTANT 级别的数据源触发诊断
- 诊断结果自动保存到数据库

### 手动诊断
1. 在 Guardian Dashboard 中点击异常查看详情
2. 如果显示 "AI diagnosis pending..."，点击 "Trigger AI Diagnosis" 按钮
3. 等待诊断完成（通常 30-120 秒）
4. 刷新查看诊断结果

### 命令行测试
```bash
# 重置卡住的异常
sqlite3 data/smartdba.db "UPDATE anomalies SET status = 'detected' WHERE status = 'diagnosing';"

# 手动触发诊断
python manual_trigger_diagnosis.py [anomaly_id]

# 检查诊断状态
python test_ai_diagnosis_fix.py
```

## 修改的文件
- backend/services/anomaly_detector.py
- backend/routers/guardian.py
- frontend/js/pages/guardian-dashboard.js
- AI_DIAGNOSIS_FIX.md (详细文档)
- test_ai_diagnosis_fix.py (测试脚本)
- manual_trigger_diagnosis.py (手动触发脚本)

## 验证步骤
1. 启动应用
2. 等待异常检测触发
3. 在 Guardian Dashboard 查看异常详情
4. 确认 AI 诊断内容正确显示
5. 或使用手动触发按钮测试
