"""Caribbeancom scraper — uncensored JAV metadata via Playwright."""
import sys, os, re
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from sites.base_scraper import BaseScraper


class CaribbeanScraper(BaseScraper):
    def setup(self):
        from playwright.sync_api import sync_playwright
        self._playwright = sync_playwright().start()
        browser = self._playwright.chromium.launch(headless=True)
        context = browser.new_context(user_agent=self.user_agent)
        if self.cookies:
            context.add_cookies([
                {"name": k, "value": v, "domain": "caribbeancom.com", "path": "/"}
                for k, v in self.cookies.items() if v
            ])
        self._page = context.new_page()
        # Navigate to base to warm up session
        self._page.goto(self.base_url + "/", timeout=30000, wait_until="domcontentloaded")

    def teardown(self):
        try:
            self._page.context.browser.close()
            self._playwright.stop()
        except Exception:
            pass

    def search(self, cid):
        """Fetch metadata for a Caribbeancom CID (e.g. 123011-900)."""
        url = f"{self.base_url}/moviepages/{cid}/index.html"
        resp = self._page.goto(url, timeout=30000, wait_until="domcontentloaded")
        if resp and resp.status in (404, 403):
            return None

        self._page.wait_for_timeout(2000)
        content = self._page.content()

        if "404" in self._page.title() or "not found" in content.lower()[:500]:
            return None

        data = {"cid": cid, "url": url}
        self._parse_detail(content, data)
        return data if data.get("title") else None

    def _parse_detail(self, html, data):
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "html.parser")

        title_el = soup.select_one("h1.movie-title, .movie-info h1, h1, .title")
        if title_el:
            data["title"] = title_el.get_text(strip=True)

        # Metadata rows — caribbeancom uses a table or dl/dt pattern
        meta = {}
        for row in soup.select(".movie-info tr, .video-info tr, .movie-spec tr"):
            cells = row.select("td, th")
            if len(cells) >= 2:
                key = cells[0].get_text(strip=True).rstrip(":")
                val = cells[1].get_text(strip=True)
                meta[key] = val

        # Alternative: dl/dt/dd pattern
        for dt in soup.select("dt"):
            dd = dt.find_next_sibling("dd")
            if dd:
                meta[dt.get_text(strip=True).rstrip(":")] = dd.get_text(strip=True)

        data["studio"] = meta.get("Studio") or meta.get("スタジオ") or "Caribbeancom"
        data["release_date"] = meta.get("Release Date") or meta.get("配信日") or meta.get("販売日")
        data["runtime"] = meta.get("Duration") or meta.get("収録時間") or meta.get("再生時間")
        data["director"] = meta.get("Director") or meta.get("監督")
        if data.get("runtime"):
            dur = re.sub(r'[^\d:]', '', data["runtime"])
            parts = dur.split(":")
            try:
                if len(parts) == 2:
                    data["runtime_seconds"] = int(parts[0]) * 60 + int(parts[1])
                elif len(parts) == 3:
                    data["runtime_seconds"] = int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
            except ValueError:
                pass

        # Actors
        actors = []
        for a in soup.select(".actress-list a, .cast a, .performer a, a[href*='actress']"):
            name = a.get_text(strip=True)
            if name and len(name) > 1:
                actors.append({"name": name})
        data["actors"] = actors

        # Genres / tags
        genres = []
        for g in soup.select(".genre-list a, .tags a, .categories a, a[href*='genre']"):
            genre = g.get_text(strip=True)
            if genre:
                genres.append(genre)
        data["genres"] = genres

        # Cover image
        cover = soup.select_one(".movie-cover img, .video-cover img, .jacket img, img.jacket")
        if not cover:
            cover = soup.select_one("img[src*='jacket'], img[src*='cover'], img[src*='movie']")
        if cover:
            src = cover.get("src") or cover.get("data-src", "")
            if src and not src.startswith("http"):
                src = "https://www.caribbeancom.com" + src if src.startswith("/") else src
            data["cover_url"] = src

        # Fanart / screenshots
        fanart = []
        for img in soup.select(".sample img, .screenshot img, .gallery img, img[src*='sample']"):
            src = img.get("src") or img.get("data-src", "")
            if src:
                if not src.startswith("http"):
                    src = "https://www.caribbeancom.com" + src if src.startswith("/") else src
                fanart.append(src)
        data["fanart_urls"] = fanart[:10]

        if data.get("release_date"):
            data["year"] = data["release_date"][:4]


def main():
    import argparse, yaml
    p = argparse.ArgumentParser(description="Caribbeancom Scraper")
    p.add_argument("--ids", help="Comma-separated CIDs")
    p.add_argument("--delay", type=str, help="Scrape delay")
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()

    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    config_path = os.environ.get("AV_CONFIG")
    if config_path:
        config_path = os.path.normpath(config_path)
    else:
        config_path = os.path.join(base_dir, "config.yaml")
        if not os.path.exists(config_path):
            config_path = os.path.join(base_dir, "config.example.yaml")
    with open(config_path) as f:
        config = yaml.safe_load(f.read())

    site_config = config.get("sites", {}).get("caribbeancom", {})
    site_config["source"] = "caribbeancom"
    if not site_config.get("base_url"):
        site_config["base_url"] = "https://www.caribbeancom.com"

    cids = [c.strip() for c in args.ids.split(",")] if args.ids else None
    if args.delay:
        site_config["scrape_delay_seconds"] = args.delay

    scraper = CaribbeanScraper(site_config)
    raw_db = config.get("db_path", "av_data.db")
    if not os.path.isabs(raw_db):
        raw_db = os.path.normpath(os.path.join(os.path.dirname(config_path), raw_db))

    scraper.scrape_pending_uncensored(
        db_path=raw_db,
        cids=cids,
        dry_run=args.dry_run
    )


# Add uncensored scrape method to base scraper pattern
def _add_uncensored_method():
    """Monkey-patch scrape_pending_uncensored onto BaseScraper if not present."""
    if hasattr(BaseScraper, "scrape_pending_uncensored"):
        return

    def scrape_pending_uncensored(self, db_path, cids=None, dry_run=False):
        from db import (connect, init_db, insert_pending_uncensored,
                        upsert_scraped_uncensored, get_pending_uncensored, get_flagged_uncensored)
        init_db(db_path)
        conn = connect(db_path)
        if cids:
            entries = [{"cid": c} for c in cids]
            for e in entries:
                insert_pending_uncensored(conn, e["cid"], e["cid"], self.source)
        else:
            entries = get_pending_uncensored(conn, source=self.source)
        if not entries:
            print(f"No pending entries for '{self.source}'.")
            conn.close()
            return
        total = len(entries)
        print(f"Scraping {total} entries from {self.source}...")
        scraped = not_found = errors = 0
        try:
            for i, entry in enumerate(entries):
                cid = entry["cid"]
                print(f"[{i+1}/{total}] {cid} ... ", end="", flush=True)
                if dry_run:
                    print("SKIP (dry-run)")
                    continue
                try:
                    data = self.search(cid)
                except Exception as e:
                    conn.execute("UPDATE uncensored_entries SET status='error', error_message=? WHERE cid=?", (str(e)[:500], cid))
                    print(f"ERROR: {e}")
                    errors += 1
                    self._rate_limit()
                    continue
                if data is None:
                    conn.execute("UPDATE uncensored_entries SET status='404', error_message='Not found' WHERE cid=?", (cid,))
                    print("404")
                    not_found += 1
                else:
                    upsert_scraped_uncensored(conn, cid, data, self.source, self.source)
                    print((data.get("title") or "OK")[:60])
                    scraped += 1
                conn.commit()
                self._rate_limit()
        finally:
            conn.close()
            self.teardown()
        print(f"\nDone: {scraped} scraped, {not_found} not found, {errors} errors")

    BaseScraper.scrape_pending_uncensored = scrape_pending_uncensored


_add_uncensored_method()


if __name__ == "__main__":
    main()
