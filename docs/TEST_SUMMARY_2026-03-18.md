# 阿里云 RDS 集成全面测试总结

## 测试日期
2026-03-18

## 已完成的测试

### ✓ 测试 1: 系统配置初始化
- 系统配置项 `aliyun_access_key_id` 和 `aliyun_access_key_secret` 已正确初始化
- 配置分类为 `integration`

### ✓ 测试 2: 集成模板加载
- 阿里云 RDS 集成模板已加载
- 配置 Schema 中已移除 `access_key_id` 和 `access_key_secret` 参数
- 只保留 `region_id` 参数

### ✓ 测试 3: 代码语法检查
- 集成代码语法正确
- 代码中使用了 `context.get_system_config()` 读取 AccessKey
- 代码中不再从 `params` 读取 `access_key_id`

### ✓ 测试 4: 数据源验证
- 正确识别有/无 `external_instance_id` 的数据源
- 当数据源没有 `external_instance_id` 时，返回明确错误信息

### ✓ 测试 5: 前端数据源选择
- 前端测试界面已添加数据源选择下拉框
- 只在 `inbound_metric` 类型的集成中显示
- 显示数据源的 `external_instance_id` 信息

## 发现的问题

### ❌ 问题 1: 阿里云 API 时间格式错误

**错误信息**:
```
InvalidStartTime.Malformed: The specified parameter "StartTime" is not valid.
```

**根本原因**:
阿里云 RDS API 的时间格式要求非常严格，当前实现存在以下问题：
1. 时间范围可能不符合阿里云要求（需要查阅官方文档确认最小/最大时间范围）
2. 时间格式可能需要特殊处理（如 URL 编码、时区等）
3. `Timestamp` 参数应该是当前时间，不应该使用查询的结束时间

**已尝试的方案**:
- ✗ 使用 `isoformat() + "Z"` - 失败
- ✗ 使用 `strftime("%Y-%m-%dT%H:%M:%SZ")` - 失败
- ✗ 对齐到整分钟 - 失败
- ✗ 查询过去的时间范围 - 失败
- ✓ 修复 `Timestamp` 参数使用当前时间 - 部分成功（错误从 IllegalTimestamp 变为 InvalidStartTime）

**建议解决方案**:
1. 查阅阿里云 RDS API 官方文档，确认正确的时间格式和范围要求
2. 参考阿里云官方 SDK 的实现
3. 考虑使用阿里云官方 Python SDK (`aliyun-python-sdk-rds`) 而不是手动构建 API 请求

## 测试环境

- Python 版本: 3.13
- 数据库: PostgreSQL
- 测试数据源: rm-bp16knn4mo4fvh99ieo (ID: 9)
- 地域: cn-hangzhou

## 下一步行动

### 短期（必须修复）
1. **修复阿里云 API 时间格式问题** - 这是阻塞问题
   - 选项 A: 使用阿里云官方 SDK
   - 选项 B: 深入研究 API 文档，找到正确的时间格式

### 中期（优化改进）
2. 添加更详细的错误提示
3. 在前端显示 API 调用的详细错误信息
4. 添加集成测试的重试机制

### 长期（功能增强）
5. 支持更多阿里云监控指标
6. 支持其他云厂商（腾讯云、华为云等）
7. 添加集成执行日志查看功能

## 相关文件

- `backend/utils/integration_templates.py` - 集成模板
- `backend/app.py` - 系统配置初始化
- `backend/services/integration_service.py` - 集成服务
- `frontend/js/pages/integrations.js` - 前端界面
- `test_aliyun_integration_full.py` - 完整测试脚本
- `test_aliyun_api_direct.py` - API 直接调用测试

## 测试脚本

运行完整测试：
```bash
python test_aliyun_integration_full.py
```

直接测试阿里云 API：
```bash
python test_aliyun_api_direct.py
```
