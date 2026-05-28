"""LoLalytics Arena scraper package."""

from arena_buddy.scraper.lolalytics import (
    AugmentStat,
    ItemStat,
    RateLimiter,
    ScrapeResult,
    champion_name_to_url_key,
    parse_games,
    parse_pick_rate,
    parse_win_rate,
    scrape_all_champions,
    scrape_champion,
    store_champion_stats,
)

__all__ = [
    "AugmentStat",
    "ItemStat",
    "RateLimiter",
    "ScrapeResult",
    "champion_name_to_url_key",
    "parse_games",
    "parse_pick_rate",
    "parse_win_rate",
    "scrape_all_champions",
    "scrape_champion",
    "store_champion_stats",
]
