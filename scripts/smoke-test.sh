#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
export MARKETING_ENVIRONMENT=mock
export MARKETING_SAFE_DRY_RUN=true
uv run pytest
uv run marketing-system acceptance

