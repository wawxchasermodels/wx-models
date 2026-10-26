/* Observations tab: live surface station plots on our own Natural Earth basemap.
   Data is fetched straight from the browser (both sources send CORS "*"; no keys, no server):
     Canada  Environment and Climate Change Canada, MSC GeoMet OGC API "swob-realtime" (Open Government Licence - Canada)
     US      NOAA/NWS ASOS + AWOS via the Iowa Environmental Mesonet currents API
   Layers (toggle chips, any combination; choice kept in localStorage "obsLayers", or "#...&l=plot,hi" in the URL):
     Station plot   current temperature (deg F), gust (mph), wind barb (kt)        -> numbers left of the station point
     High / Low     today's max / min temperature since local midnight at the station -> joins the left column
     Peak gust      today's peak gust since local midnight (mph)                    -> right of the station point
     Wind chill / heat index   NWS formulas from the current ob (only where they apply) -> right column
     MSLP           station sea-level pressure (hPa) plus a Barnes-analysed isobar overlay
   "Today" in the US comes from IEM's per-station daily summary (station's own local calendar day); in Canada it is
   built in the browser from the hourly SWOB reports since local midnight (fetched only when a daily layer is on).
   No station dot is drawn: the wind barb starts at the station point (a ring marks calm wind) and the numbers hug it;
   with no barb or ring, a single number column is centred on the station point instead.
   Declutter by zoom, airports/official first.
   Self-contained module: obs/obs.js + obs/obs.css + obs/basemap.json. It builds its own markup inside a mount element.
     On the forecast site:  <div id="obs-root"> inside the Observations tab pane; forecast.js calls Obs.show() / Obs.hide().
     Standalone page:       <link rel="stylesheet" href="obs.css"><div id="obs-root"></div><script src="obs.js"></script>
                            <script>Obs.show()</script>   (optionally Obs.setView("west") first)  */
"use strict";
const Obs = (() => {
  const HERE = new URL(".", (document.currentScript && document.currentScript.src) || location.href).href;   // basemap.json sits next to this file
  const ECCC = "https://api.weather.gc.ca/collections/swob-realtime/items";
  const IEM = "https://mesonet.agron.iastate.edu/api/1/currents.json";
  const US_NETS = ["WA", "OR", "ID", "MT", "CA", "NV", "UT", "WY", "AZ", "CO", "NM", "AK"].map((s) => s + "_ASOS");
  const CA_BBOX = "-141,41,-100,70";        // BC, Alberta, Yukon, NWT west, Saskatchewan west
  const ECCC_PROPS = ["stn_nam-value", "msc_id-value", "icao_stn_id-value", "date_tm-value", "data_pvdr-value",
    "air_temp", "air_temp-qa", "avg_wnd_spd_10m_pst10mts", "avg_wnd_dir_10m_pst10mts", "avg_wnd_spd_10m_pst2mts",
    "avg_wnd_dir_10m_pst2mts", "max_wnd_spd_10m_pst10mts", "max_wnd_gst_spd_10m_pst10mts", "clim_id-value", "rel_hum", "mslp", "mslp-qa"].join(",");
  // hourly reports since local midnight, for today's high / low / peak gust in Canada (IEM already gives these for the US)
  const ECCC_DAY_PROPS = ["stn_nam-value", "msc_id-value", "icao_stn_id-value", "clim_id-value", "date_tm-value", "air_temp", "air_temp-qa",
    "max_air_temp_pst1hr", "min_air_temp_pst1hr", "max_wnd_spd_10m_pst1hr", "max_pk_wnd_spd_10m_pst1hr", "max_wnd_gst_spd_10m_pst10mts"].join(",");
  const LAYERS = [   // sw = colour of the number on the map (the chip shows a sample, so the chips double as the legend)
    { id: "plot", label: "Station plot", sw: "#ffffff", sample: "48" },
    { id: "hi", label: "High", sw: "#ff8a6e", sample: "57" },
    { id: "lo", label: "Low", sw: "#7f97ff", sample: "36" },
    { id: "pk", label: "Peak gust", sw: "#ffd23f", sample: "41" },
    { id: "feel", label: "Wind chill / heat index", sw: "#c9a2ff", sw2: "#ffa94d", sample: "41" },
    { id: "mslp", label: "MSLP", sw: "#7fe0b5", sample: "1014" },
  ];
  const LAYER_IDS = LAYERS.map((l) => l.id);
  const MAX_AGE_MIN = 90, REFRESH_MS = 10 * 60e3;
  const VIEWS = [   // span = km across the shorter screen side; proj = [central meridian, std parallel 1, std parallel 2, origin lat]
    { id: "pnw", label: "Pacific NW", lon: -120.9, lat: 47.3, span: 1150, proj: [-121, 44, 50, 47] },
    { id: "west", label: "West + Western Canada", lon: -122, lat: 52.5, span: 3300, proj: [-122, 45, 60, 52] },
    { id: "salish", label: "Vancouver Island + Puget Sound", lon: -123, lat: 48.6, span: 600, proj: [-123, 46, 50, 48.5] },
  ];

  /* ---- Lambert conformal conic (sphere, km), one per view so each view reads "north-up" ---- */
  const R = 6371, D = Math.PI / 180;
  function makeProj(lon0, p1, p2, lat0) {
    const P1 = p1 * D, P2 = p2 * D, L0 = lon0 * D, t = (p) => Math.tan(Math.PI / 4 + p / 2);
    const n = Math.log(Math.cos(P1) / Math.cos(P2)) / Math.log(t(P2) / t(P1)), F = Math.cos(P1) * Math.pow(t(P1), n) / n;
    const rho0 = R * F / Math.pow(t(lat0 * D), n);
    const f = (lon, lat) => { const rho = R * F / Math.pow(t(lat * D), n), a = n * (lon * D - L0); return [rho * Math.sin(a), -(rho0 - rho * Math.cos(a))]; };  // y grows down
    return { f, n, L0, key: [lon0, p1, p2, lat0].join(",") };
  }
  const S = { base: null, P: null, pathCache: {}, st: [], placed: [], cities: [], regionsShown: [], view: "pnw", cx: 0, cy: 0, k: 1, w: 0, h: 0, dpr: 1,
    loaded: 0, loading: null, timer: 0, counts: null, inited: false, shown: false, raf: 0,
    raw: [], on: new Set(["plot"]), dayCA: new Map(), dayCAfeat: new Map(), dayCAloaded: 0, dayCAloading: null, dayCAstate: "", iso: null };
  const $ = (id) => document.getElementById(id);

  /* ---- basemap (Path2D in projected km, cached per projection) ---- */
  async function loadBase() {
    const r = await fetch(HERE + "basemap.json");
    if (!r.ok) throw new Error("basemap " + r.status);
    S.base = await r.json();
  }
  function setProj(spec) {
    const P = makeProj(...spec);
    if (S.P && S.P.key === P.key) return;
    S.P = P;
    for (const s of S.st) [s.x, s.y] = P.f(s.lon, s.lat);
  }
  function paths() {
    const key = S.P.key;
    if (S.pathCache[key]) return S.pathCache[key];
    const out = {}, sc = S.base.scale, f = S.P.f;
    for (const lod of ["lo", "hi"]) {
      out[lod] = {};
      for (const [layer, rings] of Object.entries(S.base[lod])) {
        const p = new Path2D(), closed = layer === "land" || layer === "lakes";
        for (const ring of rings) {
          ring.forEach(([x, y], j) => { const [px, py] = f(x / sc, y / sc); j ? p.lineTo(px, py) : p.moveTo(px, py); });
          if (closed) p.closePath();
        }
        out[lod][layer] = p;
      }
    }
    out.places = S.base.places.map(([name, lon, lat, rank, pop]) => { const [x, y] = f(lon, lat); return { name, x, y, rank, pop }; });
    out.towns = (S.base.towns || []).map(([name, lon, lat, pop]) => { const [x, y] = f(lon, lat); return { name, x, y, pop, town: true }; });
    out.regions = S.base.regions.map(([name, abbr, lon, lat]) => { const [x, y] = f(lon, lat); return { name, abbr, x, y }; });
    return (S.pathCache[key] = out);
  }

  /* ---- data ---- */
  const iso = (ms) => new Date(ms).toISOString().replace(/\.\d+Z$/, "Z");
  async function getJSON(url, ms = 60e3) { const r = await fetch(url, { cache: "no-store", signal: AbortSignal.timeout ? AbortSignal.timeout(ms) : undefined }); if (!r.ok) throw new Error(r.status + " " + url.split("?")[0]); return r.json(); }
  const ok = (v) => typeof v === "number" && Number.isFinite(v);
  const qaBad = (q) => ok(q) && q >= 0 && q <= 20;    // SWOB QA: 100 = passed, -1 = not checked/missing, low values = suspect/erroneous

  function ecccUrl(minutes, minutely) {
    const q = new URLSearchParams({ f: "json", limit: "5000", bbox: CA_BBOX, datetime: iso(Date.now() - minutes * 60e3) + "/..",
      "_is-minutely_obs-value": String(minutely), properties: ECCC_PROPS });
    return ECCC + "?" + q;
  }
  function fromEccc(f) {
    const p = f.properties, [lon, lat] = f.geometry.coordinates;
    const icao = p["icao_stn_id-value"] || "", pv = p["data_pvdr-value"] || "";
    const t = ok(p.air_temp) && !qaBad(p["air_temp-qa"]) ? p.air_temp * 9 / 5 + 32 : null;
    let ws = p.avg_wnd_spd_10m_pst10mts, wd = p.avg_wnd_dir_10m_pst10mts;
    if (!ok(ws)) { ws = p.avg_wnd_spd_10m_pst2mts; wd = p.avg_wnd_dir_10m_pst2mts; }
    const gk = ok(p.max_wnd_gst_spd_10m_pst10mts) ? p.max_wnd_gst_spd_10m_pst10mts : p.max_wnd_spd_10m_pst10mts;
    return { id: "CA:" + (p["msc_id-value"] || icao || p["stn_nam-value"]), code: icao || p["msc_id-value"] || "",
      name: p["stn_nam-value"] || icao, ctry: "CA", lon, lat, time: Date.parse(p["date_tm-value"]),
      kind: icao || pv === "NAV CANADA" ? 0 : pv === "MSC" || pv === "DND" ? 1 : 2,
      src: pv === "NAV CANADA" ? "NAV CANADA" : pv === "MSC" ? "ECCC (MSC)" : pv ? "ECCC partner " + pv : "ECCC",
      t, ws: ok(ws) ? ws / 1.852 : null, wd: ok(wd) ? wd : null, g: ok(gk) ? gk / 1.609344 : null,
      rh: ok(p.rel_hum) ? p.rel_hum : null, p: ok(p.mslp) && !qaBad(p["mslp-qa"]) ? p.mslp : null,
      elev: ok(f.geometry.coordinates[2]) ? f.geometry.coordinates[2] : null, tz: caZone(p["clim_id-value"], lon, lat) };
  }
  function fromIem(d) {
    const time = Date.parse(d.utc_valid);
    // IEM's max/min/peak fields are the station's own local calendar day (d.local_date). Just after local midnight the
    // last ob can still belong to yesterday, so only use them when "now" at the station is still that date.
    const lv = Date.parse((d.local_valid || "") + "Z"), nowLocal = ok(lv) ? new Date(lv + (Date.now() - time)).toISOString().slice(0, 10) : "";
    const today = !!d.local_date && nowLocal === d.local_date;
    const gk = ok(d.max_gust) ? d.max_gust : null, sk = ok(d.max_sknt) ? d.max_sknt : null;
    const pkKt = gk != null || sk != null ? Math.max(gk ?? -1, sk ?? -1) : null;
    return { id: "US:" + d.station, code: d.station, name: d.name, ctry: "US", lon: d.lon, lat: d.lat, time,
      kind: 0, src: "NWS ASOS/AWOS (" + d.network.replace("_ASOS", "") + ")", t: ok(d.tmpf) ? d.tmpf : null,
      ws: ok(d.sknt) ? d.sknt : null, wd: ok(d.drct) ? d.drct : null, g: ok(d.gust) ? d.gust * 1.150779 : null,
      rh: ok(d.relh) ? d.relh : null, p: ok(d.mslp) ? d.mslp : null,
      hi: today && ok(d.max_tmpf) ? d.max_tmpf : null, lo: today && ok(d.min_tmpf) ? d.min_tmpf : null,
      pk: today && pkKt != null ? pkKt * 1.150779 : null, pkKind: gk != null && gk >= (sk ?? -1) ? "gust" : "sustained",
      pkAt: today ? (gk != null && gk >= (sk ?? -1) ? d.local_max_gust_ts : d.local_max_sknt_ts) || "" : "",
      day: today ? d.local_date : "", daySrc: "IEM daily summary" };
  }

  /* ---- local calendar day ---- */
  // Canadian station time zone from the climate ID's province digit (1 BC, 2 YT/NT/NU, 3 AB, 4 SK, 5 MB), refined for the
  // parts of BC that keep Mountain time; falls back to position when there is no climate ID.
  function caZone(clim, lon, lat) {
    const pr = clim ? String(clim)[0] : lat >= 60 ? (lon < -124 ? "Y" : "2") : lon > -102 ? "5" : lon > -110 ? "4" : lon > -120 || (lat < 53.9 && lon > -118) ? "3" : "1";
    if (pr === "1") return lat > 54.5 && lon > -124 ? "America/Fort_Nelson" : lat < 52 && lon > -117.6 ? "America/Edmonton" : "America/Vancouver";
    if (pr === "2" || pr === "Y") return lon < -124 && lat < 69.6 ? "America/Whitehorse" : "America/Edmonton";
    return pr === "3" ? "America/Edmonton" : pr === "4" ? "America/Regina" : pr === "5" ? "America/Winnipeg" : "America/Vancouver";
  }
  const dtf = {};
  function zoneParts(tz, ms) {
    const f = dtf[tz] || (dtf[tz] = new Intl.DateTimeFormat("en-CA", { timeZone: tz, year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", second: "2-digit", hourCycle: "h23" }));
    const o = {}; for (const x of f.formatToParts(new Date(ms))) o[x.type] = x.value;
    return o;
  }
  function midnight(tz, ms) {   // UTC ms of the most recent local midnight in tz, plus the local date
    const o = zoneParts(tz, ms), off = Date.UTC(+o.year, o.month - 1, +o.day, +o.hour, +o.minute, +o.second) - Math.floor(ms / 1000) * 1000;
    return { t: Date.UTC(+o.year, o.month - 1, +o.day) - off, date: `${o.year}-${o.month}-${o.day}` };
  }

  /* ---- today's high / low / peak gust for Canada from hourly SWOB reports (lazy: only while a daily layer is on) ---- */
  function caStationId(p) { return "CA:" + (p["msc_id-value"] || p["icao_stn_id-value"] || p["stn_nam-value"]); }
  async function loadDayCA(force) {
    if (S.dayCAloading) return S.dayCAloading;
    if (!force && S.dayCAloaded && Date.now() - S.dayCAloaded < REFRESH_MS - 30e3) return;
    S.dayCAloading = (async () => {
      const now = Date.now(), zones = ["America/Winnipeg", "America/Regina", "America/Edmonton", "America/Vancouver", "America/Whitehorse", "America/Fort_Nelson"];
      const earliest = Math.min(...zones.map((z) => midnight(z, now).t));
      // first time: everything since the earliest local midnight; afterwards only the last 3 hours (late reports included)
      let from = S.dayCAloaded ? Math.max(earliest, S.dayCAloaded - 3 * 3600e3) : earliest;
      for (const [k, f] of S.dayCAfeat) if (f.time <= earliest) S.dayCAfeat.delete(k);
      let offset = 0, pages = 0, n = 0;
      while (pages < 6) {
        const q = new URLSearchParams({ f: "json", limit: "10000", offset: String(offset), bbox: CA_BBOX, datetime: iso(from) + "/..",
          "_is-minutely_obs-value": "false", properties: ECCC_DAY_PROPS });
        const j = await getJSON(ECCC + "?" + q);
        const fs = j.features || [];
        for (const f of fs) { const p = f.properties, t = Date.parse(p["date_tm-value"]); const [lon, lat] = (f.geometry && f.geometry.coordinates) || [];
          if (ok(t)) S.dayCAfeat.set(f.id, { id: caStationId(p), time: t, p, tz: caZone(p["clim_id-value"], lon, lat) }); }
        n += fs.length; pages++;
        if (fs.length < 10000) break;
        offset += fs.length;
      }
      // aggregate per station over reports AFTER local midnight (the midnight report's past-hour values belong to yesterday)
      const agg = new Map(), mids = {};
      for (const { id, time, p, tz } of S.dayCAfeat.values()) {
        const m = mids[tz] || (mids[tz] = midnight(tz, now));
        if (time <= m.t || time > now + 60e3) continue;
        const a = agg.get(id) || agg.set(id, { hi: null, lo: null, pk: null, n: 0, hours: new Set(), mid: m.t, date: m.date }).get(id);
        const C2F = (c) => c * 9 / 5 + 32, tq = ok(p.air_temp) && !qaBad(p["air_temp-qa"]) ? p.air_temp : null;
        const hi = [p.max_air_temp_pst1hr, tq].filter(ok), lo = [p.min_air_temp_pst1hr, tq].filter(ok);
        const pk = [p.max_wnd_spd_10m_pst1hr, p.max_pk_wnd_spd_10m_pst1hr, p.max_wnd_gst_spd_10m_pst10mts].filter(ok);
        if (hi.length) a.hi = Math.max(a.hi ?? -999, C2F(Math.max(...hi)));
        if (lo.length) a.lo = Math.min(a.lo ?? 999, C2F(Math.min(...lo)));
        if (pk.length) a.pk = Math.max(a.pk ?? -1, Math.max(...pk) / 1.609344);
        a.hours.add(Math.floor(time / 3600e3));
      }
      const out = new Map();
      for (const [id, a] of agg) {
        const want = Math.floor((now - a.mid) / 3600e3);          // hourly reports expected so far today
        const full = a.hours.size >= Math.max(1, Math.round(want * 0.6));
        out.set(id, { hi: full ? a.hi : null, lo: full ? a.lo : null, pk: full ? a.pk : null, pkKind: "gust", pkAt: "",
          day: a.date, dayN: a.hours.size, dayWant: want, daySrc: `${a.hours.size} hourly SWOB reports` });
      }
      S.dayCA = out; S.dayCAloaded = now; S.dayCAstate = `ok ${n}`;
    })().catch((e) => { S.dayCAstate = "failed"; console.warn("Canada daily", e); })
      .finally(() => { S.dayCAloading = null; finalize(); draw(); });
    return S.dayCAloading;
  }
  const needDay = () => S.on.has("hi") || S.on.has("lo") || S.on.has("pk");

  /* ---- wind chill / heat index (NWS formulas) ---- */
  function feels(t, ktWind, rh) {
    if (t == null) return null;
    const v = ktWind == null ? null : ktWind * 1.150779;
    if (t <= 50 && v != null && v > 3) { const p = Math.pow(v, 0.16); return { v: 35.74 + 0.6215 * t - 35.75 * p + 0.4275 * t * p, k: "wc" }; }
    if (t >= 80 && rh != null) {
      let hi = 0.5 * (t + 61 + (t - 68) * 1.2 + rh * 0.094);
      if ((hi + t) / 2 >= 80) {
        hi = -42.379 + 2.04901523 * t + 10.14333127 * rh - 0.22475541 * t * rh - 0.00683783 * t * t - 0.05481717 * rh * rh
          + 0.00122874 * t * t * rh + 0.00085282 * t * rh * rh - 0.00000199 * t * t * rh * rh;
        if (rh < 13 && t <= 112) hi -= ((13 - rh) / 4) * Math.sqrt((17 - Math.abs(t - 95)) / 17);
        else if (rh > 85 && t <= 87) hi += ((rh - 85) / 10) * ((87 - t) / 5);
      }
      return { v: hi, k: "hx" };
    }
    return null;
  }
  function finalize() {   // merge today's Canadian extremes into the latest obs, then QC everything
    const list = S.raw.map((o) => (o.ctry === "CA" ? { ...o, ...(S.dayCA.get(o.id) || {}) } : { ...o }));
    S.st = qc(list); S.iso = null;
    const shown = S.st.filter((s) => !s.bad), now = S.loaded;
    const lat = (c) => { const a = shown.filter((s) => s.ctry === c).map((s) => (now - s.time) / 60e3).sort((x, y) => x - y); return a.length ? Math.round(a[a.length >> 1]) : null; };
    S.counts = { us: shown.filter((s) => s.ctry === "US").length, ca: shown.filter((s) => s.ctry === "CA").length,
      dropped: S.st.length - shown.length, flagged: S.st.filter((s) => s.qc.length).length, ageUS: lat("US"), ageCA: lat("CA"), fetchMs: S.fetchMs, fails: S.fails,
      withHi: shown.filter((s) => s.hi != null).length, withPk: shown.filter((s) => s.pk != null && s.pkKind !== "sustained").length, withP: shown.filter((s) => s.p != null).length,
      withFeel: shown.filter((s) => s.fl != null).length, dayCA: S.dayCAstate };
    window.__obsStats = S.counts;
  }

  async function load() {
    if (S.loading) return S.loading;
    $("obs-loader").hidden = S.st.length > 0; status("Loading stations…");
    const t0 = performance.now();
    S.loading = (async () => {
      const jobs = [getJSON(ecccUrl(MAX_AGE_MIN + 5, false)), getJSON(ecccUrl(12, true)), ...US_NETS.map((n) => getJSON(IEM + "?network=" + n + "&minutes=" + MAX_AGE_MIN))];
      const res = await Promise.allSettled(jobs);
      const best = new Map(), now = Date.now(), fails = [];
      const add = (o) => {
        if (!ok(o.lon) || !ok(o.lat) || !ok(o.time) || now - o.time > MAX_AGE_MIN * 60e3) return;
        const b = best.get(o.id);
        if (!b || o.time > b.time) best.set(o.id, o);
      };
      res.forEach((r, j) => {
        if (r.status !== "fulfilled") { fails.push(j < 2 ? "Canada" : US_NETS[j - 2].slice(0, 2)); return; }
        if (j < 2) (r.value.features || []).forEach((f) => add(fromEccc(f)));
        else (r.value.data || []).forEach((d) => add(fromIem(d)));
      });
      S.raw = [...best.values()];
      S.loaded = now; S.fetchMs = Math.round(performance.now() - t0); S.fails = [...new Set(fails)];
      if (needDay()) await loadDayCA(true);
      finalize();
    })().finally(() => { S.loading = null; $("obs-loader").hidden = true; draw(); status(); });
    return S.loading;
  }

  /* ---- QC: range checks, then neighbours (median of stations within 100 km) ---- */
  function qc(list) {
    for (const s of list) {
      s.qx = s.lon * 111.2 * Math.cos(s.lat * D); s.qy = s.lat * 111.2; s.qc = [];
      if (S.P) [s.x, s.y] = S.P.f(s.lon, s.lat);
      if (s.t != null && (s.t < -70 || s.t > 125)) { s.t = null; s.qc.push("temperature out of range"); }
      if (s.ws != null && (s.ws < 0 || s.ws > 130)) { s.ws = null; s.qc.push("wind out of range"); }
      if (s.wd != null && (s.wd < 0 || s.wd > 360)) { s.wd = null; s.ws = null; s.qc.push("wind direction invalid"); }
      if (s.g != null && (s.g > 160 || (s.ws != null && s.g < s.ws * 1.150779 - 2))) { s.g = null; s.qc.push("gust inconsistent with wind"); }
      for (const k of ["hi", "lo"]) if (s[k] != null && (s[k] < -70 || s[k] > 130)) { s[k] = null; s.qc.push(`today's ${k === "hi" ? "high" : "low"} out of range`); }
      if (s.hi != null && s.lo != null && s.lo > s.hi) { s.hi = s.lo = null; s.qc.push("today's low above high"); }
      if (s.pk != null && (s.pk < 0 || s.pk > 180)) { s.pk = null; s.qc.push("peak gust out of range"); }
      if (s.p != null && (s.p < 940 || s.p > 1065)) { s.p = null; s.qc.push("sea-level pressure out of range"); }
      s.h = hash(s.id);
    }
    const cell = 100, grid = new Map(), key = (i, j) => i + "," + j;
    for (const s of list) { const k = key(Math.floor(s.qx / cell), Math.floor(s.qy / cell)); (grid.get(k) || grid.set(k, []).get(k)).push(s); }
    const near = (s) => {
      const i = Math.floor(s.qx / cell), j = Math.floor(s.qy / cell), out = [];
      for (let a = -1; a <= 1; a++) for (let b = -1; b <= 1; b++) for (const o of grid.get(key(i + a, j + b)) || [])
        if (o !== s && Math.hypot(o.qx - s.qx, o.qy - s.qy) < cell) out.push(o);
      return out;
    };
    const med = (a) => { a.sort((x, y) => x - y); return a[a.length >> 1]; };
    for (const s of list) {
      const nb = near(s);
      const ts = nb.map((o) => o.t).filter((v) => v != null);
      if (s.t != null && ts.length >= 4 && Math.abs(s.t - med(ts)) > 25) { s.qc.push(`temperature ${Math.round(s.t)}°F vs neighbours ${Math.round(med(ts))}°F`); s.tBad = true; }
      const gs = nb.map((o) => Math.max(o.g || 0, (o.ws || 0) * 1.15));
      if (s.g != null && s.g > 45 && gs.length >= 4 && med(gs) < s.g / 3) { s.qc.push(`gust ${Math.round(s.g)} mph vs neighbours ${Math.round(med(gs))} mph`); s.gBad = true; }
      for (const k of ["hi", "lo"]) {
        const v = nb.map((o) => o[k]).filter((x) => x != null);
        if (s[k] != null && v.length >= 4 && Math.abs(s[k] - med(v)) > 30) { s.qc.push(`today's ${k === "hi" ? "high" : "low"} ${Math.round(s[k])}°F vs neighbours ${Math.round(med(v))}°F`); s[k + "Bad"] = true; }
      }
      const pks = nb.map((o) => o.pk).filter((x) => x != null);
      if (s.pk != null && s.pk > 50 && pks.length >= 4 && med(pks) < s.pk / 3) { s.qc.push(`peak gust ${Math.round(s.pk)} mph vs neighbours ${Math.round(med(pks))} mph`); s.pkBad = true; }
      const ps = nb.map((o) => o.p).filter((x) => x != null);
      if (s.p != null && ps.length >= 4 && Math.abs(s.p - med(ps)) > 8) { s.qc.push(`pressure ${s.p.toFixed(1)} hPa vs neighbours ${med(ps).toFixed(1)} hPa`); s.pBad = true; }
    }
    for (const s of list) {
      if (s.tBad) s.t = null; if (s.gBad) s.g = null; if (s.hiBad) s.hi = null; if (s.loBad) s.lo = null; if (s.pkBad) s.pk = null; if (s.pBad) s.p = null;
      // the current reading is part of today too
      if (s.t != null && s.day) { if (s.hi != null) s.hi = Math.max(s.hi, s.t); if (s.lo != null) s.lo = Math.min(s.lo, s.t); }
      if (s.g != null && s.pk != null && s.g > s.pk) s.pk = s.g;
      const f = feels(s.t, s.ws, s.rh); s.fl = f ? f.v : null; s.flk = f ? f.k : "";
      s.bad = s.t == null && s.ws == null && s.g == null && s.hi == null && s.lo == null && s.pk == null && s.p == null;
    }
    return list;
  }
  function hash(str) { let h = 2166136261; for (let i = 0; i < str.length; i++) { h ^= str.charCodeAt(i); h = Math.imul(h, 16777619); } return (h >>> 0) / 4294967296; }

  /* ---- view ---- */
  function setView(id) { const v = VIEWS.find((x) => x.id === id) || VIEWS[0]; S.view = v.id; S.pending = v; if (S.w) applyView(); }
  function applyView() {
    const v = S.pending || VIEWS.find((x) => x.id === S.view) || VIEWS[0]; S.pending = null;
    setProj(v.proj);
    [S.cx, S.cy] = S.P.f(v.lon, v.lat);
    S.k = Math.min(S.w, S.h) / v.span;
  }
  const viewId = () => S.view;
  const sx = (x) => (x - S.cx) * S.k + S.w / 2, sy = (y) => (y - S.cy) * S.k + S.h / 2;
  function zoomAt(f, px, py) {
    const k2 = Math.max(0.035, Math.min(6, S.k * f)); f = k2 / S.k;
    S.cx += (px - S.w / 2) / S.k * (1 - 1 / f); S.cy += (py - S.h / 2) / S.k * (1 - 1 / f); S.k = k2;
    S.view = ""; hideTip(); req();
  }
  function req() { if (!S.raf) S.raf = requestAnimationFrame(() => { S.raf = 0; draw(); }); }

  function resize() {
    const c = $("obs-canvas"), r = c.getBoundingClientRect();
    if (!r.width) return false;
    const first = !S.w;
    setNumberScale();
    S.w = r.width; S.h = r.height; S.dpr = Math.min(window.devicePixelRatio || 1, 2.5);
    c.width = Math.round(S.w * S.dpr); c.height = Math.round(S.h * S.dpr);
    if (first || S.pending) applyView();
    return true;
  }

  /* ---- style: our own dark slate look ---- */
  const C = { water: "#0e1825", land: "#343c47", lake: "#0e1825", coast: "#62788b", state: "rgba(214,222,232,.20)", border: "rgba(238,229,210,.62)",
    barb: "#cfe3ee", gust: "#ff5ec4", halo: "rgba(9,14,22,.92)", city: "#efe9de", cityDot: "#f0e6d2", town: "#c2bbb0", townDot: "#b5ad9f", region: "rgba(205,214,226,.26)",
    iso: "rgba(127,224,181,.62)", isoCase: "rgba(9,14,22,.45)" };
  const KC = Object.fromEntries(LAYERS.map((l) => [l.id, l.sw]));   // number colours by kind
  KC.wc = LAYERS[4].sw; KC.hx = LAYERS[4].sw2; KC.p = KC.mslp; KC.g = "#ff5ec4";
  const tempColor = (t) => (Math.round(t) <= 32 ? "#8fd3ff" : "#ffffff");   // white; light blue at or below freezing
  const TOWN_FONT = "500 11px 'Outfit', system-ui, sans-serif", ISO_FONT = "600 12px 'IBM Plex Mono', ui-monospace, monospace";
  const Z = 1.5;   // station-plot scale (text, barb, ring, spacing all scale together)
  // station numbers: NF halves them on phone-sized screens (same breakpoint as obs.css, max-width 640px); desktop NF = 1
  const PHONE_NF = 0.5, phoneMQ = window.matchMedia ? window.matchMedia("(max-width: 640px)") : null;
  let NF = 1, FONT, FONT_S;   // FONT_S is used when a station shows 3+ numbers
  function setNumberScale() {
    NF = phoneMQ && phoneMQ.matches ? PHONE_NF : 1;
    const px = (v) => (NF === 1 ? Math.round(v) : Math.round(v * 4) / 4);   // desktop keeps whole px; phone keeps quarter px
    FONT = `600 ${px(13 * Z * NF)}px 'IBM Plex Mono', ui-monospace, monospace`;
    FONT_S = `600 ${px(11.5 * Z * NF)}px 'IBM Plex Mono', ui-monospace, monospace`;
  }
  setNumberScale();
  const CITY_FONT = "500 12px 'Outfit', system-ui, sans-serif";

  function draw() {
    if (!S.shown || !S.base || !S.w || !S.P) return;
    const c = $("obs-canvas"), g = c.getContext("2d"), d = S.dpr, PP = paths();
    g.setTransform(d, 0, 0, d, 0, 0); g.fillStyle = C.water; g.fillRect(0, 0, S.w, S.h);
    const P = PP[S.k > 0.6 ? "hi" : "lo"];
    g.setTransform(d * S.k, 0, 0, d * S.k, d * (S.w / 2 - S.cx * S.k), d * (S.h / 2 - S.cy * S.k));
    g.lineJoin = "round";
    g.fillStyle = C.land; g.fill(P.land, "evenodd");
    g.fillStyle = C.lake; g.fill(P.lakes, "evenodd");
    const lw = (px) => px / S.k;
    g.strokeStyle = C.coast; g.lineWidth = lw(0.8); g.stroke(P.land); g.stroke(P.lakes);
    g.strokeStyle = C.state; g.lineWidth = lw(1); g.stroke(P.states);
    g.strokeStyle = C.border; g.lineWidth = lw(1.4); g.stroke(P.borders);
    if (P.borders_sea) { g.setLineDash([lw(5), lw(4)]); g.lineWidth = lw(1.2); g.stroke(P.borders_sea); g.setLineDash([]); }   // boundary through water
    if (S.on.has("mslp")) {
      const A = isobars();
      if (A.path) { g.strokeStyle = C.isoCase; g.lineWidth = lw(3); g.stroke(A.path); g.strokeStyle = C.iso; g.lineWidth = lw(1.3); g.stroke(A.path); }
    }
    g.setTransform(d, 0, 0, d, 0, 0);
    layout(g, PP);
    paint(g);
    status();
  }

  /* ---- MSLP isobars: two-pass Barnes analysis of station sea-level pressure on a grid in projected km, then marching
     squares. Only drawn where stations support it (a grid cell needs a station within 110 km and 3 within 220 km). ---- */
  function grid() {
    if (S.iso && S.iso.key === S.P.key) return S.iso;
    const pts = S.st.filter((s) => !s.bad && s.p != null && !(s.elev != null && s.elev > 1500)).map((s) => [s.x, s.y, s.p]);
    const out = (S.iso = { key: S.P.key, n: pts.length, lv: {} });
    if (pts.length < 8) return out;
    let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
    for (const [x, y] of pts) { x0 = Math.min(x0, x); y0 = Math.min(y0, y); x1 = Math.max(x1, x); y1 = Math.max(y1, y); }
    let cs = 15; while (((x1 - x0) / cs + 1) * ((y1 - y0) / cs + 1) > 90000) cs *= 1.25;
    const nx = Math.ceil((x1 - x0) / cs) + 1, ny = Math.ceil((y1 - y0) / cs) + 1, B = 110, bins = new Map(), bk = (i, j) => i * 100003 + j;
    for (const q of pts) { const k = bk(Math.floor(q[0] / B), Math.floor(q[1] / B)); (bins.get(k) || bins.set(k, []).get(k)).push(q); }
    const near = (x, y, r, fn) => { const n = Math.ceil(r / B), i0 = Math.floor(x / B), j0 = Math.floor(y / B);
      for (let a = -n; a <= n; a++) for (let b = -n; b <= n; b++) for (const q of bins.get(bk(i0 + a, j0 + b)) || []) { const d2 = (q[0] - x) ** 2 + (q[1] - y) ** 2; if (d2 < r * r) fn(q, d2); } };
    const R1 = 130, R2 = 80;
    const pass = (x, y, R, val) => { let sw = 0, sv = 0; near(x, y, 2.5 * R, (q, d2) => { const w = Math.exp(-d2 / (R * R)); sw += w; sv += w * val(q); }); return sw > 1e-6 ? sv / sw : NaN; };
    const f1 = new Map(); for (const q of pts) f1.set(q, pass(q[0], q[1], R1, (o) => o[2]));
    const G = new Float32Array(nx * ny);
    for (let j = 0; j < ny; j++) for (let i = 0; i < nx; i++) {
      const x = x0 + i * cs, y = y0 + j * cs;
      let close = Infinity, cnt = 0; near(x, y, 220, (q, d2) => { cnt++; close = Math.min(close, d2); });
      if (close > 110 * 110 || cnt < 3) { G[j * nx + i] = NaN; continue; }
      const a = pass(x, y, R1, (o) => o[2]), r = pass(x, y, R2, (o) => o[2] - f1.get(o));
      G[j * nx + i] = a + (Number.isFinite(r) ? r : 0);
    }
    // two light 3x3 smoothing passes (valid cells only) so lines do not zig-zag between stations
    let H = G;
    for (let pass = 0; pass < 2; pass++) {
      const Src = H; H = new Float32Array(Src);
      for (let j = 1; j < ny - 1; j++) for (let i = 1; i < nx - 1; i++) {
        if (!Number.isFinite(Src[j * nx + i])) continue; let sw = 0, sv = 0;
        for (let b = -1; b <= 1; b++) for (let a = -1; a <= 1; a++) { const v = Src[(j + b) * nx + i + a]; if (Number.isFinite(v)) { const w = a || b ? 1 : 2; sw += w; sv += w * v; } }
        H[j * nx + i] = sv / sw;
      }
    }
    Object.assign(out, { G: H, nx, ny, x0, y0, cs });
    return out;
  }
  function contours(A, step) {
    if (A.lv[step]) return A.lv[step];
    const { G, nx, ny, x0, y0, cs } = A, path = new Path2D(), segs = [];
    let lo = Infinity, hi = -Infinity; for (const v of G) if (Number.isFinite(v)) { lo = Math.min(lo, v); hi = Math.max(hi, v); }
    for (let L = Math.ceil(lo / step) * step; L <= hi; L += step) {
      for (let j = 0; j < ny - 1; j++) for (let i = 0; i < nx - 1; i++) {
        const a = G[j * nx + i], b = G[j * nx + i + 1], c = G[(j + 1) * nx + i + 1], d = G[(j + 1) * nx + i];
        if (!(Number.isFinite(a) && Number.isFinite(b) && Number.isFinite(c) && Number.isFinite(d))) continue;
        const X = x0 + i * cs, Y = y0 + j * cs, e = [];
        const cut = (p, q, px, py, qx, qy) => { if ((p < L) !== (q < L)) { const t = (L - p) / (q - p); e.push([px + (qx - px) * t, py + (qy - py) * t]); } };
        cut(a, b, X, Y, X + cs, Y); cut(b, c, X + cs, Y, X + cs, Y + cs); cut(d, c, X, Y + cs, X + cs, Y + cs); cut(a, d, X, Y, X, Y + cs);
        if (e.length === 4) {   // saddle: pair edges by the cell-centre value
          const m = (a + b + c + d) / 4;
          const pairs = (m < L) === (a < L) ? [[0, 1], [2, 3]] : [[0, 3], [1, 2]];
          for (const [u, v] of pairs) { path.moveTo(...e[u]); path.lineTo(...e[v]); segs.push([e[u][0], e[u][1], e[v][0], e[v][1], L]); }
        } else if (e.length === 2) { path.moveTo(...e[0]); path.lineTo(...e[1]); segs.push([e[0][0], e[0][1], e[1][0], e[1][1], L]); }
      }
    }
    return (A.lv[step] = { path, segs });
  }
  const isoStep = () => (S.k > 1.2 ? 2 : 4);
  function isobars() { const A = grid(); return A.G ? contours(A, isoStep()) : {}; }

  /* ---- collision-based declutter: every label/plot reserves exact rectangles; nothing may overlap or leave the map ---- */
  function Boxes(w, h, reserved) {
    const cell = 64, grid = new Map(), all = [];
    const keys = (r, fn) => { for (let i = Math.floor(r[0] / cell); i <= Math.floor(r[2] / cell); i++) for (let j = Math.floor(r[1] / cell); j <= Math.floor(r[3] / cell); j++) fn(i * 4096 + j); };
    const api = {
      fits(rs) {
        for (const r of rs) {
          if (r[0] < 2 || r[1] < 2 || r[2] > w - 2 || r[3] > h - 2) return false;
          let hit = false;
          keys(r, (k) => { if (!hit) for (const o of grid.get(k) || []) if (r[0] < o[2] && r[2] > o[0] && r[1] < o[3] && r[3] > o[1]) { hit = true; break; } });
          if (hit) return false;
        }
        return true;
      },
      add(rs) { for (const r of rs) { all.push(r); keys(r, (k) => (grid.get(k) || grid.set(k, []).get(k)).push(r)); } },
    };
    api.add(reserved);
    return api;
  }
  const pad = (r, m) => [r[0] - m, r[1] - m, r[2] + m, r[3] + m];

  function barbGeom(s, px, py) {     // returns {lines:[[x0,y0,x1,y1]], flags:[[x0,y0,x1,y1,x2,y2]], calm:bool}
    if (s.ws == null) return null;
    if (s.ws < 2.5 || s.wd == null) return { calm: true, lines: [], flags: [] };
    const a = s.wd * D - S.P.n * (s.lon * D - S.P.L0);     // grid north differs from true north on a conic map
    const ux = Math.sin(a), uy = -Math.cos(a);                // staff points toward where the wind comes FROM
    const L = 27.5 * Z, ex = px + ux * L, ey = py + uy * L, bx = px, by = py;   // staff starts right at the station (no dot)
    const fx = -uy, fy = ux;                                  // clockwise of the staff = northern-hemisphere side (as MetPy/matplotlib)
    const FL = 10 * Z, step = 3.6 * Z, lines = [[bx, by, ex, ey]], flags = [];
    const at = (o) => [ex - ux * o, ey - uy * o];
    let kt = Math.round(s.ws / 5) * 5, pos = 0;
    while (kt >= 50) { const [x0, y0] = at(pos), [x1, y1] = at(pos + 5 * Z); flags.push([x0, y0, x0 + fx * FL, y0 + fy * FL, x1, y1]); pos += 6.5 * Z; kt -= 50; }
    const startPos = pos;
    while (kt >= 10) { const [x0, y0] = at(pos); lines.push([x0, y0, x0 + fx * FL + ux * 3 * Z, y0 + fy * FL + uy * 3 * Z]); pos += step; kt -= 10; }
    if (kt >= 5) { if (pos === 0 && startPos === 0) pos = step; const [x0, y0] = at(pos); lines.push([x0, y0, x0 + fx * FL * 0.5 + ux * 1.5 * Z, y0 + fy * FL * 0.5 + uy * 1.5 * Z]); }
    return { calm: false, lines, flags };
  }

  function layout(g, PP) {
    const zoomEl = S.root.querySelector(".obs-zoom"), base = $("ostage").getBoundingClientRect();
    const rect = (el) => { const r = el.getBoundingClientRect(); return [r.left - base.left - 4, r.top - base.top - 4, r.right - base.left + 4, r.bottom - base.top + 4]; };
    const B = Boxes(S.w, S.h, [rect(zoomEl)]);
    const M = (S.k > 1.5 ? 2 : S.k > 0.5 ? 3 : 4) * Z;              // minimum spacing between plots
    const vis = (x, y) => x > -40 && y > -40 && x < S.w + 40 && y < S.h + 40;
    S.placed = []; S.cities = []; S.regionsShown = [];

    // cities: Natural Earth scalerank tiers by zoom; the biggest are placed before stations
    g.font = CITY_FONT;
    const maxRank = S.k < 0.25 ? 3 : S.k < 0.5 ? 4 : S.k < 0.9 ? 6 : S.k < 1.8 ? 8 : 10;
    const pinRank = S.k < 0.25 ? 2 : S.k < 0.5 ? 3 : 4;   // only big cities outrank station plots
    const placeCity = (c) => {
      const x = sx(c.x), y = sy(c.y); if (!vis(x, y)) return;
      const tw = g.measureText(c.name).width, hh = c.town ? 7 : 8, dot = [x - 3, y - 3, x + 3, y + 3];
      // label to the right, left, above or below its dot (centre-aligned when above/below)
      for (const [tx, ty, al] of [[x + 6, y, "left"], [x - 6, y, "right"], [x, y - 12, "center"], [x, y + 12, "center"], [x + 5, y - 11, "left"], [x + 5, y + 11, "left"], [x - 5, y - 11, "right"], [x - 5, y + 11, "right"], [x, y - 24, "center"], [x, y + 24, "center"]]) {
        const x0 = al === "left" ? tx : al === "right" ? tx - tw : tx - tw / 2;
        const rs = [pad(dot, 1), pad([x0, ty - hh, x0 + tw, ty + hh - 1], c.town ? 9 : 2)];   // towns keep extra air around them
        if (B.fits(rs)) { B.add(rs); S.cities.push({ c, x, y, tx, ty, al }); return true; }
      }
      return S.namedTry ? S.namedTry(c) : false;
    };
    S.namedTry = null;
    S.isoLabels = [];
    if (S.on.has("mslp")) {   // isobar values, spaced along the lines, placed before everything else
      const A = isobars(); g.font = ISO_FONT;
      const pickd = [];
      for (const sg of A.segs || []) {
        const x = sx((sg[0] + sg[2]) / 2), y = sy((sg[1] + sg[3]) / 2);
        if (x < 30 || y < 20 || x > S.w - 30 || y > S.h - 20) continue;
        if (pickd.some((q) => Math.hypot(q[0] - x, q[1] - y) < (q[2] === sg[4] ? 320 : 70))) continue;
        const txt = String(Math.round(sg[4])), w = g.measureText(txt).width, r = [x - w / 2 - 2, y - 8, x + w / 2 + 2, y + 8];
        if (!B.fits([r])) continue;
        B.add([r]); pickd.push([x, y, sg[4]]); S.isoLabels.push({ txt, x, y });
      }
    }
    const cities = PP.places.filter((c) => c.rank <= maxRank);
    cities.filter((c) => c.rank <= pinRank).forEach(placeCity);

    // stations: airports/official first, then a stable per-station order so zooming in only adds stations
    g.font = FONT;
    const on = S.on, plot = on.has("plot"), r0 = (v) => String(Math.round(v));
    const linesFor = (s) => {   // left column: temperatures (+ current gust); right column: pressure, feels-like, peak gust
      const L = [], R = [];
      if (on.has("hi") && s.hi != null) L.push({ txt: r0(s.hi), kind: "hi" });
      if (plot && s.t != null) L.push({ txt: r0(s.t), kind: "t" });
      if (on.has("lo") && s.lo != null) L.push({ txt: r0(s.lo), kind: "lo" });
      if (plot && s.g != null && s.g >= 10) L.push({ txt: r0(s.g), kind: "g" });
      if (on.has("mslp") && s.p != null) R.push({ txt: r0(s.p), kind: "p" });
      if (on.has("feel") && s.fl != null) R.push({ txt: r0(s.fl), kind: s.flk });
      if (on.has("pk") && s.pk != null && s.pk >= 10 && s.pkKind !== "sustained") R.push({ txt: r0(s.pk), kind: "pk" });
      return [L, R];
    };
    const has = (s) => { const [L, R] = linesFor(s); return L.length + R.length > 0 || (plot && s.ws != null); };
    const list = S.st.filter((s) => !s.bad && has(s)).sort((a, b) => a.kind - b.kind || (b.t != null) - (a.t != null) || a.h - b.h);
    let inView = 0;
    const tryStation = (s) => {
      const px = sx(s.x), py = sy(s.y);
      const rs = [[px - 3 * Z, py - 3 * Z, px + 3 * Z, py + 3 * Z]];   // keep the bare station point clear
      const [L, R] = linesFor(s);
      const bg = plot ? barbGeom(s, px, py) : null, barbBoxes = [];
      if (bg) {
        if (bg.calm) barbBoxes.push([px - 7.5 * Z, py - 7.5 * Z, px + 7.5 * Z, py + 7.5 * Z]);
        // barbs are thin diagonals: reserve small boxes sampled along every stroke instead of one coarse bounding box
        for (const l of [...bg.lines, ...bg.flags]) for (let i = 0; i + 3 < l.length; i += 2) {
          const n = Math.max(1, Math.ceil(Math.hypot(l[i + 2] - l[i], l[i + 3] - l[i + 1]) / 5));
          for (let j = 0; j <= n; j++) { const X = l[i] + (l[i + 2] - l[i]) * j / n, Y = l[i + 1] + (l[i + 3] - l[i + 1]) * j / n; barbBoxes.push([X - 1.5 * Z, Y - 1.5 * Z, X + 1.5 * Z, Y + 1.5 * Z]); }
        }
      }
      rs.push(...barbBoxes);
      // numbers sit LEFT of the station point (temp over gust); if the barb points left, slide them
      // below or above it, and only as a last resort put them on the right
      const lab = numbers(g, L, R, px, py, barbBoxes, bg && bg.calm, !bg);
      if (lab) rs.push(...lab.rects); else if (L.length || R.length) return;
      const prs = rs.map((r) => pad(r, M));
      if (!B.fits(prs)) return;
      B.add(prs); S.placed.push({ s, px, py, bg, lab });
    };
    const inside = list.filter((s) => { const px = sx(s.x), py = sy(s.y); return px >= 0 && py >= 0 && px <= S.w && py <= S.h; });
    inView = inside.length;
    inside.forEach(tryStation);
    // a town hidden under its own airport's plot (e.g. Port Hardy) gets its name written just below that plot instead
    const named = (c) => {
      const key = c.name.toLowerCase();
      const p = S.placed.find((q) => q.s.kind === 0 && q.s.name.toLowerCase().startsWith(key) && Math.hypot(q.px - sx(c.x), q.py - sy(c.y)) < 30 * S.k + 40);
      if (!p) return false;
      g.font = c.town ? TOWN_FONT : CITY_FONT;
      const tw = g.measureText(c.name).width, bottom = Math.max(p.py + 6 * Z, ...(p.lab ? p.lab.rects.map((r) => r[3]) : [0]));
      const left = Math.min(p.px - 6 * Z, ...(p.lab ? p.lab.rects.map((r) => r[0]) : [p.px])), top = Math.min(p.py - 6 * Z, ...(p.lab ? p.lab.rects.map((r) => r[1]) : [p.py]));
      const b2 = bottom + M + 10, t2 = top - M - 10;   // plot rectangles were reserved with M padding
      for (const [tx, ty] of [[p.px, b2], [p.px - 20, b2], [p.px + 20, b2], [p.px, t2], [left - M - 4 - tw / 2, p.py]]) {
        const r = [tx - tw / 2, ty - 7, tx + tw / 2, ty + 7];
        if (B.fits([pad(r, 2)])) { B.add([pad(r, 2)]); S.cities.push({ c, x: null, y: null, tx, ty, al: "center" }); return true; }
      }
      return false;
    };
    S.namedTry = named;
    S.nView = inView; S.nShown = S.placed.length;

    // remaining cities, then faint state/province names (full names when zoomed in, abbreviations when zoomed out)
    g.font = CITY_FONT;
    cities.filter((c) => c.rank > pinRank).forEach(placeCity);
    // GeoNames small towns: biggest first, smaller ones only as you zoom in
    const minPop = S.k < 0.45 ? Infinity : S.k < 0.9 ? 25000 : S.k < 1.5 ? 4000 : S.k < 3 ? 0 : -1;
    let room = Math.round(S.w * S.h / 24000);        // cap on town labels per screen so the map stays readable
    if (minPop !== Infinity) { g.font = TOWN_FONT; for (const t of PP.towns) { if (t.pop < minPop || room <= 0) break; if (placeCity(t)) room--; } }
    const big = S.k > 0.32;
    g.font = big ? "600 15px 'Outfit', system-ui, sans-serif" : "600 13px 'Outfit', system-ui, sans-serif";
    for (const r of PP.regions) {
      const label = big ? r.name.toUpperCase() : r.abbr, w = g.measureText(label).width * (big ? 1.12 : 1.1);
      for (const dy of [0, -36, 36, -72, 72]) {
        const x = sx(r.x), y = sy(r.y) + dy, rr = [x - w / 2, y - 9, x + w / 2, y + 9];
        if (B.fits([rr])) { B.add([rr]); S.regionsShown.push({ label, x, y, big }); break; }
      }
    }
  }

  function paint(g) {
    g.lineJoin = "round"; g.lineCap = "round"; g.textBaseline = "middle"; g.textAlign = "center";
    for (const r of S.regionsShown) {
      g.font = r.big ? "600 15px 'Outfit', system-ui, sans-serif" : "600 13px 'Outfit', system-ui, sans-serif";
      if ("letterSpacing" in g) g.letterSpacing = r.big ? "2px" : "1px";
      g.fillStyle = C.region; g.fillText(r.label, r.x, r.y);
    }
    if ("letterSpacing" in g) g.letterSpacing = "0px";
    for (const { c, x, y, tx, ty, al } of S.cities) {
      const r = c.town ? 1.8 : 2.5;
      g.font = c.town ? TOWN_FONT : CITY_FONT;
      g.fillStyle = c.town ? C.townDot : C.cityDot; g.strokeStyle = C.halo; g.lineWidth = 1.5;
      if (x != null) { g.beginPath(); g.rect(x - r, y - r, 2 * r, 2 * r); g.fill(); g.stroke(); }
      g.textAlign = al; g.lineWidth = 3; g.strokeText(c.name, tx, ty); g.fillStyle = c.town ? C.town : C.city; g.fillText(c.name, tx, ty);
    }
    if (S.isoLabels && S.isoLabels.length) {
      g.font = ISO_FONT; g.textAlign = "center"; g.textBaseline = "middle"; g.lineWidth = 3.5; g.strokeStyle = C.halo;
      for (const l of S.isoLabels) { g.strokeText(l.txt, l.x, l.y); g.fillStyle = KC.mslp; g.fillText(l.txt, l.x, l.y); }
    }
    for (const p of S.placed) drawBarb(g, p);
    // numbers: dark outline plus a soft drop shadow (both carry into the downloaded image)
    g.lineJoin = "round"; g.textBaseline = "alphabetic"; g.textAlign = "left";
    for (const { s, lab } of S.placed) {
      if (!lab) continue;
      for (const it of lab.items) {
        g.font = it.font; g.fillStyle = it.kind === "t" ? tempColor(s.t) : KC[it.kind] || C.gust;
        g.shadowColor = "rgba(0,0,0,.85)"; g.shadowBlur = 3 * Z * NF; g.shadowOffsetX = Z * NF; g.shadowOffsetY = 1.2 * Z * NF;
        g.lineWidth = (it.font === FONT_S ? 2.6 : 3) * Z * NF; g.strokeStyle = C.halo; g.strokeText(it.text, it.x, it.y);
        g.shadowColor = "transparent"; g.fillText(it.text, it.x, it.y);
      }
    }
    g.shadowColor = "transparent"; g.shadowBlur = 0; g.shadowOffsetX = 0; g.shadowOffsetY = 0;
  }

  // lay out the number columns beside a station point: left column (temperatures, current gust) prefers the LEFT and the
  // right column (pressure, feels-like, peak gust) prefers the RIGHT; each slides below/above a barb in its way and only as a
  // last resort swaps sides. Returns draw items and the rectangles they cover, or null if there is no room.
  // With only the station plot on this is exactly the original layout (temp over gust, left of the station point).
  // bare = nothing else marks the station (no barb, no calm ring): a lone column is then centred on the station point.
  function numbers(g, L, R, px, py, avoid, calm, bare) {
    if (!L.length && !R.length) return null;
    const small = L.length + R.length > 2, font = small ? FONT_S : FONT;
    const asc = (small ? 8.8 : 10) * Z * NF, gap = 2 * Z * NF, off = (calm ? 8.5 : 4.5) * Z;   // no station dot, so the numbers sit close (just outside a calm ring)
    g.font = font;
    const hits = (rects, others) => rects.some((r) => others.some((o) => r[0] < o[2] && r[2] > o[0] && r[1] < o[3] && r[3] > o[1]));
    const lone = bare && (!L.length || !R.length);
    const column = (lines, pref, others) => {
      if (!lines.length) return { items: [], rects: [] };
      for (const ln of lines) ln.tw = g.measureText(ln.txt).width;
      const H = lines.length * asc + (lines.length - 1) * gap, sgn = pref === "r" ? -1 : 1, flip = pref === "r" ? "l" : "r";
      const cands = [[px + sgn * off, py - H / 2, pref], [px + sgn * off, py + 3 * Z, pref], [px + sgn * off, py - H - 3 * Z, pref],
        [px + sgn * off, py + 10 * Z, pref], [px + sgn * off, py - H - 10 * Z, pref], [px - sgn * off, py - H / 2, flip]];
      if (lone) cands.unshift([px, py - H / 2, "c"]);
      for (const [ax, top, side] of cands) {
        const items = [], rects = [];
        lines.forEach((ln, i) => {
          const base = top + asc + i * (asc + gap), x0 = side === "r" ? ax - ln.tw : side === "c" ? ax - ln.tw / 2 : ax;
          items.push({ text: ln.txt, x: x0, y: base, font, kind: ln.kind });
          rects.push([x0 - 1, base - asc - 1, x0 + ln.tw + 1, base + 2]);
        });
        if (!hits(rects, others)) return { items, rects };
      }
      return null;
    };
    const a = column(L, "r", avoid); if (!a) return null;
    const b = column(R, "l", [...avoid, ...a.rects, [px - 3 * Z, py - 3 * Z, px + 3 * Z, py + 3 * Z]]); if (!b) return null;
    return { items: [...a.items, ...b.items], rects: [...a.rects, ...b.rects] };
  }

  function drawBarb(g, { s, px, py, bg }) {
    if (bg) {
      g.strokeStyle = C.halo; g.lineWidth = 3.2 * Z;           // dark casing keeps barbs readable over borders and coast
      g.beginPath(); for (const [a, b, c2, d2] of bg.lines) { g.moveTo(a, b); g.lineTo(c2, d2); } g.stroke();
      g.strokeStyle = C.barb; g.lineWidth = 1.4 * Z;
      g.beginPath(); for (const [a, b, c2, d2] of bg.lines) { g.moveTo(a, b); g.lineTo(c2, d2); } g.stroke();
      g.fillStyle = C.barb; for (const f of bg.flags) { g.beginPath(); g.moveTo(f[0], f[1]); g.lineTo(f[2], f[3]); g.lineTo(f[4], f[5]); g.closePath(); g.fill(); }
    }
    // no station dot (owner's call); a calm-wind ring keeps its dark casing so it reads like the barbs
    if (bg && bg.calm) {
      g.strokeStyle = C.halo; g.lineWidth = 3 * Z; g.beginPath(); g.arc(px, py, 6 * Z, 0, 7); g.stroke();
      g.strokeStyle = C.barb; g.lineWidth = 1.4 * Z; g.beginPath(); g.arc(px, py, 6 * Z, 0, 7); g.stroke();
    }
  }

  /* ---- status / tooltip ---- */
  const tfmt = new Intl.DateTimeFormat("en-US", { timeZone: "America/Los_Angeles", hour: "numeric", minute: "2-digit" });
  function status(msg) {
    const el = $("obs-status"), cap = $("ocap-right");
    if (msg) { el.textContent = msg; return; }
    if (!S.counts) return;
    const c = S.counts;
    cap.textContent = `Updated ${tfmt.format(new Date(S.loaded))} PT · US ${c.us} · Canada ${c.ca} stations`;
    const notes = [];
    if (!S.on.size) notes.push("no layer selected");
    if (S.on.has("feel")) notes.push("wind chill / heat index only where they apply");
    if (needDay() && S.dayCAloading) notes.push("loading today's Canadian highs/lows…");
    if (needDay() && S.dayCAstate === "failed") notes.push("Canada daily values unavailable");
    el.textContent = `Showing ${S.nShown} of ${S.nView} stations in view${S.nShown < S.nView ? " — zoom in for more" : ""}` +
      (notes.length ? " · " + notes.join(" · ") : "") + (c.fails.length ? ` · unavailable: ${c.fails.join(", ")}` : "");
  }
  function pick(px, py) {
    let best = null, bd = 20 * Z;
    for (const p of S.placed) { const d = Math.hypot(p.px - px, p.py - py); if (d < bd) { bd = d; best = p; } }
    return best;
  }
  function showTip(p) {
    const s = p.s, tip = $("obs-tip"), age = Math.round((Date.now() - s.time) / 60e3);
    const dirs = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE", "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"];
    const wind = s.ws == null ? "—" : s.ws < 2.5 ? "calm" : `${s.wd == null ? "" : dirs[Math.round(s.wd / 22.5) % 16] + " "}${Math.round(s.ws * 1.150779)} mph (${Math.round(s.ws)} kt)`;
    tip.replaceChildren();
    const line = (b, t) => { const d = document.createElement("div"); if (b) { const e = document.createElement("b"); e.textContent = b; d.append(e, " "); } d.append(t); tip.append(d); };
    line(s.name, s.code && s.code !== s.name ? `(${s.code})` : "");
    line("", `${s.src} · ${tfmt.format(new Date(s.time))} PT (${age} min ago)`);
    line("Temp", s.t == null ? "—" : `${Math.round(s.t)}°F / ${((s.t - 32) * 5 / 9).toFixed(1)}°C`);
    line("Wind", wind);
    line("Gust", s.g == null ? "—" : `${Math.round(s.g)} mph`);
    const at = (ts) => (ts && ts.length >= 16 ? ` at ${new Date(ts + "Z").toLocaleTimeString("en-US", { timeZone: "UTC", hour: "numeric", minute: "2-digit" })} local` : "");
    const dayTxt = s.day ? ` (since midnight ${s.day.slice(5).replace("-", "/")}, ${s.daySrc})` : "";
    line("High today", s.hi == null ? "—" : `${Math.round(s.hi)}°F`);
    line("Low today", s.lo == null ? "—" : `${Math.round(s.lo)}°F${dayTxt}`);
    if (s.pkKind === "sustained") line("Peak gust today", s.pk == null ? "—" : `none reported (max sustained ${Math.round(s.pk)} mph${at(s.pkAt)})`);
    else line("Peak gust today", s.pk == null ? "—" : `${Math.round(s.pk)} mph${at(s.pkAt)}`);
    line(s.flk === "hx" ? "Heat index" : "Wind chill", s.fl == null ? "— (not applicable)" : `${Math.round(s.fl)}°F`);
    line("MSLP", s.p == null ? "—" : `${s.p.toFixed(1)} hPa`);
    if (s.qc.length) line("Checked", s.qc.join("; ") + " (hidden)");
    tip.hidden = false;
    const r = tip.getBoundingClientRect();
    tip.style.left = Math.min(Math.max(4, p.px + 12), S.w - r.width - 4) + "px";
    tip.style.top = Math.min(Math.max(4, p.py + 12), S.h - r.height - 4) + "px";
  }
  function hideTip() { const t = $("obs-tip"); if (t) t.hidden = true; }

  /* ---- input: wheel, drag, pinch, buttons, keys ---- */
  function wire() {
    const c = $("obs-canvas"), ptr = new Map();
    let moved = 0, pinch = null;
    c.addEventListener("wheel", (e) => { e.preventDefault(); const r = c.getBoundingClientRect();
      zoomAt(Math.exp(-(e.deltaMode ? e.deltaY * 33 : e.deltaY) * 0.0018), e.clientX - r.left, e.clientY - r.top); }, { passive: false });
    c.addEventListener("pointerdown", (e) => { c.setPointerCapture(e.pointerId); ptr.set(e.pointerId, [e.clientX, e.clientY]); moved = 0; c.classList.add("drag");
      if (ptr.size === 2) { const [a, b] = [...ptr.values()]; pinch = Math.hypot(a[0] - b[0], a[1] - b[1]); } });
    c.addEventListener("pointermove", (e) => {
      if (!ptr.has(e.pointerId)) return;
      const prev = ptr.get(e.pointerId), r = c.getBoundingClientRect();
      if (ptr.size === 1) { const dx = e.clientX - prev[0], dy = e.clientY - prev[1]; moved += Math.abs(dx) + Math.abs(dy);
        S.cx -= dx / S.k; S.cy -= dy / S.k; if (moved > 3) { S.view = ""; hideTip(); } req(); }
      ptr.set(e.pointerId, [e.clientX, e.clientY]);
      if (ptr.size === 2 && pinch) { const [a, b] = [...ptr.values()], d = Math.hypot(a[0] - b[0], a[1] - b[1]); moved += 10;
        zoomAt(d / pinch, (a[0] + b[0]) / 2 - r.left, (a[1] + b[1]) / 2 - r.top); pinch = d; }
    });
    const up = (e) => { if (!ptr.has(e.pointerId)) return; ptr.delete(e.pointerId); if (ptr.size < 2) pinch = null;
      if (!ptr.size) { c.classList.remove("drag"); if (moved < 6 && e.type === "pointerup") { const r = c.getBoundingClientRect(), p = pick(e.clientX - r.left, e.clientY - r.top); p ? showTip(p) : hideTip(); } else if (moved >= 6) writeHashSafe(); } };
    c.addEventListener("pointerup", up); c.addEventListener("pointercancel", up);
    c.addEventListener("dblclick", (e) => { const r = c.getBoundingClientRect(); zoomAt(2, e.clientX - r.left, e.clientY - r.top); });
    $("obs-in").onclick = () => zoomAt(1.6, S.w / 2, S.h / 2);
    $("obs-out").onclick = () => zoomAt(1 / 1.6, S.w / 2, S.h / 2);
    $("obs-refresh").onclick = () => load();
    $("dl-obs").onclick = (e) => { e.preventDefault(); download(); };
    const box = $("oviews");
    for (const v of VIEWS) { const b = document.createElement("button"); b.type = "button"; b.dataset.v = v.id; b.textContent = v.label;
      b.onclick = () => { S.view = v.id; S.pending = v; applyView(); hideTip(); draw(); renderViews(); writeHashSafe(); }; box.append(b); }
    const lb = $("olayers");
    for (const l of LAYERS) {
      const b = document.createElement("button"); b.type = "button"; b.dataset.l = l.id; b.title = LAYER_HELP[l.id];
      const sw = document.createElement("span"); sw.className = "obs-sw";
      const n1 = document.createElement("span"); n1.textContent = l.sample; n1.style.color = l.sw; sw.append(n1);
      if (l.sw2) { const n2 = document.createElement("span"); n2.textContent = "97"; n2.style.color = l.sw2; sw.append(" ", n2); }
      if (l.id === "plot") { const n2 = document.createElement("span"); n2.textContent = "25"; n2.style.color = KC.g; sw.append(" ", n2); }
      b.append(sw, " " + l.label);
      b.onclick = () => setLayers([...(S.on.has(l.id) ? [...S.on].filter((x) => x !== l.id) : [...S.on, l.id])], true);
      lb.append(b);
    }
    new ResizeObserver(() => { if (S.shown && resize()) draw(); }).observe($("ostage"));
    document.addEventListener("visibilitychange", () => { if (!document.hidden && S.shown && Date.now() - S.loaded > REFRESH_MS) load(); });
  }
  function renderViews() {
    for (const b of $("oviews").querySelectorAll("button")) b.setAttribute("aria-pressed", String(b.dataset.v === S.view));
    for (const b of $("olayers").querySelectorAll("button")) b.setAttribute("aria-pressed", String(S.on.has(b.dataset.l)));
  }
  const LAYER_HELP = {
    plot: "Current temperature (°F), gust (mph) and wind barb (kt)",
    hi: "Today's high temperature (°F) since local midnight",
    lo: "Today's low temperature (°F) since local midnight",
    pk: "Today's peak gust (mph) since local midnight",
    feel: "Wind chill (purple, 50°F or colder with wind over 3 mph) or heat index (orange, 80°F or warmer), NWS formulas",
    mslp: "Sea-level pressure (hPa) at each station, with isobars every 4 hPa (2 hPa zoomed in)",
  };
  function setLayers(ids, user) {   // ids: array or comma string; unknown ids ignored
    const list = (Array.isArray(ids) ? ids : String(ids || "").split(",")).map((x) => x.trim()).filter((x) => LAYER_IDS.includes(x));
    S.on = new Set(LAYER_IDS.filter((x) => list.includes(x)));
    if (user) try { localStorage.setItem("obsLayers", [...S.on].join(",")); } catch (e) { /* private mode */ }
    if (!S.inited) return;
    renderViews(); hideTip();
    if (needDay() && S.raw.length && !S.dayCAloaded) loadDayCA();
    draw();
  }
  const layers = () => [...S.on];
  function writeHashSafe() { renderViews(); if (S.onChange) S.onChange(S.view); }

  function download() {
    const c = $("obs-canvas"), stamp = new Intl.DateTimeFormat("en-CA", { timeZone: "America/Los_Angeles", year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", hourCycle: "h23" })
      .format(new Date(S.loaded || Date.now())).replace(/[^0-9]/g, "");
    // flatten with a credit strip so the saved image carries its sources
    const o = document.createElement("canvas"), d = S.dpr, strip = Math.round(22 * d);
    o.width = c.width; o.height = c.height + strip;
    const g = o.getContext("2d"); g.drawImage(c, 0, 0); g.fillStyle = "#1b2531"; g.fillRect(0, c.height, o.width, strip);
    g.fillStyle = "#c9d3dd"; g.font = `${Math.round(11 * d)}px 'IBM Plex Mono', monospace`; g.textBaseline = "middle";
    const names = LAYERS.filter((l) => S.on.has(l.id)).map((l) => l.label).join(", ") || "none";
    const daily = needDay() ? " (today = since local midnight)" : "";
    g.fillText(`Observed ${tfmt.format(new Date(S.loaded))} PT · ${names}${daily} · Data: ECCC (OGL-Canada), NOAA/NWS via IEM · Natural Earth · GeoNames (CC BY 4.0)`, 8 * d, c.height + strip / 2);
    o.toBlob((b) => { const a = document.createElement("a"); a.href = URL.createObjectURL(b);
      const lt = [...S.on].join("-"), tag = lt === "plot" ? "" : "_" + (lt || "none");
      a.download = `obs_${S.view || "custom"}${tag}_${stamp.slice(0, 8)}_${stamp.slice(8, 12)}PT.png`; document.body.append(a); a.click(); a.remove();
      setTimeout(() => URL.revokeObjectURL(a.href), 4000); }, "image/png");
  }

  function mount(el, opts = {}) {
    el = typeof el === "string" ? document.querySelector(el) : el;
    el.classList.add("obs-root");
    el.innerHTML = `
      <div class="obs-bar" id="oviews" role="group" aria-label="Map view"></div>
      <div class="obs-bar obs-layers" id="olayers" role="group" aria-label="Layers (tap to turn on or off)"></div>
      <div class="obs-cap"><span>Latest observations</span><span id="ocap-right"></span></div>
      <div class="obs-stage" id="ostage">
        <canvas id="obs-canvas" aria-label="Map of current weather station observations"></canvas>
        <div class="obs-zoom"><button type="button" id="obs-in" aria-label="Zoom in">+</button><button type="button" id="obs-out" aria-label="Zoom out">&minus;</button></div>
        <div class="obs-tip" id="obs-tip" hidden></div>
        <div class="loader" id="obs-loader" hidden>Loading stations…</div>
      </div>
      <div class="obs-foot"><button type="button" class="obs-dl" id="dl-obs">Download image</button><button type="button" class="obs-dl" id="obs-refresh">Refresh</button><span id="obs-status"></span></div>
      <p class="obs-hint">Scroll or pinch to zoom, drag to pan, tap a station for details. Turn layers on and off with the buttons above the map; they combine, and the sample number on each button is its colour on the map. Temperatures (high, current, low) and the current gust sit left of each station, pressure, wind chill / heat index and peak gust sit right of it. Each wind barb starts at the station's location, a ring means calm wind, and a station with no wind report has its numbers centred on it. More stations appear as you zoom in; airports and official stations are shown first. Updates every 10 minutes.</p>
      <p class="obs-credit">Observations: latest report in the past 90 minutes, checked against nearby stations. High, low and peak gust are for today since local midnight at each station: US values are the Iowa Environmental Mesonet daily summary for the station's own local day, Canadian values are built from the hourly reports since local midnight. Peak gust is the highest reported gust (US) or highest hourly peak wind (Canada); a station that reported no gust today shows none. Wind chill and heat index use the NWS formulas on the current reading. MSLP isobars are an automatic analysis of the station values, drawn only where stations are close enough. Canada: Environment and Climate Change Canada, MSC surface weather observations (SWOB). Contains information licensed under the <a href="https://open.canada.ca/en/open-government-licence-canada">Open Government Licence &ndash; Canada</a>. United States: NOAA/NWS ASOS and AWOS stations via the <a href="https://mesonet.agron.iastate.edu/">Iowa Environmental Mesonet</a>. Basemap: Natural Earth (public domain). Town names: <a href="https://www.geonames.org/">GeoNames</a>, licensed under <a href="https://creativecommons.org/licenses/by/4.0/">CC BY 4.0</a>.</p>`;
    S.root = el; S.onChange = opts.onChange || null; wire(); S.inited = true;
  }
  function hide() { S.shown = false; hideTip(); }

  async function show() {
    S.shown = true;
    if (!S.inited) {
      const q = new URLSearchParams(location.hash.slice(1)); let saved = null;
      try { saved = localStorage.getItem("obsLayers"); } catch (e) { /* private mode */ }
      setLayers(q.get("l") != null ? q.get("l") : saved != null ? saved : "plot");
      mount("#obs-root", { onChange: typeof writeHash === "function" ? () => writeHash() : null });
    }
    renderViews();
    requestAnimationFrame(async () => {
      resize();
      try { if (!S.base) await loadBase(); } catch (e) { status("Basemap could not be loaded"); return; }
      draw();
      if (!S.loaded || Date.now() - S.loaded > REFRESH_MS) load();
    });
    clearInterval(S.timer); S.timer = setInterval(() => { if (S.shown && !document.hidden) load(); }, REFRESH_MS);
  }

  // test hook: draw one barb (true-north frame) for a given direction/speed, used by qa/qa_obs.py to check the convention
  function _testBarb(canvas, wd, kt) {
    const g = canvas.getContext("2d"), keep = S.P; S.P = { n: 0, L0: 0 };
    const p = { s: { wd, ws: kt, lon: 0, kind: 0 }, px: canvas.width / 2, py: canvas.height / 2 }; p.bg = barbGeom(p.s, p.px, p.py);
    g.fillStyle = C.land; g.fillRect(0, 0, canvas.width, canvas.height); drawBarb(g, p); S.P = keep;
  }
  return { mount, show, hide, setView, viewId, load, setLayers, layers, _state: S, _testBarb };
})();
