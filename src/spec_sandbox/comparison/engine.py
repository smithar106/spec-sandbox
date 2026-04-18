"""ComparisonEngine — compares SpecBranches via their ProjectionArtifacts."""
from __future__ import annotations

from collections import Counter
from typing import Any

from spec_sandbox.domain.models import (
    BranchComparison,
    ProjectionArtifact,
    SpecBranch,
)


class ComparisonEngine:
    """Produces a BranchComparison and a markdown scorecard for a set of branches."""

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def compare(
        self,
        branches: list[SpecBranch],
        projections: list[ProjectionArtifact],
    ) -> BranchComparison:
        """Compare *branches* using their corresponding *projections*.

        Parameters
        ----------
        branches:
            All SpecBranch objects being compared.
        projections:
            ProjectionArtifacts aligned by branch_id (one per branch).

        Returns
        -------
        BranchComparison
            Fully populated comparison model.
        """
        branch_ids = [b.id for b in branches]

        # Index projections by branch_id for fast lookup
        proj_by_branch: dict[Any, ProjectionArtifact] = {
            p.branch_id: p for p in projections
        }

        # ------------------------------------------------------------------
        # Invariants — open_questions and risk_areas shared by 2+ branches
        # ------------------------------------------------------------------
        question_counter: Counter[str] = Counter()
        risk_counter: Counter[str] = Counter()

        for branch in branches:
            proj = proj_by_branch.get(branch.id)
            if proj is None:
                continue
            for q in proj.open_questions:
                question_counter[q] += 1
            for r in proj.risk_areas:
                risk_counter[r] += 1

        threshold = 2
        invariants: list[str] = [
            item
            for item, count in (question_counter + risk_counter).items()
            if count >= threshold
        ]
        # De-duplicate while preserving order
        seen: set[str] = set()
        deduped_invariants: list[str] = []
        for item in invariants:
            if item not in seen:
                seen.add(item)
                deduped_invariants.append(item)

        # ------------------------------------------------------------------
        # Material differences — unique aspects per branch
        # ------------------------------------------------------------------
        all_components: dict[Any, set[str]] = {}
        all_api_changes: dict[Any, set[str]] = {}

        for branch in branches:
            proj = proj_by_branch.get(branch.id)
            all_components[branch.id] = set(proj.components if proj else [])
            all_api_changes[branch.id] = set(proj.api_changes if proj else [])

        # Components unique to each branch
        component_diffs: dict[str, str] = {}
        for branch in branches:
            unique = all_components[branch.id] - set().union(
                *(
                    all_components[other.id]
                    for other in branches
                    if other.id != branch.id
                )
            )
            if unique:
                component_diffs[str(branch.id)] = ", ".join(sorted(unique))

        # API changes unique to each branch
        api_diffs: dict[str, str] = {}
        for branch in branches:
            unique = all_api_changes[branch.id] - set().union(
                *(
                    all_api_changes[other.id]
                    for other in branches
                    if other.id != branch.id
                )
            )
            if unique:
                api_diffs[str(branch.id)] = ", ".join(sorted(unique))

        material_differences: list[dict[str, Any]] = []
        if component_diffs:
            material_differences.append(
                {"aspect": "unique_components", "branches": component_diffs}
            )
        if api_diffs:
            material_differences.append(
                {"aspect": "unique_api_changes", "branches": api_diffs}
            )

        # ------------------------------------------------------------------
        # Complexity scores and time estimates
        # ------------------------------------------------------------------
        complexity_scores: dict[str, int] = {}
        time_estimate_days: dict[str, int] = {}

        for branch in branches:
            proj = proj_by_branch.get(branch.id)
            if proj is None:
                score = 1
            else:
                raw = len(proj.components) + len(proj.risk_areas)
                # Normalise to 1-10; every 3 items adds ~1 point, capped at 10
                score = min(10, max(1, 1 + raw // 3))
            complexity_scores[str(branch.id)] = score
            # Heuristic: ~5 days per complexity point, minimum 5
            time_estimate_days[str(branch.id)] = max(5, score * 5)

        # ------------------------------------------------------------------
        # Risk shifts — risks that appear in some branches but not others
        # ------------------------------------------------------------------
        risk_shifts: list[dict[str, Any]] = []
        all_risks: set[str] = set()
        for proj in projections:
            all_risks.update(proj.risk_areas)

        for risk in sorted(all_risks):
            branches_dict: dict[str, str] = {}
            for branch in branches:
                proj = proj_by_branch.get(branch.id)
                if proj and risk in proj.risk_areas:
                    branches_dict[str(branch.id)] = "present"
                else:
                    branches_dict[str(branch.id)] = "absent"
            unique_values = set(branches_dict.values())
            if len(unique_values) > 1:  # Only include if it actually shifts
                risk_shifts.append({"risk": risk, "branches": branches_dict})

        # ------------------------------------------------------------------
        # Confidence gaps
        # ------------------------------------------------------------------
        confidence_gaps: list[str] = []
        for branch in branches:
            proj = proj_by_branch.get(branch.id)
            if proj is None:
                confidence_gaps.append(
                    f"No projection available for branch {branch.id} ({branch.name})"
                )
            elif not proj.open_questions and not proj.risk_areas:
                confidence_gaps.append(
                    f"Branch '{branch.name}' has no open questions or risk areas — "
                    "analysis may be incomplete."
                )

        # ------------------------------------------------------------------
        # Recommendation — pick lowest complexity, fewest open questions
        # ------------------------------------------------------------------
        if branches:
            scored: list[tuple[int, int, str]] = []
            for branch in branches:
                proj = proj_by_branch.get(branch.id)
                score = complexity_scores.get(str(branch.id), 10)
                open_q = len(proj.open_questions) if proj else 999
                scored.append((score, open_q, branch.name))
            scored.sort()
            best = scored[0]
            recommendation = (
                f"Recommended branch: '{best[2]}' "
                f"(complexity={best[0]}/10, open_questions={best[1]})."
            )
        else:
            recommendation = "No branches to compare."

        return BranchComparison(
            branch_ids=branch_ids,
            invariants=deduped_invariants,
            material_differences=material_differences,
            risk_shifts=risk_shifts,
            complexity_scores=complexity_scores,
            time_estimate_days=time_estimate_days,
            confidence_gaps=confidence_gaps,
            recommendation=recommendation,
        )

    def generate_scorecard(
        self,
        comparison: BranchComparison,
        branch_names: dict[str, str],
    ) -> str:
        """Return a markdown table with per-branch scores.

        Parameters
        ----------
        comparison:
            A BranchComparison produced by :meth:`compare`.
        branch_names:
            Mapping of branch_id (str) → display name.

        Returns
        -------
        str
            Markdown string containing the scorecard table.
        """
        if not comparison.branch_ids:
            return "_No branches to score._\n"

        lines: list[str] = ["## Branch Scorecard", ""]

        # Header
        headers = ["Metric"] + [
            branch_names.get(str(bid), str(bid))
            for bid in comparison.branch_ids
        ]
        lines.append("| " + " | ".join(headers) + " |")
        lines.append("| " + " | ".join(["---"] * len(headers)) + " |")

        # Complexity row
        complexity_row = ["Complexity (1-10)"] + [
            str(comparison.complexity_scores.get(str(bid), "—"))
            for bid in comparison.branch_ids
        ]
        lines.append("| " + " | ".join(complexity_row) + " |")

        # Time estimate row
        time_row = ["Est. Days"] + [
            str(comparison.time_estimate_days.get(str(bid), "—"))
            for bid in comparison.branch_ids
        ]
        lines.append("| " + " | ".join(time_row) + " |")

        # Risk count row
        risk_count_row = ["Risk Shifts Involving Branch"] + [
            str(
                sum(
                    1
                    for rs in comparison.risk_shifts
                    if rs.get("branches", {}).get(str(bid)) == "present"
                )
            )
            for bid in comparison.branch_ids
        ]
        lines.append("| " + " | ".join(risk_count_row) + " |")

        lines.append("")

        # Recommendation
        if comparison.recommendation:
            lines.append(f"**Recommendation:** {comparison.recommendation}")
            lines.append("")

        return "\n".join(lines)
