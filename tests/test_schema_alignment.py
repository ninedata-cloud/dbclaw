from datetime import datetime
import sys
from pathlib import Path

from sqlalchemy import UniqueConstraint

sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.models.integration import Integration
from backend.schemas.datasource import DatasourceCreate
from backend.schemas.integration import IntegrationCreate, IntegrationResponse
from backend.skills.models import SkillRating
from backend.utils.datetime_helper import now


def test_integration_create_accepts_legacy_integration_id_alias():
    payload = IntegrationCreate.model_validate(
        {
            "integration_id": "builtin_test",
            "name": "Builtin Test",
            "integration_type": "bot",
            "category": "custom",
            "is_builtin": False,
            "code": "print('ok')",
            "enabled": True,
        }
    )

    assert payload.integration_code == "builtin_test"
    assert payload.model_dump(by_alias=True)["integration_id"] == "builtin_test"


def test_integration_model_supports_legacy_alias_attribute():
    integration = Integration(
        integration_code="builtin_demo",
        name="Demo",
        integration_type="bot",
        category="custom",
        is_builtin=False,
        code="print('ok')",
        enabled=True,
    )

    assert integration.integration_id == "builtin_demo"
    integration.integration_id = "builtin_demo_v2"
    assert integration.integration_code == "builtin_demo_v2"


def test_integration_response_serializes_legacy_integration_id():
    integration = Integration(
        integration_code="builtin_response",
        id=1,
        name="Response Demo",
        integration_type="bot",
        category="custom",
        is_builtin=False,
        code="print('ok')",
        enabled=True,
        created_at=datetime(2024, 1, 1, 0, 0, 0),
        updated_at=datetime(2024, 1, 1, 0, 0, 0),
    )
    response = IntegrationResponse.model_validate(
        integration,
        from_attributes=True,
    )

    assert response.model_dump(by_alias=True)["integration_id"] == "builtin_response"


def test_datasource_create_accepts_object_extra_params():
    payload = DatasourceCreate.model_validate(
        {
            "name": "demo",
            "db_type": "oracle",
            "host": "127.0.0.1",
            "port": 1521,
            "extra_params": {"oracle_conn_mode": "sysdba"},
        }
    )

    assert payload.extra_params == {"oracle_conn_mode": "sysdba"}


def test_skill_ratings_have_unique_constraint():
    constraint_names = {
        constraint.name
        for constraint in SkillRating.__table__.constraints
        if isinstance(constraint, UniqueConstraint)
    }

    assert "uq_skill_ratings_skill_user" in constraint_names


def test_now_returns_utc_naive_datetime():
    current = now()
    assert current.tzinfo is None
