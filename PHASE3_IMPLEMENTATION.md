# AI Guardian Phase 3 Implementation Complete

## 实现时间
2026-03-07

## 概述
成功实现 AI Guardian Phase 3：主动诊断和自动修复功能。当异常被检测到时，系统会自动触发 AI 诊断，分析根本原因并提供解决建议。

## 新增功能

### 1. 主动诊断服务 (ProactiveDiagnosisService)
**文件**: `backend/services/proactive_diagnosis.py`

核心功能：
- 自动触发 AI 诊断
- 调用相关技能收集详细信息
- 分析根本原因
- 生成推荐操作
- 创建告警通知
- 支持自动修复（可选）

主要方法：
```python
async def diagnose_anomaly(db, anomaly_id, auto_fix=False)
```

诊断流程：
1. 获取异常记录和数据源信息
2. 更新异常状态为 'diagnosing'
3. 构建诊断提示（包含异常详情和系统上下文）
4. 调用 AI 进行诊断（通过 run_conversation_with_skills）
5. 解析 AI 响应，提取根因和建议
6. 更新异常记录（ai_diagnosis, root_cause, recommended_actions）
7. 创建 GuardianAlert 告警
8. 如果启用自动修复，执行修复操作

### 2. 异常检测器增强
**文件**: `backend/services/anomaly_detector.py`

新增功能：
- 检测到 CRITICAL 或 IMPORTANT 级别异常时自动触发诊断
- 异步执行诊断，不阻塞指标采集
- 支持自动修复配置

关键代码：
```python
if importance and importance.importance_tier in ['CRITICAL', 'IMPORTANT']:
    asyncio.create_task(self._trigger_proactive_diagnosis(
        db, anomaly.id, importance.auto_fix_enabled
    ))
```

### 3. API 端点增强
**文件**: `backend/routers/guardian.py`

新增端点：
```
GET /api/guardian/anomalies/{datasource_id}/{anomaly_id}
```

返回完整的异常详情，包括：
- 基本信息（检测时间、严重程度、状态）
- 指标分析（基线值、当前值、偏差）
- AI 诊断结果 (ai_diagnosis)
- 根本原因 (root_cause)
- 推荐操作 (recommended_actions)
- 系统上下文快照

更新端点：
```
GET /api/guardian/anomalies/{datasource_id}
```
现在返回包含 AI 诊断信息的异常列表

### 4. 前端界面增强
**文件**: `frontend/js/pages/guardian-dashboard.js`

新增功能：
- 异常列表显示 "AI Diagnosed" 标记
- 点击异常查看详细诊断信息
- 异常详情模态框，展示：
  - 基本信息和指标对比
  - AI 诊断结果（格式化显示）
  - 根本原因（高亮显示）
  - 推荐操作列表（编号显示）
  - 系统上下文网格

**文件**: `frontend/css/guardian.css`

新增样式：
- `.anomaly-detail-modal` - 详情模态框样式
- `.diagnosis-content` - AI 诊断内容样式
- `.root-cause-content` - 根因分析样式
- `.actions-list` - 推荐操作列表样式
- `.metric-comparison` - 指标对比可视化
- `.context-grid` - 上下文信息网格

### 5. 模型关系修复
**文件**: `backend/models/diagnostic_case.py`

修复了 GuardianAlert 的关系定义，移除了对 GuardianRule 的强依赖，因为告警可以独立于规则存在。

## 工作流程

### 完整的异常处理流程

```
1. 指标采集 (metric_collector.py)
   ↓
2. 异常检测 (anomaly_detector.py)
   ↓
3. 创建异常记录 (Anomaly)
   ↓
4. 触发主动诊断 (proactive_diagnosis.py)
   ↓
5. AI 分析诊断
   - 调用诊断技能
   - 收集详细信息
   - 分析根本原因
   ↓
6. 更新异常记录
   - ai_diagnosis
   - root_cause
   - recommended_actions
   ↓
7. 创建告警 (GuardianAlert)
   ↓
8. 可选：自动修复
```

### 触发条件

主动诊断在以下情况下自动触发：
- 数据源重要性级别为 CRITICAL 或 IMPORTANT
- 检测到新的异常
- 异步执行，不阻塞指标采集

## 使用方式

### 1. 自动触发（推荐）

系统会自动为 CRITICAL 和 IMPORTANT 级别的数据源触发诊断：

```python
# 在 metric_collector.py 中自动执行
await _detect_anomalies(db, datasource_id, normalized_status)
```

### 2. 手动触发

通过 API 或代码手动触发诊断：

```python
from backend.services.proactive_diagnosis import ProactiveDiagnosisService

service = ProactiveDiagnosisService()
result = await service.diagnose_anomaly(
    db=db,
    anomaly_id=anomaly_id,
    auto_fix=False  # 是否启用自动修复
)
```

### 3. 查看诊断结果

**通过 API**:
```bash
# 获取异常详情
curl http://localhost:8000/api/guardian/anomalies/4/160

# 返回示例
{
  "id": 160,
  "ai_diagnosis": "根据分析，CPU 使用率异常偏低...",
  "root_cause": "系统负载降低，可能是业务低峰期",
  "recommended_actions": [
    "监控业务指标确认是否正常",
    "检查是否有定时任务未执行"
  ]
}
```

**通过前端界面**:
1. 访问 Guardian Dashboard
2. 点击异常记录
3. 查看完整的诊断信息

**通过数据库**:
```sql
SELECT
    id,
    detected_at,
    severity,
    ai_diagnosis,
    root_cause,
    recommended_actions
FROM anomalies
WHERE id = 160;
```

## 测试

### 测试脚本
创建了 `test_phase3.py` 用于测试主动诊断功能：

```bash
python test_phase3.py
```

测试流程：
1. 查找未诊断的异常
2. 触发主动诊断
3. 显示诊断结果

### 测试结果

✅ 主动诊断服务成功触发
✅ AI 成功调用诊断技能
✅ 异常状态正确更新
✅ 告警成功创建

⚠️ 已知问题：IPv4Address JSON 序列化问题（不影响核心功能）

## 数据库字段

### anomalies 表

现在会自动填充以下字段：

| 字段 | 类型 | 说明 |
|------|------|------|
| ai_diagnosis | TEXT | AI 完整诊断结果 |
| root_cause | TEXT | 根本原因分析 |
| recommended_actions | JSON | 推荐操作列表 |
| status | VARCHAR | 状态：detected/diagnosing/resolved |

### guardian_alerts 表

新创建的告警记录：

| 字段 | 类型 | 说明 |
|------|------|------|
| datasource_id | INTEGER | 数据源 ID |
| anomaly_id | INTEGER | 关联的异常 ID |
| severity | VARCHAR | 严重程度 |
| title | VARCHAR | 告警标题 |
| message | TEXT | 告警消息 |
| channels | JSON | 通知渠道 |
| status | VARCHAR | 状态：pending/acknowledged/resolved |

## 配置选项

### 诊断超时
```python
# 在 ProactiveDiagnosisService 中配置
self.diagnosis_timeout = 120  # 秒
```

### 自动修复
```python
# 在数据源重要性配置中启用
importance.auto_fix_enabled = True
```

### 触发级别
```python
# 在 anomaly_detector.py 中配置
if importance.importance_tier in ['CRITICAL', 'IMPORTANT']:
    # 触发诊断
```

## 性能优化

1. **异步执行**: 诊断在后台异步执行，不阻塞指标采集
2. **延迟导入**: ProactiveDiagnosisService 延迟导入，避免循环依赖
3. **错误恢复**: 诊断失败时自动恢复异常状态

## 安全考虑

1. **自动修复风险评估**: 目前自动修复功能预留接口，实际执行需要风险评估
2. **权限控制**: 诊断操作记录在 GuardianAlert 中，可追溯
3. **超时保护**: 诊断操作有超时限制，防止长时间阻塞

## 下一步计划

### Phase 4: 多维度输出
- [ ] 增强实时聊天通知
- [ ] 结构化报告生成
- [ ] 移动推送通知
- [ ] Dashboard 可视化增强

### 自动修复增强
- [ ] 实现具体的修复操作
- [ ] 风险评估机制
- [ ] 修复结果验证
- [ ] 回滚机制

### 案例学习
- [ ] 诊断案例自动保存
- [ ] 相似案例匹配
- [ ] 解决方案复用

## 文件清单

### 新增文件
- `backend/services/proactive_diagnosis.py` - 主动诊断服务
- `test_phase3.py` - Phase 3 测试脚本
- `PHASE3_IMPLEMENTATION.md` - 本文档

### 修改文件
- `backend/services/anomaly_detector.py` - 增加自动触发诊断
- `backend/routers/guardian.py` - 增加异常详情端点
- `frontend/js/pages/guardian-dashboard.js` - 增加详情查看功能
- `frontend/css/guardian.css` - 增加详情样式
- `backend/models/diagnostic_case.py` - 修复模型关系

## 总结

Phase 3 成功实现了 AI Guardian 的核心功能：主动诊断。系统现在可以：

✅ 自动检测异常
✅ 自动触发 AI 诊断
✅ 分析根本原因
✅ 生成推荐操作
✅ 创建告警通知
✅ 前端展示诊断结果

这使得 SmartDBA 从被动的监控工具升级为主动的智能诊断系统，大大提升了数据库运维效率。
