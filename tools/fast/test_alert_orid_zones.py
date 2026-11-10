#!/usr/bin/env python3
"""Fail if the Studio alert map is missing the OR/ID extension, or if posting watchers changed."""
from __future__ import annotations
import json, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SITE = HERE / "site" / "alert"
JS = SITE.parent / "alert" / "alert.js"
if not JS.exists():
    JS = HERE / "site" / "alert" / "alert.js"
# alert.js lives at site/alert/alert.js
JS = HERE / "site" / "alert" / "alert.js"
STUDIO = HERE / "site" / "studio.js"
RELAY = HERE.parent.parent / "alert_relay"
sys.path.insert(0, str(HERE / "alert"))
from orid_zones import (EXCLUDED_FORECAST, FORECAST_ZONES, MARINE_ZONES, NEW_TOWNS,
                        all_new_zone_ids, county_ids, COASTAL_ORID, MAIN_ORID)


def fail(msg):
    print("test_alert_orid_zones: FAIL", msg, file=sys.stderr)
    return 1


def main():
    js = JS.read_text()
    if 'const AREAS = ["WA", "OR", "ID"]' not in js:
        return fail("alert.js AREAS must fetch WA, OR, and ID")
    if 'const AREAS = ["WA"];' in js:
        return fail("alert.js still WA-only")
    if "lat0: 41.9" not in js or "lon1: -115.85" not in js:
        return fail("alert filter box must reach the OR coast and ID panhandle")
    if "lat0: 41.88" not in js:
        return fail("fit MAX box must allow the OR coast")
    for n in MAIN_ORID | COASTAL_ORID:
        if f'"{n}"' not in js:
            return fail(f"alert.js missing town {n}")
    if "nearby OR/ID" not in js:
        return fail("status text should mention nearby OR/ID")

    pack = json.loads((SITE / "zones_wa.json").read_text())
    have = {f.get("id") or f["properties"]["id"] for f in pack["features"]}
    missing = [z for z in all_new_zone_ids() if z not in have]
    if missing:
        return fail("zone pack missing " + ", ".join(missing))
    leaked = sorted(have & EXCLUDED_FORECAST)
    if leaked:
        return fail("inland Lane/Douglas zones should not be in the pack: " + ", ".join(leaked))
    for zid in ("WAZ001", "WAC033", "PZZ251", "PZZ271"):
        if zid not in have:
            return fail("lost existing WA zone " + zid)

    towns = {p["n"] for p in json.loads((SITE / "towns_wa.json").read_text())["places"]}
    missing_t = [t["n"] for t in NEW_TOWNS if t["n"] not in towns]
    if missing_t:
        return fail("towns missing " + ", ".join(missing_t))

    bm = json.loads((SITE / "basemap_wa.json").read_text())
    if len(bm.get("counties") or []) < 39 + len(county_ids()):
        return fail(f"basemap counties {len(bm.get('counties') or [])} too few")

    studio = STUDIO.read_text()
    if "alert/alert.js?v=20261109orid2" not in studio:
        return fail("studio.js must load the new alert.js token")
    if "const CHUNK = 40" not in js:
        return fail("alert.js PZZ fetch must use a chunk large enough for the 24 marine zones")

    # Posting watchers must stay WA-only.
    watch = (RELAY / "logic" / "watch.py").read_text()
    quiet = (RELAY / "logic" / "watch_quiet.py").read_text()
    if 'startswith(("WAC", "WAZ"))' not in watch:
        return fail("alert_relay watch.py WA UGC filter changed")
    if 'startswith(("WAC", "WAZ"))' not in quiet:
        return fail("alert_relay watch_quiet.py WA UGC filter changed")
    # Pre-existing OR/CA waterspout SPS/SMW watcher is unrelated and must stay as-is.
    if "IDC" in watch.split("ORCA")[0] and 'startswith(("IDC"' in watch:
        return fail("watch.py must not gain Idaho county posting")
    if "WAC033" not in (RELAY / "selftest.py").read_text():
        return fail("alert_relay selftest should still use WA UGCs")

    # Filter simulation: pack membership is how live alerts are kept.
    def kept(zone_list):
        return any(z in have for z in zone_list)
    if not kept(["ORZ101"]):
        return fail("Clatsop coast forecast zone should match")
    if kept(["ORZ118"]):
        return fail("Lane County Lowlands (Eugene) must not match")
    if kept(["ORC039"]):
        return fail("full Lane County UGC must not match")
    if not kept(["IDC055", "IDZ002"]):
        return fail("Kootenai / Coeur d'Alene should match")
    if not kept(["PZZ252", "PZZ350"]):
        return fail("Oregon-coast marine should match")
    if not kept(["WAC033"]):
        return fail("King County WA should still match")

    print(f"test_alert_orid_zones: ok ({len(all_new_zone_ids())} new zone ids, "
          f"{len(county_ids())} counties, {len(NEW_TOWNS)} towns, pack {len(have)} zones)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
