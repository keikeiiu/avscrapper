import sqlite3
import json
import os


def connect(db_path):
    """Return a connection with WAL mode enabled."""
    os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.row_factory = sqlite3.Row
    return conn


def init_db(db_path):
    """Create all tables if they don't exist."""
    conn = connect(db_path)
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS fc2_entries (
            cid              TEXT PRIMARY KEY,
            full_number      TEXT,
            title            TEXT,
            seller           TEXT,
            actress          TEXT,
            release_date     TEXT,
            duration         TEXT,
            duration_seconds REAL,
            cover_url        TEXT,
            tags             TEXT,
            outline          TEXT,
            url              TEXT,
            source           TEXT,
            mosaic           TEXT,
            status           TEXT DEFAULT 'pending',
            error_message    TEXT,
            scraped_at       TEXT,
            audit_status     TEXT,
            last_audited     TEXT,
            raw_json         TEXT
        );

        CREATE TABLE IF NOT EXISTS fc2_files (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            cid              TEXT NOT NULL,
            directory_path   TEXT,
            file_path        TEXT,
            file_size        INTEGER,
            duration_seconds REAL,
            duration_str     TEXT,
            part_number      INTEGER DEFAULT 1,
            auto_part        INTEGER DEFAULT 0,
            FOREIGN KEY (cid) REFERENCES fc2_entries(cid)
        );

        CREATE TABLE IF NOT EXISTS jav_entries (
            cid              TEXT PRIMARY KEY,
            full_number      TEXT,
            title            TEXT,
            title_en         TEXT,
            plot             TEXT,
            studio           TEXT,
            label            TEXT,
            series           TEXT,
            director         TEXT,
            release_date     TEXT,
            year             TEXT,
            runtime          TEXT,
            runtime_seconds  INT,
            cover_url        TEXT,
            fanart_urls      TEXT,
            genres           TEXT,
            actors           TEXT,
            rating           REAL,
            votes            INT,
            uncensored       INT DEFAULT 0,
            region           TEXT DEFAULT 'jav',
            url              TEXT,
            source           TEXT,
            status           TEXT DEFAULT 'pending',
            error_message    TEXT,
            scraped_at       TEXT,
            audit_status     TEXT,
            last_audited     TEXT,
            raw_json         TEXT
        );

        CREATE TABLE IF NOT EXISTS jav_files (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            cid              TEXT NOT NULL,
            directory_path   TEXT,
            file_path        TEXT,
            file_size        INTEGER,
            duration_seconds REAL,
            duration_str     TEXT,
            part_number      INTEGER DEFAULT 1,
            auto_part        INTEGER DEFAULT 0,
            FOREIGN KEY (cid) REFERENCES jav_entries(cid)
        );

        CREATE TABLE IF NOT EXISTS uncensored_entries (
            cid              TEXT PRIMARY KEY,
            site             TEXT NOT NULL,
            full_number      TEXT,
            title            TEXT,
            title_en         TEXT,
            plot             TEXT,
            studio           TEXT,
            label            TEXT,
            series           TEXT,
            director         TEXT,
            release_date     TEXT,
            year             TEXT,
            runtime          TEXT,
            runtime_seconds  INT,
            cover_url        TEXT,
            fanart_urls      TEXT,
            genres           TEXT,
            actors           TEXT,
            rating           REAL,
            votes            INT,
            url              TEXT,
            source           TEXT,
            status           TEXT DEFAULT 'pending',
            error_message    TEXT,
            scraped_at       TEXT,
            audit_status     TEXT,
            last_audited     TEXT,
            cover_path       TEXT,
            user_notes       TEXT,
            user_rating      TEXT,
            favorite         TEXT,
            video_metadata   TEXT,
            raw_json         TEXT
        );

        CREATE TABLE IF NOT EXISTS uncensored_files (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            cid              TEXT NOT NULL,
            directory_path   TEXT,
            file_path        TEXT,
            file_size        INTEGER,
            duration_seconds REAL,
            duration_str     TEXT,
            part_number      INTEGER DEFAULT 1,
            auto_part        INTEGER DEFAULT 0,
            path_status      TEXT,
            FOREIGN KEY (cid) REFERENCES uncensored_entries(cid)
        );

        CREATE INDEX IF NOT EXISTS idx_fc2_entries_status ON fc2_entries(status);
        CREATE INDEX IF NOT EXISTS idx_fc2_entries_source ON fc2_entries(source);
        CREATE INDEX IF NOT EXISTS idx_fc2_files_cid ON fc2_files(cid);

        CREATE INDEX IF NOT EXISTS idx_jav_entries_status ON jav_entries(status);
        CREATE INDEX IF NOT EXISTS idx_jav_entries_source ON jav_entries(source);
        CREATE INDEX IF NOT EXISTS idx_jav_files_cid ON jav_files(cid);

        CREATE INDEX IF NOT EXISTS idx_uncensored_entries_status ON uncensored_entries(status);
        CREATE INDEX IF NOT EXISTS idx_uncensored_entries_site ON uncensored_entries(site);
        CREATE INDEX IF NOT EXISTS idx_uncensored_files_cid ON uncensored_files(cid);
    """)
    # Migrate existing databases
    for table in ("fc2_entries", "jav_entries", "uncensored_entries"):
        for col in ("audit_status", "last_audited", "region", "cover_path", "user_notes", "user_rating", "favorite", "video_metadata"):
            try:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} TEXT")
            except sqlite3.OperationalError:
                pass
    for table in ("fc2_files", "jav_files"):
        for col in ("path_status",):
            try:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} TEXT")
            except sqlite3.OperationalError:
                pass
    for col in ("chinese_sub", "leaked"):
        try:
            conn.execute(f"ALTER TABLE jav_entries ADD COLUMN {col} INTEGER DEFAULT 0")
        except sqlite3.OperationalError:
            pass
    conn.commit()
    conn.close()


def insert_pending(conn, cid, full_number, source, url=None):
    """Insert a new entry as pending. No-op if already exists."""
    conn.execute("""
        INSERT OR IGNORE INTO fc2_entries (cid, full_number, source, url, status)
        VALUES (?, ?, ?, ?, 'pending')
    """, (cid, full_number, source, url))
    conn.commit()


def insert_file(conn, cid, directory_path, file_path, file_size=None, part_number=1):
    """Insert a file row for a CID."""
    conn.execute("""
        INSERT INTO fc2_files (cid, directory_path, file_path, file_size, part_number)
        VALUES (?, ?, ?, ?, ?)
    """, (cid, directory_path, file_path, file_size, part_number))
    conn.commit()


def upsert_scraped(conn, cid, data, source):
    """Upsert scraped data into fc2_entries. data is a dict from the scraper."""
    tags_json = json.dumps(data.get("tags", []), ensure_ascii=False)
    conn.execute("""
        INSERT INTO fc2_entries (cid, full_number, title, seller, actress,
            release_date, duration, duration_seconds, cover_url, tags,
            outline, url, source, mosaic, status, scraped_at, raw_json)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'scraped', datetime('now'), ?)
        ON CONFLICT(cid) DO UPDATE SET
            title=excluded.title, seller=excluded.seller, actress=excluded.actress,
            release_date=excluded.release_date, duration=excluded.duration,
            duration_seconds=excluded.duration_seconds, cover_url=excluded.cover_url,
            tags=excluded.tags, outline=excluded.outline, url=excluded.url,
            source=excluded.source, mosaic=excluded.mosaic,
            status='scraped', scraped_at=datetime('now'), raw_json=excluded.raw_json
    """, (
        cid,
        data.get("full_number", f"FC2-PPV-{cid}"),
        data.get("title"),
        data.get("seller"),
        data.get("actress"),
        data.get("release_date"),
        data.get("duration"),
        data.get("duration_seconds"),
        data.get("cover_url"),
        tags_json,
        data.get("outline"),
        data.get("url"),
        source,
        data.get("mosaic"),
        json.dumps(data, ensure_ascii=False),
    ))
    _cache_cover(conn, "fc2_entries", cid, data.get("cover_url"))
    conn.commit()
    """Update status and optional error message for a CID."""
    conn.execute("""
        UPDATE fc2_entries SET status=?, error_message=?, scraped_at=datetime('now')
        WHERE cid=?
    """, (status, error_message, cid))
    conn.commit()


def mark_flagged(conn, cid):
    """Mark an FC2 entry as flagged for re-scrape."""
    conn.execute("UPDATE fc2_entries SET status='flagged', error_message=NULL WHERE cid=?", (cid,))
    conn.commit()


def get_pending(conn, source=None):
    """Return all rows with status='pending', optionally filtered by source."""
    if source:
        rows = conn.execute(
            "SELECT * FROM fc2_entries WHERE status='pending' AND source=? ORDER BY cid", (source,)
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM fc2_entries WHERE status='pending' ORDER BY cid"
        ).fetchall()
    return [dict(r) for r in rows]


def get_scraped(conn, source=None):
    """Return all rows with status='scraped'."""
    if source:
        rows = conn.execute(
            "SELECT * FROM fc2_entries WHERE status='scraped' AND source=? ORDER BY cid", (source,)
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM fc2_entries WHERE status='scraped' ORDER BY cid"
        ).fetchall()
    return [dict(r) for r in rows]


def get_errors(conn, source=None):
    """Return all rows with status='error', '404', or 'flagged'."""
    if source:
        rows = conn.execute(
            "SELECT * FROM fc2_entries WHERE status IN ('error','404','flagged') AND source=? ORDER BY cid", (source,)
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM fc2_entries WHERE status IN ('error','404','flagged') ORDER BY cid"
        ).fetchall()
    return [dict(r) for r in rows]


def get_flagged(conn, source=None):
    """Return all rows with status='flagged'."""
    if source:
        rows = conn.execute(
            "SELECT * FROM fc2_entries WHERE status='flagged' AND source=? ORDER BY cid", (source,)
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM fc2_entries WHERE status='flagged' ORDER BY cid"
        ).fetchall()
    return [dict(r) for r in rows]


import os as _os
VIDEO_EXTS = {".mp4", ".mkv", ".avi", ".wmv", ".mov", ".ts", ".flv", ".webm", ".rmvb", ".rm", ".m4v", ".divx", ".f4v", ".asf", ".wmv"}


def find_directories(targets, id_extractor):
    """Walk target dirs, return {cid: best_dir_path}.
    Prefers directories that contain video files.

    Args:
        targets: list of base directories to scan
        id_extractor: callable(folder_name) → cid | None
    """
    cid_dirs = {}
    for base in targets:
        if not _os.path.isdir(base):
            continue
        for root, dirs, files in _os.walk(base):
            for name in dirs:
                cid = id_extractor(name)
                if cid is None:
                    continue
                full = _os.path.join(root, name)
                has_video = any(
                    _os.path.splitext(f)[1].lower() in VIDEO_EXTS
                    for f in _os.listdir(full) if _os.path.isfile(_os.path.join(full, f))
                )
                if cid not in cid_dirs or (has_video and len(root) < len(cid_dirs[cid])):
                    cid_dirs[cid] = full
    return cid_dirs


def get_stats(conn):
    """Return status counts across both tables."""
    fc2 = conn.execute("""
        SELECT source, status, COUNT(*) as count
        FROM fc2_entries GROUP BY source, status ORDER BY source, status
    """).fetchall()
    jav = conn.execute("""
        SELECT source, status, COUNT(*) as count
        FROM jav_entries GROUP BY source, status ORDER BY source, status
    """).fetchall()
    return [dict(r) for r in fc2] + [dict(r) for r in jav]


# ── JAV-specific CRUD ──

def insert_pending_jav(conn, cid, full_number, source, url=None, chinese_sub=0):
    """Insert a JAV entry as pending. No-op if already exists."""
    conn.execute("""
        INSERT OR IGNORE INTO jav_entries (cid, full_number, source, url, status, chinese_sub)
        VALUES (?, ?, ?, ?, 'pending', ?)
    """, (cid, full_number, source, url, chinese_sub))
    conn.commit()


def insert_file_jav(conn, cid, directory_path, file_path, file_size=None, part_number=1):
    """Insert a file row for a JAV CID."""
    conn.execute("""
        INSERT INTO jav_files (cid, directory_path, file_path, file_size, part_number)
        VALUES (?, ?, ?, ?, ?)
    """, (cid, directory_path, file_path, file_size, part_number))
    conn.commit()


def upsert_scraped_jav(conn, cid, data, source):
    """Upsert scraped JAV data into jav_entries."""
    conn.execute("""
        INSERT INTO jav_entries (cid, full_number, title, title_en, plot,
            studio, label, series, director, release_date, year,
            runtime, runtime_seconds, cover_url, fanart_urls, genres,
            actors, rating, votes, uncensored, region, url, source,
            status, scraped_at, raw_json)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'scraped', datetime('now'), ?)
        ON CONFLICT(cid) DO UPDATE SET
            title=excluded.title, title_en=excluded.title_en, plot=excluded.plot,
            studio=excluded.studio, label=excluded.label, series=excluded.series,
            director=excluded.director, release_date=excluded.release_date,
            year=excluded.year, runtime=excluded.runtime,
            runtime_seconds=excluded.runtime_seconds, cover_url=excluded.cover_url,
            fanart_urls=excluded.fanart_urls, genres=excluded.genres,
            actors=excluded.actors, rating=excluded.rating, votes=excluded.votes,
            uncensored=excluded.uncensored, region=excluded.region,
            url=excluded.url, source=excluded.source,
            status='scraped', scraped_at=datetime('now'), raw_json=excluded.raw_json
    """, (
        cid,
        data.get("full_number", cid),
        data.get("title"),
        data.get("title_en"),
        data.get("plot"),
        data.get("studio"),
        data.get("label"),
        data.get("series"),
        data.get("director"),
        data.get("release_date"),
        data.get("year"),
        data.get("runtime"),
        data.get("runtime_seconds"),
        data.get("cover_url"),
        json.dumps(data.get("fanart_urls", []), ensure_ascii=False),
        json.dumps(data.get("genres", []), ensure_ascii=False),
        json.dumps(data.get("actors", []), ensure_ascii=False),
        data.get("rating"),
        data.get("votes"),
        data.get("uncensored", 0),
        data.get("region", "jav"),
        data.get("url"),
        source,
        json.dumps(data, ensure_ascii=False),
    ))
    _cache_cover(conn, "jav_entries", cid, data.get("cover_url"))
    conn.commit()


def upsert_file(conn, cid, directory_path, file_path, file_size=None, part_number=1):
    """Insert or update an FC2 file record keyed by (cid, file_path)."""
    existing = conn.execute(
        "SELECT id FROM fc2_files WHERE cid=? AND file_path=?", (cid, file_path)
    ).fetchone()
    if existing:
        conn.execute(
            "UPDATE fc2_files SET directory_path=?, file_size=?, part_number=?, path_status='ok' WHERE id=?",
            (directory_path, file_size, part_number, existing["id"])
        )
    else:
        conn.execute(
            "INSERT INTO fc2_files (cid, directory_path, file_path, file_size, part_number, path_status) VALUES (?,?,?,?,?,'ok')",
            (cid, directory_path, file_path, file_size, part_number)
        )
    conn.commit()


def upsert_file_jav(conn, cid, directory_path, file_path, file_size=None, part_number=1):
    """Insert or update a JAV file record keyed by (cid, file_path)."""
    existing = conn.execute(
        "SELECT id FROM jav_files WHERE cid=? AND file_path=?", (cid, file_path)
    ).fetchone()
    if existing:
        conn.execute(
            "UPDATE jav_files SET directory_path=?, file_size=?, part_number=?, path_status='ok' WHERE id=?",
            (directory_path, file_size, part_number, existing["id"])
        )
    else:
        conn.execute(
            "INSERT INTO jav_files (cid, directory_path, file_path, file_size, part_number, path_status) VALUES (?,?,?,?,?,'ok')",
            (cid, directory_path, file_path, file_size, part_number)
        )
    conn.commit()


def mark_path_status(conn, table, file_id, status):
    """Update path_status for a file record (ok / stale / missing)."""
    conn.execute(f"UPDATE {table} SET path_status=? WHERE id=?", (status, file_id))
    conn.commit()


def get_files_with_paths(conn, table):
    """Return file records that have a non-null file_path."""
    rows = conn.execute(
        f"SELECT * FROM {table} WHERE file_path IS NOT NULL AND file_path != ''"
    ).fetchall()
    return [dict(r) for r in rows]


def set_cover_path(conn, table, cid, cover_path):
    """Update cover_path for an entry."""
    conn.execute(
        f"UPDATE {table} SET cover_path=? WHERE cid=?",
        (cover_path, cid)
    )
    conn.commit()


def _cache_cover(conn, table, cid, cover_url):
    """Download and cache cover image after upsert. Non-blocking — errors are silent."""
    if not cover_url:
        return
    try:
        db_dir = os.path.dirname(conn.execute("PRAGMA database_list").fetchone()[2] or ".")
        covers_dir = os.path.join(db_dir, "covers")
        local_path = download_cover(cid, cover_url, covers_dir)
        if local_path:
            set_cover_path(conn, table, cid, local_path)
    except Exception:
        pass


def download_cover(cid, cover_url, covers_dir):
    """Download cover image to local cache. Returns local path or None."""
    import os
    import urllib.request
    os.makedirs(covers_dir, exist_ok=True)
    ext = ".jpg"
    if cover_url:
        parsed = cover_url.split("?")[0]
        _, e = os.path.splitext(parsed)
        if e in (".png", ".webp", ".gif"):
            ext = e
    path = os.path.join(covers_dir, f"{cid}{ext}")
    if os.path.exists(path):
        return path
    try:
        req = urllib.request.Request(cover_url, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        })
        with urllib.request.urlopen(req, timeout=15) as resp:
            with open(path, "wb") as f:
                f.write(resp.read())
        return path
    except Exception:
        return None


def get_stale_files(conn, table):
    """Return file records with path_status='stale'."""
    rows = conn.execute(
        f"SELECT * FROM {table} WHERE path_status='stale'"
    ).fetchall()
    return [dict(r) for r in rows]


def mark_status_jav(conn, cid, status, error_message=None):
    """Update status for a JAV CID."""
    conn.execute("""
        UPDATE jav_entries SET status=?, error_message=?, scraped_at=datetime('now')
        WHERE cid=?
    """, (status, error_message, cid))
    conn.commit()


def mark_flagged_jav(conn, cid):
    """Mark a JAV entry as flagged for re-scrape."""
    conn.execute("UPDATE jav_entries SET status='flagged', error_message=NULL WHERE cid=?", (cid,))
    conn.commit()


def get_pending_jav(conn, source=None):
    """Return pending JAV entries."""
    if source:
        rows = conn.execute(
            "SELECT * FROM jav_entries WHERE status='pending' AND source=? ORDER BY cid", (source,)
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM jav_entries WHERE status='pending' ORDER BY cid"
        ).fetchall()
    return [dict(r) for r in rows]


def get_scraped_jav(conn, source=None):
    """Return scraped JAV entries."""
    if source:
        rows = conn.execute(
            "SELECT * FROM jav_entries WHERE status='scraped' AND source=? ORDER BY cid", (source,)
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM jav_entries WHERE status='scraped' ORDER BY cid"
        ).fetchall()
    return [dict(r) for r in rows]


def get_errors_jav(conn, source=None):
    """Return JAV entries with error/404/flagged status."""
    if source:
        rows = conn.execute(
            "SELECT * FROM jav_entries WHERE status IN ('error','404','flagged') AND source=? ORDER BY cid", (source,)
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM jav_entries WHERE status IN ('error','404','flagged') ORDER BY cid"
        ).fetchall()
    return [dict(r) for r in rows]


def get_flagged_jav(conn, source=None):
    """Return JAV entries with flagged status."""
    if source:
        rows = conn.execute(
            "SELECT * FROM jav_entries WHERE status='flagged' AND source=? ORDER BY cid", (source,)
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM jav_entries WHERE status='flagged' ORDER BY cid"
        ).fetchall()
    return [dict(r) for r in rows]


# ── Uncensored CRUD ──

def insert_pending_uncensored(conn, cid, full_number, source, url=None):
    """Insert an uncensored entry as pending. No-op if already exists."""
    conn.execute(
        "INSERT OR IGNORE INTO uncensored_entries (cid, full_number, source, site, url, status) VALUES (?, ?, ?, ?, ?, 'pending')",
        (cid, full_number, source, source, url)
    )
    conn.commit()


def upsert_scraped_uncensored(conn, cid, data, source, site):
    """Upsert scraped uncensored data into uncensored_entries."""
    conn.execute(
        """INSERT INTO uncensored_entries (cid, site, full_number, title, title_en, plot,
            studio, label, series, director, release_date, year,
            runtime, runtime_seconds, cover_url, fanart_urls, genres,
            actors, rating, votes, url, source,
            status, scraped_at, raw_json)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'scraped', datetime('now'), ?)
        ON CONFLICT(cid) DO UPDATE SET
            title=excluded.title, title_en=excluded.title_en, plot=excluded.plot,
            studio=excluded.studio, label=excluded.label, series=excluded.series,
            director=excluded.director, release_date=excluded.release_date,
            year=excluded.year, runtime=excluded.runtime,
            runtime_seconds=excluded.runtime_seconds, cover_url=excluded.cover_url,
            fanart_urls=excluded.fanart_urls, genres=excluded.genres,
            actors=excluded.actors, rating=excluded.rating, votes=excluded.votes,
            url=excluded.url, source=excluded.source,
            status='scraped', scraped_at=datetime('now'), raw_json=excluded.raw_json""",
        (cid, site, data.get("full_number", cid), data.get("title"), data.get("title_en"),
         data.get("plot"), data.get("studio"), data.get("label"), data.get("series"),
         data.get("director"), data.get("release_date"), data.get("year"),
         data.get("runtime"), data.get("runtime_seconds"), data.get("cover_url"),
         json.dumps(data.get("fanart_urls", []), ensure_ascii=False),
         json.dumps(data.get("genres", []), ensure_ascii=False),
         json.dumps(data.get("actors", []), ensure_ascii=False),
         data.get("rating"), data.get("votes"), data.get("url"), source,
         json.dumps(data, ensure_ascii=False))
    )
    _cache_cover(conn, "uncensored_entries", cid, data.get("cover_url"))
    conn.commit()


def mark_flagged_uncensored(conn, cid):
    """Mark an uncensored entry as flagged for re-scrape."""
    conn.execute("UPDATE uncensored_entries SET status='flagged', error_message=NULL WHERE cid=?", (cid,))
    conn.commit()


def get_pending_uncensored(conn, source=None):
    if source:
        rows = conn.execute("SELECT * FROM uncensored_entries WHERE status='pending' AND source=? ORDER BY cid", (source,)).fetchall()
    else:
        rows = conn.execute("SELECT * FROM uncensored_entries WHERE status='pending' ORDER BY cid").fetchall()
    return [dict(r) for r in rows]


def get_scraped_uncensored(conn, source=None):
    if source:
        rows = conn.execute("SELECT * FROM uncensored_entries WHERE status='scraped' AND source=? ORDER BY cid", (source,)).fetchall()
    else:
        rows = conn.execute("SELECT * FROM uncensored_entries WHERE status='scraped' ORDER BY cid").fetchall()
    return [dict(r) for r in rows]


def get_errors_uncensored(conn, source=None):
    if source:
        rows = conn.execute("SELECT * FROM uncensored_entries WHERE status IN ('error','404','flagged') AND source=? ORDER BY cid", (source,)).fetchall()
    else:
        rows = conn.execute("SELECT * FROM uncensored_entries WHERE status IN ('error','404','flagged') ORDER BY cid").fetchall()
    return [dict(r) for r in rows]


def get_flagged_uncensored(conn, source=None):
    if source:
        rows = conn.execute("SELECT * FROM uncensored_entries WHERE status='flagged' AND source=? ORDER BY cid", (source,)).fetchall()
    else:
        rows = conn.execute("SELECT * FROM uncensored_entries WHERE status='flagged' ORDER BY cid").fetchall()
    return [dict(r) for r in rows]


def insert_file_uncensored(conn, cid, directory_path, file_path, file_size=None, part_number=1):
    conn.execute(
        "INSERT INTO uncensored_files (cid, directory_path, file_path, file_size, part_number) VALUES (?, ?, ?, ?, ?)",
        (cid, directory_path, file_path, file_size, part_number)
    )
    conn.commit()
