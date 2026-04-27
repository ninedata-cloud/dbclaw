# 告警通知时区问题修复

## 问题描述

告警消息发送到飞书、钉钉、企业微信等 IM 平台时，显示的"触发时间"比实际时间少 8 小时。

**原因**：数据库中存储的 `created_at`、`resolved_at` 等时间字段为 UTC 时间，但在格式化为字符串发送通知时，直接使用 `strftime()` 格式化，没有转换为本地时区（北京时间 UTC+8）。

## 修复内容

### 1. 新增时区转换工具函数

在 `backend/utils/datetime_helper.py` 中新增：

- `to_local_time(dt, tz_offset_hours=8)`: 将 UTC 时间转换为本地时间
- `format_local_datetime(dt, fmt="%Y-%m-%d %H:%M:%S", tz_offset_hours=8)`: 格式化 UTC 时间为本地时间字符串

### 2. 修复通知服务时间格式化

修改以下文件中的时间格式化逻辑：

#### `backend/services/notification_dispatcher.py`

- `_build_active_alert_payload()`: 告警触发时间格式化
- `_build_recovery_alert_payload()`: 告警恢复时间格式化

#### `backend/services/notification_service.py`

- `_build_feishu_payload()`: 飞书通知卡片时间格式化
- `_build_dingtalk_payload()`: 钉钉通知时间格式化
- `_send_email()`: 邮件通知时间格式化

### 3. 测试验证

新增测试文件 `tests/test_datetime_timezone.py`，验证：

- UTC 转本地时间功能
- 时间格式化功能
- 无时区信息的 datetime 处理
- None 值处理

## 影响范围

- 飞书通知
- 钉钉通知
- 企业微信通知
- 邮件通知
- SMS 通知
- Webhook 通知
- 所有通过 Integration 系统发送的告警通知

## 验证方法

1. 触发一个告警
2. 查看飞书/钉钉/企业微信中的通知消息
3. 确认"触发时间"显示为北京时间（与服务器本地时间一致）

## 注意事项

- 默认时区为 UTC+8（北京时间）
- 如需支持其他时区，可通过 `tz_offset_hours` 参数调整
- 数据库中的时间字段仍然存储为 UTC 时间（不变）
- 仅在展示层（通知消息）进行时区转换

## 相关文件

- `backend/utils/datetime_helper.py`
- `backend/services/notification_dispatcher.py`
- `backend/services/notification_service.py`
- `tests/test_datetime_timezone.py`
