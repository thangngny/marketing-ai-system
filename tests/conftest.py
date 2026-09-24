"""Hermetic defaults for the automated suite.

The developer workstation carries a real `.env.local` (production mode) and real
Windows Credential Manager entries. Unit/contract tests must not pick those up:
doing so made results machine-dependent and let a "unit" test call a live API.
Live checks stay opt-in via RUN_LIVE_CONNECTOR_TESTS=1 (see test_live_connectors.py).
"""

from __future__ import annotations

import os
import tempfile

import pytest

LIVE = os.getenv("RUN_LIVE_CONNECTOR_TESTS") == "1"

# Never let tests write into the real data/ or logs/ directories.
_SCRATCH = tempfile.mkdtemp(prefix="marketing-tests-")
os.environ["MARKETING_DATA_DIR"] = os.path.join(_SCRATCH, "data")
os.environ["MARKETING_LOG_DIR"] = os.path.join(_SCRATCH, "logs")

if not LIVE:
    # Must run before any test module imports marketing_system.mcp_server,
    # which builds its Settings at import time.
    os.environ["MARKETING_ENV_FILE"] = os.devnull
    os.environ["MARKETING_ENVIRONMENT"] = "mock"
    os.environ["MARKETING_SAFE_DRY_RUN"] = "true"
    os.environ.pop("MARKETING_RUNTIME", None)


@pytest.fixture(autouse=True)
def _no_os_credentials(request, monkeypatch):
    if LIVE and request.node.get_closest_marker("live"):
        return
    monkeypatch.setattr("marketing_system.connectors.base.read_credential", lambda _name: None)
    monkeypatch.setattr("marketing_system.connectors.zoho_mcp.read_credential", lambda _name: None)
    monkeypatch.setattr("marketing_system.connectors.zoho_delegate.available", lambda: False)


def pytest_configure(config):
    config.addinivalue_line("markers", "live: test talks to a real provider and needs credentials")
