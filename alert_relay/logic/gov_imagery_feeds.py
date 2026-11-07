#!/usr/bin/env python3
"""Silent government weather imagery watcher (box side, no AI, no X). Built 10-21-26.

Replaces the X-search routine's every-30-min wakes. watch_quiet.py calls check() on its own
timer (every 30 min, only 5:00 AM to 8:30 PM PT) and wakes the assistant ONLY when at least one
strong candidate is found: ONE POST to the existing quiet webhook with all candidates batched:
  {"source":"quiet-watch","kind":"gov_imagery","page":"ANY","id":"govimg:<hash>","payload_id":"q-<hash>" (added by
   watch_quiet.py's single per-tick POST; if other items share the tick, this object is one entry of a
   {"kind":"batch","items":[...]} body), "checked":ISO,"slack_channel_id":"C0CAMNS8MQF","slack_channel":"#gov-weather-imagery","count":N,
   "items":[{"key","title","agency","source_name","source_url","image_url","published","why",
             "rights","credit","slack_text"}]}
"id" is a hash of the sorted item keys, so the same finds always carry the same id.

Sources (all public, no key, US federal = public domain):
  NASA Earth feed (nasa.gov/earth/feed, includes Earth Observatory Image of the Day)
  NASA Earth Observatory Natural Hazards RSS
  NOAA news RSS (noaa.gov/rss.xml)
  NOAA NESDIS news + Satellite Snapshots pages (HTML listing; new stories are opened for date/image)
Not used: X/Twitter (no API credentials on the box; X search is assistant-only), EONET (event points
  with no imagery), Esri/CARTO/Mapbox/Google/RainViewer (never), live GOES tiles (base-map rule).

Filters in code (same intent as gov_imagery_quiet.py): government source only, image must be on a
gov host, a real weather hazard named in the title/summary, a US location named, published within
LOOKBACK_H hours, not a routine outlook/forecast/admin story, no victims/injuries wording, no
non-US-government imagery credit (Copernicus/Sentinel/ESA/Maxar/Planet/EUMETSAT/Himawari/Getty/AP...).
Dedupe: gov_imagery_seen.json keys "feeds" (delivered) and "feed_checked" (NESDIS pages already opened).

Usage: gov_imagery_feeds.py --dry-run [--lookback-hours N]   one live check, print what would be sent;
                                                              no webhook, no file writes
       gov_imagery_feeds.py --once                            same as --dry-run
       gov_imagery_feeds.py --help
"""
import hashlib, html, json, os, re, sys
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from zoneinfo import ZoneInfo

# Adapted from the box gov-imagery feed filter. Judge rules and payload ids are unchanged.
BASE = os.environ.get("ALERT_RELAY_BASE", "/tmp/alert-relay")
SEEN_FILE = os.path.join(BASE, "gov_imagery_seen.json")
PT = ZoneInfo("America/Los_Angeles")
GOVIMG_POLL_SECONDS = 1800
WINDOW_START = (5, 0); WINDOW_END = (20, 30)      # PT, inclusive start times of a run
LOOKBACK_H = 36
MAX_ARTICLE_FETCHES = 10
PRUNE_DAYS = 30
SLACK_CHANNEL_ID = "C0CAMNS8MQF"; SLACK_CHANNEL = "#gov-weather-imagery"
UA = "WashingtonWeatherChasers gov imagery watcher (public feeds; contact via Grok Bot)"

FEEDS = [
    {"name": "nasa_earth", "agency": "NASA", "type": "rss", "url": "https://www.nasa.gov/earth/feed/"},
    {"name": "nasa_eo_hazards", "agency": "NASA Earth Observatory", "type": "rss", "url": "https://earthobservatory.nasa.gov/feeds/natural-hazards.rss"},
    {"name": "noaa_news", "agency": "NOAA", "type": "rss", "url": "https://www.noaa.gov/rss.xml"},
    {"name": "nesdis_news", "agency": "NOAA NESDIS", "type": "nesdis", "url": "https://www.nesdis.noaa.gov/news-events/search-news"},
    {"name": "nesdis_snapshots", "agency": "NOAA NESDIS", "type": "nesdis", "url": "https://www.nesdis.noaa.gov/imagery/collections/satellite-snapshots"},
]
GOV_HOST = r"^https://([a-z0-9-]+\.)*(nasa\.gov|noaa\.gov|usgs\.gov|weather\.gov|fema\.gov|usda\.gov|fs\.usda\.gov)/"
BANNED_HOST = r"(esri|arcgis|carto|mapbox|google|gstatic|rainviewer)"
HAZARD = (r"\b(tornado(es)?|nor.?easter|hurricane|tropical storm|tropical depression|cyclone|bomb cyclone|blizzard|snow(storm|fall|pack)?|"
          r"ice storm|freezing rain|flood(s|ing|ed)?|flash flood|storm surge|atmospheric river|wildfires?|fires?|smoke|haze|dust storm|"
          r"haboob|hail(storm)?|derecho|severe (storms?|weather|thunderstorms?)|thunderstorms?|supercell|squall line|lightning|"
          r"heat wave|record heat|extreme heat|landslides?|mudslides?|debris flow|avalanche|waterspout|winter storm|lake.effect|"
          r"cold (snap|outbreak|air)|arctic (blast|air)|deep freeze|power outages?|storm damage|damage)\b")
STRONG_HAZARD = (r"\b(tornado(es)?|nor.?easter|hurricane|tropical storm|blizzard|ice storm|flash flood(ing)?|flooding|storm surge|"
                 r"atmospheric river|wildfires?|dust storm|haboob|derecho|winter storm|heat wave|record heat|landslides?|mudslides?|avalanche)\b")
# hazard words must be in the TITLE, or a STRONG_HAZARD word in the summary (a stray "snow" in a summary is not enough)
US_PLACE = (r"\b(U\.?S\.?|United States|America(n)?|contiguous|Lower 48|East Coast|West Coast|Gulf Coast|Gulf of America|Gulf of Mexico|"
            r"Atlantic coast|Mid.Atlantic|New England|Great Lakes|Great Plains|Midwest|Southeast|Southwest|Northeast|Northwest|Pacific Northwest|"
            r"Rockies|Rocky Mountains|Appalachia(n)?|Sierra Nevada|Cascades|Ohio Valley|Mississippi|Tennessee Valley|Florida Panhandle|"
            r"Puerto Rico|Alabama|Alaska|Arizona|Arkansas|California|Colorado|Connecticut|Delaware|Florida|Georgia|Hawai.?i|Idaho|Illinois|"
            r"Indiana|Iowa|Kansas|Kentucky|Louisiana|Maine|Maryland|Massachusetts|Michigan|Minnesota|Missouri|Montana|Nebraska|Nevada|"
            r"New Hampshire|New Jersey|New Mexico|New York|North Carolina|North Dakota|Ohio|Oklahoma|Oregon|Pennsylvania|Rhode Island|"
            r"South Carolina|South Dakota|Texas|Utah|Vermont|Virginia|Washington|West Virginia|Wisconsin|Wyoming|Carolinas|Dakotas)\b")
NON_EVENT = (r"\b(outlook|forecast(s|ers)? (for|calls)|webinar|award(s|ed)?|contract|budget|partnership|decommission|cessation|"
             r"administrative|deorbit|launch(es|ed)?|anniversary|ocean facts|podcast|teacher|education|careers?|hiring|grants?|funding|"
             r"media advisory|tropical cyclone report|post.analysis|season (recap|summary)|climate (change|trend)|fingerprint|"
             r"El Ni[nñ]o|La Ni[nñ]a|drought|crops?|cotton|test(s|ing)? faster|data users|instrument|commercial data|did you know|tips?|prepare|preparedness)\b")
SKIP_HARM = r"(injur|victim|dead\b|death|died|killed|fatal|bodies|missing person|hospital|casualt|trapped|condolence|passed away)"
NON_USGOV_CREDIT = r"(copernicus|sentinel-?\d|\besa\b|european space agency|maxar|planet labs|planetscope|airbus|eumetsat|himawari|jaxa|meteosat|getty|reuters|ap photo|associated press|©|\(c\) )"
STRONG_IMAGERY = r"\b(satellite|imagery|image[sd]?|photo(s|graph)?|aerial|loop|animation|time.?lapse|captured|observes?|monitors?|watches|views?|sees|spots|tracks|nighttime lights|video)\b"
MONTHS = "January|February|March|April|May|June|July|August|September|October|November|December"


def _load(p, d):
    try:
        with open(p) as f: return json.load(f)
    except Exception: return d

def _save(p, data):
    tmp = p + ".tmp.feeds"
    with open(tmp, "w") as f: json.dump(data, f, indent=1)
    os.replace(tmp, p)

def in_window(now):
    t = now.astimezone(PT); hm = (t.hour, t.minute)
    return WINDOW_START <= hm <= WINDOW_END

def _text(s):
    s = re.sub(r"<!\[CDATA\[|\]\]>", "", s or "")
    s = re.sub(r"<[^>]+>", " ", s)
    return re.sub(r"\s+", " ", html.unescape(s)).strip()

def _tag(block, t):
    m = re.search(r"<%s[^>]*>(.*?)</%s>" % (t, t), block, re.S)
    return m.group(1) if m else ""

def _key(url):
    return "feed:" + hashlib.sha1(url.strip().rstrip("/").encode()).hexdigest()[:12]

def _first_img(h):
    h = re.sub(r"<!\[CDATA\[|\]\]>", "", h or "")
    for m in re.finditer(r'<img[^>]*?\ssrc="([^"]+)"', h):
        u = html.unescape(m.group(1))
        if re.search(r"\.(jpe?g|png|gif|webp)", u, re.I): return u
    m = re.search(r'(?:enclosure|media:content|media:thumbnail)[^>]*url="([^"]+)"', h)
    return html.unescape(m.group(1)) if m else None

def fetch(session, url, timeout=25):
    r = session.get(url, headers={"User-Agent": UA, "Accept": "*/*"}, timeout=timeout)
    r.raise_for_status()
    return r.text

def parse_rss(xml, feed):
    out = []
    for b in re.findall(r"<item>(.*?)</item>", xml, re.S):
        link = _text(_tag(b, "link")); pub = None
        try: pub = parsedate_to_datetime(_text(_tag(b, "pubDate"))).astimezone(timezone.utc)
        except Exception: pass
        desc_html = _tag(b, "description") + _tag(b, "content:encoded")
        out.append({"feed": feed["name"], "agency": feed["agency"], "title": _text(_tag(b, "title")), "url": link,
                    "published": pub, "summary": _text(desc_html)[:600], "image_url": _first_img(desc_html),
                    "credit_text": _text(desc_html), "lead": _text(desc_html)[:600]})
    return out

def nesdis_slugs(page):
    return sorted({"https://www.nesdis.noaa.gov" + m for m in re.findall(r'href="(/news/[a-z0-9-]{12,})"', page)})

def parse_nesdis_article(page, url):
    meta = lambda p: (re.search(r'<meta (?:property|name)="%s" content="([^"]*)"' % p, page) or [None, ""])[1]
    pub = None   # publication date = first "Month D, YYYY" in the page body (meta tags can hold future event dates)
    start = page.find("usa-layout-docs__main"); start = start if start >= 0 else max(page.find("<body"), 0)
    for m in re.finditer(r"\b(%s) (\d{1,2}), (20\d\d)\b" % MONTHS, page[start:]):
        try: d = datetime.strptime(m.group(0), "%B %d, %Y").replace(hour=12, tzinfo=PT).astimezone(timezone.utc)
        except Exception: continue
        if d <= datetime.now(timezone.utc) + timedelta(hours=12): pub = d; break
    body = page[start:]           # main column only (avoids nav menus); first part is the story text
    body = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", body, flags=re.S)
    return {"feed": "nesdis", "agency": "NOAA NESDIS", "title": html.unescape(meta("og:title")), "url": url, "published": pub,
            "summary": html.unescape(meta("og:description"))[:600], "image_url": html.unescape(meta("og:image")) or None,
            "credit_text": _text(body)[:6000], "lead": _text(body)[:1500]}

def judge(e, now, lookback_h):
    """Return (ok, reason_or_why)."""
    t = (e.get("title") or "") + " . " + (e.get("summary") or "")
    if not e.get("published"): return False, "no publish date"
    if e["published"] < now - timedelta(hours=lookback_h): return False, "older than %dh" % lookback_h
    if re.search(SKIP_HARM, t, re.I): return False, "victims/injuries wording"
    if re.search(NON_EVENT, e.get("title") or "", re.I): return False, "routine/outlook/admin story"
    hz = re.search(HAZARD, e.get("title") or "", re.I) or re.search(STRONG_HAZARD, t, re.I)
    if not hz: return False, "not a weather hazard"
    us = re.search(US_PLACE, t + " . " + (e.get("lead") or ""))
    if not us: return False, "no US location named"
    img = e.get("image_url")
    if not img: return False, "no image found"
    if re.search(BANNED_HOST, img, re.I): return False, "banned imagery host"
    if not re.search(GOV_HOST, img, re.I): return False, "image not on a US gov host"
    cr = re.search(NON_USGOV_CREDIT, (e.get("credit_text") or "") + " " + (e.get("summary") or ""), re.I)
    if cr: return False, "non-US-gov imagery credit (%s)" % cr.group(0).strip()
    im = re.search(STRONG_IMAGERY, t, re.I)
    if not im and e.get("feed") not in ("nesdis", "nasa_eo_hazards"): return False, "no sign of real imagery"
    goes = " (GOES satellite imagery)" if re.search(r"\bGOES", t) else ""
    return True, "hazard '%s', US place '%s', %s image%s" % (hz.group(0), us.group(0), e["agency"], goes)

def check(session, seen_doc, now, lookback_h=LOOKBACK_H, max_fetch=MAX_ARTICLE_FETCHES):
    """One pass over all sources. Returns (candidates, checked_marks, report). Writes nothing."""
    delivered = (seen_doc or {}).get("feeds") or {}; checked = (seen_doc or {}).get("feed_checked") or {}
    entries, errors, marks = [], {}, {}
    fetched = 0
    for f in FEEDS:
        try: page = fetch(session, f["url"])
        except Exception as ex: errors[f["name"]] = type(ex).__name__; continue
        if f["type"] == "rss":
            entries += parse_rss(page, f)
        else:
            for u in nesdis_slugs(page):
                k = _key(u)
                if k in delivered or k in checked or k in marks: continue
                if fetched >= max_fetch: break
                fetched += 1
                try: entries.append(parse_nesdis_article(fetch(session, u), u)); marks[k] = now.isoformat()
                except Exception as ex: errors[u] = type(ex).__name__
    cands, skipped, near, keys = [], {}, [], set()
    for e in entries:
        if not e.get("url"): continue
        k = _key(e["url"])
        if k in keys: continue
        keys.add(k)
        if k in delivered: skipped["already sent"] = skipped.get("already sent", 0) + 1; continue
        ok, why = judge(e, now, lookback_h)
        if not ok:
            skipped[why] = skipped.get(why, 0) + 1
            if not why.startswith("older"): near.append({"title": e["title"][:90], "agency": e["agency"], "reason": why})
            continue
        cands.append(item_from(e, k, why))
    cands.sort(key=lambda c: c["published"] or "", reverse=True)
    return cands, marks, {"entries_examined": len(entries), "articles_opened": fetched, "skipped": skipped,
                          "recent_rejects": near[:12], "errors": errors}

def item_from(e, k, why):
    pub = e["published"]; when = pub.astimezone(PT).strftime("%-I:%M %p PT %-m-%-d") if pub else ""
    title = re.sub(r"\s+-\s+NASA Science$", "", e["title"] or "").strip()
    credit = "Image: " + e["agency"]
    slack = "*%s* (%s), published %s\n%s\nImage: %s\nSource: %s\nCredit: %s\nFederal source: generally public domain (still credit it). Found by the silent feed watcher: %s" % (
        title, e["agency"], when, (e.get("summary") or "")[:300], e.get("image_url"), e["url"], credit, why)
    return {"key": k, "title": title, "agency": e["agency"], "source_name": e["feed"], "source_url": e["url"],
            "image_url": e.get("image_url"), "published": pub.isoformat() if pub else None, "why": why,
            "rights": "federal_public_domain", "credit": credit, "slack_text": slack}

def payload(cands, now):
    pid = "govimg:" + hashlib.sha256(json.dumps(sorted(c["key"] for c in cands)).encode()).hexdigest()[:16]
    return {"source": "quiet-watch", "kind": "gov_imagery", "page": "ANY", "id": pid, "checked": now.isoformat(),
            "slack_channel_id": SLACK_CHANNEL_ID, "slack_channel": SLACK_CHANNEL, "count": len(cands), "items": cands}

def record(seen_doc, delivered_items, marks, now):
    """Return an updated seen doc (caller saves). Keeps the X-routine keys untouched."""
    doc = dict(seen_doc or {})
    cut = now - timedelta(days=PRUNE_DAYS)
    for key in ("feeds", "feed_checked"):
        doc[key] = {k: v for k, v in (doc.get(key) or {}).items() if datetime.fromisoformat(v) > cut}
    for it in delivered_items: doc["feeds"][it["key"]] = now.isoformat()
    doc["feed_checked"].update(marks)
    return doc

def load_seen(): return _load(SEEN_FILE, {})
def save_seen(doc):
    cur = _load(SEEN_FILE, {})       # re-read so concurrent X-routine keys are not clobbered
    for k in ("feeds", "feed_checked"): cur[k] = doc.get(k, {})
    _save(SEEN_FILE, cur)


USAGE = __doc__.strip()

def main(argv):
    if any(a in ("-h", "--help") for a in argv): print(USAGE); return 0
    look = LOOKBACK_H; rest = []
    i = 0
    while i < len(argv):
        if argv[i] == "--lookback-hours" and i + 1 < len(argv): look = float(argv[i + 1]); i += 2; continue
        rest.append(argv[i]); i += 1
    if not rest or any(a not in ("--dry-run", "--once") for a in rest):
        print("this script only runs standalone as a safe test; watch_quiet.py runs it live.\n\n" + USAGE, file=sys.stderr); return 2
    import requests
    now = datetime.now(timezone.utc)
    cands, marks, rep = check(requests.Session(), load_seen(), now, look)
    out = {"mode": "dry-run (no webhook sent, no files written)", "now_pt": now.astimezone(PT).strftime("%-I:%M %p PT %-m-%-d-%y"),
           "in_window_now": in_window(now), "lookback_hours": look, "would_wake": bool(cands),
           "would_post": payload(cands, now) if cands else None, "report": rep, "nesdis_pages_would_mark_checked": len(marks)}
    print(json.dumps(out, indent=1, ensure_ascii=False, default=str)); return 0

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
