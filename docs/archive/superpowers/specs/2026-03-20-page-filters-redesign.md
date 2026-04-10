# 页面过滤器统一样式设计

## 目标

将数据源管理、主机管理、技能管理、系统参数配置四个模块的过滤条件调整到顶部，参考智能巡检页面的样式，实现视觉统一和自适应布局。

## 现状

| 页面 | 当前过滤器位置 | 样式 |
|------|--------------|------|
| 智能巡检 | Header 右侧 | `dashboard-filters` + `filter-select`/`filter-input` ✅ |
| 数据源管理 | 内容区顶部 | 内联样式，分散布局 ❌ |
| 主机管理 | 内容区顶部 | 内联样式，分散布局 ❌ |
| 技能管理 | 内容区顶部 | `skills-filters` + `search-box` ❌ |
| 系统参数配置 | 内容区表格上方 | 内联样式 ❌ |

## 设计方案

### 统一样式

复用 `dashboard.css` 中的 `dashboard-filters` + `filter-select` + `filter-input` 样式体系：

```css
.dashboard-filters {
    display: flex;
    align-items: center;
    gap: 8px;
}

.filter-select,
.filter-input {
    height: 32px;
    padding: 0 10px;
    font-size: 13px;
    border: 1px solid var(--border-color);
    border-radius: 4px;
    background: var(--bg-primary);
    color: var(--text-primary);
}
```

### 自适应布局

| 过滤器数量 | 布局方式 |
|-----------|---------|
| 1-2个 | 单行紧凑排列 |
| 3-4个 | 单行允许换行 |
| 5个以上 | 换行布局，响应式 |

```css
.page-filters {
    display: flex;
    align-items: center;
    gap: 8px;
    flex-wrap: wrap;
    padding: 12px 16px;
    background: var(--background-secondary);
    border-bottom: 1px solid var(--border-color);
    margin-bottom: 16px;
}
```

## 实施步骤

1. **CSS**: `dashboard.css` 添加 `.page-filters` 响应式容器样式
2. **数据源管理**: 将 `filterBar` 迁移到 Header filters 方式
3. **主机管理**: 将 `filterBar` 迁移到 Header filters 方式
4. **技能管理**: 统一 `skills-filters` 样式，复用 filter-select 样式
5. **系统参数配置**: 统一 `configs-filters` 样式，复用 filter-select 样式

## 涉及文件

- `frontend/css/dashboard.css`
- `frontend/js/pages/datasources.js`
- `frontend/js/pages/hosts.js`
- `frontend/js/pages/skills.js`
- `frontend/js/pages/system-configs.js`
