# Importance Level Refactoring

## 概述

将 AI Guardian 的 Importance Score 从自动计算改为用户手动配置的重要等级系统。

## 变更原因

原有的自动计算系统基于负载指标（QPS、TPS、连接频率等）来评估数据库重要性，但这种方式存在问题：
- 某些生产数据库负载不高，但业务重要性极高
- 用户无法根据业务需求自主决定监控策略
- 自动计算逻辑复杂，维护成本高

## 新的重要等级系统

### 四个等级

1. **核心系统 (core)**
   - 最高优先级
   - 适用于核心业务数据库
   - 默认监控间隔：5-15秒
   - 实时异常检测

2. **生产系统 (production)**
   - 标准生产环境
   - 适用于一般生产数据库
   - 默认监控间隔：60秒
   - 近实时检测

3. **开发测试 (development)**
   - 开发和测试环境
   - 较低优先级
   - 默认监控间隔：300秒
   - 批量检测

4. **临时 (temporary)**
   - 临时数据库
   - 最低优先级
   - 默认监控间隔：600秒
   - 批量检测

### 用户可配置项

- **重要等级**：用户在创建/编辑数据源时选择
- **监控间隔**：用户可自定义监控间隔（5-3600秒）

## 实现变更

### 1. 数据库模型 (backend/models/datasource.py)

```python
# 新增字段
importance_level = Column(String(20), default='production')  # core, production, development, temporary
monitoring_interval = Column(Integer, default=60)  # 监控间隔（秒）
```

### 2. API Schema (backend/schemas/datasource.py)

```python
class DatasourceCreate(BaseModel):
    # ... 其他字段
    importance_level: Optional[str] = Field(default='production', pattern="^(core|production|development|temporary)$")
    monitoring_interval: Optional[int] = Field(default=60, ge=5, le=3600)
```

### 3. 数据库迁移

```bash
python backend/migrations/add_importance_level_to_datasources.py
```

### 4. Guardian API 简化 (backend/routers/guardian.py)

- 移除 `/api/guardian/importance/{datasource_id}/recalculate` 端点
- 简化 `/api/guardian/importance/{datasource_id}` 端点，直接从 datasource 表读取
- 更新 `/api/guardian/dashboard/overview` 使用新的等级统计

### 5. 前端更新

#### 数据源表单 (frontend/js/components/datasource-form.js)
- 添加重要等级下拉选择
- 添加监控间隔输入框

#### 数据源列表 (frontend/js/pages/datasources.js)
- 显示重要等级标签（带颜色）
- 显示监控间隔

#### Guardian 仪表板 (frontend/js/pages/guardian-dashboard.js)
- 按重要等级分组显示数据源
- 显示各等级的数据源数量统计
- 移除自动计算的评分显示

## 废弃的组件

以下组件不再使用，但暂时保留以便回滚：

- `backend/models/importance.py` - DatasourceImportance 模型
- `backend/services/importance_classifier.py` - 自动评分服务
- `datasource_importance` 表（数据库）

## 使用方式

### 创建数据源时配置

```javascript
{
  "name": "Production DB",
  "db_type": "mysql",
  "host": "10.0.0.1",
  "port": 3306,
  "importance_level": "core",        // 核心系统
  "monitoring_interval": 10          // 10秒监控间隔
}
```

### 更新现有数据源

```javascript
PUT /api/datasources/{id}
{
  "importance_level": "production",
  "monitoring_interval": 60
}
```

## 迁移指南

### 现有数据源

所有现有数据源将自动设置为：
- `importance_level`: "production"
- `monitoring_interval`: 60

用户需要根据实际业务需求手动调整。

### 建议配置

- **核心交易系统**：core, 5-15秒
- **一般生产系统**：production, 60秒
- **测试环境**：development, 300秒
- **临时数据库**：temporary, 600秒

## 优势

1. **用户自主控制**：用户根据业务重要性决定监控策略
2. **简化架构**：移除复杂的自动计算逻辑
3. **更准确**：业务重要性由用户判断，比自动计算更准确
4. **灵活配置**：每个数据源可独立配置监控间隔
5. **易于理解**：四个等级清晰明了

## 后续优化

1. 支持批量修改数据源重要等级
2. 添加重要等级变更历史记录
3. 根据重要等级自动调整告警阈值
4. 支持按重要等级过滤和搜索数据源
