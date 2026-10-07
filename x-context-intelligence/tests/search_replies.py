from __future__ import annotations

import sys
import time
from playwright.sync_api import sync_playwright

sys.stdout.reconfigure(encoding="utf-8")

search_url = "https://x.com/search?q=to%3AAlchainHust%201971839749724975175&f=live"

with sync_playwright() as p:
    browser = p.chromium.connect_over_cdp("http://127.0.0.1:9222")
    context = browser.contexts[0]
    pages = [p for p in context.pages if "x.com" in p.url]
    page = pages[0]

    print("Navigating to search URL:", search_url)
    page.goto(search_url, wait_until="domcontentloaded", timeout=20000)
    time.sleep(4)

    articles = page.query_selector_all("article")
    print(f"Search results articles: {len(articles)}")
    for i, a in enumerate(articles):
        print(f"\n--- SEARCH ARTICLE #{i} ---")
        print(a.inner_text()[:150].replace("\n", " "))

    browser.close()
