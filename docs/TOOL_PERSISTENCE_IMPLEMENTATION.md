# Skill调用信息持久化 - 实现总结

## 问题

AI诊断页面切换会话后，skill调用信息（Tool Panel内容）丢失。

## 解决方案

实现完整持久化方案：将skill调用信息作为独立消息记录保存到数据库。

## 实现内容

### 1. 后端改造

**文件：** `backend/routers/chat.py`

在WebSocket消息处理中，保存tool_call和tool_result到数据库：

```python
# 保存tool_call消息
elif event_type == "tool_call":
    async with async_session() as tool_db:
        tool_msg = ChatMessage(
            session_id=session_id,
            role="tool_call",
            content=json.dumps({
                "tool_name": event["tool_name"],
                "tool_args": event["tool_args"]
            }),
            tool_calls=[{
                "name": event["tool_name"],
                "arguments": event["tool_args"]
            }]
        )
        tool_db.add(tool_msg)
        await tool_db.commit()

# 保存tool_result消息
elif event_type == "tool_result":
    async with async_session() as tool_db:
        result_msg = ChatMessage(
            session_id=session_id,
            role="tool_result",
            content=json.dumps({
                "tool_name": event["tool_name"],
                "result": event["result"],
                "execution_time_ms": event.get("execution_time_ms")
            })
        )
        tool_db.add(result_msg)
        await tool_db.commit()
```

### 2. 前端改造

**文件：** `frontend/js/components/chat-widget.js`

#### 2.1 扩展 loadMessages() 方法

处理tool_call和tool_result消息类型：

```javascript
loadMessages(messages) {
    // ... 清空容器 ...

    this.restoredTools = new Map();
    let hasToolMessages = false;

    for (const msg of messages) {
        if (msg.role === 'tool_call') {
            const data = JSON.parse(msg.content);
            this._restoreToolCall(data.tool_name, data.tool_args);
            hasToolMessages = true;
        } else if (msg.role === 'tool_result') {
            const data = JSON.parse(msg.content);
            this._restoreToolResult(data.tool_name, data.result, data.execution_time_ms);
            hasToolMessages = true;
        }
        // ... 处理其他消息类型 ...
    }
}
```

#### 2.2 新增 _restoreToolCall() 方法

恢复tool调用显示：

```javascript
_restoreToolCall(toolName, args) {
    const toolPanel = DOM.$('#tool-panel-content');
    // 创建tool调用卡片
    const toolId = `tool-restored-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
    // ... 渲染HTML ...

    // 存储映射关系
    if (!this.restoredTools) this.restoredTools = new Map();
    this.restoredTools.set(toolName, toolId);
}
```

#### 2.3 新增 _restoreToolResult() 方法

恢复tool执行结果：

```javascript
_restoreToolResult(toolName, result, executionTimeMs = null) {
    const toolId = this.restoredTools.get(toolName);
    // 更新状态和结果显示
    // ...
}
```

### 3. 清理逻辑优化

**文件：** `frontend/js/pages/diagnosis.js`

清空Tool Panel时同时清理映射关系：

```javascript
onClick: () => {
    // 清空UI
    toolPanelContent.innerHTML = '...';

    // 清理映射
    if (ChatWidget.restoredTools) {
        ChatWidget.restoredTools.clear();
    }
    if (ChatWidget.pendingTools) {
        ChatWidget.pendingTools.clear();
    }
}
```

## 测试验证

### 单元测试

**文件：** `test_tool_persistence.py`

测试结果：
```
✅ 测试通过：Tool调用信息持久化功能正常
✅ 消息顺序测试完成
```

### 手动测试

**测试页面：** `test_tool_persistence.html`

测试步骤：
1. 打开AI诊断页面
2. 发送触发skill调用的问题
3. 观察Tool Panel显示
4. 切换到其他会话
5. 切换回原会话
6. 验证Tool Panel内容恢复

## 数据库Schema

使用现有的 `chat_messages` 表，新增两种消息类型：

- **tool_call**：role='tool_call'，content为JSON字符串
- **tool_result**：role='tool_result'，content为JSON字符串

无需数据库迁移。

## 文件清单

### 修改的文件
- `backend/routers/chat.py` - WebSocket消息处理
- `frontend/js/components/chat-widget.js` - ChatWidget组件
- `frontend/js/pages/diagnosis.js` - 清理逻辑

### 新增的文件
- `test_tool_persistence.py` - 单元测试
- `test_tool_persistence.html` - 手动测试页面
- `docs/TOOL_PERSISTENCE_FEATURE.md` - 功能文档

## 优势

1. **数据完整性** - tool调用作为独立消息记录，保证数据完整
2. **可扩展性** - 支持未来的审计、分析、重放功能
3. **架构清晰** - 符合消息流语义
4. **无需迁移** - 利用现有表结构

## 使用说明

功能自动生效，用户无需任何配置。切换会话时，Tool Panel会自动恢复历史skill调用信息。

## 实现日期

2026-03-18
