"""Subprocess runner — spawns CLI commands, captures output, broadcasts via SSE queue."""
import subprocess
import threading
import uuid
import json
import os
import sys
import queue


ACTIONS = {
    "ingest": {
        "cmd": [sys.executable, "avscraper.py", "ingest"],
        "params": ["source", "yes", "dry_run"],
        "flags": {"yes": "--yes", "dry_run": "--dry-run"},
        "kw": {"source": "--source"},
    },
    "scrape_fc2": {
        "cmd": [sys.executable, "avscraper.py", "scrape", "fc2ppvdb"],
        "params": ["ids", "delay", "flagged", "retry_errors"],
        "flags": {"flagged": "--flagged", "retry_errors": "--retry-errors"},
        "kw": {"ids": "--ids", "delay": "--delay"},
    },
    "scrape_jav": {
        "cmd": [sys.executable, "avscraper.py", "scrape", "javdb"],
        "params": ["ids", "delay", "flagged", "retry_errors"],
        "flags": {"flagged": "--flagged", "retry_errors": "--retry-errors"},
        "kw": {"ids": "--ids", "delay": "--delay"},
    },
    "enrich_fc2": {
        "cmd": [sys.executable, "avscraper.py", "enrich", "fc2ppvdb"],
        "params": ["ids", "dry_run"],
        "flags": {"dry_run": "--dry-run"},
        "kw": {"ids": "--ids"},
    },
    "enrich_jav": {
        "cmd": [sys.executable, "avscraper.py", "enrich", "javdb"],
        "params": ["ids", "dry_run"],
        "flags": {"dry_run": "--dry-run"},
        "kw": {"ids": "--ids"},
    },
    "reorganize": {
        "cmd": [sys.executable, "avscraper.py", "reorganize"],
        "params": ["ids", "dry_run"],
        "flags": {"dry_run": "--dry-run"},
        "kw": {"ids": "--ids"},
    },
    "audit": {
        "cmd": [sys.executable, "avscraper.py", "audit"],
        "params": [],
    },
    "flag_fc2": {
        "cmd": [sys.executable, "avscraper.py", "flag", "fc2ppvdb"],
        "params": ["ids"],
        "kw": {"ids": "--ids"},
    },
    "flag_jav": {
        "cmd": [sys.executable, "avscraper.py", "flag", "javdb"],
        "params": ["ids"],
        "kw": {"ids": "--ids"},
    },
}


def build_command(action_name, params):
    """Build CLI command from action name and form parameters."""
    spec = ACTIONS[action_name]
    cmd = list(spec["cmd"])

    for param in spec["params"]:
        val = params.get(param, "").strip() if isinstance(params.get(param), str) else params.get(param)
        if not val:
            continue
        if param in spec.get("flags", {}):
            if val:  # truthy for checkboxes
                cmd.append(spec["flags"][param])
        elif param in spec.get("kw", {}):
            cmd.append(spec["kw"][param])
            cmd.append(val)

    return cmd


# Global registry of active sessions
_sessions = {}


def get_session():
    """Create a new SSE session with its own queue."""
    sid = uuid.uuid4().hex[:8]
    q = queue.Queue()
    _sessions[sid] = {"queue": q, "running": False, "process": None}
    return sid, q


def cleanup_session(sid):
    """Remove a session after use."""
    _sessions.pop(sid, None)


def run_action(action_name, params):
    """Spawn a subprocess for the action and push output to an SSE queue.

    Returns (session_id, queue). The caller uses the session_id to stream results.
    """
    sid, q = get_session()
    cmd = build_command(action_name, params)
    _sessions[sid]["running"] = True
    _sessions[sid]["cmd"] = " ".join(cmd)

    def _run():
        import time as _time
        start = _time.time()
        try:
            env = os.environ.copy()
            env["PYTHONUTF8"] = "1"
            env["PYTHONIOENCODING"] = "utf-8"
            from web.app import ROOT
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                env=env,
                cwd=ROOT,
            )
            _sessions[sid]["process"] = proc
            for line in proc.stdout:
                q.put({"type": "log", "line": line.rstrip("\n")})
            proc.wait()
            q.put({"type": "done", "code": proc.returncode})
            _record_history(action_name, params, proc.returncode, _time.time() - start)
        except Exception as e:
            q.put({"type": "log", "line": f"[ERROR] {e}"})
            q.put({"type": "done", "code": 1})
            _record_history(action_name, params, 1, _time.time() - start)
        finally:
            _sessions[sid]["running"] = False
            _sessions[sid]["process"] = None

    t = threading.Thread(target=_run, daemon=True)
    _sessions[sid]["thread"] = t
    t.start()

    return sid, q


def stop_action(sid):
    """Terminate a running action's subprocess."""
    session = _sessions.get(sid)
    if not session:
        return False
    proc = session.get("process")
    if proc and proc.poll() is None:
        proc.terminate()
        session["running"] = False
        return True
    return False


def is_running(sid):
    """Check if a session is still active."""
    session = _sessions.get(sid)
    return session["running"] if session else False


def _record_history(action_name, params, code, duration):
    """Push a completed action to the in-memory history."""
    try:
        from web.app import action_history
        action_history.appendleft({
            "action": action_name,
            "params": {k: v for k, v in params.items() if v and k != "yes"},
            "code": code,
            "duration": round(duration, 1),
            "time": __import__("time").time(),
        })
    except Exception:
        pass
