"""End-to-end pipeline test using MockProvider and in-memory SQLite."""
from __future__ import annotations

import pytest

from spec_sandbox.domain.models import BaseSpec, Scenario, ScenarioParameter
from spec_sandbox.orchestrator import SandboxOrchestrator
from spec_sandbox.providers.mock_provider import MockProvider
from spec_sandbox.storage.database import Database


def _make_spec() -> BaseSpec:
    return BaseSpec(
        title="Feature Flag Dashboard",
        content=(
            "# Feature Flag Dashboard\n\n"
            "## Overview\n\n"
            "A dashboard for managing feature flags across 10,000 flags per org.\n\n"
            "## Scale\n\n"
            "Target: 10,000 concurrent flag evaluations per second.\n\n"
            "## Security\n\n"
            "Standard OAuth 2.0 authentication.\n"
        ),
    )


def _make_scenarios() -> list[Scenario]:
    return [
        Scenario(
            name="SMB-First",
            description="Optimized for small teams",
            parameters=[
                ScenarioParameter(
                    name="scale_target",
                    key="scale_target",
                    original_value="10,000 flags per org",
                    new_value="500 flags per org",
                    rationale="SMB orgs have fewer flags",
                    dimension="scale",
                )
            ],
        ),
        Scenario(
            name="Enterprise-Ready",
            description="Full enterprise feature set",
            parameters=[
                ScenarioParameter(
                    name="scale_target",
                    key="scale_target",
                    original_value="10,000 flags per org",
                    new_value="100,000 flags per org",
                    rationale="Enterprise orgs have many teams",
                    dimension="scale",
                )
            ],
        ),
    ]


@pytest.fixture
async def db(tmp_path):
    db = Database(str(tmp_path / "pipeline_test.db"))
    await db.initialize()
    yield db
    await db.close()


@pytest.mark.asyncio
async def test_full_pipeline_returns_all_keys(db):
    orchestrator = SandboxOrchestrator(db=db, provider=MockProvider())
    spec = _make_spec()
    scenarios = _make_scenarios()

    result = await orchestrator.run(spec=spec, scenarios=scenarios)

    assert "spec_id" in result
    assert "branches" in result
    assert "agent_runs" in result
    assert "projections" in result
    assert "comparison" in result


@pytest.mark.asyncio
async def test_full_pipeline_creates_two_branches(db):
    orchestrator = SandboxOrchestrator(db=db, provider=MockProvider())
    spec = _make_spec()
    result = await orchestrator.run(spec=spec, scenarios=_make_scenarios())

    assert len(result["branches"]) == 2


@pytest.mark.asyncio
async def test_full_pipeline_runs_all_six_agents_per_branch(db):
    orchestrator = SandboxOrchestrator(db=db, provider=MockProvider())
    spec = _make_spec()
    result = await orchestrator.run(spec=spec, scenarios=_make_scenarios())

    # 2 branches × 6 roles = 12 agent runs
    assert len(result["agent_runs"]) == 12


@pytest.mark.asyncio
async def test_full_pipeline_persists_branches_to_db(db):
    orchestrator = SandboxOrchestrator(db=db, provider=MockProvider())
    spec = _make_spec()
    result = await orchestrator.run(spec=spec, scenarios=_make_scenarios())

    import uuid
    spec_id = uuid.UUID(result["spec_id"])
    branches = await db.list_branches_for_spec(spec_id)
    assert len(branches) == 2


@pytest.mark.asyncio
async def test_comparison_has_required_fields(db):
    orchestrator = SandboxOrchestrator(db=db, provider=MockProvider())
    spec = _make_spec()
    result = await orchestrator.run(spec=spec, scenarios=_make_scenarios())

    comparison = result["comparison"]
    assert "branch_ids" in comparison
    assert "complexity_scores" in comparison
    assert "time_estimate_days" in comparison
    assert len(comparison["branch_ids"]) == 2
