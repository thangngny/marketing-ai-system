"""Zoho CRM via the owner's existing Claude Code authorization (no extra OAuth).

A second OAuth client on the hosted Zoho MCP server appears to invalidate the
first one (observed 2026-09-24), so the hub reuses the authorization the owner
already granted to Claude Code. Claude only acts as a pipe:

- it is restricted to the single requested Zoho tool;
- the returned data is taken from the raw tool_result in the stream, never from
  the model's prose;
- the tool input the model actually sent must equal the requested arguments,
  otherwise the result is rejected.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

SERVER = "zoho-crm"


class ZohoDelegateError(RuntimeError):
    pass


class ZohoSessionExpired(ZohoDelegateError):
    """The hosted Zoho MCP session held by Claude Code expired (observed ~1 h lifetime)."""


def available() -> bool:
    if not shutil.which("claude.cmd") and not shutil.which("claude"):
        return False
    try:
        config = json.loads((Path.home() / ".claude.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    return SERVER in (config.get("mcpServers") or {})


def call_tool(tool: str, arguments: dict[str, Any], timeout: int = 180, attempts: int = 2) -> Any:
    last: Exception | None = None
    for _ in range(attempts):  # the Zoho MCP server may still be connecting on a cold start
        try:
            return _call_once(tool, arguments, timeout)
        except ZohoDelegateError as exc:
            if isinstance(exc, ZohoSessionExpired) or "altered" in str(exc) or "Zoho tool error" in str(exc):
                raise
            last = exc
    raise last  # type: ignore[misc]


def _call_once(tool: str, arguments: dict[str, Any], timeout: int) -> Any:
    exe = shutil.which("claude.cmd") or shutil.which("claude")
    if not exe:
        raise ZohoDelegateError("claude CLI not installed")
    full = f"mcp__{SERVER}__{tool}"
    prompt = (f"Call the tool {full} exactly once with these arguments and nothing else:\n"
              f"{json.dumps(arguments, ensure_ascii=False)}\nIf the tool is not loaded yet, search for it by its exact name first (retry if the server is still connecting). "
              "Then reply only: DONE")
    done = subprocess.run(
        # Prompt via stdin: claude.cmd goes through cmd.exe, which mangles newlines and quotes in argv.
        [exe, "-p", "--output-format", "stream-json", "--verbose", "--allowedTools", full],
        input=prompt.encode("utf-8"), capture_output=True, timeout=timeout, check=False,
        cwd=os.environ.get("TEMP") or None,
    )
    if done.returncode != 0:
        raise ZohoDelegateError(f"claude exit {done.returncode}")
    stream = done.stdout.decode("utf-8", errors="replace")
    if "mcp__zoho-crm__authenticate" in stream or "Needs authentication" in stream:
        raise ZohoSessionExpired("Zoho session in Claude Code needs re-authentication (/mcp → zoho-crm)")
    try:
        return extract(stream, full, arguments)
    except ZohoDelegateError as exc:
        if "no Zoho tool_result" in str(exc) and session_needs_auth(exe):
            raise ZohoSessionExpired("Zoho session in Claude Code needs re-authentication (/mcp → zoho-crm)") from None
        raise


def session_needs_auth(exe: str) -> bool:
    try:
        out = subprocess.run([exe, "mcp", "list"], capture_output=True, timeout=90, stdin=subprocess.DEVNULL, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return False
    return any(SERVER in line and "Needs authentication" in line
               for line in out.stdout.decode("utf-8", errors="replace").splitlines())


def extract(stream: str, full_tool: str, arguments: dict[str, Any]) -> Any:
    calls: dict[str, dict[str, Any]] = {}
    for line in stream.splitlines():
        try:
            event = json.loads(line)
        except ValueError:
            continue
        message = event.get("message") or {}
        for block in message.get("content") or []:
            if not isinstance(block, dict):
                continue
            if block.get("type") == "tool_use" and block.get("name") == full_tool:
                calls[block["id"]] = block.get("input") or {}
            elif block.get("type") == "tool_result" and block.get("tool_use_id") in calls:
                if _canonical(calls[block["tool_use_id"]]) != _canonical(arguments):
                    raise ZohoDelegateError("model altered the tool arguments; result rejected")
                if block.get("is_error"):
                    raise ZohoDelegateError(f"Zoho tool error: {str(block.get('content'))[:300]}")
                structured = (event.get("tool_use_result") or {}).get("structuredContent")
                if structured is not None:
                    return structured
                content = block.get("content")
                text = content if isinstance(content, str) else "".join(
                    c.get("text", "") for c in content or [] if isinstance(c, dict))
                return json.loads(text)
    raise ZohoDelegateError("no Zoho tool_result in the stream")


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False)
