# AV Scraper — Docker Guide

Zero-install. Works on Windows, Mac, Linux. Just need Docker Desktop.

## 1. Create Your docker-compose.yml

```yaml
services:
  avscraper:
    image: keikeiiu/avscraper:latest
    container_name: avscraper
    ports:
      - "5000:5000"
    volumes:
      - ./downloads:/app/downloads
      - ./processed:/app/processed
      - ./reorganized:/app/reorganized
      - ./config.yaml:/app/config.yaml:ro
      - av_data:/app

volumes:
  av_data:
```

## 2. Create config.yaml

```bash
curl -O https://raw.githubusercontent.com/keikeiiu/media-stack-docker-compose/main/avscrappertools/config.example.yaml
mv config.example.yaml config.yaml
```

Edit `config.yaml` — set your cookie values. Paths can stay relative (they work inside Docker).

```
sites:
  fc2ppvdb:
    cookies:
      age_pass: "your_cookie_here"
      ...
  javdb:
    cookies:
      over18: "1"
      _jdb_session: "your_cookie_here"
```

## 3. Run

### Web GUI (recommended)

```bash
# Start the web GUI (default)
docker compose up -d

# Open http://localhost:5000 in your browser
# For NAS: http://<nas-ip>:5000
```

The web GUI lets you trigger all actions, watch live logs, and browse the database.

### CLI mode

```bash
# Drop videos into ./downloads/
docker compose run avscraper python avscraper.py ingest --dry-run
docker compose run avscraper python avscraper.py ingest

# Scrape metadata
docker compose run avscraper python avscraper.py scrape fc2ppvdb --delay "5-20"
docker compose run avscraper python avscraper.py scrape javdb --delay "5-20"

# Re-scrape flagged entries
docker compose run avscraper python avscraper.py flag fc2ppvdb --ids 123456,789012
docker compose run avscraper python avscraper.py scrape fc2ppvdb --flagged

# Write NFO files
docker compose run avscraper python avscraper.py enrich fc2ppvdb
docker compose run avscraper python avscraper.py enrich javdb

# Reorganize into hierarchy
docker compose run avscraper python avscraper.py reorganize --dry-run
docker compose run avscraper python avscraper.py reorganize
```

## Without Compose (plain Docker)

```bash
docker run --rm \
  -v ./downloads:/app/downloads \
  -v ./processed:/app/processed \
  -v ./config.yaml:/app/config.yaml:ro \
  -v av_data:/app \
  keikeiiu/avscraper ingest --dry-run
```

Same commands work — just replace `docker compose run avscraper` with the `docker run` line above.

## Tips

- All data lives in Docker volumes + your mounted folders — nothing is lost on restart
- DB file persists across runs (in the `av_data` volume)
- Reports go to `./reports/` folder on your host
- Web GUI runs on port 5000 by default — change with `ports: "8080:5000"` in docker-compose.yml
- Add `--delay "5-20"` for random delays to avoid rate limiting
- CLI commands now need the full path: `docker compose run avscraper python avscraper.py ...`
- Only one action runs at a time (single gunicorn worker) — safe for Playwright/Chromium
