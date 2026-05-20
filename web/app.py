"""AV Scraper Web GUI — Flask application."""
import os
import sys
import json
import time
import shutil
from collections import deque

# PyInstaller: sys._MEIPASS points to the _internal bundle directory
_frozen = getattr(sys, 'frozen', False)
if _frozen:
    ROOT = sys._MEIPASS
    HERE = ROOT
    # Desktop: point Playwright at bundled Chromium in _internal/ms-playwright/
    _pw_browsers = os.path.join(ROOT, "ms-playwright")
    if os.path.isdir(_pw_browsers):
        os.environ["PLAYWRIGHT_BROWSERS_PATH"] = _pw_browsers
else:
    HERE = os.path.dirname(os.path.abspath(__file__))
    ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

_is_desktop = os.environ.get("AV_DESKTOP") == "1"

# Resolve config.yaml path (respects AV_CONFIG for Docker / AV_APPDATA for Desktop)
_config_default = os.path.join(ROOT, "config.yaml")
if _is_desktop:
    _appdata = os.environ.get("AV_APPDATA", os.path.join(ROOT, "appdata"))
    _config_default = os.path.join(_appdata, "config.yaml")
config_yaml = os.environ.get("AV_CONFIG", _config_default)
# Ensure config.yaml exists on first run
if not os.path.isfile(config_yaml):
    example = os.path.join(ROOT, "config.example.yaml")
    if os.path.exists(example):
        os.makedirs(os.path.dirname(config_yaml), exist_ok=True)
        shutil.copy(example, config_yaml)
        import yaml as _yaml
        with open(config_yaml, encoding="utf-8") as f:
            cfg = _yaml.safe_load(f)
        if _is_desktop:
            # Desktop: point db + reports into the user's private appdata directory.
            # Video paths are left as relative defaults from config.example.yaml
            # (e.g. ./downloads, ./processed) — user configures real paths via the
            # web UI config editor.
            cfg["db_path"] = os.path.join(_appdata, "av_data.db").replace("\\", "/")
            cfg["report_dir"] = os.path.join(_appdata, "reports").replace("\\", "/")
            os.makedirs(cfg["report_dir"], exist_ok=True)
        elif config_yaml.startswith("/app/"):
            # Docker: rewrite paths to absolute (relative breaks when config is in subdirectory)
            cfg["db_path"] = "/app/appdata/av_data.db"
            cfg["report_dir"] = "/app/appdata/reports"
            ing = cfg.setdefault("ingest", {})
            ing["source"] = "/app/downloads"
            ing["fc2_target"] = "/app/processed"
            ing["jav_target"] = "/app/processed"
            cfg.setdefault("reorganize", {})["target"] = "/app/reorganized"
            os.makedirs("/app/appdata/reports", exist_ok=True)
        with open(config_yaml, "w", encoding="utf-8") as f:
            _yaml.dump(cfg, f, default_flow_style=False, allow_unicode=True)

from flask import Flask, render_template, jsonify, request, redirect, send_file
import yaml

app = Flask(__name__, template_folder=os.path.join(ROOT, "web", "templates"), static_folder=os.path.join(ROOT, "web", "static"))

# In-memory action history (last 10 entries, lost on restart)
action_history = deque(maxlen=10)


def load_config():
    config_path = os.environ.get("AV_CONFIG") or os.path.join(ROOT, "config.yaml")
    if not os.path.exists(config_path):
        config_path = os.path.join(ROOT, "config.example.yaml")

    with open(config_path, encoding="utf-8") as f:
        config = yaml.safe_load(f)

    config_dir = os.path.dirname(config_path)
    raw_db = config.get("db_path", "av_data.db")
    if not os.path.isabs(raw_db):
        raw_db = os.path.normpath(os.path.join(config_dir, raw_db))
    config["db_path"] = raw_db

    report_dir = config.get("report_dir", "reports")
    if not os.path.isabs(report_dir):
        report_dir = os.path.normpath(os.path.join(config_dir, report_dir))
    config["report_dir"] = report_dir

    return config, config_dir


config, config_dir = load_config()
from src.db import init_db
init_db(config["db_path"])
app.config["APP_CONFIG"] = config

# ── Watch Folder Scheduler ──
def _start_watch_scheduler():
    schedule = config.get("watch_schedule", "")
    if not schedule:
        return
    import re
    cron_match = re.match(r'(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)', schedule)
    if not cron_match:
        return
    minute, hour, dom, month, dow = [int(g) for g in cron_match.groups()]
    def _check():
        import time as _time
        from datetime import datetime
        last_run = None
        while True:
            now = datetime.now()
            match = (
                (minute == -1 or now.minute == minute) and
                (hour == -1 or now.hour == hour) and
                (month == -1 or now.month == month) and
                (dow == -1 or now.weekday() + 1 == dow if dow != 0 else now.weekday() == 6)
            )
            if match and (last_run is None or (now - last_run).total_seconds() > 120):
                last_run = now
                import subprocess, sys
                cmd = [sys.executable, "avscraper.py", "ingest", "--yes"]
                src = config.get("ingest", {}).get("source", "")
                if src:
                    cmd.extend(["--source", src])
                subprocess.Popen(cmd, cwd=config_dir, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            _time.sleep(60)
    t = __import__("threading").Thread(target=_check, daemon=True)
    t.start()

_start_watch_scheduler()
app.config["ROOT_DIR"] = ROOT

from web.routes.actions import actions_bp
from web.routes.db_api import db_bp
from web.routes.stream import stream_bp
from web.routes.config_api import config_bp

app.register_blueprint(actions_bp)
app.register_blueprint(db_bp)
app.register_blueprint(stream_bp)
app.register_blueprint(config_bp)


@app.route("/")
def index():
    from src.db import connect, get_stats
    conn = connect(config["db_path"])
    stats = get_stats(conn)
    conn.close()
    history = list(action_history)
    return render_template("dashboard.html", stats=stats, history=history)


@app.route("/actions")
def actions_page():
    return render_template("actions.html")


@app.route("/db")
def db_page():
    return render_template("db_browse.html")


@app.route("/browse")
def browse_page():
    return render_template("browse.html")


@app.route("/logs")
def logs_page():
    reports_dir = config.get("report_dir", os.path.join(ROOT, "reports"))
    report_files = []
    if os.path.isdir(reports_dir):
        for f in sorted(os.listdir(reports_dir), reverse=True):
            if f.endswith(".md"):
                path = os.path.join(reports_dir, f)
                size = os.path.getsize(path)
                report_files.append({"name": f, "size": size, "mtime": os.path.getmtime(path)})
    return render_template("logs.html", reports=report_files[:50])


@app.route("/config")
def config_page():
    return render_template("config.html")


@app.route("/pipeline")
def pipeline_page():
    return render_template("pipeline.html")


@app.route("/api/cover")
def api_cover():
    """Serve cached cover image, fall back to redirecting to remote URL."""
    cid = request.args.get("cid", "")
    if not cid:
        return ("Missing cid", 400)
    from src.db import connect
    conn = connect(config["db_path"])
    row = conn.execute(
        "SELECT cover_path, cover_url FROM fc2_entries WHERE cid=? UNION ALL SELECT cover_path, cover_url FROM jav_entries WHERE cid=? LIMIT 1",
        (cid, cid)
    ).fetchone()
    conn.close()
    if not row:
        return ("Not found", 404)
    local_path, remote_url = row["cover_path"], row["cover_url"]
    if local_path and os.path.isfile(local_path):
        import mimetypes
        mime, _ = mimetypes.guess_type(local_path)
        return send_file(local_path, mimetype=mime or "image/jpeg")
    if remote_url:
        return redirect(remote_url, code=302)
    return ("No cover available", 404)


@app.route("/api/open-file")
def api_open_file():
    import subprocess
    path = request.args.get("path", "").replace("\\", "/")
    if not path:
        return jsonify({"error": "No path provided"}), 400

    # Docker: translate container path → host path via configured mount base
    host_mount = (config or {}).get("host_mount_base", "")
    if host_mount and path.startswith("/app/"):
        rel = path[len("/app/"):]
        path = os.path.normpath(os.path.join(host_mount, rel)).replace("\\", "/")

    if not os.path.exists(path):
        return jsonify({"error": "File not found", "path": path}), 404

    try:
        if sys.platform == "win32":
            os.startfile(os.path.normpath(path))
        elif sys.platform == "darwin":
            subprocess.Popen(["open", path])
        else:
            # headless Linux (Docker) — xdg-open has no display
            display = os.environ.get("DISPLAY")
            if display:
                subprocess.Popen(["xdg-open", path])
            else:
                return jsonify({"status": "path_only", "path": path})
        return jsonify({"status": "opened", "path": path})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/report/<name>")
def api_report(name):
    reports_dir = config.get("report_dir", os.path.join(ROOT, "reports"))
    path = os.path.join(reports_dir, name)
    if not os.path.isfile(path) or not name.endswith(".md"):
        return ("Not found", 404)
    with open(path, encoding="utf-8") as f:
        raw = f.read()
    import markdown
    html = markdown.markdown(raw, extensions=["tables", "fenced_code"])
    return html, 200, {"Content-Type": "text/html; charset=utf-8"}


@app.route("/api/user/<cid>", methods=["GET", "POST"])
def api_user_data(cid):
    """Get or set user data (favorite, rating, notes) for an entry."""
    from src.db import connect
    conn = connect(config["db_path"])
    # Find which table this CID belongs to
    row = conn.execute("SELECT cid, favorite, user_rating, user_notes FROM fc2_entries WHERE cid=? UNION ALL SELECT cid, favorite, user_rating, user_notes FROM jav_entries WHERE cid=? LIMIT 1", (cid, cid)).fetchone()
    if not row:
        conn.close()
        return jsonify({"error": "Not found"}), 404

    if request.method == "GET":
        conn.close()
        return jsonify({"cid": row["cid"], "favorite": bool(row["favorite"]), "user_rating": row["user_rating"], "user_notes": row["user_notes"]})

    data = request.get_json() or {}
    table = "fc2_entries" if row["cid"].isdigit() and len(row["cid"]) >= 6 else "jav_entries"
    if "favorite" in data:
        conn.execute(f"UPDATE {table} SET favorite=? WHERE cid=?", (str(int(data["favorite"])), cid))
    if "user_rating" in data:
        conn.execute(f"UPDATE {table} SET user_rating=? WHERE cid=?", (str(data["user_rating"]), cid))
    if "user_notes" in data:
        conn.execute(f"UPDATE {table} SET user_notes=? WHERE cid=?", (data["user_notes"], cid))
    conn.commit()
    conn.close()
    return jsonify({"status": "updated"})


@app.route("/api/metadata/<cid>")
def api_metadata(cid):
    """Get ffprobe metadata for the first video file of a CID."""
    from src.db import connect
    conn = connect(config["db_path"])
    # Check cached first
    row = conn.execute(
        "SELECT video_metadata FROM fc2_entries WHERE cid=? AND video_metadata IS NOT NULL UNION ALL SELECT video_metadata FROM jav_entries WHERE cid=? AND video_metadata IS NOT NULL LIMIT 1",
        (cid, cid)
    ).fetchone()
    if row and row["video_metadata"]:
        conn.close()
        import json as _json
        return jsonify(_json.loads(row["video_metadata"]))
    # Find first file for this CID
    frow = conn.execute(
        "SELECT file_path FROM fc2_files WHERE cid=? UNION ALL SELECT file_path FROM jav_files WHERE cid=? LIMIT 1",
        (cid, cid)
    ).fetchone()
    conn.close()
    if not frow or not frow["file_path"]:
        return jsonify({"error": "No file found"}), 404
    path = frow["file_path"]
    if not os.path.isfile(path):
        return jsonify({"error": "File not on disk"}), 404
    from src.duration_audit import _ffprobe_metadata
    meta = _ffprobe_metadata(path)
    if not meta:
        return jsonify({"error": "ffprobe failed"}), 500
    return jsonify(meta)


@app.route("/api/action/history")
def api_history():
    return jsonify(list(action_history))


@ app.context_processor
def inject_config():
    return {"app_config": config}


if __name__ == "__main__":
    port = int(os.environ.get("FLASK_PORT", os.environ.get("PORT", 3721)))
    debug = os.environ.get("AV_DESKTOP") != "1"
    app.run(host="127.0.0.1", port=port, debug=debug, threaded=True)
