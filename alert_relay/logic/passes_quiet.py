#!/usr/bin/env python3
"""Washington mountain-pass quiet watcher (modular addition to watch_quiet.py).

Data source (reused exactly from the former 3-hour routine, see
/workspace/wa_extras/passes_state.json "data_source"):
  https://wsdot.com/Travel/Real-time/Service/api/MountainPass
  JSON behind wsdot.com/travel/real-time/mountainpasses -- a list of 16
  {mountainPass:{mountainPassName,...}, condition:{temperature, weather,
  roadCondition, displayDate, travelAdvisoryFlag, restrictionOne/Two}}.
  No API key needed. This is NOT a page scrape; it is the underlying JSON.

Cadence: polled every PASS_POLL_SECONDS (900s = 15 min) from inside
watch_quiet.py's 5-minute loop (passes change slower than alerts/quakes;
the 5-min alert/quake poll is NOT slowed). A failed pass fetch retries on
the next 5-min cycle and never blocks alerts/quakes.

Notable changes (vs last saved snapshot in passes_quiet_state.json):
  pass closes / reopens, avalanche closure, chains required, traction
  tires required, any restriction added / lifted / changed, and snow newly
  reported on the roadway. Temperature, displayDate and weather-text-only
  changes are NOT notable alone (temperature/displayDate are stored for
  context but excluded from the diff).

State advancement discipline (shared with watch_quiet delivery):
  - No notable change: snapshot advances silently (temp-only etc.).
  - Notable change: snapshot advances ONLY after the batched POST succeeds
    (2xx) OR after the batch is queued to pending_quiet.json. On POST
    failure watch_quiet queues (same as alerts), so advancing after
    queueing cannot lose the wake. Pending items carry "kind":
    "mountain-pass" (pending format extension) plus a deterministic "id"
    (hash of the changes, no timestamp) so re-polls dedupe and a flush
    never double-posts the same change set.
  - First run (no passes_quiet_state.json): seeds silently. The seed is
    built by copying /workspace/wa_extras/passes_state.json if its format
    maps (it does), then immediately replaced by the live snapshot, so
    pre-existing conditions never wake.
"""
import hashlib, json, os, re

# Adapted from the box mountain-pass filter. Change rules and the deterministic id are unchanged.
_BASE = os.environ.get("ALERT_RELAY_BASE", "/tmp/alert-relay")
WSDOT_URL = "https://wsdot.com/Travel/Real-time/Service/api/MountainPass"
PASSES_STATE_FILE = os.path.join(_BASE, "passes_quiet_state.json")
LEGACY_PASSES_FILE = os.path.join(_BASE, "passes_legacy_absent.json")
PASS_POLL_SECONDS = 900

def _norm_name(name):
    return re.sub(r"\s+", " ", str(name or "")).strip()

def _txt(v):
    return re.sub(r"\s+", " ", str(v or "")).strip()

def _is_none_restriction(t):
    return _txt(t).lower() in ("", "no restrictions", "none", "no restriction")

def _restriction_kind(t):
    low = _txt(t).lower()
    if _is_none_restriction(low):
        return "none"
    if "chain" in low and "required" in low:
        return "chains"
    if "traction tires required" in low or "traction tire required" in low:
        return "traction_required"
    if "traction" in low and "advised" in low:
        return "traction_advised"
    return "other"

def _derive(status_texts, road, weather, restrictions):
    """Derive (status, snow_on_road, avalanche_closure) from text fields."""
    combined = " ".join([road or "", weather or ""] + list(restrictions.values())).lower()
    road_low = (road or "").lower()
    # 10-20: advance notices of planned future closures are not closures. Ignore road/weather text that is an
    # advance notice or future-tense, and count a closure only from current wording or per-direction restrictions.
    ADV = re.compile(r"advanced? notice|will (?:be )?clos|planned|scheduled|upcoming|expect(?:ed)? (?:a )?clos|beginning|starting", re.I)
    current = " ".join([t for t in [road or "", weather or ""] if not ADV.search(t)] + list(restrictions.values())).lower()
    closed = bool(re.search(r"\bclosed\b|\bclosure\b", current))
    status = "closed" if closed else "open"
    snow_on_road = bool(re.search(r"\bsnow\b", road_low))
    avalanche_closure = bool("avalanche" in combined and closed)
    return status, snow_on_road, avalanche_closure

# 10-21-26 3:14 PM (Benjamin): pass/road closure graphics and captions must state the specific cause WSDOT gives.
# closure_cause() pulls it from the WSDOT text so the wake payload carries it ("cause", "cause_line", "cause_text").
_CAUSES = [  # (regex on WSDOT text, short phrase used after "Closed for" / "due to")
    (r"avalanche control", "avalanche control"),
    (r"\bavalanche", "avalanche danger"),
    (r"spin[- ]?outs?|slide[- ]?offs?|vehicles? (?:off|in) the (?:road|ditch)", "spinouts and slide-offs"),
    (r"jack[- ]?knif", "a jackknifed truck"),
    (r"collisions?|crash(?:es)?|wreck|multi[- ]vehicle|disabled (?:vehicle|truck|semi)|incident involving", "a collision"),
    (r"winter (?:operations?|ops|maintenance|readiness)|(?:prepare|prep|get ready|getting ready|ready) for winter|winter prep", "winter operations prep"),
    (r"heavy snow|whiteout|blowing snow|snow ?fall rates?|zero visibility|poor visibility", "heavy snow"),
    (r"rock ?slides?|rock ?fall|falling rocks?", "a rockslide"),
    (r"mud ?slides?|land ?slides?|debris (?:flow|slide|on the road)|slide (?:across|on) the road", "a slide"),
    (r"rock blasting|blasting", "rock blasting"),
    (r"(?:fallen|downed|down|falling) trees?|trees? (?:down|across|on the road)", "downed trees"),
    (r"(?:downed|down) power ?lines?|power ?lines? down", "downed power lines"),
    (r"wild ?fire|\bfire\b", "wildfire"),
    (r"flood|water over the road", "flooding"),
    (r"ice storm|freezing rain|black ice|icy", "ice"),
    (r"construction|paving|bridge work|road ?work|maintenance work", "road work"),
]
def closure_cause(*texts):
    """Specific closure/restriction cause from WSDOT text -> {"cause", "cause_line", "cause_text"} or {}.
    cause = up to two phrases ("spinouts and slide-offs", "heavy snow"); cause_line = suggested white bottom
    line ("Closed for heavy snow"); cause_text = the WSDOT sentence it came from, so the run can verify it."""
    found, src = [], ""
    for t in texts:
        t = _txt(t)
        if not t: continue
        for sent in re.split(r"(?<=[.!?])\s+", t):
            for rx, phrase in _CAUSES:
                if phrase in found: continue
                if phrase == "avalanche danger" and "avalanche control" in found: continue
                if re.search(rx, sent, re.I):
                    found.append(phrase); src = src or sent
    found = found[:2]
    if not found: return {}
    cause = " and ".join(found)
    return {"cause": cause, "cause_line": "Closed for " + cause, "cause_text": src[:300]}

def _entry(status, restrictions, road, weather, temp, display_date):
    restrictions = {_txt(k): _txt(v) for k, v in (restrictions or {}).items()}
    # canonical display: empty restriction == "No restrictions"
    restrictions = {k: (v if v else "No restrictions") for k, v in restrictions.items()}
    derived_status, snow, avalanche = _derive(None, road, weather, restrictions)
    # explicit legacy status wins only if it says closed; derived closure also closes
    if status and str(status).lower() == "closed":
        derived_status = "closed"
    return {"status": derived_status, "restrictions": restrictions,
            "roadCondition": _txt(road), "weather": _txt(weather),
            "temperature": temp, "displayDate": display_date,
            "snow_on_road": snow, "avalanche_closure": avalanche}

def snapshot_from_wsdot(data):
    """WSDOT API list -> {normalized pass name: entry}."""
    out = {}
    for item in data or []:
        mp = item.get("mountainPass") or {}
        c = item.get("condition") or {}
        name = _norm_name(mp.get("mountainPassName"))
        if not name:
            continue
        restrictions = {}
        for key in ("restrictionOne", "restrictionTwo"):
            r = c.get(key) or {}
            direction = _txt(r.get("travelDirectionName")) or key
            restrictions[direction] = _txt(r.get("publicPage"))
        out[name] = _entry(None, restrictions, c.get("roadCondition"),
                           c.get("weather"), c.get("temperature"), c.get("displayDate"))
    return out

def snapshot_from_legacy(legacy):
    """Map /workspace/wa_extras/passes_state.json format -> same snapshot format."""
    out = {}
    for name, e in ((legacy or {}).get("passes") or {}).items():
        out[_norm_name(name)] = _entry(e.get("status"), e.get("restrictions") or {},
                                       e.get("roadCondition"), e.get("weather"),
                                       e.get("temperature"), e.get("displayDate"))
    return out

def fetch_passes(session, user_agent):
    r = session.get(WSDOT_URL, headers={"User-Agent": user_agent, "Accept": "application/json"}, timeout=30)
    r.raise_for_status()
    return snapshot_from_wsdot(r.json())

def diff_snapshots(old, new):
    """Return notable changes [{pass, change, details}]. Temp/displayDate/weather-only ignored."""
    changes = []
    for name in sorted(new):
        n = new[name]
        o = (old or {}).get(name)
        if o is None:
            continue  # newly-appearing pass: seeded silently, never wakes alone
        road = n.get("roadCondition") or ""
        # closure / reopen (avalanche closure labelled specifically)
        if o.get("status") != n.get("status"):
            if n.get("status") == "closed":
                label = "Avalanche closure" if n.get("avalanche_closure") else "Pass closed"
                changes.append({"pass": name, "change": label, "details": road[:300]})
            else:
                changes.append({"pass": name, "change": "Pass reopened", "details": road[:300]})
        elif n.get("avalanche_closure") and not o.get("avalanche_closure"):
            changes.append({"pass": name, "change": "Avalanche closure", "details": road[:300]})
        # restrictions per direction
        dirs = sorted(set((o.get("restrictions") or {})) | set((n.get("restrictions") or {})))
        for d in dirs:
            ov = (o.get("restrictions") or {}).get(d, "No restrictions")
            nv = (n.get("restrictions") or {}).get(d, "No restrictions")
            if _txt(ov).lower() == _txt(nv).lower():
                continue
            nk, ok = _restriction_kind(nv), _restriction_kind(ov)
            if nk == "chains":
                label = "Chains required"
            elif nk == "traction_required":
                label = "Traction tires required"
            elif nk == "none":
                label = "Restriction lifted"
            elif ok == "none":
                label = "Restriction added"
            else:
                label = "Restriction changed"
            changes.append({"pass": name, "change": label,
                            "details": f"{d}: {ov} -> {nv}" + (f" | {road[:200]}" if road else "")})
        # 10-21-26 3:14 PM: carry the WSDOT closure cause so the graphic bottom line and caption can state it
        cz = closure_cause(*((n.get("restrictions") or {}).values()), road)
        if cz:
            for c in changes:
                if c["pass"] == name and c["change"] not in ("Pass reopened", "Restriction lifted"):
                    c.update(cz)
                    if n.get("status") != "closed":   # restriction only (chains, traction): not a closure line
                        c["cause_line"] = "Due to " + cz["cause"]
        # new snow on roadway
        if n.get("snow_on_road") and not o.get("snow_on_road"):
            # avoid double-reporting when the same poll already fired a closure for this pass
            if not any(c["pass"] == name and c["change"] in ("Pass closed", "Avalanche closure") for c in changes):
                changes.append({"pass": name, "change": "Snow on roadway", "details": road[:300]})
    return changes

def pass_item(changes, checked_iso):
    """One batched payload for all changes in a poll. Deterministic id (changes only,
    no timestamp) for pending-queue dedupe; POSTed payload carries it as well."""
    digest = hashlib.sha256(json.dumps(changes, sort_keys=True).encode()).hexdigest()[:16]
    return {"source": "quiet-watch", "kind": "mountain-pass", "page": "WA",
            "id": "mountain-pass:" + digest, "changes": changes, "checked": checked_iso}


USAGE = """usage: passes_quiet.py [--dry-run | --once] [--help]
  Library used by watch_quiet.py (it has no loop of its own).
  --dry-run / --once  SAFE TEST: fetch WSDOT passes once, diff vs passes_quiet_state.json (read only),
                      print what would wake; no webhook, no file writes
  --cause "TEXT"      print the closure cause found in WSDOT text (cause, cause_line, cause_text); no network
  --help              this text (unknown args print usage and exit 2)"""

if __name__ == "__main__":
    import sys
    if len(sys.argv) == 3 and sys.argv[1] == "--cause":   # 10-21-26: routine helper, offline
        print(json.dumps(closure_cause(sys.argv[2]), indent=1)); sys.exit(0)
    import requests
    sys.path.insert(0, "/workspace/urgent_watch"); import cli_guard
    cli_guard.parse(USAGE)
    try: saved = json.load(open(PASSES_STATE_FILE))
    except Exception: saved = None
    snap = fetch_passes(requests.Session(), "WashingtonWeatherChasers urgent watcher (contact via Grok Bot)")
    ch = diff_snapshots(saved["passes"], snap) if saved and isinstance(saved.get("passes"), dict) else []
    print(json.dumps({"mode": "dry-run (no webhook sent, no files written)", "passes": len(snap), "state_seeded": saved is not None,
                      "would_wake": [pass_item(ch, "dry-run")] if ch else []}, indent=1, default=str))
