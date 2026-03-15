# System Management Skills - Quick Start Guide

## 快速开始

系统管理技能已成功部署！现在可以通过AI对话直接管理SmartDBA系统资源。

## 立即尝试

### 1. 启动服务器

```bash
python run.py
```

服务器启动时会自动加载所有7个系统管理技能。

### 2. 访问AI对话界面

打开浏览器访问：`http://localhost:8000`

### 3. 开始使用

直接用自然语言与AI对话，例如：

#### 数据源管理

```
列出所有数据源

创建一个MySQL数据源：
- 名称：test-db
- 地址：localhost
- 端口：3306
- 用户名：root
- 密码：password
- 数据库：testdb

测试数据源ID为1的连接

更新数据源ID为1的监控间隔为30秒

删除数据源ID为5
```

#### 主机管理

```
列出所有SSH主机

创建一个SSH主机：
- 名称：jump-server
- 地址：10.0.0.1
- 端口：22
- 用户名：admin
- 密码：admin123

测试SSH主机ID为1的连接
```

#### 监控数据查询

```
查询数据源ID为1最近1小时的监控数据

查看所有数据源最近24小时的监控统计

查询db_status类型的指标，最近30分钟
```

#### 诊断报告

```
触发数据源ID为1的诊断

查看最近10个诊断报告

查看报告ID为5的详细内容

列出状态为completed的所有报告
```

#### 系统元数据查询

```
查询系统统计信息

查看系统配置

列出所有用户

检查系统健康状态

执行SQL查询：SELECT db_type, COUNT(*) as count FROM datasources GROUP BY db_type

查询最近的诊断报告：SELECT id, title, status, created_at FROM reports ORDER BY created_at DESC LIMIT 10
```

#### 技能管理

```
列出所有技能

查看manage_datasource技能的详细信息

列出category为system的技能

创建一个自定义技能（需要提供完整的YAML定义）
```

## 验证安装

运行测试脚本验证所有技能已正确加载：

```bash
python test_system_management_skills_simple.py
```

预期输出：
```
✅ ALL 7 SKILLS LOADED SUCCESSFULLY
```

## 技能列表

| 技能ID | 功能 | 主要操作 |
|--------|------|----------|
| manage_datasource | 数据源管理 | 增删改查测试 |
| manage_host | SSH主机管理 | 增删改查测试 |
| manage_skill | 技能管理 | 列表、创建、修改、启用/禁用 |
| query_monitoring_data | 监控数据查询 | 查询历史指标+统计 |
| query_inspection_reports | 诊断报告查询 | 列表/详情查询 |
| trigger_inspection | 触发诊断 | 手动触发诊断 |
| query_system_metadata | 系统元数据查询 | SQL/配置/统计/用户/健康 |

## 安全提示

### SQL查询限制

query_system_metadata的SQL模式有以下安全限制：

✅ **允许**：
- SELECT查询
- 白名单表：datasources, hosts, skills, metric_snapshots, diagnostic_sessions, reports, users, knowledge_bases, skill_executions, inspection_configs, inspection_triggers, ai_models, host_metrics, login_logs
- 最多1000行

❌ **禁止**：
- UPDATE, DELETE, DROP, INSERT, ALTER, CREATE, TRUNCATE, GRANT, REVOKE
- 非白名单表
- SQL注入尝试

### 密码安全

- 所有密码和私钥自动使用Fernet加密
- 加密密钥配置在.env文件的ENCRYPTION_KEY
- 测试连接时才会临时解密

### 技能管理安全

- 内置技能不可修改或禁用
- 自定义技能需要通过代码验证
- 禁止导入危险模块（os, subprocess等）

## 常见问题

### Q: 技能没有加载？

**A**: 检查以下几点：
1. 确认YAML文件在`backend/skills/builtin/`目录
2. 检查YAML语法：`python -m yaml backend/skills/builtin/manage_datasource.yaml`
3. 查看服务器启动日志是否有错误
4. 重启服务器

### Q: AI没有调用技能？

**A**: 可能原因：
1. 技能未正确加载（运行测试脚本验证）
2. 自然语言描述不够明确（尝试更具体的描述）
3. 检查AI模型配置是否正确

### Q: 连接测试失败？

**A**: 检查：
1. 数据库/SSH服务是否运行
2. 网络连接是否正常
3. 防火墙规则
4. 用户名密码是否正确
5. ENCRYPTION_KEY是否配置

### Q: SQL查询被拒绝？

**A**: 确保：
1. 查询以SELECT开头
2. 表名在白名单中
3. 没有使用禁止的关键词
4. SQL语法正确

## 高级用法

### 复杂工作流示例

**场景1：设置新数据库监控**

```
1. 创建SSH主机jump-server，地址10.0.0.1，用户admin，密码pass123
2. 创建MySQL数据源prod-db，地址192.168.1.100:3306，通过SSH主机ID为1
3. 测试数据源连接
4. 触发首次诊断
5. 查看诊断报告
```

**场景2：性能问题调查**

```
1. 查询数据源ID为5最近2小时的监控数据
2. 查看统计信息，识别异常指标
3. 触发诊断，原因是CPU使用率异常
4. 查看诊断报告详情
5. 执行SQL查询分析：SELECT * FROM metric_snapshots WHERE datasource_id=5 ORDER BY collected_at DESC LIMIT 50
```

**场景3：系统健康检查**

```
1. 查询系统统计信息
2. 检查系统健康状态
3. 列出所有数据源
4. 查看最近的诊断报告
5. 执行SQL查询检查失败的报告：SELECT * FROM reports WHERE status='failed' ORDER BY created_at DESC
```

### 批量操作

虽然单个技能不支持批量操作，但可以通过AI对话实现：

```
对以下3个数据源执行诊断：
- 数据源ID 1
- 数据源ID 2
- 数据源ID 3
```

AI会自动调用trigger_inspection技能3次。

### 定期任务

可以通过AI对话设置提醒：

```
每天早上9点提醒我查看昨天的诊断报告
```

## 性能优化建议

1. **监控数据查询**：使用合适的时间范围和限制，避免大结果集
2. **SQL查询**：添加WHERE子句过滤数据，使用LIMIT限制行数
3. **报告查询**：使用过滤器（datasource_id, status）缩小结果范围
4. **统计模式**：比SQL查询更快，用于简单计数

## 故障排除

### 日志位置

服务器日志包含技能加载和执行信息：
- 启动日志：查看技能加载情况
- 执行日志：查看技能执行结果和错误

### 数据库检查

直接查询数据库验证技能：

```sql
-- 查看所有技能
SELECT id, name, category, is_builtin, is_enabled FROM skills;

-- 查看系统管理技能
SELECT id, name, category FROM skills WHERE id LIKE 'manage_%' OR id LIKE 'query_%' OR id = 'trigger_inspection';

-- 查看技能执行历史
SELECT skill_id, COUNT(*) as executions, AVG(execution_time_ms) as avg_time 
FROM skill_executions 
GROUP BY skill_id 
ORDER BY executions DESC;
```

### 重新加载技能

如果修改了技能YAML文件：

1. 停止服务器
2. 删除数据库中的技能记录（可选）：
   ```sql
   DELETE FROM skills WHERE id IN ('manage_datasource', 'manage_host', 'manage_skill', 'query_monitoring_data', 'query_inspection_reports', 'trigger_inspection', 'query_system_metadata');
   ```
3. 重启服务器（会自动重新加载）

## 更多信息

- **完整文档**：[docs/SYSTEM_MANAGEMENT_SKILLS.md](docs/SYSTEM_MANAGEMENT_SKILLS.md)
- **设计规范**：[docs/superpowers/specs/2026-03-15-system-management-skills-design.md](docs/superpowers/specs/2026-03-15-system-management-skills-design.md)
- **实现计划**：[docs/superpowers/plans/2026-03-15-system-management-skills-plan.md](docs/superpowers/plans/2026-03-15-system-management-skills-design.md)

## 反馈和支持

如有问题或建议，请：
1. 查看文档和故障排除指南
2. 检查服务器日志
3. 运行测试脚本验证
4. 联系开发团队

---

**祝使用愉快！🚀**

