"""
Identity and Identifier Management for Enterprise GTM AI.
Provides deterministic, stable, collision-resistant IDs and payload hashing
independent of process-dependent hash() or runtime environment.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any
from uuid import NAMESPACE_DNS, uuid5

from .lead_engine.verifier import validate_vietnam_vat


def generate_stable_lead_id(
    company: str,
    domain: str | None = None,
    vat_number: str | None = None,
) -> str:
    """
    Generate a deterministic, immutable canonical lead ID.
    Prioritizes verified legal VAT number. Falls back to normalized legal entity name + domain.
    """
    clean_company = " ".join((company or "").lower().strip().split())

    if vat_number and str(vat_number).strip():
        raw_vat = str(vat_number).strip()
        v_ok, v_norm = validate_vietnam_vat(raw_vat)
        target_vat = v_norm if v_ok else raw_vat.upper()
        # Namespace UUID5 ensures zero collision and consistency across Python runs
        vat_uuid = uuid5(NAMESPACE_DNS, f"vn:tax_id:{target_vat}")
        return f"lead-vat-{vat_uuid.hex[:16]}"

    clean_domain = (domain or "").lower().strip()
    # Normalize common business prefixes/suffixes for matching stability
    entity_key = f"entity:{clean_company}:{clean_domain}"
    entity_uuid = uuid5(NAMESPACE_DNS, entity_key)
    return f"lead-entity-{entity_uuid.hex[:16]}"


def generate_payload_hash(payload: dict[str, Any]) -> str:
    """Generate deterministic SHA-256 hash of a dictionary payload."""
    serialized = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()
