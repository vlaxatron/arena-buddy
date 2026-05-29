# Arena Buddy

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/Python-3.11%2B-green.svg)](https://python.org)
[![Tests](https://img.shields.io/badge/tests-328%20passed-brightgreen.svg)](https://github.com/vlaxatron/arena-buddy/actions)

Free, open-source, locally-running companion app for **League of Legends Arena mode**.

Shows you the **best items and augments** for your champion, tracks your **personal match history**, and lets you see what works best *for you* — like Blitz.gg, but without ads, bugs, or phoning home.

---

## Features

- [x] 🏆 **Item & Augment Recommendations** — ranked by global win rate from LoLalytics
- [x] 📋 **Personal Match History** — auto-captured via LCU, stored locally
- [x] 📊 **Personal Stats** — your win rates alongside global stats
- [x] 🔍 **Champion Browser** — search across all 172 champions
- [x] 🔴 **Live Game Detection** — auto-switches to your current champion
- [x] ✨ **First-Run Wizard** — guided setup with League install detection
- [x] 🖥️ **Runs Locally** — no accounts, no telemetry, your data stays on your machine
- [x] 🌐 **Offline Mode** — works without internet after initial stat download
- [x] 🎨 **Dark League-Themed UI** — 3-pane layout with real champion/item/augment icons
- [ ] 🪟 **Windows .exe** — PyInstaller single-file binary (coming soon)

---

## Installation

### From Source (Development)

```bash
git clone https://github.com/vlaxatron/arena-buddy.git
cd arena-buddy
pip install -e ".[dev]"
arena-buddy
```

### Windows .exe (Coming Soon)

Download `ArenaBuddy.exe` from [Releases](https://github.com/vlaxatron/arena-buddy/releases).

---

## Screenshots

> Run the app and take screenshots using `scripts/screenshots.py`:
> ```bash
> python scripts/screenshots.py
> ```

| In-Game View | Browse Champions | Match History |
|---|---|---|
| *(screenshot)* | *(screenshot)* | *(screenshot)* |

---

## Development

```bash
# Activate virtual environment
source .venv/bin/activate  # Linux/macOS
# .venv\Scripts\activate   # Windows

# Run tests (328 tests, TDD)
pytest tests/ -q

# Run with coverage
pytest tests/ -q --cov=arena_buddy --cov-report=term-missing

# Build script
python scripts/build.py test    # Run tests
python scripts/build.py lint    # Lint with ruff
python scripts/build.py package # Build .exe (Windows only)
python scripts/build.py clean   # Remove build artifacts
```

### Project Structure

```
arena-buddy/
├── src/arena_buddy/
│   ├── core/           # Game detection, LCU, Riot API
│   │   ├── game_state.py
│   │   ├── league_detector.py
│   │   ├── match_capture.py
│   │   ├── match_capture_service.py
│   │   ├── orchestrator.py
│   │   └── riot_api.py
│   ├── db/             # Schema, queries, seed data, personal stats
│   │   ├── schema.py
│   │   ├── queries.py
│   │   ├── seed.py
│   │   ├── personal_stats.py
│   │   └── importer.py
│   ├── web/            # FastAPI backend + vanilla HTML/CSS/JS frontend
│   │   ├── app.py
│   │   ├── routes.py
│   │   ├── server.py
│   │   ├── websocket.py
│   │   └── static/
│   ├── scraper/        # LoLalytics data scraping
│   ├── assets/         # Icon downloader and cache
│   ├── config.py       # Cross-platform path resolution
│   └── main.py         # Entry point
├── tests/
│   ├── unit/           # 328 unit tests (TDD)
│   └── integration/
└── scripts/            # Build, screenshots, seed data
```

### Tech Stack

| Layer | Technology |
|---|---|
| Backend | Python 3.11+, FastAPI, uvicorn |
| Database | SQLite (local, zero-config) |
| Frontend | Vanilla HTML/CSS/JS (no frameworks) |
| Desktop | PyWebView (Windows) / browser fallback |
| Data | Data Dragon, CommunityDragon, LoLalytics |
| Tests | pytest (328 tests), pytest-cov, TDD |

---

## How It Works

1. **Start the app** — Arena Buddy opens a dark-themed window
2. **First-run wizard** — detects your League install and downloads initial data
3. **In-game detection** — polls the Live Client API every 2 seconds via WebSocket
4. **Champion recognition** — auto-switches to show your current champion's best items/augments
5. **Match capture** — when a game ends, pulls match data from the LCU and stores it locally
6. **Personal stats** — computes your win rates alongside global stats from LoLalytics

---

## License

MIT — see [LICENSE](LICENSE)
