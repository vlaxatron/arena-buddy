#!/usr/bin/env python3
"""Capture Arena Buddy screenshots via HTTP GET + WeasyPrint HTML→PNG rendering."""
import urllib.request, json, time
from pathlib import Path
from weasyprint import HTML

SCREENSHOT_DIR = Path("/opt/data/projects/arena-buddy/screenshots")
SCREENSHOT_DIR.mkdir(exist_ok=True)
BASE = "http://127.0.0.1:8765"

def capture_page(filename, url, viewport_w=1280):
    """Fetch HTML from server and render to PNG."""
    print(f"  Capturing {filename}...")
    try:
        with urllib.request.urlopen(url, timeout=10) as r:
            html = r.read().decode("utf-8")
        path = SCREENSHOT_DIR / filename
        HTML(string=html).write_png(str(path), presentational_hints=True, optimize_images=True)
        size_kb = path.stat().st_size // 1024
        print(f"    ✓ {filename} ({size_kb} KB)")
        return str(path)
    except Exception as e:
        print(f"    ✗ {filename}: {e}")
        return None

def main():
    print("\n📸 Arena Buddy — Screenshot Tour\n")

    # 1. In-Game view (default: Lucian)
    print("1. In-Game Tab (Lucian)")
    capture_page("01-ingame-lucian.png", f"{BASE}/")

    # 2. In-Game — Kai'Sa
    print("\n2. In-Game Tab (Kai'Sa)")
    capture_page("02-ingame-kaisa.png", f"{BASE}/?champion=Kai%27Sa")

    # 3. Browse tab
    print("\n3. Browse Tab")
    capture_page("03-browse.png", f"{BASE}/#browse")

    # 4. Match History
    print("\n4. Match History Tab")
    capture_page("04-history.png", f"{BASE}/#history")

    # 5. Settings
    print("\n5. Settings Tab")
    capture_page("05-settings.png", f"{BASE}/#settings")

    # 6. In-Game — Zed
    print("\n6. In-Game Tab (Zed)")
    capture_page("06-ingame-zed.png", f"{BASE}/?champion=Zed")

    # 7. In-Game — Sett
    print("\n7. In-Game Tab (Sett)")
    capture_page("07-ingame-sett.png", f"{BASE}/?champion=Sett")

    print(f"\n✅ Done! Screenshots in {SCREENSHOT_DIR}/")
    for f in sorted(SCREENSHOT_DIR.glob("*.png")):
        size = f.stat().st_size // 1024
        print(f"  {f.name} ({size} KB)")


if __name__ == "__main__":
    main()
