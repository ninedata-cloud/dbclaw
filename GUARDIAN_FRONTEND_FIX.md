# Guardian Dashboard Frontend Fix

## 问题描述
点击侧边栏的 "AI Guardian" 菜单项后，页面没有响应，无法加载 Guardian Dashboard。

## 根本原因
1. **路由注册问题**: `app.js` 中使用了动态 `import()` 导入，但这与其他页面的注册方式不一致
2. **页面结构不一致**: guardian-dashboard.js 使用了 ES6 class，而其他页面使用对象字面量
3. **容器选择器错误**: 使用了 `#main-content` 而不是 `#page-content`
4. **API 调用错误**: 使用了小写的 `api` 而不是大写的 `API`
5. **脚本未加载**: index.html 中没有引入 guardian-dashboard.js

## 修复内容

### 1. 重写 guardian-dashboard.js
- 从 ES6 class 改为对象字面量 `const GuardianDashboardPage = {}`
- 修改容器选择器从 `#main-content` 改为 `#page-content`
- 统一使用 `API.get()` 和 `API.getDatasources()`
- 添加 `Header.render()` 调用
- 使用 `DOM.$()` 选择器

### 2. 更新 app.js 路由注册
```javascript
// 修改前
Router.register('guardian', () => import('./pages/guardian-dashboard.js').then(m => m.default.render()));

// 修改后
Router.register('guardian', () => GuardianDashboardPage.render());
```

### 3. 更新 index.html
在页面脚本列表中添加：
```html
<script src="/js/pages/guardian-dashboard.js"></script>
```

## 功能特性

Guardian Dashboard 提供以下功能：

1. **健康概览**
   - 系统整体健康评分
   - 数据库按重要性分级统计（Critical/Important/Normal）
   - 异常统计（Critical/Warning）

2. **数据库网格**
   - 按重要性分组显示数据库
   - 显示每个数据库的重要性评分
   - 显示监控策略（采集间隔、检测模式、自动修复）
   - 提供查看详情和异常的操作按钮

3. **异常查看**
   - 模态框显示数据库的异常列表
   - 显示异常类型、严重程度、偏差百分比
   - 显示基线值和当前值
   - 标记自动修复的异常

4. **自动刷新**
   - 每 30 秒自动刷新数据
   - 页面销毁时清理定时器

## 测试验证

### API 端点测试
```bash
curl http://localhost:8000/api/guardian/dashboard/overview
```

返回示例：
```json
{
    "datasources": {
        "total": 3,
        "by_tier": {
            "CRITICAL": 0,
            "IMPORTANT": 0,
            "NORMAL": 3
        }
    },
    "anomalies": {
        "active": 0,
        "by_severity": {
            "CRITICAL": 0,
            "WARNING": 0,
            "INFO": 0
        }
    }
}
```

### 前端测试
1. 访问 http://localhost:8000
2. 登录系统
3. 点击侧边栏 "AI Guardian" 菜单项
4. 应该看到 Guardian Dashboard 页面加载成功

## 相关文件

- `frontend/js/pages/guardian-dashboard.js` - Guardian Dashboard 页面实现
- `frontend/js/app.js` - 路由注册
- `frontend/index.html` - 脚本引入
- `frontend/css/guardian.css` - Guardian 样式
- `backend/routers/guardian.py` - Guardian API 端点

## 注意事项

1. Guardian Dashboard 依赖以下全局对象：
   - `DOM` - DOM 操作工具
   - `API` - API 调用封装
   - `Header` - 页面头部组件
   - `Router` - 路由管理器

2. 页面使用 `#page-content` 作为主容器，与其他页面保持一致

3. 自动刷新间隔为 30 秒，可根据需要调整

4. 异常查看功能使用模态框，需要确保 modal 样式正确加载
