#!/usr/bin/env python3
"""Snapshot NASA EONET events from the last 30 days into data/events.json.

    python3 fetch_data.py              # query EONET and rewrite data/events.json and data/meta.json
    python3 fetch_data.py --days 30    # same, window length in days (default 30)
    python3 fetch_data.py --from-dir path/to/dir   # convert saved responses (eonet_<category>.json) instead

Source: the NASA Earth Observatory Natural Event Tracker (EONET) v3 API,
https://eonet.gsfc.nasa.gov/docs/v3. EONET needs no API key and publishes no
formal rate limit; this script makes one request per category (thirteen in all,
plus a follow-up only when a window has to be split), pauses one second between
requests and identifies itself with a User-Agent that names this repository.

Endpoint, one call per category:
  https://eonet.gsfc.nasa.gov/api/v3/categories/<category>?status=all&days=<N>&limit=<LIMIT>
EONET caps a response at the requested limit and offers no offset parameter, so
when a response comes back exactly at the limit the window is split in half
with start= and end= (ISO dates) and both halves are requested again, until
every window is under the limit. Events seen in more than one window are
merged by id.

Outputs
  data/events.json  one compact record per event whose most recent observation
                    falls inside the window, newest first
  data/meta.json    snapshot time (UTC), window, per-category counts and errors,
                    the endpoints used and the request count

Short keys in events.json
  id  EONET event id              t   title
  c   category id (titles are in meta.json under "categories")
  d   date of the most recent observation (ISO 8601, UTC)
  f   date of the first observation in EONET's record, only when it differs from d
  n   number of observations (geometry entries) in EONET's record
  la, lo  latitude and longitude of the most recent observation; for a
          Polygon this is the centroid of the outer ring (flag g = "Polygon")
  m, mu   magnitude value and unit of the most recent observation, when EONET gives one
  s   source URL (the first source EONET lists), else the EONET API link
  si  source id (for example "InciWeb", "SIVolcano", "GDACS")
  x   date the event was closed, when EONET has closed it
"""
import datetime
import json
import pathlib
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parent
OUT = ROOT / "data"
API = "https://eonet.gsfc.nasa.gov/api/v3/categories/"
# EONET's thirteen categories and their titles (https://eonet.gsfc.nasa.gov/api/v3/categories).
# The title from a response is preferred; these are the fallback when a category has no events.
CATEGORIES = {
    "drought": "Drought", "dustHaze": "Dust and Haze", "earthquakes": "Earthquakes", "floods": "Floods",
    "landslides": "Landslides", "manmade": "Manmade", "seaLakeIce": "Sea and Lake Ice",
    "severeStorms": "Severe Storms", "snow": "Snow", "tempExtremes": "Temperature Extremes",
    "volcanoes": "Volcanoes", "waterColor": "Water Color", "wildfires": "Wildfires",
}
LIMIT = 1000           # per request; a response at exactly this size triggers a window split
PAUSE = 1.0            # seconds between requests
TIMEOUT = 60           # seconds per request
RETRIES = 2            # extra attempts on a network or 5xx error
USER_AGENT = "terramotus/2.0 (+https://github.com/phagehunter/terramotus)"


def log(*a):
    print(*a, file=sys.stderr, flush=True)


def get(url, attempt=0):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        if e.code >= 500 and attempt < RETRIES:
            time.sleep(PAUSE * (attempt + 2))
            return get(url, attempt + 1)
        raise RuntimeError(f"HTTP {e.code}") from e
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        if attempt < RETRIES:
            time.sleep(PAUSE * (attempt + 2))
            return get(url, attempt + 1)
        raise RuntimeError(str(e.reason if hasattr(e, "reason") else e)) from e


def fetch_category(cat, start, end, days, stats):
    """Return the events of one category inside [start, end], splitting the window when a response hits the limit."""
    def request(params):
        url = API + cat + "?" + urllib.parse.urlencode(params)
        stats["requests"] += 1
        stats["urls"].append(url)
        if stats["requests"] > 1:
            time.sleep(PAUSE)
        return get(url)

    def window(s, e, depth=0):
        params = {"status": "all", "limit": LIMIT}
        if depth == 0:
            params["days"] = days
        else:
            params.update({"start": s.date().isoformat(), "end": e.date().isoformat()})
        data = request(params)
        events = data.get("events") or []
        if len(events) >= LIMIT and (e - s) > datetime.timedelta(days=1):
            mid = s + (e - s) / 2
            stats["splits"] += 1
            log(f"  {cat}: {len(events)} events hit the limit, splitting {s.date()}..{e.date()}")
            return window(s, mid, depth + 1) + window(mid, e, depth + 1)
        return events

    return window(start, end)


def parse_date(s):
    return datetime.datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(datetime.timezone.utc)


def point_of(geometry):
    """[lon, lat] of a Point, or the centroid of a Polygon's outer ring (or the first ring of a MultiPolygon)."""
    c = geometry.get("coordinates")
    t = geometry.get("type")
    if t == "Point" and isinstance(c, list) and len(c) >= 2:
        return float(c[0]), float(c[1])
    ring = None
    if t == "Polygon" and c:
        ring = c[0]
    elif t == "MultiPolygon" and c and c[0]:
        ring = c[0][0]
    if ring:
        pts = [p for p in ring if isinstance(p, list) and len(p) >= 2]
        if pts:
            lon = sum(p[0] for p in pts) / len(pts)
            lat = sum(p[1] for p in pts) / len(pts)
            # Some GDACS flood polygons arrive as [lat, lon] instead of GeoJSON's [lon, lat].
            # Swap back when the pair is impossible as given; a swapped pair that still falls
            # inside both ranges cannot be told apart and is passed through as EONET gives it.
            if abs(lat) > 90 and abs(lon) <= 90:
                lon, lat = lat, lon
            return lon, lat
    return None, None


def compact(event, since):
    geoms = [g for g in event.get("geometry") or [] if g.get("date")]
    if not geoms:
        return None
    geoms.sort(key=lambda g: g["date"])
    latest, first = geoms[-1], geoms[0]
    latest_dt = parse_date(latest["date"])
    if latest_dt < since:
        return None
    cat = (event.get("categories") or [{}])[0]
    cat_id = cat.get("id") or "unknown"
    lon, lat = point_of(latest)
    src = (event.get("sources") or [{}])[0]
    rec = {
        "id": event["id"],
        "t": (event.get("title") or "").strip(),
        "c": cat_id,
        "d": latest_dt.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "n": len(geoms),
    }
    first_dt = parse_date(first["date"])
    if first_dt != latest_dt:
        rec["f"] = first_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    if lat is not None:
        rec["la"] = round(lat, 3)
        rec["lo"] = round(lon, 3)
        if latest.get("type") != "Point":
            rec["g"] = latest.get("type")
    if latest.get("magnitudeValue") is not None:
        rec["m"] = latest["magnitudeValue"]
        if latest.get("magnitudeUnit"):
            rec["mu"] = latest["magnitudeUnit"]
    rec["s"] = src.get("url") or event.get("link") or ""
    if src.get("id"):
        rec["si"] = src["id"]
    if event.get("closed"):
        rec["x"] = parse_date(event["closed"]).strftime("%Y-%m-%dT%H:%M:%SZ")
    return rec


def main(argv):
    days = 30
    from_dir = None
    args = argv[1:]
    while args:
        a = args.pop(0)
        if a == "--days":
            days = int(args.pop(0))
        elif a == "--from-dir":
            from_dir = pathlib.Path(args.pop(0))
        else:
            raise SystemExit(__doc__)

    now = datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0)
    since = now - datetime.timedelta(days=days)
    stats = {"requests": 0, "splits": 0, "urls": []}
    per_cat = {}
    raw = {}
    for cat in CATEGORIES:
        try:
            if from_dir:
                data = json.loads((from_dir / f"eonet_{cat}.json").read_text(encoding="utf-8"))
                events = data.get("events") or []
                per_cat[cat] = {"title": data.get("title") or CATEGORIES[cat]}
            else:
                log(f"{cat}: requesting")
                events = fetch_category(cat, since, now, days, stats)
                per_cat[cat] = {"title": next((c["title"] for e in events for c in e.get("categories", []) if c.get("id") == cat), CATEGORIES[cat])}
            raw[cat] = events
            per_cat[cat]["returned"] = len(events)
        except Exception as e:  # one failed category must not blank the others
            log(f"{cat}: FAILED {e}")
            per_cat[cat] = {"title": CATEGORIES[cat], "returned": 0, "error": str(e)}
            raw[cat] = []

    titles = {c: v["title"] for c, v in per_cat.items()}
    seen = {}
    for cat in CATEGORIES:
        for ev in raw[cat]:
            rec = compact(ev, since)
            if rec is None:
                continue
            prev = seen.get(rec["id"])
            if prev is None or rec["d"] > prev["d"]:
                seen[rec["id"]] = rec
    events = sorted(seen.values(), key=lambda r: (r["d"], r["t"]), reverse=True)
    for cat in CATEGORIES:
        per_cat[cat]["events"] = sum(1 for r in events if r["c"] == cat)

    meta = {
        "source": "NASA Earth Observatory Natural Event Tracker (EONET) v3",
        "source_url": "https://eonet.gsfc.nasa.gov/",
        "api_docs": "https://eonet.gsfc.nasa.gov/docs/v3",
        "endpoint": API + "<category>?status=all&days=" + str(days) + "&limit=" + str(LIMIT),
        "snapshot": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "window_days": days,
        "window_start": since.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "events": len(events),
        "observations": sum(r["n"] for r in events),
        "categories": per_cat,
        "failed": [c for c in CATEGORIES if "error" in per_cat[c]],
        "requests": stats["requests"],
        "window_splits": stats["splits"],
        "from_saved_responses": bool(from_dir),
    }
    OUT.mkdir(exist_ok=True)
    (OUT / "events.json").write_text(json.dumps(events, separators=(",", ":"), ensure_ascii=False) + "\n", encoding="utf-8")
    (OUT / "meta.json").write_text(json.dumps(meta, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    log(f"wrote data/events.json ({len(events)} events, {meta['observations']} observations) and data/meta.json; "
        f"{stats['requests']} requests, {stats['splits']} window splits, failed: {meta['failed'] or 'none'}")
    if len(meta["failed"]) == len(CATEGORIES):
        raise SystemExit("every category failed; leaving the previous snapshot in place is up to the caller")


if __name__ == "__main__":
    main(sys.argv)
