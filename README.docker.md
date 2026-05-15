# AV Scraper — Docker Guide

Zero-install. Works on Windows, Mac, Linux. Just need Docker Desktop.

## 1. Create Your docker-compose.yml

```yaml
services:
  avscraper:
    image: keikeiiu/avscraper:latest
    container_name: avscraper
    volumes:
      - ./downloads:/app/downloads
      - ./processed:/app/processed
      - ./reorganized:/app/reorganized
      - ./config.yaml:/app/config.yaml:ro
      - av_data:/app
    entrypoint: ["python", "/app/avscraper.py"]

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

```bash
# Drop videos into ./downloads/
docker compose run avscraper ingest --dry-run
docker compose run avscraper ingest

# Scrape metadata
docker compose run avscraper scrape fc2ppvdb --delay "5-20"
docker compose run avscraper scrape javdb --delay "5-20"

# Write NFO files
docker compose run avscraper enrich fc2ppvdb
docker compose run avscraper enrich javdb

# Reorganize into hierarchy
docker compose run avscraper reorganize --dry-run
docker compose run avscraper reorganize
docker compose run avscraper reorganize --report
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
- Add `--delay "5-20"` for random delays to avoid rate limiting
- Use `--ids ABP-948` to test with a single entry first
