# 集成管理 - 阿里云 RDS 凭证验证修复（简化版）

## 问题

在集成管理页面测试阿里云 RDS 时，即使随便输入 AccessKey，也返回 `success: true, 采集到 0 条指标`。

## 原因

测试接口随机选择一个数据源，如果该数据源没有配置 `external_instance_id`，代码会跳过并返回空列表，不会验证凭证。

## 解决方案

### 1. 后端：测试接口支持指定数据源

**文件**: `backend/routers/integrations.py`

```python
@router.post("/integrations/{integration_id}/test")
async def test_integration(
    integration_id: int,
    test_data: Dict[str, Any],
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """测试 Integration"""
    test_params = test_data.get("params", {})
    test_payload = test_data.get("payload")
    datasource_id = test_data.get("datasource_id")  # 新增：可选的数据源 ID

    result = await IntegrationService.test_integration(
        db,
        integration_id,
        test_params,
        test_payload,
        datasource_id  # 传递数据源 ID
    )
    return result
```

**文件**: `backend/services/integration_service.py`

修改 `test_integration` 方法签名，添加 `datasource_id` 参数：

```python
async def test_integration(
    db: AsyncSession,
    integration_id: int,
    test_params: Dict[str, Any],
    test_payload: Optional[Dict[str, Any]] = None,
    datasource_id: Optional[int] = None  # 新增参数
) -> Dict[str, Any]:
    # ...
    if datasource_id:
        test_datasource = await db.get(Datasource, datasource_id)
        if not test_datasource:
            return {"success": False, "message": f"数据源 ID {datasource_id} 不存在"}
    else:
        # 随机选择一个数据源
        ds_result = await db.execute(select(Datasource).limit(1))
        test_datasource = ds_result.scalar_one_or_none()
```

### 2. 后端：模板代码改进

**文件**: `backend/utils/integration_templates.py`

```python
# 1. 验证凭证配置
if not access_key_id or not access_key_secret:
    raise ValueError("阿里云 AccessKey ID 和 AccessKey Secret 未配置")

# 2. 如果数据源没有 external_instance_id，直接报错
for ds in datasources:
    instance_id = ds.get("external_instance_id")
    if not instance_id:
        raise ValueError(f"数据源 {ds['name']} 未配置 external_instance_id，无法采集阿里云 RDS 监控数据")

# 3. API 调用失败时直接抛出异常
if response.status_code != 200:
    # 解析错误信息
    error_msg = ...
    raise ValueError(f"阿里云 API 调用失败: {error_msg}")
```

### 3. 前端：添加数据源选择

**文件**: `frontend/js/pages/integrations.js`

在 `testIntegration` 方法中，如果是 `inbound_metric` 类型，加载数据源列表并显示选择框：

```javascript
async testIntegration(id) {
    const integration = this.integrations.find(i => i.id === id);

    // 如果是入站指标类型，加载数据源列表
    let datasourcesHtml = '';
    if (integration.integration_type === 'inbound_metric') {
        const datasources = await API.get('/api/datasources');
        datasourcesHtml = `
            <div class="form-group">
                <label>测试数据源 *</label>
                <select id="test-datasource-id" required>
                    <option value="">请选择数据源</option>
                    ${datasources.map(ds => `
                        <option value="${ds.id}">
                            ${ds.name} (${ds.db_type})
                            ${ds.external_instance_id ? ' - ' + ds.external_instance_id : ''}
                        </option>
                    `).join('')}
                </select>
                <small>提示：请选择已配置 external_instance_id 的数据源</small>
            </div>
        `;
    }
    // ...
}
```

在 `executeTest` 方法中，收集数据源 ID：

```javascript
async executeTest(id) {
    const testData = { params };

    // 收集数据源 ID
    if (integration.integration_type === 'inbound_metric') {
        const datasourceSelect = document.getElementById('test-datasource-id');
        if (datasourceSelect && datasourceSelect.value) {
            testData.datasource_id = parseInt(datasourceSelect.value);
        }
    }

    const response = await API.post(`/api/integrations/${id}/test`, testData);
}
```

## 修复后的效果

### 场景 1: 未配置凭证
```json
{
  "success": false,
  "message": "测试失败: 阿里云 AccessKey ID 和 AccessKey Secret 未配置"
}
```

### 场景 2: 随便输入的 AccessKey
```json
{
  "success": false,
  "message": "测试失败: 阿里云 API 调用失败: InvalidAccessKeyId.NotFound: Specified access key is not found."
}
```

### 场景 3: 数据源没有 external_instance_id
```json
{
  "success": false,
  "message": "测试失败: 数据源 xxx 未配置 external_instance_id，无法采集阿里云 RDS 监控数据"
}
```

## 部署步骤

1. 更新后端代码（routers、services、templates）
2. 更新前端代码（integrations.js）
3. 重启服务
4. 在集成管理页面点击"加载内置模板"更新模板代码
5. 测试验证

## 使用说明

测试阿里云 RDS 集成时：
1. 先在数据源管理中创建数据源，并配置 `external_instance_id`（阿里云 RDS 实例 ID）
2. 在集成测试界面，从下拉框中选择该数据源
3. 输入 AccessKey 信息
4. 点击"执行测试"

## 相关文件

- `backend/routers/integrations.py`
- `backend/services/integration_service.py`
- `backend/utils/integration_templates.py`
- `frontend/js/pages/integrations.js`
