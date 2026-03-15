# Bocha Web Search API 修复说明

## 问题

Bocha AI web search skill 无法返回搜索结果，虽然没有报错但返回空数据。

## 根本原因

发现了两个配置问题：

### 1. API URL 错误
- **错误的URL**: `https://api.bochaai.com/v1/web-search`
- **正确的URL**: `https://api.bocha.cn/v1/web-search`

### 2. API 参数不匹配

**Skill 原来使用的参数**:
```json
{
  "query": "搜索词",
  "max_results": 5,
  "language": "zh"
}
```

**Bocha API 实际需要的参数**:
```json
{
  "query": "搜索词",
  "count": 5,
  "summary": true,
  "freshness": "noLimit"
}
```

### 3. 响应数据结构不匹配

**Skill 原来期望的结构**:
```json
{
  "results": [
    {"title": "...", "url": "...", "snippet": "..."}
  ]
}
```

**Bocha API 实际返回的结构**:
```json
{
  "code": 200,
  "log_id": "...",
  "msg": null,
  "data": {
    "webPages": {
      "totalEstimatedMatches": 10000000,
      "value": [
        {
          "name": "标题",
          "url": "链接",
          "snippet": "摘要",
          "summary": "AI生成的总结",
          "siteName": "网站名",
          "displayUrl": "显示URL",
          "datePublished": "发布日期"
        }
      ]
    }
  }
}
```

## 解决方案

### 1. 更新 .env 配置

```bash
BOCHA_API_URL=https://api.bocha.cn/v1/web-search
```

### 2. 更新 Skill 参数定义

修改 `backend/skills/builtin/web_search_bocha.yaml`:

```yaml
parameters:
  - name: query
    type: string
    required: true
    description: Search query string
  - name: count
    type: integer
    required: false
    default: 5
    description: Number of search results to return (default 5, max 20)
    min: 1
    max: 20
  - name: summary
    type: boolean
    required: false
    default: true
    description: Whether to include AI-generated summary for each result
  - name: freshness
    type: string
    required: false
    default: noLimit
    description: Time range for search results (noLimit, day, week, month)
    enum: [noLimit, day, week, month]
```

### 3. 更新请求 Payload

```python
payload = {
    'query': query,
    'count': count,
    'summary': summary,
    'freshness': freshness
}
```

### 4. 更新响应解析

```python
# 检查响应状态码
if data.get('code') != 200:
    return {
        "success": False,
        "error": f"API returned error code {data.get('code')}",
        "details": data.get('msg', 'Unknown error')
    }

# 提取搜索结果
web_pages = data.get('data', {}).get('webPages', {})
results = web_pages.get('value', [])
total_matches = web_pages.get('totalEstimatedMatches', 0)

# 格式化结果
formatted_results = []
for idx, result in enumerate(results[:count], 1):
    formatted_results.append({
        "rank": idx,
        "title": result.get('name', ''),
        "url": result.get('url', ''),
        "snippet": result.get('snippet', ''),
        "summary": result.get('summary', ''),
        "site_name": result.get('siteName', ''),
        "display_url": result.get('displayUrl', ''),
        "date_published": result.get('datePublished'),
        "language": result.get('language')
    })
```

## 测试结果

```bash
python test_bocha_search_simple.py
```

**输出示例**:
```
============================================================
Test: Search in Chinese
============================================================
Query: oceanbase数据库
Count: 3
Summary: True
Freshness: noLimit

HTTP Status: 200
✓ Search successful!
  Total estimated matches: 10,000,000
  Results returned: 3

  Results:
    1. GitHub - oceanbase/oceanbase: OceanBase is an enterprise...
       URL: https://github.com/oceanbase/oceanbase
       Snippet: develop Go to file Code Folders and files...
       Summary: develop Go to file Code Folders and files...
```

## 修改的文件

1. **/.env** - 更新 API URL
2. **backend/skills/builtin/web_search_bocha.yaml** - 更新参数和响应解析
3. **test_bocha_search_simple.py** - 更新测试用例

## API 参数说明

### query (必需)
搜索关键词

### count (可选，默认5)
返回结果数量，范围 1-20

### summary (可选，默认true)
是否为每个结果生成AI摘要

### freshness (可选，默认noLimit)
时效性过滤：
- `noLimit`: 不限制
- `day`: 最近一天
- `week`: 最近一周
- `month`: 最近一个月

## 使用示例

```bash
curl --location 'https://api.bocha.cn/v1/web-search' \
--header 'Authorization: Bearer YOUR_API_KEY' \
--header 'Content-Type: application/json' \
--data '{
    "query": "oceanbase",
    "summary": true,
    "freshness": "noLimit",
    "count": 5
}'
```

## 注意事项

1. 确保使用正确的 API URL: `https://api.bocha.cn` (不是 `api.bochaai.com`)
2. API 返回的 `code` 字段为 200 表示成功，不是 HTTP 状态码
3. 搜索结果在 `data.webPages.value` 数组中
4. 每个结果包含 `name`（标题）而不是 `title`
5. AI 生成的摘要在 `summary` 字段中（如果启用）
