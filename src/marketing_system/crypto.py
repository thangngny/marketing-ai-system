"""
Cryptographic security module for Buzz Marketing OS.
Uses Windows DPAPI (Data Protection API) via win32crypt to encrypt secrets and
token caches at rest, bound to the current Windows user identity.

INVARIANT:
In PRODUCTION, secret storage fails closed if a secure operating system
keyring/DPAPI backend is unavailable. Base64 encoding is strictly prohibited
in production and restricted solely to isolated mock/test environments.
"""
from __future__ import annotations

import base64
import json
import logging
import os
import sys
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# Magic prefix to detect DPAPI encrypted payloads
DPAPI_MAGIC = b"BUZZ_DPAPI_V1\x00"
MOCK_TEST_MAGIC = b"BUZZ_MOCK_TEST_ONLY\x00"
LEGACY_FALLBACK_MAGIC = b"BUZZ_FALLBACK_V1\x00"


def is_dpapi_available() -> bool:
    if sys.platform != "win32":
        return False
    try:
        import win32crypt
        return True
    except ImportError:
        return False


def is_production_mode() -> bool:
    env_name = os.environ.get("ENVIRONMENT", os.environ.get("BUZZ_ENV", "")).lower()
    return env_name in ("production", "prod")


def encrypt_data(data: bytes, description: str = "BuzzSecret") -> bytes:
    """
    Encrypts bytes using Windows DPAPI bound to the current Windows user.
    Fails closed in production if DPAPI is unavailable.
    """
    if is_dpapi_available():
        import win32crypt
        encrypted = win32crypt.CryptProtectData(
            data,
            description,
            None,  # optional entropy
            None,  # reserved
            None,  # prompt struct
            0      # flags: CRYPTPROTECT_UI_FORBIDDEN (default)
        )
        return DPAPI_MAGIC + encrypted

    # Security Invariant: Production MUST fail closed
    if is_production_mode():
        raise RuntimeError(
            "SECURITY INVARIANT VIOLATION: Production requires Windows DPAPI secret backend. "
            "Insecure fallback is strictly prohibited in production."
        )

    # Isolated Mock / Unit test fallback only
    return MOCK_TEST_MAGIC + base64.b64encode(data)


def decrypt_data(data: bytes) -> bytes:
    """Decrypts bytes previously encrypted with encrypt_data."""
    if data.startswith(DPAPI_MAGIC):
        if not is_dpapi_available():
            raise RuntimeError("DPAPI encrypted data found but win32crypt is not available on this platform")
        import win32crypt
        raw_cipher = data[len(DPAPI_MAGIC):]
        _, decrypted = win32crypt.CryptUnprotectData(
            raw_cipher,
            None,
            None,
            None,
            0
        )
        return decrypted

    if data.startswith(MOCK_TEST_MAGIC) or data.startswith(LEGACY_FALLBACK_MAGIC):
        if is_production_mode():
            raise RuntimeError(
                "SECURITY INVARIANT VIOLATION: Insecure test secret payload detected in production environment."
            )
        prefix_len = len(MOCK_TEST_MAGIC) if data.startswith(MOCK_TEST_MAGIC) else len(LEGACY_FALLBACK_MAGIC)
        return base64.b64decode(data[prefix_len:])

    # Legacy unencrypted payload
    if is_production_mode():
        raise RuntimeError("SECURITY INVARIANT VIOLATION: Plaintext secret detected in production environment.")
    return data


def save_secure_json(path: Path | str, payload: Dict[str, Any], description: str = "BuzzTokenCache") -> None:
    """
    Safely serializes a dictionary to encrypted JSON on disk.
    Creates parent directories and ensures atomic overwrite.
    """
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    raw_json = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
    cipher_bytes = encrypt_data(raw_json, description=description)

    # Write atomically via temp file
    temp_target = target.with_suffix(f"{target.suffix}.tmp.{os.getpid()}")
    try:
        temp_target.write_bytes(cipher_bytes)
        if target.exists():
            target.unlink()
        temp_target.rename(target)
    finally:
        if temp_target.exists():
            try:
                temp_target.unlink()
            except OSError:
                pass


def load_secure_json(path: Path | str) -> Optional[Dict[str, Any]]:
    """
    Loads encrypted JSON payload from disk.
    If the file exists as legacy plaintext JSON, automatically upgrades/encrypts it.
    Returns None if file does not exist or payload is corrupted.
    """
    target = Path(path)
    if not target.exists():
        return None

    try:
        raw_bytes = target.read_bytes()
        if not raw_bytes:
            return None

        # Check if encrypted with DPAPI or test marker
        if raw_bytes.startswith(DPAPI_MAGIC) or raw_bytes.startswith(MOCK_TEST_MAGIC) or raw_bytes.startswith(LEGACY_FALLBACK_MAGIC):
            decrypted = decrypt_data(raw_bytes)
            return json.loads(decrypted.decode("utf-8"))

        # Legacy plaintext migration (only permitted outside strict production)
        if is_production_mode():
            raise RuntimeError("Unencrypted plaintext token file rejected in production mode")

        try:
            legacy_text = raw_bytes.decode("utf-8")
            data = json.loads(legacy_text)
            # Migrate immediately in-place to DPAPI encryption
            save_secure_json(target, data, description="BuzzMigratedTokenCache")
            return data
        except (UnicodeDecodeError, json.JSONDecodeError):
            return None
    except Exception as e:
        # Never log raw token contents or details
        logger.warning("Failed to safely read secure JSON from %s: %s", target.name, type(e).__name__)
        return None
