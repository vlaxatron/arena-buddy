# Arena Buddy

Free, open-source, locally-running companion app for League of Legends Arena mode.

Shows you the **best items and augments** for your champion, tracks your **personal match history**, and lets you see what works best *for you* — like Blitz.gg, but without ads, bugs, or phoning home.

## Features

- 🏆 Item & augment recommendations ranked by win rate
- 📋 Personal Arena match history (stored locally)
- 📊 Personal win rates alongside global stats
- 🖥️ Runs locally on your machine — no accounts, no telemetry
- 🌐 Offline mode after initial stat download
- 🎨 Dark League-themed UI

## Installation

```bash
pip install -e ".[dev]"
arena-buddy
```

## Development

```bash
source .venv/bin/activate
pytest tests/ -v
```

## License

MIT — see [LICENSE](LICENSE)
