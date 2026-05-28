#!/usr/bin/env python3
"""Batch download all Arena Buddy icons efficiently using httpx async.

Usage: python batch_download_icons.py
Downloads: ~172 champion icons + ~705 item icons + ~227 augment icons
Total: ~1104 icons from Data Dragon + CommunityDragon CDNs
"""
import asyncio, json, sys, time
from pathlib import Path
import httpx

# Config
CACHE = Path("/opt/data/.cache/arena-buddy")
DDRAGON_PATCH = "16.11.1"
CONCURRENT = 10  # parallel requests
BATCH_SIZE = 50  # report progress every N downloads

# Ensure dirs exist
for d in ["champions", "items", "augments"]:
    (CACHE / d).mkdir(parents=True, exist_ok=True)

sem = asyncio.Semaphore(CONCURRENT)
downloaded = 0
skipped = 0
failed = 0
start_time = time.time()


async def download_one(client: httpx.AsyncClient, url: str, path: Path) -> str:
    """Download a single file. Returns 'ok', 'skip', or 'fail'."""
    global downloaded, skipped, failed
    if path.exists():
        skipped += 1
        return "skip"
    try:
        async with sem:
            resp = await client.get(url, timeout=httpx.Timeout(15.0))
            if resp.status_code == 200:
                path.write_bytes(resp.content)
                downloaded += 1
                return "ok"
            else:
                failed += 1
                return f"fail-{resp.status_code}"
    except Exception as e:
        failed += 1
        return f"fail-{type(e).__name__}"


async def download_batch(items: list[tuple[str, Path]], label: str):
    """Download a batch with progress reporting."""
    global downloaded, skipped, failed
    total = len(items)
    print(f"\n--- {label}: {total} icons ---")
    
    async with httpx.AsyncClient(
        headers={"User-Agent": "Mozilla/5.0"},
        follow_redirects=True,
    ) as client:
        tasks = [download_one(client, url, path) for url, path in items]
        # Process in batches for progress reporting
        for i in range(0, total, BATCH_SIZE):
            chunk = tasks[i : i + BATCH_SIZE]
            await asyncio.gather(*chunk)
            elapsed = time.time() - start_time
            rate = (downloaded + skipped) / elapsed if elapsed > 0 else 0
            print(f"  [{i+len(chunk):4d}/{total:4d}] "
                  f"ok={downloaded} skip={skipped} fail={failed} "
                  f"({rate:.0f}/s, {elapsed:.0f}s elapsed)")
    
    print(f"  DONE {label}: {downloaded} downloaded, {skipped} skipped, {failed} failed")


async def main():
    # ---- Champions ----
    with open(CACHE / "data" / "champions.json") as f:
        champ_data = json.load(f)["data"]
    champ_tasks = [
        (f"https://ddragon.leagueoflegends.com/cdn/{DDRAGON_PATCH}/img/champion/{c['image']['full']}",
         CACHE / "champions" / c["image"]["full"])
        for c in champ_data.values()
    ]
    await download_batch(champ_tasks, "Champions")

    # ---- Items ----
    with open(CACHE / "data" / "items.json") as f:
        item_data = json.load(f)["data"]
    item_tasks = [
        (f"https://ddragon.leagueoflegends.com/cdn/{DDRAGON_PATCH}/img/item/{item_id}.png",
         CACHE / "items" / f"{item_id}.png")
        for item_id in item_data.keys()
    ]
    await download_batch(item_tasks, "Items")

    # ---- Augments ----
    with open(CACHE / "data" / "augments.json") as f:
        aug_data = json.load(f)["augments"]
    aug_tasks = []
    for aug in aug_data:
        api = aug["apiName"]
        # Use the iconLarge field if available, otherwise construct
        icon_path = aug.get("iconLarge", "")
        if icon_path:
            url = f"https://raw.communitydragon.org/latest/game/{icon_path.lower()}"
        else:
            url = f"https://raw.communitydragon.org/latest/game/assets/ux/cherry/augments/icons/{api.lower()}_large.png"
        aug_tasks.append((url, CACHE / "augments" / f"{api}.png"))
    await download_batch(aug_tasks, "Augments")

    # ---- Summary ----
    total_time = time.time() - start_time
    total = downloaded + skipped + failed
    print(f"\n{'='*60}")
    print(f"COMPLETE: {downloaded} new, {skipped} skipped, {failed} failed")
    print(f"Total: {total} icons processed in {total_time:.0f}s")
    for d in ["champions", "items", "augments"]:
        count = len(list((CACHE / d).glob("*.png")))
        print(f"  {d}: {count} icons cached")
    print(f"{'='*60}")


if __name__ == "__main__":
    asyncio.run(main())
