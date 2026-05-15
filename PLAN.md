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
| Folder reorganizer | ⬜ planned |

---

# Folder Reorganizer — Metadata-Driven Hierarchy

## Context

Flat `FC2-PPV-{id}/` structure works for tools but not for browsing. Reorganizer reads scraped metadata from DB and moves folders into a customizable hierarchy.

## Config

```yaml
reorganize:
  target: "C:/Users/keiwa/Downloads/reorganized_"
  fc2_template: "{seller}/{premiered:4}/FC2-PPV-{cid}"
  jav_template: "{studio}/{series}/{cid}"
```

## Template Variables

| Variable | Source | Example |
|----------|--------|---------|
| `{cid}` | DB cid | 409694, ABP-948 |
| `{title}` | DB title | 密着ドキュメント |
| `{seller}` | FC2 seller | 六本木円光神話 |
| `{studio}` | JAV studio | S1 NO.1 STYLE |
| `{series}` | JAV series | ※台本一切無し！！ |
| `{label}` | JAV label | S1 NO.1 STYLE |
| `{director}` | JAV director | 嵐山みちる |
| `{premiered}` | release_date | 2021-07-19 |
| `{premiered:N}` | first N chars | `{premiered:4}` → 2021 |
| `{actress}` | first actress | 架乃ゆら |
| `{rating}` | rating | 4.16 |
| `{year}` | year | 2021 |

## Safety: Copy-Verify-Delete

Each file is processed atomically: copy → verify size → delete source. If interrupted, both copies exist. Re-run skips already-moved entries. Report documents every move.

## CLI

```bash
python reorganize.py --dry-run     # preview
python reorganize.py               # execute (copy-verify-delete)
python reorganize.py --ids ABP-948 # specific entries
```

## New File

| File | Purpose |
|------|---------|
| `src/reorganize.py` | CLI: read DB, expand template, copy-verify-delete |

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
