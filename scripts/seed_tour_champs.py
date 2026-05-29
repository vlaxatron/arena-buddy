"""Quick seed for Twisted Fate, Zoe, Anivia — AP mage item/augment stats."""

import sqlite3, os, random, shutil, sys

os.environ['XDG_DATA_HOME'] = '/tmp/test_tour4'
os.environ['XDG_CACHE_HOME'] = '/tmp/test_tour_cache4'

sys.path.insert(0, '/opt/data/projects/arena-buddy/src')
from arena_buddy.config import get_db_path
from arena_buddy.db.connection import init_database
from arena_buddy.db.seed import seed_all

db_path = get_db_path()
if db_path.exists():
    db_path.unlink()
init_database(db_path)
conn = sqlite3.connect(str(db_path))
conn.execute('PRAGMA foreign_keys = ON')
seed_all(conn)

random.seed(42)

AP_ITEMS = [
    (6655, 0.572), (4645, 0.561), (3157, 0.558), (3089, 0.554),
    (3135, 0.551), (4629, 0.547), (6653, 0.543), (3102, 0.538),
    (3020, 0.535), (3158, 0.531),
]

AP_PRIS_ITEMS = [
    (446656, 0.672), (447113, 0.668), (447103, 0.664), (447114, 0.658),
    (228006, 0.652), (447121, 0.648), (223069, 0.643), (446632, 0.637),
]

AUG_BASES = [
    (101, 2, 0.598, 0.089, 3100, 1), (102, 2, 0.615, 0.104, 3500, 2),
    (103, 2, 0.587, 0.095, 3400, 3), (201, 1, 0.576, 0.168, 5800, 1),
    (202, 1, 0.559, 0.132, 4400, 2), (203, 1, 0.572, 0.204, 7200, 3),
    (204, 1, 0.562, 0.155, 5200, 4), (301, 0, 0.528, 0.244, 8500, 1),
    (302, 0, 0.515, 0.182, 6200, 2), (303, 0, 0.511, 0.108, 3600, 3),
]

CHAMPIONS = {4: 'TwistedFate', 142: 'Zoe', 34: 'Anivia'}

for cid, name in CHAMPIONS.items():
    rank = 1
    for item_id, base_wr in AP_ITEMS:
        wr = base_wr + random.uniform(-0.025, 0.025)
        pr = random.uniform(0.08, 0.30)
        games = int(random.uniform(3000, 12000))
        conn.execute(
            'INSERT OR IGNORE INTO global_item_stats '
            '(champion_id, item_id, patch_id, win_rate, pick_rate, games_played, rank) '
            'VALUES (?, ?, 1, ?, ?, ?, ?)',
            (cid, item_id, round(wr, 4), round(pr, 4), games, rank),
        )
        rank += 1

    rank = 1
    for item_id, base_wr in AP_PRIS_ITEMS:
        wr = base_wr + random.uniform(-0.025, 0.025)
        pr = random.uniform(0.05, 0.18)
        games = int(random.uniform(800, 3500))
        conn.execute(
            'INSERT OR IGNORE INTO global_item_stats '
            '(champion_id, item_id, patch_id, win_rate, pick_rate, games_played, rank) '
            'VALUES (?, ?, 1, ?, ?, ?, ?)',
            (cid, item_id, round(wr, 4), round(pr, 4), games, rank),
        )
        rank += 1

    for aug_id, rarity, base_wr, base_pr, base_games, rank in AUG_BASES:
        wr = base_wr + random.uniform(-0.03, 0.03)
        pr = base_pr + random.uniform(-0.02, 0.02)
        games = int(base_games * random.uniform(0.7, 1.3))
        conn.execute(
            'INSERT OR IGNORE INTO global_augment_stats '
            '(champion_id, augment_id, patch_id, rarity, win_rate, pick_rate, games_played, rank) '
            'VALUES (?, ?, 1, ?, ?, ?, ?, ?)',
            (cid, aug_id, rarity, round(wr, 4), round(pr, 4), games, rank),
        )

conn.commit()

for name in ['Twisted Fate', 'Zoe', 'Anivia']:
    row = conn.execute('SELECT id FROM champions WHERE name = ?', (name,)).fetchone()
    cid = row['id']
    ic = conn.execute('SELECT COUNT(*) as cnt FROM global_item_stats WHERE champion_id = ?', (cid,)).fetchone()
    ac = conn.execute('SELECT COUNT(*) as cnt FROM global_augment_stats WHERE champion_id = ?', (cid,)).fetchone()
    print(f'{name} (id={cid}): {ic["cnt"]} item stats, {ac["cnt"]} augment stats')

conn.close()
shutil.rmtree('/tmp/test_tour4', ignore_errors=True)
shutil.rmtree('/tmp/test_tour_cache4', ignore_errors=True)
