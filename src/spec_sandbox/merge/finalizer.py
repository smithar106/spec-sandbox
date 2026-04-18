"""SpecFinalizer: creates canonical revisions from merge results and exports them."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from spec_sandbox.domain.models import (
    BaseSpec,
    CanonicalSpecRevision,
    DecisionRecord,
)

_FRONTMATTER_TEMPLATE = """\
---
title: {title}
version: {version}
decision_id: {decision_id}
created_at: {created_at}
revision_summary: >-
  {revision_summary}
---

"""


class SpecFinalizer:
    """Converts a merged spec string into a CanonicalSpecRevision and can export it."""

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def create_revision(
        self,
        base_spec: BaseSpec,
        merged_content: str,
        decision: DecisionRecord,
        previous_revision: CanonicalSpecRevision | None,
    ) -> CanonicalSpecRevision:
        """Create a new CanonicalSpecRevision from the merge output.

        The revision number is incremented from previous_revision (or starts at 1).
        The revision_summary is generated from the decision and content diff.
        """
        next_version = (previous_revision.version + 1) if previous_revision else 1
        prev_id = previous_revision.id if previous_revision else None

        summary = self.generate_revision_summary(base_spec, merged_content, decision)

        return CanonicalSpecRevision(
            id=uuid.uuid4(),
            base_spec_id=base_spec.id,
            previous_revision_id=prev_id,
            content=merged_content,
            decision_record_id=decision.id,
            version=next_version,
            revision_summary=summary,
            created_at=datetime.now(timezone.utc),
        )

    def generate_revision_summary(
        self,
        base_spec: BaseSpec,
        merged_content: str,
        decision: DecisionRecord,
    ) -> str:
        """Write a 2-3 sentence human-readable summary of what changed and why.

        Derives the summary from the decision rationale, criteria used,
        and open follow-ups rather than calling an LLM (this keeps the
        finalizer self-contained and fast).
        """
        # Sentence 1: chosen branch and hybrid context
        if decision.hybrid_branch_ids:
            n_hybrid = len(decision.hybrid_branch_ids)
            branch_clause = (
                f"Merged chosen branch {decision.chosen_branch_id} with "
                f"{n_hybrid} hybrid branch{'es' if n_hybrid != 1 else ''}"
            )
        elif decision.chosen_branch_id:
            branch_clause = f"Applied chosen branch {decision.chosen_branch_id}"
        else:
            branch_clause = "Applied decision"

        # Sentence 2: rationale (trimmed to ~120 chars)
        rationale = decision.rationale.strip()
        if len(rationale) > 120:
            rationale = rationale[:117].rstrip() + "..."
        rationale_sentence = f"Decision rationale: {rationale}." if rationale else ""

        # Sentence 3: criteria and follow-ups
        criteria_part = ""
        if decision.criteria_used:
            top_criteria = ", ".join(decision.criteria_used[:3])
            criteria_part = f"Key criteria: {top_criteria}."

        follow_up_part = ""
        if decision.open_follow_ups:
            n = len(decision.open_follow_ups)
            follow_up_part = f" {n} open follow-up{'s' if n != 1 else ''} recorded."

        sentences = [s for s in [branch_clause + ".", rationale_sentence, criteria_part + follow_up_part] if s.strip(".")]
        return " ".join(sentences).strip()

    def export_markdown(self, revision: CanonicalSpecRevision, output_path: str) -> None:
        """Write the canonical spec to a markdown file with YAML frontmatter.

        Frontmatter fields written:
        - title (inferred from first H1 in content, fallback to spec ID)
        - version
        - decision_id
        - created_at (ISO 8601)
        - revision_summary
        """
        title = self._extract_title(revision.content) or f"Spec {revision.base_spec_id}"

        # Indent multiline revision_summary for YAML block scalar
        summary_indented = revision.revision_summary.replace("\n", "\n  ")

        frontmatter = _FRONTMATTER_TEMPLATE.format(
            title=title,
            version=revision.version,
            decision_id=str(revision.decision_record_id),
            created_at=revision.created_at.isoformat(),
            revision_summary=summary_indented,
        )

        full_output = frontmatter + revision.content

        with open(output_path, "w", encoding="utf-8") as fh:
            fh.write(full_output)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _extract_title(self, content: str) -> str | None:
        """Return the text of the first H1 heading in the content, or None."""
        for line in content.splitlines():
            stripped = line.strip()
            if stripped.startswith("# ") and not stripped.startswith("## "):
                return stripped[2:].strip()
        return None
