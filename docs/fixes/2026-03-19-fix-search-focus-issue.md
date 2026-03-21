# 数据源选择器搜索框焦点问题修复

**日期**: 2026-03-19
**问题**: 在搜索框中输入字符时会失去焦点，导致无法连续输入
**状态**: ✅ 已修复

## 问题描述

用户在数据源选择器的搜索框中输入字符时，输入框会失去焦点，导致：
- 无法连续输入多个字符
- 每输入一个字符就需要重新点击搜索框
- 用户体验极差

## 问题原因

在原始实现中，搜索框的 `input` 事件处理函数调用了 `this.renderDropdown()`：

```javascript
searchInput.addEventListener('input', (e) => {
    this.searchQuery = e.target.value.toLowerCase();
    this.renderDropdown();  // ❌ 这会重新创建整个下拉面板，包括搜索框
});
```

`renderDropdown()` 方法会清空并重新创建整个下拉面板（`this.dropdown.innerHTML = ''`），包括搜索框本身。这导致：
1. 原来的搜索框 DOM 元素被销毁
2. 新的搜索框 DOM 元素被创建
3. 焦点丢失（因为原来获得焦点的元素已经不存在了）

## 解决方案

将下拉面板的渲染逻辑拆分为两部分：

### 1. `renderDropdown()` - 创建固定结构
只在初始化时调用，创建搜索框和数据源列表容器：

```javascript
renderDropdown() {
    const { searchable } = this.options;

    this.dropdown.innerHTML = '';

    // 搜索框（固定，不会被重新创建）
    if (searchable) {
        const searchBox = DOM.el('div', { className: 'datasource-selector-search' });
        this.searchInput = DOM.el('input', {
            type: 'text',
            placeholder: '搜索数据源...',
            className: 'datasource-selector-search-input',
            value: this.searchQuery
        });
        this.searchInput.addEventListener('input', (e) => {
            this.searchQuery = e.target.value.toLowerCase();
            this.renderItems();  // ✅ 只更新数据源列表
        });
        searchBox.appendChild(this.searchInput);
        this.dropdown.appendChild(searchBox);
    }

    // 数据源列表容器（固定）
    this.itemsContainer = DOM.el('div', { className: 'datasource-selector-items' });
    this.dropdown.appendChild(this.itemsContainer);

    // 渲染数据源列表
    this.renderItems();
}
```

### 2. `renderItems()` - 更新数据源列表
在搜索、选择等操作时调用，只更新数据源列表部分：

```javascript
renderItems() {
    const { groupByType, allowEmpty, emptyText } = this.options;

    this.itemsContainer.innerHTML = '';  // ✅ 只清空列表容器，不影响搜索框

    // 空选项
    if (allowEmpty && !this.options.multiple) {
        const emptyItem = this.createDatasourceItem(null, emptyText);
        this.itemsContainer.appendChild(emptyItem);
    }

    // 过滤数据源
    const filtered = this.filterDatasources();

    if (filtered.length === 0) {
        const empty = DOM.el('div', {
            className: 'datasource-selector-empty',
            textContent: this.searchQuery ? '未找到匹配的数据源' : '暂无数据源'
        });
        this.itemsContainer.appendChild(empty);
        return;
    }

    // 分组或列表显示
    if (groupByType) {
        this.renderGrouped(filtered);
    } else {
        this.renderList(filtered);
    }
}
```

### 3. 更新相关调用

将所有 `this.renderDropdown()` 调用（除了初始化）改为 `this.renderItems()`：

- 多选模式选择数据源后
- `setValue()` 方法中

## 代码变更

### 修改的文件

1. **frontend/js/components/datasource-selector.js**
   - 拆分 `renderDropdown()` 为两个方法
   - 更新 `renderGrouped()` 和 `renderList()` 使用 `itemsContainer`
   - 更新多选模式和 `setValue()` 中的调用

2. **frontend/css/datasource-selector.css**
   - 更新下拉面板样式，使用 `flex` 布局
   - 添加 `.datasource-selector-items` 容器样式
   - 更新滚动条样式应用到 `.datasource-selector-items`

### 新增的文件

- **frontend/test-search-focus.html** - 焦点问题测试页面

## 测试验证

### 自动化测试
访问测试页面：http://localhost:9939/test-search-focus.html

### 测试场景

1. **基础搜索功能**
   - ✅ 连续输入多个字符
   - ✅ 输入框保持焦点
   - ✅ 列表实时过滤

2. **多选模式搜索**
   - ✅ 选择数据源后搜索框保持焦点
   - ✅ 搜索内容不丢失

3. **快速输入测试**
   - ✅ 快速连续输入不丢失字符
   - ✅ 所有字符都被正确输入

4. **中文输入测试**
   - ✅ 中文输入法正常工作
   - ✅ 候选框正常显示

## 技术要点

### DOM 结构变化

**修复前：**
```
.datasource-selector-dropdown
  ├── .datasource-selector-search (每次搜索都重新创建)
  │   └── input
  ├── .datasource-selector-item (每次搜索都重新创建)
  ├── .datasource-selector-item
  └── ...
```

**修复后：**
```
.datasource-selector-dropdown
  ├── .datasource-selector-search (固定，只创建一次)
  │   └── input
  └── .datasource-selector-items (容器固定，内容动态更新)
      ├── .datasource-selector-item
      ├── .datasource-selector-item
      └── ...
```

### 关键改进

1. **搜索框持久化** - 搜索框 DOM 元素只创建一次，不会被销毁
2. **焦点保持** - 输入时不会重新创建输入框，焦点自然保持
3. **性能优化** - 只更新需要变化的部分（数据源列表），减少 DOM 操作
4. **用户体验** - 搜索框的 value 属性保持同步，即使重新打开下拉框也能看到之前的搜索内容

## 影响范围

- ✅ 不影响现有功能
- ✅ 不影响 API 接口
- ✅ 完全向后兼容
- ✅ 所有已集成页面无需修改

## 相关问题

这个问题是一个常见的 React/Vue 等框架中也会遇到的问题：
- **问题本质**: 在输入过程中重新渲染包含输入框的父容器
- **解决思路**: 将静态部分（输入框）和动态部分（列表）分离
- **最佳实践**: 只更新需要变化的最小 DOM 范围

## 后续优化建议

1. **防抖优化** - 可以考虑对搜索添加防抖，减少频繁的列表更新
2. **虚拟滚动** - 如果数据源数量非常大（>1000），可以考虑虚拟滚动
3. **键盘导航** - 添加上下键选择、回车确认等键盘快捷键

## 验证清单

- [x] 搜索框可以连续输入
- [x] 输入时不会失去焦点
- [x] 列表实时过滤正确
- [x] 多选模式正常工作
- [x] 中文输入法正常
- [x] 快速输入不丢失字符
- [x] 智能巡检页面正常工作
- [x] 示例页面正常工作
- [x] 无控制台错误

## 总结

通过将下拉面板的渲染逻辑拆分为固定结构（`renderDropdown`）和动态内容（`renderItems`），成功解决了搜索框焦点丢失的问题。这是一个典型的 DOM 操作优化案例，体现了"最小化 DOM 更新范围"的最佳实践。
