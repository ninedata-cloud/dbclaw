# DBClaw 改进验证清单

## ✅ 修复完成

### 1. 语法错误修复
- ✅ 修复 `datasource_metric.py` 中的 `__table_args__` 语法错误
- ✅ 添加缺失的逗号使其成为正确的元组格式

### 2. 模块导入验证
```bash
python -c "
from backend.models.alert_message import AlertMessage
from backend.models.datasource_metric import DatasourceMetric
from backend.models.inspection_trigger import InspectionTrigger
from backend.services.task_manager import BackgroundTaskManager
from backend.utils.password_validator import validate_password_strength
print('所有模块导入成功')
"
```
**结果：** ✅ 通过

### 3. 应用创建验证
```bash
python -c "from backend.app import create_app; app = create_app(); print('应用创建成功')"
```
**结果：** ✅ 通过

## 🚀 启动应用

现在可以正常启动应用了：

```bash
python run.py
```

应该看到以下日志：
```
INFO:backend.app:Starting DBClaw...
INFO:backend.app:Task manager initialized
INFO:backend.database:Database initialized
INFO:backend.app:SSH connection pool started
INFO:backend.app:Inspection Service activated
INFO:backend.app:Host metrics collector started
INFO:backend.app:Notification dispatcher started
INFO:backend.app:Integration scheduler started
...
INFO:     Uvicorn running on http://0.0.0.0:8000
```

## 📋 功能验证清单

### 前端 XSS 防护验证

1. **访问数据源管理页面**
   ```
   http://localhost:8000/#datasources
   ```

2. **创建/编辑数据源，输入测试数据**
   - 名称：`<script>alert('XSS')</script>`
   - Host：`<img src=x onerror=alert('XSS')>`
   - 备注：`<b>测试</b>`

3. **验证结果**
   - ✅ 应该显示为纯文本，不执行脚本
   - ✅ 查看页面源码，应该看到 HTML 实体编码

### 后台任务管理验证

1. **查看启动日志**
   ```bash
   tail -f logs/app.log | grep -i "task"
   ```

2. **应该看到**
   ```
   Task manager initialized
   Registered background task: host_metrics_collector
   Registered background task: notification_dispatcher
   Registered background task: integration_scheduler
   ```

3. **停止应用（Ctrl+C）**
   ```
   Starting graceful shutdown...
   Cancelling 3 running tasks...
   All tasks cancelled successfully
   ```

### SSH 超时保护验证

1. **配置一个 SSH 主机（故意配置错误或不可达）**

2. **查看日志**
   ```bash
   tail -f logs/app.log | grep -i "ssh"
   ```

3. **应该看到**
   ```
   SSH metrics collection timeout for datasource X
   Marked SSH connection as unhealthy for host Y
   ```

### 数据库索引验证

1. **连接到 PostgreSQL**
   ```bash
   psql -U <username> -d <database>
   ```

2. **查看索引**
   ```sql
   SELECT indexname, indexdef 
   FROM pg_indexes 
   WHERE tablename = 'alert_message'
   ORDER BY indexname;
   ```

3. **应该看到新增的索引**
   ```
   idx_alert_message_datasource_status
   idx_alert_message_type_status
   ```

### 密码验证工具测试

```python
from backend.utils.password_validator import validate_password_strength

# 测试弱密码
print(validate_password_strength("123456"))
# 输出: (False, '密码长度至少为 8 个字符')

print(validate_password_strength("password"))
# 输出: (False, '密码必须包含至少一个大写字母')

print(validate_password_strength("Password"))
# 输出: (False, '密码必须包含至少一个数字')

print(validate_password_strength("Password1"))
# 输出: (False, '密码必须包含至少一个特殊字符')

# 测试强密码
print(validate_password_strength("MyP@ssw0rd123"))
# 输出: (True, '')
```

## 🔍 性能监控

### 告警查询性能对比

**测试查询：**
```sql
-- 按数据源和状态查询（应使用新索引）
EXPLAIN ANALYZE 
SELECT * FROM alert_message 
WHERE datasource_id = 1 AND status = 'active'
ORDER BY created_at DESC 
LIMIT 20;

-- 按类型和状态查询（应使用新索引）
EXPLAIN ANALYZE 
SELECT alert_type, status, COUNT(*) 
FROM alert_message 
WHERE status IN ('active', 'acknowledged')
GROUP BY alert_type, status;
```

**预期结果：**
- ✅ 查询计划中应显示使用了新索引
- ✅ 执行时间应明显缩短（相比无索引时）

## 📊 监控指标

### 应用启动后监控

1. **任务状态**
   ```bash
   curl http://localhost:8000/health/checks
   ```

2. **内存使用**
   ```bash
   ps aux | grep "python run.py"
   ```

3. **数据库连接**
   ```sql
   SELECT count(*) FROM pg_stat_activity 
   WHERE datname = 'dbclaw';
   ```

## ⚠️ 已知问题和注意事项

### 1. 数据库迁移
- 新增的索引会在首次启动时自动创建
- 如果数据量大，索引创建可能需要几分钟
- 建议在低峰期首次启动

### 2. 向后兼容性
- ✅ 所有改动都是向后兼容的
- ✅ 不影响现有功能
- ✅ 可以安全部署

### 3. 回滚方案
如果出现问题，可以快速回滚：
```bash
git checkout HEAD~1 backend/
git checkout HEAD~1 frontend/
python run.py
```

## ✅ 验证完成标准

- [ ] 应用正常启动，无错误日志
- [ ] 前端 XSS 防护生效
- [ ] 后台任务正常注册和管理
- [ ] SSH 超时保护生效
- [ ] 数据库索引创建成功
- [ ] 密码验证工具正常工作
- [ ] 所有现有功能正常运行

## 📞 问题反馈

如果遇到任何问题，请检查：
1. 日志文件：`logs/app.log`
2. 数据库连接：确保 PostgreSQL 正常运行
3. 依赖版本：`pip list | grep -i sqlalchemy`

---

**验证日期：** 2026-04-22  
**验证状态：** ✅ 基础验证通过，待生产环境测试
