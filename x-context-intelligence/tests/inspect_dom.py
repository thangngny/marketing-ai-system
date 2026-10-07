from __future__ import annotations

import sys
import time
from playwright.sync_api import sync_playwright

sys.stdout.reconfigure(encoding="utf-8")

with sync_playwright() as p:
    browser = p.chromium.connect_over_cdp("http://127.0.0.1:9222")
    context = browser.contexts[0]
    pages = [p for p in context.pages if "x.com" in p.url]
    page = pages[0]

    print("Current page URL:", page.url)
    print("Waiting for page load state...")
    time.sleep(3)

    # Check for tweet containers
    selectors = [
        'article',
        '[data-testid="tweet"]',
        '[data-testid="tweetText"]',
        '[data-testid="cellInnerDiv"]',
        'div[data-testid="primaryColumn"]',
        'main[role="main"]',
        'div[aria-label="Timeline: Conversation"]'
    ]

    for sel in selectors:
        els = page.query_selector_all(sel)
        print(f"Selector '{sel}': {len(els)} elements found")

    # Check if there is text in primaryColumn or main
    main_el = page.query_selector('main[role="main"]')
    if main_el:
        print("Main text preview (first 500 chars):\n", main_el.inner_text()[:500])

    browser.close()
