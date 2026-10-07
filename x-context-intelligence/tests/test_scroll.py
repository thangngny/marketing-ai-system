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

    all_articles_text = {}
    unproductive = 0
    cycle = 0

    print("Starting scroll convergence loop...")
    while cycle < 15:
        cycle += 1
        articles = page.query_selector_all("article")
        new_count = 0
        for a in articles:
            txt = a.inner_text().strip()
            # Extract first 60 chars as signature
            sig = txt[:80]
            if sig not in all_articles_text:
                all_articles_text[sig] = txt
                new_count += 1

        print(f"Cycle {cycle}: {len(articles)} on screen, {new_count} new (Total unique: {len(all_articles_text)})")
        if new_count == 0:
            unproductive += 1
        else:
            unproductive = 0

        if unproductive >= 3:
            print(f"Convergence reached after {unproductive} unproductive cycles!")
            break

        page.evaluate("window.scrollBy(0, 800);")
        time.sleep(1.5)

    print(f"\nFinal count of collected articles: {len(all_articles_text)}")
    for idx, (sig, full_text) in enumerate(all_articles_text.items()):
        print(f"\n=== ARTICLE #{idx} ===")
        print(full_text[:200])

    browser.close()
