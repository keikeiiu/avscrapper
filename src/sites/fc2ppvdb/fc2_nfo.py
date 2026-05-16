"""NFO XML parse, build, and merge utilities for FC2 video metadata.

Produces Kodi-compliant NFOs with <uniqueid>, <sorttitle>, <originaltitle>,
<runtime>, <art><poster>, plus legacy <num>/<website> as extensions.
"""

from xml.etree import ElementTree as ET
from xml.sax.saxutils import escape as _xml_escape


# Fields written as simple <key>value</key> in order
FLAT_FIELDS = [
    "title",
    "originaltitle",
    "sorttitle",
    "uniqueid",
    "num",
    "plot",
    "studio",
    "genre",
    "premiered",
    "runtime",
    "website",
]


def parse_nfo(path):
    """Read existing NFO, return (fields_dict, tags_list, art_dict).

    fields: all simple <key>text</key> elements
    tags: list of <tag> element texts
    art: dict of <art><key>url</key></art> (e.g. {'poster': 'https://...'})
    """
    tree = ET.parse(path)
    root = tree.getroot()

    fields = {}
    tags = []
    art = {}

    for child in root:
        if child.tag == "tag":
            if child.text:
                tags.append(child.text)
        elif child.tag == "art":
            for sub in child:
                art[sub.tag] = sub.text or ""
        else:
            fields[child.tag] = child.text or ""

    return fields, tags, art


def build_nfo(fields, tags=None, art=None):
    """Build Kodi-compliant NFO XML string."""
    lines = ['<?xml version="1.0" encoding="UTF-8"?>', "<movie>"]

    for key in FLAT_FIELDS:
        value = fields.get(key, "")
        if value is None:
            value = ""
        if key == "uniqueid" and value:
            lines.append(f'  <uniqueid type="fc2" default="true">{_xml_escape(str(value))}</uniqueid>')
        else:
            lines.append(f"  <{key}>{_xml_escape(str(value))}</{key}>")

    if art and any(art.values()):
        lines.append("  <art>")
        for sub_key in ("poster", "fanart"):
            if art.get(sub_key):
                lines.append(f"    <{sub_key}>{_xml_escape(str(art[sub_key]))}</{sub_key}>")
        lines.append("  </art>")

    if tags:
        for tag in tags:
            lines.append(f"  <tag>{_xml_escape(str(tag))}</tag>")

    lines.append("</movie>")
    return "\n".join(lines)


def merge_fields(existing, scraped):
    """Merge scraped data into existing NFO fields.

    Rules:
    - Never overwrite poster art
    - Title: scraped wins unless existing has a real title
    - Tags: additive merge
    - All other fields: scraped fills empty, never overwrites non-empty
    """
    merged = dict(existing)
    scraped = dict(scraped)

    # Never overwrite art
    scraped.pop("cover", None)
    scraped.pop("cover_url", None)
    scraped.pop("art", None)

    for key, val in scraped.items():
        if val is None or val == "":
            continue
        existing_val = existing.get(key, "")
        if existing_val is None:
            existing_val = ""
        if key == "title" and existing_val and existing_val != existing.get("num", ""):
            continue
        if existing_val and key != "tags":
            continue
        merged[key] = val

    return merged
