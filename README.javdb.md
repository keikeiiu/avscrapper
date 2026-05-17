# JavDB Scraper

Scrapes metadata from [javdb.com](https://javdb.com) using Playwright → SQLite → Kodi NFO files.

## How It Works

1. **Search**: navigates to `https://javdb.com/search?q={ID}&f=all`
2. **Match**: finds the result where the `<strong>` ID tag matches the query CID
3. **Detail page**: navigates to the matched video page (e.g., `/v/0YqAa`)
4. **Parse**: extracts metadata from `<nav>` label-value pairs (番號, 日期, 時長, 導演, 片商, 系列, 評分, 類別, 演員)
5. **NFO-first check**: if `{cid}.nfo` already exists in the video folder, metadata is imported from the NFO directly — no web request
6. **Write to DB**: upserts into `jav_entries` table
7. **Rate limit**: random delay between requests, exponential backoff on 429

## Config Required

Add to `config.yaml` under `sites.javdb`:

```yaml
sites:
  javdb:
    base_url: "https://javdb.com"
    scrape_delay_seconds: "5-20"    # random delay range (recommended)
    user_agent: "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:135.0) Gecko/20100101 Firefox/135.0"
    cookies:
      over18: "1"           # required — bypass age gate
      _jdb_session: ""      # optional — needed for VIP/restricted content
```

### Auth Levels

- **Public**: `over18: "1"` cookie only — access to non-VIP content
- **Logged in**: `_jdb_session` cookie — needed for VIP/restricted videos
- **Without cookies**: age gate blocks access, scraper fails

### Getting Cookies

1. Open https://javdb.com in Chrome/Firefox
2. F12 → Application (或 Storage) → Cookies → javdb.com
3. Copy `over18` (value is usually `1`) and `_jdb_session`
4. Update `config.yaml`

## Scraped Fields

| Field | Source Label | Example |
|-------|-------------|---------|
| `cid` | 番號 | `SSIS-119` |
| `title` | `<title>` tag | `SSIS-119 ※台本一切無し！！...` |
| `studio` | 片商 | `S1 NO.1 STYLE` |
| `label` | 標籤/發行 | `S1 NO.1 STYLE` (defaults to studio if missing) |
| `series` | 系列 | `※台本一切無し！！...` |
| `director` | 導演 | `嵐山みちる` |
| `release_date` | 日期 | `2021-07-19` |
| `year` | Derived from date | `2021` |
| `runtime` | 時長 | `150 分鍾` |
| `runtime_seconds` | Calculated | (runtime in minutes × 60) |
| `rating` | 評分 | `4.16` |
| `votes` | 評分 count | `236` |
| `genres` | 類別 | `[美少女電影, 單體作品, ...]` |
| `actors` | 演員 | `[{name: "架乃ゆら"}, ...]` |
| `cover_url` | Cover image | `jdbstatic.com/covers/...` |
| `fanart_urls` | Samples | 10× `jdbstatic.com/samples/...` |
| `url` | Page URL | `https://javdb.com/v/0YqAa` |

## NFO Format

Written as `{cid}.nfo` (e.g., `SSIS-119.nfo`) alongside the video files:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<movie>
  <title>SSIS-119 Japanese Title</title>
  <originaltitle>Japanese Title</originaltitle>
  <sorttitle>SSIS-119</sorttitle>
  <uniqueid type="jav" default="true">SSIS-119</uniqueid>
  <plot>Description text</plot>
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
  </actor>
  <rating>4.16</rating>
  <votes>236</votes>
  <website>https://javdb.com/v/0YqAa</website>
  <art>
    <poster>https://c0.jdbstatic.com/covers/...</poster>
    <fanart>https://c0.jdbstatic.com/samples/...</fanart>
  </art>
</movie>
```

## Merge Behavior

When enriching, if an NFO already exists:
- **Poster/fanart**: never overwritten
- **Title**: scraped value fills empty, doesn't overwrite existing
- **Genres/tags/actors**: additive merge (deduplicated by name)
- **All other fields**: scraped fills empty, never overwrites non-empty

## Studio/Series Maps

JavDB uses inconsistent or Japanese names for studios and series. The `studio_map` and `series_map` in `config.yaml` normalize these — e.g., `SODクリエイト` → `SOD Create`. See `config.example.yaml` for the full map of 40+ studios.

## CLI

See [README.cli.md](README.cli.md) for full command reference. JavDB-specific examples:

```bash
python avscraper.py scrape javdb --ids SSIS-119,CAWD-122 --delay "5-20"
python avscraper.py scrape javdb --flagged
python avscraper.py enrich javdb --dry-run
python avscraper.py flag javdb --ids SSIS-119
```
