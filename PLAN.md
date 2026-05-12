# FC2 Automated Scraper + NFO Enricher Plan

## Context

Previously, 304 FC2 videos had their metadata manually scraped from `fc2ppvdb.com` using Browser MCP (one-by-one navigation) and NFOs were enriched via `enrich_nfos.js`. This needs to become an **automated, repeatable tool** in `avscrappertools/` with **separated scraper and enricher processes** communicating through SQLite.

Architecture discussed with Gemini: Python for scraper (AI-friendly, reuses MDC-FIX), SQLite as shared DB, separation of "scrape to DB" and "DB to NFO" phases.

## Architecture

```
[FC2 directories] → fc2_scraper.py → HTTP(+cookie) → fc2ppvdb.com
                                ↓
                           fc2_data.db (SQLite)
                                ↓
[FC2 directories] → fc2_enricher.py → NFO files + report.md
```

**Language: Python-only** — reuses the existing `MDC-FIX/scrapinglib/fc2ppvdb.py` which already has all XPath expressions and cookie support.

## Files to Create (all in `avscrappertools/`)

| File | Purpose | ~Lines |
|------|---------|--------|
| `fc2_config.yaml` | Config: scan dirs, cookie, DB path, rate limit, MDC-FIX path | 25 |
| `config.ini` | Minimal MDC-FIX config (required by its Config() loader) | 50 |
| `fc2_db.py` | SQLite schema + CRUD: init, upsert_entry, upsert_file, get_pending, get_scraped, update_status | 110 |
| `fc2_scraper.py` | CLI: scan dirs → insert pending → scrape FC2PPVDB → save to DB | 220 |
| `fc2_enricher.py` | CLI: read scraped from DB → merge with existing NFO → write NFO → report | 250 |
| `fc2_nfo.py` | NFO XML parse/build/write using xml.etree.ElementTree | 80 |
| `fc2_mp4.py` | MP4 duration parser (port get_durations.js moov/mvhd atom parsing to Python struct) | 70 |
| `fc2_reporter.py` | Markdown audit report generation | 70 |
| `requirements.txt` | pyyaml, requests, lxml | 3 |

## SQLite Schema

**`fc2_entries`** — one row per FC2 ID:
- `cid` TEXT PK (bare number, e.g. "3173579")
- `full_number` TEXT ("FC2-PPV-3173579")
- `title`, `seller`, `actress`, `release_date`, `duration`, `duration_seconds`
- `cover_url`, `tags` (JSON array), `outline`, `url`, `mosaic`
- `status` TEXT: `pending` → `scraped` → `nfo_done` | `404` | `error`
- `error_message` TEXT, `scraped_at` TEXT, `raw_json` TEXT

**`fc2_files`** — one row per MP4 file:
- `id` INTEGER PK auto
- `cid` TEXT FK → fc2_entries
- `directory_path`, `file_path`, `file_size`
- `duration_seconds` REAL, `duration_str` TEXT
- `part_number` INTEGER DEFAULT 1

## Key Design Decisions

1. **Import MDC-FIX, don't copy**: `sys.path.insert(0, config.mdcfix_path)` then `from scrapinglib.api import Scraping`. Reuses battle-tested XPath expressions. If fc2ppvdb.com changes, fix once in MDC-FIX.

2. **Scraper uses `Scraping().search()` not `Fc2ppvdb()` directly**: The `Scraping` orchestrator properly wires `fc2cookies` through `updateCore()`. Without it, the cookie dict never reaches the HTTP request.

3. **Cookie**: `all_age_verification_check=1` passed as `fc2cookies` dict.

4. **Rate limiting**: `scrape_delay_seconds: 3` between entries (MDC-FIX already has built-in 3s retry delay).

5. **Cover preservation**: Enricher NEVER overwrites existing `<cover>`. Tags are merged additively.

6. **Multi-part detection**: Regex `[-_]?(?:part?|pt)(\d+)` before `.mp4`. One DB entry per CID, multiple `fc2_files` rows. Duration audit sums all parts.

7. **Date normalization**: `YYYY/MM/DD` → `YYYY-MM-DD`.

## Data Flow

### Scraper (`fc2_scraper.py`)
```
1. Load config.yaml
2. If --ids: use those; else: scan all configured directories
3. Parse dir names → extract CID, detect multi-part, find MP4s
4. INSERT OR IGNORE into fc2_entries (status='pending'), INSERT into fc2_files
5. For each pending entry:
   a. Call Scraping().search(cid, sources='fc2ppvdb', fc2cookies={...})
   b. Parse returned JSON → upsert fc2_entries (status='scraped' or '404')
   c. Parse MP4 durations via fc2_mp4 → update fc2_files
   d. Sleep(scrape_delay_seconds)
6. Print summary
```

### Enricher (`fc2_enricher.py`)
```
1. Load config.yaml
2. Query fc2_entries WHERE status='scraped' (or specific --ids)
3. For each entry:
   a. Find directory on disk (search scan dirs)
   b. Read existing NFO via fc2_nfo.parse_nfo()
   c. Merge: title, studio, tags, premiered, website (NEVER cover)
   d. If changed: write NFO, update status='nfo_done'
4. Generate markdown report
```

## CLI Usage

```bash
python fc2_scraper.py                        # Scrape all pending
python fc2_scraper.py --ids 3173579,409694   # Scrape specific IDs
python fc2_scraper.py --retry-errors         # Retry failed
python fc2_enricher.py                       # Enrich all scraped
python fc2_enricher.py --dry-run             # Preview changes
python fc2_enricher.py --ids 3173579,409694  # Enrich specific IDs
```

## Implementation Order

1. **Foundation**: `fc2_config.yaml`, `config.ini`, `fc2_db.py`, `fc2_nfo.py`, `fc2_mp4.py`, `requirements.txt`
2. **Scraper**: `fc2_scraper.py` — scan + scrape + DB persistence
3. **Enricher**: `fc2_enricher.py` + `fc2_reporter.py` — NFO merge + write + report
4. **Integration test**: Run full pipeline against 10 IDs, verify NFO output

## Verification

1. `python fc2_scraper.py --ids 409694` (known working ID) → DB has status='scraped'
2. `python fc2_enricher.py --ids 409694 --dry-run` → merge logic correct
3. `python fc2_enricher.py --ids 409694` → NFO written, cover preserved
4. `python fc2_scraper.py --ids 999999999999` (fake ID) → status='404'
5. Test multi-part ID → part detection + duration summation work
