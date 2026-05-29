"""Pre-seed all 172 champions with class-appropriate item/augment stats.

Categorizes champions by DDragon tags (Mage, Marksman, Assassin, Fighter,
Tank, Support) and assigns appropriate item pools with realistic win-rate
distributions.

Run: python scripts/seed_all_champions.py
"""

import sqlite3
import random
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

os.environ.setdefault("XDG_DATA_HOME", os.path.expanduser("~/.local/share"))
os.environ.setdefault("XDG_CACHE_HOME", os.path.expanduser("~/.cache"))

from arena_buddy.config import get_db_path

random.seed(42)

# ============================================================================
# Item pools by class (item_id, base_win_rate)
# ============================================================================

AD_ITEMS = [  # Marksman / AD Assassin
    (6672, 0.562),   # Kraken Slayer
    (6675, 0.558),   # Navori Flickerblade
    (3031, 0.554),   # Infinity Edge
    (3072, 0.551),   # Bloodthirster
    (3036, 0.548),   # Lord Dominik's Regards
    (3026, 0.544),   # Guardian Angel
    (3153, 0.541),   # Blade of the Ruined King
    (3085, 0.538),   # Runaan's Hurricane
    (3139, 0.535),   # Mercurial Scimitar
    (3046, 0.532),   # Phantom Dancer
]

AP_ITEMS = [  # Mage
    (6655, 0.572),   # Luden's Companion
    (4645, 0.568),   # Shadowflame
    (3157, 0.565),   # Zhonya's Hourglass
    (3089, 0.561),   # Rabadon's Deathcap
    (3135, 0.558),   # Void Staff
    (6653, 0.554),   # Liandry's Torment
    (3116, 0.551),   # Rylai's Crystal Scepter
    (4628, 0.547),   # Cosmic Drive
    (4629, 0.544),   # Cryptbloom
    (3102, 0.540),   # Banshee's Veil
]

ASSASSIN_ITEMS = [  # Lethality
    (6692, 0.571),   # Eclipse
    (3142, 0.567),   # Youmuu's Ghostblade
    (6694, 0.564),   # Serylda's Grudge
    (3814, 0.560),   # Edge of Night
    (6699, 0.557),   # Profane Hydra
    (3179, 0.553),   # Umbral Glaive
    (6696, 0.550),   # Axiom Arc
    (6695, 0.546),   # Serpent's Fang
    (6693, 0.543),   # Opportunity
    (4005, 0.539),   # Voltaic Cyclosword
]

FIGHTER_ITEMS = [  # Bruiser
    (3078, 0.568),   # Trinity Force
    (3053, 0.565),   # Sterak's Gage
    (3071, 0.561),   # Black Cleaver
    (6610, 0.558),   # Sundered Sky
    (3748, 0.554),   # Titanic Hydra
    (3074, 0.551),   # Ravenous Hydra
    (6333, 0.547),   # Death's Dance
    (3156, 0.544),   # Maw of Malmortius
    (6630, 0.540),   # Shojin's Spear
    (3050, 0.537),   # Zeke's Convergence
]

TANK_ITEMS = [  # Tank
    (6662, 0.561),   # Iceborn Gauntlet
    (3075, 0.558),   # Thornmail
    (6665, 0.554),   # Jak'Sho
    (3143, 0.551),   # Randuin's Omen
    (3068, 0.548),   # Sunfire Aegis
    (3193, 0.544),   # Gargoyle Stoneplate
    (4401, 0.541),   # Force of Nature
    (3065, 0.538),   # Spirit Visage
    (3110, 0.534),   # Frozen Heart
    (2504, 0.531),   # Kaenic Rookern
]

SUPPORT_ITEMS = [  # Enchanter / Support
    (6617, 0.564),   # Moonstone Renewer
    (3504, 0.561),   # Ardent Censer
    (3508, 0.557),   # Staff of Flowing Water
    (3107, 0.554),   # Redemption
    (3222, 0.550),   # Mikael's Blessing
    (3190, 0.547),   # Locket of the Iron Solari
    (2065, 0.543),   # Shurelya's Battlesong
    (4005, 0.540),   # Imperial Mandate
    (3109, 0.536),   # Knight's Vow
    (4643, 0.533),   # Echoes of Helia
]

BOOTS = [(3006, 0.535), (3009, 0.532), (3020, 0.529), (3047, 0.526), (3111, 0.523), (3158, 0.520)]

PRISMATIC_ITEMS = [
    (447103, 0.671), (446632, 0.665), (223069, 0.662), (228006, 0.655),
    (447113, 0.651), (446656, 0.648), (447114, 0.642), (447121, 0.635),
]

AUGMENT_BASES = [
    (101, 2, 0.632, 0.124, 4200, 1), (102, 2, 0.618, 0.087, 3100, 2),
    (103, 2, 0.594, 0.101, 3600, 3), (201, 1, 0.584, 0.182, 6200, 1),
    (202, 1, 0.571, 0.143, 4900, 2), (203, 1, 0.563, 0.228, 7800, 3),
    (204, 1, 0.557, 0.165, 5600, 4), (301, 0, 0.532, 0.284, 9800, 1),
    (302, 0, 0.521, 0.192, 6600, 2), (303, 0, 0.508, 0.113, 3900, 3),
]

# ============================================================================
# Champion → class mapping (DDragon tags)
# ============================================================================

CHAMPION_CLASSES: dict[str, str] = {
    # The key is the DDragon "key" (e.g., "Aatrox")
    # Class determines item pool
}

# Populate by querying DDragon champion data
def _build_class_map(conn: sqlite3.Connection) -> dict[int, str]:
    """Determine class for each champion using their ID-based heuristics.

    Since we don't have tags in the SQLite DB, use well-known ID ranges
    and manual classification lists.
    """
    # Manual classification covering all 172 champions
    # Based on primary role in Arena mode
    marksman = {
        "Aphelios", "Ashe", "Caitlyn", "Corki", "Draven", "Ezreal",
        "Jhin", "Jinx", "Kai'Sa", "Kalista", "Kindred", "Kog'Maw",
        "Lucian", "Miss Fortune", "Nilah", "Samira", "Senna",
        "Sivir", "Smolder", "Tristana", "Twitch", "Varus", "Vayne",
        "Xayah", "Zeri", "Akshan",
    }
    mage = {
        "Ahri", "Anivia", "Annie", "Aurelion Sol", "Azir", "Brand",
        "Cassiopeia", "Fiddlesticks", "Heimerdinger", "Hwei",
        "Karthus", "LeBlanc", "Lillia", "Lissandra", "Lux", "Malzahar",
        "Neeko", "Orianna", "Ryze", "Seraphine", "Swain", "Sylas",
        "Syndra", "Taliyah", "Twisted Fate", "Veigar", "Vel'Koz",
        "Vex", "Viktor", "Vladimir", "Xerath", "Ziggs", "Zoe",
        "Zyra", "Karma", "Morgana", "Zilean",
    }
    assassin = {
        "Akali", "Evelynn", "Kassadin", "Katarina", "Kayn",
        "Kha'Zix", "Naafiri", "Nocturne", "Pyke", "Qiyana",
        "Rengar", "Shaco", "Talon", "Zed",
    }
    fighter = {
        "Aatrox", "Bel'Veth", "Briar", "Camille", "Darius", "Diana",
        "Dr. Mundo", "Ekko", "Elise", "Fiora", "Gangplank", "Garen",
        "Gnar", "Gwen", "Hecarim", "Illaoi", "Irelia", "Jarvan IV",
        "Jax", "Jayce", "Kayle", "Kled", "Lee Sin", "Master Yi",
        "Mordekaiser", "Nasus", "Nidalee", "Olaf", "Pantheon",
        "Renekton", "Riven", "Rumble", "Shyvana", "Sion",
        "Skarner", "Trundle", "Tryndamere", "Udyr", "Urgot",
        "Vi", "Viego", "Volibear", "Warwick", "Wukong",
        "Xin Zhao", "Yasuo", "Yone", "Yorick", "Graves",
        "Rek'Sai", "Sett", "Singed",
    }
    tank = {
        "Alistar", "Amumu", "Braum", "Cho'Gath", "Galio",
        "K'Sante", "Leona", "Malphite", "Maokai", "Nautilus",
        "Nunu & Willump", "Ornn", "Poppy", "Rammus", "Rell",
        "Sejuani", "Shen", "Tahm Kench", "Taric", "Thresh",
        "Zac",
    }
    support_enchanter = {
        "Bard", "Janna", "Lulu", "Milio", "Nami", "Rakan",
        "Renata Glasc", "Sona", "Soraka", "Yuumi",
    }

    # Overlap resolution: champions in multiple categories
    # Ekko → fighter (bruiser build in Arena), Kayle → fighter, etc.
    # Elise, Nidalee, Jayce → fighter (bruiser items in Arena)

    class_map: dict[int, str] = {}
    rows = conn.execute("SELECT id, key FROM champions").fetchall()
    for row in rows:
        cid = row["id"]
        key = row["key"]
        if key in marksman:
            class_map[cid] = "marksman"
        elif key in mage:
            class_map[cid] = "mage"
        elif key in assassin:
            class_map[cid] = "assassin"
        elif key in fighter:
            class_map[cid] = "fighter"
        elif key in tank:
            class_map[cid] = "tank"
        elif key in support_enchanter:
            class_map[cid] = "support"
        else:
            class_map[cid] = "fighter"  # default fallback

    return class_map


# ============================================================================
# Main
# ============================================================================

def main():
    db_path = get_db_path()
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")

    class_map = _build_class_map(conn)

    # Items by class
    ITEM_POOL = {
        "marksman": AD_ITEMS,
        "mage": AP_ITEMS,
        "assassin": ASSASSIN_ITEMS,
        "fighter": FIGHTER_ITEMS,
        "tank": TANK_ITEMS,
        "support": SUPPORT_ITEMS,
    }

    # Boots by class
    BOOTS_POOL = {
        "marksman": [(3006, 0.528), (3009, 0.525), (3047, 0.522)],   # Zerkers, Swifties, Tabis
        "mage": [(3020, 0.535), (3158, 0.531), (3111, 0.527)],       # Sorcs, Ionian, Mercs
        "assassin": [(3009, 0.541), (3158, 0.537), (3111, 0.533)],    # Swifties, Ionian, Mercs
        "fighter": [(3047, 0.538), (3111, 0.534), (3009, 0.530)],     # Tabis, Mercs, Swifties
        "tank": [(3047, 0.541), (3111, 0.537), (3009, 0.532)],        # Tabis, Mercs, Swifties
        "support": [(3158, 0.539), (3111, 0.535), (3009, 0.531)],     # Ionian, Mercs, Swifties
    }

    all_champs = conn.execute("SELECT id, key FROM champions").fetchall()

    inserted_items = 0
    inserted_augments = 0
    skipped = 0

    for row in all_champs:
        cid = row["id"]
        key = row["key"]
        cls = class_map.get(cid, "fighter")

        # Skip if already has stats
        existing = conn.execute(
            "SELECT COUNT(*) as cnt FROM global_item_stats WHERE champion_id = ?",
            (cid,),
        ).fetchone()["cnt"]
        if existing > 0:
            skipped += 1
            continue

        items = ITEM_POOL.get(cls, FIGHTER_ITEMS)
        boots = BOOTS_POOL.get(cls, BOOTS_POOL["fighter"])

        # Regular items + boots
        rank = 1
        for item_id, base_wr in items:
            wr = round(base_wr + random.uniform(-0.025, 0.025), 4)
            pr = round(random.uniform(0.08, 0.30), 4)
            games = int(random.uniform(3000, 12000))
            conn.execute(
                "INSERT OR IGNORE INTO global_item_stats "
                "(champion_id, item_id, patch_id, win_rate, pick_rate, games_played, rank) "
                "VALUES (?, ?, 1, ?, ?, ?, ?)",
                (cid, item_id, wr, pr, games, rank),
            )
            rank += 1
            inserted_items += 1

        # Boots
        for item_id, base_wr in boots:
            wr = round(base_wr + random.uniform(-0.02, 0.02), 4)
            pr = round(random.uniform(0.15, 0.55), 4)
            games = int(random.uniform(5000, 20000))
            conn.execute(
                "INSERT OR IGNORE INTO global_item_stats "
                "(champion_id, item_id, patch_id, win_rate, pick_rate, games_played, rank) "
                "VALUES (?, ?, 1, ?, ?, ?, ?)",
                (cid, item_id, wr, pr, games, rank),
            )
            rank += 1
            inserted_items += 1

        # Prismatic items
        rank = 1
        for item_id, base_wr in PRISMATIC_ITEMS:
            wr = round(base_wr + random.uniform(-0.025, 0.025), 4)
            pr = round(random.uniform(0.05, 0.20), 4)
            games = int(random.uniform(800, 4000))
            conn.execute(
                "INSERT OR IGNORE INTO global_item_stats "
                "(champion_id, item_id, patch_id, win_rate, pick_rate, games_played, rank) "
                "VALUES (?, ?, 1, ?, ?, ?, ?)",
                (cid, item_id, wr, pr, games, rank),
            )
            rank += 1
            inserted_items += 1

        # Augment stats
        for aug_id, rarity, base_wr, base_pr, base_games, arank in AUGMENT_BASES:
            wr = round(base_wr + random.uniform(-0.04, 0.04), 4)
            pr = round(base_pr + random.uniform(-0.03, 0.03), 4)
            games = int(base_games * random.uniform(0.7, 1.5))
            conn.execute(
                "INSERT OR IGNORE INTO global_augment_stats "
                "(champion_id, augment_id, patch_id, rarity, win_rate, pick_rate, games_played, rank) "
                "VALUES (?, ?, 1, ?, ?, ?, ?, ?)",
                (cid, aug_id, rarity, wr, pr, games, arank),
            )
            inserted_augments += 1

    conn.commit()

    # Stats
    total = conn.execute("SELECT COUNT(*) FROM champions").fetchone()[0]
    with_items = conn.execute(
        "SELECT COUNT(DISTINCT champion_id) FROM global_item_stats"
    ).fetchone()[0]
    with_augments = conn.execute(
        "SELECT COUNT(DISTINCT champion_id) FROM global_augment_stats"
    ).fetchone()[0]

    print(f"Champions: {total} total")
    print(f"  With item stats:  {with_items} (skipped {skipped} already-seeded)")
    print(f"  With augment stats: {with_augments}")
    print(f"  Item stat rows inserted: {inserted_items}")
    print(f"  Augment stat rows inserted: {inserted_augments}")

    conn.close()


if __name__ == "__main__":
    main()
