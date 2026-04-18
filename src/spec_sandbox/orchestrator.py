"""SandboxOrchestrator: runs the full spec-branching pipeline end-to-end."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from spec_sandbox.branching.engine import BranchingEngine
from spec_sandbox.domain.models import (
    AgentRole,
    AgentRun,
    BaseSpec,
    BranchComparison,
    ProjectionArtifact,
    RunStatus,
    Scenario,
    SpecBranch,
)
from spec_sandbox.providers.base import LLMProvider
from spec_sandbox.storage.database import Database

# System prompt templates per agent role
_SYSTEM_PROMPTS: dict[AgentRole, str] = {
    AgentRole.PRODUCT: (
        "You are a Senior Product Manager reviewing a software specification. "
        "Analyse it from a product perspective: user stories, feature scope, "
        "success metrics, and stakeholder impacts. Be specific and cite assumptions."
    ),
    AgentRole.ARCHITECTURE: (
        "You are a Staff Software Architect reviewing a software specification. "
        "Analyse it from an architecture perspective: components, api surface, "
        "scalability implications, and dependency changes. Be specific."
    ),
    AgentRole.UX: (
        "You are a Senior UX designer reviewing a software specification. "
        "Analyse it from a user experience and platform perspective: user flows, "
        "ui components, accessibility implications. Be specific."
    ),
    AgentRole.DATA_MODEL: (
        "You are a database architect reviewing a software specification. "
        "Analyse it from a data model perspective: schema changes, new entities, "
        "relationships, storage implications, and migration needs."
    ),
    AgentRole.RISK_COMPLIANCE: (
        "You are a risk and compliance officer reviewing a software specification. "
        "Analyse it from a risk and compliance perspective: security risks, "
        "compliance requirements, audit trail needs. Be specific."
    ),
    AgentRole.ROLLOUT_OPS: (
        "You are a Site Reliability Engineer reviewing a software specification. "
        "Analyse it from a rollout and operations perspective: deployment steps, "
        "feature flag needs, rollback plan, monitoring additions."
    ),
}

_USER_PROMPT_TEMPLATE = """Please analyse the following spec branch:

{content}

Return a comprehensive JSON analysis with keys appropriate to your role.
Include: cited_assumptions, confidence_notes, and open_questions arrays.
"""

_COMPARISON_SYSTEM = (
    "You are a technical product strategist comparing multiple spec branches. "
    "Given a set of branch analyses, identify invariants (shared elements), "
    "material differences, risk shifts across branches, and provide a recommendation."
)

_COMPARISON_USER_TEMPLATE = """Compare the following {n} spec branches:

{branch_summaries}

Identify: invariants across all branches, material differences, risk profile shifts,
complexity and time estimates per branch, and a recommendation on which to pursue.
Return a structured JSON response.
"""


class SandboxOrchestrator:
    """Coordinates the full pipeline: branch → agent runs → projections → comparison."""

    def __init__(self, db: Database, provider: LLMProvider) -> None:
        self.db = db
        self.provider = provider
        self.engine = BranchingEngine()

    async def run(
        self,
        spec: BaseSpec,
        scenarios: list[Scenario],
        roles: list[AgentRole] | None = None,
    ) -> dict[str, Any]:
        """Run the full pipeline for a spec against a list of scenarios.

        Returns a dict with keys:
        - spec_id: str
        - branches: list of SpecBranch dicts
        - agent_runs: list of AgentRun dicts
        - projections: list of ProjectionArtifact dicts
        - comparison: BranchComparison dict
        """
        active_roles = roles or list(AgentRole)

        # 1. Create branches
        branches: list[SpecBranch] = []
        for scenario in scenarios:
            branch = await self.engine.create_branch(spec, scenario)
            await self.db.save_branch(branch)
            branches.append(branch)

        # 2. Run agents on each branch
        all_runs: list[AgentRun] = []
        all_projections: list[ProjectionArtifact] = []

        for branch in branches:
            for role in active_roles:
                run, projection = await self._run_agent(branch, role)
                all_runs.append(run)
                if projection:
                    all_projections.append(projection)

        # 3. Build comparison
        comparison = await self._build_comparison(branches, all_projections)
        await self.db.save_comparison(comparison)

        return {
            "spec_id": str(spec.id),
            "branches": [b.model_dump(mode="json") for b in branches],
            "agent_runs": [r.model_dump(mode="json") for r in all_runs],
            "projections": [p.model_dump(mode="json") for p in all_projections],
            "comparison": comparison.model_dump(mode="json"),
        }

    async def _run_agent(
        self, branch: SpecBranch, role: AgentRole
    ) -> tuple[AgentRun, ProjectionArtifact | None]:
        """Run a single agent role on a branch, persist results, return (run, artifact)."""
        now = datetime.now(timezone.utc)
        run = AgentRun(
            id=uuid.uuid4(),
            branch_id=branch.id,
            role=role,
            status=RunStatus.RUNNING,
            input_spec=branch.content,
            started_at=now,
        )
        await self.db.save_agent_run(run)

        system_prompt = _SYSTEM_PROMPTS.get(role, _SYSTEM_PROMPTS[AgentRole.PRODUCT])
        user_prompt = _USER_PROMPT_TEMPLATE.format(content=branch.content)

        try:
            output_json = await self.provider.complete_json(
                system=system_prompt,
                user=user_prompt,
            )
            output_md = await self.provider.complete(
                system=system_prompt,
                user=user_prompt,
            )

            run.status = RunStatus.COMPLETE
            run.output_json = output_json
            run.output_markdown = output_md
            run.cited_assumptions = output_json.get("cited_assumptions", [])
            run.confidence_notes = output_json.get("confidence_notes", [])
            run.completed_at = datetime.now(timezone.utc)
            await self.db.update_agent_run(run)

            projection = self._build_projection(branch, run, output_json)
            await self.db.save_projection(projection)
            return run, projection

        except Exception as exc:
            run.status = RunStatus.FAILED
            run.completed_at = datetime.now(timezone.utc)
            # Store error in output_markdown so it is visible
            run.output_markdown = f"ERROR: {exc}"
            await self.db.update_agent_run(run)
            return run, None

    def _build_projection(
        self,
        branch: SpecBranch,
        run: AgentRun,
        data: dict[str, Any],
    ) -> ProjectionArtifact:
        """Map raw agent JSON output to a ProjectionArtifact."""

        def _flat_list(obj: Any) -> list[str]:
            """Flatten a list of str | dict into a list of strings."""
            if not obj:
                return []
            result: list[str] = []
            for item in obj:
                if isinstance(item, str):
                    result.append(item)
                elif isinstance(item, dict):
                    # Use the first string value in the dict, or str() the whole thing
                    first_str = next(
                        (v for v in item.values() if isinstance(v, str)), None
                    )
                    result.append(first_str or str(item))
            return result

        components: list[str] = _flat_list(
            data.get("new_components", []) + data.get("modified_components", [])
        )
        api_changes: list[str] = []
        raw_api = data.get("api_surface_changes", [])
        for item in raw_api:
            if isinstance(item, dict):
                api_changes.append(
                    f"{item.get('endpoint', '')} — {item.get('change', '')}"
                )
            elif isinstance(item, str):
                api_changes.append(item)

        ux_changes: list[str] = _flat_list(
            data.get("new_user_flows", [])
            + data.get("modified_flows", [])
            + data.get("new_ui_components", [])
        )
        schema_changes: list[str] = _flat_list(
            data.get("schema_changes", []) + data.get("new_entities", [])
        )
        dependencies: list[str] = _flat_list(data.get("new_dependencies", []))
        test_implications: list[str] = _flat_list(data.get("test_implications", []))
        operational_requirements: list[str] = _flat_list(
            data.get("monitoring_additions", [])
            + data.get("infrastructure_changes", [])
        )
        rollout_needs: list[str] = _flat_list(
            data.get("deployment_steps", [])
            + data.get("feature_flag_needs", [])
        )

        # Risk areas from various keys
        raw_risks = data.get("new_risks", [])
        risk_areas: list[str] = []
        for item in raw_risks:
            if isinstance(item, dict):
                risk_text = item.get("risk", "")
                severity = item.get("severity", "")
                risk_areas.append(f"[{severity}] {risk_text}" if severity else risk_text)
            elif isinstance(item, str):
                risk_areas.append(item)
        risk_areas += _flat_list(data.get("security_implications", []))

        open_questions: list[str] = _flat_list(data.get("open_questions", []))

        return ProjectionArtifact(
            id=uuid.uuid4(),
            branch_id=branch.id,
            agent_run_id=run.id,
            artifact_type=run.role.value.lower(),
            components=components,
            api_changes=api_changes,
            ux_changes=ux_changes,
            schema_changes=schema_changes,
            dependencies=dependencies,
            test_implications=test_implications,
            operational_requirements=operational_requirements,
            rollout_needs=rollout_needs,
            risk_areas=risk_areas,
            open_questions=open_questions,
        )

    async def _build_comparison(
        self,
        branches: list[SpecBranch],
        projections: list[ProjectionArtifact],
    ) -> BranchComparison:
        """Ask the provider to compare all branches and build a BranchComparison."""
        # Build per-branch summaries
        branch_summaries_parts: list[str] = []
        complexity_scores: dict[str, int] = {}
        time_estimate_days: dict[str, int] = {}

        for branch in branches:
            branch_projs = [p for p in projections if p.branch_id == branch.id]
            total_comps = sum(len(p.components) for p in branch_projs)
            total_risks = sum(len(p.risk_areas) for p in branch_projs)
            total_questions = sum(len(p.open_questions) for p in branch_projs)
            complexity = min(10, max(1, total_comps + total_risks))
            days = max(5, total_comps * 3 + total_risks * 2)

            complexity_scores[str(branch.id)] = complexity
            time_estimate_days[str(branch.id)] = days

            summary = (
                f"Branch: {branch.name} (id={branch.id})\n"
                f"  Components: {total_comps}, Risks: {total_risks}, Open questions: {total_questions}\n"
                f"  Estimated complexity: {complexity}/10, Estimated days: {days}"
            )
            branch_summaries_parts.append(summary)

        branch_summaries = "\n\n".join(branch_summaries_parts)
        user_prompt = _COMPARISON_USER_TEMPLATE.format(
            n=len(branches),
            branch_summaries=branch_summaries,
        )

        try:
            comp_json = await self.provider.complete_json(
                system=_COMPARISON_SYSTEM,
                user=user_prompt,
            )
            invariants: list[str] = comp_json.get("invariants", [])
            material_differences: list[dict[str, Any]] = comp_json.get("material_differences", [])
            risk_shifts: list[dict[str, Any]] = comp_json.get("risk_shifts", [])
            confidence_gaps: list[str] = comp_json.get("confidence_gaps", [])
            recommendation: str | None = comp_json.get("recommendation")
        except Exception:
            invariants = []
            material_differences = []
            risk_shifts = []
            confidence_gaps = []
            recommendation = (
                "Comparison could not be generated automatically. "
                "Review the branch projections manually."
            )

        return BranchComparison(
            id=uuid.uuid4(),
            branch_ids=[b.id for b in branches],
            invariants=invariants,
            material_differences=material_differences,
            risk_shifts=risk_shifts,
            complexity_scores=complexity_scores,
            time_estimate_days=time_estimate_days,
            confidence_gaps=confidence_gaps,
            recommendation=recommendation,
        )
