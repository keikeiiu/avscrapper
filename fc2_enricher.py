"""NFO Enricher — reads scraped metadata from SQLite, writes NFO files to disk."""

import sys
import os
import re
import argparse
import yaml
from db import connect, get_scraped, mark_status
from fc2_nfo import parse_nfo, build_nfo, merge_fields


def _parse_runtime_minutes(dur):
    """Convert HH:MM:SS or MM:SS string to integer minutes."""
    if not dur:
        return None
    parts = dur.strip().split(":")
    if len(parts) == 3:
        return int(parts[0]) * 60 + int(parts[1])
    elif len(parts) == 2:
        return int(parts[0])
    return None


def find_directories(scan_dirs):
    """Walk scan_dirs and return {cid: dir_path} for all FC2-PPV-* folders."""
    cid_dirs = {}
    for base in scan_dirs:
        if not os.path.isdir(base):
            continue
        for name in os.listdir(base):
            if not name.startswith("FC2-PPV-"):
                continue
            full = os.path.join(base, name)
            if not os.path.isdir(full):
                continue
            cid = name.replace("FC2-PPV-", "").split("[")[0].split("_")[0].strip()
            cid_dirs[cid] = full
    return cid_dirs


def enrich(scan_dirs, db_path, cids=None, dry_run=False):
    """Main enrichment loop."""
    conn = connect(db_path)
    entries = get_scraped(conn, source="fc2ppvdb")
    cid_dirs = find_directories(scan_dirs)

    if cids:
        entries = [e for e in entries if str(e["cid"]) in cids]
    if not entries:
        print("No scraped entries to enrich.")
        conn.close()
        return

    total = len(entries)
    updated = 0
    skipped = 0
    no_dir = 0
    report_lines = []
    report_lines.append(f"# FC2 NFO Enrichment Report\n")
    report_lines.append(f"**Total scraped entries:** {total}\n\n")
    report_lines.append("| ID | Dir Found | Action |")
    report_lines.append("|----|-----------|--------|")

    print(f"Enriching {total} entries...")

    for i, entry in enumerate(entries):
        cid = entry["cid"]
        dir_path = cid_dirs.get(cid)
        if not dir_path:
            print(f"[{i+1}/{total}] {cid}: no directory")
            report_lines.append(f"| {cid} | no | skipped |")
            no_dir += 1
            continue

        nfo_path = os.path.join(dir_path, f"FC2-PPV-{cid}.nfo")

        # Read existing NFO data (any .nfo in folder)
        existing_fields = {}
        existing_tags = []
        existing_art = {}
        for fname in os.listdir(dir_path):
            if fname.endswith(".nfo"):
                fpath = os.path.join(dir_path, fname)
                if os.path.exists(fpath):
                    existing_fields, existing_tags, existing_art = parse_nfo(fpath)
                break

        raw_title = entry.get("title") or ""
        scraped = {
            "title": f"FC2-PPV-{cid} {raw_title}",
            "originaltitle": raw_title,
            "sorttitle": f"FC2-PPV-{cid}",
            "uniqueid": cid,
            "num": f"FC2-PPV-{cid}",
            "plot": raw_title,
            "studio": entry.get("seller"),
            "genre": "FC2",
            "premiered": entry.get("release_date"),
            "runtime": _parse_runtime_minutes(entry.get("duration")),
            "website": entry.get("url") or f"https://fc2ppvdb.com/articles/{cid}",
        }
        scraped = {k: v for k, v in scraped.items() if v is not None and v != ""}

        # Art: use scraped cover_url if no existing poster
        cover_url = entry.get("cover_url")
        if cover_url and "poster" not in existing_art:
            existing_art["poster"] = cover_url

        merged = merge_fields(existing_fields, scraped)
        actress = entry.get("actress", "")
        if actress:
            for name in actress.split(","):
                n = name.strip()
                if n and n not in existing_tags:
                    existing_tags.append(n)

        if dry_run:
            changed = merged != existing_fields
            status = "would update" if changed else "no change"
            print(f"[{i+1}/{total}] {cid}: {status} (dry-run)")
            report_lines.append(f"| {cid} | yes | {status} |")
            if changed:
                updated += 1
            else:
                skipped += 1
            continue

        xml = build_nfo(merged, existing_tags, existing_art)
        os.makedirs(dir_path, exist_ok=True)
        with open(nfo_path, "w", encoding="utf-8") as f:
            f.write(xml)

        # Remove old NFO files with different names
        target = f"FC2-PPV-{cid}.nfo"
        for fname in os.listdir(dir_path):
            if fname.endswith(".nfo") and fname != target:
                os.remove(os.path.join(dir_path, fname))

        print(f"[{i+1}/{total}] {cid}: written")
        report_lines.append(f"| {cid} | yes | updated |")
        updated += 1

    conn.close()

    report_lines.append(f"\n**Summary:** {updated} updated, {skipped} skipped, {no_dir} no directory")

    report_path = os.path.join(os.path.dirname(__file__), "enrichment-report.md")
    with open(report_path, "w", encoding="utf-8") as f:
        f.write("\n".join(report_lines))
    print(f"\nDone: {updated} updated, {skipped} skipped, {no_dir} no directory")
    print(f"Report: {report_path}")


def main():
    p = argparse.ArgumentParser(description="FC2 NFO Enricher")
    p.add_argument("--ids", help="Comma-separated CIDs to enrich")
    p.add_argument("--dry-run", action="store_true", help="Preview changes, no writes")
    args = p.parse_args()

    base_dir = os.path.dirname(os.path.abspath(__file__))
    config_path = os.path.join(base_dir, "config.yaml")
    if not os.path.exists(config_path):
        config_path = os.path.join(base_dir, "fc2_config.yaml")
    config_path = os.environ.get("AV_CONFIG", config_path)
    with open(config_path) as f:
        config = yaml.safe_load(f)

    scan_dirs = config.get("scan_directories", [])
    if not scan_dirs:
        print("No scan_directories in config. Add directories to config.yaml.")
        sys.exit(1)

    cids = [c.strip() for c in args.ids.split(",")] if args.ids else None

    enrich(scan_dirs, config.get("db_path", "av_data.db"), cids=cids, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
