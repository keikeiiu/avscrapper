"""Dedup tool — scan a directory for JAV files and find duplicates already in the DB."""

import sys
import os
import re
import shutil
import argparse
import yaml
from datetime import datetime

VIDEO_EXTS = {".mp4", ".mkv", ".avi", ".wmv", ".mov", ".ts", ".flv", ".webm", ".rmvb", ".rm", ".m4v", ".divx", ".f4v"}
JAV_RE = re.compile(r'\b([A-Z]{2,6}[ -]?\d{2,5})\b')


def detect_cid(filename):
    """Extract JAV CID from filename, or None."""
    stem = os.path.splitext(filename)[0]
    m = JAV_RE.search(stem)
    if m:
        return m.group(1).upper().replace(" ", "-").replace("_", "-")
    return None


def scan_source(source_dir):
    """Walk source_dir and return list of {filename, path, cid, size} for video files."""
    results = []
    if not os.path.isdir(source_dir):
        print(f"Source directory not found: {source_dir}")
        return results

    for root, dirs, files in os.walk(source_dir):
        for fname in files:
            ext = os.path.splitext(fname)[1].lower()
            if ext not in VIDEO_EXTS:
                continue
            full_path = os.path.join(root, fname)
            cid = detect_cid(fname)
            size = os.path.getsize(full_path)
            results.append({
                "filename": fname,
                "path": full_path,
                "cid": cid,
                "size": size,
            })

    results.sort(key=lambda r: (r["cid"] or "", r["filename"]))
    return results


def check_duplicates(conn, files):
    """Query DB for each CID and classify files as dupe or new.

    Returns (dupes, new_files, unknown) — unknown = can't detect CID from filename.
    """
    # Collect unique CIDs
    cids = set(f["cid"] for f in files if f["cid"])
    if not cids:
        return [], [], [f for f in files if not f["cid"]]

    # Batch query: which CIDs exist in jav_entries?
    placeholders = ",".join("?" for _ in cids)
    existing_rows = conn.execute(
        f"SELECT cid, title, studio, status FROM jav_entries WHERE cid IN ({placeholders})",
        list(cids)
    ).fetchall()
    existing_cids = {r["cid"]: dict(r) for r in existing_rows}

    # Also check jav_files for file paths
    file_rows = conn.execute(
        f"SELECT cid, file_path, file_size FROM jav_files WHERE cid IN ({placeholders})",
        list(cids)
    ).fetchall()
    file_map = {}
    for r in file_rows:
        file_map.setdefault(r["cid"], []).append(dict(r))

    dupes = []
    new_files = []
    unknowns = []

    for f in files:
        if not f["cid"]:
            f["reason"] = "unrecognized filename"
            unknowns.append(f)
            continue

        entry = existing_cids.get(f["cid"])
        if entry:
            f["db_title"] = entry.get("title")
            f["db_studio"] = entry.get("studio")
            f["db_status"] = entry.get("status")
            f["existing_paths"] = [fr["file_path"] for fr in file_map.get(f["cid"], [])]
            f["existing_sizes"] = [fr["file_size"] for fr in file_map.get(f["cid"], [])]
            dupes.append(f)
        else:
            new_files.append(f)

    return dupes, new_files, unknowns


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


def print_report(dupes, new_files, unknowns, source_dir):
    """Print a readable summary to stdout."""
    total = len(dupes) + len(new_files) + len(unknowns)
    dupe_size = sum(f["size"] for f in dupes)
    new_size = sum(f["size"] for f in new_files)
    unk_size = sum(f["size"] for f in unknowns)

    print(f"\n{'='*70}")
    print(f"  DEDUP SCAN: {source_dir}")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*70}")
    print(f"  Total files:  {total}")
    print(f"  Duplicates:   {len(dupes)}  ({format_size(dupe_size)})")
    print(f"  New:          {len(new_files)}  ({format_size(new_size)})")
    print(f"  Unrecognized: {len(unknowns)}  ({format_size(unk_size)})")

    if dupes:
        print(f"\n── DUPLICATES ({len(dupes)}) ──")
        for f in dupes:
            entry_info = f"{f['db_status']}"
            if f.get("db_title"):
                entry_info += f" | {f['db_title'][:60]}"
            if f.get("existing_paths"):
                existing = f['existing_paths'][0]
                if len(f['existing_paths']) > 1:
                    existing += f" (+{len(f['existing_paths']) - 1} more)"
                print(f"  [{f['cid']}] {f['filename']}  ({format_size(f['size'])})")
                print(f"           → already in DB [{entry_info}]")
                print(f"           → on disk: {existing}")
            else:
                print(f"  [{f['cid']}] {f['filename']}  ({format_size(f['size'])})")
                print(f"           → already in DB [{entry_info}] (no files on disk)")

    if new_files:
        print(f"\n── NEW ({len(new_files)}) ──")
        for f in new_files:
            print(f"  [{f['cid']}] {f['filename']}  ({format_size(f['size'])})")

    if unknowns:
        print(f"\n── UNRECOGNIZED ({len(unknowns)}) ──")
        for f in unknowns:
            print(f"  ? {f['filename']}  ({format_size(f['size'])})")

    print()


def generate_md_report(dupes, new_files, unknowns, source_dir):
    """Generate a markdown report string."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    total_dupe_size = sum(f["size"] for f in dupes)
    total_new_size = sum(f["size"] for f in new_files)

    lines = [
        f"# JAV Dedup Report",
        f"**Date:** {now}",
        f"**Source:** {source_dir}",
        "",
        f"| Category | Count | Size |",
        f"|----------|-------|------|",
        f"| Duplicates | {len(dupes)} | {format_size(total_dupe_size)} |",
        f"| New | {len(new_files)} | {format_size(total_new_size)} |",
        f"| Unrecognized | {len(unknowns)} | {format_size(sum(f['size'] for f in unknowns))} |",
        "",
    ]

    if dupes:
        lines.append("## Duplicates")
        lines.append("")
        lines.append("| CID | Filename | Size | DB Status | DB Title | Existing Path |")
        lines.append("|-----|----------|------|-----------|----------|---------------|")
        for f in dupes:
            existing = f['existing_paths'][0] if f.get('existing_paths') else '-'
            title = (f.get('db_title') or '')[:50]
            lines.append(
                f"| {f['cid']} | {f['filename']} | {format_size(f['size'])} "
                f"| {f.get('db_status', '-')} | {title} | {existing} |"
            )
        lines.append("")

    if new_files:
        lines.append("## New Files")
        lines.append("")
        lines.append("| CID | Filename | Size |")
        lines.append("|-----|----------|------|")
        for f in new_files:
            lines.append(f"| {f['cid']} | {f['filename']} | {format_size(f['size'])} |")
        lines.append("")

    if unknowns:
        lines.append("## Unrecognized")
        lines.append("")
        for f in unknowns:
            lines.append(f"- {f['filename']} ({format_size(f['size'])})")
        lines.append("")

    return "\n".join(lines)


def move_dupes(dupes, target_dir):
    """Move duplicate files into target_dir, preserving subfolder structure."""
    moved = 0
    for f in dupes:
        dest = os.path.join(target_dir, f["filename"])
        # Avoid name collisions
        base, ext = os.path.splitext(dest)
        counter = 1
        while os.path.exists(dest):
            dest = f"{base}_{counter}{ext}"
            counter += 1
        os.makedirs(os.path.dirname(dest) or target_dir, exist_ok=True)
        shutil.move(f["path"], dest)
        f["_moved_to"] = dest
        moved += 1
    return moved


def main():
    p = argparse.ArgumentParser(description="Dedup JAV files — find duplicates already in the database")
    p.add_argument("source", nargs="?", help="Directory to scan for JAV files")
    p.add_argument("--move", action="store_true", help="Move duplicates to _dupes/ folder (default: dry-run)")
    p.add_argument("--dupes-dir", help="Target directory for moved duplicates (default: <source>/_dupes_JAV)")
    p.add_argument("--report-dir", help="Directory for markdown report (default: report_dir from config)")
    args = p.parse_args()

    # Resolve config
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    config_path = os.environ.get("AV_CONFIG")
    if config_path:
        config_path = os.path.normpath(config_path)
    else:
        config_path = os.path.join(base_dir, "config.yaml")
        if not os.path.exists(config_path):
            config_path = os.path.join(base_dir, "appdata", "config.yaml")
        if not os.path.exists(config_path):
            print("No config.yaml found. Run: python avscraper.py setup")
            sys.exit(1)

    with open(config_path, encoding="utf-8") as f:
        config = yaml.safe_load(f)
    config_dir = os.path.dirname(config_path)

    # Resolve db_path
    raw_db = config.get("db_path", "av_data.db")
    if not os.path.isabs(raw_db):
        raw_db = os.path.normpath(os.path.join(config_dir, raw_db))

    if not os.path.exists(raw_db):
        print(f"Database not found: {raw_db}")
        sys.exit(1)

    # Resolve source
    source = args.source
    if not source:
        ingest = config.get("ingest", {})
        source = ingest.get("source")
    if not source:
        print("No source directory specified. Pass as argument or set ingest.source in config.yaml")
        sys.exit(1)
    if not os.path.isabs(source):
        source = os.path.normpath(os.path.join(config_dir, source))

    # Resolve report dir
    report_dir = args.report_dir or config.get("report_dir")
    if report_dir and not os.path.isabs(report_dir):
        report_dir = os.path.normpath(os.path.join(config_dir, report_dir))

    # Resolve dupes dir
    dupes_dir = args.dupes_dir or os.path.join(source, "_dupes_JAV")

    # Scan
    print(f"Scanning: {source}")
    files = scan_source(source)
    if not files:
        print("No video files found.")
        return

    # Check against DB
    from db import connect
    conn = connect(raw_db)
    dupes, new_files, unknowns = check_duplicates(conn, files)
    conn.close()

    # Print report
    print_report(dupes, new_files, unknowns, source)

    # Move dupes if requested
    if args.move and dupes:
        print(f"Moving {len(dupes)} duplicates to: {dupes_dir}")
        moved = move_dupes(dupes, dupes_dir)
        print(f"  Moved: {moved} files")
    elif dupes:
        print(f"Dry-run mode. {len(dupes)} duplicate(s) would be moved.")
        print(f"  Target: {dupes_dir}")
        print(f"  Run with --move to actually move files.")

    # Write report
    if report_dir or dupes:
        md = generate_md_report(dupes, new_files, unknowns, source)
        if not report_dir:
            report_dir = source
        os.makedirs(report_dir, exist_ok=True)
        today = datetime.now().strftime("%Y-%m-%d")
        report_path = os.path.join(report_dir, f"jav-dedup-{today}.md")
        with open(report_path, "w", encoding="utf-8") as f:
            f.write(md)
        print(f"\nReport: {report_path}")


if __name__ == "__main__":
    main()
