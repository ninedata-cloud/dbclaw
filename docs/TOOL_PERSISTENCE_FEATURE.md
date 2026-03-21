# Skill调用信息持久化功能

## 问题描述

在AI诊断页面，当用户正在对话时切换到其他会话，再切换回来时，skill调用信息（tool panel中的内容）会丢失，只能看到对话消息，无法看到之前执行的skill调用详情。

## 根本原因

1. **Tool Panel清空**：`ChatWidget.loadMessages()` 方法在加载历史消息时会清空tool panel
2. **Tool调用信息未持久化**：虽然后端 `ChatMessage` 模型有 `tool_calls` 字段，但tool调用和结果信息没有被保存为独立的消息记录
3. **Tool Panel只显示实时调用**：`addToolCall()` 和 `addToolResult()` 方法只在WebSocket实时接收消息时被调用

## 解决方案

采用**完整持久化方案**：将skill调用信息作为独立的消息记录保存到数据库，切换回会话时从数据库恢复。

### 架构设计

#### 1. 消息类型扩展

在原有的 `user` 和 `assistant` 消息类型基础上，新增两种消息类型：

- **`tool_call`**：记录skill调用信息
  - `content`：JSON字符串，包含 `tool_name` 和 `tool_args`
  - `tool_calls`：原有字段，保存工具调用元数据

- **`tool_result`**：记录skill执行结果
  - `content`：JSON字符串，包含 `tool_name`、`result` 和 `execution_time_ms`

#### 2. 数据流程

```
用户发送消息
    ↓
AI调用skill
    ↓
WebSocket发送 tool_call 事件 → 保存到数据库（role=tool_call）
    ↓                           ↓
前端显示在Tool Panel         持久化存储
    ↓
Skill执行完成
    ↓
WebSocket发送 tool_result 事件 → 保存到数据库（role=tool_result）
    ↓                            ↓
前端更新Tool Panel状态         持久化存储
    ↓
用户切换会话
    ↓
加载历史消息（包括tool_call和tool_result）
    ↓
前端恢复Tool Panel显示
```

### 实现细节

#### 后端改造（backend/routers/chat.py）

在WebSocket消息处理中，当接收到 `tool_call` 和 `tool_result` 事件时，保存到数据库：

```python
elif event_type == "tool_call":
    # 保存tool_call到数据库
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

    # 发送到前端
    await websocket.send_json({...})

elif event_type == "tool_result":
    # 保存tool_result到数据库
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

    # 发送到前端
    await websocket.send_json({...})
```

#### 前端改造（frontend/js/components/chat-widget.js）

##### 1. 扩展 `loadMessages()` 方法

处理 `tool_call` 和 `tool_result` 类型的消息：

```javascript
loadMessages(messages) {
    // ... 清空容器 ...

    this.restoredTools = new Map();
    let hasToolMessages = false;

    for (const msg of messages) {
        if (msg.role === 'user') {
            this.addUserMessage(msg.content, msg.attachments || []);
        } else if (msg.role === 'assistant') {
            // ... 渲染assistant消息 ...
        } else if (msg.role === 'tool_call') {
            // 恢复tool调用
            const data = JSON.parse(msg.content);
            this._restoreToolCall(data.tool_name, data.tool_args);
            hasToolMessages = true;
        } else if (msg.role === 'tool_result') {
            // 恢复tool结果
            const data = JSON.parse(msg.content);
            this._restoreToolResult(data.tool_name, data.result, data.execution_time_ms);
            hasToolMessages = true;
        }
    }

    // 如果没有tool消息，显示空状态
    if (!hasToolMessages) {
        toolPanel.innerHTML = '<div>暂无skill调用记录</div>';
    }
}
```

##### 2. 新增 `_restoreToolCall()` 方法

从历史记录恢复tool调用显示：

```javascript
_restoreToolCall(toolName, args) {
    const toolPanel = DOM.$('#tool-panel-content');
    if (!toolPanel) return;

    // 创建tool调用卡片（初始状态为Pending）
    const toolId = `tool-restored-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
    const toolMsg = DOM.el('div', {
        className: 'chat-tool-call',
        id: toolId,
        'data-tool-name': toolName
    });

    toolMsg.innerHTML = `
        <div class="chat-tool-header">
            <span class="chat-tool-name">${toolName}</span>
            <span class="chat-tool-status pending">Pending</span>
        </div>
        <div class="chat-tool-body">
            <div class="chat-tool-section">
                <div class="chat-tool-section-title">Arguments</div>
                <div class="chat-tool-content">${JSON.stringify(args, null, 2)}</div>
            </div>
            <div class="chat-tool-section" id="${toolId}-result" style="display: none;">
                <div class="chat-tool-section-title">Result</div>
                <div class="chat-tool-content" id="${toolId}-result-content"></div>
            </div>
        </div>
    `;

    toolPanel.appendChild(toolMsg);

    // 存储映射关系，用于后续匹配result
    if (!this.restoredTools) this.restoredTools = new Map();
    this.restoredTools.set(toolName, toolId);
}
```

##### 3. 新增 `_restoreToolResult()` 方法

从历史记录恢复tool执行结果：

```javascript
_restoreToolResult(toolName, result, executionTimeMs = null) {
    if (!this.restoredTools) return;

    const toolId = this.restoredTools.get(toolName);
    if (!toolId) return;

    const toolMsg = DOM.$(`#${toolId}`);
    if (!toolMsg) return;

    // 更新状态为Complete或Error
    const isError = result && (
        (typeof result === 'object' && result.error) ||
        (typeof result === 'string' && result.toLowerCase().includes('error'))
    );

    const status = toolMsg.querySelector('.chat-tool-status');
    if (status) {
        status.className = `chat-tool-status ${isError ? 'error' : 'success'}`;
        const timeStr = executionTimeMs !== null ? ` (${executionTimeMs}ms)` : '';
        status.innerHTML = isError
            ? `Error${timeStr}`
            : `Complete${timeStr}`;
    }

    // 显示结果
    const resultSection = toolMsg.querySelector(`#${toolId}-result`);
    if (resultSection) {
        resultSection.style.display = 'block';
        const resultContent = resultSection.querySelector('.chat-tool-content');
        if (resultContent) {
            resultContent.textContent = JSON.stringify(result, null, 2);
        }
    }

    this.restoredTools.delete(toolName);
}
```

## 数据库Schema

使用现有的 `chat_messages` 表，无需修改表结构：

```sql
CREATE TABLE chat_messages (
    id SERIAL PRIMARY KEY,
    session_id INTEGER NOT NULL,
    role VARCHAR(20) NOT NULL,  -- 'user', 'assistant', 'tool_call', 'tool_result'
    content TEXT NOT NULL,
    tool_calls JSON,
    tool_call_id VARCHAR(100),
    attachments JSON,
    created_at TIMESTAMP DEFAULT NOW()
);
```

### 消息示例

#### tool_call消息

```json
{
    "id": 123,
    "session_id": 1,
    "role": "tool_call",
    "content": "{\"tool_name\": \"get_slow_queries\", \"tool_args\": {\"limit\": 10}}",
    "tool_calls": [
        {
            "name": "get_slow_queries",
            "arguments": {"limit": 10}
        }
    ],
    "created_at": "2026-03-18T10:30:00"
}
```

#### tool_result消息

```json
{
    "id": 124,
    "session_id": 1,
    "role": "tool_result",
    "content": "{\"tool_name\": \"get_slow_queries\", \"result\": {\"queries\": [...]}, \"execution_time_ms\": 150}",
    "created_at": "2026-03-18T10:30:01"
}
```

## 优势

1. **数据完整性**：tool调用是对话的重要组成部分，作为独立消息记录保存，保证数据完整性
2. **可扩展性**：未来可以支持tool调用的审计、分析、重放等功能
3. **架构清晰**：每条消息独立存储，符合消息流的语义
4. **无需迁移**：利用现有的 `ChatMessage` 模型，只需扩展 `role` 字段的取值

## 测试验证

运行测试脚本验证功能：

```bash
python test_tool_persistence.py
```

测试覆盖：
1. tool_call和tool_result消息能正确保存到数据库
2. 查询历史消息时能正确加载tool消息
3. 消息顺序正确（user → tool_call → tool_result → assistant）
4. 前端能正确恢复Tool Panel显示

## 使用说明

### 用户体验

1. **正常对话**：用户发送问题，AI调用skill，Tool Panel实时显示调用过程
2. **切换会话**：用户切换到其他会话，当前会话的Tool Panel内容被清空
3. **切换回来**：用户切换回原会话，Tool Panel自动恢复之前的skill调用历史
4. **清空历史**：点击Tool Panel的清空按钮，只清空UI显示，不删除数据库记录

### 开发注意事项

1. **消息顺序**：tool_call和tool_result消息必须按时间顺序保存，确保恢复时顺序正确
2. **工具名称匹配**：通过 `tool_name` 匹配tool_call和tool_result，确保同一个skill的调用和结果能正确关联
3. **错误处理**：如果JSON解析失败，应该捕获异常并记录日志，不影响其他消息的加载
4. **性能优化**：对于包含大量tool调用的会话，可以考虑分页加载或懒加载

## 未来扩展

1. **Tool调用审计**：记录所有tool调用的历史，用于安全审计和问题排查
2. **Tool调用分析**：统计最常用的skill、平均执行时间、成功率等
3. **Tool调用重放**：支持重新执行历史的tool调用，用于调试和测试
4. **Tool调用导出**：导出tool调用历史为JSON或CSV格式，用于分析和报告

## 相关文件

### 后端
- `backend/routers/chat.py`：WebSocket消息处理，保存tool消息
- `backend/models/diagnostic_session.py`：ChatMessage模型定义
- `backend/schemas/chat.py`：ChatMessageResponse schema

### 前端
- `frontend/js/components/chat-widget.js`：ChatWidget组件，恢复tool历史
- `frontend/js/pages/diagnosis.js`：AI诊断页面

### 测试
- `test_tool_persistence.py`：功能测试脚本

## 更新日期

2026-03-18
