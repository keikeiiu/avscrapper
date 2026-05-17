"""Config Editor API — read and write config.yaml."""
import os
import shutil
from flask import Blueprint, request, jsonify, current_app
import yaml

config_bp = Blueprint("config", __name__)


def _config_path():
    # Use ROOT stored in app config (set in web/app.py)
    root = current_app.config.get("ROOT_DIR", os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    path = os.path.join(root, "config.yaml")
    if not os.path.exists(path):
        path = os.path.join(root, "config.example.yaml")
    return path


@config_bp.route("/api/config", methods=["GET"])
def get_config():
    path = _config_path()
    if not os.path.exists(path):
        return jsonify({"error": "config.yaml not found"}), 404
    with open(path, encoding="utf-8") as f:
        content = f.read()
    return jsonify({"content": content, "path": os.path.basename(path)})


@config_bp.route("/api/config", methods=["POST"])
def save_config():
    data = request.get_json() or {}
    content = data.get("content", "")
    if not content.strip():
        return jsonify({"error": "Content cannot be empty"}), 400

    # Validate YAML syntax
    try:
        yaml.safe_load(content)
    except yaml.YAMLError as e:
        return jsonify({"error": f"YAML syntax error: {e}"}), 400

    path = _config_path()
    # Backup existing config
    bak_path = path + ".bak"
    if os.path.exists(path):
        shutil.copy(path, bak_path)

    with open(path, "w", encoding="utf-8") as f:
        f.write(content)

    return jsonify({"status": "saved", "backup": os.path.basename(bak_path)})
