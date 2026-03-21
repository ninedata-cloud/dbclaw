# 告警分页功能使用指南

## 功能概述

告警管理页面现已支持完整的分页功能，包括事件视图和告警视图。分页风格与数据库智能巡检模块保持一致。

## 主要特性

### 1. 简洁的分页控件
- **导航按钮**：上一页、页码、下一页
- **智能页码**：显示当前页前后各2页，首尾页始终显示
- **固定每页**：每页显示 10 条记录

### 2. 统一风格
- 与巡检模块分页风格完全一致
- 简洁清晰的按钮样式
- 居中对齐的布局

### 3. 智能联动
- 修改筛选条件时自动重置到第一页
- 事件视图和告警视图独立分页

## 使用方法

### 基本操作

1. **查看告警**
   ```
   访问：http://localhost:9939/frontend/index.html#alerts
   ```

2. **切换视图**
   - 点击"事件视图"查看聚合后的告警事件
   - 点击"告警视图"查看原始告警记录

3. **翻页**
   - 点击页码直接跳转
   - 使用"上一页"/"下一页"按钮导航
   - 首页和末页始终可见

4. **筛选数据**
   - 使用顶部筛选器（数据源、状态、严重程度等）
   - 分页自动重置到第一页

## 技术实现

### 前端
- **文件**：`frontend/js/pages/alerts.js`
- **样式**：`frontend/css/alerts.css`（复用全局按钮样式）
- **数据结构**：
  ```javascript
  currentPage: { events: 1, alerts: 1 }
  pageSize: { events: 10, alerts: 10 }
  totalCount: { events: 0, alerts: 0 }
  ```
- **方法**：
  - `renderPagination(type)` - 渲染分页控件
  - `goToPage(type, page)` - 跳转页面
  - `resetPagination()` - 重置分页

### 后端
- **路由**：`backend/routers/alerts.py`
- **参数**：
  - `limit` - 每页数量（1-1000，默认 100）
  - `offset` - 偏移量（从 0 开始）
- **返回**：
  ```json
  {
    "events": [...],
    "total": 100,
    "limit": 10,
    "offset": 0
  }
  ```

## 与巡检模块的一致性

| 特性 | 巡检模块 | 告警模块 |
|------|---------|---------|
| 每页数量 | 10 条 | 10 条 |
| 按钮样式 | btn-sm btn-secondary/primary | btn-sm btn-secondary/primary |
| 页码显示 | 当前页±2 | 当前页±2 |
| 布局方式 | 居中对齐 | 居中对齐 |
| 省略号 | 支持 | 支持 |

## 验证测试

运行验证脚本：
```bash
python verify_pagination.py
```

访问测试页面：
```
http://localhost:9939/test_alert_pagination.html
```

## 常见问题

**Q: 为什么固定每页10条？**
A: 与巡检模块保持一致，提供统一的用户体验。

**Q: 为什么修改筛选条件后回到第一页？**
A: 这是设计行为，确保用户看到筛选后的完整结果。

**Q: 可以自定义每页数量吗？**
A: 当前版本固定为10条，如需调整可修改 `pageSize` 配置。

## 相关文档

- 详细实现文档：`docs/ALERT_PAGINATION_FEATURE.md`
- 告警系统文档：`CLAUDE.md`
- 巡检模块参考：`frontend/js/pages/inspection.js`
