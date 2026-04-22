# 监控系统修复记录

本文档记录了对 DBClaw 监控数据采集与前端展示功能的修复。

## 修复时间
2026-04-22

## 已修复问题

### 🔴 P0 严重问题（已全部修复）

#### 1. ✅ 修复 `_build_connection_failure_health()` 缺少返回值

**文件**: `backend/routers/metrics.py:21-38`

**问题**: 函数定义了 `violation` 字典但没有返回任何值，导致连接失败时健康检查 API 返回 `None`。

**修复**:
```python
def _build_connection_failure_health(datasource) -> Dict[str, Any]:
    error_message = (getattr(datasource, "connection_error", None) or "").strip()
    message = f"数据库连接失败: {error_message}" if error_message else "数据库连接失败"
    violation: Dict[str, Any] = {
        "type": "connection_failure",
        "metric": "connection_status",
        "value": 0,
        "threshold": 1,
    }
    return {
        "healthy": False,
        "status": "critical",
        "violations": [violation],
        "message": message,
        "alert_engine": "system"
    }
```

**影响**: 修复后，连接失败的数据源能正确返回健康状态，前端可以正确显示"连接失败"状态。

---

#### 2. ✅ 优化指标合并逻辑，避免数据竞争

**文件**: `backend/services/metric_collector.py:93-117`

**问题**: 对于 `metric_source=integration` 的数据源，系统同时执行直连采集和外部集成采集，导致数据抖动。

**修复**: 在 `collect_metrics_for_connection()` 函数开头添加检查，跳过 integration 数据源的直连采集：

```python
# 对于使用外部集成采集的数据源，跳过直连采集，避免数据竞争
if datasource.metric_source == "integration":
    logger.debug(f"Skipping direct collection for integration datasource {datasource_id}")
    return
```

同时移除了后续的指标合并逻辑（171-186 行），因为不再需要合并。

**影响**: 
- 消除了双重采集导致的数据竞争
- 监控数据更加稳定，不会出现抖动
- 减少了不必要的数据库连接和查询

---

#### 3. ✅ 修复 WebSocket 时间戳使用错误

**文件**: `frontend/js/pages/monitor.js:927-939`

**问题**: WebSocket 消息包含服务器采集时间 `collected_at`，但前端使用本地时间 `Date.now()`，导致图表时间轴不准确。

**修复**:
```javascript
this.ws.on('message', (data) => {
    if (data.type === 'heartbeat') {
        console.log('[Monitor] Heartbeat received');
        return;
    }
    if (data.type === 'db_status' && data.data) {
        console.log('[Monitor] Received metric data:', data.data);
        // 使用服务器采集时间而非本地时间
        const collectedAt = data.collected_at || new Date().toISOString();
        const timestamp = this._parseUTCDateTime(collectedAt).getTime();
        const time = this._formatChartLabel(collectedAt);
        this._updateMetricCards(data.data);
        this._updateCharts(data.data, time, timestamp);
    }
});
```

**影响**:
- 图表时间轴与实际采集时间一致
- 历史数据和实时数据时间戳连续
- 跨时区使用时显示正确

---

#### 4. ✅ 隔离网络速率计算状态

**文件**: `frontend/js/pages/monitor.js:1-67, 184-267, 625-648, 993-1139`

**问题**: 网络速率计算状态是全局单例，所有数据源共享，切换数据源时状态未清理，导致速率计算错误。

**修复**:

1. 将全局状态改为按数据源隔离的 Map：
```javascript
// 按数据源隔离网络状态，避免多数据源切换时互相干扰
networkStates: new Map(), // datasource_id -> { db: {...}, host: {...} }
currentDatasourceId: null,
```

2. 添加状态管理方法：
```javascript
_getNetworkState(datasourceId, type) {
    if (!datasourceId) return { rx: null, tx: null, time: null };
    if (!this.networkStates.has(datasourceId)) {
        this.networkStates.set(datasourceId, {
            db: { rx: null, tx: null, time: null },
            host: { rx: null, tx: null, time: null }
        });
    }
    return this.networkStates.get(datasourceId)[type];
}

_resetNetworkStateForDatasource(datasourceId) {
    if (datasourceId) {
        this.networkStates.delete(datasourceId);
    }
}
```

3. 更新所有网络速率计算函数，传入 `datasourceId` 参数：
   - `_extractDatabaseNetworkRates(data, timestamp, datasourceId)`
   - `_extractHostNetworkRates(data, timestamp, datasourceId)`

4. 在 `_reloadData()` 中重置当前数据源状态：
```javascript
this._resetNetworkStateForDatasource(connId);
this.currentDatasourceId = connId;
```

5. 在 `_updateCharts()` 和 `_batchUpdateCharts()` 中传入数据源 ID。

**影响**:
- 切换数据源后，网络 I/O 图表显示正确
- 每个数据源的速率计算独立，互不干扰
- 数据源切换时自动清理旧状态

---

### 🟡 P1 中等问题（已修复部分）

#### 5. ✅ 改进 WebSocket 重连逻辑

**文件**: `frontend/js/utils/websocket.js:13-45`

**问题**: 
- 只检查 `readyState === OPEN`，不检查 `CONNECTING` 状态，可能创建多个连接
- 重连延迟线性增长（2s, 4s, 6s, 8s, 10s），可能过慢

**修复**:

1. 检查 CONNECTING 状态：
```javascript
connect() {
    // 检查是否已经在连接或已连接状态，避免创建多个连接
    if (this.ws && (this.ws.readyState === WebSocket.OPEN ||
                    this.ws.readyState === WebSocket.CONNECTING)) {
        return;
    }
    // ...
}
```

2. 使用指数退避策略：
```javascript
this.ws.onclose = (event) => {
    this._emit('close', event);
    if (this.shouldReconnect && this.reconnectAttempts < this.maxReconnectAttempts) {
        this.reconnectAttempts++;
        // 使用指数退避策略：2s, 4s, 8s, 16s, 32s
        const delay = Math.min(this.reconnectDelay * Math.pow(2, this.reconnectAttempts - 1), 32000);
        setTimeout(() => this.connect(), delay);
    }
};
```

**影响**:
- 避免创建多个 WebSocket 连接
- 重连速度更合理，减少服务器压力
- 提升连接稳定性

---

#### 6. ✅ 添加指标标准化器缓存清理

**文件**: `backend/routers/datasources.py:313-333`

**问题**: `MetricNormalizer._last_values` 是类级别字典，删除数据源后缓存不会自动清理，导致内存泄漏。

**修复**: 在数据源删除时清理缓存：
```python
@router.delete("/{datasource_id}")
async def delete_datasource(
    datasource_id: int,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    logger.info(f"Deleting datasource {datasource_id}")

    datasource = await get_alive_by_id(db, Datasource, datasource_id)
    if not datasource:
        raise HTTPException(status_code=404, detail="数据源不存在")

    datasource.soft_delete(current_user.id)
    await db.commit()
    await unschedule_datasource(datasource_id)

    # 清理指标标准化器缓存，防止内存泄漏
    from backend.services.metric_normalizer import MetricNormalizer
    MetricNormalizer.clear_cache(datasource_id)

    logger.info(f"Soft deleted datasource {datasource_id}")
    return {"message": "Datasource deleted"}
```

**影响**:
- 防止长时间运行导致的内存泄漏
- 删除数据源后立即释放相关缓存

---

#### 7. ✅ 限制缓存命中率在 0-100 范围内

**文件**: `frontend/js/pages/monitor.js:1006-1010, 1078-1082`

**问题**: 后端某些数据库可能返回 > 100 的缓存命中率值，导致图表显示异常。

**修复**: 在更新图表前标准化缓存命中率：
```javascript
// 在 _updateCharts() 中
const normalizedHitRate = hitRate !== undefined && hitRate !== null
    ? Math.min(Math.max(parseFloat(hitRate) || 0, 0), 100)
    : null;
ChartPanel.update('cache_hit', time, normalizedHitRate, maxPoints);

// 在 _batchUpdateCharts() 中
const hitRate = data.buffer_pool_hit_rate ?? data.cache_hit_rate ?? data.hit_rate;
const normalizedHitRate = hitRate !== undefined && hitRate !== null
    ? Math.min(Math.max(parseFloat(hitRate) || 0, 0), 100)
    : null;
batchData.cache_hit.push(normalizedHitRate);
```

**影响**:
- 缓存命中率图表始终在 0-100% 范围内
- 避免异常值导致的图表显示问题

---

## 修复总结

### 已修复问题统计
- **P0 严重问题**: 4/4 (100%)
- **P1 中等问题**: 3/7 (43%)
- **总计**: 7/15 (47%)

### 修复的核心问题
1. ✅ 连接失败健康检查返回 None
2. ✅ 指标双重采集导致数据竞争
3. ✅ WebSocket 时间戳不准确
4. ✅ 网络速率状态未隔离
5. ✅ WebSocket 重连逻辑缺陷
6. ✅ 指标标准化器内存泄漏
7. ✅ 缓存命中率可能超过 100%

### 待修复问题（P1）
- 批量健康检查性能优化（串行查询改并行）
- SSH 指标采集超时处理改进
- WebSocket 推送队列满时的处理
- 历史数据加载时网络状态处理

### 待修复问题（P2）
- 连接状态指标映射标准化
- 图表数据点数限制逻辑优化
- 时间格式化性能优化
- 健康状态横幅实时更新

---

## 测试建议

### 功能测试
1. **连接失败场景**
   - 停止数据库服务
   - 验证 `/api/metrics/{conn_id}/health` 返回正确的连接失败状态
   - 验证前端显示"连接失败"状态

2. **多数据源切换**
   - 添加多个数据源（不同数据库类型）
   - 快速切换数据源
   - 验证网络 I/O 图表显示正确，无数据混淆

3. **时区测试**
   - 修改客户端时区（如 UTC+8 → UTC-5）
   - 验证图表时间轴显示正确
   - 验证历史数据和实时数据时间连续

4. **Integration 数据源**
   - 创建 `metric_source=integration` 的数据源
   - 验证只有集成采集在运行，无直连采集
   - 验证监控数据稳定，无抖动

### 性能测试
1. **WebSocket 重连**
   - 模拟网络断开
   - 验证重连延迟符合指数退避（2s, 4s, 8s, 16s, 32s）
   - 验证不会创建多个连接

2. **内存泄漏**
   - 创建并删除 100 个数据源
   - 验证内存使用稳定，无持续增长

### 边界测试
1. **缓存命中率**
   - 模拟返回 > 100 的缓存命中率
   - 验证图表显示在 0-100% 范围内

2. **网络速率计算**
   - 测试累积值重置场景（数据库重启）
   - 验证速率计算正确

---

## 部署注意事项

1. **前端资源更新**
   - 修改了 `frontend/js/pages/monitor.js` 和 `frontend/js/utils/websocket.js`
   - 需要清除浏览器缓存或更新版本号

2. **后端兼容性**
   - 修改了 `backend/routers/metrics.py`、`backend/services/metric_collector.py`、`backend/routers/datasources.py`
   - 需要重启后端服务

3. **数据库迁移**
   - 无需数据库迁移

4. **配置变更**
   - 无需配置变更

---

## 回滚方案

如果修复后出现问题，可以回滚以下文件：

```bash
git checkout HEAD~1 -- backend/routers/metrics.py
git checkout HEAD~1 -- backend/services/metric_collector.py
git checkout HEAD~1 -- backend/routers/datasources.py
git checkout HEAD~1 -- frontend/js/pages/monitor.js
git checkout HEAD~1 -- frontend/js/utils/websocket.js
```

然后重启服务。

---

## 后续优化建议

1. **引入时序数据库**
   - 当前使用 PostgreSQL 存储时序数据，查询性能有限
   - 建议引入 InfluxDB 或 TimescaleDB

2. **批量查询优化**
   - 优化 `/api/metrics/batch/dashboard` 接口
   - 使用单次查询批量获取数据

3. **前端图表库升级**
   - 考虑使用 ECharts 替代 Chart.js
   - 支持更大数据量和更好的性能

4. **监控数据压缩**
   - 对历史数据进行降采样
   - 减少存储空间和查询时间
