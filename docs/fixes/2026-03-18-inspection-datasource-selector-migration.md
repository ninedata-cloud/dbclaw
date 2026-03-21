# 智能巡检页面数据源选择器迁移

**日期**: 2026-03-18
**类型**: 功能增强
**影响范围**: 智能巡检页面 (inspection.js)

## 变更概述

将智能巡检页面的简单 select 数据源选择器迁移到新的 `DatasourceSelector` 组件，提供更好的用户体验。

## 变更内容

### 1. 组件引入

在页面对象中添加了 `datasourceSelector` 属性用于保存组件实例：

```javascript
const InspectionPage = {
    // ...
    datasourceSelector: null,
    // ...
};
```

### 2. HTML 结构变更

**之前**：
```html
<select id="filterDatasource" class="form-select" style="padding: 8px; border-radius: 4px; min-width: 360px;">
    <option value="">所有数据源</option>
</select>
```

**之后**：
```html
<div id="filterDatasource" style="min-width: 360px;"></div>
```

### 3. 数据源加载逻辑变更

**之前**：
```javascript
async loadDatasources() {
    const datasources = await API.getDatasources();
    const select = DOM.$('#filterDatasource');
    datasources.forEach(ds => {
        const option = DOM.el('option', { value: ds.id, textContent: `${ds.name} (${ds.db_type})` });
        select.appendChild(option);
    });
}
```

**之后**：
```javascript
async loadDatasources() {
    this.datasourceSelector = new DatasourceSelector({
        container: DOM.$('#filterDatasource'),
        allowEmpty: true,
        emptyText: '所有数据源',
        minWidth: '360px',
        maxWidth: '360px',
        showStatus: true,
        showDetails: true,
        onChange: (datasource) => {
            this.filters.datasource_id = datasource ? datasource.id : null;
            this.currentPage = 1;
            this.loadReports();
        }
    });
}
```

### 4. 筛选逻辑简化

移除了 "应用筛选" 按钮，数据源选择器的 `onChange` 回调直接触发筛选。

**之前**：
- 需要点击 "应用筛选" 按钮才能触发筛选
- `applyFilters()` 方法中包含数据源筛选逻辑

**之后**：
- 选择数据源后立即触发筛选
- `applyFilters()` 方法不再处理数据源筛选

### 5. 重置逻辑更新

**之前**：
```javascript
resetFilters() {
    this.filters = { datasource_id: null, status: null, trigger_type: null, start_date: null, end_date: null };
    DOM.$('#filterDatasource').value = '';
    // ...
}
```

**之后**：
```javascript
resetFilters() {
    this.filters = { datasource_id: null, status: null, trigger_type: null, start_date: null, end_date: null };

    // 重置数据源选择器
    if (this.datasourceSelector) {
        this.datasourceSelector.setValue(null);
    }
    // ...
}
```

### 6. 清理逻辑增强

在页面卸载时销毁组件实例：

```javascript
cleanup() {
    if (this.pollInterval) {
        clearInterval(this.pollInterval);
        this.pollInterval = null;
    }
    if (this.datasourceSelector) {
        this.datasourceSelector.destroy();
        this.datasourceSelector = null;
    }
}
```

## 新功能特性

迁移后，智能巡检页面的数据源选择器获得以下新功能：

1. **搜索过滤** - 可以搜索数据源名称、类型、主机等信息
2. **按类型分组** - 数据源按数据库类型（MySQL、PostgreSQL 等）自动分组
3. **连接状态显示** - 实时显示数据源的连接状态（绿色/红色/黄色指示器）
4. **详细信息展示** - 显示主机和端口信息
5. **即时筛选** - 选择后立即触发筛选，无需点击"应用"按钮
6. **更好的视觉效果** - 现代化的下拉面板设计

## 用户体验改进

1. **更快的筛选** - 选择数据源后立即生效，无需额外点击
2. **更容易找到数据源** - 搜索和分组功能让大量数据源更易管理
3. **更多信息** - 一眼就能看到数据源的类型、主机和连接状态
4. **更好的视觉反馈** - 选中状态、悬停效果等视觉反馈更清晰

## 测试要点

- [ ] 数据源列表正确加载
- [ ] 搜索功能正常工作
- [ ] 选择数据源后立即触发筛选
- [ ] 选择"所有数据源"显示所有报告
- [ ] 重置按钮正确清空数据源选择
- [ ] 连接状态指示器正确显示
- [ ] 按类型分组正确显示
- [ ] 页面卸载时组件正确销毁
- [ ] 无控制台错误

## 兼容性

- 完全向后兼容，不影响现有功能
- API 调用保持不变
- 筛选逻辑保持不变

## 后续计划

可以考虑将其他页面的数据源选择器也迁移到新组件：
- Monitor 页面
- Diagnosis 页面
- Alerts 页面
- Query 页面
- Dashboard 页面

## 相关文档

- [数据源选择器使用文档](../DATASOURCE_SELECTOR_GUIDE.md)
- [数据源选择器迁移指南](../DATASOURCE_SELECTOR_MIGRATION.md)
- [示例页面](/datasource-selector-demo.html)
