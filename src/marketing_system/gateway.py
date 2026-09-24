"""Conversation Gateway: Buzz (or any surface) → runtime-neutral ConversationInput.

Owns normalization, identity/channel mapping and event dedupe. Holds no
provider logic. The wire transport itself is supplied by the active runtime
(Hermes native gateway or Buzz Desktop ACP); both hand the event here.
"""

from __future__ import annotations

import re

from .runtime.base import ConversationInput
from .telemetry import new_correlation_id
from .workflows.store import WorkflowStore

_MENTION = re.compile(r"(?:^|\s)@\S+")
_HEX64 = re.compile(r"^[0-9a-f]{64}$")


def normalize(text: str, *, source: str = "buzz", event_id: str | None = None, channel_id: str | None = None,
              user_id: str | None = None, correlation_id: str | None = None) -> ConversationInput:
    clean = " ".join(_MENTION.sub(" ", text or "").split())
    return ConversationInput(
        text=clean,
        correlation_id=correlation_id or new_correlation_id(),
        source=source,
        buzz_event_id=event_id if event_id and _HEX64.match(event_id.lower()) else None,
        channel_id=channel_id or None,
        user_id=user_id.lower() if user_id and _HEX64.match(user_id.lower()) else None,
    )


def ingest(store: WorkflowStore, text: str, **kwargs) -> tuple[ConversationInput, bool]:
    """Return (input, is_duplicate). Duplicate Buzz deliveries of one event are processed once."""
    request = normalize(text, **kwargs)
    if request.buzz_event_id is None:
        return request, False
    first = store.claim_event(request.buzz_event_id, request.channel_id, request.user_id, request.correlation_id)
    return request, not first
