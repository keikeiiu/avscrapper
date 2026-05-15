# AV Scraper & NFO Enricher

Scrapes metadata → SQLite → Kodi-compliant NFO files.

## Sites

| Site | Scraper | Enricher | Guide |
|------|---------|----------|-------|
| [fc2ppvdb.com](https://fc2ppvdb.com) | `scrapers/fc2ppvdb_scraper.py` | `fc2_enricher.py` | [README.fc2ppv.md](README.fc2ppv.md) |
| [javdb.com](https://javdb.com) | `scrapers/javdb_scraper.py` | `jav_enricher.py` | [README.javdb.md](README.javdb.md) |

## Setup

```bash
pip install -r requirements.txt
playwright install chromium
```

## Shared Architecture

```
[Video folders] → scraper.py → Playwright → site.com
                                    ↓
                               fc2_data.db (SQLite)
                                    ↓
[Video folders] → enricher.py → .nfo files + report.md
```

## Shared Components

| File | Purpose |
|------|---------|
| `config.yaml` | Cookies, delays, scan dirs |
| `db.py` | SQLite: `fc2_entries`, `fc2_files`, `jav_entries`, `jav_files` |
| `scrapers/base.py` | CLI, rate-limiting, DB writes |
| `fc2_nfo.py` | FC2 NFO XML builder |
| `jav_nfo.py` | JAV NFO XML builder |

## Checking Progress

```bash
sqlite3 fc2_data.db "SELECT source, status, COUNT(*) FROM fc2_entries GROUP BY source, status"
sqlite3 fc2_data.db "SELECT source, status, COUNT(*) FROM jav_entries GROUP BY source, status"
```

## Reorganizer

Move organized folders into a metadata-driven hierarchy.

```bash
python reorganize.py --dry-run     # preview
python reorganize.py               # execute
python reorganize.py --ids 409694  # specific entries
```

See [README.reorganize.md](README.reorganize.md) for template config.

## Delay Format

| Value | Behavior |
|-------|----------|
| `5` | Fixed 5s |
| `"5-20"` | Random 5–20s (human-like) |

Set in `config.yaml` (`scrape_delay_seconds`) or `--delay` CLI flag.
