# SmartDBA 文件上传功能 - 实现完成

## 功能概述

为AI诊断添加了类似ChatGPT的文件和图片上传功能，用户可以上传文件并针对附件内容提问。

## 实现的功能

### 1. 支持的文件类型

**图片文件**
- .jpg, .jpeg, .png, .gif, .webp, .bmp
- 自动处理为vision API格式（base64编码）
- 自动缩放大图（最大1024x1024）

**文本文件**
- .txt, .log, .sql, .json, .yaml, .yml, .md, .csv
- 自动读取内容并传递给AI
- 内容限制50000字符

**文档文件**
- .pdf, .doc, .docx
- 提供文件元数据

### 2. 文件大小限制
- 单个文件最大10MB
- 支持多文件上传

### 3. 用户界面

**上传按钮**
- 聊天输入框左侧的回形针图标
- 点击选择文件，支持多选

**附件预览**
- 上传后显示在输入框上方
- 显示文件名和类型图标
- 可以删除已上传的附件

**消息显示**
- 用户消息中显示附件列表
- 附件带有类型图标和文件名

## 技术实现

### 后端组件

1. **AttachmentHandler** (`backend/utils/attachment_handler.py`)
   - 文件上传和存储
   - 图片处理（缩放、格式转换）
   - 文本文件读取
   - 格式化为LLM可用格式

2. **API端点** (`backend/routers/chat.py`)
   - `POST /api/chat/sessions/{session_id}/upload` - 上传文件
   - 文件类型和大小验证
   - 返回文件元数据

3. **数据库扩展**
   - `chat_messages.attachments` - JSON字段存储附件元数据
   - 自动迁移添加字段

4. **WebSocket处理**
   - 接收附件元数据
   - 处理附件内容并传递给AI
   - 支持多模态消息（文本+图片）

### 前端组件

1. **ChatWidget更新** (`frontend/js/components/chat-widget.js`)
   - 文件选择和上传
   - 附件预览管理
   - 消息中显示附件
   - 清理附件功能

2. **DiagnosisPage更新** (`frontend/js/pages/diagnosis.js`)
   - 传递附件到WebSocket
   - 加载历史消息时显示附件

3. **样式** (`frontend/css/chat-attachments.css`)
   - 附件预览区域
   - 附件芯片样式
   - 消息中的附件显示

## 使用方法

### 用户操作流程

1. 打开AI诊断页面
2. 创建或选择会话
3. 点击输入框左侧的📎图标
4. 选择要上传的文件（可多选）
5. 文件上传后显示在输入框上方
6. 输入问题或直接发送
7. AI会分析附件内容并回答

### 示例场景

**场景1：上传错误日志**
```
用户：上传 error.log
用户：这个错误是什么原因？
AI：分析日志内容，发现是连接超时错误...
```

**场景2：上传SQL文件**
```
用户：上传 slow_query.sql
用户：这个查询如何优化？
AI：分析SQL语句，建议添加索引...
```

**场景3：上传截图**
```
用户：上传数据库监控截图
用户：这个性能图表有什么问题？
AI：分析图表，发现CPU使用率异常...
```

## 文件存储

- 上传的文件存储在 `uploads/chat_attachments/` 目录
- 文件名格式：`{session_id}_{uuid}.{ext}`
- 元数据存储在数据库中

## 安全措施

1. **文件类型白名单** - 只允许特定类型文件
2. **文件大小限制** - 最大10MB
3. **文件名清理** - 使用UUID避免冲突
4. **权限检查** - 需要登录才能上传
5. **内容限制** - 文本文件限制50000字符

## 依赖项

新增依赖：
- `pillow` - 图片处理库

安装：
```bash
pip install pillow
```

## 数据库迁移

系统会自动迁移，添加 `chat_messages.attachments` 字段。

如果需要手动迁移：
```sql
ALTER TABLE chat_messages ADD COLUMN attachments TEXT;
```

## API使用示例

### 上传文件
```javascript
const formData = new FormData();
formData.append('file', file);

const response = await fetch('/api/chat/sessions/1/upload', {
    method: 'POST',
    headers: { 'Authorization': 'Bearer token' },
    body: formData
});

const metadata = await response.json();
// {
//   "filename": "error.log",
//   "stored_filename": "1_abc123.log",
//   "file_type": "text",
//   "mime_type": "text/plain",
//   "size": 1024,
//   "path": "/path/to/file"
// }
```

### 发送带附件的消息
```javascript
ws.send(JSON.stringify({
    message: "分析这个日志",
    attachments: [metadata],
    connection_id: 1,
    model_id: 1
}));
```

## 注意事项

1. **Vision模型支持** - 图片分析需要支持vision的AI模型（如GPT-4V）
2. **文件清理** - 建议定期清理旧的上传文件
3. **存储空间** - 注意监控上传目录的磁盘使用
4. **并发上传** - 支持同时上传多个文件

## 未来增强

1. **拖拽上传** - 支持拖拽文件到聊天区域
2. **图片预览** - 在消息中显示图片缩略图
3. **文件下载** - 允许下载历史附件
4. **OCR支持** - 从图片中提取文本
5. **PDF解析** - 提取PDF文本内容
6. **文件压缩** - 自动压缩大文件

## 测试建议

1. 上传各种类型的文件
2. 测试文件大小限制
3. 测试多文件上传
4. 测试图片处理
5. 测试文本文件读取
6. 测试AI对附件的理解

---

**状态**: ✅ 功能完成并可用

文件上传功能已完全集成到AI诊断中，用户可以像使用ChatGPT一样上传文件并提问！
