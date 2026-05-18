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

from flask import Flask, render_template, jsonify
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
