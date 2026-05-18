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

## Future

| Item | Notes |
|------|-------|
| Uncensored JAV scraper | 123011-900 pattern. Caribbean/1Pondo/Heyzo |
| JavBus fallback | When JavDB returns 404 |
| Obscura browser backend | Evaluate when more mature. CDP-compatible drop-in for Chromium, ~30MB memory, built-in anti-fingerprinting. Would replace Playwright's bundled Chromium via `connect_over_cdp`. Risk: early-stage. |
