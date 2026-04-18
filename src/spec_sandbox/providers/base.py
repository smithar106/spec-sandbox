"""Abstract LLM provider interface. Swap implementations without changing agent logic."""
from abc import ABC, abstractmethod


class LLMProvider(ABC):
    @abstractmethod
    async def complete(self, system: str, user: str, max_tokens: int = 4096) -> str:
        """Return completion text."""
        ...

    @abstractmethod
    async def complete_json(self, system: str, user: str, max_tokens: int = 4096) -> dict:
        """Return parsed JSON from completion."""
        ...
