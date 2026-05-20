"""Path Audit — verify file paths in DB match disk, repair stale/missing records."""

import sys
import os
import re
import argparse
import yaml
from datetime import datetime
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from db import connect, upsert_file, upsert_file_jav, mark_path_status, VIDEO_EXTS

_FC2_FOLDER_RE = re.compile(r'FC2-PPV-(\d{6,8})')
_JAV_FOLDER_RE = re.compile(r'^([A-Z]+[_-]?\d{2,5})', re.IGNORECASE)


def _extract_cid_from_folder(folder_name):
    """Try to extract a CID from a folder name."""
    m = _FC2_FOLDER_RE.match(folder_name)
    if m:
        return "fc2", m.group(1)
    m = _JAV_FOLDER_RE.match(folder_name)
    if m:
        return "jav", m.group(1).upper().replace("_", "-")
    return None, None


def _find_files_for_cid(base_dirs):
    """Walk base_dirs and return {cid: [(directory_path, file_path, size, part)]}."""
    cid_files = defaultdict(list)
    for base in base_dirs:
        if not os.path.isdir(base):
            continue
        for root, dirs, files in os.walk(base):
            for fname in files:
                ext = os.path.splitext(fname)[1].lower()
                if ext not in VIDEO_EXTS:
                    continue
                # Try to extract CID from parent folder name
                folder = os.path.basename(root)
                vtype, cid = _extract_cid_from_folder(folder)
                if not cid:
                    continue
                file_path = os.path.join(root, fname)
                file_size = os.path.getsize(file_path)
                part_m = re.search(r'[-_]pt(\d+)', fname, re.IGNORECASE)
                part = int(part_m.group(1)) if part_m else 1
                cid_files[(vtype, cid)].append((root, file_path, file_size, part))
    return cid_files


def format_size(bytes_val):
    if not bytes_val:
        return "0 B"
    units = ["B", "KB", "MB", "GB", "TB"]
    i = 0
    size = float(bytes_val)
    while size >= 1024 and i < len(units) - 1:
        size /= 1024
        i += 1
    return f"{size:.{0 if i == 0 else 1}f} {units[i]}"


def audit_file_paths(conn, table, vtype):
    """Check all file records in table: does file_path exist on disk?
    Returns (ok_count, stale_count, stale_list).
    """
    rows = conn.execute(
        f"SELECT * FROM {table} WHERE file_path IS NOT NULL AND file_path != ''"
    ).fetchall()
    ok_count = 0
    stale = []
    for r in rows:
        d = dict(r)
        if os.path.exists(d["file_path"]):
            conn.execute(f"UPDATE {table} SET path_status='ok' WHERE id=?", (d["id"],))
            ok_count += 1
        else:
            conn.execute(f"UPDATE {table} SET path_status='stale' WHERE id=?", (d["id"],))
            stale.append(d)
    conn.commit()
    return ok_count, len(stale), stale


def repair_stale(conn, table, vtype, stale_records, on_disk_files):
    """For each stale record, try to find a matching file on disk by CID.
    Returns (repaired, still_missing).
    """
    repaired = 0
    still_missing = []
    upsert = upsert_file if vtype == "fc2" else upsert_file_jav

    for rec in stale_records:
        cid = rec["cid"]
        candidates = on_disk_files.get((vtype, cid), [])
        # Try to match by filename
        old_fname = os.path.basename(rec["file_path"])
        matched = None
        for dir_path, file_path, size, part in candidates:
            if os.path.basename(file_path) == old_fname or part == rec.get("part_number", 1):
                matched = (dir_path, file_path, size, part)
                break
        if not matched and candidates:
            # Just take the first candidate
            matched = candidates[0]

        if matched:
            dir_path, file_path, size, part = matched
            upsert(conn, cid, dir_path, file_path, size, part)
            repaired += 1
        else:
            still_missing.append(rec)

    conn.commit()
    return repaired, still_missing


def main():
    p = argparse.ArgumentParser(description="Path Audit — verify and repair file path records")
    p.add_argument("--repair", action="store_true", help="Repair stale paths by scanning target dirs")
    p.add_argument("--type", choices=["fc2", "jav"], help="Audit only one type")
    args = p.parse_args()

    # Resolve config
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    config_path = os.environ.get("AV_CONFIG")
    if config_path:
        config_path = os.path.normpath(config_path)
    else:
        for candidate in [
            os.path.join(base_dir, "config.yaml"),
            os.path.join(base_dir, "appdata", "config.yaml"),
        ]:
            if os.path.exists(candidate):
                config_path = candidate
                break
    if not config_path:
        print("No config.yaml found.")
        sys.exit(1)

    with open(config_path, encoding="utf-8") as f:
        config = yaml.safe_load(f)
    config_dir = os.path.dirname(config_path)

    raw_db = config.get("db_path", "av_data.db")
    if not os.path.isabs(raw_db):
        raw_db = os.path.normpath(os.path.join(config_dir, raw_db))

    if not os.path.exists(raw_db):
        print(f"Database not found: {raw_db}")
        sys.exit(1)

    report_dir = config.get("report_dir")
    if report_dir and not os.path.isabs(report_dir):
        report_dir = os.path.normpath(os.path.join(config_dir, report_dir))

    # Resolve scan directories: ingest targets + reorganize target
    ing = config.get("ingest", {})
    reorg = config.get("reorganize", {})
    scan_dirs = []
    for key in ("fc2_target", "jav_target"):
        v = ing.get(key)
        if v and not os.path.isabs(v):
            v = os.path.normpath(os.path.join(config_dir, v))
        if v:
            scan_dirs.append(v)
    target = reorg.get("target")
    if target and not os.path.isabs(target):
        target = os.path.normpath(os.path.join(config_dir, target))
    if target:
        scan_dirs.append(target)

    conn = connect(raw_db)
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    print(f"Path Audit — {now}")
    print(f"  DB: {raw_db}")
    print(f"  Scan dirs: {', '.join(scan_dirs)}")
    print()

    report_lines = [
        "# Path Audit Report",
        f"**Date:** {now}",
        "",
    ]

    for vtype, table, label in [
        ("fc2", "fc2_files", "FC2"),
        ("jav", "jav_files", "JAV"),
    ]:
        if args.type and args.type != vtype:
            continue

        # Phase 1: Check existing paths
        ok_count, stale_count, stale_records = audit_file_paths(conn, table, vtype)
        total = ok_count + stale_count
        print(f"{label}: {total} file records, {ok_count} OK, {stale_count} stale")
        report_lines.append(f"## {label}")
        report_lines.append(f"")
        report_lines.append(f"| Status | Count |")
        report_lines.append(f"|--------|-------|")
        report_lines.append(f"| OK | {ok_count} |")
        report_lines.append(f"| Stale | {stale_count} |")
        report_lines.append("")

        if stale_records:
            report_lines.append("### Stale Paths")
            report_lines.append("")
            for rec in stale_records:
                report_lines.append(f"- `{rec['cid']}`: `{rec['file_path']}`")
            report_lines.append("")

        # Phase 2: Repair if requested
        if args.repair and stale_records:
            print(f"  Repairing {label} stale records...")
            on_disk = _find_files_for_cid(scan_dirs)
            repaired, still_missing = repair_stale(conn, table, vtype, stale_records, on_disk)
            print(f"    Repaired: {repaired}, Still missing: {still_missing}")
            report_lines.append("### Repair Results")
            report_lines.append("")
            report_lines.append(f"- **Repaired:** {repaired}")
            report_lines.append(f"- **Still missing:** {len(still_missing)}")
            if still_missing:
                report_lines.append("")
                for rec in still_missing:
                    report_lines.append(f"- `{rec['cid']}`: was `{rec['file_path']}` — file not found on disk")
            report_lines.append("")

    conn.close()

    # Write report
    if report_dir:
        os.makedirs(report_dir, exist_ok=True)
        today = datetime.now().strftime("%Y-%m-%d")
        report_path = os.path.join(report_dir, f"path-audit-{today}.md")
        with open(report_path, "w", encoding="utf-8") as f:
            f.write("\n".join(report_lines))
        print(f"\nReport: {report_path}")


if __name__ == "__main__":
    main()
