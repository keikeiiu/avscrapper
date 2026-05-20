"""Cookie health check — verifies scraper auth is still valid."""
import sys
import os
import yaml


def check_site(site_name, site_config, timeout=15):
    """Launch headless browser, navigate to site, return (ok, detail).

    Returns:
        (True, "OK — logged in as <user>")
        (False, "session expired")
        (False, "Cloudflare challenge")
        (False, "age gate blocked")
        (False, "<error message>")
    """
    from playwright.sync_api import sync_playwright

    base_url = site_config["base_url"].rstrip("/")
    cookies = {k: v for k, v in site_config.get("cookies", {}).items() if v}
    user_agent = site_config.get("user_agent",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:135.0) Gecko/20100101 Firefox/135.0")

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(user_agent=user_agent)

            if cookies:
                context.add_cookies([
                    {"name": k, "value": v, "domain": site_name.replace("_", ".").replace("fc2ppvdb", "fc2ppvdb.com").replace("javdb", "javdb.com"), "path": "/"}
                    for k, v in cookies.items()
                ])

            page = context.new_page()
            resp = page.goto(base_url + "/", timeout=timeout * 1000, wait_until="domcontentloaded")
            status = resp.status if resp else 0

            if status in (403, 503):
                browser.close()
                return False, f"HTTP {status} — blocked"

            # Give JS a moment to render
            page.wait_for_timeout(2000)
            content = page.content()
            url = page.url
            title = page.title()
            browser.close()

        if site_name == "javdb":
            return _check_javdb(status, url, content, title)
        else:
            return _check_fc2(status, url, content, title)

    except Exception as e:
        msg = str(e)
        if "Timeout" in msg:
            return False, "timeout — site unreachable"
        return False, msg[:120]


def _check_fc2(status, url, content, title):
    if "fc2ppvdb.com" not in url and "fc2.com" not in url:
        return False, f"redirected to {url[:60]}"
    if status == 200 and ("Just a moment" in title or "challenge" in content.lower()[:500]):
        return False, "Cloudflare challenge"
    if status == 200 and ("login" in url.lower() or "signin" in url.lower()):
        return False, "redirected to login"
    if status == 200 and ("article" in content.lower()[:1000] or "FC2" in title):
        return True, "OK — authenticated"
    if status == 200:
        return True, "OK — page loaded"
    return False, f"HTTP {status}"


def _check_javdb(status, url, content, title):
    if status == 200 and "age" in title.lower() and "over18" not in url:
        return False, "age gate blocked — over18 cookie missing/expired"
    if status == 200 and ("login" in url.lower()):
        return False, "redirected to login"
    if status == 200 and ("javdb" in url.lower() or "JavDB" in title or "影片" in title):
        return True, "OK — authenticated"
    if status == 200:
        return True, "OK — page loaded"
    return False, f"HTTP {status}"


def run_checks(config_path):
    """Run health checks for all configured sites. Returns list of (site, ok, detail)."""
    with open(config_path, encoding="utf-8") as f:
        config = yaml.safe_load(f)

    sites = config.get("sites", {})
    results = []
    for name, cfg in sites.items():
        print(f"Checking {name}...", end=" ", flush=True)
        ok, detail = check_site(name, cfg)
        icon = "OK" if ok else "FAIL"
        print(f"{icon} — {detail}")
        results.append((name, ok, detail))
    return results
