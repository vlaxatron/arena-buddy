# Arena Buddy — Implementation Plan

> **For Hermes:** Use `subagent-driven-development` skill to implement this plan task-by-task with strict TDD (test-driven-development skill). Each task = one RED-GREEN-REFACTOR cycle.

**Goal:** Build Arena Buddy — a free, open-source, locally-running desktop app for LoL Arena mode showing item/augment recommendations with personal match history.

**Architecture:** Python FastAPI backend + vanilla HTML/CSS/JS frontend served via WebView2 (Windows) / browser (Linux dev). SQLite for all data. Rust core for LCU polling (Phase 2). LoLalytics scraping (Phase 3).

**Tech Stack:** Python 3.11+, FastAPI, uvicorn, SQLite (sqlite3), httpx, beautifulsoup4, pywebview, vanilla HTML/CSS/JS (no frameworks).

**Test Framework:** pytest with pytest-cov. TDD enforced: no production code without a failing test first.

**Repo:** `/opt/data/projects/arena-buddy` (local-only, git-tracked)

**Conventions:**
- Branch: `main`
- Python package: `arena_buddy` (src layout: `src/arena_buddy/`)
- Tests: `tests/` mirroring `src/arena_buddy/`
- Database: SQLite at `~/.local/share/arena-buddy/arena_buddy.db` (Linux) / `%APPDATA%/ArenaBuddy/` (Windows)
- Icons cache: `~/.cache/arena-buddy/` (Linux) / `%APPDATA%/ArenaBuddy/cache/` (Windows)
- Config: `~/.config/arena-buddy/settings.json` (Linux) / `%APPDATA%/ArenaBuddy/config/settings.json` (Windows)

---

## Phase 1: MVP — "Lucian on Screen" (Cross-Platform)

**Goal:** Open a dark-themed window showing Lucian's best Arena items and augments with global win rates, using hardcoded seed data.

### Task 1.1: Project Scaffold & Dependencies
**Objective:** Set up pyproject.toml, virtual env, and project metadata.

**Files:**
- Create: `pyproject.toml`
- Create: `src/arena_buddy/__init__.py`
- Create: `tests/__init__.py`
- Create: `tests/conftest.py`

**Implementation:**
- `pyproject.toml` with setuptools, Python >= 3.11
- Dependencies: fastapi, uvicorn[standard], httpx (Phase 3), beautifulsoup4 (Phase 3), apscheduler (Phase 3), pywebview (Phase 1)
- Dev dependencies: pytest, pytest-cov, pytest-asyncio, httpx (for TestClient)
- Add `[project.scripts]` entry point: `arena-buddy = "arena_buddy.main:main"`
- Create empty `__init__.py` files
- `conftest.py` with fixtures: temp DB path, test FastAPI app

**Test:** `pytest tests/ -v` — should pass with 0 tests (confirm env works)

**Commit:** `git add -A && git commit -m "chore: project scaffold with pyproject.toml and test infrastructure"`

---

### Task 1.2: Config / Paths Module
**Objective:** Cross-platform app data directory resolution.

**Files:**
- Create: `src/arena_buddy/config.py`
- Create: `tests/unit/test_config.py`

**Spec:**
```python
# src/arena_buddy/config.py
import os, sys, json, platform
from pathlib import Path

def get_app_dir() -> Path:
    """Return the platform-appropriate app data directory."""
    ...

def get_db_path() -> Path:
    """Return path to SQLite database."""
    ...

def get_cache_dir() -> Path:
    """Return icon cache directory."""
    ...

def get_config_path() -> Path:
    """Return settings.json path."""
    ...

def load_settings() -> dict:
    """Load settings.json, return defaults if not found."""
    ...

def save_settings(settings: dict) -> None:
    """Save settings.json."""
    ...
```

**TDD Cycle:**
1. `test_default_app_dir_linux` — on Linux, returns `~/.local/share/arena-buddy`
2. `test_default_app_dir_windows` — on Windows, returns `%APPDATA%/ArenaBuddy`
3. `test_db_path_returns_sqlite_file`
4. `test_cache_dir_returns_cache_subdir`
5. `test_load_settings_returns_defaults_when_no_file`
6. `test_save_and_load_settings_roundtrip`

**Commit:** `git commit -m "feat: cross-platform config and path resolution"`

---

### Task 1.3: Database Schema & Connection
**Objective:** SQLite schema creation and connection management.

**Files:**
- Create: `src/arena_buddy/db/__init__.py`
- Create: `src/arena_buddy/db/schema.py`
- Create: `src/arena_buddy/db/connection.py`
- Create: `tests/unit/test_db_schema.py`
- Create: `tests/unit/test_db_connection.py`

**Tables (Phase 1):**
- `champions` — id, key, name, icon_filename
- `items` — id, name, icon_filename, gold_cost, description
- `augments` — id, api_name, name, rarity, description, icon_filename
- `patches` — id, version, scraped_at, is_current
- `global_item_stats` — champion_id, item_id, patch_id, win_rate, pick_rate, games_played, rank
- `global_augment_stats` — champion_id, augment_id, patch_id, rarity, win_rate, pick_rate, games_played, rank

**TDD Cycle:**
1. `test_create_tables_creates_all_expected_tables` — verify table existence
2. `test_insert_and_query_champion` — roundtrip CRUD
3. `test_insert_and_query_item`
4. `test_insert_and_query_augment`
5. `test_global_item_stats_composite_pk`
6. `test_connection_context_manager_closes`
7. `test_get_db_uses_configured_path`

**Commit:** `git commit -m "feat: SQLite database schema and connection management"`

---

### Task 1.4: Seed Data — Lucian + Items + Augments
**Objective:** Hardcoded seed data for Lucian Arena stats to power the MVP UI.

**Files:**
- Create: `src/arena_buddy/db/seed.py`
- Create: `tests/unit/test_seed.py`

**Data (from PRD wireframe / real LoLalytics):**
- Champion: Lucian (id=236, key="Lucian")
- Items (top 8, sorted by WR):
  | Item | Win Rate | Pick Rate | Games |
  |------|----------|-----------|-------|
  | Kraken Slayer | 56.2% | 38.4% | 12400 |
  | Navori Flickerblade | 55.8% | 42.1% | 13600 |
  | Infinity Edge | 54.9% | 28.9% | 9300 |
  | Bloodthirster | 54.1% | 22.3% | 7200 |
  | Lord Dominik's Regards | 53.7% | 18.5% | 6000 |
  | Guardian Angel | 53.2% | 15.8% | 5100 |
  | Berserker's Greaves | 52.8% | 65.2% | 21000 |
  | Mercurial Scimitar | 51.5% | 8.4% | 2700 |

- Augments (grouped by rarity, sorted by WR):
  **Prismatic:**
  | Augment | Win Rate | Pick Rate | Games |
  |---------|----------|-----------|-------|
  | Back To Basics | 63.2% | 12.4% | 4200 |
  | Blade Waltz | 61.8% | 8.7% | 3100 |
  | Symphony of War | 59.4% | 10.1% | 3600 |

  **Gold:**
  | Augment | Win Rate | Pick Rate | Games |
  |---------|----------|-----------|-------|
  | ADAPt | 58.4% | 18.2% | 6200 |
  | Buff Buddies | 57.1% | 14.3% | 4900 |
  | Bread And Butter | 56.3% | 22.8% | 7800 |
  | Vulnerability | 55.7% | 16.5% | 5600 |

  **Silver:**
  | Augment | Win Rate | Pick Rate | Games |
  |---------|----------|-----------|-------|
  | Stats! | 53.2% | 28.4% | 9800 |
  | Warmup Routine | 52.1% | 19.2% | 6600 |
  | Tank It Or Leave It | 50.8% | 11.3% | 3900 |

**TDD Cycle:**
1. `test_seed_creates_lucian_champion` — verify Lucian row exists
2. `test_seed_creates_all_8_items` — verify all 8 items inserted
3. `test_seed_creates_all_10_augments` — verify all augments inserted
4. `test_seed_global_item_stats_have_correct_win_rates`
5. `test_seed_is_idempotent` — running twice doesn't duplicate
6. `test_seed_creates_patch_record`

**Commit:** `git commit -m "feat: Lucian Arena seed data with items and augments"`

---

### Task 1.5: Data Access Layer — Queries
**Objective:** Query functions to retrieve item/augment recommendations for a champion.

**Files:**
- Create: `src/arena_buddy/db/queries.py`
- Create: `tests/unit/test_queries.py`

**Functions:**
```python
def get_champion_by_key(db, key: str) -> dict | None
def get_items_for_champion(db, champion_id: int, patch_id: int) -> list[dict]
def get_augments_for_champion(db, champion_id: int, patch_id: int) -> list[dict]
def get_current_patch(db) -> dict | None
def get_all_champions(db) -> list[dict]
```

**TDD Cycle:**
1. `test_get_champion_by_key_returns_lucian`
2. `test_get_champion_by_key_returns_none_for_unknown`
3. `test_get_items_for_champion_returns_sorted_by_win_rate`
4. `test_get_items_limited_to_top_8`
5. `test_get_augments_grouped_by_rarity_then_win_rate`
6. `test_get_current_patch_returns_seeded_patch`
7. `test_get_all_champions_returns_all`

**Commit:** `git commit -m "feat: data access layer for champion item/augment queries"`

---

### Task 1.6: FastAPI Web Server — API Endpoints
**Objective:** REST API serving champion recommendations.

**Files:**
- Create: `src/arena_buddy/web/__init__.py`
- Create: `src/arena_buddy/web/app.py`
- Create: `src/arena_buddy/web/routes.py`
- Create: `tests/unit/test_api.py`

**Endpoints:**
| Method | Path | Response |
|--------|------|----------|
| GET | `/api/health` | `{"status": "ok", "version": "0.1.0"}` |
| GET | `/api/champions` | `[{"id": 236, "key": "Lucian", "name": "Lucian"}, ...]` |
| GET | `/api/champions/{key}/items` | `{"champion": {...}, "patch": "16.11", "items": [...], "augments": [...]}` |
| GET | `/api/champions/{key}/augments` | Same structure as above (or combined endpoint) |
| GET | `/api/stats/summary` | `{"patch": "16.11", "last_updated": "2026-05-28", "champions_covered": 1}` |

**Response shapes (from wireframe):**
```json
{
  "champion": {"id": 236, "key": "Lucian", "name": "Lucian"},
  "patch": "16.11",
  "last_updated": "2026-05-28T12:00:00",
  "items": [
    {
      "id": 6672, "name": "Kraken Slayer",
      "global_win_rate": 0.562, "global_pick_rate": 0.384,
      "global_games": 12400, "rank": 1,
      "personal_win_rate": null, "personal_games": 0
    }
  ],
  "augments": {
    "prismatic": [{"id": 1, "name": "Back To Basics", "global_win_rate": 0.632, ...}],
    "gold": [...],
    "silver": [...]
  }
}
```

**TDD Cycle:**
1. `test_health_endpoint_returns_ok` — FastAPI TestClient
2. `test_champions_endpoint_returns_lucian`
3. `test_items_endpoint_returns_sorted_items`
4. `test_items_endpoint_returns_404_for_unknown_champion`
5. `test_augments_endpoint_returns_grouped_by_rarity`
6. `test_stats_summary_has_patch_info`

**Commit:** `git commit -m "feat: FastAPI REST API for champion recommendations"`

---

### Task 1.7: Frontend — HTML Structure & CSS
**Objective:** Dark-themed League-style UI with tab navigation.

**Files:**
- Create: `src/arena_buddy/web/static/index.html`
- Create: `src/arena_buddy/web/static/css/style.css`
- Create: `src/arena_buddy/web/static/js/app.js`

**HTML Structure:**
```html
- Title bar (Arena Buddy, window controls placeholder)
- Tab bar: [▶ In Game] [📋 History] [🔍 Browse] [⚙ Settings]
- Content area (switched by tab)
  - In-Game tab:
    - Top: champion name + status indicator
    - Two columns:
      - Left: "BEST ITEMS" list with icon, name, global WR, personal WR
      - Right: "AUGMENTS" grouped by tier (Prismatic > Gold > Silver)
    - Footer: stats freshness bar
```

**CSS variables (dark theme):**
```css
:root {
  --bg-primary: #0a0a0f;
  --bg-secondary: #141422;
  --bg-card: #1a1a2e;
  --text-primary: #e0e0e0;
  --text-secondary: #8888aa;
  --accent-prismatic: #a855f7;
  --accent-gold: #f59e0b;
  --accent-silver: #94a3b8;
  --accent-personal: #22d3ee;  /* teal/cyan */
  --win-high: #22c55e;
  --win-mid: #eab308;
  --win-low: #ef4444;
  --placement-1st: #ffd700;
  --placement-2nd: #c0c0c0;
  --placement-3rd: #cd7f32;
  --placement-4th: #6b7280;
}
```

**TDD + Visual verification:**
- No pytest for CSS/HTML (visual), but verify:
  - Page loads without errors in browser
  - All 4 tabs render
  - Dark theme colors match spec

**Commit:** `git commit -m "feat: dark-themed HTML/CSS shell with tab navigation"`

---

### Task 1.8: Frontend — JavaScript API Client & Dynamic Rendering
**Objective:** JS fetches API data and renders item/augment lists with stats.

**Files:**
- Modify: `src/arena_buddy/web/static/js/app.js`

**Functions:**
```javascript
async function fetchChampionData(championKey) → renders items + augments
async function fetchChampions() → populates champion selector
function renderItems(items) → creates item cards with WR bars
function renderAugments(augmentsByTier) → creates augment cards grouped by tier
function formatWinRate(wr) → "56.2% WR" with color class
function formatPersonalStat(wr, games) → "You: 60.0% (3/5)" in teal
```

**TDD (frontend tests, lightweight):**
- `test_format_win_rate_0_562` → `{text: "56.2%", class: "win-high"}`
- `test_format_win_rate_0_480` → `{text: "48.0%", class: "win-mid"}`
- `test_format_win_rate_0_350` → `{text: "35.0%", class: "win-low"}`
- `test_format_personal_stat_with_games` → `"You: 60.0% (3/5)"`
- `test_format_personal_stat_no_games` → `"You: — (0 games)"`

**Commit:** `git commit -m "feat: JS rendering engine with win-rate formatting"`

---

### Task 1.9: Static File Serving — FastAPI Integration
**Objective:** FastAPI serves the static HTML/CSS/JS and frontend loads data from API.

**Files:**
- Modify: `src/arena_buddy/web/app.py` — add StaticFiles mount and index route
- Modify: `src/arena_buddy/web/routes.py` — add frontend serve route

**Integration test:**
1. `test_index_page_loads_html` — GET `/` returns 200 with HTML
2. `test_static_css_served` — GET `/static/css/style.css` returns CSS
3. `test_static_js_served` — GET `/static/js/app.js` returns JS
4. `test_full_flow` — GET `/api/champions/Lucian/items` → returns valid data rendered by frontend

**Commit:** `git commit -m "feat: static file serving and frontend-backend integration"`

---

### Task 1.10: Desktop Window — PyWebView (Linux Dev Mode)
**Objective:** Wrap the web app in a desktop window. Linux fallback: open browser.

**Files:**
- Create: `src/arena_buddy/main.py` — entry point
- Create: `src/arena_buddy/web/server.py` — uvicorn launcher
- Create: `tests/integration/test_desktop.py`

**Logic:**
```python
def main():
    # 1. Initialize DB, run seed if needed
    # 2. Start FastAPI in a thread
    # 3. On Windows: create pywebview window pointing to localhost:PORT
    # 4. On Linux (dev): open browser or print URL
```

**TDD:**
1. `test_main_initializes_db_and_seeds` — mock to verify flow
2. `test_server_starts_on_configured_port`
3. `test_pywebview_import_or_fallback` — graceful on Linux without WebView2

**Commit:** `git commit -m "feat: desktop window wrapper with Linux browser fallback"`

---

### Task 1.11: Window Position Memory & Config Persistence
**Objective:** Save/restore window size and position.

**Files:**
- Modify: `src/arena_buddy/config.py` — add window geometry
- Modify: `src/arena_buddy/main.py` — load/save geometry on start/close

**TDD:**
1. `test_default_window_geometry` — 1024x768 default
2. `test_save_and_restore_window_geometry`
3. `test_settings_persist_across_restarts`

**Commit:** `git commit -m "feat: window position memory and config persistence"`

---

### Task 1.12: Integration Test — Full MVP Flow
**Objective:** End-to-end test: seed → API → frontend → window.

**Test:** Start server, query endpoint, verify full response matches seed data.

**Commit:** `git commit -m "test: end-to-end integration test for Phase 1 MVP"`

---

## Phase 2: Live Game Detection + LCU Integration

**Prerequisite:** Windows machine (or mock LCU responses for testing on Linux).

### Task 2.1: LCU Connection Module (Python Fallback)
**Files:**
- Create: `src/arena_buddy/core/__init__.py`
- Create: `src/arena_buddy/core/lcu.py`
- Create: `tests/unit/test_lcu.py`

**Functions:**
```python
def find_lockfile() -> Path | None  # search known locations
def parse_lockfile(path: Path) -> dict  # extract port, password
def create_lcu_client(port: int, password: str) -> httpx.AsyncClient
```

**TDD with mocked lockfile:**
1. `test_find_lockfile_at_default_path`
2. `test_parse_lockfile_extracts_port_and_password`
3. `test_lcu_client_uses_basic_auth`
4. `test_lcu_client_bypasses_ssl`

### Task 2.2: Game State Poller (Live Client :2999)
**Files:**
- Create: `src/arena_buddy/core/game_state.py`
- Create: `tests/unit/test_game_state.py`

**Polls `localhost:2999/liveclientdata/allgamedata` every 2s**

### Task 2.3: Match History Capture
**Files:**
- Create: `src/arena_buddy/core/match_capture.py`

### Task 2.4: Personal Stats Computation
**Files:**
- Create: `src/arena_buddy/db/personal_stats.py`

---

## Phase 3: Full Champion Coverage + Scraper

### Task 3.1: CommunityDragon Augment Sync
### Task 3.2: Data Dragon Champion/Item Sync
### Task 3.3: LoLalytics Scraper
### Task 3.4: Champion Selector UI
### Task 3.5: Match History Browser UI
### Task 3.6: Patch Detection & Auto-Refresh

---

## Phase 4: Polish & Distribution

### Task 4.1: PyInstaller Packaging
### Task 4.2: Auto-Detect League Install
### Task 4.3: First-Run Wizard
### Task 4.4: README & Screenshots

---

## Phase 5: Self-Computed Stats (Future)

### Task 5.1: Riot API Integration
### Task 5.2: Aggregate Stats Computation

---

*Implementation begins: Phase 1 MVP — target: 1-2 working sessions.*
