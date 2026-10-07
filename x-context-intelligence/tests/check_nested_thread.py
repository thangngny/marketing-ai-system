from __future__ import annotations

import sys
import time
from playwright.sync_api import sync_playwright

sys.stdout.reconfigure(encoding="utf-8")

thread_url = "https://x.com/sunnyguoyuan/status/1972290242192572828"

with sync_playwright() as p:
    browser = p.chromium.connect_over_cdp("http://127.0.0.1:9222")
    context = browser.contexts[0]
    pages = [p for p in context.pages if "chrome://" not in p.url]
    page = pages[0] if pages else context.new_page()

    page.goto(thread_url, wait_until="domcontentloaded", timeout=20000)
    time.sleep(3)

    articles = page.query_selector_all("article")
    print(f"Total articles on thread page: {len(articles)}")
    for i, a in enumerate(articles):
        print(f"\n--- THREAD ARTICLE #{i} ---")
        print(a.inner_text().replace("\n", " ")[:200])

    browser.close()
