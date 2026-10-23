#!/usr/bin/env python3
# Adapted from the box quiet watcher for the GitHub Actions relay.
# Filters, batch payload shape, payload ids, and the 9 PM-2 AM / 9 PM-5 AM PT hold are unchanged.
"""Quiet routine-alert watcher (no AI while idle).

Polls api.weather.gov every ~30 min and wakes an agent ONLY on a NEW
qualifying routine alert:
  WA  - any new Washington LAND alert postable per /workspace/alert_style.md
        (skip Small Craft Advisory + Dense Fog Advisory; marine-only skipped)
  USA - graphic-worthy major alerts per alert_style.md (explicit list below)

Earthquakes: also polls USGS 2.5_day GeoJSON on the 5-min master cycle
  (USGS feeds update ~every 5 min; never poll faster). Qualifying quakes
  (see classify_quake) are POSTed to the same QUIET webhook as
  {"source":"quiet-watch","kind":"earthquake","page":"WA"|"USA",...}.
  Quakes are NOT warnings / NOT urgent-auto-post; the woken routine handles
  approval + graphics. Dedupe is in seen_quakes_quiet.json (separate from
  alert seen_quiet.json); an unseen quake first sighted >30 min after its
  event time is seeded silently so downtime never wakes for stale quakes.
  The 6 POSTs/hour cap is shared with routine alerts.

Mountain passes: also polls the WSDOT MountainPass JSON (see passes_quiet.py)
  every 15 min inside this 5-min master loop (general NWS alerts are on a
  30-min cadence; the quake cadence is unchanged). Wakes
  ONLY on notable changes vs passes_quiet_state.json (closure/reopen,
  avalanche closure, chains/traction required, restriction added/lifted/
  changed, new snow on roadway; temperature alone never wakes). All changes
  in one poll are batched into ONE POST:
  {"source":"quiet-watch","kind":"mountain-pass","page":"WA",
   "changes":[{"pass":...,"change":...,"details":...}],"checked":ISO,"id":...}
  (extra deterministic "id" added for pending dedupe). Pass state advances
  only after POST success or after queueing to pending_quiet.json; pending
  items carry kind="mountain-pass" and flushing them marks no alert/quake seen.
  First run seeds passes_quiet_state.json silently (legacy wa_extras copy if
  it maps, replaced by the live snapshot).

SPC Day 1 + Day 2 outlooks (rule 2026-10-20): polls SPC day1 and day2
  categorical GeoJSON (spc_quiet.py) every 30 min. USA item when a non-WA
  state is SLGT+; WA item when ANY category (incl. TSTM) touches Washington.
  One item per page/day/outlook date; refire only on an upgrade (USA: a state
  rising to ENH+; WA: Washington's category rising). Payload {"source":
  "quiet-watch","kind":"spc-outlook","page":"USA"|"WA","day":1|2,"risk",
  "states","issued","valid","expires","id":"spc:d<day>:<issued>:<page>:<risk>"}.
  A page/day/date is recorded only after POST success or queueing; first
  sighting of each day (and the schema-2 upgrade) seeds silently.

Hurricane cone: also polls NHC CurrentStorms.json (+ per-storm track KMZ)
  (hurricanes_quiet.py) every 30 min. Wakes for a NEW AL/EP/CP tropical
  storm/hurricane with a cone (first), and a SECOND wake >=20h later only if
  approaching the lower 48/Hawaii (documented bbox heuristic there). Never
  WP/typhoon. Payload {"source":"quiet-watch","kind":"hurricane-cone",
  "page":"USA","storm":"AL092026 name","basin":"AL","second":false,
  "id":"nhc:<stormid>:<issued-or-day>"}. State hurricanes_quiet_state.json
  advances only after POST success or queueing; first run seeds silently.

Government imagery (10-21-26): every 30 min, only 5:00 AM to 8:30 PM PT,
  gov_imagery_feeds.check() reads NASA / NOAA / NESDIS public feeds (no X, no key).
  ONLY when it finds at least one strong candidate does it queue ONE item
  {"source":"quiet-watch","kind":"gov_imagery","page":"ANY","id":"govimg:<hash>","checked":ISO,
   "slack_channel_id":"C0CAMNS8MQF","slack_channel":"#gov-weather-imagery","count":N,
   "items":[{key,title,agency,source_name,source_url,image_url,published,why,rights,credit,slack_text}]}
  which goes out in this tick's single POST. Dedupe: gov_imagery_seen.json keys
  "feeds" (recorded only once queued) and "feed_checked" (NESDIS pages opened).

Overnight hold (10-22-26): USA 9 PM-2 AM PT, WA 9 PM-5 AM PT. No prep wakes: held alerts are only
  remembered (state overnight_held); the first poll after the window opens re-checks current NWS data
  (alerts + updates) and sends normal wakes for what is still active (current Update if replaced; skips
  anything ending within 60 min). Same catch-up after a freeze/outage (state alert_outages).

Delivery (10-21-26 audit fix): every source (alerts, quakes, passes, SPC, NHC,
  leftovers) is queued to pending_quiet.json during the tick,
  then deliver() sends ONE POST per tick with everything pending. One item: the
  item itself plus "payload_id". Several: {"source":"quiet-watch","kind":"batch",
  "payload_id":...,"tick":ISO,"count":N,"items":[...]}. payload_id is identical
  on a resend after a timeout/failure (payload_seen.py; the routine runs
  `python3 /workspace/urgent_watch/payload_seen.py ID` and ignores exit 3).
  Legacy notes below describe the item shapes, which are unchanged.
  - If QUIET_WEBHOOK_URL / QUIET_WEBHOOK_AUTH are in env: POST one JSON item
    per alert {"source":"quiet-watch","page":"WA"|"USA","event":...,
    "area":...,"id":...,"expires":...,...} (same Bearer-auth mechanism as
    watch.py). A NEW routine named 'quiet-weather-alert-trigger' should own
    that URL; it is NOT created by this script.
  - If absent: log "no quiet webhook configured" and append to the pending
    queue file instead of failing. Pending items are retried (flushed)
    first on every poll once a webhook is configured.
  - Non-urgent POSTs capped at 6/hour; excess goes to the pending queue.
  - An ID is marked seen only after its POST succeeds OR it is queued.
    Pending-queue IDs also dedupe, so nothing is queued/posted twice.

Isolation from the urgent watcher: this script only READS watch.py's
seen.json plus /workspace/{wa,usa}_alerts/seen.json (via watch.other_seen_ids)
and writes ONLY seen_quiet.json / state_quiet.json / pending_quiet.json /
watch_quiet.{log,pid}. It never writes urgent seen/state, so an urgent
tornado/flash-flood alert can never be suppressed by the quiet path.
Alerts that watch.classify() already handles (urgent) are skipped here.

Usage: watch_quiet.py                run forever
       watch_quiet.py --dry-run      one live poll, print only, change nothing
       watch_quiet.py --once         same as --dry-run (10-21-26: no longer delivers)
       watch_quiet.py --help         usage; unknown args print usage and exit 2
Secrets come ONLY from env and are never logged or written.
"""
import json, logging, logging.handlers, os, re, signal, sys, time
from datetime import datetime, timedelta, timezone
_LOGIC = os.path.dirname(os.path.abspath(__file__))
_RELAY = os.path.dirname(_LOGIC)
for _p in (_RELAY, _LOGIC):
    if _p not in sys.path:
        sys.path.insert(0, _p)
import net as requests
import watch as urgent  # reuse is_washington, ugc_states, major_city_hit, helpers
try:
    import claim_lock
except Exception:
    claim_lock = None
import passes_quiet
import spc_quiet
import payload_seen  # 10-21-26: one batched POST per tick + stable payload_id
import hurricanes_quiet
import gov_imagery_feeds  # 10-21-26: silent gov imagery check (replaces the X-search routine wakes)

# ---------------- config ----------------
POLL_SECONDS = 300  # master tick: USGS quakes and due checks for the slower sources
ALERT_POLL_SECONDS = 1800  # general NWS alerts every 30 min, so neighboring NWS offices can finish issuing before one combined post
MAX_POSTS_PER_HOUR = 6   # 10-21-26: counts batched POSTs (one per tick at most)
BATCH_ONE_POST = True    # 10-21-26 audit fix: all sources queue, deliver() sends ONE POST per tick
SEED_RECENT_MINUTES = 15      # on first run, older active alerts are seeded seen silently
SEEN_PRUNE_DAYS = 3
BASE = os.environ.get("ALERT_RELAY_BASE", "/tmp/alert-relay")
SEEN_FILE = BASE + "/seen_quiet.json"
STATE_FILE = BASE + "/state_quiet.json"
PENDING_FILE = BASE + "/pending_quiet.json"
SEEN_QUAKES_FILE = BASE + "/seen_quakes_quiet.json"
PASSES_FILE = passes_quiet.PASSES_STATE_FILE
PASS_POLL_SECONDS = passes_quiet.PASS_POLL_SECONDS  # 900s; quake poll stays 300s, general NWS alert poll is 1800s
SPC_FILE = spc_quiet.SPC_STATE_FILE
SPC_POLL_SECONDS = spc_quiet.SPC_POLL_SECONDS  # 1800s (30 min); Day 1 + Day 2 each poll
HURRICANES_FILE = hurricanes_quiet.HURRICANES_STATE_FILE
NHC_POLL_SECONDS = hurricanes_quiet.NHC_POLL_SECONDS  # 1800s (30 min); NHC advisories every ~3-6h
USGS_URL = "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/2.5_day.geojson"  # covers WA M3.5 (2.5_day, ~5-min updates)
QUAKE_RECENT_MINUTES = 30     # first sighting older than this: seed silently, do not wake
LOG_FILE = BASE + "/watch_quiet.log"
PID_FILE = BASE + "/watch_quiet.pid"
SCHEMA = 1

WA_SKIP_EVENTS = {"Small Craft Advisory", "Dense Fog Advisory"}
# USA: always graphic-worthy on a NEW 'Alert' (never on Update).
USA_ALWAYS = {
    "Winter Storm Warning", "Winter Storm Watch",
    "Blizzard Warning", "Blizzard Watch",
    "Ice Storm Warning", "Ice Storm Watch",
    "Hurricane Warning", "Hurricane Watch",
    "Tropical Storm Warning", "Tropical Storm Watch",
    "Storm Surge Warning", "Storm Surge Watch",
    "Extreme Heat Warning",
    "Lake Effect Snow Warning",
    "Hurricane Force Wind Warning",
    "Red Flag Warning",
    "Freeze Warning",          # previously covered on USA page (freeze graphics exist)
    "Tornado Watch", "Severe Thunderstorm Watch",
}
USA_SKIP_EVENTS = {"Winter Weather Advisory"}  # outside WA; WA WWA handled by WA path
# ----------------------------------------
log = logging.getLogger("quiet_watch")

def setup_logging(to_stdout=False):
    log.setLevel(logging.INFO)
    h = logging.StreamHandler(sys.stdout) if to_stdout else logging.handlers.RotatingFileHandler(LOG_FILE, maxBytes=256*1024, backupCount=2)
    h.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    log.addHandler(h)

load_json, save_json, parse_time = urgent.load_json, urgent.save_json, urgent.parse_time

def zone_codes(p):
    codes = [u.upper() for u in (p.get("geocode") or {}).get("UGC") or []]
    for z in p.get("affectedZones") or []:
        m = re.search(r"/([A-Z]{3,6}\d{3})$", z or "")
        if m: codes.append(m.group(1).upper())
    return codes

def wa_land(p):
    """True if the alert touches WA land (county WAC / land zone WAZ, or SAME 053)."""
    if any(c.startswith(("WAC", "WAZ")) for c in zone_codes(p)):
        return True
    return any(str(s).startswith("053") for s in (p.get("geocode") or {}).get("SAME") or [])

def gust_mph(p):
    vals = []
    for v in (p.get("parameters") or {}).get("windGust") or []:
        vals += [int(x) for x in re.findall(r"\d+", str(v))]
    text = urgent.alert_text(p)
    for m in re.finditer(r"gust\w*[^.\n]{0,40}?(\d{2,3})\s*mph", text, re.I):
        vals.append(int(m.group(1)))
    return max(vals) if vals else 0

def classify_quiet(feature):
    """Return list of (page, reason); [] = not qualifying. New 'Alert' only."""
    p = feature.get("properties") or {}
    if (p.get("messageType") or "") != "Alert" or (p.get("status") or "Actual") != "Actual":
        return []
    ev = p.get("event") or ""
    if "Typhoon" in ev:                      # skip typhoon cone graphics
        return []
    if urgent.classify(feature) is not None: # urgent watcher already wakes for this
        return []
    out = []
    wa = urgent.is_washington(p)
    # --- Washington page ---
    if wa and wa_land(p) and ev not in WA_SKIP_EVENTS:
        out.append(("WA", f"new WA land alert: {ev}"))
    # --- USA page (any non-WA state/territory portion) ---
    states = urgent.ugc_states(p)
    non_wa = states - {"WA"}
    if non_wa or not wa:
        if ev in USA_ALWAYS:
            out.append(("USA", f"USA major alert: {ev}"))
        elif ev == "High Wind Warning":
            g = gust_mph(p)
            if g >= 75:
                out.append(("USA", f"High Wind Warning gusts {g} mph"))
            else:
                city = urgent.major_city_hit(p)
                if city: out.append(("USA", "High Wind Warning: " + city))
        elif ev == "High Wind Watch":        # rule 10-20 5:53 PM PT: always when gusts over 65 mph
            g = gust_mph(p)
            if g > 65:
                out.append(("USA", f"High Wind Watch gusts {g} mph"))
        elif ev == "Flash Flood Warning":
            threat = " ".join((p.get("parameters") or {}).get("flashFloodDamageThreat") or []).upper()
            if "CONSIDERABLE" in threat or "CATASTROPHIC" in threat:
                out.append(("USA", "Flash Flood Warning (considerable/catastrophic)"))
            else:
                city = urgent.major_city_hit(p)
                if city: out.append(("USA", "Flash Flood Warning: " + city))
        # Winter Weather Advisory + everything not listed: skip for USA
    return out

def item_for(feature, page, reason):
    p = feature.get("properties") or {}
    return {"source": "quiet-watch", "page": page, "event": p.get("event"),
            "area": p.get("areaDesc"), "id": p.get("id") or feature.get("id"),
            "expires": p.get("expires"), "headline": p.get("headline"),
            "sent": p.get("sent"), "reason": reason,
            "sender": p.get("senderName") or p.get("sender")}

RELEASE_WINDOW_MIN = 5   # one NWS release can stamp segments a minute or two apart

def batch_release(items):
    """10-20 fix: alerts of the same event type, page, NWS office and release (sent time)
    become ONE wake item carrying all their ids (primary id = first sorted id)."""
    groups, order = {}, []
    for it in items:
        if it.get("kind"):
            order.append(("solo", id(it))); groups[("solo", id(it))] = [it]; continue
        base = (it.get("page"), it.get("event"), it.get("sender"))
        t = parse_time(it.get("sent") or "")
        k = None
        for ok in order:   # same release = same office/type/page, sent within RELEASE_WINDOW_MIN
            if ok[0] == "solo" or ok[:3] != base: continue
            t0 = parse_time(ok[3] or "")
            if (t is None and ok[3] == it.get("sent")) or (t and t0 and abs((t - t0).total_seconds()) <= RELEASE_WINDOW_MIN * 60):
                k = ok; break
        if k is None:
            k = base + (it.get("sent"),); groups[k] = []; order.append(k)
        groups[k].append(it)
    out = []
    for k in order:
        g = groups[k]
        if len(g) == 1:
            out.append(g[0]); continue
        g = sorted(g, key=lambda x: x["id"])
        m = dict(g[0])
        m["ids"] = [x["id"] for x in g]
        m["area"] = "; ".join(x.get("area") or "" for x in g)
        m["expires"] = max((x.get("expires") or "") for x in g) or None
        m["reason"] = g[0].get("reason", "") + " (batched %d alerts, one release)" % len(g)
        out.append(m)
    return out

def item_ids(it):
    return it.get("ids") or [it["id"]]

def mark_seen(seen, it, now):
    for i in item_ids(it):
        seen[f'{i}|{it["page"]}'] = now.isoformat()

HOLD_START_PT = 21                      # 10-20 rule: non-urgent quiet posts hold from 9 PM PT
HOLD_END_PT = {"USA": 2, "WA": 5}       # ...until 2 AM PT (USA) / 5 AM PT (WA); still-active items post then
# 10-22-26 (Benjamin): NO overnight prep wakes. During the hold an alert is only remembered (not sent,
# not marked seen, no claim). The first poll after the window opens (forced, not waiting for the 30-min
# cadence) re-checks current NWS data and sends a normal wake for what is still active, using the
# current Update if NWS replaced the original. Same after a freeze/outage.
RELEASE_MIN_REMAINING_MIN = 60   # held/replaced alerts ending within ~60 min are skipped at release
OUTAGE_GAP_MIN = 45              # alert-poll gap longer than this = watcher frozen or down
HELD_KEEP_HOURS = 30


def overnight_held(page, now=None):
    from zoneinfo import ZoneInfo
    h = (now or datetime.now(timezone.utc)).astimezone(ZoneInfo("America/Los_Angeles")).hour
    return h >= HOLD_START_PT or h < HOLD_END_PT.get(page, 5)


def note_overnight_held(state, items, now):
    """Remember alerts that qualified during the hold window (no wake, no seen, no claim)."""
    held = state.setdefault("overnight_held", {})
    pages = state.setdefault("held_pages", {})
    for it in items:
        for i in item_ids(it):
            held.setdefault(f'{i}|{it["page"]}', now.isoformat())
        pages.setdefault(it.get("page"), now.isoformat())


def note_held_page(state, page, now):
    state.setdefault("held_pages", {}).setdefault(page, now.isoformat())


def prune_overnight(state, now):
    """Drop old held records/outages; one-time migration of the retired overnight_prepped record."""
    cut = now - timedelta(hours=HELD_KEEP_HOURS)
    held = state.get("overnight_held") or {}
    old = state.pop("overnight_prepped", None)   # 10-22-26: prep wakes retired; treat prepped ids as held
    if old:
        for k in old: held.setdefault(k, now.isoformat())
    for k in [k for k, v in held.items() if (parse_time(v or "") or now) < cut]: held.pop(k, None)
    state["overnight_held"] = held
    state["alert_outages"] = [o for o in (state.get("alert_outages") or []) if (parse_time(o[1] or "") or now) >= cut]


def release_due_pages(state, now):
    """Pages that had something held and whose window is now open: force an alert + SPC poll."""
    return [pg for pg in (state.get("held_pages") or {}) if not overnight_held(pg, now)]


def note_alert_poll_ok(state, now):
    """Record a successful alert fetch; a gap > OUTAGE_GAP_MIN since the last one is an outage window."""
    prev = parse_time(state.get("last_alert_ok") or "")
    if prev and (now - prev).total_seconds() > OUTAGE_GAP_MIN * 60:
        state.setdefault("alert_outages", []).append([prev.isoformat(), now.isoformat()])
        log.info("alert polling gap %d min (frozen/down %s -> %s); replaced alerts from that window can still wake",
                 int((now - prev).total_seconds() // 60), prev.isoformat(), now.isoformat())
    state["last_alert_ok"] = now.isoformat()


def _ends_soon(p, now):
    end = parse_time(p.get("ends") or "") or parse_time(p.get("expires") or "")
    return bool(end and end < now + timedelta(minutes=RELEASE_MIN_REMAINING_MIN))


def seen_key(item): return f'{item["id"]}|{item["page"]}'

def evaluate_quiet(features, seen, other_ids, pending_ids, now, state=None):
    """New qualifying Alerts as before. 10-22-26: an Update/Continuation qualifies ONLY when it replaces an
    alert we held overnight (state overnight_held) or one first issued while the watcher was down
    (state alert_outages), and only if the original was never sent/claimed/posted. Held or replaced
    alerts ending within RELEASE_MIN_REMAINING_MIN are skipped."""
    held = (state or {}).get("overnight_held") or {}
    outages = [(parse_time(a or ""), parse_time(b or "")) for a, b in ((state or {}).get("alert_outages") or [])]
    out = []
    for f in sorted(features, key=lambda x: (x.get("properties") or {}).get("sent") or ""):
        p = f.get("properties") or {}
        if not p.get("id"): p["id"] = f.get("id")
        exp = parse_time(p.get("expires") or "")
        if exp and exp < now: continue
        is_update = (p.get("messageType") or "") == "Update"
        refs, link_pages = [], None
        if is_update:
            refs = [r.get("identifier") for r in (p.get("references") or []) if r.get("identifier")]
            link_pages = {k.rsplit("|", 1)[1] for r in refs for k in (f"{r}|USA", f"{r}|WA") if k in held}
            ref_times = [t for t in (parse_time(r.get("sent") or "") for r in (p.get("references") or [])) if t]
            first = min(ref_times) if ref_times else None
            in_outage = bool(first and any(a and b and a <= first <= b for a, b in outages))
            if not link_pages and not in_outage:
                continue   # ordinary Update/continuation: never a new wake
            f = dict(f); f["properties"] = dict(p, messageType="Alert")   # classify the current version
            cls = classify_quiet(f)
            if link_pages: cls = [c for c in cls if c[0] in link_pages]
        else:
            cls = classify_quiet(f)
        for page, reason in cls:
            it = item_for(f, page, reason)
            k = seen_key(it)
            if k in seen or it["id"] in other_ids or it["id"] in pending_ids or k in pending_ids:
                continue
            if is_update and any(f"{r}|{page}" in seen or r in other_ids or r in pending_ids or f"{r}|{page}" in pending_ids for r in refs):
                continue   # original already went out: an update is not new
            release = is_update or k in held
            if release and _ends_soon(p, now):
                log.info("overnight/outage release skipped (ends within %d min): %s %s", RELEASE_MIN_REMAINING_MIN, page, p.get("event"))
                continue
            if claim_lock is not None:
                try:
                    blocked = claim_lock.is_claimed([it["id"]] + refs, page, p.get("event"), zone_codes(p), sorted(urgent.ugc_states(p)))
                except Exception:
                    blocked = None
                if blocked:
                    continue
            if is_update:
                it["message_type"] = "Update"; it["replaces"] = refs
                it["reason"] = reason + " (current NWS update of an alert held overnight or missed while down)"
            elif release:
                it["reason"] = reason + " (held overnight, still active)"
            out.append(it)
    replaced = {r for it in out for r in (it.get("replaces") or [])}
    out = [it for it in out if it["id"] not in replaced]   # the current version wins over its original
    return batch_release(out)


# ---------------- earthquakes (USGS) ----------------
def _norm_lon(lon):
    """Normalize longitude to -180..180 (Aleutians cross the dateline)."""
    try: return ((float(lon) + 180.0) % 360.0) - 180.0
    except Exception: return None

def quake_region(lat, lon):
    """Return "WA" | "AK" | "CONUS" | None from coordinates. Pragmatic bbox heuristic:
    - WA: lat 45.5-49.1, lon -125.5..-116.9 (land bbox -124.8..-116.9 plus ~0.7 deg
      just-offshore margin to the west; a few miles offshore WA still counts).
    - AK: lat >=51 and lon <=-129, or lon >=172 (western Aleutians wrapping past
      +180 into positive longitudes). NOTE: this bbox also catches parts of
      Yukon/BC and, for lon>0, far-eastern Russia at M7+ -- accepted heuristic,
      the woken routine verifies place before any post.
    - CONUS: lat 24-50, lon -125..-66 expanded by ~0.5 deg on coastal sides
      (23.5-50.5, -125.5..-65.5) so just-offshore (<=~30-50 mi) quakes count,
      while distant-ocean quakes (e.g. >200 mi off California at lon -130)
      fall outside and are rejected. Hawaii (lat ~18-22) and Puerto Rico
      (lat ~18) fall below 23.5 and are excluded (not continental US).
    - Everything else (mid-ocean, Hawaii, territories, foreign): None.
    """
    try: lat = float(lat); lon = _norm_lon(lon)
    except Exception: return None
    if lon is None: return None
    if 45.5 <= lat <= 49.1 and -125.5 <= lon <= -116.9:
        return "WA"
    if lat >= 51.0 and (lon <= -129.0 or lon >= 172.0):
        return "AK"
    if 23.5 <= lat <= 50.5 and -125.5 <= lon <= -65.5:
        return "CONUS"
    return None

def quake_item(feature):
    """classify one USGS feature -> payload item or None (thresholds per alert_style.md:
    WA M3.5+, CONUS (rest of nation) M4.5+, Alaska M7.0+; below = skip entirely)."""
    props = feature.get("properties") or {}
    geom = feature.get("geometry") or {}
    coords = geom.get("coordinates") or []
    if len(coords) < 2: return None
    lon, lat = coords[0], coords[1]
    depth = coords[2] if len(coords) > 2 else None
    try: mag = float(props.get("mag"))
    except Exception: return None
    region = quake_region(lat, lon)
    if region is None: return None
    if region == "WA":
        if mag < 3.5: return None
        page = "WA"
    elif region == "AK":
        if mag < 7.0: return None
        page = "USA"
    else:  # CONUS
        if mag < 4.5: return None
        page = "USA"
    t_ms = props.get("time")
    try:
        t_iso = datetime.fromtimestamp(float(t_ms)/1000.0, tz=timezone.utc).isoformat() if t_ms is not None else None
    except Exception: t_iso = None
    return {"source": "quiet-watch", "kind": "earthquake", "page": page,
            "mag": mag, "place": props.get("place"), "id": feature.get("id") or props.get("id"),
            "time": t_iso, "lat": lat, "lon": lon, "depth_km": depth}

def evaluate_quakes(features, seen_quakes, pending_ids, now):
    """Return (fire, stale): fire = qualifying, unseen, event <=30 min old (also
    tolerate small future clock skew); stale = qualifying/unseen but older --
    caller seeds them silently. seen_quakes keys are bare USGS ids."""
    fire, stale = [], []
    cut = now - timedelta(minutes=QUAKE_RECENT_MINUTES)
    for f in sorted(features, key=lambda x: (x.get("properties") or {}).get("time") or 0):
        it = quake_item(f)
        if not it or not it.get("id"): continue
        if it["id"] in seen_quakes or it["id"] in pending_ids or seen_key(it) in pending_ids: continue
        t = parse_time(it["time"] or "")
        if t is None or t < cut: stale.append(it)
        else: fire.append(it)
    return fire, stale

QUIET_API_URL = "https://api.weather.gov/alerts/active?status=actual&message_type=alert,update"   # 10-22-26: updates too, so a held alert replaced by an Update is not lost (Updates never wake otherwise)
QUIET_API_URL_PRE_1022 = "https://api.weather.gov/alerts/active?status=actual&message_type=alert"   # unfiltered by event (bug fix 10-21-26: shared filtered URL hid Frost Advisories etc.)

def fetch_all_alerts(session):
    r = session.get(QUIET_API_URL, headers={"User-Agent": urgent.USER_AGENT, "Accept": "application/geo+json"}, timeout=45)
    r.raise_for_status()
    return r.json().get("features") or []


def fetch_quakes(session):
    r = session.get(USGS_URL, headers={"User-Agent": urgent.USER_AGENT, "Accept": "application/geo+json"}, timeout=30)
    r.raise_for_status()
    return r.json().get("features") or []
# ----------------------------------------

def item_label(item):
    if item.get("kind") == "spc-outlook":
        return f'SPC Day {item.get("day") or 1} outlook {item.get("page")} {item.get("risk")} {",".join(item.get("states") or [])}{" (upgrade)" if item.get("upgrade") else ""}'
    if item.get("kind") == "hurricane-cone":
        return f'Hurricane cone {item.get("storm")} second={item.get("second")}'
    if item.get("kind") == "mountain-pass":
        ch = item.get("changes") or []
        return "Mountain pass: " + "; ".join(f'{c.get("pass")} {c.get("change")}' for c in ch)[:160]
    return item.get("event") or (f'{item.get("mag")} Earthquake' if item.get("kind") == "earthquake" else str(item.get("kind") or "?"))

def queue_pending(items, now):
    """Append to pending queue; returns queued items. Caller marks them seen."""
    pend = load_json(PENDING_FILE, [])
    have = {seen_key(i) for i in pend} | {i.get("id") for i in pend} | {x for i in pend for x in (i.get("ids") or [])}
    added = []
    for it in items:
        if seen_key(it) in have or it["id"] in have: continue
        pend.append(dict(it, queued_at=now.isoformat(), attempts=0)); added.append(it)
    if added: save_json(PENDING_FILE, pend)
    return added

def post_one(session, url, auth, item):
    r = session.post(url, json=item, headers={"Authorization": urgent.auth_header(auth),
                     "Content-Type": "application/json", "User-Agent": urgent.USER_AGENT}, timeout=30)
    return r.status_code

def _batch_key(it):
    k = it.get("kind") or "alert"
    ids = it.get("ids") or [it.get("id")]
    return "%s:%s|%s" % (k, ",".join(sorted(str(x) for x in ids)), it.get("page"))

def _mark_delivered(items, seen, seen_quakes, now):
    for it in items:
        if it.get("kind") in ("mountain-pass", "spc-outlook", "hurricane-cone") or (it.get("kind") and it.get("kind") != "earthquake"):
            continue  # state advancement handled by source-specific delivery / state files
        if it.get("kind") == "earthquake":
            if seen_quakes is not None: seen_quakes[it["id"]] = now.isoformat()
        else:
            mark_seen(seen, it, now)

def _wire(it):
    return {k: v for k, v in it.items() if not k.startswith("_") and k not in ("queued_at", "attempts")}

def batch_body(batch, pid, now):
    if len(batch) == 1:
        body = _wire(batch[0]); body["payload_id"] = pid
        return body
    return {"source": "quiet-watch", "kind": "batch", "payload_id": pid, "tick": now.isoformat(),
            "count": len(batch), "items": [_wire(i) for i in batch]}

def post_body(session, url, auth, body):
    r = session.post(url, json=body, headers={"Authorization": urgent.auth_header(auth),
                     "Content-Type": "application/json", "User-Agent": urgent.USER_AGENT}, timeout=30)
    return r.status_code

def deliver(session, url, auth, items, seen, state, now, seen_quakes=None):
    """10-21-26 audit fix: ONE batched POST per tick.
    New items are queued to pending_quiet.json first (marked seen once queued, as before),
    then everything pending (this tick's alerts/quakes plus passes/SPC/NHC/prep items the
    source paths queued earlier in the tick, plus any leftovers) goes out in ONE POST with a
    stable payload_id (same id on a resend of the same items after a timeout/failure).
    Returns (posted, queued, flushed): posted = items that went out, queued = new items
    still waiting, flushed = earlier-queued entries that went out. One POST = one unit of
    the 6/hour cap."""
    queued_new = queue_pending(items, now)
    _mark_delivered(queued_new, seen, seen_quakes, now)
    if not url or not auth:
        if items: log.info("no quiet webhook configured; queued %d item(s)", len(queued_new))
        return [], queued_new, 0
    batch = load_json(PENDING_FILE, [])
    if not batch:
        return [], [], 0
    state["posts"] = [t for t in state.get("posts", []) if t > time.time() - 3600]
    if len(state["posts"]) >= MAX_POSTS_PER_HOUR:
        log.warning("quiet POST capped (%d/hr); %d item(s) stay queued", MAX_POSTS_PER_HOUR, len(batch))
        return [], queued_new, 0
    keys = [_batch_key(i) for i in batch]
    pid = payload_seen.stable_id(state, "q", keys, now.isoformat())
    state["posts"].append(time.time()); save_json(STATE_FILE, state)
    try: code = post_body(session, url, auth, batch_body(batch, pid, now))
    except Exception as e:
        log.warning("quiet batch POST failed (%s); %d item(s) stay queued, payload_id %s kept for resend", type(e).__name__, len(batch), pid); code = None
    if code and 200 <= code < 300:
        sent = set(keys)
        save_json(PENDING_FILE, [i for i in load_json(PENDING_FILE, []) if _batch_key(i) not in sent])
        _mark_delivered(batch, seen, seen_quakes, now)
        payload_seen.clear_inflight(state)
        try:
            import delivered
            delivered.note(BASE, "quiet", pid, [_wire(i) for i in batch])
        except Exception as e:
            log.warning("delivery note failed (%s)", type(e).__name__)
        new_keys = {_batch_key(i) for i in queued_new}
        flushed = sum(1 for k in keys if k not in new_keys)
        log.info("quiet POST batch payload_id=%s %d item(s) -> HTTP %s: %s", pid, len(batch), code,
                 "; ".join("%s %s" % (i.get("page"), item_label(i)) for i in batch)[:400])
        return batch, [], flushed
    if code: log.warning("quiet batch POST HTTP %s; %d item(s) stay queued, payload_id %s kept for resend", code, len(batch), pid)
    pend = load_json(PENDING_FILE, [])
    for i in pend:
        i["attempts"] = int(i.get("attempts") or 0) + 1
    save_json(PENDING_FILE, pend)
    return [], queued_new, 0

def deliver_pass_batch(session, url, auth, changes, state, now):
    """Deliver ONE batched mountain-pass POST. Returns (posted, queued).
    Caller advances passes_quiet_state.json only if posted or queued is True.
    Shares the 6/hour cap via state["posts"] (same as alerts/quakes)."""
    item = passes_quiet.pass_item(changes, now.isoformat())
    def _queued_present():
        queue_pending([item], now)
        pend = load_json(PENDING_FILE, [])
        return any(i.get("id") == item["id"] for i in pend)
    if not url or not auth:
        log.info("no quiet webhook configured; queueing mountain-pass batch (%d change(s))", len(changes))
        return False, _queued_present()
    if BATCH_ONE_POST:   # 10-21-26: goes out in this tick's single deliver() POST
        return False, _queued_present()
    state["posts"] = [t for t in state.get("posts", []) if t > time.time() - 3600]
    if len(state["posts"]) >= MAX_POSTS_PER_HOUR:
        log.warning("quiet POST capped (%d/hr); queueing mountain-pass batch", MAX_POSTS_PER_HOUR)
        return False, _queued_present()
    state["posts"].append(time.time()); save_json(STATE_FILE, state)
    try: code = post_one(session, url, auth, item)
    except Exception as e:
        log.warning("quiet mountain-pass POST failed (%s); queueing", type(e).__name__); code = None
    if code and 200 <= code < 300:
        log.info("quiet POST WA %s -> HTTP %s", item_label(item), code)
        return True, False
    if code: log.warning("quiet mountain-pass POST HTTP %s; queueing", code)
    return False, _queued_present()

def deliver_quiet_item(session, url, auth, item, state, now):
    """Deliver ONE spc-outlook / hurricane-cone item. Returns (posted, queued).
    Caller advances that source's state file only if posted or queued.
    Shares the 6/hour cap via state["posts"]."""
    def _queued_present():
        queue_pending([item], now)
        pend = load_json(PENDING_FILE, [])
        return any(i.get("id") == item["id"] for i in pend)
    if not url or not auth:
        log.info("no quiet webhook configured; queueing %s (%s)", item.get("kind"), item_label(item))
        return False, _queued_present()
    if BATCH_ONE_POST:   # 10-21-26: goes out in this tick's single deliver() POST
        return False, _queued_present()
    state["posts"] = [t for t in state.get("posts", []) if t > time.time() - 3600]
    if len(state["posts"]) >= MAX_POSTS_PER_HOUR:
        log.warning("quiet POST capped (%d/hr); queueing %s", MAX_POSTS_PER_HOUR, item_label(item))
        return False, _queued_present()
    state["posts"].append(time.time()); save_json(STATE_FILE, state)
    try: code = post_one(session, url, auth, item)
    except Exception as e:
        log.warning("quiet %s POST failed (%s); queueing", item.get("kind"), type(e).__name__); code = None
    if code and 200 <= code < 300:
        log.info("quiet POST %s %s -> HTTP %s", item.get("page"), item_label(item), code)
        return True, False
    if code: log.warning("quiet POST HTTP %s; queueing", code)
    return False, _queued_present()

def flush_pending(session, url, auth, seen, state, now, seen_quakes=None):
    """Retry queued items first when a webhook exists. Returns count posted."""
    pend = load_json(PENDING_FILE, [])
    if not pend or not url or not auth: return 0
    done = 0; remain = []
    for it in pend:
        state["posts"] = [t for t in state.get("posts", []) if t > time.time() - 3600]
        if len(state["posts"]) >= MAX_POSTS_PER_HOUR:
            remain.append(it); continue
        state["posts"].append(time.time())
        try: code = post_one(session, url, auth, it)
        except Exception: code = None
        if code and 200 <= code < 300:
            done += 1
            if it.get("kind") in ("mountain-pass", "spc-outlook", "hurricane-cone"): pass  # source state already advanced at queue time
            elif it.get("kind") == "earthquake" and seen_quakes is not None: seen_quakes[it["id"]] = now.isoformat()
            else: mark_seen(seen, it, now)
            log.info("quiet pending flushed: %s %s", it.get("page"), item_label(it))
        else:
            it["attempts"] = int(it.get("attempts") or 0) + 1; remain.append(it)
    save_json(PENDING_FILE, remain); save_json(STATE_FILE, state)
    return done

def prune(seen, now):
    cut = now - timedelta(days=SEEN_PRUNE_DAYS)
    return {k: v for k, v in seen.items() if (parse_time(v) or now) > cut}

def run(once=False, dry_run=False):
    url = os.environ.get("QUIET_WEBHOOK_URL", ""); auth = os.environ.get("QUIET_WEBHOOK_AUTH", "")
    if not dry_run and os.environ.get("ALERT_RELAY") != "1":
        with open(PID_FILE, "w") as fh: fh.write(str(os.getpid()))
    stop = {"flag": False}
    signal.signal(signal.SIGTERM, lambda *a: stop.update(flag=True))
    session = requests.Session()
    first_run = (not os.path.exists(SEEN_FILE)) or os.environ.get("ALERT_RELAY_FORCE_SEED") == "1"
    log.info("quiet watcher start pid=%s dry_run=%s first_run=%s quiet_env_url=%s quiet_env_auth=%s alert_poll_seconds=%s master_poll_seconds=%s",
             os.getpid(), dry_run, first_run, bool(url), bool(auth), ALERT_POLL_SECONDS, POLL_SECONDS)
    while not stop["flag"]:
        now = datetime.now(timezone.utc)
        # General NWS alerts are due only every ALERT_POLL_SECONDS. The loop
        # still ticks every POLL_SECONDS for USGS quakes, pending flushes,
        # and the 15 min and 30 min due checks for the other sources.
        _state_preview = load_json(STATE_FILE, {"posts": []})
        _release_pages = release_due_pages(_state_preview, now)   # 10-22-26: first poll after the hold window opens
        alerts_due = dry_run or bool(_release_pages) or (time.time() - float(_state_preview.get("last_alert_attempt_ts") or 0) >= ALERT_POLL_SECONDS)
        features = []
        if alerts_due:
            try:
                features = fetch_all_alerts(session)   # 10-21-26 10:35 PM: full feed; urgent.API_URL is event-filtered
            except Exception as e:
                log.warning("fetch failed (%s); retry next poll", type(e).__name__)
                if once: return None
                _sleep(POLL_SECONDS, stop); continue
        try: quake_features = fetch_quakes(session)
        except Exception as e:
            log.warning("USGS fetch failed (%s); alerts continue, retry quakes next poll", type(e).__name__); quake_features = []
        # Mountain passes: fetched only when due (15 min) in live mode; always in dry-run for reporting.
        pass_snapshot = None; pass_error = None
        seen = prune(load_json(SEEN_FILE, {}), now)
        seen_quakes = prune(load_json(SEEN_QUAKES_FILE, {}), now)
        state = load_json(STATE_FILE, {"posts": []})
        prune_overnight(state, now)
        if alerts_due and not dry_run:
            state["last_alert_attempt_ts"] = time.time()
            note_alert_poll_ok(state, now)   # fetch succeeded (a failed fetch 'continue's above)
        pend = load_json(PENDING_FILE, [])
        pending_ids = {seen_key(i) for i in pend} | {i.get("id") for i in pend} | {x for i in pend for x in (i.get("ids") or [])} | {f'{x}|{i.get("page")}' for i in pend for x in (i.get("ids") or [])}
        other = urgent.other_seen_ids()
        # urgent watcher's own seen (read-only) also dedupes
        other |= set(load_json(urgent.SEEN_FILE, {}).keys())
        items = evaluate_quiet(features, seen, other, pending_ids, now, state) if alerts_due else []
        quake_fire, quake_stale = evaluate_quakes(quake_features, seen_quakes, pending_ids, now)
        # --- mountain passes (15-min cadence, does not slow the 5-min master tick) ---
        saved_pass_doc = load_json(PASSES_FILE, None)
        passes_due = dry_run or (time.time() - float(state.get("last_pass_attempt_ts") or 0) >= PASS_POLL_SECONDS)
        pass_changes = []
        if passes_due:
            try: pass_snapshot = passes_quiet.fetch_passes(session, urgent.USER_AGENT)
            except Exception as e:
                pass_error = type(e).__name__
                log.warning("WSDOT pass fetch failed (%s); alerts/quakes continue, retry next cycle", pass_error)
            if pass_snapshot is not None and not dry_run:
                state["last_pass_attempt_ts"] = time.time()
            if pass_snapshot is not None:
                if saved_pass_doc and isinstance(saved_pass_doc.get("passes"), dict):
                    pass_changes = passes_quiet.diff_snapshots(saved_pass_doc["passes"], pass_snapshot)
                elif not dry_run:
                    pass_changes = []  # first run: seeded silently below
                else:
                    legacy = load_json(passes_quiet.LEGACY_PASSES_FILE, {})
                    base = passes_quiet.snapshot_from_legacy(legacy) if legacy else {}
                    pass_changes = passes_quiet.diff_snapshots(base, pass_snapshot) if base else []
        # --- SPC Day 1 + Day 2 outlooks (30-min cadence) ---
        saved_spc_doc = load_json(SPC_FILE, None)
        spc_due = dry_run or bool(_release_pages) or (time.time() - float(state.get("last_spc_attempt_ts") or 0) >= SPC_POLL_SECONDS)
        spc_parsed = None; spc_error = None; spc_items = []; spc_seed = False
        spc_by_day = {}; spc_meta = {}; spc_seeded_days = []
        if spc_due:
            for _d in (1, 2):
                try: spc_by_day[_d] = spc_quiet.fetch_spc(session, urgent.USER_AGENT, _d)
                except Exception as e:
                    spc_error = (spc_error + "; " if spc_error else "") + f"day{_d} {type(e).__name__}"
                    log.warning("SPC Day %d fetch failed (%s); other sources continue", _d, type(e).__name__)
            spc_parsed = spc_by_day.get(1) or spc_by_day.get(2)
            if spc_by_day and not dry_run:
                state["last_spc_attempt_ts"] = time.time()
            if spc_by_day:
                spc_items, spc_meta, spc_seeded_days = spc_quiet.evaluate(spc_by_day, saved_spc_doc, pending_ids)
                spc_seed = bool(spc_seeded_days)
        # --- NHC hurricane cones (30-min cadence) ---
        saved_nhc_doc = load_json(HURRICANES_FILE, None)
        nhc_due = dry_run or (time.time() - float(state.get("last_nhc_attempt_ts") or 0) >= NHC_POLL_SECONDS)
        nhc_storms = None; nhc_error = None; nhc_items = []; nhc_seed = False
        if nhc_due:
            try: nhc_storms = hurricanes_quiet.fetch_nhc(session, urgent.USER_AGENT)
            except Exception as e:
                nhc_error = type(e).__name__
                log.warning("NHC fetch failed (%s); other sources continue", nhc_error)
            if nhc_storms is not None and not dry_run:
                state["last_nhc_attempt_ts"] = time.time()
            if nhc_storms is not None:
                nhc_items, nhc_seed = hurricanes_quiet.evaluate_hurricanes(nhc_storms, saved_nhc_doc, pending_ids, now)
        # --- government imagery (30-min cadence, 5:00 AM to 8:30 PM PT only) ---
        gov_due = dry_run or (gov_imagery_feeds.in_window(now) and time.time() - float(state.get("last_govimg_attempt_ts") or 0) >= gov_imagery_feeds.GOVIMG_POLL_SECONDS)
        gov_cands, gov_marks, gov_report, gov_error = [], {}, None, None
        if gov_due:
            try:
                gov_seen_doc = gov_imagery_feeds.load_seen()
                gov_cands, gov_marks, gov_report = gov_imagery_feeds.check(session, gov_seen_doc, now)
            except Exception as e:
                gov_error = type(e).__name__; gov_cands = []
                log.warning("gov imagery check failed (%s); other sources continue", gov_error)
            if not dry_run: state["last_govimg_attempt_ts"] = time.time()
        if dry_run:
            return {"gov_imagery_in_window": gov_imagery_feeds.in_window(now),
                    "gov_imagery_would_send": (gov_imagery_feeds.payload(gov_cands, now) if gov_cands else None),
                    "gov_imagery_report": gov_report, "gov_imagery_error": gov_error,
                    "active": len(features), "qualifying": items,
                    "held_overnight_now": [i["id"] + "|" + i["page"] for i in items if overnight_held(i.get("page"), now)],
                    "quakes_active": len(quake_features), "quakes_qualifying": quake_fire,
                    "quakes_stale_would_seed": len(quake_stale), "pending": len(pend),
                    "webhook_configured": bool(url and auth),
                    "passes_active": len(pass_snapshot) if pass_snapshot is not None else None,
                    "passes_changes": pass_changes, "passes_error": pass_error,
                    "passes_state_seeded": saved_pass_doc is not None,
                    "spc": spc_by_day, "spc_qualifying": spc_items,
                    "spc_error": spc_error, "spc_state_schema": (saved_spc_doc or {}).get("schema"),
                    "spc_would_seed_days": spc_seeded_days,
                    "spc_would_fire_if_unseeded": [i for i in spc_quiet.evaluate(spc_by_day, {"schema": spc_quiet.SCHEMA, "days": {str(d): 1 for d in spc_by_day}, "posted": {}}, set())[0]],
                    "hurricanes_active": (len(nhc_storms) if nhc_storms is not None else None),
                    "hurricanes": [{"storm_id": x["storm_id"], "name": x["name"], "basin": x["basin"], "classification": x["classification"], "approaching": hurricanes_quiet.approaching_region(x.get("forecast_points"), x["basin"]), "points": len(x.get("forecast_points") or [])} for x in (nhc_storms or [])],
                    "hurricanes_qualifying": [{k: v for k, v in i.items() if not k.startswith("_")} for i in nhc_items],
                    "hurricanes_error": nhc_error, "hurricanes_state_seeded": saved_nhc_doc is not None, "hurricanes_would_seed": nhc_seed}
        if first_run and alerts_due and not os.environ.get("ALERT_RELAY_ADOPT_BEFORE"):
            cut = now - timedelta(minutes=SEED_RECENT_MINUTES)
            old = [i for i in items if (parse_time(i["sent"] or "") or now) < cut]
            for i in old: mark_seen(seen, i, now)
            items = [i for i in items if i not in old]
            log.info("first run: seeded %d older qualifying alert(s) without waking", len(old))
            first_run = False
        for it in quake_stale: seen_quakes[it["id"]] = now.isoformat()
        if quake_stale: log.info("seeded %d stale quake(s) silently (>%d min old on first sighting)", len(quake_stale), QUAKE_RECENT_MINUTES)
        adopt_before = parse_time(os.environ.get("ALERT_RELAY_ADOPT_BEFORE") or "")
        if adopt_before:
            import adopt as _adopt
            def _alert_held(it, sent_at):
                return overnight_held(it.get("page"), sent_at) if not it.get("kind") else False
            adopted, items = _adopt.partition(items, adopt_before, _alert_held, lambda it: parse_time(it.get("sent") or ""))
            for it in adopted:
                mark_seen(seen, it, now)
            q_adopted, quake_fire = _adopt.partition(quake_fire, adopt_before, lambda it, sent_at: False, lambda it: parse_time(it.get("time") or ""))
            for it in q_adopted:
                seen_quakes[it["id"]] = now.isoformat()
            if adopted or q_adopted:
                log.info("adopted %d quiet alert(s) and %d quake(s) covered while the box heartbeat was fresh", len(adopted), len(q_adopted))
        flushed = 0  # 10-21-26: leftovers now go out inside this tick's single deliver() POST
        # --- mountain passes: seed / diff / batched wake (state advances only on POST success or queueing) ---
        pass_posted = pass_queued = 0
        if passes_due and pass_snapshot is not None:
            if saved_pass_doc is None:
                legacy = load_json(passes_quiet.LEGACY_PASSES_FILE, {})
                legacy_snap = passes_quiet.snapshot_from_legacy(legacy) if legacy else {}
                save_json(PASSES_FILE, {"passes": pass_snapshot, "seeded_at": now.isoformat(),
                                        "seed_source": ("wa_extras/passes_state.json+live" if legacy_snap else "live"),
                                        "last_poll": now.isoformat(), "last_changes": []})
                log.info("mountain passes: seeded %d pass(es) silently on first run (source=%s)", len(pass_snapshot), "wa_extras+live" if legacy_snap else "live")
            elif pass_changes:
                p_ok, q_ok = deliver_pass_batch(session, url, auth, pass_changes, state, now)
                if p_ok or q_ok:
                    save_json(PASSES_FILE, {"passes": pass_snapshot, "seeded_at": saved_pass_doc.get("seeded_at"),
                                            "last_poll": now.isoformat(), "last_changes": pass_changes})
                    pass_posted, pass_queued = (1 if p_ok else 0), (1 if q_ok else 0)
                    log.info("mountain passes: %d notable change(s) %s", len(pass_changes), "posted" if p_ok else "queued")
                else:
                    log.warning("mountain passes: delivery neither posted nor queued; state NOT advanced")
            else:
                save_json(PASSES_FILE, {"passes": pass_snapshot, "seeded_at": saved_pass_doc.get("seeded_at"),
                                        "last_poll": now.isoformat(), "last_changes": []})
        # --- SPC: seed / fire (state advances only on POST success or queueing; silent advance if no fire) ---
        spc_posted = spc_queued = 0
        if spc_due and spc_by_day:
            spc_doc = spc_quiet.new_doc(spc_by_day, saved_spc_doc, spc_seeded_days, now.isoformat())
            for _d in spc_seeded_days:
                _p = spc_by_day[_d]
                log.info("SPC Day %d outlook: seeded silently (issued=%s max=%s WA=%s)", _d, _p.get("issued"), _p.get("max_risk"),
                         spc_quiet.RANK_RISK.get((_p.get("risk_by_state") or {}).get("WA"), "none"))
            for it in spc_items:
                if not dry_run and overnight_held(it.get("page"), now):
                    # 10-22-26: no prep wake; not marked posted, so the first poll after the window sends the current outlook
                    log.info("SPC outlook %s held overnight (%s page); will re-check when the window opens", it["id"], it.get("page"))
                    note_held_page(state, it.get("page"), now); continue
                p_ok, q_ok = deliver_quiet_item(session, url, auth, it, state, now)
                if p_ok or q_ok:
                    spc_quiet.mark_posted(spc_doc, it, spc_meta, now.isoformat())
                    spc_posted, spc_queued = spc_posted + (1 if p_ok else 0), spc_queued + (1 if q_ok else 0)
                else:
                    log.warning("SPC outlook: delivery neither posted nor queued; %s will retry next poll", it["id"])
            save_json(SPC_FILE, spc_doc)
        # --- NHC: seed / fire (per-storm state advances only for delivered storms) ---
        nhc_posted = nhc_queued = 0
        if nhc_due and nhc_storms is not None:
            if nhc_seed:
                storms_doc = {x["storm_id"]: hurricanes_quiet.updated_storm_record(x, None, now.isoformat(), seeded=True) for x in nhc_storms if x.get("storm_id")}
                save_json(HURRICANES_FILE, {"storms": storms_doc, "seeded_at": now.isoformat(), "last_poll": now.isoformat()})
                log.info("NHC hurricanes: seeded %d active storm(s) silently on first run", len(storms_doc))
            else:
                delivered = {}  # storm_id -> item
                for it in nhc_items:
                    clean = {k: v for k, v in it.items() if not k.startswith("_")}
                    p_ok, q_ok = deliver_quiet_item(session, url, auth, clean, state, now)
                    if p_ok or q_ok:
                        delivered[it["_storm_id"]] = it
                        nhc_posted, nhc_queued = nhc_posted + (1 if p_ok else 0), nhc_queued + (1 if q_ok else 0)
                    else:
                        log.warning("NHC hurricane %s: delivery neither posted nor queued; state NOT advanced for it", it.get("storm"))
                # Advance last_seen for all current storms; bump woken only for delivered ones.
                storms_doc = dict((saved_nhc_doc or {}).get("storms") or {})
                for x in nhc_storms:
                    sid = x.get("storm_id")
                    if not sid: continue
                    it = delivered.get(sid)
                    if it is not None:
                        storms_doc[sid] = hurricanes_quiet.updated_storm_record(x, storms_doc.get(sid), now.isoformat(), woken_delta=1, fired_second=bool(it.get("_second")))
                    elif sid in storms_doc:
                        storms_doc[sid] = hurricanes_quiet.updated_storm_record(x, storms_doc.get(sid), now.isoformat())
                    # Unseen non-firing storms (e.g. TDs) are NOT recorded, so a later TS/HU upgrade can fire as new.
                save_json(HURRICANES_FILE, {"storms": storms_doc, "seeded_at": (saved_nhc_doc or {}).get("seeded_at"), "last_poll": now.isoformat()})
        # --- government imagery: wake only on a strong candidate; record seen only once posted/queued ---
        if gov_due and not dry_run and gov_report is not None:
            delivered_gov = []
            if gov_cands:
                gov_item = gov_imagery_feeds.payload(gov_cands, now)
                p_ok, q_ok = deliver_quiet_item(session, url, auth, gov_item, state, now)
                if p_ok or q_ok:
                    delivered_gov = gov_cands
                    log.info("gov imagery: %d candidate(s) %s as %s", len(gov_cands), "posted" if p_ok else "queued for this tick's POST", gov_item["id"])
                else:
                    log.warning("gov imagery: delivery neither posted nor queued; will retry next check")
            try: gov_imagery_feeds.save_seen(gov_imagery_feeds.record(gov_imagery_feeds.load_seen(), delivered_gov, gov_marks, now))
            except Exception as e: log.warning("gov imagery seen save failed (%s)", type(e).__name__)
            if not gov_cands:
                log.info("gov imagery: checked %d entries, nothing worth waking for", gov_report.get("entries_examined", 0))
        # shared 6/hr cap: alerts + quakes delivered as one batch against state["posts"]
        if not dry_run:
            _held = [i for i in items if overnight_held(i.get("page"), now)]
            if _held:   # 10-22-26: no prep wake, no claim, not seen; re-checked against current NWS data when the window opens
                log.info("held %d alert(s) overnight until the page window opens (no wake)", len(_held))
                items = [i for i in items if i not in _held]
                note_overnight_held(state, _held, now)
            if _release_pages and alerts_due:
                log.info("overnight window open for %s: release poll sends %d alert item(s) still active", ",".join(_release_pages),
                         sum(1 for i in items if i.get("page") in _release_pages))
                for _pg in _release_pages: (state.get("held_pages") or {}).pop(_pg, None)
        posted, queued, flushed = deliver(session, url, auth, items + quake_fire, seen, state, now, seen_quakes)
        save_json(SEEN_FILE, seen); save_json(SEEN_QUAKES_FILE, seen_quakes)
        state.update(last_poll=now.isoformat(), last_active_count=(len(features) if alerts_due else state.get("last_active_count")), schema=SCHEMA,
                     last_posted=len(posted), last_queued=len(queued), last_flushed=flushed,
                     last_quake_count=len(quake_features), last_quakes_qualifying=len(quake_fire),
                     last_pass_count=(len(pass_snapshot) if pass_snapshot is not None else state.get("last_pass_count")),
                     last_pass_changes=len(pass_changes), last_pass_posted=pass_posted, last_pass_queued=pass_queued,
                     last_spc_issued=(spc_parsed.get("issued") if spc_parsed else state.get("last_spc_issued")),
                     last_spc_risk=(spc_parsed.get("max_risk") if spc_parsed else state.get("last_spc_risk")),
                     last_spc_days=({str(d): {"issued": p.get("issued"), "max": p.get("max_risk"), "wa": spc_quiet.RANK_RISK.get((p.get("risk_by_state") or {}).get("WA"), "none")} for d, p in spc_by_day.items()} if spc_by_day else state.get("last_spc_days")),
                     last_spc_error=(spc_error if spc_due else state.get("last_spc_error")),
                     last_spc_qualifying=len(spc_items), last_spc_posted=spc_posted, last_spc_queued=spc_queued,
                     last_nhc_count=(len(nhc_storms) if nhc_storms is not None else state.get("last_nhc_count")),
                     last_nhc_qualifying=len(nhc_items), last_nhc_posted=nhc_posted, last_nhc_queued=nhc_queued,
                     pending_count=len(load_json(PENDING_FILE, [])))
        save_json(STATE_FILE, state)
        if once: return {"active": len(features), "qualifying": items, "quakes_active": len(quake_features),
                         "quakes_qualifying": quake_fire, "posted": len(posted), "queued": len(queued),
                         "passes_active": (len(pass_snapshot) if pass_snapshot is not None else None),
                         "passes_changes": pass_changes, "spc_qualifying": spc_items,
                         "hurricanes_qualifying": [{k: v for k, v in i.items() if not k.startswith("_")} for i in nhc_items]}
        _sleep(POLL_SECONDS, stop)
    log.info("quiet watcher stopping (SIGTERM)")

def _sleep(sec, stop):
    end = time.time() + sec
    while time.time() < end and not stop["flag"]:
        time.sleep(max(0, min(5, end - time.time())))

USAGE = """usage: watch_quiet.py [--dry-run | --once] [--help]
  (no args)   run forever (keepalive_quiet.sh starts it this way)
  --dry-run   SAFE TEST: one live check of NWS alerts, quakes, passes, SPC, NHC and gov imagery feeds, print what would wake;
              no webhook, no seen/state/pending/pid writes
  --once      same as --dry-run (10-21-26: --once no longer delivers or queues)
  --help      this text"""

if __name__ == "__main__":
    import cli_guard
    dry = cli_guard.parse(USAGE)
    setup_logging(to_stdout=dry)
    res = run(once=dry, dry_run=dry)
    if dry:
        if res is not None:
            print(json.dumps({"mode": "dry-run (no webhook sent, no files written)",
                              "would_wake": {"alerts": [{k: i.get(k) for k in ("page", "event", "area", "id")} for i in res.get("qualifying") or []],
                                             "quakes": len(res.get("quakes_qualifying") or []), "pass_changes": res.get("passes_changes"),
                                             "spc": res.get("spc_qualifying"), "hurricanes": res.get("hurricanes_qualifying"),
                                             "gov_imagery": res.get("gov_imagery_would_send")}}, indent=1, default=str)[:4000])
        print(json.dumps(res if res is not None else {"error": "live fetch failed"}, indent=1, default=str)[:6000])
