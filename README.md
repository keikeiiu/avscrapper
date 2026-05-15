# AV Scraper & NFO Enricher

Scrapes metadata → SQLite → Kodi-compliant NFO files.

## Quick Start (Docker)

```bash
cp config.example.yaml config.yaml   # then edit
docker compose up                    # auto-build + run
docker compose run scraper enrich javdb
docker compose run scraper reorganize --dry-run
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
python avscraper.py scrape <fc2ppvdb|javdb> [--ids ...]
python avscraper.py enrich <fc2ppvdb|javdb> [--ids ...]
python avscraper.py reorganize [--dry-run] [--report]
```

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
