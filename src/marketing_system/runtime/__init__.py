from __future__ import annotations

import os

from .adapters import ClaudeRuntime, CodexRuntime, HermesRuntime
from .base import AgentRuntime, ConversationInput, RuntimeCapabilities, RuntimeHealth, RuntimeResult
from .mock import MockRuntime

RUNTIMES: dict[str, type[AgentRuntime]] = {
    "hermes": HermesRuntime,
    "claude": ClaudeRuntime,
    "codex": CodexRuntime,
    "mock": MockRuntime,
}


def get_runtime(name: str | None = None, environment: str | None = None) -> AgentRuntime:
    """MARKETING_RUNTIME selects the implementation; mock environments default to MockRuntime."""
    chosen = name or os.getenv("MARKETING_RUNTIME")
    if not chosen:
        chosen = "mock" if (environment or os.getenv("MARKETING_ENVIRONMENT", "mock")) == "mock" else "hermes"
    try:
        return RUNTIMES[chosen]()
    except KeyError:
        raise ValueError(f"Unknown runtime '{chosen}'. Known: {', '.join(RUNTIMES)}") from None


__all__ = [
    "AgentRuntime", "ConversationInput", "RuntimeResult", "RuntimeHealth", "RuntimeCapabilities",
    "HermesRuntime", "ClaudeRuntime", "CodexRuntime", "MockRuntime", "RUNTIMES", "get_runtime",
]
