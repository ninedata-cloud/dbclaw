# 修改摘要：智能巡检触发去重

## 问题
连接失败和指标异常每分钟都重复触发诊断报告，造成大量重复记录。

## 解决方案
在 `backend/services/metric_collector.py` 中添加去重逻辑：
- 检查最近 5 分钟内是否已有相同类型的触发
- 如果存在则跳过，避免重复触发
- 只在首次检测到问题时触发诊断

## 修改文件
- `backend/services/metric_collector.py`
  - 新增导入：`timedelta`, `and_`, `desc`, `InspectionTrigger`
  - 修改 `_handle_connection_failure()` - 添加连接失败去重
  - 修改 `_check_thresholds_and_trigger()` - 添加异常指标去重

## 测试
```bash
python test_deduplication.py
```

## 预期效果
减少 90%+ 的重复诊断报告，只在问题首次出现或状态变化时触发。
