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
const KINDS = [["low", "Lows"], ["high", "Highs"], ["precip", "Precip total"], ["snow", "Snow total"]];
// WA Maps quick slice (10-31-26 12:35 PM, Benjamin: "add most recent European data, and hrrr", "precipitation totals, let me choose the time
// frame in little boxes with dates and time in UT", snow, "go out like 7 days"): totals from NBM / ECMWF 9 km / ECMWF 0.25 / HRRR, window
// picked in two UTC boxes, capped at 168 h. Lows / highs stay NBM. Kit extras from wamaps/build_totals_kit.py (per-model LUT + label points,
// overlay without the temp scale and tag, Impact titles rasterized there).
const SRC = { nbm: { tag: "[NBM 2.5 km]", name: "NBM" }, ifs9: { tag: "[ECMWF 9 km]", name: "ECMWF 9 km" }, ifs: { tag: "[ECMWF 0.25°]", name: "ECMWF 0.25°" },
              hrrr: { tag: "[HRRR 3 km]", name: "HRRR" } };
const TOTALS = new Set(["precip", "snow"]), MAXH = 168;
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
  return { edges: E, cols, band, line32: 31.5,
           valColor: t => t <= 32 ? "rgb(150,220,255)" : t > 85 ? "rgb(255,72,60)" : "#fff", pyr };
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
const PRODUCTS = {
  low: { title: d => `${d.day} Predicted Low Temps`, sub: d => `Coldest Temps 4 AM to 8 AM ${d.day} ${d.md}`, pal: TEMP, extreme: ["Coldest", true] },
  high: { title: d => `${d.day} Predicted High Temps`, sub: d => `Afternoon highs ${d.day} ${d.md}`, pal: TEMP, extreme: ["Warmest", false] },
  precip: { title: () => "Total Precipitation", pal: RAIN, key: "Precip (in)", field: { nbm: "nq6", def: "apcp" }, word: "Wettest", none: "Little or no precipitation at labeled towns" },
  snow: { title: () => "Total Snowfall", pal: SNOW, key: "Snow (in)", field: { nbm: "ns6", def: "asnow" }, word: "Snowiest", none: "Little or no snow at labeled spots" },
};
// ---------------------------------------------------------------- data (same R2 layout / decoding as viewer.js)
async function loadRun(c) { if (!WA.runs[c]) WA.runs[c] = await (await fetch(`${DATA}runs/nbm/${c}/run.json`, { cache: "no-cache" })).json(); return WA.runs[c]; }
const rkey = (m, c) => m === "nbm" ? c : `${m}/${c}`;   // NBM keeps the Phase 1 keys
async function loadRunM(m, c) { const k = rkey(m, c); if (!WA.runs[k]) WA.runs[k] = await (await fetch(`${DATA}runs/${m}/${c}/run.json`, { cache: "no-cache" })).json(); return WA.runs[k]; }
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
  const R_ = WA.runs[c], st = R_.steps.find(s => s.f === f), pk = st.packs && st.packs[name];
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
  for (const s of R_.steps) if (s.f > 0 && s.f <= MAXH && s.ranges[fld] && (m !== "nbm" || s.f % 6 === 0)) out.push(s.f);
  return out.map(f => ({ f, ms: t0 + f * 3600e3 }));
}
const utcLbl = ms => { const d = new Date(ms); return `${DAYS[d.getUTCDay()].slice(0, 3)} ${d.getUTCMonth() + 1}-${d.getUTCDate()} ${String(d.getUTCHours()).padStart(2, "0")}Z`; };
async function totalField(m, c, kind, f0, f1) {
  const key = `${m}/${c}/${kind}/${f0}-${f1}`; if (WA.fields.has(key)) return WA.fields.get(key);
  const p = (async () => {
    const rk = rkey(m, c), R_ = WA.runs[rk], fld = PRODUCTS[kind].field[m] || PRODUCTS[kind].field.def;
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
    const [lut, mask] = await Promise.all([fetch(KIT + view + (mdl === "nbm" ? "/lut.bin" : `/lut_${mdl}.bin`)).then(r => { if (!r.ok) throw new Error("lut " + r.status); return r.arrayBuffer(); }).then(b => new Float32Array(b)),
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
async function render(cv, c, kind, view, d) {
  const P = PRODUCTS[kind], [K, VK, F] = await Promise.all([kindKit(kind, view), viewKit(view), fieldFor(c, kind, d)]);
  const [base, over, title] = await Promise.all([loadImg(KIT + view + "/base.png"), loadImg(KIT + view + "/" + kind + "_overlay.png"), loadImg(KIT + view + `/titles/${kind}_${d.day}.png`)]);
  cv.width = K.W; cv.height = K.H; const ctx = cv.getContext("2d");
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
  return { title: P.title(d), sub: P.sub(d), l1, l2, vals, steps: d.steps };
}
async function renderTotals(cv, m, c, kind, view, w) {
  const P = PRODUCTS[kind], pal = P.pal;
  const [K, VK, F, T, LB] = await Promise.all([kindKit("low", view), viewKit(view, m), totalField(m, c, kind, w.f0, w.f1),
    fetch(KIT + view + "/totals.json").then(r => r.json()), m === "nbm" ? null : fetch(KIT + view + `/lab_${m}.json`).then(r => r.json())]);
  const [base, over, title] = await Promise.all([loadImg(KIT + view + "/base.png"), loadImg(KIT + view + "/plain_overlay.png"), loadImg(KIT + view + `/titles/${kind}.png`)]);
  cv.width = K.W; cv.height = K.H; const ctx = cv.getContext("2d");
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
  const vals = {}, tv = {};
  K.labels.forEach((L, i) => {
    const [fi, fj] = LB ? LB[i] : [L.fi, L.fj], v = bil(F, fi, fj); if (v !== v) return;
    const x = Math.max(0, v); if (L.wa) vals[L.name] = x;
    if (L.wa && (kind === "snow" || !L.pass_)) tv[L.name] = +pal.fmt(x);
    pilText(ctx, pal.fmt(x), L.x, L.y, L.anchor, L.font, L.sw, "#fff");
  });
  const fitPx = (txt, px) => { while (px > 20) { ctx.font = `800 ${px}px Montserrat`; if (ctx.measureText(txt).width <= K.sum_maxw) break; px -= 2; } return px; };
  const mx = Math.max(...Object.values(tv));
  const l2 = !(mx > 0) ? P.none : extremeLine(Object.fromEntries(Object.entries(tv).map(([k, v]) => [k, v])), K.pops, P.word, false,
    s => { ctx.font = `800 ${K.sum_px[1]}px Montserrat`; return ctx.measureText(s).width <= K.sum_maxw; }).replace(/ ([\d.]+)$/, (q, v) => ` ${pal.fmt(+v)} in`);
  const rv = {}; for (const k in vals) rv[k] = +pal.fmt(vals[k]);
  const l1 = summaryLine1(K, rv, v => pal.fmt(v), " in"), [s2, s1] = K.summary;
  pilText(ctx, l2, s2.x, s2.y, "rs", ["", fitPx(l2, K.sum_px[1]), 800], 4, "#fff");
  pilText(ctx, l1, s1.x, s1.y, "rs", ["", fitPx(l1, K.sum_px[0]), 800], 4, "#fff");
  const R_ = WA.runs[rkey(m, c)], sub = `${utcLbl(w.ms0)} to ${utcLbl(w.ms1)} UTC (${w.f1 - w.f0} h) · ${SRC[m].name} ${c.slice(8)}Z run`;
  const dt = K.date[0]; pilText(ctx, sub, dt.x, dt.y, "ls", dt.font, 4, "#fff");
  return { title: P.title(), sub, l1, l2, vals, steps: [w.f0, w.f1], n: F.n };
}
// ---------------------------------------------------------------- page
const MODELS_T = ["nbm", "ifs9", "ifs", "hrrr"];
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
  const byK = k => T.findIndex(t => ymdh(t.ms) === k);
  let a = byK(S.f0), b = byK(S.f1);
  if (a < 0) a = 0; if (b < 0 || b <= a) b = T.length - 1; if (b <= a) a = Math.max(0, b - 1);
  S.f0 = ymdh(T[a].ms); S.f1 = ymdh(T[b].ms);
  fillSel($("from"), T.slice(0, -1).map(t => [ymdh(t.ms), utcLbl(t.ms)]), S.f0);
  fillSel($("to"), T.slice(a + 1).map(t => [ymdh(t.ms), utcLbl(t.ms)]), S.f1);
}
function runsOf(m) { return [...(WA.man.runs[m] || [])].reverse(); }
async function setRun() {   // model / kind changed: run list for the model (lows / highs: NBM only)
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
  if (tot) { const T = S.times, a = T.find(t => ymdh(t.ms) === S.f0), b = T.find(t => ymdh(t.ms) === S.f1); w = { f0: a.f, f1: b.f, ms0: a.ms, ms1: b.ms }; }
  else { d = S.days.find(x => x.key === S.day); if (!d) { $("msg").textContent = "No data for this day in this run."; return; } }
  $("msg").textContent = "Drawing…"; const t0 = performance.now();
  const cv = document.createElement("canvas");
  try { const info = tot ? await renderTotals(cv, S.m, S.c, S.kind, S.view, w) : await render(cv, S.c, S.kind, S.view, d); if (my !== S.busy) return;
    const old = $("map"); cv.id = "map"; old.replaceWith(cv); S.info = info; fit();
    const R_ = WA.runs[rkey(tot ? S.m : "nbm", S.c)];
    $("msg").textContent = `${R_.runline} · ${tot ? (S.m === "nbm" ? `sum of ${info.n} NBM 6 h amounts` : "run total at the end minus at the start") : S.kind === "low" ? "min of " + info.steps.length + " t2m steps" : "NBM 12 h max"} · ${Math.round(performance.now() - t0)} ms`;
    const u = new URL(location); u.searchParams.set("kind", S.kind); u.searchParams.set("view", S.view); u.searchParams.set("run", S.c);
    for (const k of ["day", "model", "from", "to"]) u.searchParams.delete(k);
    if (tot) { u.searchParams.set("model", S.m); u.searchParams.set("from", S.f0); u.searchParams.set("to", S.f1); } else u.searchParams.set("day", S.day);
    try { history.replaceState(null, "", u); } catch (e) {}
    window.__drawn = (window.__drawn || 0) + 1;
  } catch (e) { console.error(e); if (my === S.busy) $("msg").textContent = "Could not draw: " + e.message; }
}
function fit() {   // whole map in the window (phones: full width)
  const cv = $("map"), wr = $("wrap"), r = wr.getBoundingClientRect(), k = Math.min(r.width / cv.width, (r.height || 1e9) / cv.height);
  if (document.body.classList.contains("phone")) { cv.style.width = r.width + "px"; cv.style.height = (cv.height * r.width / cv.width) + "px"; }
  else { cv.style.width = cv.width * k + "px"; cv.style.height = cv.height * k + "px"; }
}
function save() {
  const cv = $("map"), v = VIEWS.find(x => x[0] === S.view)[1].replace(/ /g, "-");
  let name;
  if (isTot()) name = `${v}_${S.kind === "precip" ? "Precip" : "Snow"}_${S.f0.slice(4, 8)}-${S.f0.slice(8)}Z_to_${S.f1.slice(4, 8)}-${S.f1.slice(8)}Z_${SRC[S.m].name.replace(/[ °.]/g, "")}_${S.c.slice(8)}Z.jpg`;
  else { const d = S.days.find(x => x.key === S.day); name = `${v}_${S.kind === "low" ? "Lows" : "Highs"}_${d.day}-${d.md}_NBM_${S.c.slice(8)}Z.jpg`; }
  cv.toBlob(async b => {
    const f = new File([b], name, { type: "image/jpeg" });
    if (matchMedia("(max-width: 700px)").matches && navigator.canShare && navigator.canShare({ files: [f] })) { try { await navigator.share({ files: [f] }); return; } catch (e) { if (e.name === "AbortError") return; } }
    const a = document.createElement("a"); a.href = URL.createObjectURL(b); a.download = name; document.body.appendChild(a); a.click(); a.remove(); setTimeout(() => URL.revokeObjectURL(a.href), 60e3);
  }, "image/jpeg", 0.95);
}
async function boot() {
  const [man] = await Promise.all([fetch(DATA + "manifest.json", { cache: "no-cache" }).then(r => r.json()), document.fonts.load("800 40px Montserrat")]);
  WA.man = man; if (!(man.runs.nbm || []).length) { $("msg").textContent = "No NBM run available."; return; }
  const ms = MODELS_T.filter(m => (man.runs[m] || []).length); if (!ms.includes(S.m)) S.m = "nbm";
  fillSel($("model"), ms.map(m => [m, SRC[m].name]), S.m);
  fillSel($("kind"), KINDS, S.kind); fillSel($("view"), VIEWS, S.view);
  await setRun();
  $("run").onchange = async e => { S.c = e.target.value; await loadRunM(isTot() ? S.m : "nbm", S.c); if (isTot()) setTimes(); else setDays(); draw(); };
  $("kind").onchange = async e => { S.kind = e.target.value; await setRun(); draw(); };
  $("model").onchange = async e => { S.m = e.target.value; S.c = null; await setRun(); draw(); };
  $("from").onchange = e => { S.f0 = e.target.value; setTimes(); draw(); };
  $("to").onchange = e => { S.f1 = e.target.value; draw(); };
  $("day").onchange = e => { S.day = e.target.value; draw(); };
  $("view").onchange = e => { S.view = e.target.value; draw(); };
  $("save").onclick = save;
  const mq = matchMedia("(max-width: 700px)"), ph = () => { document.body.classList.toggle("phone", mq.matches); fit(); };
  ph(); (mq.addEventListener ? mq.addEventListener("change", ph) : mq.addListener(ph)); addEventListener("resize", fit);
  await draw(); window.__ready = true;
}
boot().catch(e => { console.error(e); $("msg").textContent = "Could not load: " + e.message; });
