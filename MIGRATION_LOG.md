# 数据库迁移执行记录

## 迁移历史

### 2026-04-22: 添加 inspection_trigger.error_message 字段

**迁移脚本：** `backend/migrations/add_inspection_trigger_error_message.py`

**执行时间：** 2026-04-22 22:15

**变更内容：**
- 添加 `error_message TEXT` 字段到 `inspection_trigger` 表
- 用于记录报告生成失败时的错误信息

**执行命令：**
```bash
python -c "
import asyncio
from backend.migrations.add_inspection_trigger_error_message import upgrade
asyncio.run(upgrade())
"
```

**验证结果：**
```
✓ error_message 字段已成功添加
✓ 字段类型：TEXT
✓ 可为空：YES
```

**影响范围：**
- 不影响现有数据
- 向后兼容
- 新字段默认为 NULL

## 自动迁移配置

迁移脚本已注册到 `backend/migrations/runner.py` 的 `POST_CREATE_MIGRATIONS` 列表中。

下次启动应用时，如果字段不存在，会自动执行迁移。

## 回滚方案

如需回滚此迁移：

```python
import asyncio
from backend.migrations.add_inspection_trigger_error_message import downgrade
asyncio.run(downgrade())
```

或手动执行 SQL：

```sql
ALTER TABLE inspection_trigger DROP COLUMN IF EXISTS error_message;
```

---

**执行人员：** Claude (Opus 4.6)  
**执行日期：** 2026-04-22  
**状态：** ✅ 成功
