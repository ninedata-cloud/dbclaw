import pytest

from backend.utils.integration_templates import BUILTIN_TEMPLATES


@pytest.mark.unit
def test_builtin_templates_have_unique_integration_ids():
    integration_ids = [template.get("integration_id") for template in BUILTIN_TEMPLATES]
    assert len(integration_ids) == len(set(integration_ids))


@pytest.mark.unit
def test_builtin_templates_have_required_top_level_fields():
    required_fields = {"integration_id", "name", "integration_type", "category", "config_schema", "code"}
    for template in BUILTIN_TEMPLATES:
        assert required_fields.issubset(template.keys())
        assert isinstance(template["config_schema"], dict)
        assert isinstance(template["code"], str)
        assert template["code"].strip()


@pytest.mark.unit
def test_builtin_templates_required_keys_exist_in_properties():
    for template in BUILTIN_TEMPLATES:
        schema = template["config_schema"]
        properties = schema.get("properties", {})
        for required_key in schema.get("required", []):
            assert required_key in properties, (
                f"{template['integration_id']} schema required key missing: {required_key}"
            )


@pytest.mark.unit
def test_notification_templates_expose_send_notification_entrypoint():
    notification_types = {"outbound_notification"}
    for template in BUILTIN_TEMPLATES:
        if template.get("integration_type") in notification_types:
            assert "send_notification" in template["code"]
