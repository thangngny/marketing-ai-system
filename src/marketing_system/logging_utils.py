from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


_SECRET_KEYS = re.compile(r"secret|token|password|authorization|cookie|private|api.?key", re.I)


def redact(value: Any, key: str = "") -> Any:
    if _SECRET_KEYS.search(key):
        return "[REDACTED]" if value else value
    if isinstance(value, dict):
        return {k: redact(v, k) for k, v in value.items()}
    if isinstance(value, list):
        return [redact(v) for v in value]
    return value


def write_event(log_dir: Path, **event: Any) -> None:
    log_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        **redact(event),
    }
    with (log_dir / "marketing.jsonl").open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False, default=str) + "\n")

