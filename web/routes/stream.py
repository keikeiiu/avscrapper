"""SSE (Server-Sent Events) endpoint — streams subprocess output to browser."""
import json
import time
import queue
from flask import Blueprint, request, Response, current_app
from web.process_manager import _sessions

stream_bp = Blueprint("stream", __name__)


@stream_bp.route("/api/stream")
def event_stream():
    """SSE endpoint. Connect with ?session=<uuid> to receive log lines."""
    sid = request.args.get("session", "")
    session = _sessions.get(sid)

    if not session:
        def _no_session():
            yield f"data: {json.dumps({'type': 'error', 'line': 'Session not found'})}\n\n"
        return Response(_no_session(), mimetype="text/event-stream")

    q = session["queue"]

    def _stream():
        while True:
            try:
                msg = q.get(timeout=30)
                yield f"data: {json.dumps(msg)}\n\n"
                if msg["type"] == "done":
                    break
            except queue.Empty:
                # Send keepalive every 30s
                yield f": keepalive\n\n"

    return Response(_stream(), mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache",
                             "X-Accel-Buffering": "no"})
