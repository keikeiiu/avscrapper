# AV Scraper & NFO Enricher

Scrapes metadata → SQLite → Kodi-compliant NFO files.

## Quick Start (Docker)

See [README.docker.md](README.docker.md) for full guide.

```bash
cp config.example.yaml config.yaml   # then edit
docker compose run avscraper ingest --dry-run
```

## Quick Start (Local)

```bash
# 1. Create config
cp config.example.yaml config.yaml

# 2. Install
pip install -r requirements.txt
playwright install chromium

# 3. Drop downloaded videos into ./downloads/
# 4. Run the pipeline
python avscraper.py ingest --source ./downloads
python avscraper.py scrape fc2ppvdb
python avscraper.py scrape javdb
python avscraper.py enrich fc2ppvdb
python avscraper.py enrich javdb
python avscraper.py reorganize --dry-run
python avscraper.py reorganize
```

## Install

### Windows
```bash
python -m pip install -r requirements.txt
python -m playwright install chromium
```

### macOS
```bash
pip3 install -r requirements.txt
playwright install chromium
```

### Docker
```bash
docker build -t avscraper .
docker run -v ./downloads:/app/downloads -v ./processed:/app/processed -v ./config.yaml:/app/config.yaml avscraper ingest --source /app/downloads
```

## Entry Point

```bash
python avscraper.py ingest [--source ./downloads] [--dry-run]
python avscraper.py scrape <fc2ppvdb|javdb> [--ids ...] [--flagged] [--retry-errors]
python avscraper.py enrich <fc2ppvdb|javdb> [--ids ...]
python avscraper.py flag <fc2ppvdb|javdb> --ids <cids>
python avscraper.py reorganize [--dry-run] [--report]
```

### NFO-First Import

During `scrape`, the tool checks if a `.nfo` file already exists in the video's folder. If found, metadata is imported from the NFO directly — no web request is made. This avoids unnecessary scraping for videos that already have metadata.

### Re-Scrape Flagging

Mark entries for re-scraping when metadata appears wrong or incomplete:

```bash
# Flag specific entries
python avscraper.py flag fc2ppvdb --ids 123456,789012
python avscraper.py flag javdb --ids SSIS-123

# Re-scrape flagged entries
python avscraper.py scrape fc2ppvdb --flagged
python avscraper.py scrape javdb --flagged --delay "5-20"
```

`--retry-errors` also picks up flagged entries alongside errors and 404s.

## Sites

| Site | Guide |
|------|-------|
| fc2ppvdb.com | [README.fc2ppv.md](README.fc2ppv.md) |
| javdb.com | [README.javdb.md](README.javdb.md) |

## Reorganizer

Metadata-driven folder hierarchy via configurable templates. See [README.reorganize.md](README.reorganize.md).

```bash
python avscraper.py reorganize --dry-run
python avscraper.py reorganize --report
```

## Config

Copy `config.example.yaml` → `config.yaml` and set your paths + cookies. All paths are relative to the config file. See [README.reorganize.md](README.reorganize.md) for structure templates and studio/series maps.

## DB Stats

```bash
python -c "from src.db import connect,get_stats; c=connect('av_data.db'); [print(f'{r[\"source\"]:12} {r[\"status\"]:10} {r[\"count\"]}') for r in get_stats(c)]"
```

## Web GUI

A browser-based interface for managing the full pipeline — trigger actions, watch live logs, browse the database.

```bash
# Install web dependencies
pip install flask gunicorn

# Start (development)
python -m web.app

# Open http://localhost:5000
```

**Pages:**
- **Dashboard** — stat cards, quick actions, live output
- **Actions** — trigger any pipeline step with parameters, stream live output via SSE
- **Database** — browse FC2/JAV entries with filters, search, sort, expand rows, flag entries
- **Logs** — view report files and live session output

**Docker:** The Docker image starts the web GUI by default on port 5000. CLI access is still available via `docker compose run avscraper python avscraper.py ...`. See [README.docker.md](README.docker.md).

## Credits

Built with these open source libraries:

| Library | Purpose | License |
|---------|---------|---------|
| [Playwright](https://playwright.dev) | Browser automation for scraping | Apache 2.0 |
| [Flask](https://flask.palletsprojects.com) | Web framework | BSD |
| [CodeMirror 5](https://codemirror.net/5/) | In-browser YAML editor | MIT |
| [Python-Markdown](https://python-markdown.github.io) | Markdown rendering for reports | BSD |
| [PyYAML](https://pyyaml.org) | YAML config parsing | MIT |
| [Gunicorn](https://gunicorn.org) | WSGI server (production) | MIT |
