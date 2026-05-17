# AV Scraper — Plan

## Current Architecture

```
avscrappertools/
├── avscraper.py              # entry point (ingest/scrape/enrich/audit/reorganize)
├── config.example.yaml       # template config (relative paths, no cookies)
├── docker-compose.yml        # Docker Compose deployment
├── Dockerfile                # Docker image build
├── requirements.txt          # pyyaml, playwright
├── reports/                  # dated log reports
└── src/
    ├── db.py                 # SQLite (4 tables), find_directories(), CRUD
    ├── ingest.py             # auto-detect FC2/JAV, organize, seed DB
    ├── reorganize.py         # metadata-driven folder hierarchy
    ├── duration_audit.py     # ffprobe duration check, tiered flags
    └── sites/
        ├── base_scraper.py   # shared scraper framework (CLI, rate-limit)
        ├── fc2ppvdb/
        │   ├── fc2ppvdb_scraper.py
        │   ├── fc2_nfo.py
        │   └── fc2_enricher.py
        └── javdb/
            ├── javdb_scraper.py
            ├── jav_nfo.py
            └── jav_enricher.py
```

## Status

| Component | Status |
|-----------|--------|
| FC2 scraper + NFO + enricher | ✅ |
| JavDB scraper + NFO + enricher | ✅ |
| Ingest (auto-detect FC2/JAV/Chinese) | ✅ |
| Reorganizer (customizable templates) | ✅ |
| Duration audit (ffprobe, two-tier flagging) | ✅ |
| Docker image + Compose + GitHub Actions CI | ✅ |
| Security (XML escaping, parse guards, Bandit/pip-audit CI) | ✅ |
| Chinese AV auto-detection (`region` column) | ✅ |
| JavDB login wall vs 404 distinction | ✅ |
| `{title:N}`, `{series:N}`, `{code}` template vars | ✅ |
| Studio/series maps (40+ JAV, 18 Chinese) | ✅ |

## Database

4 tables: `fc2_entries`, `fc2_files`, `jav_entries`, `jav_files`. `jav_entries` has `region` column (jav/chinese). Both entries tables have `audit_status` + `last_audited`.

## Workflow

```
downloads/ → ingest.py → processed/
                              ↓
               scraper.py → av_data.db
                              ↓
               enricher.py → .nfo files
                              ↓
               reorganize.py → reorganized/{FC2,JAV}/{structure}/
                              ↓
               duration_audit.py → report + audit tags
```

## CLI (via avscraper.py)

```bash
python avscraper.py setup
python avscraper.py ingest --dry-run
python avscraper.py scrape fc2ppvdb --delay "5-20"
python avscraper.py scrape javdb --delay "5-20"
python avscraper.py enrich fc2ppvdb
python avscraper.py enrich javdb
python avscraper.py reorganize --dry-run
python avscraper.py audit --dry-run
```

## Future

| Item | Notes |
|------|-------|
| Uncensored JAV scraper | 123011-900 pattern. Caribbean/1Pondo/Heyzo |
| JavBus fallback | When JavDB returns 404 |
| F-drive batch scrape | 617 FC2 IDs pending |
| Madou dedicated scraper | Low priority — JavDB covers CUS/NHAV |
| Obscura browser backend | Evaluate when more mature (v0.1.2 as of 2026-05). CDP-compatible drop-in for Chromium, ~30MB memory, built-in anti-fingerprinting. Would replace Playwright's bundled Chromium via `connect_over_cdp`. Risk: early-stage, may not support all Playwright APIs used by scrapers. |
