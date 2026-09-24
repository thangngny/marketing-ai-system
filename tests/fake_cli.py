"""Stand-in for hermes / claude / codex executables in runtime contract tests.

usage: python fake_cli.py <flavor> <cli args...>
FAKE_MODE=ok|fail|sleep|empty controls behaviour.
"""

import json
import os
import sys
import time

flavor, args = sys.argv[1], sys.argv[2:]
mode = os.getenv("FAKE_MODE", "ok")
if mode == "fail":
    sys.exit(3)
if mode == "sleep":
    time.sleep(10)

if flavor == "hermes":
    prompt = args[args.index("-z") + 1]
elif flavor == "claude":
    prompt = args[args.index("-p") + 1]
else:
    prompt = args[-1]

corr = os.getenv("MARKETING_CORRELATION_ID", "")
if mode == "empty":
    body = ""
elif "JSON" in prompt:
    body = json.dumps({"echo_correlation": corr, "flavor": flavor, "ok": True})
else:
    body = f"{flavor.upper()}_OK corr={corr} prompt_has_corr={corr in prompt}"

if flavor == "claude":
    session = args[args.index("--resume") + 1] if "--resume" in args else "fake-session-1"
    print(json.dumps({"result": body, "session_id": session}))
elif flavor == "codex":
    out = args[args.index("--output-last-message") + 1]
    with open(out, "w", encoding="utf-8") as handle:
        handle.write(body)
    print("codex banner noise\n" + body)
else:
    print(body)
