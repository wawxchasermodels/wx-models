// WA Maps (Phase 1, 10-31-26, Benjamin 8:58 AM: "I would rather have my state view forecast maps built into the website first").
// The posted Washington state-view NBM Lows / Highs maps, drawn in the browser from the NBM fields already in R2.
// Static layers come from a kit built by the server renderer itself (wamaps/build_kit.py runs nbm_map.render with hooks): dark base,
// overlay (borders, fades, scale, model tag, town names, logo), data mask, LUT (map px -> NBM grid), Impact titles, label layout.
// Here: data fill (v8 stepped palette, band edges, white 32F line), value numbers, title, summary lines and date line.
// Shared pieces (kit loading, fill, labels, summary, save) are product-neutral so gusts / rain / snow / observed can plug in (Phase 2+).
"use strict";
const DATA = window.WX_DATA || "data/", KIT = "wamaps/kit/", $ = id => document.getElementById(id), Q = new URLSearchParams(location.search);
const WA = { man: null, runs: {}, fields: new Map(), kits: {}, imgs: {} };
const VIEWS = [["full", "Washington"], ["west", "Western WA"], ["east", "Eastern WA"]];
const KINDS = [["low", "Lows"], ["high", "Highs"], ["gust", "Max gust"], ["precip", "Precip total"], ["snow", "Snow total"], ["wind", "12 h max wind"], ["tmin24", "24 h min temp"], ["tmax24", "24 h max temp"], ["snod", "Snow depth from 0\""], ["kuchera", "Kuchera snow"]];
// WA Maps quick slice (10-31-26 12:35 PM, Benjamin: "add most recent European data, and hrrr", "precipitation totals, let me choose the time
// frame in little boxes with dates and time in UT", snow, "go out like 7 days"): totals from NBM / ECMWF 9 km / ECMWF 0.25 / HRRR, window
// picked in two UTC boxes, capped at 168 h. Lows / highs stay NBM. Kit extras from wamaps/build_totals_kit.py (per-model LUT + label points,
// overlay without the temp scale and tag, Impact titles rasterized there).
// 11-04 (t2310u/t2311u): model sources are one table so more (European) sources plug in later: lut = which kit grid (LUT + label points)
// the model's fast crop shares (EPS uses the IFS 0.25 grid), ec = ECMWF data (licence credit), kinds = the window products it can make.
const SRC = { nbm: { tag: "[NBM 2.5 km]", name: "NBM", res: "NBM 2.5 km", kinds: ["precip", "snow", "gust"] }, ifs9: { tag: "[ECMWF 9 km]", name: "ECMWF 9 km", ec: 1, kinds: ["precip", "snow"] },
              ifs: { tag: "[ECMWF 0.25°]", name: "ECMWF 0.25°", res: "ECMWF IFS 0.25°", ec: 1, kinds: ["precip", "snow", "gust"] },
              eps: { tag: "[ECMWF ENS]", name: "ECMWF ENS mean", res: "ECMWF ENS mean 0.25°", ec: 1, lut: "ifs", kinds: ["precip", "snow", "gust", "tmin24", "tmax24"] },   // 11-09 queue B: EPS mean precip/snow/temps; gusts were already here
              hrrr: { tag: "[HRRR 3 km]", name: "HRRR", res: "HRRR 3 km", kinds: ["precip", "snow", "gust", "wind", "tmin24", "tmax24", "snod", "kuchera"] } };
// Western WA gusts: HRRR and the standard NBM 10 m gust only (both instantaneous at the valid hour, maxed over the
// window below). No ensemble (EPS) and no IFS in that menu. Full state and Eastern WA keep their gust sources.
const lutOf = m => (SRC[m] && SRC[m].lut) || m;
const TOTALS = new Set(["precip", "snow", "gust", "wind", "tmin24", "tmax24", "snod", "kuchera"]), MAXH = 168;
const PT = "America/Los_Angeles", DAYS = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"];
const INK = "rgb(14,16,22)";
// ---------------------------------------------------------------- products (Phase 2+ adds gusts / rain / snow / observed here)
// v8 temperature palette, identical to nbm_map.py (0-110 F stepped: 4 F below 32, 2 F from 32 to 70, 5 F above; alternate bands x0.9)
const TEMP = (() => {
  const E = []; for (let v = 0; v < 32; v += 4) E.push(v); for (let v = 32; v < 70; v += 2) E.push(v); for (let v = 70; v <= 110; v += 5) E.push(v);
  const A = [[0, [95, 20, 125]], [8, [135, 60, 195]], [16, [85, 75, 220]], [24, [40, 95, 215]], [31.9, [30, 115, 220]], [32, [220, 245, 255]], [34, [150, 225, 250]],
             [36, [90, 205, 225]], [39, [55, 185, 170]], [42, [40, 165, 100]], [46, [90, 190, 60]], [50, [150, 210, 60]], [54, [200, 225, 70]], [58, [235, 235, 85]],
             [63, [250, 222, 75]], [67.9, [250, 205, 65]], [68, [250, 160, 50]], [72, [245, 130, 45]], [78, [235, 95, 40]], [85, [215, 45, 35]], [95, [170, 15, 30]], [110, [110, 0, 20]]];
  const pyr = x => { const f = Math.floor(x), r = x - f; return r > 0.5 || (r === 0.5 && f % 2) ? f + 1 : f; };   // Python round (half to even)
  const pal = t => { for (let k = 0; k < A.length - 1; k++) { const [a, ca] = A[k], [b, cb] = A[k + 1];
    if (t <= b) { const f = (t - a) / (b - a); return ca.map((c, i) => pyr(c + (cb[i] - c) * f)); } } return A[A.length - 1][1]; };
  const I32 = E.indexOf(32), cols = [];
  for (let i = 0; i < E.length - 1; i++) cols.push(pal((E[i] + E[i + 1]) / 2).map(c => Math.min(255, Math.trunc(c * ((i - I32) % 2 === 0 ? 1 : 0.9)))));
  // band index of the ROUNDED value (floor(v + 0.5)), as a lookup over whole degrees
  const band = v => { const r = Math.floor(v + 0.5); let i = 0; while (i < E.length - 1 && E[i + 1] <= r) i++; return Math.min(i, cols.length - 1); };
  const labs = E.slice(0, -1).map(e => (e === 0 || e === 32 || e === 50 || e === 70 || e === 90) ? String(e) : "");
  labs[labs.length - 1] = "110";
  return { edges: E, cols, band, line32: 31.5,
           valColor: t => t <= 32 ? "rgb(150,220,255)" : t > 85 ? "rgb(255,72,60)" : "#fff", pyr,
           labs, fmt: v => String(pyr(v)), unit: "" };
})();
const blendCol = (A, v) => { if (v <= A[0][0]) return A[0][1]; if (v >= A[A.length - 1][0]) return A[A.length - 1][1];
  for (let k = 0; k < A.length - 1; k++) { const [a, ca] = A[k], [b, cb] = A[k + 1]; if (v >= a && v <= b) { const t = (v - a) / (b - a); return ca.map((c, i) => Math.round(c + (cb[i] - c) * t)); } } };
const mkTotPal = (E, cols, labs, fmt, unit) => ({ edges: E, cols, labs, fmt, unit, line32: Infinity, edgeF: 1, valColor: () => "#fff",
  band: v => { if (!(v >= E[0])) return -1; let i = 0; while (i < cols.length - 1 && v >= E[i + 1]) i++; return i; } });
const RAIN = (() => {
  const E = [0.01]; for (let k = 1; k <= 40; k++) E.push(+(0.1 * k).toFixed(2)); for (let k = 1; k <= 16; k++) E.push(4 + 0.5 * k);
  const A = [[0.01, [215, 245, 205]], [0.10, [180, 232, 165]], [0.30, [130, 208, 110]], [0.50, [75, 178, 78]], [0.70, [35, 138, 55]], [0.90, [15, 95, 42]],
             [1.00, [250, 240, 150]], [1.25, [250, 225, 60]], [1.50, [250, 200, 50]], [1.75, [250, 175, 45]], [2.25, [245, 135, 40]], [2.75, [235, 100, 35]],
             [3.00, [220, 50, 40]], [3.30, [190, 30, 35]], [3.60, [155, 18, 35]], [3.90, [120, 10, 40]],
             [4.00, [225, 65, 175]], [5.50, [170, 50, 195]], [7.00, [110, 40, 160]], [8.50, [150, 115, 215]], [10.0, [190, 170, 235]], [11.5, [230, 222, 250]], [12.0, [255, 255, 255]]];
  const cols = E.map(e => blendCol(A, e));   // 57 bins, color at each bin's lower edge
  const labs = E.map(e => e < 0.5 ? "" : e <= 4 ? (Math.abs(e * 2 - Math.round(e * 2)) < 1e-9 ? String(+e.toFixed(1)) : "") : (Math.abs(e - Math.round(e)) < 1e-9 ? String(e) : ""));
  labs[labs.length - 1] = "12+";
  return mkTotPal(E, cols, labs, v => v < 0.005 ? "0" : v.toFixed(2), " in");
})();
const SNOW = (() => {
  const E = [0.1, 1, 2, 3, 4, 5, 6, 8, 10, 12, 15, 18, 21, 24, 30, 36, 42, 48, 60, 72];
  const cols = [[190, 215, 240], [140, 185, 235], [90, 150, 225], [50, 110, 205], [30, 75, 175], [25, 45, 140], [105, 75, 185], [140, 85, 205], [175, 95, 215],
                [205, 90, 200], [225, 75, 165], [240, 105, 160], [250, 140, 185], [250, 175, 210], [245, 205, 230], [255, 230, 242], [238, 238, 250], [205, 205, 222],
                [170, 170, 192], [255, 255, 255]];
  const labs = [""].concat(E.slice(1, -1).map(String), ["72+"]);
  return mkTotPal(E, cols, labs, v => v < 0.05 ? "0" : v < 9.95 ? v.toFixed(1) : String(Math.round(v)), " in");
})();
// Snow depth from 0": same colors as snowfall, but the first edge is 0" so any positive depth is filled.
const SNOD = (() => {
  const E = [0, 0.1, 1, 2, 3, 4, 5, 6, 8, 10, 12, 15, 18, 21, 24, 30, 36, 42, 48, 60, 72];
  const cols = [[210, 230, 245], [190, 215, 240], [140, 185, 235], [90, 150, 225], [50, 110, 205], [30, 75, 175], [25, 45, 140], [105, 75, 185], [140, 85, 205], [175, 95, 215],
                [205, 90, 200], [225, 75, 165], [240, 105, 160], [250, 140, 185], [250, 175, 210], [245, 205, 230], [255, 230, 242], [238, 238, 250], [205, 205, 222],
                [170, 170, 192], [255, 255, 255]];
  const labs = ["0"].concat(E.slice(1, -1).map(e => e < 1 ? "" : String(e)), ["72+"]);
  return mkTotPal(E, cols, labs, v => v < 0.05 ? "0" : v < 9.95 ? v.toFixed(1) : String(Math.round(v)), " in");
})();
// gust palette (mph), identical to gust_map.py: 5 mph bands to 60, then 60-70-80+; values white < 40, gold 40-57, red 58+
const GUST = (() => {
  const E = [0, 5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55, 60, 70, 80];
  const cols = [[70, 95, 160], [55, 125, 190], [40, 160, 205], [40, 180, 160], [60, 185, 95], [130, 200, 60], [200, 215, 60], [245, 220, 55], [250, 180, 45],
                [245, 135, 40], [230, 80, 40], [205, 35, 45], [200, 40, 150], [175, 60, 210], [225, 150, 245]];
  const labs = E.map(e => e === 80 ? "80+" : e % 10 === 0 ? String(e) : "");
  const P = mkTotPal(E, cols, labs, v => String(Math.round(v)), " mph"); P.edgeF = 0.55;
  P.band = v => { const r = Math.floor(v + 0.5); if (!(r >= 0)) return r < 0 ? 0 : -1; let i = 0; while (i < cols.length - 1 && r >= E[i + 1]) i++; return i; };
  P.valColor = t => t >= 58 ? "rgb(255,72,60)" : t >= 40 ? "rgb(255,196,64)" : "#fff"; return P;
})();
const PRODUCTS = {
  low: { title: d => `${d.day} Predicted Low Temps`, sub: d => `Coldest Temps 4 AM to 8 AM ${d.day} ${d.md}`, pal: TEMP, extreme: ["Coldest", true] },
  high: { title: d => `${d.day} Predicted High Temps`, sub: d => `Afternoon highs ${d.day} ${d.md}`, pal: TEMP, extreme: ["Warmest", false] },
  precip: { title: () => "Total Precipitation", pal: RAIN, key: "Precip (in)", field: { nbm: "nq6", def: "apcp" }, word: "Wettest", none: "Little or no precipitation at labeled towns" },
  gust: { title: w => `${w.day} Predicted Max Wind Gusts`, timg: w => `gust_${w.day}`, pal: GUST, key: "Gust (mph)", field: { def: "gust" }, word: "Windiest", none: "Calm at labeled towns", max: 1 },
  snow: { title: () => "Total Snowfall", pal: SNOW, key: "Snow (in)", field: { nbm: "ns6", def: "asnow" }, word: "Snowiest", none: "Little or no snow at labeled spots" },
  // 11-09 HRRR extras on WA forecast maps (t2810u queue A): 12 h max 10 m wind, 24 h min/max t2m, snow depth change from 0", Kuchera.
  wind: { title: () => "12-Hour Max Wind", pal: GUST, key: "Wind (mph)", field: { def: "u10" }, word: "Windiest", none: "Calm at labeled towns", wind: 1, hours: 12, winPt: 1 },
  tmin24: { title: () => "24-Hour Low Temps", pal: TEMP, key: "Temp (°F)", field: { def: "t2m", eps: "mint" }, word: "Coldest", cold: 1, tminmax: "min", hours: 24, winPt: 1, clip0: 0 },
  tmax24: { title: () => "24-Hour High Temps", pal: TEMP, key: "Temp (°F)", field: { def: "t2m", eps: "maxt" }, word: "Warmest", tminmax: "max", hours: 24, winPt: 1, clip0: 0 },
  snod: { title: () => "Snow Depth from 0\"", pal: SNOD, key: "Depth (in)", field: { def: "dsnod" }, word: "Snowiest", none: "Little or no snow-depth gain at labeled spots", dsnod: 1 },
  kuchera: { title: () => "Kuchera Snowfall", pal: SNOW, key: "Snow (in)", field: { def: "kinc" }, word: "Snowiest", none: "Little or no snow at labeled spots", suminc: 1 },
};
// ---------------------------------------------------------------- data (same R2 layout / decoding as viewer.js)
async function readJSON(url) { const r = await fetch(url, { cache: "no-cache" }); const text = await r.text(); if (!r.ok) throw new Error(url + ": HTTP " + r.status); try { return JSON.parse(text); } catch (e) { throw new Error(url + ": response is not JSON"); } }
async function loadRun(c) { if (!WA.runs[c]) WA.runs[c] = await readJSON(`${DATA}runs/nbm/${c}/run.json`); return WA.runs[c]; }
const rkey = (m, c) => m === "nbm" ? c : `${m}/${c}`;   // NBM keeps the Phase 1 keys
async function loadRunM(m, c) { const k = rkey(m, c); if (!WA.runs[k]) WA.runs[k] = await readJSON(`${DATA}runs/${m}/${c}/run.json`); return WA.runs[k]; }
const pix = new Map();
function getPixels(url) {
  if (pix.has(url)) return pix.get(url);
  const p = (async () => { const r = await fetch(url); if (!r.ok) throw new Error(`${url}: HTTP ${r.status}`);
    const bm = await createImageBitmap(await r.blob(), { premultiplyAlpha: "none", colorSpaceConversion: "none" });
    const oc = new OffscreenCanvas(bm.width, bm.height), cx = oc.getContext("2d", { willReadFrequently: true }); cx.drawImage(bm, 0, 0);
    return { px: cx.getImageData(0, 0, bm.width, bm.height).data, w: bm.width, h: bm.height }; })();
  p.catch(() => pix.delete(url)); pix.set(url, p); return p;
}
async function getField(c, name, f) {
  const R_ = WA.runs[c]; if (!R_ || !R_.steps) throw new Error("run not loaded");
  const st = R_.steps.find(s => s.f === f); if (!st) throw new Error("step not in run");
  const pk = st.packs && st.packs[name];
  const url = `${DATA}${R_.base}/` + R_.file.replace("{name}", pk ? pk[0] : name).replace("{f:03d}", String(f).padStart(3, "0")), ch = pk ? pk[1] : 0;
  if (!st.ranges[name]) throw new Error(`no ${name} at F${f}`);
  const I = await getPixels(url), [lo, hi, enc] = st.ranges[name], sc = (hi - lo) / 255, n = I.w * I.h, o = new Float32Array(n);
  if (enc === 2) for (let k = 0; k < n; k++) { const q = I.px[k * 4 + ch] / 255; o[k] = lo + q * q * (hi - lo); }   // sqrt-coded amounts (as viewer.js)
  else for (let k = 0; k < n; k++) o[k] = lo + I.px[k * 4 + ch] * sc;   // row 0 = first grid row of the crop (south on NBM / HRRR, north on ECMWF)
  return { v: o, w: I.w, h: I.h };
}
const ptParts = ms => { const p = {}; for (const x of new Intl.DateTimeFormat("en-US", { timeZone: PT, year: "numeric", month: "numeric", day: "numeric", hour: "numeric", hourCycle: "h23", weekday: "long" }).formatToParts(new Date(ms))) p[x.type] = x.value; return p; };
// days each product can be made for from this run: lows = hourly / 3-hourly t2m valid 4-8 AM PT; highs = NBM 12 h max ending 00Z next day
function daysFor(R_, kind) {
  const out = new Map();
  for (const s of R_.steps) {
    const ms = Date.parse(s.valid), p = ptParts(ms);
    if (kind === "low" && s.ranges.t2m && +p.hour >= 4 && +p.hour <= 8) {
      const k = `${p.year}-${p.month}-${p.day}`; if (!out.has(k)) out.set(k, { key: k, day: p.weekday, md: `${p.month}-${p.day}`, steps: [] }); out.get(k).steps.push(s.f);
    }
    if (kind === "high" && s.ranges.maxt && new Date(ms).getUTCHours() === 0) {
      const p2 = ptParts(ms - 12 * 3600e3), k = `${p2.year}-${p2.month}-${p2.day}`;
      out.set(k, { key: k, day: p2.weekday, md: `${p2.month}-${p2.day}`, steps: [s.f] });
    }
  }
  // a low needs the whole 4-8 AM window inside the run: 5 hourly steps (to F36), or the 3-hourly steps after that (2: 4 AM and 7 AM)
  return [...out.values()].filter(d => kind === "high" || (Math.max(...d.steps) <= 36 ? d.steps.length >= 5 : d.steps.length >= 2));
}
// totals: the hours a window can start / end at (NBM: 6-hourly amounts, so 6 h boundaries; others: every step with the run total)
function totalTimes(R_, m, kind) {
  const fld = PRODUCTS[kind].field[m] || PRODUCTS[kind].field.def, t0 = Date.parse(R_.init), out = [0];
  for (const s of R_.steps) if (s.f > 0 && s.f <= MAXH && s.ranges[fld] && (m !== "nbm" || kind === "gust" || s.f % 6 === 0)) out.push(s.f);
  return out.map(f => ({ f, ms: t0 + f * 3600e3 }));
}
const ptHr = ms => { const h = +ptParts(ms).hour; return `${h % 12 || 12} ${h < 12 ? "AM" : "PM"}`; };
// West view gust menu: only models in this list (HRRR, standard NBM). Other views keep every id passed in.
function gustModels(view, ids) { return view === "west" ? ids.filter(m => m === "hrrr" || m === "nbm") : ids.slice(); }
// Hours that enter a window max. instantaneous (HRRR GUST, NBM GUST:10 m): each encoded step whose valid hour is inside
// [f0, f1]; a missing hour is skipped, never filled. Period max (IFS / EPS 10fg): keep a step when its interval starts at
// or after f0 and ends by f1. No step inside the window (run still arriving): the next step at or after f1, else the last step.
function gustSteps(st, f0, f1, instantaneous) {
  const fs = [];
  st.forEach((s, i) => { const prev = i ? st[i - 1].f : 0, hourly = s.f - prev <= 1; if (s.f <= f1 && (instantaneous || hourly ? s.f >= f0 : prev >= f0)) fs.push(s.f); });
  if (!fs.length && st.length) { const nx = st.find(s => s.f >= f1) || st[st.length - 1]; fs.push(nx.f); }
  return fs;
}
function gustWindowLabel(w) { return `Max gust over ${ptHr(w.ms0)} to ${ptHr(w.ms1)} ${w.day} ${w.md}`; }
const ptLbl = ms => { const p = ptParts(ms); return `${p.weekday.slice(0, 3)} ${p.month}-${p.day} ${ptHr(ms)} PT`; };
const utcLbl = ms => { const d = new Date(ms); return `${DAYS[d.getUTCDay()].slice(0, 3)} ${d.getUTCMonth() + 1}-${d.getUTCDate()} ${String(d.getUTCHours()).padStart(2, "0")}Z`; };
async function totalField(m, c, kind, f0, f1) {
  const key = `${m}/${c}/${kind}/${f0}-${f1}`; if (WA.fields.has(key)) return WA.fields.get(key);
  const p = (async () => {
    const rk = rkey(m, c), R_ = WA.runs[rk], fld = PRODUCTS[kind].field[m] || PRODUCTS[kind].field.def;
    if (!R_ || !R_.steps) throw new Error("run not loaded");
    if (PRODUCTS[kind].max) {   // gusts: max over the window (gustSteps). HRRR / NBM are instantaneous; IFS / EPS 10fg is a period max.
      const st = R_.steps.filter(s => s.ranges[fld]), fs = gustSteps(st, f0, f1, m === "hrrr" || m === "nbm");
      const Fs = await Promise.all(fs.map(f => getField(rk, fld, f))), o = Float32Array.from(Fs[0].v);
      for (const F of Fs.slice(1)) for (let k = 0; k < o.length; k++) if (F.v[k] > o[k]) o[k] = F.v[k];
      return { v: o, w: Fs[0].w, h: Fs[0].h, n: fs.length, fs };
    }
    if (PRODUCTS[kind].wind) {   // 10 m wind (u10/v10 stored in kt) maxed over the window, reported in mph
      const KT2MPH = 1.150779448, st = R_.steps.filter(s => s.ranges.u10 && s.ranges.v10), fs = gustSteps(st, f0, f1, true);
      const Us = await Promise.all(fs.map(f => getField(rk, "u10", f))), Vs = await Promise.all(fs.map(f => getField(rk, "v10", f)));
      const o = new Float32Array(Us[0].v.length);
      for (let i = 0; i < fs.length; i++) for (let k = 0; k < o.length; k++) { const spd = Math.hypot(Us[i].v[k], Vs[i].v[k]) * KT2MPH; if (i === 0 || spd > o[k]) o[k] = spd; }
      return { v: o, w: Us[0].w, h: Us[0].h, n: fs.length, fs };
    }
    if (PRODUCTS[kind].tminmax) {
      const inst = fld === "t2m";   // EPS mint/maxt are period min/max (mean of member extremes), same window rule as 10fg
      const st = R_.steps.filter(s => s.ranges[fld]), fs = gustSteps(st, f0, f1, inst);
      const Fs = await Promise.all(fs.map(f => getField(rk, fld, f))), o = Float32Array.from(Fs[0].v), mn = PRODUCTS[kind].tminmax === "min";
      for (const F of Fs.slice(1)) for (let k = 0; k < o.length; k++) if (mn ? F.v[k] < o[k] : F.v[k] > o[k]) o[k] = F.v[k];
      return { v: o, w: Fs[0].w, h: Fs[0].h, n: fs.length, fs };
    }
    if (PRODUCTS[kind].suminc) {   // kinc is the interval increment (sqrt-coded); sum steps ending in (f0, f1]
      const fs = R_.steps.filter(s => s.f > f0 && s.f <= f1 && s.ranges[fld]).map(s => s.f);
      const Fs = await Promise.all(fs.map(f => getField(rk, fld, f))), o = new Float32Array(Fs[0].v.length);
      for (const F of Fs) for (let k = 0; k < o.length; k++) o[k] += F.v[k];
      return { v: o, w: Fs[0].w, h: Fs[0].h, n: fs.length };
    }
    if (PRODUCTS[kind].dsnod) {   // dsnod = SNOD(now) - SNOD(run start); window gain from 0" is dsnod(f1) - dsnod(f0), floored at 0
      const b = await getField(rk, "dsnod", f1), a = f0 > 0 ? await getField(rk, "dsnod", f0) : null, o = new Float32Array(b.v.length);
      for (let k = 0; k < o.length; k++) o[k] = Math.max(0, b.v[k] - (a ? a.v[k] : 0));
      return { v: o, w: b.w, h: b.h, n: 2 };
    }
    if (m === "nbm") {   // sum of the 6 h amounts ending in (f0, f1]
      const fs = R_.steps.filter(s => s.f > f0 && s.f <= f1 && s.f % 6 === 0).map(s => s.f);
      const Fs = await Promise.all(fs.map(f => getField(rk, fld, f))), o = new Float32Array(Fs[0].v.length);
      for (const F of Fs) for (let k = 0; k < o.length; k++) o[k] += F.v[k];
      return { v: o, w: Fs[0].w, h: Fs[0].h, n: fs.length };
    }
    const b = await getField(rk, fld, f1), a = f0 > 0 ? await getField(rk, fld, f0) : null, o = new Float32Array(b.v.length);   // run total now - run total then
    for (let k = 0; k < o.length; k++) o[k] = Math.max(0, b.v[k] - (a ? a.v[k] : 0));
    return { v: o, w: b.w, h: b.h, n: 2 };
  })(); p.catch(() => WA.fields.delete(key)); WA.fields.set(key, p); return p;
}
async function fieldFor(c, kind, d) {
  const key = `${c}/${kind}/${d.key}`; if (WA.fields.has(key)) return WA.fields.get(key);
  const p = (async () => {
    const fs = await Promise.all(d.steps.map(f => getField(c, kind === "low" ? "t2m" : "maxt", f)));
    const o = Float32Array.from(fs[0].v); for (const F of fs.slice(1)) for (let k = 0; k < o.length; k++) if (F.v[k] < o[k]) o[k] = F.v[k];
    return { v: o, w: fs[0].w, h: fs[0].h, n: fs.length };
  })(); p.catch(() => WA.fields.delete(key)); WA.fields.set(key, p); return p;
}
const bil = (F, fi, fj) => {   // bilinear in grid (row fi from the south, column fj); NaN outside
  if (!(fi >= 0 && fj >= 0 && fi <= F.h - 1 && fj <= F.w - 1)) return NaN;
  const r = Math.min(F.h - 2, fi | 0), c = Math.min(F.w - 2, fj | 0), y = fi - r, x = fj - c, k = r * F.w + c, v = F.v;
  return (v[k] * (1 - x) + v[k + 1] * x) * (1 - y) + (v[k + F.w] * (1 - x) + v[k + F.w + 1] * x) * y;
};
// ---------------------------------------------------------------- kit
const loadImg = u => WA.imgs[u] || (WA.imgs[u] = new Promise((ok, no) => { const i = new Image(); i.onload = () => ok(i); i.onerror = () => no(new Error(u)); i.src = u; }));
async function viewKit(view, mdl = "nbm") {
  const kk = view + "@" + mdl; if (WA.kits[kk]) return WA.kits[kk];
  return (WA.kits[kk] = (async () => {
    const [lut, mask] = await Promise.all([fetch(KIT + view + (mdl === "nbm" ? "/lut.bin" : `/lut_${mdl}.bin`) + "?v=20261109close", { cache: "no-cache" }).then(r => { if (!r.ok) throw new Error("lut " + r.status); return r.arrayBuffer(); }).then(b => new Float32Array(b)),
                                           loadImg(KIT + view + "/mask.png")]);
    const oc = new OffscreenCanvas(mask.width, mask.height), cx = oc.getContext("2d", { willReadFrequently: true }); cx.drawImage(mask, 0, 0);
    const md = cx.getImageData(0, 0, mask.width, mask.height).data, m = new Uint8Array(mask.width * mask.height); for (let k = 0; k < m.length; k++) m[k] = md[k * 4];
    return { lut, mask: m };
  })());
}
async function kindKit(kind, view) {
  const k = kind + "_" + view; if (WA.kits[k]) return WA.kits[k];
  return (WA.kits[k] = fetch(KIT + view + "/" + kind + ".json").then(r => { if (!r.ok) throw new Error("kit " + r.status); return r.json(); }));
}
// ---------------------------------------------------------------- drawing
function fillData(ctx, K, VK, F, pal) {
  const W = K.W, H = K.H, S = K.stride, nx = K.nx, L = VK.lut, M = VK.mask, n = W * H;
  const V = new Float32Array(n).fill(NaN), B = new Int16Array(n).fill(-1);
  for (let y = 0; y < H; y++) {
    const gy = y / S, r0 = Math.min(K.ny - 2, gy | 0), ty = gy - r0;
    for (let x = 0; x < W; x++) {
      const k = y * W + x; if (!M[k]) continue;
      const gx = x / S, c0 = Math.min(nx - 2, gx | 0), tx = gx - c0, a = (r0 * nx + c0) * 2, b = a + 2, c = a + nx * 2, d = c + 2;
      const fi = (L[a] * (1 - tx) + L[b] * tx) * (1 - ty) + (L[c] * (1 - tx) + L[d] * tx) * ty;
      const fj = (L[a + 1] * (1 - tx) + L[b + 1] * tx) * (1 - ty) + (L[c + 1] * (1 - tx) + L[d + 1] * tx) * ty;
      const v = bil(F, fi, fj); if (v === v) { V[k] = v; B[k] = pal.band(v); }
    }
  }
  const im = new ImageData(W, H), o = im.data, C = pal.cols, T = pal.line32;
  for (let y = 0; y < H; y++) for (let x = 0; x < W; x++) {
    const k = y * W + x, bi = B[k]; if (bi < 0) continue;
    const col = C[bi]; let f = 1, white = false;
    // band edges (x0.55) and the white 32 F line (2 px, like the server's 5 px at 3x), at 1x: neighbours left/right/up/down (server: 3x supersampled, dilated, LANCZOS)
    const hi = V[k] >= T;
    for (const q of [k - 1, k + 1, k - W, k + W]) { if (q < 0 || q >= n || B[q] < 0) continue; if ((V[q] >= T) !== hi) white = true; else if (B[q] !== bi) f = pal.edgeF || 0.55; }
    const a = M[k];
    if (white) { o[k * 4] = o[k * 4 + 1] = o[k * 4 + 2] = 255; o[k * 4 + 3] = Math.round(a * 235 / 255); continue; }
    o[k * 4] = col[0] * f; o[k * 4 + 1] = col[1] * f; o[k * 4 + 2] = col[2] * f; o[k * 4 + 3] = a;
  }
  const oc = new OffscreenCanvas(W, H); oc.getContext("2d").putImageData(im, 0, 0); ctx.drawImage(oc, 0, 0);
}
// Decimal totals (precip / snow / snod / kuchera): sit each value just under its
// overlay town name using measured ink, not a fixed font-fraction shift (11-09 t2813u).
// Name bottom = overlay letterform band (incl. descenders + stroke/halo). Value top =
// that bottom + a ~2.5 CSS-px gap at a 1920-wide fitted view (kit units: 2.5 / fit).
const DEC_TOTALS = new Set(["precip", "snow", "snod", "kuchera"]);
const MS_ASC = 0.968;   // Montserrat typoAscender / em; keep in sync with pilText
function labelGap(K) {
  const wr = typeof document !== "undefined" && document.getElementById("wrap");
  let fit = 0;
  if (wr) { const r = wr.getBoundingClientRect(); if (r.width > 0 && r.height > 0) fit = Math.min(r.width / K.W, r.height / K.H); }
  if (!(fit > 0)) fit = Math.min(1920 / K.W, (1080 - 48) / K.H);
  const dpr = (typeof window !== "undefined" && window.devicePixelRatio) || 1;
  // ~2.5 CSS px at a 1920-wide fitted view (2–3 px). CSS px already map to device
  // pixels via DPR, so the visual gap stays 2.5 px and backing-store px scale with DPR.
  return (2.5 * dpr) / (fit * dpr);
}
function scanNameBoxes(data, W, H, labels) {   // overlay RGBA → [{x0,y0,x1,y1}|null] per label
  const at = (x, y) => { const i = (y * W + x) * 4; return [data[i], data[i + 3]]; };
  return labels.map((L) => {
    const fs = L.font[1], name = L.name, nameSw = Math.max(0, (L.sw || 0) - 1);
    const nw = 0.62 * fs * Math.max(1, name.length) + 2 * nameSw + 8;
    let x0 = Math.floor(L.x - nw / 2), x1 = Math.ceil(L.x + nw / 2);
    let y0 = Math.floor(L.y - fs * 1.7), y1 = Math.ceil(L.y + Math.max(8, 0.32 * fs));
    x0 = Math.max(0, x0); y0 = Math.max(0, y0); x1 = Math.min(W, x1); y1 = Math.min(H, y1);
    const h = y1 - y0, w = x1 - x0; if (h <= 0 || w <= 0) return null;
    const counts = new Int32Array(h), white = new Uint8Array(h * w);
    for (let y = y0; y < y1; y++) { let n = 0; for (let x = x0; x < x1; x++) { const p = at(x, y); if (p[0] > 180 && p[1] > 160) { white[(y - y0) * w + (x - x0)] = 1; n++; } } counts[y - y0] = n; }
    const thresh = Math.max(10, (w * 0.12) | 0); let rows = [];
    for (let i = 0; i < h; i++) if (counts[i] >= thresh) rows.push(i);
    if (!rows.length) { const t2 = Math.max(4, thresh >> 1); for (let i = 0; i < h; i++) if (counts[i] >= t2) rows.push(i); }
    if (!rows.length) return null;
    const runs = []; let rs = rows[0], rp = rows[0];
    for (let k = 1; k < rows.length; k++) { const r = rows[k]; if (r > rp + 2) { runs.push([rs, rp]); rs = r; } rp = r; }
    runs.push([rs, rp]);
    const ey = (L.y - 0.5 * fs) - y0;
    runs.sort((A, B) => { const sc = (R) => { const cy = (R[0] + R[1]) / 2, hh = R[1] - R[0] + 1; return Math.abs(cy - ey) + (hh >= 0.4 * fs && hh <= 1.45 * fs ? 0 : 40); }; return sc(A) - sc(B); });
    let r0 = runs[0][0], r1 = runs[0][1];
    if (/[gjpqy]/.test(name)) { const lim = Math.min(h - 1, r1 + Math.round(0.38 * fs));
      for (let r = r1 + 1; r <= lim; r++) { if (counts[r] >= 2) r1 = r; else if (counts[r] === 0 && r + 1 <= lim && counts[r + 1] >= 2) continue; else break; } }
    let c0 = w, c1 = -1;
    for (let y = r0; y <= r1; y++) for (let x = 0; x < w; x++) if (white[y * w + x]) { if (x < c0) c0 = x; if (x > c1) c1 = x; }
    if (c1 < 0) return null;
    let bx0 = x0 + c0 - nameSw, by0 = y0 + r0 - nameSw, bx1 = x0 + c1 + nameSw, by1 = y0 + r1 + nameSw;
    bx0 = Math.max(0, Math.floor(bx0)); by0 = Math.max(0, Math.floor(by0));
    bx1 = Math.min(W - 1, Math.ceil(bx1)); by1 = Math.min(H - 1, Math.ceil(by1));
    const bw = bx1 - bx0 + 1, ink = new Uint8Array(bw * (by1 - by0 + 1));
    for (let y = by0; y <= by1; y++) for (let x = bx0; x <= bx1; x++) { const p = (y * W + x) * 4; if (data[p] > 180 && data[p + 3] > 160) ink[(y - by0) * bw + (x - bx0)] = 1; }
    return { x0: bx0, y0: by0, x1: bx1, y1: by1, w: bw, ink };
  });
}
const _nameBoxCache = new WeakMap();
function nameBoxesFor(over, labels) {
  let hit = _nameBoxCache.get(over); if (hit) return hit;
  const c = typeof OffscreenCanvas !== "undefined" ? new OffscreenCanvas(over.width, over.height) : document.createElement("canvas");
  c.width = over.width; c.height = over.height;
  const x = c.getContext("2d", { willReadFrequently: true }); x.drawImage(over, 0, 0);
  const im = x.getImageData(0, 0, c.width, c.height);
  hit = scanNameBoxes(im.data, c.width, c.height, labels); _nameBoxCache.set(over, hit); return hit;
}
function textInk(ctx, txt, font, sw) {   // stroked glyph metrics relative to the alignment point / baseline
  const [, size, wg] = font; ctx.font = `${wg || 800} ${size}px Montserrat`;
  const m = ctx.measureText(txt), pad = sw || 0;
  return { ascent: (m.actualBoundingBoxAscent || 0.70 * size) + pad, descent: (m.actualBoundingBoxDescent || 0) + pad,
           left: ((m.actualBoundingBoxLeft != null) ? m.actualBoundingBoxLeft : m.width / 2) + pad,
           right: ((m.actualBoundingBoxRight != null) ? m.actualBoundingBoxRight : m.width / 2) + pad };
}
function decimalValueY(L, nameBottom, gap, ink) { return nameBottom + gap + ink.ascent - MS_ASC * L.font[1]; }
function valueBox(L, vy, ink) {
  const yb = vy + MS_ASC * L.font[1];
  return { x0: L.x - ink.left, y0: yb - ink.ascent, x1: L.x + ink.right, y1: yb + ink.descent };
}
function boxesHit(a, b) { return a.x0 < b.x1 && a.x1 > b.x0 && a.y0 < b.y1 && a.y1 > b.y0; }
const OTHER_INK = 8;   // ignore 1–2 px anti-aliased fringe against a neighbour
function countValueNameInk(L, vy, txt, inkM, nb) {
  if (!nb || !nb.ink) return 0;
  const vb = valueBox(L, vy, inkM); if (!boxesHit(vb, nb)) return 0;
  const ox = Math.floor(vb.x0), oy = Math.floor(vb.y0);
  const vw = Math.max(1, Math.ceil(vb.x1) - ox), vh = Math.max(1, Math.ceil(vb.y1) - oy);
  const cv = typeof OffscreenCanvas !== "undefined" ? new OffscreenCanvas(vw, vh) : document.createElement("canvas");
  cv.width = vw; cv.height = vh;
  const c = cv.getContext("2d");
  const size = L.font[1], sw = L.sw || 0, yb = vy + MS_ASC * size - oy;
  c.font = `${(L.font[2] || 800)} ${size}px Montserrat`;
  c.textAlign = "center"; c.textBaseline = "alphabetic"; c.lineJoin = "round";
  if (sw) { c.lineWidth = 2 * sw; c.strokeStyle = "#000"; c.strokeText(txt, L.x - ox, yb); }
  c.fillStyle = "#fff"; c.fillText(txt, L.x - ox, yb);
  const pix = c.getImageData(0, 0, vw, vh).data, bw = nb.w || (nb.x1 - nb.x0 + 1);
  const ix0 = Math.max(ox, nb.x0), iy0 = Math.max(oy, nb.y0);
  const ix1 = Math.min(ox + vw - 1, nb.x1), iy1 = Math.min(oy + vh - 1, nb.y1);
  let n = 0;
  for (let y = iy0; y <= iy1; y++) for (let x = ix0; x <= ix1; x++) {
    if (!nb.ink[(y - nb.y0) * bw + (x - nb.x0)]) continue;
    if (pix[((y - oy) * vw + (x - ox)) * 4 + 3] > 40) n++;
  }
  return n;
}
function resolveDecimalTotals(items, nameBoxes, gap) {   // keep kit X; ease Y toward the name only when that clears a real ink hit
  for (const it of items) {
    const nb = nameBoxes[it.i]; if (!nb || !it.ink) continue;
    const L = it.L, ink = it.ink, txt = it.txt;
    const desired = decimalValueY(L, nb.y1, gap, ink), minY = decimalValueY(L, nb.y1, 0, ink);
    const hitsOther = (vy) => {
      for (let j = 0; j < nameBoxes.length; j++) {
        if (j === it.i || !nameBoxes[j]) continue;
        if (countValueNameInk(L, vy, txt, ink, nameBoxes[j]) > OTHER_INK) return true;
      }
      return false;
    };
    if (!hitsOther(desired)) { it.vy = desired; continue; }
    let cleared = false;
    for (let vy = desired - 0.5; vy >= minY; vy -= 0.5) { if (!hitsOther(vy)) { it.vy = vy; cleared = true; break; } }
    if (!cleared) it.vy = desired;   // unfixable side clip: keep the measured gap rather than eat into the name
  }
}

function pilText(ctx, txt, x, y, anchor, font, sw, fill) {   // PIL anchors: l/m/r + t (ascender) / s (baseline); Montserrat ascender 968/1000
  const [, size, wg] = font; ctx.font = `${wg || 400} ${size}px Montserrat`;
  ctx.textAlign = anchor[0] === "m" ? "center" : anchor[0] === "r" ? "right" : "left"; ctx.textBaseline = "alphabetic";
  const yb = anchor[1] === "t" ? y + 0.968 * size : y;
  if (sw) { ctx.lineJoin = "round"; ctx.lineWidth = 2 * sw; ctx.strokeStyle = INK; ctx.strokeText(txt, x, yb); }
  ctx.fillStyle = fill; ctx.fillText(txt, x, yb);
}
function extremeLine(tv, pops, word, cold, fits) {   // region_maps.extreme_line (ties: biggest towns first, max 3 + "+N more")
  const vs = Object.values(tv), v = cold ? Math.min(...vs) : Math.max(...vs);
  const t = Object.keys(tv).filter(k => tv[k] === v).sort((a, b) => (pops[b] || 0) - (pops[a] || 0)), num = String(v);
  if (t.length === 1) return `${word} town: ${t[0]} ${num}`;
  const opts = []; if (t.length <= 3) opts.push(`${word} towns: ${t.join(", ")} ${num}`);
  for (let k = Math.min(3, t.length - 1); k > 0; k--) opts.push(`${word} towns: ${t.slice(0, k).join(", ")} +${t.length - k} more ${num}`);
  return opts.find(fits) || opts[opts.length - 1];
}
function summaryLine1(K, vals, fmt = String, unit = "") {
  const rng = ks => ks.filter(k => k in vals).map(k => vals[k]), f_ = g => Math.min(...g) === Math.max(...g) ? `${fmt(g[0])}${unit}` : `${fmt(Math.min(...g))} to ${fmt(Math.max(...g))}${unit}`;
  if (!K.region) { const lw = rng(["Seattle", "Tacoma", "Olympia", "Vancouver", "Bellingham", "Aberdeen"]),
    ea = rng(["Spokane", "Yakima", "Wenatchee", "Ellensburg", "Moses Lake", "Kennewick", "Walla Walla", "Pullman", "Omak", "Colville", "Goldendale"]);
    return unit ? `West side ${f_(lw)}, east side ${f_(ea)}` : `West side ${Math.min(...lw)} to ${Math.max(...lw)}, east side ${Math.min(...ea)} to ${Math.max(...ea)}`; }
  const G = K.region === "west" ? [["Puget Sound", ["Seattle", "Tacoma", "Everett", "Bellevue", "Olympia", "Bellingham", "Federal Way", "Mount Vernon"]],
                                   ["coast", ["Aberdeen", "Ocean Shores", "Westport", "Long Beach", "Forks", "Neah Bay", "Raymond", "Ilwaco", "La Push"]]]
                                : [["Spokane area", ["Spokane", "Spokane Valley", "Cheney", "Deer Park", "Medical Lake", "Airway Heights", "Liberty Lake"]],
                                   ["Columbia Basin", ["Moses Lake", "Ephrata", "Othello", "Quincy", "Kennewick", "Pasco", "Richland", "Ritzville"]]];
  const l = G.map(([n, ks]) => [n, rng(ks)]).filter(([, g]) => g.length).map(([n, g]) => `${n} ${f_(g)}`).join(", ");
  return l.slice(0, 1).toUpperCase() + l.slice(1);
}
// 11-01-26 legal audit (Benjamin t2020u): faint credit just above the date line like nbm_map (R.subtle_credit: 22 px 600, white 38 %, 1 px dark halo).
// ECMWF sources: (c) year ECMWF (www.ecmwf.int), CC BY 4.0, Modified. Every map: GeoNames town points (CC BY 4.0). NOAA: no Data credit (his rule).
function wamCredit(ctx, K, m, up = 0) {
  const L = [];
  if (SRC[m] && SRC[m].ec) L.push(`Data: \u00a9 ${new Date().getFullYear()} ECMWF (www.ecmwf.int), CC BY 4.0. Modified.`);
  L.push("Places: GeoNames (geonames.org), CC BY 4.0");
  const dt = K.date[0], top = dt.y - dt.font[1] - 34 - up;
  ctx.save(); ctx.font = "600 22px Montserrat"; ctx.textAlign = "left"; ctx.textBaseline = "alphabetic"; ctx.lineJoin = "round";
  L.forEach((l, i) => { const yb = top - 28 * (L.length - 1 - i) + 0.968 * 22;
    ctx.lineWidth = 2; ctx.strokeStyle = "rgba(0,0,0,0.30)"; ctx.strokeText(l, dt.x, yb); ctx.fillStyle = "rgba(255,255,255,0.38)"; ctx.fillText(l, dt.x, yb); });
  ctx.restore();
}
async function render(cv, c, kind, view, d) {
  const P = PRODUCTS[kind], [K, VK, F] = await Promise.all([kindKit(kind, view), viewKit(view), fieldFor(c, kind, d)]);
  const [base, over, title] = await Promise.all([loadImg(KIT + view + "/base.png"), loadImg(KIT + view + "/" + kind + "_overlay.png"), loadImg(KIT + view + `/titles/${kind}_${d.day}.png`)]);
  const SC = 2;   // backing pixels: titles, town values and credits rasterize at 2x (Studio frames sample this 1:1)
  cv.width = K.W * SC; cv.height = K.H * SC; const ctx = cv.getContext("2d"); ctx.setTransform(SC, 0, 0, SC, 0, 0);
  ctx.drawImage(base, 0, 0); fillData(ctx, K, VK, F, P.pal); ctx.drawImage(over, 0, 0); ctx.drawImage(title, 0, 0);
  const vals = {}, pyr = P.pal.pyr;
  for (const L of K.labels) {
    const v = bil(F, L.fi, L.fj); if (v !== v) continue;
    const t = pyr(v + (L.pass_ ? L.corr : 0)); if (L.wa) vals[L.name] = t;
    pilText(ctx, String(t), L.x, L.y, L.anchor, L.font, L.sw, P.pal.valColor(t));
  }
  const tv = {}; for (const L of K.labels) if (L.wa && !L.pass_ && L.name in vals) tv[L.name] = vals[L.name];
  const fitPx = (txt, px) => { while (px > 20) { ctx.font = `800 ${px}px Montserrat`; if (ctx.measureText(txt).width <= K.sum_maxw) break; px -= 2; } return px; };
  const l2 = extremeLine(tv, K.pops, P.extreme[0], P.extreme[1], s => { ctx.font = `800 ${K.sum_px[1]}px Montserrat`; return ctx.measureText(s).width <= K.sum_maxw; });
  const l1 = summaryLine1(K, vals), [s2, s1] = K.summary;   // kit order: l2 (bottom) then l1
  pilText(ctx, l2, s2.x, s2.y, "rs", ["", fitPx(l2, K.sum_px[1]), 800], 4, "#fff");
  pilText(ctx, l1, s1.x, s1.y, "rs", ["", fitPx(l1, K.sum_px[0]), 800], 4, "#fff");
  const dt = K.date[0]; pilText(ctx, P.sub(d), dt.x, dt.y, "ls", dt.font, 4, "#fff");
  wamCredit(ctx, K, "nbm");
  return { title: P.title(d), sub: P.sub(d), l1, l2, vals, steps: d.steps };
}
async function renderTotals(cv, m, c, kind, view, w) {
  const P = PRODUCTS[kind], pal = P.pal;
  const [K, VK, F, T, LB] = await Promise.all([kindKit("low", view), viewKit(view, lutOf(m)), totalField(m, c, kind, w.f0, w.f1),
    readJSON(KIT + view + "/totals.json"), m === "nbm" ? null : readJSON(KIT + view + `/lab_${lutOf(m)}.json?v=20261109close`)]);
  const [base, over, title] = await Promise.all([loadImg(KIT + view + "/base.png"), loadImg(KIT + view + "/plain_overlay.png"), loadImg(KIT + view + `/titles/${P.timg ? P.timg(w) : kind}.png`)]);
  const SC = 2;   // same 2x backing as the daily maps
  cv.width = K.W * SC; cv.height = K.H * SC; const ctx = cv.getContext("2d"); ctx.setTransform(SC, 0, 0, SC, 0, 0);
  ctx.drawImage(base, 0, 0); fillData(ctx, K, VK, F, pal); ctx.drawImage(over, 0, 0); ctx.drawImage(title, 0, 0);
  // scale (same box as the temp scale it replaces) + [model] tag (nbm_map: Montserrat 700 32 px, stroke 4, right-aligned at W-34, y 30)
  const sc = T.scale, n = pal.cols.length, bw = (sc.x1 - sc.x0) / n, port = K.H > K.W, tp = port ? 24 : 22;
  for (let i = 0; i < n; i++) { const c_ = pal.cols[i]; ctx.fillStyle = `rgb(${c_[0]},${c_[1]},${c_[2]})`; ctx.fillRect(Math.floor(sc.x0 + i * bw), sc.y0, Math.ceil(bw) + 1, sc.y1 - sc.y0 + 1); }
  ctx.strokeStyle = "rgba(255,255,255,0.6)"; ctx.lineWidth = 1.5; ctx.strokeRect(sc.x0, sc.y0, sc.x1 - sc.x0, sc.y1 - sc.y0 + 1);
  let lastR = -1e9;
  for (let i = 0; i < n; i++) { const t = pal.labs[i]; if (!t) continue; ctx.font = `700 ${tp}px Montserrat`; const tw = ctx.measureText(t).width, x = sc.x0 + i * bw + (i === n - 1 ? bw / 2 : 0);
    if (x - tw / 2 < lastR + 6) continue; lastR = x + tw / 2; pilText(ctx, t, x, sc.y1 + 6, "mt", ["", tp, 700], 3, "#fff"); }
  if (port) pilText(ctx, P.key, sc.x0, sc.y0 - 10, "ls", ["", 28, 800], 4, "#fff"); else pilText(ctx, P.key, sc.x0 - 14, sc.y1 + 1, "rs", ["", 26, 800], 4, "#fff");
  pilText(ctx, SRC[m].tag, K.W - 34, 30, "rt", ["", 32, 700], 4, "#fff");
  // town values
  const vals = {}, tv = {}, drawn = [];
  K.labels.forEach((L, i) => {
    const [fi, fj] = LB ? LB[i] : [L.fi, L.fj], v = bil(F, fi, fj); if (v !== v) return;
    const x = P.clip0 === 0 ? v : Math.max(0, v); if (L.wa) vals[L.name] = x;
    if (L.wa && (kind === "snow" || kind === "kuchera" || kind === "snod" || !L.pass_)) tv[L.name] = +pal.fmt(x);
    const txt = pal.fmt(x);
    let vy = L.y, ink = null;
    if (DEC_TOTALS.has(kind)) {
      if (!K._nameBoxes) K._nameBoxes = nameBoxesFor(over, K.labels);
      ink = textInk(ctx, txt, L.font, L.sw);
      const nb = K._nameBoxes[i];
      if (nb) vy = decimalValueY(L, nb.y1, labelGap(K), ink);
    }
    drawn.push({ L, i, txt, vy, ink });
  });
  if (DEC_TOTALS.has(kind) && K._nameBoxes) resolveDecimalTotals(drawn, K._nameBoxes, labelGap(K));
  for (const it of drawn) pilText(ctx, it.txt, it.L.x, it.vy, it.L.anchor, it.L.font, it.L.sw, pal.valColor(+it.txt));
  const fitPx = (txt, px) => { while (px > 20) { ctx.font = `800 ${px}px Montserrat`; if (ctx.measureText(txt).width <= K.sum_maxw) break; px -= 2; } return px; };
  const mx = Math.max(...Object.values(tv));
  const l2 = (P.none && !(mx > 0)) ? P.none : extremeLine(Object.fromEntries(Object.entries(tv).map(([k, v]) => [k, v])), K.pops, P.word, !!P.cold,
    s => { ctx.font = `800 ${K.sum_px[1]}px Montserrat`; return ctx.measureText(s).width <= K.sum_maxw; }).replace(/ ([\d.-]+)$/, (q, v) => ` ${pal.fmt(+v)}${pal.unit}`);
  const rv = {}; for (const k in vals) rv[k] = +pal.fmt(vals[k]);
  const l1 = summaryLine1(K, rv, v => pal.fmt(v), pal.unit), [s2, s1] = K.summary;
  pilText(ctx, l2, s2.x, s2.y, "rs", ["", fitPx(l2, K.sum_px[1]), 800], 4, "#fff");
  pilText(ctx, l1, s1.x, s1.y, "rs", ["", fitPx(l1, K.sum_px[0]), 800], 4, "#fff");
  const R_ = WA.runs[rkey(m, c)], ri = Date.parse(R_.init), rp = ptParts(ri);
  const sub = P.max ? gustWindowLabel(w)
    : P.winPt ? `${P.tminmax === "min" ? "Min" : P.tminmax === "max" ? "Max" : "Max"} over ${ptHr(w.ms0)} to ${ptHr(w.ms1)} ${w.day} ${w.md}`
    : `${utcLbl(w.ms0)} to ${utcLbl(w.ms1)} UTC (${w.f1 - w.f0} h) · ${SRC[m].name} ${c.slice(8)}Z run`;
  const dt = K.date[0]; pilText(ctx, sub, dt.x, dt.y, "ls", dt.font, 4, "#fff");
  let up = 0;
  if (P.max || P.winPt) { const ml = `${SRC[m].res || SRC[m].name}, ${c.slice(8)}Z run ${rp.month}-${rp.day} (${ptHr(ri)} PT)`; up = dt.font[1] - 6 + 10;
    pilText(ctx, ml, dt.x, dt.y - dt.font[1] - 10, "ls", ["", dt.font[1] - 6, dt.font[2] || 800], 4, "#fff"); }
  wamCredit(ctx, K, m, up);
  return { title: P.title(w), sub, l1, l2, vals, steps: [w.f0, w.f1], n: F.n };
}
// ---------------------------------------------------------------- page
const MODELS_T = ["nbm", "ifs9", "ifs", "eps", "hrrr"];
const S = { c: null, kind: KINDS.some(k => k[0] === Q.get("kind")) ? Q.get("kind") : "low", view: VIEWS.some(v => v[0] === Q.get("view")) ? Q.get("view") : "full",
            day: Q.get("day"), m: MODELS_T.includes(Q.get("model")) ? Q.get("model") : "nbm", f0: Q.get("from"), f1: Q.get("to"), busy: 0 };
const fillSel = (sel, opts, cur) => { sel.innerHTML = opts.map(([v, t]) => `<option value="${v}"${v === cur ? " selected" : ""}>${t}</option>`).join(""); };
const isTot = () => TOTALS.has(S.kind);
function setDays() {
  const ds = daysFor(WA.runs[S.c], S.kind); S.days = ds;
  if (!ds.some(d => d.key === S.day)) S.day = ds.length ? ds[0].key : null;
  fillSel($("day"), ds.map(d => [d.key, `${d.day.slice(0, 3)} ${d.md}`]), S.day);
}
// window boxes: values are UTC valid times (YYYYMMDDHH) so a link keeps its window across runs when the run still covers it
const ymdh = ms => new Date(ms).toISOString().replace(/[-T:]/g, "").slice(0, 10);
function setTimes() {
  const R_ = WA.runs[rkey(S.m, S.c)], T = totalTimes(R_, S.m, S.kind); S.times = T;
  const byK = k => { if (!k) return -1; const i = T.findIndex(t => ymdh(t.ms) === k); if (i >= 0 || S.kind !== "gust") return i;   // gusts: nearest step (3-hourly models)
    const ms = Date.UTC(+k.slice(0, 4), +k.slice(4, 6) - 1, +k.slice(6, 8), +k.slice(8, 10)); let b = -1, bd = 3.01 * 3600e3;
    T.forEach((t, j) => { const d_ = Math.abs(t.ms - ms); if (d_ < bd) { bd = d_; b = j; } }); return b; };
  if (S.kind !== "gust" || !S.want) S.want = [S.f0, S.f1];   // gusts: the window asked for, so snapping to a 3-hourly model never drifts it
  let a = byK(S.want[0]), b = byK(S.want[1]);
  if (S.kind === "gust" && (a < 0 || b < 0)) {   // default gust window = gust_map.py's 2 PM to 11 PM PT, first day the run covers (nearest steps)
    for (let i = 1; i < T.length; i++) { if (+ptParts(T[i].ms).hour !== 14 && !(T[i].ms - T[i - 1].ms > 3600e3 && +ptParts(T[i].ms).hour >= 13 && +ptParts(T[i].ms).hour <= 15)) continue;
      const j = byK(ymdh(T[i].ms + 9 * 3600e3)); if (j > i) { a = i; b = j; break; } } }
  const Ph = PRODUCTS[S.kind] || {};
  if ((a < 0 || b < 0) && Ph.hours) {   // 12 h wind / 24 h temps: prefer a midnight-to-midnight PT day for temps, else the last N hours
    if (Ph.hours === 24) {   // prefer a PT calendar day; 3-hourly EPS snaps to the step nearest midnight
      let best = null, bestOff = 99;
      for (let i = 0; i < T.length; i++) {
        const target = T[i].ms + 24 * 3600e3; let j = -1, jd = Infinity;
        T.forEach((t, k) => { const d = Math.abs(t.ms - target); if (k > i && d < jd) { jd = d; j = k; } });
        if (j <= i || jd > 1.6 * 3600e3) continue;   // closest step to +24 h, not the first within a wide band (that was 21 h on 3-hourly EPS)
        const h = +ptParts(T[i].ms).hour, off = Math.min(h, 24 - h);
        if (off < bestOff) { bestOff = off; best = [i, j]; if (off === 0) break; }
      }
      if (best) { a = best[0]; b = best[1]; }
    }
    if (a < 0 || b < 0) {
      const end = T.length - 1, target = T[end].ms - Ph.hours * 3600e3; let i = 0;
      T.forEach((t, j) => { if (t.ms <= target + 1) i = j; });
      a = i; b = end;
    }
  }
  if (a < 0) a = 0; if (b < 0 || b <= a) b = T.length - 1; if (b <= a) a = Math.max(0, b - 1);
  S.f0 = ymdh(T[a].ms); S.f1 = ymdh(T[b].ms);
  const usePt = S.kind === "gust" || Ph.winPt;
  const lb = usePt ? ptLbl : utcLbl; const uz = document.querySelector("#win .utc"); if (uz) uz.textContent = usePt ? "" : "UTC";
  fillSel($("from"), T.slice(0, -1).map(t => [ymdh(t.ms), lb(t.ms)]), S.f0);
  fillSel($("to"), T.slice(a + 1).map(t => [ymdh(t.ms), lb(t.ms)]), S.f1);
}
function runsOf(m) { return [...(WA.man.runs[m] || [])].reverse(); }
function modelIds() {
  let xs = MODELS_T.filter(x => (WA.man.runs[x] || []).length && (!isTot() || SRC[x].kinds.includes(S.kind)));
  if (S.kind === "gust") xs = gustModels(S.view, xs);   // west: HRRR + standard NBM only (no EPS, no IFS)
  return xs;
}
async function setRun() {   // model / kind changed: run list for the model (lows / highs: NBM only)
  const ids = modelIds();
  if (isTot() && !ids.includes(S.m)) { S.m = ((S.kind === "gust" || (SRC.hrrr && SRC.hrrr.kinds.includes(S.kind) && S.kind !== "precip" && S.kind !== "snow")) && ids.includes("hrrr") ? "hrrr" : ids[0]) || "nbm"; S.c = null; }
  fillSel($("model"), ids.map(x => [x, SRC[x].name]), S.m);
  const m = isTot() ? S.m : "nbm", rs = runsOf(m);
  if (!rs.includes(S.c)) S.c = rs.includes(Q.get("run")) ? Q.get("run") : rs[0];
  fillSel($("run"), rs.map(c => [c, `${SRC[m].name} ${c.slice(8)}Z ${c.slice(4, 6)}-${c.slice(6, 8)}`]), S.c);
  await loadRunM(m, S.c);
  $("model").disabled = !isTot(); if (!isTot()) $("model").value = "nbm"; else $("model").value = S.m;
  $("day").style.display = isTot() ? "none" : ""; $("win").style.display = isTot() ? "" : "none";
  if (isTot()) setTimes(); else setDays();
}
async function draw() {
  const my = ++S.busy; const tot = isTot(); let d = null, w = null;
  if (tot) { const T = S.times || []; const a = T.find(t => ymdh(t.ms) === S.f0), b = T.find(t => ymdh(t.ms) === S.f1); if (!a || !b) { $("msg").textContent = "Loading times\u2026"; return; } w = { f0: a.f, f1: b.f, ms0: a.ms, ms1: b.ms }; const p = ptParts(a.ms); w.day = p.weekday; w.md = `${p.month}-${p.day}`; }
  else { d = S.days.find(x => x.key === S.day); if (!d) { $("msg").textContent = "No data for this day in this run."; return; } }
  $("msg").textContent = "Drawing…"; const t0 = performance.now();
  const cv = document.createElement("canvas");
  try { const info = tot ? await renderTotals(cv, S.m, S.c, S.kind, S.view, w) : await render(cv, S.c, S.kind, S.view, d); if (my !== S.busy) return;
    const old = $("map"); cv.id = "map"; old.replaceWith(cv); S.info = info; fit();
    const R_ = WA.runs[rkey(tot ? S.m : "nbm", S.c)];
    if (!R_) { $("msg").textContent = "Loading run\u2026"; return; }
    const how = !tot ? (S.kind === "low" ? "min of " + info.steps.length + " t2m steps" : "NBM 12 h max")
      : S.kind === "gust" || S.kind === "wind" || S.kind === "tmin24" || S.kind === "tmax24" ? `${S.kind === "tmin24" ? "min" : "max"} over ${info.n} step${info.n === 1 ? "" : "s"}`
      : S.kind === "kuchera" ? `sum of ${info.n} Kuchera increments` : S.kind === "snod" ? "snow depth now minus at the window start, from 0\"" 
      : S.m === "nbm" ? `sum of ${info.n} NBM 6 h amounts` : "run total at the end minus at the start";
    $("msg").textContent = `${R_.runline} · ${how} · ${Math.round(performance.now() - t0)} ms`;
    const u = new URL(location); u.searchParams.set("kind", S.kind); u.searchParams.set("view", S.view); u.searchParams.set("run", S.c);
    for (const k of ["day", "model", "from", "to"]) u.searchParams.delete(k);
    if (tot) { u.searchParams.set("model", S.m); u.searchParams.set("from", S.f0); u.searchParams.set("to", S.f1); } else u.searchParams.set("day", S.day);
    try { history.replaceState(null, "", u); } catch (e) {}
    window.__drawn = (window.__drawn || 0) + 1;
  } catch (e) { if (my === S.busy && $("msg")) $("msg").textContent = "Could not draw: " + (e && e.message || e); }
}
function fit() {   // whole map in the window (phones: full width)
  const cv = $("map"), wr = $("wrap"), r = wr.getBoundingClientRect(), k = Math.min(r.width / cv.width, (r.height || 1e9) / cv.height);
  if (document.body.classList.contains("phone")) { cv.style.width = r.width + "px"; cv.style.height = (cv.height * r.width / cv.width) + "px"; }
  else { cv.style.width = cv.width * k + "px"; cv.style.height = cv.height * k + "px"; }
}
function save() {
  const cv = $("map"), v = VIEWS.find(x => x[0] === S.view)[1].replace(/ /g, "-");
  let name;
  if (isTot()) { const kn = ({ precip: "Precip", gust: "Gusts", snow: "Snow", wind: "MaxWind", tmin24: "MinTemp", tmax24: "MaxTemp", snod: "SnowDepth", kuchera: "Kuchera" })[S.kind] || S.kind;
    name = `${v}_${kn}_${S.f0.slice(4, 8)}-${S.f0.slice(8)}Z_to_${S.f1.slice(4, 8)}-${S.f1.slice(8)}Z_${SRC[S.m].name.replace(/[ °.]/g, "")}_${S.c.slice(8)}Z.jpg`; }
  else { const d = S.days.find(x => x.key === S.day); name = `${v}_${S.kind === "low" ? "Lows" : "Highs"}_${d.day}-${d.md}_NBM_${S.c.slice(8)}Z.jpg`; }
  cv.toBlob(async b => {
    const f = new File([b], name, { type: "image/jpeg" });
    if (matchMedia("(max-width: 700px)").matches && navigator.canShare && navigator.canShare({ files: [f] })) { try { await navigator.share({ files: [f] }); return; } catch (e) { if (e.name === "AbortError") return; } }
    const a = document.createElement("a"); a.href = URL.createObjectURL(b); a.download = name; document.body.appendChild(a); a.click(); a.remove(); setTimeout(() => URL.revokeObjectURL(a.href), 60e3);
  }, "image/jpeg", 0.95);
}
async function boot() {
  const [man] = await Promise.all([readJSON(DATA + "manifest.json"), document.fonts.load("800 40px Montserrat")]);
  WA.man = man; if (!(man.runs.nbm || []).length) { $("msg").textContent = "No NBM run available."; return; }
  const ms = MODELS_T.filter(m => (man.runs[m] || []).length); if (!ms.includes(S.m)) S.m = "nbm";
  fillSel($("model"), ms.map(m => [m, SRC[m].name]), S.m);
  fillSel($("kind"), KINDS, S.kind); fillSel($("view"), VIEWS, S.view);
  await setRun();
  $("run").onchange = async e => { S.c = e.target.value; await loadRunM(isTot() ? S.m : "nbm", S.c); if (isTot()) setTimes(); else setDays(); draw(); };
  $("kind").onchange = async e => { const nk = e.target.value, hrrrPref = ["gust", "wind", "tmin24", "tmax24", "snod", "kuchera"];
    const keep = SRC[S.m] && SRC[S.m].kinds.includes(nk) && (S.m === "eps" || hrrrPref.includes(S.kind));
    if (hrrrPref.includes(nk) && !keep && (WA.man.runs.hrrr || []).length) { S.m = "hrrr"; S.c = null; }
    S.kind = nk; S.want = null; await setRun(); draw(); };
  $("model").onchange = async e => { S.m = e.target.value; S.c = null; await setRun(); draw(); };
  $("from").onchange = e => { S.f0 = e.target.value; S.want = null; setTimes(); draw(); };
  $("to").onchange = e => { S.f1 = e.target.value; S.want = null; draw(); };
  $("day").onchange = e => { S.day = e.target.value; draw(); };
  $("view").onchange = async e => { S.view = e.target.value; if (S.kind === "gust") await setRun(); draw(); };
  $("save").onclick = save;
  const mq = matchMedia("(max-width: 700px)"), ph = () => { document.body.classList.toggle("phone", mq.matches); fit(); };
  ph(); (mq.addEventListener ? mq.addEventListener("change", ph) : mq.addListener(ph)); addEventListener("resize", fit);
  await draw(); window.__ready = true;
}
boot().catch(e => { if ($("msg")) $("msg").textContent = "Could not load: " + (e && e.message || e); });
