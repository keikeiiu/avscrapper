"""JAV Kodi NFO parse, build, and merge utilities.

Richer than FC2: nested <actor> elements, <label>, <series>, <director>,
<rating>, <votes>, multiple <genre>/<tag>, <art> with poster+fanart.
"""

from xml.etree import ElementTree as ET
from xml.sax.saxutils import escape as _xml_escape


FLAT_FIELDS = [
    "title",
    "originaltitle",
    "sorttitle",
    "uniqueid",
    "plot",
    "studio",
    "label",
    "series",
    "director",
    "premiered",
    "year",
    "runtime",
    "rating",
    "votes",
    "website",
]


def parse_nfo(path):
    """Read existing NFO. Returns (fields, genres, tags, actors, art).

    fields: flat <key>text</key> elements
    genres: list of <genre> texts
    tags: list of <tag> texts
    actors: list of {"name": ..., "thumb": ...} dicts
    art: dict of <art><key>url</key></art>
    """
    tree = ET.parse(path)
    root = tree.getroot()

    fields = {}
    genres = []
    tags = []
    actors = []
    art = {}

    for child in root:
        if child.tag == "genre":
            if child.text:
                genres.append(child.text)
        elif child.tag == "tag":
            if child.text:
                tags.append(child.text)
        elif child.tag == "actor":
            actor = {}
            for sub in child:
                if sub.tag in ("name", "thumb"):
                    actor[sub.tag] = sub.text or ""
            if actor.get("name"):
                actors.append(actor)
        elif child.tag == "art":
            for sub in child:
                art[sub.tag] = sub.text or ""
        else:
            fields[child.tag] = child.text or ""

    return fields, genres, tags, actors, art


def build_nfo(fields, genres=None, tags=None, actors=None, art=None):
    """Build JAV Kodi NFO XML string."""
    lines = ['<?xml version="1.0" encoding="UTF-8"?>', "<movie>"]

    for key in FLAT_FIELDS:
        value = fields.get(key, "")
        if value is None:
            value = ""
        if key == "uniqueid" and value:
            lines.append(f'  <uniqueid type="jav" default="true">{_xml_escape(str(value))}</uniqueid>')
        else:
            lines.append(f"  <{key}>{_xml_escape(str(value))}</{key}>")

    if art and any(art.values()):
        lines.append("  <art>")
        for sub_key in ("poster", "fanart"):
            if art.get(sub_key):
                lines.append(f"    <{sub_key}>{_xml_escape(str(art[sub_key]))}</{sub_key}>")
        lines.append("  </art>")

    if genres:
        for g in genres:
            lines.append(f"  <genre>{_xml_escape(str(g))}</genre>")
    if tags:
        for t in tags:
            lines.append(f"  <tag>{_xml_escape(str(t))}</tag>")
    if actors:
        for a in actors:
            lines.append("  <actor>")
            lines.append(f"    <name>{_xml_escape(str(a.get('name', '')))}</name>")
            if a.get("thumb"):
                lines.append(f"    <thumb>{_xml_escape(str(a['thumb']))}</thumb>")
            lines.append("  </actor>")

    lines.append("</movie>")
    return "\n".join(lines)


def nfo_to_db_data(parsed):
    """Convert parsed NFO data back to DB-ready dict for upsert_scraped_jav()."""
    fields, genres, tags, actors, art = parsed
    data = {}
    data["full_number"] = fields.get("uniqueid", "")
    data["title"] = fields.get("title", "")
    data["plot"] = fields.get("plot", "")
    data["studio"] = fields.get("studio", "")
    data["label"] = fields.get("label", "")
    data["series"] = fields.get("series", "")
    data["director"] = fields.get("director", "")
    data["release_date"] = fields.get("premiered", "")
    data["year"] = fields.get("year", "")
    data["runtime"] = fields.get("runtime", "")
    data["rating"] = float(fields["rating"]) if fields.get("rating") else None
    data["votes"] = int(fields["votes"]) if fields.get("votes") else None
    data["url"] = fields.get("website", "")
    data["genres"] = genres if genres else []
    data["tags"] = tags if tags else []
    data["actors"] = actors if actors else []
    data["cover_url"] = art.get("poster", "")
    data["fanart_urls"] = [art["fanart"]] if art.get("fanart") else []
    return data


def merge_fields(existing, scraped):
    """Merge scraped data into existing NFO fields.

    Rules:
    - Never overwrite existing art (poster/fanart)
    - Title: scraped fills empty, doesn't overwrite real titles
    - Genres/tags/actors: additive merge (deduplicated by name)
    - Other fields: scraped fills empty, never overwrites non-empty
    """
    merged = dict(existing)
    scraped = dict(scraped)

    scraped.pop("art", None)
    scraped.pop("cover", None)
    scraped.pop("cover_url", None)
    scraped.pop("fanart_urls", None)

    for key, val in scraped.items():
        if val is None or val == "":
            continue
        existing_val = existing.get(key, "")
        if existing_val is None:
            existing_val = ""
        if key == "title" and existing_val:
            continue
        if existing_val and key not in ("genres", "tags", "actors"):
            continue
        merged[key] = val

    return merged


def merge_actors(existing, scraped):
    """Add scraped actors to existing list, deduplicated by name."""
    names = {a.get("name", "") for a in existing}
    for a in scraped:
        if a.get("name") and a["name"] not in names:
            names.add(a["name"])
            existing.append(a)
    return existing
