# Datasource Delete Fix - 数据源删除功能修复

## 问题描述

删除数据源时报错：`Failed to delete: Internal Server Error`

错误信息：
```
AssertionError: Dependency rule on column 'datasources.id' tried to blank-out primary key column 'datasource_importance.datasource_id' on instance '<DatasourceImportance at 0x10f0ef310>'
```

## 根本原因

所有关联到 `datasources` 表的外键都没有配置 `ON DELETE CASCADE`，导致 SQLAlchemy 在删除数据源时无法正确处理级联删除。

## 修复内容

### 1. 更新模型定义

为以下模型的外键添加 `ondelete="CASCADE"`：

- `backend/models/metric_snapshot.py` - MetricSnapshot
- `backend/models/baseline.py` - MetricBaseline
- `backend/models/importance.py` - DatasourceImportance
- `backend/models/anomaly.py` - Anomaly
- `backend/models/diagnostic_case.py` - DiagnosticCase, GuardianAlert
- `backend/models/guardian_rule.py` - RuleExecution
- `backend/models/report.py` - Report
- `backend/models/diagnostic_session.py` - DiagnosticSession

### 2. 更新 Datasource 关系定义

在 `backend/models/datasource.py` 中为所有关系添加 `cascade="all, delete-orphan"`：

```python
baselines = relationship("MetricBaseline", back_populates="datasource", cascade="all, delete-orphan")
importance = relationship("DatasourceImportance", back_populates="datasource", uselist=False, cascade="all, delete-orphan")
anomalies = relationship("Anomaly", back_populates="datasource", cascade="all, delete-orphan")
diagnostic_cases = relationship("DiagnosticCase", back_populates="datasource", cascade="all, delete-orphan")
```

### 3. 数据库迁移

创建并执行了两个迁移脚本：

1. `backend/migrations/add_cascade_delete.py` - 迁移 Guardian 相关表
2. `backend/migrations/add_cascade_delete_remaining.py` - 迁移其他表

迁移的表：
- metric_baselines
- datasource_importance
- anomalies
- diagnostic_cases
- guardian_alerts
- rule_executions
- metric_snapshots
- reports
- diagnostic_sessions

### 4. 清理孤立数据

删除了 29,342 条 metric_snapshots 孤立记录和 6 条 reports 孤立记录。

## 验证结果

所有表的外键约束已正确设置为 `ON DELETE CASCADE`：

```sql
FOREIGN KEY (datasource_id) REFERENCES datasources(id) ON DELETE CASCADE
```

现在删除数据源时，所有关联数据会自动级联删除：
- 指标快照 (metric_snapshots)
- 指标基线 (metric_baselines)
- 重要性评分 (datasource_importance)
- 异常记录 (anomalies)
- 诊断案例 (diagnostic_cases)
- 守护告警 (guardian_alerts)
- 规则执行记录 (rule_executions)
- 报告 (reports)
- 诊断会话 (diagnostic_sessions)

## 使用说明

重启后端服务后，删除数据源功能即可正常工作。删除操作会自动清理所有关联数据，无需手动处理。

## 注意事项

- 删除操作不可逆，请谨慎操作
- 删除数据源会同时删除所有历史监控数据和诊断记录
- 建议在删除前先导出重要数据或创建备份
