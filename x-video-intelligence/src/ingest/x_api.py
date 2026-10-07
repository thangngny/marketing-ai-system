from __future__ import annotations

import os
from typing import Any, Dict, Optional


def fetch_via_x_api(url: str) -> Optional[Dict[str, Any]]:
    """Attempt extraction via official Twitter/X API v2 if credentials are provided in env."""
    bearer_token = os.environ.get("TWITTER_BEARER_TOKEN") or os.environ.get("X_BEARER_TOKEN")
    if not bearer_token:
        return None  # Pass to next layer without error

    # If bearer token exists, query X API v2 tweet endpoint with media expansion
    try:
        import httpx
        tweet_id = url.rstrip("/").split("/")[-1].split("?")[0]
        headers = {"Authorization": f"Bearer {bearer_token}"}
        endpoint = f"https://api.twitter.com/2/tweets/{tweet_id}?expansions=attachments.media_keys&media.fields=duration_ms,variants,preview_image_url&tweet.fields=created_at,text,author_id"
        resp = httpx.get(endpoint, headers=headers, timeout=10.0)
        if resp.status_code == 200:
            data = resp.json()
            return {
                "resolver": "X_API",
                "tweet_data": data,
                "post_text": data.get("data", {}).get("text", ""),
                "created_at": data.get("data", {}).get("created_at", "")
            }
    except Exception:
        pass
    return None
