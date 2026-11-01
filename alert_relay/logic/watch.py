#!/usr/bin/env python3
# Adapted from the box urgent watcher for the GitHub Actions relay.
# Event filters, payload shape, payload ids, and the overnight hold are unchanged.
"""Urgent weather alert watcher (no AI while idle).

Polls api.weather.gov every 30 seconds and POSTs qualifying life-safety alerts
to the urgent routine webhook. Secrets come ONLY from env vars
URGENT_WEBHOOK_URL / URGENT_WEBHOOK_AUTH and are never logged or written.

Usage: watch.py            run forever
       watch.py --dry-run  (or --once)  one poll, print what would be sent, change nothing
       watch.py --help     usage; unknown args print usage and exit 2
"""
# ---------------- config ----------------
OVERNIGHT_URGENT_ALLOWED = True     # post life-safety alerts during the 9 PM-2 AM PT pause
OVERNIGHT_START_HOUR = 21           # America/Los_Angeles; 10-21-26 4:57 PM Benjamin: 9 PM-2 AM, same as quiet USA posts
OVERNIGHT_END_HOUR = 2            # 10-21-26 4:05 PM Benjamin: USA non-urgent urgent-watcher wakes hold 9 PM-2 AM PT (start changed 4:57 PM)
POLL_SECONDS = 30   # 10-21-26 9:22 AM: tornado warnings out almost immediately
MAX_POSTS_PER_HOUR = 6
SEED_RECENT_MINUTES = 15            # on first start, alerts newer than this still fire
SEEN_PRUNE_DAYS = 3
USER_AGENT = "WashingtonWeatherChasers urgent watcher (contact via Grok Bot)"
# 10-21 2 PM: event filter = exactly the types classify()/classify_update() act on (~12 KB vs ~127 KB per poll).
# ADD A TYPE HERE whenever classify() learns a new event, or it will never be seen. Names checked against /alerts/types.
WATCH_EVENTS = ["Tornado Warning", "Flash Flood Warning", "Extreme Wind Warning", "Severe Thunderstorm Warning",
                "Special Weather Statement", "Special Marine Warning",
                "Flood Warning"]   # 10-25-26 11:48 AM PT (Benjamin): USA regular Flood Warnings, major stage or catastrophic/emergency/evacuation
API_URL = "https://api.weather.gov/alerts/active?status=actual&event=" + ",".join(e.replace(" ", "%20") for e in WATCH_EVENTS)   # Alerts + Updates (Cancels ignored)
ALERT_URL = "https://api.weather.gov/alerts/"
MAX_REF_FETCHES = 10                # per poll, to look up the prior level of an updated warning
SCHEMA = 2
import os as _relay_os
BASE = _relay_os.environ.get("ALERT_RELAY_BASE", "/tmp/alert-relay")
SEEN_FILE = BASE + "/seen.json"
STATE_FILE = BASE + "/state.json"
LOG_FILE = BASE + "/watch.log"
PID_FILE = BASE + "/watch.pid"
OTHER_SEEN_FILES = ["/workspace/usa_alerts/seen.json", "/workspace/wa_alerts/seen.json"]
# ----------------------------------------

import json, logging, logging.handlers, os, re, signal, sys, time
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

_LOGIC = os.path.dirname(os.path.abspath(__file__))
_RELAY = os.path.dirname(_LOGIC)
for _p in (_RELAY, _LOGIC):
    if _p not in sys.path:
        sys.path.insert(0, _p)
import net as requests
from cities import CITIES, METRO_COUNTIES
import payload_seen  # 10-21-26: stable payload_id for resend dedupe
import flood_rules   # 10-25-26: USA Flood Warning rule (major flood stage or catastrophic/emergency/evacuation); FLOOD_USA=0 turns it off
try:
    import claim_lock
except Exception:
    claim_lock = None

PT = ZoneInfo("America/Los_Angeles")
log = logging.getLogger("urgent_watch")


def setup_logging(to_stdout=False):
    log.setLevel(logging.INFO)
    if to_stdout:
        h = logging.StreamHandler(sys.stdout)
    else:
        h = logging.handlers.RotatingFileHandler(LOG_FILE, maxBytes=256 * 1024, backupCount=2)
    h.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    log.addHandler(h)


# ---------- helpers ----------
def parse_time(s):
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except Exception:
        return None


def load_json(path, default):
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return default


def save_json(path, data):
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(data, f, indent=1)
    os.replace(tmp, path)


def other_seen_ids():
    """IDs already handled by the regular USA / Washington alert routines."""
    ids = set()
    def walk(x):
        if isinstance(x, str):
            ids.add(x)
        elif isinstance(x, dict):
            if isinstance(x.get("id"), str):
                ids.add(x["id"])
            for k, v in x.items():
                if isinstance(k, str) and k.startswith("urn:"):
                    ids.add(k)
                if isinstance(v, (list, dict)):
                    walk(v)
        elif isinstance(x, list):
            for i in x:
                walk(i)
    for p in OTHER_SEEN_FILES:
        walk(load_json(p, []))
    return ids


def in_overnight(now=None):
    h = (now or datetime.now(PT)).astimezone(PT).hour
    return h >= OVERNIGHT_START_HOUR or h < OVERNIGHT_END_HOUR


def alert_text(p):
    params = p.get("parameters") or {}
    parts = [p.get("headline") or "", p.get("description") or "", p.get("instruction") or ""]
    parts += params.get("NWSheadline") or []
    return " ".join(parts)


def ugc_states(p):
    geo = p.get("geocode") or {}
    sts = {u[:2].upper() for u in geo.get("UGC") or [] if len(u) >= 3}
    for z in p.get("affectedZones") or []:
        m = re.search(r"/([A-Z]{2})[CZ]\d{3}$", z)
        if m:
            sts.add(m.group(1))
    for part in (p.get("areaDesc") or "").split(";"):
        m = re.search(r",\s*([A-Z]{2})\s*$", part.strip())
        if m:
            sts.add(m.group(1))
    return sts


ORCA_SPS_REASON = "Oregon/California waterspout Special Weather Statement"
def is_or_ca(p):
    geo = p.get("geocode") or {}
    if any(u.upper().startswith(("ORC", "ORZ", "CAC", "CAZ")) for u in geo.get("UGC") or []):
        return True
    if any(s.startswith(("041", "006")) for s in geo.get("SAME") or []):
        return True
    return any(re.search(r"/(OR|CA)[CZ]\d{3}$", z) for z in p.get("affectedZones") or [])


ORCA_SMW_REASON = "Oregon/California waterspout Special Marine Warning"
def is_orca_marine(p):   # 10-21-26 8:51 PM: OR/CA coastal waters are PZZ3xx-PZZ7xx (WA uses PZZ1xx/210/250/270)
    for u in (p.get("geocode") or {}).get("UGC") or []:
        u = u.upper()
        if u.startswith("PZZ") and u[3:].isdigit() and 300 <= int(u[3:]) <= 799:
            return True
    return False


def is_washington(p):
    geo = p.get("geocode") or {}
    if any(u.upper().startswith(("WAC", "WAZ")) for u in geo.get("UGC") or []):
        return True
    if any(s.startswith("053") for s in geo.get("SAME") or []):
        return True
    return any(re.search(r"/WA[CZ]\d{3}$", z) for z in p.get("affectedZones") or [])


# WA marine zones (10-21): Seattle office PZZ1xx (Puget Sound, Hood Canal, Strait of Juan de Fuca, San Juans,
# WA coastal waters, Grays Harbor bar) plus Portland-office zones that touch WA waters (Columbia River Bar,
# Cape Shoalwater to Cape Falcon). is_washington() only knows land zones, so marine warnings need this.
WA_MARINE_EXTRA = {"PZZ210", "PZZ250", "PZZ270"}


def is_wa_marine(p):
    geo = p.get("geocode") or {}
    ugcs = [u.upper() for u in geo.get("UGC") or []]
    ugcs += [z.rsplit("/", 1)[-1].upper() for z in p.get("affectedZones") or []]
    return any(re.fullmatch(r"PZZ1\d\d", u) or u in WA_MARINE_EXTRA for u in ugcs)


_CITY_RE = {}
def _name_re(name):
    r = _CITY_RE.get(name)
    if r is None:
        alts = {name}
        if name.startswith("St. "):
            alts |= {"St " + name[4:], "Saint " + name[4:]}
        r = re.compile(r"(?<![A-Za-z])(" + "|".join(re.escape(a) for a in alts) + r")(?![A-Za-z])", re.I)
        _CITY_RE[name] = r
    return r


def major_city_hit(p):
    """Return a short reason string if a 100k+ city (or its core county) is in the warning."""
    states = ugc_states(p)
    desc = p.get("description") or ""
    m = re.search(r"Locations impacted include\.*\s*(.+?)(?:\n\s*\n|$)", desc, re.I | re.S)
    loc_text = m.group(1) if m else ""
    # storm-location sentence, e.g. "a tornado was located near Moore"
    storm_text = " ".join(re.findall(r"(?:located|was|tornado)\s+(?:\w+\s+){0,6}(?:near|over)\s+[^.\n]{0,60}", desc, re.I))
    for name, st in CITIES:
        if st not in states:
            continue
        r = _name_re(name)
        if loc_text and r.search(loc_text):
            return f"major city {name}, {st} in impacted locations"
        if storm_text and r.search(storm_text):
            return f"tornado near major city {name}, {st}"
    for part in (p.get("areaDesc") or "").split(";"):
        part = part.strip()
        for name, st in METRO_COUNTIES:
            if part.lower() == f"{name}, {st}".lower():
                return f"metro county {part}"
            if st in states and name.lower() in ("new york", "district of columbia") and part.lower().startswith(name.lower()):
                return f"metro county {part}"
    return None


FFW_EVAC_RE = re.compile(r"EVACUAT")   # switch: FFW_EVAC=0 env turns it off
if os.environ.get("FFW_EVAC", "1") == "0":
    FFW_EVAC_RE = re.compile(r"(?!x)x")


def threat_level(p):
    """0 = normal, 2 = PDS/CONSIDERABLE, 3 = Emergency/CATASTROPHIC (Tornado or Flash Flood Warning)."""
    ev = p.get("event") or ""
    params = p.get("parameters") or {}
    text = alert_text(p).upper()
    if ev == "Tornado Warning":
        t = " ".join(params.get("tornadoDamageThreat") or []).upper()
        if "CATASTROPHIC" in t or "TORNADO EMERGENCY" in text:
            return 3
        if "CONSIDERABLE" in t or "PARTICULARLY DANGEROUS SITUATION" in text:
            return 2
        det = " ".join(params.get("tornadoDetection") or []).upper()
        if "OBSERVED" in det or "CONFIRMED TORNADO" in text:
            return 1
    elif ev == "Flash Flood Warning":
        t = " ".join(params.get("flashFloodDamageThreat") or []).upper()
        if "CATASTROPHIC" in t or "FLASH FLOOD EMERGENCY" in text:
            return 3
        if FFW_EVAC_RE.search(text):   # 10-24-26 10:50 PM (Benjamin): FFW that mentions evacuations posts on USA
            return 1
        if "PARTICULARLY DANGEROUS SITUATION" in text:
            return 2
    elif ev == "Flood Warning":   # 10-25-26 (Benjamin): 1 = qualifies for the USA page (major stage or catastrophic/emergency/evacuation)
        if flood_rules.flood_usa_reason(p):
            return 1
    return 0


LEVEL_NAME = {("Tornado Warning", 3): "Tornado Emergency", ("Tornado Warning", 2): "PDS Tornado Warning", ("Tornado Warning", 1): "Confirmed Tornado Warning",
              ("Flash Flood Warning", 3): "Flash Flood Emergency", ("Flash Flood Warning", 2): "PDS Flash Flood Warning",
              ("Flash Flood Warning", 1): "Flash Flood Warning with evacuations",
              ("Flood Warning", 1): "USA Flood Warning (major stage or catastrophic/emergency/evacuation)"}
# minimum level an Update must reach to fire
UPGRADE_MIN = {"Tornado Warning": 1, "Flash Flood Warning": 1}
FFW_FIRE_LEVELS = (1, 3)   # FFW Update fires for evacuations (1) or Emergency (3), never PDS-only (2)


def classify_update(feature, prior_level):
    """For an Update to a Tornado/Flash Flood Warning: fire if threat rose to PDS/Emergency."""
    p = feature.get("properties") or {}
    if (p.get("messageType") or "") != "Update" or (p.get("status") or "Actual") != "Actual":
        return None
    ev = p.get("event") or ""
    if ev not in UPGRADE_MIN:
        return None
    lvl = threat_level(p)
    if lvl < UPGRADE_MIN[ev] or lvl <= (prior_level or 0):
        return None
    if ev == "Flash Flood Warning" and lvl not in FFW_FIRE_LEVELS:
        return None
    scope = "WA" if is_washington(p) else "USA"
    return (scope, f"Upgraded to {LEVEL_NAME[(ev, lvl)]}", True, lvl)


WA_SVR_REASON = "WA Severe Thunderstorm Warning"
USA_SVR_REASON = "USA Severe Thunderstorm Warning 300k+"
USA_SVR_MIN_POP = 300000   # 10-21-26 3:16 PM Benjamin: 300,000 OR MORE (>=) people in the warning polygon, 2020 Census blocks
SVR_POP_CACHE_FILE = BASE + "/svr_pop_cache.json"   # alert id -> raw Census count (or null); shared with watch_quiet.py
SVR_POP_CACHE_DAYS = 2
_svr_pop_cache = None


def svr_population(feature):
    """2020 Census block population inside a non-WA SVR polygon, cached per alert id (memory + file), so each
    warning is counted once. Uses mapgen/population.census_population (same as render_alert_map --pop-box).
    None when there is no polygon, no Census data or anything fails (then the warning does not wake the routine)."""
    global _svr_pop_cache
    if os.environ.get("ALERT_RELAY") == "1":
        # The relay image has no Census block tables. Fail closed: a USA SVR does not wake.
        if not getattr(svr_population, "_relay_logged", False):
            svr_population._relay_logged = True
            log.info("SVR population lookup unavailable in the relay (no Census blocks); USA 300k+ SVR will not fire")
        return None
    p = feature.get("properties") or {}
    aid = p.get("id") or feature.get("id") or ""
    if _svr_pop_cache is None:
        _svr_pop_cache = load_json(SVR_POP_CACHE_FILE, {})
    hit = _svr_pop_cache.get(aid)
    if hit is None and aid:   # another watcher may have counted it since we loaded
        hit = load_json(SVR_POP_CACHE_FILE, {}).get(aid)
    if hit is not None:
        return hit.get("pop")
    n = None
    try:
        if feature.get("geometry"):
            sys.path.insert(0, "/workspace/mapgen")
            import population
            from shapely.geometry import shape
            n = population.census_population(shape(feature["geometry"]))
            population._blk.clear()   # keep the always-on watcher light: do not hold block arrays between warnings
    except Exception as e:
        log.warning("SVR population lookup failed (%s)", type(e).__name__)
        n = None
    now = datetime.now(timezone.utc)
    if aid:
        try:
            disk = load_json(SVR_POP_CACHE_FILE, {})
            disk.update(_svr_pop_cache)
            disk[aid] = {"pop": n, "t": now.isoformat()}
            cut = now - timedelta(days=SVR_POP_CACHE_DAYS)
            disk = {k: v for k, v in disk.items() if (parse_time(v.get("t", "")) or now) > cut}
            save_json(SVR_POP_CACHE_FILE, disk)
            _svr_pop_cache = disk
        except Exception as e:
            log.warning("SVR population cache write failed (%s)", type(e).__name__)
    log.info("SVR population %s: %s", aid[-20:], n)
    return n
WA_HOLD_START_HOUR = 21   # WA page overnight hold is 9 PM-5 AM PT (USA hold is 9 PM-2 AM, OVERNIGHT_START_HOUR)
WA_HOLD_END_HOUR = 5      # 10-21-26 final check: own constant; it used OVERNIGHT_END_HOUR, which became 2 at 4:05 PM


def wa_hold(now):
    h = now.astimezone(PT).hour
    return h >= WA_HOLD_START_HOUR or h < WA_HOLD_END_HOUR


def _urgent_held_at_issue(item, sent_dt):
    """True when a live box would have held this urgent-watcher item instead of posting it."""
    reason = item.get("reason") or ""
    if reason == WA_SVR_REASON:
        return wa_hold(sent_dt)
    if reason.startswith(USA_SVR_REASON):
        return in_overnight(sent_dt)
    return False


RARE_TOR_STATES = {"WA": "053", "OR": "041", "CA": "006", "AZ": "004", "UT": "049", "ID": "016", "NV": "032"}  # 10-20: every tornado warning here posts (NV added 10-21)


def rare_tornado_state(p):
    geo = p.get("geocode") or {}
    for u in geo.get("UGC") or []:
        if u[:2].upper() in RARE_TOR_STATES: return u[:2].upper()
    for sm in geo.get("SAME") or []:
        for st, fips in RARE_TOR_STATES.items():
            if sm.zfill(6)[1:4] == fips: return st
    return None


def vtec_end_only(p):
    """True when every VTEC string is a cancel/expire (O.CAN / O.EXP): the warning is ending, nothing new to post."""
    acts = [m.group(1) for v in (p.get("parameters") or {}).get("VTEC") or [] for m in [re.match(r"/[OTEX]\.([A-Z]{3})\.", v)] if m]
    return bool(acts) and all(a in ("CAN", "EXP") for a in acts)


_claim_skip_logged = set()
_minor_skip_logged = set()   # 10-26-26: USA minor-only Flood Warnings skipped (logged once per id)


def classify_flood(feature):
    """10-25-26 (Benjamin): USA regular Flood Warning rule for an Alert OR an Update (evaluate() decides whether an
    Update newly qualifies). (scope, reason, urgent) or None. Washington alerts never (WA page unchanged)."""
    p = feature.get("properties") or {}
    if (p.get("event") or "") != "Flood Warning" or (p.get("messageType") or "") not in ("Alert", "Update"):
        return None
    if (p.get("status") or "Actual") != "Actual" or vtec_end_only(p) or is_washington(p):
        return None
    r = flood_rules.flood_usa_reason(p)
    if not r:
        ms = flood_rules.minor_skip_reason(p) if flood_rules.FLOOD_USA_ON else None
        if ms and p.get("id") not in _minor_skip_logged:   # 10-26-26 11:40 AM PT (Benjamin): minor flooding only -> skip, no wake (logged once)
            _minor_skip_logged.add(p.get("id"))
            if len(_minor_skip_logged) > 5000:
                _minor_skip_logged.clear()
            log.info("minor flood skip: Flood Warning | %s | %s | %s", ms, (p.get("areaDesc") or "")[:80], p.get("id"))
        return None
    return ("USA", "USA " + r, flood_rules.flood_usa_urgent(r))


def classify(feature):
    """Return (scope, reason, urgent_overnight) or None. Ignores non-'Alert' messages."""
    p = feature.get("properties") or {}
    if (p.get("messageType") or "") != "Alert":
        return None
    if (p.get("status") or "Actual") != "Actual":
        return None
    if vtec_end_only(p):   # 10-21-26 final check: NWS sends CAN/EXP as messageType "Alert" (9:46 AM / 11:44 AM Coconino AZ)
        return None
    ev = p.get("event") or ""
    params = p.get("parameters") or {}
    text = alert_text(p).upper()
    wa = is_washington(p)

    if ev == "Tornado Warning":
        threat = " ".join(params.get("tornadoDamageThreat") or []).upper()
        if "CATASTROPHIC" in threat or "TORNADO EMERGENCY" in text:
            return ("WA" if wa else "USA", "Tornado Emergency", True)
        if "CONSIDERABLE" in threat or "PARTICULARLY DANGEROUS SITUATION" in text:
            return ("WA" if wa else "USA", "PDS Tornado Warning", True)
        if wa:
            return ("WA", "Washington Tornado Warning", True)
        rare = rare_tornado_state(p)
        if rare:
            return ("USA", "Rare-state Tornado Warning (%s)" % rare, True)
        det = " ".join(params.get("tornadoDetection") or []).upper()
        if "OBSERVED" in det or "CONFIRMED TORNADO" in text:
            return ("USA", "Confirmed Tornado Warning", True)
        city = major_city_hit(p)
        if city:
            return ("USA", "Tornado Warning: " + city, True)   # 10-21-26 5:30 PM (Benjamin): tornado warnings post any hour
        return None
    if ev == "Flash Flood Warning":
        threat = " ".join(params.get("flashFloodDamageThreat") or []).upper()
        if "CATASTROPHIC" in threat or "FLASH FLOOD EMERGENCY" in text:
            return ("WA" if wa else "USA", "Flash Flood Emergency", True)
        if not wa and FFW_EVAC_RE.search(text):   # 10-24-26 10:50 PM (Benjamin): USA FFW with evacuation language posts
            return ("USA", "Flash Flood Warning with evacuations", True)
        return None
    if ev == "Flood Warning":
        # 10-25-26 11:48 AM PT (Benjamin): USA page posts a regular Flood Warning forecast to reach MAJOR flood stage, or one that
        # mentions catastrophic, emergency or evacuation language. Others stay skipped. WA page unchanged (quiet watcher's WA path).
        # Text-language ones post any hour like the FFW evacuation rule; major-stage-only ones wait out the 9 PM-2 AM PT hold.
        return classify_flood(feature)
    if ev == "Extreme Wind Warning":
        return ("WA" if wa else "USA", "Extreme Wind Warning", True)
    if ev == "Severe Thunderstorm Warning" and wa:   # 10-21 7:13 AM: WA SVR auto-posts to WA page (WA overnight hold applies)
        return ("WA", WA_SVR_REASON, False)
    if ev == "Severe Thunderstorm Warning":   # 10-21 3:16 PM (Benjamin): USA SVR auto-posts when 300,000 or more people are in the polygon
        n = svr_population(feature)
        if n is not None and n >= USA_SVR_MIN_POP:
            return ("USA", "%s (population %s)" % (USA_SVR_REASON, "{:,}".format(n)), False)
        return None
    if ev == "Special Weather Statement" and (wa or is_wa_marine(p)) and "WATERSPOUT" in text:   # 10-21-26 airtight: WA marine-zone-only SPS counts too
        return ("WA", "Washington waterspout Special Weather Statement", True)   # 10-21-26 3:47 PM: posts any time of day (no overnight hold)
    if ev == "Special Weather Statement" and "WATERSPOUT" in text and is_or_ca(p):   # 10-21-26 3:44 PM (Benjamin): OR/CA waterspout SPS post on USA page
        return ("USA", ORCA_SPS_REASON, True)   # 10-21-26 5:30 PM (Benjamin): any hour, skips caps
    if ev == "Special Marine Warning" and (wa or is_wa_marine(p)) and "WATERSPOUT" in text:   # 10-21 2 PM: WA marine warnings mentioning waterspouts
        return ("WA", "Washington waterspout Special Marine Warning", True)   # 10-21-26 4:03 PM: posts immediately any time, like tornado warnings
    if ev == "Special Marine Warning" and "WATERSPOUT" in text and (is_orca_marine(p) or is_or_ca(p)):   # 10-21-26 8:51 PM (Benjamin)
        return ("USA", ORCA_SMW_REASON, True)   # any hour, skips caps, like OR/CA waterspout SPS
    return None


# ---------- network ----------
def fetch_alerts(session):
    r = session.get(API_URL, headers={"User-Agent": USER_AGENT, "Accept": "application/geo+json"}, timeout=30)
    r.raise_for_status()
    return r.json().get("features") or []


def auth_header(value):
    v = (value or "").strip()
    if v.lower().startswith("authorization:"):
        v = v.split(":", 1)[1].strip()
    return v if v.lower().startswith("bearer ") else "Bearer " + v


def post_batch(session, url, auth, items, payload_id=None):
    body = {"source": "urgent_watch", "alerts": items}
    if payload_id:
        # 10-21-26: stable id, identical on a resend after a timeout/failure; the routine
        # runs payload_seen.py PAYLOAD_ID and ignores the wake on exit 3 (already handled).
        body["payload_id"] = payload_id
    r = session.post(url, json=body, headers={"Authorization": auth_header(auth),
                                              "Content-Type": "application/json",
                                              "User-Agent": USER_AGENT}, timeout=30)
    return r.status_code


def _tag_wa_ask(item, page, props):
    """10-30-26 6:25 PM (Benjamin): WA ask-first switch (/workspace/wa_alerts/wa_ask_first.json). Adds needs_benjamin_ok/post_mode to WA wake items."""
    if (page or "").upper() != "WA": return item
    try:
        import wa_ask_first
        n, why = wa_ask_first.needs_ok("wa", props.get("event"), (props.get("headline") or "") + " " + (props.get("description") or ""))
    except Exception as e:
        n, why = True, "WA ask-first check failed (%r); ask first" % (e,)
    if n:
        item["needs_benjamin_ok"] = True
        item["post_mode"] = why
        # 10-31-26 6:58 PM (Benjamin): Dense Fog Advisory and fog Special Weather Statements are CHAT-QUESTION ONLY:
        # build NO graphic, take NO claim, post NO Slack until he says yes in chat.
        _ev = (props.get("event") or "").lower()
        _tx = ((props.get("headline") or "") + " " + (props.get("description") or "")).lower()
        if _ev == "dense fog advisory" or (_ev == "special weather statement" and "fog" in _tx):
            item["ask_chat_only_no_build"] = True
            item["post_mode"] = ("CHAT QUESTION ONLY (Benjamin 10-31-26): send a one-line text question in chat (event, area, until time); "
                                 "do NOT run post_alert.py, take a claim, build a graphic or caption, or send Slack until he says yes in chat.")
    return item


def alert_item(feature, scope, reason):
    p = feature.get("properties") or {}
    return {"id": p.get("id") or feature.get("id"), "event": p.get("event"), "headline": p.get("headline"),
            "areaDesc": p.get("areaDesc"), "sent": p.get("sent"), "scope": scope, "reason": reason}


# ---------- main logic ----------
def prune(seen, now):
    cut = now - timedelta(days=SEEN_PRUNE_DAYS)
    return {k: v for k, v in seen.items() if (parse_time(v) or now) > cut}


class LevelTracker:
    """Remembers threat level + chain root for every Tornado/Flash Flood Warning (and, 10-25-26, Flood Warning) message seen."""
    def __init__(self, cache, session=None, fetch=True):
        self.cache = cache            # id -> {"lvl": int, "root": id, "t": iso}
        self.session, self.fetch, self.fetched = session, fetch, 0
        self.defer = {}               # 10-25-26: Flood Warning update id -> polls deferred because its history was not known yet

    def record(self, p, now):
        refs = [r.get("identifier") for r in p.get("references") or [] if r.get("identifier")]
        root = None
        for r in refs:
            if r in self.cache:
                root = self.cache[r]["root"]; break
        if root is None:
            root = p.get("id")
            dated = sorted((r.get("sent") or "", r.get("identifier")) for r in p.get("references") or [] if r.get("identifier"))
            if dated:
                root = dated[0][1]
        self.cache[p["id"]] = {"lvl": threat_level(p), "root": root, "t": now.isoformat()}
        return root

    def level_of(self, ref_id):
        if ref_id in self.cache:
            return self.cache[ref_id]["lvl"]
        if not self.fetch or self.session is None or self.fetched >= MAX_REF_FETCHES:
            return None
        self.fetched += 1
        try:
            r = self.session.get(ALERT_URL + ref_id, headers={"User-Agent": USER_AGENT,
                                 "Accept": "application/geo+json"}, timeout=20)
            r.raise_for_status()
            p = r.json().get("properties") or {}
            lvl = threat_level(p)
            self.cache[ref_id] = {"lvl": lvl, "root": ref_id, "t": datetime.now(timezone.utc).isoformat()}
            return lvl
        except Exception as e:
            log.warning("could not fetch referenced alert (%s)", type(e).__name__)
            return None

    def prior_level(self, p, latest_only=False):
        """Highest level among referenced messages; None if none of them could be determined.
        latest_only (10-25-26, Flood Warnings): only the most recent referenced message counts (one lookup, and
        'newly qualifies' means the message right before this one did not)."""
        refs = [r for r in p.get("references") or [] if r.get("identifier")]
        if latest_only and refs:
            refs = [sorted(refs, key=lambda r: r.get("sent") or "")[-1]]
        lv = [self.level_of(r.get("identifier")) for r in refs]
        lv = [x for x in lv if x is not None]
        return max(lv) if lv else None

    def prune(self, now):
        cut = now - timedelta(days=SEEN_PRUNE_DAYS)
        self.cache = {k: v for k, v in self.cache.items() if (parse_time(v.get("t", "")) or now) > cut}


def evaluate(features, seen, other, now, overnight, tracker=None):
    """Return (to_send, held). Each item carries a private '_keys' list of seen keys to mark on success."""
    tracker = tracker or LevelTracker({}, fetch=False)
    send, held = [], []
    flood_batch = set()
    feats = sorted(features, key=lambda f: (f.get("properties") or {}).get("sent") or "")
    for f in feats:
        p = f.get("properties") or {}
        if not p.get("id"):
            p["id"] = f.get("id")
        mt = p.get("messageType") or ""
        exp = parse_time(p.get("expires") or "")
        expired = bool(exp and exp < now)
        c = None
        if p.get("event") == "Flood Warning":
            # 10-25-26 11:48 AM PT (Benjamin): USA Flood Warnings (major stage / catastrophic / emergency / evacuation).
            # A brand-new warning (Alert, VTEC NEW) fires if it qualifies. An Update, or an Alert that extends an existing
            # VTEC event (EXT/EXA/EXB), fires only if it NEWLY qualifies (the message right before it did not), same idea as
            # the 10-24-26 FFW evacuation rule. Keys include the VTEC event so one flood event posts once.
            if mt not in ("Alert", "Update"):
                continue
            refs = [r for r in p.get("references") or [] if r.get("identifier")]
            vk = flood_rules.vtec_key(p)
            vkeys = [f"vtec:{vk}|L1"] if vk else []
            if mt == "Alert" and (flood_rules.vtec_action(p) in (None, "NEW") or not refs):
                tracker.record(p, now)
                c = classify_flood(f)
                if c:
                    scope, reason, urgent = c
                    keys = [p["id"], f'{p["id"]}|L1'] + vkeys
            else:
                prior = tracker.prior_level(p, latest_only=True)
                if prior is None and refs:
                    n = tracker.defer.get(p["id"], 0) + 1
                    tracker.defer[p["id"]] = n
                    if n <= 3:      # history lookup capped/failed this poll: retry next poll before judging it
                        continue
                    prior = 0       # still unknown after 3 polls: treat as not previously qualifying
                tracker.defer.pop(p["id"], None)
                root = tracker.record(p, now)
                c = classify_flood(f)
                if c and (prior or 0) < 1:
                    scope, reason, urgent = c
                    reason = reason + " (update now qualifies)"
                    keys = [f"{root}|L1", p["id"]] + vkeys
                else:
                    c = None
        elif mt == "Alert":
            if p.get("event") in UPGRADE_MIN:
                tracker.record(p, now)
            c = classify(f)
            if c:
                scope, reason, urgent = c
                lvl = threat_level(p)
                keys = [p["id"]] + ([f'{p["id"]}|L{lvl}'] if lvl else [])
        elif mt == "Update" and p.get("event") in UPGRADE_MIN:
            prior = tracker.prior_level(p)
            root = tracker.record(p, now)
            if prior is None:
                prior = 0      # unknown history: treat as not previously elevated
            cu = classify_update(f, prior)
            if cu:
                scope, reason, urgent, lvl = cu
                c = cu
                keys = [f"{root}|L{lvl}", p["id"]]
        if not c or expired:
            continue
        if p["id"] in other or any(k in seen for k in keys):
            continue
        if claim_lock is not None:
            try:
                _refs, _cont = claim_lock.alert_link_info(p)   # 10-31-26: new vs update (references / VTEC chain)
                blocked = claim_lock.is_claimed([p["id"]], scope, p.get("event"), (p.get("geocode") or {}).get("UGC") or [], sorted(ugc_states(p)),
                                                refs=_refs, continuation=_cont)
            except Exception:
                blocked = None
            if blocked:
                if p["id"] not in _claim_skip_logged:   # 10-21-26 final check: claim_lock skips are never silent (once per alert)
                    _claim_skip_logged.add(p["id"])
                    if len(_claim_skip_logged) > 5000:
                        _claim_skip_logged.clear()
                    log.info("claim_lock skip: %s | %s | %s blocked by claim %s (%s, owner %s)", p.get("event"), reason,
                             (p.get("areaDesc") or "")[:80], blocked.get("claim_id"), blocked.get("status"), blocked.get("owner"))
                continue
        if p.get("event") == "Flood Warning":   # 10-25-26: two messages of one flood event in the same poll post once
            if any(k in flood_batch for k in keys):
                continue
            flood_batch.update(keys)
        item = alert_item(f, scope, reason)
        item["_keys"] = keys
        _tag_wa_ask(item, scope, p)   # 10-30-26 6:25 PM WA ask-first
        if reason == WA_SVR_REASON and wa_hold(now):
            held.append(item)
        elif overnight and not (OVERNIGHT_URGENT_ALLOWED and urgent):
            held.append(item)
            if p.get("event") == "Flood Warning" and p["id"] in tracker.cache:
                tracker.cache[p["id"]]["lvl"] = 0   # 10-25-26: held, not posted; a later update must still count as newly qualifying
        else:
            send.append(item)
    return send, held


def cap_exempt(item):
    if (item.get("reason") or "").startswith(USA_SVR_REASON):   # 10-22-26 10:20 AM (Benjamin): SVR 300k+ is urgent, skips caps
        return True
    """Tornado Warnings of every kind skip MAX_POSTS_PER_HOUR (an Emergency/PDS is still event 'Tornado Warning')."""
    return (item.get("event") or "") in ("Tornado Warning", "Tornado Emergency") or item.get("reason") in (ORCA_SPS_REASON, ORCA_SMW_REASON)   # 10-21-26 5:30 PM: OR/CA waterspout SPS too


def public(items):
    return [{k: v for k, v in i.items() if not k.startswith("_")} for i in items]


def run(once=False, dry_run=False):
    url = os.environ.get("URGENT_WEBHOOK_URL", "")
    auth = os.environ.get("URGENT_WEBHOOK_AUTH", "")
    if not dry_run and (not url or not auth):
        log.error("URGENT_WEBHOOK_URL / URGENT_WEBHOOK_AUTH missing from environment; exiting")
        sys.exit(2)
    if not dry_run and os.environ.get("ALERT_RELAY") != "1":
        with open(PID_FILE, "w") as f:
            f.write(str(os.getpid()))
    if not dry_run and os.environ.get("ALERT_RELAY") != "1":   # 10-23-26 alert relay: merge ids the GitHub backup already POSTed (never raises)
        try: import box_sync_seen; box_sync_seen.sync()
        except Exception: pass
    stop = {"flag": False}
    signal.signal(signal.SIGTERM, lambda *a: stop.update(flag=True))
    session = requests.Session()
    seen = load_json(SEEN_FILE, {})
    state = load_json(STATE_FILE, {"posts": []})
    first_run = (not os.path.exists(SEEN_FILE) or state.get("schema", 1) < SCHEMA
                 or os.environ.get("ALERT_RELAY_FORCE_SEED") == "1")
    tracker = LevelTracker(state.get("levels", {}), session, fetch=True)
    fail = 0
    log.info("watcher start pid=%s dry_run=%s first_run=%s env_url=%s env_auth=%s",
             os.getpid(), dry_run, first_run, bool(url), bool(auth))
    while not stop["flag"]:
        now = datetime.now(timezone.utc)
        if not dry_run and not once and os.environ.get("ALERT_RELAY") != "1":   # relaygap 10-31-26: after a freeze, merge ids the GitHub relay POSTed meanwhile
            try:
                import box_sync_seen
                if box_sync_seen.resync_after_gap("urgent"):
                    for _k, _v in load_json(SEEN_FILE, {}).items():
                        seen.setdefault(_k, _v)
            except Exception:
                pass
        try:
            features = fetch_alerts(session)
            fail = 0
        except Exception as e:
            fail += 1
            wait = min(POLL_SECONDS * (2 ** min(fail, 2)), 120)   # 10-21-26 final check: cap 2 min (7:49 AM Yavapai TOR sat behind 240 s backoffs)
            log.warning("fetch failed (%s: %s); retry in %ss", type(e).__name__, str(e)[:150], wait)
            if once:
                return None
            _sleep(wait, stop)
            continue

        seen = prune(seen, now)
        overnight = in_overnight(now)
        tracker.prune(now)
        tracker.fetched = 0
        send, held = evaluate(features, seen, other_seen_ids(), now, overnight, tracker)

        adopt_before = parse_time(os.environ.get("ALERT_RELAY_ADOPT_BEFORE") or "") if not dry_run else None
        if first_run and not dry_run and not adopt_before:
            recent_cut = now - timedelta(minutes=SEED_RECENT_MINUTES)
            seeded = [i for i in send + held if (parse_time(i["sent"] or "") or now) < recent_cut]
            for i in seeded:
                for k in i["_keys"]:
                    seen[k] = now.isoformat()
            send = [i for i in send if i not in seeded]
            held = [i for i in held if i not in seeded]
            save_json(SEEN_FILE, seen)
            state["schema"] = SCHEMA
            log.info("first run: seeded %d active qualifying alerts without posting", len(seeded))
            first_run = False
        if adopt_before:
            import adopt as _adopt
            adopted, send = _adopt.partition(send, adopt_before, _urgent_held_at_issue, lambda i: parse_time(i.get("sent") or ""))
            for i in adopted:
                for k in i.get("_keys") or []:
                    seen[k] = now.isoformat()
            if adopted:
                log.info("adopted %d urgent alert(s) covered while the box heartbeat was fresh", len(adopted))

        result = {"active": len(features), "send": public(send), "held": public(held), "overnight": overnight}
        if dry_run:
            return result

        if held:
            log.info("overnight hold: %d non-urgent alert(s) held: %s", len(held), [i["reason"] for i in held])
        if send:
            state["posts"] = [t for t in state.get("posts", []) if t > time.time() - 3600]
            if len(state["posts"]) >= MAX_POSTS_PER_HOUR:
                # 10-21 2 PM (Benjamin): every Tornado Warning (incl. Emergency, PDS, confirmed, rare-state, upgrades)
                # skips the hourly wake cap; other types keep it and retry next poll
                rest = [i for i in send if not cap_exempt(i)]
                if rest:
                    log.warning("POST capped (%d in last hour); holding %d alert(s)", len(state["posts"]), len(rest))
                send = [i for i in send if cap_exempt(i)]
                if send:
                    log.info("hourly cap reached but %d urgent alert(s) exempt; posting them", len(send))
            if send:
                pid = payload_seen.stable_id(state, "u", [i["id"] for i in send], now.isoformat())
                save_json(STATE_FILE, state)
                try:
                    code = post_batch(session, url, auth, public(send), pid)
                except Exception as e:
                    code = None
                    log.warning("POST failed (%s); will retry next poll", type(e).__name__)
                if code and 200 <= code < 300:
                    state["posts"].append(time.time())   # 10-22-26: only successful sends count toward the hourly cap
                    for i in send:
                        for k in i["_keys"]:
                            seen[k] = now.isoformat()
                    payload_seen.clear_inflight(state)
                    try:
                        import delivered
                        delivered.note(BASE, "urgent", pid, [
                            {"id": i.get("id"), "keys": list(i.get("_keys") or []), "event": i.get("event"),
                             "scope": i.get("scope"), "reason": i.get("reason"), "sent": i.get("sent")}
                            for i in send])
                    except Exception as e:
                        log.warning("delivery note failed (%s)", type(e).__name__)
                    log.info("POSTed %d alert(s) payload_id=%s -> HTTP %s: %s", len(send), pid, code,
                             [f'{i["event"]} | {i["reason"]} | {i["areaDesc"][:80] if i["areaDesc"] else ""}' for i in send])
                elif code:
                    log.warning("POST returned HTTP %s; will retry next poll", code)
        save_json(SEEN_FILE, seen)
        state["last_poll"] = now.isoformat()
        state["last_active_count"] = len(features)
        state["levels"] = tracker.cache
        save_json(STATE_FILE, state)
        if not dry_run and os.environ.get("ALERT_RELAY") != "1":   # 10-23-26 alert relay heartbeat (throttled, never raises)
            try: import box_heartbeat; box_heartbeat.beat("urgent")
            except Exception: pass
        if once:
            return result
        _sleep(POLL_SECONDS, stop)
    log.info("watcher stopping (SIGTERM)")


def _sleep(sec, stop):
    end = time.time() + sec
    while time.time() < end and not stop["flag"]:
        time.sleep(max(0, min(5, end - time.time())))


USAGE = """usage: watch.py [--dry-run | --once] [--help]
  (no args)   run forever (keepalive.sh starts it this way, env must hold URGENT_WEBHOOK_URL/AUTH)
  --dry-run   SAFE TEST: one live poll, print what would wake; no webhook, no seen/state/pid writes
  --once      same as --dry-run (10-21-26: --once no longer posts)
  --help      this text"""

if __name__ == "__main__":
    import cli_guard
    dry = cli_guard.parse(USAGE)
    setup_logging(to_stdout=dry)
    res = run(once=dry, dry_run=dry)
    if dry and res is not None:
        print(json.dumps({"mode": "dry-run (no webhook sent, no files written)", "active_alerts": res["active"], "overnight_now": res["overnight"],
                          "would_wake": res["send"], "would_hold": res["held"]}, indent=1))
    elif dry:
        print("live fetch failed")
