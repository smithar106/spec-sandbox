"""Tests for Database CRUD round-trips."""
from __future__ import annotations

import uuid
import pytest

from spec_sandbox.domain.models import (
    BaseSpec,
    Scenario,
    ScenarioParameter,
    SpecBranch,
    AgentRun,
    AgentRole,
    RunStatus,
    ProjectionArtifact,
    BranchComparison,
    DecisionRecord,
)
from spec_sandbox.storage.database import Database


@pytest.fixture
async def db(tmp_path):
    db = Database(str(tmp_path / "test.db"))
    await db.initialize()
    yield db
    await db.close()


@pytest.mark.asyncio
async def test_base_spec_round_trip(db):
    spec = BaseSpec(title="My Spec", content="# Spec\n\nContent.")
    await db.save_base_spec(spec)
    loaded = await db.get_base_spec(spec.id)
    assert loaded is not None
    assert loaded.title == "My Spec"
    assert loaded.id == spec.id


@pytest.mark.asyncio
async def test_list_base_specs(db):
    for i in range(3):
        await db.save_base_spec(BaseSpec(title=f"Spec {i}", content="content"))
    specs = await db.list_base_specs()
    assert len(specs) == 3


@pytest.mark.asyncio
async def test_scenario_round_trip(db):
    scenario = Scenario(
        name="S1",
        parameters=[
            ScenarioParameter(name="n", key="k", original_value="a", new_value="b")
        ],
    )
    await db.save_scenario(scenario)
    loaded = await db.get_scenario(scenario.id)
    assert loaded is not None
    assert loaded.name == "S1"
    assert loaded.parameters[0].key == "k"


@pytest.mark.asyncio
async def test_branch_round_trip(db):
    spec_id = uuid.uuid4()
    scenario_id = uuid.uuid4()
    branch = SpecBranch(
        base_spec_id=spec_id,
        scenario_id=scenario_id,
        name="Branch A",
        content="# Branch\n\nContent.",
    )
    await db.save_branch(branch)
    loaded = await db.get_branch(branch.id)
    assert loaded is not None
    assert loaded.name == "Branch A"

    branches = await db.list_branches_for_spec(spec_id)
    assert len(branches) == 1


@pytest.mark.asyncio
async def test_agent_run_round_trip(db):
    branch_id = uuid.uuid4()
    run = AgentRun(
        branch_id=branch_id,
        role=AgentRole.PRODUCT,
        status=RunStatus.COMPLETE,
        output_json={"cited_assumptions": ["a"], "confidence_notes": [], "open_questions": []},
    )
    await db.save_agent_run(run)
    loaded = await db.get_agent_run(run.id)
    assert loaded is not None
    assert loaded.role == AgentRole.PRODUCT
    assert loaded.status == RunStatus.COMPLETE


@pytest.mark.asyncio
async def test_comparison_round_trip(db):
    comparison = BranchComparison(
        branch_ids=[uuid.uuid4(), uuid.uuid4()],
        invariants=["auth is always required"],
        recommendation="Choose branch A",
    )
    await db.save_comparison(comparison)
    loaded = await db.get_comparison(comparison.id)
    assert loaded is not None
    assert loaded.recommendation == "Choose branch A"
