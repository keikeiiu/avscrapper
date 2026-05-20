"""Action API endpoints — trigger ingest, scrape, enrich, etc."""
from flask import Blueprint, request, jsonify, current_app
from web.process_manager import run_action, stop_action, is_running, ACTIONS

actions_bp = Blueprint("actions", __name__)


@actions_bp.route("/api/actions")
def list_actions():
    """Return available actions with their parameters."""
    result = {}
    for name, spec in ACTIONS.items():
        result[name] = {
            "params": spec["params"],
            "flags": list(spec.get("flags", {}).keys()),
            "kw": list(spec.get("kw", {}).keys()),
        }
    return jsonify(result)


@actions_bp.route("/api/action/<name>", methods=["POST"])
def trigger_action(name):
    """Start an action. Returns session ID for SSE connection."""
    if name not in ACTIONS:
        return jsonify({"error": f"Unknown action: {name}"}), 404

    params = {}
    if request.is_json:
        params = request.get_json() or {}
    else:
        params = {k: v for k, v in request.form.items()}

    sid, _queue = run_action(name, params)
    return jsonify({"status": "started", "session": sid})


@actions_bp.route("/api/action/<name>/stop", methods=["POST"])
def stop(name):
    """Stop a running action."""
    sid = (request.get_json() or {}).get("session", "")
    if stop_action(sid):
        return jsonify({"status": "stopped"})
    return jsonify({"status": "not_running"}), 404


@actions_bp.route("/api/action/status/<sid>")
def status(sid):
    """Check if a session is still running."""
    return jsonify({"running": is_running(sid)})


@actions_bp.route("/api/batch/flag", methods=["POST"])
def batch_flag():
    """Flag multiple entries for re-scrape."""
    data = request.get_json() or {}
    cids = data.get("cids", [])
    if not cids:
        return jsonify({"error": "No CIDs provided"}), 400
    flagged = 0
    try:
        import os, yaml as _yaml
        root = current_app.config.get("ROOT_DIR", ".")
        config_path = os.environ.get("AV_CONFIG", os.path.join(root, "config.yaml"))
        with open(config_path) as f:
            cfg = _yaml.safe_load(f)
        from src.db import connect, mark_flagged, mark_flagged_jav
        raw_db = cfg.get("db_path", "av_data.db")
        if not os.path.isabs(raw_db):
            raw_db = os.path.normpath(os.path.join(os.path.dirname(config_path), raw_db))
        conn = connect(raw_db)
        for cid in cids:
            if cid.isdigit() and len(cid) >= 6:
                mark_flagged(conn, cid)
            else:
                mark_flagged_jav(conn, cid)
            flagged += 1
        conn.close()
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    return jsonify({"status": "flagged", "count": flagged})


@actions_bp.route("/api/batch/delete", methods=["POST"])
def batch_delete():
    """Delete entries and their files."""
    data = request.get_json() or {}
    cids = data.get("cids", [])
    if not cids:
        return jsonify({"error": "No CIDs provided"}), 400
    deleted = 0
    try:
        import os, yaml as _yaml
        root = current_app.config.get("ROOT_DIR", ".")
        config_path = os.environ.get("AV_CONFIG", os.path.join(root, "config.yaml"))
        with open(config_path) as f:
            cfg = _yaml.safe_load(f)
        from src.db import connect
        raw_db = cfg.get("db_path", "av_data.db")
        if not os.path.isabs(raw_db):
            raw_db = os.path.normpath(os.path.join(os.path.dirname(config_path), raw_db))
        conn = connect(raw_db)
        for cid in cids:
            for table in ("fc2_entries", "jav_entries"):
                conn.execute(f"DELETE FROM {table} WHERE cid=?", (cid,))
            for ftable in ("fc2_files", "jav_files"):
                conn.execute(f"DELETE FROM {ftable} WHERE cid=?", (cid,))
            deleted += 1
        conn.commit()
        conn.close()
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    return jsonify({"status": "deleted", "count": deleted})
