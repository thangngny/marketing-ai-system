import argparse
import base64
import hashlib
import json
import os
import secrets
import sys
import urllib.parse
from pathlib import Path

import httpx

from marketing_system.credentials import read_credential, write_credential
from marketing_system.oauth import _value, _pkce

# Set UTF-8 encoding for console
sys.stdout.reconfigure(encoding='utf-8')

PENDING_FILE = Path(r"C:\Users\Admin\marketing-ai-system\data\tiktok_pending_auth.json")
REDIRECT_URI = "https://minhvanlogistics.com/oauth/tiktok/callback"
TIKTOK_SCOPES = "user.info.basic,video.upload,video.publish"

def cmd_start():
    client_key = _value("TIKTOK_CLIENT_KEY")
    client_secret = _value("TIKTOK_CLIENT_SECRET")
    
    verifier, challenge = _pkce()
    state = secrets.token_urlsafe(32)
    
    data = {
        "client_key": client_key,
        "client_secret": client_secret,
        "verifier": verifier,
        "challenge": challenge,
        "state": state,
        "redirect_uri": REDIRECT_URI,
        "scope": TIKTOK_SCOPES
    }
    
    PENDING_FILE.parent.mkdir(parents=True, exist_ok=True)
    PENDING_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")
    
    params = {
        "client_key": client_key,
        "scope": TIKTOK_SCOPES,
        "response_type": "code",
        "redirect_uri": REDIRECT_URI,
        "state": state,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
    }
    auth_url = f"https://www.tiktok.com/v2/auth/authorize/?{urllib.parse.urlencode(params)}"
    print(auth_url)
    return auth_url

def cmd_exchange(code_or_url: str):
    if not PENDING_FILE.exists():
        print("ERROR: No pending TikTok authorization found. Please run start first.", file=sys.stderr)
        return False
        
    data = json.loads(PENDING_FILE.read_text(encoding="utf-8"))
    
    # If a full URL was provided, extract the code
    code = code_or_url.strip()
    if "code=" in code:
        parsed = urllib.parse.urlparse(code)
        query = urllib.parse.parse_qs(parsed.query)
        code = query.get("code", [code])[0]
        # Check error if any
        if "error" in query:
            print(f"TikTok error returned: {query.get('error_description') or query['error']}", file=sys.stderr)
            return False
            
    print(f"Exchanging code: {code[:10]}...")
    
    client_key = data["client_key"]
    client_secret = data["client_secret"]
    redirect_uri = data["redirect_uri"]
    verifier = data["verifier"]
    
    response = httpx.post(
        "https://open.tiktokapis.com/v2/oauth/token/",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        data={
            "client_key": client_key,
            "client_secret": client_secret,
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": redirect_uri,
            "code_verifier": verifier,
        },
        timeout=30.0,
    )
    
    print(f"HTTP Status: {response.status_code}")
    body = response.json()
    print("Response payload:", body)
    
    token_data = body.get("data") or {}
    refresh_token = token_data.get("refresh_token")
    if not refresh_token:
        print("ERROR: No refresh token returned by TikTok:", body, file=sys.stderr)
        return False
        
    write_credential("TIKTOK_REFRESH_TOKEN", str(refresh_token))
    if token_data.get("access_token"):
        write_credential("TIKTOK_ACCESS_TOKEN", str(token_data["access_token"]))
    if token_data.get("open_id"):
        write_credential("TIKTOK_OPEN_ID", str(token_data["open_id"]))
        
    print("SUCCESS: TikTok credentials stored in Windows Credential Manager!")
    return True

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["start", "exchange"])
    parser.add_argument("--code", help="The authorization code or redirected callback URL")
    args = parser.parse_args()
    
    if args.action == "start":
        cmd_start()
    elif args.action == "exchange":
        if not args.code:
            print("ERROR: --code required for exchange", file=sys.stderr)
            sys.exit(1)
        ok = cmd_exchange(args.code)
        sys.exit(0 if ok else 1)
