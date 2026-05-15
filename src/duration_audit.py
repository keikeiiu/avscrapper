"""Duration Audit — compare metadata vs actual video duration using ffprobe."""

import sys
import os
import re
import subprocess
import json
import yaml
from datetime import datetime
from db import connect, init_db, find_directories


def _find_ffprobe():
    """Find ffprobe binary. Returns path or None."""
    # Check common locations
    import shutil
    for candidate in ["ffprobe", "ffprobe.exe"]:
        if shutil.which(candidate):
            return candidate
    # WinGet install location
    winget_base = os.path.expandvars(
        r"%LOCALAPPDATA%\Microsoft\WinGet\Packages\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe")
    for root, dirs, files in os.walk(winget_base):
        for f in files:
            if f == "ffprobe.exe":
                return os.path.join(root, f)
    return None


def _ffprobe_duration(filepath):
    """Get video duration in seconds via ffprobe. Returns float or None."""
    ffprobe = getattr(_ffprobe_duration, "_path", None)
    if ffprobe is None:
        ffprobe = _find_ffprobe()
        _ffprobe_duration._path = ffprobe or "ffprobe"  # cache result
    if not ffprobe:
        return None
    try:
        result = subprocess.run(
            [ffprobe, "-v", "quiet", "-show_entries", "format=duration",
             "-of", "csv=p=0", filepath],
            capture_output=True, text=True, timeout=30
        )
        if result.returncode == 0 and result.stdout.strip():
            return float(result.stdout.strip())
    except Exception:
        pass
    return None


def _parse_fc2_duration(entry):
    """Parse FC2 duration string (HH:MM:SS or MM:SS) to seconds."""
    dur = entry.get("duration")
    if not dur:
        return None
    parts = dur.strip().split(":")
    try:
        if len(parts) == 3:
            return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
        elif len(parts) == 2:
            return int(parts[0]) * 60 + int(parts[1])
    except ValueError:
        pass
    return None


def _format_duration(seconds):
    """Seconds → HH:MM:SS string."""
    if seconds is None:
        return "—"
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    return f"{h}:{m:02d}:{s:02d}"


def _format_diff(seconds):
    """Show diff as signed HH:MM:SS."""
    if seconds is None:
        return "—"
    sign = "-" if seconds < 0 else "+"
    s = abs(int(seconds))
    h = s // 3600
    m = (s % 3600) // 60
    sec = s % 60
    return f"{sign}{h}:{m:02d}:{sec:02d}"


def _classify(meta_sec, actual_sec, minor, hard):
    """Classify mismatch tier."""
    if actual_sec is None:
        return "no_file"
    diff = abs(meta_sec - actual_sec)
    if diff <= minor:
        return "ok"
    elif diff <= hard:
        return "minor_mismatch"
    else:
        return "hard_mismatch"


def _fc2_extractor(name):
    if name.startswith("FC2-PPV-"):
        m = re.match(r'FC2-PPV-(\d{6,8})', name)
        return m.group(1) if m else None
    return None


def _jav_extractor(name):
    m = re.match(r'^([A-Z]+[_-]?\d{2,5})', name, re.IGNORECASE)
    return m.group(1).upper().replace("_", "-") if m else None


def audit(config_path, dry_run=False, cids=None, vtype=None):
    """Run duration audit for FC2 and/or JAV entries."""
    with open(config_path) as f:
        config = yaml.safe_load(f)

    raw_db = config.get("db_path", "av_data.db")
    if not os.path.isabs(raw_db):
        raw_db = os.path.normpath(os.path.join(os.path.dirname(config_path), raw_db))

    aud_cfg = config.get("duration_audit", {})
    minor_thresh = aud_cfg.get("minor_threshold", 30)
    hard_thresh = aud_cfg.get("hard_threshold", 60)

    ing = config.get("ingest", {})
    reorg = config.get("reorganize", {})
    fc2_targets = [ing.get("fc2_target")] if ing.get("fc2_target") else []
    jav_targets = [ing.get("jav_target")] if ing.get("jav_target") else []
    reorg_target = reorg.get("target")
    if reorg_target:
        fc2_targets.append(reorg_target)
        jav_targets.append(reorg_target)

    init_db(raw_db)
    conn = connect(raw_db)

    now = datetime.now().isoformat(timespec="seconds")
    report_lines = [
        f"# Duration Audit Report",
        f"**Date:** {now}",
        f"**Thresholds:** minor ≤{minor_thresh}s, hard >{hard_thresh}s\n",
    ]

    def _jav_meta_seconds(e):
        """JAV runtime_seconds was stored in minutes (legacy bug). Fix for audit."""
        v = e.get("runtime_seconds")
        if v is None:
            return None
        runtime_str = e.get("runtime") or ""
        if "分" in runtime_str and v < 3600:
            # Old data: stored minutes not seconds
            return v * 60
        return v

    for label, targets, extractor, table, file_table, meta_fn in [
        ("FC2", fc2_targets, _fc2_extractor, "fc2_entries", "fc2_files", _parse_fc2_duration),
        ("JAV", jav_targets, _jav_extractor, "jav_entries", "jav_files", _jav_meta_seconds),
    ]:
        if vtype and vtype.lower() != label.lower():
            continue
        if not targets:
            continue

        cid_dirs = find_directories(targets, extractor)
        entries = conn.execute(
            f"SELECT * FROM {table} WHERE status='scraped'"
        ).fetchall()

        if cids:
            entries = [e for e in entries if str(e["cid"]) in cids]

        ok_count = minor_count = hard_count = nofile_count = 0
        rows = []

        for i, entry in enumerate(entries):
            entry = dict(entry)
            cid = entry["cid"]
            dir_info = cid_dirs.get(cid)
            meta_sec = meta_fn(entry)

            if not dir_info or not meta_sec:
                continue

            src_dir = dir_info  # dir_info is full path string from db.find_directories
            videos = [f for f in os.listdir(src_dir)
                      if os.path.splitext(f)[1].lower() in
                      {".mp4", ".mkv", ".avi", ".wmv", ".mov", ".ts", ".flv", ".webm"}]

            actual_total = 0
            for vf in sorted(videos):
                dur = _ffprobe_duration(os.path.join(src_dir, vf))
                if dur:
                    actual_total += dur

            actual_sec = actual_total if actual_total > 0 else None
            status = _classify(meta_sec, actual_sec, minor_thresh, hard_thresh)

            if status == "ok":
                ok_count += 1
            elif status == "minor_mismatch":
                minor_count += 1
            elif status == "hard_mismatch":
                hard_count += 1
            else:
                nofile_count += 1

            rows.append((cid, meta_sec, actual_sec, status))

            if not dry_run:
                conn.execute(f"UPDATE {table} SET audit_status=?, last_audited=? WHERE cid=?",
                             (status, now, cid))
                if actual_sec:
                    conn.execute(
                        f"INSERT INTO {file_table} (cid, duration_seconds, duration_str) VALUES (?,?,?)",
                        (cid, actual_sec, _format_duration(actual_sec)))

        conn.commit()

        report_lines.append(f"## {label}")
        report_lines.append(
            f"🟢 {ok_count} ok | 🟡 {minor_count} minor | 🔴 {hard_count} hard | ⚪ {nofile_count} no file\n")
        report_lines.append("| ID | Metadata | Actual | Diff | Status |")
        report_lines.append("|----|----------|--------|------|--------|")

        icons = {"ok": "🟢", "minor_mismatch": "🟡", "hard_mismatch": "🔴", "no_file": "⚪"}

        for cid, meta_sec, actual_sec, status in rows:
            meta_str = _format_duration(meta_sec)
            actual_str = _format_duration(actual_sec)
            diff = (actual_sec - meta_sec) if (meta_sec and actual_sec) else None
            diff_str = _format_diff(diff) if diff is not None else "—"

            if status == "ok":
                hint = "ok"
            elif status == "minor_mismatch":
                hint = "minor — commercials cut?" if diff and diff < 0 else "minor — bonus content?"
            elif status == "hard_mismatch":
                hint = "hard — missing parts!" if diff and diff < 0 else "hard — possible different video?"
            else:
                hint = "no video file found"

            report_lines.append(
                f"| {cid} | {meta_str} | {actual_str} | {diff_str} | {icons[status]} {hint} |")

        report_lines.append("")
        print(f"{label}: {ok_count} ok, {minor_count} minor, {hard_count} hard, {nofile_count} no file")

    conn.close()

    # Write report
    report_dir = config.get("report_dir", "reports")
    if not os.path.isabs(report_dir):
        report_dir = os.path.normpath(os.path.join(os.path.dirname(config_path), report_dir))
    os.makedirs(report_dir, exist_ok=True)
    today = datetime.now().strftime("%Y-%m-%d")
    path = os.path.join(report_dir, f"duration-audit-{today}.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(report_lines))
    print(f"Report: {path}")


def main():
    import argparse
    p = argparse.ArgumentParser(description="Duration Audit")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--ids", help="Comma-separated CIDs")
    p.add_argument("--type", dest="vtype", help="fc2 or jav")
    args = p.parse_args()

    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    config_path = os.path.join(base_dir, "config.yaml")
    if not os.path.exists(config_path):
        config_path = os.path.join(base_dir, "config.example.yaml")

    cids = [c.strip() for c in args.ids.split(",")] if args.ids else None
    audit(config_path, dry_run=args.dry_run, cids=cids, vtype=args.vtype)


if __name__ == "__main__":
    main()
