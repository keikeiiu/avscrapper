"""JAV NFO Enricher — reads scraped metadata from SQLite, writes NFO files to disk."""

import sys
import os
import re
import argparse
import json
import yaml
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from db import connect, get_scraped_jav, mark_status_jav, find_directories
from sites.javdb.jav_nfo import parse_nfo, build_nfo, merge_fields, merge_actors


VIDEO_EXTS = {".mp4", ".mkv", ".avi", ".wmv", ".mov", ".ts", ".flv", ".webm"}
PART_RE = re.compile(r'[-_](?:part?\s*|pt\s*|cd\s*|dvd\s*|disk\s*|disc\s*)(\d+)', re.IGNORECASE)

def _jav_id_extractor(folder_name):
    """Extract JAV CID from folder name like 'SSIS-119' or 'CAWD-122'."""
    m = re.match(r'^([A-Z]+[_-]?\d{2,5})', folder_name, re.IGNORECASE)
    return m.group(1).upper().replace("_", "-") if m else None


def enrich_jav(targets, db_path, cids=None, dry_run=False, report_dir=None):
    """Main JAV enrichment loop."""
    if report_dir is None:
        report_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    conn = connect(db_path)
    entries = get_scraped_jav(conn, source="javdb")
    cid_dirs = find_directories(targets, _jav_id_extractor)

    if cids:
        entries = [e for e in entries if str(e["cid"]) in cids]
    if not entries:
        print("No scraped JAV entries to enrich.")
        conn.close()
        return

    total = len(entries)
    updated = 0
    skipped = 0
    no_dir = 0
    report_lines = []
    report_lines.append("# JAV NFO Enrichment Report\n")
    report_lines.append(f"**Total scraped entries:** {total}\n\n")
    report_lines.append("| ID | Dir Found | Action |")
    report_lines.append("|----|-----------|--------|")

    print(f"Enriching {total} JAV entries...")

    for i, entry in enumerate(entries):
        cid = entry["cid"]
        dir_path = cid_dirs.get(cid)

        if not dir_path:
            print(f"[{i+1}/{total}] {cid}: no directory")
            report_lines.append(f"| {cid} | no | skipped |")
            no_dir += 1
            continue

        nfo_path = os.path.join(dir_path, f"{cid}.nfo")

        existing_fields = {}
        existing_genres = []
        existing_tags = []
        existing_actors = []
        existing_art = {}
        if os.path.exists(nfo_path):
            existing_fields, existing_genres, existing_tags, existing_actors, existing_art = parse_nfo(nfo_path)

        raw_title = entry.get("title") or ""
        scraped = {
            "title": f"{cid} {raw_title}",
            "originaltitle": raw_title,
            "sorttitle": cid,
            "uniqueid": cid,
            "plot": entry.get("plot") or raw_title,
            "studio": entry.get("studio"),
            "label": entry.get("label"),
            "series": entry.get("series"),
            "director": entry.get("director"),
            "premiered": entry.get("release_date"),
            "year": entry.get("year"),
            "runtime": entry.get("runtime"),
            "rating": str(entry.get("rating")) if entry.get("rating") else None,
            "votes": str(entry.get("votes")) if entry.get("votes") else None,
        }
        scraped = {k: v for k, v in scraped.items() if v is not None and v != ""}

        # Art
        cover_url = entry.get("cover_url")
        if cover_url and "poster" not in existing_art:
            existing_art["poster"] = cover_url
        fanart_json = entry.get("fanart_urls")
        if fanart_json and "fanart" not in existing_art:
            try:
                fanart = json.loads(fanart_json)
                if fanart:
                    existing_art["fanart"] = fanart[0]
            except (json.JSONDecodeError, TypeError):
                pass

        merged = merge_fields(existing_fields, scraped)

        # Genres
        genres_json = entry.get("genres")
        if genres_json:
            try:
                scraped_genres = json.loads(genres_json)
                for g in scraped_genres:
                    if g not in existing_genres:
                        existing_genres.append(g)
            except (json.JSONDecodeError, TypeError):
                pass

        # Actors
        actors_json = entry.get("actors")
        if actors_json:
            try:
                scraped_actors = json.loads(actors_json)
                existing_actors = merge_actors(existing_actors, scraped_actors)
            except (json.JSONDecodeError, TypeError):
                pass

        if dry_run:
            changed = merged != existing_fields
            status = "would update" if changed else "no change"
            print(f"[{i+1}/{total}] {cid}: {status} (dry-run)")
            report_lines.append(f"| {cid} | yes | {status} |")
            updated += 1 if changed else 0
            continue

        xml = build_nfo(merged, existing_genres, existing_tags, existing_actors, existing_art)
        os.makedirs(dir_path, exist_ok=True)
        with open(nfo_path, "w", encoding="utf-8") as f:
            f.write(xml)
        print(f"[{i+1}/{total}] {cid}: written")
        report_lines.append(f"| {cid} | yes | updated |")
        updated += 1

    conn.close()

    report_lines.append(f"\n**Summary:** {updated} updated, {skipped} skipped, {no_dir} no directory")
    from datetime import date
    today = date.today().isoformat()
    report_path = os.path.join(report_dir, f"enrichment-jav-{today}.md")
    os.makedirs(report_dir, exist_ok=True)
    with open(report_path, "a", encoding="utf-8") as f:
        f.write("\n".join(report_lines))
    print(f"\nDone: {updated} updated, {skipped} skipped, {no_dir} no directory")
    print(f"Report: {report_path}")


def main():
    p = argparse.ArgumentParser(description="JAV NFO Enricher")
    p.add_argument("--ids", help="Comma-separated JAV CIDs to enrich")
    p.add_argument("--dry-run", action="store_true", help="Preview changes, no writes")
    args = p.parse_args()

    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    config_path = os.path.join(base_dir, "config.yaml")
    if not os.path.exists(config_path):
        config_path = os.path.join(base_dir, "fc2_config.yaml")
    with open(config_path) as f:
        config = yaml.safe_load(f)

    raw_db = config.get("db_path", "av_data.db")
    if not os.path.isabs(raw_db):
        raw_db = os.path.normpath(os.path.join(os.path.dirname(config_path), raw_db))
    config["db_path"] = raw_db

    ing = config.get("ingest", {})
    targets = [ing.get("jav_target")] if ing.get("jav_target") else []
    if not targets:
        targets = config.get("scan_directories", [])
    if not targets:
        print("No targets configured. Set ingest.jav_target in config.yaml.")
        sys.exit(1)

    report_dir = config.get("report_dir")
    if report_dir and not os.path.isabs(report_dir):
        report_dir = os.path.normpath(os.path.join(os.path.dirname(config_path), report_dir))

    cids = [c.strip() for c in args.ids.split(",")] if args.ids else None

    enrich_jav(targets, config.get("db_path", "av_data.db"), cids=cids, dry_run=args.dry_run, report_dir=report_dir)


if __name__ == "__main__":
    main()
