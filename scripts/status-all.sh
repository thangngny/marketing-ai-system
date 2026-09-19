#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PID_FILE="$ROOT/runtime/hermes-marketing-gateway.pid"
if [[ -f "$PID_FILE" ]] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then echo "Hermes marketing gateway: RUNNING"; else echo "Hermes marketing gateway: STOPPED"; fi
cd "$ROOT"
uv run marketing-system status

