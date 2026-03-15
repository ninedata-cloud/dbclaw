# 修复监控曲线无数据问题

## 问题描述
性能监控界面打开后，曲线图完全没有数据显示，后端报错：
```
Error sending metric:
```

## 根本原因
在批量更新图表时，对包含 null 值的 OS 指标数据进行了过滤，但没有同步过滤对应的时间标签（labels），导致：
- `labels` 数组长度 = 30
- `values` 数组长度 < 30（过滤掉 null 后）
- Chart.js 要求两个数组长度必须一致，否则无法渲染图表

## 修复方案

### 新增辅助方法
在 `frontend/js/pages/monitor.js` 中新增两个方法来同步过滤 labels 和 values：

```javascript
_filterNullValues(labels, values) {
    const filtered = { labels: [], values: [] };
    for (let i = 0; i < values.length; i++) {
        if (values[i] !== null) {
            filtered.labels.push(labels[i]);
            filtered.values.push(values[i]);
        }
    }
    return filtered;
}

_filterNullValuesMulti(labels, valuesArray) {
    const filtered = { labels: [], valuesArray: valuesArray.map(() => []) };
    for (let i = 0; i < labels.length; i++) {
        const hasValue = valuesArray.some(arr => arr[i] !== null);
        if (hasValue) {
            filtered.labels.push(labels[i]);
            valuesArray.forEach((arr, idx) => {
                filtered.valuesArray[idx].push(arr[i] !== null ? arr[i] : 0);
            });
        }
    }
    return filtered;
}
```

### 修改批量更新逻辑

**修改前**（错误）:
```javascript
// OS charts
if (batchData.cpu_usage.some(v => v !== null)) {
    ChartPanel.batchUpdate('cpu_usage', batchData.labels, batchData.cpu_usage.filter(v => v !== null));
}
```

**修改后**（正确）:
```javascript
// OS charts - filter labels and data together
if (batchData.cpu_usage.some(v => v !== null)) {
    const filtered = this._filterNullValues(batchData.labels, batchData.cpu_usage);
    ChartPanel.batchUpdate('cpu_usage', filtered.labels, filtered.values);
}
```

## 影响范围
修复影响以下图表：
- CPU 使用率
- 内存使用率
- 磁盘使用率
- 负载平均
- 磁盘 I/O（读/写）
- 网络 I/O（接收/发送）

## 测试验证
1. 启动服务器：`python run.py`
2. 打开浏览器访问监控页面
3. 验证所有图表都能正常显示数据
4. 验证实时数据更新正常

## 修改文件
- `frontend/js/pages/monitor.js`: 新增过滤方法，修复批量更新逻辑
- `性能监控优化说明.md`: 更新文档，记录问题修复
- `修复监控IO显示问题.md`: 本文档

## 相关优化
此修复是性能监控优化的一部分，完整优化内容请参考 `性能监控优化说明.md`。
