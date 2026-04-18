"""MergePlanner: generates and executes merge plans from chosen/hybrid spec branches."""

from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone

from spec_sandbox.domain.models import (
    BaseSpec,
    DecisionRecord,
    MergePlan,
    SpecBranch,
)

# Markdown ATX heading pattern (# through ######)
_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+)$", re.MULTILINE)

# Scenario frontmatter/header injected by BranchingEngine
_SCENARIO_FRONTMATTER_RE = re.compile(
    r"^---\s*\nscenario:.*?---\s*\n(?:<!-- SCENARIO BRANCH:.*?-->\s*\n)*(?:<!-- Generated:.*?-->\s*\n)*\s*",
    re.DOTALL,
)


class MergePlanner:
    """Generates MergePlan objects and executes them against a BaseSpec."""

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def plan_merge(
        self,
        chosen_branch: SpecBranch,
        hybrid_branches: list[SpecBranch],
        decision: DecisionRecord,
    ) -> MergePlan:
        """Generate a merge plan from the chosen branch and any hybrid branches.

        Strategy
        --------
        * Single branch (no hybrids): emit a replace_section instruction for every
          section present in chosen_branch (excluding scenario-header boilerplate).
        * Hybrid: for each section across all branches, use the version from
          chosen_branch if it has a mutation for that section; otherwise use the
          first hybrid branch that has a mutation for it; otherwise emit
          keep_original.
        """
        all_branches = [chosen_branch] + hybrid_branches
        conflicts = self._detect_conflicts(all_branches)

        if not hybrid_branches:
            instructions = self._plan_single(chosen_branch)
        else:
            instructions = self._plan_hybrid(chosen_branch, hybrid_branches)

        all_branch_ids = [chosen_branch.id] + [b.id for b in hybrid_branches]

        return MergePlan(
            id=uuid.uuid4(),
            decision_record_id=decision.id,
            source_branch_ids=all_branch_ids,
            merge_instructions=instructions,
            conflicts=conflicts,
            created_at=datetime.now(timezone.utc),
        )

    def execute_merge(self, plan: MergePlan, base_spec: BaseSpec) -> str:
        """Apply the merge instructions to the base spec content.

        Returns clean markdown without any scenario-branch headers.
        Instructions are applied in order.  Possible action values:
        - replace_section  — replace an existing section (heading + body) with new content
        - append_section   — add a new section that does not exist in the base
        - keep_original    — no-op; the base section is retained as-is
        """
        working = base_spec.content

        for instruction in plan.merge_instructions:
            action = instruction.get("action", "keep_original")
            section = instruction.get("section", "")
            content = instruction.get("content", "")

            if action == "keep_original" or not section:
                continue

            if action == "replace_section":
                working = self._replace_section(working, section, content)

            elif action == "append_section":
                # Only append if the section is not already present
                if not self._section_exists(working, section):
                    working = working.rstrip() + "\n\n" + content.strip() + "\n"

        return working.strip() + "\n"

    # ------------------------------------------------------------------
    # Internal planning helpers
    # ------------------------------------------------------------------

    def _plan_single(self, branch: SpecBranch) -> list[dict[str, str]]:
        """Build instructions that replace every section from a single chosen branch."""
        clean_content = self._strip_scenario_header(branch.content)
        sections = self._extract_sections(clean_content)
        instructions: list[dict[str, str]] = []

        for heading, body in sections.items():
            instructions.append(
                {
                    "section": heading,
                    "action": "replace_section",
                    "content": f"{heading}\n\n{body.strip()}\n",
                    "source_branch_id": str(branch.id),
                }
            )

        return instructions

    def _plan_hybrid(
        self, chosen_branch: SpecBranch, hybrid_branches: list[SpecBranch]
    ) -> list[dict[str, str]]:
        """Build instructions by picking the best section source across all branches.

        For each section heading found across all branches:
        1. If chosen_branch has a mutation touching this section → use chosen_branch.
        2. Else if any hybrid branch has a mutation → use the first such hybrid.
        3. Else → keep_original.
        """
        # Collect all section headings across every branch
        all_headings: list[str] = []
        branch_sections: dict[str, dict[str, str]] = {}  # branch_id → {heading: content}

        all_branches = [chosen_branch] + hybrid_branches
        for branch in all_branches:
            clean = self._strip_scenario_header(branch.content)
            secs = self._extract_sections(clean)
            branch_sections[str(branch.id)] = secs
            for h in secs:
                if h not in all_headings:
                    all_headings.append(h)

        # Determine which sections each branch has mutated
        chosen_mutated = self._mutated_sections(chosen_branch)
        hybrid_mutated: dict[str, set[str]] = {
            str(b.id): self._mutated_sections(b) for b in hybrid_branches
        }

        instructions: list[dict[str, str]] = []

        for heading in all_headings:
            # Priority 1: chosen_branch mutated this section
            if heading in chosen_mutated:
                content = branch_sections.get(str(chosen_branch.id), {}).get(heading, "")
                instructions.append(
                    {
                        "section": heading,
                        "action": "replace_section",
                        "content": f"{heading}\n\n{content.strip()}\n",
                        "source_branch_id": str(chosen_branch.id),
                    }
                )
                continue

            # Priority 2: a hybrid branch mutated this section
            picked_hybrid: SpecBranch | None = None
            for hb in hybrid_branches:
                if heading in hybrid_mutated.get(str(hb.id), set()):
                    picked_hybrid = hb
                    break

            if picked_hybrid is not None:
                content = branch_sections.get(str(picked_hybrid.id), {}).get(heading, "")
                instructions.append(
                    {
                        "section": heading,
                        "action": "replace_section",
                        "content": f"{heading}\n\n{content.strip()}\n",
                        "source_branch_id": str(picked_hybrid.id),
                    }
                )
                continue

            # Priority 3: keep original
            instructions.append(
                {
                    "section": heading,
                    "action": "keep_original",
                    "content": "",
                    "source_branch_id": "",
                }
            )

        return instructions

    # ------------------------------------------------------------------
    # Section parsing
    # ------------------------------------------------------------------

    def _extract_sections(self, content: str) -> dict[str, str]:
        """Parse markdown into {section_heading_line: section_body} dict.

        The heading_line includes the leading # characters, e.g. "## Overview".
        The body is the text between this heading and the next heading at the
        same or higher level (or end of document).
        """
        matches = list(_HEADING_RE.finditer(content))
        if not matches:
            return {}

        sections: dict[str, str] = {}
        for i, match in enumerate(matches):
            heading_line = match.group(0).strip()
            body_start = match.end()
            body_end = matches[i + 1].start() if i + 1 < len(matches) else len(content)
            body = content[body_start:body_end].strip()
            sections[heading_line] = body

        return sections

    def _section_exists(self, content: str, section_heading: str) -> bool:
        """Return True if the section heading already appears in content."""
        # Normalize: strip leading/trailing whitespace for comparison
        heading_text = section_heading.strip()
        return heading_text in content

    def _replace_section(self, content: str, heading: str, new_block: str) -> str:
        """Replace the named section (heading + its body) with new_block.

        If the heading is not found in content, the content is returned unchanged.
        """
        heading_escaped = re.escape(heading.strip())
        # Match from the heading line to just before the next heading of equal/higher level
        # or end of string.
        heading_hashes = len(re.match(r"^(#+)", heading.strip()).group(1))  # type: ignore[union-attr]
        higher_or_equal = f"{{1,{heading_hashes}}}"
        pattern = re.compile(
            rf"({heading_escaped})\s*\n.*?(?=\n#{higher_or_equal}\s|\Z)",
            re.DOTALL | re.MULTILINE,
        )
        new_block_clean = new_block.strip()
        result, count = pattern.subn(new_block_clean, content, count=1)
        if count == 0:
            # Heading not found; return content unchanged
            return content
        return result

    # ------------------------------------------------------------------
    # Conflict detection
    # ------------------------------------------------------------------

    def _detect_conflicts(self, branches: list[SpecBranch]) -> list[str]:
        """Identify sections that were modified differently in more than one branch.

        Two branches conflict on a section when both have a mutation record whose
        path references that section, but the replacement text differs.
        """
        if len(branches) < 2:
            return []

        # Build {section_name: {branch_id: replacement_text}} mapping
        section_replacements: dict[str, dict[str, str]] = {}

        for branch in branches:
            for mutation in branch.mutations:
                path = mutation.get("path", "")
                replacement = mutation.get("replacement", "")
                # Normalise path → section name
                section_key = path.split(":", 1)[-1] if ":" in path else path
                if section_key not in section_replacements:
                    section_replacements[section_key] = {}
                section_replacements[section_key][str(branch.id)] = replacement

        conflicts: list[str] = []
        for section, branch_map in section_replacements.items():
            if len(branch_map) > 1:
                unique_replacements = set(branch_map.values())
                if len(unique_replacements) > 1:
                    conflicts.append(section)

        return conflicts

    # ------------------------------------------------------------------
    # Mutation helper
    # ------------------------------------------------------------------

    def _mutated_sections(self, branch: SpecBranch) -> set[str]:
        """Return the set of section headings mutated by a branch.

        Uses BranchingEngine.list_changed_sections logic directly on the
        branch content to identify affected markdown headings.
        """
        from spec_sandbox.branching.engine import BranchingEngine

        engine = BranchingEngine()
        changed = engine.list_changed_sections(branch)
        return set(changed)

    # ------------------------------------------------------------------
    # Scenario header stripping
    # ------------------------------------------------------------------

    def _strip_scenario_header(self, content: str) -> str:
        """Remove the YAML frontmatter + HTML comment banner injected by BranchingEngine."""
        stripped = _SCENARIO_FRONTMATTER_RE.sub("", content, count=1)
        return stripped
