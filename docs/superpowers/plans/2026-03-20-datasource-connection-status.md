# 数据源连接状态展示 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在数据源管理列表中新增连接状态列，显示彩色徽章和最后检查时间，并提供一键刷新功能。

**Architecture:** 修改 frontend/js/pages/datasources.js 的表格渲染逻辑，添加状态配置映射和渲染代码；在 api.js 添加批量状态检查方法。保持现有代码风格，使用 inline styles。遵循 YAGNI，仅实现必要功能。

**Tech Stack:** Vanilla JavaScript, DOM manipulation, existing API wrapper, Lucide icons (if needed), Tailwind-like inline styles.

---

### Task 1: Add API method for bulk status check

**Files:**
- Modify: `frontend/js/api.js`

- [ ] **Step 1: Add the method to API object**
```js
    async checkAllDatasourceStatus() {
        return this.post('/api/datasources/check-status');
    },
```

- [ ] **Step 2: Test the method manually**
Run in browser console: `API.checkAllDatasourceStatus().then(console.log)`

- [ ] **Step 3: Commit**
```bash
git add frontend/js/api.js
git commit -m "feat: add checkAllDatasourceStatus API method"
```

### Task 2: Update datasources page with status column and config

**Files:**
- Modify: `frontend/js/pages/datasources.js:114-174` (around _renderTable)

- [ ] **Step 1: Add statusConfig object in _renderTable**
Add the statusConfig map with colors as designed.

- [ ] **Step 2: Update table header**
Add `<th>连接状态</th>` after 类型 column.

- [ ] **Step 3: Add status cell in row template**
Implement the statusHtml with dot, badge and time.

- [ ] **Step 4: Commit**
```bash
git add frontend/js/pages/datasources.js
git commit -m "feat: add connection status column to datasources table"
```

### Task 3: Add refresh button and wire up functionality

**Files:**
- Modify: `frontend/js/pages/datasources.js`

- [ ] **Step 1: Add refresh button in render()**
Add button next to filters or in header.

- [ ] **Step 2: Implement refresh handler**
Create `_refreshStatus()` method that calls API and re-renders.

- [ ] **Step 3: Update onclick handlers if needed**
Ensure button calls the new method.

- [ ] **Step 4: Commit**
```bash
git add frontend/js/pages/datasources.js
git commit -m "feat: add refresh connection status button"
```

### Task 4: Polish, test and verify

**Files:**
- Modify: `frontend/js/pages/datasources.js` (if needed)
- Test: Manually in browser

- [ ] **Step 1: Test all 4 status types**
Create test datasources or mock data to verify display.

- [ ] **Step 2: Test refresh button**
Verify it updates statuses and table refreshes without breaking filters.

- [ ] **Step 3: Verify responsive layout and Chinese text**
Check on different screen sizes.

- [ ] **Step 4: Final commit**
```bash
git add frontend/js/pages/datasources.js
git commit -m "feat: complete connection status display in datasource list"
```

**测试命令：**
- 启动应用：`python run.py`
- 访问数据源管理页面
- 验证状态列显示正确，刷新按钮工作正常

**完成后**：使用 superpowers:verification-before-completion 验证。
