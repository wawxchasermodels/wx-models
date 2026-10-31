// Meteograms page (fast site, 10-30-26). Same layout as the old site's Meteograms tab (Model chips, Town A-Z, Product dropdown,
// one full-width chart, Download image), but every chart is drawn here from small per-step JSON in R2:
//   runs/<model>/<cycle>/single/pts_fFFF.json  deterministic / ensemble-mean values at every town and pass (order = run.json points)
//   runs/<model>/<cycle>/single/mem_fFFF.json  ensemble members at MEM_POINTS (EPS / AIFS ENS runs encoded after 10-30 evening)
"use strict";
const DATA = window.WX_DATA || "data/";
const $ = (id) => document.getElementById(id);
const PTZ = "America/Los_Angeles";
const FMT = {}; const fmt = (o) => FMT[JSON.stringify(o)] || (FMT[JSON.stringify(o)] = new Intl.DateTimeFormat("en-US", Object.assign({ timeZone: PTZ }, o)));
const ptHour = (ms) => +fmt({ hour: "numeric", hourCycle: "h23" }).format(ms) % 24;
const ptDay = (ms) => fmt({ weekday: "short", month: "numeric", day: "numeric" }).format(ms).replace(",", "");
const ptHm = (ms) => fmt({ hour: "numeric" }).format(ms).replace(" ", "").toLowerCase();
const S = { man: null, sec: "", town: "", prod: "", tok: 0 };

/* ---------------- products (old site order; ids kept so old links map 1:1) ---------------- */
const NA_XSEC = "Needs model levels at each town (vertical profiles). The fast data stores surface and single-level fields only, so this chart is not drawn yet.";
const NA_SMOKE = "Smoke is not in the fast data yet.";
const det = (m, L) => [
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
  [`${m}_t2m_members`, "Member View & Mean: 2m Temp", "mem_t2m"],
  [`${m}_qpf24_members`, "Member View & Mean: 24-Hour QPF", "grid_tp24"],
  [`${m}_qpf_members`, "Member View & Mean: Total QPF", "grid_tp"],
  [`${m}_snow24_members`, "Member View & Mean: 24-Hour Snow", "grid_sf24"],
  [`${m}_snow_members`, "Member View & Mean: Total Snow", "grid_sf"],
  [`${m}_tcc_members`, "Member View & Mean: Cloud Cover", null, "Member cloud cover is not stored in the fast data yet (one more ensemble field)."],
  [`${m}_gust_members`, "Member View & Mean: 6-hr Max Gust", "grid_gust"],
  [`${m}_mucape_members`, "Member View & Mean: MUCAPE", "grid_cape"],
  [`${m}_pwat_members`, "Member View & Mean: PWAT", null, "Member precipitable water is not stored in the fast data yet (one more ensemble field)."],
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
const SECTIONS = [   // the old page's three models first, then the fast site's extra models
  { id: "eps", label: "ECMWF EPS", credit: "Source: ECMWF open data, CC BY 4.0. Modified. \u00a9 ECMWF, www.ecmwf.int", products: ens("eps") },
  { id: "hrrr", label: "HRRR", credit: "Data: NOAA HRRR (public domain)", products: det("hrrr") },
  { id: "rrfs", label: "RRFS", credit: "Data: NOAA RRFS (public domain)", products: det("rrfs") },
  { id: "nbm", label: "NBM", extra: true, credit: "Data: NOAA National Blend of Models (public domain)", products: glob("nbm").filter((p) => !/qpf24|snow$/.test(p[0]) || p[0].endsWith("_snow")) },
  { id: "gfs", label: "GFS", extra: true, credit: "Data: NOAA GFS (public domain)", products: glob("gfs") },
  { id: "ifs", label: "ECMWF", extra: true, credit: "Source: ECMWF open data, CC BY 4.0. Modified. \u00a9 ECMWF, www.ecmwf.int", products: glob("ifs") },
  { id: "aifs", label: "AIFS", extra: true, credit: "Source: ECMWF open data, CC BY 4.0. Modified. \u00a9 ECMWF, www.ecmwf.int", products: glob("aifs") },
  { id: "aens", label: "AIFS ENS", extra: true, credit: "Source: ECMWF open data, CC BY 4.0. Modified. \u00a9 ECMWF, www.ecmwf.int", products: ens("aens") },
].map((s) => Object.assign(s, { products: s.products.map(([id, label, kind, note]) => ({ id, label, kind, note })) }));
const secObj = () => SECTIONS.find((s) => s.id === S.sec);
const ENS = (m) => m === "eps" || m === "aens";

/* ---------------- data ---------------- */
const CACHE = new Map();
const getJSON = (u, nc) => fetch(u, nc ? { cache: "no-cache" } : {}).then((r) => { if (!r.ok) throw new Error(r.status); return r.json(); });
function memo(k, fn) { if (!CACHE.has(k)) CACHE.set(k, fn().catch((e) => { CACHE.delete(k); throw e; })); return CACHE.get(k); }
const runsOf = (m) => [...((S.man && S.man.runs[m]) || [])].sort().reverse();   // newest first
const loadRun = (m, c) => memo(`run/${m}/${c}`, () => getJSON(`${DATA}runs/${m}/${c}/run.json`, true));
async function perStep(m, c, name) {   // [{f, valid, d}] for steps whose file exists
  const R = await loadRun(m, c), st = R.steps || [], out = new Array(st.length); let k = 0;
  const one = async () => { while (k < st.length) { const i = k++; const f = String(st[i].f).padStart(3, "0");
    try { out[i] = await getJSON(`${DATA}runs/${m}/${c}/single/${name}_f${f}.json`); } catch (e) { out[i] = null; } } };
  await Promise.all(Array.from({ length: 8 }, one));
  return st.map((s, i) => ({ f: s.f, valid: s.valid, d: out[i] })).filter((x) => x.d);
}
const ptsSeries = (m, c) => memo(`pts/${m}/${c}`, async () => { const R = await loadRun(m, c); if (!R.points) return null; const st = await perStep(m, c, "pts"); return st.length ? { R, points: R.points, st } : null; });
const memSeries = (m, c) => memo(`mem/${m}/${c}`, async () => {   // probe the first step: runs encoded before 10-30 evening have no member files
  const R = await loadRun(m, c), s0 = (R.steps || [])[0]; if (!s0) return null;
  const ok = await fetch(`${DATA}runs/${m}/${c}/single/mem_f${String(s0.f).padStart(3, "0")}.json`, { method: "HEAD" }).then((r) => r.ok).catch(() => false);
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
  if (has("u10")) { const u = col("u10"), v = col("v10"); T.wind = u.map((x, k) => (x == null ? null : Math.hypot(x, v[k]) * 2.23694 / 1.94384)); T.wdir = u.map((x, k) => (x == null ? null : (Math.atan2(-x, -v[k]) * 180 / Math.PI + 360) % 360)); }
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
function winSum(T, tot, hrs) {   // amount over the last `hrs` hours ending at each step (from a run-total series)
  return T.f.map((f, k) => { if (f < hrs) return null; let j = T.f.findIndex((g) => g >= f - hrs); if (j < 0) return null; const base = T.f[j] === f - hrs ? tot[j] : j === 0 && f - hrs <= 0 ? 0 : null; return base == null ? (T.f[0] >= f - hrs && f - hrs <= 0 ? tot[k] : null) : tot[k] - base; });
}

/* ---------------- drawing ---------------- */
const C = { BG: "#17181c", PANEL: "#20232a", GRID: "#363a43", INK: "#e8e6e1", MUTED: "#9a9da4", WARM: "#ff6b3d", COLD: "#7fb2ff", RAIN: "#3fc35f", SNOW: "#bfe0ff", FRZ: "#f06bd0", MEAN: "#ffffff", GOLD: "#f6c35b" };
const niceStep = (x) => { const p = Math.pow(10, Math.floor(Math.log10(x || 1))), r = x / p; return (r <= 1 ? 1 : r <= 2 ? 2 : r <= 2.5 ? 2.5 : r <= 5 ? 5 : 10) * p; };
function sizeCanvas(cv, W, H) { const dpr = Math.min(2, window.devicePixelRatio || 1); cv.width = Math.round(W * dpr); cv.height = Math.round(H * dpr); cv.style.width = W + "px"; cv.style.height = H + "px"; const c = cv.getContext("2d"); c.setTransform(dpr, 0, 0, dpr, 0, 0); return c; }
function header(c, W, spec, small) {
  c.fillStyle = C.BG; c.fillRect(0, 0, W, spec.H);
  c.fillStyle = C.GOLD; c.fillRect(small ? 8 : 14, 10, 4, small ? 38 : 46);
  c.textBaseline = "top"; c.fillStyle = C.INK; let fs = small ? 15 : 21; c.font = `800 ${fs}px Montserrat, system-ui, sans-serif`;
  while (fs > 11 && c.measureText(spec.title).width > W - 30 - (small ? 18 : 26)) { fs -= 0.5; c.font = `800 ${fs}px Montserrat, system-ui, sans-serif`; }   // shrink long titles on phones
  fitText(c, spec.title, (small ? 18 : 26), 10 + ((small ? 15 : 21) - fs) / 2, W - 30);
  c.fillStyle = C.GOLD; c.font = `600 ${small ? 11 : 14}px Montserrat, system-ui, sans-serif`; fitText(c, spec.sub, (small ? 18 : 26), small ? 32 : 40, W - 30);
  c.fillStyle = C.MUTED; c.font = `500 ${small ? 9.5 : 11.5}px Montserrat, system-ui, sans-serif`; c.textBaseline = "bottom"; fitText(c, spec.credit, small ? 8 : 14, spec.H - 5, W - 20);
}
function fitText(c, s, x, y, maxW) { let t = s || ""; while (t.length > 4 && c.measureText(t).width > maxW - x) t = t.slice(0, -2); if (t !== s) t = t.slice(0, -1) + "\u2026"; c.fillText(t, x, y); }
// Time axis under one panel: hour row + day row (Pacific). Every panel gets its own (Benjamin 10-30).
function timeAxis(c, X, x0, x1, L, R, yb, small) {
  const span = (x1 - x0) / 36e5, every = span <= 30 ? 3 : span <= 54 ? 6 : span <= 100 ? 12 : 0;
  c.font = `600 ${small ? 9.5 : 11}px Montserrat, system-ui, sans-serif`; c.fillStyle = "#cfd3da"; c.textBaseline = "top"; c.textAlign = "center";
  const mids = []; let lastX = -1e9;
  for (let t = Math.ceil(x0 / 36e5) * 36e5; t <= x1; t += 36e5) {
    const h = ptHour(t);
    if (h === 0) mids.push(t);
    if (every && h % every === 0 && X(t) - lastX > (small ? 30 : 38)) { c.fillText(ptHm(t), X(t), yb); lastX = X(t); }
  }
  const edges = [x0, ...mids, x1], dy = every ? (small ? 12 : 14) : 0, dw = mids.length > 1 ? X(mids[1]) - X(mids[0]) : R + 1e4;
  if (dw > c.measureText("Wed 10/28").width + 8) { for (let k = 0; k + 1 < edges.length; k++) { const xa = X(edges[k]), xb = X(edges[k + 1]); const lab = ptDay(edges[k] + 1); if (xb - xa > c.measureText(lab).width + 6) c.fillText(lab, (xa + xb) / 2, yb + dy); } }
  else { const kk = Math.max(1, Math.ceil((c.measureText("10/28").width + 10) / dw)); mids.forEach((m, k) => { if (k % kk) return; c.fillRect(X(m) - 0.5, yb - 4, 1, 4); c.fillText(fmt({ month: "numeric", day: "numeric" }).format(m + 1), X(m), yb + dy); }); }   // long runs on phones: every k-th midnight
  c.textAlign = "left";
  return mids;
}
// spec: {title, sub, credit, panels: [{wt, ylab, items, lo?, hi?, zero?, legend?: "left"|"right"}], x0, x1}
function drawChart(cv, box, spec) {
  const W = Math.max(300, box.clientWidth), small = W < 620;
  const head = small ? 58 : 70, foot = small ? 18 : 22, axisH = small ? 32 : 36, gap = 10;
  const unit = Math.max(small ? 110 : 150, Math.min(small ? 200 : 260, W * (small ? 0.42 : 0.3)));
  const H = head + foot + spec.panels.reduce((a, p) => a + p.wt * unit + axisH + gap, 0);
  spec.H = H; const c = sizeCanvas(cv, W, H); header(c, W, spec, small);
  const L = small ? 40 : 58, R = small ? 12 : 22, PW = W - L - R;
  const x0 = spec.x0, x1 = spec.x1, X = (t) => L + (t - x0) / Math.max(1, x1 - x0) * PW;
  let y = head;
  for (const P of spec.panels) {
    const h = P.wt * unit, y0 = y, y1 = y + h; y = y1 + axisH + gap;
    c.fillStyle = C.PANEL; c.fillRect(L, y0, PW, h); c.strokeStyle = C.GRID; c.lineWidth = 1; c.strokeRect(L + 0.5, y0 + 0.5, PW - 1, h - 1);
    // y range
    let lo = P.lo, hi = P.hi;
    if (lo == null || hi == null) { const vs = []; for (const it of P.items) for (const a of [it.y, it.lo, it.hi]) if (a) for (const v of a) if (v != null && isFinite(v)) vs.push(v);
      if (it_boxes(P)) for (const b of it_boxes(P)) for (const v of [b.p10, b.p90, b.p50]) if (v != null) vs.push(v);
      let a = vs.length ? Math.min(...vs) : 0, b = vs.length ? Math.max(...vs) : 1; if (P.ref != null) { a = Math.min(a, P.ref); b = Math.max(b, P.ref); }
      if (P.zero) a = 0; if (P.minTop != null) b = Math.max(b, P.minTop); const pad = (b - a || 1) * 0.08; if (lo == null) lo = P.zero ? 0 : a - pad; if (hi == null) hi = b + pad; }
    const step = niceStep((hi - lo) / (h > 150 ? 5 : 3)); if (!P.lo && !P.zero) lo = Math.floor(lo / step) * step; if (P.hi == null) hi = Math.ceil(hi / step) * step;
    const Y = (v) => y1 - (v - lo) / (hi - lo || 1) * h;
    c.save(); c.beginPath(); c.rect(L, y0, PW, h); c.clip();
    // grid
    c.strokeStyle = C.GRID; c.lineWidth = 1; for (let v = Math.ceil(lo / step) * step; v <= hi + 1e-9; v += step) { const yy = Math.round(Y(v)) + 0.5; c.beginPath(); c.moveTo(L, yy); c.lineTo(L + PW, yy); c.stroke(); }
    for (let t = Math.ceil(x0 / 36e5) * 36e5; t <= x1; t += 36e5) if (ptHour(t) === 0) { const xx = Math.round(X(t)) + 0.5; c.beginPath(); c.moveTo(xx, y0); c.lineTo(xx, y1); c.stroke(); }
    if (P.ref != null) { c.strokeStyle = C.COLD; c.setLineDash([6, 4]); c.lineWidth = 1.4; c.beginPath(); c.moveTo(L, Y(P.ref)); c.lineTo(L + PW, Y(P.ref)); c.stroke(); c.setLineDash([]); }
    for (const it of P.items) drawItem(c, it, X, Y, y1, PW, small);
    c.restore();
    // y labels
    c.font = `500 ${small ? 9.5 : 11}px Montserrat, system-ui, sans-serif`; c.fillStyle = C.INK; c.textBaseline = "middle"; c.textAlign = "right";
    for (let v = Math.ceil(lo / step) * step; v <= hi + 1e-9; v += step) c.fillText(+v.toFixed(step < 0.1 ? 2 : step < 1 ? 1 : 0) + "", L - 5, Y(v));
    c.save(); c.translate(small ? 9 : 14, (y0 + y1) / 2); c.rotate(-Math.PI / 2); c.textAlign = "center"; c.textBaseline = "middle"; c.fillText(P.ylab || "", 0, 0); c.restore(); c.textAlign = "left";
    legend(c, P.items.filter((it) => it.label), P.legend === "left" ? L + 8 : L + PW - 8, y0 + 8, P.legend !== "left", small);
    timeAxis(c, X, x0, x1, L, R, y1 + 5, small);
  }
}
const it_boxes = (P) => { const b = P.items.find((it) => it.t === "boxes"); return b ? b.boxes : null; };
function drawItem(c, it, X, Y, yb, PW, small) {
  const xs = it.x;
  if (it.t === "line") { c.strokeStyle = it.color; c.lineWidth = it.lw || 2; c.globalAlpha = it.alpha || 1; c.setLineDash(it.dash || []); c.beginPath(); let on = false;
    it.y.forEach((v, k) => { if (v == null || !isFinite(v)) { on = false; return; } const xx = X(xs[k]), yy = Y(v); if (on) c.lineTo(xx, yy); else c.moveTo(xx, yy); on = true; }); c.stroke(); c.setLineDash([]); c.globalAlpha = 1; }
  else if (it.t === "multi") { c.strokeStyle = it.color; c.lineWidth = it.lw || 0.8; c.globalAlpha = it.alpha || 0.5; for (const a of it.ys) { c.beginPath(); let on = false; a.forEach((v, k) => { if (v == null) { on = false; return; } const xx = X(xs[k]), yy = Y(v); on ? c.lineTo(xx, yy) : c.moveTo(xx, yy); on = true; }); c.stroke(); } c.globalAlpha = 1; }
  else if (it.t === "band") { c.fillStyle = it.color; c.globalAlpha = it.alpha || 0.2; c.beginPath(); let started = false;
    it.hi.forEach((v, k) => { if (v == null) return; const xx = X(xs[k]); started ? c.lineTo(xx, Y(v)) : c.moveTo(xx, Y(v)); started = true; });
    for (let k = it.lo.length - 1; k >= 0; k--) if (it.lo[k] != null) c.lineTo(X(xs[k]), Y(it.lo[k])); c.closePath(); c.fill(); c.globalAlpha = 1; }
  else if (it.t === "area") { c.fillStyle = it.color; c.globalAlpha = it.alpha || 0.6; c.beginPath(); c.moveTo(X(xs[0]), yb); it.y.forEach((v, k) => c.lineTo(X(xs[k]), Y(v || 0))); c.lineTo(X(xs[xs.length - 1]), yb); c.closePath(); c.fill(); c.globalAlpha = 1; }
  else if (it.t === "bars") { c.fillStyle = it.color; c.globalAlpha = it.alpha || 1; it.y.forEach((v, k) => { if (v == null || v <= 0) return; const w = Math.max(1.5, (X(xs[k]) - X(xs[k] - (it.w || 36e5))) * 0.82), base = it.base ? Y(it.base[k] || 0) : yb; c.fillRect(X(xs[k]) - w, Y((it.base ? it.base[k] || 0 : 0) + v), w, base - Y((it.base ? it.base[k] || 0 : 0) + v)); }); c.globalAlpha = 1; }
  else if (it.t === "arrows") { c.fillStyle = "#cfd3da"; const every = Math.max(1, Math.ceil(xs.length / (PW / 24)));
    for (let k = 0; k < xs.length; k += every) { if (it.dir[k] == null) continue; const r = (it.dir[k] + 180) * Math.PI / 180; c.save(); c.translate(X(xs[k]), yb - 10); c.rotate(r); c.beginPath(); c.moveTo(0, -6); c.lineTo(3.5, 4); c.lineTo(-3.5, 4); c.closePath(); c.fill(); c.restore(); } }
  else if (it.t === "boxes") { for (const b of it.boxes) { const xa = X(b.xa), xb = X(b.xb), w = Math.max(6, (xb - xa) * 0.62), xm = (xa + xb) / 2;
      c.strokeStyle = it.color; c.lineWidth = 2; c.beginPath(); c.moveTo(xm, Y(b.p10)); c.lineTo(xm, Y(b.p90)); c.stroke();
      c.fillStyle = it.color; c.globalAlpha = 0.85; c.fillRect(xm - w / 2, Y(b.p75), w, Math.max(2, Y(b.p25) - Y(b.p75))); c.globalAlpha = 1;
      c.fillStyle = "#fff"; c.beginPath(); c.arc(xm, Y(b.p50), 3.5, 0, 7); c.fill();
      c.font = `700 ${small ? 10 : 12}px Montserrat, system-ui, sans-serif`; c.textAlign = "center"; c.textBaseline = it.below ? "top" : "bottom"; c.fillStyle = it.text || "#fff";
      c.fillText(Math.round(b.p50), xm, it.below ? Y(b.p10) + 3 : Y(b.p90) - 3); c.textAlign = "left"; } }
  else if (it.t === "dots") { c.font = `800 ${small ? 10 : 12}px Montserrat, system-ui, sans-serif`; c.textAlign = "center"; for (const d of it.pts) { c.fillStyle = it.color; c.beginPath(); c.arc(X(d.x), Y(d.v), 3.5, 0, 7); c.fill(); c.textBaseline = it.below ? "top" : "bottom"; c.fillText(Math.round(d.v), X(d.x), Y(d.v) + (it.below ? 5 : -5)); } c.textAlign = "left"; }
}
function legend(c, items, x, y, right, small) {
  if (!items.length) return; c.font = `500 ${small ? 9.5 : 11.5}px Montserrat, system-ui, sans-serif`; c.textBaseline = "middle";
  const lh = small ? 15 : 18, w = Math.max(...items.map((it) => c.measureText(it.label).width)) + (small ? 34 : 40), h = items.length * lh + 8, x0 = right ? x - w : x;
  c.fillStyle = "#20232ae6"; c.strokeStyle = C.GRID; c.fillRect(x0, y, w, h); c.strokeRect(x0 + 0.5, y + 0.5, w - 1, h - 1);
  items.forEach((it, k) => { const yy = y + 4 + lh * k + lh / 2; c.strokeStyle = it.color; c.fillStyle = it.color;
    if (it.t === "bars" || it.t === "area" || it.t === "band" || it.t === "boxes") { c.globalAlpha = it.t === "band" ? 0.5 : 1; c.fillRect(x0 + 6, yy - 4, 18, 8); c.globalAlpha = 1; }
    else { c.lineWidth = Math.min(3, it.lw || 2); c.setLineDash(it.dash || []); c.beginPath(); c.moveTo(x0 + 6, yy); c.lineTo(x0 + 24, yy); c.stroke(); c.setLineDash([]); }
    c.fillStyle = C.INK; c.fillText(it.label, x0 + (small ? 28 : 32), yy); });
}
// Member grid (old site "Member View & Mean"): rows Mean / Control / members, columns = PT days (or 12 h), colour-coded cells.
function drawGrid(cv, box, spec) {
  const avail = Math.max(300, box.clientWidth), small = avail < 620;
  const rowH = small ? 15 : 17, colW = small ? 38 : 50, L = small ? 50 : 64, head = small ? 58 : 70, colHead = small ? 30 : 34, foot = small ? 34 : 40;
  const W = Math.max(avail, L + spec.cols.length * colW + 12), rows = spec.rows;
  const H = head + colHead + rows.length * rowH + foot + 8; spec.H = H;
  const c = sizeCanvas(cv, W, H); header(c, W, spec, small);
  c.font = `600 ${small ? 9.5 : 11}px Montserrat, system-ui, sans-serif`; c.textAlign = "center"; c.textBaseline = "middle"; c.fillStyle = "#cfd3da";
  spec.cols.forEach((col, j) => { const xm = L + j * colW + colW / 2; c.fillText(col[0], xm, head + colHead * 0.3); if (col[1]) c.fillText(col[1], xm, head + colHead * 0.72); });
  rows.forEach((r, i) => { const y = head + colHead + i * rowH;
    c.textAlign = "right"; c.fillStyle = r.bold ? C.GOLD : C.MUTED; c.font = `${r.bold ? 800 : 500} ${small ? 9 : 10.5}px Montserrat, system-ui, sans-serif`; c.fillText(r.label, L - 5, y + rowH / 2);
    r.v.forEach((v, j) => { const x = L + j * colW; const bg = v == null ? "#2a2d34" : spec.color(v); c.fillStyle = bg; c.fillRect(x + 0.5, y + 0.5, colW - 1, rowH - 1);
      if (v != null) { c.fillStyle = ink(bg); c.textAlign = "center"; c.font = `${r.bold ? 800 : 600} ${small ? 9 : 10.5}px Montserrat, system-ui, sans-serif`; c.fillText(spec.fmt(v), x + colW / 2, y + rowH / 2 + 0.5); } });
    if (r.bold) { c.strokeStyle = C.GOLD; c.lineWidth = 1; c.strokeRect(L + 0.5, y + 0.5, spec.cols.length * colW - 1, rowH - 1); } });
  c.textAlign = "left"; c.textBaseline = "bottom"; c.fillStyle = C.MUTED; c.font = `500 ${small ? 9.5 : 11.5}px Montserrat, system-ui, sans-serif`;
  if (spec.note) fitText(c, spec.note, small ? 8 : 14, H - (small ? 18 : 22), W - 10);
}
const ink = (hex) => { const n = parseInt(hex.slice(1, 7), 16), r = n >> 16, g = (n >> 8) & 255, b = n & 255; return 0.299 * r + 0.587 * g + 0.114 * b > 140 ? "#111" : "#fff"; };
const ramp = (stops) => (v) => { let k = 0; while (k + 1 < stops.length && v >= stops[k + 1][0]) k++; return stops[k][1]; };
const TEMP_RAMP = ramp([[-99, "#3b1d6e"], [0, "#4f3fa8"], [10, "#3e6fd1"], [20, "#4aa3e8"], [28, "#8fd3f5"], [32.5, "#cfe9c4"], [40, "#a8d977"], [50, "#f2e46b"], [60, "#f6b24b"], [70, "#ef7a35"], [80, "#d9452b"], [90, "#a6192e"]]);
const QPF_RAMP = ramp([[-1, "#2a2d34"], [0.01, "#cfe8d0"], [0.1, "#8fd18e"], [0.25, "#3fae4f"], [0.5, "#24823c"], [1, "#f2d64b"], [2, "#f08c2e"], [3, "#d6392a"], [5, "#9b1d73"]]);
const SNOW_RAMP = ramp([[-1, "#2a2d34"], [0.1, "#d8ecff"], [1, "#a9cdf5"], [3, "#6fa6e8"], [6, "#3f74cf"], [12, "#6a48c2"], [18, "#a23bb5"], [24, "#d63f8c"]]);
const GUST_RAMP = ramp([[-1, "#2a2d34"], [10, "#d9e7f2"], [20, "#a8d0e6"], [30, "#f2e46b"], [40, "#f6a24b"], [50, "#e0552f"], [60, "#b0172f"], [75, "#7a1450"]]);
const CAPE_RAMP = ramp([[-1, "#2a2d34"], [50, "#e6eedc"], [250, "#f2e46b"], [500, "#f6a24b"], [1000, "#e0552f"], [2000, "#b0172f"]]);

/* ---------------- product builders ---------------- */
const pct = (arr, p) => { const a = arr.filter((v) => v != null && isFinite(v)).sort((x, y) => x - y); if (!a.length) return null; const i = (a.length - 1) * p, lo = Math.floor(i); return a[lo] + (a[Math.min(a.length - 1, lo + 1)] - a[lo]) * (i - lo); };
const mean = (arr) => { const a = arr.filter((v) => v != null && isFinite(v)); return a.length ? a.reduce((s, v) => s + v, 0) / a.length : null; };
function memTown(M, T, name, field, f2v) {   // -> {x: [ms], f:[], m: [[member values per step]...]} (members x steps)
  if (!M) return null; const st = M.st.filter((s) => s.d.v && s.d.v[field]); if (!st.length) return null;
  const j = st[0].d.n.indexOf(name); if (j < 0) return null; const sc = st[0].d.s[field] || 1;
  const nm = Math.max(...st.map((s) => s.d.v[field].length));
  const m = Array.from({ length: nm }, (_, k) => st.map((s) => { const row = s.d.v[field][k]; const v = row ? row[j] : null; return v == null ? null : f2v(v / sc); }));
  return { x: st.map((s) => Date.parse(s.valid)), f: st.map((s) => s.f), m };
}
const runLabel = (m, c) => `${c.slice(8)}Z ${+c.slice(4, 6)}/${+c.slice(6, 8)}`;
const runLine = (m, c) => { const t = Date.UTC(+c.slice(0, 4), +c.slice(4, 6) - 1, +c.slice(6, 8), +c.slice(8)); return `${S.man.models[m].name} ${S.man.models[m].res || ""}, ${c.slice(8)}Z run ${fmt({ month: "numeric", day: "numeric", year: "2-digit" }).format(t).replace(/\//g, "-")} (${ptHm(t).toUpperCase().replace("AM", " AM").replace("PM", " PM")} PT)`; };
const placeLabel = (p) => (p.k === "pass" ? `${p.n} Pass` : p.n);

async function build(sec, prod, town) {
  const m = sec.id, runs = runsOf(m);
  // newest run with town data (older runs were encoded before town points existed)
  let D = null, c = null; for (const cc of runs) { try { D = await ptsSeries(m, cc); } catch (e) { D = null; } if (D) { c = cc; break; } }
  if (!D) return { empty: ["Not generated yet", `${sec.label} town data starts with the first run encoded after 10-30 12:53 PM PT. Check back after the next ${sec.label} run.`], sug: "none" };
  const P = D.points.find((p) => p.n === town); if (!P) return { empty: ["Not in this model", `${town} is outside the ${sec.label} area.`] };
  const T = townSeries(D, town), name = placeLabel(P), x0 = T.x[0], x1 = T.x[T.x.length - 1];
  const base = { sub: runLine(m, c), credit: sec.credit + (P.k === "pass" ? " \u00b7 Temperature corrected to pass summit height" : ""), x0, x1, run: c };
  const k = prod.kind, ensM = ENS(m);
  const deg = (v) => v;   // members are stored in deg F / in / mph already
  if (k === "summary") {
    const panels = [];
    if (T.t2m) panels.push({ wt: 1.1, ylab: "\u00b0F", ref: 32, items: [{ t: "line", x: T.x, y: T.t2m, color: C.WARM, lw: 2.5, label: ensM ? "Temp (ens. mean)" : "Temp" }, ...(T.d2m ? [{ t: "line", x: T.x, y: T.d2m, color: C.RAIN, lw: 2, label: "Dew point" }] : [])] });
    if (T.gust || T.wind) panels.push({ wt: 0.9, ylab: "mph", zero: true, minTop: 10, items: [...(T.gust ? [{ t: "line", x: T.x, y: T.gust, color: C.WARM, lw: 2, label: "Gust" }] : []), ...(T.wind ? [{ t: "line", x: T.x, y: T.wind, color: C.INK, lw: 1.6, label: "Sustained" }, { t: "arrows", x: T.x, dir: T.wdir }] : [])] });
    if (T.pcp) { const stepH = T.f.length > 1 ? T.f[1] - T.f[0] : 1, tot = T.apcpTot || cum(T.pcp);
      panels.push({ wt: 0.9, ylab: "in", zero: true, minTop: 0.1, legend: "left", items: [{ t: "bars", x: T.x, y: T.pcp, w: stepH * 36e5, color: C.RAIN, label: T.f.some((f, i) => i && f - T.f[i - 1] !== stepH) ? "Precip per step" : `${stepH}-hour precip` }, { t: "line", x: T.x, y: tot, color: C.MEAN, lw: 2, label: `Total ${(tot[tot.length - 1] || 0).toFixed(2)} in` }] }); }
    if (T.tcc) panels.push({ wt: 0.7, ylab: "%", lo: 0, hi: 100, items: [{ t: "area", x: T.x, y: T.tcc, color: "#8c8f95", alpha: 0.65, label: "Cloud cover" }] });
    return Object.assign(base, { title: `${name} ${sec.label} Surface Summary`, panels });
  }
  if (k === "winter") {
    const panels = [], stepH = T.f.length > 1 ? T.f[1] - T.f[0] : 1;
    if (T.t2m) { const wb = T.d2m ? T.t2m.map((t, i) => wetBulbF(t, T.d2m[i])) : null;
      panels.push({ wt: 1, ylab: "\u00b0F", ref: 32, items: [{ t: "line", x: T.x, y: T.t2m, color: C.WARM, lw: 2.5, label: "Temp" }, ...(wb ? [{ t: "line", x: T.x, y: wb, color: C.COLD, lw: 2, label: "Wet bulb" }] : []), ...(T.d2m ? [{ t: "line", x: T.x, y: T.d2m, color: C.RAIN, lw: 1.4, label: "Dew point" }] : [])] }); }
    if (T.pcp) { // precip split by type: snow water (snow/10), freezing rain, rest = rain
      const fz = T.fzinc || T.pcp.map(() => 0), sw = T.snow ? T.snow.map((s, i) => Math.min(T.pcp[i] || 0, (s || 0) / 10)) : T.pcp.map(() => 0);
      const rain = T.pcp.map((p, i) => Math.max(0, (p || 0) - (fz[i] || 0) - sw[i])), b1 = sw, b2 = sw.map((s, i) => s + (fz[i] || 0));
      panels.push({ wt: 0.8, ylab: "in", zero: true, minTop: 0.05, legend: "left", items: [{ t: "bars", x: T.x, y: sw, w: stepH * 36e5, color: C.SNOW, label: "Snow (water)" }, { t: "bars", x: T.x, y: fz, base: b1, w: stepH * 36e5, color: C.FRZ, label: "Freezing rain" }, { t: "bars", x: T.x, y: rain, base: b2, w: stepH * 36e5, color: C.RAIN, label: "Rain" }] }); }
    if (T.snowTot || T.kuchTot) panels.push({ wt: 0.8, ylab: "in", zero: true, minTop: 1, legend: "left", items: [...(T.snowTot ? [{ t: "line", x: T.x, y: T.snowTot, color: C.SNOW, lw: 2.5, label: `Snow 10:1${T.snowEst ? " (est.)" : ""} ${(T.snowTot[T.snowTot.length - 1] || 0).toFixed(1)} in` }] : []), ...(T.kuchTot ? [{ t: "line", x: T.x, y: T.kuchTot, color: C.GOLD, lw: 2, label: `Kuchera ${(T.kuchTot[T.kuchTot.length - 1] || 0).toFixed(1)} in` }] : []), ...(T.fzinc ? [{ t: "line", x: T.x, y: cum(T.fzinc), color: C.FRZ, lw: 2, label: `Freezing rain ${cum(T.fzinc).pop().toFixed(2)} in` }] : [])] });
    if (T.frz) panels.push({ wt: 0.7, ylab: "ft", zero: true, items: [{ t: "line", x: T.x, y: T.frz, color: C.COLD, lw: 2, label: "Freezing level" }] });
    if (!panels.length) return { empty: ["Not enough data", "This model has no temperature or precipitation at this place."] };
    return Object.assign(base, { title: `${name} ${sec.label} Winter Weather Summary`, panels });
  }
  if (k.startsWith("mr_")) return multiRun(sec, prod, town, name, base, runs);
  // ---- ensemble member products ----
  let M = null; try { M = await memSeries(m, c); } catch (e) { M = null; }
  const memNote = (what) => ({ empty: ["Not generated yet", `${what} need the ensemble members at each town. They are stored from the first ${sec.label} run encoded after this page went up (10-30 evening), for ${MEM_HINT}.`], sug: "mem" });
  const t2 = memTown(M, T, town, "2t", (v) => v + (P.c || 0)), tp = memTown(M, T, town, "tp", deg), sf = memTown(M, T, town, "sf", deg);
  const mx = memTown(M, T, town, "mx2t", (v) => v + (P.c || 0)), mn = memTown(M, T, town, "mn2t", (v) => v + (P.c || 0));
  const stats = (S_, fn) => S_.x.map((_, i) => fn(S_.m.map((a) => a[i])));
  if (k === "mem_t2m") {
    if (!t2) { if (!T.t2m) return memNote("Member lines"); return Object.assign(base, { title: `${name} 2 m Temperature: Mean and Spread`, note: "Members not stored for this run: mean \u00b11 spread.", panels: [{ wt: 1.6, ylab: "\u00b0F", ref: 32, items: [{ t: "band", x: T.x, lo: T.t2m.map((v, i) => v - (T.t2sd ? T.t2sd[i] : 0)), hi: T.t2m.map((v, i) => v + (T.t2sd ? T.t2sd[i] : 0)), color: C.WARM, alpha: 0.2, label: "\u00b11 spread" }, { t: "line", x: T.x, y: T.t2m, color: C.MEAN, lw: 3, label: "Mean" }] }] }); }
    return Object.assign(base, { title: `${name} 2 m Temperature: Members and Mean`, panels: [{ wt: 1.6, ylab: "\u00b0F", ref: 32, items: [{ t: "band", x: t2.x, lo: stats(t2, (a) => pct(a, 0.1)), hi: stats(t2, (a) => pct(a, 0.9)), color: C.WARM, alpha: 0.15, label: "10-90%" }, { t: "multi", x: t2.x, ys: t2.m, color: "#9aa0aa", lw: 0.8, alpha: 0.55 }, { t: "line", x: t2.x, y: stats(t2, mean), color: C.MEAN, lw: 3, label: "Mean" }, { t: "line", x: t2.x, y: stats(t2, (a) => pct(a, 0.5)), color: C.WARM, lw: 2, dash: [7, 4], label: "Median" }] }] });
  }
  if (k === "plume_tp" || k === "plume_sf") {
    const S_ = k === "plume_tp" ? tp : sf, what = k === "plume_tp" ? "Total Precipitation" : "Total Snow (10:1)", col = k === "plume_tp" ? C.RAIN : C.SNOW;
    if (!S_) { const a = k === "plume_tp" ? T.apcpTot : T.snowTot; if (!a) return memNote("Plumes");
      return Object.assign(base, { title: `${name} ${what}: Ensemble Mean`, panels: [{ wt: 1.6, ylab: "inches", zero: true, minTop: 0.25, legend: "left", items: [{ t: "line", x: T.x, y: a, color: C.MEAN, lw: 3, label: `Mean ${(a[a.length - 1] || 0).toFixed(2)} in` }] }] }); }
    const mu = stats(S_, mean), md = stats(S_, (a) => pct(a, 0.5));
    return Object.assign(base, { title: `${name} ${what} Plume`, panels: [{ wt: 1.6, ylab: k === "plume_tp" ? "inches (liquid)" : "inches of snow", zero: true, minTop: 0.25, legend: "left", items: [{ t: "multi", x: S_.x, ys: S_.m, color: col, lw: 0.9, alpha: 0.5 }, { t: "line", x: S_.x, y: mu, color: C.MEAN, lw: 3, label: `Mean ${(mu[mu.length - 1] || 0).toFixed(2)} in` }, { t: "line", x: S_.x, y: md, color: C.WARM, lw: 2, dash: [7, 4], label: `Median ${(md[md.length - 1] || 0).toFixed(2)} in` }] }] });
  }
  if (k === "spread_tp") {
    if (!tp) return memNote("Spread charts");
    const q = (p) => stats(tp, (a) => pct(a, p));
    return Object.assign(base, { title: `${name} Total Precipitation Spread`, panels: [{ wt: 1.6, ylab: "inches (liquid)", zero: true, minTop: 0.25, legend: "left", items: [{ t: "band", x: tp.x, lo: q(0.1), hi: q(0.9), color: C.RAIN, alpha: 0.22, label: "10-90%" }, { t: "band", x: tp.x, lo: q(0.25), hi: q(0.75), color: C.RAIN, alpha: 0.45, label: "25-75%" }, { t: "line", x: tp.x, y: q(0.5), color: C.MEAN, lw: 2.5, label: `Median ${(q(0.5).pop() || 0).toFixed(2)} in` }, { t: "line", x: tp.x, y: q(0.9), color: C.GOLD, lw: 1.4, dash: [4, 3], label: `90th pct ${(q(0.9).pop() || 0).toFixed(2)} in` }] }] });
  }
  if (k === "hilo" || k === "spread_mx") {
    const days = dayBins(T.x[0], T.x[T.x.length - 1]).filter((d) => d.b - d.a >= 12 * 36e5);   // skip short partial days at the run edges
    if (!mx || !mn) {   // members not stored: daily mean of member max / min (pts maxt / mint)
      if (!T.maxt && !T.mint) return memNote("Daily high / low boxes");
      const hp = [], lp = []; for (const d of days) { const iH = T.x.map((x, i) => i).filter((i) => T.x[i] > d.a && T.x[i] <= d.b + 3 * 36e5 && T.maxt && T.maxt[i] != null); const iL = T.x.map((x, i) => i).filter((i) => T.x[i] > d.a && T.x[i] <= d.b + 3 * 36e5 && T.mint && T.mint[i] != null);
        if (iH.length >= 2) hp.push({ x: (d.a + d.b) / 2, v: Math.max(...iH.map((i) => T.maxt[i])) }); if (iL.length >= 2) lp.push({ x: (d.a + d.b) / 2, v: Math.min(...iL.map((i) => T.mint[i])) }); }
      return Object.assign(base, { title: `${name} Daily High / Low Temperature`, sub: base.sub + " \u00b7 ensemble mean (members not stored for this run)", panels: [{ wt: 1.6, ylab: "\u00b0F", ref: 32, items: [{ t: "dots", pts: hp, color: C.WARM, label: "High (mean)" }, { t: "dots", pts: lp, color: C.COLD, below: true, label: "Low (mean)" }] }] });
    }
    if (k === "spread_mx") {
      const q = (S_, p) => stats(S_, (a) => pct(a, p));
      return Object.assign(base, { title: `${name} Max / Min Temperature Spread`, panels: [{ wt: 1.6, ylab: "\u00b0F", ref: 32, items: [
        { t: "band", x: mx.x, lo: q(mx, 0.1), hi: q(mx, 0.9), color: C.WARM, alpha: 0.2, label: "Max 10-90%" }, { t: "band", x: mx.x, lo: q(mx, 0.25), hi: q(mx, 0.75), color: C.WARM, alpha: 0.4 }, { t: "line", x: mx.x, y: q(mx, 0.5), color: C.WARM, lw: 2.5, label: "Max median" },
        { t: "band", x: mn.x, lo: q(mn, 0.1), hi: q(mn, 0.9), color: C.COLD, alpha: 0.2, label: "Min 10-90%" }, { t: "band", x: mn.x, lo: q(mn, 0.25), hi: q(mn, 0.75), color: C.COLD, alpha: 0.4 }, { t: "line", x: mn.x, y: q(mn, 0.5), color: C.COLD, lw: 2.5, label: "Min median" }] }] });
    }
    const hb = [], lb = [];
    for (const d of days) {
      const per = (S_, fn) => S_.m.map((a) => { const v = a.filter((_, i) => S_.x[i] > d.a && S_.x[i] <= d.b + 3 * 36e5 && a[i] != null); return v.length >= 2 ? fn(...v) : null; });
      const hi = per(mx, Math.max), lo = per(mn, Math.min), box = (a) => ({ xa: d.a, xb: d.b, p10: pct(a, 0.1), p25: pct(a, 0.25), p50: pct(a, 0.5), p75: pct(a, 0.75), p90: pct(a, 0.9) });
      if (hi.some((v) => v != null)) hb.push(box(hi)); if (lo.some((v) => v != null)) lb.push(box(lo));
    }
    return Object.assign(base, { title: `${name} Daily High / Low Temperature`, sub: base.sub + " \u00b7 dots = median of members", panels: [{ wt: 1.6, ylab: "\u00b0F", ref: 32, items: [{ t: "boxes", boxes: hb, color: "#c8553d", label: "High: 25-75% box, 10-90% whisker" }, { t: "boxes", boxes: lb, color: "#4b7fc4", below: true, label: "Low: 25-75% box, 10-90% whisker" }] }] });
  }
  if (k === "z500t850") {
    const z = memTown(M, T, town, "gh", (v) => v / 10), t8 = memTown(M, T, town, "t850", deg);
    if (!z || !t8) return memNote("500 mb height and 850 mb temperature plumes");
    return Object.assign(base, { title: `${name} 500 mb Height and 850 mb Temperature`, panels: [
      { wt: 1.1, ylab: "dam", items: [{ t: "multi", x: z.x, ys: z.m, color: "#b6a6ff", lw: 0.8, alpha: 0.5 }, { t: "line", x: z.x, y: stats(z, mean), color: C.MEAN, lw: 3, label: "500 mb height mean" }] },
      { wt: 1.1, ylab: "\u00b0C", ref: 0, items: [{ t: "multi", x: t8.x, ys: t8.m, color: "#ff9f80", lw: 0.8, alpha: 0.5 }, { t: "line", x: t8.x, y: stats(t8, mean), color: C.MEAN, lw: 3, label: "850 mb temp mean" }] }] });
  }
  if (k.startsWith("grid_")) {
    const days = dayBins(T.x[0], T.x[T.x.length - 1]).filter((d) => d.b - d.a >= 6 * 36e5);
    const cols = days.map((d) => [fmt({ weekday: "short" }).format(d.a + 1), fmt({ month: "numeric", day: "numeric" }).format(d.a + 1)]);
    const inDay = (S_, d) => S_.x.map((x, i) => i).filter((i) => S_.x[i] > d.a && S_.x[i] <= d.b + (S_ === mx || S_ === mn ? 3 * 36e5 : 0));
    const atEnd = (S_, d) => { const ii = S_.x.map((x, i) => i).filter((i) => S_.x[i] <= d.b + 1); return ii.length ? ii[ii.length - 1] : null; };
    const atStart = (S_, d) => { const ii = S_.x.map((x, i) => i).filter((i) => S_.x[i] <= d.a + 1); return ii.length ? ii[ii.length - 1] : null; };
    const G = { grid_mx: [mx, "Daily Max Temp (\u00b0F)", (a, d) => mxOf(a, inDay(mx, d), Math.max), TEMP_RAMP, (v) => Math.round(v)],
      grid_mn: [mn, "Daily Min Temp (\u00b0F)", (a, d) => mxOf(a, inDay(mn, d), Math.min), TEMP_RAMP, (v) => Math.round(v)],
      grid_tp24: [tp, "24-Hour Precipitation (in), midnight to midnight PT", (a, d) => diff(a, atStart(tp, d), atEnd(tp, d)), QPF_RAMP, (v) => v.toFixed(2).replace(/^0/, "")],
      grid_tp: [tp, "Total Precipitation to end of day (in)", (a, d) => { const j = atEnd(tp, d); return j == null ? null : a[j]; }, QPF_RAMP, (v) => v.toFixed(2).replace(/^0/, "")],
      grid_sf24: [sf, "24-Hour Snow 10:1 (in)", (a, d) => diff(a, atStart(sf, d), atEnd(sf, d)), SNOW_RAMP, (v) => v.toFixed(1)],
      grid_sf: [sf, "Total Snow 10:1 to end of day (in)", (a, d) => { const j = atEnd(sf, d); return j == null ? null : a[j]; }, SNOW_RAMP, (v) => v.toFixed(1)],
      grid_gust: [memTown(M, T, town, "10fg", deg), "Daily Max Gust (mph)", null, GUST_RAMP, (v) => Math.round(v)],
      grid_cape: [memTown(M, T, town, "mucape", deg), "Daily Max MUCAPE (J/kg)", null, CAPE_RAMP, (v) => Math.round(v)] }[k];
    const S_ = G[0]; if (!S_) return memNote("Member grids");
    const cell = G[2] || ((a, d) => mxOf(a, inDay(S_, d), Math.max));
    const memRows = S_.m.map((a) => days.map((d) => cell(a, d)));
    const rowsMean = days.map((_, j) => mean(memRows.map((r) => r[j])));
    const rows = [{ label: "MEAN", bold: true, v: rowsMean }, ...memRows.map((v, i) => ({ label: `M${i + 1}`, v }))];
    const cut = cols.length; const ok = rowsMean.some((v) => v != null); if (!ok) return memNote("Member grids");
    return Object.assign(base, { grid: true, title: `${name} ${G[1].split(" (")[0]}: Members and Mean`, sub: base.sub, cols: cols.slice(0, cut), rows, color: G[3], fmt: G[4], note: `${G[1]}. Rows: ensemble mean, then each member (${memRows.length}). Columns: Pacific days. Swipe sideways on phones.` });
  }
  return { empty: ["Not available yet", prod.note || "This chart is not drawn on the fast site yet."] };
}
const MEM_HINT = "47 places (the old site's meteogram towns, the mountain passes and a few more)";
function mxOf(a, idx, fn) { const v = idx.map((i) => a[i]).filter((x) => x != null); return v.length ? fn(...v) : null; }
function diff(a, i, j) { if (j == null) return null; const b = i == null ? 0 : a[i]; return a[j] == null || b == null ? null : Math.max(0, a[j] - b); }
function dayBins(x0, x1) {   // Pacific calendar days overlapping [x0, x1]
  const out = []; let a = x0; for (let t = Math.ceil(x0 / 36e5) * 36e5; t <= x1 + 36e5; t += 36e5) if (ptHour(t) === 0 && t > a) { out.push({ a, b: Math.min(t, x1) }); a = t; }
  if (x1 > a) out.push({ a, b: x1 }); return out.filter((d) => d.b > d.a);
}
function wetBulbF(tF, dF) { if (tF == null || dF == null) return null; const t = (tF - 32) / 1.8, d = (dF - 32) / 1.8;
  const es = (x) => 6.112 * Math.exp(17.67 * x / (x + 243.5)); const rh = Math.max(1, Math.min(100, 100 * es(d) / es(t)));
  const w = t * Math.atan(0.151977 * Math.sqrt(rh + 8.313659)) + Math.atan(t + rh) - Math.atan(rh - 1.676331) + 0.00391838 * Math.pow(rh, 1.5) * Math.atan(0.023101 * rh) - 4.686035; return w * 1.8 + 32; }

async function multiRun(sec, prod, town, name, base, runs) {
  const m = sec.id, k = prod.kind, list = [];
  for (const c of runs.slice(0, 4)) { let D = null; try { D = await ptsSeries(m, c); } catch (e) { D = null; } if (D) { const T = townSeries(D, town); if (T) list.push([c, T]); } }
  if (!list.length) return { empty: ["Not generated yet", "No run with town data yet."] };
  const pick = (T) => {
    if (k === "mr_t2m") return T.t2m; if (k === "mr_tmax") return T.maxt; if (k === "mr_tmin") return T.mint;
    if (k === "mr_qpf") return T.apcpTot; if (k === "mr_snow") return T.snowTot;
    if (k === "mr_qpf6") return T.apcpTot && winSum(T, T.apcpTot, 6); if (k === "mr_qpf24") return T.apcpTot && winSum(T, T.apcpTot, 24);
    if (k === "mr_snow6") return T.snowTot && winSum(T, T.snowTot, 6); if (k === "mr_snow24") return T.snowTot && winSum(T, T.snowTot, 24);
  };
  const greys = ["#b5b7bb", "#8c8f95", "#6c6f75"], temp = /t2m|tmax|tmin/.test(k);
  const items = []; let x0 = Infinity, x1 = -Infinity;
  list.forEach(([c, T], i) => { const y = pick(T); if (!y) return; x0 = Math.min(x0, T.x[0]); x1 = Math.max(x1, T.x[T.x.length - 1]);
    const fin = y.filter((v) => v != null).pop(); const tail = temp || !/mr_qpf$|mr_snow$/.test(k) ? "" : ` (${fin == null ? "\u2013" : fin.toFixed(2)} in)`;
    items.push({ t: "line", x: T.x, y, color: i === 0 ? C.WARM : greys[i - 1] || "#555", lw: i === 0 ? 3 : 1.6, label: `${runLabel(m, c)}${i === 0 ? " (newest)" : ""}${tail}` }); });
  if (!items.length) return { empty: ["Not in this model", "This model run has no data for this product."] };
  items.reverse();
  const what = { mr_t2m: "2 m Temperature", mr_tmax: "6-h Max Temperature", mr_tmin: "6-h Min Temperature", mr_qpf6: "6-Hour Precipitation", mr_qpf24: "24-Hour Precipitation", mr_qpf: "Total Precipitation", mr_snow6: "6-Hour Snow (10:1)", mr_snow24: "24-Hour Snow (10:1)", mr_snow: "Total Snow (10:1)" }[k];
  return Object.assign(base, { x0, x1, title: `${name} ${sec.label} Multi-run ${what}`, sub: `${ENS(m) ? "Ensemble mean, " : ""}last ${items.length} run${items.length > 1 ? "s" : ""} on the fast site, newest bold`, panels: [{ wt: 1.6, ylab: temp ? "\u00b0F" : "inches", ref: temp ? 32 : null, zero: !temp, minTop: temp ? null : 0.1, legend: temp ? "right" : "left", items }] });
}

/* ---------------- page ---------------- */
async function townsFor(sec) {
  for (const c of runsOf(sec.id)) { try { const R = await loadRun(sec.id, c); if (R.points) return R.points; } catch (e) { /* next */ } }
  return [];
}
function readHash() { const q = new URLSearchParams(location.hash.slice(1)); S.sec = q.get("s") || ""; S.town = q.get("w") || ""; S.prod = q.get("p") || ""; }
function writeHash() { const q = new URLSearchParams({ s: S.sec, w: S.town, p: S.prod }); history.replaceState(null, "", "#" + q.toString()); }
function btn(label, onClick, attrs = {}) { const b = document.createElement("button"); b.type = "button"; b.textContent = label; b.onclick = onClick; for (const [k, v] of Object.entries(attrs)) if (v != null) b.setAttribute(k, v); return b; }
function emptyState(el, title, body, sug = []) {
  el.replaceChildren(); const h = document.createElement("p"); h.className = "empty-title"; h.textContent = title; const p = document.createElement("p"); p.className = "empty-body"; p.textContent = body; el.append(h, p);
  if (sug.length) { const w = document.createElement("div"); w.className = "empty-try"; const l = document.createElement("span"); l.textContent = "Available:"; w.appendChild(l); for (const [lab, fn] of sug.slice(0, 8)) w.appendChild(btn(lab, fn)); el.appendChild(w); }
  el.hidden = false;
}
let LAST = null;
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
  if (!pts.some((p) => p.n === S.town)) S.town = (pts.find((p) => p.n === "Seattle") || pts[0] || { n: "Seattle" }).n;
  const town = $("town"); town.replaceChildren();
  for (const [lab, arr] of [["Towns (A\u2013Z)", pts.filter((p) => p.k !== "pass")], ["Mountain passes (A\u2013Z)", pts.filter((p) => p.k === "pass")]]) {
    if (!arr.length) continue; const g = document.createElement("optgroup"); g.label = lab;
    for (const p of [...arr].sort((a, b) => a.n.localeCompare(b.n))) g.appendChild(new Option(placeLabel(p), p.n)); town.appendChild(g);
  }
  if (!pts.length) town.appendChild(new Option("(no towns yet)", S.town));
  town.value = S.town; town.onchange = () => { S.town = town.value; render(); };
  if (!sec.products.some((p) => p.id === S.prod)) S.prod = sec.products[0].id;
  const sel = $("mproduct"); sel.replaceChildren();
  for (const p of sec.products) { const o = new Option(p.label + (p.kind ? "" : " (not on the fast site yet)"), p.id); if (!p.kind) o.className = "na"; sel.add(o); }
  sel.value = S.prod; sel.onchange = () => { S.prod = sel.value; render(); };
  writeHash();
  const prod = sec.products.find((p) => p.id === S.prod), P = pts.find((p) => p.n === S.town);
  $("mcap-left").textContent = `${sec.label} \u00b7 ${prod.label} \u00b7 ${P ? placeLabel(P) : S.town}`; $("mcap-right").textContent = "";
  const cv = $("mchart"), empty = $("meteo-empty"), dl = $("dl-meteo"), box = $("mstage");
  dl.setAttribute("aria-disabled", "true"); dl.removeAttribute("href");
  if (!prod.kind) { cv.hidden = true; emptyState(empty, "Not on the fast site yet", prod.note || "", altProducts(sec)); $("mnote").textContent = ""; return; }
  const ld = $("meteo-loader"); const lt = setTimeout(() => (ld.hidden = false), 150);
  let spec; try { spec = await build(sec, prod, S.town); } catch (e) { spec = { empty: ["Could not load", "The data for this chart failed to download. Reload the page to try again."] }; console.error(e); }
  clearTimeout(lt); ld.hidden = true; if (tok !== S.tok) return;
  if (spec.empty) { cv.hidden = true; emptyState(empty, spec.empty[0], spec.empty[1], spec.sug === "mem" ? memTowns(sec) : spec.sug === "none" ? [] : altProducts(sec)); $("mnote").textContent = ""; LAST = null; return; }
  empty.hidden = true; cv.hidden = false; LAST = spec;
  draw();
  $("mcap-right").textContent = `${S.man.models[sec.id].site} ${runLabel(sec.id, spec.run)}`;
  $("mnote").textContent = spec.grid ? "" : spec.note || "";
}
function draw() {
  if (!LAST) return; const cv = $("mchart"), box = $("mstage");
  if (LAST.grid) drawGrid(cv, box, LAST); else drawChart(cv, box, LAST);
  cv.setAttribute("aria-label", `${LAST.title}. ${LAST.sub}`);
  const dl = $("dl-meteo"); cv.toBlob((b) => { if (!b) return; if (dl._u) URL.revokeObjectURL(dl._u); dl._u = URL.createObjectURL(b); dl.href = dl._u; dl.download = `${S.sec}_${S.prod}_${S.town.replace(/\W+/g, "_")}.png`; dl.removeAttribute("aria-disabled"); }, "image/png");
}
function sameKind(pid, s) { const cur = SECTIONS.flatMap((x) => x.products).find((p) => p.id === pid); const m = cur && s.products.find((p) => p.kind && p.kind === cur.kind); return (m || s.products.find((p) => p.kind) || s.products[0]).id; }
function altProducts(sec) { return sec.products.filter((p) => p.kind && p.id !== S.prod).slice(0, 6).map((p) => [p.label, () => { S.prod = p.id; render(); }]); }
function memTowns(sec) { const want = ["Seattle", "Spokane", "Yakima", "Bellingham", "Snoqualmie", "Stevens"]; return want.filter((n) => n !== S.town).map((n) => [n === "Snoqualmie" || n === "Stevens" ? n + " Pass" : n, () => { S.town = n; render(); }]); }
let rT = null; let lastW = 0;
addEventListener("resize", () => { const w = $("mstage").clientWidth; if (w === lastW) return; lastW = w; clearTimeout(rT); rT = setTimeout(draw, 150); });
addEventListener("hashchange", () => { const a = [S.sec, S.town, S.prod].join("|"); readHash(); if ([S.sec, S.town, S.prod].join("|") !== a) { if (!secObj()) S.sec = "eps"; render(); } });
(async function init() {
  readHash(); if (!secObj()) S.sec = "eps";
  try { await Promise.race([Promise.all(["800 16px Montserrat", "600 12px Montserrat", "500 11px Montserrat"].map((f) => document.fonts.load(f))), new Promise((r) => setTimeout(r, 2500))]); } catch (e) { /* system font */ }
  try { S.man = await getJSON(DATA + "manifest.json", true); } catch (e) { $("stamp").textContent = "Could not load the model list. Reload the page."; return; }
  const newest = Object.keys(S.man.runs).map((m) => runsOf(m)[0]).filter(Boolean).sort().pop();
  if (newest) $("stamp").textContent = `Newest run ${newest.slice(8)}Z ${+newest.slice(4, 6)}-${+newest.slice(6, 8)} \u00b7 times are PT`;
  lastW = $("mstage").clientWidth; render();
})();
