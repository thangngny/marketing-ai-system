from __future__ import annotations

import datetime
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional
import requests

from src.config import XContextConfig, load_config
from src.core.browser_worker import BrowserWorker
from src.core.context_graph import ContextGraphBuilder
from src.core.conversation import process_replies
from src.core.coverage import CoverageReporter
from src.core.media_router import MediaRouter
from src.core.reproduction import ReproductionPlanner
from src.models.types import (
    AuthorInfo,
    ContextGraph,
    CoverageReport,
    ExternalLink,
    MediaItem,
    MediaType,
    QuoteNode,
    ReplyCategory,
    ReplyNode,
    ReproductionPlan,
    RootPost,
    TruthClassification,
    XContextManifest,
)
from src.utils.sanitizer import clean_x_url, extract_urls_from_text, parse_x_url

logger = logging.getLogger("x_context.resolver")


class XContextResolver:
    """
    Main resolution engine for X Context Intelligence V2.
    Integrates structured endpoints, browser worker fallback, media delegation to
    x-video-intelligence, conversation processing, and graph generation.
    """

    def __init__(self, config: Optional[XContextConfig] = None):
        self.config = config or load_config()
        self.media_router = MediaRouter(self.config.x_video_service_dir, self.config.data_dir)
        self.browser_worker = BrowserWorker(
            chrome_executable=self.config.chrome_executable,
            user_data_dir=self.config.chrome_profile_dir,
            headless=True,
            convergence_limit=self.config.browser_convergence_scrolls,
            user_agent=self.config.user_agent,
        )
        self.graph_builder = ContextGraphBuilder()
        self.coverage_reporter = CoverageReporter()
        self.reproduction_planner = ReproductionPlanner()

    def resolve_context(
        self,
        url: str,
        max_replies: int = 25,
        max_quotes: int = 5,
        include_author_replies: bool = True,
        force_refresh: bool = False,
        enable_video_deep_analysis: bool = True,
    ) -> XContextManifest:
        """
        Ingests and reconstructs the complete accessible context for an X URL.
        """
        handle, status_id = parse_x_url(url)
        if not status_id:
            raise ValueError(f"Could not parse valid status ID from URL: {url}")

        job_id = f"ctx_{handle or 'tweet'}_{status_id}"
        job_dir = self.config.data_dir / job_id
        job_dir.mkdir(parents=True, exist_ok=True)
        manifest_file = job_dir / "manifest.json"

        # Check cache
        if not force_refresh and manifest_file.exists():
            try:
                with open(manifest_file, "r", encoding="utf-8") as f:
                    cached_data = json.load(f)
                    logger.info(f"Loaded cached context manifest for {job_id}")
                    return XContextManifest.model_validate(cached_data)
            except Exception as e:
                logger.warning(f"Failed to read cache file {manifest_file}: {e}")

        canonical_url = clean_x_url(url)
        logger.info(f"Resolving context for {canonical_url} (Job: {job_id})")

        # 1. Fetch structured metadata via vxtwitter / fxtwitter
        root_data, structured_media, resolver_name = self._fetch_structured_metadata(handle, status_id)

        # 2. Extract external links in root post
        raw_text = root_data.get("text", "")
        extracted_links = extract_urls_from_text(raw_text)
        resolved_external_links = []
        for l_url in extracted_links:
            # Skip twitter / t.co links that are just media anchors if needed
            if "t.co" not in l_url and "x.com" not in l_url and "twitter.com" not in l_url:
                res_link = self.media_router.resolve_external_link(l_url)
                resolved_external_links.append(res_link)

        # 3. Create RootPost model
        author_info = AuthorInfo(
            name=root_data.get("author_name", handle or ""),
            handle=root_data.get("author_handle", handle or ""),
            verified=root_data.get("author_verified", False),
        )

        root_post = RootPost(
            id=status_id,
            url=canonical_url,
            author=author_info,
            text=raw_text,
            created_at=root_data.get("created_at"),
            likes=root_data.get("likes", 0),
            retweets=root_data.get("retweets", 0),
            replies_count=root_data.get("replies_count", 0),
            quotes_count=root_data.get("quotes_count", 0),
            views=root_data.get("views"),
            media=structured_media,
            links=resolved_external_links,
        )

        # 4. Deep Video Analysis Delegation (if video attached and requested)
        if enable_video_deep_analysis:
            for m in root_post.media:
                if m.type == MediaType.VIDEO:
                    logger.info(f"Delegating video to x-video-intelligence: {m.url or canonical_url}")
                    self.media_router.process_video_item(m, canonical_url)

        # 5. Conversation Replies Retrieval
        # If replies are reported or requested, attempt browser scrape or fallback
        raw_replies: List[ReplyNode] = []
        truncation_notes = []
        screenshot_path = job_dir / "screenshot.png"

        # If browser worker is available, scrape replies and screenshot
        if self.config.chrome_executable and Path(self.config.chrome_executable).exists():
            logger.info("Executing BrowserWorker for conversation replies and screenshot...")
            browser_res = self.browser_worker.scrape_post_and_replies(
                url=canonical_url,
                max_replies=max_replies,
                screenshot_path=screenshot_path,
                job_id=job_id,
            )
            if browser_res.get("screenshot_taken"):
                logger.info(f"Screenshot successfully captured at {screenshot_path}")

            # Parse replies collected from browser
            for b_rep in browser_res.get("replies", []):
                rep_id = b_rep.get("id", f"rep_{len(raw_replies)}")
                rep_author = AuthorInfo(
                    name=b_rep.get("author", {}).get("name", ""),
                    handle=b_rep.get("author", {}).get("handle", ""),
                )
                rep_node = ReplyNode(
                    id=rep_id,
                    author=rep_author,
                    text=b_rep.get("text", ""),
                )
                raw_replies.append(rep_node)

            if browser_res.get("error"):
                truncation_notes.append(f"Browser worker notice: {browser_res['error']}")
        else:
            truncation_notes.append("Chrome executable not found for browser replies inspection")

        # 6. Process Conversation & Separate Author Follow-ups
        author_followups, top_replies = process_replies(
            raw_replies,
            root_author_handle=root_post.author.handle,
            min_rank=0,
            filter_author_only=False,
        )

        # 7. Quotes (Empty list if not available via public endpoints)
        quotes: List[QuoteNode] = []

        # 8. Build Provenance Graph
        graph = self.graph_builder.build_graph(
            root=root_post,
            author_followups=author_followups,
            replies=top_replies,
            quotes=quotes,
        )

        # 9. Compute Coverage
        coverage = self.coverage_reporter.compute_coverage(
            root=root_post,
            author_followups=author_followups,
            top_replies=top_replies,
            quotes=quotes,
            resolver_used=resolver_name,
            hit_limit=len(raw_replies) >= max_replies,
            limit_count=max_replies,
            truncation_notes=truncation_notes,
        )

        # 10. Summary dictionary
        summary = {
            "title": f"Post by @{root_post.author.handle}",
            "objective": root_post.text[:140],
            "media_types": [m.type.value for m in root_post.media],
            "replies_analyzed": len(author_followups) + len(top_replies),
            "author_followup_count": len(author_followups),
            "external_links": len(root_post.links),
            "coverage_status": coverage.status,
        }

        # Create temporary manifest to pass to reproduction planner
        manifest = XContextManifest(
            job_id=job_id,
            url=url,
            canonical_url=canonical_url,
            fetched_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
            root=root_post,
            author_followups=author_followups,
            top_replies=top_replies,
            quotes=quotes,
            graph=graph,
            coverage=coverage,
            summary=summary,
        )

        # 11. Generate Reproduction Plan
        repro_plan = self.reproduction_planner.generate_plan(manifest)
        manifest.reproduction_plan = repro_plan

        # Save manifest
        with open(manifest_file, "w", encoding="utf-8") as f:
            json.dump(manifest.model_dump(), f, indent=2, ensure_ascii=False)
        logger.info(f"Context manifest successfully written to {manifest_file}")

        return manifest

    def _fetch_structured_metadata(
        self, handle: Optional[str], status_id: str
    ) -> Tuple[Dict[str, Any], List[MediaItem], str]:
        """
        Attempts structured metadata retrieval via vxtwitter and fxtwitter.
        """
        headers = {"User-Agent": "Mozilla/5.0"}
        author_h = handle or "i"

        # Try vxtwitter
        vx_url = f"https://api.vxtwitter.com/{author_h}/status/{status_id}"
        try:
            r = requests.get(vx_url, headers=headers, timeout=10)
            if r.status_code == 200:
                d = r.json()
                media_list = []
                for m in d.get("media_extended", []):
                    m_type = MediaType.VIDEO if m.get("type") == "video" else MediaType.IMAGE
                    media_list.append(
                        MediaItem(
                            media_id=m.get("id_str"),
                            type=m_type,
                            url=m.get("url", ""),
                            thumbnail_url=m.get("thumbnail_url"),
                            duration_seconds=(m.get("duration_millis", 0) / 1000.0) if m.get("duration_millis") else None,
                            width=m.get("size", {}).get("width"),
                            height=m.get("size", {}).get("height"),
                        )
                    )
                return (
                    {
                        "text": d.get("text", ""),
                        "author_name": d.get("user_name", author_h),
                        "author_handle": d.get("user_screen_name", author_h),
                        "likes": d.get("likes", 0),
                        "retweets": d.get("retweets", 0),
                        "replies_count": d.get("replies", 0),
                        "created_at": d.get("date"),
                    },
                    media_list,
                    "VXTWITTER_API",
                )
        except Exception as e:
            logger.warning(f"vxtwitter fetch failed: {e}")

        # Try fxtwitter
        fx_url = f"https://api.fxtwitter.com/{author_h}/status/{status_id}"
        try:
            r = requests.get(fx_url, headers=headers, timeout=10)
            if r.status_code == 200:
                d = r.json().get("tweet", {})
                media_list = []
                for m in d.get("media", {}).get("videos", []):
                    media_list.append(
                        MediaItem(
                            type=MediaType.VIDEO,
                            url=m.get("url", ""),
                            thumbnail_url=m.get("thumbnail_url"),
                            duration_seconds=m.get("duration"),
                        )
                    )
                for photo in d.get("media", {}).get("photos", []):
                    media_list.append(
                        MediaItem(
                            type=MediaType.IMAGE,
                            url=photo.get("url", ""),
                        )
                    )
                return (
                    {
                        "text": d.get("text", ""),
                        "author_name": d.get("author", {}).get("name", author_h),
                        "author_handle": d.get("author", {}).get("screen_name", author_h),
                        "likes": d.get("likes", 0),
                        "retweets": d.get("retweets", 0),
                        "replies_count": d.get("replies", 0),
                        "created_at": d.get("created_at"),
                        "views": d.get("views"),
                    },
                    media_list,
                    "FXTWITTER_API",
                )
        except Exception as e:
            logger.warning(f"fxtwitter fetch failed: {e}")

        # Fallback to minimal placeholder
        return (
            {
                "text": f"Status {status_id}",
                "author_name": author_h,
                "author_handle": author_h,
            },
            [],
            "FALLBACK",
        )
