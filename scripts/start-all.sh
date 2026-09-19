#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PID_FILE="$ROOT/runtime/hermes-marketing-gateway.pid"
mkdir -p "$ROOT/runtime"
if [[ -f "$PID_FILE" ]] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
  echo "Marketing gateway already running (PID $(cat "$PID_FILE"))."
  exit 0
fi
rm -f "$PID_FILE"
test -x "$HOME/.hermes/profiles/marketing/venv/bin/python" || true
grep -Eq '^BUZZ_PRIVATE_KEY=.+$' "$HOME/.hermes/profiles/marketing/.env" || { echo 'Buzz identity missing.' >&2; exit 1; }
cd "$ROOT"
nohup hermes -p marketing gateway run >"$ROOT/logs/hermes-gateway.log" 2>&1 &
echo $! >"$PID_FILE"
echo "Marketing gateway started (PID $!)."

