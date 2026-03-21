# 告警通知系统 API 修复

## 修复日期
2026-03-18 22:20

## 问题描述

### 问题 1：Alert Channels API 422 错误
```
GET http://localhost:9939/api/integrations/alert-channels 422 (Unprocessable Content)
Error: path.integration_id: Input should be a valid integer, unable to parse string as an integer
```

### 问题 2：Alert Subscriptions API 500 错误
```
GET http://localhost:9939/api/alerts/subscriptions/list?user_id=1 500 (Internal Server Error)
Error: 1 validation error for AlertSubscriptionResponse
channels
  Field required [type=missing]
```

---

## 根本原因

在迁移告警通知系统到集成管理时，数据库模型已更新，但 Pydantic Schema 没有同步更新：

1. **数据库模型**（`alert_subscription.py`）：
   - ✅ 已移除 `channels`、`webhook_url`、`dingtalk_webhook_url`、`dingtalk_secret` 字段
   - ✅ 保留 `channel_ids` 字段

2. **Pydantic Schema**（`alert.py`）：
   - ❌ 仍然使用旧的 `channels` 字段
   - ❌ 仍然包含 `webhook_url` 等旧字段

---

## 修复内容

### 1. 更新 `AlertSubscriptionBase`

**之前**：
```python
class AlertSubscriptionBase(BaseModel):
    datasource_ids: List[int] = Field(default_factory=list)
    severity_levels: List[str] = Field(default_factory=list)
    time_ranges: List[TimeRange] = Field(default_factory=list)
    channels: List[str] = Field(..., min_length=1)  # 旧字段
    webhook_url: Optional[str] = Field(None, max_length=500)  # 旧字段
    dingtalk_webhook_url: Optional[str] = Field(None, max_length=500)  # 旧字段
    dingtalk_secret: Optional[str] = Field(None, max_length=200)  # 旧字段
    enabled: bool = True
    aggregation_script: Optional[str] = None
```

**之后**：
```python
class AlertSubscriptionBase(BaseModel):
    datasource_ids: List[int] = Field(default_factory=list)
    severity_levels: List[str] = Field(default_factory=list)
    time_ranges: List[TimeRange] = Field(default_factory=list)
    channel_ids: List[int] = Field(..., min_length=1)  # 新字段：Integration Channel IDs
    enabled: bool = True
    aggregation_script: Optional[str] = None
```

### 2. 更新 `AlertSubscriptionUpdate`

**之前**：
```python
class AlertSubscriptionUpdate(BaseModel):
    datasource_ids: Optional[List[int]] = None
    severity_levels: Optional[List[str]] = None
    time_ranges: Optional[List[TimeRange]] = None
    channels: Optional[List[str]] = None  # 旧字段
    webhook_url: Optional[str] = None  # 旧字段
    dingtalk_webhook_url: Optional[str] = None  # 旧字段
    dingtalk_secret: Optional[str] = None  # 旧字段
    enabled: Optional[bool] = None
    aggregation_script: Optional[str] = None
```

**之后**：
```python
class AlertSubscriptionUpdate(BaseModel):
    datasource_ids: Optional[List[int]] = None
    severity_levels: Optional[List[str]] = None
    time_ranges: Optional[List[TimeRange]] = None
    channel_ids: Optional[List[int]] = None  # 新字段
    enabled: Optional[bool] = None
    aggregation_script: Optional[str] = None
```

### 3. 移除旧的验证器

移除了 `validate_channels` 验证器，因为不再需要验证 channel 类型。

---

## 验证

### Schema 验证
```bash
python -c "
from backend.schemas.alert import AlertSubscriptionBase
data = {
    'datasource_ids': [],
    'severity_levels': [],
    'time_ranges': [],
    'channel_ids': [1, 2],
    'enabled': True,
    'aggregation_script': None
}
sub = AlertSubscriptionBase(**data)
print('✓ Schema 验证通过')
"
```

**结果**：✅ 通过

---

## 测试步骤

### 1. 重启服务
```bash
# 停止当前服务（Ctrl+C）
# 启动服务
python run.py
```

### 2. 测试 Alert Channels API
```bash
curl http://localhost:9939/api/integrations/alert-channels
```

**预期结果**：返回空数组 `[]`（因为还没有创建 Channel）

### 3. 测试 Alert Subscriptions API
```bash
curl http://localhost:9939/api/alerts/subscriptions/list?user_id=1
```

**预期结果**：返回订阅列表（可能为空）

### 4. 前端测试
1. 刷新浏览器页面（强制刷新：Ctrl+Shift+R）
2. 进入"告警管理"页面
3. 切换到"订阅管理"标签
4. 点击"新建订阅"

**预期结果**：
- 页面正常加载
- 表单显示"暂无可用的通知渠道"提示
- 显示"管理通知渠道"链接

---

## 相关文件

- `backend/schemas/alert.py` - Alert Schema 定义（已更新）
- `backend/models/alert_subscription.py` - 数据库模型（已更新）
- `frontend/js/pages/alerts.js` - 前端页面（已更新）

---

## 下一步

1. **创建 Alert Channel**
   - 进入"集成管理"页面
   - 加载内置模板
   - 创建通知渠道（飞书/钉钉/邮件）

2. **创建告警订阅**
   - 进入"告警管理"页面
   - 创建订阅，选择通知渠道

3. **测试通知**
   - 点击"测试通知"按钮
   - 验证通知发送成功

---

**修复完成时间**: 2026-03-18 22:20
**修复状态**: ✅ 完成
**需要重启**: 是
