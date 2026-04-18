"""Anthropic SDK-backed LLM provider."""
from __future__ import annotations

import json
import re

import anthropic

from spec_sandbox.domain.models import (
    AgentRole,
    AgentRun,
    SpecBranch,
    ProjectionArtifact,
    BranchComparison,
    BaseSpec,
    Scenario,
)
from spec_sandbox.providers.base import LLMProvider


class AnthropicProvider(LLMProvider):
    """Calls the real Anthropic Messages API."""

    def __init__(self, api_key: str, model: str = "claude-sonnet-4-6") -> None:
        self.model = model
        self.client = anthropic.AsyncAnthropic(api_key=api_key)

    async def complete(self, system: str, user: str, max_tokens: int = 4096) -> str:
        """Call the Anthropic Messages API and return the text of the first content block."""
        message = await self.client.messages.create(
            model=self.model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        return message.content[0].text

    async def complete_json(self, system: str, user: str, max_tokens: int = 4096) -> dict:
        """Call complete(), strip any markdown code fences, parse and return JSON dict.

        Raises:
            ValueError: if the response cannot be parsed as JSON.
        """
        raw = await self.complete(system=system, user=user, max_tokens=max_tokens)
        cleaned = _strip_markdown_fences(raw)
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"AnthropicProvider.complete_json: failed to parse JSON. "
                f"Parse error: {exc}. Raw text:\n{raw}"
            ) from exc


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _strip_markdown_fences(text: str) -> str:
    """Remove ```json ... ``` or ``` ... ``` wrappers if present."""
    text = text.strip()
    # Match optional language identifier after the opening fence
    pattern = re.compile(r"^```(?:json)?\s*\n?(.*?)\n?```$", re.DOTALL)
    match = pattern.match(text)
    if match:
        return match.group(1).strip()
    return text
