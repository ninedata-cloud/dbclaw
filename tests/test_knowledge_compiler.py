import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.services.knowledge_compiler import compile_document_knowledge


def test_compile_document_knowledge_extracts_units_and_resolves_aliases():
    compiled = compile_document_knowledge(
        title="PostgreSQL 综合诊断",
        content="""
# PostgreSQL 综合诊断

## 适用场景

当连接数飙高、慢查询增多时使用。

## 第一步：快速健康检查

### 调用 `get_db_status` skill

```sql
SELECT 1;
```

## 判断标准

- 连接使用率 > 85% 说明风险升高

## 优化建议

- 先排查慢 SQL 和连接池配置
""",
        diagnosis_profile={
            "symptom_tags": ["连接数高"],
            "signal_tags": ["slow_queries"],
            "recommended_skills": ["get_slow_queries"],
        },
        db_types=["postgresql"],
        freshness_level="stable",
        valid_skill_ids={"pg_get_db_status", "pg_get_slow_queries"},
    )

    snapshot = compiled["compiled_snapshot"]
    units = snapshot["units"]
    unit_types = {item["unit_type"] for item in units}
    recommended_skills = {
        skill_id
        for item in units
        for skill_id in (item.get("recommended_skills") or [])
    }

    assert compiled["quality_status"] == "ready"
    assert {"trigger", "evidence_step", "decision_rule", "action"}.issubset(unit_types)
    assert "pg_get_db_status" in recommended_skills
    assert "pg_get_slow_queries" in recommended_skills
    assert snapshot["warnings"] == []


def test_compile_document_knowledge_warns_on_expired_doc_and_missing_trigger():
    compiled = compile_document_knowledge(
        title="旧版处理文档",
        content="""
## 修复步骤

- 重建索引
""",
        diagnosis_profile={},
        db_types=["mysql"],
        freshness_level="expired",
        valid_skill_ids={"mysql_get_db_status"},
    )

    warnings = compiled["compiled_snapshot"]["warnings"]

    assert compiled["quality_status"] == "expired"
    assert "缺少触发条件" in warnings
    assert "文档已过期" in warnings
