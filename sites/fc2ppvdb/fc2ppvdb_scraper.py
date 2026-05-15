"""fc2ppvdb.com scraper — Playwright-rendered pages, metadata extraction."""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from sites.base_scraper import BaseScraper


class Fc2ppvdbScraper(BaseScraper):
    def setup(self):
        from playwright.sync_api import sync_playwright

        domain = self.base_url.split("//")[1].split("/")[0]

        self._pw = sync_playwright().start()
        self._browser = self._pw.chromium.launch(headless=True)
        context = self._browser.new_context(
            user_agent=self.user_agent,
            viewport={"width": 1920, "height": 1080},
        )
        if self.cookies:
            for k, v in self.cookies.items():
                if v:
                    context.add_cookies([{
                        "name": k, "value": v,
                        "domain": ".fc2ppvdb.com" if k.startswith("cf_") else domain,
                        "path": "/",
                    }])

        self._page = context.new_page()

        # Visit homepage to establish Cloudflare clearance
        self._page.goto(self.base_url + "/", timeout=30000, wait_until="domcontentloaded")
        self._page.wait_for_timeout(3000)

    def teardown(self):
        if hasattr(self, "_browser") and self._browser:
            self._browser.close()
        if hasattr(self, "_pw") and self._pw:
            self._pw.stop()

    def search(self, cid):
        url = f"{self.base_url}/articles/{cid}"
        resp = self._page.goto(url, timeout=30000, wait_until="domcontentloaded")

        if resp.status == 404:
            return None
        if resp.status == 429:
            self._consecutive_429 += 1
            raise Exception(f"HTTP 429 at {url}")
        if resp.status != 200:
            raise Exception(f"HTTP {resp.status} at {url}")

        # Wait for JS to replace "Loading..." with real content
        try:
            self._page.wait_for_function(
                "document.querySelector('#article-info') && "
                "document.querySelector('#article-info').textContent.trim() !== 'Loading...'",
                timeout=15000,
            )
        except Exception:
            pass
        self._page.wait_for_timeout(1000)

        return self._extract_from_page(cid, url)

    def _extract_from_page(self, cid, url):
        data = {
            "cid": cid,
            "full_number": f"FC2-PPV-{cid}",
            "url": url,
        }

        article = self._page.query_selector("#article-info")
        if not article:
            return data

        raw = article.inner_text()
        lines = [l.strip() for l in raw.split("\n") if l.strip()]

        def field(label):
            for line in lines:
                if line.startswith(label):
                    return line[len(label):].lstrip("：:").strip() or None
            return None

        data["release_date"] = field("販売日")
        data["duration"] = field("収録時間") or None
        data["mosaic"] = field("モザイク") or None
        data["title"] = lines[0] if lines else None

        seller_el = article.query_selector("a[href*='/writers/']")
        data["seller"] = seller_el.inner_text().strip() if seller_el else None

        actress_els = article.query_selector_all("a[href*='/actresses/']")
        names = [a.inner_text().strip() for a in actress_els if a.inner_text().strip()]
        data["actress"] = ", ".join(names) if names else None

        tag_els = article.query_selector_all("a[href*='/tags/']")
        data["tags"] = [t.inner_text().strip() for t in tag_els if t.inner_text().strip()]

        img = self._page.query_selector("#ArticleImage")
        if img:
            src = img.get_attribute("src")
            no_img = f"{self.base_url}/storage/images/article/no-image.jpg"
            if src and src != no_img:
                data["cover_url"] = src

        return data


if __name__ == "__main__":
    Fc2ppvdbScraper.run(site_name="fc2ppvdb")
