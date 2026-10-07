from __future__ import annotations

import sys
import time
from playwright.sync_api import sync_playwright

sys.stdout.reconfigure(encoding="utf-8")

profile_dir = r"C:\Users\Admin\.buzz\chrome_profiles\Buzz-X-Research"
chrome_exe = r"C:\Program Files\Google\Chrome\Application\chrome.exe"

with sync_playwright() as p:
    context = p.chromium.launch_persistent_context(
        user_data_dir=profile_dir,
        executable_path=chrome_exe,
        headless=True,
        args=[
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-blink-features=AutomationControlled",
        ],
    )
    page = context.new_page()
    target_url = "https://x.com/AlchainHust/status/1971839749724975175"
    print(f"Navigating to {target_url}...")
    try:
        resp = page.goto(target_url, timeout=20000)
        print("Response status:", resp.status if resp else "None")
    except Exception as e:
        print("Navigation exception:", e)

    time.sleep(4)
    print("Page URL:", page.url)
    print("Page Title:", page.title())

    # Check for login indicators or overlays
    sign_in_texts = page.query_selector_all('text="Sign in to X"')
    login_buttons = page.query_selector_all('a[href*="/login"]')
    account_btn = page.query_selector('div[data-testid="SideNav_AccountSwitcher_Button"]')

    print("Sign in prompts found:", len(sign_in_texts))
    print("Login buttons found:", len(login_buttons))
    print("Logged in account switcher found:", bool(account_btn))

    articles = page.query_selector_all('article[data-testid="tweet"]')
    print("Tweets/Articles on page:", len(articles))
    for i, a in enumerate(articles[:5]):
        print(f" - Article #{i}: {a.inner_text()[:60]}...")

    # Check network/responses
    context.close()
