"""JavDB scraper — search-based lookup, detail page extraction, Playwright rendering."""

import sys
import os
import re
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from sites.base_scraper import BaseScraper


class JavdbScraper(BaseScraper):
    def scrape_pending(self, db_path, cids=None, retry_errors=False, dry_run=False):
        """Override to use JAV-specific DB functions."""
        from db import (connect, init_db, insert_pending_jav, upsert_scraped_jav,
                         mark_status_jav, get_pending_jav, get_errors_jav)

        init_db(db_path)
        conn = connect(db_path)

        if cids:
            entries = [{"cid": c, "full_number": c} for c in cids]
            for e in entries:
                insert_pending_jav(conn, e["cid"], e["full_number"], self.source)
        elif retry_errors:
            entries = get_errors_jav(conn, source=self.source)
        else:
            entries = get_pending_jav(conn, source=self.source)

        if not entries:
            print(f"No pending entries for source '{self.source}'. Nothing to scrape.")
            conn.close()
            return

        from sites.base_scraper import _delay_str
        total = len(entries)
        print(f"Scraping {total} entries from {self.source} (delay={_delay_str(self.delay)})...")
        if dry_run:
            print("[DRY RUN -- no DB writes]")

        scraped = 0
        not_found = 0
        errors = 0

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
                    mark_status_jav(conn, cid, "error", str(e)[:500])
                    print(f"ERROR: {e}")
                    errors += 1
                    self._rate_limit()
                    continue

                if data is None:
                    mark_status_jav(conn, cid, "404")
                    print("404")
                    not_found += 1
                else:
                    upsert_scraped_jav(conn, cid, data, self.source)
                    status = (data.get("title") or "OK")[:60]
                    print(status)
                    scraped += 1

                self._rate_limit()
        finally:
            conn.close()
            self.teardown()

        print(f"\nDone: {scraped} scraped, {not_found} not found, {errors} errors")

    def setup(self):
        from playwright.sync_api import sync_playwright

        self._pw = sync_playwright().start()
        self._browser = self._pw.chromium.launch(headless=True)
        context = self._browser.new_context(
            user_agent=self.user_agent,
            viewport={"width": 1920, "height": 1080},
        )
        if self.cookies:
            for k, v in self.cookies.items():
                if not v:
                    continue
                context.add_cookies([{
                    "name": k, "value": v,
                    "domain": "javdb.com",
                    "path": "/",
                }])
        self._page = context.new_page()

        # Visit homepage to establish Cloudflare / cookie context
        self._page.goto(self.base_url + "/", timeout=30000, wait_until="domcontentloaded")
        self._page.wait_for_timeout(3000)

    def teardown(self):
        if hasattr(self, "_browser") and self._browser:
            self._browser.close()
        if hasattr(self, "_pw") and self._pw:
            self._pw.stop()

    def _normalise_id(self, cid):
        """Normalise JAV ID: uppercase, strip CJK prefix tags, strip suffixes."""
        cid = cid.strip()
        # Strip leading CJK prefix like [中文字幕]
        cid = re.sub(r'^\[[^\]]+\]', '', cid).strip()
        cid = cid.upper()
        # Strip known suffixes after the core ID
        cid = re.sub(r'[-_](C|HD|4K|FHD|SD)$', '', cid)
        return cid

    def search(self, cid):
        cid = self._normalise_id(cid)
        url = f"{self.base_url}/search?q={cid}&f=all"

        resp = self._page.goto(url, timeout=30000, wait_until="domcontentloaded")
        if resp.status == 404:
            return None
        if resp.status != 200:
            raise Exception(f"HTTP {resp.status} at {url}")

        self._page.wait_for_timeout(2000)

        # Try to find the matching result in search listings
        detail_url = self._find_result(cid)
        if detail_url:
            self._page.goto(detail_url, timeout=30000, wait_until="domcontentloaded")
            self._page.wait_for_timeout(2000)

        return self._extract_page(cid, self._page.url)

    def _find_result(self, cid):
        """Find the correct result link in search listings by matching the ID."""
        # Search results are <a href="/v/XXXX"> with <strong>ID</strong> inside
        links = self._page.query_selector_all("a[href*='/v/']")
        for link in links:
            strong = link.query_selector("strong")
            if strong:
                uid = strong.inner_text().strip().upper()
                if cid == uid:
                    href = link.get_attribute("href")
                    if href:
                        if href.startswith("/"):
                            return self.base_url + href
                        return href
        # Fallback: try any link containing the cid in text or href
        for link in links:
            text = link.inner_text().upper()
            if cid in text:
                href = link.get_attribute("href")
                if href and "/v/" in href:
                    if href.startswith("/"):
                        return self.base_url + href
                    return href
        return None

    def _extract_page(self, cid, url):
        data = {
            "cid": cid,
            "full_number": cid,
            "url": url,
        }

        # Title — from <title> tag
        title_el = self._page.query_selector("title")
        if title_el:
            raw = title_el.inner_text().strip()
            raw = re.sub(r'\s*\|\s*JavDB.*$', '', raw, flags=re.DOTALL)
            if raw and raw != "JavDB 成人影片數據庫":
                data["title"] = raw

        # Find the metadata nav — the one containing 番號:/日期: labels
        navs = self._page.query_selector_all("nav")
        nav = None
        for n in navs:
            if n.query_selector("xpath=.//strong[contains(text(),'番號')]"):
                nav = n
                break
        # If not found, try the whole page body
        if not nav:
            nav = self._page.query_selector("body")

        # Studio
        data["studio"] = self._field_from_nav(nav, "片商")
        data["label"] = self._field_from_nav(nav, "標籤") or self._field_from_nav(nav, "發行") or data["studio"]
        data["series"] = self._field_from_nav(nav, "系列")
        data["director"] = self._field_from_nav(nav, "導演")

        # Release date
        raw_date = self._field_from_nav(nav, "日期") if nav else None
        if raw_date:
            data["release_date"] = raw_date.replace("/", "-")
            data["year"] = raw_date[:4] if len(raw_date) >= 4 else None

        # Runtime
        raw_runtime = self._field_from_nav(nav, "時長") if nav else None
        if raw_runtime:
            data["runtime"] = raw_runtime
            data["runtime_seconds"] = _parse_jav_runtime(raw_runtime)

        # Rating — from "評分: ★★★★★ 4.16分, 由236人評價"
        if nav:
            rating_text = self._field_from_nav(nav, "評分")
            if rating_text:
                m = re.search(r'([\d.]+)分', rating_text)
                if m:
                    data["rating"] = float(m.group(1))
                m_votes = re.search(r'(\d+)人評價', rating_text)
                if m_votes:
                    data["votes"] = int(m_votes.group(1))

        # Actors — links to /actors/*
        if nav:
            actor_els = nav.query_selector_all("a[href*='/actors/']")
            actors = []
            for a in actor_els:
                name = a.inner_text().strip()
                if name:
                    actors.append({"name": name, "thumb": ""})
            data["actors"] = actors

        # Genres — links to /tags? after 類別: label
        if nav:
            tag_els = nav.query_selector_all("a[href*='/tags?']")
            data["genres"] = [t.inner_text().strip() for t in tag_els if t.inner_text().strip()]

        # Cover — first large image on the page
        imgs = self._page.query_selector_all("img")
        for img in imgs:
            src = img.get_attribute("src") or ""
            if "jdbstatic.com/covers" in src:
                data["cover_url"] = src
                break

        # Fanart / samples
        sample_els = self._page.query_selector_all("a[href*='jdbstatic.com/samples/']")
        fanart = [a.get_attribute("href") for a in sample_els if a.get_attribute("href")]
        if fanart:
            data["fanart_urls"] = fanart

        return data

    def _field_from_nav(self, nav, label):
        """Extract value after a <strong>label:</strong> in the nav.
        Uses relative XPath from nav, then gets next sibling text/link."""
        if not nav:
            return None
        # Use relative XPath starting from nav
        strong = nav.query_selector(f"xpath=.//strong[contains(text(),'{label}')]")
        if not strong:
            return None
        # Get next sibling's text content
        text = strong.evaluate("""el => {
            let node = el.nextSibling;
            while (node) {
                if (node.nodeType === 3 && node.textContent.trim())  // TEXT_NODE
                    return node.textContent.trim();
                if (node.nodeType === 1) {  // ELEMENT_NODE
                    let t = node.textContent.trim();
                    if (t) return t;
                }
                node = node.nextSibling;
            }
            // If no sibling, try parent text minus label
            let p = el.parentElement?.textContent || '';
            p = p.replace(el.textContent, '').trim();
            return p || null;
        }""")
        return text if text else None

    def _field(self, panel, label):
        """Extract value from a strong-text + span pattern: <strong>label:</strong> <span>value</span>"""
        el = panel.query_selector(f"xpath=//strong[contains(text(),'{label}')]/../span")
        if not el:
            el = panel.query_selector(f"xpath=//strong[contains(text(),'{label}')]/../span/a")
        if el:
            return el.inner_text().strip()
        return None


def _parse_jav_runtime(text):
    """Parse runtime string like '120 分' or '2:00:00' to integer seconds."""
    if not text:
        return None
    text = text.strip()
    m = re.search(r'(\d+)\s*分', text)
    if m:
        return int(m.group(1)) * 60  # minutes → seconds
    parts = text.split(":")
    if len(parts) == 3:
        return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
    if len(parts) == 2:
        return (int(parts[0]) * 60 + int(parts[1]))
    return None


if __name__ == "__main__":
    JavdbScraper.run(site_name="javdb")
