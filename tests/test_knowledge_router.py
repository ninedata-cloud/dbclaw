from backend.services.knowledge_router import compute_document_route, infer_issue_categories_from_text


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
