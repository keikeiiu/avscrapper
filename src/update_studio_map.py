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


def _is_real_name(name):
    """Filter out numeric IDs and other junk that isn't a real studio name."""
    if not name or len(name) < 2:
        return False
    if re.match(r'^\d+$', name):
        return False
    if re.match(r'^[\d\s,.\-+]+$', name):
        return False
    # Too generic single words
    if name.lower() in ('av', 'vr', 'top', 'new', 'best', 'sex'):
        return False
    return True


def _is_generic_name(name):
    """Names too generic to be useful as studio mappings."""
    generic = {'av', 'vr', 'top', 'new', 'best', 'sex', 'girl', 'man', 'hot',
               'love', 'max', 'ace', 'one', 'two', 'big', 'fun', 'joy', 'art'}
    return name.lower() in generic


def _split_name_parts(text):
    """Split a multi-name strong text into primary name + alternates.
    '1000人斬, 1000giri' → ['1000人斬', '1000giri']"""
    parts = [p.strip() for p in re.split(r'[,、]', text) if p.strip()]
    return [p for p in parts if _is_real_name(p)]


def _parse_makers_page(html, category, seen):
    """Parse javdb maker listing page. Return list of maker dicts."""
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, "html.parser")
    makers = []

    maker_links = soup.select("a[href*='/makers/']")
    if not maker_links:
        return makers

    for link in maker_links:
        href = link.get("href", "")
        if not href.startswith("/makers/"):
            continue

        strong = link.select_one("strong")
        if not strong:
            continue

        # Parse the strong text — may be multi-name: "蚊香社, PRESTIGE,プレステージ"
        # May also contain bracket alts: "マドンナ(Madonna)"
        strong_text = strong.get_text(strip=True)

        # Extract bracket content as alt names BEFORE splitting
        bracket_alts = re.findall(r'\(([^)]+)\)', strong_text)
        bracket_alts = [b.strip() for b in bracket_alts if _is_real_name(b.strip())]

        # Remove bracket text from the strong text for cleaner primary name
        clean_text = re.sub(r'\([^)]*\)', '', strong_text).strip()

        name_parts = _split_name_parts(clean_text)
        if not name_parts:
            continue

        primary_name = name_parts[0]
        if primary_name in seen:
            continue

        # Remaining parts (after first comma) are alternate names
        alt_names = name_parts[1:]

        # Add bracket alts
        for b in bracket_alts:
            if b not in name_parts and b not in alt_names and b != primary_name:
                alt_names.append(b)

        # Also check full link text for additional bracket text
        full_text = link.get_text(" ", strip=True)
        bracket_matches = re.findall(r'\(([^)]+)\)', full_text)
        for bm in bracket_matches:
            bm_clean = bm.strip()
            if _is_real_name(bm_clean) and bm_clean not in name_parts and bm_clean not in alt_names and bm_clean != primary_name:
                alt_names.append(bm_clean)

        # Deduplicate while preserving order
        alt_names = list(dict.fromkeys(alt_names))

        maker_type = "uncensored" if "uncensored" in category else "censored"

        makers.append({
            "name": primary_name,
            "alt_names": alt_names,
            "type": maker_type,
            "url": urljoin("https://javdb.com", href),
        })

    return makers


def _is_japanese(text):
    """Check if text contains Japanese characters (hiragana, katakana, kanji)."""
    return bool(re.search(r'[぀-ゟ゠-ヿ一-鿿]', text))


def _has_english(text):
    """Check if text contains ASCII letters (potential English name)."""
    return bool(re.search(r'[A-Za-z]{2,}', text))


def build_studio_map(makers):
    """Generate clean studio_map from scraped makers.

    Rules:
    - Japanese name → English canonical (e.g. マドンナ → Madonna)
    - English self-map (e.g. S1 NO.1 STYLE → S1 NO.1 STYLE) — only if not generic
    - Alt names → canonical (e.g. 蚊香社 → PRESTIGE)
    - Skip entries with no useful mapping (e.g. kanji-only with no English alt)
    """
    studio_map = {}

    for m in makers:
        name = m["name"]
        alt_names = m.get("alt_names", [])

        # Determine canonical: prefer English
        canonical = None
        if _has_english(name):
            canonical = name
        else:
            for alt in alt_names:
                if _has_english(alt):
                    canonical = alt
                    break

        if not canonical:
            canonical = name

        # Skip if canonical is too generic OR if there's no real mapping value
        # (Japanese-only name self-mapping isn't useful for reorganize)
        if _is_generic_name(canonical):
            continue
        # Skip entries where the only mapping is self-mapping a Japanese name
        if _is_japanese(name) and canonical == name and not alt_names:
            continue

        # Map primary name → canonical
        if name != canonical:
            studio_map[name] = canonical

        # Map alternates → canonical
        for alt in alt_names:
            if alt not in studio_map and alt != canonical:
                studio_map[alt] = canonical

        # Canonical self-map
        if canonical not in studio_map:
            studio_map[canonical] = canonical

    return studio_map


def merge_studio_map(existing_map, new_map):
    """Merge new studio_map into existing, keeping user overrides."""
    merged = dict(new_map)
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
