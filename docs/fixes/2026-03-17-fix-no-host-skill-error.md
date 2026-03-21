# 修复：数据源未配置主机时技能调用失败的问题

## 问题描述

在生成AI巡检报告时，如果数据源没有配置主机ID（`host_id` 为 `NULL`），系统会尝试调用需要主机连接的技能（如 `get_os_metrics`、`diagnose_high_cpu`），导致以下问题：

1. 技能执行失败并抛出异常：`ValueError: Datasource X has no host configured`
2. 报告生成失败，无法产生任何内容
3. 错误日志中显示技能执行失败的堆栈跟踪

## 根本原因

相关技能在调用 `context.execute_command()` 时，`context.py` 会检查数据源是否配置了主机：

```python
# backend/skills/context.py line 80-81
if not datasource.host_id:
    raise ValueError(f"Datasource {datasource_id} has no host configured")
```

但技能代码没有在调用前进行前置条件检查，导致异常直接抛出，中断了报告生成流程。

## 解决方案

修改需要主机连接的技能，在执行OS命令前先检查数据源是否配置了主机，如果没有配置则返回友好的错误信息而不是抛出异常。

### 修改的技能

1. **get_os_metrics** (`backend/skills/builtin/get_os_metrics.yaml`)
2. **diagnose_high_cpu** (`backend/skills/builtin/diagnose_high_cpu.yaml`)

### 修改内容

在技能代码开头添加主机配置检查：

```python
# Check if datasource has host configured by querying database directly
from backend.models.datasource import Datasource
from sqlalchemy import select

result = await context.db.execute(
    select(Datasource).where(Datasource.id == datasource_id)
)
datasource = result.scalar_one_or_none()

if not datasource:
    return {
        "success": False,
        "error": "datasource_not_found",
        "message": f"数据源 ID {datasource_id} 不存在"
    }

if not datasource.host_id:
    return {
        "success": False,
        "error": "no_host_configured",
        "message": f"数据源 {datasource.name} (ID: {datasource_id}) 未配置主机连接，无法收集操作系统指标。如需收集OS指标，请在数据源配置中关联主机。"
    }
```

## 效果

修复后的行为：

1. **技能执行**：返回 `success: false` 和友好的错误信息，不抛出异常
2. **AI报告生成**：AI会收到技能返回的错误信息，可以在报告中说明该数据源未配置主机，无法收集OS指标
3. **报告完整性**：报告仍然可以正常生成，只是不包含OS指标部分

## 测试验证

创建了测试脚本验证修复：

```bash
# 测试技能直接调用
python test_no_host_skill.py

# 测试在对话中调用
python test_skill_conversation.py
```

测试结果：
- ✅ `get_os_metrics` 正确处理无主机配置的情况
- ✅ `diagnose_high_cpu` 正确处理无主机配置的情况
- ✅ 返回友好的中文错误信息
- ✅ 不抛出异常，不中断报告生成流程

## 相关文件

- `backend/skills/builtin/get_os_metrics.yaml`
- `backend/skills/builtin/diagnose_high_cpu.yaml`
- `backend/skills/context.py` (execute_command 方法)
- `backend/services/inspection_service.py`
- `backend/services/report_generator.py`

## 注意事项

1. 其他直接使用 `host_id` 参数的技能（如 `execute_os_command`、`execute_any_os_command`）不需要修改，因为它们直接接收 `host_id` 参数，由调用方负责确保主机存在
2. 未来添加新的需要主机连接的技能时，应该遵循相同的模式，在调用 `execute_command` 前检查主机配置
3. 这个修复是防御性编程的良好实践，让系统更加健壮

## 日期

2026-03-17
