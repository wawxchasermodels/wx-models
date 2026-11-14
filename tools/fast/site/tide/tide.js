// Tides viewer (Benjamin t3011u, 2026-11-14): NOAA official tide prediction, observed water level, and an experimental
// "Conditional Prediction" = prediction + forecast non-tidal residual (STOFS-2D-Global sub-tidal water level, bias-corrected to the current
// observed residual, relaxing to the 30-day mean residual = slow coastal sea level anomaly incl. Kelvin waves / El Nino).
// All data is public NOAA (CO-OPS API with CORS, STOFS on the NOAA Open Data bucket). No keys. Times shown in Pacific time.
// window.TIDE.draw(ctx, W, H, opt) draws the chart into any 2D context in CSS px (Studio draws it into its frames).
(() => {
"use strict";
const API = "https://api.tidesandcurrents.noaa.gov/api/prod/datagetter";
const MD = "https://api.tidesandcurrents.noaa.gov/mdapi/prod/webapi/stations/";
const S3 = "https://noaa-gestofs-pds.s3.amazonaws.com/";
const TZ = "America/Los_Angeles";
const STATIONS = [
  ["9441102", "Westport, WA"], ["9440910", "Toke Point, WA"], ["9442396", "La Push, WA"], ["9443090", "Neah Bay, WA"],
  ["9444090", "Port Angeles, WA"], ["9444900", "Port Townsend, WA"], ["9449880", "Friday Harbor, WA"], ["9449424", "Cherry Point, WA"],
  ["9447130", "Seattle, WA"], ["9446484", "Tacoma, WA"], ["9439040", "Astoria, OR"],
];
const DAYS = [3, 5, 7, 9, 14, 17, 21, 30];
const COL = { pred: "#5aa9ff", obs: "#ff5d5d", cond: "#ffb02e", now: "#f4f2ee", flood: "#ff7a45", grid: "#2c3039", axis: "#a7abb3", text: "#f4f2ee", bg: "#15171c" };
const H6 = 6 * 60000, HR = 3600000, DAY = 86400000;
const TAU_BIAS = 12 * HR, TAU_RELAX = 24 * HR, SLOW_DAYS = 30;
const Q = new URLSearchParams(location.search), STUDIO = !!Q.get("studio");
const $ = (id) => document.getElementById(id);
const T = { st: Q.get("st") || localStorage.getItem("tide:st") || "9441102", from: Q.get("from") || "", days: +(Q.get("days") || 9) };
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
    let flood = null;
    if (mllw != null) { if (fl.nos_minor != null) flood = { v: fl.nos_minor - mllw, src: "NOS" }; else if (fl.nws_minor != null) flood = { v: fl.nws_minor - mllw, src: "NWS" }; }
    return { shef: s.shefcode || "", flood };
  } catch (e) { return { shef: "", flood: null }; }
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

function interp(pts, t) {   // linear on a sorted [t,v] array, null outside
  if (!pts || !pts.length || t < pts[0][0] || t > pts[pts.length - 1][0]) return null;
  let lo = 0, hi = pts.length - 1; while (hi - lo > 1) { const mid = (lo + hi) >> 1; if (pts[mid][0] <= t) lo = mid; else hi = mid; }
  const a = pts[lo], b = pts[hi]; if (b[0] === a[0]) return a[1]; return a[1] + (b[1] - a[1]) * (t - a[0]) / (b[0] - a[0]);
}

async function load() {
  const my = ++seq; const R = range(); const now = R.now;
  setMsg("Loading tides\u2026");
  const st = T.st, b0 = Math.min(R.start, now - SLOW_DAYS * DAY), eP = Math.max(R.end, now) + 3 * HR;
  try {
    const [pred, obs, md, cyc, pr] = await Promise.all([
      coops("predictions", st, b0, eP, "&datum=MLLW&interval=6"),
      coops("water_level", st, b0, Math.min(R.end, now) + H6, "&datum=MLLW"),
      meta(st), stofsCycle(now).catch(() => null), pressure(st)]);
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
    const cond = []; if (R.end > t0c && (rNow != null || rs)) for (const [t, v] of pred) if (t >= t0c && t <= R.end) cond.push([t, v + resid(t)]);
    const name = (STATIONS.find((s) => s[0] === st) || [st, st])[1];
    D = { st, name, R, now, pred: pred.filter((p) => p[0] >= R.start - HR && p[0] <= R.end + HR), obs: obs.filter((p) => p[0] >= R.start - HR && p[0] <= R.end + HR),
      cond, rNow, rSlow, bias, cyc: sto ? cyc : null, stofsEnd: rsEnd ? rsEnd[0] : null, flood: md.flood, pr, tObs, method: sto && rsNow != null ? "stofs" : "persist" };
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
  c.font = F(800, 22); const y1 = pad + 22 * s; c.fillText(`${D.name}  \u00b7  ${D.st}`, pad, y1);
  c.font = F(600, 13.5); c.fillStyle = COL.axis;
  c.fillText(`Water level, feet above MLLW  \u00b7  ${fMd.format(new Date(R.start))} \u2013 ${fMd.format(new Date(R.end - 1))}, ${new Date(R.end - 1).getUTCFullYear()}  \u00b7  ${zoneName(R.now)}`, pad, y1 + 21 * s);
  // legend
  const items = [["Official prediction", COL.pred, 2.2], ["Observed", COL.obs, 2.2], ["Conditional Prediction (experimental)", COL.cond, 3.2]];
  if (D.flood) items.push([`Minor flood ${D.flood.v.toFixed(1)} ft (${D.flood.src})`, COL.flood, -1]);
  c.font = F(700, 13.5); let lx, ly; const sw = 26 * s, gap = 18 * s;
  const widths = items.map((it) => sw + 8 * s + c.measureText(it[0]).width);
  const legW = widths.reduce((a, b) => a + b, 0) + gap * (items.length - 1);
  c.font = F(800, 22); const titleW = c.measureText(`${D.name}  \u00b7  ${D.st}`).width; c.font = F(700, 13.5);
  const legTwoRows = portrait || legW > W - 2 * pad - titleW - 40 * s;
  const legend = (x0, y0, list) => { let x = x0; list.forEach((it, i) => { c.strokeStyle = it[1]; c.lineWidth = Math.abs(it[2] === -1 ? 2 : it[2]) * s; c.setLineDash(it[2] === -1 ? [7 * s, 5 * s] : []);
    c.beginPath(); c.moveTo(x, y0 - 5 * s); c.lineTo(x + sw, y0 - 5 * s); c.stroke(); c.setLineDash([]); c.fillStyle = COL.text; c.fillText(it[0], x + sw + 8 * s, y0); x += widths[items.indexOf(it)] + gap; }); };
  let top;
  if (!legTwoRows) { lx = W - pad - legW; ly = y1; legend(lx, ly, items); top = y1 + 40 * s; }
  else {   // greedy rows that fit the width (phones / 9:16)
    const rows = [[]]; let rw = 0; items.forEach((it, i) => { const w = widths[i]; if (rows[rows.length - 1].length && rw + gap + w > W - 2 * pad) { rows.push([]); rw = 0; } rw += (rows[rows.length - 1].length ? gap : 0) + w; rows[rows.length - 1].push(it); });
    rows.forEach((r, i) => legend(pad, y1 + 50 * s + i * 24 * s, r)); top = y1 + 50 * s + (rows.length - 1) * 24 * s + 18 * s; }
  // info lines (bottom)
  const info = [];
  const lastObs = D.obs.length ? D.obs[D.obs.length - 1] : null;
  if (lastObs && D.rNow != null) info.push(`Latest observed ${lastObs[1].toFixed(2)} ft at ${fTime.format(new Date(lastObs[0]))}  \u00b7  residual (observed \u2212 predicted) ${sgn(D.rNow, 2)} ft`);
  const bits = [];
  if (D.pr) bits.push(`Pressure ${D.pr.hpa.toFixed(1)} hPa (inverse barometer \u2248 ${sgn((1013.25 - D.pr.hpa) * 0.0328, 2)} ft)`);
  if (D.rSlow != null) bits.push(`30-day mean residual ${sgn(D.rSlow, 2)} ft (slow anomaly, Kelvin wave / El Ni\u00f1o)`);
  if (bits.length) info.push(bits.join("  \u00b7  "));
  info.push(D.method === "stofs" ? `Conditional = official + STOFS-2D-Global ${new Date(D.cyc.t).getUTCHours().toString().padStart(2, "0")}Z surge + anomaly (bias ${sgn(D.bias, 2)} ft fading 12 h), then the 30-day mean. Experimental, not official.`
    : `Conditional = official + current residual relaxing to the 30-day mean (STOFS guidance unavailable). Experimental, not official.`);
  const infoFs = portrait ? 12.5 : 12.5, lh = 18 * s;
  // wrap info lines to width
  c.font = F(600, infoFs); const wrapped = [];
  for (const l of info) { const words = l.split(" "); let cur = ""; for (const w of words) { const t = cur ? cur + " " + w : w; if (c.measureText(t).width > W - 2 * pad && cur) { wrapped.push(cur); cur = w; } else cur = t; } if (cur) wrapped.push(cur); }
  const bottomInfo = wrapped.length * lh + 8 * s;
  const axisH = 40 * s, yL = 46 * s, xR = pad + 8 * s;
  const X0 = pad + yL, X1 = W - xR, Y0 = top + 10 * s, Y1 = H - bottomInfo - axisH;
  // y range
  let lo = Infinity, hi = -Infinity; const scan = (a) => { for (const [, v] of a) { if (v < lo) lo = v; if (v > hi) hi = v; } };
  scan(D.pred); scan(D.obs); scan(D.cond); if (D.flood && D.flood.v < hi + 3) hi = Math.max(hi, D.flood.v);
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
  if (D.flood && D.flood.v >= lo && D.flood.v <= hi) { c.strokeStyle = COL.flood; c.lineWidth = 2 * s; c.setLineDash([9 * s, 6 * s]); const y = Y(D.flood.v); c.beginPath(); c.moveTo(X0, y); c.lineTo(X1, y); c.stroke(); c.setLineDash([]); }
  const line = (pts, col, w, gapMs) => { if (!pts.length) return; c.strokeStyle = col; c.lineWidth = w * s; c.lineJoin = "round"; c.lineCap = "round"; c.beginPath(); let pen = false, lt = 0;
    for (const [t, v] of pts) { const x = X(t), y = Y(v); if (!pen || (gapMs && t - lt > gapMs)) { c.moveTo(x, y); pen = true; } else c.lineTo(x, y); lt = t; } c.stroke(); };
  line(D.pred, COL.pred, 2.2);
  line(D.obs, COL.obs, 2.2, 31 * 60000);
  if (D.cond.length) { c.save(); c.shadowColor = "rgba(0,0,0,0.55)"; c.shadowBlur = 3 * s; line(D.cond, COL.cond, 3.2); c.restore(); }
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
  wrapped.forEach((l, i) => c.fillText(l, pad, H - bottomInfo + (i + 1) * lh - 2 * s));
  c.restore();
  return { X0, X1, Y0, Y1, X, Y, lo, hi };
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
function syncURL() { const u = new URL(location.href); u.searchParams.set("st", T.st); if (T.from) u.searchParams.set("from", T.from); else u.searchParams.delete("from"); u.searchParams.set("days", String(T.days)); history.replaceState(null, "", u); try { localStorage.setItem("tide:st", T.st); } catch (e) { /* private */ } }
function ui() {
  const st = $("st"); st.innerHTML = STATIONS.map(([id, n]) => `<option value="${id}">${n} (${id})</option>`).join(""); st.value = T.st;
  const ds = $("days"); ds.innerHTML = DAYS.map((d) => `<option value="${d}">${d}</option>`).join(""); ds.value = String(T.days);
  const fr = $("from"); fr.value = ymdLocal(range().start);
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
      const p = interp(D.pred, tt), o = interp(D.obs, tt), cc = interp(D.cond, tt);
      tip.innerHTML = `${fDay.format(new Date(tt))} ${fTime.format(new Date(tt))}` + (p != null ? `<br><span style="color:${COL.pred}">Prediction ${p.toFixed(2)} ft</span>` : "") +
        (o != null ? `<br><span style="color:${COL.obs}">Observed ${o.toFixed(2)} ft</span>` : "") + (cc != null ? `<br><span style="color:${COL.cond}">Conditional ${cc.toFixed(2)} ft</span>` : "");
      tip.hidden = false; const w = tip.offsetWidth; tip.style.left = Math.min(x + 14, b.width - w - 4) + "px"; tip.style.top = Math.max(4, y - 70) + "px"; });
    cv.addEventListener("pointerleave", () => { tip.hidden = true; });
  }
}
window.TIDE = {
  draw: (c, W, H, opt) => drawChart(c, W, H, opt),
  state: () => D, stations: STATIONS,
  qa: () => D ? { st: D.st, name: D.name, pred: D.pred.length, obs: D.obs.length, cond: D.cond.length, method: D.method, cycle: D.cyc ? new Date(D.cyc.t).toISOString() : null,
    rNow: D.rNow, rSlow: D.rSlow, bias: D.bias, flood: D.flood, start: D.R.start, end: D.R.end, now: D.now,
    condAboveFrac: D.cond.length ? D.cond.filter(([t, v]) => v >= (interp(D.pred, t) || 0)).length / D.cond.length : null, sharp: window.__tideSharp || null } : { err: window.__tideErr || null },
};
ui(); syncURL(); load();
setInterval(() => { if (document.visibilityState === "visible") load(); }, 10 * 60000);   // new observations every 6 min; refresh every 10
})();
