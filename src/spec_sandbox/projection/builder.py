"""ProjectionBuilder — consolidates AgentRun outputs into a ProjectionArtifact."""
from __future__ import annotations

import uuid

from spec_sandbox.domain.models import (
    AgentRun,
    ProjectionArtifact,
    RunStatus,
    SpecBranch,
)

# Keys inside output_json that map directly to ProjectionArtifact list fields.
_LIST_FIELDS = (
    "components",
    "api_changes",
    "ux_changes",
    "schema_changes",
    "dependencies",
    "test_implications",
    "operational_requirements",
    "rollout_needs",
    "risk_areas",
    "open_questions",
)


class ProjectionBuilder:
    """Merges completed AgentRun outputs for a branch into one ProjectionArtifact."""

    def build_projection(
        self,
        branch: SpecBranch,
        runs: list[AgentRun],
    ) -> ProjectionArtifact:
        """Build a consolidated ProjectionArtifact from *runs* for *branch*.

        Only COMPLETE runs that have a non-None ``output_json`` are included.
        Items are de-duplicated (case-insensitive, first-seen ordering preserved).
        The resulting artifact's ``agent_run_id`` is set to the ID of the first
        contributing run, or a new UUID when no runs contribute.

        Parameters
        ----------
        branch:
            The SpecBranch being projected.
        runs:
            All AgentRun objects produced for this branch.

        Returns
        -------
        ProjectionArtifact
            A single consolidated artifact covering all contributing runs.
        """
        # Accumulators: preserve insertion order while de-duplicating
        accumulated: dict[str, list[str]] = {field: [] for field in _LIST_FIELDS}
        seen: dict[str, set[str]] = {field: set() for field in _LIST_FIELDS}

        first_run_id: uuid.UUID | None = None

        for run in runs:
            if run.status != RunStatus.COMPLETE:
                continue
            if run.output_json is None:
                continue

            if first_run_id is None:
                first_run_id = run.id

            for field in _LIST_FIELDS:
                raw = run.output_json.get(field)
                if not isinstance(raw, list):
                    continue
                for item in raw:
                    if not isinstance(item, str):
                        item = str(item)
                    key = item.strip().lower()
                    if key and key not in seen[field]:
                        seen[field].add(key)
                        accumulated[field].append(item.strip())

        return ProjectionArtifact(
            branch_id=branch.id,
            agent_run_id=first_run_id if first_run_id is not None else uuid.uuid4(),
            artifact_type="full_projection",
            **accumulated,
        )
