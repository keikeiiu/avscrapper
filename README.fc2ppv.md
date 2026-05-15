# FC2 PPV Scraper + NFO Enricher

Scrapes metadata from [fc2ppvdb.com](https://fc2ppvdb.com) → SQLite → Kodi NFO files.

## Quick Start

```bash
pip install -r requirements.txt
playwright install chromium
```

## Usage

```bash
# Scrape all pending
python scrapers/fc2ppvdb_scraper.py

# Specific IDs
python scrapers/fc2ppvdb_scraper.py --ids 409694,3173579,1234567

# Bulk from ID list (617 F-drive IDs)
python scrapers/fc2ppvdb_scraper.py --ids-file F-drive-FC2-list.md --delay "5-20"

# Seed DB first, scrape later
python scrapers/fc2ppvdb_scraper.py --ids-file F-drive-FC2-list.md --seed-only
python scrapers/fc2ppvdb_scraper.py --delay "5-20"

# Resume / retry
python scrapers/fc2ppvdb_scraper.py
python scrapers/fc2ppvdb_scraper.py --retry-errors

# Write NFOs
python fc2_enricher.py
python fc2_enricher.py --ids 409694
python fc2_enricher.py --dry-run
```

## Delay Control

| Flag | Behavior |
|------|----------|
| `--delay 5` | Fixed 5s |
| `--delay "5-20"` | Random 5–20s (human-like) |

## Scraped Fields

| Field | Source | Example |
|-------|--------|---------|
| `title` | article-info h2 | 【素人動画】さゆみ18歳 ... |
| `seller` | /writers/ link | 六本木円光神話 |
| `actress` | /actresses/ links | さゆみ |
| `release_date` | 販売日 | 2016-06-18 |
| `duration` | 収録時間 | 01:00:19 |
| `mosaic` | モザイク | --- |
| `cover_url` | #ArticleImage | storage2000.contents.fc2.com/... |
| `tags` | /tags/ links | [素人, 中出し, ...] |

## NFO Format

```xml
<movie>
  <title>FC2-PPV-409694 Japanese Title</title>
  <originaltitle>Japanese Title</originaltitle>
  <sorttitle>FC2-PPV-409694</sorttitle>
  <uniqueid type="fc2" default="true">409694</uniqueid>
  <plot>Title</plot>
  <studio>Seller Name</studio>
  <genre>FC2</genre>
  <premiered>2016-06-18</premiered>
  <runtime>60</runtime>
  <website>https://fc2ppvdb.com/articles/409694</website>
  <art><poster>cover-url.jpg</poster></art>
  <tag>actress</tag>
</movie>
```

## Cookie Refresh

1. Log into https://fc2ppvdb.com in Chrome
2. F12 → Application → Cookies → fc2ppvdb.com
3. Copy: `fc2ppvdb_session`, `XSRF-TOKEN`, `remember_web_*`, `cf_clearance`, `age_pass`, `stype`
4. Update `config.yaml` → `sites.fc2ppvdb.cookies`
