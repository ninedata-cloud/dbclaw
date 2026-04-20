"""
测试 Skill 授权 UI 的默认值行为
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.agent.skill_authorization import (
    build_skill_authorization_catalog,
    normalize_skill_authorizations,
)
from types import SimpleNamespace


def test_ui_checkbox_initial_state():
    """验证 UI 中复选框的初始状态应该是未选中（平台操作和高权限操作）"""

    # 模拟一些技能
    skills = [
        SimpleNamespace(
            id="query_monitoring_history",
            name="查询监控历史",
            description="查询监控历史数据",
            category="平台操作",
        ),
        SimpleNamespace(
            id="execute_any_sql",
            name="执行任意SQL",
            description="执行任意SQL语句",
            category="高权限操作",
        ),
        SimpleNamespace(
            id="search_knowledge",
            name="搜索知识库",
            description="搜索内置知识库",
            category="知识检索",
        ),
    ]

    # 构建 catalog（模拟后端返回）
    catalog = build_skill_authorization_catalog(skills)

    # 模拟前端首次加载时的授权状态（null）
    initial_authorizations = None

    # 前端调用 normalize（模拟前端逻辑）
    current_authorizations = normalize_skill_authorizations(initial_authorizations)

    # 验证每个分组的初始状态
    for group in catalog:
        group_id = group["id"]
        enabled_by_default = group["enabled_by_default"]
        current_enabled = current_authorizations.get(group_id, True)

        print(f"\n分组: {group['label']} ({group_id})")
        print(f"  enabled_by_default (后端): {enabled_by_default}")
        print(f"  current_enabled (前端): {current_enabled}")

        # 模拟前端的 isEnabled 逻辑
        is_enabled_in_ui = current_enabled is not False
        print(f"  UI 复选框状态: {'checked' if is_enabled_in_ui else 'unchecked'}")

        # 验证
        if group_id == "platform_operations":
            assert enabled_by_default is False, "平台操作应该默认禁用"
            assert current_enabled is False, "前端应该正确读取默认值"
            assert is_enabled_in_ui is False, "UI 复选框应该未选中"

        elif group_id == "high_privilege_operations":
            assert enabled_by_default is False, "高权限操作应该默认禁用"
            assert current_enabled is False, "前端应该正确读取默认值"
            assert is_enabled_in_ui is False, "UI 复选框应该未选中"

        elif group_id == "knowledge_retrieval":
            assert enabled_by_default is True, "知识检索应该默认启用"
            assert current_enabled is True, "前端应该正确读取默认值"
            assert is_enabled_in_ui is True, "UI 复选框应该选中"

    print("\n✓ 所有验证通过！")


if __name__ == "__main__":
    test_ui_checkbox_initial_state()
