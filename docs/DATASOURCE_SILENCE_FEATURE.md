# 数据源临时静默功能

**开发日期**: 2026-03-18
**功能**: 允许用户临时关闭数据源的监控和告警，适用于数据库维护、系统升级等场景

## 功能概述

当数据库需要临时关闭或维护时，用户可以设置静默期，在此期间：
- ✓ 停止指标采集
- ✓ 停止告警通知
- ✓ 停止巡检触发
- ✓ 自动恢复监控（静默期结束后）

## 数据库变更

### 新增字段

在 `datasources` 表中添加了两个字段：

```sql
ALTER TABLE datasources ADD COLUMN silence_until TIMESTAMP NULL;
ALTER TABLE datasources ADD COLUMN silence_reason VARCHAR(500) NULL;
```

- `silence_until`: 静默截止时间，为空表示未静默
- `silence_reason`: 静默原因（可选）

### 迁移脚本

`backend/migrations/add_datasource_silence_fields.py`

## 后端实现

### 1. 数据模型 (backend/models/datasource.py)

```python
class Datasource(Base):
    # ... 其他字段 ...

    # 临时静默配置
    silence_until = Column(DateTime, nullable=True)
    silence_reason = Column(String(500), nullable=True)
```

### 2. API Schema (backend/schemas/datasource.py)

新增三个Schema：

- `DatasourceSilenceRequest`: 设置静默请求
  - `hours`: 静默时长（1-72小时）
  - `reason`: 静默原因（可选）

- `DatasourceSilenceResponse`: 静默状态响应
  - `datasource_id`: 数据源ID
  - `silence_until`: 静默截止时间
  - `silence_reason`: 静默原因
  - `is_silenced`: 是否在静默期内
  - `remaining_hours`: 剩余静默时长

- `DatasourceResponse`: 添加静默字段
  - `silence_until`
  - `silence_reason`

### 3. API 接口 (backend/routers/datasources.py)

#### POST /api/datasources/{id}/silence
设置数据源静默

**请求体**:
```json
{
  "hours": 2,
  "reason": "数据库维护"
}
```

**响应**:
```json
{
  "datasource_id": 1,
  "silence_until": "2026-03-18T16:00:00",
  "silence_reason": "数据库维护",
  "is_silenced": true,
  "remaining_hours": 2.0
}
```

#### DELETE /api/datasources/{id}/silence
取消数据源静默

**响应**:
```json
{
  "datasource_id": 1,
  "silence_until": null,
  "silence_reason": null,
  "is_silenced": false,
  "remaining_hours": null
}
```

#### GET /api/datasources/{id}/silence
获取数据源静默状态

**响应**: 同上

### 4. 采集器逻辑 (backend/services/metric_collector.py)

#### collect_metrics_for_connection()

在采集指标前检查静默状态：

```python
# 检查是否在静默期内
if datasource.silence_until:
    current_time = now()
    if current_time < datasource.silence_until:
        logger.debug(f"Skipping metrics collection: in silence period")
        return
    else:
        # 静默已过期，自动清除
        datasource.silence_until = None
        datasource.silence_reason = None
        await db.commit()
```

#### _check_thresholds_and_trigger()

在检查阈值前验证静默状态，静默期内不触发巡检和告警。

#### _handle_connection_failure()

在创建连接失败告警前验证静默状态，静默期内不创建告警。

## 前端实现

### 1. API 客户端 (frontend/js/api.js)

新增三个API方法：

```javascript
setDatasourceSilence(id, data)      // 设置静默
cancelDatasourceSilence(id)         // 取消静默
getDatasourceSilenceStatus(id)      // 获取静默状态
```

### 2. 数据源列表 (frontend/js/pages/datasources.js)

#### 显示静默状态

在数据源列表中新增"状态"列，显示：

- **监控中**: 绿色徽章，铃铛图标
- **静默中**: 橙色徽章，静音铃铛图标，显示剩余时长

```javascript
// 静默状态计算
const now = new Date();
if (ds.silence_until) {
    const silenceUntil = new Date(ds.silence_until);
    if (now < silenceUntil) {
        isSilenced = true;
        remainingHours = (silenceUntil - now) / (1000 * 60 * 60);
    }
}
```

#### 操作按钮

- **未静默**: 显示"临时静默"按钮（静音铃铛图标）
- **已静默**: 显示"取消静默"按钮（铃铛图标，橙色）

### 3. 静默设置对话框

点击"临时静默"按钮弹出对话框：

- **静默时长**: 下拉选择（1/2/4/8/12/24/48/72小时）
- **静默原因**: 文本框（可选）
- **确认按钮**: 调用API设置静默

## 使用场景

### 场景1: 数据库维护

```
1. 用户在数据源列表点击"临时静默"按钮
2. 选择静默时长：4小时
3. 填写原因：数据库维护
4. 确认后，系统停止监控和告警
5. 4小时后自动恢复监控
```

### 场景2: 系统升级

```
1. 用户设置静默24小时
2. 填写原因：系统升级
3. 升级完成后，手动点击"取消静默"
4. 立即恢复监控
```

### 场景3: 临时关闭数据库

```
1. 数据库临时关闭前设置静默
2. 避免收到大量连接失败告警
3. 数据库恢复后取消静默
```

## 测试验证

### 自动化测试

运行测试脚本：

```bash
PYTHONPATH=/Users/william/prog2/temp/dbclaw python test_datasource_silence.py
```

测试内容：
1. ✓ 设置静默
2. ✓ 采集器跳过静默数据源
3. ✓ 取消静默
4. ✓ 采集器恢复正常

### 手动测试

1. **设置静默**
   - 在数据源列表点击"临时静默"
   - 选择时长并填写原因
   - 确认后查看状态变为"静默中"

2. **验证不采集**
   - 等待采集周期（60秒）
   - 检查数据库 `metric_snapshots` 表
   - 确认静默期间无新记录

3. **验证不告警**
   - 在静默期间触发告警条件
   - 确认不创建新告警

4. **取消静默**
   - 点击"取消静默"按钮
   - 确认状态变为"监控中"

5. **自动恢复**
   - 设置短时静默（1小时）
   - 等待静默期结束
   - 确认自动恢复监控

## 技术亮点

1. **自动过期清理**: 采集器检测到静默过期时自动清除配置
2. **多层防护**: 在采集、阈值检查、告警创建三个环节都进行静默检查
3. **实时状态显示**: 前端实时计算并显示剩余静默时长
4. **用户友好**: 提供预设时长选项，支持自定义原因

## 注意事项

1. **静默时长限制**: 最长72小时，避免长期静默导致监控失效
2. **静默原因**: 建议填写，便于后续审计和问题追溯
3. **手动取消**: 支持提前取消静默，灵活应对实际情况
4. **日志记录**: 所有静默操作都会记录日志

## 相关文件

### 后端
- `backend/models/datasource.py` - 数据模型
- `backend/schemas/datasource.py` - API Schema
- `backend/routers/datasources.py` - API 接口
- `backend/services/metric_collector.py` - 采集器逻辑
- `backend/migrations/add_datasource_silence_fields.py` - 数据库迁移

### 前端
- `frontend/js/api.js` - API 客户端
- `frontend/js/pages/datasources.js` - 数据源管理页面

### 测试
- `test_datasource_silence.py` - 自动化测试脚本
