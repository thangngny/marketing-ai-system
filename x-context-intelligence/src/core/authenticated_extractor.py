from __future__ import annotations

import json
import logging
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple
from playwright.sync_api import sync_playwright

from src.models.types import (
    AuthorInfo,
    ExternalLink,
    MediaItem,
    MediaType,
    QuoteNode,
    ReplyCategory,
    ReplyNode,
    RootPost,
)
from src.utils.sanitizer import extract_urls_from_text

logger = logging.getLogger("x_context.auth_extractor")


class AuthenticatedContextExtractor:
    """
    Extracts complete X context via authenticated Chrome session:
    - Network interception (GraphQL TweetDetail)
    - DOM extraction with real convergence (stops after 3 cycles of 0 new IDs)
    - Explicit isolation and high-priority classification for Root Author replies
    - Nested reply tracking and quote detection
    """

    def __init__(self, cdp_url: str = "http://127.0.0.1:9222"):
        self.cdp_url = cdp_url

    def extract_context(
        self,
        target_url: str,
        max_scroll_cycles: int = 15,
        convergence_threshold: int = 3,
        screenshot_path: Optional[Path] = None,
    ) -> Dict[str, Any]:
        result = {
            "root_post": None,
            "replies": [],
            "author_followups": [],
            "nested_replies": [],
            "quotes": [],
            "scroll_cycles": 0,
            "unique_reply_ids": [],
            "nested_reply_ids": [],
            "author_reply_ids": [],
            "stop_reason": "UNKNOWN",
            "graphql_captured": False,
            "authenticated": False,
            "error": None,
        }

        # Match root author handle from URL
        match = re.search(r"x\.com/([A-Za-z0-9_]+)/status/(\d+)", target_url)
        target_handle = match.group(1).lower() if match else ""
        target_status_id = match.group(2) if match else ""

        try:
            with sync_playwright() as p:
                browser = p.chromium.connect_over_cdp(self.cdp_url)
                context = browser.contexts[0]

                # Check auth cookies
                cookies = context.cookies()
                cookie_names = [c["name"] for c in cookies]
                if "auth_token" in cookie_names or "twid" in cookie_names:
                    result["authenticated"] = True

                # Use active tab or open new
                pages = [p for p in context.pages if "chrome://" not in p.url]
                page = pages[0] if pages else context.new_page()

                # Setup Network Interceptor for GraphQL TweetDetail
                graphql_entries = []

                def handle_response(response):
                    try:
                        url = response.url
                        if "TweetDetail" in url or "graphql" in url:
                            if response.status == 200 and "application/json" in (response.headers.get("content-type") or ""):
                                text_body = response.text()
                                try:
                                    json_body = json.loads(text_body)
                                    graphql_entries.append(json_body)
                                    result["graphql_captured"] = True
                                except Exception:
                                    pass
                    except Exception:
                        pass

                page.on("response", handle_response)

                logger.info(f"Navigating to {target_url} in authenticated Chrome...")
                page.goto(target_url, wait_until="domcontentloaded", timeout=30000)
                time.sleep(3)

                # Capture full screenshot
                if screenshot_path:
                    try:
                        screenshot_path.parent.mkdir(parents=True, exist_ok=True)
                        page.screenshot(path=str(screenshot_path), full_page=False)
                    except Exception as e:
                        logger.warning(f"Could not save screenshot: {e}")

                # Real convergence loop
                seen_ids: Set[str] = set()
                collected_replies: Dict[str, ReplyNode] = {}
                nested_ids: Set[str] = set()
                author_ids: Set[str] = set()

                unproductive_count = 0
                cycle = 0

                while cycle < max_scroll_cycles:
                    cycle += 1
                    articles = page.query_selector_all('article[data-testid="tweet"]')
                    new_in_cycle = 0

                    for art in articles:
                        try:
                            t_info = self._parse_article_dom(art, target_handle)
                            if not t_info:
                                continue

                            tid = t_info["id"]

                            # Skip if root tweet
                            if tid == target_status_id:
                                if not result["root_post"]:
                                    result["root_post"] = t_info
                                continue

                            if tid not in seen_ids:
                                seen_ids.add(tid)
                                new_in_cycle += 1

                                r_node = ReplyNode(
                                    id=tid,
                                    author=AuthorInfo(
                                        name=t_info["author_name"],
                                        handle=t_info["author_handle"],
                                    ),
                                    text=t_info["text"],
                                    likes=t_info["likes"],
                                    retweets=t_info["retweets"],
                                    is_author_reply=t_info["is_author"],
                                    reply_to_id=t_info.get("reply_to_id"),
                                )

                                # Priority classification for Root Author
                                if t_info["is_author"]:
                                    author_ids.add(tid)
                                    r_text_lower = t_info["text"].lower()
                                    if any(k in r_text_lower for k in ["fix", "error", "bug", "mistake", "update"]):
                                        r_node.category = ReplyCategory.CORRECTION_OR_DEBUNK
                                    elif any(k in r_text_lower for k in ["mcp", "code", "config", "port", "install", "chrome"]):
                                        r_node.category = ReplyCategory.TECHNICAL_IMPLEMENTATION
                                    else:
                                        r_node.category = ReplyCategory.AUTHOR_FOLLOWUP
                                    r_node.rank = 100
                                    result["author_followups"].append(r_node)
                                else:
                                    if t_info.get("is_nested"):
                                        nested_ids.add(tid)
                                    collected_replies[tid] = r_node

                        except Exception as e:
                            logger.debug(f"Error parsing article element in cycle {cycle}: {e}")

                    if new_in_cycle == 0:
                        unproductive_count += 1
                    else:
                        unproductive_count = 0

                    if unproductive_count >= convergence_threshold:
                        result["stop_reason"] = f"CONVERGENCE_REACHED (0 new tweets in {convergence_threshold} consecutive cycles)"
                        break

                    # Scroll down by viewport height
                    page.evaluate("window.scrollBy(0, 800);")
                    time.sleep(1.5)

                if cycle >= max_scroll_cycles and result["stop_reason"] == "UNKNOWN":
                    result["stop_reason"] = f"MAX_CYCLES_REACHED ({max_scroll_cycles})"

                result["scroll_cycles"] = cycle
                result["unique_reply_ids"] = list(seen_ids)
                result["nested_reply_ids"] = list(nested_ids)
                result["author_reply_ids"] = list(author_ids)
                result["replies"] = list(collected_replies.values())

                browser.close()

        except Exception as e:
            logger.error(f"Error during authenticated extraction: {e}")
            result["error"] = str(e)

        return result

    def _parse_article_dom(self, article_el, target_handle: str) -> Optional[Dict[str, Any]]:
        try:
            # 1. Extract status ID
            links = article_el.query_selector_all('a[href*="/status/"]')
            tweet_id = None
            handle = ""
            for l in links:
                href = l.get_attribute("href") or ""
                parts = href.strip("/").split("/")
                if "status" in parts:
                    idx = parts.index("status")
                    if idx + 1 < len(parts) and parts[idx + 1].isdigit():
                        tweet_id = parts[idx + 1]
                        if idx > 0:
                            handle = parts[idx - 1]
                        break

            if not tweet_id:
                return None

            # 2. Extract Author
            user_el = article_el.query_selector('div[data-testid="User-Name"]')
            name = ""
            if user_el:
                lines = user_el.inner_text().split("\n")
                if len(lines) >= 1:
                    name = lines[0]
                if len(lines) >= 2 and "@" in lines[1]:
                    handle = lines[1].replace("@", "")

            # 3. Text
            text_el = article_el.query_selector('div[data-testid="tweetText"]')
            text = text_el.inner_text() if text_el else ""

            # 4. Check if nested or replying to someone
            is_nested = False
            reply_to_el = article_el.query_selector('div[dir="ltr"]')
            if reply_to_el and "Replying to" in reply_to_el.inner_text():
                is_nested = True

            # 5. Metrics
            likes = 0
            retweets = 0
            like_el = article_el.query_selector('button[data-testid="like"]')
            if like_el and like_el.inner_text().isdigit():
                likes = int(like_el.inner_text())
            rt_el = article_el.query_selector('button[data-testid="retweet"]')
            if rt_el and rt_el.inner_text().isdigit():
                retweets = int(rt_el.inner_text())

            is_author = handle.lower().lstrip("@") == target_handle.lstrip("@")

            return {
                "id": tweet_id,
                "author_name": name,
                "author_handle": handle,
                "text": text,
                "likes": likes,
                "retweets": retweets,
                "is_author": is_author,
                "is_nested": is_nested,
            }
        except Exception:
            return None
