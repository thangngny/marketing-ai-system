from __future__ import annotations

import sys
from playwright.sync_api import sync_playwright

sys.stdout.reconfigure(encoding="utf-8")

with sync_playwright() as p:
    browser = p.chromium.connect_over_cdp("http://127.0.0.1:9222")
    context = browser.contexts[0]
    pages = [p for p in context.pages if "x.com" in p.url]
    page = pages[0]

    # Look for buttons like "Show", "More", "Replies"
    buttons = page.query_selector_all("button")
    print(f"Total buttons: {len(buttons)}")
    for b in buttons:
        txt = b.inner_text().strip()
        if txt and any(k in txt.lower() for k in ["show", "more", "reply", "replies", "view"]):
            print(" Button text:", txt)

    browser.close()
