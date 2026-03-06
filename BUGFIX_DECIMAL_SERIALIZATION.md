# Bug修复：Decimal序列化错误

## 问题描述

在AI诊断过程中，当技能执行返回包含 `Decimal` 类型的结果时，保存到数据库时会抛出错误：

```
TypeError: Object of type Decimal is not JSON serializable
```

这导致后续的技能调用失败，因为数据库会话被回滚。

## 错误示例

```python
# 技能返回的结果
{
    'success': True,
    'databases': [
        ['sysbench', Decimal('942.09'), Decimal('3.36'), Decimal('945.45')]
    ],
    'columns': ['database', 'data_size_mb', 'index_size_mb', 'total_size_mb']
}

# 尝试保存到数据库时失败
# SkillExecution.result 字段是 JSON 类型，无法序列化 Decimal
```

## 根本原因

1. MySQL查询返回的数值类型是 `Decimal`（来自 `pymysql` 或 `mysqlclient`）
2. SQLAlchemy 的 JSON 字段使用 `json.dumps()` 序列化数据
3. Python 的 `json.dumps()` 不支持 `Decimal` 类型

## 解决方案

在 `backend/skills/executor.py` 中添加序列化方法，在保存到数据库前将 `Decimal` 转换为 `float`：

### 修改内容

1. **导入必要的模块**：
```python
import json
from decimal import Decimal
```

2. **添加序列化方法**：
```python
@staticmethod
def _serialize_result(obj):
    """Convert non-serializable objects to serializable format"""
    if isinstance(obj, Decimal):
        return float(obj)
    elif isinstance(obj, dict):
        return {k: SkillExecutor._serialize_result(v) for k, v in obj.items()}
    elif isinstance(obj, (list, tuple)):
        return [SkillExecutor._serialize_result(item) for item in obj]
    return obj
```

3. **在保存前序列化结果**：
```python
async def _log_execution(self, ...):
    # Serialize result to handle Decimal and other non-JSON types
    serialized_result = None
    if result is not None:
        serialized_result = self._serialize_result(result)

    execution = SkillExecution(
        ...
        result=serialized_result,
        ...
    )
```

## 技术细节

### 序列化策略

- **Decimal → float**: 保持数值精度，适合大多数场景
- **递归处理**: 处理嵌套的字典和列表
- **保持其他类型**: 不影响已经可序列化的类型

### 为什么不在技能代码中处理？

1. 技能代码应该专注于业务逻辑
2. 序列化是框架层面的问题
3. 统一处理更可靠，避免遗漏

### 精度考虑

将 `Decimal` 转换为 `float` 可能会有微小的精度损失，但对于数据库大小、性能指标等场景，这个精度足够了。如果需要保持完全精度，可以考虑：

- 转换为字符串：`str(decimal_value)`
- 使用自定义 JSON encoder

## 测试验证

修复后，包含 `Decimal` 的技能结果可以正常保存：

```python
# 原始结果
result = {
    'databases': [['db1', Decimal('100.5'), Decimal('50.2')]]
}

# 序列化后
serialized = {
    'databases': [['db1', 100.5, 50.2]]
}

# 成功保存到数据库
```

## 影响范围

- 所有返回数值类型的数据库查询技能
- 特别是 `get_db_size`、`get_table_size` 等统计类技能
- 不影响技能的实际执行逻辑，只影响结果存储

## 相关文件

- `backend/skills/executor.py` - 主要修改
- `backend/skills/models.py` - SkillExecution 模型定义
- `backend/agent/conversation_skills.py` - 技能调用流程

## 后续优化建议

1. 考虑在数据库连接层统一处理 Decimal 转换
2. 添加更多类型的序列化支持（datetime、bytes等）
3. 考虑使用 `orjson` 等更快的 JSON 库
