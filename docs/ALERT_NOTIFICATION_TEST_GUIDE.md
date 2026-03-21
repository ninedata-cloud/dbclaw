# 告警通知系统测试指南

## 修复内容

### 问题
前端 `alerts.js` 文件存在语法错误，导致告警管理页面无法打开。

### 修复
1. 移除了重复的旧代码片段
2. 添加了 `alertChannels` 数组初始化
3. 语法检查通过

---

## 测试步骤

### 1. 重启服务

```bash
# 停止当前服务（如果正在运行）
# Ctrl+C

# 启动服务
python run.py
```

### 2. 配置通知渠道

#### 2.1 进入集成管理页面
1. 登录系统
2. 点击左侧菜单"集成管理"

#### 2.2 加载内置模板（如果还没有）
1. 点击"加载内置模板"按钮
2. 确认加载成功

#### 2.3 创建告警通道

**选项 A：飞书 Webhook**
1. 点击"阿里云 RDS 监控数据采集"旁边的"创建通道"按钮
2. 或者找到"飞书 Webhook 通知"，点击"创建通道"
3. 填写：
   - 通道名称：如"运维群通知"
   - Webhook URL：你的飞书机器人 Webhook 地址
   - 签名密钥：可选
4. 启用通道
5. 保存

**选项 B：钉钉 Webhook**
1. 找到"钉钉 Webhook 通知"，点击"创建通道"
2. 填写：
   - 通道名称：如"告警通知群"
   - Webhook URL：你的钉钉机器人 Webhook 地址
   - 签名密钥：必填
3. 启用通道
4. 保存

**选项 C：邮件通知**
1. 先在"系统配置"中配置 SMTP 参数：
   - smtp_host
   - smtp_port
   - smtp_username
   - smtp_password
   - smtp_from_email
   - smtp_use_tls
2. 找到"邮件通知"，点击"创建通道"
3. 填写：
   - 通道名称：如"管理员邮件"
   - 收件人：邮箱地址（多个用逗号分隔）
   - 抄送：可选
4. 启用通道
5. 保存

### 3. 创建告警订阅

#### 3.1 进入告警管理页面
1. 点击左侧菜单"告警管理"
2. 切换到"订阅管理"标签

#### 3.2 创建订阅
1. 点击"新建订阅"按钮
2. 配置订阅：
   - **数据源**：选择要监控的数据源（留空表示全部）
   - **严重程度**：选择要接收的告警级别（留空表示全部）
   - **通知渠道**：勾选刚才创建的通道
   - **启用订阅**：勾选
3. 点击"保存"

### 4. 测试通知

#### 4.1 测试订阅
1. 在订阅列表中，找到刚创建的订阅
2. 点击"测试通知"按钮（信封图标）
3. 确认发送
4. 检查通知渠道是否收到测试消息

#### 4.2 触发真实告警
1. 在"巡检管理"中配置一个阈值规则
2. 等待巡检触发告警
3. 检查是否收到告警通知

### 5. 验证恢复通知

1. 等待告警条件恢复正常
2. 系统会自动发送恢复通知
3. 检查是否收到恢复通知

---

## 验证清单

- [ ] 告警管理页面可以正常打开
- [ ] 可以加载告警通道列表
- [ ] 订阅表单显示正常
- [ ] 可以选择通知渠道
- [ ] 可以创建订阅
- [ ] 订阅列表显示通道名称
- [ ] 测试通知功能正常
- [ ] 告警通知发送成功
- [ ] 恢复通知发送成功
- [ ] 执行日志记录正常

---

## 故障排查

### 问题 1：告警管理页面打开报错

**检查**：
```bash
# 检查浏览器控制台错误
# 按 F12 打开开发者工具，查看 Console 标签
```

**解决**：
- 清除浏览器缓存
- 强制刷新页面（Ctrl+Shift+R 或 Cmd+Shift+R）

### 问题 2：订阅表单中没有可用的通知渠道

**原因**：还没有创建 Alert Channel

**解决**：
1. 点击"管理通知渠道"链接
2. 在集成管理页面创建 Alert Channel

### 问题 3：测试通知发送失败

**检查**：
1. 查看浏览器控制台错误
2. 查看后端日志
3. 检查 Integration Channel 是否启用
4. 检查 Integration 是否启用
5. 检查参数配置是否正确

**数据库查询**：
```sql
-- 查看执行日志
SELECT * FROM integration_execution_logs
ORDER BY executed_at DESC
LIMIT 10;

-- 查看投递日志
SELECT * FROM alert_delivery_logs
ORDER BY sent_at DESC
LIMIT 10;
```

### 问题 4：邮件通知发送失败

**检查**：
1. 确认系统配置中的 SMTP 参数
2. 测试 SMTP 连接：
```bash
python backend/services/test_send_email.py
```

---

## 数据库查询

### 查看订阅配置
```sql
SELECT
    id,
    user_id,
    datasource_ids,
    severity_levels,
    channel_ids,
    enabled,
    created_at
FROM alert_subscriptions
ORDER BY created_at DESC;
```

### 查看告警通道
```sql
SELECT
    id,
    name,
    integration_id,
    enabled,
    created_at
FROM alert_channels
ORDER BY created_at DESC;
```

### 查看最近的通知执行
```sql
SELECT
    iel.id,
    iel.integration_id,
    i.name as integration_name,
    iel.channel_id,
    ac.name as channel_name,
    iel.trigger_source,
    iel.status,
    iel.execution_time_ms,
    iel.error_message,
    iel.executed_at
FROM integration_execution_logs iel
LEFT JOIN integrations i ON iel.integration_id = i.id
LEFT JOIN alert_channels ac ON iel.channel_id = ac.id
WHERE iel.trigger_source IN ('alert_dispatch', 'alert_recovery')
ORDER BY iel.executed_at DESC
LIMIT 20;
```

---

## 预期结果

### 告警通知 Payload（飞书/钉钉）

**告警通知**：
```
【CRITICAL】数据库名称 告警

告警详细信息

数据源：数据库名称
时间：2026-03-18 14:00:00
```

**恢复通知**：
```
【已恢复】数据库名称 告警已恢复

告警详细信息

告警时间：2026-03-18 14:00:00
恢复时间：2026-03-18 14:30:00
```

### 邮件通知

**主题**：`[CRITICAL] 告警标题`

**内容**：
```
告警详情：
--------------
严重程度：CRITICAL
告警类型：threshold
数据库信息：
--------------
名称：数据库名称
类型：MYSQL
地址：localhost:3306
数据库：test

告警内容...

创建时间：2026-03-18 14:00:00
```

---

**测试完成时间**: 待测试
**测试状态**: 待验证
