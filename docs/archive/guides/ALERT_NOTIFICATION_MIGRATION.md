# 告警通知系统迁移到集成管理

## 迁移日期
2026-03-18

## 迁移概述

将告警通知系统从旧的独立通知服务完全迁移到外部集成管理系统，实现统一的通知渠道管理。

---

## 一、迁移内容

### 1. 后端变更

#### 1.1 notification_dispatcher.py
- **移除**：旧通知系统的兼容代码
- **新增**：`_send_recovery_via_integrations()` 函数，通过 Integration 系统发送恢复通知
- **变更**：所有告警通知和恢复通知都通过 Integration 系统发送

#### 1.2 数据库模型
- **移除字段**（alert_subscriptions 表）：
  - `channels` - 旧的通知渠道列表
  - `webhook_url` - 旧的 Webhook URL
  - `dingtalk_webhook_url` - 旧的钉钉 Webhook URL
  - `dingtalk_secret` - 旧的钉钉签名密钥
- **保留字段**：
  - `channel_ids` - Integration 系统的通道 ID 列表

#### 1.3 数据库迁移
- 脚本：`backend/migrations/remove_legacy_notification_fields.py`
- 状态：✅ 已执行成功

### 2. 前端变更

#### 2.1 告警订阅表单
- **移除**：旧的通知渠道选择器（email、sms、phone、webhook）
- **移除**：Webhook URL 输入框
- **新增**：Integration Channel 选择器
- **新增**：加载 Alert Channels 的 API 调用
- **新增**："管理通知渠道"链接，跳转到集成管理页面

#### 2.2 订阅列表显示
- **变更**：显示 Integration Channel 名称而不是旧的 channels

---

## 二、使用指南

### 1. 配置通知渠道

在使用告警订阅之前，需要先在"集成管理"页面配置通知渠道：

1. 进入"集成管理"页面
2. 加载内置模板（如果还没有）
3. 创建 Alert Channel：
   - 选择集成类型（飞书 Webhook、钉钉 Webhook、邮件、通用 Webhook）
   - 配置参数（Webhook URL、邮件地址等）
   - 启用通道

### 2. 创建告警订阅

1. 进入"告警管理"页面
2. 切换到"订阅管理"标签
3. 点击"新建订阅"
4. 配置订阅：
   - 选择数据源（留空表示全部）
   - 选择严重程度（留空表示全部）
   - **选择通知渠道**（从已配置的 Integration Channels 中选择）
   - 启用订阅
5. 保存

### 3. 测试通知

在订阅列表中，点击"测试通知"按钮，系统会发送一条测试通知到选定的渠道。

---

## 三、支持的通知类型

### 1. 告警通知

当告警触发时，系统会通过选定的 Integration Channels 发送通知，包含：
- 告警标题
- 告警内容
- 严重程度
- 数据源信息
- 触发时间

### 2. 恢复通知

当告警恢复时，系统会自动发送恢复通知，包含：
- 告警标题（标记为"已恢复"）
- 告警内容
- 告警时间
- 恢复时间

---

## 四、内置集成模板

系统提供以下内置通知集成：

### 1. 飞书 Webhook 通知
- **集成 ID**: `builtin_feishu_webhook`
- **类型**: outbound_notification
- **参数**:
  - `webhook_url`: 飞书机器人 Webhook 地址
  - `secret`: 签名密钥（可选）

### 2. 钉钉 Webhook 通知
- **集成 ID**: `builtin_dingtalk_webhook`
- **类型**: outbound_notification
- **参数**:
  - `webhook_url`: 钉钉机器人 Webhook 地址
  - `secret`: 签名密钥（必填）

### 3. 邮件通知
- **集成 ID**: `builtin_email`
- **类型**: outbound_notification
- **参数**:
  - `to`: 收件人邮箱地址（多个用逗号分隔）
  - `cc`: 抄送邮箱地址（可选）
- **系统配置**（需要在系统配置中设置）:
  - `smtp_host`: SMTP 服务器地址
  - `smtp_port`: SMTP 端口
  - `smtp_username`: SMTP 用户名
  - `smtp_password`: SMTP 密码
  - `smtp_from_email`: 发件人邮箱
  - `smtp_use_tls`: 是否使用 TLS

### 4. 通用 Webhook 通知
- **集成 ID**: `builtin_generic_webhook`
- **类型**: outbound_notification
- **参数**:
  - `webhook_url`: 目标 Webhook 地址
  - `method`: HTTP 方法（POST/PUT）
  - `auth_type`: 认证方式（none/bearer/basic）
  - `auth_token`: 认证 Token（可选）

---

## 五、通知 Payload 格式

### 告警通知 Payload

```json
{
  "title": "【CRITICAL】数据库名称 告警",
  "content": "告警详细信息",
  "severity": "critical",
  "datasource_name": "数据库名称",
  "alert_id": 123,
  "timestamp": "2026-03-18T14:00:00Z"
}
```

### 恢复通知 Payload

```json
{
  "title": "【已恢复】数据库名称 告警已恢复",
  "content": "告警详细信息\n\n告警时间：2026-03-18T14:00:00Z\n恢复时间：2026-03-18T14:30:00Z",
  "severity": "info",
  "datasource_name": "数据库名称",
  "alert_id": 123,
  "timestamp": "2026-03-18T14:30:00Z",
  "status": "resolved"
}
```

---

## 六、执行日志

所有通知的执行情况都会记录在以下表中：

### 1. integration_execution_logs
- 记录 Integration 的执行情况
- 包含执行时间、状态、结果、错误信息

### 2. alert_delivery_logs
- 记录告警投递情况
- 包含告警 ID、订阅 ID、通道、收件人、状态

---

## 七、故障排查

### 1. 订阅表单中没有可用的通知渠道

**原因**：还没有配置 Alert Channel

**解决**：
1. 进入"集成管理"页面
2. 加载内置模板
3. 创建 Alert Channel

### 2. 通知发送失败

**检查步骤**：
1. 查看 `integration_execution_logs` 表，检查错误信息
2. 查看 `alert_delivery_logs` 表，检查投递状态
3. 检查 Integration Channel 是否启用
4. 检查 Integration 是否启用
5. 检查参数配置是否正确（Webhook URL、邮件配置等）

### 3. 邮件通知发送失败

**检查步骤**：
1. 确认系统配置中的 SMTP 参数是否正确
2. 检查 SMTP 服务器是否可访问
3. 检查用户名和密码是否正确
4. 检查端口和 TLS 设置是否匹配

---

## 八、迁移后的优势

### 1. 统一管理
- 所有通知渠道在"集成管理"中统一配置和管理
- 支持多个相同类型的通知渠道（如多个飞书群、多个邮箱）

### 2. 可扩展性
- 可以轻松添加新的通知类型（Slack、企业微信、短信等）
- 通过编写 Integration 代码即可实现

### 3. 可复用性
- Integration Channel 可以在多个订阅中复用
- 修改通道配置后，所有使用该通道的订阅都会生效

### 4. 可追溯性
- 完整的执行日志
- 可以查看每次通知的发送情况和结果

### 5. 灵活性
- 支持自定义 Integration 代码
- 可以实现复杂的通知逻辑（如条件判断、数据转换等）

---

## 九、相关文件

### 后端
- `backend/services/notification_dispatcher.py` - 通知分发器（已更新）
- `backend/models/alert_subscription.py` - 订阅模型（已更新）
- `backend/migrations/remove_legacy_notification_fields.py` - 数据库迁移脚本

### 前端
- `frontend/js/pages/alerts.js` - 告警管理页面（已更新）

### 集成模板
- `backend/utils/integration_templates.py` - 内置集成模板

---

## 十、测试清单

- [x] 数据库迁移成功
- [ ] 创建 Alert Channel
- [ ] 创建告警订阅
- [ ] 触发告警，验证通知发送
- [ ] 告警恢复，验证恢复通知发送
- [ ] 测试飞书 Webhook 通知
- [ ] 测试钉钉 Webhook 通知
- [ ] 测试邮件通知
- [ ] 测试通用 Webhook 通知
- [ ] 查看执行日志

---

**迁移完成时间**: 2026-03-18 22:10
**迁移状态**: ✅ 完成
**建议**: 需要重启服务以加载新的代码
