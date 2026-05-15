# AV Scraper & NFO Enricher

Scrapes metadata from [fc2ppvdb.com](https://fc2ppvdb.com) and [javdb.com](https://javdb.com) → SQLite → Kodi-compliant NFO files.

## Setup

```bash
pip install -r requirements.txt
playwright install chromium
```

## Full Workflow

```bash
# Step 1: Scrape metadata from fc2ppvdb.com (617 IDs, ~2 hrs at 5-20s delay)
python scrapers/fc2ppvdb_scraper.py --ids-file F-drive-FC2-list.md --delay "5-20"

# Step 2: Write NFO files to video folders
python fc2_enricher.py
```

Resume-safe — Ctrl+C anytime, re-run the same command to continue.

## Scraper

Fetch metadata from fc2ppvdb.com and store in SQLite.

```bash
# Specific IDs
python scrapers/fc2ppvdb_scraper.py --ids 409694,3173579

# Bulk from file
python scrapers/fc2ppvdb_scraper.py --ids-file F-drive-FC2-list.md --delay "5-20"

# Seed DB first, scrape later
python scrapers/fc2ppvdb_scraper.py --ids-file F-drive-FC2-list.md --seed-only
python scrapers/fc2ppvdb_scraper.py --delay "5-20"

# Resume / retry errors
python scrapers/fc2ppvdb_scraper.py
python scrapers/fc2ppvdb_scraper.py --retry-errors

# Preview (no network)
python scrapers/fc2ppvdb_scraper.py --ids-file F-drive-FC2-list.md --dry-run
```

### Delay Control

| Flag | Behavior |
|------|----------|
| `--delay 5` | Fixed 5s between requests |
| `--delay "5-20"` | Random 5–20s (human-like) |
| Config `scrape_delay_seconds: "5-20"` | Default in `fc2_config.yaml` |
| Config `scrape_delay_seconds: 5` | Static delay |

## Enricher

Read scraped data from SQLite, write Kodi-standard NFO files to disk.

```bash
# All scraped entries
python fc2_enricher.py

# Specific IDs
python fc2_enricher.py --ids 409694,3173579

# Preview (no writes)
python fc2_enricher.py --dry-run
```

### NFO Format (Kodi-compliant)

```xml
<movie>
  <title>FC2-PPV-409694 Japanese Title</title>
  <originaltitle>Japanese Title</originaltitle>
  <sorttitle>FC2-PPV-409694</sorttitle>
  <uniqueid type="fc2" default="true">409694</uniqueid>
  <num>FC2-PPV-409694</num>
  <plot>Japanese Title</plot>
  <studio>Seller Name</studio>
  <genre>FC2</genre>
  <premiered>2020-10-18</premiered>
  <runtime>60</runtime>
  <website>https://fc2ppvdb.com/articles/409694</website>
  <art>
    <poster>https://cover-url.jpg</poster>
  </art>
  <tag>actress1</tag>
  <tag>actress2</tag>
</movie>
```

**Merge rules:** Never overwrites existing cover/poster. Tags are additive. Empty existing fields are filled from scraped data.

## JavDB (JAV)

Scrape JAV metadata from javdb.com and write Kodi NFOs.

```bash
# Scrape specific JAV IDs
python scrapers/javdb_scraper.py --ids SSIS-119,CAWD-122 --delay "5-20"

# Enrich (write NFOs)
python jav_enricher.py --ids SSIS-119

# Dry-run preview
python jav_enricher.py --dry-run
```

### JAV NFO Format

Additional fields vs FC2: `<label>`, `<series>`, `<director>`, `<year>`, `<rating>`, `<votes>`, nested `<actor><name><thumb>`, `<art><fanart>`.

### JavDB Auth

- Public: `over18: 1` cookie (bypass age gate)
- Full: `_jdb_session` + `remember_me_token` (login required for VIP content)

Cookies go in `config.yaml` under `sites.javdb.cookies`.

## Checking Progress

```bash
sqlite3 fc2_data.db "SELECT status, COUNT(*) FROM fc2_entries GROUP BY status"
sqlite3 fc2_data.db "SELECT status, COUNT(*) FROM jav_entries GROUP BY status"
```

Output: `pending` / `scraped` / `404` / `error`

## Files

| File | Purpose |
|------|---------|
| `config.yaml` | Config: cookies, delays, scan dirs, DB path |
| `db.py` | SQLite schema + CRUD (fc2 + jav tables) |
| `scrapers/base.py` | Shared framework: CLI, rate-limit, DB writes |
| `scrapers/fc2ppvdb_scraper.py` | fc2ppvdb.com parser (Playwright) |
| `scrapers/javdb_scraper.py` | javdb.com parser (Playwright) |
| `fc2_enricher.py` | FC2: read DB → write NFOs |
| `jav_enricher.py` | JAV: read DB → write NFOs |
| `fc2_nfo.py` | FC2 NFO XML parse / build / merge |
| `jav_nfo.py` | JAV NFO XML parse / build / merge |
| `F-drive-FC2-list.md` | 617 FC2 IDs from F drive |

## Cookie Refresh

If scraper returns 404 for known-valid IDs, cookies have expired.

1. Log into the target site in Chrome
2. F12 → Application → Cookies → site domain
3. Copy the session/auth cookies
4. Update `config.yaml`
