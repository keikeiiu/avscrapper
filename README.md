# AV Scraper Tools

Auto-detect, scrape, enrich, and organize adult video files. Drop videos into a folder, run the pipeline, get Kodi-compliant NFO metadata and a clean folder hierarchy.

```
downloads/  →  ingest  →  processed/  →  scrape  →  enrich  →  reorganized/
                   (detect type,        (metadata     (NFO        (folder hierarchy
                    sort into folders)   to SQLite)    files)      from templates)
```

## Quick Start (Desktop App) ![Windows](https://img.shields.io/badge/Windows-0078D6?logo=windows&logoColor=white)

Download from [GitHub Releases](https://github.com/keikeiiu/avscrapper/releases/latest):

| File | What |
|------|------|
| `AVScraper-1.x.x-portable.zip` | Extract anywhere, double-click `AV Scraper.exe` |
| `AVScraper-Setup.exe` | Single-file self-extracting installer |

**No Docker, no terminal, no setup.** Launch and the web GUI opens in its own window. Everything (config, database, reports) lives in `%APPDATA%/avscrapper/`.

On first run, a config file is seeded automatically pointing to your Downloads folder. Edit cookies and paths via the built-in Config page.

See [desktop/README.md](desktop/README.md) for build instructions and architecture.

## Quick Start (Docker Compose)

```bash
# 1. Create docker-compose.yml (see below) and start
docker compose up -d

# 2. Open http://localhost:3721 — configure paths + cookies in the Config page

# 3. Drop videos into ./downloads, then use the Actions page or CLI
docker compose run avscraper python avscraper.py ingest --dry-run
```

## Quick Start (Local)

```bash
# 1. Install
pip install -r requirements.txt
playwright install chromium

# 2. Create config
cp config.example.yaml config.yaml   # edit paths + cookies

# 3. Run the pipeline
python avscraper.py ingest --source ./downloads
python avscraper.py scrape fc2ppvdb --delay "5-20"
python avscraper.py scrape javdb --delay "5-20"
python avscraper.py enrich fc2ppvdb
python avscraper.py enrich javdb
python avscraper.py reorganize --dry-run
python avscraper.py reorganize
```

## Docker Compose

```yaml
services:
  avscraper:
    image: keikeiiu/avscraper:latest
    container_name: avscraper
    ports:
      - "3721:3721"
    volumes:
      - ./appdata:/app/appdata         # config, DB, reports (required)
      - ./downloads:/app/downloads     # video source
      - ./processed:/app/processed     # ingest staging
      - ./reorganized:/app/reorganized # final destination
    environment:
      - AV_CONFIG=/app/appdata/config.yaml
    restart: unless-stopped
    stdin_open: true
    tty: true
```

- `./appdata` is the only required mount — holds config.yaml, av_data.db, and reports.
- Video mounts are flexible — mount as many or as few as you need, matching your config paths.
- On first run, config.yaml is auto-created from the example template.
- Edit paths and cookies via the Web UI Config page (or directly on the host at `./appdata/config.yaml`).

### CLI mode in Docker

```bash
docker compose run avscraper python avscraper.py ingest --dry-run
docker compose run avscraper python avscraper.py scrape fc2ppvdb --delay "5-20"
docker compose run avscraper python avscraper.py enrich fc2ppvdb
docker compose run avscraper python avscraper.py reorganize --dry-run
docker compose run avscraper python avscraper.py audit --dry-run
```

## Plain Docker (without Compose)

```bash
docker run --rm \
  -v ./appdata:/app/appdata \
  -v ./downloads:/app/downloads \
  -v ./processed:/app/processed \
  -v ./reorganized:/app/reorganized \
  -e AV_CONFIG=/app/appdata/config.yaml \
  keikeiiu/avscraper python avscraper.py ingest --dry-run
```

## Install (Local)

### macOS / Linux
```bash
pip3 install -r requirements.txt
playwright install chromium
```

### Windows
```bash
python -m pip install -r requirements.txt
python -m playwright install chromium
```

## Guides

| Guide | Content |
|-------|---------|
| [README.cli.md](README.cli.md) | CLI reference — all commands, flags, templates |
| [README.fc2ppv.md](README.fc2ppv.md) | FC2 scraper — implementation, config, cookies |
| [README.javdb.md](README.javdb.md) | JavDB scraper — implementation, config, cookies |
| [README.webgui.md](README.webgui.md) | Web GUI — dashboard, pipeline, actions, database, config editor |
| [desktop/README.md](desktop/README.md) | Desktop app — build, distribute, architecture |
| [PLAN.md](PLAN.md) | Architecture overview, status, future roadmap |

## Pipeline

Run all steps sequentially with one click — open `/pipeline` in the web GUI or use the CLI:

```bash
# Web GUI — one-click run-all with live flow visualization
open http://localhost:3721/pipeline

# Docker CLI — all steps sequentially
docker compose run avscraper python avscraper.py pipeline
```

| Step | Command | What it does |
|------|---------|--------------|
| Setup | `python avscraper.py setup` | Copy example config, check Playwright, create directories |
| Ingest | `python avscraper.py ingest` | Detect FC2/JAV by filename, move into folders, seed DB |
| Scrape | `python avscraper.py scrape <site>` | Fetch metadata from fc2ppvdb.com or javdb.com → SQLite |
| Enrich | `python avscraper.py enrich <site>` | Write Kodi-compliant NFO files alongside videos |
| Flag | `python avscraper.py flag <site> --ids ...` | Mark entries for re-scrape |
| Reorganize | `python avscraper.py reorganize` | Move folders into metadata-driven hierarchy |
| Audit | `python avscraper.py audit` | Compare metadata duration vs actual video duration |

## Sites

| Site | Status | Auth |
|------|--------|------|
| [fc2ppvdb.com](https://fc2ppvdb.com) | Production | Session cookies required |
| [javdb.com](https://javdb.com) | Production | `over18` cookie (public), `_jdb_session` (VIP) |

## Credits

| Library | Purpose | License |
|---------|---------|---------|
| [Playwright](https://playwright.dev) | Browser automation | Apache 2.0 |
| [Flask](https://flask.palletsprojects.com) | Web framework | BSD |
| [CodeMirror 5](https://codemirror.net/5/) | In-browser YAML editor | MIT |
| [Python-Markdown](https://python-markdown.github.io) | Report rendering | BSD |
| [PyYAML](https://pyyaml.org) | Config parsing | MIT |
| [Gunicorn](https://gunicorn.org) | WSGI server | MIT |
| [defusedxml](https://pypi.org/project/defusedxml/) | Safe XML parsing | PSF |
| [Electron](https://www.electronjs.org) | Desktop app shell | MIT |
| [electron-builder](https://www.electron.build) | Desktop packaging | MIT |
| [PyInstaller](https://pyinstaller.org) | Python-to-exe bundling | GPLv2+ (with bootloader exception — does not extend to bundled applications) |
| [Pillow](https://python-pillow.org) | Icon generation | MIT-CMU |
| [7-Zip](https://7-zip.org) | Self-extracting archive | LGPL |
