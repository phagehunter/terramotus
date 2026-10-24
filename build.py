#!/usr/bin/env python3
"""Build index.html and sitemap.xml from src/template.html, data/events.json and data/meta.json.

    python3 build.py

Every row of the events table and every number in the page's copy (counts,
snapshot time, window, category tallies, JSON-LD) is rendered here from the
snapshot, so crawlers and readers without JavaScript see the same events the
client script filters and sorts. Do not edit index.html by hand.
"""
import datetime
import html
import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent
EVENTS = json.loads((ROOT / "data" / "events.json").read_text(encoding="utf-8"))
META = json.loads((ROOT / "data" / "meta.json").read_text(encoding="utf-8"))
TEMPLATE = (ROOT / "src" / "template.html").read_text(encoding="utf-8")
URL = "https://curtishoffmann.com/terramotus/"
CATEGORY_ORDER = list(META["categories"].keys())
UNIT = {"hectare": "ha", "acres": "acres", "kts": "kt", "NM^2": "NM²", "km^2": "km²"}


def esc(s):
    return html.escape(str(s), quote=True)


def n(v):
    return f"{v:,}"


def parse(iso):
    return datetime.datetime.strptime(iso, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=datetime.timezone.utc)


def day(dt):
    return dt.strftime("%-d %b %Y")


def long_day(dt):
    return dt.strftime("%-d %B %Y")


def stamp(dt):
    return dt.strftime("%-d %B %Y, %H:%M UTC")


def coords(r):
    if "la" not in r:
        return "—"
    la, lo = r["la"], r["lo"]
    s = f"{abs(la):.2f}°{'N' if la >= 0 else 'S'}, {abs(lo):.2f}°{'E' if lo >= 0 else 'W'}"
    return ("≈ " + s) if r.get("g") else s


def size(r):
    if "m" not in r:
        return ""
    v = r["m"]
    txt = n(int(v)) if float(v).is_integer() else f"{v:,.1f}"
    return f"{txt} {UNIT.get(r.get('mu'), r.get('mu', ''))}".strip()


def rows_html():
    # Rows carry no data attributes or classes: the client script reads category, size and
    # observation count from the cell text, and the initial order (newest first) is the date sort.
    out = []
    for r in EVENTS:
        d = parse(r["d"])
        title_attr = f' title="Observed {r["n"]} times since {esc(day(parse(r["f"])))}"' if "f" in r else ""
        out.append(
            f'<tr><td>{esc(day(d))}</td>'
            f'<td>{esc(META["categories"][r["c"]]["title"])}</td>'
            f'<td><a href="{esc(r["s"])}" target="_blank" rel="noopener">{esc(r["t"])}</a></td>'
            f'<td>{esc(size(r))}</td>'
            f'<td{title_attr}>{r["n"]}</td>'
            f'<td>{esc(coords(r))}</td></tr>'
        )
    return "\n".join(out)


def category_buttons():
    out = ['<button type="button" class="chip" data-c="" aria-pressed="true">All <span class="cnt">%s</span></button>' % n(META["events"])]
    for c in CATEGORY_ORDER:
        v = META["categories"][c]
        count = v.get("events", 0)
        dis = "" if count else " disabled"
        out.append(f'<button type="button" class="chip" data-c="{esc(c)}" aria-pressed="false"{dis}>{esc(v["title"])} <span class="cnt">{n(count)}</span></button>')
    return "\n        ".join(out)


def category_list():
    items = []
    for c in CATEGORY_ORDER:
        v = META["categories"][c]
        count = v.get("events", 0)
        note = f"{n(count)} event{'s' if count != 1 else ''}" if count else "none in this window"
        if "error" in v:
            note = f"request failed ({esc(v['error'])})"
        items.append(f"<li><strong>{esc(v['title'])}</strong>: {note}</li>")
    return "\n        ".join(items)


def errors_html():
    failed = META.get("failed") or []
    if not failed:
        return ""
    names = ", ".join(f"{esc(META['categories'][c]['title'])} ({esc(META['categories'][c].get('error', 'error'))})" for c in failed)
    return (f'<p class="note warn" role="alert"><strong>Incomplete snapshot.</strong> EONET did not answer for {names} '
            f'when this snapshot was taken, so events in {"that category are" if len(failed) == 1 else "those categories are"} missing. '
            f'The next scheduled refresh will try again.</p>')


def json_ld(snapshot):
    person = {"@type": "Person", "name": "Curtis Hoffmann", "url": "https://curtishoffmann.com/"}
    return json.dumps({
        "@context": "https://schema.org",
        "@graph": [
            {"@type": "WebPage", "@id": URL, "url": URL,
             "name": "Terra Motus · Natural events on Earth in the last 30 days",
             "description": f"{n(META['events'])} natural events observed on Earth in the 30 days to {long_day(snapshot)}, from NASA's Earth Observatory Natural Event Tracker (EONET): wildfires, severe storms, floods, volcanoes, sea and lake ice and more, each linked to the agency that reported it.",
             "author": person, "dateModified": snapshot.strftime("%Y-%m-%dT%H:%M:%SZ"),
             "inLanguage": "en",
             "isPartOf": {"@type": "WebSite", "name": "Curtis Hoffmann", "url": "https://curtishoffmann.com/"},
             "primaryImageOfPage": URL + "assets/og-image.png"},
            {"@type": "Dataset", "@id": URL + "data/events.json",
             "name": "Terra Motus EONET snapshot",
             "description": f"{n(META['events'])} EONET events whose most recent observation falls in the {META['window_days']} days before {stamp(snapshot)}: id, title, category, latest and first observation dates, observation count, position of the latest observation, magnitude where given, source link and closing date. Refreshed every six hours by a GitHub Actions workflow.",
             "creator": person, "dateModified": snapshot.strftime("%Y-%m-%dT%H:%M:%SZ"),
             "temporalCoverage": f"{META['window_start'][:10]}/{META['snapshot'][:10]}",
             "isBasedOn": "https://eonet.gsfc.nasa.gov/",
             "sdPublisher": {"@type": "Organization", "name": "NASA Earth Science Data Systems", "url": "https://eonet.gsfc.nasa.gov/"},
             "keywords": ["NASA EONET", "natural events", "wildfires", "severe storms", "floods", "volcanoes", "sea ice", "Earth observation"],
             "distribution": {"@type": "DataDownload", "encodingFormat": "application/json", "contentUrl": URL + "data/events.json"}},
            {"@type": "BreadcrumbList", "itemListElement": [
                {"@type": "ListItem", "position": 1, "name": "Curtis Hoffmann", "item": "https://curtishoffmann.com/"},
                {"@type": "ListItem", "position": 2, "name": "Terra Motus", "item": URL}]},
        ],
    }, indent=1, ensure_ascii=False)


def main():
    snapshot = parse(META["snapshot"])
    start = parse(META["window_start"])
    active = [c for c in CATEGORY_ORDER if META["categories"][c].get("events")]
    top = max(active, key=lambda c: META["categories"][c]["events"]) if active else None
    data_kb = (ROOT / "data" / "events.json").stat().st_size / 1024
    rep = {
        "{{N_EVENTS}}": n(META["events"]),
        "{{N_OBS}}": n(META["observations"]),
        "{{N_CATS_ACTIVE}}": str(len(active)),
        "{{N_CATS}}": str(len(CATEGORY_ORDER)),
        "{{TOP_CAT}}": esc(META["categories"][top]["title"]) if top else "—",
        "{{TOP_CAT_N}}": n(META["categories"][top]["events"]) if top else "0",
        "{{SNAPSHOT}}": esc(stamp(snapshot)),
        "{{SNAPSHOT_DAY}}": esc(long_day(snapshot)),
        "{{SNAPSHOT_ISO}}": META["snapshot"],
        "{{SNAPSHOT_DATE}}": META["snapshot"][:10],
        "{{WINDOW_START}}": esc(long_day(start)),
        "{{WINDOW_DAYS}}": str(META["window_days"]),
        "{{REQUESTS}}": str(META["requests"]),
        "{{DATA_KB}}": f"{data_kb:,.0f}",
        "{{CAT_BUTTONS}}": category_buttons(),
        "{{CAT_LIST}}": category_list(),
        "{{ROWS}}": rows_html(),
        "{{ERRORS}}": errors_html(),
        "{{JSON_LD}}": json_ld(snapshot),
        "{{ASSET_VERSION}}": META["snapshot"].replace("-", "").replace(":", "")[:13],
    }
    page = TEMPLATE
    for k, v in rep.items():
        page = page.replace(k, v)
    assert "{{" not in page, "unreplaced placeholder: " + page[page.index("{{"):page.index("{{") + 40]
    (ROOT / "index.html").write_text(page, encoding="utf-8")
    sitemap = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" xmlns:image="http://www.google.com/schemas/sitemap-image/1.1">\n'
        f'  <url>\n    <loc>{URL}</loc>\n    <lastmod>{META["snapshot"][:10]}</lastmod>\n    <changefreq>daily</changefreq>\n    <priority>0.8</priority>\n'
        f'    <image:image><image:loc>{URL}assets/og-image.png</image:loc><image:title>Terra Motus</image:title></image:image>\n  </url>\n</urlset>\n'
    )
    (ROOT / "sitemap.xml").write_text(sitemap, encoding="utf-8")
    print(f"wrote index.html ({len(page.encode('utf-8')):,} bytes, {n(META['events'])} events, snapshot {stamp(snapshot)}) and sitemap.xml")


if __name__ == "__main__":
    main()
