"""Tests for MockProvider — verifies it returns valid JSON for all 6 roles."""
from __future__ import annotations

import pytest

from spec_sandbox.agents.prompts import AGENT_PROMPTS
from spec_sandbox.domain.models import AgentRole
from spec_sandbox.providers.mock_provider import MockProvider

PROVIDER = MockProvider()


@pytest.mark.asyncio
@pytest.mark.parametrize("role", list(AgentRole))
async def test_mock_complete_json_returns_dict(role: AgentRole):
    system, schema = AGENT_PROMPTS[role]
    result = await PROVIDER.complete_json(system=system, user="## Spec\n\nSample spec content.")
    assert isinstance(result, dict)
    # Every role schema must include these three keys
    assert "cited_assumptions" in result
    assert "confidence_notes" in result
    assert "open_questions" in result


@pytest.mark.asyncio
@pytest.mark.parametrize("role", list(AgentRole))
async def test_mock_complete_returns_string(role: AgentRole):
    system, _ = AGENT_PROMPTS[role]
    result = await PROVIDER.complete(system=system, user="## Spec\n\nSample spec content.")
    assert isinstance(result, str)
    assert len(result) > 50
