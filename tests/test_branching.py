"""Tests for BranchingEngine."""
from __future__ import annotations

import pytest

from spec_sandbox.branching.engine import BranchingEngine
from spec_sandbox.domain.models import BaseSpec, Scenario, ScenarioParameter


def _make_spec(content: str) -> BaseSpec:
    return BaseSpec(title="Test Spec", content=content)


def _make_scenario(params: list[tuple[str, str, str]]) -> Scenario:
    return Scenario(
        name="Test Scenario",
        parameters=[
            ScenarioParameter(
                name=key,
                key=key,
                original_value=orig,
                new_value=new,
                rationale="test",
                dimension="test",
            )
            for key, orig, new in params
        ],
    )


@pytest.mark.asyncio
async def test_create_branch_replaces_value():
    engine = BranchingEngine()
    spec = _make_spec("We support 1,000 users at peak load.")
    scenario = _make_scenario([("scale", "1,000 users", "100,000 users")])
    branch = await engine.create_branch(spec, scenario)

    assert "100,000 users" in branch.content
    assert branch.base_spec_id == spec.id
    assert branch.scenario_id == scenario.id


@pytest.mark.asyncio
async def test_create_branch_appends_when_value_not_found():
    engine = BranchingEngine()
    spec = _make_spec("# Overview\n\nThis is a spec.\n")
    scenario = _make_scenario([("budget", "low budget", "high budget")])
    branch = await engine.create_branch(spec, scenario)

    # Original value not in spec → should append override section
    assert "Scenario Override: budget" in branch.content
    assert "high budget" in branch.content


@pytest.mark.asyncio
async def test_scenario_header_injected():
    engine = BranchingEngine()
    spec = _make_spec("# Spec\n\nContent here.\n")
    scenario = _make_scenario([("key1", "old", "new")])
    branch = await engine.create_branch(spec, scenario)

    assert "scenario:" in branch.content
    assert "SCENARIO BRANCH:" in branch.content


@pytest.mark.asyncio
async def test_mutations_recorded():
    engine = BranchingEngine()
    spec = _make_spec("Target: 10 regions.")
    scenario = _make_scenario([("regions", "10 regions", "50 regions")])
    branch = await engine.create_branch(spec, scenario)

    assert len(branch.mutations) == 1
    mut = branch.mutations[0]
    assert mut["replacement"] == "50 regions"


@pytest.mark.asyncio
async def test_diff_branches():
    engine = BranchingEngine()
    spec = _make_spec("Scale: 100 users.")
    s1 = _make_scenario([("scale", "100 users", "1,000 users")])
    s2 = _make_scenario([("scale", "100 users", "10,000 users")])
    b1 = await engine.create_branch(spec, s1)
    b2 = await engine.create_branch(spec, s2)
    hunks = engine.diff_branches(b1, b2)
    assert len(hunks) > 0
    assert any("1,000 users" in l or "10,000 users" in l for h in hunks for l in h["lines"])
