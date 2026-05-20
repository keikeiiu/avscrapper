# AV Scraper — Plan

## Quick Start (for continuing on Mac)

```bash
git clone https://github.com/keikeiiu/avscrapper.git
cd avscrapper
pip install -r requirements.txt
playwright install chromium

# Copy your config (with _jdb_session cookie) or create from example
cp config.example.yaml config.yaml   # edit paths + cookies

# Optional: use the test DB from the media-stack repo (141 JAV entries scraped)
git clone https://github.com/keikeiiu/media-stack-docker-compose.git ../media-stack-docker-compose
cp ../media-stack-docker-compose/avscrappertools/av_data.db ./appdata/av_data.db

# Start web GUI
python web/app.py
# Open http://127.0.0.1:3721/browse
```

**Test DB:** `media-stack-docker-compose/avscrappertools/av_data.db` (610 KB, 141 JAV entries, 119 with file paths)

## Current Architecture

```
avscrapper/
├── avscraper.py              # entry point (ingest/scrape/enrich/audit/reorganize/setup/flag)
├── config.example.yaml       # template config (relative paths, no cookies)
├── docker-compose.yml        # Docker Compose deployment (4 mounts)
├── Dockerfile                # Docker image build (python:3.12-slim + Chromium)
├── requirements.txt          # pyyaml, playwright, flask, gunicorn, markdown, defusedxml
├── .github/workflows/
│   ├── docker-publish.yml    # build + push to Docker Hub on main push
│   ├── desktop-release.yml   # build Windows portable .exe (manual trigger)
│   └── python-audit.yml      # Bandit SAST + pip-audit on src/** changes
├── desktop/                  # Electron desktop app
│   ├── main.js               # Electron main process
│   ├── preload.js            # IPC bridge
│   ├── package.json          # Electron + electron-builder config
│   ├── build.py              # PyInstaller + electron-builder → SFX
│   ├── icons/                # App icons
│   └── README.md
├── web/                      # Flask web GUI
│   ├── app.py                # app factory, config load, first-run init
│   ├── routes/
│   │   ├── actions.py        # pipeline trigger + SSE streaming
│   │   ├── db_api.py         # DB browse/filter/search/flag (JSON API)
│   │   ├── stream.py         # SSE endpoint for live output
│   │   └── config_api.py     # config read/write with YAML validation
│   ├── templates/
│   │   ├── dashboard.html    # stat cards, quick actions, history
│   │   ├── actions.html      # action trigger with parameter forms
│   │   ├── db_browse.html    # FC2/JAV table browser with filters
│   │   ├── logs.html         # report file viewer
│   │   └── config.html       # CodeMirror YAML editor
│   └── static/
├── src/
│   ├── db.py                 # SQLite (4 tables), find_directories(), CRUD
│   ├── ingest.py             # auto-detect FC2/JAV, organize, seed DB
│   ├── reorganize.py         # metadata-driven folder hierarchy (copy-verify-delete)
│   ├── duration_audit.py     # ffprobe duration check, tiered flags
│   └── sites/
│       ├── base_scraper.py   # shared scraper framework (CLI, rate-limit, NFO import)
│       ├── fc2ppvdb/
│       │   ├── fc2ppvdb_scraper.py
│       │   ├── fc2_nfo.py    # NFO parse/build/merge (defusedxml)
│       │   └── fc2_enricher.py
│       └── javdb/
│           ├── javdb_scraper.py
│           ├── jav_nfo.py    # NFO parse/build/merge (defusedxml)
│           └── jav_enricher.py
├── appdata/                  # persistent: config.yaml, av_data.db, reports/ (Docker mount)
├── downloads/                # video source (user mount)
├── processed/                # ingest staging (user mount)
└── reorganized/              # final destination (user mount)
```

## Status

| Component | Status |
|-----------|--------|
| FC2 scraper + NFO + enricher | ✅ |
| JavDB scraper + NFO + enricher | ✅ |
| Ingest pipeline (auto-detect, part assignment, seed DB) | ✅ |
| Reorganizer (folder templates, studio/series maps) | ✅ |
| Duration audit (ffprobe, two-tier flags) | ✅ |
| Web GUI (dashboard, config editor, DB browser, SSE) | ✅ |
| Docker (image + Compose, first-run auto-config) | ✅ |
| Desktop app (Electron + PyInstaller + SFX portable .exe) | ✅ |
| CI/CD (Docker publish, desktop release, Python audit) | ✅ |

## Database

4 tables: `fc2_entries`, `fc2_files`, `jav_entries`, `jav_files`. `jav_entries` has `region` column (jav/chinese). Both entries tables have `audit_status` + `last_audited`.

## Workflow

```
downloads/ → ingest.py → processed/
                              ↓
               scraper.py → av_data.db
                              ↓
               enricher.py → .nfo files (alongside videos)
                              ↓
               reorganize.py → reorganized/{FC2,JAV}/{structure}/
                              ↓
               duration_audit.py → report + audit tags
```

## Docker Layout

```
Host:                          Container:
./appdata/          → /app/appdata/    (config.yaml, av_data.db, reports/)
./downloads/        → /app/downloads/  (video source)
./processed/        → /app/processed/  (ingest staging)
./reorganized/      → /app/reorganized/ (final destination)
```

First-run auto-config copies `config.example.yaml` → `/app/appdata/config.yaml` and patches app-data paths to absolute for Docker. Video paths stay user-configurable like *arr stack.

## Config Path Resolution

Every script follows the same order: `AV_CONFIG` env var → `config.yaml` (relative to script) → error. All relative paths (`db_path`, `report_dir`, `ingest.*`, `reorganize.target`) are resolved against the config file's directory via `os.path.normpath(os.path.join(config_dir, val))`.

## CLI (via avscraper.py)

```bash
python avscraper.py setup
python avscraper.py ingest [--source ./downloads] [--dry-run] [--scrape] [--enrich] [--yes]
python avscraper.py scrape <fc2ppvdb|javdb> [--ids ...] [--flagged] [--retry-errors] [--delay "5-20"]
python avscraper.py enrich <fc2ppvdb|javdb> [--ids ...] [--dry-run]
python avscraper.py flag <fc2ppvdb|javdb> --ids <cids>
python avscraper.py reorganize [--dry-run] [--ids ...] [--report]
python avscraper.py audit [--dry-run] [--type fc2|jav] [--ids ...]
```

See [README.cli.md](README.cli.md) for full reference.

## Future Enhancements

Priority order based on impact/effort. Every feature targets both Docker and Windows Desktop.

---

### 1. Cookie Health Check (High Value / Low Effort)

Before scraping, verify cookies are still valid to avoid wasting time on 100+ `login_required` failures.

- Add `python avscraper.py check` command
- For each site: launch headless browser with stored cookies, navigate to a known page, check HTTP status
- Report: "fc2ppvdb: OK / javdb: session expired"
- Web UI: health status indicator on dashboard + Config page "Test Scraper" button

### 2. Studio Mapping Scraper (Low-Medium Effort)

Scrape `https://javdb.com/makers` and `https://javdb.com/makers/uncensored` to build a comprehensive `studio_map` with canonical English names.

**Approach:**
- Reuse Playwright + existing `_jdb_session` cookie from config
- Script: `python avscraper.py update-studios` (or `python src/update_studio_map.py`)
- For each maker on javdb:
  - Extract primary name (bold text) + alternate names from the listing
  - Map Japanese names (e.g., `マドンナ`) → English canonical (e.g., `Madonna`)
  - Map alternate names (e.g., `蚊香社` → `PRESTIGE`)
- Write updated `studio_map` into config.yaml (merge with existing, keep user edits)

**Censored page 1 sample (50 makers, ~300+ total across 6 pages):**
- S1 NO.1 STYLE, MOODYZ, FALENO, PRESTIGE/プレステージ, IDEA POCKET, kawaii
- E-BODY, Madonna/マドンナ, Attackers, ワンズファクトリー, 溜池ゴロー, OPPAI
- Premium/プレミアム, Fitch, SOD Create, KMP/ケイ・エム・プロデュース, etc.
- Many have dual Japanese/English names needing mapping

**Uncensored makers page:**
- Requires login (redirects to `/login` without session)
- Will use `_jdb_session` cookie via Playwright for access
- Known uncensored studios to expect: Caribbeancom, 1Pondo, Heyzo, 10musume, Pacopacomama, etc.

**Output:** `studio_map` in config.yaml grows from 63 → 300+ entries. Japanese → English canonical mappings auto-generated. User reviews and adjusts after generation.

### 3. Cover Image Caching (High Impact / Low Effort)

Currently `cover_url` points to external CDNs (jdbstatic.com, fc2ppvdb.com). These can go down, change URLs, or block hotlinking. Download covers locally, serve from Flask, and fall back gracefully.

- Add a `cover_path` column to entries tables (local file path)
- On scrape, download the cover image to `appdata/covers/{cid}.jpg`
- Serve via `/api/cover/<cid>` endpoint
- Browse page uses local covers when available, remote as fallback
- Existing entries can be backfilled with a `--download-covers` flag on scrape

### 4. Missing File Detection (High Impact / Low Effort)

Entries exist in the DB but their files may have been moved/deleted outside the app. Detect and surface this.

- Extend `path_audit.py` to also check entries that have NO file records
- Add a `no_files` status or flag to the browse page filter dropdown
- Show "Files missing" badge on poster cards when files can't be found

### 5. Browse Page Improvements (Low-Medium Effort)

- **Keyboard shortcuts**: `j`/`k` for next/prev card, `Enter` to open detail, `f` to play first file, `Esc` to close modal
- **Infinite scroll**: load next page automatically when scrolling near bottom
- **Grid density toggle**: small/medium/large card sizes
- **Card right-click context menu**: open file, open folder, copy CID, flag

### 6. User Data Layer (Medium Effort)

Let users add their own data on top of scraped metadata.

- `user_notes` TEXT column on entries — free-text notes
- `user_rating` INTEGER — 1-5 stars
- `favorite` boolean flag — toggle from detail modal, filter in browse
- Browse page: filter by favorites only
- Detail modal: editable notes field, star rating widget

**Scope note:** `watched` deferred — app doesn't provide a watch function yet (keep as future option).

### 7. Video Metadata Extraction (Medium Impact / Medium Effort)

Beyond duration, extract rich video metadata using ffprobe.

- Extract: codec (h264/h265), resolution (1080p/4K), bitrate, framerate, audio codec, subtitle tracks
- Store in new columns (or a `video_metadata` JSON column)
- Show on detail modal: "1080p · h264 · 5.2 Mbps · AAC"
- Filter by resolution in browse page: 720p/1080p/4K

### 8. Watch Folder / Auto-Ingest (Medium Impact / Medium Effort)

Detect new files dropped into the source directory and auto-trigger ingest.

- Config: `watch_schedule: "0 */6 * * *"` (cron format — every 6 hours)
- Add `croniter` dependency for cron expression parsing
- Background thread checks "is it time to run?" on each cron tick
- Human-readable examples in config:
  - `"0 */6 * * *"` — every 6 hours
  - `"0 3 * * *"` — daily at 3 AM
  - `"0 0 * * 0"` — weekly on Sunday midnight
  - `""` (empty) — disabled
- Web UI: "Auto-ingest" toggle + next scheduled run time display
- SSE notification: "Ingest complete: 5 new, 2 skipped"

### 9. Batch Operations (Medium Impact / Medium Effort)

Bulk actions beyond the current single-entry flag.

- Bulk re-scrape (flag multiple + trigger scrape)
- Bulk delete entries + files
- Bulk mark as reviewed/ignored
- Selection: click checkbox on cards, shift-click range select

### 10. Config & Setup UX (Low Effort)

- Add `avscraper.py check` for cookie validation (shared with item #1)
- Add test-connection button in Config page: "Test Scraper" → headless browser test
- Validation warnings in config editor (missing required cookies, invalid paths)

### 11. Uncensored Scrapers (High Impact / High Effort)

Each uncensored site has its own CID format, scraper, and metadata layout. Add incrementally.

#### Site formats

| Site | CID Pattern | Example | Scraper URL |
|------|-------------|---------|-------------|
| Caribbeancom | `\d{6}-\d{3,4}` | `123011-900` | caribbeancom.com |
| 1Pondo | `1pon[\s_-]\d{6}[\s_-]\d{3}` | `1pon-021717_484` | 1pondo.tv |
| Heyzo | `[Hh][Ee][Yy][Zz][Oo][\s_-]?\d{4}` | `HEYZO-2625` | heyzo.com |
| 10musume | `10mu[\s_-]\d{6}[\s_-]\d{2}` | `10mu-123017_01` | 10musume.com |
| Pacopacomama | `paco[\s_-]\d{6}[\s_-]\d{3}` | `paco-123017_123` | pacopacomama.com |

#### Implementation approach
- New scraper modules: `src/sites/caribbean/`, `src/sites/1pondo/`, etc.
- Each with `_scraper.py`, `_nfo.py`, `_enricher.py` following existing pattern
- New DB table per site (or a `site` column on a shared `uncensored_entries` table)
- CID detection: extend `detect_type()` in ingest.py with new patterns
- Ingest: `_Unprocessed/uncensored/{site}/{cid}/` folder structure
- Start with one site (Caribbeancom — simplest pattern), add others incrementally

### Priority Order

| # | Item | Why |
|---|------|-----|
| 1 | Cookie Health Check | Prevents wasting hours on failed scrapes |
| 2 | Studio Mapping Scraper | Comprehensive studio_map from javdb (63→300+) |
| 3 | Cover Image Caching | Fixes broken/missing posters in browse grid |
| 4 | Missing File Detection | Critical data integrity for file management |
| 5 | Browse Shortcuts | Daily-use UX — keyboard nav, infinite scroll |
| 6 | User Favorites | Simple curation: favorite flag, filter, star rating |
| 7 | Video Metadata | Resolution/codec info for filtering and display |
| 8 | Watch Folder (cron) | Automate the first pipeline step on a schedule |
| 9 | Batch Operations | Bulk management at scale (flag, delete, review) |
| 10 | Config UX | Health check button, validation warnings |
| 11 | Uncensored Scrapers | New content sources (Caribbeancom → 1Pondo → ...) |

### Docker + Desktop Compatibility

Every feature must work in both environments:

| Concern | Desktop (Native) | Docker |
|---------|-----------------|--------|
| File paths | Native OS paths | `/app/...` container paths |
| File opening | `os.startfile()` (Win) / `open` (Mac) / `xdg-open` (Linux) | `host_mount_base` translation → returns host path |
| Scheduling | Background thread | Container cron or thread |
| Config | `config.example.yaml` covers both with comments | Same |

### Tech Stack Leftovers

| Item | Notes |
|------|-------|
| macOS desktop build | Package config exists (`dmg` target in electron-builder). Need: PyInstaller on macOS runner, CI workflow variant, testing. |
| Tauri shell (replace Electron) | Rust-based desktop wrapper. Binary ~5 MB vs Electron's 180 MB. Need Rust shim layer for IPC to Python backend. Risk: moderate. |
| JavBus fallback | When JavDB returns 404 |
| Obscura browser backend | CDP-compatible drop-in for Chromium, ~30MB memory, built-in anti-fingerprinting. Evaluate when mature. |

## Tech Stack Analysis (2026-05)

### Headless browser

| Option | Bundle | Verdict |
|--------|--------|---------|
| **Playwright Chromium** (current) | ~150 MB | Right choice — both target sites require JS rendering + cookie auth. Bare HTTP won't work. |
| Playwright Firefox | ~100 MB | Viable drop-in, smaller but same API |
| Obscura | ~30 MB | Promising CDP-compatible alternative. Not production-ready yet. |

### Frontend

| Option | Bundle | Verdict |
|--------|--------|---------|
| **Flask + Jinja2 + vanilla JS** (current) | ~3 MB | Right choice — zero build step, sufficient for a single-user local tool |
| HTMX + Alpine.js | ~50 KB | Could simplify the JS further, keep Flask backend |
| React/Vue/Svelte | +5-10 MB | Overkill for this scope |

### Backend language

| Language | Frozen size | Verdict |
|----------|-------------|---------|
| **Python** (current) | ~60 MB | Right choice — rapid dev, huge ecosystem. Rewrite would be months for marginal benefit |
| C# (.NET AOT) | ~15-30 MB | Strong candidate — official Playwright bindings, native Windows interop, good web framework (ASP.NET). Worth considering for a v2 if Windows-only |
| Go | ~10 MB | Compiled, fast, great CLI. Playwright bindings are immature |
| Rust | ~5 MB | Smallest/fastest. Significantly slower to write for scraper complexity |
| Node.js | Already in Electron | Could merge backend into Electron main process, but adds complexity |
| C++ | ~3 MB | Maximum performance but painful for DOM/HTML work. No meaningful Playwright binding. Wrong tool for this job |

### Database

| Option | Verdict |
|--------|---------|
| **SQLite** (current) | Right choice — single file, zero config, perfect for 4-table metadata store |
| DuckDB | Overkill for simple metadata queries |
| JSON files | No query capability, easy to corrupt |
