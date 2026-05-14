# FC2 PPV Scraper Tool

Automated metadata scraper for [fc2ppvdb.com](https://fc2ppvdb.com) — fetches title, seller, actress, release date, duration, tags, cover URL for FC2-PPV videos and stores everything in SQLite.

## Setup

```bash
pip install -r requirements.txt
playwright install chromium
```

## Usage

### One-off scrape (specific IDs)

```bash
python scrapers/fc2ppvdb_scraper.py --ids 409694,3173579,1234567
```

### Bulk scrape from ID list

```bash
python scrapers/fc2ppvdb_scraper.py --ids-file F-drive-FC2-list.md --delay "5-20"
```

### Seed DB first, scrape later

```bash
# Stage IDs without scraping
python scrapers/fc2ppvdb_scraper.py --ids-file F-drive-FC2-list.md --seed-only

# Scrape all pending
python scrapers/fc2ppvdb_scraper.py --delay "5-20"
```

### Resume interrupted run

```bash
python scrapers/fc2ppvdb_scraper.py
```

### Retry failed/404 entries

```bash
python scrapers/fc2ppvdb_scraper.py --retry-errors
```

### Dry-run (preview only, no network)

```bash
python scrapers/fc2ppvdb_scraper.py --ids-file F-drive-FC2-list.md --dry-run
```

## Delay Control

| Flag | Behavior |
|------|----------|
| `--delay 5` | Fixed 5 seconds between requests |
| `--delay "5-20"` | Random delay between 5-20 seconds (human-like) |
| Config `scrape_delay_seconds: "5-20"` | Default set in `fc2_config.yaml` |

## Checking Progress

```bash
sqlite3 fc2_data.db "SELECT status, COUNT(*) FROM fc2_entries GROUP BY status"
```

Output shows: `pending` (not yet scraped), `scraped` (done), `404` (not found), `error` (failed).

## Files

| File | Purpose |
|------|---------|
| `fc2_config.yaml` | Config: cookies, delays, scan dirs, DB path |
| `fc2_db.py` | SQLite schema + CRUD |
| `scrapers/base.py` | Shared scraper framework (CLI, rate-limiting, DB writes) |
| `scrapers/fc2ppvdb_scraper.py` | fc2ppvdb.com parser (Playwright) |
| `fc2_nfo.py` | NFO XML builder (for future enricher) |
| `F-drive-FC2-list.md` | 617 FC2 IDs from F drive |

## Cookie Refresh

If scraping returns 404 for known-valid IDs, cookies have expired.

1. Log into https://fc2ppvdb.com in Chrome
2. F12 → Application → Cookies → fc2ppvdb.com
3. Copy values for: `fc2ppvdb_session`, `XSRF-TOKEN`, `remember_web_*`, `cf_clearance`, `age_pass`, `stype`
4. Update `fc2_config.yaml` with new values
