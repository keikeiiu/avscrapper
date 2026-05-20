"""AV Scraper Tool — Entry Point.

Usage:
    python avscraper.py ingest --source ./downloads --dry-run
    python avscraper.py scrape fc2ppvdb
    python avscraper.py scrape javdb
    python avscraper.py enrich fc2ppvdb
    python avscraper.py enrich javdb
    python avscraper.py reorganize --dry-run
    python avscraper.py reorganize --report
    python avscraper.py flag fc2ppvdb --ids 123456,789012
    python avscraper.py flag javdb --ids SSIS-123
    python avscraper.py path-audit --repair
    python avscraper.py dedup ./downloads --move
"""

import sys
import os
import subprocess

# Ensure src/ is on the path
HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "src")
sys.path.insert(0, SRC)


def _find_config():
    """Return path to config.yaml, preferring env var, then local, then example."""
    env = os.environ.get("AV_CONFIG")
    if env and os.path.exists(env):
        return env
    local = os.path.join(HERE, "config.yaml")
    if os.path.exists(local):
        return local
    example = os.path.join(HERE, "config.example.yaml")
    if os.path.exists(example):
        return example
    return None


def _resolve_paths(config_path):
    """Resolve relative paths in config against config directory."""
    import yaml
    with open(config_path, encoding="utf-8") as f:
        config = yaml.safe_load(f)
    base = os.path.dirname(config_path)

    for key in ("db_path", "report_dir"):
        val = config.get(key)
        if val and not os.path.isabs(val):
            config[key] = os.path.normpath(os.path.join(base, val))

    ingest = config.get("ingest", {})
    for key in ("source", "fc2_target", "jav_target"):
        val = ingest.get(key)
        if val and not os.path.isabs(val):
            ingest[key] = os.path.normpath(os.path.join(base, val))

    reorg = config.get("reorganize", {})
    target = reorg.get("target")
    if target and not os.path.isabs(target):
        reorg["target"] = os.path.normpath(os.path.join(base, target))

    return config, config_path


def _run_script(name, *args):
    script = os.path.join(SRC, name)
    return subprocess.run([sys.executable, script] + list(args))


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return

    config_path = _find_config()
    if not config_path:
        print("No config.yaml or config.example.yaml found.")
        sys.exit(1)

    config, config_path = _resolve_paths(config_path)

    command = sys.argv[1]
    extra = sys.argv[2:]

    if command == "ingest":
        _run_script("ingest.py", *extra)
    elif command == "scrape":
        if not extra:
            print("Usage: python avscraper.py scrape <site> [--ids ...]")
            return
        site = extra[0]
        scraper = f"sites/{site}/{site}_scraper.py" if site not in ("fc2ppvdb","javdb") else f"sites/{site}/{site}_scraper.py"
        if site == "fc2ppvdb":
            scraper = "sites/fc2ppvdb/fc2ppvdb_scraper.py"
        elif site == "javdb":
            scraper = "sites/javdb/javdb_scraper.py"
        else:
            print(f"Unknown site: {site}")
            return
        _run_script(scraper, *extra[1:])
    elif command == "enrich":
        if not extra:
            print("Usage: python avscraper.py enrich <site> [--ids ...]")
            return
        site = extra[0]
        if site == "fc2ppvdb":
            _run_script("sites/fc2ppvdb/fc2_enricher.py", *extra[1:])
        elif site == "javdb":
            _run_script("sites/javdb/jav_enricher.py", *extra[1:])
        else:
            print(f"Unknown site: {site}")
    elif command == "reorganize":
        _run_script("reorganize.py", *extra)
    elif command == "audit":
        _run_script("duration_audit.py", *extra)
    elif command == "flag":
        if not extra:
            print("Usage: python avscraper.py flag <site> --ids <cids>")
            print("  site: fc2ppvdb or javdb")
            return
        site = extra[0]
        flag_args = extra[1:]
        if not flag_args:
            print("Usage: python avscraper.py flag <site> --ids <cids>")
            return
        _flag_entries(config_path, site, flag_args)
    elif command == "path-audit":
        _run_script("path_audit.py", *extra)
    elif command == "dedup":
        _run_script("dedup.py", *extra)
    elif command == "setup":
        _setup(config, config_path)
    else:
        print(f"Unknown command: {command}")
        print(__doc__)


def _flag_entries(config_path, site, flag_args):
    """Mark entries as flagged for re-scrape."""
    import argparse
    import yaml

    p = argparse.ArgumentParser(description=f"Flag {site} entries for re-scrape")
    p.add_argument("--ids", required=True, help="Comma-separated CIDs to flag")
    args = p.parse_args(flag_args)

    cids = [c.strip() for c in args.ids.split(",") if c.strip()]
    if not cids:
        print("No CIDs provided.")
        return

    config_dir = os.path.dirname(config_path)
    with open(config_path, encoding="utf-8") as f:
        config = yaml.safe_load(f)

    raw_db = config.get("db_path", "av_data.db")
    if not os.path.isabs(raw_db):
        raw_db = os.path.normpath(os.path.join(config_dir, raw_db))

    from src.db import connect, mark_flagged, mark_flagged_jav

    conn = connect(raw_db)
    if site == "fc2ppvdb":
        mark = mark_flagged
    elif site == "javdb":
        mark = mark_flagged_jav
    else:
        print(f"Unknown site: {site}")
        conn.close()
        return

    for cid in cids:
        mark(conn, cid)
        print(f"  {cid} → flagged")

    conn.close()
    print(f"\n{len(cids)} entries flagged. Run:")
    print(f"  python avscraper.py scrape {site} --flagged")


def _setup(config, config_path):
    """First-run setup: create config, check deps, create dirs."""
    import shutil

    # 1. Auto-copy config if using example
    if os.path.basename(config_path) == "config.example.yaml":
        target = os.path.join(os.path.dirname(config_path), "config.yaml")
        if not os.path.exists(target):
            shutil.copy(config_path, target)
            print(f"Created config.yaml from example. Edit paths + cookies:")
            print(f"  {target}")
        else:
            print("config.yaml already exists.")
    else:
        print(f"Using: {config_path}")

    # 2. Check playwright
    try:
        from playwright.sync_api import sync_playwright
        p = sync_playwright().start()
        try:
            b = p.chromium.launch(headless=True)
            b.close()
            print("Playwright + Chromium: OK")
        except Exception:
            print("Chromium not installed. Run: playwright install chromium")
        p.stop()
    except ImportError:
        print("Playwright not installed. Run: pip install playwright && playwright install chromium")

    # 3. Create directories from config
    ingest = config.get("ingest", {})
    reorg = config.get("reorganize", {})
    dirs = [
        ingest.get("source"),
        ingest.get("fc2_target"),
        ingest.get("jav_target"),
        reorg.get("target"),
        config.get("report_dir"),
    ]
    for d in dirs:
        if d and not os.path.isabs(d):
            d = os.path.join(HERE, d)
        if d:
            os.makedirs(d, exist_ok=True)
    print("Directories created from config.")
    print("\nSetup complete. Drop videos into your source directory and run:")
    print("  python avscraper.py ingest --dry-run")


if __name__ == "__main__":
    main()
