from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------


class AgentRole(str, Enum):
    PRODUCT = "PRODUCT"
    ARCHITECTURE = "ARCHITECTURE"
    UX = "UX"
    DATA_MODEL = "DATA_MODEL"
    RISK_COMPLIANCE = "RISK_COMPLIANCE"
    ROLLOUT_OPS = "ROLLOUT_OPS"


class RunStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETE = "COMPLETE"
    FAILED = "FAILED"


# ---------------------------------------------------------------------------
# ScenarioParameter
# ---------------------------------------------------------------------------


class ScenarioParameter(BaseModel):
    """A single axis of variation that a scenario applies to a base spec."""

    name: str = Field(
        description="Human-readable label for the parameter (e.g. 'Target user scale').",
    )
    key: str = Field(
        description=(
            "Machine-readable identifier used as a template key (e.g. 'target_scale')."
        ),
    )
    original_value: Any = Field(
        description="The value present in the base spec that this parameter replaces.",
    )
    new_value: Any = Field(
        description="The replacement value the scenario introduces.",
    )
    rationale: str = Field(
        default="",
        description="Why this parameter is being changed under this scenario.",
    )
    dimension: str = Field(
        default="general",
        description=(
            "The concern domain this parameter belongs to — e.g. 'scale', 'security', "
            "'budget', 'platform', 'architecture'."
        ),
    )


# ---------------------------------------------------------------------------
# Scenario
# ---------------------------------------------------------------------------


class Scenario(BaseModel):
    """A named set of parameter overrides that together define one alternative reality."""

    id: uuid.UUID = Field(
        default_factory=lambda: uuid.uuid4(),
        description="Unique identifier for this scenario.",
    )
    name: str = Field(
        description="Short descriptive name (e.g. '10x Scale, EU-only').",
    )
    description: str = Field(
        default="",
        description="Longer prose description of what this scenario models.",
    )
    parameters: list[ScenarioParameter] = Field(
        default_factory=list,
        description="Ordered list of parameter mutations that define this scenario.",
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="UTC timestamp when this scenario was created.",
    )


# ---------------------------------------------------------------------------
# BaseSpec
# ---------------------------------------------------------------------------


class BaseSpec(BaseModel):
    """The canonical source-of-truth spec document that branches are derived from."""

    id: uuid.UUID = Field(
        default_factory=lambda: uuid.uuid4(),
        description="Unique identifier for this spec.",
    )
    title: str = Field(
        description="Short title identifying the spec (e.g. 'Payments Service v2').",
    )
    content: str = Field(
        description="Full markdown text of the spec.",
    )
    source_file: str | None = Field(
        default=None,
        description="Original filesystem path the spec was loaded from, if any.",
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Arbitrary key/value metadata (YAML frontmatter, tags, etc.).",
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="UTC timestamp when this spec was ingested.",
    )


# ---------------------------------------------------------------------------
# SpecBranch
# ---------------------------------------------------------------------------


class SpecBranch(BaseModel):
    """A mutated copy of a BaseSpec produced by applying a Scenario."""

    id: uuid.UUID = Field(
        default_factory=lambda: uuid.uuid4(),
        description="Unique identifier for this branch.",
    )
    base_spec_id: uuid.UUID = Field(
        description="ID of the BaseSpec this branch was derived from.",
    )
    scenario_id: uuid.UUID = Field(
        description="ID of the Scenario whose parameters were applied.",
    )
    name: str = Field(
        description="Display name for this branch (usually '<spec> @ <scenario>').",
    )
    content: str = Field(
        description="Full markdown text of the mutated spec.",
    )
    mutations: list[dict[str, str]] = Field(
        default_factory=list,
        description=(
            "Ordered list of mutation records applied to produce this branch. "
            "Each dict has keys: 'path', 'original', 'replacement', 'reason'."
        ),
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="UTC timestamp when this branch was created.",
    )


# ---------------------------------------------------------------------------
# AgentRun
# ---------------------------------------------------------------------------


class AgentRun(BaseModel):
    """A single agent's analysis pass over a SpecBranch."""

    id: uuid.UUID = Field(
        default_factory=lambda: uuid.uuid4(),
        description="Unique identifier for this agent run.",
    )
    branch_id: uuid.UUID = Field(
        description="ID of the SpecBranch being analyzed.",
    )
    role: AgentRole = Field(
        description="The specialist role this agent is playing.",
    )
    status: RunStatus = Field(
        default=RunStatus.PENDING,
        description="Current lifecycle state of the run.",
    )
    input_spec: str = Field(
        default="",
        description="The spec content passed to the agent as input.",
    )
    output_json: dict[str, Any] | None = Field(
        default=None,
        description="Structured JSON output produced by the agent, if any.",
    )
    output_markdown: str | None = Field(
        default=None,
        description="Prose markdown output produced by the agent, if any.",
    )
    cited_assumptions: list[str] = Field(
        default_factory=list,
        description="Explicit assumptions the agent surfaced during its analysis.",
    )
    confidence_notes: list[str] = Field(
        default_factory=list,
        description="Notes about confidence level or uncertainty in the output.",
    )
    started_at: datetime | None = Field(
        default=None,
        description="UTC timestamp when the agent run began execution.",
    )
    completed_at: datetime | None = Field(
        default=None,
        description="UTC timestamp when the agent run finished (success or failure).",
    )


# ---------------------------------------------------------------------------
# ProjectionArtifact
# ---------------------------------------------------------------------------


class ProjectionArtifact(BaseModel):
    """A structured impact projection produced for one branch by one or more agents."""

    id: uuid.UUID = Field(
        default_factory=lambda: uuid.uuid4(),
        description="Unique identifier for this artifact.",
    )
    branch_id: uuid.UUID = Field(
        description="ID of the SpecBranch this projection describes.",
    )
    agent_run_id: uuid.UUID = Field(
        description="ID of the AgentRun that produced this artifact.",
    )
    artifact_type: str = Field(
        default="full_projection",
        description=(
            "Category of this artifact — e.g. 'full_projection', 'risk_summary', "
            "'rollout_plan'."
        ),
    )
    components: list[str] = Field(
        default_factory=list,
        description="New or modified software components implied by this branch.",
    )
    api_changes: list[str] = Field(
        default_factory=list,
        description="API surface changes (new endpoints, altered contracts, removed routes).",
    )
    ux_changes: list[str] = Field(
        default_factory=list,
        description="User-facing experience changes implied by this branch.",
    )
    schema_changes: list[str] = Field(
        default_factory=list,
        description="Data model or database schema changes implied by this branch.",
    )
    dependencies: list[str] = Field(
        default_factory=list,
        description="New or changed external dependencies (libraries, services, infra).",
    )
    test_implications: list[str] = Field(
        default_factory=list,
        description="Testing strategy implications — new test types, coverage gaps, load tests.",
    )
    operational_requirements: list[str] = Field(
        default_factory=list,
        description="SRE/operational requirements such as monitoring, alerting, runbooks.",
    )
    rollout_needs: list[str] = Field(
        default_factory=list,
        description="Deployment or migration steps required to ship this branch safely.",
    )
    risk_areas: list[str] = Field(
        default_factory=list,
        description="Identified risk areas or potential failure modes.",
    )
    open_questions: list[str] = Field(
        default_factory=list,
        description="Questions that remain unanswered and need resolution before building.",
    )


# ---------------------------------------------------------------------------
# BranchComparison
# ---------------------------------------------------------------------------


class BranchComparison(BaseModel):
    """A side-by-side comparison of two or more SpecBranches."""

    id: uuid.UUID = Field(
        default_factory=lambda: uuid.uuid4(),
        description="Unique identifier for this comparison.",
    )
    branch_ids: list[uuid.UUID] = Field(
        description="Ordered list of branch IDs being compared.",
    )
    invariants: list[str] = Field(
        default_factory=list,
        description="Properties or requirements that hold true across all compared branches.",
    )
    material_differences: list[dict[str, Any]] = Field(
        default_factory=list,
        description=(
            "Meaningful differences between branches. Each entry has keys: "
            "'aspect' (str) and 'branches' (dict[str, str] mapping branch_id to description)."
        ),
    )
    risk_shifts: list[dict[str, Any]] = Field(
        default_factory=list,
        description=(
            "How risk profile shifts across branches. Each entry has keys: "
            "'risk' (str), 'branches' (dict[str, str])."
        ),
    )
    complexity_scores: dict[str, int] = Field(
        default_factory=dict,
        description=(
            "Estimated implementation complexity per branch on a 1-10 scale. "
            "Keys are branch IDs (as strings), values are integers 1-10."
        ),
    )
    time_estimate_days: dict[str, int] = Field(
        default_factory=dict,
        description=(
            "Estimated calendar days to implement each branch. "
            "Keys are branch IDs (as strings), values are integers."
        ),
    )
    confidence_gaps: list[str] = Field(
        default_factory=list,
        description="Areas where the comparison is uncertain or data is insufficient.",
    )
    recommendation: str | None = Field(
        default=None,
        description="Optional summary recommendation on which branch to pursue.",
    )


# ---------------------------------------------------------------------------
# DecisionRecord
# ---------------------------------------------------------------------------


class DecisionRecord(BaseModel):
    """A formal record of which branch(es) were chosen and why."""

    id: uuid.UUID = Field(
        default_factory=lambda: uuid.uuid4(),
        description="Unique identifier for this decision record.",
    )
    chosen_branch_id: uuid.UUID | None = Field(
        default=None,
        description="The single branch selected, if the decision is not a hybrid.",
    )
    hybrid_branch_ids: list[uuid.UUID] = Field(
        default_factory=list,
        description=(
            "Branches whose elements were combined in a hybrid decision. "
            "Empty if a single branch was chosen."
        ),
    )
    rationale: str = Field(
        default="",
        description="Prose explanation of why this decision was made.",
    )
    criteria_used: list[str] = Field(
        default_factory=list,
        description="The evaluation criteria that drove the decision.",
    )
    discarded_alternatives: list[dict[str, str]] = Field(
        default_factory=list,
        description=(
            "Branches that were considered and rejected. Each entry has keys: "
            "'branch_id' (str) and 'reason' (str)."
        ),
    )
    open_follow_ups: list[str] = Field(
        default_factory=list,
        description="Action items or open questions that must be resolved post-decision.",
    )
    decided_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="UTC timestamp when this decision was recorded.",
    )


# ---------------------------------------------------------------------------
# MergePlan
# ---------------------------------------------------------------------------


class MergePlan(BaseModel):
    """Instructions for merging selected branch elements back into a canonical spec."""

    id: uuid.UUID = Field(
        default_factory=lambda: uuid.uuid4(),
        description="Unique identifier for this merge plan.",
    )
    decision_record_id: uuid.UUID = Field(
        description="ID of the DecisionRecord that produced this merge plan.",
    )
    source_branch_ids: list[uuid.UUID] = Field(
        description="Branches whose content is being merged.",
    )
    merge_instructions: list[dict[str, str]] = Field(
        default_factory=list,
        description=(
            "Ordered list of merge operations. Each entry has keys: "
            "'section' (str), 'action' (str — e.g. 'replace', 'insert', 'delete'), "
            "and 'content' (str)."
        ),
    )
    conflicts: list[str] = Field(
        default_factory=list,
        description=(
            "Sections or fields where branch content conflicts and requires manual resolution."
        ),
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="UTC timestamp when this merge plan was generated.",
    )


# ---------------------------------------------------------------------------
# CanonicalSpecRevision
# ---------------------------------------------------------------------------


class CanonicalSpecRevision(BaseModel):
    """An immutable revision of the canonical spec after a decision has been applied."""

    id: uuid.UUID = Field(
        default_factory=lambda: uuid.uuid4(),
        description="Unique identifier for this revision.",
    )
    base_spec_id: uuid.UUID = Field(
        description="ID of the BaseSpec this revision belongs to.",
    )
    previous_revision_id: uuid.UUID | None = Field(
        default=None,
        description="ID of the immediately preceding revision, forming a linked chain.",
    )
    content: str = Field(
        description="Full markdown text of the canonical spec at this revision.",
    )
    decision_record_id: uuid.UUID = Field(
        description="ID of the DecisionRecord that triggered this revision.",
    )
    version: int = Field(
        default=1,
        ge=1,
        description="Monotonically increasing revision number, starting at 1.",
    )
    revision_summary: str = Field(
        default="",
        description="Short human-readable description of what changed in this revision.",
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="UTC timestamp when this revision was created.",
    )
