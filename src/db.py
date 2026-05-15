import sqlite3
import json
import os


def connect(db_path):
    """Return a connection with WAL mode enabled."""
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

        CREATE INDEX IF NOT EXISTS idx_fc2_entries_status ON fc2_entries(status);
        CREATE INDEX IF NOT EXISTS idx_fc2_entries_source ON fc2_entries(source);
        CREATE INDEX IF NOT EXISTS idx_fc2_files_cid ON fc2_files(cid);

        CREATE INDEX IF NOT EXISTS idx_jav_entries_status ON jav_entries(status);
        CREATE INDEX IF NOT EXISTS idx_jav_entries_source ON jav_entries(source);
        CREATE INDEX IF NOT EXISTS idx_jav_files_cid ON jav_files(cid);
    """)
    # Migrate existing databases
    for table in ("fc2_entries", "jav_entries"):
        for col in ("audit_status", "last_audited"):
            try:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} TEXT")
            except sqlite3.OperationalError:
                pass  # column already exists
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
    conn.commit()


def mark_status(conn, cid, status, error_message=None):
    """Update status and optional error message for a CID."""
    conn.execute("""
        UPDATE fc2_entries SET status=?, error_message=?, scraped_at=datetime('now')
        WHERE cid=?
    """, (status, error_message, cid))
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
    """Return all rows with status='error' or '404'."""
    if source:
        rows = conn.execute(
            "SELECT * FROM fc2_entries WHERE status IN ('error','404') AND source=? ORDER BY cid", (source,)
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM fc2_entries WHERE status IN ('error','404') ORDER BY cid"
        ).fetchall()
    return [dict(r) for r in rows]


import os as _os
VIDEO_EXTS = {".mp4", ".mkv", ".avi", ".wmv", ".mov", ".ts", ".flv", ".webm", ".rmvb", ".rm", ".m4v", ".divx", ".f4v"}


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

def insert_pending_jav(conn, cid, full_number, source, url=None):
    """Insert a JAV entry as pending. No-op if already exists."""
    conn.execute("""
        INSERT OR IGNORE INTO jav_entries (cid, full_number, source, url, status)
        VALUES (?, ?, ?, ?, 'pending')
    """, (cid, full_number, source, url))
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
            actors, rating, votes, uncensored, url, source,
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
            uncensored=excluded.uncensored, url=excluded.url, source=excluded.source,
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
        data.get("url"),
        source,
        json.dumps(data, ensure_ascii=False),
    ))
    conn.commit()


def mark_status_jav(conn, cid, status, error_message=None):
    """Update status for a JAV CID."""
    conn.execute("""
        UPDATE jav_entries SET status=?, error_message=?, scraped_at=datetime('now')
        WHERE cid=?
    """, (status, error_message, cid))
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
    """Return JAV entries with error/404 status."""
    if source:
        rows = conn.execute(
            "SELECT * FROM jav_entries WHERE status IN ('error','404') AND source=? ORDER BY cid", (source,)
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM jav_entries WHERE status IN ('error','404') ORDER BY cid"
        ).fetchall()
    return [dict(r) for r in rows]
