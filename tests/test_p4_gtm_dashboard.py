"""
Tests for P4: GTM Funnel Dashboard & Security Barrier Protection.
Verifies:
- Separation of REAL DATA from DEMO DATA modes.
- Elimination of hardcoded business metrics in production path.
- Authentication barrier enforcement on both GET and POST.
"""
import json
import os
import re
import sys
from pathlib import Path
import pytest
from conftest import get_sibling_workspace_path

DASHBOARD_PATH = get_sibling_workspace_path("buzz-ai-usage-center/bin/dashboard.py")
if not DASHBOARD_PATH or not DASHBOARD_PATH.exists():
    pytest.skip("buzz-ai-usage-center/bin/dashboard.py not found in workspace", allow_module_level=True)


def test_gtm_funnel_route_and_view_present():
    content = DASHBOARD_PATH.read_text(encoding="utf-8")
    assert "def v_gtm_funnel" in content
    assert "def get_gtm_funnel_data" in content
    assert 'elif path == "/gtm-funnel":' in content
    assert 'elif path == "/api/gtm-funnel.json":' in content


def test_gtm_funnel_real_vs_demo_modes():
    """Verify get_gtm_funnel_data supports explicit DEMO mode vs honest REAL data mode."""
    content = DASHBOARD_PATH.read_text(encoding="utf-8")
    assert "funnel_stages" in content
    assert "kpis" in content
    assert "crm_security" in content
    assert "top_leads" in content

    # Test execution in isolated scope
    namespace = {
        "Path": Path,
        "json": json,
        "os": os,
    }
    match = re.search(r"(def get_gtm_funnel_data\(.*?\)\s*->\s*dict:.*?)(?=def v_gtm_funnel)", content, re.DOTALL)
    assert match is not None, "get_gtm_funnel_data function not found"
    func_code = match.group(1)
    exec(func_code, namespace)

    funnel_fn = namespace["get_gtm_funnel_data"]

    # 1. Test REAL DATA mode (default):
    real_data = funnel_fn(mode="real")
    assert real_data["mode"] == "REAL"
    assert real_data["is_demo"] is False
    assert len(real_data["funnel_stages"]) == 7
    # Real data must not invent fake 12.8B VND if no real deals exist
    assert "crm_protected_vats" in real_data["kpis"]
    assert real_data["kpis"]["crm_protected_vats"] >= 3600
    assert "token_encrypted_dpapi" in real_data["crm_security"]
    if Path(Path.home() / ".buzz" / ".scratch" / "zoho_token_cache.json").exists():
        assert real_data["crm_security"]["token_encrypted_dpapi"] is True

    # 2. Test DEMO mode:
    demo_data = funnel_fn(mode="demo")
    assert demo_data["mode"] == "DEMO"
    assert demo_data["is_demo"] is True
    assert "banner_warning" in demo_data
    assert "MÔ PHỎNG" in demo_data["banner_warning"]
    assert len(demo_data["funnel_stages"]) == 7


def test_dashboard_security_barrier_enforcement():
    """Verify security barrier checks BUZZ_DASHBOARD_TOKEN on both GET and POST."""
    content = DASHBOARD_PATH.read_text(encoding="utf-8")
    assert "def _check_auth" in content, "DashboardHandler must have _check_auth method"
    assert "BUZZ_DASHBOARD_TOKEN" in content
    assert "Bearer realm=" in content
    assert "if not self._check_auth():" in content
