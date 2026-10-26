#!/usr/bin/env python3
"""NOAA GFS: the only two GFS maps kept on the site (Benjamin 10-24-26; every other GFS product is archived in
archive/gfs_products_20261024/):
  * 500 mb Height Anomaly: GFS 500 mb height minus the NCEP/NCAR Reanalysis 1 monthly long-term mean 1991-2020
    (NOAA PSL), linearly interpolated in time to the valid date and bilinearly to the GFS grid. Same climatology file
    and method as the AIFS 500 mb anomaly (ncep_hgt500_mon_ltm_1991_2020.npz, built by make_clim.py).
  * Sea-Level Pressure: PRMSL fill with labeled isobars and H/L centers (same renderer and rules as the AIFS map).
Views: North America, Pacific NW, Pacific NW tight. Every 6 h to 240 h from the latest 00Z/12Z run.
Data: NOAA GFS 0.25 deg (AWS open data, public domain). Basemap: Natural Earth. NOT scheduled; run by hand:
  python tools/forecast/gfs_maps.py [--cycle YYYYMMDDHH] [--hours 240] [--every 6] [--views na,pnw,pnwt] [--products z500,mslp]
Writes $SITE_BATCH/<cycle>/aifs500-<model>|aifsmslp-<model>/step/<view>/<valid>/final.jpg + site_frame.json
(tab aifs500 / aifsmslp, model "GFS", so they show as a GFS pill on the AIFS tabs).
--model ifs --products mslp (10-25-26): the same Sea-Level Pressure map from ECMWF IFS open data (0.1 deg), written to
aifsmslp-ifs/ as the "ECMWF 9 km" pill on the Sea-level pressure tab (run in the workflow's mslp job).
"""
import sys, argparse, datetime as dt, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import aifs_maps as AM
import menu_maps as MM

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--cycle"); ap.add_argument("--hours", type=int, default=240); ap.add_argument("--every", type=int, default=6)
    ap.add_argument("--steps", help="explicit comma list of forecast hours (overrides --hours/--every)")
    ap.add_argument("--views", default="na,pnw,pnwt"); ap.add_argument("--products", default="z500,mslp")
    ap.add_argument("--model", default="gfs", choices=["gfs", "ifs"])
    a = ap.parse_args(); M = a.model
    # 10-25-26 (Benjamin): ECMWF 9 km 500 mb height anomaly too, as the "ECMWF 9 km" pill on the 500 mb anomaly tab (Aloft);
    # same climatology (NCEP/NCAR R1 1991-2020 monthly mean) and renderer as the AIFS/GFS anomaly maps
    c = dt.datetime.strptime(a.cycle, "%Y%m%d%H").replace(tzinfo=dt.timezone.utc) if a.cycle else MM.latest(M)
    steps = [int(x) for x in a.steps.split(",")] if a.steps else list(range(0, min(a.hours, 240) + 1, a.every))
    views = [v for v in a.views.split(",") if v in AM.VIEWS]; tot = 0
    for s in steps:
        R = MM.Reader(M, c, s); vt = f"{c + dt.timedelta(hours=s):%Y%m%d%H}"
        try:
            if "z500" in a.products:
                lat, lon, z = R.f("Z:500"); z = z / 10.0   # gpm -> dam
                if M == "ifs":   # 0.1 deg: light smoothing so the contours read like the 0.25 deg AIFS/GFS maps
                    from scipy.ndimage import gaussian_filter; z = gaussian_filter(z, 1.5)
                an = z - AM.clim_at(c + dt.timedelta(hours=s), lat, lon)
                for v in views:
                    out = f"{AM.ROOT}/{c:%Y%m%d%H}/aifs500-{M}/step/{v}/{vt}"
                    AM.render(c, s, lat, lon, z, an, v, out, src=M); print("ok", out, flush=True)
            if "mslp" in a.products:
                lat, lon, p = R.f("msl")
                if M == "ifs":   # 0.1 deg MSLP is noisy over terrain: smooth to about the GFS/AIFS 0.25 deg look
                    from scipy.ndimage import gaussian_filter; p = gaussian_filter(p, 2.5)
                for v in views:
                    out = f"{AM.ROOT}/{c:%Y%m%d%H}/aifsmslp-{M}/step/{v}/{vt}"
                    AM.render_mslp(c, s, lat, lon, p, v, out, src=M); print("ok", out, flush=True)
        except KeyError as e:
            print(f"{M.upper()} step {s}: no field {e}, skipped", flush=True)
        tot += R.bytes
    print(f"{'NOAA GFS' if M == 'gfs' else 'ECMWF IFS'} {c:%Y%m%d%H}Z downloaded {tot/1e6:.1f} MB")
    sys.stdout.flush(); sys.stderr.flush(); os._exit(0)
