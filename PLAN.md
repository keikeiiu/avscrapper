# FC2 Scraper — Updated Plan (Multi-Site)

## Status
- ✅ Scraper (`scrapers/fc2ppvdb_scraper.py`) — working, Playwright-based
- ✅ Kodi NFO (`fc2_nfo.py`) — standard fields, merge logic
- ✅ Enricher (`fc2_enricher.py`) — writes `movie.nfo` per folder
- ⬜ Duration audit — deferred (no MP4 access)
- ⬜ Video renaming — deferred

## Context

Building HTTP scrapers for FC2PPV metadata. No `MDC-FIX` repo on this PC — all parsing built from scratch with `requests` + `lxml`. Cookie-based auth. No MP4 files on this PC, so **scraper + DB only** — enricher comes later.

Key design requirement: **each website gets its own scraper module**. `fc2ppvdb_scraper.py` targets fc2ppvdb.com specifically. Future sites (fc2hub, dmm, etc.) add new modules without touching shared infrastructure.

## Architecture (Multi-Site)

```
avscrappertools/
├── fc2_config.yaml              # Config with per-site sections
├── fc2_db.py                    # Shared SQLite layer (schema + CRUD for all sites)
├── fc2_nfo.py                   # Shared NFO XML parse/build/write
├── requirements.txt             # pyyaml, requests, lxml
├── scrapers/
│   ├── __init__.py
│   ├── base.py                  # BaseScraper: session, rate-limit, DB writes, CLI dispatch
│   └── fc2ppvdb_scraper.py      # fc2ppvdb.com parser + site-specific logic
└── F-drive-FC2-list.md
```

**Shared layer** (`fc2_db.py`, `fc2_nfo.py`, `fc2_config.yaml`): one schema, one config file, one NFO format. All scrapers write to the same `fc2_data.db`.

**Site scrapers** (`scrapers/*.py`): each inherits `BaseScraper`, implements `search(cid) → dict`. Only responsible for HTTP + HTML parsing for their target site.

## Files to Create (7 files, ~530 lines)

| File | Purpose | Lines |
|------|---------|-------|
| `fc2_config.yaml` | Per-site config: cookies, UA, delays, scan dirs, DB path | ~30 |
| `requirements.txt` | pyyaml, requests, lxml | 3 |
| `fc2_db.py` | SQLite schema + CRUD (init, upsert_entry, get_pending, etc.) | ~110 |
| `fc2_nfo.py` | NFO XML parse/build/write (scaffold for future enricher) | ~80 |
| `scrapers/__init__.py` | Package init, scraper registry | ~10 |
| `scrapers/base.py` | BaseScraper: session, rate-limit, anti-ban headers, DB write helpers, CLI arg parsing | ~150 |
| `scrapers/fc2ppvdb_scraper.py` | fc2ppvdb.com: search URL, HTML selectors, parse logic | ~150 |

**Deferred** (no MP4 files): `fc2_enricher.py`, `fc2_mp4.py`, `fc2_reporter.py`

## BaseScraper Design (`scrapers/base.py`)

Abstract base class that handles everything site-agnostic:

```
class BaseScraper:
    def __init__(self, config_section)      # Load site config from fc2_config.yaml
    def _init_session(self)                  # requests.Session with UA, cookies, headers
    def _rate_limit(self)                    # Sleep scrape_delay_seconds, backoff on 429
    def search(self, cid) -> dict            # ABSTRACT: site implements HTTP GET + parse
    def scrape_pending(self, db)             # Loop: get pending from DB → search() → upsert
    def run(self, args)                      # CLI entry: parse args, dispatch
```

Each site scraper only needs to implement `search(cid)`:
1. HTTP GET to site's search/display URL
2. Parse HTML with `lxml.cssselect`
3. Return dict of {title, seller, actress, tags, release_date, cover_url, outline, ...}

## SQLite Schema (same as original, shared across all sites)

**`fc2_entries`**: `cid` TEXT PK, `full_number`, `title`, `seller`, `actress`, `release_date`, `duration`, `duration_seconds`, `cover_url`, `tags` (JSON), `outline`, `url`, `source` (site name, e.g. "fc2ppvdb"), `mosaic`, `status` (pending→scraped | 404 | error), `error_message`, `scraped_at`, `raw_json`

**`fc2_files`**: `id` PK auto, `cid` FK, `directory_path`, `file_path`, `file_size`, `duration_seconds`, `duration_str`, `part_number`

Added `source` column to track which site provided the data — useful when multiple scrapers exist.

## fc2ppvdb.com Parsing

Target URL: `https://fc2ppvdb.com/search?q={cid}` → redirects to video page.

Parsing approach: use `lxml` CSS selectors against known page structure. Validate with known ID `409694`. Key targets:
- Title, seller, actress, tags, release date, duration, cover URL, outline

## Config Structure (`fc2_config.yaml`)

```yaml
db_path: "fc2_data.db"
scan_directories: []  # populated when F-drive is available

sites:
  fc2ppvdb:
    base_url: "https://fc2ppvdb.com"
    scrape_delay_seconds: 3
    user_agent: "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Firefox/135.0"
    cookies:
      all_age_verification_check: "1"
      # add session cookies after login
```

## Anti-Ban Measures

1. Per-site `scrape_delay_seconds` (default 3s)
2. Real browser User-Agent per site
3. `Referer` header set to site base URL
4. Single `requests.Session` reused across all requests
5. Exponential backoff on 429 (30s/60s/120s)
6. Resume-safe: only scrape `status='pending'` rows

## Cookie Acquisition

Browser MCP configured (`@browsermcp/mcp@latest`). Will try:
1. Browser MCP: navigate → user logs in → extract cookies → write to yaml
2. Fallback: DevTools manual copy

## CLI Usage

```bash
# Via fc2ppvdb_scraper.py directly:
python scrapers/fc2ppvdb_scraper.py                          # Scrape all pending
python scrapers/fc2ppvdb_scraper.py --ids 409694,3173579     # Test specific IDs
python scrapers/fc2ppvdb_scraper.py --ids-file ../../F-drive-FC2-list.md
python scrapers/fc2ppvdb_scraper.py --retry-errors
python scrapers/fc2ppvdb_scraper.py --delay 5 --dry-run

# Future: single dispatcher that routes to correct scraper by source
```

## Enricher NFO Naming

Always `FC2-PPV-{cid}.nfo` per folder. Kodi/Jellyfin auto-detect multi-part from file suffixes.

```
FC2-PPV-409694/
  └── FC2-PPV-409694.nfo

FC2-PPV-3173579[UNCENSORED]/
  ├── FC2-PPV-3173579-pt1.mp4
  ├── FC2-PPV-3173579-pt2.mp4
  └── FC2-PPV-3173579.nfo          ← one NFO covers all parts
```

## Implementation Order

1. ✅ `fc2_config.yaml` — config with cookies, delays, scan dirs
2. ✅ `requirements.txt` — pyyaml, playwright
3. ✅ `fc2_db.py` — SQLite schema + CRUD
4. ✅ `scrapers/base.py` — BaseScraper framework
5. ✅ `scrapers/fc2ppvdb_scraper.py` — Playwright scraper
6. ✅ `fc2_nfo.py` — Kodi-standard NFO builder
7. ✅ `fc2_enricher.py` — writes `movie.nfo` per folder
8. ⬜ Duration audit (deferred, no MP4 access)

## Verification

1. `python scrapers/fc2ppvdb_scraper.py --ids 409694` → scraped OK
2. `python fc2_enricher.py --ids 409694` → `FC2-PPV-409694.nfo` in folder
3. `sqlite3 fc2_data.db "SELECT status, COUNT(*) FROM fc2_entries GROUP BY status"` → correct counts

---

# JavDB Scraper + JAV NFO (Next Phase)

## Context

JAV metadata is richer than FC2 — series, label, director, multiple actors with photos, ratings. JavDB.com is the community standard. Unprocessed JAV files at `F:/AV/Japanese/JAV/_Unprocessed/`.

## New Components

| File | Purpose |
|------|---------|
| `db.py` | Rename from `fc2_db.py`, add `jav_entries` + `jav_files` tables |
| `config.yaml` | Rename from `fc2_config.yaml`, add `javdb:` section |
| `scrapers/javdb_scraper.py` | JavDB Playwright scraper |
| `jav_nfo.py` | JAV Kodi NFO: series, label, director, actors with thumbs, rating |
| `jav_enricher.py` | JAV NFO enricher |

## JAV NFO Fields

`<title>`, `<originaltitle>`, `<sorttitle>`, `<uniqueid type="jav">`, `<plot>`, `<studio>`, `<label>`, `<series>`, `<director>`, `<premiered>`, `<year>`, `<runtime>`, `<genre>`, `<actor><name><thumb>`, `<rating>`, `<votes>`, `<art><poster><fanart>`

## JavDB Auth

- Public: `over18: 1` cookie
- Full: `_jdb_session` + `remember_me_token` (login)

## Implementation Order

1. Rename `fc2_db.py` → `db.py`, add JAV tables
2. Rename `fc2_config.yaml` → `config.yaml`
3. Update imports across all files
4. `jav_nfo.py` builder
5. `scrapers/javdb_scraper.py`
6. `jav_enricher.py`
