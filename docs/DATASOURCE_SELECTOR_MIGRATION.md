# 数据源选择器迁移指南

本文档指导如何将现有页面中的简单 select 元素迁移到新的 `DatasourceSelector` 组件。

## 迁移概述

新的 `DatasourceSelector` 组件提供了更强大的功能和更好的用户体验，包括：
- 搜索过滤
- 按类型分组
- 连接状态显示
- 详细信息展示
- 统一的样式和交互

## 迁移步骤

### 1. 确认已引入组件文件

确保在 `index.html` 中已引入：

```html
<!-- CSS -->
<link rel="stylesheet" href="/css/datasource-selector.css">

<!-- JavaScript -->
<script src="/js/components/datasource-selector.js"></script>
```

### 2. 识别需要迁移的代码

查找以下模式的代码：

```javascript
// 模式 1：手动创建 select 元素
const select = DOM.el('select', { className: 'form-select' });
select.appendChild(DOM.el('option', { value: '', textContent: '选择数据源...' }));

// 模式 2：HTML 中的 select 元素
<select id="datasourceSelect" class="form-select">
    <option value="">选择数据源...</option>
</select>

// 模式 3：动态填充数据源
const datasources = await API.getDatasources();
datasources.forEach(ds => {
    const option = DOM.el('option', { value: ds.id, textContent: `${ds.name} (${ds.db_type})` });
    select.appendChild(option);
});
```

## 具体页面迁移示例

### Monitor 页面 (monitor.js)

**迁移前：**

```javascript
// Connection selector
const connSelect = DOM.el('select', { className: 'form-select', style: { minWidth: '200px', maxWidth: '300px', flex: '1' } });
connSelect.appendChild(DOM.el('option', { value: '', textContent: '选择数据源...' }));
for (const c of connections) {
    const opt = DOM.el('option', { value: c.id, textContent: `${c.name} (${c.db_type})` });
    if (conn && c.id === conn.id) opt.selected = true;
    connSelect.appendChild(opt);
}
connSelect.addEventListener('change', async () => {
    const id = parseInt(connSelect.value);
    if (id) {
        const conns = Store.get('datasources') || [];
        const selected = conns.find(c => c.id === id);
        Store.set('currentConnection', selected);
        this._reloadData(id);
    }
});
headerActions.appendChild(connSelect);
```

**迁移后：**

```javascript
// Connection selector
const connSelectorContainer = DOM.el('div', { style: { minWidth: '200px', maxWidth: '300px', flex: '1' } });
const connSelector = new DatasourceSelector({
    container: connSelectorContainer,
    placeholder: '选择数据源...',
    allowEmpty: false,
    onChange: (datasource) => {
        if (datasource) {
            Store.set('currentConnection', datasource);
            this._reloadData(datasource.id);
        }
    },
    onLoad: (datasources) => {
        // 设置默认选中
        const conn = Store.get('currentConnection');
        if (conn) {
            connSelector.setValue(conn.id);
        } else if (datasources.length > 0) {
            connSelector.setValue(datasources[0].id);
        }
    }
});
headerActions.appendChild(connSelectorContainer);
```

### Diagnosis 页面 (diagnosis.js)

**迁移前：**

```javascript
const connSelect = DOM.el('select', { className: 'form-select', style: { minWidth: '200px', maxWidth: '300px', flex: '1' } });
connSelect.appendChild(DOM.el('option', { value: '', textContent: '选择数据源...' }));

try {
    const datasources = await API.getDatasources();
    Store.set('datasources', datasources);
    const current = Store.get('currentDatasource');
    for (const c of datasources) {
        const opt = DOM.el('option', { value: c.id, textContent: `${c.name} (${c.db_type})` });
        if (current && c.id === current.id) opt.selected = true;
        connSelect.appendChild(opt);
    }
} catch (e) { /* ignore */ }

connSelect.addEventListener('change', () => {
    const id = parseInt(connSelect.value);
    if (id) {
        const conns = Store.get('datasources') || [];
        Store.set('currentDatasource', conns.find(c => c.id === id));
    }
});
```

**迁移后：**

```javascript
const connSelectorContainer = DOM.el('div', { style: { minWidth: '200px', maxWidth: '300px', flex: '1' } });
const connSelector = new DatasourceSelector({
    container: connSelectorContainer,
    placeholder: '选择数据源...',
    allowEmpty: false,
    onChange: (datasource) => {
        if (datasource) {
            Store.set('currentDatasource', datasource);
        }
    },
    onLoad: (datasources) => {
        Store.set('datasources', datasources);
        const current = Store.get('currentDatasource');
        if (current) {
            connSelector.setValue(current.id);
        }
    }
});
```

### Inspection 页面 (inspection.js)

**迁移前：**

```javascript
<div>
    <label style="display:block;font-size:12px;margin-bottom:4px;color:var(--text-muted);">数据源</label>
    <select id="filterDatasource" class="form-select" style="padding: 8px; border-radius: 4px; min-width: 360px;">
        <option value="">所有数据源</option>
    </select>
</div>

// ...

async loadDatasources() {
    const datasources = await API.getDatasources();
    const select = DOM.$('#filterDatasource');
    datasources.forEach(ds => {
        const option = DOM.el('option', { value: ds.id, textContent: `${ds.name} (${ds.db_type})` });
        select.appendChild(option);
    });
}

// ...

applyFilters() {
    this.filters.datasource_id = DOM.$('#filterDatasource')?.value || null;
    // ...
}
```

**迁移后：**

```javascript
<div>
    <label style="display:block;font-size:12px;margin-bottom:4px;color:var(--text-muted);">数据源</label>
    <div id="filterDatasource" style="min-width: 360px;"></div>
</div>

// ...

async loadDatasources() {
    this.datasourceSelector = new DatasourceSelector({
        container: DOM.$('#filterDatasource'),
        allowEmpty: true,
        emptyText: '所有数据源',
        onChange: (datasource) => {
            this.filters.datasource_id = datasource ? datasource.id : null;
            this.currentPage = 1;
            this.loadReports();
        }
    });
}

// 不再需要 applyFilters 中的数据源处理代码
```

### Alerts 页面 (alerts.js)

**迁移前：**

```javascript
const datasourceSelect = DOM.el('select', {
    id: 'filterDatasource',
    className: 'form-select',
    style: { padding: '8px', borderRadius: '4px', minWidth: '200px' }
});
datasourceSelect.appendChild(DOM.el('option', { value: '', textContent: '所有数据源' }));

const datasources = await API.getDatasources();
datasources.forEach(ds => {
    const option = DOM.el('option', { value: ds.id, textContent: `${ds.name} (${ds.db_type})` });
    datasourceSelect.appendChild(option);
});

datasourceSelect.addEventListener('change', () => {
    this.applyFilters();
});
```

**迁移后：**

```javascript
const datasourceSelectorContainer = DOM.el('div', {
    style: { minWidth: '200px', maxWidth: '300px' }
});

const datasourceSelector = new DatasourceSelector({
    container: datasourceSelectorContainer,
    allowEmpty: true,
    emptyText: '所有数据源',
    onChange: (datasource) => {
        this.filters.datasource_id = datasource ? datasource.id : null;
        this.applyFilters();
    }
});
```

## 迁移检查清单

完成迁移后，请检查以下项目：

- [ ] 组件正常显示
- [ ] 数据源列表正确加载
- [ ] 搜索功能正常工作
- [ ] 选择变化时触发正确的回调
- [ ] 默认选中项正确设置
- [ ] 样式与页面整体风格一致
- [ ] 响应式布局正常
- [ ] 无控制台错误

## 常见迁移问题

### 问题 1：如何保持原有的默认选中逻辑？

**解决方案：** 使用 `onLoad` 回调设置默认值

```javascript
const selector = new DatasourceSelector({
    container: container,
    onLoad: (datasources) => {
        // 从 Store 获取之前选中的
        const current = Store.get('currentDatasource');
        if (current) {
            selector.setValue(current.id);
        } else if (datasources.length > 0) {
            // 默认选中第一个
            selector.setValue(datasources[0].id);
        }
    }
});
```

### 问题 2：如何在筛选场景中使用？

**解决方案：** 使用 `allowEmpty: true` 和 `emptyText`

```javascript
const selector = new DatasourceSelector({
    container: container,
    allowEmpty: true,
    emptyText: '所有数据源',
    onChange: (datasource) => {
        if (datasource) {
            // 按数据源筛选
            filterByDatasource(datasource.id);
        } else {
            // 显示所有
            showAll();
        }
    }
});
```

### 问题 3：如何获取选中的数据源 ID？

**解决方案：** 在 `onChange` 回调中直接使用 `datasource.id`

```javascript
onChange: (datasource) => {
    const id = datasource ? datasource.id : null;
    // 使用 id
}
```

### 问题 4：如何在页面卸载时清理组件？

**解决方案：** 在页面的 cleanup 函数中调用 `destroy()`

```javascript
const MyPage = {
    selector: null,

    async render() {
        this.selector = new DatasourceSelector({ ... });

        // 返回 cleanup 函数
        return () => this.cleanup();
    },

    cleanup() {
        if (this.selector) {
            this.selector.destroy();
            this.selector = null;
        }
    }
};
```

### 问题 5：如何处理数据源列表刷新？

**解决方案：** 调用 `refresh()` 方法

```javascript
// 在需要刷新的地方
await selector.refresh();
```

## 性能优化建议

1. **避免频繁创建和销毁**：在页面级别保持组件实例，只在页面卸载时销毁

2. **使用 filter 选项**：如果只需要特定类型的数据源，使用 `filter` 选项而不是加载所有数据源后再过滤

3. **合理使用 showDetails**：在空间有限的场景中关闭详细信息显示以提升性能

## 批量迁移脚本

如果需要迁移多个页面，可以使用以下脚本辅助：

```bash
#!/bin/bash
# 查找所有使用旧模式的文件
grep -r "DOM.el('select'" frontend/js/pages/ | grep datasource
```

## 迁移时间估算

- 简单页面（1 个选择器）：5-10 分钟
- 中等页面（2-3 个选择器）：15-20 分钟
- 复杂页面（多个选择器 + 复杂逻辑）：30-45 分钟

## 需要迁移的页面清单

根据代码分析，以下页面需要迁移：

- [x] Monitor 页面 (monitor.js) - 1 个选择器
- [x] Diagnosis 页面 (diagnosis.js) - 1 个选择器
- [x] Inspection 页面 (inspection.js) - 1 个选择器
- [ ] Alerts 页面 (alerts.js) - 1 个选择器
- [ ] Query 页面 (query.js) - 可能需要
- [ ] Dashboard 页面 (dashboard.js) - 可能需要

## 获取帮助

如果在迁移过程中遇到问题，请参考：

1. [数据源选择器使用文档](./DATASOURCE_SELECTOR_GUIDE.md)
2. `docs/archive/manual-checks/frontend/datasource-selector-demo.html`
3. 查看已迁移页面的代码作为参考
