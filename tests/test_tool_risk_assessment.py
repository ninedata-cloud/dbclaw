from unittest.mock import AsyncMock, patch

import pytest

from backend.agent.conversation_skills import assess_tool_risk


@pytest.mark.asyncio
async def test_read_only_os_pipeline_skips_llm_risk_misclassification():
    command = (
        'cat /proc/loadavg ; echo "---CPU INFO---" ; '
        'cat /proc/cpuinfo | grep "model name" | head -1 ; '
        'cat /proc/cpuinfo | grep processor | wc -l'
    )

    with patch(
        "backend.agent.conversation_skills._llm_assess_risk",
        new=AsyncMock(return_value={"level": "destructive", "reason": "误判"}),
    ) as mocked_llm:
        risk = await assess_tool_risk(
            "execute_os_command",
            {"command": command},
            permissions=["execute_command"],
            client=object(),
        )

    assert risk["level"] == "safe"
    assert risk["confirmation_key"] == "os_readonly"
    mocked_llm.assert_not_called()


@pytest.mark.asyncio
async def test_non_read_only_os_command_still_uses_llm_assessment():
    with patch(
        "backend.agent.conversation_skills._llm_assess_risk",
        new=AsyncMock(return_value={"level": "high", "reason": "需要确认"}),
    ) as mocked_llm:
        risk = await assess_tool_risk(
            "execute_os_command",
            {"command": "python manage.py migrate"},
            permissions=["execute_command"],
            client=object(),
        )

    assert risk["level"] == "high"
    assert risk["confirmation_key"] == "os_write"
    mocked_llm.assert_awaited_once()
