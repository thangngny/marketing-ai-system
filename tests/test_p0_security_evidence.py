"""
Tests for P0: Security, DPAPI Token Encryption, Concurrency Lock, Evidence Data Model.
"""
import json
import os
import sys
import tempfile
import time
from pathlib import Path
import pytest

from marketing_system.crypto import (
    encrypt_data,
    decrypt_data,
    save_secure_json,
    load_secure_json,
    is_dpapi_available,
    DPAPI_MAGIC,
)
from marketing_system.models import LeadCandidate, EvidenceItem, EvidenceStatus, Environment


def test_crypto_direct_roundtrip():
    plain = b"super_secret_zoho_refresh_token_12345"
    encrypted = encrypt_data(plain, description="TestToken")
    assert encrypted != plain
    assert DPAPI_MAGIC in encrypted or b"BUZZ_FALLBACK_V1" in encrypted
    decrypted = decrypt_data(encrypted)
    assert decrypted == plain


def test_save_and_load_secure_json(tmp_path):
    cache_file = tmp_path / "secure_token.json"
    data = {
        "access_token": "1000.sample_token_xyz",
        "api_domain": "https://www.zohoapis.com",
        "expires_at": time.time() + 3600,
    }
    save_secure_json(cache_file, data, description="TestCache")
    
    # Verify raw file content is encrypted on disk
    raw_content = cache_file.read_bytes()
    assert b"1000.sample_token_xyz" not in raw_content
    
    loaded = load_secure_json(cache_file)
    assert loaded == data
    assert loaded["access_token"] == "1000.sample_token_xyz"


def test_legacy_plaintext_migration(tmp_path):
    legacy_file = tmp_path / "legacy_token.json"
    legacy_data = {
        "access_token": "1000.legacy_token_abc",
        "api_domain": "https://www.zohoapis.com",
        "expires_at": 123456789,
    }
    # Write legacy plaintext
    legacy_file.write_text(json.dumps(legacy_data), encoding="utf-8")
    
    # Load should auto-migrate to encrypted
    migrated = load_secure_json(legacy_file)
    assert migrated == legacy_data
    
    # Verify raw file is now encrypted
    raw_after = legacy_file.read_bytes()
    assert b"1000.legacy_token_abc" not in raw_after


def test_evidence_model_separation():
    candidate = LeadCandidate(
        company="CÔNG TY TNHH PHÂN PHỐI THIẾT BỊ MINH TÂM",
        domain="minhtammedical.vn",
        vat_number="0312345678",
        source="apollo_crawler",
        environment=Environment.PRODUCTION,
    )
    # Add verified legal/identity evidence
    candidate.add_evidence(
        field_name="vat_number",
        field_value="0312345678",
        source_provider="masothue_vn",
        evidence_status=EvidenceStatus.VERIFIED,
        confidence=1.0,
        verification_method="tax_code_registry",
    )
    candidate.add_evidence(
        field_name="domain_active",
        field_value=True,
        source_provider="dns_mx",
        evidence_status=EvidenceStatus.VERIFIED,
        confidence=1.0,
        verification_method="dns_lookup",
    )
    
    # Add inferred commercial intelligence evidence
    candidate.add_evidence(
        field_name="logistics_type",
        field_value="Air Freight Express",
        source_provider="customs_manifest_analysis",
        evidence_status=EvidenceStatus.INFERRED,
        confidence=0.82,
        verification_method="llm_classification",
    )
    candidate.add_evidence(
        field_name="est_monthly_kg",
        field_value=2500,
        source_provider="icp_volume_estimator",
        evidence_status=EvidenceStatus.INFERRED,
        confidence=0.75,
    )
    
    verified = candidate.get_verified_fields()
    inferred = candidate.get_inferred_fields()
    
    assert "vat_number" in verified
    assert "domain_active" in verified
    assert "logistics_type" not in verified
    
    assert "logistics_type" in inferred
    assert "est_monthly_kg" in inferred
    assert "vat_number" not in inferred
    
    assert len(candidate.evidence) == 4
    assert candidate.stage == "NEW"
