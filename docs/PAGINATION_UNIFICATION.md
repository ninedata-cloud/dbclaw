# 告警分页功能统一说明

## 变更概述

将告警管理页面的分页功能统一为与数据库智能巡检模块相同的风格，实现全系统分页体验的一致性。

## 变更对比

### 数据结构

**统一前：**
```javascript
pagination: {
    events: { limit: 20, offset: 0, total: 0 },
    alerts: { limit: 20, offset: 0, total: 0 }
}
```

**统一后：**
```javascript
currentPage: { events: 1, alerts: 1 },
pageSize: { events: 10, alerts: 10 },
totalCount: { events: 0, alerts: 0 }
```

### 分页控件

**统一前：**
- 显示信息：显示 1-20 / 共 100 条
- 导航按钮：首页、上一页、页码、下一页、末页
- 每页数量选择器：10/20/50/100 可选
- 默认每页：20 条

**统一后：**
- 导航按钮：上一页、页码、下一页
- 固定每页：10 条
- 无额外信息显示
- 无每页数量选择器

### 样式实现

**统一前：**
```css
.pagination-container {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 1rem;
    background: var(--bg-secondary);
    border-top: 1px solid var(--border-color);
    gap: 1rem;
    flex-wrap: wrap;
}

.pagination-info { ... }
.pagination-controls { ... }
.page-size-selector { ... }
```

**统一后：**
```javascript
// 使用内联样式，复用全局按钮样式
style: 'margin-top: 15px; display: flex; justify-content: center; gap: 10px;'
```

### 方法变化

**统一前：**
- `renderPagination(type)` - 复杂的分页控件
- `goToPage(type, page)` - 计算 offset
- `changePageSize(type, size)` - 修改每页数量
- `resetPagination()` - 重置 offset

**统一后：**
- `renderPagination(type)` - 简洁的分页控件（与巡检一致）
- `goToPage(type, page)` - 直接设置 currentPage
- `resetPagination()` - 重置 currentPage
- 移除 `changePageSize()` 方法

## 统一的好处

### 1. 用户体验一致性
- 用户在不同模块看到相同的分页风格
- 减少学习成本
- 提升专业感

### 2. 代码简洁性
- 移除复杂的分页信息显示逻辑
- 移除每页数量选择器逻辑
- 减少 CSS 样式定义
- 代码更易维护

### 3. 性能优化
- 固定每页10条，减少大数据量加载
- 简化 DOM 结构
- 减少样式计算

### 4. 开发效率
- 新功能可直接复用巡检模块的分页实现
- 统一的代码模式
- 减少重复代码

## 迁移指南

如果需要在其他模块实现分页功能，参考以下步骤：

### 1. 定义数据结构
```javascript
currentPage: 1,
pageSize: 10,
totalCount: 0
```

### 2. 加载数据时计算 offset
```javascript
const offset = (this.currentPage - 1) * this.pageSize;
const params = new URLSearchParams({
    limit: this.pageSize,
    offset: offset
});
```

### 3. 渲染分页控件
```javascript
renderPagination() {
    const totalPages = Math.ceil(this.totalCount / this.pageSize);
    if (totalPages <= 1) return DOM.el('div');

    const container = DOM.el('div', {
        style: 'margin-top: 15px; display: flex; justify-content: center; gap: 10px;'
    });

    // 上一页按钮
    const prevBtn = DOM.el('button', {
        className: 'btn btn-sm btn-secondary',
        style: 'flex: 0 0 auto;',
        textContent: '上一页',
        disabled: this.currentPage === 1,
        onClick: () => this.goToPage(this.currentPage - 1)
    });
    container.appendChild(prevBtn);

    // 页码按钮（智能显示）
    for (let i = 1; i <= totalPages; i++) {
        if (i === 1 || i === totalPages ||
            (i >= this.currentPage - 2 && i <= this.currentPage + 2)) {
            const pageBtn = DOM.el('button', {
                className: `btn btn-sm ${i === this.currentPage ? 'btn-primary' : 'btn-secondary'}`,
                style: 'flex: 0 0 auto;',
                textContent: i,
                onClick: () => this.goToPage(i)
            });
            container.appendChild(pageBtn);
        } else if (i === this.currentPage - 3 || i === this.currentPage + 3) {
            const ellipsis = DOM.el('span', {
                style: 'padding: 0 5px; flex: 0 0 auto;',
                textContent: '...'
            });
            container.appendChild(ellipsis);
        }
    }

    // 下一页按钮
    const nextBtn = DOM.el('button', {
        className: 'btn btn-sm btn-secondary',
        style: 'flex: 0 0 auto;',
        textContent: '下一页',
        disabled: this.currentPage === totalPages,
        onClick: () => this.goToPage(this.currentPage + 1)
    });
    container.appendChild(nextBtn);

    return container;
}
```

### 4. 实现翻页方法
```javascript
async goToPage(page) {
    this.currentPage = page;
    await this.loadData();
}
```

## 参考实现

- **巡检模块**：`frontend/js/pages/inspection.js` (行 215-241)
- **告警模块**：`frontend/js/pages/alerts.js` (行 1100+)

## 总结

通过统一分页风格，DBClaw 实现了：
- ✅ 全系统一致的用户体验
- ✅ 更简洁的代码实现
- ✅ 更好的可维护性
- ✅ 更高的开发效率

建议后续所有需要分页的模块都采用此统一风格。
