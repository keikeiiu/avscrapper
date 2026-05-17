"""DB Browser API — read-only access to the SQLite database."""
import json
import os
import math
from flask import Blueprint, request, jsonify, current_app
from src.db import connect, get_stats

db_bp = Blueprint("db", __name__)


def _db_path():
    cfg = current_app.config.get("APP_CONFIG", {})
    return cfg.get("db_path", "av_data.db")

TABLES = {
    "fc2_entries": {
        "columns": ["cid", "full_number", "title", "seller", "actress", "release_date",
                    "duration", "cover_url", "tags", "outline", "url", "source", "mosaic",
                    "status", "error_message", "scraped_at", "audit_status"],
        "pk": "cid",
        "safe_columns": ["cid", "full_number", "title", "seller", "actress", "release_date",
                        "duration", "cover_url", "status", "scraped_at"],
    },
    "jav_entries": {
        "columns": ["cid", "full_number", "title", "studio", "label", "series", "director",
                    "release_date", "year", "runtime", "cover_url", "genres", "actors",
                    "rating", "votes", "region", "url", "source", "status", "error_message",
                    "scraped_at", "audit_status"],
        "pk": "cid",
        "safe_columns": ["cid", "full_number", "title", "studio", "label", "series", "director",
                        "release_date", "year", "runtime", "cover_url", "rating", "votes",
                        "region", "status", "scraped_at"],
    },
    "fc2_files": {
        "columns": ["id", "cid", "directory_path", "file_path", "file_size",
                    "duration_seconds", "duration_str", "part_number"],
        "pk": "id",
        "safe_columns": ["id", "cid", "directory_path", "file_path", "file_size",
                        "duration_seconds", "part_number"],
    },
    "jav_files": {
        "columns": ["id", "cid", "directory_path", "file_path", "file_size",
                    "duration_seconds", "duration_str", "part_number"],
        "pk": "id",
        "safe_columns": ["id", "cid", "directory_path", "file_path", "file_size",
                        "duration_seconds", "part_number"],
    },
}


@db_bp.route("/api/db/stats")
def api_stats():
    conn = connect(_db_path())
    rows = get_stats(conn)
    conn.close()
    return jsonify([dict(r) for r in rows])


@db_bp.route("/api/db/table/<name>")
def api_table(name):
    if name not in TABLES:
        return jsonify({"error": f"Unknown table: {name}"}), 404

    t = TABLES[name]
    conn = connect(_db_path())

    status_filter = request.args.get("status")
    source_filter = request.args.get("source")
    search = request.args.get("search")
    page = max(1, int(request.args.get("page", 1)))
    per_page = min(200, max(10, int(request.args.get("per_page", 50))))

    where = []
    params = []
    if status_filter and "status" in t["columns"]:
        where.append("status = ?")
        params.append(status_filter)
    if source_filter and "source" in t["columns"]:
        where.append("source = ?")
        params.append(source_filter)
    if search:
        if name in ("fc2_entries", "jav_entries"):
            where.append("(cid LIKE ? OR title LIKE ?)")
            params.extend([f"%{search}%", f"%{search}%"])
        else:
            where.append("cid LIKE ?")
            params.append(f"%{search}%")

    clause = (" WHERE " + " AND ".join(where)) if where else ""
    safe_cols = ", ".join(t["safe_columns"])

    try:
        # Count total
        total_row = conn.execute(f"SELECT COUNT(*) FROM {name}{clause}", params).fetchone()
        total = total_row[0] if total_row else 0
        pages = max(1, math.ceil(total / per_page))
        page = min(page, pages)

        offset = (page - 1) * per_page
        order = "scraped_at" if "scraped_at" in t["safe_columns"] else t["pk"]
        rows = conn.execute(
            f"SELECT {safe_cols} FROM {name}{clause} ORDER BY {order} DESC LIMIT ? OFFSET ?",
            params + [per_page, offset],
        ).fetchall()
        conn.close()
        return jsonify({
            "rows": [dict(r) for r in rows],
            "total": total,
            "page": page,
            "per_page": per_page,
            "pages": pages,
        })
    except Exception as e:
        conn.close()
        return jsonify({"error": str(e)}), 500


@db_bp.route("/api/db/row/<table>/<cid>")
def api_row(table, cid):
    if table not in TABLES:
        return jsonify({"error": f"Unknown table: {table}"}), 404

    t = TABLES[table]
    conn = connect(_db_path())

    try:
        row = conn.execute(
            f"SELECT * FROM {table} WHERE {t['pk']} = ?", (cid,)
        ).fetchone()
        conn.close()
        if row:
            d = dict(row)
            for col in ["tags", "genres", "actors", "fanart_urls"]:
                if col in d and isinstance(d[col], str):
                    try:
                        d[col] = json.loads(d[col])
                    except (json.JSONDecodeError, TypeError):
                        pass
            return jsonify(d)
        return jsonify({"error": "Not found"}), 404
    except Exception as e:
        conn.close()
        return jsonify({"error": str(e)}), 500


@db_bp.route("/api/db/summary")
def api_summary():
    conn = connect(_db_path())
    fc2_total = conn.execute("SELECT COUNT(*) FROM fc2_entries").fetchone()[0]
    jav_total = conn.execute("SELECT COUNT(*) FROM jav_entries").fetchone()[0]
    fc2_pending = conn.execute("SELECT COUNT(*) FROM fc2_entries WHERE status='pending'").fetchone()[0]
    jav_pending = conn.execute("SELECT COUNT(*) FROM jav_entries WHERE status='pending'").fetchone()[0]
    fc2_errors = conn.execute("SELECT COUNT(*) FROM fc2_entries WHERE status IN ('error','404','flagged')").fetchone()[0]
    jav_errors = conn.execute("SELECT COUNT(*) FROM jav_entries WHERE status IN ('error','404','flagged')").fetchone()[0]
    conn.close()
    return jsonify({
        "fc2_total": fc2_total, "jav_total": jav_total,
        "fc2_pending": fc2_pending, "jav_pending": jav_pending,
        "fc2_errors": fc2_errors, "jav_errors": jav_errors,
    })
