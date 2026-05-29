"""Capture Arena Buddy screenshots for Twisted Fate, Zoe, Anivia."""

import time
from playwright.sync_api import sync_playwright

BROWSER = "/opt/hermes/.playwright/chromium_headless_shell-1217/chrome-headless-shell-linux64/chrome-headless-shell"

with sync_playwright() as p:
    browser = p.chromium.launch(
        executable_path=BROWSER,
        headless=True,
        args=["--no-sandbox", "--disable-gpu", "--disable-dev-shm-usage"],
    )
    page = browser.new_page(viewport={"width": 1280, "height": 900})

    for champ_name, champ_key, filename in [
        ("Twisted Fate", "TwistedFate", "tour-twisted-fate"),
        ("Zoe", "Zoe", "tour-zoe"),
        ("Anivia", "Anivia", "tour-anivia"),
    ]:
        print(f"Capturing {champ_name}...")
        page.goto("http://127.0.0.1:8765", wait_until="load", timeout=15000)
        time.sleep(1.0)

        # Load champion data — forces API call + render
        page.evaluate(f"loadChampionData('{champ_key}')")
        time.sleep(2.5)

        # Switch to in-game tab for the 3-pane view
        page.evaluate("switchTab('in-game')")
        time.sleep(0.5)

        path = f"/opt/data/projects/arena-buddy/screenshots/{filename}.png"
        page.screenshot(path=path, full_page=False)
        print(f"  → {path}")

    browser.close()
    print("Done!")
