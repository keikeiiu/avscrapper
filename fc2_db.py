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
    """Create tables if they don't exist."""
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
            FOREIGN KEY (cid) REFERENCES fc2_entries(cid)
        );

        CREATE INDEX IF NOT EXISTS idx_entries_status ON fc2_entries(status);
        CREATE INDEX IF NOT EXISTS idx_entries_source ON fc2_entries(source);
        CREATE INDEX IF NOT EXISTS idx_files_cid ON fc2_files(cid);
    """)
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


def get_stats(conn):
    """Return status counts."""
    rows = conn.execute("""
        SELECT source, status, COUNT(*) as count
        FROM fc2_entries
        GROUP BY source, status
        ORDER BY source, status
    """).fetchall()
    return [dict(r) for r in rows]
