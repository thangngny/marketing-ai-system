"""Zoho CRM through Zoho's official hosted MCP server (mcp.zoho.com).

Why: the REST path needs an OAuth client from Zoho API Console, which is
blocked on owner MFA. Zoho's hosted MCP server fronts the same official CRM
API with its own OAuth (dynamic client registration). This module is only a
transport; ZohoConnector keeps normalization and the canonical model.

Secrets: endpoint URL, OAuth client info and tokens live in Windows Credential
Manager (BuzzMarketing/ZOHO_MCP_URL, ZOHO_MCP_CLIENT, ZOHO_MCP_TOKENS).
"""

from __future__ import annotations

import asyncio
import json
import threading
import urllib.parse
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any

from mcp import ClientSession
from mcp.client.auth import OAuthClientProvider
from mcp.client.streamable_http import create_mcp_http_client, streamable_http_client
from mcp.shared.auth import AuthorizationCodeResult, OAuthClientInformationFull, OAuthClientMetadata, OAuthToken

from ..credentials import read_credential, write_credential

CALLBACK_PORT = 53683
REDIRECT_URI = f"http://localhost:{CALLBACK_PORT}/callback"


class ZohoMcpAuthRequired(RuntimeError):
    """No usable OAuth token; an interactive `marketing-system oauth zoho-mcp` is needed."""


_CHUNK = 1000  # Credential Manager blobs cap at 2560 bytes (UTF-16) — split larger JSON.


def _put(name: str, value: str) -> None:
    chunks = [value[i:i + _CHUNK] for i in range(0, len(value), _CHUNK)] or [""]
    for index, chunk in enumerate(chunks):
        write_credential(f"{name}_{index}", chunk)
    write_credential(name, f"chunks:{len(chunks)}")


def _get(name: str) -> str | None:
    head = read_credential(name)
    if not head or not head.startswith("chunks:"):
        return head
    return "".join(read_credential(f"{name}_{i}") or "" for i in range(int(head.split(":", 1)[1])))


class VaultTokenStorage:
    async def get_tokens(self) -> OAuthToken | None:
        raw = _get("ZOHO_MCP_TOKENS")
        return OAuthToken.model_validate_json(raw) if raw else None

    async def set_tokens(self, tokens: OAuthToken) -> None:
        _put("ZOHO_MCP_TOKENS", tokens.model_dump_json())

    async def get_client_info(self) -> OAuthClientInformationFull | None:
        raw = _get("ZOHO_MCP_CLIENT")
        return OAuthClientInformationFull.model_validate_json(raw) if raw else None

    async def set_client_info(self, client_info: OAuthClientInformationFull) -> None:
        _put("ZOHO_MCP_CLIENT", client_info.model_dump_json())


def endpoint() -> str | None:
    return read_credential("ZOHO_MCP_URL")


def has_tokens() -> bool:
    return bool(read_credential("ZOHO_MCP_TOKENS"))


def _metadata() -> OAuthClientMetadata:
    return OAuthClientMetadata(client_name="Buzz Marketing Platform (read-only)", redirect_uris=[REDIRECT_URI],
                               grant_types=["authorization_code", "refresh_token"], response_types=["code"],
                               token_endpoint_auth_method="none")


async def _refuse_redirect(_url: str) -> None:
    raise ZohoMcpAuthRequired("Zoho MCP authorization required; run: marketing-system oauth zoho-mcp")


async def _refuse_callback() -> AuthorizationCodeResult:
    raise ZohoMcpAuthRequired("Zoho MCP authorization required; run: marketing-system oauth zoho-mcp")


async def _call(url: str, tool: str, arguments: dict[str, Any], interactive: bool) -> Any:
    if interactive:
        redirect, callback = _browser_redirect, _local_callback
    else:
        redirect, callback = _refuse_redirect, _refuse_callback
    provider = OAuthClientProvider(url, _metadata(), VaultTokenStorage(), redirect_handler=redirect, callback_handler=callback)
    async with create_mcp_http_client(auth=provider) as http:
        async with streamable_http_client(url, http_client=http) as streams:
            read, write = streams[0], streams[1]
            # Interactive consent happens inside the first request, so give the human up to 10 minutes.
            async with ClientSession(read, write, read_timeout_seconds=600 if interactive else 60) as session:
                await session.initialize()
                result = await session.call_tool(tool, arguments)
    if result.is_error:
        text = " ".join(getattr(c, "text", "") for c in result.content)
        raise RuntimeError(f"Zoho MCP tool error: {text[:300]}")
    if result.structured_content is not None:
        return result.structured_content
    text = "".join(getattr(c, "text", "") for c in result.content)
    try:
        return json.loads(text)
    except ValueError:
        return {"text": text}


def call_tool(tool: str, arguments: dict[str, Any], interactive: bool = False) -> Any:
    url = endpoint()
    if not url:
        raise ZohoMcpAuthRequired("ZOHO_MCP_URL missing from the credential store")
    try:
        return asyncio.run(_call(url, tool, arguments, interactive))
    except BaseExceptionGroup as group:  # anyio task groups wrap the real error
        auth = [e for e in _flatten(group) if isinstance(e, ZohoMcpAuthRequired)]
        if auth:
            raise auth[0] from None
        raise _flatten(group)[0] from None


def _flatten(group: BaseException) -> list[BaseException]:
    if isinstance(group, BaseExceptionGroup):
        return [leaf for e in group.exceptions for leaf in _flatten(e)]
    return [group]


# ----------------------------------------------------------------------- interactive consent
_captured: dict[str, str] = {}
_done = threading.Event()


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802
        query = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        _captured.update({k: v[0] for k, v in query.items() if v})
        ok = "code" in _captured
        self.send_response(200 if ok else 400)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(("Đã nhận uỷ quyền Zoho. Có thể đóng tab này." if ok else "Uỷ quyền chưa hoàn tất.").encode("utf-8"))
        _done.set()

    def log_message(self, *_: object) -> None:
        return


async def _browser_redirect(url: str) -> None:
    _captured.clear()
    _done.clear()
    server = HTTPServer(("127.0.0.1", CALLBACK_PORT), _Handler)
    threading.Thread(target=server.handle_request, daemon=True).start()
    webbrowser.open(url, new=2)


async def _local_callback() -> AuthorizationCodeResult:
    await asyncio.get_running_loop().run_in_executor(None, _done.wait, 600)
    if "code" not in _captured:
        raise ZohoMcpAuthRequired(f"Authorization not completed: {_captured.get('error', 'timeout')}")
    return AuthorizationCodeResult(code=_captured["code"], state=_captured.get("state"))


def authorize() -> dict[str, str]:
    """One-time interactive consent (opens the browser). Verifies with a harmless count call."""
    data = call_tool("ZohoCRM_getRecordCount", {"path_variables": {"moduleApiName": "Leads"}}, interactive=True)
    return {"provider": "zoho-mcp", "state": "CREDENTIAL_STORED", "probe": json.dumps(data)[:120]}
