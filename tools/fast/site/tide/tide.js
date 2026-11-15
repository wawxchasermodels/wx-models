// Tides viewer (Conditional, 2026-11-14): official NOAA tide + air-pressure effect (observed for
// past/now, AIFS ENS mean forecast ahead) + SST anomaly vs a typical year + a multi-day observed
// leftover held through the forecast and a 12 h fade so the line starts at the latest gauge reading.
// Default does not use STOFS. "Wind surge" (off by default) adds only STOFS wind = (swl minus the
// 5-day station anomaly minus pressure effect on STOFS forcing). Toggle identity: on - off = wind.
// Public data only, no keys. Times in Pacific time. window.TIDE.draw(ctx, W, H, opt) for Studio frames.
(() => {
"use strict";
const API = "https://api.tidesandcurrents.noaa.gov/api/prod/datagetter";
const MD = "https://api.tidesandcurrents.noaa.gov/mdapi/prod/webapi/stations/";
const S3 = "https://noaa-gestofs-pds.s3.amazonaws.com/";
const TZ = "America/Los_Angeles";
// Benjamin t3044u: list A to Z by name (default stays Westport 9441102). Birch Bay has no NOAA gauge, prediction station or
// STOFS point of its own (CO-OPS metadata, 11-14); it uses Cherry Point 9449424, the nearest NOAA gauge, about 4 mi south on the same shore.
const STATIONS = [
  ["9439040", "Astoria, OR"], ["birchbay", "Birch Bay, WA"], ["9440581", "Cape Disappointment, WA"], ["9449424", "Cherry Point, WA"], ["9449880", "Friday Harbor, WA"],
  ["9442396", "La Push, WA"], ["9443090", "Neah Bay, WA"], ["9444090", "Port Angeles, WA"], ["9444900", "Port Townsend, WA"],
  ["9447130", "Seattle, WA"], ["9446484", "Tacoma, WA"], ["9440910", "Toke Point, WA"], ["9441102", "Westport, WA"],
];
const ALIAS = {"birchbay": "9449424"};
const sidOf = (k) => ALIAS[k] || k;
const stLabel = (k) => ALIAS[k] ? `Cherry Point ${ALIAS[k]}` : k;
// 9440581 is NOAA's official "Cape Disappointment" harmonic / PORTS gauge (CPTW1): live water levels and
// official predictions. It has no air-pressure sensor; observed pressure is borrowed from Toke Point,
// then Westport (same fallback as Astoria). SST uses the Westport OISST pixel (SST_MAP). No official
// NWS flood stages (mdapi and the inundation dashboard have only an "action" value, not drawn).
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
  vl: +(Q.get("vl") ?? 24), sd: +(Q.get("sd") || 7), flood: true, wind: false };
if (!LEADS.includes(T.vl)) T.vl = 24;
if (!SDAYS.includes(T.sd)) T.sd = 7;
if (!STATIONS.some((s) => s[0] === T.st)) T.st = "9441102";
if (!DAYS.includes(T.days)) T.days = 9;
{ const qf = Q.get("flood");
  if (qf === "0" || qf === "off") T.flood = false;
  else if (qf === "1" || qf === "on") T.flood = true;
  else { try { if (localStorage.getItem("tide:flood") === "0") T.flood = false; } catch (e) { /* private */ } } }
{ const qw = Q.get("wind");
  if (qw === "1" || qw === "on") T.wind = true;
  else if (qw === "0" || qw === "off") T.wind = false;
  else { try { if (localStorage.getItem("tide:wind") === "1") T.wind = true; } catch (e) { /* private */ } } }
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

// ---- Conditional v2: IB, SST, wind (must stay algebraically identical to cond_v2.py / test_tide_wind_ib.py) ----
const P0 = 1013.25, FT_PER_M = 3.28084, FT_PER_CM = FT_PER_M / 100;
const ibFt = (hpa) => (hpa == null || !isFinite(hpa) ? null : (P0 - hpa) * FT_PER_CM);
const fadeAt = (dt, tau) => Math.exp(-Math.max(0, dt) / (tau || TAU_BIAS));
const dIB = (ibA, ibG) => (ibA == null || ibG == null ? 0 : ibA - ibG);
const c1Resid = (rsT, rNow, rsNow, dt) => rsT + (rNow - rsNow) * fadeAt(dt);
const windOnly = (rsT, anom, pStofs) => { const ib = ibFt(pStofs); if (rsT == null || anom == null || ib == null || !isFinite(rsT) || !isFinite(anom)) return null; return rsT - anom - ib; };
const windComp = (wT, w0, dt) => (wT == null ? 0 : wT - (w0 || 0) * fadeAt(dt));
function rhoUnesco(T, S) {
  const a0 = 999.842594, a1 = 6.793952e-2, a2 = -9.095290e-3, a3 = 1.001685e-4, a4 = -1.120083e-6, a5 = 6.536332e-9;
  const b0 = 8.24493e-1, b1 = -4.0899e-3, b2 = 7.6438e-5, b3 = -8.2467e-7, b4 = 5.3875e-9;
  const c0 = -5.72466e-3, c1 = 1.0227e-4, c2 = -1.6546e-6, d0 = 4.8314e-4;
  const smow = a0 + T * (a1 + T * (a2 + T * (a3 + T * (a4 + T * a5))));
  return smow + S * (b0 + T * (b1 + T * (b2 + T * (b3 + T * b4)))) + Math.pow(S, 1.5) * (c0 + T * (c1 + T * c2)) + d0 * S * S;
}
function alphaThermal(T, S) { const dT = 0.05, r1 = rhoUnesco(T - dT, S), r2 = rhoUnesco(T + dT, S); return -(r2 - r1) / (2 * dT) / ((r1 + r2) / 2); }
function Wft(dT, T, S, He) { if (dT == null || T == null || !He) return 0; return alphaThermal(T, S) * dT * He * FT_PER_M; }
const COORDS = {"9439040":[46.207306,-123.7683],"9440581":[46.28103,-124.04628],"9440910":[46.7075,-123.96694],"9441102":[46.90431,-124.10508],"9442396":[47.912838,-124.63574],"9443090":[48.370724,-124.601585],"9444090":[48.125,-123.44],"9444900":[48.11122,-122.759674],"9449880":[48.545277,-123.0125],"9449424":[48.862717,-122.75858],"9447130":[47.60264,-122.3393],"9446484":[47.2667,-122.4133]};
const SALT = {"9439040":25,"9440581":32.2,"9440910":32.2,"9441102":32.2,"9442396":32.2,"9443090":32.2,"9444090":31,"9444900":31,"9449880":31,"9449424":31,"9447130":30,"9446484":30};
const SST_MAP = {"9440581":"9441102","9440910":"9441102","9447130":"9446484","9449880":"9444900"};
const SST_OWN = {9441102:1,9442396:1,9443090:1,9444090:1,9444900:1,9446484:1};
const P_FALLBACK = {"9439040":["9440910","9441102"],"9440581":["9440910","9441102"]};
const H_EFF = {"9439040":0,"9440581":0,"9440910":0,"9441102":0,"9442396":0,"9443090":0,"9444090":0,"9444900":0,"9449880":0,"9449424":0,"9447130":0,"9446484":0};   // filled from backtest (m); 0 means no SST height until calibrated
let AUX = null;
async function loadAux() {
  if (AUX) return AUX;
  const localAux = await fetchJsonOk("tide_aux.json");
  if (localAux && localAux.H_eff_m) for (const k of Object.keys(localAux.H_eff_m)) H_EFF[k] = localAux.H_eff_m[k];
  const idx = await loadArchIndex();
  const localA = await fetchJsonOk("aifs_ens_msl.json");
  const archAifs = archSidecarUrl(idx, "aifs_ens_msl.json");
  const archA = archAifs ? await fetchJsonOk(archAifs) : null;
  const fromAux = localAux && (localAux.aifs || (localAux.steps && localAux.init ? localAux : null));
  const aifs = pickFresher(pickFresher(localA, fromAux), archA);
  AUX = aifs || localAux || {};
  if (localAux && localAux.H_eff_m) AUX.H_eff_m = localAux.H_eff_m;
  return AUX;
}
let ANOM = null;
async function loadAnom() {
  if (ANOM) return ANOM;
  const unwrap = (j) => { const rec = (j && j.anom) ? j.anom : j; return rec && rec.stations ? rec : null; };
  const idx = await loadArchIndex();
  const local = unwrap(await fetchJsonOk("stofs_anom.json")) || unwrap(await fetchJsonOk("tide_aux.json"));
  const archAnom = archSidecarUrl(idx, "stofs_anom.json");
  const arch = archAnom ? unwrap(await fetchJsonOk(archAnom)) : null;
  ANOM = pickFresher(local, arch) || { stations: {} };
  return ANOM;
}
function cycleMs(rec) {
  if (!rec) return null;
  if (rec.init) {
    const raw = String(rec.init);
    const s = raw.indexOf("T") >= 0 ? (raw.length === 16 ? raw + ":00" : raw).replace("Z", "") : (raw.slice(0, 4) + "-" + raw.slice(4, 6) + "-" + raw.slice(6, 8) + "T" + raw.slice(8, 10) + ":00");
    const t = parseT(s);
    return isFinite(t) ? t : null;
  }
  if (rec.cycle && String(rec.cycle).length >= 10) {
    const c = String(rec.cycle);
    return Date.UTC(+c.slice(0, 4), +c.slice(4, 6) - 1, +c.slice(6, 8), +c.slice(8, 10));
  }
  return null;
}
async function fetchJsonOk(u) {
  // A missing archive or sidecar file must not throw: keep the copy shipped with the site, or the 0 / persist fallbacks.
  try { const r = await fetch(u, { cache: "no-store" }); if (r.ok) return await r.json(); } catch (e) { /* 404 / CORS / offline is fine */ }
  return null;
}
function recFreshness(rec) {
  if (!rec) return -1;
  const c = cycleMs(rec);
  if (c != null) return c;
  if (rec.refreshed_at) { const t = Date.parse(rec.refreshed_at); if (isFinite(t)) return t; }
  if (rec.last_day) { const t = Date.parse(rec.last_day + "T00:00:00Z"); if (isFinite(t)) return t; }
  let last = -1;
  if (rec.stations) {
    for (const row of Object.values(rec.stations)) {
      if (row && row.last_day) { const t = Date.parse(row.last_day + "T00:00:00Z"); if (isFinite(t) && t > last) last = t; }
    }
  }
  return last;
}
function pickFresher(a, b) {
  if (!a) return b || null;
  if (!b) return a;
  return recFreshness(b) > recFreshness(a) ? b : a;
}
let ARCH_IDX_P = null;
async function loadArchIndex() {
  if (!ARCH_IDX_P) ARCH_IDX_P = (async () => (await fetchJsonOk(ARCH + "index.json")) || { months: {}, sidecars: {} })();
  return ARCH_IDX_P;
}
function archSidecarUrl(idx, name) {
  const s = (idx && idx.sidecars) || {};
  if (s[name] === true || s[name.replace(/\.json$/, "")] === true) return ARCH + name;
  return null;  // do not GET a file the index does not list — a 404 would show in the console
}
function anomAt(st, t, cycT) {
  const rec = ANOM;
  if (!rec || !rec.stations || !rec.stations[st] || cycT == null) return null;
  const init = cycleMs(rec);
  if (init != null && Math.abs(init - cycT) > HR) return null;   // sidecar is for a different STOFS cycle
  const hourly = rec.stations[st].hourly || rec.stations[st];
  if (!hourly) return null;
  const h = (t - (init != null ? init : cycT)) / HR;
  const h0 = Math.floor(h), h1 = h0 + 1;
  const a = hourly[h0] != null ? +hourly[h0] : (hourly[String(h0)] != null ? +hourly[String(h0)] : null);
  const b = hourly[h1] != null ? +hourly[h1] : (hourly[String(h1)] != null ? +hourly[String(h1)] : null);
  if (a == null && b == null) return null;
  if (a == null) return b;
  if (b == null || h1 === h0) return a;
  return a + (b - a) * (h - h0);
}
async function coopsMetricPressure(st, b, e) {
  const out = [];
  try {
    const j = await getJSON(`${API}?product=air_pressure&application=wx_models_tides&station=${st}&begin_date=${encodeURIComponent(gmt(b))}&end_date=${encodeURIComponent(gmt(e))}&time_zone=gmt&units=metric&interval=h&format=json`);
    for (const p of (j.data || [])) { const v = parseFloat(p.v); if (isFinite(v)) out.push([parseT(p.t), v]); }
  } catch (e) { /* none */ }
  return out;
}
async function obsPressureSeries(st, b, e) {
  let pts = await coopsMetricPressure(st, b, e);
  if (pts.length) return { pts, src: "coops:" + st, sid: st };
  for (const fb of (P_FALLBACK[st] || [])) {
    pts = await coopsMetricPressure(fb, b, e);
    if (pts.length) return { pts, src: "coops:" + fb, sid: fb };
  }
  return { pts: [], src: null, sid: st };
}
async function openMeteoPressure(lat, lon, model, pastDays) {
  const u = `https://api.open-meteo.com/v1/forecast?latitude=${lat}&longitude=${lon}&hourly=pressure_msl&models=${encodeURIComponent(model)}&forecast_days=16&past_days=${pastDays || 1}&timezone=UTC`;
  const j = await getJSON(u);
  const t = (j.hourly && j.hourly.time) || [], p = (j.hourly && j.hourly.pressure_msl) || [];
  const pts = [];
  for (let i = 0; i < t.length; i++) if (p[i] != null && isFinite(p[i])) pts.push([parseT(t[i].length === 16 ? t[i] + ":00" : t[i]), p[i]]);
  return { pts, model, n: pts.length };
}
function hourlyFromSix(initMs, stepHpa) {
  const hs = Object.keys(stepHpa).map(Number).sort((a, b) => a - b);
  if (!hs.length) return [];
  const out = [], last = hs[hs.length - 1];
  for (let h = hs[0]; h <= last; h++) {
    const t = initMs + h * HR;
    if (stepHpa[h] != null) { out.push([t, stepHpa[h]]); continue; }
    let a = hs[0], b = last;
    for (const x of hs) { if (x <= h) a = x; if (x >= h) { b = x; break; } }
    const va = stepHpa[a], vb = stepHpa[b];
    out.push([t, b === a ? va : va + (vb - va) * (h - a) / (b - a)]);
  }
  return out;
}
async function forecastPressure(st) {
  const aux = await loadAux();
  const rec = aux && (aux.aifs || aux);
  if (rec && rec.steps && rec.init) {
    const raw = rec.init;
    const init = (raw.indexOf("T") >= 0)
      ? parseT((raw.length === 16 ? raw + ":00" : raw).replace("Z", ""))
      : parseT(raw.slice(0, 4) + "-" + raw.slice(4, 6) + "-" + raw.slice(6, 8) + "T" + raw.slice(8, 10) + ":00");
    const steps = {};
    const srcs = new Set();
    for (const [h, row] of Object.entries(rec.steps)) {
      const v = (row.msl_hpa && row.msl_hpa[st] != null) ? row.msl_hpa[st] : null;
      if (v != null) steps[+h] = v;
      if (row.source) srcs.add(row.source);
    }
    // Only label the run as a fallback if no step is the 51-member ENS mean.
    let src = rec.source || "aifs-ens-mean";
    if (srcs.size && !srcs.has("aifs-ens-mean")) src = [...srcs][0];
    else src = "aifs-ens-mean";
    const pts = hourlyFromSix(init, steps);
    if (pts.length) return { pts, src, run: rec.cycle || rec.init, note: rec.note || null, latency: rec.meta || null };
  }
  const [lat, lon] = COORDS[st] || [46.9, -124.1];
  for (const model of ["ecmwf_aifs025", "ecmwf_ifs025"]) {
    try {
      const r = await openMeteoPressure(lat, lon, model, 1);
      if (r.n) return { pts: r.pts, src: "open-meteo:" + model, run: null, note: model === "ecmwf_ifs025" ? "AIFS ENS extract unavailable; fell back to IFS via Open-Meteo" : "AIFS single via Open-Meteo (ENS extract unavailable)", latency: null };
    } catch (e) { /* next */ }
  }
  return { pts: [], src: null, run: null, note: "no forecast pressure", latency: null };
}
async function gfsPressure(st) {
  const [lat, lon] = COORDS[st] || [46.9, -124.1];
  try { const r = await openMeteoPressure(lat, lon, "gfs_seamless", 2); if (r.n) return r.pts; } catch (e) { /* none */ }
  try { const r = await openMeteoPressure(lat, lon, "gfs_global", 2); if (r.n) return r.pts; } catch (e) { /* none */ }
  return [];
}
// SST sidecar (sst.json): shipped with the site; a newer copy on the tide-archive branch wins. A 404 there is fine.
const SSTU = window.TIDE_SST || (typeof ARCH !== "undefined" ? ARCH + "sst.json" : "sst.json");
function sstProductLabel(sst) {
  const s = String((sst && (sst.src || sst.source)) || "");
  if (/oisst/i.test(s)) return "NOAA OISST";
  if (/geopolar/i.test(s)) return "NOAA Geo-Polar Blended";
  if (/mur/i.test(s)) return "MUR";
  return null;
}
function aifsProductLabel(aifs) {
  if (!aifs || (!aifs.src && !aifs.run)) return null;
  if (!aifs.src || aifs.src === "aifs-ens-mean") return "ECMWF AIFS ensemble pressure";
  if (/aifs-single|ecmwf_aifs/i.test(aifs.src)) return "ECMWF AIFS pressure";
  if (/ifs/i.test(aifs.src)) return "ECMWF IFS pressure";
  return "ECMWF AIFS ensemble pressure";
}
function productsLine(wind, sst, aifs, obsP, st) {
  const parts = ["NOAA official tide prediction"];
  const pSid = obsP && obsP.sid;
  if (pSid && st && pSid !== st) {
    const raw = (STATIONS.find((s) => s[0] === pSid) || [pSid, pSid])[1];
    parts.push("NOAA gauge water levels", raw.replace(/, (WA|OR)$/, "") + " gauge pressure");
  } else {
    parts.push("NOAA gauge water levels and pressure");
  }
  const a = aifsProductLabel(aifs);
  if (a) parts.push(a);
  const s = sstProductLabel(sst);
  if (s) parts.push("sea surface temperature (" + s + ")");
  if (wind) parts.push("NOAA STOFS wind surge");
  return "Conditional uses: " + parts.join(", ") + ". Experimental, not official.";
}
async function sstTerm(st, now) {
  const sstId = SST_MAP[st] || st;
  const usable = (row) => row && (isFinite(row.W) || isFinite(row.steric_ft) || (isFinite(row.k_ft_per_c) && (isFinite(row.ssta) || isFinite(row.ssta30_c))) || (isFinite(row.adj_ft) && isFinite(row.ssta30_c)));
  const rowOf = (j) => j && (j.stations && j.stations[sstId] || (j.sst && j.sst[sstId]) || (j[sstId] && typeof j[sstId] === "object" ? j[sstId] : null));
  const idx = await loadArchIndex();
  const localJ = await fetchJsonOk("sst.json");
  const archSst = (SSTU && SSTU !== "sst.json") ? (archSidecarUrl(idx, "sst.json") || null) : null;
  const archJ = archSst ? await fetchJsonOk(archSst) : null;
  const aux = await loadAux();
  const pack = pickFresher(localJ, archJ) || aux;
  const rec = usable(rowOf(pack)) ? rowOf(pack) : (usable(rowOf(aux)) ? rowOf(aux) : null);
  const src = rec ? (pack === archJ ? SSTU : (pack === localJ ? "sst.json" : "tide_aux.json")) : "none";
  if (!rec) return { adj: 0, dT: 0, ssta30: null, ssta: null, k: 0, W: 0, src: "none" };
  const ssta = rec.ssta != null ? +rec.ssta : (rec.ssta30_c != null ? +rec.ssta30_c : 0);
  const k = rec.k_ft_per_c != null ? +rec.k_ft_per_c : 0;
  const W = rec.W != null ? +rec.W : (rec.steric_ft != null ? +rec.steric_ft : k * ssta);
  return {
    adj: rec.adj_ft || 0, dT: rec.d_c, ssta, ssta30: rec.ssta30_c != null ? +rec.ssta30_c : ssta, k, W,
    steric: rec.steric_ft, last_day: rec.last_day, src: rec.source || rec.src || src, url: src,
    blend: rec.blend || null, clim: rec.clim || null
  };
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
function holdLast(pts, t) {
  // After the last forecast hour, keep that value. Do not snap back to the issue-time
  // observation: that step showed up as a kink in the Conditional line (Westport, 2026-11-17).
  if (!pts || !pts.length) return null;
  const v = interp(pts, t);
  if (v != null) return v;
  if (t > pts[pts.length - 1][0]) return pts[pts.length - 1][1];
  return null;
}

async function load() {
  const my = ++seq; const R = range(); const now = R.now;
  setMsg("Loading tides\u2026");
  const key = T.st, st = sidOf(key), b0 = Math.min(R.start, now - SLOW_DAYS * DAY), eP = Math.max(R.end, now) + 3 * HR;
  try {
    const [pred, obs, md, cyc, pr, arch, obsP, fcP, gfsP, sst] = await Promise.all([
      coops("predictions", st, b0, eP, "&datum=MLLW&interval=6"),
      coops("water_level", st, b0, Math.min(R.end, now) + H6, "&datum=MLLW"),
      meta(st), stofsCycle(now).catch(() => null), pressure(st),
      archive(st, Math.min(R.start, now - T.sd * DAY) - 61 * HR, Math.min(R.end, now)).catch(() => ({ issues: [], calib: null })),
      obsPressureSeries(st, b0, now + HR).catch(() => ({ pts: [], src: null })),
      forecastPressure(st).catch(() => ({ pts: [], src: null })),
      gfsPressure(st).catch(() => []),
      sstTerm(st, now).catch(() => ({ dT: 0, W: 0, src: "none" })),
      loadAnom().catch(() => null)]);
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
    const pObsPts = (obsP && obsP.pts) || [], pFcPts = (fcP && fcP.pts) || [], pGfsPts = gfsP || [];
    const pIB = (t) => { const po = (t <= now) ? interp(pObsPts, t) : null; return po != null ? po : holdLast(pFcPts, t); };
    // SST term: k x anomaly vs a typical year (best source / in-situ blend). Full anomaly, not a
    // recent-change increment — default does not use STOFS, so there is no 5-day model bias to double-count.
    const W = (sst && sst.W != null && isFinite(sst.W)) ? +sst.W : ((sst && sst.k && (sst.ssta != null || sst.ssta30 != null)) ? sst.k * (sst.ssta != null ? sst.ssta : sst.ssta30) : 0);
    const r0v = rNow != null ? rNow : (base || 0);
    const cycT = cyc && cyc.t != null ? cyc.t : null;
    const ibA0 = ibFt(pIB(t0c)) || 0;
    const anom0 = (cycT != null) ? anomAt(st, t0c, cycT) : null;
    const wFull0 = (rsNow != null) ? windOnly(rsNow, anom0, interp(pGfsPts, t0c)) : null;
    // Multi-day observed leftover: mean of (gauge residual minus the pressure and warm-water parts)
    // over the 5 days ending at the newest observation. Held through the forecast. Not a STOFS field.
    let offSum = 0, offN = 0;
    const t5 = t0c - 5 * DAY;
    for (const [tt, rr] of res) {
      if (tt < t5 || tt > t0c) continue;
      const ibh = ibFt(pIB(tt));
      if (ibh == null) continue;
      offSum += rr - ibh - W; offN++;
    }
    const offset5 = offN ? offSum / offN : 0;
    const leftover = r0v - ibA0 - W - offset5;
    const partsAt = (t) => {
      const dt = t - t0c;
      const ibv = ibFt(pIB(t));
      const ib = ibv == null ? ibA0 : ibv;
      const pNow = pIB(t);
      const off = ib + W + offset5 + leftover * fadeAt(dt);
      const inStofs = !!(rs && rsEnd && t <= rsEnd[0]);
      const rsT = inStofs ? interp(rs, t) : null;
      const anom = (inStofs && cycT != null) ? anomAt(st, t, cycT) : null;
      const wT = inStofs ? windOnly(rsT, anom, interp(pGfsPts, t)) : null;
      const wind = windComp(wT, wFull0, dt);
      return { ib, W, wind, off, on: off + wind, p: pNow, offset5, leftover, anom };
    };
    const resid = (t) => T.wind ? partsAt(t).on : partsAt(t).off;
    const cond = [], condRaw = [], condOff = [], condOn = [];
    if (R.end > t0c && (rNow != null || W || pFcPts.length || pObsPts.length)) for (const [t, v] of pred) if (t >= t0c && t <= R.end) {
      const pt = partsAt(t);
      condOff.push([t, v + pt.off]); condOn.push([t, v + pt.on]);
      const r = T.wind ? pt.on : pt.off;
      condRaw.push([t, v + r]); cond.push([t, v + r]);
    }
    window.__tideWindTest = (function () {
      if (!condOff.length || condOff.length !== condOn.length) return { ok: false, n: 0 };
      let n = 0, fail = 0, zmatch = 0;
      for (let i = 0; i < condOff.length; i++) {
        const t = condOff[i][0], pt = partsAt(t);
        n++;
        if (Math.abs((condOn[i][1] - condOff[i][1]) - pt.wind) > 1e-9) fail++;
        if (Math.abs(pt.wind) <= 1e-12 && Math.abs(condOn[i][1] - condOff[i][1]) > 1e-9) fail++;
        if (Math.abs(pt.wind) <= 1e-12) zmatch++;
      }
      return { ok: fail === 0, n, fail, zeroWindHours: zmatch };
    })();
    const name = (STATIONS.find((s) => s[0] === key) || [key, key])[1];
    const tPast = Math.min(R.end, tObs != null ? tObs : now);
    const verAll = verified(pred, issues, T.vl, tPast, Math.min(R.start, now - T.sd * DAY) - HR);   // raw snapshots (r)
    const ver = verAll.filter((p) => p[0] >= R.start - HR && p[0] <= R.end + HR);
    const stats = T.vl && tObs != null ? verStats(pred, obs, verAll, tObs - T.sd * DAY, tObs) : null;
    const prNow = pIB(now) != null ? { t: now, hpa: pIB(now) } : pr;
    D = { st: key, sid: st, name, R, now, pred: pred.filter((p) => p[0] >= R.start - HR && p[0] <= R.end + HR), obs: obs.filter((p) => p[0] >= R.start - HR && p[0] <= R.end + HR),
      cond, condRaw, condOff, condOn, partsAt, sst, fcP, obsP, calib, calibBg, ver, stats, vl: T.vl, sd: T.sd, nIssues: issues.length, nArchive: issues.filter((i) => i.kind === "archive").length, rNow, rSlow, bias, cyc: sto ? cyc : null, stofsEnd: rsEnd ? rsEnd[0] : null, flood: md.flood, floods: md.floods || [], floodSkip: md.floodSkip || [], pr: prNow, tObs, method: "stofs-free" + (T.wind ? "+wind" : ""), windOn: !!T.wind,
      aifs: fcP && { src: fcP.src, run: fcP.run, note: fcP.note, latency: fcP.latency } };
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
  // t3052u: flood stages are labeled on the lines and in the hover readout, not as legend rows
  window.__tideLegend = items.map((it) => it[0]);
  c.font = F(700, 13.5); let lx, ly; const sw = 26 * s, gap = 18 * s;
  const widths = items.map((it) => sw + 8 * s + c.measureText(it[0]).width);
  const legW = widths.reduce((a, b) => a + b, 0) + gap * (items.length - 1);
  c.font = F(800, 22); const titleW = c.measureText(`${D.name}  \u00b7  ${stLabel(D.st)}`).width; c.font = F(700, 13.5);
  const legTwoRows = portrait || legW > W - 2 * pad - titleW - 40 * s;
  const legend = (x0, y0, list) => { let x = x0; list.forEach((it, i) => { c.strokeStyle = it[1]; c.lineWidth = (it[2] === -1 ? 2 : it[2] === -2 ? 2 : it[2]) * s; c.setLineDash(it[2] === -1 ? [7 * s, 5 * s] : it[2] === -2 ? [5 * s, 4 * s] : []);
    c.beginPath(); c.moveTo(x, y0 - 5 * s); c.lineTo(x + sw, y0 - 5 * s); c.stroke(); c.setLineDash([]); c.fillStyle = COL.text; c.fillText(it[0], x + sw + 8 * s, y0); x += widths[items.indexOf(it)] + gap; }); };
  let top, legendBox;
  if (!legTwoRows) { lx = W - pad - legW; ly = y1; legend(lx, ly, items); top = y1 + 40 * s;
    legendBox = { x: lx, y: ly - 13.5 * s, w: legW, h: 16.5 * s }; }
  else {   // greedy rows that fit the width (phones / 9:16)
    const rows = [[]]; let rw = 0; items.forEach((it, i) => { const w = widths[i]; if (rows[rows.length - 1].length && rw + gap + w > W - 2 * pad) { rows.push([]); rw = 0; } rw += (rows[rows.length - 1].length ? gap : 0) + w; rows[rows.length - 1].push(it); });
    rows.forEach((r, i) => legend(pad, y1 + 50 * s + i * 24 * s, r)); top = y1 + 50 * s + (rows.length - 1) * 24 * s + 18 * s;
    const legBase = y1 + 50 * s;
    legendBox = { x: pad, y: legBase - 13.5 * s, w: W - 2 * pad, h: (rows.length - 1) * 24 * s + 16.5 * s }; }
  // info lines (bottom)
  const info = [];
  const lastObs = D.obs.length ? D.obs[D.obs.length - 1] : null;
  if (lastObs && D.rNow != null) info.push(`Latest observed ${lastObs[1].toFixed(2)} ft at ${fTime.format(new Date(lastObs[0]))}  \u00b7  residual (observed \u2212 predicted) ${sgn(D.rNow, 2)} ft`);
  const bits = [];
  if (D.pr) bits.push(`Pressure ${D.pr.hpa.toFixed(1)} hPa (about ${sgn(ibFt(D.pr.hpa) || 0, 2)} ft on the water)`);
  if (D.sst && D.sst.src && D.sst.src !== "none") {
    const a30 = D.sst.ssta30, Wft = D.sst.W;
    if (a30 != null) bits.push(`Sea temperature ${sgn(a30, 2)} \u00b0C (${sgn(a30 * 1.8, 1)} \u00b0F) vs a typical year${Wft != null ? ", adding " + sgn(Wft, 2) + " ft" : ""}`);
  } else if (D.sst && D.sst.src === "none") {
    bits.push("Sea temperature unavailable; warm-water term set to 0 ft");
  }
  if (D.aifs && D.aifs.run) bits.push(`AIFS ENS ${String(D.aifs.run)}${D.aifs.src && D.aifs.src !== "aifs-ens-mean" ? " (" + D.aifs.src + " fallback)" : ""}`);
  else if (D.aifs && D.aifs.src) bits.push(`Forecast pressure ${D.aifs.src}`);
  if (bits.length) info.push(bits.join("  \u00b7  "));
  info.push(productsLine(T.wind, D.sst, D.aifs, D.obsP, D.sid));
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
  // t3061u: phone page only — a reserved 3-line readout slot between the legend and the plot, always present so hover does not shift the chart. Studio and desktop stay as they are.
  const phoneSlotH = (!STUDIO && portrait) ? 84 : 0;
  const slotBox = phoneSlotH ? { x: pad, y: top + 2, w: W - 2 * pad, h: phoneSlotH } : null;
  // Desktop: when the hover strip wraps (flood rows + pressure/warm-water), it sits below the
  // x-axis labels. Reserve that band always so hover does not cover the axis or shift the chart.
  const deskHoverH = (!STUDIO && !portrait) ? 56 : 0;
  const X0 = pad + yL, X1 = W - xR, Y0 = top + (phoneSlotH ? 6 + phoneSlotH : 10 * s), Y1 = H - bottomInfo - axisH - deskHoverH;
  if (slotBox && !opt.hoverT) { c.save(); c.strokeStyle = "rgba(125,130,140,0.28)"; c.lineWidth = 1;
    const sx = slotBox.x + 0.5, sy = slotBox.y + 0.5, sw2 = slotBox.w - 1, sh2 = slotBox.h - 1;
    c.beginPath(); c.roundRect ? c.roundRect(sx, sy, sw2, sh2, 6) : c.rect(sx, sy, sw2, sh2); c.stroke(); c.restore(); }
  // y range
  let lo = Infinity, hi = -Infinity; const scan = (a) => { for (const [, v] of a) { if (v < lo) lo = v; if (v > hi) hi = v; } };
  scan(D.pred); scan(D.obs); scan(D.cond); scan(D.ver); if (T.flood) { const hd = hi; for (const f of D.floods) if (f.v < hd + 3) hi = Math.max(hi, f.v); }   // same rule as minor, per level; skipped when Flood levels is off
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
  window.__tideFloodDrawn = []; window.__tideFloodLabels = []; window.__tideFloodLabelNote = null; const fTag = [];
  const fOn = T.flood ? D.floods.filter((f) => f.v >= lo && f.v <= hi) : [];
  // t3052u: every flood line spans the full plot. Names sit at the far left, 9.5 CSS px (Studio: 9.5*s),
  // bottom 2 px above their own line. If another line would run through a word, knock out a short gap
  // in that line only (chart-bg, a few px past the box). Shrink to 9 px if words overlap; only then shift the higher word right.
  const fTarget = (s > 1.35) ? Math.round(9.5 * s * 10) / 10 : 9.5;
  const fMin = (s > 1.35) ? Math.round(9 * s * 10) / 10 : 9;
  const fLineW = 2 * s, fHalo = Math.max(2, 1.2 * s), fPadX = 6 * s, fKo = 3, fShift = 4;
  const fGapY = Math.min(3, Math.max(2, fLineW / 2 + 1));
  const fFont = (fs) => `700 ${fs}px Montserrat, system-ui, sans-serif`;
  const boxAt = (f, fs, x) => {
    c.font = fFont(fs); const tw = c.measureText(f.lab).width, y = Y(f.v);
    const asc = fs * 0.92, desc = fs * 0.08, y1b = y - fGapY, base = y1b - desc - fHalo / 2, y0 = base - asc - fHalo / 2;
    return { k: f.k, lab: f.lab, x0: x, x1: x + tw, y0, y1: y1b, base, ly: y, tw, fontCss: fs, lineW: fLineW, s, plotX0: X0, plotX1: X1, lineX0: X0, lineX1: X1, offset: false, knockouts: [] };
  };
  const yOverlap = (a, b) => a.y0 < b.y1 && b.y0 < a.y1;
  const anyVertOverlap = (a) => { for (let i = 0; i < a.length; i++) for (let j = i + 1; j < a.length; j++) if (yOverlap(a[i], a[j]) && a[i].x0 < a[j].x1 && a[j].x0 < a[i].x1) return true; return false; };
  const placeLeft = (fs) => fOn.map((f) => boxAt(f, fs, X0 + fPadX));
  let fCss = fTarget, fLabs = placeLeft(fCss);
  while (fCss > fMin + 0.01 && anyVertOverlap(fLabs)) { fCss = Math.max(fMin, Math.round((fCss - 0.5) * 10) / 10); fLabs = placeLeft(fCss); }
  const shifted = [];
  if (anyVertOverlap(fLabs)) {
    const laid = [];
    fLabs = fOn.map((f) => {
      let b = boxAt(f, fCss, X0 + fPadX);
      for (const o of laid) if (yOverlap(b, o) && b.x0 < o.x1 && o.x0 < b.x1) { b = boxAt(f, fCss, o.x1 + fShift); b.offset = true; shifted.push(b.k); }
      laid.push(b); return b;
    });
    if (shifted.length) window.__tideFloodLabelNote = `${D.name}: offset ${shifted.join(", ")} at ${fCss}px (min type, lines still too close vertically)`;
  }
  const lineHitsLabel = (ln, lab) => ln.k !== lab.k && lab.y0 < ln.ly + fLineW / 2 + 0.5 && lab.y1 > ln.ly - fLineW / 2 - 0.5;
  for (const ln of fLabs) ln.knockouts = fLabs.filter((lab) => lineHitsLabel(ln, lab)).map((lab) => ({ k: lab.k, x0: lab.x0 - fKo, x1: lab.x1 + fKo }));
  const dashSeg = (x0, y, x1, col) => { if (x1 - x0 < 0.5) return; c.strokeStyle = col; c.lineWidth = fLineW; c.setLineDash([9 * s, 6 * s]); c.beginPath(); c.moveTo(x0, y); c.lineTo(x1, y); c.stroke(); c.setLineDash([]); };
  for (const b of fLabs) {
    const kos = b.knockouts.slice().sort((a, z) => a.x0 - z.x0); let x = X0;
    for (const k of kos) { dashSeg(x, b.ly, Math.min(k.x0, X1), FCOL[b.k]); c.fillStyle = COL.bg; c.fillRect(k.x0, b.ly - fLineW / 2 - 1, Math.max(0, k.x1 - k.x0), fLineW + 2); x = Math.max(x, k.x1); }
    dashSeg(x, b.ly, X1, FCOL[b.k]);
  }
  fTag.push(() => { c.setLineDash([]); c.textAlign = "left"; c.textBaseline = "alphabetic"; c.font = fFont(fCss);
    for (const b of fLabs) { c.lineWidth = fHalo; c.strokeStyle = COL.bg; c.strokeText(b.lab, b.x0, b.base); c.fillStyle = FCOL[b.k]; c.fillText(b.lab, b.x0, b.base); } });
  window.__tideFloodLabels = fLabs.map((b) => ({ k: b.k, x0: b.x0, x1: b.x1, y0: b.y0, y1: b.y1, ly: b.ly, lineX0: b.lineX0, lineX1: b.lineX1, knockouts: b.knockouts, offset: b.offset, plotX0: b.plotX0, plotX1: b.plotX1, fontCss: b.fontCss, lineW: b.lineW, s: b.s }));
  window.__tideFloodDrawn = fOn.map((f) => f.k);
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
  for (const t of fTag) { c.save(); t(); c.restore(); }   // flood names (plain, on top of their lines) over the curves
  // now line
  window.__tideNowLabel = null;
  if (D.now >= R.start && D.now <= R.end) { const x = Math.round(X(D.now)) + 0.5; c.strokeStyle = COL.now; c.lineWidth = 1.6 * s; c.setLineDash([6 * s, 5 * s]); c.beginPath(); c.moveTo(x, Y0); c.lineTo(x, Y1); c.stroke(); c.setLineDash([]);
    c.font = F(800, 12.5); c.textBaseline = "top"; const lab = `Now ${fTime.format(new Date(D.now))}`, tw = c.measureText(lab).width + 12 * s, th = 20 * s;
    let lx2 = Math.min(Math.max(x - tw / 2, X0 + 2), X1 - tw - 2);
    // Default: just under the top of the plot. If that pill would cover a flood-stage word (typical on a
    // phone, where "Now" sits only a couple of days from the left and Moderate/Major sit high and left),
    // drop the pill just below those words, or slide it to their right. Never snap back onto a word.
    let ny = Y0 + 4 * s;
    const nowHits = (px, py) => (fLabs || []).filter((b) => px < b.x1 && b.x0 < px + tw && py < b.y1 && b.y0 < py + th);
    if (fLabs && fLabs.length) {
      for (let i = 0; i < 8 && nowHits(lx2, ny).length; i++) {
        ny = Math.max(...nowHits(lx2, ny).map((b) => b.y1)) + Math.max(3, 4 * s);
      }
      if (ny + th > Y1 - 2 * s) {
        const clipped = Math.max(Y0 + 4 * s, Y1 - th - 2 * s);
        if (!nowHits(lx2, clipped).length) ny = clipped;
        else if (nowHits(lx2, ny).length) {
          const right = Math.max(...nowHits(lx2, Y0 + 4 * s).concat(nowHits(lx2, ny)).map((b) => b.x1)) + Math.max(3, 4 * s);
          const lxR = Math.min(Math.max(right, X0 + 2), X1 - tw - 2);
          if (!nowHits(lxR, Y0 + 4 * s).length) { lx2 = lxR; ny = Y0 + 4 * s; }
        }
      }
    }
    c.fillStyle = "rgba(21,23,28,0.85)"; c.fillRect(lx2, ny, tw, th); c.fillStyle = COL.now; c.textAlign = "left"; c.fillText(lab, lx2 + 6 * s, ny + 4 * s);
    window.__tideNowLabel = { x: lx2, y: ny, w: tw, h: th, lab }; }
  // t3052u: vertical crosshair at the hover / touch-hold time
  if (opt.hoverT != null && opt.hoverT >= R.start && opt.hoverT <= R.end) { const hx = Math.round(X(opt.hoverT)) + 0.5;
    c.strokeStyle = "rgba(244,242,238,0.92)"; c.lineWidth = 1.2 * s; c.setLineDash([]); c.beginPath(); c.moveTo(hx, Y0); c.lineTo(hx, Y1); c.stroke(); }
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
  const axisBox = { x: X0, y: Y1, w: X1 - X0, h: axisH };
  const axisYBox = { x: 0, y: Y0, w: X0, h: Y1 - Y0 };
  const notesBox = { x: pad, y: infoTop, w: W - 2 * pad, h: wrapped.length * lh };
  const layout = { X0, X1, Y0, Y1, W, H, slotH: phoneSlotH };
  window.__tideChrome = { slot: slotBox, legend: legendBox, axis: axisBox, axisY: axisYBox, stats: window.__tideStatsBox, notes: notesBox, layout };
  c.restore();
  return { X0, X1, Y0, Y1, X, Y, lo, hi, slot: slotBox, legend: legendBox, axis: axisBox, axisY: axisYBox, stats: window.__tideStatsBox, notes: notesBox, layout };
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

let geom = null, hoverT = null, hoverRaf = 0;
function readout(t) {
  if (!D || t == null) return null;
  const p = interp(D.pred, t), o = interp(D.obs, t), cc = interp(D.cond, t);
  const vv = D.ver.length ? interp(D.ver.map((q) => [q[0], q[1]]), t) : null;
  const rows = [];
  if (p != null) rows.push({ k: "pred", lab: "Official prediction", col: COL.pred, v: p });
  if (o != null) rows.push({ k: "obs", lab: "Observed", col: COL.obs, v: o });
  if (vv != null) rows.push({ k: "ver", lab: "Conditional, verified", col: COL.ver, v: vv });
  if (cc != null) rows.push({ k: "cond", lab: "Conditional Prediction", col: COL.cond, v: cc });
  if (T.flood) for (const f of D.floods) rows.push({ k: "flood-" + f.k, lab: f.lab + " flood", col: FCOL[f.k], v: f.v, flood: true });
  const time = `${fDay.format(new Date(t))} ${fTime.format(new Date(t))} ${zoneName(t)}`;
  const bits = rows.map((r) => `<span class="tv" style="color:${r.col}">${r.lab} ${r.v.toFixed(2)} ft</span>`);
  if (cc != null && D.partsAt) {
    const pt = D.partsAt(t);
    const bits2 = [`pressure ${sgn(pt.ib, 2)} ft` + (pt.p != null ? ` (${pt.p.toFixed(1)} hPa)` : ""), `warm water ${sgn(pt.W, 2)} ft`];
    if (D.sst && D.sst.src && D.sst.src !== "none") {
      const extra = [];
      if (D.sst.ssta30 != null) extra.push(`${sgn(D.sst.ssta30, 2)} \u00b0C / ${sgn(D.sst.ssta30 * 1.8, 1)} \u00b0F vs normal (not added)`);
      if (D.sst.dT != null) extra.push(`recent ${sgn(D.sst.dT, 2)} \u00b0C, ${sgn(D.sst.adj || 0, 2)} ft fades in`);
      if (extra.length) bits2[1] += ` (${extra.join("; ")})`;
    }
    if (T.wind) bits2.push(`wind ${sgn(pt.wind, 2)} ft`);
    bits.push(`<span class="tdot">${bits2.join("  \u00b7  ")}</span>`);
  }
  const html = `<span class="tt">${time}</span>` + bits.join("");
  return { t, rows, html };
}
function overlaps(a, b, eps) { eps = eps || 0.5; return a.x + a.w > b.x + eps && b.x + b.w > a.x + eps && a.y + a.h > b.y + eps && b.y + b.h > a.y + eps; }
// Place the compact readout as a strip outside the plot (above it if it fits, otherwise below). Never covers the curves.
function placeStrip(tip, box, plot, maxW, axisH) {
  const gap = 3;
  tip.style.maxWidth = Math.max(80, maxW) + "px";
  tip.style.left = "0px"; tip.style.top = "0px";
  const tw = tip.offsetWidth, th = tip.offsetHeight;
  let left = plot.x, top = plot.y - th - gap;
  // One-line strips sit just above the plot (under the title/legend). Taller wrapped strips go
  // below the x-axis labels (not into the axis band) so they don't cover the legend or the ticks.
  const aboveOk = th <= 32 && top >= box.y + 2 && !overlaps({ x: left, y: top, w: tw, h: th }, plot);
  if (!aboveOk) {
    const skip = axisH || 0;
    top = plot.y + plot.h + skip + gap;
    if (top + th > box.y + box.h - 2) top = Math.max(plot.y + plot.h + skip + 1, box.y + box.h - th - 2);
  }
  if (left + tw > box.x + box.w - 4) left = Math.max(box.x + 4, box.x + box.w - tw - 4);
  if (left < box.x + 4) left = box.x + 4;
  tip.style.left = left + "px"; tip.style.top = top + "px";
  return { x: left, y: top, w: tip.offsetWidth, h: tip.offsetHeight };
}
function placeTip(cssX, cssY) {
  const tip = $("tip"), cv = $("tc"), wrap = $("wrap"); if (!tip || !cv || !wrap || STUDIO) return;
  const info = readout(hoverT);
  if (!info) { tip.hidden = true; window.__tideHover = null; return; }
  tip.innerHTML = info.html; tip.hidden = false;
  const ox = cv.offsetLeft, oy = cv.offsetTop;
  let tipBox;
  if (geom && geom.slot) {
    const sl = geom.slot;
    tip.style.maxWidth = Math.max(80, sl.w) + "px";
    tip.style.left = "0px"; tip.style.top = "0px";
    const tw = tip.offsetWidth, th = tip.offsetHeight;
    let left = ox + sl.x, top = oy + sl.y + Math.max(0, (sl.h - th) / 2);
    if (top < oy + sl.y) top = oy + sl.y;
    if (top + th > oy + sl.y + sl.h) top = oy + sl.y + Math.max(0, sl.h - th);
    if (left + tw > ox + sl.x + sl.w) left = ox + sl.x + Math.max(0, sl.w - tw);
    if (left < ox + sl.x) left = ox + sl.x;
    tip.style.left = left + "px"; tip.style.top = top + "px";
    tipBox = { x: left, y: top, w: tip.offsetWidth, h: tip.offsetHeight };
  } else {
    const plot = geom ? { x: ox + geom.X0, y: oy + geom.Y0, w: geom.X1 - geom.X0, h: geom.Y1 - geom.Y0 } : { x: ox + 8, y: oy + 80, w: cv.clientWidth - 16, h: 200 };
    const box = { x: 0, y: 0, w: wrap.clientWidth, h: wrap.clientHeight };
    tipBox = placeStrip(tip, box, plot, plot.w, geom && geom.axis ? geom.axis.h : 0);
  }
  // Guard uses canvas CSS pixels (origin at the canvas, not the wrap).
  const tipCv = { x: tipBox.x - ox, y: tipBox.y - oy, w: tipBox.w, h: tipBox.h };
  const plotCv = geom ? { x: geom.X0, y: geom.Y0, w: geom.X1 - geom.X0, h: geom.Y1 - geom.Y0 } : null;
  const x = geom ? geom.X(hoverT) : cssX;
  window.__tideHover = { t: hoverT, x, y0: geom ? geom.Y0 : 0, y1: geom ? geom.Y1 : 0, rows: info.rows, tip: tipCv, plot: plotCv, layout: geom && geom.layout, regions: geom ? { plot: plotCv, legend: geom.legend, axis: geom.axis, axisY: geom.axisY, stats: geom.stats, notes: geom.notes, slot: geom.slot } : null };
}
function clearHover() { hoverT = null; window.__tideHover = null; const tip = $("tip"); if (tip) tip.hidden = true; if (!STUDIO) draw(); }
function applyHover(clientX, clientY, fromTouch) {
  if (!D || !geom) return;
  const cv = $("tc"), b = cv.getBoundingClientRect(), x = clientX - b.left, y = clientY - b.top;
  if (x < geom.X0 || x > geom.X1 || y < geom.Y0 || y > geom.Y1) { if (!fromTouch) clearHover(); else { const tip = $("tip"); if (tip) tip.hidden = true; hoverT = null; window.__tideHover = null; draw(); } return; }
  const t = D.R.start + (x - geom.X0) / (geom.X1 - geom.X0) * (D.R.end - D.R.start), tt = Math.round(t / H6) * H6;
  hoverT = tt;
  const go = () => { hoverRaf = 0; draw(); placeTip(x, y); };
  if (fromTouch) go(); else if (!hoverRaf) hoverRaf = requestAnimationFrame(go);
}
function draw() {
  if (STUDIO) return; const cv = $("tc"), w = cv.clientWidth, h = cv.clientHeight; if (!w || !h) return;
  const dpr = Math.min(window.devicePixelRatio || 1, 3); const bw = Math.round(w * dpr), bh = Math.round(h * dpr);
  if (cv.width !== bw || cv.height !== bh) { cv.width = bw; cv.height = bh; }
  const c = cv.getContext("2d"); c.setTransform(dpr, 0, 0, dpr, 0, 0);
  const s = Math.max(0.78, Math.min(1.25, Math.min(w / 1100, h / 640) * 1.05));
  geom = drawChart(c, w, h, { scale: s, hoverT }); window.__tideSharp = { dpr, cssW: w, backingW: cv.width, scale: s };
}
function setMsg(t) { const m = $("msg"); if (m) m.textContent = STUDIO ? "" : t; }
function note() { const n = $("tnote"); if (!n || !D) return;
  const bits = [];
  bits.push(T.wind ? "Wind surge on" : "Default (no wind)");
  if (D.aifs && D.aifs.run) bits.push("AIFS ENS " + String(D.aifs.run));
  else if (D.aifs && D.aifs.src) bits.push(D.aifs.src);
  if (T.wind && D.cyc) bits.push("surge model " + new Date(D.cyc.t).toISOString().slice(5, 13).replace("T", " ") + "Z");
  n.textContent = bits.join("  \u00b7  "); }

// ---- UI ----
function syncURL() { const u = new URL(location.href); u.searchParams.set("st", T.st); u.searchParams.set("vl", String(T.vl)); u.searchParams.set("sd", String(T.sd)); if (T.from) u.searchParams.set("from", T.from); else u.searchParams.delete("from"); u.searchParams.set("days", String(T.days)); history.replaceState(null, "", u); try { localStorage.setItem("tide:st", T.st); } catch (e) { /* private */ } }
function ui() {
  const st = $("st"); st.innerHTML = STATIONS.map(([id, n]) => `<option value="${id}">${n} (${stLabel(id)})</option>`).join(""); st.value = T.st;
  const ds = $("days"); ds.innerHTML = DAYS.map((d) => `<option value="${d}">${d}</option>`).join(""); ds.value = String(T.days);
  const fr = $("from"); fr.value = ymdLocal(range().start);
  const vl = $("vl"), sd = $("sd");
  if (vl) { vl.innerHTML = LEADS.map((l) => `<option value="${l}">${l ? `${l}\u2013${l + 6} h` : "Off"}</option>`).join(""); vl.value = String(T.vl); vl.onchange = () => { T.vl = +vl.value; syncURL(); load(); }; }
  if (sd) { sd.innerHTML = SDAYS.map((d) => `<option value="${d}">${d} days</option>`).join(""); sd.value = String(T.sd); sd.onchange = () => { T.sd = +sd.value; syncURL(); load(); }; }
  const floodChip = () => { const b = $("floodtog"); if (!b) return; b.setAttribute("aria-pressed", T.flood ? "true" : "false"); b.title = T.flood ? "Hide the NWS flood stage lines" : "Show the NWS flood stage lines"; };
  const windChip = () => { const b = $("windtog"); if (!b) return; b.setAttribute("aria-pressed", T.wind ? "true" : "false"); b.title = T.wind ? "Hide the wind-driven setup from the NOAA surge model (on now)" : "Add the wind-driven setup from the NOAA surge model. Off by default."; };
  floodChip(); windChip();
  const ft = $("floodtog");
  if (ft) ft.onclick = () => { T.flood = !T.flood; try { localStorage.setItem("tide:flood", T.flood ? "1" : "0"); } catch (e) { /* private */ } floodChip(); draw(); window.__tideDrawn++; if (hoverT != null) { const cv = $("tc"), b = cv.getBoundingClientRect(); placeTip((geom.X0 + geom.X1) / 2, (geom.Y0 + geom.Y1) / 2); } };
  const wt = $("windtog");
  if (wt) wt.onclick = () => { T.wind = !T.wind; try { localStorage.setItem("tide:wind", T.wind ? "1" : "0"); } catch (e) { /* private */ } windChip(); if (D && D.condOff && D.condOn) { D.cond = T.wind ? D.condOn : D.condOff; D.condRaw = D.cond; D.windOn = !!T.wind; D.method = "stofs-free" + (T.wind ? "+wind" : ""); } note(); draw(); window.__tideDrawn++; if (hoverT != null) { const cv = $("tc"), b = cv.getBoundingClientRect(); placeTip((geom.X0 + geom.X1) / 2, (geom.Y0 + geom.Y1) / 2); } };
  st.onchange = () => { T.st = st.value; syncURL(); load(); };
  ds.onchange = () => { T.days = +ds.value; syncURL(); load(); };
  fr.onchange = () => { if (/^\d{4}-\d{2}-\d{2}$/.test(fr.value)) { T.from = fr.value; syncURL(); load(); } };
  $("today").onclick = () => { T.from = ""; T.days = 9; ds.value = "9"; fr.value = ymdLocal(range().start); syncURL(); load(); };
  $("reload").onclick = () => { shefCache = { url: "", txt: "" }; load(); };
  if (!STUDIO) {
    addEventListener("resize", () => requestAnimationFrame(draw));
    const cv = $("tc"), tip = $("tip");
    // t3052u: desktop hover shows a vertical crosshair + readout; phone uses tap or touch-and-hold.
    // Touch is single-finger only and ignores a moved finger, so a later phone-stretch merge (pinch / one-finger pan / double-tap reset) can coexist.
    const tPtrs = new Set(); let tHold = null;
    cv.addEventListener("pointermove", (e) => {
      if (e.pointerType === "touch") {
        if (tHold && e.pointerId === tHold.id && !tHold.fired && Math.hypot(e.clientX - tHold.x0, e.clientY - tHold.y0) > 12) { clearTimeout(tHold.tid); tHold = null; }
        return;
      }
      applyHover(e.clientX, e.clientY, false);
    });
    cv.addEventListener("pointerleave", (e) => { if (e.pointerType !== "touch") clearHover(); });
    cv.addEventListener("pointerdown", (e) => {
      if (e.pointerType !== "touch" || !D || !geom) return;
      tPtrs.add(e.pointerId);
      if (tPtrs.size >= 2) { if (tHold) { clearTimeout(tHold.tid); tHold = null; } return; }
      tHold = { id: e.pointerId, x0: e.clientX, y0: e.clientY, fired: false, tid: setTimeout(() => { if (!tHold) return; tHold.fired = true; applyHover(tHold.x0, tHold.y0, true); }, 400) };
    });
    const tEnd = (e) => {
      if (e.pointerType !== "touch") return; tPtrs.delete(e.pointerId);
      if (!tHold || e.pointerId !== tHold.id) return;
      clearTimeout(tHold.tid);
      const moved = Math.hypot(e.clientX - tHold.x0, e.clientY - tHold.y0) > 12;
      if (e.type === "pointerup" && !tHold.fired && !moved && tPtrs.size === 0) applyHover(e.clientX, e.clientY, true);
      tHold = null;
    };
    cv.addEventListener("pointerup", tEnd); cv.addEventListener("pointercancel", tEnd);
  }
}
window.TIDE = {
  draw: (c, W, H, opt) => drawChart(c, W, H, opt),
  state: () => D, stations: STATIONS, readout, geom: () => geom,
  qa: () => D ? { st: D.st, name: D.name, pred: D.pred.length, obs: D.obs.length, cond: D.cond.length, method: D.method, cycle: D.cyc ? new Date(D.cyc.t).toISOString() : null,
    rNow: D.rNow, rSlow: D.rSlow, bias: D.bias, flood: D.flood, floods: D.floods, floodSkip: D.floodSkip, floodOn: !!T.flood, floodDrawn: window.__tideFloodDrawn || [], floodLabels: window.__tideFloodLabels || [], floodLabelNote: window.__tideFloodLabelNote || null, legend: window.__tideLegend || [], hover: window.__tideHover || null, sid: D.sid, start: D.R.start, end: D.R.end, now: D.now,
    statsBox: window.__tideStatsBox || null, chrome: window.__tideChrome || null, arch: ARCH, calib: D.calib ? D.calib.c.map((b) => b.corr) : null, calibBg: D.calibBg ? { t: D.calibBg.t, c: D.calibBg.c.map((b) => b.corr) } : null, ver: D.ver.length, verHindcast: D.ver.filter((p) => !p[2]).length, issues: D.nIssues, archived: D.nArchive, vl: D.vl, sd: D.sd, stats: D.stats,
    condAboveFrac: D.cond.length ? D.cond.filter(([t, v]) => v >= (interp(D.pred, t) || 0)).length / D.cond.length : null, sharp: window.__tideSharp || null, windOn: !!T.wind, sst: D.sst || null, aifs: D.aifs || null, windTest: window.__tideWindTest || null, nowLabel: window.__tideNowLabel || null, products: productsLine(!!T.wind, D.sst, D.aifs, D.obsP, D.sid) } : { err: window.__tideErr || null },
};
ui(); syncURL(); load();
setInterval(() => { if (document.visibilityState === "visible") load(); }, 10 * 60000);   // new observations every 6 min; refresh every 10
})();
