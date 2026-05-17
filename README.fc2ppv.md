# FC2 PPV Scraper

Scrapes metadata from [fc2ppvdb.com](https://fc2ppvdb.com) using Playwright → SQLite → Kodi NFO files.

## How It Works

1. **Search**: navigates to `https://fc2ppvdb.com/articles/{cid}`
2. **Parse**: extracts metadata from the article page using DOM selectors
3. **NFO-first check**: if `FC2-PPV-{cid}.nfo` already exists in the video folder, metadata is imported from the NFO directly — no web request
4. **Write to DB**: upserts into `fc2_entries` table
5. **Rate limit**: random delay between requests, exponential backoff on 429

## Config Required

Add to `config.yaml` under `sites.fc2ppvdb`:

```yaml
sites:
  fc2ppvdb:
    base_url: "https://fc2ppvdb.com"
    scrape_delay_seconds: "5-20"    # random delay range (recommended)
    user_agent: "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:135.0) Gecko/20100101 Firefox/135.0"
    cookies:
      age_pass: ""           # required — bypass age gate
      cf_clearance: ""       # required — Cloudflare
      fc2ppvdb_session: ""   # required — session
      remember_web_xxx: ""   # optional — persistent login
      stype: ""              # optional
      XSRF-TOKEN: ""         # required — CSRF token
```

### Getting Cookies

1. Log into https://fc2ppvdb.com in Chrome/Firefox
2. F12 → Application (或 Storage) → Cookies → fc2ppvdb.com
3. Copy the six cookie values into `config.yaml`

Cookies typically last weeks to months. If scraping fails with redirects or empty results, refresh them.

## Scraped Fields

| Field | Source | Example |
|-------|--------|---------|
| `cid` | URL | `409694` |
| `title` | `.article-info h2` | `【素人動画】さゆみ18歳 ...` |
| `seller` | `/writers/` link | `六本木円光神話` |
| `actress` | `/actresses/` links (comma-joined) | `さゆみ, あかり` |
| `release_date` | `販売日` row | `2016-06-18` |
| `duration` | `収録時間` row | `01:00:19` |
| `duration_seconds` | Parsed from duration | `3619` |
| `mosaic` | `モザイク` row | `---` |
| `cover_url` | `#ArticleImage` src | `storage2000.contents.fc2.com/...` |
| `tags` | `/tags/` links | `[素人, 中出し, 巨乳]` |
| `outline` | Article description text | (full description) |
| `url` | Article URL | `https://fc2ppvdb.com/articles/409694` |

## NFO Format

Written as `FC2-PPV-{cid}.nfo` alongside the video files:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<movie>
  <title>FC2-PPV-409694 Japanese Title</title>
  <originaltitle>Japanese Title</originaltitle>
  <sorttitle>FC2-PPV-409694</sorttitle>
  <uniqueid type="fc2" default="true">409694</uniqueid>
  <num>FC2-PPV-409694</num>
  <plot>Title</plot>
  <studio>Seller Name</studio>
  <genre>FC2</genre>
  <premiered>2016-06-18</premiered>
  <runtime>60</runtime>
  <website>https://fc2ppvdb.com/articles/409694</website>
  <art>
    <poster>https://storage2000.contents.fc2.com/...</poster>
  </art>
  <tag>actress_name_1</tag>
  <tag>actress_name_2</tag>
</movie>
```

## Merge Behavior

When enriching, if an NFO already exists:
- **Poster art**: never overwritten
- **Title**: scraped value fills empty, doesn't overwrite real titles
- **Tags**: additive merge (actress names from DB appended)
- **All other fields**: scraped fills empty, never overwrites non-empty

## CLI

See [README.cli.md](README.cli.md) for full command reference. FC2-specific examples:

```bash
python avscraper.py scrape fc2ppvdb --ids 409694,3173579 --delay "5-20"
python avscraper.py scrape fc2ppvdb --flagged
python avscraper.py enrich fc2ppvdb --dry-run
python avscraper.py flag fc2ppvdb --ids 409694
```
