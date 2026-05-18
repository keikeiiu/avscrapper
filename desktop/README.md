# AV Scraper Desktop

Standalone desktop app for Windows. No Docker, no terminal, no setup — double-click and go.

## Download

Get the latest `avscrapper-portable.exe` from [GitHub Releases](https://github.com/keikeiiu/avscrapper/releases).

## How it works

```
avscrapper.exe
├── Electron shell           ← native window, system tray
├── Python backend (frozen)  ← Flask web server, auto-started
└── Playwright Chromium      ← bundled for scraping
```

On launch:
1. Electron starts the Python backend on a random localhost port
2. Backend seeds a fresh `config.yaml` in `%APPDATA%/avscraper/` on first run
3. Electron opens the Web GUI in a native window
4. Closing the window stops the backend and exits

## AppData

Everything is stored per-user:

| OS | Location |
|---|---|
| Windows | `%APPDATA%/avscraper/` |
| macOS | `~/Library/Application Support/avscraper/` |

Contents:
- `config.yaml` — your paths, cookies, settings
- `av_data.db` — SQLite database of scraped metadata
- `reports/` — audit and ingest reports

## Build from source

```bash
# Prerequisites
pip install -r requirements.txt pyinstaller pillow
playwright install --with-deps chromium
npm --prefix desktop install

# Build
cd desktop
python build.py
```

This runs PyInstaller (freeze Python backend) then electron-builder (package into portable .exe).

Output: `desktop/output/avscrapper-1.0.1-Portable.exe`

## Architecture

```
desktop/
├── package.json          # Electron + electron-builder config
├── main.js               # Electron main process — spawns backend, opens window
├── preload.js            # Safe IPC bridge for renderer
├── build.py              # Full build orchestration
├── icons/                # App icons (icon.png, icon.ico)
├── python-dist/          # PyInstaller output (gitignored)
├── output/               # Electron-builder output (gitignored)
└── README.md
```

## vs Docker / NAS

| | Desktop | Docker |
|---|---|---|
| Setup | Download .exe, run | `docker compose up` |
| Web GUI | Native window | Browser at `http://nas-ip:3721` |
| Config | `%APPDATA%/avscraper/` | `./appdata/` mount |
| Scraping | Bundled Chromium | Docker Chromium |
| Multi-device | ❌ local only | ✅ network access |
| Distribution | .exe download | Docker Hub pull |

Both share the same codebase (`src/`, `web/`). Desktop adds Electron as a window shell; Docker adds container orchestration. All scraper logic is identical.
