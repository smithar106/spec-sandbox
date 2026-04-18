"""AgentRunner — executes one or all agent roles against a SpecBranch."""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone

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
from spec_sandbox.agents.prompts import AGENT_PROMPTS
from spec_sandbox.providers.base import LLMProvider

logger = logging.getLogger(__name__)

_ALL_ROLES: list[AgentRole] = list(AgentRole)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class AgentRunner:
    """Runs agent roles against a SpecBranch and returns populated AgentRun records."""

    def __init__(self, provider: LLMProvider) -> None:
        self.provider = provider

    async def run(self, branch: SpecBranch, role: AgentRole) -> AgentRun:
        """Run a single agent role against *branch*.

        The method:
          1. Creates an AgentRun in PENDING state.
          2. Transitions to RUNNING, calls the LLM provider.
          3. On success, stores the raw JSON/text output and transitions to COMPLETED.
          4. On failure, stores the error message and transitions to FAILED.

        Returns the completed (or failed) AgentRun.
        """
        run = AgentRun(
            branch_id=branch.id,
            role=role,
            status=RunStatus.PENDING,
        )

        # --- transition to RUNNING ---
        run.status = RunStatus.RUNNING
        run.started_at = _utcnow()

        system_prompt, output_schema = AGENT_PROMPTS[role]

        # Build the user message: full branch spec content + a reminder of expected schema
        user_message = _build_user_message(branch, output_schema)

        try:
            # Attempt to get structured JSON first; fall back to plain text
            try:
                output_dict = await self.provider.complete_json(
                    system=system_prompt,
                    user=user_message,
                )
                run.output_json = output_dict
            except ValueError:
                # Provider could not parse JSON — store raw text as markdown
                raw_text = await self.provider.complete(
                    system=system_prompt,
                    user=user_message,
                )
                run.output_markdown = raw_text

            run.status = RunStatus.COMPLETE
            run.completed_at = _utcnow()

            logger.debug(
                "AgentRunner: role=%s branch=%s completed",
                role.value,
                branch.id,
            )

        except Exception as exc:  # noqa: BLE001
            run.status = RunStatus.FAILED
            run.output_markdown = f"ERROR: {exc}"
            run.completed_at = _utcnow()

            logger.warning(
                "AgentRunner: role=%s branch=%s FAILED: %s",
                role.value,
                branch.id,
                exc,
            )

        return run

    async def run_all_roles(
        self,
        branch: SpecBranch,
        roles: list[AgentRole] | None = None,
    ) -> list[AgentRun]:
        """Run all (or a subset of) agent roles concurrently using asyncio.gather.

        Args:
            branch: The SpecBranch to analyse.
            roles:  Subset of AgentRole values to run.  Defaults to all 8 roles.

        Returns:
            List of AgentRun records in the same order as *roles*.
        """
        effective_roles = roles if roles is not None else _ALL_ROLES
        tasks = [self.run(branch, role) for role in effective_roles]
        results: list[AgentRun] = await asyncio.gather(*tasks)
        return list(results)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_user_message(branch: SpecBranch, output_schema: dict) -> str:
    """Construct the user-turn message sent to the LLM provider."""
    schema_hint = json.dumps(output_schema, indent=2)
    return (
        f"## Spec Branch: {branch.name}\n\n"
        f"{branch.content or 'No spec content provided.'}\n\n"
        "---\n"
        "Analyse the spec above from your assigned perspective and return JSON "
        f"matching this schema exactly:\n```json\n{schema_hint}\n```"
    )
