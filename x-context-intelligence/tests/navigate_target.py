from __future__ import annotations

import sys
import time
from playwright.sync_api import sync_playwright

sys.stdout.reconfigure(encoding="utf-8")

target_url = "https://x.com/AlchainHust/status/1971839749724975175"

with sync_playwright() as p:
    browser = p.chromium.connect_over_cdp("http://127.0.0.1:9222")
    context = browser.contexts[0]
    pages = [p for p in context.pages if "chrome://" not in p.url]
    page = pages[0] if pages else context.new_page()

    print("Navigating to target URL:", target_url)
    page.goto(target_url, wait_until="domcontentloaded", timeout=30000)
    time.sleep(5)

    print("Current URL:", page.url)
    print("Page Title:", page.title())

    articles = page.query_selector_all('article[data-testid="tweet"]')
    print("Articles found:", len(articles))
    for idx, art in enumerate(articles):
        text_clean = art.inner_text().replace("\n", " ")
        print(f"Article #{idx}: {text_clean[:120]}...")

    # Check if there is a 'Sign in' modal or backdrop blocking
    dialogs = page.query_selector_all('div[role="dialog"]')
    print("Dialogs/Modals found:", len(dialogs))
    for d in dialogs:
        print(" Dialog text preview:", d.inner_text().replace("\n", " ")[:100])

    browser.close()
