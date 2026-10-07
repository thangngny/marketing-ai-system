from __future__ import annotations

import ctypes
import datetime
import json
import logging
import os
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional
from playwright.sync_api import sync_playwright

logger = logging.getLogger("x_context.browser")


class BrowserLock:
    """
    Cross-process mutex lock ensuring only one agent accesses the shared
    Buzz-X-Research Chrome profile / CDP port at a time.
    Uses Win32 Named Mutex with automatic abandoned-mutex recovery (crashed tasks
    automatically release their lock in the Windows kernel) + lockfile metadata.
    """
    WAIT_OBJECT_0 = 0x00000000
    WAIT_ABANDONED = 0x00000080
    WAIT_TIMEOUT = 0x00000102

    def __init__(
        self,
        job_id: str,
        timeout: int = 60,
        lock_dir: Optional[Path] = None,
        mutex_name: str = "Local\\Buzz_X_Research_Browser_Mutex",
    ):
        self.job_id = job_id
        self.timeout = timeout
        self.mutex_name = mutex_name
        self.lock_dir = lock_dir or Path(r"C:\Users\Admin\.buzz\chrome_profiles")
        self.lock_file = self.lock_dir / "browser_lock.json"
        self._kernel32 = ctypes.windll.kernel32
        self._handle = None
        self._acquired = False

    def __enter__(self):
        self.acquire()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.release()

    def acquire(self):
        timeout_ms = int(self.timeout * 1000)
        self._handle = self._kernel32.CreateMutexW(None, False, self.mutex_name)
        if not self._handle:
            raise RuntimeError(f"Failed to create browser mutex '{self.mutex_name}'")

        wait_res = self._kernel32.WaitForSingleObject(self._handle, timeout_ms)
        if wait_res == self.WAIT_TIMEOUT:
            holder_info = self._read_lock_file()
            raise TimeoutError(
                f"Timed out waiting {self.timeout}s for browser lock. Current holder: {holder_info}"
            )
        elif wait_res == self.WAIT_ABANDONED:
            logger.warning(
                f"Browser mutex was abandoned by a previously crashed process. Acquired safely by job {self.job_id}."
            )

        self._acquired = True
        self._write_lock_file()
        logger.info(f"Acquired browser lock for job {self.job_id} (pid {os.getpid()})")

    def release(self):
        if self._acquired and self._handle:
            try:
                self._clear_lock_file()
            except Exception as e:
                logger.warning(f"Failed to clear browser lock file: {e}")
            try:
                self._kernel32.ReleaseMutex(self._handle)
            except Exception as e:
                logger.warning(f"Failed to release browser mutex: {e}")
            self._acquired = False

        if self._handle:
            try:
                self._kernel32.CloseHandle(self._handle)
            except Exception:
                pass
            self._handle = None
            logger.info(f"Released browser lock for job {self.job_id}")

    def _write_lock_file(self):
        try:
            self.lock_dir.mkdir(parents=True, exist_ok=True)
            data = {
                "job_id": self.job_id,
                "pid": os.getpid(),
                "acquired_at": time.time(),
                "time_iso": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            }
            with open(self.lock_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.warning(f"Could not write browser lock file: {e}")

    def _clear_lock_file(self):
        try:
            if self.lock_file.exists():
                self.lock_file.unlink(missing_ok=True)
        except Exception:
            pass

    def _read_lock_file(self) -> Dict[str, Any]:
        try:
            if self.lock_file.exists():
                with open(self.lock_file, "r", encoding="utf-8") as f:
                    return json.load(f)
        except Exception:
            pass
        return {}


class BrowserWorker:
    """
    Dedicated Chrome browser worker connecting to port 9222 (Buzz-X-Research profile).
    STRICTLY READ-ONLY: Never interacts with like/repost/reply/follow buttons.
    Uses scrolling with convergence detection (stops after 3 unproductive cycles).
    Guarded by cross-process BrowserLock to prevent multi-agent profile & port collisions.
    """

    def __init__(
        self,
        chrome_executable: str = r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        user_data_dir: str = r"C:\Users\Admin\.buzz\chrome_profiles\Buzz-X-Research",
        cdp_port: int = 9222,
        headless: bool = True,
        convergence_limit: int = 3,
        user_agent: Optional[str] = None,
        lock_timeout: int = 60,
    ):
        self.chrome_executable = chrome_executable
        self.user_data_dir = user_data_dir
        self.cdp_port = cdp_port
        self.headless = headless
        self.convergence_limit = convergence_limit
        self.user_agent = user_agent
        self.lock_timeout = lock_timeout

    def scrape_post_and_replies(
        self,
        url: str,
        max_replies: int = 25,
        screenshot_path: Optional[Path] = None,
        job_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        results: Dict[str, Any] = {
            "root": None,
            "replies": [],
            "screenshot_taken": False,
            "scroll_count": 0,
            "convergence_reached": False,
            "stop_reason": "UNKNOWN",
            "error": None,
        }

        lock_id = job_id or f"scrape_{abs(hash(url))}"
        lock_dir = Path(self.user_data_dir).parent

        try:
            with BrowserLock(job_id=lock_id, timeout=self.lock_timeout, lock_dir=lock_dir):
                with sync_playwright() as p:
                    browser = None
                    context = None
                    created_page = False

                    # Try connecting to active CDP session on port 9222 first
                    try:
                        browser = p.chromium.connect_over_cdp(f"http://127.0.0.1:{self.cdp_port}")
                        context = browser.contexts[0]
                        logger.info(f"Connected to existing Chrome session over CDP (port {self.cdp_port}).")
                    except Exception:
                        logger.info("No active CDP port, launching persistent context...")
                        context = p.chromium.launch_persistent_context(
                            user_data_dir=self.user_data_dir,
                            executable_path=self.chrome_executable,
                            headless=self.headless,
                            args=[
                                "--no-first-run",
                                "--no-default-browser-check",
                                "--disable-blink-features=AutomationControlled",
                            ],
                        )

                    try:
                        pages = [pg for pg in context.pages if "chrome://" not in pg.url]
                        if pages:
                            page = pages[0]
                        else:
                            page = context.new_page()
                            created_page = True

                        logger.info(f"Navigating to {url}...")
                        page.goto(url, wait_until="domcontentloaded", timeout=25000)
                        time.sleep(3)

                        if screenshot_path:
                            try:
                                screenshot_path.parent.mkdir(parents=True, exist_ok=True)
                                page.screenshot(path=str(screenshot_path), full_page=False)
                                results["screenshot_taken"] = True
                            except Exception as e:
                                logger.warning(f"Could not take screenshot: {e}")

                        # Real convergence loop
                        extracted_tweets = {}
                        unproductive_scrolls = 0
                        scroll_count = 0

                        while scroll_count < 10 and len(extracted_tweets) < (max_replies + 1):
                            scroll_count += 1
                            articles = page.query_selector_all("article")
                            new_found = 0

                            for art in articles:
                                try:
                                    tweet_data = self._parse_article(art)
                                    if tweet_data and tweet_data["id"] not in extracted_tweets:
                                        extracted_tweets[tweet_data["id"]] = tweet_data
                                        new_found += 1
                                except Exception as e:
                                    logger.debug(f"Error parsing article element: {e}")

                            if new_found == 0:
                                unproductive_scrolls += 1
                            else:
                                unproductive_scrolls = 0

                            if unproductive_scrolls >= self.convergence_limit:
                                results["convergence_reached"] = True
                                results["stop_reason"] = f"CONVERGENCE_REACHED (0 new tweets in {self.convergence_limit} consecutive scrolls)"
                                break

                            page.evaluate("window.scrollBy(0, 800);")
                            time.sleep(1.2)

                        results["scroll_count"] = scroll_count
                        if not results["stop_reason"] or results["stop_reason"] == "UNKNOWN":
                            results["stop_reason"] = "MAX_SCROLLS_COMPLETED"

                        # Separate root tweet from replies
                        all_items = list(extracted_tweets.values())
                        if all_items:
                            results["root"] = all_items[0]
                            results["replies"] = all_items[1:max_replies + 1]

                    finally:
                        if browser is not None:
                            # CDP session: close page if we created it, disconnect browser
                            try:
                                if created_page and page:
                                    page.close()
                            except Exception:
                                pass
                        elif context is not None:
                            # Standalone persistent context: close context
                            try:
                                context.close()
                            except Exception:
                                pass

        except TimeoutError as te:
            logger.error(f"BrowserWorker lock timeout scraping {url}: {te}")
            results["error"] = f"BROWSER_LOCK_TIMEOUT: {te}"
            results["stop_reason"] = "BROWSER_BUSY_TIMEOUT"
        except Exception as e:
            logger.error(f"BrowserWorker error scraping {url}: {e}")
            results["error"] = str(e)

        return results

    def _parse_article(self, article_el) -> Optional[Dict[str, Any]]:
        try:
            links = article_el.query_selector_all('a[href*="/status/"]')
            tweet_id = None
            handle = ""

            for l in links:
                href = l.get_attribute("href") or ""
                match = re.search(r"/([A-Za-z0-9_]+)/status/(\d+)", href)
                if match:
                    handle = match.group(1)
                    tweet_id = match.group(2)
                    break

            if not tweet_id:
                # Check for profile link
                for l in article_el.query_selector_all("a"):
                    href = l.get_attribute("href") or ""
                    if href.startswith("/") and len(href) > 2 and "/" not in href[1:]:
                        handle = href.strip("/")
                        break
                text_content = article_el.inner_text().strip()
                if not text_content:
                    return None
                tweet_id = f"gen_{hash(text_content)}"

            # Extract user name and text
            all_text = article_el.inner_text().split("\n")
            name = all_text[0] if all_text else handle

            # Find the main body text
            body_lines = []
            for line in all_text:
                clean_l = line.strip()
                if not clean_l:
                    continue
                if clean_l.startswith("@") or clean_l == name or "·" in clean_l or clean_l == "Show translation":
                    continue
                if clean_l.isdigit() or any(clean_l.endswith(s) for s in ["Views", "K", "M"]):
                    continue
                body_lines.append(clean_l)

            full_body = "\n".join(body_lines)

            # Metrics
            likes = 0
            retweets = 0
            for l in all_text:
                if l.strip().isdigit() and int(l.strip()) > likes:
                    likes = int(l.strip())

            return {
                "id": tweet_id,
                "author": {
                    "name": name,
                    "handle": handle,
                },
                "text": full_body if full_body else "\n".join(all_text[:3]),
                "likes": likes,
                "retweets": retweets,
            }
        except Exception as e:
            logger.debug(f"Failed parsing article: {e}")
            return None
