"""
Tests for P4: GTM Funnel Dashboard & Security Barrier Protection.
"""
import json
import os
import sys
from pathlib import Path
import pytest

DASHBOARD_PATH = Path(r"C:\Users\Admin\buzz-ai-usage-center\bin\dashboard.py")


def test_gtm_funnel_route_and_view_present():
    content = DASHBOARD_PATH.read_text(encoding="utf-8")
    assert "def v_gtm_funnel" in content
    assert "def get_gtm_funnel_data" in content
    assert 'elif path == "/gtm-funnel":' in content
    assert 'elif path == "/api/gtm-funnel.json":' in content


def test_gtm_funnel_data_structure():
    # Read and parse get_gtm_funnel_data logic directly
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
    # Extract get_gtm_funnel_data definition
    start_idx = content.find("def get_gtm_funnel_data() -> dict:")
    end_idx = content.find("def v_gtm_funnel() -> str:")
    func_code = content[start_idx:end_idx]
    exec(func_code, namespace)

    funnel_fn = namespace["get_gtm_funnel_data"]
    data = funnel_fn()

    assert "funnel_stages" in data
    assert len(data["funnel_stages"]) == 7
    assert data["funnel_stages"][0]["count"] >= data["funnel_stages"][-1]["count"]

    assert "kpis" in data
    assert data["kpis"]["verified_leads"] >= 400
    assert data["kpis"]["crm_protected_vats"] >= 3600

    assert "crm_security" in data
    assert data["crm_security"]["token_encrypted_dpapi"] is True
    assert data["crm_security"]["concurrency_lock"] is True


def test_dashboard_security_barrier_enforcement():
    content = DASHBOARD_PATH.read_text(encoding="utf-8")
    assert "BUZZ_DASHBOARD_TOKEN" in content
    assert "Bearer realm=" in content
    assert "Valid Bearer token required" in content
