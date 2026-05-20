# AV Scraper — Plan

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

### 1. Cookie Health Check (High Value / Low Effort)

Verify cookies before scraping to avoid 100+ `login_required` failures.

- `python avscraper.py check` — launch headless browser with stored cookies, verify HTTP 200
- Report: "fc2ppvdb: OK / javdb: session expired"
- Web UI: health status indicator on dashboard + Config page "Test Scraper" button

### 2. Studio Mapping Scraper (Low-Medium Effort)

Scrape `javdb.com/makers` + `/makers/uncensored` for a comprehensive `studio_map`.

- Reuse Playwright + `_jdb_session` cookie. Script: `python avscraper.py update-studios`
- Extract primary name + alternate names per maker; map Japanese → English canonical
- `studio_map` grows from 63 → 300+ entries. Merge with existing, keep user edits.
- Uncensored page requires login (redirects `/login` without session)
- Known uncensored: Caribbeancom, 1Pondo, Heyzo, 10musume, Pacopacomama, etc.

### 3. Cover Image Caching

`cover_url` points to external CDNs — download locally to avoid broken/missing posters.

- Add `cover_path` column. On scrape, download to `appdata/covers/{cid}.jpg`
- `/api/cover/<cid>` endpoint. Browse uses local cover, remote as fallback.
- Backfill existing: `--download-covers` flag on scrape

### 4. Missing File Detection

Detect entries whose files have been moved/deleted outside the app.

- Extend `path_audit.py` to check entries with no file records
- "Files missing" filter + badge on browse page

### 5. Browse Page Improvements

- **Keyboard shortcuts**: `j`/`k` next/prev, `Enter` detail, `f` play, `Esc` close
- **Infinite scroll**: auto-load next page near bottom
- **Grid density toggle**: small/medium/large cards
- **Card right-click**: open file, open folder, copy CID, flag

### 6. User Favorites

Simple curation layer on top of scraped metadata.

- `favorite` boolean column on entries. Filter in browse. Toggle from detail modal.
- `user_notes` TEXT and `user_rating` INTEGER (1-5) for later iteration
- `watched` deferred — app doesn't provide a watch function yet

### 7. Video Metadata Extraction

Beyond duration, extract codec, resolution, bitrate, framerate, audio tracks via ffprobe.

- Store in `video_metadata` JSON column. Show in detail modal: "1080p · h264 · 5.2 Mbps · AAC"
- Filter by resolution in browse: 720p/1080p/4K

### 8. Watch Folder / Auto-Ingest

Detect new files and trigger ingest on a cron schedule.

- Config: `watch_schedule: "0 */6 * * *"` (cron format). Uses `croniter` package.
- Background thread. Web UI: toggle + next-run display + SSE notifications.

### 9. Uncensored Scrapers

Each uncensored site has its own CID format. Add incrementally.

| Site | CID Pattern | Example |
|------|-------------|---------|
| Caribbeancom | `\\d{6}-\\d{3,4}` | `123011-900` |
| 1Pondo | `1pon[\\s_-]\\d{6}[\\s_-]\\d{3}` | `1pon-021717_484` |
| Heyzo | `[Hh][Ee][Yy][Zz][Oo][\\s_-]?\\d{4}` | `HEYZO-2625` |
| 10musume | `10mu[\\s_-]\\d{6}[\\s_-]\\d{2}` | `10mu-123017_01` |
| Pacopacomama | `paco[\\s_-]\\d{6}[\\s_-]\\d{3}` | `paco-123017_123` |

- New `src/sites/{site}/` modules: scraper, NFO, enricher following existing pattern
- New DB table per site (or `site` column on shared `uncensored_entries`)
- Extend `detect_type()` in ingest.py. Start with Caribbeancom.

### Platform Notes

| Concern | Desktop (Native) | Docker |
|---------|-----------------|--------|
| File paths | Native Windows paths | `/app/...` container paths |
| File opening | `os.startfile()` | `host_mount_base` translation |
| Scheduling | Background thread | Container cron or thread |
| Config | `config.example.yaml` covers both with comments |

### Tech Stack Leftovers

| Item | Notes |
|------|-------|
| macOS desktop build | Package config exists. Need PyInstaller on macOS runner + CI workflow. |
| Tauri shell | Replace Electron, ~5 MB binary. Need Rust IPC bridge to Python backend. |
| JavBus fallback | When JavDB returns 404 |
| Obscura browser backend | CDP-compatible, ~30MB memory, anti-fingerprinting. Evaluate when mature. |

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
