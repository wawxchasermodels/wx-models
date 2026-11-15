#!/usr/bin/env python3
"""Guards for tide-archive sidecar refresh resilience (mock 20261115)."""
from __future__ import annotations
import datetime as D
import json
import math
import os
import sys
import tempfile
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import tide_archive as TA
import refresh_tide_sidecars as R
import fetch_aifs_ens_msl as AIFS


def nearly(a, b, eps=1e-9):
    return abs(a - b) <= eps


def test_ft_per_hpa():
    assert hasattr(TA, "FT_PER_HPA"), "FT_PER_HPA must be defined"
    assert nearly(TA.FT_PER_HPA, 3.28084 / 100)
    assert TA.ib_ft(None) is None
    assert nearly(TA.ib_ft(1013.25), 0.0)
    # 10 hPa below standard ~ 0.328 ft (1 cm/hPa)
    assert nearly(TA.ib_ft(1003.25), 10 * TA.FT_PER_HPA, 1e-8)
    print("PASS  FT_PER_HPA is defined; ib_ft matches 1 cm per hPa in feet")


def test_aifs_skip_and_continue(tmp):
    # A missing/unreadable first cycle must not abort the walk; a later cycle is used.
    dest_dir = os.path.join(tmp, "arch", "v1")
    os.makedirs(dest_dir, exist_ok=True)
    work = os.path.join(tmp, "work")
    os.makedirs(work, exist_ok=True)

    cyc_bad = D.datetime(2026, 11, 15, 12, tzinfo=D.timezone.utc)
    cyc_ok = D.datetime(2026, 11, 15, 6, tzinfo=D.timezone.utc)
    ok_path = os.path.join(work, "ok.json")
    rec = {"cycle": "2026111506", "init": "2026-11-15T06:00:00Z",
           "steps": {str(h): {"msl_hpa": {"9441102": 1013.0}} for h in range(0, 361, 6)}}
    json.dump(rec, open(ok_path, "w"))

    def fake_cycles(now=None):
        return [cyc_bad, cyc_ok]

    def fake_do_cycle(c, work, steps):
        if c == cyc_bad:
            raise json.JSONDecodeError("Expecting value", "", 0)
        return ok_path, len(rec["steps"]), "ok"

    old_cycles, old_do = R.latest_aifs_cycle, AIFS.do_cycle
    R.latest_aifs_cycle = fake_cycles
    AIFS.do_cycle = fake_do_cycle
    try:
        path = R.refresh_aifs(os.path.join(tmp, "arch"), work)
    finally:
        R.latest_aifs_cycle = old_cycles
        AIFS.do_cycle = old_do
    assert path and os.path.exists(path), path
    out = json.load(open(path))
    assert out["cycle"] == "2026111506", out.get("cycle")
    print("PASS  an unavailable AIFS cycle is skipped; a later cycle is still written")


def test_sidecars_isolated(tmp):
    # If AIFS raises, SST and anomaly refresh still run.
    calls = []

    def boom(*a, **k):
        calls.append("aifs")
        raise RuntimeError("aifs down")

    def sst(*a, **k):
        calls.append("sst")
        return "sst"

    def anom(*a, **k):
        calls.append("anom")
        return "anom"

    old = R.refresh_sst, R.refresh_aifs, R.refresh_anom, R.loadj
    R.refresh_sst, R.refresh_aifs, R.refresh_anom = sst, boom, anom
    R.loadj = lambda path: None
    argv = sys.argv
    sys.argv = ["refresh_tide_sidecars.py", "--out", os.path.join(tmp, "arch2")]
    try:
        rc = R.main()
    finally:
        sys.argv = argv
        R.refresh_sst, R.refresh_aifs, R.refresh_anom, R.loadj = old
    assert rc == 0, rc
    assert calls == ["sst", "aifs", "anom"], calls
    print("PASS  AIFS failure does not skip SST or STOFS anomaly refresh")


def main():
    fails = []
    with tempfile.TemporaryDirectory() as tmp:
        for fn in (test_ft_per_hpa, lambda: test_aifs_skip_and_continue(tmp), lambda: test_sidecars_isolated(tmp)):
            try:
                fn()
            except Exception:
                traceback.print_exc()
                fails.append(fn)
    if fails:
        print(f"FAIL  {len(fails)} test(s)")
        return 1
    print("PASS  sidecar resilience tests")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
