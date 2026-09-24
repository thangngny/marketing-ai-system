from __future__ import annotations

import base64
import hashlib
import os
import secrets
import time
import urllib.parse
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

import httpx

from .credentials import read_credential, write_credential


M365_SCOPES = "openid profile offline_access User.Read Mail.Read Calendars.Read Files.Read"
ZOHO_SCOPES = ",".join(
    [
        "ZohoCRM.org.READ",
        "ZohoCRM.settings.modules.READ",
        "ZohoCRM.modules.leads.READ",
        "ZohoCRM.modules.contacts.READ",
        "ZohoCRM.modules.accounts.READ",
        "ZohoCRM.modules.deals.READ",
        "ZohoCRM.modules.tasks.READ",
    ]
)


def _value(name: str) -> str:
    value = os.getenv(name) or read_credential(name)
    if not value:
        raise RuntimeError(f"Missing local configuration: {name}")
    return value


def _pkce() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(64)
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return verifier, challenge


class _CallbackHandler(BaseHTTPRequestHandler):
    server: "_CallbackServer"

    def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        query = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        self.server.callback = {key: values[0] for key, values in query.items() if values}
        ok = "code" in self.server.callback and "error" not in self.server.callback
        self.send_response(200 if ok else 400)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        message = "Authorization captured. You may close this tab." if ok else "Authorization was not completed."
        page = (
            "<html><body><h1>"
            + message
            + "</h1><script>history.replaceState({}, '', '/complete');</script></body></html>"
        )
        self.wfile.write(page.encode("utf-8"))

    def log_message(self, _format: str, *_args: object) -> None:
        return


class _CallbackServer(ThreadingHTTPServer):
    callback: dict[str, str] | None = None


def _capture_callback(auth_url: str, *, port: int = 0, timeout: int = 300) -> tuple[dict[str, str], str]:
    server = _CallbackServer(("127.0.0.1", port), _CallbackHandler)
    server.timeout = timeout
    actual_port = server.server_address[1]
    redirect_uri = f"http://localhost:{actual_port}"
    url = auth_url.replace("REDIRECT_URI_PLACEHOLDER", urllib.parse.quote(redirect_uri, safe=""))
    webbrowser.open(url, new=2)
    # Browsers send stray requests (favicon, prefetch) first; wait for the one carrying code/error.
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        server.timeout = max(1, deadline - time.monotonic())
        server.handle_request()
        if server.callback and ("code" in server.callback or "error" in server.callback):
            break
        server.callback = None
    server.server_close()
    if not server.callback:
        raise TimeoutError("OAuth callback was not received")
    return server.callback, redirect_uri


def authorize_m365() -> dict[str, str]:
    client_id = _value("MS_CLIENT_ID")
    tenant = _value("MS_TENANT_ID")
    verifier, challenge = _pkce()
    state = secrets.token_urlsafe(32)
    params = {
        "client_id": client_id,
        "response_type": "code",
        "redirect_uri": "REDIRECT_URI_PLACEHOLDER",
        "response_mode": "query",
        "scope": M365_SCOPES,
        "state": state,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
    }
    auth_url = f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0/authorize?{urllib.parse.urlencode(params)}"
    callback, redirect_uri = _capture_callback(auth_url)
    if callback.get("state") != state:
        raise RuntimeError("OAuth state validation failed")
    if callback.get("error"):
        raise RuntimeError(f"Microsoft authorization failed: {callback['error']}")
    token = httpx.post(
        f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token",
        data={
            "client_id": client_id,
            "scope": M365_SCOPES,
            "code": callback["code"],
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
            "code_verifier": verifier,
        },
        timeout=30.0,
    )
    token.raise_for_status()
    body = token.json()
    if not body.get("refresh_token"):
        raise RuntimeError("Microsoft returned no refresh token")
    write_credential("MS_REFRESH_TOKEN", str(body["refresh_token"]))
    return {"provider": "m365", "state": "CREDENTIAL_STORED", "scope": M365_SCOPES}


def authorize_zoho() -> dict[str, str]:
    client_id = _value("ZOHO_CLIENT_ID")
    client_secret = _value("ZOHO_CLIENT_SECRET")
    accounts = os.getenv("ZOHO_ACCOUNTS_URL") or read_credential("ZOHO_ACCOUNTS_URL") or "https://accounts.zoho.com"
    verifier, challenge = _pkce()
    state = secrets.token_urlsafe(32)
    fixed_port = 53682
    params = {
        "scope": ZOHO_SCOPES,
        "client_id": client_id,
        "response_type": "code",
        "access_type": "offline",
        "prompt": "consent",
        "redirect_uri": "REDIRECT_URI_PLACEHOLDER",
        "state": state,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
    }
    auth_url = f"{accounts.rstrip('/')}/oauth/v2/auth?{urllib.parse.urlencode(params)}"
    callback, redirect_uri = _capture_callback(auth_url, port=fixed_port)
    if callback.get("state") != state:
        raise RuntimeError("OAuth state validation failed")
    if callback.get("error"):
        raise RuntimeError(f"Zoho authorization failed: {callback['error']}")
    token = httpx.post(
        f"{accounts.rstrip('/')}/oauth/v2/token",
        data={
            "grant_type": "authorization_code",
            "client_id": client_id,
            "client_secret": client_secret,
            "redirect_uri": redirect_uri,
            "code": callback["code"],
            "code_verifier": verifier,
        },
        timeout=30.0,
    )
    token.raise_for_status()
    body: dict[str, Any] = token.json()
    if not body.get("refresh_token"):
        raise RuntimeError("Zoho returned no refresh token")
    write_credential("ZOHO_REFRESH_TOKEN", str(body["refresh_token"]))
    if body.get("api_domain"):
        write_credential("ZOHO_API_DOMAIN", str(body["api_domain"]))
    return {"provider": "zoho", "state": "CREDENTIAL_STORED", "scope": ZOHO_SCOPES}
