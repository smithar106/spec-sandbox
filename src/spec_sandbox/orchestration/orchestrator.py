"""SandboxOrchestrator — full pipeline: branch → agents → project → compare."""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from spec_sandbox.domain.models import (
    AgentRole,
    AgentRun,
    SpecBranch,
    ProjectionArtifact,
    BranchComparison,
    BaseSpec,
    Scenario,
    RunStatus,
)
from spec_sandbox.branching.engine import BranchingEngine
from spec_sandbox.agents.runner import AgentRunner
from spec_sandbox.comparison.engine import ComparisonEngine
from spec_sandbox.projection.builder import ProjectionBuilder
from spec_sandbox.providers.base import LLMProvider
from spec_sandbox.storage.database import Database

logger = logging.getLogger(__name__)


class SandboxOrchestrator:
    """Drives the full spec-sandbox pipeline for a base spec + list of scenarios.

    Pipeline
    --------
    1. Persist the BaseSpec.
    2. For each Scenario: create a SpecBranch, run all agent roles concurrently.
    3. For each branch: build a ProjectionArtifact from the completed AgentRuns.
    4. Run the ComparisonEngine across all branches and projections.
    5. Return a summary dict.
    """

    def __init__(self, db: Database, provider: LLMProvider) -> None:
        self.db = db
        self.provider = provider
        self.branching = BranchingEngine()
        self.runner = AgentRunner(provider)
        self._projection_builder = ProjectionBuilder()
        self._comparison_engine = ComparisonEngine()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def run_sandbox(
        self,
        base_spec: BaseSpec,
        scenarios: list[Scenario],
        roles: list[AgentRole] | None = None,
    ) -> dict[str, Any]:
        """Full pipeline: branch → agents → project → compare.

        Returns a summary dict with keys:
          "branches"    — list[dict] (branch model dumps)
          "agent_runs"  — list[dict] (agent run model dumps, grouped by branch)
          "projections" — list[dict] (projection artifact dumps)
          "comparison"  — dict (comparison model dump)
        """
        if not scenarios:
            raise ValueError("run_sandbox requires at least one scenario.")

        # Step 1: persist base spec
        await self.db.save_base_spec(base_spec)
        logger.info("Orchestrator: saved base spec id=%s title=%r", base_spec.id, base_spec.title)

        # Step 2: branch + run agents for all scenarios concurrently
        effective_roles = roles if roles is not None else list(AgentRole)
        tasks = [
            self._branch_and_run(base_spec, scenario, effective_roles)
            for scenario in scenarios
        ]
        scenario_results: list[dict[str, Any]] = await asyncio.gather(*tasks)

        # Flatten collected data
        all_branches: list[SpecBranch] = []
        all_runs: list[AgentRun] = []
        branch_run_map: dict[str, list[AgentRun]] = {}  # branch.id → runs

        for result in scenario_results:
            branch: SpecBranch = result["branch"]
            runs: list[AgentRun] = result["runs"]
            all_branches.append(branch)
            all_runs.extend(runs)
            branch_run_map[branch.id] = runs

        # Step 3: build projections from agent runs
        all_projections: list[ProjectionArtifact] = []
        for branch in all_branches:
            runs = branch_run_map.get(branch.id, [])
            projection = self._projection_builder.build_projection(branch, runs)
            await self.db.save_projection(projection)
            all_projections.append(projection)
            logger.info(
                "Orchestrator: built projection id=%s branch=%s scenario=%r",
                projection.id,
                branch.id,
                branch.scenario_name,
            )

        # Step 4: compare all branches
        comparison = self._comparison_engine.compare(all_branches, all_projections)
        await self.db.save_comparison(comparison)
        logger.info("Orchestrator: comparison id=%s complete", comparison.id)

        # Step 5: assemble summary
        branch_names: dict[str, str] = {b.id: b.scenario_name for b in all_branches}
        scorecard = self._comparison_engine.generate_scorecard(comparison, branch_names)
        comparison.scorecard_markdown = scorecard

        return {
            "branches": [_branch_to_dict(b) for b in all_branches],
            "agent_runs": [r.model_dump(mode="json") for r in all_runs],
            "projections": [p.model_dump(mode="json") for p in all_projections],
            "comparison": comparison.model_dump(mode="json"),
        }

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    async def _branch_and_run(
        self,
        base_spec: BaseSpec,
        scenario: Scenario,
        roles: list[AgentRole],
    ) -> dict[str, Any]:
        """Create a SpecBranch for *scenario* then run all *roles* against it.

        Returns {"branch": SpecBranch, "runs": list[AgentRun], "projections": []}.
        """
        # Create the branch
        branch = await self.branching.create_branch(base_spec, scenario)
        await self.db.save_branch(branch)
        logger.info(
            "Orchestrator: created branch id=%s scenario=%r",
            branch.id,
            scenario.name,
        )

        # Run all agent roles concurrently
        runs = await self.runner.run_all_roles(branch, roles)

        # Persist each run
        for run in runs:
            await self.db.save_agent_run(run)

        completed = sum(1 for r in runs if r.status == RunStatus.COMPLETED)
        failed = sum(1 for r in runs if r.status == RunStatus.FAILED)
        logger.info(
            "Orchestrator: branch=%s runs complete=%d failed=%d",
            branch.id,
            completed,
            failed,
        )

        return {"branch": branch, "runs": runs, "projections": []}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _branch_to_dict(branch: SpecBranch) -> dict[str, Any]:
    """Serialise SpecBranch to a plain dict, handling UUID fields gracefully."""
    return branch.model_dump(mode="json")
