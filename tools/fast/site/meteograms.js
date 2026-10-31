// Meteograms page (fast site, 10-30-26). Same page and same charts as the old site's Meteograms tab (Model chips, Town, Product,
// one full-width chart image, Download image), but every chart is drawn here in the browser from small per-step JSON in R2:
//   runs/<model>/<cycle>/single/pts_fFFF.json  deterministic / ensemble-mean values at every town and pass (order = run.json points)
//   runs/<model>/<cycle>/single/mem_fFFF.json  ensemble members at 47 places (EPS / AIFS ENS runs encoded after 10-30 evening)
// Chart look = the old matplotlib / PIL charts (tools/forecast/meteo_suite.py, member_grid.py, snow_ens.py): same pixel sizes,
// fonts, colours, titles, legends and axes, drawn on a canvas and shown as an <img> (right-click Save image as works).
// One change asked for by Benjamin (10-30): stacked charts get their own time axis under every panel.
"use strict";
const DATA = window.WX_DATA || "data/";
const $ = (id) => document.getElementById(id);
const PTZ = "America/Los_Angeles";
const FMT = {}; const fmt = (o) => FMT[JSON.stringify(o)] || (FMT[JSON.stringify(o)] = new Intl.DateTimeFormat("en-US", Object.assign({ timeZone: PTZ }, o)));
const ptHour = (ms) => +fmt({ hour: "numeric", hourCycle: "h23" }).format(ms) % 24;
const ptDate = (ms) => fmt({ year: "numeric", month: "2-digit", day: "2-digit" }).format(ms);
const dayLab = (ms) => fmt({ weekday: "short", month: "numeric", day: "numeric" }).format(ms).replace(",", "");     // Sat 10/24
const hourLab = (ms) => fmt({ hour: "numeric" }).format(ms);                                                        // 5 PM
const S = { man: null, sec: "", town: "", prod: "", tok: 0 };

/* ---------------- products (old site order and ids, so old links map 1:1) ---------------- */
const NA_XSEC = "Needs model levels at each town (vertical profiles). The fast data stores surface and single-level fields only, so this chart is not drawn yet.";
const NA_SMOKE = "Smoke is not in the fast data yet.";
const det = (m) => [
  [`${m}_surface_summary`, "Surface Summary", "summary"],
  [`${m}_smoke_xsec_low`, "Low Level Smoke X-Sec", null, m === "rrfs" ? "Operational RRFS has no smoke on levels (not in free data)." : NA_SMOKE],
  [`${m}_multirun_t2m`, "Multi-run 2m Temperature", "mr_t2m"],
  [`${m}_multirun_qpf6`, "Multi-run 6-Hour QPF", "mr_qpf6"],
  [`${m}_multirun_snow6`, "Multi-run 6-Hour Snow", "mr_snow6"],
  [`${m}_multirun_qpf`, "Multi-run Total QPF", "mr_qpf"],
  [`${m}_multirun_snow`, "Multi-run Total Snow", "mr_snow"],
  [`${m}_smoke_xsec`, "Smoke X-Sec", null, m === "rrfs" ? "Operational RRFS has no smoke on levels (not in free data)." : NA_SMOKE],
  ...(m === "rrfs" ? [[`rrfs_smoke_sfc`, "Near-Surface Smoke", null, NA_SMOKE]] : []),
  [`${m}_winter_summary`, "Winter Weather Summary", "winter"],
  [`${m}_winter_thermal`, "Winter Thermal Environment", null, NA_XSEC],
  [`${m}_temp_xsec`, "Temp X-Sec", null, NA_XSEC],
  [`${m}_temp_xsec_low`, "Low Level Temp X-Sec", null, NA_XSEC],
  [`${m}_rh_xsec`, "Rel. Humidity X-Sec", null, NA_XSEC],
];
const ens = (m) => [
  [`${m}_daily_hilo`, "Daily High/Low Temp", "hilo"],
  [`${m}_qpf_plume`, "Total QPF Plume", "plume_tp"],
  [`${m}_snow_plume`, "Total Snow Plume", "plume_sf"],
  [`${m}_spread_maxmin`, "Spread: Max/Min Temp", "spread_mx"],
  [`${m}_tmax_members`, "Member View & Mean: Max Temp", "grid_mx"],
  [`${m}_tmin_members`, "Member View & Mean: Min Temp", "grid_mn"],
  [`${m}_t2m_members`, "Member View & Mean: 2m Temp", "lines_t2m"],
  [`${m}_qpf24_members`, "Member View & Mean: 24-Hour QPF", "grid_tp24"],
  [`${m}_qpf_members`, "Member View & Mean: Total QPF", "grid_tp"],
  [`${m}_snow24_members`, "Member View & Mean: 24-Hour Snow", "lines_sf24"],
  [`${m}_snow_members`, "Member View & Mean: Total Snow", "snowens"],
  [`${m}_tcc_members`, "Member View & Mean: Cloud Cover", "lines_tcc"],
  [`${m}_gust_members`, "Member View & Mean: 6-hr Max Gust", "grid_gust"],
  [`${m}_mucape_members`, "Member View & Mean: MUCAPE", "lines_cape"],
  [`${m}_pwat_members`, "Member View & Mean: PWAT", "lines_pwat"],
  [`${m}_mr_t2m`, "Multi-run: 2m Temperature", "mr_t2m"],
  [`${m}_mr_tmax6`, "Multi-run: 6-h Max Temperature", "mr_tmax"],
  [`${m}_mr_tmin6`, "Multi-run: 6-h Min Temperature", "mr_tmin"],
  [`${m}_mr_qpf6`, "Multi-run: 6-Hour QPF", "mr_qpf6"],
  [`${m}_mr_snow6`, "Multi-run: 6-Hour Snow", "mr_snow6"],
  [`${m}_mr_qpf24`, "Multi-run: 24-Hour QPF", "mr_qpf24"],
  [`${m}_mr_snow24`, "Multi-run: 24-Hour Snow", "mr_snow24"],
  [`${m}_mr_qpf`, "Multi-run: Total QPF", "mr_qpf"],
  [`${m}_mr_snow`, "Multi-run: Total Snow", "mr_snow"],
  [`${m}_spread_qpf`, "Spread: Total QPF", "spread_tp"],
  [`${m}_z500_t850`, "500hPa Height and 850hPa Temp", "z500t850"],
];
const glob = (m) => [
  [`${m}_surface_summary`, "Surface Summary", "summary"],
  [`${m}_multirun_t2m`, "Multi-run 2m Temperature", "mr_t2m"],
  [`${m}_multirun_qpf6`, "Multi-run 6-Hour QPF", "mr_qpf6"],
  [`${m}_multirun_qpf24`, "Multi-run 24-Hour QPF", "mr_qpf24"],
  [`${m}_multirun_qpf`, "Multi-run Total QPF", "mr_qpf"],
  [`${m}_multirun_snow`, "Multi-run Total Snow", "mr_snow"],
  [`${m}_winter_summary`, "Winter Weather Summary", "winter"],
];
const ECMWF_CREDIT = "Source: ECMWF open data, CC BY 4.0. Modified. \u00a9 ECMWF, www.ecmwf.int";
// tag = old chart title tag / caption tag; rl = old run-line model name
const SECTIONS = [   // the old page's three models first, then the fast site's extra models
  { id: "eps", label: "ECMWF EPS", tag: "EPS", rl: "ECMWF ENS 0.25\u00b0, 50 members", credit: ECMWF_CREDIT, products: ens("eps") },
  { id: "hrrr", label: "HRRR", tag: "HRRR", rl: "HRRR 3 km", credit: "Data: NOAA HRRR (public domain)", products: det("hrrr"), hrs: 48 },
  { id: "rrfs", label: "RRFS", tag: "RRFS", rl: "RRFS 3 km", credit: "Data: NOAA RRFS (public domain)", products: det("rrfs"), hrs: 60 },
  { id: "nbm", label: "NBM", tag: "NBM", rl: "NBM 2.5 km", extra: true, credit: "Data: NOAA National Blend of Models (public domain)", products: glob("nbm").filter((p) => !/qpf24|snow$/.test(p[0]) || p[0].endsWith("_snow")) },
  { id: "gfs", label: "GFS", tag: "GFS", rl: "GFS 0.25\u00b0", extra: true, credit: "Data: NOAA GFS (public domain)", products: glob("gfs") },
  { id: "ifs", label: "ECMWF", tag: "ECMWF", rl: "ECMWF IFS 0.25\u00b0", extra: true, credit: ECMWF_CREDIT, products: glob("ifs") },
  { id: "aifs", label: "AIFS", tag: "AIFS", rl: "ECMWF AIFS 0.25\u00b0", extra: true, credit: ECMWF_CREDIT, products: glob("aifs") },
  { id: "aens", label: "AIFS ENS", tag: "AIFS ENS", rl: "AIFS ENS 0.25\u00b0, 50 members", extra: true, credit: ECMWF_CREDIT, products: ens("aens") },
].map((s) => Object.assign(s, { products: s.products.map(([id, label, kind, note]) => ({ id, label, kind, note })) }));
const secObj = () => SECTIONS.find((s) => s.id === S.sec);
const ENS = (m) => m === "eps" || m === "aens";
const ENS_HOURS = 240, SNOW_HOURS = 360;   // old EPS charts: 0-240 h, snow-total member chart to 360 h

/* ---------------- towns: the old site's 22 towns (old ids and labels), then more places ---------------- */
const OLD_TOWNS = [["seattle", "Seattle (SeaTac)", "Seattle"], ["tacoma", "Tacoma (Narrows)", "Tacoma"], ["everett", "Everett (Paine Field)", "Everett"],
  ["arlington", "Arlington", "Arlington"], ["bellingham", "Bellingham", "Bellingham"], ["olympia", "Olympia", "Olympia"],
  ["vancouver", "Vancouver WA (Pearson)", "Portland"], ["portangeles", "Port Angeles", "Port Angeles"], ["forks", "Forks (Quillayute)", "Forks"],
  ["aberdeen", "Aberdeen (Hoquiam)", "Aberdeen"], ["oceanshores", "Ocean Shores", "Ocean Shores"], ["spokane", "Spokane", "Spokane"],
  ["yakima", "Yakima", "Yakima"], ["wenatchee", "Wenatchee (Pangborn)", "Wenatchee"], ["kennewick", "Tri-Cities (Pasco)", "Tri-Cities"],
  ["wallawalla", "Walla Walla", "Walla Walla"], ["moseslake", "Moses Lake", "Moses Lake"], ["ellensburg", "Ellensburg", "Ellensburg"],
  ["pullman", "Pullman", "Pullman"], ["omak", "Omak", "Omak"], ["snoqualmie", "Snoqualmie Pass", "Snoqualmie"], ["stevens", "Stevens Pass", "Stevens"]];
// places with ensemble members (fast_encode.MEM_POINTS); Portland = Vancouver WA
const MEM_POINTS = ["Seattle", "Tacoma", "Everett", "Arlington", "Bellingham", "Olympia", "Portland", "Port Angeles", "Forks", "Aberdeen",
  "Ocean Shores", "Spokane", "Yakima", "Wenatchee", "Tri-Cities", "Walla Walla", "Moses Lake", "Ellensburg", "Pullman", "Omak",
  "Bellevue", "Granite Falls", "Mount Vernon", "Leavenworth", "North Bend", "Enumclaw", "Longview", "Centralia", "Port Townsend",
  "Sequim", "Chelan", "Winthrop", "Colville", "Packwood", "Skykomish", "Goldendale", "Shelton", "Monroe",
  "Snoqualmie", "Stevens", "White", "Blewett", "Chinook", "Satus", "Sherman", "Wauconda", "Disautel"];
const placeLabel = (p) => (p.k === "pass" ? `${p.n} Pass` : p.n);
function townList(sec, pts) {   // [{id, label, pt, old}]
  const byN = new Map(pts.map((p) => [p.n, p])), out = [], used = new Set();
  for (const [id, label, n] of OLD_TOWNS) { const p = byN.get(n); if (p) { out.push({ id, label, pt: p, old: true }); if (n !== "Portland") used.add(n); } }
  out.sort((a, b) => a.label.localeCompare(b.label));
  const more = pts.filter((p) => !used.has(p.n) && (!ENS(sec.id) || MEM_POINTS.includes(p.n))).map((p) => ({ id: p.n, label: placeLabel(p), pt: p, old: false }));
  more.sort((a, b) => a.label.localeCompare(b.label));
  return out.concat(more);
}

/* ---------------- data ---------------- */
const CACHE = new Map();
const getJSON = (u, nc) => fetch(u, nc ? { cache: "no-cache" } : {}).then((r) => { if (!r.ok) throw new Error(r.status); return r.json(); });
function memo(k, fn) { if (!CACHE.has(k)) CACHE.set(k, fn().catch((e) => { CACHE.delete(k); throw e; })); return CACHE.get(k); }
// newest first: map runs + older "slim" runs that keep only their town files (manifest.mgruns, up to 4 per model)
const runsOf = (m) => [...new Set([...((S.man && S.man.runs[m]) || []), ...((S.man && S.man.mgruns && S.man.mgruns[m]) || [])])].sort().reverse();
const loadRun = (m, c) => memo(`run/${m}/${c}`, () => getJSON(`${DATA}runs/${m}/${c}/run.json`, true));
async function perStep(m, c, name, maxF) {   // [{f, valid, d}] for steps whose file exists
  const R = await loadRun(m, c), st = (R.steps || []).filter((s) => maxF == null || s.f <= maxF), out = new Array(st.length); let k = 0;
  if ((R.agg || []).includes(name)) try {   // complete runs: one aggregated file ({name}_all.json) instead of ~50
    const A = await getJSON(`${DATA}runs/${m}/${c}/single/${name}_all.json`), by = new Map(A.f.map((f, i) => [f, A.d[i]]));
    st.forEach((s, i) => { out[i] = by.get(s.f) || null; });
  } catch (e) { out.fill(null); }
  const one = async () => { while (k < st.length) { const i = k++; if (out[i]) continue; const f = String(st[i].f).padStart(3, "0");
    try { out[i] = await getJSON(`${DATA}runs/${m}/${c}/single/${name}_f${f}.json`); } catch (e) { out[i] = null; } } };
  await Promise.all(Array.from({ length: 8 }, one));
  return st.map((s, i) => ({ f: s.f, valid: s.valid, d: out[i] })).filter((x) => x.d);
}
const ptsSeries = (m, c) => memo(`pts/${m}/${c}`, async () => { const R = await loadRun(m, c); if (!R.points) return null; const st = await perStep(m, c, "pts"); return st.length ? { R, points: R.points, st } : null; });
const memSeries = (m, c) => memo(`mem/${m}/${c}`, async () => {   // probe the first step: runs encoded before 10-30 evening have no member files
  const R = await loadRun(m, c), s0 = (R.steps || [])[0]; if (!s0) return null;
  const ok = (R.agg || []).includes("mem") || await fetch(`${DATA}runs/${m}/${c}/single/mem_f${String(s0.f).padStart(3, "0")}.json`, { method: "HEAD" }).then((r) => r.ok).catch(() => false);
  if (!ok) return null; const st = await perStep(m, c, "mem"); return st.length ? { st } : null; });

function townSeries(D, name) {   // per-step values of one place (same derivations as the map viewer's Meteogram)
  const i = D.points.findIndex((p) => p.n === name); if (i < 0) return null;
  const P = D.points[i], col = (k) => D.st.map((o) => (o.d[k] ? o.d[k][i] : null)), has = (k) => D.st.some((o) => o.d[k] && o.d[k][i] != null);
  const T = { P, f: D.st.map((s) => s.f), x: D.st.map((s) => Date.parse(s.valid)) };
  const corr = (a) => a.map((v) => (v == null ? v : v + (P.c || 0)));
  if (has("t2m")) T.t2m = corr(col("t2m"));
  if (has("d2m")) T.d2m = corr(col("d2m"));
  for (const k of ["t2sd", "p32", "gust", "tcc", "mslp", "frz", "t850", "mucape", "pw", "tstm", "dsnod"]) if (has(k)) T[k] = col(k);
  if (has("maxt")) T.maxt = corr(col("maxt")); if (has("mint")) T.mint = corr(col("mint"));
  if (has("u10")) { const u = col("u10"), v = col("v10"); T.wind = u.map((x, k) => (x == null ? null : Math.hypot(x, v[k]) * 2.23694 / 1.94384)); }
  const inc = (a) => a.map((x, k) => (x == null ? null : Math.max(0, k ? x - (a[k - 1] ?? 0) : x)));
  if (has("apcp")) { T.apcpTot = col("apcp"); T.pcp = inc(T.apcpTot); }
  else if (has("nq1") || has("nq6")) {   // NBM: 1 h amounts to 36 h, then 6 h amounts
    const q1 = col("nq1"), q6 = col("nq6"); T.pcp = T.f.map((f, k) => (f <= 36 ? q1[k] : f % 6 === 0 ? q6[k] : 0)); T.apcpTot = cum(T.pcp);
    if (has("ns6")) { const s6 = col("ns6"); T.snow = T.f.map((f, k) => (f % 6 === 0 ? s6[k] || 0 : 0)); T.snowTot = cum(T.snow); }
  }
  if (has("asnow")) { T.snowTot = col("asnow"); T.snow = inc(T.snowTot); }
  else if (!T.snow && T.pcp && T.t2m) { T.snow = T.pcp.map((x, k) => (x == null ? null : T.t2m[k] <= 33 ? x * 10 : 0)); T.snowTot = cum(T.snow); T.snowEst = true; }
  if (has("kinc")) { T.kinc = col("kinc"); T.kuchTot = cum(T.kinc); }
  if (has("fzinc")) T.fzinc = col("fzinc");
  return T;
}
function cum(a) { let s = 0; return a.map((v) => (s += v || 0)); }
// members of one place: {x: [ms], f: [h], m: [[value per step] per member]}
function memTown(M, name, field, f2v, maxF) {
  if (!M) return null; const st = M.st.filter((s) => s.d.v && s.d.v[field] && s.d.v[field].length && (maxF == null || s.f <= maxF)); if (!st.length) return null;
  const j = st[0].d.n.indexOf(name); if (j < 0) return null; const sc = st[0].d.s[field] || 1;
  const nm = Math.max(...st.map((s) => s.d.v[field].length));
  const m = Array.from({ length: nm }, (_, k) => st.map((s) => { const row = s.d.v[field][k]; const v = row ? row[j] : null; return v == null ? null : f2v(v / sc); }));
  if (!m.some((a) => a.some((v) => v != null))) return null;
  return { x: st.map((s) => Date.parse(s.valid)), f: st.map((s) => s.f), m };
}
const fin = (v) => v != null && isFinite(v);
const nanmean = (a) => { const b = a.filter(fin); return b.length ? b.reduce((s, v) => s + v, 0) / b.length : null; };
const pct = (arr, p) => { const a = arr.filter(fin).sort((x, y) => x - y); if (!a.length) return null; const i = (a.length - 1) * p, lo = Math.floor(i); return a[lo] + (a[Math.min(a.length - 1, lo + 1)] - a[lo]) * (i - lo); };
const colStat = (S_, fn) => S_.x.map((_, i) => fn(S_.m.map((a) => a[i])));

/* ---------------- chart engine: the old matplotlib look ---------------- */
const K = { BG: "#15171c", PANEL: "#20232a", GRID: "#3a3e46", INK: "#f4f2ee", MUTED: "#a7abb3", WARM: "#ff6a3d", COLD: "#5fa8ff", RAIN: "#3fbf5a",
  SNOW: "#8fd3ff", MEAN: "#ffffff", ICE: "#ff5fa2", PLUM: "#b48cff", ACCENT: "#ffc970" };
const FONT = (w, px) => `${w} ${px}px Montserrat, system-ui, sans-serif`;
const MINUS = "\u2212";
function newFig(W, H, dpi) { const cv = document.createElement("canvas"); cv.width = W; cv.height = H; const c = cv.getContext("2d"); c.fillStyle = K.BG; c.fillRect(0, 0, W, H); return { cv, c, W, H, k: dpi / 72 }; }
function ftext(F, s, x, y, w, pt, color, base) { const c = F.c; c.font = FONT(w, pt * F.k); c.fillStyle = color; c.textAlign = "left"; c.textBaseline = base || "top"; c.fillText(s, x, y); }
const rgba = (hex, a) => { const n = parseInt(hex.slice(1, 7), 16); return `rgba(${n >> 16},${(n >> 8) & 255},${n & 255},${a == null ? 1 : a})`; };
function niceTicks(lo, hi, nbins) {   // matplotlib MaxNLocator(steps=[1, 2, 2.5, 5, 10])
  const raw = (hi - lo) / nbins; if (!(raw > 0)) return [lo];
  const sc = Math.pow(10, Math.floor(Math.log10(raw))); let step = 10 * sc;
  for (const s of [1, 2, 2.5, 5, 10]) if (s * sc >= raw * (1 - 1e-9)) { step = s * sc; break; }
  const out = []; for (let v = Math.ceil(lo / step - 1e-9) * step; v <= hi + step * 1e-9; v += step) out.push(Math.abs(v) < step * 1e-9 ? 0 : v);
  return out;
}
function tickFmt(ticks) { let d = 0; while (d < 6 && ticks.some((v) => Math.abs(v * Math.pow(10, d) - Math.round(v * Math.pow(10, d))) > 1e-6)) d++;
  return (v) => { const s = v.toFixed(d); return s.startsWith("-") ? MINUS + s.slice(1) : s; }; }
function dashPx(F, it) { const lw = it.lw || 1.5, k = F.k; if (it.dash === "--") return [3.7 * lw * k, 1.6 * lw * k]; if (it.dash === ":") return [1 * lw * k, 1.65 * lw * k]; if (Array.isArray(it.dash)) return it.dash.map((v) => v * lw * k); return []; }
// box: {l, t, r, b} px. o: {items, ylab, ylabPt, tickPt, legPt, legend: "upper right"|"upper left"|null, legNcol, legFace, xmode: "days"|"hours"|"cats",
//   ticks?: [{x, s}], ylim?: (lo, hi) => [lo, hi], xlim?: [a, b], ygrid?: true, xgrid?: true, tickLen?, tickColor?, tickFont?}
function axes(F, box, o) {
  const c = F.c, k = F.k, W = box.r - box.l, H = box.b - box.t;
  // data limits
  let xa = Infinity, xb = -Infinity, ya = Infinity, yb = -Infinity, xsa = null, xsb = null, ysa = null;
  const X = (v) => { if (fin(v)) { xa = Math.min(xa, v); xb = Math.max(xb, v); } }, Y = (v) => { if (fin(v)) { ya = Math.min(ya, v); yb = Math.max(yb, v); } };
  for (const it of o.items) {
    if (it.t === "line" || it.t === "scatter") it.x.forEach((x, i) => { if (fin(it.y[i])) { X(x); Y(it.y[i]); } });
    else if (it.t === "fill") { it.x.forEach((x, i) => { if (fin(it.lo[i]) && fin(it.hi[i])) { X(x); Y(it.lo[i]); Y(it.hi[i]); } }); const xs = it.x.filter((x, i) => fin(it.lo[i])); if (xs.length) { xsa = xsa == null ? xs[0] : Math.min(xsa, xs[0]); xsb = xsb == null ? xs[xs.length - 1] : Math.max(xsb, xs[xs.length - 1]); } }
    else if (it.t === "bars") it.x.forEach((x, i) => { if (!fin(it.y[i])) return; X(x - it.w / 2); X(x + it.w / 2); const b0 = it.base ? it.base[i] || 0 : 0; Y(b0); Y(b0 + it.y[i]); if (b0 === 0) ysa = 0; });
    else if (it.t === "vlines") it.x.forEach((x, i) => { if (fin(it.lo[i])) { X(x); Y(it.lo[i]); Y(it.hi[i]); } });
    else if (it.t === "hline") Y(it.y);
  }
  if (!isFinite(xa)) { xa = 0; xb = 1; } if (!isFinite(ya)) { ya = 0; yb = 1; }
  if (xa === xb) { xa -= 1; xb += 1; } if (ya === yb) { ya -= 0.5; yb += 0.5; }
  let x0 = xa - 0.05 * (xb - xa), x1 = xb + 0.05 * (xb - xa), y0 = ya - 0.05 * (yb - ya), y1 = yb + 0.05 * (yb - ya);
  if (xsa != null && xsa <= xa && x0 < xsa) x0 = xsa; if (xsb != null && xsb >= xb && x1 > xsb) x1 = xsb;   // fill_between: sticky x edges
  if (ysa === 0 && ya >= 0) y0 = 0;                                                                        // bars: sticky at 0
  if (o.xlim) [x0, x1] = o.xlim; if (o.ylim) [y0, y1] = o.ylim(y0, y1);
  const px = (v) => box.l + (v - x0) / (x1 - x0) * W, py = (v) => box.b - (v - y0) / (y1 - y0) * H;
  // ticks
  const tickPt = o.tickPt || 11, tpx = tickPt * k, tl = (o.tickLen == null ? 3.5 : o.tickLen) * k, pad = 3.5 * k, tcol = o.tickColor || K.INK;
  const nb = Math.max(1, Math.min(9, Math.floor(H / k / (tickPt * 2))));
  const yt = niceTicks(y0, y1, nb).filter((v) => v >= y0 - 1e-9 && v <= y1 + 1e-9), yf = tickFmt(niceTicks(y0, y1, nb));
  let xt = [];
  if (o.xmode === "cats") xt = o.ticks.filter((t) => t.x >= x0 && t.x <= x1);
  else { for (let t = Math.ceil(x0 / 36e5) * 36e5; t <= x1; t += 36e5) { const h = ptHour(t);
      if (o.xmode === "hours" ? h === 5 || h === 17 : h === 0) xt.push({ x: t, s: o.xmode === "hours" ? `${fmt({ weekday: "short" }).format(t)} ${hourLab(t)}` : dayLab(t) }); } }
  // panel, patches (below grid), grid, lines
  c.fillStyle = K.PANEL; c.fillRect(box.l, box.t, W, H);
  c.save(); c.beginPath(); c.rect(box.l, box.t, W, H); c.clip();
  const draw = (it) => drawItem(F, it, px, py);
  for (const it of o.items) if (it.t === "fill" || it.t === "bars") draw(it);
  c.strokeStyle = K.GRID; c.lineWidth = (o.gridLw || 0.8) * k;
  if (o.ygrid !== false) for (const v of yt) { const yy = py(v); c.beginPath(); c.moveTo(box.l, yy); c.lineTo(box.r, yy); c.stroke(); }
  if (o.xgrid !== false) for (const t of xt) { const xx = px(t.x); c.beginPath(); c.moveTo(xx, box.t); c.lineTo(xx, box.b); c.stroke(); }
  for (const it of o.items) if (it.t !== "fill" && it.t !== "bars" && it.t !== "text" && it.t !== "scatter") draw(it);
  for (const it of o.items) if (it.t === "scatter" || it.t === "text") draw(it);
  c.restore();
  // spines, tick marks, labels
  c.strokeStyle = K.GRID; c.lineWidth = 0.8 * k; c.strokeRect(box.l, box.t, W, H);
  c.strokeStyle = tcol; c.lineWidth = 0.8 * k; c.fillStyle = tcol; c.font = o.tickFont || FONT(500, tpx);
  c.textAlign = "right"; c.textBaseline = "middle"; let yw = 0;
  for (const v of yt) { const yy = py(v); if (tl) { c.beginPath(); c.moveTo(box.l, yy); c.lineTo(box.l - tl, yy); c.stroke(); } const s = yf(v); yw = Math.max(yw, c.measureText(s).width); c.fillText(s, box.l - tl - pad, yy); }
  c.textAlign = o.xAlign || "center"; c.textBaseline = "top";
  for (const t of xt) { const xx = px(t.x); if (tl) { c.beginPath(); c.moveTo(xx, box.b); c.lineTo(xx, box.b + tl); c.stroke(); } c.fillText(t.s, xx, box.b + tl + pad); }
  if (o.ylab) { c.save(); c.font = o.ylabFont || FONT(500, (o.ylabPt || 12) * k); c.fillStyle = K.INK; c.translate(box.l - tl - pad - yw - 4 * k, (box.t + box.b) / 2); c.rotate(-Math.PI / 2); c.textAlign = "center"; c.textBaseline = "bottom"; c.fillText(o.ylab, 0, 0); c.restore(); }
  if (o.legend) legend(F, box, o.items.filter((it) => it.label), o.legend, o.legPt || 9.5, o.legNcol || 1, o.legFace || K.PANEL);
  c.textAlign = "left";
  return { px, py, x0, x1, y0, y1 };
}
function drawItem(F, it, px, py) {
  const c = F.c, k = F.k;
  if (it.t === "line") { c.strokeStyle = it.color; c.globalAlpha = it.alpha == null ? 1 : it.alpha; c.lineWidth = (it.lw || 1.5) * k; c.setLineDash(dashPx(F, it)); c.lineJoin = "round"; c.lineCap = it.dash ? "butt" : "square";
    c.beginPath(); let on = false; it.x.forEach((x, i) => { const v = it.y[i]; if (!fin(v)) { on = false; return; } if (on) c.lineTo(px(x), py(v)); else c.moveTo(px(x), py(v)); on = true; }); c.stroke(); c.setLineDash([]); c.globalAlpha = 1; }
  else if (it.t === "hline") { c.strokeStyle = it.color; c.lineWidth = (it.lw || 1.5) * k; c.setLineDash(dashPx(F, it)); c.lineCap = "butt"; const yy = py(it.y); c.beginPath(); c.moveTo(0, yy); c.lineTo(F.W, yy); c.stroke(); c.setLineDash([]); }
  else if (it.t === "vline") { c.strokeStyle = it.color; c.lineWidth = (it.lw || 1) * k; const xx = px(it.x); c.beginPath(); c.moveTo(xx, 0); c.lineTo(xx, F.H); c.stroke(); }
  else if (it.t === "fill") { c.fillStyle = rgba(it.color, it.alpha); let seg = [];
    const flush = () => { if (seg.length > 1) { c.beginPath(); seg.forEach((i, j) => (j ? c.lineTo(px(it.x[i]), py(it.hi[i])) : c.moveTo(px(it.x[i]), py(it.hi[i])))); for (let j = seg.length - 1; j >= 0; j--) c.lineTo(px(it.x[seg[j]]), py(it.lo[seg[j]])); c.closePath(); c.fill(); } seg = []; };
    it.x.forEach((x, i) => { if (fin(it.lo[i]) && fin(it.hi[i])) seg.push(i); else flush(); }); flush(); }
  else if (it.t === "bars") { c.fillStyle = rgba(it.color, it.alpha); it.x.forEach((x, i) => { const v = it.y[i]; if (!fin(v) || v === 0) return; const b0 = it.base ? it.base[i] || 0 : 0; const xa = px(x - it.w / 2), xb = px(x + it.w / 2), ya = py(b0 + v), yb = py(b0); c.fillRect(xa, Math.min(ya, yb), xb - xa, Math.abs(yb - ya)); }); }
  else if (it.t === "vlines") { c.strokeStyle = it.color; c.lineWidth = (it.lw || 1.5) * k; it.x.forEach((x, i) => { if (!fin(it.lo[i])) return; c.beginPath(); c.moveTo(px(x), py(it.lo[i])); c.lineTo(px(x), py(it.hi[i])); c.stroke(); }); }
  else if (it.t === "scatter") { c.fillStyle = rgba(it.color, it.alpha); const r = Math.sqrt(it.s || 36) / 2 * k; it.x.forEach((x, i) => { if (!fin(it.y[i])) return; c.beginPath(); c.arc(px(x), py(it.y[i]), r, 0, 7); c.fill(); }); }
  else if (it.t === "text") { c.font = FONT(500, (it.pt || 10) * k); c.fillStyle = it.color; c.textAlign = "center"; c.textBaseline = "alphabetic"; it.x.forEach((x, i) => { if (fin(it.y[i])) c.fillText(it.s[i], px(x), py(it.y[i])); }); c.textAlign = "left"; }
}
function legend(F, box, items, loc, pt, ncol, face) {
  if (!items.length) return; const c = F.c, k = F.k, fs = pt * k;
  c.font = FONT(500, fs); const bp = 0.4 * fs, hl = 2 * fs, hp = 0.8 * fs, ls = 0.5 * fs, cs = 2 * fs, rh = fs * 1.17, ap = 0.5 * fs;
  const nrow = Math.ceil(items.length / ncol), cols = [];
  for (let j = 0; j < ncol; j++) cols.push(items.slice(j * nrow, (j + 1) * nrow));
  const cw = cols.map((cl) => hl + hp + Math.max(0, ...cl.map((it) => c.measureText(it.label).width)));
  const w = 2 * bp + cw.reduce((a, b) => a + b, 0) + cs * (ncol - 1), h = 2 * bp + nrow * rh + (nrow - 1) * ls;
  const x0 = loc === "upper left" ? box.l + ap : box.r - ap - w, y0 = box.t + ap;
  c.save(); c.globalAlpha = 0.8; const r = 0.2 * fs; c.beginPath(); c.roundRect ? c.roundRect(x0, y0, w, h, r) : c.rect(x0, y0, w, h); c.fillStyle = face; c.fill(); c.strokeStyle = K.GRID; c.lineWidth = 1 * k; c.stroke(); c.restore();
  let xx = x0 + bp;
  cols.forEach((cl, j) => { cl.forEach((it, i) => { const yy = y0 + bp + i * (rh + ls) + rh / 2;
      if (it.t === "fill" || it.t === "bars") { c.fillStyle = rgba(it.color, it.alpha); c.fillRect(xx, yy - 0.35 * fs, hl, 0.7 * fs); }
      else { c.strokeStyle = it.color; c.globalAlpha = it.alpha == null ? 1 : it.alpha; c.lineWidth = (it.lw || 1.5) * k; c.setLineDash(dashPx(F, it)); c.lineCap = it.dash ? "butt" : "square"; c.beginPath(); c.moveTo(xx, yy); c.lineTo(xx + hl, yy); c.stroke(); c.setLineDash([]); c.globalAlpha = 1; }
      c.fillStyle = K.INK; c.textAlign = "left"; c.textBaseline = "middle"; c.fillText(it.label, xx + hl + hp, yy); });
    xx += cw[j] + cs; });
}

/* ---------------- figure layouts (meteograms.frame, meteo_suite panels / z500, member_grid, snow_ens) ---------------- */
// single chart, 12 x 6.75 in at 120 dpi = 1440 x 810 (meteograms.frame)
function figFrame(spec) {
  const F = newFig(1440, 810, 120), W = F.W, H = F.H, c = F.c;
  c.fillStyle = K.ACCENT; c.fillRect(0.012 * W, (1 - 0.97) * H, 0.0045 * W, 0.105 * H);
  ftext(F, spec.title, 0.024 * W, (1 - 0.965) * H, 800, 20, K.INK);
  ftext(F, spec.sub, 0.024 * W, (1 - 0.905) * H, 600, 12.5, K.ACCENT);
  ftext(F, spec.credit, 0.024 * W, (1 - 0.012) * H, 500, 9.5, K.MUTED, "alphabetic");
  const P = spec.panels[0];
  axes(F, { l: 0.07 * W, r: 0.98 * W, t: (1 - 0.83) * H, b: (1 - 0.12) * H }, Object.assign({ tickPt: 11, ylabPt: 12, legPt: 9.5, xmode: spec.hourly ? "hours" : "days" }, P));
  return F.cv;
}
// stacked panels (HRRR / RRFS summaries): 12 x h in at 110 dpi; every panel keeps its own time axis (Benjamin 10-30)
function figPanels(spec) {
  const hIn = spec.hIn || 13.5, F = newFig(1320, Math.round(hIn * 110), 110), W = F.W, H = F.H, n = spec.panels.length;
  ftext(F, spec.title, 0.024 * W, (1 - 0.985) * H, 800, 20, K.INK);
  ftext(F, spec.sub, 0.024 * W, (1 - 0.958) * H, 600, 12, K.ACCENT);
  ftext(F, spec.credit, 0.015 * W, (1 - 0.006) * H, 500, 9.5, K.MUTED, "alphabetic");
  const top = (1 - 0.94) * H, bot = (1 - 0.04) * H, ah = (bot - top) / (n + 0.12 * (n - 1)), gap = 0.12 * ah;
  const xs = spec.panels.map(() => null); let lo = Infinity, hi = -Infinity;
  for (const P of spec.panels) for (const it of P.items) if (it.x) for (const x of it.x) { lo = Math.min(lo, x - (it.w || 0) / 2); hi = Math.max(hi, x + (it.w || 0) / 2); }
  const xlim = [lo - 0.05 * (hi - lo), hi + 0.05 * (hi - lo)];   // sharex
  spec.panels.forEach((P, i) => axes(F, { l: 0.07 * W, r: 0.98 * W, t: top + i * (ah + gap), b: top + i * (ah + gap) + ah }, Object.assign({ tickPt: 10, ylabPt: 10, legPt: 9.5, xmode: spec.hourly ? "hours" : "days", xlim }, P)));
  return F.cv;
}
// 500 mb height / 850 mb temp: 12 x 9 in at 120 dpi, two panels sharing x
function figZ500(spec) {
  const F = newFig(1440, 1080, 120), W = F.W, H = F.H;
  ftext(F, spec.title, 0.024 * W, (1 - 0.975) * H, 800, 20, K.INK);
  ftext(F, spec.sub, 0.024 * W, (1 - 0.94) * H, 600, 12, K.ACCENT);
  ftext(F, spec.credit, 0.024 * W, (1 - 0.008) * H, 500, 9.5, K.MUTED, "alphabetic");
  const top = (1 - 0.9) * H, bot = (1 - 0.07) * H, ah = (bot - top) / 2.1;
  let lo = Infinity, hi = -Infinity; for (const P of spec.panels) for (const it of P.items) if (it.x) for (const x of it.x) { lo = Math.min(lo, x); hi = Math.max(hi, x); }
  const xlim = [lo - 0.05 * (hi - lo), hi + 0.05 * (hi - lo)];
  spec.panels.forEach((P, i) => axes(F, { l: 0.08 * W, r: 0.98 * W, t: top + i * 1.1 * ah, b: top + i * 1.1 * ah + ah }, Object.assign({ tickPt: 10, ylabPt: 10, legPt: 9.5, xmode: "days", xlim }, P)));
  return F.cv;
}
// member grid (member_grid.grid_png): one row per member, CTRL row, MEAN row
const hexRGB = (h) => { const n = parseInt(h.slice(1, 7), 16); return [n >> 16, (n >> 8) & 255, n & 255]; };
const RGB = (a) => `rgb(${a[0]},${a[1]},${a[2]})`;
const G_PANEL = [32, 35, 42], G_INK = [244, 242, 238];
const inkFor = (bg) => (0.299 * bg[0] + 0.587 * bg[1] + 0.114 * bg[2] > 150 ? [15, 16, 20] : G_INK);
function shade(v, levels, colors) { if (!fin(v)) return G_PANEL; let i = -1; for (let j = 0; j < levels.length; j++) if (v >= levels[j]) i = j; if (i < 0) return G_PANEL;
  const c = hexRGB(colors[Math.min(i, colors.length - 1)]); return [0, 1, 2].map((q) => Math.trunc(G_PANEL[q] * 0.45 + c[q] * 0.55)); }
function figGrid(g) {   // g: {title, sub, credit, cols: [[a, b]], ctrl: null, M: [[member][col]], fmt, levels, colors, unit, note, legend}
  const tmp = document.createElement("canvas").getContext("2d"), L = (w, s, t) => { tmp.font = FONT(w, s); return tmp.measureText(t).width; };
  const nm = g.M.length, nc = g.cols.length;
  let cw = Math.max(38, 9 + 8 * Math.max(g.fmt(0).length, ...g.M.flat().filter(fin).map((v) => g.fmt(v).length)));
  if (nc <= 14) cw = Math.max(cw, Math.trunc(Math.max(...g.cols.map(([a]) => L(700, 12, a)))) + 12);
  const rh = 19, lw = 74, top = 136, hh = 40;
  const need = Math.max(L(800, 28, g.title), L(700, 14, g.legend), L(500, 14, g.note), L(500, 13, g.credit)) + 56;
  const W = Math.trunc(Math.max(lw + nc * cw + 24, need)), H = top + hh + (nm + 2) * rh + 10 + 8 + 48;
  const F = newFig(W, H, 72), c = F.c;
  const T = (s, x, y, w, px, col, al, bl) => { c.font = FONT(w, px); c.fillStyle = Array.isArray(col) ? RGB(col) : col; c.textAlign = al || "left"; c.textBaseline = bl || "top"; c.fillText(s, x, y); };
  c.fillStyle = K.ACCENT; c.fillRect(14, 16, 6, 101);
  T(g.title, 28, 12, 800, 28, K.INK); T(g.sub, 28, 52, 600, 16, K.ACCENT); T(g.note, 28, 78, 500, 14, K.MUTED); T(g.legend, 28, 100, 700, 14, K.ACCENT);
  const x0 = lw, y0 = top;
  g.cols.forEach(([a, b], j) => { let run = 1; while (j + run < nc && g.cols[j + run][0] === a) run++;
    const first = j === 0 || g.cols[j - 1][0] !== a;
    if (first && (run * cw >= L(700, 12, a) + 6 || !b)) T(a, x0 + j * cw + 3, y0 + 2, 700, 12, K.INK);
    if (b) T(b, x0 + j * cw + cw / 2, y0 + 20, 500, 11, K.MUTED, "center"); });
  T(g.unit, lw - 8, y0 + 20, 700, 12, K.ACCENT, "right");
  let y = y0 + hh;
  const row = (label, vals, y, labFill, bold, outline) => {
    T(label, lw - 8, y + rh / 2, bold ? 800 : 600, 12, labFill, "right", "middle");
    vals.forEach((v, j) => { const x = x0 + j * cw, bg = shade(v, g.levels, g.colors); c.fillStyle = RGB(bg); c.fillRect(x, y, cw, rh);
      if (fin(v)) T(g.fmt(v), x + cw / 2, y + rh / 2 + 0.5, bold ? 800 : 600, 12, inkFor(bg), "center", "middle"); });
    if (outline) { c.strokeStyle = outline; c.lineWidth = 2; c.strokeRect(x0 + 1, y + 1, nc * cw - 2, rh - 2); }
    c.fillStyle = K.GRID; for (let j = 1; j < nc; j++) if (g.cols[j][0] !== g.cols[j - 1][0]) c.fillRect(x0 + j * cw, y, 1, rh);
  };
  if (g.ref) row("9 KM", g.ref, y, REF_COLOR, true, REF_COLOR);
  else { T(g.legend.startsWith("9 KM") ? "9 KM" : "CTRL", lw - 8, y + rh / 2, 800, 12, g.legend.startsWith("9 KM") ? REF_COLOR : K.ACCENT, "right", "middle");
    c.fillStyle = K.PANEL; c.fillRect(x0, y, nc * cw, rh); c.strokeStyle = K.ACCENT; c.lineWidth = 2; c.strokeRect(x0 + 1, y + 1, nc * cw - 2, rh - 2);
    T(g.ctrlNote, x0 + 10, y + rh / 2, 600, 12, K.MUTED, "left", "middle"); }
  y += rh;
  for (let m = 0; m < nm; m++) { row(String(m + 1), g.M[m], y, K.MUTED); y += rh; if ((m + 1) % 10 === 0 && m + 1 < nm) { c.fillStyle = K.BG; c.fillRect(x0, y - 2, nc * cw, 2); } }
  y += 8; c.fillStyle = K.INK; c.fillRect(x0, y - 6, nc * cw, 2);
  const mean = g.cols.map((_, j) => nanmean(g.M.map((r) => r[j])));
  row("MEAN", mean, y, K.INK, true, K.INK);
  T(g.credit, 28, H - 30, 500, 13, K.MUTED);
  return F.cv;
}
// snow totals by member (snow_ens.snow_ens_png): 12 h columns, CTRL / members / MEAN / chance rows, member-spread chart below
const SN_LEVELS = [0.1, 0.5, 1, 2, 3, 4, 6, 8, 10, 12, 15, 18, 24, 30, 36];
const SN_COLORS = ["#24414f", "#2b5d6b", "#2f7a80", "#33988c", "#4fb38a", "#82c97f", "#b6da75", "#e3e46b", "#f3cf57", "#f6ad45", "#f08a3a", "#e46536", "#cc4436", "#a82d3f", "#7d2140"];
const SN_THRESH = [1, 3, 6, 12], SN_BAND = "#4fb3a0";
function figSnowEns(g) {   // g: {title, sub, credit, x: [ms], f: [h], A: [[member values per step]] (members x steps), every: 12}
  const every = 12, ci = g.f.map((f, i) => i).filter((i) => g.f[i] && g.f[i] % every === 0), nc = ci.length, nm = g.A.length;
  const G = g.A.map((a) => ci.map((i) => a[i])), mean = ci.map((_, j) => nanmean(G.map((r) => r[j])));
  const prob = SN_THRESH.map((t) => ci.map((_, j) => { const v = G.map((r) => r[j]).filter(fin); return v.length ? 100 * v.filter((x) => x >= t).length / v.length : 0; }));
  const lt = ci.map((i) => g.x[i]), cw = 40, rh = 18, lw = 86, top = 150, hh = 38, W = lw + nc * cw + 26, chartH = 330;
  const rows = 1 + nm + 1 + SN_THRESH.length, gy0 = top + hh, gy1 = gy0 + rows * rh + 3 * 6, H = gy1 + 24 + chartH + 44;
  const F = newFig(W, H, 72), c = F.c;
  const T = (s, x, y, w, px, col, al, bl) => { c.font = FONT(w, px); c.fillStyle = Array.isArray(col) ? RGB(col) : col; c.textAlign = al || "left"; c.textBaseline = bl || "top"; c.fillText(s, x, y); };
  const fill = (v) => (!fin(v) || v < SN_LEVELS[0] ? G_PANEL : hexRGB(SN_COLORS[Math.min(SN_LEVELS.filter((l) => v >= l).length - 1, SN_COLORS.length - 1)]));
  const sfmt = (v) => (!fin(v) || v < SN_LEVELS[0] ? "" : v < 9.95 ? v.toFixed(1) : v.toFixed(0));
  c.fillStyle = K.ACCENT; c.fillRect(14, 16, 6, 113);
  T(g.title, 28, 12, 800, 28, K.INK); T(g.sub, 28, 52, 600, 16, K.ACCENT);
  T("Run-total snow at 10:1 from each member's snowfall (water equivalent x 10), inches, every 12 h", 28, 78, 500, 14, K.MUTED);
  T(g.refRun ? `9 KM = ${REF_LABEL} (IFS 0.1\u00b0 ${g.refRun.slice(8)}Z, 0-144 h)  \u00b7  rows 1-${nm} = members  \u00b7  MEAN = mean  \u00b7  \u2265 rows = % of members at or above`
    : `CTRL = control run  \u00b7  rows 1-${nm} = members  \u00b7  MEAN = ensemble mean  \u00b7  \u2265 rows = % of members at or above`, 28, 100, 700, 13, K.ACCENT);
  const kx = W - 22 - SN_LEVELS.length * 30, ky = 124, kw = 30;
  SN_LEVELS.forEach((lv, k) => { c.fillStyle = SN_COLORS[k]; c.fillRect(kx + k * kw, ky, kw - 1, 13); T(lv >= 1 ? String(lv) : lv.toFixed(1).replace(/^0/, ""), kx + k * kw, ky - 3, 600, 11, K.MUTED, "left", "bottom"); });
  T("in", kx - 6, ky + 6, 700, 12, K.ACCENT, "right", "middle");
  const x0 = lw, dOf = (t) => ptDate(t);
  lt.forEach((t, j) => { const run = lt.slice(j).filter((u) => dOf(u) === dOf(t)).length;
    if ((j === 0 || dOf(lt[j - 1]) !== dOf(t)) && run * cw >= (c.font = FONT(700, 12), c.measureText(dayLab(t)).width) + 4) T(dayLab(t), x0 + j * cw + 3, top + 2, 700, 12, K.INK);
    T(hourLab(t).replace(" ", "").toLowerCase(), x0 + j * cw + cw / 2, top + 20, 500, 11, K.MUTED, "center"); });
  T("inches", lw - 8, top + 20, 700, 12, K.ACCENT, "right");
  const newday = lt.map((t, j) => j).filter((j) => j > 0 && dOf(lt[j]) !== dOf(lt[j - 1]));
  const row = (label, vals, y, lab, bold, outline, txt, col) => {
    T(label, lw - 8, y + rh / 2, bold ? 800 : 600, 12, lab, "right", "middle");
    vals.forEach((v, j) => { const x = x0 + j * cw, bg = (col || fill)(v); c.fillStyle = RGB(bg); c.fillRect(x + 1, y + 1, cw - 2, rh - 2);
      const s = (txt || sfmt)(v); if (s) T(s, x + cw / 2, y + rh / 2 + 0.5, bold ? 800 : 600, 11, inkFor(bg), "center", "middle"); });
    if (outline) { c.strokeStyle = outline; c.lineWidth = 2; c.strokeRect(x0 + 1, y + 1, nc * cw - 2, rh - 2); }
    c.fillStyle = bold ? K.INK : K.GRID; for (const j of newday) c.fillRect(x0 + j * cw, y, 1, rh);
  };
  let y = gy0;
  const refC = g.ref ? ci.map((i) => g.ref[i]) : null;
  if (refC && refC.some(fin)) row("9 KM", refC, y, REF_COLOR, true, REF_COLOR);
  else { T(g.refRun ? "9 KM" : "CTRL", lw - 8, y + rh / 2, 800, 12, g.refRun ? REF_COLOR : K.ACCENT, "right", "middle");
    c.fillStyle = K.PANEL; c.fillRect(x0, y, nc * cw, rh); c.strokeStyle = K.ACCENT; c.lineWidth = 2; c.strokeRect(x0 + 1, y + 1, nc * cw - 2, rh - 2);
    T(g.ctrlNote, x0 + 10, y + rh / 2, 600, 11, K.MUTED, "left", "middle"); }
  y += rh + 6;
  for (let m = 0; m < nm; m++) { row(String(m + 1), G[m], y, K.MUTED); y += rh; if ((m + 1) % 10 === 0 && m + 1 < nm) { c.fillStyle = K.BG; c.fillRect(x0, y - 1, nc * cw, 3); } }
  y += 6; row("MEAN", mean, y, K.INK, true, K.INK); y += rh + 6;
  const blue = hexRGB("#9fb4ff"), pcol = (p) => (!p ? G_PANEL : [0, 1, 2].map((q) => Math.trunc(G_PANEL[q] + (blue[q] - G_PANEL[q]) * (0.25 + 0.75 * p / 100))));
  SN_THRESH.forEach((t, i) => { row(`\u2265 ${t} in`, prob[i], y, "#b8c6ff", false, null, (v) => (v ? `${v.toFixed(0)}%` : ""), pcol); y += rh; });
  // member spread chart on the same columns (x = column index), 100 dpi
  T("Member spread", 28, gy1 + 4, 800, 15, K.INK);
  const oy = gy1 + 24, xs = g.f.map((f) => (f - every) / every), keep = xs.map((x) => x >= -1);
  const q = [0.1, 0.25, 0.5, 0.75, 0.9].map((p) => g.f.map((_, i) => pct(g.A.map((a) => a[i]), p))), mu = g.f.map((_, i) => nanmean(g.A.map((a) => a[i])));
  const sel = (a) => a.map((v, i) => (keep[i] ? v : null)), last = (a) => a.filter(fin).pop() || 0;
  const sub = { W, H: chartH, k: 100 / 72, c };
  c.save(); c.translate(0, oy);
  const box = { l: x0 - cw / 2, r: x0 - cw / 2 + (nc + 0.5) * cw, t: chartH * (1 - 0.93), b: chartH * (1 - 0.13) };
  const qmax = Math.max(...q[4].filter(fin), 0);
  const ax = axes(sub, box, { tickPt: 9, tickLen: 0, tickColor: K.MUTED, tickFont: FONT(600, 9 * sub.k), ylab: "inches (10:1)", ylabFont: FONT(600, 10 * sub.k), legPt: 9, legend: "upper left", legNcol: 5, legFace: K.BG,
    xmode: "cats", xAlign: "left", xgrid: false, gridLw: 0.7, ticks: [...((newday[0] == null ? nc : newday[0]) >= 2 ? [0] : []), ...newday].map((j) => ({ x: j - 0.5, s: fmt({ weekday: "short", day: "numeric" }).format(lt[j]).replace(/(\d+) (\w+)/, "$2 $1") })),
    xlim: [-1, nc - 0.5], ylim: () => [0, Math.max(1, qmax * 1.12)],
    items: [{ t: "fill", x: xs, lo: sel(q[0]), hi: sel(q[4]), color: SN_BAND, alpha: 0.22, label: "10-90% of members" },
      { t: "fill", x: xs, lo: sel(q[1]), hi: sel(q[3]), color: SN_BAND, alpha: 0.45, label: "25-75%" },
      ...newday.map((j) => ({ t: "vline", x: j - 0.5, color: K.GRID, lw: 0.8 })),
      { t: "line", x: xs, y: sel(q[2]), color: SN_BAND, lw: 2, label: `Median  ${last(q[2]).toFixed(1)} in` },
      { t: "line", x: xs, y: sel(mu), color: K.INK, lw: 2.6, label: `Mean  ${last(mu).toFixed(1)} in` },
      { t: "line", x: xs, y: sel(q[4]), color: SN_BAND, lw: 0.8, alpha: 0.8 }] });
  c.restore();
  T(g.credit, 28, H - 30, 500, 13, K.MUTED);
  return F.cv;
}

/* ---------------- product builders (titles, colours, legends as in meteo_suite.py) ---------------- */
const runTime = (c) => Date.UTC(+c.slice(0, 4), +c.slice(4, 6) - 1, +c.slice(6, 8), +c.slice(8));
const ampm = (t) => hourLab(t);   // "5 PM"
// old run line: "ECMWF ENS 0.25°, 50 members, 00Z run 10-23-26 (5 PM PT)"
const runLine = (sec, c, every) => { const t = runTime(c); return `${sec.rl}, ${c.slice(8)}Z run ${fmt({ month: "numeric", day: "numeric", year: "2-digit" }).format(t).replace(/\//g, "-")} (${ampm(t)} PT)` + (every ? `, every ${every} h` : ""); };
// old caption: "EPS 00Z run 10-23 (5 PM PT)"
const capRun = (sec, c) => { const t = runTime(c); return `${sec.tag} ${c.slice(8)}Z run ${+c.slice(4, 6)}-${+c.slice(6, 8)} (${ampm(t)} PT)`; };
const mrLabel = (c) => `${c.slice(8)}Z ${+c.slice(4, 6)}/${+c.slice(6, 8)}`;
const SHADES = ["#b5b7bb", "#8c8f95", "#6c6f75"];
const floor0 = (top) => (lo, hi) => [0, Math.max(hi, top == null ? 0.25 : top)];
const bottom0 = (lo, hi) => [0, hi];
function membersItems(S_, color, lw, alpha, meanLabel) {   // meteo_suite.members(): member lines, mean (white, 3), median (orange dashed)
  return [{ t: "multi", S: S_, color, lw: lw || 0.8, alpha: alpha == null ? 0.55 : alpha },
    { t: "line", x: S_.x, y: colStat(S_, nanmean), color: K.MEAN, lw: 3, label: meanLabel || "Mean" },
    { t: "line", x: S_.x, y: colStat(S_, (a) => pct(a, 0.5)), color: K.WARM, lw: 1.8, dash: "--", label: "Median" }];
}
const expand = (items) => items.flatMap((it) => (it.t === "multi" ? it.S.m.map((y) => ({ t: "line", x: it.S.x, y, color: it.color, lw: it.lw, alpha: it.alpha })) : [it]));
function bandsItems(x, A, color, label) {   // meteo_suite.bands(): A = members x steps
  const q = [0.1, 0.25, 0.5, 0.75, 0.9].map((p) => x.map((_, i) => pct(A.map((a) => a[i]), p)));
  return [{ t: "fill", x, lo: q[0], hi: q[4], color, alpha: 0.18, label: `${label} 10-90%` }, { t: "fill", x, lo: q[1], hi: q[3], color, alpha: 0.38, label: `${label} 25-75%` },
    { t: "line", x, y: q[2], color, lw: 2.6, label: `${label} median` }];
}
// ECMWF 9 km reference (Benjamin 10-31 6:29 AM "show the euro high res run as a reference row where the eps control used to
// be"): the open ENS files have no control member, so EPS charts show the newest ECMWF 9 km (IFS 0.1 deg) deterministic run in its
// place, matched by valid time. Limits of the 9 km data: 0-144 h and only places inside its Washington-scale views.
const REF_COLOR = "#4fd1ff", REF_LABEL = "ECMWF 9 km (reference)";
async function refSeries(town) {
  if (!S.man || !S.man.models || !S.man.models.ifs9) return null;
  for (const c of runsOf("ifs9")) { let D = null; try { D = await ptsSeries("ifs9", c); } catch (e) { D = null; }
    const T = D && townSeries(D, town.pt.n); if (T) return { T, c, init: runTime(c) }; }
  return null;
}
function refVal(R, key, x, since) {   // value at valid time x; since (ms): amount accumulated after that time (run totals)
  if (!R || !R.T[key]) return null; const T = R.T, at = (t) => { if (t === R.init) return 0; const i = T.x.indexOf(t); return i < 0 || !fin(T[key][i]) ? null : T[key][i]; };
  const v = at(x); if (v == null) return null; if (since == null) return v; if (since < R.init) return null; const b = at(since); return b == null ? null : Math.max(0, v - b);
}
const refGust6 = (R, x) => { const a = refVal(R, "gust", x), b = refVal(R, "gust", x - 3 * 36e5); return a == null ? null : b == null ? a : Math.max(a, b); };   // 9 km gust = max in prior 3 h
const refLine = (R, xs, f) => { const y = xs.map(f); return y.some(fin) ? [{ t: "line", x: xs, y, color: REF_COLOR, lw: 2.4, label: `${REF_LABEL} ${R.c.slice(8)}Z` }] : []; };
function withZero(S_, c) { return { x: [runTime(c), ...S_.x], f: [0, ...S_.f], m: S_.m.map((a) => [0, ...a]) }; }   // run totals start at 0
function roll(S_, h) {   // running h-hour total from a run-total series
  return { x: S_.x, f: S_.f, m: S_.m.map((a) => S_.f.map((s, i) => { if (s < h) return null; const j = S_.f.indexOf(s - h); if (j < 0) return null; return fin(a[i]) && fin(a[j]) ? Math.max(0, a[i] - a[j]) : null; })) };
}
function daily(S_, fn) {   // per PT day (only days with >= 4 values), members kept: {days: [ms noon-ish label time], v: members x days}
  const groups = new Map(); S_.x.forEach((x, i) => { if (!S_.f[i]) return; const d = ptDate(x); if (!groups.has(d)) groups.set(d, []); groups.get(d).push(i); });
  const days = [], idx = []; for (const [d, ii] of groups) { const ok = ii.filter((i) => S_.m.some((a) => fin(a[i]))); if (ok.length >= 4) { days.push(d); idx.push(ok); } }
  const noon = days.map((d) => { const [mo, da, yr] = d.split("/").map(Number); const g = Date.UTC(yr, mo - 1, da, 19); return g; });   // ~noon PT
  return { days, noon, v: S_.m.map((a) => idx.map((ii) => { const v = ii.map((i) => a[i]).filter(fin); return v.length ? fn(...v) : null; })) };
}
const memEmpty = (sec, what) => ({ empty: ["Not generated yet", `${what} need the ensemble members at each town. They are stored from the first ${sec.label} run encoded after 10-30 evening, at 47 places (the old site's towns, the mountain passes and a few more). Check back after the next ${sec.label} run.`], sug: "mem" });

async function build(sec, prod, town) {
  const m = sec.id, runs = runsOf(m);
  let D = null, c = null; for (const cc of runs) { try { D = await ptsSeries(m, cc); } catch (e) { D = null; } if (D) { c = cc; break; } }
  if (!D) return { empty: ["Not generated yet", `${sec.label} town data starts with the first run encoded after 10-30 12:53 PM PT. Check back after the next ${sec.label} run.`], sug: "none" };
  const name = town.label, pn = town.pt.n, k = prod.kind, ensM = ENS(m);
  const credit = sec.credit, run = runLine(sec, c);
  const base = { credit, run: c };
  if (k.startsWith("mr_")) return multiRun(sec, prod, town, runs, base);
  if (!ensM) {
    const T = townSeries(D, pn); if (!T) return { empty: ["Not in this model", `${name} is outside the ${sec.label} area.`] };
    const lim = sec.hrs ? T.f.map((f) => f <= sec.hrs) : T.f.map(() => true), cut = (a) => a && a.filter((_, i) => lim[i]);
    const x = cut(T.x), f = cut(T.f), every = f.length > 1 ? f[1] - f[0] : 1, hourly = !!sec.hrs;
    const stepH = f.map((v, i) => (i ? v - f[i - 1] : every)), w = stepH.map((h) => h * 36e5 * 0.85);
    const A = T.apcpTot ? cut(T.apcpTot).map((v) => v || 0) : null, Pinc = A ? A.map((v, i) => Math.max(0, i ? v - A[i - 1] : v)) : null;
    const runL = runLine(sec, c, every);
    if (k === "summary") {
      const panels = [];
      if (T.t2m) panels.push({ ylab: "\u00b0F", legend: "upper right", items: [{ t: "line", x, y: cut(T.t2m), color: K.WARM, lw: 2.5, label: "Temp" }, ...(T.d2m ? [{ t: "line", x, y: cut(T.d2m), color: K.RAIN, lw: 2, label: "Dew point" }] : []), { t: "hline", y: 32, label: "Freezing (32\u00b0F)", color: K.COLD, dash: "--", lw: 1.3 }] });
      if (T.gust || T.wind) panels.push({ ylab: "mph", legend: "upper right", items: [...(T.gust ? [{ t: "line", x, y: cut(T.gust), color: K.WARM, lw: 2, label: "Gust" }] : []), ...(T.wind ? [{ t: "line", x, y: cut(T.wind), color: K.INK, lw: 1.6, label: "Sustained" }] : [])] });
      if (A) panels.push({ ylab: "in", legend: "upper right", ylim: () => [0, Math.max(0.05, A[A.length - 1] * 1.15)], items: [{ t: "bars", x, y: Pinc, w: w[1] || w[0], color: K.RAIN, label: `${every}-hour precip` }, { t: "line", x, y: A, color: K.MEAN, lw: 2, label: `Total ${A[A.length - 1].toFixed(2)} in` }] });
      if (T.tcc) panels.push({ ylab: "%", legend: "upper right", ylim: () => [0, 100], items: [{ t: "fill", x, lo: x.map(() => 0), hi: cut(T.tcc), color: K.MUTED, alpha: 0.6, label: "Cloud cover" }] });
      if (!panels.length) return { empty: ["Not in this model", "This model has no surface fields at this place."] };
      return Object.assign(base, { fig: "panels", hIn: 13.5 * panels.length / 4, hourly, title: `${name} ${sec.tag} Surface Summary`, sub: runL, panels });
    }
    if (k === "winter") {
      if (!T.t2m && !A) return { empty: ["Not enough data", "This model has no temperature or precipitation at this place."] };
      const panels = [];
      if (T.t2m) panels.push({ ylab: "\u00b0F", legend: "upper left", items: [{ t: "line", x, y: cut(T.t2m), color: K.WARM, lw: 2.5, label: "Temp" }, ...(T.d2m ? [{ t: "line", x, y: cut(T.d2m), color: K.RAIN, lw: 1.8, label: "Dew point" }] : []), { t: "hline", y: 32, label: "Freezing (32\u00b0F)", color: K.COLD, dash: "--", lw: 1.3 }] });
      if (A) {   // precip by type: the fast data has snow (water = snow / 10) and freezing rain amounts, the rest is rain
        const sn = T.snow ? cut(T.snow) : null, fz = T.fzinc ? cut(T.fzinc) : null;
        const sw = Pinc.map((p, i) => Math.min(p, sn ? (sn[i] || 0) / 10 : 0)), fr = Pinc.map((p, i) => Math.min(p - sw[i], fz ? fz[i] || 0 : 0)), rn = Pinc.map((p, i) => Math.max(0, p - sw[i] - fr[i]));
        const b1 = sw, b2 = sw.map((v, i) => v + fr[i]), bw = w[1] || w[0];
        panels.push({ ylab: `in per ${every} h`, legend: "upper left", items: [{ t: "bars", x, y: sw, w: bw, color: K.SNOW, label: "Snow" }, { t: "bars", x, y: fr, base: b1, w: bw, color: K.ICE, label: "Freezing rain" },
          { t: "bars", x, y: x.map(() => 0), w: bw, color: K.PLUM, label: "Sleet" }, { t: "bars", x, y: rn, base: b2, w: bw, color: K.RAIN, label: "Rain" }, { t: "bars", x, y: x.map(() => 0), w: bw, color: K.MUTED, label: "Type not set" }] });
        const SN = T.snowTot ? cut(T.snowTot).map((v) => v || 0) : null;
        panels.push({ ylab: "snow (in)", legend: "upper left", ylim: bottom0, items: [...(SN ? [{ t: "line", x, y: SN, color: K.SNOW, lw: 2.5, label: `Model snowfall ${SN[SN.length - 1].toFixed(1)} in` }] : []), { t: "line", x, y: A.map((v) => v * 10), color: K.MUTED, lw: 1.4, dash: "--", label: "10:1 of all precip" }] });
      }
      return Object.assign(base, { fig: "panels", hIn: 11 * panels.length / 3, hourly, title: `${name} ${sec.tag} Winter Weather Summary`, sub: runL + "  \u00b7  precip bars colored by the model's precip type at each hour", panels });
    }
    return { empty: ["Not available yet", prod.note || "This chart is not drawn on the fast site yet."] };
  }
  // ---- ensemble (EPS / AIFS ENS): members at 47 places ----
  let M = null; try { M = await memSeries(m, c); } catch (e) { M = null; }
  if (!M) return memEmpty(sec, "Ensemble charts");
  const R = m === "eps" ? await refSeries(town) : null, t0 = runTime(c);
  const corr = town.pt.c || 0, id = (v) => v, H_ = ENS_HOURS;
  const get = (field, f2v, maxF) => memTown(M, pn, field, f2v || id, maxF == null ? H_ : maxF);
  const nm = (S_) => S_.m.length;
  const fr = (pid, title, ylab, items, legendLoc, ylim, extra) => Object.assign(base, { fig: "frame", title: `${name} ${title}`, sub: run, panels: [Object.assign({ ylab, legend: legendLoc || "upper right", ylim, items: expand(items) }, extra || {})] });
  const noField = (what) => ({ empty: ["Not in this model", `${sec.label} open data has no ${what} for the members.`] });
  if (k === "lines_t2m") { const t2 = get("2t", (v) => v + corr); if (!t2) return memEmpty(sec, "Member lines");
    return fr(k, "2 m Temperature: Members and Mean", "\u00b0F", [...membersItems(t2, K.MUTED), ...(R ? refLine(R, t2.x, (x) => refVal(R, "t2m", x)) : []), { t: "hline", y: 32, label: "Freezing (32\u00b0F)", color: K.COLD, lw: 1.4, dash: "--" }]); }
  if (k === "plume_tp" || k === "plume_sf") {
    const S0 = get(k === "plume_tp" ? "tp" : "sf"); if (!S0) return memEmpty(sec, "Plumes"); const A = withZero(S0, c), col = k === "plume_tp" ? K.RAIN : K.SNOW;
    const mu = colStat(A, nanmean), md = colStat(A, (a) => pct(a, 0.5)), lastM = nanmean(A.m.map((a) => a[a.length - 1])), lastD = pct(A.m.map((a) => a[a.length - 1]), 0.5);
    return fr(k, k === "plume_tp" ? "Total Precipitation Plume" : "Total Snow Plume (10:1)", k === "plume_tp" ? "inches (liquid)" : "inches of snow",
      [{ t: "multi", S: A, color: col, lw: 0.9, alpha: 0.45 }, { t: "line", x: A.x, y: mu, color: K.MEAN, lw: 3, label: `Mean ${(lastM || 0).toFixed(2)} in` }, { t: "line", x: A.x, y: md, color: K.WARM, lw: 2, dash: "--", label: `Median ${(lastD || 0).toFixed(2)} in` }, ...(R ? refLine(R, A.x, (x) => refVal(R, k === "plume_tp" ? "apcpTot" : "snowTot", x, t0)) : [])], "upper left", floor0(0.25));
  }
  if (k === "spread_tp") { const S0 = get("tp"); if (!S0) return memEmpty(sec, "Spread charts"); const A = withZero(S0, c);
    return fr(k, "Spread: Total Precipitation", "inches (liquid)", bandsItems(A.x, A.m, K.RAIN, "Total"), "upper left", bottom0); }
  if (k === "lines_sf24") { const S0 = get("sf"); if (!S0) return memEmpty(sec, "Member lines"); const A = roll(withZero(S0, c), 24);
    return fr(k, "24-Hour Snow (10:1): Members and Mean", "inches in prior 24 h", [...membersItems(A, K.SNOW), ...(R ? refLine(R, A.x, (x) => refVal(R, "snowTot", x, x - 24 * 36e5)) : [])], "upper left", floor0(0.25)); }
  if (k === "lines_tcc") { const S0 = get("tcc"); if (!S0) return M.st.some((s) => s.d.v && s.d.v.tcc) ? memEmpty(sec, "Member lines") : memEmpty(sec, "Member cloud cover lines");
    return fr(k, "Cloud Cover: Members and Mean", "%", membersItems(S0, K.MUTED), "upper right", () => [0, 100]); }
  if (k === "lines_cape") { const S0 = get("mucape"); if (!S0) return noField("most-unstable CAPE");
    return fr(k, "Most-Unstable CAPE: Members and Mean", "J/kg", membersItems(S0, K.PLUM), "upper right", bottom0); }
  if (k === "lines_pwat") { const S0 = get("pwat"); if (!S0) return memEmpty(sec, "Member precipitable water lines");
    return fr(k, "Precipitable Water: Members and Mean", "inches", membersItems(S0, K.RAIN), "upper right", bottom0); }
  if (k === "hilo" || k === "spread_mx" || k === "grid_mx" || k === "grid_mn") {
    const mx = get("mx2t", (v) => v + corr), mn = get("mn2t", (v) => v + corr); if (!mx || !mn) return noField("2 m max / min temperature");
    const HI = daily(mx, Math.max), LO = daily(mn, Math.min); if (!HI.days.length) return memEmpty(sec, "Daily charts");
    if (k === "hilo") {
      const items = [], ticks = HI.days.map((d, i) => ({ x: i, s: dayLab(HI.noon[i]) }));
      for (const [D_, col, lab, off] of [[HI, K.WARM, "High", -0.17], [LO, K.COLD, "Low", 0.17]]) {
        const n = D_.days.length, xs = Array.from({ length: n }, (_, i) => i + off), q = [0.1, 0.25, 0.5, 0.75, 0.9].map((p) => D_.days.map((_, j) => pct(D_.v.map((a) => a[j]), p)));
        items.push({ t: "vlines", x: xs, lo: q[0], hi: q[4], color: col, lw: 1.6 }, { t: "bars", x: xs, y: q[3].map((v, i) => v - q[1][i]), base: q[1], w: 0.3, color: col, alpha: 0.55, label: `${lab}: 25-75% box, 10-90% whisker` },
          { t: "scatter", x: xs, y: q[2], color: K.MEAN, s: 26 }, { t: "text", x: xs, y: q[2].map((v) => v + 1), s: q[2].map((v) => String(Math.round(v))), color: K.INK, pt: 9 });
      }
      items.push({ t: "hline", y: 32, label: "Freezing (32\u00b0F)", color: K.COLD, lw: 1.2, dash: "--" });
      return Object.assign(base, { fig: "frame", title: `${name} Daily High / Low Temperature`, sub: run + `  \u00b7  dots = median of ${nm(mx)} members`, panels: [{ ylab: "\u00b0F", legend: "upper left", xmode: "cats", ticks, items }] });
    }
    if (k === "spread_mx") return fr(k, "Spread: Daily High and Low", "\u00b0F", [...bandsItems(HI.noon, HI.v, K.WARM, "High"), ...bandsItems(LO.noon, LO.v, K.COLD, "Low"), { t: "hline", y: 32, label: "Freezing (32\u00b0F)", color: K.COLD, lw: 1.2, dash: "--" }], "upper left");
    const D_ = k === "grid_mx" ? HI : LO, hi = k === "grid_mx";
    return Object.assign(base, { fig: "grid", g: gridSpec(sec, name, run, `${hi ? "Daily High" : "Daily Low"} Temperature: Each Member + Mean`, "\u00b0F",
      `${hi ? "Highest of the 6 h max" : "Lowest of the 6 h min"} temps in each PT day`, D_.noon.map((t) => [dayLab(t), ""]), D_.v, (v) => v.toFixed(0), TL, TC, null, R) });
  }
  if (k === "grid_tp" || k === "grid_tp24") { const S0 = get("tp"); if (!S0) return memEmpty(sec, "Member grids"); let A = withZero(S0, c);
    if (k === "grid_tp24") A = roll(A, 24);
    const ii = A.f.map((f, i) => i).filter((i) => A.f[i] && A.f[i] % (k === "grid_tp24" ? 24 : 6) === 0);
    return Object.assign(base, { fig: "grid", g: gridSpec(sec, name, run, k === "grid_tp" ? "Total Precipitation: Each Member + Mean" : "24-Hour Precipitation: Each Member + Mean", "in",
      k === "grid_tp" ? "Run total from the start of the run to each time (liquid)" : "Liquid precipitation in the 24 h ending at each time",
      ii.map((i) => [dayLab(A.x[i]), hourLab(A.x[i])]), A.m.map((a) => ii.map((i) => a[i])), (v) => v.toFixed(2), QL, QC,
      R && ii.map((i) => refVal(R, "apcpTot", A.x[i], k === "grid_tp" ? t0 : A.x[i] - 24 * 36e5)), R) }); }
  if (k === "grid_gust") { const S0 = get("10fg"); if (!S0) return noField("10 m wind gust");
    const ii = S0.f.map((f, i) => i).filter((i) => S0.f[i] % 6 === 0);
    return Object.assign(base, { fig: "grid", g: gridSpec(sec, name, run, "Max Wind Gust: Each Member + Mean", "mph", `Max 10 m gust in the 6 h ending at each time; ${sec.id === "eps" ? "ECMWF ENS" : sec.label} has no hourly output`,
      ii.map((i) => [dayLab(S0.x[i]), hourLab(S0.x[i])]), S0.m.map((a) => ii.map((i) => a[i])), (v) => v.toFixed(0), GL, GC, R && ii.map((i) => refGust6(R, S0.x[i])), R) }); }
  if (k === "snowens") { const S0 = get("sf", id, SNOW_HOURS); if (!S0) return memEmpty(sec, "Snow totals by member"); const A = withZero(S0, c);
    return Object.assign(base, { fig: "snowens", g: { title: `${name}  \u00b7  Snow Totals by Member`, sub: `${run}  \u00b7  0-${A.f[A.f.length - 1]} h`, credit, x: A.x, f: A.f, A: A.m,
      ref: R ? A.x.map((x) => refVal(R, "snowTot", x, t0)) : null, refRun: R && R.c,
      ctrlNote: R ? `${REF_LABEL}: not at this place / time` : "control run: not stored in the fast data (members only)" } }); }
  if (k === "z500t850") { const z = get("gh", (v) => v / 10), t8 = get("t850"); if (!z || !t8) return noField("500 mb height / 850 mb temperature");
    return Object.assign(base, { fig: "z500", title: `${name} 500 mb Height and 850 mb Temperature`, sub: run + "  \u00b7  850 mb: 0\u00b0C dashed, -5\u00b0C dotted (lowland snow rule of thumb)",
      panels: [{ ylab: "500 mb height (dam)", legend: "upper right", items: expand(membersItems(z, K.MUTED)) },
        { ylab: "850 mb temp (\u00b0C)", legend: "upper right", items: expand([...membersItems(t8, K.COLD), { t: "hline", y: 0, label: "Freezing (0\u00b0C)", color: K.COLD, lw: 1.2, dash: "--" }, { t: "hline", y: -5, color: K.SNOW, lw: 1, dash: ":" }]) }] }); }
  return { empty: ["Not available yet", prod.note || "This chart is not drawn on the fast site yet."] };
}
const TL = [-20, 0, 10, 20, 32, 40, 50, 60, 70, 80, 90, 100];
const TC = ["#7f4fd6", "#5b6ee8", "#4f9be8", "#5fc3e8", "#7fd6c4", "#8fd68f", "#c4de6a", "#f0d45a", "#f0a040", "#e8603c", "#c0304a", "#a01860"];
const QL = [0.01, 0.1, 0.25, 0.5, 0.75, 1, 1.5, 2, 3, 4];
const QC = ["#2f6f3f", "#3f9f4f", "#5fbf5a", "#9fd65a", "#e0e05a", "#f0b040", "#f07a30", "#e04040", "#c02a70", "#9a2ab0"];
const GL = [10, 20, 30, 40, 45, 50, 58, 70];
const GC = ["#3f6f9f", "#4f9fbf", "#6fbf8f", "#d6d65a", "#f0b040", "#f07a30", "#e04040", "#b02ab0"];
function gridSpec(sec, name, run, title, unit, note, cols, M, f, levels, colors, ref, R) {
  const nm = M.length;
  if (R) return { title: `${name} ${title}`, sub: run, credit: sec.credit, cols, M, fmt: f, levels, colors, unit, note, ref: ref && ref.some(fin) ? ref : null,
    legend: `9 KM = ${REF_LABEL}, deterministic IFS 0.1\u00b0 ${R.c.slice(8)}Z run, 0-144 h (no control in the open ENS data)  \u00b7  rows 1-${nm} = members  \u00b7  MEAN = average of ${nm}`,
    ctrlNote: ref ? `${REF_LABEL}: no value at these times` : `${REF_LABEL}: not drawn for this chart (no 9 km daily max / min)` };
  return { title: `${name} ${title}`, sub: run, credit: sec.credit, cols, M, fmt: f, levels, colors, unit, note,
    legend: `CTRL = control run (member 0, unperturbed)  \u00b7  rows 1-${nm} = perturbed members  \u00b7  MEAN = average of ${nm} members  \u00b7  control run not stored in the fast data`,
    ctrlNote: "control run (member 0): not stored in the fast data (members only)" };
}

async function multiRun(sec, prod, town, runs, base) {
  const m = sec.id, k = prod.kind, list = [], ensM = ENS(m);
  for (const c of runs.slice(0, 4)) { let D = null; try { D = await ptsSeries(m, c); } catch (e) { D = null; } if (D) { const T = townSeries(D, town.pt.n); if (T) list.push([c, T]); } }
  if (!list.length) return { empty: ["Not generated yet", "No run with town data yet."] };
  const newest = runTime(list[0][0]), endT = newest + (ensM ? ENS_HOURS : sec.hrs || 1e4) * 36e5;
  const win = (T, tot, h) => T.f.map((f, i) => { const j = T.f.indexOf(f - h); const b = j >= 0 ? tot[j] : f - h === 0 ? 0 : null; return b == null || !fin(tot[i]) ? null : Math.max(0, tot[i] - b); });
  const pick = (T) => {
    if (k === "mr_t2m") return T.t2m; if (k === "mr_tmax") return T.maxt; if (k === "mr_tmin") return T.mint;
    const tot = /qpf/.test(k) ? T.apcpTot : T.snowTot; if (!tot) return null;
    if (/mr_(qpf|snow)$/.test(k)) return tot; return win(T, tot, +k.match(/\d+/)[0]);
  };
  const temp = /t2m|tmax|tmin/.test(k), items = [];
  list.forEach(([c, T], i) => { const y = pick(T); if (!y) return; const keep = T.x.map((x) => x <= endT);
    items.push({ t: "line", x: T.x.filter((_, j) => keep[j]), y: y.filter((_, j) => keep[j]), lw: i === 0 ? 3 : 1.5, color: i === 0 ? K.WARM : SHADES[Math.min(i - 1, 2)], label: mrLabel(c) }); });
  if (!items.length) return { empty: ["Not in this model", "This model run has no data for this product."] };
  const n = items.length;
  if (ensM) {
    const what = { mr_t2m: "2 m Temperature", mr_tmax: "Max Temperature (6 h window ending each step)", mr_tmin: "Min Temperature (6 h window ending each step)", mr_qpf6: "6-Hour Precipitation", mr_snow6: "6-Hour Snow (10:1)", mr_qpf24: "24-Hour Precipitation", mr_snow24: "24-Hour Snow (10:1)", mr_qpf: "Total Precipitation", mr_snow: "Total Snow (10:1)" }[k];
    return Object.assign(base, { fig: "frame", title: `${town.label} Multi-run: ${what}`, sub: `Ensemble mean of the last ${n} ${sec.id === "eps" ? "ENS" : sec.label} runs, newest bold`,
      panels: [{ ylab: temp ? "\u00b0F" : "inches", legend: "upper left", ylim: temp ? null : floor0(0.25), items: [...items, ...(temp ? [{ t: "hline", y: 32, label: "Freezing (32\u00b0F)", color: K.COLD, lw: 1.2, dash: "--" }] : [])] }] });
  }
  const what = { mr_t2m: "2 m Temperature", mr_qpf6: "6-Hour Precipitation", mr_snow6: "6-Hour Snow", mr_qpf24: "24-Hour Precipitation", mr_qpf: "Total Precipitation", mr_snow: "Total Snow" }[k];
  return Object.assign(base, { fig: "frame", hourly: !!sec.hrs, title: `${town.label} ${sec.tag} Multi-run: ${what}`, sub: `Last ${n} ${sec.hrs ? "long " : ""}${sec.tag} runs, newest bold`,
    panels: [{ ylab: temp ? "\u00b0F" : "in", legend: "upper left", ylim: temp ? null : bottom0, items: [...items, ...(temp ? [{ t: "hline", y: 32, label: "Freezing (32\u00b0F)", color: K.COLD, lw: 1.3, dash: "--" }] : [])] }] });
}

/* ---------------- page (old forecast.js renderMeteo) ---------------- */
function drawSpec(spec) {
  if (spec.fig === "grid") return figGrid(spec.g);
  if (spec.fig === "snowens") return figSnowEns(spec.g);
  if (spec.fig === "z500") return figZ500(spec);
  if (spec.fig === "panels") return figPanels(spec);
  return figFrame(spec);
}
async function townsFor(sec) {
  for (const c of runsOf(sec.id)) { try { const R = await loadRun(sec.id, c); if (R.points) return R.points; } catch (e) { /* next */ } }
  return [];
}
function readHash() { const q = new URLSearchParams(location.hash.slice(1)); S.sec = q.get("s") || ""; S.town = q.get("w") || ""; S.prod = q.get("p") || ""; }
function writeHash() { const q = new URLSearchParams({ s: S.sec, w: S.town, p: S.prod }); history.replaceState(null, "", "#" + q.toString()); }
function btn(label, onClick, attrs = {}) { const b = document.createElement("button"); b.type = "button"; b.textContent = label; b.onclick = onClick; for (const [k, v] of Object.entries(attrs)) if (v != null) b.setAttribute(k, v); return b; }
function emptyState(el, title, body, sug = []) {
  el.replaceChildren(); const h = document.createElement("p"); h.className = "empty-title"; h.textContent = title; const p = document.createElement("p"); p.className = "empty-body"; p.textContent = body; el.append(h, p);
  if (sug.length) { const w = document.createElement("div"); w.className = "empty-try"; const l = document.createElement("span"); l.textContent = "Try:"; w.appendChild(l); for (const [lab, fn] of sug.slice(0, 8)) w.appendChild(btn(lab, fn)); el.appendChild(w); }
  el.hidden = false;
}
let URLS = [];
async function render() {
  const tok = ++S.tok, sec = secObj(); window.MG_DONE = false;
  try { await render_(tok, sec); } finally { if (tok === S.tok) window.MG_DONE = true; }
}
async function render_(tok, sec) {
  const sc = $("msections"); sc.replaceChildren(); let sep = false;
  for (const s of SECTIONS) {
    if (s.extra && !sep) { const x = document.createElement("span"); x.className = "chip-sep"; x.textContent = "Fast extras"; sc.appendChild(x); sep = true; }
    sc.appendChild(btn(s.label, () => { S.sec = s.id; if (!s.products.some((p) => p.id === S.prod)) S.prod = sameKind(S.prod, s); render(); }, { "aria-pressed": String(s.id === S.sec), class: s.extra ? "extra" : "" }));
  }
  const pts = await townsFor(sec); if (tok !== S.tok) return;
  const towns = townList(sec, pts);
  const want = S.town, oldHit = OLD_TOWNS.find(([id, , n]) => id === want || (n === want && n !== "Portland"));   // old ids (w=seattle) or place names
  let T = towns.find((t) => t.id === want) || (oldHit && towns.find((t) => t.id === oldHit[0])) || towns.find((t) => t.pt.n === want) || towns.find((t) => t.id === "seattle") || towns[0];
  if (!T) T = { id: "seattle", label: "Seattle (SeaTac)", pt: { n: "Seattle" } };
  S.town = T.id;
  const town = $("town"); town.replaceChildren(); let og = null;
  for (const t of towns) { if (!t.old && !og) { og = document.createElement("optgroup"); og.label = "More places (fast site)"; town.appendChild(og); } (og || town).appendChild(new Option(t.label, t.id)); }
  if (!towns.length) town.appendChild(new Option("(no towns yet)", S.town));
  town.value = S.town; town.onchange = () => { S.town = town.value; render(); };
  if (!sec.products.some((p) => p.id === S.prod)) S.prod = sec.products[0].id;
  const sel = $("mproduct"); sel.replaceChildren();
  for (const p of sec.products) sel.add(new Option(p.label + (p.kind ? "" : " (not on the fast site yet)"), p.id));
  sel.value = S.prod; sel.onchange = () => { S.prod = sel.value; render(); };
  writeHash();
  const prod = sec.products.find((p) => p.id === S.prod);
  $("mcap-left").textContent = `${sec.label} \u00b7 ${prod.label} \u00b7 ${T.label}`; $("mcap-right").textContent = "";
  const img = $("meteo-img"), empty = $("meteo-empty"), dl = $("dl-meteo");
  dl.setAttribute("aria-disabled", "true"); dl.removeAttribute("href");
  if (!prod.kind) { img.hidden = true; img.removeAttribute("src"); emptyState(empty, "Not on the fast site yet", prod.note || "", altProducts(sec)); return; }
  const ld = $("meteo-loader"); const lt = setTimeout(() => (ld.hidden = false), 150);
  let spec; try { spec = await build(sec, prod, T); } catch (e) { spec = { empty: ["Could not load", "The data for this chart failed to download. Reload the page to try again."] }; console.error(e); }
  if (tok !== S.tok) { clearTimeout(lt); return; }
  if (spec.empty) { clearTimeout(lt); ld.hidden = true; img.hidden = true; img.removeAttribute("src"); emptyState(empty, spec.empty[0], spec.empty[1], spec.sug === "mem" ? memTowns(towns) : spec.sug === "none" ? [] : altProducts(sec)); return; }
  let cv; try { cv = drawSpec(spec); } catch (e) { console.error(e); clearTimeout(lt); ld.hidden = true; img.hidden = true; emptyState(empty, "Could not draw", "This chart could not be drawn. Reload the page to try again."); return; }
  const blob = await new Promise((r) => cv.toBlob(r, "image/png"));
  clearTimeout(lt); ld.hidden = true; if (tok !== S.tok || !blob) return;
  URLS.forEach((u) => URL.revokeObjectURL(u)); const u = URL.createObjectURL(blob); URLS = [u];
  empty.hidden = true; img.alt = `${sec.label} ${prod.label}, ${T.label}`;
  await new Promise((r) => { img.onload = r; img.onerror = r; img.src = u; }); img.hidden = false;
  $("mcap-right").textContent = capRun(sec, spec.run);
  dl.href = u; dl.download = `${S.sec}_${S.prod}_${S.town.replace(/\W+/g, "_")}.png`; dl.removeAttribute("aria-disabled");
}
function sameKind(pid, s) { const cur = SECTIONS.flatMap((x) => x.products).find((p) => p.id === pid); const m = cur && s.products.find((p) => p.kind && p.kind === cur.kind); return (m || s.products.find((p) => p.kind) || s.products[0]).id; }
function altProducts(sec) { return sec.products.filter((p) => p.kind && p.id !== S.prod).slice(0, 6).map((p) => [p.label, () => { S.prod = p.id; render(); }]); }
function memTowns(towns) { return towns.filter((t) => ["seattle", "spokane", "yakima", "bellingham", "snoqualmie", "stevens"].includes(t.id) && t.id !== S.town).map((t) => [t.label, () => { S.town = t.id; render(); }]); }
addEventListener("hashchange", () => { const a = [S.sec, S.town, S.prod].join("|"); readHash(); if ([S.sec, S.town, S.prod].join("|") !== a) { if (!secObj()) S.sec = "eps"; render(); } });
(async function init() {
  readHash(); if (!secObj()) S.sec = "eps";
  try { await Promise.race([Promise.all(["800 16px Montserrat", "700 12px Montserrat", "600 12px Montserrat", "500 11px Montserrat"].map((f) => document.fonts.load(f))), new Promise((r) => setTimeout(r, 2500))]); } catch (e) { /* system font */ }
  let lm = null;
  try { const r = await fetch(DATA + "manifest.json", { cache: "no-cache" }); if (!r.ok) throw new Error(r.status); lm = Date.parse(r.headers.get("last-modified") || ""); S.man = await r.json(); }
  catch (e) { $("stamp").textContent = "Could not load the map list"; return; }
  const full = fmt({ weekday: "short", month: "numeric", day: "numeric", hour: "numeric", minute: "2-digit" });
  const newest = Object.keys(S.man.runs).map((m) => runsOf(m)[0]).filter(Boolean).sort().pop();
  $("stamp").textContent = isFinite(lm) ? `Updated ${full.format(lm)} PT` : newest ? `Newest run ${full.format(runTime(newest))} PT` : "";
  render();
})();
