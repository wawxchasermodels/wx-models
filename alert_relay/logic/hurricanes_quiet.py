#!/usr/bin/env python3
"""NHC hurricane/tropical cone quiet watcher (modular addition to watch_quiet.py).

Source (official): NHC CurrentStorms.json
  https://www.nhc.noaa.gov/CurrentStorms.json
plus, per storm, the forecast-track KMZ it links (forecastTrack.kmzFile,
storm_graphics/api/<ID>_<adv>adv_TRACK.kmz) parsed for forecast (lat,lon)
points. Basins are taken from the storm id prefix; only AL/EP/CP (NHC) are
considered -- West Pacific typhoons never appear in NHC CurrentStorms and any
non-AL/EP/CP id is skipped explicitly.
Cadence: NHC_POLL_SECONDS=1800 (30 min) inside watch_quiet's 5-min loop;
NHC advisories update every ~3-6h, so 30 min is prompt and cheap.

Wake rule (Benjamin 2026-10-18):
  - FIRST wake: a NEW AL/EP/CP tropical storm or hurricane (classification
    TS or HU; tropical depressions/post-tropical/etc. do not fire) with a
    forecast cone/track (forecastTrack present in CurrentStorms).
  - SECOND wake: allowed the NEXT DAY, >=20h after the first wake, ONLY IF
    approaching the lower 48 or Hawaii (heuristic below). second=true.
  Never a third wake from this watcher; the woken routine must re-check the
  storm id against its own posted-cone log before making a second graphic.
Dedupe/state: hurricanes_quiet_state.json {storms:{<ID>:{name,basin,
  first_woken_at, second_woken_at, woken, seeded, last_seen, last_issued}}};
  state advances ONLY after POST success or queueing. First run seeds all
  currently-active storms silently (woken=0, seeded=true) so storms already
  handled by the old 7AM/5PM routine never wake on deploy; a seeded storm
  does not later claim a 'first' or 'second' wake.

Approaching heuristic (documented, pragmatic): any forecast point (track KMZ
points, falling back to the current position) that is
  - Hawaii: within ~500 mi of the main islands -- lat 13..28, lon -170..-145; or
  - Lower 48: for AL storms lat 15..50, lon -100..-60 (Caribbean/Gulf/East
    Coast approach corridor); for EP/CP storms lat >=23, lon -125..-100
    (Baja/Southern California approach) -- open-ocean EP points below 23N off
    Mexico do not count. Returns "Hawaii" / "CONUS" / None.
"""
import io, os, re, zipfile
from datetime import datetime, timezone

# Adapted from the box NHC filter. Wake rules and payload ids are unchanged.
_BASE = os.environ.get("ALERT_RELAY_BASE", "/tmp/alert-relay")
NHC_URL = "https://www.nhc.noaa.gov/CurrentStorms.json"
HURRICANES_STATE_FILE = os.path.join(_BASE, "hurricanes_quiet_state.json")
NHC_POLL_SECONDS = 1800  # 30 min
SECOND_AFTER_SECONDS = 20 * 3600
NHC_BASINS = {"AL", "EP", "CP"}
FIRE_CLASSIFICATIONS = {"TS", "HU"}  # tropical storm / hurricane only

def _parse_latlon(s):
    try:
        txt = str(s.get("latitude") or ""); lon_txt = str(s.get("longitude") or "")
        lat = s.get("latitudeNumeric"); lon = s.get("longitudeNumeric")
        if lat is not None and lon is not None: return float(lat), float(lon)
        lat = float(re.sub(r"[NnSs]", "", txt)) * (-1 if txt.upper().endswith("S") else 1)
        lon = float(re.sub(r"[EeWw]", "", lon_txt)) * (-1 if lon_txt.upper().endswith("W") else 1)
        return lat, lon
    except Exception:
        return None, None

def normalize_storm(s, forecast_points=None):
    sid = str(s.get("id") or "").upper()
    basin = sid[:2] if len(sid) >= 2 else ""
    lat, lon = _parse_latlon(s)
    issued = None
    for key in ("forecastGraphics", "publicAdvisory", "forecastAdvisory"):
        blk = s.get(key) or {}
        if blk.get("issuance"): issued = blk["issuance"]; break
    if not issued: issued = s.get("lastUpdate")
    has_cone = bool((s.get("trackCone") or {}).get("kmzFile") or (s.get("forecastTrack") or {}).get("kmzFile"))
    pts = list(forecast_points) if forecast_points is not None else ([(lat, lon)] if lat is not None else [])
    return {"storm_id": sid, "name": str(s.get("name") or ""), "basin": basin,
            "classification": str(s.get("classification") or "").upper(),
            "lat": lat, "lon": lon, "issued": issued, "has_cone": has_cone,
            "forecast_points": pts, "raw": s}

def approaching_region(points, basin):
    for lat, lon in points or []:
        try: lat = float(lat); lon = float(lon)
        except Exception: continue
        if 13.0 <= lat <= 28.0 and -170.0 <= lon <= -145.0:
            return "Hawaii"
        if basin == "AL" and 15.0 <= lat <= 50.0 and -100.0 <= lon <= -60.0:
            return "CONUS"
        if basin in ("EP", "CP") and lat >= 23.0 and -125.0 <= lon <= -100.0:
            return "CONUS"
    return None

def cone_item(storm, second, region, now):
    day = (storm.get("issued") or now.isoformat())[:10]
    label = f'{storm["storm_id"]} {storm["name"]}'.strip()
    return {"source": "quiet-watch", "kind": "hurricane-cone", "page": "USA",
            "storm": label, "basin": storm["basin"], "second": bool(second),
            "approaching": region, "classification": storm.get("classification"),
            "issued": storm.get("issued"),
            "id": (f'nhc:{storm["storm_id"]}:second:{day}' if second else f'nhc:{storm["storm_id"]}:{day}')}

def evaluate_hurricanes(storms, state, pending_ids, now):
    """storms = [normalize_storm(...)]. state = saved dict or None.
    Return (items, is_seed). Caller advances state only after POST/queue
    (or silently for seed / non-firing polls). Each item carries
    _storm_id/_second for the caller's state update (stripped before POST)."""
    if state is None:
        return [], True
    known = state.get("storms") or {}
    out = []
    for st in storms or []:
        sid = st.get("storm_id") or ""
        if st.get("basin") not in NHC_BASINS: continue  # WP/typhoon etc: skip
        if st.get("classification") not in FIRE_CLASSIFICATIONS: continue
        if not st.get("has_cone", True): continue
        rec = known.get(sid)
        if rec is None:
            it = cone_item(st, False, approaching_region(st.get("forecast_points"), st.get("basin")), now)
            it["_storm_id"] = sid; it["_second"] = False
            if it["id"] not in (pending_ids or set()): out.append(it)
        elif rec.get("seeded") or int(rec.get("woken") or 0) != 1:
            continue  # seeded storms never wake; woken>=2 done
        else:
            first = rec.get("first_woken_at")
            try: first_dt = datetime.fromisoformat(str(first).replace("Z", "+00:00"))
            except Exception: first_dt = None
            if first_dt is None or (now - first_dt).total_seconds() < SECOND_AFTER_SECONDS: continue
            region = approaching_region(st.get("forecast_points"), st.get("basin"))
            if not region: continue
            it = cone_item(st, True, region, now)
            it["_storm_id"] = sid; it["_second"] = True
            if it["id"] not in (pending_ids or set()): out.append(it)
    return out, False

def updated_storm_record(storm, prev_rec, now_iso, woken_delta=0, fired_second=False, seeded=False):
    rec = dict(prev_rec or {})
    rec.update({"name": storm.get("name"), "basin": storm.get("basin"),
                "classification": storm.get("classification"), "last_seen": now_iso,
                "last_issued": storm.get("issued")})
    if seeded and "woken" not in rec:
        rec.update({"woken": 0, "seeded": True, "seeded_at": now_iso})
    if woken_delta:
        rec["woken"] = int(rec.get("woken") or 0) + woken_delta
        if fired_second: rec["second_woken_at"] = now_iso
        elif rec.get("woken") == 1: rec["first_woken_at"] = now_iso
    return rec

def fetch_forecast_points(session, user_agent, raw_storm, current_latlon):
    """Parse forecast track points from the storm's TRACK KMZ; fall back to current position."""
    url = ((raw_storm.get("forecastTrack") or {}).get("kmzFile") or
           (raw_storm.get("trackCone") or {}).get("kmzFile"))
    pts = []
    if url:
        try:
            r = session.get(url, headers={"User-Agent": user_agent}, timeout=30); r.raise_for_status()
            z = zipfile.ZipFile(io.BytesIO(r.content))
            kml_name = next((n for n in z.namelist() if n.lower().endswith(".kml")), z.namelist()[0])
            txt = z.read(kml_name).decode("utf-8", "ignore")
            seen = set()
            for block in re.findall(r"<coordinates>([^<]+)</coordinates>", txt):
                for tok in block.split():
                    parts = tok.split(",")
                    if len(parts) < 2: continue
                    lon, lat = float(parts[0]), float(parts[1])
                    key = (round(lat, 3), round(lon, 3))
                    if key not in seen: seen.add(key); pts.append((lat, lon))
        except Exception:
            pts = []
    if not pts and current_latlon and current_latlon[0] is not None:
        pts = [tuple(current_latlon)]
    return pts

def fetch_nhc(session, user_agent, with_points=True):
    r = session.get(NHC_URL, headers={"User-Agent": user_agent, "Accept": "application/json"}, timeout=30)
    r.raise_for_status()
    out = []
    for s in (r.json().get("activeStorms") or []):
        base = normalize_storm(s, forecast_points=[])
        pts = fetch_forecast_points(session, user_agent, s, (base["lat"], base["lon"])) if with_points else [(base["lat"], base["lon"])]
        out.append(normalize_storm(s, forecast_points=pts))
    return out


USAGE = """usage: hurricanes_quiet.py [--dry-run | --once] [--help]
  Library used by watch_quiet.py (it has no loop of its own).
  --dry-run / --once  SAFE TEST: fetch NHC storms once, evaluate vs hurricanes_quiet_state.json (read only),
                      print what would wake; no webhook, no file writes
  --help              this text (unknown args print usage and exit 2)"""

if __name__ == "__main__":
    import sys, json, requests
    sys.path.insert(0, "/workspace/urgent_watch"); import cli_guard
    cli_guard.parse(USAGE)
    try: saved = json.load(open(HURRICANES_STATE_FILE))
    except Exception: saved = None
    storms = fetch_nhc(requests.Session(), "WashingtonWeatherChasers urgent watcher (contact via Grok Bot)")
    items, seed = evaluate_hurricanes(storms, saved, set(), datetime.now(timezone.utc))
    print(json.dumps({"mode": "dry-run (no webhook sent, no files written)", "storms": [x.get("storm_id") for x in storms],
                      "would_seed": seed, "would_wake": [{k: v for k, v in i.items() if not k.startswith("_")} for i in items]}, indent=1, default=str))
