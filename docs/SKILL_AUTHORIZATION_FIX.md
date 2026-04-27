# Skill 授权修复说明

## 问题描述

在 AI 诊断界面上设置 skill 授权后，后端 AI 调用时发现无法使用已授权的 skill。

## 根本原因

在 `backend/agent/skill_authorization.py` 的 `filter_skills_by_authorization` 函数中，存在双重归一化问题：

1. 函数首先调用 `normalize_skill_authorizations` 归一化授权配置
2. 然后调用 `is_skill_authorized` 检查每个 skill
3. `is_skill_authorized` 内部又会再次调用 `normalize_skill_authorizations`
4. 第二次归一化时，传入的是已归一化的字典，导致被重置为默认值

## 修复方案

修改 `filter_skills_by_authorization` 函数，直接使用归一化后的配置进行过滤，避免重复归一化：

```python
def filter_skills_by_authorization(
    skills: Iterable[Any],
    authorizations: dict[str, Any] | None = None,
    legacy_disabled_tools: Iterable[str] | None = None,
) -> list[Any]:
    normalized = normalize_skill_authorizations(authorizations, legacy_disabled_tools)
    result = []
    for skill in skills:
        group_id = get_group_id_for_skill(skill)
        if not group_id:
            result.append(skill)
            continue
        if normalized.get(group_id, True):
            result.append(skill)
    return result
```

## 修改文件

- `backend/agent/skill_authorization.py` - 修复过滤逻辑
- `backend/agent/skill_selector.py` - 移除调试日志
- `backend/routers/chat.py` - 移除调试日志
- `frontend/js/pages/diagnosis.js` - 移除调试日志

## 测试验证

创建了两个测试文件验证修复：

1. `tests/test_skill_authorization_fix.py` - 单元测试
2. `tests/test_skill_auth_e2e.py` - 端到端测试

运行测试：
```bash
python tests/test_skill_authorization_fix.py
python tests/test_skill_auth_e2e.py
```

## 默认安全策略

- `platform_operations` (平台操作): **默认禁用**
- `high_privilege_operations` (高权限操作): **默认禁用**
- `knowledge_retrieval` (知识检索): **默认启用**

## 工作流程

1. 用户在前端 "Skill 授权" 弹窗中配置授权
2. 前端通过 WebSocket 发送 `skill_authorizations` 配置
3. 后端接收并归一化配置
4. 后端根据配置过滤可用的 skills
5. AI 只能调用已授权分组中的 skills

## 注意事项

- 授权配置仅在当前会话生效
- 刷新页面或切换会话后会恢复默认配置
- 授权配置不会保存到数据库
