# 数据源列表连接状态展示设计文档

**日期**：2026-03-20
**主题**：数据源管理页面列表中增加连接状态展示
**作者**：Claude

## 1. 需求概述
在 `frontend/js/pages/datasources.js` 的数据源表格中新增“连接状态”列，展示每个数据源的连接状态（normal/failed/warning/unknown），使用彩色徽章 + 最后检查时间。

后端已完整支持（模型字段、Response Schema、批量检测接口）。

## 2. 实现方案
采用**推荐方案1**：
- 表格新增一列（置于“类型”之后）
- 使用彩色圆点 + 徽章 + 时间展示
- 顶部增加“刷新连接状态”按钮，调用批量检测接口后刷新列表

## 3. 详细设计

### 3.1 状态配置
```js
const statusConfig = {
    'normal': { label: '正常', color: '#10b981', bg: '#ecfdf5' },
    'failed': { label: '连接失败', color: '#ef4444', bg: '#fef2f2' },
    'warning': { label: '警告', color: '#f59e0b', bg: '#fffbeb' },
    'unknown': { label: '未知', color: '#6b7280', bg: '#f3f4f6' }
};
```

### 3.2 表格修改 (`_renderTable()`)
- thead 新增 `<th>连接状态</th>`
- 每行新增状态单元格，使用上述配置渲染徽章 + 时间
- 时间格式：`HH:mm`（本地时间）

### 3.3 刷新功能
- 在 filterBar 或 Header 添加按钮 `<button class="btn btn-sm btn-outline-primary">刷新状态</button>`
- 点击调用 `API.checkAllDatasourceStatus()` 后执行 `this.render()`
- 在 `api.js` 添加辅助方法

### 3.4 样式
- 使用 inline style 保持与现有代码一致（无新CSS文件）
- 徽章圆角、字体大小12px
- 状态圆点（8px）

## 4. 边缘情况处理
- 无 `connection_status` 时显示 "未知"
- 无检查时间显示 "未检测"
- 批量检测失败时友好提示
- 保持现有过滤器和操作按钮功能

## 5. 测试要点
- 表格正确显示4种状态
- 点击刷新按钮后状态更新
- 响应式布局不被破坏
- 中文显示正确

**下一阶段**：编写实现计划并执行代码修改。
