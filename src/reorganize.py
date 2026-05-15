"""Folder Reorganizer — metadata-driven folder hierarchy.

Reads scraped metadata from DB, expands user-defined templates into
target paths, then copy-verify-deletes each folder atomically.
"""

import sys
import os
import re
import shutil
import argparse
import json
import yaml

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from db import connect

# Windows-unsafe filename chars
_UNSAFE = re.compile(r'[:*?"<>|\\/]')
_LEADING_SPACE_DOT = re.compile(r'^[ .]+')
_TRAILING_SPACE_DOT = re.compile(r'[ .]+$')


def _sanitize(s):
    """Replace unsafe chars, trim leading/trailing spaces/dots."""
    if not s:
        return "_"
    s = _UNSAFE.sub("-", s)
    s = _LEADING_SPACE_DOT.sub("", s)
    s = _TRAILING_SPACE_DOT.sub("", s)
    return s or "_"


def _expand(structure, entry, studio_map=None, series_map=None):
    """Expand a structure string with values from a DB entry dict."""
    result = structure
    if studio_map is None: studio_map = {}
    if series_map is None: series_map = {}

    # {premiered:N} → first N chars of release_date
    def _slice(m):
        n = int(m.group(1))
        val = entry.get("release_date") or ""
        return val[:n] if val else "_"

    result = re.sub(r'\{premiered:(\d+)\}', _slice, result)

    # {title:N} → first N chars of title (sanitized)
    def _title_slice(m):
        n = int(m.group(1))
        val = _sanitize(entry.get("title") or "")
        return val[:n] if val else "_"
    result = re.sub(r'\{title:(\d+)\}', _title_slice, result)

    # {series:N} → first N chars of series (sanitized)
    def _series_slice(m):
        n = int(m.group(1))
        val = _sanitize(entry.get("series") or "")
        return val[:n] if val else "_"
    result = re.sub(r'\{series:(\d+)\}', _series_slice, result)

    raw_studio = entry.get("studio") or ""
    raw_series = entry.get("series") or ""
    mapped_studio = _sanitize(studio_map.get(raw_studio, raw_studio))
    mapped_series = _sanitize(series_map.get(raw_series, raw_series))

    replacements = [
        ("cid", entry.get("cid", "")),
        ("title", _sanitize(entry.get("title") or "")),
        ("seller", _sanitize(entry.get("seller") or entry.get("studio") or "")),
        ("studio", mapped_studio),
        ("label", _sanitize(entry.get("label") or "")),
        ("series", mapped_series),
        ("director", _sanitize(entry.get("director") or "")),
        ("premiered", entry.get("release_date") or "_"),
        ("year", entry.get("year") or "_"),
        ("rating", str(entry.get("rating") or "")),
        ("actress", _sanitize(_first_actress(entry))),
        ("code", _code_prefix(entry.get("cid", ""))),
    ]

    for key, val in replacements:
        result = result.replace("{" + key + "}", val)

    return result


def _first_actress(entry):
    """Extract first actress name from JSON or comma-separated string."""
    actors = entry.get("actors")
    if actors:
        try:
            arr = json.loads(actors)
            if arr and arr[0].get("name"):
                return arr[0]["name"]
        except (json.JSONDecodeError, TypeError):
            pass
    actress = entry.get("actress") or ""
    return actress.split(",")[0].strip() if actress else ""


def _find_source_dirs(targets, id_extractor):
    """Return {cid: (source_dir, folder_name)} for matching directories."""
    from db import VIDEO_EXTS
    cid_dirs = {}
    for base in targets:
        if not os.path.isdir(base):
            continue
        for root, dirs, files in os.walk(base):
            for name in dirs:
                cid = id_extractor(name)
                if cid is None:
                    continue
                full = os.path.join(root, name)
                has_video = any(
                    os.path.splitext(f)[1].lower() in VIDEO_EXTS
                    for f in os.listdir(full) if os.path.isfile(os.path.join(full, f))
                )
                if cid not in cid_dirs or (has_video and len(root) < len(cid_dirs[cid][0])):
                    cid_dirs[cid] = (root, name)
    return cid_dirs


def reorganize(config_path, dry_run=False, cids=None):
    """Main reorganize loop."""
    with open(config_path) as f:
        config = yaml.safe_load(f)

    # Resolve paths
    raw_db = config.get("db_path", "av_data.db")
    if not os.path.isabs(raw_db):
        raw_db = os.path.normpath(os.path.join(os.path.dirname(config_path), raw_db))
    report_dir = config.get("report_dir", "reports")
    if not os.path.isabs(report_dir):
        report_dir = os.path.normpath(os.path.join(os.path.dirname(config_path), report_dir))

    reorg = config.get("reorganize", {})
    target_base = reorg.get("target")
    if not target_base:
        print("No reorganize.target in config.yaml")
        return

    ing = config.get("ingest", {})
    fc2_targets = [ing.get("fc2_target")] if ing.get("fc2_target") else []
    jav_targets = [ing.get("jav_target")] if ing.get("jav_target") else []

    conn = connect(raw_db)

    studio_map = reorg.get("studio_map", {})
    series_map = reorg.get("series_map", {})

    # ── FC2 ──
    fc2_structure = reorg.get("fc2_structure")
    if fc2_structure and fc2_targets:
        fc2_dirs = _find_source_dirs(fc2_targets, _fc2_extractor)
        entries = conn.execute(
            "SELECT * FROM fc2_entries WHERE status='scraped' AND title IS NOT NULL"
        ).fetchall()
        _process_type("FC2", entries, fc2_dirs, fc2_structure, target_base, conn, dry_run, cids, studio_map, series_map)

    # ── JAV ──
    jav_structure = reorg.get("jav_structure")
    if jav_structure and jav_targets:
        jav_dirs = _find_source_dirs(jav_targets, _jav_extractor)
        entries = conn.execute(
            "SELECT * FROM jav_entries WHERE status='scraped' AND title IS NOT NULL"
        ).fetchall()
        _process_type("JAV", entries, jav_dirs, jav_structure, target_base, conn, dry_run, cids, studio_map, series_map)

    conn.close()


def _code_prefix(cid):
    """Extract letter prefix from JAV ID: 'SSIS-119' → 'SSIS'."""
    m = re.match(r'^([A-Z]+)', str(cid))
    return m.group(1) if m else cid


def _fc2_extractor(name):
    if name.startswith("FC2-PPV-"):
        m = re.match(r'FC2-PPV-(\d{6,8})', name)
        return m.group(1) if m else None
    return None


def _jav_extractor(name):
    m = re.match(r'^([A-Z]+[_-]?\d{2,5})', name, re.IGNORECASE)
    return m.group(1).upper().replace("_", "-") if m else None


def _process_type(label, entries, cid_dirs, structure, target_base, conn,
                  dry_run=False, cids=None, studio_map=None, series_map=None):
    """Process one type (FC2 or JAV)."""
    if studio_map is None: studio_map = {}
    if series_map is None: series_map = {}
    if cids:
        entries = [e for e in entries if str(e["cid"]) in cids]

    total = len(entries)
    if not total:
        print(f"No {label} entries to reorganize.")
        return

    moved = 0
    skipped = 0
    no_dir = 0
    report = []
    report.append(f"# {label} Reorganize Report\n")
    report.append(f"**Structure:** `{structure}`\n")
    report.append(f"**Target:** {target_base}\n\n")
    report.append("| ID | From | To | Status |")
    report.append("|----|------|----|--------|")

    print(f"Reorganizing {total} {label} entries...")

    for i, entry in enumerate(entries):
        entry = dict(entry)
        cid = entry["cid"]
        dir_info = cid_dirs.get(cid)

        if not dir_info:
            print(f"[{i+1}/{total}] {cid}: no source directory")
            report.append(f"| {cid} | - | - | no dir |")
            no_dir += 1
            continue

        src_base, src_folder = dir_info
        src_path = os.path.join(src_base, src_folder)
        rel_path = _expand(structure, entry, studio_map, series_map)
        dest_path = os.path.join(target_base, rel_path)

        print(f"[{i+1}/{total}] {cid}: {src_folder} → {rel_path}")

        if dry_run:
            moved += 1
            report.append(f"| {cid} | {src_folder} | {rel_path} | dry-run |")
            continue

        if os.path.exists(dest_path):
            print(f"  SKIP: target exists")
            report.append(f"| {cid} | {src_folder} | {rel_path} | skipped |")
            skipped += 1
            continue

        # Copy-verify-delete
        try:
            os.makedirs(os.path.dirname(dest_path), exist_ok=True)
            shutil.copytree(src_path, dest_path)
            # Verify — check a file count matches
            src_count = sum(1 for _ in _walk_files(src_path))
            dest_count = sum(1 for _ in _walk_files(dest_path))
            if src_count != dest_count:
                raise Exception(f"File count mismatch: {src_count} vs {dest_count}")

            shutil.rmtree(src_path)
            print(f"  OK")
            report.append(f"| {cid} | {src_folder} | {rel_path} | moved |")
            moved += 1
        except Exception as e:
            print(f"  FAIL: {e}")
            report.append(f"| {cid} | {src_folder} | {rel_path} | error: {e} |")

    from datetime import date
    today = date.today().isoformat()
    report_path = os.path.join(os.path.dirname(target_base), "reports",
                               f"reorganize-{label.lower()}-{today}.md")
    os.makedirs(os.path.dirname(report_path), exist_ok=True)
    with open(report_path, "w", encoding="utf-8") as f:
        f.write("\n".join(report))
    print(f"\nDone: {moved} moved, {skipped} skipped, {no_dir} no dir")
    print(f"Report: {report_path}")


def _walk_files(d):
    """Yield all file paths under directory."""
    for root, dirs, files in os.walk(d):
        for f in files:
            yield os.path.join(root, f)


def _generate_structure_report(target_base, report_dir):
    """Generate a tree-view markdown report of the reorganized folder."""
    if not os.path.isdir(target_base):
        print(f"Target directory not found: {target_base}")
        return

    from datetime import date
    lines = [f"# Reorganized Structure Report",
             f"**Date:** {date.today().isoformat()}",
             f"**Target:** {target_base}\n",
             "```"]
    for root, dirs, files in os.walk(target_base):
        depth = root.replace(target_base, "").count(os.sep)
        indent = "  " * depth
        folder = os.path.basename(root) or target_base
        lines.append(f"{indent}{folder}/")
        for f in sorted(files):
            lines.append(f"{indent}  {f}")
    lines.append("```")

    os.makedirs(report_dir, exist_ok=True)
    path = os.path.join(report_dir, f"reorganized-structure-{date.today().isoformat()}.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"Structure report: {path}")


def main():
    p = argparse.ArgumentParser(description="Folder Reorganizer — metadata-driven hierarchy")
    p.add_argument("--dry-run", action="store_true", help="Preview only")
    p.add_argument("--ids", help="Comma-separated CIDs to reorganize")
    p.add_argument("--report", action="store_true", help="Generate structure report only, no moves")
    args = p.parse_args()

    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    config_path = os.path.join(base_dir, "config.yaml")
    if not os.path.exists(config_path):
        config_path = os.path.join(base_dir, "fc2_config.yaml")

    with open(config_path) as f:
        config = yaml.safe_load(f)

    target_base = config.get("reorganize", {}).get("target")
    report_dir = config.get("report_dir", "reports")
    if not os.path.isabs(report_dir):
        report_dir = os.path.normpath(os.path.join(os.path.dirname(config_path), report_dir))

    if args.report:
        if not target_base:
            print("No reorganize.target in config.yaml")
            return
        _generate_structure_report(target_base, report_dir)
        return

    cids = [c.strip() for c in args.ids.split(",")] if args.ids else None

    reorganize(config_path, dry_run=args.dry_run, cids=cids)


if __name__ == "__main__":
    main()
