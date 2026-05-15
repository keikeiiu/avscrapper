"""AV Scraper Tool — Entry Point.

Usage:
    python avscraper.py ingest --source ./downloads --dry-run
    python avscraper.py scrape fc2ppvdb
    python avscraper.py scrape javdb
    python avscraper.py enrich fc2ppvdb
    python avscraper.py enrich javdb
    python avscraper.py reorganize --dry-run
    python avscraper.py reorganize --report
"""

import sys
import os
import subprocess

# Ensure src/ is on the path
HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "src")
sys.path.insert(0, SRC)


def _find_config():
    """Return path to config.yaml, preferring local over example."""
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
    with open(config_path) as f:
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
    else:
        print(f"Unknown command: {command}")
        print(__doc__)


if __name__ == "__main__":
    main()
