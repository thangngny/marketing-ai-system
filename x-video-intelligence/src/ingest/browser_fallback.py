from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional, Tuple


def extract_via_browser_fallback(url: str, output_dir: Path) -> Tuple[bool, Optional[Dict[str, Any]], str]:
    """Browser fallback worker for protected or obfuscated posts.

    Strict guardrails:
    - Capture media only for analysis
    - Never like, repost, follow, DM, or change settings
    - If no authorized session is available, return MANUAL_FILE_REQUIRED gracefully.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    # Check if a custom browser script or session is present in environment
    # In headless/unauthenticated environments without direct cookies:
    return False, None, "MANUAL_FILE_REQUIRED: Browser fallback could not authenticate or locate playable media."
