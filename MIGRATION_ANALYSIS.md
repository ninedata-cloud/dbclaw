# 迁移脚本分析报告

## 执行摘要

已完成对 103 个迁移脚本的系统性分析。**所有索引已成功迁移到模型定义中**，可以安全删除迁移脚本。

## 1. 索引迁移状态 ✅

所有迁移脚本中的索引已完全迁移到模型定义：

- ✅ alert_message: 2 个复合索引
- ✅ datasource_metric: 2 个复合索引
- ✅ diagnosis_conclusion: 1 个复合索引
- ✅ diagnosis_event: 1 个复合索引
- ✅ host_metric: 1 个复合索引
- ✅ report: 6 个索引（包括复合索引）
- ✅ doc_category: 1 个复合索引
- ✅ doc_document: 1 个复合索引
- ✅ skill_execution: 1 个复合索引
- ✅ skill_rating: 1 个唯一约束
- ✅ chat_channel_binding: 1 个唯一复合索引

## 2. 列定义迁移状态 ✅

### 2.1 已完整迁移的功能

以下功能的所有列定义已在模型中：

- ✅ **软删除字段** (is_deleted, deleted_at, deleted_by)
  - 通过 `SoftDeleteMixin` 统一管理
  - 涵盖表: datasource, app_user, host, doc_document, integration, alert_subscription, diagnostic_session, chat_message, report, diagnosis_event

- ✅ **聊天消息扩展字段**
  - run_id, render_segments, status
  - input_tokens, output_tokens, total_tokens

- ✅ **文档路由字段**
  - scope, doc_kind, db_types, issue_categories
  - datasource_ids, host_ids, tags, priority
  - freshness_level, enabled_in_diagnosis
  - diagnosis_profile, compiled_snapshot, compiled_at, quality_status

- ✅ **用户会话安全字段**
  - email, phone, session_version, password_changed_at

- ✅ **集成系统字段**
  - integration_id, config_schema

- ✅ **主机配置缓存**
  - config_data, config_collected_at

- ✅ **诊断会话扩展**
  - knowledge_snapshot, host_id

### 2.2 已归档/删除的字段

以下字段已通过迁移脚本归档并删除，**不需要**在模型中定义：

#### Report 表废弃字段
- ❌ ai_analysis (已归档到 archive.report_deprecated_fields)
- ❌ knowledge_sources (已归档)
- ❌ is_scheduled (已归档)
- ❌ schedule_config_id (已归档)
- ❌ retention_days (已归档)

迁移脚本: `archive_and_drop_deprecated_report_columns.py`

#### Datasource 表废弃字段
- ❌ adapter_id (已归档到 archive.datasource_adapter_mapping)

迁移脚本: `archive_legacy_adapter_schema.py`

#### AlertSubscription 表废弃字段
- ❌ dingtalk_webhook_url (已删除，迁移到 Integration 系统)
- ❌ dingtalk_secret (已删除)
- ❌ channel_ids (已删除)
- ❌ channels (已删除)
- ❌ webhook_url (已删除)

迁移脚本: `remove_legacy_notification_fields.py`

## 3. 发现的代码问题 ⚠️

### 3.1 废弃字段仍在使用

**文件**: `backend/services/notification_service.py`

**问题代码**:
```python
# 第 397-398 行
elif channel == "dingtalk" and subscription.dingtalk_webhook_url:
    log = await NotificationService._send_recovery_dingtalk(
        db, alert, subscription.dingtalk_webhook_url, 
        subscription.dingtalk_secret, subscription.id, datasource
    )
```

**影响**: 
- 这些字段已从数据库中删除
- 代码会在运行时抛出 AttributeError
- 钉钉通知功能已失效

**建议修复**:
1. 将钉钉通知迁移到 Integration 系统
2. 或者删除这段废弃代码
3. 检查是否有其他地方引用了这些废弃字段

## 4. 迁移脚本中的特殊逻辑

### 4.1 数据迁移逻辑

以下迁移脚本包含数据转换逻辑（不仅是 DDL）：

1. **密码重加密**: `reencrypt_passwords.py`
   - 使用新的加密算法重新加密所有密码
   - 如果数据库中有历史数据，需要确保已执行

2. **表重命名**: `rename_tables_to_singular.py`
   - 将复数表名改为单数（如 reports → report）
   - 模型定义已使用单数表名

3. **字段迁移**: `migrate_datasource_extra_params_to_jsonb.py`
   - 将 extra_params 从 TEXT 转换为 JSONB
   - 模型中已定义为 JSON 类型

4. **集成系统迁移**: 
   - `migrate_alert_channels_to_subscription_targets.py`
   - `migrate_subscriptions_to_channels.py`
   - 将旧的通知系统迁移到新的 Integration 系统

### 4.2 CREATE TABLE 语句

部分迁移脚本创建了新表，这些表已在模型中定义：
- alert_ai_policy
- alert_ai_runtime_state
- alert_ai_evaluation_log
- user_session
- 等等

## 5. 验证结果

### 5.1 索引验证
```bash
python verify_indexes.py
```
结果: ✅ 所有关键索引已覆盖

### 5.2 列定义验证
已验证以下关键表的列定义完整性：
- ✅ chat_message: 所有字段已定义
- ✅ doc_document: 所有字段已定义
- ✅ app_user: 所有字段已定义
- ✅ diagnostic_session: 所有字段已定义
- ✅ host: 所有字段已定义
- ✅ integration: 所有字段已定义

## 6. 结论与建议

### 6.1 可以安全删除迁移脚本 ✅

**原因**:
1. 所有索引已迁移到模型定义
2. 所有活跃字段已在模型中定义
3. 废弃字段已通过专门的归档脚本处理
4. `Base.metadata.create_all()` 可以创建完整的数据库结构

### 6.2 删除前的准备工作

1. **修复代码 bug** (高优先级)
   ```bash
   # 检查所有废弃字段的引用
   grep -r "dingtalk_webhook_url\|dingtalk_secret\|channel_ids" backend --include="*.py" | grep -v migrations
   grep -r "adapter_id" backend --include="*.py" | grep -v migrations
   grep -r "\.ai_analysis\|\.knowledge_sources" backend --include="*.py" | grep -v migrations
   ```

2. **备份迁移脚本**
   ```bash
   tar -czf migrations_backup_$(date +%Y%m%d).tar.gz backend/migrations/
   ```

3. **在测试环境验证**
   ```bash
   # 删库重建
   DROP DATABASE dbclaw_test;
   CREATE DATABASE dbclaw_test;
   
   # 运行应用，让 create_all() 创建表结构
   python -c "from backend.database import init_db; import asyncio; asyncio.run(init_db())"
   
   # 验证索引
   SELECT tablename, indexname, indexdef 
   FROM pg_indexes 
   WHERE schemaname = 'public' 
   ORDER BY tablename, indexname;
   ```

4. **创建 README**
   ```bash
   # 在 backend/migrations/ 目录添加 README.md
   # 说明新部署流程和迁移脚本的历史作用
   ```

### 6.3 保留的文件

建议保留以下文件：
- `backend/migrations/__init__.py`
- `backend/migrations/runner.py` (如果有其他用途)
- `backend/migrations/README.md` (新建，说明历史)

### 6.4 删除的文件

可以删除所有 `*.py` 迁移脚本（103 个文件）

## 7. 新部署流程

删除迁移脚本后，新部署流程：

```python
# backend/database.py 中的 init_db() 函数
async def init_db():
    async with engine.begin() as conn:
        # 创建所有表、索引、约束
        await conn.run_sync(Base.metadata.create_all)
```

**优点**:
- 简化部署流程
- 避免迁移脚本顺序问题
- 模型定义即数据库结构
- 更容易维护和理解

**注意事项**:
- 仅适用于新部署
- 现有数据库仍需保持当前结构
- 不影响已运行的生产环境
