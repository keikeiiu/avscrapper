# Decision Points

Items requiring human judgment before implementation. Checked boxes are implemented and verified.

## Completed (2026-05-21)

- [x] **1. Cookie Health Check** — `avscraper.py check` + web UI "Test Scrapers" button. Both sites verified working.
- [x] **2. Studio Mapping Scraper** — `avscraper.py update-studios`. Scrapes javdb.com/makers for studio_map. Not yet executed (needs real cookies to scrape).
- [x] **3. Cover Image Caching** — Downloads covers on scrape, serves from `/api/cover?cid=X`, falls back to remote redirect.
- [x] **4. Missing File Detection** — `path_audit.py` already handles this with `--repair` flag.
- [x] **5. Browse Keyboard Shortcuts** — `j/k` nav, `Enter` open, `f` play first file, `Esc` close modal.
- [x] **6. User Data Layer** — Favorites, 1-5 rating, notes. API: `GET/POST /api/user/<cid>`.
- [x] **7. Video Metadata** — ffprobe JSON extraction (codec, resolution, bitrate, fps). API: `GET /api/metadata/<cid>`.
- [x] **8. Watch Folder** — Cron-based auto-ingest. Set `watch_schedule` in config (e.g. `"0 */6 * * *"`).
- [x] **9. Batch Operations** — `POST /api/batch/flag` and `POST /api/batch/delete` with CID list.
- [x] **10. Config UX** — "Test Scrapers" button on Config page validates cookies live.

## Needs Decision

### 11. Uncensored Scrapers

**Scope decision needed.** Sites to implement in order:

| Site | CID Pattern | Notes |
|------|-------------|-------|
| Caribbeancom | `123011-900` | Simplest pattern, good first target |
| 1Pondo | `1pon-021717_484` | Same CDN infrastructure as Caribbean |
| Heyzo | `HEYZO-2625` | Own CDN, different layout |
| 10musume | `10mu-123017_01` | Same CDN as Caribbean/1Pondo |
| Pacopacomama | `paco-123017_123` | Same CDN |

**Decision: Which site to implement first?** Caribbeancom is recommended — simplest CID format, shared CDN with others.

**Auth:** Most uncensored sites are public (no login required). Some may need age verification cookies.

**DB design:**
- Option A: New table per site (like FC2/JAV) — more code, cleaner separation
- Option B: Single `uncensored_entries` table with `site` column — less code, harder to query per-site

**Decision: A or B?** Option B is faster to ship, Option A is cleaner long-term.

### macOS Desktop Build

Package config exists (`dmg` target in electron-builder). Need:
- PyInstaller on macOS runner
- CI workflow variant for macOS
- Testing on actual Mac hardware

### Tauri Shell (Replace Electron)

Binary ~5 MB vs Electron's 180 MB. Need Rust shim for IPC to Python backend. Risk: moderate. Worth evaluating after desktop app is stable on Electron.

### JavBus Fallback

When JavDB returns 404, try javbus.com as secondary source. Low priority — JavDB covers >95% of JAV IDs.

### Obscura Browser

CDP-compatible Chromium replacement (~30MB). Built-in anti-fingerprinting. Not production-ready yet (v0.1.2 as of 2026-05). Re-evaluate quarterly.

## Docker Config Init Issue

The first-run config init patches paths to absolute in Docker. But if the user copies a config.yaml from local (relative paths), the second run doesn't re-patch. The config ends up with `db_path: ./appdata/av_data.db` which resolves to `/app/appdata/appdata/av_data.db` (wrong).

**Fix applied:** Always resolve paths at startup with `os.path.isabs()` check. The `load_config()` function already handles this — the issue was the user's config had the wrong base path.
