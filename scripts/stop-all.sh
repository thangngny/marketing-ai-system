#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PID_FILE="$ROOT/runtime/hermes-marketing-gateway.pid"
if [[ ! -f "$PID_FILE" ]]; then echo 'Marketing gateway is not running.'; exit 0; fi
PID="$(cat "$PID_FILE")"
if kill -0 "$PID" 2>/dev/null; then
  CMD="$(ps -p "$PID" -o args=)"
  [[ "$CMD" == *hermes*marketing*gateway* ]] || { echo "PID $PID is not the marketing gateway; refusing." >&2; exit 1; }
  kill "$PID"
fi
rm -f "$PID_FILE"
echo 'Marketing gateway stopped.'

