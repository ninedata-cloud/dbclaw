# Bocha Web Search 完整修复总结

## 修复的两个问题

### 问题1: Brotli 解压缩错误
**错误信息**: `400, message: Can not decode content-encoding: br`

**原因**: Python 3.13 + aiohttp 3.13.3 + brotli 库的API不兼容

**解决方案**: 
- 禁用 aiohttp 自动解压缩 (`auto_decompress=False`)
- 手动使用 brotlipy 库解压缩响应数据

### 问题2: API 参数和响应结构不匹配
**现象**: 没有报错但返回空数据

**原因**: 
1. API URL 错误 (`api.bochaai.com` → `api.bocha.cn`)
2. 请求参数不匹配 (`max_results`, `language` → `count`, `summary`, `freshness`)
3. 响应结构不匹配 (`results[]` → `data.webPages.value[]`)

**解决方案**: 
- 更新 API URL
- 使用正确的请求参数
- 正确解析响应数据结构

## 修改的文件

### 1. `.env`
```bash
# 修改前
BOCHA_API_URL=https://api.bochaai.com/v1/web-search

# 修改后
BOCHA_API_URL=https://api.bocha.cn/v1/web-search
```

### 2. `backend/skills/builtin/web_search_bocha.yaml`

**参数定义**:
```yaml
# 修改前
parameters:
  - name: max_results
  - name: language

# 修改后
parameters:
  - name: count
  - name: summary
  - name: freshness
```

**请求处理**:
```python
# 添加 auto_decompress=False
async with aiohttp.ClientSession(connector=connector, auto_decompress=False) as session:
    # 手动解压缩
    raw_data = await response.read()
    content_encoding = response.headers.get('Content-Encoding', '').lower()
    if content_encoding == 'br':
        import brotli
        decompressed_data = brotli.decompress(raw_data)
        data = json.loads(decompressed_data.decode('utf-8'))
```

**响应解析**:
```python
# 修改前
results = data.get('results', [])

# 修改后
web_pages = data.get('data', {}).get('webPages', {})
results = web_pages.get('value', [])
```

### 3. `test_bocha_search_simple.py`
更新测试用例使用新的参数和响应结构

## 测试验证

```bash
$ python test_bocha_search_simple.py

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
       ...
```

## 技术细节

### Brotli 解压缩兼容性

| 库 | Decompressor API | 兼容性 |
|---|---|---|
| `brotli` 1.1.0/1.2.0 | `process(data, max_length)` | ❌ 不兼容 |
| `brotlipy` 0.7.0 | `decompress(data)` | ✅ 兼容 |

aiohttp 期望 `decompress(data, max_length)` 方法，但：
- `brotli` 只有 `process()` 方法
- `brotlipy` 的 `decompress()` 只接受1个参数

解决方案：禁用自动解压缩，手动调用 `brotli.decompress()`

### Bocha API 规范

**请求**:
```json
{
  "query": "搜索词",
  "count": 5,
  "summary": true,
  "freshness": "noLimit"
}
```

**响应**:
```json
{
  "code": 200,
  "log_id": "...",
  "data": {
    "webPages": {
      "totalEstimatedMatches": 10000000,
      "value": [
        {
          "name": "标题",
          "url": "链接",
          "snippet": "摘要",
          "summary": "AI总结",
          "siteName": "网站",
          "displayUrl": "显示URL",
          "datePublished": "发布日期"
        }
      ]
    }
  }
}
```

## 使用示例

### Curl
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

### Python (aiohttp)
```python
connector = aiohttp.TCPConnector()
async with aiohttp.ClientSession(connector=connector, auto_decompress=False) as session:
    async with session.post(url, json=payload, headers=headers) as response:
        raw_data = await response.read()
        if response.headers.get('Content-Encoding', '').lower() == 'br':
            import brotli
            data = json.loads(brotli.decompress(raw_data).decode('utf-8'))
        else:
            data = json.loads(raw_data.decode('utf-8'))
```

## 依赖要求

```bash
pip install brotlipy  # 用于 Brotli 解压缩
pip install aiohttp   # HTTP 客户端
```

注意：不要使用 `brotli` 包（大写B），它与 aiohttp 不兼容。

## 相关文档

- [BOCHA_BROTLI_FIX.md](BOCHA_BROTLI_FIX.md) - Brotli 解压缩问题详细说明
- [BOCHA_WEB_SEARCH_FIX.md](BOCHA_WEB_SEARCH_FIX.md) - API 参数和响应结构修复说明

## 状态

✅ **已完成并验证**
- Brotli 解压缩正常工作
- API 调用返回正确数据
- 测试用例全部通过
