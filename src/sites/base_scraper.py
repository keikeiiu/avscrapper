"""Base class for site scrapers — handles CLI, rate-limiting, DB writes."""

import time
import random
import sys
import os
import argparse
from abc import ABC, abstractmethod


def _parse_delay(value):
    """Parse delay spec: '5' → 5, '5-20' → (5, 20), tuple passes through."""
    if isinstance(value, (int, float)):
        return value
    if isinstance(value, (tuple, list)):
        return (float(value[0]), float(value[1]))
    if isinstance(value, str) and "-" in value:
        parts = value.split("-", 1)
        return (float(parts[0]), float(parts[1]))
    return float(value)


def _delay_str(delay):
    if isinstance(delay, tuple):
        return f"{delay[0]}-{delay[1]}s (random)"
    return f"{delay}s"


def _fc2_extractor(folder_name):
    if folder_name.startswith("FC2-PPV-"):
        import re
        m = re.match(r'FC2-PPV-(\d{6,8})', folder_name)
        return m.group(1) if m else None
    return None


def _jav_extractor(folder_name):
    import re
    m = re.match(r'^([A-Z]+[_-]?\d{2,5})', folder_name, re.IGNORECASE)
    return m.group(1).upper().replace("_", "-") if m else None


class BaseScraper(ABC):
    def __init__(self, site_config):
        self.base_url = site_config["base_url"].rstrip("/")
        raw_delay = site_config.get("scrape_delay_seconds", 3)
        self.delay = _parse_delay(raw_delay)
        self.user_agent = site_config.get("user_agent",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:135.0) Gecko/20100101 Firefox/135.0")
        self.cookies = site_config.get("cookies", {})
        self.source = site_config.get("source", "unknown")
        self._consecutive_429 = 0
        self._nfo_dirs = None  # lazily populated for NFO-first check
        self.setup()

    def setup(self):
        """Override to initialise transport (browser, session, etc)."""

    def teardown(self):
        """Override to clean up transport."""

    def _rate_limit(self):
        if isinstance(self.delay, tuple):
            d = random.uniform(self.delay[0], self.delay[1])
        else:
            d = self.delay
        d = min(120, d * (2 ** self._consecutive_429))
        time.sleep(d)
        self._consecutive_429 = max(0, self._consecutive_429 - 1)

    @abstractmethod
    def search(self, cid):
        """Fetch and parse metadata for a CID. Returns dict or None on 404."""
        ...

    def _try_nfo_import(self, cid):
        """Check for existing NFO in the CID's directory. Return DB-ready dict or None."""
        try:
            from db import VIDEO_EXTS

            # Determine NFO filename: FC2 uses FC2-PPV-{cid}.nfo, JAV uses {cid}.nfo
            is_fc2 = cid.isdigit() and len(cid) >= 6
            nfo_name = f"FC2-PPV-{cid}.nfo" if is_fc2 else f"{cid}.nfo"
            id_extractor = _fc2_extractor if is_fc2 else _jav_extractor

            # Lazy-load directories from config ingest targets
            if self._nfo_dirs is None:
                self._nfo_dirs = {}
                config_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
                config_path = os.path.join(config_dir, "config.yaml")
                if not os.path.exists(config_path):
                    config_path = os.path.join(config_dir, "fc2_config.yaml")
                if os.path.exists(config_path):
                    import yaml
                    with open(config_path, encoding="utf-8") as f:
                        config = yaml.safe_load(f)
                    ing = config.get("ingest", {})
                    targets = []
                    if is_fc2 and ing.get("fc2_target"):
                        targets = [ing["fc2_target"]]
                    elif ing.get("jav_target"):
                        targets = [ing["jav_target"]]
                    for target in targets:
                        if not os.path.isabs(target):
                            target = os.path.normpath(os.path.join(config_dir, target))
                        if os.path.isdir(target):
                            for root, dirs, _files in os.walk(target):
                                for name in dirs:
                                    ecid = id_extractor(name)
                                    if ecid:
                                        full = os.path.join(root, name)
                                        has_video = any(
                                            os.path.splitext(f)[1].lower() in VIDEO_EXTS
                                            for f in os.listdir(full)
                                            if os.path.isfile(os.path.join(full, f))
                                        )
                                        if ecid not in self._nfo_dirs or has_video:
                                            self._nfo_dirs[ecid] = full

            dir_path = self._nfo_dirs.get(cid)
            if not dir_path:
                return None

            nfo_path = os.path.join(dir_path, nfo_name)
            if not os.path.exists(nfo_path):
                return None

            if is_fc2:
                from sites.fc2ppvdb.fc2_nfo import parse_nfo, nfo_to_db_data
            else:
                from sites.javdb.jav_nfo import parse_nfo, nfo_to_db_data

            parsed = parse_nfo(nfo_path)
            data = nfo_to_db_data(parsed)
            if data.get("title"):
                return data
        except Exception:
            pass
        return None

    def scrape_pending(self, db_path, cids=None, retry_errors=False, flagged=False, dry_run=False):
        """Main loop: scrape pending (or specified) CIDs and write to DB."""
        from db import connect, init_db, insert_pending, upsert_scraped, mark_status, get_pending, get_errors, get_flagged

        init_db(db_path)
        conn = connect(db_path)

        if cids:
            entries = [{"cid": c, "full_number": f"FC2-PPV-{c}"} for c in cids]
            for e in entries:
                insert_pending(conn, e["cid"], e["full_number"], self.source)
        elif flagged:
            entries = get_flagged(conn, source=self.source)
        elif retry_errors:
            entries = get_errors(conn, source=self.source)
        else:
            entries = get_pending(conn, source=self.source)

        if not entries:
            print(f"No entries for source '{self.source}'. Nothing to scrape.")
            conn.close()
            return

        total = len(entries)
        print(f"Scraping {total} entries from {self.source} (delay={_delay_str(self.delay)})...")
        if dry_run:
            print("[DRY RUN -- no DB writes]")

        scraped = 0
        nfo_imported = 0
        not_found = 0
        errors = 0

        try:
            for i, entry in enumerate(entries):
                cid = entry["cid"]
                print(f"[{i+1}/{total}] {cid} ... ", end="", flush=True)

                # Check for existing NFO before hitting the web
                nfo_data = self._try_nfo_import(cid)
                if nfo_data:
                    if dry_run:
                        status = (nfo_data.get("title") or "OK")[:60]
                        print(f"DRY-RUN NFO: {status}")
                        nfo_imported += 1
                        continue
                    upsert_scraped(conn, cid, nfo_data, self.source)
                    status = (nfo_data.get("title") or "OK")[:60]
                    print(f"NFO: {status}")
                    nfo_imported += 1
                    self._rate_limit()
                    continue

                if dry_run:
                    print("SKIP (dry-run)")
                    continue

                try:
                    data = self.search(cid)
                except Exception as e:
                    mark_status(conn, cid, "error", str(e)[:500])
                    print(f"ERROR: {e}")
                    errors += 1
                    self._rate_limit()
                    continue

                if data is None:
                    mark_status(conn, cid, "404")
                    print("404")
                    not_found += 1
                else:
                    upsert_scraped(conn, cid, data, self.source)
                    status = (data.get("title") or "OK")[:60]
                    print(status)
                    scraped += 1

                self._rate_limit()
        finally:
            conn.close()
            self.teardown()

        print(f"\nDone: {scraped} scraped, {nfo_imported} from NFO, {not_found} not found, {errors} errors")

    @classmethod
    def build_argparser(cls):
        p = argparse.ArgumentParser(description=f"{cls.__name__} scraper")
        p.add_argument("--ids", help="Comma-separated CIDs to scrape")
        p.add_argument("--ids-file", help="File with one CID per line (or markdown list)")
        p.add_argument("--retry-errors", action="store_true", help="Retry entries with status=error, 404, or flagged")
        p.add_argument("--flagged", action="store_true", help="Scrape only entries marked as flagged for re-scrape")
        p.add_argument("--delay", type=str, help="Scrape delay in seconds or range 'min-max' (e.g. '5-20')")
        p.add_argument("--dry-run", action="store_true", help="Show what would be scraped without DB writes")
        p.add_argument("--seed-only", action="store_true", help="Insert CIDs as pending, then exit (no scraping)")
        return p

    @staticmethod
    def parse_ids_from_file(filepath):
        import re
        cids = []
        with open(filepath) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or line.startswith("```"):
                    continue
                if line.startswith("|") or line.startswith("-"):
                    continue
                matches = re.findall(r'\b(\d{6,8})\b', line)
                cids.extend(matches)
        return cids

    @classmethod
    def run(cls, site_name, argv=None):
        """Standard CLI entry: load config, create scraper, scrape.

        Args:
            site_name: key in config['sites'] (e.g. 'fc2ppvdb')
            argv: CLI args (defaults to sys.argv[1:])
        """
        import yaml

        if argv is None:
            argv = sys.argv[1:]

        parser = cls.build_argparser()
        args = parser.parse_args(argv)

        config_parent = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        config_path = os.path.join(config_parent, "config.yaml")
        if not os.path.exists(config_path):
            config_path = os.path.join(config_parent, "fc2_config.yaml")
        config_path = os.environ.get("AV_CONFIG", config_path)
        config_path = os.path.normpath(config_path)
        with open(config_path, encoding="utf-8") as f:
            config = yaml.safe_load(f)

        # Resolve relative db_path against config directory
        raw_db = config.get("db_path", "av_data.db")
        if not os.path.isabs(raw_db):
            raw_db = os.path.normpath(os.path.join(os.path.dirname(config_path), raw_db))
        config["db_path"] = raw_db

        site_config = config["sites"][site_name]
        site_config["source"] = site_name

        if args.delay:
            site_config["scrape_delay_seconds"] = _parse_delay(args.delay)

        cids = None
        if args.ids:
            cids = [c.strip() for c in args.ids.split(",") if c.strip()]
        elif args.ids_file:
            cids = cls.parse_ids_from_file(args.ids_file)

        if args.seed_only:
            from db import connect, init_db, insert_pending

            init_db(config.get("db_path", "av_data.db"))
            conn = connect(config.get("db_path", "av_data.db"))
            if cids:
                for c in cids:
                    insert_pending(conn, c, f"FC2-PPV-{c}", site_name)
                print(f"Seeded {len(cids)} CIDs as pending.")
            else:
                print("No CIDs provided (use --ids or --ids-file).")
            conn.close()
            return

        scraper = cls(site_config)

        scraper.scrape_pending(
            db_path=config.get("db_path", "av_data.db"),
            cids=cids,
            retry_errors=args.retry_errors,
            flagged=args.flagged,
            dry_run=args.dry_run,
        )
