"""Studio Mapping Scraper — scrape javdb.com/makers to build studio_map.

Usage:
    python src/update_studio_map.py [--dry-run]
    python avscraper.py update-studios [--dry-run]
"""
import sys
import os
import re
import yaml
from urllib.parse import urljoin


def _find_config():
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    config_path = os.environ.get("AV_CONFIG")
    if not config_path:
        config_path = os.path.join(base, "config.yaml")
        if not os.path.exists(config_path):
            config_path = os.path.join(base, "appdata", "config.yaml")
    if not os.path.exists(config_path):
        config_path = os.path.join(base, "config.example.yaml")
    return config_path


def scrape_makers(config, dry_run=False):
    """Scrape javdb makers pages. Returns list of {name, alt_names, url, type}."""
    from playwright.sync_api import sync_playwright

    site_cfg = config.get("sites", {}).get("javdb", {})
    cookies = {k: v for k, v in site_cfg.get("cookies", {}).items() if v}
    user_agent = site_cfg.get("user_agent",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:135.0) Gecko/20100101 Firefox/135.0")
    base = site_cfg.get("base_url", "https://javdb.com").rstrip("/")

    all_makers = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(user_agent=user_agent)
        if cookies:
            cookie_list = [{"name": k, "value": v, "domain": "javdb.com", "path": "/"} for k, v in cookies.items()]
            context.add_cookies(cookie_list)

        for category in ("makers", "makers/uncensored"):
            print(f"\nScraping {base}/{category} ...")
            page = context.new_page()
            page_num = 1
            seen = set()

            while True:
                url = f"{base}/{category}?page={page_num}"
                resp = page.goto(url, timeout=30000, wait_until="domcontentloaded")
                if resp and resp.status != 200:
                    print(f"  HTTP {resp.status} at page {page_num}")
                    break

                page.wait_for_timeout(1500)
                content = page.content()

                # Extract makers from the page
                makers = _parse_makers_page(content, category, seen)
                if not makers:
                    print(f"  No new makers on page {page_num} — done")
                    break

                seen.update(m["name"] for m in makers)
                all_makers.extend(makers)
                print(f"  Page {page_num}: {len(makers)} makers (total: {len(all_makers)})")
                page_num += 1

                if page_num > 20:  # safety limit
                    break

            page.close()

        browser.close()

    return all_makers


def _parse_makers_page(html, category, seen):
    """Parse javdb maker listing page. Return list of maker dicts."""
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, "html.parser")
    makers = []

    # javdb maker cards: .maker-list > .item or .makers > .box
    items = soup.select(".movie-list .item, .maker-list .item, .section .item, .box")
    if not items:
        items = soup.select("a[href*='/makers/']")

    for item in items:
        # Try to find the name
        name_el = item.select_one(".video-title strong, .maker-name, strong")
        if not name_el:
            name_el = item.select_one("a")
        if not name_el:
            continue

        name = name_el.get_text(strip=True)
        if not name or len(name) < 2:
            continue

        # Skip duplicates and non-maker entries
        if name in seen:
            continue

        # Try to find alternate names
        alt_div = item.select_one(".alternate-names, .aka, .subtitle, .maker-aliases, .aliases")
        alt_names = []
        if alt_div:
            alt_text = alt_div.get_text(strip=True)
            alt_names = [n.strip() for n in re.split(r'[,/、]', alt_text) if n.strip() and n.strip() != name]

        # Also check for alt text in the item
        full_text = item.get_text(strip=True)
        # Japanese names often have a reading in brackets
        bracket_match = re.findall(r'\(([^)]+)\)', full_text)
        for bm in bracket_match:
            if bm != name and len(bm) > 1 and bm not in alt_names:
                alt_names.append(bm)

        maker_type = "uncensored" if "uncensored" in category else "censored"
        href = None
        link_el = item.select_one("a[href*='/makers/']") or (name_el if name_el.name == "a" else None)
        if link_el and link_el.name == "a":
            href = link_el.get("href", "")

        makers.append({
            "name": name,
            "alt_names": alt_names,
            "type": maker_type,
            "url": urljoin("https://javdb.com", href) if href else "",
        })

    return makers


def _is_japanese(text):
    """Check if text contains Japanese characters (hiragana, katakana, kanji)."""
    return bool(re.search(r'[぀-ゟ゠-ヿ一-鿿]', text))


def build_studio_map(makers):
    """Generate studio_map from scraped makers. Maps Japanese→English names."""
    studio_map = {}

    for m in makers:
        name = m["name"]
        alt_names = m.get("alt_names", [])

        # If the main name is Japanese and there's an English alt, map JA→EN
        if _is_japanese(name):
            english_alts = [a for a in alt_names if not _is_japanese(a)]
            if english_alts:
                # Map Japanese name → English name
                canonical = english_alts[0]
                studio_map[name] = canonical
            # Also add self-mapping for the English canonical if it exists
            for a in alt_names:
                if not _is_japanese(a) and a not in studio_map:
                    studio_map[a] = a  # English name maps to itself
        else:
            # English name — self-map
            studio_map[name] = name

        # Map alternate names to the primary name
        for alt in alt_names:
            if alt not in studio_map:
                studio_map[alt] = name

    return studio_map


def merge_studio_map(existing_map, new_map):
    """Merge new studio_map into existing, keeping user overrides."""
    merged = dict(new_map)
    # Existing entries override auto-generated ones
    for k, v in existing_map.items():
        merged[k] = v
    return merged


def main():
    import argparse
    p = argparse.ArgumentParser(description="Scrape javdb.com/makers to build studio_map")
    p.add_argument("--dry-run", action="store_true", help="Scrape and show mappings, don't update config")
    p.add_argument("--report-only", action="store_true", help="Only show current studio_map stats")
    args = p.parse_args()

    config_path = _find_config()
    with open(config_path, encoding="utf-8") as f:
        config = yaml.safe_load(f)

    existing = config.get("reorganize", {}).get("studio_map", {})

    if args.report_only:
        print(f"Current studio_map: {len(existing)} entries")
        ja_mappings = {k: v for k, v in existing.items() if _is_japanese(k)}
        print(f"  Japanese→English mappings: {len(ja_mappings)}")
        for k, v in sorted(ja_mappings.items()):
            print(f"    {k} → {v}")
        return

    print(f"Existing studio_map: {len(existing)} entries")
    makers = scrape_makers(config, dry_run=args.dry_run)

    if not makers:
        print("No makers scraped — check cookies and site availability")
        return

    print(f"\nScraped {len(makers)} makers total")

    if args.dry_run:
        # Show sample mappings without modifying config
        new_map = build_studio_map(makers)
        merged = merge_studio_map(existing, new_map)
        added = {k: v for k, v in merged.items() if k not in existing}
        print(f"New mappings to add: {len(added)}")
        for k, v in sorted(added.items())[:30]:
            print(f"  {k} → {v}")
        if len(added) > 30:
            print(f"  ... and {len(added) - 30} more")
        print(f"\nFinal merged size would be: {len(merged)} entries")
        return

    # Build and merge
    new_map = build_studio_map(makers)
    merged = merge_studio_map(existing, new_map)
    added = {k: v for k, v in merged.items() if k not in existing}

    config.setdefault("reorganize", {})["studio_map"] = merged

    with open(config_path, "w", encoding="utf-8") as f:
        yaml.dump(config, f, default_flow_style=False, allow_unicode=True)

    print(f"Added {len(added)} new mappings")
    print(f"studio_map: {len(existing)} → {len(merged)} entries")
    print(f"Updated: {config_path}")


if __name__ == "__main__":
    main()
