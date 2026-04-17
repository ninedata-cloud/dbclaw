import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.services.knowledge_router import (
    activate_units,
    compute_document_route,
    infer_issue_categories_from_text,
    replan_with_evidence,
    route_playbooks,
)


def test_infer_issue_categories_from_text_prefers_explicit_issue():
    categories = infer_issue_categories_from_text("数据库 CPU 很高而且有慢查询", "performance")

    assert categories[0] == "performance"
    assert "sql" in categories or "resource" in categories


def test_compute_document_route_prefers_datasource_bound_tenant_runbook():
    tenant_doc = compute_document_route(
        doc={
            "title": "订单库 CPU 高应急 Runbook",
            "summary": "适用于订单库 CPU 飙高和慢 SQL 排查",
            "scope": "tenant",
            "doc_kind": "runbook",
            "db_types": ["mysql"],
            "issue_categories": ["performance", "sql"],
            "datasource_ids": [9],
            "host_ids": [],
            "tags": ["cpu", "slow query"],
            "priority": 2,
            "freshness_level": "stable",
            "category_name": "性能诊断",
            "category_db_type": "mysql",
        },
        user_message="订单库 CPU 很高，帮我查慢查询",
        datasource_id=9,
        host_id=None,
        db_type="mysql",
        issue_categories=["performance", "sql"],
    )
    builtin_doc = compute_document_route(
        doc={
            "title": "MySQL CPU使用高诊断优化流程",
            "summary": "标准 MySQL CPU 诊断流程",
            "scope": "builtin",
            "doc_kind": "runbook",
            "db_types": ["mysql"],
            "issue_categories": ["performance"],
            "datasource_ids": [],
            "host_ids": [],
            "tags": ["mysql", "cpu"],
            "priority": 0,
            "freshness_level": "stable",
            "category_name": "性能诊断",
            "category_db_type": "mysql",
        },
        user_message="订单库 CPU 很高，帮我查慢查询",
        datasource_id=9,
        host_id=None,
        db_type="mysql",
        issue_categories=["performance", "sql"],
    )

    assert tenant_doc["score"] > builtin_doc["score"]
    assert any("绑定当前数据源" in reason for reason in tenant_doc["reasons"])


def test_compute_document_route_penalizes_expired_documents():
    active = compute_document_route(
        doc={
            "title": "MySQL 连接失败排查",
            "summary": "连接类故障排查",
            "scope": "builtin",
            "doc_kind": "runbook",
            "db_types": ["mysql"],
            "issue_categories": ["connectivity"],
            "datasource_ids": [],
            "host_ids": [],
            "tags": ["连接"],
            "priority": 0,
            "freshness_level": "stable",
            "category_name": "故障排查",
            "category_db_type": "mysql",
        },
        user_message="数据库连接失败，用户连不上",
        datasource_id=1,
        host_id=None,
        db_type="mysql",
        issue_categories=["connectivity"],
    )
    expired = compute_document_route(
        doc={
            "title": "MySQL 连接失败旧文档",
            "summary": "旧版处理方法",
            "scope": "builtin",
            "doc_kind": "runbook",
            "db_types": ["mysql"],
            "issue_categories": ["connectivity"],
            "datasource_ids": [],
            "host_ids": [],
            "tags": ["连接"],
            "priority": 0,
            "freshness_level": "expired",
            "category_name": "故障排查",
            "category_db_type": "mysql",
        },
        user_message="数据库连接失败，用户连不上",
        datasource_id=1,
        host_id=None,
        db_type="mysql",
        issue_categories=["connectivity"],
    )

    assert active["score"] > expired["score"]
    assert expired["score"] < 0


def test_activate_units_prefers_trigger_and_skills():
    routed_docs = [
        {
            "document_id": 7,
            "title": "MySQL CPU 诊断",
            "summary": "CPU 高排查",
            "scope": "builtin",
            "doc_kind": "runbook",
            "score": 90,
            "reason": "匹配 CPU 高场景",
            "reasons": ["匹配问题类别 performance"],
            "quality_status": "ready",
            "diagnosis_profile": {"evidence_requirements": []},
            "compiled_snapshot_summary": {"unit_count": 3},
            "compiled_snapshot": {
                "version_hash": "v1",
                "units": [
                    {
                        "unit_id": "u_trigger",
                        "unit_type": "trigger",
                        "title": "适用场景",
                        "path": "适用场景",
                        "summary": "CPU 持续偏高时使用",
                        "recommended_skills": ["mysql_get_db_status"],
                        "signal_tags": ["cpu"],
                        "symptom_tags": ["cpu高"],
                    },
                    {
                        "unit_id": "u_evidence",
                        "unit_type": "evidence_step",
                        "title": "第一步",
                        "path": "第一步",
                        "summary": "先看慢查询和状态",
                        "recommended_skills": ["mysql_get_slow_queries"],
                        "signal_tags": ["slow_queries"],
                        "symptom_tags": ["慢查询"],
                    },
                    {
                        "unit_id": "u_action",
                        "unit_type": "action",
                        "title": "优化建议",
                        "path": "优化建议",
                        "summary": "补充索引并限流",
                        "recommended_skills": [],
                        "signal_tags": [],
                        "symptom_tags": [],
                    },
                ]
            },
        }
    ]

    knowledge_plan = route_playbooks(
        routed_docs,
        unit_limit=10,
        user_message="数据库 CPU 很高，而且慢查询明显增多",
        issue_categories=["performance", "sql"],
        host_configured=False,
        evidence_ledger={"tool_calls": [], "consumed_unit_ids": [], "citation_refs": []},
    )

    assert knowledge_plan["active_units"][0]["unit_id"] == "u_trigger"
    assert "mysql_get_db_status" in knowledge_plan["recommended_skills"]
    assert knowledge_plan["active_documents"][0]["document_id"] == 7


def test_replan_with_evidence_updates_ledger_and_consumes_units():
    routed_docs = [
        {
            "document_id": 9,
            "title": "MySQL 锁等待排查",
            "summary": "锁诊断",
            "scope": "tenant",
            "doc_kind": "runbook",
            "score": 88,
            "reason": "匹配锁等待",
            "reasons": ["匹配问题类别 locking"],
            "quality_status": "ready",
            "diagnosis_profile": {"evidence_requirements": []},
            "compiled_snapshot_summary": {"unit_count": 2},
            "compiled_snapshot": {
                "version_hash": "hash9",
                "units": [
                    {
                        "unit_id": "unit_lock_check",
                        "unit_type": "evidence_step",
                        "title": "查看锁等待",
                        "path": "查看锁等待",
                        "summary": "先看 process list",
                        "recommended_skills": ["mysql_get_process_list"],
                        "signal_tags": ["lock"],
                        "symptom_tags": ["阻塞"],
                    },
                    {
                        "unit_id": "unit_lock_decision",
                        "unit_type": "decision_rule",
                        "title": "判断是否阻塞链",
                        "path": "判断是否阻塞链",
                        "summary": "如果长事务持续存在，则进入阻塞根因分析",
                        "recommended_skills": ["mysql_get_process_list"],
                        "signal_tags": ["lock"],
                        "symptom_tags": ["阻塞"],
                    },
                ]
            },
        }
    ]
    knowledge_context = {
        "user_message": "数据库存在阻塞和锁等待",
        "issue_categories": ["locking"],
        "host_configured": False,
        "routed_documents": routed_docs,
        "knowledge_plan": activate_units(
            routed_docs,
            issue_categories=["locking"],
            user_message="数据库存在阻塞和锁等待",
            host_configured=False,
            evidence_ledger={"tool_calls": [], "consumed_unit_ids": [], "citation_refs": []},
        ),
        "evidence_ledger": {"tool_calls": [], "consumed_unit_ids": [], "citation_refs": []},
    }

    updated = replan_with_evidence(
        knowledge_context,
        tool_name="mysql_get_process_list",
        tool_args={"datasource_id": 1},
        tool_result={"rows": [{"state": "Waiting for lock"}]},
    )

    assert updated["evidence_ledger"]["tool_calls"][-1]["tool_name"] == "mysql_get_process_list"
    assert "unit_lock_check" in updated["evidence_ledger"]["consumed_unit_ids"]
    assert updated["knowledge_plan"]["active_units"]
