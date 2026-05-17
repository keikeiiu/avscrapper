# JavDB Scraper + JAV NFO Enricher

Scrapes metadata from [javdb.com](https://javdb.com) → SQLite → Kodi NFO files.

## Quick Start

```bash
pip install -r requirements.txt
playwright install chromium
```

## How It Works

1. Navigate to `https://javdb.com/search?q={ID}&f=all`
2. Find the matching result by `<strong>` ID tag
3. Navigate to the detail page (e.g., `/v/0YqAa`)
4. Parse metadata from `<nav>` labels: 番號, 日期, 時長, 導演, 片商, 系列, 評分, 類別, 演員
5. Extract cover from `jdbstatic.com/covers`, fanart from `jdbstatic.com/samples`

## Usage

```bash
# Specific IDs
python scrapers/javdb_scraper.py --ids SSIS-119,CAWD-122 --delay "5-20"

# Resume / retry
python scrapers/javdb_scraper.py
python scrapers/javdb_scraper.py --retry-errors

# Re-scrape flagged entries
python scrapers/javdb_scraper.py --flagged

# Flag entries for re-scrape (via main entry point)
python avscraper.py flag javdb --ids SSIS-119,CAWD-122

# Write NFOs
python jav_enricher.py
python jav_enricher.py --ids SSIS-119
python jav_enricher.py --dry-run
```

## Delay Control

| Flag | Behavior |
|------|----------|
| `--delay 5` | Fixed 5s |
| `--delay "5-20"` | Random 5–20s (human-like) |

## NFO-First Import

If a `.nfo` file (`{cid}.nfo`) already exists in the video's folder, the scraper imports metadata from it directly instead of making a web request. This avoids unnecessary scraping for videos that already have metadata.

## Scraped Fields (29)

| Field | Source | Example |
|-------|--------|---------|
| `title` | `<title>` tag | SSIS-119 ※台本一切無し！！... |
| `studio` | 片商 | S1 NO.1 STYLE |
| `label` | 標籤/發行 | S1 NO.1 STYLE (defaults to studio) |
| `series` | 系列 | ※台本一切無し！！... |
| `director` | 導演 | 嵐山みちる |
| `release_date` | 日期 | 2021-07-19 |
| `year` | derived | 2021 |
| `runtime` | 時長 | 150 分鍾 |
| `rating` | 評分 | 4.16 |
| `votes` | 評分 | 236 |
| `genres` | 類別 | [美少女電影, 單體作品, ...] |
| `actors` | 演員 | [{name: 架乃ゆら}, ...] |
| `cover_url` | img | jdbstatic.com/covers/... |
| `fanart_urls` | samples | 10x jdbstatic.com/samples/... |

## NFO Format

```xml
<movie>
  <title>SSIS-119 Japanese Title</title>
  <originaltitle>Japanese Title</originaltitle>
  <sorttitle>SSIS-119</sorttitle>
  <uniqueid type="jav" default="true">SSIS-119</uniqueid>
  <plot>Description</plot>
  <studio>S1 NO.1 STYLE</studio>
  <label>S1 NO.1 STYLE</label>
  <series>Series Name</series>
  <director>嵐山みちる</director>
  <premiered>2021-07-19</premiered>
  <year>2021</year>
  <runtime>150</runtime>
  <genre>美少女電影</genre>
  <genre>單體作品</genre>
  <actor>
    <name>架乃ゆら</name>
    <thumb></thumb>
  </actor>
  <rating>4.16</rating>
  <votes>236</votes>
  <art>
    <poster>https://c0.jdbstatic.com/covers/...</poster>
    <fanart>https://c0.jdbstatic.com/samples/...</fanart>
  </art>
</movie>
```

## Auth

- **Public**: `over18: 1` cookie (bypass age gate)
- **Logged in**: `_jdb_session` (session cookie) — needed for VIP content

Cookies go in `config.yaml` → `sites.javdb.cookies`.

## Cookie Refresh

1. Log into https://javdb.com in Chrome
2. F12 → Application → Cookies → javdb.com
3. Copy: `_jdb_session`, `cf_clearance`, `over18`, `locale`
4. Update `config.yaml`
