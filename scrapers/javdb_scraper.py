"""JavDB scraper — search-based lookup, detail page extraction, Playwright rendering."""

import sys
import os
import re
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scrapers.base import BaseScraper


class JavdbScraper(BaseScraper):
    def setup(self):
        from playwright.sync_api import sync_playwright

        self._pw = sync_playwright().start()
        self._browser = self._pw.chromium.launch(headless=True)
        context = self._browser.new_context(
            user_agent=self.user_agent,
            viewport={"width": 1920, "height": 1080},
        )
        if self.cookies:
            context.add_cookies([
                {"name": k, "value": v, "domain": ".javdb.com", "path": "/"}
                for k, v in self.cookies.items() if v
            ])
        self._page = context.new_page()

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
        items = self._page.query_selector_all(".movie-list .item")
        for item in items:
            uid_el = item.query_selector(".uid")
            if not uid_el:
                continue
            uid = uid_el.inner_text().strip().upper()
            if cid in uid or uid in cid:
                link = item.query_selector("a[href*='/v/']")
                if link:
                    href = link.get_attribute("href")
                    if href.startswith("/"):
                        return self.base_url + href
                    return href
        # Fallback: try direct detail URL
        return None

    def _extract_page(self, cid, url):
        data = {
            "cid": cid,
            "full_number": cid,
            "url": url,
        }

        panel = self._page.query_selector(".movie-panel-info")
        if not panel:
            panel = self._page.query_selector("body")

        if not panel:
            return data

        # Title — from <title> tag or h1
        title_el = self._page.query_selector("title")
        if title_el:
            raw = title_el.inner_text().strip()
            raw = re.sub(r'\s*\|\s*JavDB.*$', '', raw)
            if raw:
                data["title"] = raw
                data["title_en"] = None

        # Studio / Label / Series / Director — from strong/span pairs
        data["studio"] = self._field(panel, "片商")
        data["label"] = self._field(panel, "標籤") or self._field(panel, "發行")
        data["series"] = self._field(panel, "系列")
        data["director"] = self._field(panel, "導演")

        # Release date
        raw_date = self._field(panel, "日期")
        if raw_date:
            data["release_date"] = raw_date.replace("/", "-")
            data["year"] = raw_date[:4] if len(raw_date) >= 4 else None

        # Runtime
        raw_runtime = self._field(panel, "時長")
        if raw_runtime:
            data["runtime"] = raw_runtime
            data["runtime_seconds"] = _parse_jav_runtime(raw_runtime)

        # Rating
        score_el = panel.query_selector(".score-stars")
        if score_el:
            score_text = score_el.evaluate("el => el.parentElement?.textContent?.trim() || ''")
            if score_text:
                parts = score_text.split()
                if parts:
                    try:
                        data["rating"] = float(parts[0])
                    except ValueError:
                        pass
                if len(parts) > 1:
                    try:
                        data["votes"] = int(parts[1].replace(",", ""))
                    except ValueError:
                        pass

        # Actors
        actor_els = panel.query_selector_all("a[href*='/actors/']")
        actors = []
        for a in actor_els:
            name = a.inner_text().strip()
            if name:
                actors.append({"name": name, "thumb": ""})
        data["actors"] = actors

        # Genres / tags
        tag_els = panel.query_selector_all("a[href*='/tags/']")
        data["genres"] = [t.inner_text().strip() for t in tag_els if t.inner_text().strip()]

        # Cover
        img = panel.query_selector("img.video-cover")
        if not img:
            img = self._page.query_selector(".column-video-cover img")
        if img:
            src = img.get_attribute("src")
            if src and not src.startswith("data:"):
                data["cover_url"] = src

        # Fanart / samples
        sample_els = self._page.query_selector_all("a[href*='/samples/']")
        fanart = [a.get_attribute("href") for a in sample_els if a.get_attribute("href")]
        if fanart:
            data["fanart_urls"] = fanart

        return data

    def _field(self, panel, label):
        """Extract value from a strong-text + span pattern: <strong>label:</strong> <span>value</span>"""
        el = panel.query_selector(f"xpath=//strong[contains(text(),'{label}')]/../span")
        if not el:
            el = panel.query_selector(f"xpath=//strong[contains(text(),'{label}')]/../span/a")
        if el:
            return el.inner_text().strip()
        return None


def _parse_jav_runtime(text):
    """Parse runtime string like '120 分' or '2:00:00' to integer minutes."""
    if not text:
        return None
    text = text.strip()
    m = re.search(r'(\d+)\s*分', text)
    if m:
        return int(m.group(1))
    parts = text.split(":")
    if len(parts) == 3:
        return int(parts[0]) * 60 + int(parts[1])
    if len(parts) == 2:
        return int(parts[0])
    return None


if __name__ == "__main__":
    JavdbScraper.run(site_name="javdb")
