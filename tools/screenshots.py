#!/usr/bin/env python3
"""Capture screenshots — inject JS to load specific champion data."""
import time
from pathlib import Path
from playwright.sync_api import sync_playwright

SCREENSHOT_DIR = Path("/opt/data/projects/arena-buddy/screenshots")
SCREENSHOT_DIR.mkdir(exist_ok=True)
BASE = "http://127.0.0.1:8765"
BROWSER = "/opt/hermes/.playwright/chromium_headless_shell-1217/chrome-headless-shell-linux64/chrome-headless-shell"

def capture(page, name, url=None, wait=1.5):
    if url:
        page.goto(url, wait_until="networkidle", timeout=15000)
        time.sleep(wait)
    path = SCREENSHOT_DIR / f"{name}.png"
    page.screenshot(path=str(path), full_page=False)
    size_kb = path.stat().st_size // 1024
    print(f"  ✓ {name} ({size_kb} KB)")
    return str(path)

def main():
    print("\n📸 Arena Buddy — Screenshot Tour\n")

    with sync_playwright() as p:
        browser = p.chromium.launch(
            executable_path=BROWSER,
            headless=True,
            args=["--no-sandbox", "--disable-gpu", "--disable-dev-shm-usage"]
        )

        # --- 1. In-Game: Lucian ---
        print("1. In-Game — Lucian:")
        ctx = browser.new_context(viewport={"width": 1280, "height": 900})
        page = ctx.new_page()
        page.goto(BASE, wait_until="networkidle", timeout=15000)
        time.sleep(1.0)
        # Force-load Lucian via JS
        page.evaluate("loadChampionData('Lucian')")
        time.sleep(2.0)
        capture(page, "01-ingame-lucian", wait=0)

        # --- 2. In-Game: Zed ---
        print("2. In-Game — Zed:")
        page.evaluate("loadChampionData('Zed')")
        time.sleep(2.0)
        capture(page, "02-ingame-zed", wait=0)

        # --- 3. In-Game: Sett ---
        print("3. In-Game — Sett:")
        page.evaluate("loadChampionData('Sett')")
        time.sleep(2.0)
        capture(page, "03-ingame-sett", wait=0)

        # --- 4. In-Game: Aatrox ---
        print("4. In-Game — Aatrox:")
        page.evaluate("loadChampionData('Aatrox')")
        time.sleep(2.0)
        capture(page, "04-ingame-aatrox", wait=0)

        # --- 5. In-Game: Yasuo ---
        print("5. In-Game — Yasuo:")
        page.evaluate("loadChampionData('Yasuo')")
        time.sleep(2.0)
        capture(page, "05-ingame-yasuo", wait=0)

        # --- 6. Browse tab ---
        print("6. Browse Tab:")
        page.evaluate("switchTab('browse')")
        time.sleep(1.0)
        capture(page, "06-browse", wait=0)

        # --- 7. Match History ---
        print("7. Match History:")
        page.evaluate("switchTab('history')")
        time.sleep(1.0)
        capture(page, "07-history", wait=0)

        # --- 8. Settings ---
        print("8. Settings:")
        page.evaluate("switchTab('settings')")
        time.sleep(1.0)
        capture(page, "08-settings", wait=0)

        # --- 9. Wide Lucian ---
        print("9. Wide view — Lucian:")
        ctx2 = browser.new_context(viewport={"width": 1440, "height": 1000})
        page2 = ctx2.new_page()
        page2.goto(BASE, wait_until="networkidle", timeout=15000)
        time.sleep(1.0)
        page2.evaluate("loadChampionData('Lucian')")
        time.sleep(2.0)
        capture(page2, "09-wide-lucian", wait=0)

        browser.close()

    print(f"\n✅ Done! {SCREENSHOT_DIR}/")
    for f in sorted(SCREENSHOT_DIR.glob("*.png")):
        print(f"  {f.name} ({f.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
