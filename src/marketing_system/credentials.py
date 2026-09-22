from __future__ import annotations

import ctypes
import getpass
import sys
from ctypes import wintypes


SERVICE_NAME = "BuzzMarketing"
TARGET_PREFIX = f"{SERVICE_NAME}/"


class CredentialStoreError(RuntimeError):
    """Raised when the operating-system credential store cannot complete an operation."""


if sys.platform == "win32":
    CRED_TYPE_GENERIC = 1
    CRED_PERSIST_LOCAL_MACHINE = 2
    ERROR_NOT_FOUND = 1168

    class _CREDENTIALW(ctypes.Structure):
        _fields_ = [
            ("Flags", wintypes.DWORD),
            ("Type", wintypes.DWORD),
            ("TargetName", wintypes.LPWSTR),
            ("Comment", wintypes.LPWSTR),
            ("LastWritten", wintypes.FILETIME),
            ("CredentialBlobSize", wintypes.DWORD),
            ("CredentialBlob", ctypes.POINTER(ctypes.c_ubyte)),
            ("Persist", wintypes.DWORD),
            ("AttributeCount", wintypes.DWORD),
            ("Attributes", ctypes.c_void_p),
            ("TargetAlias", wintypes.LPWSTR),
            ("UserName", wintypes.LPWSTR),
        ]

    _advapi32 = ctypes.WinDLL("Advapi32.dll", use_last_error=True)
    _advapi32.CredReadW.argtypes = [
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
        ctypes.POINTER(ctypes.POINTER(_CREDENTIALW)),
    ]
    _advapi32.CredReadW.restype = wintypes.BOOL
    _advapi32.CredWriteW.argtypes = [ctypes.POINTER(_CREDENTIALW), wintypes.DWORD]
    _advapi32.CredWriteW.restype = wintypes.BOOL
    _advapi32.CredDeleteW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD]
    _advapi32.CredDeleteW.restype = wintypes.BOOL
    _advapi32.CredFree.argtypes = [ctypes.c_void_p]
    _advapi32.CredFree.restype = None


def _target(name: str) -> str:
    normalized = name.strip().upper()
    if not normalized or not all(char.isalnum() or char == "_" for char in normalized):
        raise ValueError("Credential names may contain only letters, digits, and underscores")
    return f"{TARGET_PREFIX}{normalized}"


def available() -> bool:
    return sys.platform == "win32"


def read_credential(name: str) -> str | None:
    """Read a secret without logging or copying it into application storage."""
    if not available():
        return None
    credential = ctypes.POINTER(_CREDENTIALW)()
    if not _advapi32.CredReadW(_target(name), CRED_TYPE_GENERIC, 0, ctypes.byref(credential)):
        error = ctypes.get_last_error()
        if error == ERROR_NOT_FOUND:
            return None
        raise CredentialStoreError(f"Windows Credential Manager read failed ({error})")
    try:
        size = credential.contents.CredentialBlobSize
        if not size:
            return ""
        raw = ctypes.string_at(credential.contents.CredentialBlob, size)
        return raw.decode("utf-16-le")
    finally:
        _advapi32.CredFree(credential)


def write_credential(name: str, value: str) -> None:
    """Write a secret to the current user's Windows Credential Manager vault."""
    if not available():
        raise CredentialStoreError("The OS credential store is not available")
    if not value:
        raise ValueError("Credential value cannot be empty")
    encoded = value.encode("utf-16-le")
    blob = (ctypes.c_ubyte * len(encoded)).from_buffer_copy(encoded)
    credential = _CREDENTIALW()
    credential.Type = CRED_TYPE_GENERIC
    credential.TargetName = _target(name)
    credential.Comment = "Buzz Marketing integration credential"
    credential.CredentialBlobSize = len(encoded)
    credential.CredentialBlob = ctypes.cast(blob, ctypes.POINTER(ctypes.c_ubyte))
    credential.Persist = CRED_PERSIST_LOCAL_MACHINE
    credential.UserName = getpass.getuser()
    if not _advapi32.CredWriteW(ctypes.byref(credential), 0):
        error = ctypes.get_last_error()
        raise CredentialStoreError(f"Windows Credential Manager write failed ({error})")


def delete_credential(name: str) -> bool:
    if not available():
        return False
    if _advapi32.CredDeleteW(_target(name), CRED_TYPE_GENERIC, 0):
        return True
    error = ctypes.get_last_error()
    if error == ERROR_NOT_FOUND:
        return False
    raise CredentialStoreError(f"Windows Credential Manager delete failed ({error})")


def credential_present(name: str) -> bool:
    return bool(read_credential(name))
