"""OpenTelemetry-shaped spans written to the existing JSONL log.

Each span is one line: trace_id (= correlation_id), span_id, parent_span_id,
name, latency_ms, result, error_code and flat attributes. No exporter is wired
yet; the record layout maps 1:1 onto an OTel span so one can be added later.
"""

from __future__ import annotations

import time
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path
from typing import Any, Iterator
from uuid import uuid4

from .logging_utils import write_event

_current: ContextVar["Span | None"] = ContextVar("marketing_span", default=None)


def new_correlation_id() -> str:
    return str(uuid4())


class Span:
    def __init__(self, name: str, trace_id: str, parent: "Span | None", attributes: dict[str, Any]):
        self.name = name
        self.trace_id = trace_id
        self.span_id = uuid4().hex[:16]
        self.parent_span_id = parent.span_id if parent else None
        self.attributes = dict(attributes)
        self.result = "OK"
        self.error_code: str | None = None

    def set(self, **attributes: Any) -> None:
        self.attributes.update({k: v for k, v in attributes.items() if v is not None})

    def fail(self, error_code: str, result: str = "ERROR") -> None:
        self.error_code = error_code
        self.result = result


def current_span() -> Span | None:
    return _current.get()


def current_trace_id() -> str | None:
    span = _current.get()
    return span.trace_id if span else None


@contextmanager
def span(name: str, log_dir: Path, *, trace_id: str | None = None, **attributes: Any) -> Iterator[Span]:
    parent = _current.get()
    resolved_trace = trace_id or (parent.trace_id if parent else new_correlation_id())
    inherited = {k: v for k, v in (parent.attributes if parent else {}).items() if k in _INHERITED}
    current = Span(name, resolved_trace, parent, {**inherited, **{k: v for k, v in attributes.items() if v is not None}})
    token = _current.set(current)
    started = time.perf_counter()
    try:
        yield current
    except Exception as exc:
        if current.error_code is None:
            current.fail(type(exc).__name__)
        raise
    finally:
        _current.reset(token)
        write_event(
            log_dir,
            kind="span",
            name=current.name,
            trace_id=current.trace_id,
            correlation_id=current.trace_id,
            span_id=current.span_id,
            parent_span_id=current.parent_span_id,
            latency_ms=round((time.perf_counter() - started) * 1000, 2),
            result=current.result,
            error_code=current.error_code,
            **current.attributes,
        )


# Attributes that describe the request context and should appear on every child span.
_INHERITED = {"workflow_id", "buzz_event_id", "channel_id", "user_id", "runtime", "environment"}
