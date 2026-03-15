# 博查AI Web搜索Skill创建完成

## 已完成的工作

### 1. Skill定义文件
创建了 `/backend/skills/builtin/web_search_bocha.yaml`，包含：
- 支持中英文搜索（zh/en）
- 可配置返回结果数量（1-20条）
- 30秒超时保护
- 完整的错误处理和响应格式化

### 2. 配置更新

#### backend/config.py
添加了Bocha AI配置字段：
```python
# Bocha AI Web Search API
bocha_api_key: str = ""
bocha_api_url: str = "https://api.bochaai.com/v1/web-search"
```

#### backend/skills/schema.py
添加了新权限类型：
```python
"access_external_api",  # Access external APIs (web search, etc.)
```

#### .env.example
添加了配置示例：
```bash
# Bocha AI Web Search API
BOCHA_API_KEY=your-bocha-api-key-here
BOCHA_API_URL=https://api.bochaai.com/v1/web-search
```

### 3. 测试脚本
创建了两个测试脚本：
- `test_bocha_search.py` - 完整的skill测试（需要数据库）
- `test_bocha_search_simple.py` - 简化的API测试（不需要数据库）

### 4. 文档
创建了 `/docs/BOCHA_WEB_SEARCH_SKILL.md`，包含：
- 功能特性说明
- 配置步骤
- 使用方法（AI对话、API调用、Python代码）
- 参数说明
- 返回格式
- 故障排查
- 扩展开发建议

## 使用方法

### 配置步骤

1. 在 `.env` 文件中添加博查AI API配置：
```bash
BOCHA_API_KEY=your-actual-api-key-here
BOCHA_API_URL=https://api.bochaai.com/v1/web-search
```

2. 重启应用加载新skill：
```bash
python run.py
```

### 在AI对话中使用

直接在SmartDBA的AI对话界面询问：
```
搜索一下最新的MySQL性能优化技巧
```

```
帮我查一下PostgreSQL慢查询分析的最佳实践
```

AI会自动调用 `web_search_bocha` skill获取实时网络信息。

### 通过API调用

```bash
curl -X POST http://localhost:8000/api/skills/web_search_bocha/execute \
  -H "Content-Type: application/json" \
  -d '{
    "query": "数据库性能优化",
    "max_results": 5,
    "language": "zh"
  }'
```

## Skill参数

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
  ]
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

## 测试结果

运行 `python test_bocha_search_simple.py` 测试API连接：
- HTTP Status: 404
- 可能原因：API URL不正确或API密钥无效

## 下一步

1. **验证API配置**：
   - 确认博查AI的正确API endpoint
   - 验证API密钥是否有效
   - 检查API文档确认请求格式

2. **更新API URL**：
   根据博查AI官方文档更新 `BOCHA_API_URL` 配置

3. **测试验证**：
   配置正确后运行测试脚本验证功能

4. **集成到AI对话**：
   在应用启动时会自动加载skill，AI可以在对话中调用

## 文件清单

- `/backend/skills/builtin/web_search_bocha.yaml` - Skill定义
- `/backend/config.py` - 配置文件（已更新）
- `/backend/skills/schema.py` - Schema定义（已更新）
- `/.env.example` - 环境变量示例（已更新）
- `/docs/BOCHA_WEB_SEARCH_SKILL.md` - 完整文档
- `/test_bocha_search.py` - 完整测试脚本
- `/test_bocha_search_simple.py` - 简化测试脚本
- `/BOCHA_SEARCH_SKILL_SETUP.md` - 本文档

## 注意事项

1. **API配额管理**：注意博查AI的API调用配额限制
2. **搜索频率**：避免短时间内大量搜索请求
3. **错误处理**：生产环境应添加重试机制和降级策略
4. **结果缓存**：考虑对常见查询结果进行缓存以减少API调用

## 依赖包

已安装 `aiohttp` 用于异步HTTP请求：
```bash
pip install aiohttp
```
