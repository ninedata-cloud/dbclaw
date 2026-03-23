# 资源大盘重新设计实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将资源大盘重新设计为深蓝专业风 + 玻璃拟态的科技感界面，顶部三栏概览 + 异常资源自动置顶并高亮。

**Architecture:** 纯前端改动。重写 `dashboard.css`（全新深色样式）和 `dashboard.js`（重写渲染逻辑）。布局：顶部三栏概览（主机健康/活跃告警/数据库健康）+ 异常置顶区 + 正常资源网格。所有数据通过现有 API 获取，15s 自动刷新。

**Tech Stack:** 原生 JavaScript（无框架），CSS 变量，SVG 内联环形图，无构建步骤。

**Spec:** `docs/superpowers/specs/2026-03-22-dashboard-redesign-design.md`

---

## 文件改动

- **修改**：`frontend/css/dashboard.css` — 完全重写，深色科技感样式
- **修改**：`frontend/js/pages/dashboard.js` — 完全重写，新渲染逻辑

---

## Task 1: 重写 dashboard.css

**Files:**
- Modify: `frontend/css/dashboard.css`

- [ ] **Step 1: 将 dashboard.css 完全替换为新的深色样式**

用 Write 工具替换 `frontend/css/dashboard.css` 全部内容为以下 CSS：

```css
/* ===== Dashboard - Tech Dark Theme ===== */

.dashboard-overview {
    display: grid;
    grid-template-columns: 1fr 1fr 1fr;
    background: rgba(255,255,255,0.03);
    backdrop-filter: blur(12px);
    -webkit-backdrop-filter: blur(12px);
    border: 1px solid rgba(255,255,255,0.08);
    border-radius: 12px;
    margin-bottom: 24px;
    overflow: hidden;
}

.overview-panel { padding: 24px; }
.overview-panel + .overview-panel { border-left: 1px solid rgba(255,255,255,0.06); }

.overview-panel-title {
    font-size: 11px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    color: rgba(255,255,255,0.35);
    margin-bottom: 16px;
}

.donut-container { display: flex; align-items: center; gap: 20px; margin-bottom: 14px; }

.donut-center-text {
    font-size: 26px; font-weight: 700;
    font-variant-numeric: tabular-nums;
    fill: #f0f6ff;
    dominant-baseline: middle; text-anchor: middle;
}

.donut-legend { flex: 1; min-width: 0; }

.donut-legend-item {
    display: flex; align-items: center; gap: 8px;
    font-size: 13px; color: rgba(255,255,255,0.65);
    margin-bottom: 6px;
    font-variant-numeric: tabular-nums;
}

.donut-legend-dot { width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; }

.anomaly-host-list { display: flex; flex-direction: column; gap: 5px; }

.anomaly-host-item {
    display: flex; align-items: center; gap: 8px;
    font-size: 12px; color: rgba(255,255,255,0.55);
    white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}

.status-dot { width: 6px; height: 6px; border-radius: 50%; flex-shrink: 0; }
.status-dot.healthy { background: #3fb950; }
.status-dot.warning { background: #d29922; }
.status-dot.error   { background: #f85149; }
.status-dot.offline { background: #f85149; }
.status-dot.unknown { background: rgba(255,255,255,0.3); }

.all-healthy-text {
    font-size: 13px; color: #3fb950;
    display: flex; align-items: center; gap: 6px;
}

.alert-list {
    display: flex; flex-direction: column; gap: 8px;
    max-height: 130px; overflow-y: auto;
}
.alert-list::-webkit-scrollbar { width: 3px; }
.alert-list::-webkit-scrollbar-track { background: transparent; }
.alert-list::-webkit-scrollbar-thumb { background: rgba(255,255,255,0.15); border-radius: 2px; }

.alert-list-item { display: flex; align-items: flex-start; gap: 8px; font-size: 12px; line-height: 1.4; }

.alert-severity-bar {
    width: 3px; min-height: 32px; border-radius: 2px;
    flex-shrink: 0; margin-top: 2px; align-self: stretch;
}
.alert-severity-bar.critical, .alert-severity-bar.high { background: #f85149; }
.alert-severity-bar.medium { background: #d29922; }
.alert-severity-bar.low    { background: #58a6ff; }

.alert-content { flex: 1; min-width: 0; }
.alert-title { color: rgba(255,255,255,0.82); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.alert-time  { color: rgba(255,255,255,0.3); font-size: 11px; margin-top: 2px; }

.alert-count-badge {
    display: inline-flex; align-items: center; justify-content: center;
    min-width: 20px; height: 18px; padding: 0 6px;
    background: rgba(248,81,73,0.2); color: #f85149;
    border-radius: 9px; font-size: 11px; font-weight: 600;
    margin-left: 8px; vertical-align: middle;
    font-variant-numeric: tabular-nums;
}

.no-alerts-text {
    font-size: 13px; color: #3fb950;
    display: flex; align-items: center; gap: 6px; padding-top: 4px;
}

.db-type-list { display: grid; grid-template-columns: 1fr 1fr; gap: 6px 16px; margin-top: 4px; }

.db-type-item {
    display: flex; align-items: center; gap: 6px;
    font-size: 12px; color: rgba(255,255,255,0.55);
    font-variant-numeric: tabular-nums;
}

.db-type-dot { width: 8px; height: 8px; border-radius: 2px; flex-shrink: 0; }

.live-indicator {
    display: flex; align-items: center; gap: 8px;
    font-size: 12px; color: rgba(255,255,255,0.35);
    font-variant-numeric: tabular-nums;
}

.live-dot {
    width: 7px; height: 7px; border-radius: 50%;
    background: #3fb950; flex-shrink: 0;
    animation: live-pulse 2s ease-in-out infinite;
}

@keyframes live-pulse {
    0%, 100% { opacity: 1; }
    50%       { opacity: 0.3; }
}

.resource-section { margin-bottom: 24px; }

.resource-section-header {
    display: flex; align-items: center; gap: 10px;
    margin-bottom: 14px; font-size: 13px; font-weight: 600;
}
.resource-section-header.anomaly { color: #f85149; }
.resource-section-header.normal  { color: rgba(255,255,255,0.45); }

.resource-count-badge {
    display: inline-flex; align-items: center; justify-content: center;
    min-width: 22px; height: 20px; padding: 0 7px;
    border-radius: 10px; font-size: 11px; font-weight: 600;
    font-variant-numeric: tabular-nums;
}
.resource-count-badge.anomaly { background: rgba(248,81,73,0.2); color: #f85149; }
.resource-count-badge.normal  { background: rgba(255,255,255,0.08); color: rgba(255,255,255,0.4); }

.dashboard-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
    gap: 14px;
}

.dash-card {
    background: rgba(255,255,255,0.04);
    backdrop-filter: blur(12px);
    -webkit-backdrop-filter: blur(12px);
    border: 1px solid rgba(255,255,255,0.08);
    border-radius: 10px;
    padding: 16px;
    cursor: pointer;
    transition: transform 0.15s ease, border-color 0.15s ease, box-shadow 0.15s ease;
}

.dash-card:hover {
    transform: translateY(-2px);
    border-color: rgba(88,166,255,0.3);
    box-shadow: 0 8px 24px rgba(0,0,0,0.35);
}

.dash-card.status-critical,
.dash-card.status-error {
    border-color: rgba(248,81,73,0.55);
    box-shadow: 0 0 16px rgba(248,81,73,0.18);
}
.dash-card.status-critical:hover,
.dash-card.status-error:hover { box-shadow: 0 0 24px rgba(248,81,73,0.32); }

.dash-card.status-warning {
    border-color: rgba(210,153,34,0.55);
    box-shadow: 0 0 16px rgba(210,153,34,0.12);
}
.dash-card.status-warning:hover { box-shadow: 0 0 24px rgba(210,153,34,0.28); }

.dash-card-header {
    display: flex; align-items: center;
    justify-content: space-between; gap: 8px; margin-bottom: 5px;
}

.dash-card-name {
    font-size: 14px; font-weight: 600; color: rgba(255,255,255,0.9);
    white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
    display: flex; align-items: center; gap: 7px; min-width: 0;
}

.dash-card-type {
    font-size: 10px; font-weight: 700;
    padding: 2px 7px; border-radius: 4px; flex-shrink: 0;
    text-transform: uppercase; letter-spacing: 0.05em;
}

.dash-card-host {
    font-size: 12px; color: rgba(255,255,255,0.3);
    margin-bottom: 14px;
    white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}

.dash-card-divider {
    height: 1px; background: rgba(255,255,255,0.06); margin-bottom: 12px;
}

.dash-card-metrics {
    display: grid; grid-template-columns: 1fr 1fr; gap: 10px 16px;
}

.dash-metric-label {
    font-size: 10px; color: rgba(255,255,255,0.32);
    text-transform: uppercase; letter-spacing: 0.06em; margin-bottom: 3px;
}

.dash-metric-value {
    font-size: 15px; font-weight: 600;
    color: rgba(255,255,255,0.88);
    font-variant-numeric: tabular-nums; line-height: 1;
}

.dash-metric-value.health-healthy { color: #3fb950; }
.dash-metric-value.health-warning { color: #d29922; }
.dash-metric-value.health-critical,
.dash-metric-value.health-error   { color: #f85149; }
.dash-metric-value.health-unknown { color: rgba(255,255,255,0.35); }

.dash-metric-bar {
    height: 3px; background: rgba(255,255,255,0.08);
    border-radius: 2px; overflow: hidden; margin-top: 4px;
}

.dash-metric-bar-fill {
    height: 100%; border-radius: 2px;
    transition: width 0.6s ease;
    background: #58a6ff;
}
.dash-metric-bar-fill.level-high   { background: #f85149; }
.dash-metric-bar-fill.level-medium { background: #d29922; }

/* DB type badge colors */
.type-mysql      { background: rgba(0,129,194,0.15); color: #4db8ff; }
.type-postgresql { background: rgba(51,103,145,0.2);  color: #7bbfed; }
.type-oracle     { background: rgba(240,80,50,0.15);  color: #f08060; }
.type-sqlserver  { background: rgba(204,0,0,0.15);    color: #ff6b6b; }
.type-mongodb    { background: rgba(71,162,72,0.15);  color: #6bc96c; }
.type-redis      { background: rgba(220,53,34,0.15);  color: #ff7055; }
.type-tidb       { background: rgba(232,72,26,0.15);  color: #ff8060; }
.type-dm         { background: rgba(0,100,200,0.15);  color: #5599dd; }
.type-oceanbase  { background: rgba(0,180,120,0.15);  color: #33cc88; }
.type-opengauss  { background: rgba(100,60,200,0.15); color: #9977ee; }

/* DB dot colors for distribution */
.db-dot-mysql      { background: #4db8ff; }
.db-dot-postgresql { background: #7bbfed; }
.db-dot-oracle     { background: #f08060; }
.db-dot-sqlserver  { background: #ff6b6b; }
.db-dot-mongodb    { background: #6bc96c; }
.db-dot-redis      { background: #ff7055; }
.db-dot-other      { background: rgba(255,255,255,0.3); }

/* Filters */
.dashboard-filters { display: flex; align-items: center; gap: 8px; }

.filter-select, .filter-input {
    height: 30px; padding: 0 10px; font-size: 12px;
    border: 1px solid rgba(255,255,255,0.12);
    border-radius: 6px;
    background: rgba(255,255,255,0.06);
    color: rgba(255,255,255,0.7);
    transition: border-color 0.2s; outline: none;
}
.filter-select { min-width: 100px; cursor: pointer; }
.filter-input  { min-width: 160px; }
.filter-select:focus, .filter-input:focus { border-color: rgba(88,166,255,0.5); }
.filter-select option { background: #1a2133; color: rgba(255,255,255,0.8); }
.dashboard-filters .btn { height: 30px; padding: 0 14px; font-size: 12px; white-space: nowrap; }

/* Responsive */
@media (max-width: 768px) {
    .dashboard-overview { grid-template-columns: 1fr; }
    .overview-panel + .overview-panel { border-left: none; border-top: 1px solid rgba(255,255,255,0.06); }
    .dashboard-grid { grid-template-columns: 1fr; }
    .dashboard-filters { flex-wrap: wrap; }
    .filter-select, .filter-input { min-width: 100%; }
}
```

- [ ] **Step 2: 提交 CSS 变更**

```bash
git add frontend/css/dashboard.css
git commit -m "feat: rewrite dashboard.css with tech dark theme"
```

---

## Task 2: 重写 dashboard.js — 核心结构与辅助函数

**Files:**
- Modify: `frontend/js/pages/dashboard.js`

这是最重要的 Task。用 Write 工具将 `frontend/js/pages/dashboard.js` 完全替换为以下内容：

- [ ] **Step 1: 替换 dashboard.js 全部内容**

```javascript
/*