// Tides viewer (Benjamin t3011u / wording t3023u, 2026-11-14): NOAA official tide prediction, observed water level, and an experimental
// "Conditional Prediction" = official prediction + NOAA STOFS surge forecast (which already includes low pressure and wind driven
// coastal waves), with a fading correction to the current observed residual. The 30 day average offset is used only after the STOFS
// forecast ends or if it is missing. The inverse barometer figure is info only (already included in STOFS) and is not added on top.
// All data is public NOAA (CO-OPS API with CORS, STOFS on the NOAA Open Data bucket). No keys. Times shown in Pacific time.
// window.TIDE.draw(ctx, W, H, opt) draws the chart into any 2D context in CSS px (Studio draws it into its frames).
(() => {
"use strict";
const API = "https://api.tidesandcurrents.noaa.gov/api/prod/datagetter";
const MD = "https://api.tidesandcurrents.noaa.gov/mdapi/prod/webapi/stations/";
const S3 = "https://noaa-gestofs-pds.s3.amazonaws.com/";
const TZ = "America/Los_Angeles";
// Benjamin t3044u: list A to Z by name (default stays Westport 9441102). Birch Bay has no NOAA gauge, prediction station or
// STOFS point of its own (CO-OPS metadata, 11-14); it uses Cherry Point 9449424, the nearest NOAA gauge, about 4 mi south on the same shore.
const STATIONS = [
  ["9439040", "Astoria, OR"], ["birchbay", "Birch Bay, WA"], ["9449424", "Cherry Point, WA"], ["9449880", "Friday Harbor, WA"],
  ["9442396", "La Push, WA"], ["9443090", "Neah Bay, WA"], ["9444090", "Port Angeles, WA"], ["9444900", "Port Townsend, WA"],
  ["9447130", "Seattle, WA"], ["9446484", "Tacoma, WA"], ["9440910", "Toke Point, WA"], ["9441102", "Westport, WA"],
];
const ALIAS = {"birchbay": "9449424"};
const sidOf = (k) => ALIAS[k] || k;
const stLabel = (k) => ALIAS[k] ? `Cherry Point ${ALIAS[k]}` : k;
// Official NWS coastal flood levels, ft MLLW, triple-checked 2026-11-14 by tools/fast/tide_archive/flood_verify.py:
// S1 CO-OPS mdapi nws_* (with datums.json), S2 Tides & Currents inundation dashboard file, S3 NWS NWPS gauge where one exists.
// A level is drawn only when the live mdapi value still matches this table within 0.05 ft. NOS derived thresholds are not drawn.
const FLOOD_VERIFIED = "2026-11-14";
const FLOOD = {"9439040": {"minor": 12.01, "moderate": 14.51}, "9440910": {"minor": 11.02, "moderate": 14.52}, "9441102": {"minor": 10.94, "moderate": 11.39, "major": 11.84}, "9442396": {"minor": 11.11}, "9443090": {"minor": 10.58}, "9444090": {"minor": 9.17}, "9444900": {"minor": 11.37, "moderate": 11.82}, "9446484": {"minor": 14.07, "moderate": 14.77, "major": 15.17}, "9447130": {"minor": 13.46, "moderate": 14.36, "major": 14.76}, "9449424": {"minor": 11.0, "moderate": 12.0, "major": 13.0}, "9449880": {"minor": 9.51, "moderate": 10.01, "major": 10.51}};
const FCOL = { minor: "#ff7a45", moderate: "#e6194b", major: "#c74bff" };
const FLV = [["minor", "Minor"], ["moderate", "Moderate"], ["major", "Major"]];
const DAYS = [3, 5, 7, 9, 14, 17, 21, 30];
const LEADS = [0, 12, 24, 48], SDAYS = [3, 7];
// Conditional archive: 6-hourly snapshots per station written by tools/fast/tide_archive/tide_archive.py (GitHub Actions) to the
// orphan branch "tide-archive" of the public repo; raw.githubusercontent.com serves it with CORS *. Not R2.
const ARCH = window.TIDE_ARCH || "https://raw.githubusercontent.com/wawxchasermodels/wx-models/tide-archive/v1/";
const COL = { pred: "#5aa9ff", obs: "#ff5d5d", cond: "#ffb02e", ver: "rgba(255,222,160,0.85)", now: "#f4f2ee", flood: "#ff7a45", floodMod: "#e6194b", floodMaj: "#c74bff", grid: "#2c3039", axis: "#a7abb3", text: "#f4f2ee", bg: "#15171c" };
const H6 = 6 * 60000, HR = 3600000, DAY = 86400000;
const TAU_BIAS = 12 * HR, TAU_RELAX = 24 * HR, SLOW_DAYS = 30;
const Q = new URLSearchParams(location.search), STUDIO = !!Q.get("studio");
const $ = (id) => document.getElementById(id);
const T = { st: Q.get("st") || localStorage.getItem("tide:st") || "9441102", from: Q.get("from") || "", days: +(Q.get("days") || 9),
  vl: +(Q.get("vl") ?? 24), sd: +(Q.get("sd") || 7) };
if (!LEADS.includes(T.vl)) T.vl = 24;
if (!SDAYS.includes(T.sd)) T.sd = 7;
if (!STATIONS.some((s) => s[0] === T.st)) T.st = "9441102";
if (!DAYS.includes(T.days)) T.days = 9;
let D = null, seq = 0;
window.__tideDrawn = 0;

// ---- time helpers (Pacific) ----
const fmtParts = new Intl.DateTimeFormat("en-US", { timeZone: TZ, year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", second: "2-digit", hourCycle: "h23" });
function tzOff(ms) { const p = {}; for (const x of fmtParts.formatToParts(new Date(ms))) p[x.type] = x.value;
  return (Date.UTC(+p.year, +p.month - 1, +p.day, +p.hour % 24, +p.minute, +p.second) - Math.floor(ms / 1000) * 1000) / 60000; }
function localMidnight(y, m, d) { let t = Date.UTC(y, m - 1, d, 8); t = Date.UTC(y, m - 1, d) - tzOff(t) * 60000; return Date.UTC(y, m - 1, d) - tzOff(t) * 60000; }
function ymdLocal(ms) { const p = {}; for (const x of fmtParts.formatToParts(new Date(ms))) p[x.type] = x.value; return `${p.year}-${p.month}-${p.day}`; }
const fDay = new Intl.DateTimeFormat("en-US", { timeZone: TZ, weekday: "short", month: "short", day: "numeric" });
const fMd = new Intl.DateTimeFormat("en-US", { timeZone: TZ, month: "short", day: "numeric" });
const fTime = new Intl.DateTimeFormat("en-US", { timeZone: TZ, hour: "numeric", minute: "2-digit" });
const fZone = new Intl.DateTimeFormat("en-US", { timeZone: TZ, timeZoneName: "short" });
const zoneName = (ms) => (fZone.formatToParts(new Date(ms)).find((x) => x.type === "timeZoneName") || {}).value || "PT";
const gmt = (ms) => { const d = new Date(ms), z = (n) => String(n).padStart(2, "0"); return `${d.getUTCFullYear()}${z(d.getUTCMonth() + 1)}${z(d.getUTCDate())} ${z(d.getUTCHours())}:${z(d.getUTCMinutes())}`; };
const parseT = (s) => Date.UTC(+s.slice(0, 4), +s.slice(5, 7) - 1, +s.slice(8, 10), +s.slice(11, 13), +s.slice(14, 16));

function range() {
  const now = Date.now();
  let start;
  if (/^\d{4}-\d{2}-\d{2}$/.test(T.from)) { const [y, m, d] = T.from.split("-").map(Number); start = localMidnight(y, m, d); }
  else { const [y, m, d] = ymdLocal(now - 2 * DAY).split("-").map(Number); start = localMidnight(y, m, d); }
  const [y2, m2, d2] = ymdLocal(start + T.days * DAY + 12 * HR).split("-").map(Number);
  return { start, end: localMidnight(y2, m2, d2), now };
}

// ---- data ----
async function getJSON(u) { const r = await fetch(u, { cache: "no-store" }); if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.json(); }
async function coops(product, st, b, e, extra) {
  const out = [];
  for (let t = b; t < e; t += 30 * DAY) {
    const u = `${API}?product=${product}&application=wx_models_tides&station=${st}&begin_date=${encodeURIComponent(gmt(t))}&end_date=${encodeURIComponent(gmt(Math.min(e, t + 30 * DAY)))}&time_zone=gmt&units=english&format=json${extra || ""}`;
    const j = await getJSON(u); const a = j.predictions || j.data || [];
    for (const p of a) { const v = parseFloat(p.v); if (isFinite(v)) out.push([parseT(p.t), v]); }
  }
  out.sort((a, b) => a[0] - b[0]); const o2 = []; for (const p of out) if (!o2.length || p[0] > o2[o2.length - 1][0]) o2.push(p); return o2;
}
async function meta(st) {
  try {
    const [m, dj] = await Promise.all([getJSON(`${MD}${st}.json?expand=floodlevels`), getJSON(`${MD}${st}/datums.json`)]);
    const s = m.stations[0], fl = s.floodlevels || {}, mllw = ((dj.datums || []).find((x) => x.name === "MLLW") || {}).value;
    // t3044u: minor, moderate and major = the official NWS levels, drawn only where the live mdapi value matches the triple-checked table
    const floods = [], floodSkip = [], ok = FLOOD[st] || {};
    if (mllw != null) for (const [k, lab] of FLV) { const nws = fl[`nws_${k}`];
      if (nws == null) { if (ok[k] != null) floodSkip.push({ k, why: "missing in mdapi" }); continue; }
      const v = Math.round((nws - mllw) * 100) / 100;
      if (ok[k] != null && Math.abs(v - ok[k]) <= 0.05) floods.push({ k, lab, v, src: "NWS" }); else floodSkip.push({ k, v, table: ok[k] ?? null, why: ok[k] == null ? "not verified" : "differs from verified table" }); }
    const flood = floods.find((f) => f.k === "minor") || null;
    return { shef: s.shefcode || "", flood, floods, floodSkip };
  } catch (e) { return { shef: "", flood: null, floods: [], floodSkip: [] }; }
}
async function stofsCycle(now) {
  const cands = []; for (let k = 0; k < 10; k++) { const t = Math.floor(now / (6 * HR)) * 6 * HR - k * 6 * HR; cands.push(t); }
  const key = (t) => { const d = new Date(t), z = (n) => String(n).padStart(2, "0"); return `stofs_2d_glo.${d.getUTCFullYear()}${z(d.getUTCMonth() + 1)}${z(d.getUTCDate())}/stofs_2d_glo.t${z(d.getUTCHours())}z.points.swl.shef`; };
  const hits = await Promise.all(cands.map(async (t) => { try { const r = await fetch(`${S3}?list-type=2&prefix=${encodeURIComponent(key(t))}`); const x = await r.text(); return /<KeyCount>[1-9]/.test(x) ? t : 0; } catch (e) { return 0; } }));
  const t = hits.find((h) => h); return t ? { t, url: S3 + key(t) } : null;
}
let shefCache = { url: "", txt: "" };
async function stofsSeries(shef, cyc) {
  if (!shef || !cyc) return null;
  if (shefCache.url !== cyc.url) { const r = await fetch(cyc.url); if (!r.ok) return null; shefCache = { url: cyc.url, txt: await r.text() }; }
  const L = shefCache.txt.split("\n"); let i = L.findIndex((l) => l.startsWith(`.E ${shef} `)); if (i < 0) return null;
  const h = L[i], m = h.match(/(\d{8}) Z DH(\d{2})(\d{2}).*?DIN(\d+)\/(.*)$/); if (!m) return null;
  const t0 = Date.UTC(+m[1].slice(0, 4), +m[1].slice(4, 6) - 1, +m[1].slice(6, 8), +m[2], +m[3]), step = +m[4] * 60000;
  const vals = m[5].split("/").map((s) => s.trim()).filter(Boolean);
  for (i++; i < L.length && /^\.E\d+\s/.test(L[i]); i++) vals.push(...L[i].replace(/^\.E\d+\s+/, "").split("/").map((s) => s.trim()).filter(Boolean));
  const out = []; vals.forEach((v, k) => { const x = parseFloat(v); if (isFinite(x) && x > -90) out.push([t0 + k * step, x]); });
  return out.length ? { t0, step, pts: out } : null;
}
async function pressure(st) {
  try { const j = await getJSON(`${API}?product=air_pressure&application=wx_models_tides&station=${st}&range=3&time_zone=gmt&units=metric&format=json`);
    const a = (j.data || []).filter((p) => isFinite(parseFloat(p.v))); if (!a.length) return null; const p = a[a.length - 1]; return { t: parseT(p.t), hpa: parseFloat(p.v) };
  } catch (e) { return null; }
}

async function archive(st, b, e) {   // snapshots issued in [b, e] (ms); missing months are fine (archive not started yet)
  const months = []; for (let d = new Date(b); d.getTime() <= e + 31 * DAY; d.setUTCMonth(d.getUTCMonth() + 1, 1)) { const m = `${d.getUTCFullYear()}-${String(d.getUTCMonth() + 1).padStart(2, "0")}`; if (!months.includes(m) && Date.UTC(d.getUTCFullYear(), d.getUTCMonth(), 1) <= e) months.push(m); }
  let have = null, calib = null; try { const r = await fetch(`${ARCH}index.json`, { cache: "no-cache" }); if (r.ok) { const j = await r.json(); have = (j.months || {})[st] || []; calib = (j.calib || {})[st] || null; } } catch (err) { have = null; }
  if (!have) return { issues: [], calib: null };
  const got = await Promise.all(months.filter((m) => have.includes(m)).map(async (m) => { try { const r = await fetch(`${ARCH}${st}/${m}.json`, { cache: "no-cache" }); return r.ok ? (await r.json()).issues || [] : []; } catch (err) { return []; } }));
  return { issues: got.flat().filter((i) => i.t >= b && i.t <= e && Array.isArray(i.r)).sort((x, y) => x.t - y.t), calib };
}
// daily self-calibration (tools/fast/tide_archive/calibrate.py): correction by lead, 0 at lead 0, range values at the range centres
function calAt(leadH, cal) { if (!cal) return 0; const pts = [[0, 0]].concat(cal.centres.map((x, i) => [x, cal.c[i].corr]));
  if (leadH >= pts[pts.length - 1][0]) return pts[pts.length - 1][1]; if (leadH <= 0) return 0;
  for (let i = 1; i < pts.length; i++) if (leadH <= pts[i][0]) return pts[i - 1][1] + (pts[i][1] - pts[i - 1][1]) * (leadH - pts[i - 1][0]) / (pts[i][0] - pts[i - 1][0]); return 0; }
// What the Conditional line said for each past time t, from the newest snapshot issued at least `lead` hours before t
// (snapshots are 6-hourly, so the lead is lead..lead+6 h; up to lead+12 h if one run was missed).
function verified(pred, issues, lead, t1, tStart, key) {
  const out = []; if (!lead || !issues.length) return out; let k = 0;
  for (const [t, p] of pred) { if (t < tStart || t > t1) continue;
    while (k + 1 < issues.length && issues[k + 1].t <= t - lead * HR) k++;
    const I = issues[k]; if (!I || I.t > t - lead * HR || t - I.t > (lead + 12) * HR) continue;
    const r = (key && I[key]) || I.r, f = (t - I.t) / HR, j = Math.floor(f); if (j + 1 >= r.length) continue;
    out.push([t, p + r[j] + (r[j + 1] - r[j]) * (f - j), I.kind === "archive" ? 1 : 0, I.t, !!(key && I[key])]); }
  return out;
}
function verStats(pred, obs, ver, t0, t1, verRaw) {
  const S = verStats1(pred, obs, ver, t0, t1); if (!S || !verRaw) return S;
  const R = verStats1(pred, obs, verRaw, t0, t1, new Set(ver.map((v) => v[0]))); if (R) { S.raw = R.cond; if (S.peak && R.peak) S.peak.raw = R.peak.cond; } return S; }
function verStats1(pred, obs, ver, t0, t1, only) {   // hourly points in [t0, t1] where observed, official and verified all exist
  const pm = new Map(pred), om = new Map(obs), vm = new Map(ver.filter((v) => !only || only.has(v[0])).map((v) => [v[0], v]));
  let n = 0, nh = 0, aeC = 0, bC = 0, aeO = 0, bO = 0;
  for (let t = Math.ceil(t0 / HR) * HR; t <= t1; t += HR) { const o = om.get(t), p = pm.get(t), v = vm.get(t); if (o == null || p == null || !v) continue;
    n++; if (!v[2]) nh++; aeC += Math.abs(v[1] - o); bC += v[1] - o; aeO += Math.abs(p - o); bO += p - o; }
  if (!n) return null;
  // peak high tide: the highest observed high water in the window (max within +-90 min of each predicted high)
  let pk = null;
  for (const e of extremes(pred, t0, t1)) { if (!e.hi) continue; let oM = null, oT = 0, pM = -1e9, vM = -1e9, vOk = 0, cnt = 0;
    for (const [t, v] of obs) { if (t < e.t - 90 * 60000) continue; if (t > e.t + 90 * 60000) break; cnt++; if (oM == null || v > oM) { oM = v; oT = t; } }
    for (let t = e.t - 90 * 60000; t <= e.t + 90 * 60000; t += H6) { const p = pm.get(t); if (p != null && p > pM) pM = p; const v = vm.get(t); if (v) { vOk++; if (v[1] > vM) vM = v[1]; } }
    if (oM == null || cnt < 20 || vOk < 25) continue;
    if (!pk || oM > pk.obs) pk = { t: oT, obs: oM, cond: vM - oM, off: pM - oM }; }
  return { n, nh, cond: { mae: aeC / n, bias: bC / n }, off: { mae: aeO / n, bias: bO / n }, peak: pk };
}

function interp(pts, t) {   // linear on a sorted [t,v] array, null outside
  if (!pts || !pts.length || t < pts[0][0] || t > pts[pts.length - 1][0]) return null;
  let lo = 0, hi = pts.length - 1; while (hi - lo > 1) { const mid = (lo + hi) >> 1; if (pts[mid][0] <= t) lo = mid; else hi = mid; }
  const a = pts[lo], b = pts[hi]; if (b[0] === a[0]) return a[1]; return a[1] + (b[1] - a[1]) * (t - a[0]) / (b[0] - a[0]);
}

async function load() {
  const my = ++seq; const R = range(); const now = R.now;
  setMsg("Loading tides\u2026");
  const key = T.st, st = sidOf(key), b0 = Math.min(R.start, now - SLOW_DAYS * DAY), eP = Math.max(R.end, now) + 3 * HR;
  try {
    const [pred, obs, md, cyc, pr, arch] = await Promise.all([
      coops("predictions", st, b0, eP, "&datum=MLLW&interval=6"),
      coops("water_level", st, b0, Math.min(R.end, now) + H6, "&datum=MLLW"),
      meta(st), stofsCycle(now).catch(() => null), pressure(st),
      archive(st, Math.min(R.start, now - T.sd * DAY) - 61 * HR, Math.min(R.end, now)).catch(() => ({ issues: [], calib: null }))]);
    // Benjamin t3018u: the chart and stats show the RAW Conditional; the daily calibration is archived in the background only.
    const issues = arch.issues, calib = null, calibBg = arch.calib;
    if (my !== seq) return;
    if (!pred.length) throw new Error("no predictions returned");
    const pmap = new Map(pred);
    // residual = observed - predicted (6-min)
    const res = []; for (const [t, v] of obs) { const p = pmap.get(t); if (p != null) res.push([t, v - p]); }
    const tObs = obs.length ? obs[obs.length - 1][0] : null;
    const mean = (a) => a.length ? a.reduce((s, x) => s + x[1], 0) / a.length : null;
    const rSlow = mean(res.filter((r) => r[0] >= now - SLOW_DAYS * DAY));
    const rNow = tObs != null && now - tObs < 6 * HR ? mean(res.filter((r) => r[0] >= tObs - HR)) : null;
    let sto = null; try { sto = await stofsSeries(md.shef, cyc); } catch (e) { sto = null; }
    if (my !== seq) return;
    // STOFS sub-tidal water level (swl = combined - model tide: pressure + wind surge + STOFS sea level anomaly), 3 h running mean.
    // Hindcast 11-09..11-13 (9 cycles x 11 WA/OR stations, 3-72 h leads): swl + fading bias MAE 0.25 ft; cwl - official 0.35; persistence 0.88; official alone 1.40.
    let rs = null;
    if (sto) { const raw = sto.pts;
      const n = Math.max(1, Math.round(1.5 * HR / sto.step)); rs = raw.map((r, i) => { let s = 0, c = 0; for (let j = Math.max(0, i - n); j <= Math.min(raw.length - 1, i + n); j++) { s += raw[j][1]; c++; } return [r[0], s / c]; }); }
    const t0c = tObs != null && rNow != null ? tObs : now;   // the conditional line starts at the newest observation
    const rsNow = rs ? interp(rs, t0c) : null;
    const bias = rNow != null && rsNow != null ? rNow - rsNow : 0;
    const base = rSlow != null ? rSlow : 0;
    const rsEnd = rs && rs.length ? rs[rs.length - 1] : null;
    const resid = (t) => {
      const dt = t - t0c;
      if (rs && rsNow != null && t <= rsEnd[0]) return interp(rs, t) + bias * Math.exp(-dt / TAU_BIAS);
      if (rs && rsNow != null) { const rEnd = rsEnd[1] + bias * Math.exp(-(rsEnd[0] - t0c) / TAU_BIAS); return base + (rEnd - base) * Math.exp(-(t - rsEnd[0]) / TAU_RELAX); }
      const r0 = rNow != null ? rNow : base; return base + (r0 - base) * Math.exp(-dt / TAU_BIAS);
    };
    const cond = [], condRaw = []; if (R.end > t0c && (rNow != null || rs)) for (const [t, v] of pred) if (t >= t0c && t <= R.end) { const r = resid(t); condRaw.push([t, v + r]); cond.push([t, v + r]); }
    const name = (STATIONS.find((s) => s[0] === key) || [key, key])[1];
    const tPast = Math.min(R.end, tObs != null ? tObs : now);
    const verAll = verified(pred, issues, T.vl, tPast, Math.min(R.start, now - T.sd * DAY) - HR);   // raw snapshots (r)
    const ver = verAll.filter((p) => p[0] >= R.start - HR && p[0] <= R.end + HR);
    const stats = T.vl && tObs != null ? verStats(pred, obs, verAll, tObs - T.sd * DAY, tObs) : null;
    D = { st: key, sid: st, name, R, now, pred: pred.filter((p) => p[0] >= R.start - HR && p[0] <= R.end + HR), obs: obs.filter((p) => p[0] >= R.start - HR && p[0] <= R.end + HR),
      cond, condRaw, calib, calibBg, ver, stats, vl: T.vl, sd: T.sd, nIssues: issues.length, nArchive: issues.filter((i) => i.kind === "archive").length, rNow, rSlow, bias, cyc: sto ? cyc : null, stofsEnd: rsEnd ? rsEnd[0] : null, flood: md.flood, floods: md.floods || [], floodSkip: md.floodSkip || [], pr, tObs, method: sto && rsNow != null ? "stofs" : "persist" };
    setMsg(""); note(); draw(); window.__tideDrawn++;
  } catch (e) {
    if (my !== seq) return; D = null; setMsg(`Could not load tides for this station (${e.message || e}).`); window.__tideErr = String(e.message || e); window.__tideDrawn++;
  }
}

// ---- drawing ----
const sgn = (x, d = 1) => (x >= 0 ? "+" : "\u2212") + Math.abs(x).toFixed(d);
function niceStep(span, n) { const raw = span / n, p = Math.pow(10, Math.floor(Math.log10(raw))), f = raw / p; return (f < 1.5 ? 1 : f < 3 ? 2 : f < 7 ? 5 : 10) * p; }
function extremes(pts, t0, t1) {   // local highs/lows of the 6-min prediction (one per ~3 h window)
  const out = []; for (let i = 2; i < pts.length - 2; i++) { const [t, v] = pts[i]; if (t < t0 || t > t1) continue;
    const hi = v >= pts[i - 1][1] && v > pts[i + 1][1] && v >= pts[i - 2][1] && v > pts[i + 2][1];
    const lo = v <= pts[i - 1][1] && v < pts[i + 1][1] && v <= pts[i - 2][1] && v < pts[i + 2][1];
    if (hi || lo) { const last = out[out.length - 1]; if (last && t - last.t < 3 * HR && last.hi === hi) { if ((hi && v > last.v) || (lo && v < last.v)) out[out.length - 1] = { t, v, hi }; } else out.push({ t, v, hi }); } }
  return out; }

function drawChart(c, W, H, opt) {
  opt = opt || {}; const s = opt.scale || 1, portrait = H > W * 1.2;
  c.save(); c.fillStyle = opt.bg || COL.bg; c.fillRect(0, 0, W, H);
  const F = (w, px) => `${w} ${Math.round(px * s * 10) / 10}px Montserrat, system-ui, sans-serif`;
  if (!D) { c.font = F(700, 18); c.fillStyle = "#c9ced8"; c.textAlign = "center"; c.fillText(window.__tideErr ? "Could not load tides" : "Loading tides\u2026", W / 2, H / 2); c.restore(); return; }
  const { R } = D, pad = 14 * s;
  // header
  c.textBaseline = "alphabetic"; c.textAlign = "left"; c.fillStyle = COL.text;
  c.font = F(800, 22); const y1 = pad + 22 * s; c.fillText(`${D.name}  \u00b7  ${stLabel(D.st)}`, pad, y1);
  c.font = F(600, 13.5); c.fillStyle = COL.axis;
  c.fillText(`Water level, feet above MLLW  \u00b7  ${fMd.format(new Date(R.start))} \u2013 ${fMd.format(new Date(R.end - 1))}, ${new Date(R.end - 1).getUTCFullYear()}  \u00b7  ${zoneName(R.now)}`, pad, y1 + 21 * s);
  // legend
  const items = [["Official prediction", COL.pred, 2.2], ["Observed", COL.obs, 2.2], [D.calib ? "Conditional Prediction (experimental, calibrated)" : "Conditional Prediction (experimental)", COL.cond, 3.2]];
  if (D.ver.length) items.splice(2, 0, [`Conditional, verified (${D.ver.some((v) => v[4]) ? "calibrated, " : ""}issued ${D.vl}\u2013${D.vl + 6} h before)`, COL.ver, -2]);
  let dHi = -Infinity; for (const a of [D.pred, D.obs, D.cond, D.ver]) for (const p of a) if (p[1] > dHi) dHi = p[1];
  const fIn = (f) => f.v < dHi + 3;   // same "reasonably close" rule as the y range below
  for (const f of D.floods) items.push([`${f.lab} flood ${f.v.toFixed(1)} ft (${f.src}${fIn(f) ? "" : ", above chart"})`, FCOL[f.k], -1]);
  c.font = F(700, 13.5); let lx, ly; const sw = 26 * s, gap = 18 * s;
  const widths = items.map((it) => sw + 8 * s + c.measureText(it[0]).width);
  const legW = widths.reduce((a, b) => a + b, 0) + gap * (items.length - 1);
  c.font = F(800, 22); const titleW = c.measureText(`${D.name}  \u00b7  ${stLabel(D.st)}`).width; c.font = F(700, 13.5);
  const legTwoRows = portrait || legW > W - 2 * pad - titleW - 40 * s;
  const legend = (x0, y0, list) => { let x = x0; list.forEach((it, i) => { c.strokeStyle = it[1]; c.lineWidth = (it[2] === -1 ? 2 : it[2] === -2 ? 2 : it[2]) * s; c.setLineDash(it[2] === -1 ? [7 * s, 5 * s] : it[2] === -2 ? [5 * s, 4 * s] : []);
    c.beginPath(); c.moveTo(x, y0 - 5 * s); c.lineTo(x + sw, y0 - 5 * s); c.stroke(); c.setLineDash([]); c.fillStyle = COL.text; c.fillText(it[0], x + sw + 8 * s, y0); x += widths[items.indexOf(it)] + gap; }); };
  let top;
  if (!legTwoRows) { lx = W - pad - legW; ly = y1; legend(lx, ly, items); top = y1 + 40 * s; }
  else {   // greedy rows that fit the width (phones / 9:16)
    const rows = [[]]; let rw = 0; items.forEach((it, i) => { const w = widths[i]; if (rows[rows.length - 1].length && rw + gap + w > W - 2 * pad) { rows.push([]); rw = 0; } rw += (rows[rows.length - 1].length ? gap : 0) + w; rows[rows.length - 1].push(it); });
    rows.forEach((r, i) => legend(pad, y1 + 50 * s + i * 24 * s, r)); top = y1 + 50 * s + (rows.length - 1) * 24 * s + 18 * s; }
  // info lines (bottom)
  const info = [];
  if (ALIAS[D.st]) info.push(`Birch Bay has no NOAA tide gauge or prediction station of its own: all lines use Cherry Point (${ALIAS[D.st]}), the nearest NOAA gauge, about 4 mi south on the same shore.`);
  const lastObs = D.obs.length ? D.obs[D.obs.length - 1] : null;
  if (lastObs && D.rNow != null) info.push(`Latest observed ${lastObs[1].toFixed(2)} ft at ${fTime.format(new Date(lastObs[0]))}  \u00b7  residual (observed \u2212 predicted) ${sgn(D.rNow, 2)} ft`);
  const bits = [];
  if (D.pr) bits.push(`Pressure ${D.pr.hpa.toFixed(1)} hPa (inverse barometer \u2248 ${sgn((1013.25 - D.pr.hpa) * 0.0328, 2)} ft, info only, already included in STOFS)`);
  if (D.rSlow != null) bits.push(`30 day average offset ${sgn(D.rSlow, 2)} ft, used only after the STOFS forecast ends or if it is missing`);
  if (bits.length) info.push(bits.join("  \u00b7  "));
  info.push(D.method === "stofs" ? `Conditional = official prediction + NOAA STOFS ${new Date(D.cyc.t).getUTCHours().toString().padStart(2, "0")}Z surge forecast, which already includes low pressure and wind driven coastal waves, plus a fading correction to current observations (bias ${sgn(D.bias, 2)} ft fading 12 h). Experimental, not official.`
    : `Conditional = official prediction + current residual, relaxing to the 30 day average offset (STOFS forecast missing). Experimental, not official.`);
  const infoFs = portrait ? 12.5 : 12.5, lh = 18 * s;
  // wrap info lines to width
  c.font = F(600, infoFs); const wrapped = [];
  for (const l of info) { const words = l.split(" "); let cur = ""; for (const w of words) { const t = cur ? cur + " " + w : w; if (c.measureText(t).width > W - 2 * pad && cur) { wrapped.push(cur); cur = w; } else cur = t; } if (cur) wrapped.push(cur); }
  // verification stats box (bottom right in landscape, above the info lines in portrait)
  const SB = D.stats ? { w: Math.min(W - 2 * pad, 400 * s), h: (99 + (D.stats.peak ? 17 : 0) + (D.stats.raw ? 19 : 0) + (D.calib ? 32 : 0)) * s } : null;
  if (SB && !portrait) {   // re-wrap the info lines beside the box
    wrapped.length = 0; const maxW = W - 2 * pad - SB.w - 16 * s;
    for (const l of info) { const words = l.split(" "); let cur = ""; for (const w of words) { const t = cur ? cur + " " + w : w; if (c.measureText(t).width > maxW && cur) { wrapped.push(cur); cur = w; } else cur = t; } if (cur) wrapped.push(cur); } }
  const bottomInfo = SB ? (portrait ? wrapped.length * lh + SB.h + 18 * s : Math.max(wrapped.length * lh, SB.h) + 10 * s) : wrapped.length * lh + 8 * s;
  const axisH = 40 * s, yL = 46 * s, xR = pad + 8 * s;
  const X0 = pad + yL, X1 = W - xR, Y0 = top + 10 * s, Y1 = H - bottomInfo - axisH;
  // y range
  let lo = Infinity, hi = -Infinity; const scan = (a) => { for (const [, v] of a) { if (v < lo) lo = v; if (v > hi) hi = v; } };
  scan(D.pred); scan(D.obs); scan(D.cond); scan(D.ver); { const hd = hi; for (const f of D.floods) if (f.v < hd + 3) hi = Math.max(hi, f.v); }   // same rule as minor, per level
  const padY = (hi - lo) * 0.08 + 0.3; lo -= padY; hi += padY;
  const ys = niceStep(hi - lo, portrait ? 10 : 7); lo = Math.floor(lo / ys) * ys; hi = Math.ceil(hi / ys) * ys;
  const X = (t) => X0 + (t - R.start) / (R.end - R.start) * (X1 - X0), Y = (v) => Y1 - (v - lo) / (hi - lo) * (Y1 - Y0);
  // grid: days + y
  c.lineWidth = 1 * s; c.strokeStyle = COL.grid; c.font = F(600, 12.5); c.fillStyle = COL.axis;
  c.textAlign = "right"; c.textBaseline = "middle";
  for (let v = lo; v <= hi + 1e-9; v += ys) { const y = Math.round(Y(v)) + 0.5; c.beginPath(); c.moveTo(X0, y); c.lineTo(X1, y); c.stroke(); c.fillText(`${+v.toFixed(2)}`, X0 - 8 * s, y); }
  c.save(); c.translate(pad + 8 * s, (Y0 + Y1) / 2); c.rotate(-Math.PI / 2); c.textAlign = "center"; c.fillText("ft (MLLW)", 0, 0); c.restore();
  const nd = Math.round((R.end - R.start) / DAY), labEvery = (X1 - X0) / nd < 64 * s ? Math.ceil(64 * s / ((X1 - X0) / nd)) : 1;
  c.textAlign = "center"; c.textBaseline = "top";
  for (let k = 0; k <= nd; k++) { const [yy, mm, dd] = ymdLocal(R.start + k * DAY + 12 * HR).split("-").map(Number), t = localMidnight(yy, mm, dd); if (t > R.end + HR) break;
    const x = Math.round(X(t)) + 0.5; c.strokeStyle = COL.grid; c.beginPath(); c.moveTo(x, Y0); c.lineTo(x, Y1); c.stroke();
    if (k < nd && k % labEvery === 0) { const xm = X(t + 12 * HR); const d = new Date(t + 12 * HR); c.fillStyle = COL.axis;
      if ((X1 - X0) / nd >= 80 * s) { c.fillText(fDay.format(d).split(",")[0], xm, Y1 + 7 * s); c.fillText(fMd.format(d), xm, Y1 + 23 * s); } else c.fillText(fMd.format(d), xm, Y1 + 9 * s); } }
  c.strokeStyle = "#4a4f5a"; c.strokeRect(X0, Y0, X1 - X0, Y1 - Y0);
  // clip plot
  c.save(); c.beginPath(); c.rect(X0, Y0, X1 - X0, Y1 - Y0); c.clip();
  window.__tideFloodDrawn = []; window.__tideFloodLabels = []; const fBox = [], fTag = [];
  for (const f of D.floods) if (f.v >= lo && f.v <= hi) { c.strokeStyle = FCOL[f.k]; c.lineWidth = 2 * s; c.setLineDash([9 * s, 6 * s]); const y = Y(f.v); c.beginPath(); c.moveTo(X0, y); c.lineTo(X1, y); c.stroke(); c.setLineDash([]);
    // t3046u: name tag sits ON its own line (vertically centered), in a chart-bg pill; close levels only shift sideways, never off the line
    c.font = F(700, 11.5); c.textAlign = "left"; c.textBaseline = "middle"; const tw = c.measureText(f.lab).width, px = 5 * s, ph = 15 * s, pw = tw + 2 * px;
    let x = X0 + 8 * s; const y0 = y - ph / 2, y1b = y + ph / 2;
    for (let moved = true; moved;) { moved = false; for (const b of fBox) if (x < b.x1 + 6 * s && x + pw > b.x0 - 6 * s && y0 < b.y1 && y1b > b.y0) { x = b.x1 + 6 * s; moved = true; } }
    fBox.push({ k: f.k, x0: x, x1: x + pw, y0, y1: y1b, ly: y });
    fTag.push(() => { const rr = ph / 2; c.fillStyle = COL.bg; c.beginPath(); c.moveTo(x + rr, y0); c.lineTo(x + pw - rr, y0); c.arc(x + pw - rr, y, rr, -Math.PI / 2, Math.PI / 2); c.lineTo(x + rr, y1b); c.arc(x + rr, y, rr, Math.PI / 2, 3 * Math.PI / 2); c.closePath(); c.fill();
    c.lineWidth = 1 * s; c.strokeStyle = FCOL[f.k]; c.stroke();
    c.fillStyle = FCOL[f.k]; c.fillText(f.lab, x + px, y + 0.5 * s); }); window.__tideFloodLabels = fBox.map((b) => ({ k: b.k, x0: b.x0, x1: b.x1, yc: (b.y0 + b.y1) / 2, ly: b.ly })); window.__tideFloodDrawn.push(f.k); }
  const line = (pts, col, w, gapMs) => { if (!pts.length) return; c.strokeStyle = col; c.lineWidth = w * s; c.lineJoin = "round"; c.lineCap = "round"; c.beginPath(); let pen = false, lt = 0;
    for (const [t, v] of pts) { const x = X(t), y = Y(v); if (!pen || (gapMs && t - lt > gapMs)) { c.moveTo(x, y); pen = true; } else c.lineTo(x, y); lt = t; } c.stroke(); };
  line(D.pred, COL.pred, 2.2);
  if (D.ver.length) {   // faint dashed: what the Conditional line had said (issued vl..vl+6 h earlier); a new snapshot every 6 h
    c.save(); c.setLineDash([5 * s, 4 * s]); line(D.ver.map((p) => [p[0], p[1]]), COL.ver, 2, 7 * 60000); c.restore();
    // hindcast span (snapshots reconstructed after the fact, before the live archive began)
    const hs = D.ver.filter((p) => !p[2]); if (hs.length) { const xa = Math.max(X0, X(hs[0][0])), xb = Math.min(X1, X(hs[hs.length - 1][0]));
      c.fillStyle = "rgba(255,200,110,0.07)"; c.fillRect(xa, Y1 - 18 * s, xb - xa, 18 * s); c.strokeStyle = "rgba(255,200,110,0.35)"; c.lineWidth = 1 * s;
      c.beginPath(); c.moveTo(xa, Y1 - 18 * s); c.lineTo(xb, Y1 - 18 * s); c.stroke();
      c.font = F(700, 10.5); c.fillStyle = "rgba(255,214,150,0.9)"; c.textAlign = "left"; c.textBaseline = "middle";
      const lab = xb - xa > 210 * s ? "Verified line: hindcast (before the archive started)" : "hindcast"; if (xb - xa > c.measureText(lab).width + 10 * s) c.fillText(lab, xa + 6 * s, Y1 - 9 * s); } }
  line(D.obs, COL.obs, 2.2, 31 * 60000);
  if (D.cond.length) { c.save(); c.shadowColor = "rgba(0,0,0,0.55)"; c.shadowBlur = 3 * s; line(D.cond, COL.cond, 3.2); c.restore(); }
  for (const t of fTag) { c.save(); c.setLineDash([]); c.textAlign = "left"; c.textBaseline = "middle"; c.font = F(700, 11.5); t(); c.restore(); }   // flood name pills on top of the curves
  // now line
  if (D.now >= R.start && D.now <= R.end) { const x = Math.round(X(D.now)) + 0.5; c.strokeStyle = COL.now; c.lineWidth = 1.6 * s; c.setLineDash([6 * s, 5 * s]); c.beginPath(); c.moveTo(x, Y0); c.lineTo(x, Y1); c.stroke(); c.setLineDash([]);
    c.font = F(800, 12.5); c.textBaseline = "top"; const lab = `Now ${fTime.format(new Date(D.now))}`, tw = c.measureText(lab).width + 12 * s, lx2 = Math.min(Math.max(x - tw / 2, X0 + 2), X1 - tw - 2);
    c.fillStyle = "rgba(21,23,28,0.85)"; c.fillRect(lx2, Y0 + 4 * s, tw, 20 * s); c.fillStyle = COL.now; c.textAlign = "left"; c.fillText(lab, lx2 + 6 * s, Y0 + 8 * s); }
  // high-tide labels (prediction in blue; conditional in amber when it exists)
  const pxPerDay = (X1 - X0) / nd;
  if (pxPerDay >= 70 * s) { c.font = F(700, 11.5); c.textAlign = "center"; c.textBaseline = "bottom";
    for (const e of extremes(D.pred, R.start, R.end)) { if (!e.hi) continue; const x = X(e.t); let y = Y(e.v) - 6 * s;
      const cv = interp(D.cond, e.t); c.lineJoin = "round"; c.lineWidth = 4 * s; c.strokeStyle = COL.bg;
      if (cv != null) { const yc = Math.min(Y(cv) - 7 * s, y - 15 * s); c.strokeText(cv.toFixed(1), x, yc); c.fillStyle = COL.cond; c.fillText(cv.toFixed(1), x, yc); }
      c.strokeText(e.v.toFixed(1), x, y); c.fillStyle = COL.pred; c.fillText(e.v.toFixed(1), x, y); } }
  c.restore();
  // info
  c.font = F(600, infoFs); c.fillStyle = "rgba(236,239,244,0.92)"; c.textAlign = "left"; c.textBaseline = "alphabetic";
  const infoTop = H - bottomInfo + (SB && portrait ? SB.h + 12 * s : 0);
  wrapped.forEach((l, i) => c.fillText(l, pad, infoTop + (i + 1) * lh - 2 * s));
  if (SB) { const sx = portrait ? pad : W - pad - SB.w, sy = H - bottomInfo + 6 * s; statsBox(c, sx, sy, SB.w, SB.h, s, F); window.__tideStatsBox = { x: sx, y: sy, w: SB.w, h: SB.h, W, H }; }
  else window.__tideStatsBox = null;
  c.restore();
  return { X0, X1, Y0, Y1, X, Y, lo, hi };
}

function statsBox(c, x, y, w, h, s, F) {
  const S = D.stats, f2 = (v) => v.toFixed(2), sg = (v) => sgn(v, 2);
  c.save(); c.fillStyle = "rgba(29,32,39,0.92)"; c.strokeStyle = "#3a3f4a"; c.lineWidth = 1 * s;
  c.beginPath(); c.roundRect ? c.roundRect(x + 0.5, y + 0.5, w - 1, h - 1, 6 * s) : c.rect(x + 0.5, y + 0.5, w - 1, h - 1); c.fill(); c.stroke();
  const px = x + 10 * s, inner = w - 20 * s; let yy = y + 17 * s; c.textBaseline = "alphabetic"; c.textAlign = "left";
  const fit = (t, wt, px0, max) => { let f = px0; c.font = F(wt, f); while (f > 8 && c.measureText(t).width > max) { f -= 0.5; c.font = F(wt, f); } };
  const head = `Verification \u00b7 last ${D.sd} days \u00b7 issued ${D.vl}\u2013${D.vl + 6} h ahead`;
  fit(head, 800, 12, inner); c.fillStyle = COL.text; c.fillText(head, px, yy);
  const sub = `${S.n} hourly points${S.nh ? (S.nh === S.n ? " \u00b7 all hindcast" : ` \u00b7 ${Math.round(100 * S.nh / S.n)}% hindcast`) : ""} \u00b7 forecast \u2212 observed`;
  yy += 15 * s; fit(sub, 600, 10.5, inner); c.fillStyle = COL.axis; c.fillText(sub, px, yy);
  const cx = [x + w * 0.52, x + w * 0.72, x + w - 10 * s];
  yy += 18 * s; c.font = F(700, 10.5); c.fillStyle = COL.axis; c.textAlign = "right"; ["Mean abs error", "Bias", "Peak high miss"].forEach((t, i) => c.fillText(t, cx[i], yy));
  const row = (lab, col, m, pk) => { yy += 19 * s; c.textAlign = "left"; c.font = F(800, 12); c.fillStyle = col; c.fillText(lab, px, yy);
    c.textAlign = "right"; c.font = F(700, 12); c.fillStyle = COL.text; c.fillText(`${f2(m.mae)} ft`, cx[0], yy); c.fillText(`${sg(m.bias)} ft`, cx[1], yy); c.fillText(pk == null ? "\u2013" : `${sg(pk)} ft`, cx[2], yy); };
  if (S.raw) { row("Calibrated", COL.cond, S.cond, S.peak && S.peak.cond); row("Raw conditional", "rgba(255,200,110,0.75)", S.raw, S.peak && S.peak.raw); }
  else row("Conditional", COL.cond, S.cond, S.peak && S.peak.cond);
  row("Official", COL.pred, S.off, S.peak && S.peak.off);
  if (D.calib) { c.textAlign = "left"; const cc = D.calib.c.map((b) => b.corr), rg = D.calib.ranges, cd = new Date(D.calib.t);
    const ri = Math.max(0, rg.findIndex((r) => D.vl >= r[0] && D.vl < r[1]));
    const l1 = `Calibrated: ${sgn(cc[ri], 2)} ft at ${rg[ri][0]}\u2013${rg[ri][1]} h ahead (last ${D.calib.lookback_d} days, set ${fMd.format(cd)} ${fTime.format(cd)})`;
    const l2 = `All ranges: ${rg.map((r, i) => `${r[0]}\u2013${r[1]} h ${sgn(cc[i], 2)}`).join("  \u00b7  ")} ft`;
    yy += 17 * s; fit(l1, 700, 10.5, inner); c.fillStyle = "rgba(255,214,150,0.95)"; c.fillText(l1, px, yy);
    yy += 15 * s; fit(l2, 600, 10, inner); c.fillStyle = COL.axis; c.fillText(l2, px, yy); }
  if (S.peak) { yy += 17 * s; c.textAlign = "left"; const ft = `Peak high: observed ${S.peak.obs.toFixed(2)} ft, ${fDay.format(new Date(S.peak.t))} ${fTime.format(new Date(S.peak.t))}`; fit(ft, 600, 10.5, inner); c.fillStyle = COL.axis; c.fillText(ft, px, yy); }
  c.restore();
}

let geom = null;
function draw() {
  if (STUDIO) return; const cv = $("tc"), w = cv.clientWidth, h = cv.clientHeight; if (!w || !h) return;
  const dpr = Math.min(window.devicePixelRatio || 1, 3); const bw = Math.round(w * dpr), bh = Math.round(h * dpr);
  if (cv.width !== bw || cv.height !== bh) { cv.width = bw; cv.height = bh; }
  const c = cv.getContext("2d"); c.setTransform(dpr, 0, 0, dpr, 0, 0);
  const s = Math.max(0.78, Math.min(1.25, Math.min(w / 1100, h / 640) * 1.05));
  geom = drawChart(c, w, h, { scale: s }); window.__tideSharp = { dpr, cssW: w, backingW: cv.width, scale: s };
}
function setMsg(t) { const m = $("msg"); if (m) m.textContent = STUDIO ? "" : t; }
function note() { const n = $("tnote"); if (!n || !D) return; n.textContent = D.method === "stofs" ? `STOFS ${new Date(D.cyc.t).toISOString().slice(5, 13).replace("T", " ")}Z` : "Persistence (no STOFS)"; }

// ---- UI ----
function syncURL() { const u = new URL(location.href); u.searchParams.set("st", T.st); u.searchParams.set("vl", String(T.vl)); u.searchParams.set("sd", String(T.sd)); if (T.from) u.searchParams.set("from", T.from); else u.searchParams.delete("from"); u.searchParams.set("days", String(T.days)); history.replaceState(null, "", u); try { localStorage.setItem("tide:st", T.st); } catch (e) { /* private */ } }
function ui() {
  const st = $("st"); st.innerHTML = STATIONS.map(([id, n]) => `<option value="${id}">${n} (${stLabel(id)})</option>`).join(""); st.value = T.st;
  const ds = $("days"); ds.innerHTML = DAYS.map((d) => `<option value="${d}">${d}</option>`).join(""); ds.value = String(T.days);
  const fr = $("from"); fr.value = ymdLocal(range().start);
  const vl = $("vl"), sd = $("sd");
  if (vl) { vl.innerHTML = LEADS.map((l) => `<option value="${l}">${l ? `${l}\u2013${l + 6} h` : "Off"}</option>`).join(""); vl.value = String(T.vl); vl.onchange = () => { T.vl = +vl.value; syncURL(); load(); }; }
  if (sd) { sd.innerHTML = SDAYS.map((d) => `<option value="${d}">${d} days</option>`).join(""); sd.value = String(T.sd); sd.onchange = () => { T.sd = +sd.value; syncURL(); load(); }; }
  st.onchange = () => { T.st = st.value; syncURL(); load(); };
  ds.onchange = () => { T.days = +ds.value; syncURL(); load(); };
  fr.onchange = () => { if (/^\d{4}-\d{2}-\d{2}$/.test(fr.value)) { T.from = fr.value; syncURL(); load(); } };
  $("today").onclick = () => { T.from = ""; T.days = 9; ds.value = "9"; fr.value = ymdLocal(range().start); syncURL(); load(); };
  $("reload").onclick = () => { shefCache = { url: "", txt: "" }; load(); };
  if (!STUDIO) {
    addEventListener("resize", () => requestAnimationFrame(draw));
    const cv = $("tc"), tip = $("tip");
    cv.addEventListener("pointermove", (e) => { if (!D || !geom) return; const b = cv.getBoundingClientRect(), x = e.clientX - b.left, y = e.clientY - b.top;
      if (x < geom.X0 || x > geom.X1 || y < geom.Y0 || y > geom.Y1) { tip.hidden = true; return; }
      const t = D.R.start + (x - geom.X0) / (geom.X1 - geom.X0) * (D.R.end - D.R.start), tt = Math.round(t / H6) * H6;
      const p = interp(D.pred, tt), o = interp(D.obs, tt), cc = interp(D.cond, tt), vv = D.ver.find((q) => q[0] === tt);
      tip.innerHTML = `${fDay.format(new Date(tt))} ${fTime.format(new Date(tt))}` + (p != null ? `<br><span style="color:${COL.pred}">Prediction ${p.toFixed(2)} ft</span>` : "") +
        (o != null ? `<br><span style="color:${COL.obs}">Observed ${o.toFixed(2)} ft</span>` : "") + (cc != null ? `<br><span style="color:${COL.cond}">Conditional ${cc.toFixed(2)} ft</span>` + (D.calib ? `<br><span style="color:#a7abb3;font-weight:500">raw (uncalibrated) ${interp(D.condRaw, tt).toFixed(2)} ft</span>` : "") : "") +
        (vv ? `<br><span style="color:${COL.ver}">Conditional, verified ${vv[1].toFixed(2)} ft</span><br><span style="color:#a7abb3;font-weight:500">issued ${fDay.format(new Date(vv[3]))} ${fTime.format(new Date(vv[3]))}${vv[2] ? "" : " (hindcast)"}</span>` : "");
      tip.hidden = false; const w = tip.offsetWidth; tip.style.left = Math.min(x + 14, b.width - w - 4) + "px"; tip.style.top = Math.max(4, y - 70) + "px"; });
    cv.addEventListener("pointerleave", () => { tip.hidden = true; });
  }
}
window.TIDE = {
  draw: (c, W, H, opt) => drawChart(c, W, H, opt),
  state: () => D, stations: STATIONS,
  qa: () => D ? { st: D.st, name: D.name, pred: D.pred.length, obs: D.obs.length, cond: D.cond.length, method: D.method, cycle: D.cyc ? new Date(D.cyc.t).toISOString() : null,
    rNow: D.rNow, rSlow: D.rSlow, bias: D.bias, flood: D.flood, floods: D.floods, floodSkip: D.floodSkip, floodDrawn: window.__tideFloodDrawn || [], floodLabels: window.__tideFloodLabels || [], sid: D.sid, start: D.R.start, end: D.R.end, now: D.now,
    statsBox: window.__tideStatsBox || null, arch: ARCH, calib: D.calib ? D.calib.c.map((b) => b.corr) : null, calibBg: D.calibBg ? { t: D.calibBg.t, c: D.calibBg.c.map((b) => b.corr) } : null, ver: D.ver.length, verHindcast: D.ver.filter((p) => !p[2]).length, issues: D.nIssues, archived: D.nArchive, vl: D.vl, sd: D.sd, stats: D.stats,
    condAboveFrac: D.cond.length ? D.cond.filter(([t, v]) => v >= (interp(D.pred, t) || 0)).length / D.cond.length : null, sharp: window.__tideSharp || null } : { err: window.__tideErr || null },
};
ui(); syncURL(); load();
setInterval(() => { if (document.visibilityState === "visible") load(); }, 10 * 60000);   // new observations every 6 min; refresh every 10
})();
