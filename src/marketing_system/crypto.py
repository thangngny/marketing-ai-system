"""
Cryptographic security module for Buzz Marketing OS.
Uses Windows DPAPI (Data Protection API) via win32crypt to encrypt secrets and
token caches at rest, bound to the current Windows user identity.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, Optional

# Magic prefix to detect encrypted payloads
DPAPI_MAGIC = b"BUZZ_DPAPI_V1\x00"


def is_dpapi_available() -> bool:
    if sys.platform != "win32":
        return False
    try:
        import win32crypt
        return True
    except ImportError:
        return False


def encrypt_data(data: bytes, description: str = "BuzzSecret") -> bytes:
    """Encrypts bytes using Windows DPAPI bound to the current user."""
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
    # Fallback for non-Windows / mock environments: Base64 encoding with marker
    import base64
    return b"BUZZ_FALLBACK_V1\x00" + base64.b64encode(data)


def decrypt_data(data: bytes) -> bytes:
    """Decrypts bytes previously encrypted with encrypt_data."""
    if data.startswith(DPAPI_MAGIC):
        if not is_dpapi_available():
            raise RuntimeError("DPAPI encrypted data found but win32crypt is not available")
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
    elif data.startswith(b"BUZZ_FALLBACK_V1\x00"):
        import base64
        return base64.b64decode(data[len(b"BUZZ_FALLBACK_V1\x00"):])
    else:
        # Legacy unencrypted payload or raw bytes
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
    Returns None if file does not exist.
    """
    target = Path(path)
    if not target.exists():
        return None

    try:
        raw_bytes = target.read_bytes()
        if not raw_bytes:
            return None

        # Check if encrypted
        if raw_bytes.startswith(DPAPI_MAGIC) or raw_bytes.startswith(b"BUZZ_FALLBACK_V1\x00"):
            decrypted = decrypt_data(raw_bytes)
            return json.loads(decrypted.decode("utf-8"))
        
        # Legacy plaintext migration: attempt to parse as UTF-8 JSON
        try:
            legacy_text = raw_bytes.decode("utf-8")
            data = json.loads(legacy_text)
            # Migrate immediately in-place to DPAPI encryption
            save_secure_json(target, data, description="BuzzMigratedTokenCache")
            return data
        except (UnicodeDecodeError, json.JSONDecodeError):
            return None
    except Exception as e:
        sys.stderr.write(f"[Crypto] Failed to read secure JSON from {path}: {e}\n")
        return None
