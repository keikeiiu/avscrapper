# CLI Reference

All commands go through `python avscraper.py`. Run without arguments to see the help:

```bash
python avscraper.py
```

## Commands

### setup

First-run setup — copies `config.example.yaml` → `config.yaml`, checks Playwright/Chromium, creates configured directories.

```bash
python avscraper.py setup
```

### ingest

Scans a source directory for video files, detects type (FC2 or JAV) from the filename, moves files into organized folders, and seeds the database as `pending`.

```bash
python avscraper.py ingest --source ./downloads
python avscraper.py ingest --source ./downloads --dry-run
python avscraper.py ingest --source ./downloads --scrape    # auto-trigger scrapers after
python avscraper.py ingest --source ./downloads --enrich    # auto-trigger enrichers after
python avscraper.py ingest --source ./downloads --yes       # skip confirmation prompt
```

**Detection rules:**
- `FC2-PPV-123456.mp4` or `FC2 PPV 123456.mkv` → FC2, CID `123456`
- `SSIS-119.mp4` or `CAWD-122.mkv` → JAV, CID `SSIS-119`
- `-pt2`, `-part2`, `-cd2` suffixes → part numbers assigned automatically
- Unrecognized filenames → skipped, listed as "unknown"

### scrape

Fetches metadata from a site using Playwright. Reads `pending` entries from the database, scrapes each one, and writes results to SQLite.

```bash
# Scrape all pending
python avscraper.py scrape fc2ppvdb
python avscraper.py scrape javdb

# Specific IDs
python avscraper.py scrape fc2ppvdb --ids 409694,3173579
python avscraper.py scrape javdb --ids SSIS-119,CAWD-122

# Bulk from file (one CID per line or markdown list)
python avscraper.py scrape fc2ppvdb --ids-file F-drive-FC2-list.md

# Retry previously failed
python avscraper.py scrape fc2ppvdb --retry-errors

# Re-scrape flagged entries
python avscraper.py scrape fc2ppvdb --flagged

# Seed DB only (insert as pending, no scraping)
python avscraper.py scrape fc2ppvdb --ids 123456 --seed-only

# Dry-run (no DB writes)
python avscraper.py scrape fc2ppvdb --dry-run
```

**Delay control:**

| Flag | Behavior |
|------|----------|
| `--delay 5` | Fixed 5s between requests |
| `--delay "5-20"` | Random 5–20s (human-like) |

**NFO-first import:** Before making a web request, the scraper checks for an existing `.nfo` file in the video's folder. If found with a title, metadata is imported from the NFO directly — no web request. Set per-site in [README.fc2ppv.md](README.fc2ppv.md) and [README.javdb.md](README.javdb.md).

### enrich

Reads scraped metadata from SQLite and writes Kodi-compliant NFO files into the video's folder.

```bash
python avscraper.py enrich fc2ppvdb
python avscraper.py enrich javdb
python avscraper.py enrich fc2ppvdb --ids 409694
python avscraper.py enrich fc2ppvdb --dry-run
```

NFO files are written alongside the video files — they travel with the video through reorganize. Existing NFO metadata is merged additively (scraped data fills gaps, never overwrites non-empty fields, poster art never overwritten).

### flag

Marks entries for re-scraping when metadata appears wrong or incomplete.

```bash
python avscraper.py flag fc2ppvdb --ids 123456,789012
python avscraper.py flag javdb --ids SSIS-123,CAWD-456
```

Flagged entries are picked up by `scrape --flagged` or `scrape --retry-errors`.

### reorganize

Moves processed folders into a metadata-driven folder hierarchy using configurable templates.

```bash
python avscraper.py reorganize --dry-run    # preview
python avscraper.py reorganize              # execute
python avscraper.py reorganize --ids SSIS-119,ABP-948
python avscraper.py reorganize --report     # generate structure report only
```

**Safety:** Each folder is copy-verified before the source is deleted. If interrupted, source files remain intact. Already-moved entries are skipped (dest exists check).

**Template variables:**

| Variable | Source | Example |
|----------|--------|---------|
| `{cid}` | DB cid | `409694` |
| `{title}` | DB title (sanitized) | `密着ドキュメント` |
| `{title:N}` | First N chars | `{title:50}` |
| `{seller}` | FC2 seller | `六本木円光神話` |
| `{studio}` | JAV studio (after map) | `S1 NO.1 STYLE` |
| `{series}` | JAV series (after map) | `台本一切無し！！` |
| `{series:N}` | First N chars | `{series:40}` |
| `{label}` | JAV label | `S1 NO.1 STYLE` |
| `{director}` | JAV director | `嵐山みちる` |
| `{code}` | Letter prefix from CID | `SSIS` |
| `{premiered}` | Release date | `2021-07-19` |
| `{premiered:N}` | First N chars | `{premiered:4}` → `2021` |
| `{year}` | Year | `2021` |
| `{actress}` | First actress | `架乃ゆら` |
| `{rating}` | Rating | `4.16` |

**Template examples:**

```yaml
# FC2 — Seller → Year → ID + Title
fc2_structure: "FC2/{seller}/{premiered:4}/FC2-PPV-{cid} - {title:50}"

# JAV — Studio → Series → ID
jav_structure: "JAV/{studio}/{code}/{series:40}/{cid} - {title:50}"

# JAV — Director-focused
jav_structure: "JAV/{director}/{premiered:4}/{cid} - {title:40}"
```

**Studio/series maps** normalize inconsistent names from JavDB. See `config.example.yaml` for the full map of 40+ studios.

**Filename sanitization:** `: * ? " < > | \ /` are replaced with `-`. Leading/trailing spaces and dots are trimmed.

### audit

Compares metadata duration against actual video duration using ffprobe. Classifies mismatches into tiers.

```bash
python avscraper.py audit --dry-run
python avscraper.py audit --type fc2           # FC2 only
python avscraper.py audit --type jav           # JAV only
python avscraper.py audit --ids 409694,SSIS-119
```

Thresholds (configurable in `config.yaml` → `duration_audit`):
- `minor_threshold` (default 30s) — likely commercials cut or bonus content
- `hard_threshold` (default 60s) — possible wrong video or missing parts

Results are written to the database (`audit_status` column) and a dated report.

## DB Stats

```bash
python -c "
from src.db import connect, get_stats
c = connect('appdata/av_data.db')
for r in get_stats(c):
    print(f'{r[\"source\"]:12} {r[\"status\"]:10} {r[\"count\"]}')
"
```
