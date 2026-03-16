# 数据源选择器宽度更新总结

## 问题描述
前端界面中的数据源下拉框宽度不足，无法完整显示较长的数据源名称，影响用户体验。

## 修改内容

### 页面级修改

已将以下页面中的数据源选择器最小宽度从 200px 增加到 400px：

1. **Monitor Page** (`frontend/js/pages/monitor.js:37`)
   - 修改前: `minWidth: '200px'`
   - 修改后: `minWidth: '400px'`

2. **Query Page** (`frontend/js/pages/query.js:26`)
   - 修改前: `minWidth: '200px'`
   - 修改后: `minWidth: '400px'`

3. **Diagnosis Page** (`frontend/js/pages/diagnosis.js:20`)
   - 修改前: `minWidth: '200px'`
   - 修改后: `minWidth: '400px'`

4. **Inspection Page** (`frontend/js/pages/inspection.js:24`)
   - 修改前: `min-width: 180px`
   - 修改后: `min-width: 360px`
   - 注：此页面为筛选器，宽度设置为 360px 以适应布局

5. **Skills Page** (`frontend/js/pages/skills.js:195`)
   - 修改前: 无宽度限制
   - 修改后: `min-width: 400px`

### CSS 级修改

在 `frontend/css/main.css` 中添加了专用样式类：

```css
.form-select.datasource-select { min-width: 400px; }
```

此样式类可用于未来需要添加数据源选择器的新页面，只需添加 `datasource-select` 类即可。

## 修改原则

1. **主要页面**（Monitor, Query, Diagnosis）：使用 400px 最小宽度
2. **筛选器页面**（Inspection）：使用 360px 最小宽度，避免布局过宽
3. **参数表单**（Skills）：使用 400px 最小宽度

## 影响范围

- 所有包含数据源选择器的页面
- 不影响其他类型的下拉框（如状态、类型等筛选器）
- 响应式布局仍然正常工作（使用 min-width 而非固定 width）

## 测试建议

1. 在各个页面测试长数据源名称的显示效果
2. 验证在不同屏幕尺寸下的布局表现
3. 确认下拉框展开时选项文本完整显示

## 未来改进

如需统一管理所有数据源选择器样式，可以：
1. 使用 CSS 类 `datasource-select` 替代内联样式
2. 在组件级别封装数据源选择器
