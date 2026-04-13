# Bocha AI Web Search Skill

## 概述

`web_search_bocha` 是一个集成博查AI web搜索API的skill，允许DBClaw系统通过AI对话获取实时网络信息。

## 功能特性

- 支持中英文搜索
- 可配置返回结果数量（1-20条）
- 异步HTTP请求，超时保护
- 完整的错误处理和响应格式化

## 配置

### 1. 环境变量设置

在 `.env` 文件中添加以下配置：

```bash
# Bocha AI Web Search API
BOCHA_API_KEY=your-bocha-api-key-here
BOCHA_API_URL=https://api.bochaai.com/v1/web-search
```

### 2. 获取API密钥

1. 访问博查AI官网注册账号
2. 在控制台创建API密钥
3. 将密钥填入 `.env` 文件的 `BOCHA_API_KEY`

## 使用方法

### 通过AI对话使用

直接在DBClaw的AI对话界面询问：

```
搜索一下最新的MySQL 8.0性能优化技巧
```

```
帮我查一下PostgreSQL慢查询分析的最佳实践
```

AI会自动调用 `web_search_bocha` skill获取实时信息。

### 通过API直接调用

```bash
curl -X POST http://localhost:9939/api/skills/web_search_bocha/execute \
  -H "Content-Type: application/json" \
  -d '{
    "query": "数据库性能优化",
    "max_results": 5,
    "language": "zh"
  }'
```

### Python代码调用

```python
from backend.skills.registry import get_skill_registry
from backend.skills.executor import SkillExecutor
from backend.skills.context import SkillContext

# 获取skill
registry = get_skill_registry()
skill = await registry.get_skill("web_search_bocha")

# 创建执行上下文
context = SkillContext(
    db=db_session,
    user_id=1,
    permissions=["access_external_api"]
)

# 执行搜索
executor = SkillExecutor()
result = await executor.execute(skill, {
    "query": "database performance tuning",
    "max_results": 3,
    "language": "en"
}, context)

print(result)
```

## 参数说明

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| query | string | 是 | - | 搜索查询字符串 |
| max_results | integer | 否 | 5 | 返回结果数量（1-20） |
| language | string | 否 | zh | 搜索语言（zh/en） |

## 返回格式

### 成功响应

```json
{
  "success": true,
  "query": "数据库性能优化",
  "language": "zh",
  "total_results": 5,
  "results": [
    {
      "rank": 1,
      "title": "MySQL性能优化最佳实践",
      "url": "https://example.com/mysql-optimization",
      "snippet": "本文介绍MySQL数据库性能优化的核心技巧...",
      "source": "example.com",
      "published_date": "2026-03-10"
    }
  ],
  "api_response_time": 0.5,
  "timestamp": "2026-03-15T10:30:00Z"
}
```

### 错误响应

```json
{
  "success": false,
  "error": "API request failed with status 401",
  "details": "Invalid API key"
}
```

## 权限要求

该skill需要 `access_external_api` 权限。在skill执行时，系统会自动检查权限。

## 超时设置

- 默认超时：30秒
- HTTP请求超时：25秒
- 可在skill YAML中调整 `timeout` 字段

## 测试

运行测试脚本：

```bash
python test_bocha_search.py
```

测试脚本会执行中英文搜索测试，验证skill功能是否正常。

## 故障排查

### 1. API密钥未配置

**错误信息**：
```
BOCHA_API_KEY not configured in environment variables
```

**解决方法**：
在 `.env` 文件中设置 `BOCHA_API_KEY`

### 2. 网络连接失败

**错误信息**：
```
Network error occurred
```

**解决方法**：
- 检查网络连接
- 确认API URL是否正确
- 检查防火墙设置

### 3. API请求失败

**错误信息**：
```
API request failed with status 401/403/500
```

**解决方法**：
- 401: 检查API密钥是否正确
- 403: 检查API配额是否用尽
- 500: 联系博查AI技术支持

## 注意事项

1. **API配额管理**：注意博查AI的API调用配额限制
2. **搜索频率**：避免短时间内大量搜索请求
3. **结果缓存**：考虑对常见查询结果进行缓存
4. **错误处理**：生产环境应添加重试机制和降级策略

## 扩展开发

### 添加结果缓存

可以在skill中添加Redis缓存，减少API调用：

```python
# 检查缓存
cache_key = f"bocha_search:{query}:{language}"
cached_result = await redis.get(cache_key)
if cached_result:
    return json.loads(cached_result)

# 调用API...

# 缓存结果（1小时）
await redis.setex(cache_key, 3600, json.dumps(result))
```

### 添加搜索历史

可以将搜索记录保存到数据库：

```python
from backend.models.search_history import SearchHistory

history = SearchHistory(
    user_id=context.user_id,
    query=query,
    language=language,
    results_count=len(results)
)
context.db.add(history)
await context.db.commit()
```

## 相关文档

- [Skills System Documentation](../CLAUDE.md#skills-system)
- [Skill Development Guide](./SKILLS_IMPROVEMENTS_COMPLETE.md)
- [API Integration Best Practices](./API_INTEGRATION.md)

## 更新日志

- **v1.0.0** (2026-03-15): 初始版本，支持基础web搜索功能
