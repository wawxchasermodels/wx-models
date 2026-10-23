#!/usr/bin/env python3
"""SPC Day 1 + Day 2 convective outlook quiet watcher (modular addition to watch_quiet.py).

Sources (official SPC GIS layers, verified HTTP 200 on 2026-10-20):
  Day 1: https://www.spc.noaa.gov/products/outlook/day1otlk_cat.lyr.geojson
  Day 2: https://www.spc.noaa.gov/products/outlook/day2otlk_cat.lyr.geojson
Each feature has LABEL (TSTM/MRGL/SLGT/ENH/MDT/HIGH), ISSUE_ISO, VALID_ISO, EXPIRE_ISO.
Cadence: SPC_POLL_SECONDS=1800 (30 min) inside watch_quiet's 5-min loop; both days per poll.

Wake rule (Benjamin 2026-10-20 5:47 AM PT; replaces the 10-18 MDT+ only rule):
  USA page: fire when any NON-WA state is SLGT or higher (SLGT/ENH/MDT/HIGH).
    risk = highest category over non-WA states; states = non-WA states at SLGT+.
  WA page: fire whenever ANY category, including TSTM (general thunder), touches Washington.
    risk = Washington's highest category; states = ["WA"].
  Dedupe per (page, day, outlook date): at most one post each, where the outlook date is the
  convective day (EXPIRE_ISO date minus 1 day, so the 01Z Day 1 update keeps the same key). A refire for the
  same key is allowed only on an UPGRADE vs what was last posted:
    USA: a non-WA state reaches a higher category than it had in the last post AND the new category
         is ENH or higher (SLGT->ENH, ENH->MDT, MDT->HIGH, or a new state straight at ENH+).
         New states merely added at SLGT never refire (no spam on reissuances).
    WA:  Washington's category rises (TSTM->MRGL, MRGL->SLGT, ...).
  Reissuances without an upgrade never refire. Day 2 for date X and Day 1 for date X are separate
  keys (so a Day 2 post and next morning's Day 1 post for the same date are both allowed).
Payload: {"source":"quiet-watch","kind":"spc-outlook","page":"USA"|"WA","day":1|2,"risk",
  "states":[...],"states_by_risk":{...},"issued","valid","expires","outlook_date",
  "upgrade":bool,"upgraded_states":[...],"id":"spc:d<day>:<issued>:<page>:<risk>"}
State (spc_quiet_state.json, schema 2): {"schema":2,"days":{"1":parsed,"2":parsed},
  "posted":{"PAGE:dN:DATE":{"ranks":{ST:rank},"max_rank":n,"ids":[...],"seeded":bool}},
  "fired":[ids], "seeded_at", "last_poll"}. A key is recorded in "posted" ONLY after POST success
  or queueing; undelivered items simply retry next poll. First run under schema 2 (or a day never
  seen before) SEEDS the currently active outlook silently (recorded as seeded, so only a later
  upgrade can fire for it).
States affected: point-in-polygon of a Census-derived state grid (spc_state_grid.json:
  0.25 deg grid per CONUS state, 0.1 deg for WA, plus a representative point each). The woken
  routine still verifies against the real SPC map.
"""
import json, os

# Adapted from the box SPC filter. Wake rules and payload ids are unchanged.
# GRID_FILE is the relay's generated state grid (the box file is not in source control).
_HERE = os.path.dirname(os.path.abspath(__file__))
_BASE = os.environ.get("ALERT_RELAY_BASE", "/tmp/alert-relay")
SPC_URLS = {1: "https://www.spc.noaa.gov/products/outlook/day1otlk_cat.lyr.geojson",
            2: "https://www.spc.noaa.gov/products/outlook/day2otlk_cat.lyr.geojson"}
SPC_URL = SPC_URLS[1]  # back-compat
SPC_STATE_FILE = os.path.join(_BASE, "spc_quiet_state.json")
GRID_FILE = os.path.normpath(os.path.join(_HERE, "..", "data", "spc_state_grid.json"))
SPC_POLL_SECONDS = 1800  # 30 min
SCHEMA = 2
RISK_RANK = {"TSTM": 0, "MRGL": 1, "SLGT": 2, "ENH": 3, "MDT": 4, "HIGH": 5}
RANK_RISK = {v: k for k, v in RISK_RANK.items()}
USA_FIRE_RANK = 2      # SLGT
USA_REFIRE_RANK = 3    # an upgrade must reach ENH+ to refire
WA_FIRE_RANK = 0       # TSTM
FIRE_RANK = USA_FIRE_RANK  # back-compat name

_GRID = None
def state_points():
    global _GRID
    if _GRID is None:
        with open(GRID_FILE) as f:
            _GRID = {st: [tuple(p) for p in pts] for st, pts in json.load(f)["points"].items()}
    return _GRID

def _rings(geom):
    t = (geom or {}).get("type"); c = (geom or {}).get("coordinates") or []
    if t == "Polygon": yield c
    elif t == "MultiPolygon":
        for poly in c: yield poly

def _in_ring(lon, lat, ring):
    inside = False; n = len(ring); j = n - 1
    for i in range(n):
        xi, yi = ring[i][0], ring[i][1]; xj, yj = ring[j][0], ring[j][1]
        if ((yi > lat) != (yj > lat)) and (lon < (xj - xi) * (lat - yi) / (yj - yi) + xi):
            inside = not inside
        j = i
    return inside

def _prep(geom):
    out = []
    for poly in _rings(geom):
        if not poly or not poly[0]: continue
        rings = [[(float(x), float(y)) for x, y, *_ in r] for r in poly]
        xs = [p[0] for p in rings[0]]; ys = [p[1] for p in rings[0]]
        out.append(((min(xs), min(ys), max(xs), max(ys)), rings))
    return out

def point_in_geom(lat, lon, geom, _prepped=None):
    for (x0, y0, x1, y1), rings in (_prepped if _prepped is not None else _prep(geom)):
        if lon < x0 or lon > x1 or lat < y0 or lat > y1: continue
        if _in_ring(lon, lat, rings[0]) and not any(_in_ring(lon, lat, h) for h in rings[1:]):
            return True
    return False

def states_for_geom(geom, only=None):
    pp = _prep(geom)
    if not pp: return []
    bx0 = min(b[0][0] for b in pp); by0 = min(b[0][1] for b in pp)
    bx1 = max(b[0][2] for b in pp); by1 = max(b[0][3] for b in pp)
    hits = []
    for st, pts in state_points().items():
        if only is not None and st not in only: continue
        for lat, lon in pts:
            if bx0 <= lon <= bx1 and by0 <= lat <= by1 and point_in_geom(lat, lon, None, pp):
                hits.append(st); break
    return sorted(hits)

def _outlook_date(expires, valid, issued):
    """Convective day label: the date the outlook period starts (EXPIRE_ISO 12Z minus 1 day),
    so the 01Z Day 1 update keeps the same key as the 06Z/13Z/1630Z/20Z issuances."""
    from datetime import datetime, timedelta
    if expires:
        try: return (datetime.fromisoformat(expires.replace("Z", "+00:00")) - timedelta(days=1)).date().isoformat()
        except ValueError: pass
    return (valid or issued or "")[:10] or None

def parse_spc(data, day=1):
    """GeoJSON -> {day, issued, valid, expires, outlook_date, max_risk, max_rank, risk_by_state}.
    risk_by_state: highest rank per state; MRGL+ for all states, TSTM tracked for WA only."""
    feats = (data or {}).get("features") or []
    issued = valid = expires = None; risk_by_state = {}; max_rank = -1
    for f in feats:
        p = f.get("properties") or {}
        rank = RISK_RANK.get(str(p.get("LABEL") or "").upper().strip())
        if rank is None: continue
        iss = p.get("ISSUE_ISO") or p.get("ISSUE") or ""
        if iss and (issued is None or str(iss) > str(issued)): issued = str(iss)
        if p.get("VALID_ISO"): valid = str(p["VALID_ISO"])
        if p.get("EXPIRE_ISO"): expires = str(p["EXPIRE_ISO"])
        max_rank = max(max_rank, rank)
        for st in states_for_geom(f.get("geometry"), only=({"WA"} if rank <= 0 else None)):
            if rank > risk_by_state.get(st, -1): risk_by_state[st] = rank
    return {"day": int(day), "issued": issued, "valid": valid, "expires": expires,
            "outlook_date": _outlook_date(expires, valid, issued),
            "max_risk": RANK_RISK.get(max_rank, "NONE"), "max_rank": max_rank,
            "risk_by_state": risk_by_state,
            "fire_states": sorted(s for s, r in risk_by_state.items() if s != "WA" and r >= USA_FIRE_RANK)}

def page_scope(parsed, page):
    """{ST: rank} relevant to a page."""
    rbs = {k: int(v) for k, v in (parsed.get("risk_by_state") or {}).items()}
    if page == "WA":
        return {"WA": rbs["WA"]} if rbs.get("WA", -1) >= WA_FIRE_RANK else {}
    return {s: r for s, r in rbs.items() if s != "WA" and r >= USA_FIRE_RANK}

def post_key(page, day, parsed):
    return f'{page}:d{int(day)}:{parsed.get("outlook_date")}'

def spc_item(parsed, page, scope, upgraded_states, upgrade=False):
    day = int(parsed.get("day") or 1)
    mr = max(scope.values()) if scope else -1
    risk = RANK_RISK.get(mr, "NONE")
    by = {}
    for s, r in sorted(scope.items()): by.setdefault(RANK_RISK[r], []).append(s)
    return {"source": "quiet-watch", "kind": "spc-outlook", "page": page, "day": day,
            "risk": risk, "states": sorted(scope), "states_by_risk": by,
            "issued": parsed.get("issued"), "valid": parsed.get("valid"), "expires": parsed.get("expires"),
            "outlook_date": parsed.get("outlook_date"), "upgrade": bool(upgrade),
            "upgraded_states": sorted(upgraded_states),
            "id": f'spc:d{day}:{parsed.get("issued")}:{page}:{risk}'}

def _fires(page, scope, rec):
    """Return (fire, upgrade, upgraded_states) for a page scope vs posted record (or None)."""
    if not scope: return False, False, []
    if rec is None: return True, False, sorted(scope)
    old = {k: int(v) for k, v in (rec.get("ranks") or {}).items()}
    need = USA_REFIRE_RANK if page == "USA" else WA_FIRE_RANK
    up = sorted(s for s, r in scope.items() if r > old.get(s, -1) and r >= need)
    return (bool(up), True, up) if up else (False, False, [])

RECENT_ISSUE_HOURS = 12


def recent_issue(parsed, now=None):
    from datetime import datetime, timezone, timedelta
    try: iss = datetime.fromisoformat(str(parsed.get("issued")).replace("Z", "+00:00"))
    except (TypeError, ValueError): return False
    if iss.tzinfo is None: iss = iss.replace(tzinfo=timezone.utc)
    return (now or datetime.now(timezone.utc)) - iss <= timedelta(hours=RECENT_ISSUE_HOURS)


def evaluate(parsed_by_day, prev, pending_ids=None):
    """parsed_by_day {1: parsed|None, 2: parsed|None}. Returns (items, meta, seeded_days).
    meta[id] = (posted_key, scope) for mark_posted. Seeding is applied by new_doc()."""
    pending_ids = pending_ids or set()
    v2 = isinstance(prev, dict) and prev.get("schema") == SCHEMA
    posted = (prev or {}).get("posted") or {} if v2 else {}
    fired = set((prev or {}).get("fired") or []) if v2 else set()
    known_days = set(((prev or {}).get("days") or {}).keys()) if v2 else set()
    items, meta, seeded = [], {}, []
    for day, parsed in sorted(parsed_by_day.items()):
        if not parsed or not parsed.get("issued"): continue
        if str(day) not in known_days and not recent_issue(parsed):
            seeded.append(int(day)); continue  # first sighting of an OLD outlook: seed silently
        # 10-20: an outlook issued in the last 12 h (e.g. overnight) still fires on first sighting
        for page in ("USA", "WA"):
            scope = page_scope(parsed, page)
            key = post_key(page, day, parsed)
            fire, upgrade, ups = _fires(page, scope, posted.get(key))
            if not fire: continue
            it = spc_item(parsed, page, scope, ups, upgrade)
            if it["id"] in pending_ids or it["id"] in fired: continue
            items.append(it); meta[it["id"]] = (key, scope)
    return items, meta, seeded

def new_doc(parsed_by_day, prev, seeded_days, now_iso):
    """Next state doc: refresh per-day parsed data, record seeded keys (silent), prune old keys."""
    v2 = isinstance(prev, dict) and prev.get("schema") == SCHEMA
    doc = {"schema": SCHEMA, "days": dict((prev or {}).get("days") or {}) if v2 else {},
           "posted": dict((prev or {}).get("posted") or {}) if v2 else {},
           "fired": list((prev or {}).get("fired") or []) if v2 else [],
           "seeded_at": ((prev or {}).get("seeded_at") if v2 else None) or now_iso, "last_poll": now_iso}
    for day, parsed in parsed_by_day.items():
        if not parsed or not parsed.get("issued"): continue
        doc["days"][str(day)] = parsed
        if int(day) in seeded_days:
            for page in ("USA", "WA"):
                scope = page_scope(parsed, page)
                if scope:
                    doc["posted"][post_key(page, day, parsed)] = {"ranks": scope, "max_rank": max(scope.values()),
                                                                  "ids": [], "seeded": True, "at": now_iso}
    dates = sorted({k.rsplit(":", 1)[-1] for k in doc["posted"]})
    keep = set(dates[-4:])
    doc["posted"] = {k: v for k, v in doc["posted"].items() if k.rsplit(":", 1)[-1] in keep}
    return doc

def mark_posted(doc, item, meta, now_iso):
    key, scope = meta[item["id"]]
    rec = doc["posted"].get(key) or {"ranks": {}, "ids": []}
    ranks = {k: int(v) for k, v in (rec.get("ranks") or {}).items()}
    for s, r in scope.items(): ranks[s] = max(r, ranks.get(s, -1))
    doc["posted"][key] = {"ranks": ranks, "max_rank": max(ranks.values()) if ranks else -1,
                          "ids": list(rec.get("ids") or []) + [item["id"]], "seeded": False, "at": now_iso}
    doc["fired"] = (list(doc.get("fired") or []) + [item["id"]])[-40:]
    return doc

def fetch_spc(session, user_agent, day=1):
    r = session.get(SPC_URLS[int(day)], headers={"User-Agent": user_agent, "Accept": "application/geo+json, application/json"}, timeout=30)
    r.raise_for_status()
    return parse_spc(r.json(), day)


USAGE = """usage: spc_quiet.py [--dry-run | --once] [--help]
  Library used by watch_quiet.py (it has no loop of its own).
  --dry-run / --once  SAFE TEST: fetch SPC Day 1 + Day 2 once, evaluate vs spc_quiet_state.json (read only),
                      print what would wake; no webhook, no file writes
  --help              this text (unknown args print usage and exit 2)"""

if __name__ == "__main__":
    import sys, requests
    sys.path.insert(0, "/workspace/urgent_watch"); import cli_guard
    cli_guard.parse(USAGE)
    try: saved = json.load(open(SPC_STATE_FILE))
    except Exception: saved = None
    s = requests.Session(); by_day = {}
    for d in (1, 2):
        try: by_day[d] = fetch_spc(s, "WashingtonWeatherChasers urgent watcher (contact via Grok Bot)", d)
        except Exception as e: print("SPC day %d fetch failed: %s" % (d, type(e).__name__))
    items, meta, seeded = evaluate(by_day, saved, set()) if by_day else ([], {}, [])
    print(json.dumps({"mode": "dry-run (no webhook sent, no files written)", "days_fetched": sorted(by_day),
                      "would_seed_days": seeded, "would_wake": items}, indent=1, default=str))
