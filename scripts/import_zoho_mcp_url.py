"""Copy the Zoho hosted-MCP endpoint the owner already registered in Claude Code into the vault.

The URL is treated as a secret: it is read from ~/.claude.json and written to
Windows Credential Manager (BuzzMarketing/ZOHO_MCP_URL) without being printed.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from marketing_system.credentials import credential_present, write_credential


def main() -> int:
    config = json.loads((Path.home() / ".claude.json").read_text(encoding="utf-8"))
    server = (config.get("mcpServers") or {}).get("zoho-crm")
    url = server.get("url") if isinstance(server, dict) else None
    if not url or not url.startswith("https://") or "zoho" not in url:
        print("zoho-crm MCP server not found in Claude Code user config")
        return 2
    write_credential("ZOHO_MCP_URL", url)
    print(f"ZOHO_MCP_URL stored in Windows Credential Manager: {credential_present('ZOHO_MCP_URL')} (value not displayed)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
