from __future__ import annotations

import difflib
import re
import uuid
from datetime import datetime, timezone
from typing import Any

from spec_sandbox.domain.models import BaseSpec, Scenario, ScenarioParameter, SpecBranch


class BranchingEngine:
    """Creates and manages spec branches by applying scenario mutations."""

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def create_branch(self, base_spec: BaseSpec, scenario: Scenario) -> SpecBranch:
        """Clone base spec and apply all scenario parameter mutations.

        For each ScenarioParameter in the scenario:
        1. Search the spec content for the original_value string (case-insensitive).
        2. If found, replace it with new_value and record the mutation.
        3. If not found, append a '## Scenario Override: {key}' section at the end.

        The scenario context block is prepended to the resulting content.
        """
        working_content = base_spec.content
        mutations: list[dict[str, str]] = []

        for param in scenario.parameters:
            working_content, mutation = self._apply_mutation(working_content, param)
            mutations.append(mutation)

        final_content = self._inject_scenario_header(working_content, scenario)

        branch = SpecBranch(
            id=uuid.uuid4(),
            base_spec_id=base_spec.id,
            scenario_id=scenario.id,
            name=f"{base_spec.title} @ {scenario.name}",
            content=final_content,
            mutations=mutations,
            created_at=datetime.now(timezone.utc),
        )
        return branch

    def _apply_mutation(
        self, content: str, param: ScenarioParameter
    ) -> tuple[str, dict[str, str]]:
        """Apply a single parameter mutation to spec content.

        Returns (new_content, mutation_record) where mutation_record is a dict
        with keys: 'path', 'original', 'replacement', 'reason'.
        """
        original_str = str(param.original_value)
        new_str = str(param.new_value)

        # Case-insensitive search using re.sub with re.IGNORECASE.
        # We escape the original value so regex metacharacters in spec text don't
        # cause errors.
        pattern = re.compile(re.escape(original_str), re.IGNORECASE)

        if pattern.search(content):
            # Preserve the case of the very first match for the mutation record.
            first_match = pattern.search(content)
            assert first_match is not None  # guarded by branch above
            actual_original = first_match.group(0)

            new_content = pattern.sub(new_str, content)

            mutation: dict[str, str] = {
                "path": f"parameter:{param.key}",
                "original": actual_original,
                "replacement": new_str,
                "reason": param.rationale or f"Scenario override for '{param.name}'",
            }
        else:
            # Value not found — append an explicit override section.
            override_section = (
                f"\n\n## Scenario Override: {param.key}\n\n"
                f"**Parameter:** {param.name}  \n"
                f"**Dimension:** {param.dimension}  \n"
                f"**Value:** {new_str}  \n"
                f"**Rationale:** {param.rationale or 'No rationale provided.'}\n"
            )
            new_content = content + override_section

            mutation = {
                "path": f"appended:scenario_override:{param.key}",
                "original": "(not found in original spec)",
                "replacement": new_str,
                "reason": (
                    f"Original value '{original_str}' was not found in spec content; "
                    f"override section appended. "
                    + (param.rationale or f"Scenario override for '{param.name}'")
                ),
            }

        return new_content, mutation

    def _inject_scenario_header(self, content: str, scenario: Scenario) -> str:
        """Prepend a scenario context block to the spec markdown.

        The injected block uses a YAML-style frontmatter fence so that tools
        that parse frontmatter can extract the scenario metadata.  An HTML
        comment banner is also added as a visible marker when frontmatter
        stripping is not performed.
        """
        now_str = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        # Build YAML-style parameter list.
        param_lines: list[str] = []
        for p in scenario.parameters:
            param_lines.append(f"  - key: {p.key}")
            param_lines.append(f"    name: {p.name}")
            param_lines.append(f"    original: {p.original_value}")
            param_lines.append(f"    new: {p.new_value}")
            param_lines.append(f"    dimension: {p.dimension}")

        params_yaml = "\n".join(param_lines) if param_lines else "  []"

        header = (
            f"---\n"
            f"scenario: {scenario.name}\n"
            f"scenario_id: {scenario.id}\n"
            f"parameters:\n"
            f"{params_yaml}\n"
            f"---\n"
            f"<!-- SCENARIO BRANCH: {scenario.name} -->\n"
            f"<!-- Generated: {now_str} -->\n"
            f"\n"
        )

        return header + content

    # ------------------------------------------------------------------
    # Diff and inspection helpers
    # ------------------------------------------------------------------

    def diff_branches(self, branch_a: SpecBranch, branch_b: SpecBranch) -> list[dict[str, Any]]:
        """Return line-level unified diff between two branch contents.

        Returns a list of diff-hunk dicts, each with keys:
        - 'hunk_header': the @@ ... @@ line
        - 'lines': list of diff lines (prefixed with '+', '-', or ' ')
        - 'branch_a_id': str UUID of branch_a
        - 'branch_b_id': str UUID of branch_b
        """
        lines_a = branch_a.content.splitlines(keepends=True)
        lines_b = branch_b.content.splitlines(keepends=True)

        diff_iter = difflib.unified_diff(
            lines_a,
            lines_b,
            fromfile=f"branch/{branch_a.id} ({branch_a.name})",
            tofile=f"branch/{branch_b.id} ({branch_b.name})",
            lineterm="",
        )

        hunks: list[dict[str, Any]] = []
        current_hunk: dict[str, Any] | None = None

        for line in diff_iter:
            if line.startswith("@@"):
                if current_hunk is not None:
                    hunks.append(current_hunk)
                current_hunk = {
                    "hunk_header": line.strip(),
                    "lines": [],
                    "branch_a_id": str(branch_a.id),
                    "branch_b_id": str(branch_b.id),
                }
            elif line.startswith("---") or line.startswith("+++"):
                # Skip the file header lines; they're captured in branch metadata.
                continue
            else:
                if current_hunk is not None:
                    current_hunk["lines"].append(line.rstrip("\n"))

        if current_hunk is not None:
            hunks.append(current_hunk)

        return hunks

    def list_changed_sections(self, branch: SpecBranch) -> list[str]:
        """Return names of markdown sections (## headings) that were mutated.

        A section is considered changed if any of the branch's mutation records
        have a 'replacement' value that appears within that section's content,
        or if an 'appended' mutation path targets it.

        Approach:
        1. Split the branch content into sections by ATX headings (# / ## / etc.).
        2. For each mutation record, find which section the replacement text lives in.
        3. Also include any 'Scenario Override' sections appended by the engine.
        """
        # Parse markdown sections: collect (heading_text, section_body) pairs.
        heading_pattern = re.compile(r"^(#{1,6})\s+(.+)$", re.MULTILINE)
        content = branch.content

        matches = list(heading_pattern.finditer(content))
        sections: list[tuple[str, str]] = []  # (heading, body_text)

        for i, match in enumerate(matches):
            heading_text = match.group(2).strip()
            body_start = match.end()
            body_end = matches[i + 1].start() if i + 1 < len(matches) else len(content)
            body = content[body_start:body_end]
            sections.append((heading_text, body))

        changed: list[str] = []

        for mutation in branch.mutations:
            replacement = mutation.get("replacement", "")
            path = mutation.get("path", "")

            # Appended override sections are trivially "Scenario Override: <key>".
            if path.startswith("appended:scenario_override:"):
                key = path.split("appended:scenario_override:", 1)[-1]
                section_name = f"Scenario Override: {key}"
                if section_name not in changed:
                    changed.append(section_name)
                continue

            # For in-place replacements: find which section now contains the
            # replacement text.
            if replacement:
                for heading_text, body in sections:
                    if replacement in body and heading_text not in changed:
                        changed.append(heading_text)
                        break

        return changed
