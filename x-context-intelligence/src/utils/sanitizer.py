from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse, urlunparse


def parse_x_url(url: str) -> Tuple[Optional[str], Optional[str]]:
    """
    Extract (author_handle, status_id) from an X/Twitter URL.
    Handles x.com, twitter.com, vxtwitter.com, fxtwitter.com, fixupx.com.
    """
    clean_url = url.strip()
    match = re.search(r"(?:twitter\.com|x\.com|vxtwitter\.com|fxtwitter\.com|fixupx\.com)/([A-Za-z0-9_]+)/status/(\d+)", clean_url)
    if match:
        return match.group(1), match.group(2)
    # Just status ID
    id_match = re.search(r"/status/(\d+)", clean_url)
    if id_match:
        return None, id_match.group(1)
    return None, None


def clean_x_url(url: str) -> str:
    """Normalize X URL to canonical https://x.com/<author>/status/<id> without query params."""
    handle, status_id = parse_x_url(url)
    if handle and status_id:
        return f"https://x.com/{handle}/status/{status_id}"
    elif status_id:
        return f"https://x.com/i/status/{status_id}"
    return url.split("?")[0]


def extract_urls_from_text(text: str) -> List[str]:
    """Find all http/https URLs inside arbitrary text."""
    url_pattern = r"https?://[^\s<>\"')]+"
    urls = re.findall(url_pattern, text)
    return list(dict.fromkeys(urls))


def extract_github_repos(text: str) -> List[str]:
    """Find github repository URLs or owner/repo references."""
    pattern = r"https?://github\.com/([a-zA-Z0-9_\-\.]+)/([a-zA-Z0-9_\-\.]+)"
    matches = re.findall(pattern, text)
    repos = []
    for owner, repo in matches:
        repo_clean = repo.rstrip(".,;:)")
        repos.append(f"https://github.com/{owner}/{repo_clean}")
    return list(dict.fromkeys(repos))


def translate_shell_to_powershell(command: str) -> str:
    """Translate common Unix shell commands to Windows PowerShell equivalents."""
    cmd = command.strip()

    # export VAR=VAL -> $env:VAR = "VAL"
    def _quote_env(m):
        var = m.group(1)
        val = m.group(2).strip("\"'")
        return f'$env:{var} = "{val}"'

    cmd = re.sub(r"^export\s+([A-Za-z0-9_]+)=([^\n;]+)", _quote_env, cmd)

    # source .venv/bin/activate -> .\.venv\Scripts\Activate.ps1
    cmd = re.sub(r"(?:source|\.)\s+\.venv/bin/activate", lambda m: r".\.venv\Scripts\Activate.ps1", cmd)
    cmd = re.sub(r"(?:source|\.)\s+venv/bin/activate", lambda m: r".\venv\Scripts\Activate.ps1", cmd)
    # python3 -> python
    cmd = re.sub(r"\bpython3\b", "python", cmd)
    # touch file -> New-Item -ItemType File -Force file
    cmd = re.sub(r"^touch\s+([^\n;]+)", r"New-Item -ItemType File -Force \1", cmd)
    # mkdir -p -> New-Item -ItemType Directory -Force
    cmd = re.sub(r"^mkdir\s+-p\s+([^\n;]+)", r"New-Item -ItemType Directory -Force \1", cmd)
    # rm -rf -> Remove-Item -Recurse -Force
    cmd = re.sub(r"^rm\s+-rf\s+([^\n;]+)", r"Remove-Item -Recurse -Force \1", cmd)
    # cat -> Get-Content
    cmd = re.sub(r"^cat\s+([^\n;]+)", r"Get-Content \1", cmd)
    return cmd


def assess_command_risk(command: str) -> Tuple[str, bool]:
    """Assess command risk level (LOW, MEDIUM, HIGH) and whether approval is required."""
    cmd_lower = command.lower()
    dangerous_patterns = [
        r"\|\s*(?:bash|sh|powershell|cmd)",
        r"rm\s+-rf",
        r"remove-item\s+.*-recurse",
        r"format\s+[a-z]:",
        r"del\s+/f\s+/s\s+/q",
        r"api[-_]?key",
        r"token",
        r"password",
        r"chmod\s+777",
        r"curl.*\|.*iex",
        r"irm.*\|.*iex",
    ]
    for p in dangerous_patterns:
        if re.search(p, cmd_lower):
            return "HIGH", True

    medium_patterns = [
        r"pip\s+install",
        r"npm\s+install",
        r"winget\s+install",
        r"git\s+clone",
        r"docker\s+run",
        r"docker-compose\s+up",
    ]
    for p in medium_patterns:
        if re.search(p, cmd_lower):
            return "MEDIUM", False

    return "LOW", False
