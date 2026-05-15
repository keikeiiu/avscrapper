"""NFO Enricher — reads scraped metadata from SQLite, writes NFO files to disk."""

import sys
import os
import re
import argparse
import yaml
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from db import connect, get_scraped, mark_status, find_directories
from sites.fc2ppvdb.fc2_nfo import parse_nfo, build_nfo, merge_fields


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


def _fc2_id_extractor(folder_name):
    """Extract CID from FC2-PPV-* folder name."""
    if not folder_name.startswith("FC2-PPV-"):
        return None
    return folder_name.replace("FC2-PPV-", "").split("[")[0].split("_")[0].strip()


def enrich(targets, db_path, cids=None, dry_run=False, report_dir=None):
    """Main enrichment loop."""
    if report_dir is None:
        report_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    conn = connect(db_path)
    entries = get_scraped(conn, source="fc2ppvdb")
    cid_dirs = find_directories(targets, _fc2_id_extractor)

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

    report_path = os.path.join(report_dir, "enrichment-report.md")
    os.makedirs(report_dir, exist_ok=True)
    with open(report_path, "w", encoding="utf-8") as f:
        f.write("\n".join(report_lines))
    print(f"\nDone: {updated} updated, {skipped} skipped, {no_dir} no directory")
    print(f"Report: {report_path}")


def main():
    p = argparse.ArgumentParser(description="FC2 NFO Enricher")
    p.add_argument("--ids", help="Comma-separated CIDs to enrich")
    p.add_argument("--dry-run", action="store_true", help="Preview changes, no writes")
    args = p.parse_args()

    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    config_path = os.path.join(base_dir, "config.yaml")
    if not os.path.exists(config_path):
        config_path = os.path.join(base_dir, "fc2_config.yaml")
    config_path = os.environ.get("AV_CONFIG", config_path)
    with open(config_path) as f:
        config = yaml.safe_load(f)

    # Resolve relative db_path
    raw_db = config.get("db_path", "av_data.db")
    if not os.path.isabs(raw_db):
        raw_db = os.path.normpath(os.path.join(os.path.dirname(config_path), raw_db))
    config["db_path"] = raw_db

    ing = config.get("ingest", {})
    targets = [ing.get("fc2_target")] if ing.get("fc2_target") else []
    if not targets:
        # Fallback to scan_directories for backward compat
        targets = config.get("scan_directories", [])
    if not targets:
        print("No targets configured. Set ingest.fc2_target in config.yaml.")
        sys.exit(1)

    report_dir = config.get("report_dir")
    if report_dir and not os.path.isabs(report_dir):
        report_dir = os.path.normpath(os.path.join(os.path.dirname(config_path), report_dir))

    cids = [c.strip() for c in args.ids.split(",")] if args.ids else None

    enrich(targets, config.get("db_path", "av_data.db"), cids=cids, dry_run=args.dry_run, report_dir=report_dir)


if __name__ == "__main__":
    main()
