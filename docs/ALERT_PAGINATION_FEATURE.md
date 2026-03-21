# 告警管理分页功能实现文档

## 实现概述

为告警管理页面的事件视图和告警视图添加了完整的分页功能，风格与数据库智能巡检模块保持一致。

## 设计原则

### 统一性
- 与巡检模块（`frontend/js/pages/inspection.js`）保持完全一致的分页风格
- 使用相同的按钮样式和布局方式
- 固定每页10条记录，简化用户选择

### 简洁性
- 移除复杂的分页信息显示
- 移除每页数量选择器
- 只保留核心的翻页功能

### 一致性
- 事件视图和告警视图独立分页
- 筛选条件变化时自动重置到第一页

## 修改的文件

### 1. 后端（已有支持，无需修改）

- `backend/routers/alerts.py` - 已支持 limit/offset 参数
- `backend/schemas/alert.py` - 已定义 AlertQueryParams 和 AlertEventQueryParams

### 2. 前端代码

**文件**: `frontend/js/pages/alerts.js`

#### 数据结构（统一为巡检风格）

```javascript
currentPage: {
    events: 1,
    alerts: 1
},
pageSize: {
    events: 10,
    alerts: 10
},
totalCount: {
    events: 0,
    alerts: 0
}
```

#### 修改的方法

1. **loadEvents()** - 使用 currentPage 和 pageSize 计算 offset
2. **loadAlerts()** - 使用 currentPage 和 pageSize 计算 offset
3. **renderEventsList()** - 在表格底部添加分页组件
4. **renderAlertsList()** - 在表格底部添加分页组件
5. **所有筛选器的 onChange** - 添加 resetPagination() 调用

#### 核心方法

1. **renderPagination(type)** - 渲染分页控件（巡检风格）
   ```javascript
   renderPagination(type) {
       const totalPages = Math.ceil(this.totalCount[type] / this.pageSize[type]);
       if (totalPages <= 1) return DOM.el('div');

       // 创建居中对齐的按钮组
       // 上一页 | 1 2 3 ... 10 | 下一页
   }
   ```

2. **goToPage(type, page)** - 跳转到指定页
   ```javascript
   async goToPage(type, page) {
       this.currentPage[type] = page;
       // 重新加载数据
   }
   ```

3. **resetPagination()** - 重置分页状态
   ```javascript
   resetPagination() {
       this.currentPage.events = 1;
       this.currentPage.alerts = 1;
   }
   ```

### 3. 前端样式

**文件**: `frontend/css/alerts.css`

- 移除了复杂的分页样式类
- 复用全局按钮样式（`.btn`, `.btn-sm`, `.btn-primary`, `.btn-secondary`）
- 使用内联样式实现居中对齐和间距

## 功能特性

### 1. 简洁的分页控件

- **上一页按钮** - 第一页时禁用
- **页码按钮** - 显示当前页前后各2页
- **下一页按钮** - 最后一页时禁用
- **省略号** - 页码过多时显示省略号
- 当前页按钮高亮显示（btn-primary）

### 2. 智能页码显示

```
示例1（总共5页，当前第3页）：
上一页 | 1 2 [3] 4 5 | 下一页

示例2（总共10页，当前第5页）：
上一页 | 1 ... 3 4 [5] 6 7 ... 10 | 下一页

示例3（总共10页，当前第1页）：
上一页(禁用) | [1] 2 3 ... 10 | 下一页
```

### 3. 筛选器联动

- 修改任何筛选条件时自动重置到第一页
- 保持固定的每页显示数量（10条）

## 与巡检模块的对比

| 特性 | 巡检模块 | 告警模块（统一后） |
|------|---------|------------------|
| 数据结构 | currentPage, pageSize, totalReports | currentPage, pageSize, totalCount |
| 每页数量 | 固定10条 | 固定10条 |
| 按钮样式 | btn-sm btn-secondary/primary | btn-sm btn-secondary/primary |
| 页码显示逻辑 | 当前页±2，首尾页 | 当前页±2，首尾页 |
| 布局方式 | 居中对齐，gap: 10px | 居中对齐，gap: 10px |
| 省略号 | 支持 | 支持 |
| 每页数量选择 | 无 | 无 |
| 分页信息显示 | 无 | 无 |

## 使用说明

### 用户操作

1. **查看告警列表**
   - 访问告警管理页面
   - 选择"事件视图"或"告警视图"
   - 默认显示前 10 条记录

2. **翻页**
   - 点击页码按钮跳转到指定页
   - 使用上一页/下一页按钮导航

3. **筛选数据**
   - 使用顶部筛选器过滤数据
   - 分页自动重置到第一页

### API 调用示例

```javascript
// 获取事件列表（第1页，每页10条）
GET /api/alerts/events?limit=10&offset=0

// 获取告警列表（第2页，每页10条）
GET /api/alerts?limit=10&offset=10

// 带筛选条件的分页
GET /api/alerts/events?datasource_ids=1,2&status=active&limit=10&offset=0
```

## 测试验证

### 测试页面

访问 `test_alert_pagination.html` 进行功能测试。

### 测试要点

1. **基本分页**
   - [x] 分页控件正确显示
   - [x] 页码按钮正确高亮
   - [x] 首页/末页按钮正确禁用

2. **翻页功能**
   - [x] 点击页码正确跳转
   - [x] 上一页/下一页正确工作

3. **筛选联动**
   - [x] 修改筛选条件后重置到第一页
   - [x] 保持每页显示数量（10条）

4. **数据准确性**
   - [x] 显示的记录数与设置一致
   - [x] 总数统计正确
   - [x] 页码计算正确

5. **风格一致性**
   - [x] 与巡检模块风格一致
   - [x] 按钮样式统一
   - [x] 布局方式统一

## 性能优化

1. **按需加载** - 只加载当前页数据
2. **缓存优化** - 保持筛选条件和分页状态
3. **防抖处理** - 搜索输入使用 500ms 防抖

## 代码示例

### 分页控件渲染

```javascript
renderPagination(type) {
    const totalPages = Math.ceil(this.totalCount[type] / this.pageSize[type]);
    if (totalPages <= 1) return DOM.el('div');

    const container = DOM.el('div', {
        style: 'margin-top: 15px; display: flex; justify-content: center; gap: 10px;'
    });

    // 上一页按钮
    const prevBtn = DOM.el('button', {
        className: 'btn btn-sm btn-secondary',
        textContent: '上一页',
        disabled: currentPage === 1,
        onClick: () => this.goToPage(type, currentPage - 1)
    });

    // 页码按钮（智能显示）
    for (let i = 1; i <= totalPages; i++) {
        if (i === 1 || i === totalPages ||
            (i >= currentPage - 2 && i <= currentPage + 2)) {
            // 显示页码按钮
        } else if (i === currentPage - 3 || i === currentPage + 3) {
            // 显示省略号
        }
    }

    // 下一页按钮
    const nextBtn = DOM.el('button', {
        className: 'btn btn-sm btn-secondary',
        textContent: '下一页',
        disabled: currentPage === totalPages,
        onClick: () => this.goToPage(type, currentPage + 1)
    });

    return container;
}
```

## 后续改进建议

1. **URL 同步** - 将分页状态同步到 URL，支持浏览器前进/后退
2. **键盘导航** - 支持左右箭头键翻页
3. **快速跳转** - 添加输入框直接跳转到指定页
4. **加载状态** - 添加加载动画提升用户体验
5. **虚拟滚动** - 对于大数据量，考虑使用虚拟滚动替代分页

## 兼容性

- 现代浏览器（Chrome、Firefox、Safari、Edge）
- 移动端浏览器
- 不支持 IE11 及以下版本

## 总结

通过统一告警模块和巡检模块的分页风格，实现了：
- 更简洁的用户界面
- 更一致的用户体验
- 更易维护的代码结构
- 更好的性能表现


## 修改的文件

### 1. 后端（已有支持，无需修改）

- `backend/routers/alerts.py` - 已支持 limit/offset 参数
- `backend/schemas/alert.py` - 已定义 AlertQueryParams 和 AlertEventQueryParams

### 2. 前端代码

**文件**: `frontend/js/pages/alerts.js`

#### 新增数据结构

```javascript
pagination: {
    events: { limit: 20, offset: 0, total: 0 },
    alerts: { limit: 20, offset: 0, total: 0 }
}
```

#### 修改的方法

1. **loadEvents()** - 添加 limit/offset 参数，保存 total
2. **loadAlerts()** - 添加 limit/offset 参数，保存 total
3. **renderEventsList()** - 在表格底部添加分页组件
4. **renderAlertsList()** - 在表格底部添加分页组件
5. **所有筛选器的 onChange** - 添加 resetPagination() 调用

#### 新增方法

1. **renderPagination(type)** - 渲染分页控件
   - 显示当前页信息（如：显示 1-20 / 共 100 条）
   - 首页、上一页、页码、下一页、末页按钮
   - 每页显示数量选择器（10/20/50/100）

2. **goToPage(type, page)** - 跳转到指定页
   - 计算新的 offset
   - 重新加载数据
   - 更新视图

3. **changePageSize(type, size)** - 修改每页显示数量
   - 更新 limit
   - 重置 offset 为 0
   - 重新加载数据

4. **resetPagination()** - 重置分页状态
   - 在筛选条件变化时调用
   - 将 offset 重置为 0

### 3. 前端样式

**文件**: `frontend/css/alerts.css`

新增样式类：
- `.pagination-container` - 分页容器
- `.pagination-info` - 显示信息
- `.pagination-controls` - 控制按钮组
- `.page-numbers` - 页码按钮组
- `.page-size-selector` - 每页数量选择器

## 功能特性

### 1. 分页信息显示

- 显示当前页范围（如：显示 1-20 / 共 100 条）
- 实时更新总数

### 2. 分页控制

- **首页按钮** - 跳转到第一页
- **上一页按钮** - 跳转到上一页
- **页码按钮** - 显示当前页前后各2页的页码
- **下一页按钮** - 跳转到下一页
- **末页按钮** - 跳转到最后一页
- 当前页按钮高亮显示
- 首页/末页时相应按钮禁用

### 3. 每页显示数量

- 可选择：10、20、50、100 条/页
- 默认：20 条/页
- 修改后自动重置到第一页

### 4. 筛选器联动

- 修改任何筛选条件时自动重置到第一页
- 保持当前的每页显示数量设置

### 5. 响应式设计

- 移动端自动调整布局
- 分页控件垂直排列
- 按钮自适应大小

## 使用说明

### 用户操作

1. **查看告警列表**
   - 访问告警管理页面
   - 选择"事件视图"或"告警视图"
   - 默认显示前 20 条记录

2. **翻页**
   - 点击页码按钮跳转到指定页
   - 使用首页/上一页/下一页/末页按钮导航

3. **调整每页显示数量**
   - 在页面底部选择每页显示数量
   - 系统自动重新加载数据

4. **筛选数据**
   - 使用顶部筛选器过滤数据
   - 分页自动重置到第一页

### API 调用示例

```javascript
// 获取事件列表（第1页，每页20条）
GET /api/alerts/events?limit=20&offset=0

// 获取告警列表（第2页，每页50条）
GET /api/alerts?limit=50&offset=50

// 带筛选条件的分页
GET /api/alerts/events?datasource_ids=1,2&status=active&limit=20&offset=0
```

## 测试验证

### 测试页面

访问 `test_alert_pagination.html` 进行功能测试。

### 测试要点

1. **基本分页**
   - [ ] 分页控件正确显示
   - [ ] 页码按钮正确高亮
   - [ ] 首页/末页按钮正确禁用

2. **翻页功能**
   - [ ] 点击页码正确跳转
   - [ ] 上一页/下一页正确工作
   - [ ] 首页/末页正确跳转

3. **每页数量**
   - [ ] 修改每页数量后正确重新加载
   - [ ] 自动重置到第一页

4. **筛选联动**
   - [ ] 修改筛选条件后重置到第一页
   - [ ] 保持每页显示数量设置

5. **数据准确性**
   - [ ] 显示的记录数与设置一致
   - [ ] 总数统计正确
   - [ ] 页码计算正确

6. **响应式**
   - [ ] 移动端布局正确
   - [ ] 按钮大小适配

## 性能优化

1. **按需加载** - 只加载当前页数据
2. **缓存优化** - 保持筛选条件和分页状态
3. **防抖处理** - 搜索输入使用 500ms 防抖

## 后续改进建议

1. **URL 同步** - 将分页状态同步到 URL，支持浏览器前进/后退
2. **记忆功能** - 记住用户的每页显示数量偏好
3. **快速跳转** - 添加输入框直接跳转到指定页
4. **加载状态** - 添加加载动画提升用户体验
5. **虚拟滚动** - 对于大数据量，考虑使用虚拟滚动替代分页

## 兼容性

- 现代浏览器（Chrome、Firefox、Safari、Edge）
- 移动端浏览器
- 不支持 IE11 及以下版本
