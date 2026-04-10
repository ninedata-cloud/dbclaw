# 数据源选择器组件使用文档

## 概述

`DatasourceSelector` 是一个功能强大、高度可定制的数据源下拉选择组件，适用于 SmartDBA 项目的各个模块。

## 功能特性

- ✅ **搜索过滤**：支持实时搜索数据源名称、类型、主机等信息
- ✅ **按类型分组**：自动按数据库类型（MySQL、PostgreSQL 等）分组显示
- ✅ **连接状态显示**：实时显示数据源的连接状态（成功/错误/警告）
- ✅ **多选模式**：支持单选和多选两种模式
- ✅ **详细信息展示**：可选显示主机、端口、描述等详细信息
- ✅ **自定义过滤**：支持自定义过滤函数，只显示特定类型的数据源
- ✅ **响应式设计**：适配不同屏幕尺寸
- ✅ **程序控制**：提供完整的 API 用于程序化控制
- ✅ **样式可定制**：支持自定义宽度、样式等

## 快速开始

### 1. 引入文件

在 HTML 中引入必要的文件：

```html
<!-- CSS -->
<link rel="stylesheet" href="/css/datasource-selector.css">

<!-- JavaScript -->
<script src="/js/components/datasource-selector.js"></script>
```

### 2. 基础使用

```javascript
// 创建一个基础的单选选择器
const selector = new DatasourceSelector({
    container: document.getElementById('my-container'),
    placeholder: '请选择数据源',
    onChange: (datasource) => {
        console.log('选中的数据源:', datasource);
    }
});
```

### 3. HTML 结构

```html
<div id="my-container"></div>
```

## 配置选项

### 完整配置示例

```javascript
const selector = new DatasourceSelector({
    // 必需参数
    container: document.getElementById('container'),  // 容器元素

    // 基础配置
    placeholder: '选择数据源',      // 占位符文本
    multiple: false,                // 是否多选
    allowEmpty: true,               // 是否允许不选择
    emptyText: '所有数据源',        // 空选项文本
    disabled: false,                // 是否禁用

    // 显示配置
    searchable: true,               // 是否可搜索
    groupByType: true,              // 是否按数据库类型分组
    showStatus: true,               // 是否显示连接状态
    showDetails: true,              // 是否显示详细信息（主机、端口）
    showDescription: false,         // 是否显示描述

    // 样式配置
    minWidth: '200px',              // 最小宽度
    maxWidth: '400px',              // 最大宽度

    // 功能配置
    filter: null,                   // 自定义过滤函数
    onChange: null,                 // 选择变化回调
    onLoad: null                    // 数据加载完成回调
});
```

### 配置项说明

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `container` | HTMLElement | - | **必需**，组件容器元素 |
| `placeholder` | string | '选择数据源' | 占位符文本 |
| `multiple` | boolean | false | 是否多选模式 |
| `searchable` | boolean | true | 是否显示搜索框 |
| `groupByType` | boolean | true | 是否按数据库类型分组 |
| `showStatus` | boolean | true | 是否显示连接状态指示器 |
| `showDetails` | boolean | true | 是否显示主机和端口信息 |
| `showDescription` | boolean | false | 是否显示数据源描述 |
| `allowEmpty` | boolean | true | 是否允许不选择（显示空选项） |
| `emptyText` | string | '所有数据源' | 空选项的显示文本 |
| `disabled` | boolean | false | 是否禁用组件 |
| `filter` | function | null | 自定义过滤函数 `(datasource) => boolean` |
| `onChange` | function | null | 选择变化回调 `(datasource\|datasources) => void` |
| `onLoad` | function | null | 数据加载完成回调 `(datasources) => void` |
| `minWidth` | string | '200px' | 组件最小宽度 |
| `maxWidth` | string | '400px' | 组件最大宽度 |

## 使用场景

### 场景 1：基础单选

```javascript
const selector = new DatasourceSelector({
    container: document.getElementById('datasource-selector'),
    placeholder: '请选择数据源',
    onChange: (datasource) => {
        if (datasource) {
            console.log(`选中: ${datasource.name} (${datasource.db_type})`);
            // 执行后续操作
            loadMetrics(datasource.id);
        }
    }
});
```

### 场景 2：多选模式

```javascript
const multiSelector = new DatasourceSelector({
    container: document.getElementById('multi-selector'),
    multiple: true,
    onChange: (datasources) => {
        console.log(`已选择 ${datasources.length} 个数据源`);
        datasources.forEach(ds => {
            console.log(`- ${ds.name}`);
        });
    }
});
```

### 场景 3：带空选项（用于筛选）

```javascript
const filterSelector = new DatasourceSelector({
    container: document.getElementById('filter-selector'),
    allowEmpty: true,
    emptyText: '所有数据源',
    onChange: (datasource) => {
        if (datasource) {
            // 按数据源筛选
            filterByDatasource(datasource.id);
        } else {
            // 显示所有数据源的数据
            showAllDatasources();
        }
    }
});
```

### 场景 4：自定义过滤（只显示特定类型）

```javascript
// 只显示 MySQL 数据源
const mysqlSelector = new DatasourceSelector({
    container: document.getElementById('mysql-selector'),
    filter: (ds) => ds.db_type.toLowerCase() === 'mysql',
    placeholder: '选择 MySQL 数据源'
});

// 只显示关系型数据库
const rdbmsSelector = new DatasourceSelector({
    container: document.getElementById('rdbms-selector'),
    filter: (ds) => ['mysql', 'postgresql', 'oracle', 'sqlserver'].includes(ds.db_type.toLowerCase()),
    placeholder: '选择关系型数据库'
});
```

### 场景 5：显示详细信息

```javascript
const detailedSelector = new DatasourceSelector({
    container: document.getElementById('detailed-selector'),
    showDetails: true,        // 显示主机和端口
    showDescription: true,    // 显示描述
    showStatus: true,         // 显示连接状态
    maxWidth: '500px'         // 增加宽度以容纳更多信息
});
```

### 场景 6：程序化控制

```javascript
const selector = new DatasourceSelector({
    container: document.getElementById('selector'),
    onChange: (ds) => console.log('选中:', ds)
});

// 获取当前选中值
const selected = selector.getValue();

// 设置选中值
selector.setValue(datasourceId);

// 清空选择
selector.setValue(null);

// 刷新数据源列表
await selector.refresh();

// 禁用/启用
selector.setDisabled(true);
selector.setDisabled(false);

// 销毁组件
selector.destroy();
```

## API 方法

### getValue()

获取当前选中的数据源。

```javascript
const selected = selector.getValue();

// 单选模式：返回 datasource 对象或 null
// 多选模式：返回 datasource 对象数组
```

### setValue(value)

设置选中的数据源。

```javascript
// 单选模式：传入数据源 ID
selector.setValue(1);

// 多选模式：传入数据源 ID 数组
selector.setValue([1, 2, 3]);

// 清空选择
selector.setValue(null);
```

### refresh()

刷新数据源列表（重新从 API 加载）。

```javascript
await selector.refresh();
```

### setDisabled(disabled)

设置组件的禁用状态。

```javascript
selector.setDisabled(true);   // 禁用
selector.setDisabled(false);  // 启用
```

### destroy()

销毁组件，清理事件监听器。

```javascript
selector.destroy();
```

## 集成到现有页面

### 替换现有的简单 select

**之前的代码：**

```javascript
const select = DOM.el('select', { className: 'form-select' });
select.appendChild(DOM.el('option', { value: '', textContent: '选择数据源...' }));

const datasources = await API.getDatasources();
datasources.forEach(ds => {
    const option = DOM.el('option', {
        value: ds.id,
        textContent: `${ds.name} (${ds.db_type})`
    });
    select.appendChild(option);
});

select.addEventListener('change', () => {
    const id = parseInt(select.value);
    // 处理选择变化
});
```

**使用新组件：**

```javascript
const container = DOM.el('div');
const selector = new DatasourceSelector({
    container: container,
    placeholder: '选择数据源...',
    onChange: (datasource) => {
        if (datasource) {
            // 处理选择变化
            const id = datasource.id;
        }
    }
});
```

### 在 Monitor 页面中使用

```javascript
// 在 MonitorPage.render() 中
const selectorContainer = DOM.el('div');
const selector = new DatasourceSelector({
    container: selectorContainer,
    minWidth: '200px',
    maxWidth: '300px',
    onChange: (datasource) => {
        if (datasource) {
            Store.set('currentConnection', datasource);
            this._reloadData(datasource.id);
        }
    }
});

headerActions.appendChild(selectorContainer);
```

### 在 Inspection 页面中使用

```javascript
// 在 InspectionPage.render() 中
const filterContainer = DOM.el('div');
const selector = new DatasourceSelector({
    container: filterContainer,
    allowEmpty: true,
    emptyText: '所有数据源',
    minWidth: '360px',
    onChange: (datasource) => {
        this.filters.datasource_id = datasource ? datasource.id : null;
        this.currentPage = 1;
        this.loadReports();
    }
});
```

## 样式定制

### CSS 变量

组件使用 CSS 变量，可以通过修改这些变量来定制样式：

```css
:root {
    --primary-color: #3b82f6;
    --bg-primary: #1a1a1a;
    --bg-secondary: #2a2a2a;
    --bg-hover: #333333;
    --text-primary: #ffffff;
    --text-muted: #999999;
    --border-color: #404040;
}
```

### 自定义样式

```css
/* 修改按钮样式 */
.datasource-selector-button {
    border-radius: 8px;
    padding: 10px 14px;
}

/* 修改下拉面板样式 */
.datasource-selector-dropdown {
    border-radius: 8px;
    box-shadow: 0 8px 16px rgba(0, 0, 0, 0.2);
}

/* 修改选项样式 */
.datasource-selector-item:hover {
    background: rgba(59, 130, 246, 0.2);
}
```

## 最佳实践

1. **合理使用 allowEmpty**：在筛选场景中使用 `allowEmpty: true`，在必选场景中使用 `allowEmpty: false`

2. **根据场景选择显示选项**：
   - 空间充足时启用 `showDetails` 和 `showDescription`
   - 空间有限时只显示基本信息

3. **使用自定义过滤**：当页面只需要特定类型的数据源时，使用 `filter` 选项而不是在 onChange 中过滤

4. **响应式宽度**：使用 `minWidth` 和 `maxWidth` 确保组件在不同屏幕尺寸下都能正常显示

5. **及时销毁**：在页面卸载时调用 `destroy()` 方法清理资源

## 示例页面

历史交互式示例已归档到 `docs/archive/manual-checks/frontend/datasource-selector-demo.html`。

## 浏览器兼容性

- Chrome/Edge 90+
- Firefox 88+
- Safari 14+

## 常见问题

### Q: 如何获取选中数据源的完整信息？

A: 使用 `getValue()` 方法返回完整的数据源对象，包含所有字段。

### Q: 如何在组件初始化时设置默认选中项？

A: 在组件创建后调用 `setValue()` 方法：

```javascript
const selector = new DatasourceSelector({ ... });
selector.setValue(defaultDatasourceId);
```

### Q: 如何监听数据源列表加载完成？

A: 使用 `onLoad` 回调：

```javascript
const selector = new DatasourceSelector({
    container: container,
    onLoad: (datasources) => {
        console.log(`加载了 ${datasources.length} 个数据源`);
        // 设置默认选中第一个
        if (datasources.length > 0) {
            selector.setValue(datasources[0].id);
        }
    }
});
```

### Q: 如何实现级联选择（选择数据源后自动加载相关数据）？

A: 在 `onChange` 回调中执行后续操作：

```javascript
const selector = new DatasourceSelector({
    container: container,
    onChange: async (datasource) => {
        if (datasource) {
            // 加载该数据源的相关数据
            await loadDatasourceMetrics(datasource.id);
            await loadDatasourceTables(datasource.id);
        }
    }
});
```

## 更新日志

### v1.0.0 (2026-03-18)

- 初始版本发布
- 支持单选和多选模式
- 支持搜索和分组
- 支持连接状态显示
- 支持自定义过滤
- 完整的 API 支持
