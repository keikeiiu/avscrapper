"""NFO XML parse, build, and merge utilities for FC2 video metadata.

Used by the enricher (future) to read existing NFOs and merge scraped data
without overwriting user-curated fields (cover, existing tags).
"""

from xml.etree import ElementTree as ET


NFO_TEMPLATE = """<?xml version="1.0" encoding="UTF-8"?>
<movie>
  <title>{title}</title>
  <num>{num}</num>
  <outline>{outline}</outline>
  <plot>{plot}</plot>
  <studio>{studio}</studio>
  <genre>{genre}</genre>
  <premiered>{premiered}</premiered>
  <cover>{cover}</cover>
  <website>{website}</website>
</movie>
"""


def parse_nfo(path):
    """Parse an existing NFO file. Returns a dict of field→value and list of <tag> texts.
    Returns (fields, tags) — fields is a dict, tags is a list.
    """
    tree = ET.parse(path)
    root = tree.getroot()

    fields = {}
    for child in root:
        if child.tag == "tag":
            continue
        fields[child.tag] = child.text or ""

    tags = [child.text for child in root if child.tag == "tag" and child.text]

    return fields, tags


def build_nfo(fields, tags=None):
    """Build an NFO XML string from a fields dict and optional tags list."""
    lines = ['<?xml version="1.0" encoding="UTF-8"?>', "<movie>"]
    for key in ["title", "num", "outline", "plot", "studio", "genre", "premiered", "cover", "website"]:
        value = fields.get(key, "")
        if value is None:
            value = ""
        lines.append(f"  <{key}>{value}</{key}>")

    if tags:
        for tag in tags:
            lines.append(f"  <tag>{tag}</tag>")
    else:
        lines.append("  <tag></tag>")

    lines.append("</movie>")
    return "\n".join(lines)


def merge_fields(existing, scraped):
    """Merge scraped data into existing NFO fields.

    Rules:
    - Never overwrite cover
    - Title: scraped wins if existing is just the code
    - Tags: additive merge
    - All other fields: scraped fills empty, never overwrites non-empty
    """
    merged = dict(existing)
    scraped = dict(scraped)

    # Cover is sacred — never overwrite
    scraped.pop("cover", None)
    scraped.pop("cover_url", None)

    for key, val in scraped.items():
        if val is None or val == "":
            continue
        existing_val = existing.get(key, "")
        if existing_val is None:
            existing_val = ""
        if key == "title" and existing_val and existing_val != existing.get("num", ""):
            continue  # Don't overwrite a real title
        if existing_val and key != "tags":
            continue  # Don't overwrite non-empty fields
        merged[key] = val

    return merged
