# AV Scraper — Plan

## Current Architecture

```
avscrappertools/
├── config.yaml              # shared: db_path, report_dir, ingest targets, site sections
├── reports/                 # dated log-style reports
├── src/
│   ├── db.py                # SQLite: fc2/jav tables, find_directories(), CRUD
│   ├── ingest.py            # auto-detect type, organize files, seed DB
│   └── sites/
│       ├── base_scraper.py  # shared scraper framework (CLI, rate-limit, DB writes)
│       ├── fc2ppvdb/
│       │   ├── fc2ppvdb_scraper.py   # Playwright → fc2ppvdb.com
│       │   ├── fc2_nfo.py            # FC2 Kodi NFO builder
│       │   └── fc2_enricher.py       # writes NFOs next to video files
│       └── javdb/
│           ├── javdb_scraper.py      # Playwright → javdb.com
│           ├── jav_nfo.py            # JAV Kodi NFO builder
│           └── jav_enricher.py       # writes NFOs next to video files
└── README.md / .fc2ppv / .javdb
```

## Status

| Component | Status |
|-----------|--------|
| FC2 scraper + NFO + enricher | ✅ working |
| JavDB scraper + NFO + enricher | ✅ working |
| Ingest tool (auto-detect FC2/JAV) | ✅ working |
| Dated report logs | ✅ working |
| Shared `find_directories` | ✅ working |
| Duration audit | ⬜ deferred (no MP4 access) |
| Chinese AV / Madou scraper | ⬜ planned |
| Uncensored JAV support | ⬜ planned |

## Workflow

```
Downloads → ingest.py → organize + seed DB
                              ↓
               scraper.py → fetch metadata → DB
                              ↓
               enricher.py → write .nfo files
```

## Detection Strategy (for new sites)

Current: `FC2-PPV-\d+` → FC2, `[A-Z]+-\d+` → JAV.
Future: prefix blacklist splits Madou from JAV. `--type` flag for explicit control.

## Future: Madou (Chinese AV)

Same ID pattern as JAV (`MD-0123`, `MADOU-456`). Need prefix-based detection:
- `sites/madou/` with scraper + nfo + enricher
- Config: `ingest.madou_target`
- Known prefixes: MD, MADOU, MMZ, MSD, MDX, MDSR, MDWP, etc.

## Future: Uncensored JAV

Could use separate scrapers (Caribbean, 1Pondo, Heyzo) or JavDB's existing uncensored flag. NFO already supports `<uncensored>` tag.
