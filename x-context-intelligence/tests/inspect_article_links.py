from __future__ import annotations

import sys
import time
from playwright.sync_api import sync_playwright

sys.stdout.reconfigure(encoding="utf-8")

with sync_playwright() as p:
    browser = p.chromium.connect_over_cdp("http://127.0.0.1:9222")
    context = browser.contexts[0]
    pages = [p for p in context.pages if "chrome://" not in p.url]
    page = pages[0] if pages else context.new_page()

    page.goto("https://x.com/AlchainHust/status/1971839749724975175", wait_until="domcontentloaded", timeout=20000)
    time.sleep(3)

    articles = page.query_selector_all("article")
    print(f"Total articles on page: {len(articles)}")
    for i, a in enumerate(articles):
        print(f"\n--- ARTICLE #{i} LINKS ---")
        links = a.query_selector_all("a")
        for l in links:
            print("  Href:", l.get_attribute("href"), "| Text:", l.inner_text().replace("\n", " "))

    browser.close()
