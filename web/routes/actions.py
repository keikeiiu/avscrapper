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
