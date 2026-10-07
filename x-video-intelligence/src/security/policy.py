from __future__ import annotations

import re
from typing import Tuple, List
from ..models import RiskLevel, TruthClassification


# Patterns that are inherently high risk or destructive
DANGEROUS_PATTERNS = [
    (r"curl\s+.*\|\s*(bash|sh|zsh|pwsh|powershell)", "Untrusted script piped directly to shell", RiskLevel.DESTRUCTIVE),
    (r"wget\s+.*\|\s*(bash|sh|zsh|pwsh|powershell)", "Untrusted script piped directly to shell", RiskLevel.DESTRUCTIVE),
    (r"rm\s+-rf\s+[/~]", "Recursive deletion of root or home directory", RiskLevel.DESTRUCTIVE),
    (r"del\s+/[fF]\s+/[sS]\s+/[qQ]\s+[cC]:\\", "System-wide deletion on Windows drive", RiskLevel.DESTRUCTIVE),
    (r"format\s+[a-zA-Z]:", "Disk formatting command", RiskLevel.DESTRUCTIVE),
    (r"chmod\s+-R\s+777", "Insecure wide-open filesystem permissions", RiskLevel.HIGH),
    (r"Set-MpPreference.*-DisableRealtimeMonitoring", "Disabling Windows Defender / Antivirus", RiskLevel.DESTRUCTIVE),
    (r"net\s+user\s+.*\/add", "Unauthorized local user creation", RiskLevel.HIGH),
    (r"drop\s+database", "Destructive database operation", RiskLevel.DESTRUCTIVE),
    (r"truncate\s+table", "Destructive database operation", RiskLevel.HIGH),
    (r"mkfs", "Filesystem destruction command", RiskLevel.DESTRUCTIVE),
    (r"dd\s+if=.*of=/dev", "Direct block device write", RiskLevel.DESTRUCTIVE),
]

# Patterns for secrets
SECRET_PATTERNS = [
    (r"nsec1[02-9ac-hj-np-z]{58}", "[REDACTED_NOSTR_NSEC]"),
    (r"sk-[a-zA-Z0-9]{32,64}", "[REDACTED_OPENAI_KEY]"),
    (r"ghp_[a-zA-Z0-9]{36}", "[REDACTED_GITHUB_TOKEN]"),
    (r"glpat-[a-zA-Z0-9\-_]{20,}", "[REDACTED_GITLAB_TOKEN]"),
    (r"AIza[0-9A-Za-z\-_]{35}", "[REDACTED_GOOGLE_API_KEY]"),
    (r"xox[baprs]-[0-9a-zA-Z]{10,48}", "[REDACTED_SLACK_TOKEN]"),
    (r"-----BEGIN (?:RSA |EC )?PRIVATE KEY-----[\s\S]+?-----END (?:RSA |EC )?PRIVATE KEY-----", "[REDACTED_PRIVATE_KEY]"),
    (r"(?:api[_-]?key|secret|password|auth[_-]?token)\s*[:=]\s*['\"]([^'\"]{8,})['\"]", "[REDACTED_CREDENTIAL]"),
]


def assess_command_risk(command: str) -> Tuple[RiskLevel, bool, List[str]]:
    """Assess command safety, returning (RiskLevel, requires_approval, reasons)."""
    reasons: List[str] = []
    highest_risk = RiskLevel.LOW
    requires_approval = False

    cmd_lower = command.lower().strip()

    for pattern, reason, risk in DANGEROUS_PATTERNS:
        if re.search(pattern, command, re.IGNORECASE):
            reasons.append(f"{reason} (matched: {pattern})")
            if risk == RiskLevel.DESTRUCTIVE:
                highest_risk = RiskLevel.DESTRUCTIVE
                requires_approval = True
            elif risk == RiskLevel.HIGH and highest_risk != RiskLevel.DESTRUCTIVE:
                highest_risk = RiskLevel.HIGH
                requires_approval = True

    # Check for general mutation commands
    if any(k in cmd_lower for k in ["pip install", "npm install", "git clone", "winget install", "choco install"]):
        if highest_risk == RiskLevel.LOW:
            highest_risk = RiskLevel.MEDIUM

    # Check for sensitive keywords
    if any(k in cmd_lower for k in ["password", "token", "secret", "credentials", "auth"]):
        requires_approval = True
        if highest_risk == RiskLevel.LOW:
            highest_risk = RiskLevel.MEDIUM
        reasons.append("Command touches sensitive credentials or authentication parameters.")

    return highest_risk, requires_approval, reasons


def redact_secrets(text: str) -> str:
    """Scrub sensitive keys and tokens from logs, transcripts, and evidence artifacts."""
    redacted = text
    for pattern, replacement in SECRET_PATTERNS:
        redacted = re.sub(pattern, replacement, redacted)
    return redacted
