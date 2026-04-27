# 数据库迁移说明

## 新部署方式（推荐）

从 v0.9.3 版本开始，DBClaw 使用 SQLAlchemy 的 `Base.metadata.create_all()` 自动创建数据库表结构和索引。

### 初始化数据库

新部署时，数据库会在应用启动时自动初始化：

```python
# backend/database.py
async def init_db():
    await run_pre_create_migrations()  # 在 create_all 之前执行的迁移
    
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    await run_post_create_migrations()  # 在 create_all 之后执行的迁移
```

所有表结构、索引、约束都已在模型定义中声明（`backend/models/`），无需手动运行迁移脚本。

### 添加新的迁移脚本

如果需要执行无法通过模型定义实现的数据库操作（如数据迁移、复杂的 schema 变更等），可以在 `runner.py` 中添加迁移函数：

```python
# backend/migrations/runner.py

# 在 create_all() 之前执行（如：删除旧表、重命名表等）
PRE_CREATE_MIGRATIONS = [
    lambda: some_pre_migration(),
]

# 在 create_all() 之后执行（如：数据迁移、种子数据等）
POST_CREATE_MIGRATIONS = [
    lambda: some_post_migration(),
]
```

迁移函数应该是幂等的（可以安全地重复执行）。

### 验证部署

部署后可以通过以下 SQL 验证索引是否正确创建：

```sql
-- 查看所有索引
SELECT 
    schemaname,
    tablename,
    indexname,
    indexdef
FROM pg_indexes 
WHERE schemaname = 'public'
ORDER BY tablename, indexname;

-- 查看所有约束
SELECT
    conname AS constraint_name,
    conrelid::regclass AS table_name,
    contype AS constraint_type
FROM pg_constraint
WHERE connamespace = 'public'::regnamespace
ORDER BY table_name, constraint_name;
```

## 历史迁移脚本

历史迁移脚本已被清理。所有数据库 schema 变更现在都通过模型定义管理。

如果需要查看历史迁移记录，请参考 git 历史：

```bash
git log --all --full-history -- backend/migrations/
```

## 升级现有部署

如果你有现有的 DBClaw 部署（v0.9.2 或更早版本），建议：

1. **备份数据库**
2. **删除旧数据库**（或创建新数据库）
3. **启动新版本**，让 `create_all()` 自动创建表结构
4. **恢复数据**（如需要）

注意：由于 schema 变更较多，不建议尝试从旧版本直接升级。
