"""Ingest tool — auto-detect video type, organize files, seed DB."""

import sys
import os
import re
import shutil
import argparse
import yaml

VIDEO_EXTS = {".mp4", ".mkv", ".avi", ".wmv", ".mov", ".ts", ".flv", ".webm", ".rmvb", ".rm", ".m4v", ".divx", ".f4v"}
FC2_RE = re.compile(r'FC2[ -]?PPV[ -]?(\d{6,8})', re.IGNORECASE)
JAV_RE = re.compile(r'\b([A-Z]{2,6}[ -]?\d{2,5})\b')
PART_RE = re.compile(r'[-_ ](?:part\s*|pt\s*|cd\s*|dvd\s*|disk\s*|disc\s*)(\d+)\b', re.IGNORECASE)


def detect_type(filename):
    """Return (type, id, part_number) or None."""
    stem = os.path.splitext(filename)[0]

    m = FC2_RE.search(stem)
    if m:
        return ("fc2", m.group(1), _part_number(stem))

    m = JAV_RE.search(stem)
    if m:
        jid = m.group(1).upper().replace(" ", "-").replace("_", "-")
        return ("jav", jid, _part_number(stem))

    return None


def _part_number(stem):
    m = PART_RE.search(stem)
    if m:
        return int(m.group(1))
    return 1


def _assign_parts(results):
    """Auto-assign part numbers when multiple files share the same (type, cid)
    and none have explicit part markers.  Already-explicit parts are left alone."""
    from collections import defaultdict
    groups = defaultdict(list)
    for i, r in enumerate(results):
        if r["type"]:
            groups[(r["type"], r["cid"])].append(i)

    for (vtype, cid), indices in groups.items():
        if len(indices) <= 1:
            continue
        has_explicit = any(results[i]["part"] > 1 for i in indices)
        if has_explicit:
            continue  # trust explicit -pt1/-pt2 markers
        for seq, i in enumerate(sorted(indices), 1):
            results[i]["part"] = seq
            results[i]["auto_part"] = True


def _ingest_report(source, fc2_target, jav_target, moved, skipped, unknowns):
    """Generate markdown report of the ingest operation."""
    from datetime import datetime
    lines = [
        "# Ingest Report",
        f"**Date:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"**Source:** {source}",
        "",
        f"**Moved:** {len(moved)}  |  **Skipped:** {len(skipped)}  |  **Unknown:** {len(unknowns)}",
        "",
    ]
    if moved:
        lines.append("## Moved")
        lines.append("")
        lines.append("| Type | ID | From | To |")
        lines.append("|------|-----|------|----|")
        for r in moved:
            dest = r.get("_dest", "")
            lines.append(f"| {r['type'].upper()} | {r['cid']} | {r['original']} | {dest} |")
        lines.append("")
        # Resulting folder structure
        lines.append("## Result Structure")
        lines.append("```")
        # Group by target dir
        from collections import defaultdict
        tree = defaultdict(list)
        for r in moved:
            dest = r.get("_dest", "")
            folder = os.path.dirname(dest)
            fname = os.path.basename(dest)
            tree[folder].append(fname)
        for folder in sorted(tree):
            lines.append(f"{folder}/")
            for fname in sorted(tree[folder]):
                lines.append(f"  ├── {fname}")
        lines.append("```")
        lines.append("")
    if skipped:
        lines.append("## Skipped (already exists)")
        lines.append("")
        for r in skipped:
            lines.append(f"- {r['original']} → {r.get('_dest', '')}")
        lines.append("")
    if unknowns:
        lines.append("## Unknown (not recognized)")
        lines.append("")
        for r in unknowns:
            lines.append(f"- {r['original']}")
        lines.append("")
    return "\n".join(lines)


def clean_filename(info):
    """Return clean filename without title text."""
    cid = info["cid"]
    ext = info["ext"]
    if info["type"] == "fc2":
        name = f"FC2-PPV-{cid}"
    else:
        name = cid
    if info["part"] > 1:
        return f"{name}-pt{info['part']}{ext}"
    return f"{name}{ext}"


def ingest(source, fc2_target, jav_target, db_path, dry_run=False, scrape=False, enrich=False, confirm=False):
    from db import connect, init_db, insert_pending, insert_pending_jav

    if not os.path.isdir(source):
        print(f"Source directory not found: {source}")
        return

    init_db(db_path)
    conn = connect(db_path)

    files = [f for f in os.listdir(source) if os.path.splitext(f)[1].lower() in VIDEO_EXTS]
    files.sort()

    if not files:
        print(f"No video files found in {source}")
        conn.close()
        return

    results = []
    for fname in files:
        info = detect_type(fname)
        if info:
            vtype, cid, part = info
            ext = os.path.splitext(fname)[1].lower()
            results.append({
                "original": fname,
                "type": vtype,
                "cid": cid,
                "part": part,
                "ext": ext,
                "auto_part": False,
            })
        else:
            results.append({
                "original": fname,
                "type": None,
                "cid": None,
                "part": 1,
                "ext": os.path.splitext(fname)[1].lower(),
            })

    # Auto-assign part numbers for duplicate CIDs without explicit markers
    _assign_parts(results)

    # Phase 1: compute plan
    to_move = 0
    to_skip = 0
    to_unknown = 0
    unknowns = []
    skips = []
    normal = []

    for r in results:
        if r["type"] is None:
            unknowns.append(r)
            to_unknown += 1
            continue

        if r["type"] == "fc2":
            folder_name = f"FC2-PPV-{r['cid']}"
            target_base = fc2_target
        else:
            folder_name = r["cid"]
            target_base = jav_target

        dest_path = os.path.join(target_base, folder_name, clean_filename(r))
        r["_dest"] = os.path.join(folder_name, clean_filename(r))

        if os.path.exists(dest_path):
            skips.append(r)
            to_skip += 1
        else:
            normal.append(r)
            to_move += 1

    auto_parts = [r for r in results if r.get("auto_part")]

    # Print summary
    print(f"Found {len(files)} files in {source}")
    print(f"  {to_move} to move, {to_skip} skip (exists), {to_unknown} unknown")

    # Print issues only
    issues = []
    if unknowns:
        issues.append(f"  Unknown ({len(unknowns)}):")
        for r in unknowns:
            issues.append(f"    ? {r['original']}")

    if skips:
        issues.append(f"  Already exists ({len(skips)}):")
        for r in skips:
            issues.append(f"    {r['original']}  →  {r['_dest']}")

    if auto_parts:
        issues.append(f"  Auto-assigned parts ({len(auto_parts)}):")
        for r in auto_parts:
            issues.append(f"    {r['original']}  →  {r.get('_dest','')}")

    if issues:
        print()
        for line in issues:
            print(line)

    if to_move == 0:
        print("\nNothing to move.")
        conn.close()
        return

    if dry_run:
        conn.close()
        return

    # Phase 2: ask user, timeout → move clean only
    has_issues = to_skip > 0 or to_unknown > 0 or len(auto_parts) > 0
    if has_issues and not confirm:
        print("\nSome files have issues (see above).")
        print(f"Press Enter to move {to_move} clean file(s) only, type 'all' to force all, or wait 60s to auto-proceed.")
        try:
            import threading
            resp = [None]
            def _get_input():
                try:
                    resp[0] = input("> ").strip().lower()
                except EOFError:
                    pass
            t = threading.Thread(target=_get_input, daemon=True)
            t.start()
            t.join(timeout=60)
            if resp[0] is None:
                print("\nTimeout — moving clean files only...")
            elif resp[0] in ("all", "a", "yes", "y"):
                print("Moving all files (including issues)...")
                # Move everything — clear skip list
                normal.extend(skips)
                to_move += to_skip
                to_skip = 0
            else:
                print("Moving clean files only...")
        except Exception:
            print("Timeout — moving clean files only...")

    print(f"\nMoving {to_move} file(s)...")
    moved = 0
    skipped = 0
    for r in normal:
        if r["type"] is None:
            continue

        target_base = fc2_target if r["type"] == "fc2" else jav_target
        folder = f"FC2-PPV-{r['cid']}" if r["type"] == "fc2" else r["cid"]
        dest_dir = os.path.join(target_base, folder)
        dest_path = os.path.join(dest_dir, clean_filename(r))

        src_path = os.path.join(source, r["original"])
        os.makedirs(dest_dir, exist_ok=True)
        shutil.move(src_path, dest_path)

        full_number = f"FC2-PPV-{r['cid']}" if r["type"] == "fc2" else r["cid"]
        if r["type"] == "fc2":
            insert_pending(conn, r["cid"], full_number, "fc2ppvdb",
                          f"https://fc2ppvdb.com/articles/{r['cid']}")
        else:
            insert_pending_jav(conn, r["cid"], full_number, "javdb",
                             f"https://javdb.com/search?q={r['cid']}&f=all")
        moved += 1

    conn.close()
    print(f"Done: {moved} moved, {skipped} skipped")

    # Write audit report
    report_lines = [_ingest_report(source, fc2_target, jav_target, normal, skips, unknowns)]
    report_path = os.path.join(source, "_ingest-report.md")
    with open(report_path, "w", encoding="utf-8") as f:
        f.write("\n".join(report_lines))
    print(f"Report: {report_path}")

    # Optional: trigger scraper
    if scrape:
        print("\nScraping new entries...")
        from subprocess import run
        if any(r["type"] == "fc2" for r in results if r["type"]):
            run([sys.executable, "sites/fc2ppvdb/fc2ppvdb_scraper.py"], cwd=os.path.dirname(__file__))
        if any(r["type"] == "jav" for r in results if r["type"]):
            run([sys.executable, "sites/javdb/javdb_scraper.py"], cwd=os.path.dirname(__file__))

    if enrich:
        print("\nWriting NFOs...")
        from subprocess import run
        if any(r["type"] == "fc2" for r in results if r["type"]):
            run([sys.executable, "sites/fc2ppvdb/fc2_enricher.py"], cwd=os.path.dirname(__file__))
        if any(r["type"] == "jav" for r in results if r["type"]):
            run([sys.executable, "sites/javdb/jav_enricher.py"], cwd=os.path.dirname(__file__))


def main():
    p = argparse.ArgumentParser(description="Ingest video files — detect type, organize, seed DB")
    p.add_argument("--source", help="Source directory with video files")
    p.add_argument("--fc2-target", help="Target directory for FC2 videos")
    p.add_argument("--jav-target", help="Target directory for JAV videos")
    p.add_argument("--dry-run", action="store_true", help="Preview only, no moves")
    p.add_argument("--yes", "-y", action="store_true", help="Move all files without prompting")
    p.add_argument("--scrape", action="store_true", help="Run scrapers after ingest")
    p.add_argument("--enrich", action="store_true", help="Write NFOs after ingest")
    args = p.parse_args()

    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    config_path = os.path.join(base_dir, "config.yaml")
    if not os.path.exists(config_path):
        config_path = os.path.join(base_dir, "fc2_config.yaml")
    with open(config_path) as f:
        config = yaml.safe_load(f)

    ing = config.get("ingest", {})
    source = args.source or ing.get("source")
    fc2_target = args.fc2_target or ing.get("fc2_target")
    jav_target = args.jav_target or ing.get("jav_target")

    if not source:
        print("No source specified. Use --source or set ingest.source in config.yaml")
        sys.exit(1)
    if not fc2_target and not jav_target:
        print("No target specified. Use --fc2-target / --jav-target or set in config.yaml")
        sys.exit(1)

    fc2_target = fc2_target or os.path.join(source, "_fc2")
    jav_target = jav_target or os.path.join(source, "_jav")

    ingest(source, fc2_target, jav_target,
           config.get("db_path", "av_data.db"),
           dry_run=args.dry_run,
           scrape=args.scrape,
           enrich=args.enrich,
           confirm=args.yes)


if __name__ == "__main__":
    main()
