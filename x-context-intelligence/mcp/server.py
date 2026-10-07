from __future__ import annotations

import json
from pathlib import Path
import sys
from typing import Any, Dict, List, Optional
from mcp.server.mcpserver import MCPServer

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from src.config import load_config
from src.core.resolver import XContextResolver
from src.models.types import XContextManifest

config = load_config()
resolver = XContextResolver(config)

server = MCPServer(
    "x-context-intelligence",
    title="X Context Intelligence",
    description="Full X post context understanding, browser inspection, media routing, conversation analysis, and safe reproduction planning.",
    version="2.0.0",
)


def _load_manifest_file(job_id: str) -> Optional[Dict[str, Any]]:
    manifest_path = config.data_dir / job_id / "manifest.json"
    if not manifest_path.exists():
        return None
    try:
        with open(manifest_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


@server.tool()
def x_context_ingest(
    url: str,
    max_replies: int = 20,
    max_quotes: int = 5,
    include_author_replies: bool = True,
    force_refresh: bool = False,
) -> Dict[str, Any]:
    """
    Ingest any X/Twitter post URL (text, images, video, thread, article) and reconstruct its full accessible context.
    Evidence-only: Captures metadata, media, author follow-ups, and conversation graph.
    Returns structured summary and disk artifact references (manifest_path, screenshot_path).
    """
    bounded_replies = min(max(1, max_replies), 25)
    bounded_quotes = min(max(1, max_quotes), 10)

    try:
        manifest = resolver.resolve_context(
            url=url,
            max_replies=bounded_replies,
            max_quotes=bounded_quotes,
            include_author_replies=include_author_replies,
            force_refresh=force_refresh,
            enable_video_deep_analysis=True,
        )
    except ValueError as ve:
        return {
            "status": "FAILED",
            "error_category": "DETERMINISTIC",
            "retryable": False,
            "error": str(ve),
        }
    except Exception as e:
        return {
            "status": "FAILED",
            "error_category": "TRANSIENT",
            "retryable": True,
            "error": str(e),
        }

    manifest_file = config.data_dir / manifest.job_id / "manifest.json"
    screenshot_file = config.data_dir / manifest.job_id / "screenshot.png"

    return {
        "status": "SUCCESS",
        "job_id": manifest.job_id,
        "manifest_path": str(manifest_file),
        "screenshot_path": str(screenshot_file) if screenshot_file.exists() else None,
        "root": {
            "id": manifest.root.id,
            "url": manifest.root.url,
            "author": manifest.root.author.model_dump(),
            "text": manifest.root.text[:300] + ("..." if len(manifest.root.text) > 300 else ""),
            "created_at": manifest.root.created_at,
            "likes": manifest.root.likes,
            "retweets": manifest.root.retweets,
            "replies_count": manifest.root.replies_count,
            "media_count": len(manifest.root.media),
        },
        "media_references": [
            {
                "type": m.type.value,
                "url": m.url,
                "video_job_id": m.video_job_id,
                "duration_seconds": m.duration_seconds,
            }
            for m in manifest.root.media
        ],
        "author_followup_count": len(manifest.author_followups),
        "author_followups": [af.model_dump() for af in manifest.author_followups[:5]],
        "top_replies_count": len(manifest.top_replies),
        "top_replies": [r.model_dump() for r in manifest.top_replies[:10]],
        "coverage": manifest.coverage.model_dump(),
        "summary": manifest.summary.model_dump() if hasattr(manifest.summary, "model_dump") else manifest.summary,
        "reproduction_plan_summary": {
            "mode": manifest.reproduction_plan.mode.value if manifest.reproduction_plan else "PLAN_ONLY",
            "steps_count": len(manifest.reproduction_plan.steps) if manifest.reproduction_plan else 0,
        },
    }


@server.tool()
def x_context_manifest(job_id: str) -> Dict[str, Any]:
    """
    Retrieve the context manifest for an ingested job ID, bounded to avoid giant raw payloads.
    Full unclipped raw payload is preserved on disk at manifest_path.
    """
    data = _load_manifest_file(job_id)
    if not data:
        return {"error": "JOB_NOT_FOUND", "job_id": job_id}

    manifest_path = config.data_dir / job_id / "manifest.json"
    top_replies = data.get("top_replies", [])
    is_truncated = len(top_replies) > 25

    return {
        "job_id": job_id,
        "manifest_path": str(manifest_path),
        "root": data.get("root", {}),
        "author_followups": data.get("author_followups", [])[:10],
        "top_replies": top_replies[:25],
        "total_top_replies": len(top_replies),
        "truncated": is_truncated,
        "coverage": data.get("coverage", {}),
        "summary": data.get("summary", {}),
        "reproduction_plan": data.get("reproduction_plan", {}),
    }


@server.tool()
def x_context_root(job_id: str) -> Dict[str, Any]:
    """
    Get root post details (author, full text, timestamp, stats, verified status) for a job.
    """
    data = _load_manifest_file(job_id)
    if not data:
        return {"error": "JOB_NOT_FOUND", "job_id": job_id}
    return {
        "job_id": job_id,
        "root": data.get("root", {}),
        "fetched_at": data.get("fetched_at"),
    }


@server.tool()
def x_context_media(job_id: str) -> Dict[str, Any]:
    """
    List all media attachments (videos, images, transcripts, frame summaries) associated with the post.
    Returns metadata and disk references (never raw base64 image data).
    """
    data = _load_manifest_file(job_id)
    if not data:
        return {"error": "JOB_NOT_FOUND", "job_id": job_id}
    media_items = data.get("root", {}).get("media", [])
    return {
        "job_id": job_id,
        "media_count": len(media_items),
        "media": media_items,
    }


@server.tool()
def x_context_conversation(
    job_id: str,
    filter_author_only: bool = False,
    min_rank: int = 0,
    limit: int = 20,
) -> Dict[str, Any]:
    """
    Retrieve conversation replies, bounded by limit to prevent huge payloads.
    """
    data = _load_manifest_file(job_id)
    if not data:
        return {"error": "JOB_NOT_FOUND", "job_id": job_id}

    author_followups = data.get("author_followups", [])
    top_replies = data.get("top_replies", [])

    if filter_author_only:
        filtered_top = []
    else:
        filtered_top = [r for r in top_replies if r.get("rank", 0) >= min_rank]

    bounded_limit = min(max(1, limit), 25)
    return {
        "job_id": job_id,
        "author_followup_count": len(author_followups),
        "author_followups": author_followups[:bounded_limit],
        "reply_count": len(filtered_top),
        "top_replies": filtered_top[:bounded_limit],
        "limit_applied": bounded_limit,
    }


@server.tool()
def x_context_quotes(job_id: str) -> Dict[str, Any]:
    """
    Retrieve quote posts and community perspectives on this X post.
    """
    data = _load_manifest_file(job_id)
    if not data:
        return {"error": "JOB_NOT_FOUND", "job_id": job_id}
    quotes = data.get("quotes", [])
    return {
        "job_id": job_id,
        "quote_count": len(quotes),
        "quotes": quotes[:20],
    }


@server.tool()
def x_context_links(job_id: str) -> Dict[str, Any]:
    """
    Retrieve external links found in the post or thread, including resolved destinations and GitHub repo metadata.
    """
    data = _load_manifest_file(job_id)
    if not data:
        return {"error": "JOB_NOT_FOUND", "job_id": job_id}
    links = data.get("root", {}).get("links", [])
    return {
        "job_id": job_id,
        "link_count": len(links),
        "links": links[:25],
    }


@server.tool()
def x_context_graph(job_id: str) -> Dict[str, Any]:
    """
    Get the provenance context graph (nodes: ROOT, AUTHOR, MEDIA, REPLY, QUOTE, LINK; edges: AUTHORED, REPLIED_TO, CONTAINS_MEDIA).
    """
    data = _load_manifest_file(job_id)
    if not data:
        return {"error": "JOB_NOT_FOUND", "job_id": job_id}
    return {
        "job_id": job_id,
        "graph": data.get("graph", {}),
    }


@server.tool()
def x_context_summary(job_id: str) -> Dict[str, Any]:
    """
    Get a high-level summary of the context, truth classifications, coverage status, and core objective.
    """
    data = _load_manifest_file(job_id)
    if not data:
        return {"error": "JOB_NOT_FOUND", "job_id": job_id}
    return {
        "job_id": job_id,
        "summary": data.get("summary", {}),
        "coverage": data.get("coverage", {}),
    }


@server.tool()
def x_context_reproduce_plan(job_id: str) -> Dict[str, Any]:
    """
    Get the structured reproduction plan (PLAN_ONLY) with local Windows/PowerShell gap analysis and step-by-step verification.
    Evidence and planning only: NEVER executes commands.
    """
    data = _load_manifest_file(job_id)
    if not data:
        return {"error": "JOB_NOT_FOUND", "job_id": job_id}
    return {
        "job_id": job_id,
        "reproduction_plan": data.get("reproduction_plan", {}),
    }


def main():
    server.run(transport="stdio")


if __name__ == "__main__":
    main()
