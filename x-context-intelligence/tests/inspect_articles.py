from __future__ import annotations

import sys
from playwright.sync_api import sync_playwright

sys.stdout.reconfigure(encoding="utf-8")

with sync_playwright() as p:
    browser = p.chromium.connect_over_cdp("http://127.0.0.1:9222")
    context = browser.contexts[0]
    pages = [p for p in context.pages if "x.com" in p.url]
    page = pages[0]

    articles = page.query_selector_all("article")
    print(f"Total articles found: {len(articles)}")
    for i, a in enumerate(articles):
        print(f"\n--- ARTICLE #{i} ---")
        print("HTML tag / attrs:", a.evaluate("el => el.outerHTML.substring(0, 200)"))
        print("Text:\n", a.inner_text())

    browser.close()
