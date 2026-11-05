// PROTOTYPE fast viewer: draws HRRR maps in the browser from 8-bit data images (values stored in pixel colors).
// No framework. Static layers (borders, towns, color keys) are drawn once by the encoder with the site's own code.
"use strict";
const $ = id => document.getElementById(id);
// Old-site links (go-live audit 10-30 8:50 PM): the old site kept its state in the hash (#t=tab&m=model&p=period&v=view&e=end,
// #t=meteograms&s=&w=&p=, #t=obs&v=). Bookmarks / shared links of the old site open the matching fast map, meteogram or obs.
(function oldLink() {
  const h = new URLSearchParams(location.hash.slice(1)), t = h.get("t"); if (!t || location.search) return;
  if (t === "meteograms") { location.replace(`meteograms.html#${new URLSearchParams({ s: h.get("s") || "", w: h.get("w") || "", p: h.get("p") || "" })}`); return; }
  if (t === "obs") { location.replace("?obs=1"); return; }
  const M = { "ECMWF 0.25\u00b0": "ifs", ECMWF: "ifs", AIFS: "aifs", GFS: "gfs", HRRR: "hrrr", RRFS: "rrfs", NBM: "nbm", EPS: "eps", "EPS mean": "eps",
              "EPS 90th pct": "eps", "AIFS ENS": "aens", "AIFS ENS mean": "aens" };
  const V = { full: "wa", west: "wwa", east: "ewa", cascades: "passes", northeast: "newa", lowermainland: "lm", vi: "wa" };
  const ml = h.get("m") || "", m = M[ml] || "", per = h.get("p") || "", p90 = /90th/.test(ml);
  const acc = { "1h": "qpf1", step: "qpf3", "6h": "qpf6", "12h": "qpf12", "24h": "qpf24", "48h": "qpf48", total: "qpf" };
  let prod = { t2m: "t2m", t2manom: "t2ma", feels: "feels", t850: "t850w", gust10: "gust10", peakgust: "gustmax", td2m: "d2m", t925: "t925w",
    t700: "t700w", t500: "t500w", t300: "t300w", mslpptype: "ptype", snowkuch: "kuchera", snowk24: "kuch24", snowrate: "snow1", frzr: "fzra",
    tcc: "tcc", ir: "ir", vis: "vis", fog: "fog", ivt: "ivt", pwanom: "pwa", pw: "pw", w250: "w250", w500: "w500", w850: "w850", thick: "thick",
    t850anom: "t850a", aifs500: "z500anom", aifsmslp: "slp", mslpprecip: "mslpqpf", aifswind: "aifswind", elows: "elows", e500: "spag" }[t] || "";
  const hh = { "6h": "6", "12h": "12", "24h": "24", "48h": "48" }[per];
  if (t === "rain" || t === "bcrain" || t === "qpf") prod = m === "nbm" ? (per === "1h" ? "nqpf1" : per === "total" ? "nqpftot" : "nqpf" + (hh || "6")) : p90 ? "eqpf90" : (acc[per] || "qpf");
  if (t === "snow" || t === "snow10") prod = m === "nbm" ? (per === "total" ? "nsnowtot" : "nsnow" + (hh || "6")) : m === "eps" ? (p90 ? "esnow90" : hh ? "esnow" + hh : "esnow")
    : per === "1h" ? "snow1" : hh ? "snow" + hh : "snow";
  if (t === "snowkuch" && hh) prod = "kuch" + hh;
  if (t === "frzr" && hh) prod = "fzra" + hh;
  if (t === "gusts") prod = p90 ? "egust90" : per === "max6h" && m !== "nbm" ? "gust6" : per === "max12h" && m !== "nbm" ? "gust12" : per === "max24h" && m !== "nbm" ? "gust24" : "gust10";
  if (t === "lows") prod = m === "eps" ? "elow" : "nmint";
  if (t === "highs") prod = m === "eps" ? "ehigh" : "nmaxt";
  if (t === "waves") prod = per === "max24h" ? "wavemax" : "waves";
  const q = new URLSearchParams(); if (prod) q.set("prod", prod); if (m || t === "waves") q.set("model", m || "ifs");
  const v = h.get("v"); if (v) q.set("view", V[v] || v); q.set("valid", h.get("e") || new Date().toISOString());   // old default: the first frame that is current
  history.replaceState(null, "", "?" + q);
})();
// 11-04 (t2283u): index.html opened with no map in the URL (bookmark, home-screen app) comes back on the last model / product / view / hour
try { const q0 = new URLSearchParams(location.search), sv0 = localStorage.getItem("viewer:last");
  if (sv0 && !/studio\.html$/.test(location.pathname) && !location.hash && !["run", "model", "prod", "view", "f", "valid", "obs", "mg", "embed", "id", "slim", "studio"].some(k => q0.has(k))) history.replaceState(null, "", location.pathname + sv0); } catch (e) { /* private mode */ }
const Q = new URLSearchParams(location.search);
const DATA = window.WX_DATA || "data/";   // "/d/" on the hosted fast page (Pages Function -> R2)
const S = { man: null, runs: {}, view: Q.get("view") || "wa", prod: Q.get("prod") || "t2m", run: null, i: 0,
            fields: new Map(), derived: new Map(), statics: {}, pix: {}, timings: [] };
window.__S = S;

const pt = v => v * S.man.dpi / 72;                 // points -> canvas px (same as matplotlib at the encoder dpi)
// 11-03 hidden preview (NOAA WW3, no R2 writes): a site-shipped supplement (pdata/manifest_pv.json: models + runs for new models) is
// merged into the manifest, and data URLs for those models (runs/<m>/, static lut_/key_<m>_) are read from the site's pdata/ copy.
// No pdata/ on the site (production) -> nothing changes.
let PV = null;
const pvU = u => { if (!PV || typeof u !== "string" || !u.startsWith(DATA)) return u; const r = u.slice(DATA.length);
  return PV.re.test(r) ? "pdata/" + r : u; };
const pvMerge = M => { if (PV) { Object.assign(M.models || (M.models = {}), PV.models); Object.assign(M.runs || (M.runs = {}), PV.runs); } return M; };
{ const f0 = window.fetch.bind(window); window.fetch = (u, o) => f0(pvU(u), o); }
// 11-03 AIFS ENS single members (model "aensm", Benjamin t2147u / t2148u / t2153u): one file per member per hour (run.json file has {mem});
// the member box under Runs picks the member, and only that member's files are fetched. Cache keys carry the member.
S.mem = Math.min(50, Math.max(1, parseInt(Q.get("mem") || "1", 10) || 1));
const isMemRun = r => !!(S.runs[r] && S.runs[r].file && S.runs[r].file.includes("{mem}"));
const rk = r => isMemRun(r) ? `${r}#m${S.mem}` : r;   // run key incl. member (field / product / line caches)
const memPad = () => String(S.mem).padStart(2, "0");
function prepRun(R_) {   // runline "... member {mem} ..." follows the picked member
  if (R_ && typeof R_.runline === "string" && R_.runline.includes("{mem}")) { const t = R_.runline; Object.defineProperty(R_, "runline", { get: () => t.replace("{mem}", S.mem), configurable: true }); }
  return R_;
}
const img = src => new Promise((ok, no) => { const im = new Image(); im.onload = () => ok(im); im.onerror = no; im.src = pvU(src); });

function fitPhone() {   // phones: map as large as fits between the menus and the slider bar, placed right under the menus
  const cv = $("map"); if (!cv) return;
  const LW = cv._lw || cv.width, LH = cv._lh || cv.height;   // logical (figure px) size; the bitmap can be LW x RS (sharpMap)
  const cb = CMPBOX && !document.body.classList.contains("phone") && !document.body.classList.contains("cslim") ? CMPBOX : null;   // compare: same size as the other map
  if (cb) { const k = Math.min(cb.w / LW, cb.h / LH, 1); cv.style.maxWidth = Math.floor(LW * k) + "px"; cv.style.maxHeight = Math.floor(LH * k) + "px"; }
  else { cv.style.maxWidth = `min(100%, ${LW}px)`; cv.style.maxHeight = document.body.classList.contains("phone") ? "none" : `min(100%, ${LH}px)`; }
  if (!document.body.classList.contains("phone") || !cv.width) { cv.style.width = cv.style.height = ""; schedSharp(); return; }
  const wr = $("wrap"), cs = getComputedStyle(wr), padX = parseFloat(cs.paddingLeft) + parseFloat(cs.paddingRight), padY = parseFloat(cs.paddingTop) + parseFloat(cs.paddingBottom);
  const vh = window.visualViewport ? visualViewport.height : innerHeight;
  const availW = document.documentElement.clientWidth - padX, availH = document.body.classList.contains("cslim") ? 1e5 : document.body.classList.contains("embed") ? vh - 2 : vh - $("bar").offsetHeight - $("dock").offsetHeight - padY;   // compare frames (11-01 t2027u): menus sit under the map, so they never change its size
  const k = Math.max(0.05, Math.min(availW / LW, availH / LH));
  cv.style.width = Math.floor(LW * k) + "px"; cv.style.height = Math.floor(LH * k) + "px"; schedSharp();
}
// 10-30 4:50 PM (Benjamin: "the model images look super low res on the phone"): the map bitmap was always the figure size
// (1600 px wide, encoder dpi 100; the old site's PNGs are 150 dpi = 2400 px), and the in-page zoom is a CSS scale of that
// bitmap, so a 2.5x double-tap on a 3x iPhone stretched 1600 px over ~2900 screen px (soft text, lines and color edges).
// Now the bitmap follows the screen: RS = shown size x devicePixelRatio x zoom / figure size (1 .. 3, at most 12 MP, steps
// of 0.25). Lines, barbs, H/L, numbers and header text are drawn at RS; the color fill is binned at RS from the same values
// (sharp band edges); the fixed layers (borders, town names, color key) are 1600 px PNGs scaled up smoothly. RS = 1 (phone
// unzoomed, ordinary desktop) draws exactly as before. A new RS is applied ~200 ms after zooming stops; while the slider is
// dragged the RS in use is kept and the fill is the light half-res one; the full sharp frame comes when the finger lifts.
function wantRS(LW, LH) {
  const cv = $("map"); if (!cv || !LW || Q.get("rs1")) return 1;
  if (window.__saveRS) return window.__saveRS;   // 11-03 zoomed "Save image": one sharp redraw at the save resolution
  if (Q.get("studio")) return Math.max(1, Math.min(3, Math.floor(Math.sqrt(16e6 / (LW * LH)) * 4) / 4));   // Studio: always sharp (crops are scaled up to 1920 px)
  const shown = cv.offsetWidth || LW, want = shown * (window.devicePixelRatio || 1) * (Z.k || 1) / LW;
  const cap = Math.min(3, Math.sqrt(12e6 / (LW * LH)));
  return Math.max(1, Math.min(cap, Math.ceil(want * 4 - 0.2) / 4));
}
// 10-30 7:30 PM (Benjamin: "images are still blurry on the phone view", "check the desktop versions too"): the soft parts were
// the fixed layers (coast / borders / county lines, town names, color key + credit), 1600 px PNGs stretched to the RS bitmap
// (2x on a zoomed phone, 1.5x on a retina laptop). The encoder now also saves them at 2x (static/x2/, same figure, same
// placement). When the bitmap is above 1x the x2 file is fetched (only then: unzoomed phones / 1x desktops never load
// it), the 1x one is drawn until it lands, then the frame is redrawn. Missing x2 file (404) -> 1x, no retry. ?x1=1 = old way.
const X2 = new Map();   // 1x url -> HTMLImageElement | null (failed) | Promise (loading); small LRU (decoded 3200 px layers are big)
function layer(im1, u1, rs) {
  if (!im1 || !u1 || rs <= 1.01 || Q.get("x1")) return im1;
  const h = X2.get(u1);
  if (h instanceof HTMLImageElement) { X2.delete(u1); X2.set(u1, h); return h; }
  if (h === undefined) {
    const u2 = u1.replace("static/", "static/x2/");
    X2.set(u1, img(u2).then(im => (im.decode ? im.decode().then(() => im, () => im) : im)).then(im => {
      X2.set(u1, im); while (X2.size > 5) X2.delete(X2.keys().next().value);
      if (window.__drawn) draw(); }, () => X2.set(u1, null)));
  }
  return im1;
}
// x2 layer at a bitmap scale other than 2 (e.g. 1.5 on a retina laptop): resample once into a canvas of the bitmap size, so each
// frame copies it 1:1 instead of resampling three 3200 px layers per frame (measured +25 ms per frame at RS 1.5 without this)
const XS = new Map();
function fitLayer(im, u1, rs, LW, LH) {
  if (!im || !(im instanceof HTMLImageElement) || im.naturalWidth <= LW + 1) return im;   // 1x layer: as before
  const w = Math.round(LW * rs), h = Math.round(LH * rs); if (Math.abs(im.naturalWidth - w) <= 1) return im;
  const k = `${u1}@${w}x${h}`; let c = XS.get(k);
  if (!c) { c = document.createElement("canvas"); c.width = w; c.height = h; const x = c.getContext("2d");
    x.imageSmoothingEnabled = true; x.imageSmoothingQuality = "high"; x.drawImage(im, 0, 0, w, h);
    XS.set(k, c); while (XS.size > 4) XS.delete(XS.keys().next().value); }
  else { XS.delete(k); XS.set(k, c); }
  return c;
}
let sharpTimer = null;
function schedSharp() {
  clearTimeout(sharpTimer); sharpTimer = setTimeout(() => { const cv = $("map");
    if (cv && cv._lw && window.__drawn && !S.dragging && wantRS(cv._lw, cv._lh) !== (cv._rs || 1)) draw(); }, 200);
}
// 10-31 6:44 PM (Benjamin: "Scrubbing through the model hours on the studio view is not smooth on the phone version"): Studio keeps
// its map bitmap at RS 3 (4800 x 3150) for sharp 1920 px frames, and the light drag frame was drawn at that size too (~0.5-1 s
// per hour on a 4x-slowed phone CPU, and the Studio frames did not change at all until the finger lifted). While the slider is
// dragged in Studio the map is now drawn at RS 1 (9x fewer pixels) and the Studio frames follow every drawn hour; the sharp RS 3
// frame is drawn once when the finger lifts.
const STUDIO_DRAG_RS = 1;   // FINE_PTR: mouse / trackpad (a full Studio frame takes ~0.5-1 s on a phone CPU, so touch keeps the light frames)
const FINE_PTR = !!(window.matchMedia && matchMedia("(hover: hover) and (pointer: fine)").matches);
// Regular maps (t2511u): show the Coast view's 16:9 camera (studio_views fit = COAST_H), the same ocean-centered box Studio uses
// for the wide frame, Westport included. fitV (the 9:16 box) stays Studio-only. The blit is 1:1 figure pixels, so the map is not stretched.
// Header, color key and credit sit in bands outside that box. Studio never calls this; it still crops fit / fitV itself.
function coastShown(V) {
  if (Q.get("studio") || !V || !V.studioCoast || !V.fit) return null;
  const x = +V.fit[0], y = +V.fit[1], w = +V.fit[2], h = +V.fit[3];
  if (!(w > 40 && h > 40)) return null;
  const head = Math.round(Math.min(78, Math.max(58, h * 0.07))), foot = Math.round(Math.min(120, Math.max(88, h * 0.11)));
  return { x, y, w, h, head, foot, W: w, H: head + h + foot };
}
function coastKey(ctx, P, x, y, w, h) {
  const L = P && P.levels, C = P && P.colors; if (!L || !C || L.length < 2 || !C.length) return false;
  const n = Math.min(C.length, L.length - 1), span = (L[L.length - 1] - L[0]) || 1;
  for (let i = 0; i < n; i++) { ctx.fillStyle = C[i]; ctx.fillRect(Math.floor(x + (i / n) * w), y, Math.ceil(w / n) + 1, h); }
  ctx.strokeStyle = "rgba(255,255,255,0.55)"; ctx.lineWidth = 1; ctx.strokeRect(x, y, w, h);
  ctx.fillStyle = "#e9ecf1"; ctx.font = "600 12px Montserrat"; ctx.textAlign = "center"; ctx.textBaseline = "top";
  let last = -1e9; for (const t of (P.ticks || [])) { if (t < L[0] || t > L[L.length - 1]) continue; const tx = x + (t - L[0]) / span * w, s = String(t);
    if (tx - 8 < last) continue; last = tx + 16; ctx.fillText(s, tx, y + h + 2); }
  ctx.textAlign = "left"; ctx.textBaseline = "alphabetic"; ctx.font = "700 13px Montserrat"; if (P.key) ctx.fillText(P.key, x, y - 4);
  return true;
}
function showCoast(cv, V, meta) {
  const C = coastShown(V); if (!C || !cv) return false;
  const rs = cv._rs || 1, src = document.createElement("canvas"); src.width = cv.width; src.height = cv.height;
  src.getContext("2d").drawImage(cv, 0, 0);
  cv.width = Math.max(1, Math.round(C.W * rs)); cv.height = Math.max(1, Math.round(C.H * rs)); cv._lw = C.W; cv._lh = C.H;
  const ctx = cv.getContext("2d"); ctx.setTransform(rs, 0, 0, rs, 0, 0); ctx.imageSmoothingEnabled = true; ctx.imageSmoothingQuality = "high";
  ctx.fillStyle = (S.man && S.man.style && S.man.style.BG) || "#111318"; ctx.fillRect(0, 0, C.W, C.H);
  ctx.drawImage(src, C.x * rs, C.y * rs, C.w * rs, C.h * rs, 0, C.head, C.w, C.h);   // uniform scale: dest w/h equals source w/h
  const m = meta || {}, ink = (S.man && S.man.style && S.man.style.INK) || "#f4f2ee", acc = (S.man && S.man.style && S.man.style.ACCENT) || "#ffc24d", muted = (S.man && S.man.style && S.man.style.MUTED) || "#a7abb3";
  ctx.textAlign = "left"; ctx.textBaseline = "top"; ctx.fillStyle = ink; ctx.font = "800 22px Montserrat"; ctx.fillText(m.title || "", 14, 6);
  ctx.fillStyle = acc; ctx.font = "700 15px Montserrat"; ctx.fillText(m.valid || "", 14, 30);
  ctx.fillStyle = muted; ctx.font = "500 12px Montserrat"; ctx.fillText(m.sub || "", 14, 48);
  if (m.badge) { ctx.textAlign = "right"; ctx.fillStyle = ink; ctx.font = "800 18px Montserrat"; ctx.fillText(m.badge[0] || "", C.W - 14, 8); ctx.fillStyle = muted; ctx.font = "600 11px Montserrat"; ctx.fillText(m.badge[1] || "", C.W - 14, 30); ctx.textAlign = "left"; }
  const barY = C.head + C.h + 18, barH = 14;
  if (m.P) coastKey(ctx, m.P, 14, barY, Math.max(80, C.W - 28), barH);
  if (m.pid && m.P) { const lines = creditLines(m.pid, m.P, m.towns !== false); ctx.fillStyle = muted; ctx.font = "500 11px Montserrat"; ctx.textBaseline = "bottom"; lines.forEach((l, i) => ctx.fillText(l, 14, C.H - 6 - (lines.length - 1 - i) * 14)); }
  fitPhone(); return true;
}
function sizeMap(cv, V, keepRS) {   // bitmap = figure px x RS; context transform = RS, so all drawing stays in figure px
  const [LW, LH] = V.fig, rs = keepRS && Q.get("studio") && S.dragging ? STUDIO_DRAG_RS : keepRS && cv._lw === LW && cv._lh === LH ? (cv._rs || 1) : wantRS(LW, LH);
  const bw = Math.round(LW * rs), bh = Math.round(LH * rs), relayout = cv._lw !== LW || cv._lh !== LH;
  if (cv.width !== bw || cv.height !== bh) { cv.width = bw; cv.height = bh; }
  cv._lw = LW; cv._lh = LH; cv._rs = rs; if (relayout) fitPhone();
  const ctx = cv.getContext("2d"); ctx.setTransform(rs, 0, 0, rs, 0, 0); ctx.imageSmoothingEnabled = true; ctx.imageSmoothingQuality = "high";
  return ctx;
}
function fillSharp(ctx, st, vals, pal, mins, nn, rs) {   // fill binned at RS from the figure-px values (bilinear; precip type nearest)
  const W = st.W, H = st.H, X0 = Math.round(st.x0 * rs), Y0 = Math.round(st.y0 * rs);
  const w2 = Math.round((st.x0 + W) * rs) - X0, h2 = Math.round((st.y0 + H) * rs) - Y0, sx = W / w2, sy = H / h2;
  const im = new ImageData(w2, h2), o32 = new Uint32Array(im.data.buffer), le = new Uint8Array(new Uint32Array([1]).buffer)[0] === 1;
  const pk = c => c ? (le ? (255 << 24 | c[2] << 16 | c[1] << 8 | c[0]) >>> 0 : (c[0] << 24 | c[1] << 16 | c[2] << 8 | 255) >>> 0) : 0;
  const cols = pal.cols.map(pk), under = pk(pal.under), over = pk(pal.over);
  const CX = new Int32Array(w2), TX = new Float32Array(w2);
  for (let x = 0; x < w2; x++) { const fx = Math.min(W - 1, Math.max(0, (x + 0.5) * sx - 0.5)), c0 = Math.min(W - 2, fx | 0); CX[x] = c0; TX[x] = fx - c0; }
  const lo = mins === undefined ? -Infinity : mins;
  for (let y = 0; y < h2; y++) {
    const fy = Math.min(H - 1, Math.max(0, (y + 0.5) * sy - 0.5)), r0 = Math.min(H - 2, fy | 0), ty = fy - r0, row = r0 * W, q0 = y * w2;
    let lastK = -1, a = 0, b = 0, c = 0, d = 0;
    for (let x = 0; x < w2; x++) {
      const k = row + CX[x], tx = TX[x];
      if (k !== lastK) { a = vals[k]; b = vals[k + 1]; c = vals[k + W]; d = vals[k + W + 1]; lastK = k; }
      let v;
      if (nn) v = tx >= 0.5 ? (ty >= 0.5 ? d : b) : (ty >= 0.5 ? c : a);
      else { v = (a + (b - a) * tx) * (1 - ty) + (c + (d - c) * tx) * ty;
             if (v !== v) v = tx >= 0.5 ? (ty >= 0.5 ? d : b) : (ty >= 0.5 ? c : a); }
      if (!(v >= lo)) continue;   // NaN or below the shown minimum
      o32[q0 + x] = v < pal.L0 ? under : v >= pal.Lend ? over : cols[bin(pal, v)];
    }
  }
  const tmp = new OffscreenCanvas(w2, h2); tmp.getContext("2d").putImageData(im, 0, 0);
  ctx.save(); ctx.setTransform(1, 0, 0, 1, 0, 0); ctx.drawImage(tmp, X0, Y0); ctx.restore();
}
// 10-31 06Z/18Z ensembles, hidden preview before a push: runs the box published under manifest "runs_x" (run file run_x.json, so
// the production page never lists them) join the normal run lists here. After the push the workflow drops runs_x itself.
const XR = new Set();
function mergeRunsX(man) {
  for (const [m, cs] of Object.entries(man.runs_x || {})) {
    const reg = (man.runs || {})[m] || [];
    for (const c of cs) if (!reg.includes(c)) XR.add(`${m}/${c}`);
    (man.runs = man.runs || {})[m] = [...new Set([...reg, ...cs])].sort();
  }
  return man;
}
// 10-31 7:30 PM (Benjamin: "a slightly more zoomed-out Washington view made specifically for Studio loop videos"): Studio only, an
// extra view "Washington (wide, for loops)" = this model's Pacific NW tight / high-res map (src) that Studio frames on Washington so
// the whole state fits both video frames. Same data, basemap, towns and key as src; the normal Washington view is unchanged.
// 11-02 (Benjamin t2105u "Passes need to be added to maps on Washington wide for loops"): the global models' wide view uses a town
// layer with the Washington view's 9 passes (plum triangle + italic name; studio_views.py --passes), shipped with the site ("@").
const WAWIDE_PASSES_PNG = "@slayers/static/towns_wawide_p1.png";
// 11-04 (Benjamin t2308u "Make the town names little smaller on Washington wide for loops"): town / pass labels ~17 % smaller on the
// wide view (studio_views wawide_small_towns.py: towns_wawide_s2.png + its number slots, shipped with the site); wave maps' coast labels too
// 11-04 (t2314u "yes rebuild those too"): HRRR / RRFS / NBM wide view (pnwhr) too: wawide_s2.json models.{hrrr,rrfs,nbm} = {towns, towns_png}
let WAWIDE_S2 = null; const WAWIDE_FS = 0.83;
function addStudioViews(man, sv) {
  // 10-31 7:55 PM (Benjamin: "city labels on the new washington wide are way too big"): the global models now get a real view
  // made for Studio (tools/fast/studio_views.py -> static/studio_views.json, not in manifest.json): its own basemap and town layer
  // drawn at the size the Studio frames show it. Models without one (HRRR / RRFS / NBM) keep the high-res Pacific NW map as before.
  // Washington (wide, for loops) stays Studio-only. Coast view does not: the regular map page lists it too (t2511u).
  const SVM = (sv && sv.models) || {};
  if (Q.get("studio")) for (const [m, M] of Object.entries(man.models || {})) { const V = M.views || {}, own = (SVM[m] || {}).wawide, src = V.pnwt ? "pnwt" : V.pnwhr ? "pnwhr" : null;
    if ((!own && !src) || !V.wa || V.wawide) continue; const out = {};
    for (const [k, v] of Object.entries(V)) { out[k] = v; if (k === "wa") out.wawide = own ? Object.assign({}, own, { studioWide: "wa", towns_png: WAWIDE_PASSES_PNG }, WAWIDE_S2 && WAWIDE_S2.models && WAWIDE_S2.models[m] ? { towns: WAWIDE_S2.models[m], towns_png: "@slayers/" + WAWIDE_S2.png } : {}) : Object.assign({}, V[src], { label: "Washington (wide, for loops)", src, studioWide: "wa" }, WAWIDE_S2 && WAWIDE_S2.models && WAWIDE_S2.models[m] && WAWIDE_S2.models[m].towns_png ? { towns: WAWIDE_S2.models[m].towns, towns_png: "@slayers/" + WAWIDE_S2.models[m].towns_png, townsOwn: true } : {}); }
    M.views = out; }
  // 11-04 (Benjamin t2289u "Make me a coastal view for studio that is a little bigger and wider, centered over the ocean, land in the right
  // third. Call it 'coast view'"): "Coast view" (studio_views.py, view id coast). Studio keeps framing it with fit / fitV.
  // 11-04 t2300u / t2311u: coast_s (30 mi south of coast_t), its own base / towns / LUT. A model with neither entry is not offered
  // (HRRR / RRFS / NBM have no coast LUT). This is not the wave-only West Coast view (wave_views id wc).
  // 11-05 (t2511u): the same coast entry is in the regular View menu. The map page shows the 16:9 camera box (fit), not fitV.
  for (const [m, M] of Object.entries(man.models || {})) { const V = M.views || {}, sv = SVM[m] || {}, ck = sv.coast_s ? "coast_s" : sv.coast_t ? "coast_t" : null, own = ck ? Object.assign({}, sv[ck], { base_png: `static/base_${ck}.png`, towns_png: sv[ck].towns_png || `static/towns_${ck}.png` }) : sv.coast;   // t2311u: coast_s = 30 mi south
    if (!own || V.coast) continue; const out = {}; let put = false; const anchor = Q.get("studio") ? "wawide" : "wa";
    for (const [k, v] of Object.entries(V)) { out[k] = v; if (k === anchor) { out.coast = Object.assign({}, own); put = true; } }
    if (!put) out.coast = Object.assign({}, own); M.views = out; }
  return man;
}
// 10-31 8:17 PM (Benjamin: "Fix the pacific nw tight view"): per-view overrides from static/view_fixes.json (studio_views.py
// pnwt_fix) laid over the manifest: Pacific NW tight's town layer (towns_pnwt_v2.png) + the number slots built with it, since the
// old towns_pnwt.png no longer matched the manifest's slots (numbers sat on other towns' names). Missing file -> manifest as is.
function viewFixes(man, vf) {
  for (const [m, vs] of Object.entries((vf && vf.models) || {})) { const M = (man.models || {})[m]; if (!M) continue;
    for (const [vid, o] of Object.entries(vs)) if (M.views[vid] && o.towns && o.towns_png) M.views[vid] = Object.assign({}, M.views[vid], { towns: o.towns, towns_png: o.towns_png }); }
  return man;
}
// 11-01 9:40 AM (Benjamin t1999u "Make me a new view, just for waves right now, titled west coast"): wave-only views from
// static/wave_views.json (tools/fast/wave_views.py, not in manifest.json), inserted after their "after" view; offered for wave products only
function waveViews(man, wv) {
  for (const [m, vs] of Object.entries((wv && wv.models) || {})) { const M = (man.models || {})[m]; if (!M || !M.views) continue;
    for (const [vid, e] of Object.entries(vs)) { if (M.views[vid]) continue; const out = {}; let put = false;
      for (const [k, v] of Object.entries(M.views)) { out[k] = v; if (k === e.after) { out[vid] = e; put = true; } }
      if (!put) out[vid] = e; M.views = out; } }
  return man;
}
const VSRC = (vid) => { const V = VIEWS()[vid]; return (V && V.src) || vid; };   // file / tuning id of a view (Studio wide view -> its src)
const runFile = (r) => XR.has(r) ? "run_x.json" : "run.json";
async function boot() {
  if (Q.get("bare")) document.body.classList.add("bare");
  if (Q.get("embed")) { document.body.classList.add("embed"); addEventListener("message", onCompareMsg); }
  // 10-31 3:17 PM slim compare (Benjamin: "a slimmer phone compare"): menus folded behind a small button, the compare page's shared
  // hour slider replaces this frame's own, the map is sized to the frame width (the page sizes the frame to the map)
  if (Q.get("slim")) document.body.classList.add("cslim");
  // 11-01 (Benjamin t2021u: "Need a way to minimize the menus after I've opened them in the compare view"): every compare frame (desktop
  // and phone) gets a Menus / Hide menus toggle; shown menus put "Hide menus" first in the bar, hidden menus leave a small "Menus" pill.
  // Remembered per frame (localStorage cmpMenus_L / _R). The compare page's "Hide menus" button sets both frames at once.
  if (Q.get("embed")) { const b = document.createElement("button"); b.id = "cgear"; b.type = "button";
    b.title = "Show / hide this map's model, product and view menus"; b.onclick = () => cmpMenus(!cmpMenusShown(), true);
    let sv = null; try { sv = localStorage.getItem("cmpMenus_" + Q.get("id")); } catch (e) { /* private mode */ }
    cmpMenus(sv === null ? !Q.get("slim") : sv === "1", false, b); }
  if (Q.get("embed") && "ResizeObserver" in window) new ResizeObserver(() => cmpBox()).observe($("wrap"));
  if (Q.get("slim")) {
    let lh = 0; new ResizeObserver(() => { const h = cslimH(); if (Math.abs(h - lh) > 2 && parent !== window) { lh = h; parent.postMessage({ wx: "size", id: Q.get("id"), h }, "*"); } }).observe(document.body); }
  // 10-29: manifest, fonts and the shown run's run.json in parallel; other runs load when picked
  PV = await fetch("pdata/manifest_pv.json", { cache: "no-cache" }).then(r => r.ok ? r.json() : null).catch(() => null);
  if (PV) PV.re = new RegExp(`^(runs/(${Object.keys(PV.models).join("|")})/|static/(x2/)?(lut|key)_(${Object.keys(PV.models).join("|")})_)`);
  const [man, sv, vf, wv] = await Promise.all([fetch(DATA + "manifest.json", { cache: "no-cache" }).then(r => r.json()).then(pvMerge),
                                   fetch(DATA + "static/studio_views.json", { cache: "no-cache" }).then(r => r.ok ? r.json() : null, () => null),
                                   fetch(DATA + "static/view_fixes.json", { cache: "no-cache" }).then(r => r.ok ? r.json() : null, () => null),
                                   fetch(DATA + "static/wave_views.json", { cache: "no-cache" }).then(r => r.ok ? r.json() : null, () => null),
                                   document.fonts.load("800 20px Montserrat"), document.fonts.load("500 12px Montserrat"),
                                   Q.get("studio") ? fetch("slayers/static/wawide_s2.json", { cache: "no-cache" }).then(r => r.ok ? r.json() : null, () => null).then(j => { WAWIDE_S2 = j; }) : null]);
  if (PV && PV.studio && sv) Object.assign(sv.models || (sv.models = {}), PV.studio);   // 11-03 preview supplement: Studio wide view
  S.man = addStudioViews(waveViews(viewFixes(mergeRunsX(man), vf), wv), sv);
  // runs: "model/cycle", newest first per model; models in a fixed order
  const order = ["hrrr", "rrfs", "nbm", "gfs", "ifs", "ifs9", "aifs", "eps", "aens", "aensm", "epsm", "gfsw", "oisst"].filter(m => S.man.models[m] && (S.man.runs[m] || []).length);
  const all = []; for (const m of order) for (const c of [...S.man.runs[m]].reverse()) all.push(`${m}/${c}`);
  const qr = Q.get("run"), qm = Q.get("model");
  // 11-01: a ?prod= link with no run/model (e.g. ?prod=waves) opens the first model that has that product
  const qp = !qr && !qm && Q.get("prod"), pm = qp && order.find(m => allProds(S.man.models[m])[qp]);
  S.run = all.includes(qr) ? qr : (all.find(r => qm && r.startsWith(qm + "/")) || (pm && all.find(r => r.startsWith(pm + "/"))) || all[0]);
  // 11-04 (Benjamin t2269u "when I refresh a product, or Studio, it refreshes onto the same exact product and view with the latest model
  // data"): a ?run= from the URL (kept there on every change) opens that model's newest run, at the same valid time when the newest run
  // has it (within 3 h), else the same forecast hour (t2270u: same model, same product, latest data). Same product, view, member and Studio framing.
  let vKeep = null;
  // 11-04 (t2286u, "it goes to the 2m temp on the latest HRRR run"): the URL's run had rolled out of the manifest (older cycles are pruned),
  // so the model fell back to the first one (HRRR). The model now comes from the URL's run even when that run is gone, and the valid time
  // is worked out from its cycle + forecast hour (no need to read the old run).
  if (qr && !Q.get("embed") && !Q.get("id") && !Q.get("slim")) { const qm2 = qr.split("/")[0], cyc = qr.split("/")[1] || "", nw = all.find(r => r.startsWith(qm2 + "/")), f0q = +Q.get("f");
    if (nw && nw !== qr) { S.run = nw;
      if (/^\d{10}$/.test(cyc) && isFinite(f0q)) vKeep = Date.UTC(+cyc.slice(0, 4), +cyc.slice(4, 6) - 1, +cyc.slice(6, 8), +cyc.slice(8, 10)) + f0q * 3600e3; } }
  await loadRun(S.run);
  // 11-04 (Benjamin t2319u/t2336u "It refreshes into a different product"): a refresh moves to the model's newest run, but a run that is
  // still coming in (or lacks this product) used to drop the product back to the tab's first one. Now the newest run is used only when it
  // carries the product; otherwise the refresh stays on the run in the address (same product, same hour).
  if (qr && S.run !== qr && Q.get("prod")) { const P0 = PRODS()[Q.get("prod")], carries = r => P0 && P0.fields.every(f => new Set((S.runs[r] || {}).fields || []).has(f));
    if (P0 && !carries(S.run)) { const m0 = qr.split("/")[0], cand = [qr, ...all.filter(r => r.startsWith(m0 + "/") && r !== S.run && r !== qr)].filter(r => all.includes(r)).slice(0, 3);
      for (const r of cand) { try { await loadRun(r); } catch (e) { continue; } if (carries(r)) { if (r !== qr) { /* keep the valid time */ } else vKeep = null; S.run = r; break; } } } }
  // "Runs" menu (Benjamin 10-29 7:10 PM): every available run, grouped by model, newest first; picking one keeps the valid time
  const runLabel = r => { const [m, c] = r.split("/"), p = ((S.man.progress || {})[m] || {})[c];
    if (m === "oisst") { const st = (S.runs[r] || {}).steps, d = x => { const v = new Date(x.valid); return `${v.getUTCMonth() + 1}-${v.getUTCDate()}`; };   // 11-03: daily analyses, not a run time
      return `${S.man.models[m].site} daily ${c.slice(4, 6)}-${c.slice(6, 8)}` + (st && st.length ? ` to ${d(st[st.length - 1])}` : ""); }
    return `${S.man.models[m].site} ${c.slice(8)}Z ${c.slice(4, 6)}-${c.slice(6, 8)}${p ? ` (loading, to F+${p[0]})` : ""}`; };
  // 10-31 6:08 PM (Benjamin "Go for it on the eps 3 hourly"): the group label says how often a model's maps come (manifest note, else here)
  const RUN_NOTE = { eps: "3-hourly to F+144, then 6-hourly" }, runNote = m => S.man.models[m].note || RUN_NOTE[m] || "";
  // 11-03 (Benjamin t2228u "Put these products under the waves tab"): the picker lists only the runs that belong to the open tab (runInTab)
  const runMenu = (ord0, al0) => { S._runs = [ord0, al0]; const al = al0.filter(r => r === S.run || runInTab(r, S.tab)), ord = ord0.filter(m => al.some(r => r.startsWith(m + "/")));
    $("run").innerHTML = ord.map(m => `<optgroup label="${S.man.models[m].site}${runNote(m) ? ` \u00b7 ${runNote(m)}` : ""}">` +
    al.filter(r => r.startsWith(m + "/")).map(r => `<option value="${r}"${r === S.run ? " selected" : ""}>${runLabel(r)}</option>`).join("") + "</optgroup>").join(""); };
  runMenu(order, all); S.runMenu = () => S._runs && runMenu(...S._runs);
  // 10-31 frame at a time: every 2 min re-read the manifest so a run that just started shows up in the Runs menu without a reload
  setInterval(async () => {
    if (document.hidden) return; let M2; try { M2 = await (await fetch(DATA + "manifest.json", { cache: "no-cache" })).json(); } catch (e) { return; }
    mergeRunsX(pvMerge(M2)); if (JSON.stringify([M2.runs, M2.progress]) === JSON.stringify([S.man.runs, S.man.progress])) return;
    S.man.runs = M2.runs; S.man.progress = M2.progress; S.man.mgruns = M2.mgruns;
    const o2 = order.filter(m => (S.man.runs[m] || []).length), a2 = []; for (const m of o2) for (const c of [...S.man.runs[m]].reverse()) a2.push(`${m}/${c}`);
    if (!a2.includes(S.run)) a2.push(S.run);
    runMenu(o2, a2); loadNote();
  }, 120e3);
  setLists();
  if (vKeep != null && !S.runs[S.run].steps.some(x => Math.abs(Date.parse(x.valid) - vKeep) <= 3 * 3600e3)) vKeep = null;
  const f0 = vKeep != null ? null : Q.get("f"), steps = S.runs[S.run].steps; S.i = f0 ? Math.max(0, steps.findIndex(s => s.f == +f0)) : S.run.startsWith("oisst/") ? steps.length - 1 : 0;   // 11-03: daily analyses open on the newest day
  const vq = vKeep != null ? vKeep : Date.parse(Q.get("valid") || ""); if (!f0 && vq) { let b = 0; steps.forEach((x, k) => { if (Math.abs(Date.parse(x.valid) - vq) < Math.abs(Date.parse(steps[b].valid) - vq)) b = k; }); S.i = b; }   // old-site links
  $("step").value = S.i;
  $("run").onchange = async e => {   // keep the same valid time when switching runs/models (nearest step)
    const vt = Date.parse(S.runs[S.run].steps[S.i].valid); S.run = e.target.value; await loadRun(S.run); setLists();
    const st = S.runs[S.run].steps; let b = 0; st.forEach((x, k) => { if (Math.abs(Date.parse(x.valid) - vt) < Math.abs(Date.parse(st[b].valid) - vt)) b = k; });
    S.i = b; $("step").value = b; memUI(); draw(); loadNote(); };
  memUI();
  // phones: hour slider under the map (Benjamin 10-29 9:01 PM)
  const mq = matchMedia("(max-width: 700px), (max-height: 500px)"), placeSteps = () => {
    const ph = mq.matches; document.body.classList.toggle("phone", ph);
    const c = $("stepctl"), dest = ph ? $("dock") : $("bar"); if (c.parentNode !== dest) { if (ph) dest.appendChild(c); else dest.insertBefore(c, $("save")); }
    fitPhone();
  };
  placeSteps(); addEventListener("resize", fitPhone); window.visualViewport && visualViewport.addEventListener("resize", fitPhone); (mq.addEventListener ? mq.addEventListener("change", placeSteps) : mq.addListener(placeSteps));
  setupPointer(); $("share") && ($("share").onclick = share); $("save") && ($("save").onclick = saveImage);
  $("obsbtn") && ($("obsbtn").onclick = obsOpen);
  $("mgbtn") && ($("mgbtn").onclick = () => mgOpen("town")); $("pfbtn") && ($("pfbtn").onclick = () => mgOpen("pass"));
  $("prod").onchange = e => { S.prod = e.target.value; S.lastTab[S.tab || tabOf(S.prod)] = S.prod; draw(); };
  $("view").onchange = e => { S.view = e.target.value; resetZoom(); draw(); };
  const sl = $("step"), endDrag = () => { if (S.dragging) { S.dragging = false; draw(); } };
  sl.addEventListener("pointerdown", () => { S.dragging = true; });
  sl.addEventListener("touchstart", () => { S.dragging = true; }, { passive: true });
  for (const ev of ["pointerup", "pointercancel", "touchend", "touchcancel", "change"]) sl.addEventListener(ev, endDrag);
  sl.oninput = e => { const v = +e.target.value; if (v === S.i) return; S.i = v; draw(); };
  $("prev").onclick = () => go(-1); $("next").onclick = () => go(1);
  $("play").onclick = () => { if (S.timer) { clearInterval(S.timer); S.timer = null; $("play").textContent = "Play"; }
                              else { S.timer = setInterval(() => go(1, true), 250); $("play").textContent = "Stop"; } };
  addEventListener("keydown", e => { if (e.key === "Escape") mgClose(); if (MG.open) return; if (e.key === "ArrowRight") go(1); if (e.key === "ArrowLeft") go(-1); });
  await draw(); loadNote(); setInterval(refreshPartial, 60e3);
  // ?mg= / ?obs= open the panel once (meteograms page "Pass Forecaster" tab links to ./?mg=pass) and are then dropped from the
  // address: they used to stay in it after Close, so every reload / iOS tab restore / shared link reopened Pass Forecaster
  // ("the website glitches into pass mode every so often", Benjamin 10-31 2:01 AM).
  // 11-04 (t2269u): an Observations / meteogram window that was open stays open after a refresh (this tab only)
  let ssw = {}; try { ssw = { obs: sessionStorage.getItem("vw:obs"), mg: sessionStorage.getItem("vw:mg") }; } catch (e) { /* private mode */ }
  if (Q.get("obs") || (!Q.get("studio") && !Q.get("embed") && ssw.obs)) obsOpen();
  if (Q.get("mg")) mgOpen(Q.get("mg") === "pass" ? "pass" : "town"); else if (!Q.get("studio") && !Q.get("embed") && ssw.mg) mgOpen(ssw.mg === "pass" ? "pass" : "town");
  if (Q.has("mg") || Q.has("obs")) { const u = new URL(location); u.searchParams.delete("mg"); u.searchParams.delete("obs"); try { history.replaceState(null, "", u); } catch (e) {} }
  window.__ready = true;
  if (Q.get("bench")) bench();
}
// 10-31 (Benjamin: "make it so the first forecast hours show for a new run in every model"): runs go live after their first few
// hours; while one is still coming in (run.json complete = false) a note by the slider says so and new hours are added in place.
function loadNote() {
  const el = $("loadnote"), R_ = S.runs[S.run]; if (!el || !R_) return;
  const on = R_.complete === false, last = R_.steps.length ? R_.steps[R_.steps.length - 1].f : 0;
  el.classList.toggle("on", on);
  const [m, c] = S.run.split("/"), p = ((S.man.progress || {})[m] || {})[c];
  if (on && document.body.classList.contains("phone")) el.textContent = `Loading F+${last}${p && p[1] ? `/${p[1]}` : ""}`; else
  el.textContent = on ? `Run still coming in: F+${last}${p && p[1] ? ` of F+${p[1]}` : ""} so far${!(p && p[1]) && R_.expected ? ` (${R_.steps.length} of ${R_.expected} maps)` : ""}` : "";
  if (!on && p) {   // finished while open: drop "(loading ...)" from the Runs menu
    delete S.man.progress[m][c]; const o = [...$("run").options].find(x => x.value === S.run); if (o) o.textContent = o.textContent.replace(/ \(loading[^)]*\)$/, "");
  } else if (on) { const o = [...$("run").options].find(x => x.value === S.run); if (o) o.textContent = o.textContent.replace(/ \(loading[^)]*\)$/, "") + ` (loading, to F+${last})`; }
}
async function refreshPartial() {
  const r = S.run, R_ = S.runs[r]; if (!R_ || R_.complete !== false || document.hidden) return;
  let N; try { N = await (await fetch(`${DATA}runs/${r}/${runFile(r)}`, { cache: "no-cache" })).json(); } catch (e) { return; }
  if (S.run !== r || !N || !N.steps || N.steps.length < R_.steps.length) return;
  const newF = N.fields.join() !== R_.fields.join();
  S.runs[r] = prepRun(N); if (newF) setLists(); $("step").max = N.steps.length - 1; $("step").value = S.i; loadNote();
}
// Side-by-side viewer (10-31, Benjamin: "a side by side viewer"): compare.html shows two of these pages in frames (?embed=compare&id=L|R).
// Each frame tells the page what it shows after every draw; the page sends "set" to the other frame when sync is on.
let cmpEcho = false;
const cslimH = () => { const m = $("map"), b = $("bar"), bot = (e) => e ? e.getBoundingClientRect().bottom + scrollY : 0;   // content height for the slim compare frame
  return Math.ceil(Math.max(bot(m), document.body.classList.contains("cshow") ? bot(b) : 0)) + 2; };
function postCompare(run, pid, vid, step) {
  if (!Q.get("embed") || parent === window) return;
  parent.postMessage({ wx: "state", id: Q.get("id"), run, prod: pid, tab: S.tab, view: vid, f: step.f, valid: step.valid, echo: cmpEcho,
    i: S.i, n: S.runs[run].steps.length, vline: step.valid_line || "", h: cslimH() }, "*");   // i / n / vline: shared hour slider; h: frame height (slim phone layout)
  cmpEcho = false;
}
const cmpMenusShown = () => document.body.classList.contains("cslim") ? document.body.classList.contains("cshow") : !document.body.classList.contains("cmin");
function cmpMenus(show, save, btn) {   // compare frames: show / hide this frame's menus (11-01 t2021u)
  const b = btn || $("cgear"); if (!b) return; const B = document.body;
  if (B.classList.contains("cslim")) B.classList.toggle("cshow", show); else B.classList.toggle("cmin", !show);
  b.textContent = show ? "Hide menus" : "Menus"; b.classList.toggle("on", show); b.setAttribute("aria-expanded", String(show));
  if (show) $("bar").prepend(b); else B.appendChild(b);
  if (save) try { localStorage.setItem("cmpMenus_" + Q.get("id"), show ? "1" : "0"); } catch (e) { /* private mode */ }
  fitPhone(); setTimeout(() => { cmpBox(); S.cur && postCompare(S.cur.run, S.cur.pid, S.view, S.runs[S.run].steps[S.i]); }, 50);
}
// 11-01 (t2021u: "Make sure the compare window is the same size as the first window"): each desktop frame reports the room its map has;
// the compare page sends back the smaller of the two, and both maps are capped to it, so the two maps always show at the same size
let CMPBOX = null, cmpBoxLast = "";
function cmpBox() {
  if (!Q.get("embed") || parent === window || document.body.classList.contains("cslim")) return;
  const wr = $("wrap"), cs = getComputedStyle(wr), w = Math.floor(wr.clientWidth - parseFloat(cs.paddingLeft) - parseFloat(cs.paddingRight)),
    h = Math.floor(wr.clientHeight - parseFloat(cs.paddingTop) - parseFloat(cs.paddingBottom)), k = w + "x" + h;
  if (k === cmpBoxLast) return; cmpBoxLast = k; parent.postMessage({ wx: "box", id: Q.get("id"), w, h }, "*");
}
async function onCompareMsg(e) {
  const d0 = e.data; if (d0 && e.source === parent && d0.wx === "menus") { cmpMenus(!!d0.show, true); return; }
  if (d0 && e.source === parent && d0.wx === "box") { CMPBOX = d0.w > 0 && d0.h > 0 ? { w: d0.w, h: d0.h } : null; fitPhone(); return; }
  const d = e.data; if (!d || d.wx !== "set" || e.source !== parent) return;
  if (d.run && d.run !== S.run) { try { await loadRun(d.run); S.run = d.run; $("run").value = d.run; } catch (err) { return; } }
  const P = PRODS(), has = new Set(S.runs[S.run].fields);
  if (d.prod && P[d.prod] && P[d.prod].fields.every(x => has.has(x))) { S.prod = d.prod; S.tab = null; }
  if (d.view && VIEWS()[d.view]) S.view = d.view;
  setLists();
  const lead = typeof d.i === "number";   // shared slider (compare page): this frame leads, so its new state is passed on to the other map
  if (lead) { S.i = Math.max(0, Math.min(S.runs[S.run].steps.length - 1, d.i)); $("step").value = S.i; d.valid = null; }
  if (d.valid) { const st = S.runs[S.run].steps, vt = Date.parse(d.valid); let b = 0;
    st.forEach((x, k) => { if (Math.abs(Date.parse(x.valid) - vt) < Math.abs(Date.parse(st[b].valid) - vt)) b = k; }); S.i = b; $("step").value = b; }
  cmpEcho = !lead; draw(); loadNote();
}
async function loadRun(r) { if (!S.runs[r]) S.runs[r] = prepRun(await (await fetch(`${DATA}runs/${r}/${runFile(r)}`, { cache: "no-cache" })).json()); return S.runs[r]; }
const SV = () => (S.man.static_v ? `?v=${S.man.static_v}` : "");   // cache-buster for static layers (they are cached 1 day)
const MD = () => S.man.models[S.run.split("/")[0]];
// Severe tab (10-31): new products are published under the manifest's products_x (production's older viewer only reads "products")
// 11-01 (Benjamin 7:30 AM "max wave height scale ... at least 60'"): changed product scales are published under the manifest's
// products_p (new key file names), read over products/products_x; production's older viewer keeps the old scale until this ships
// 11-01 neon example (branch wave_scale_neon): products_n (neon max wave keys/colors) read over products_p; only this build reads it
// 11-01 8:53 AM (Benjamin t1992u, 5 ft numbers 40-85 on the max wave scale): products_t (same colors, keys _85t, ticks every 5 ft 40-85) over products_n
// 11-01 9:15 AM (Benjamin t1993u, bright blue-violet between hot pink and neon cyan): products_v (75-80 split at 77.5, keys _85v) over products_t
// 11-02 (Benjamin t2103u): MSLP anomaly negative end 50 mb deeper, -30..+30 -> -80..+30 mb (2 mb bins; -30..+30 colors unchanged; below -30
// gray-lavender > lavender > purple > deep violet > near-black violet, under #12021a). Code-side over the manifest's products_x (no R2/manifest
// change); keys "@mkeys/static/key_<m>_mslpa_a80_<view>.png" ship with the site ("@" = site-relative, not DATA). Made by fast_encode.py (keyver _a80).
const MSLPA_A80 = {"levels":[-80.0,-78.0,-76.0,-74.0,-72.0,-70.0,-68.0,-66.0,-64.0,-62.0,-60.0,-58.0,-56.0,-54.0,-52.0,-50.0,-48.0,-46.0,-44.0,-42.0,-40.0,-38.0,-36.0,-34.0,-32.0,-30.0,-28.0,-26.0,-24.0,-22.0,-20.0,-18.0,-16.0,-14.0,-12.0,-10.0,-8.0,-6.0,-4.0,-2.0,0.0,2.0,4.0,6.0,8.0,10.0,12.0,14.0,16.0,18.0,20.0,22.0,24.0,26.0,28.0,30.0],"colors":["#260636","#2f0844","#370a52","#3f0c5f","#480e6d","#51127a","#5a1888","#641f94","#6d25a2","#772dac","#8138b6","#8b42be","#954dc8","#9d59ce","#a467d0","#ab75d4","#b283d6","#b58ed5","#b495d0","#b49dca","#b3a4c5","#b7aec5","#c0b9ca","#c9c5d0","#d2d0d5","#d6d6d8","#bcbcc0","#9e9fa4","#8f9095","#236630","#32803c","#4c9b4a","#74b866","#9fd089","#b5dc9c","#5f4bb0","#3e43ba","#366cd4","#72a7e8","#f7f7f5","#f7f7f5","#fcee9e","#fbdd62","#f6c23b","#f29f36","#ec7630","#e24e2c","#d12c2c","#b91733","#c31a5f","#d22d84","#dc57a6","#d97fbe","#cc9bcd","#c3aed8"],"ticks":[-80.0,-70.0,-60.0,-50.0,-40.0,-30.0,-20.0,-10.0,0.0,10.0,20.0,30.0],"under":"#12021a"};
// 11-03 (Benjamin t2245u: "increase the precipitation total key to 18 inches, adjust the color scale accordingly"): run-total precip
// (qpf, eqpf90, NBM nqpftot; every model) 0.01-18 in. Bins and colors to 7 in unchanged; 0.5 in bins 4-18; 7+ deep violet > indigo > blue >
// cyan > ice, 18+ white. Viewer-side over the manifest (data unchanged: precip fields are stored to each frame's own max, nothing clipped);
// keys "@mkeys/static/key_<m>_<pid>_q18_<view>.png" ship with the site. Made by fast_encode.py (house_style.QPF18_*, keyver _q18).
const QPF_Q18 = {"levels": [0.01, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0, 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 1.8, 1.9, 2.0, 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 2.8, 2.9, 3.0, 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8, 3.9, 4.0, 4.5, 5.0, 5.5, 6.0, 6.5, 7.0, 7.5, 8.0, 8.5, 9.0, 9.5, 10.0, 10.5, 11.0, 11.5, 12.0, 12.5, 13.0, 13.5, 14.0, 14.5, 15.0, 15.5, 16.0, 16.5, 17.0, 17.5, 18.0], "colors": ["#d7f5cd", "#b4e8a5", "#9bdc8a", "#82d06e", "#66c15e", "#4bb24e", "#379e42", "#238a37", "#197430", "#0f5f2a", "#faf096", "#faea72", "#fae44e", "#fadc3a", "#fad236", "#fac832", "#fabe30", "#fab42e", "#faab2c", "#f8a32c", "#f89b2a", "#f6932a", "#f68b28", "#f48428", "#f27c26", "#f07626", "#ee6e24", "#ec6724", "#e85a24", "#e24626", "#dc3228", "#d22b26", "#c82525", "#be1e23", "#b21a23", "#a71623", "#9b1223", "#8f0f25", "#840d26", "#780a28", "#e141af", "#cf3cb6", "#bc37bc", "#aa32c3", "#962fb7", "#822bac", "#6e28a0", "#622aa5", "#572baa", "#4b2daf", "#4139b7", "#3744c0", "#2d50c8", "#2a5fcd", "#266ed2", "#237dd7", "#258cda", "#269bde", "#28aae1", "#35b6e3", "#43c1e4", "#50cde6", "#67d5e9", "#7fdced", "#96e4f0", "#ace9f3", "#c1eff7", "#d7f4fa"], "ticks": [0.1, 0.5, 1.0, 2.0, 3.0, 4.0, 6.0, 8.0, 10.0, 12.0, 15.0, 18.0], "over": "#ffffff"};
const ISO_MSLP = { every: 2, lw: 0.75, halo: 1.6 };
const allProds = md => md._allP || (md._allP = (() => {
  const A = Object.assign({}, md.products, md.products_x || {}, md.products_p || {}, md.products_n || {}, md.products_t || {}, md.products_v || {});
  if (A.mslpa && A.mslpa.levels && A.mslpa.levels[0] > -80) A.mslpa = Object.assign({}, A.mslpa, MSLPA_A80,
    { keys: Object.fromEntries(Object.entries(A.mslpa.keys || {}).map(([v, k]) => [v, "@mkeys/" + k.replace("_mslpa_", "_mslpa_a80_")])) });
  for (const pid of ["qpf", "eqpf90", "nqpftot"]) { const P = A[pid]; if (P && P.levels && P.levels[P.levels.length - 1] < 18)
    A[pid] = Object.assign({}, P, QPF_Q18, { keys: Object.fromEntries(Object.entries(P.keys || {}).map(([v, k]) => [v, "@mkeys/" + k.replace(`_${pid}_`, `_${pid}_q18_`)])) }); }
  // 11-04 (Benjamin t2279u "added to the high end of shorter interval like 24 hour precipitation key"): interval precip keys (1 / 3 / 6 / 12 /
  // 24 / 48 h, MSLP + precip; 0.01-12 in) get numbers up to 12 (4 6 8 10 12 after their own top tick); a label that would touch is skipped
  for (const [k, P] of Object.entries(A)) if (P && Array.isArray(P.levels) && Array.isArray(P.ticks) && P.levels[0] === 0.01 && P.levels[P.levels.length - 1] === 12 && /precip \(in\)/i.test(P.key || "")) {
    const mx = Math.max(...P.ticks); if (mx < 12) A[k] = Object.assign({}, P, { ticks: [...P.ticks, ...[4, 6, 8, 10, 12].filter((t) => t > mx)] }); }
  // 11-03 (Benjamin: "thin isobar lines WITH every 2 mb spacing", mock /workspace/isobar_mock 2_denser + 3_thinner): every MSLP isobar
  // layer (all models, viewer + Studio + compare) draws every 2 mb at 0.75 pt with a 1.6 pt halo; smoothing (sigma) unchanged.
  // Copies only: the manifest's own product objects are not touched (an R2 manifest edit is not needed for this).
  for (const [k, P] of Object.entries(A)) if (P && P.isobars && (P.isobars.field || "mslp") === "mslp")
    A[k] = Object.assign({}, P, { isobars: Object.assign({}, P.isobars, ISO_MSLP), extra: typeof P.extra === "string" ? P.extra.replace(/isobars every 4 mb/g, "isobars every 2 mb") : P.extra });
  return A; })());
const PRODS = () => allProds(MD()), VIEWS = () => MD().views;
// Product tabs (Benjamin 10-30 8:04 PM: "upper air tab, surface tab, precipitation tab, snow tab", Pivotal Weather style).
// The Product menu lists only the open tab's products, in the order below (Pivotal: winds by level, 250 -> 850 mb);
// product ids / URLs are unchanged (?prod= picks its tab). Products not listed here land in an "Other" tab.
const TABS = [
  ["sfc", "Surface", ["t2m", "feels", "d2m", "t2ma", "nmaxt", "nmint", "ehigh", "elow", "et2sd", "ep32", "gust10", "gust6", "gust12", "gust24", "gustmax", "egust90",
                      "aifswind", "slp", "elows", "tcc", "vis", "fog", "ir"]],
  ["pcp", "Precip", ["qpf", "qpf1", "nqpf1", "qpf3", "qpf6", "nqpf6", "qpf12", "qpf24", "qpf48", "nqpf12", "nqpf24", "nqpf48", "nqpftot", "eqpf90", "mslpqpf", "ptype", "refc", "pw", "pwa", "ivt",
                     "qpfa", "qpfpct"]],
  ["snow", "Snow", ["snow", "kuchera", "esnow", "esnow90", "snow1", "snow6", "snow12", "snow24", "snow48", "nsnow6", "nsnow12", "nsnow24", "nsnow48", "nsnowtot", "esnow6", "esnow12", "esnow24", "esnow48", "kuch6", "kuch12", "kuch24", "kuch48", "dsnod", "fzra", "fzra6", "fzra12", "fzra24", "fzra48", "snowlvl", "frz", "thick"]],
  ["ua", "Upper Air", ["w250", "w300", "w500", "w850", "t300w", "t500w", "t700w", "t850w", "t925w", "t850", "t700", "t850a", "z500anom", "ez500", "spag"]],
  // 10-31 (Benjamin 9:15 AM): simulated radar (also listed under Precip), radar + UH, UH, UH streaks, CAPEs, SRH, lapse rates
  ["svr", "Severe", ["refc", "refuh", "uh", "uhs", "sbcape", "mucape", "cape3", "srh03", "lr03", "lr75", "epcape", "ltng", "ltng6", "ltgp", "ntstm"]],
  // 11-01 (Benjamin 2:02 AM "We should probably make a waves tab"): ECMWF 0.25 wave products, out of Surface.
  // ECMWF (ifs) only: on other models the tab still shows (dimmed) and opens the newest ECMWF run.
  ["wav", "Waves", ["waves", "swper", "swellhs", "wavemax", "wavemax24", "ssta"]],   // 11-03: + NOAA OISST SST anomaly   // 11-03: NOAA WW3 swell period, wave height + swell period
];
const tabOf = pid => (TABS.find(t => t[2].includes(pid)) || ["other"])[0];
// 11-03 (Benjamin t2228u "Put these products under the waves tab"): NOAA WW3 and NOAA OISST (ocean-only models) live under the Waves tab.
// Runs picker: on the Waves tab only models with wave products (ECMWF 0.25, NOAA WW3, NOAA OISST); on every other tab the weather models
// (no WW3 / OISST). The shown run is always listed, so old ?model=gfsw / ?model=oisst / ?run= links still open. Compare frames: unchanged.
const OCEAN = ["gfsw", "oisst"], WAVE_TAB = TABS.find(t => t[0] === "wav")[2];
const hasWaves = m => { const P = allProds(S.man.models[m] || {}); return WAVE_TAB.some(k => P[k]); };
const runInTab = (r, tab) => { const m = r.split("/")[0]; if (Q.get("embed")) return true; return tab === "wav" ? hasWaves(m) : !OCEAN.includes(m); };
S.lastTab = {};
function setLists() {   // products this run carries (all their fields present), views this model has
  const R_ = S.runs[S.run], has = new Set(R_.fields), P = PRODS(), V = VIEWS();
  const prods = Object.entries(P).filter(([k, p]) => p.fields.every(f => has.has(f)));
  const tabs = [...TABS, ["other", "Other", []]].map(([id, label, ids]) => [id, label,
    prods.filter(([k]) => id === "other" ? tabOf(k) === "other" : ids.includes(k)).sort((a, b) => ids.indexOf(a[0]) - ids.indexOf(b[0]))]).filter(t => t[2].length);
  if (!prods.some(([k]) => k === S.prod)) {   // not in this run: stay in the same tab when it can
    const t = tabs.find(t => t[0] === (S.tab || tabOf(S.prod))) || tabs.find(t => t[0] === tabOf(S.prod)); S.prod = (t ? t[2][0] : prods[0])[0]; }
  const inTab = id => tabs.some(t => t[0] === id && t[2].some(([k]) => k === S.prod));
  const cur = S.tab && inTab(S.tab) ? S.tab : tabOf(S.prod); S.tab = cur; S.lastTab[cur] = S.prod;
  $("tabs").innerHTML =
    // 11-03 (t2228u): on a NOAA WW3 / OISST run the weather tabs show dimmed (same order as usual, before Waves) and open the newest ECMWF run on that tab
    (Q.get("embed") || !OCEAN.includes(S.run.split("/")[0]) || !(S.man.runs.ifs || []).length ? "" :
      TABS.filter(t => t[0] !== "wav" && !tabs.some(x => x[0] === t[0])).map(([id, label]) => `<button type="button" data-t="${id}" data-wx="1" class="dim" title="${label}: opens the newest ECMWF run">${label}</button>`).join("")) +
    tabs.map(([id, label]) => `<button type="button" role="tab" data-t="${id}" aria-selected="${id === cur}"${id === cur ? ' class="on"' : ""}>${label}</button>`).join("") +
    (Q.get("embed") || tabs.some(t => t[0] === "wav") || !(S.man.runs.ifs || []).length ? "" :
      `<button type="button" data-t="wav" class="dim" title="Waves: ECMWF, NOAA WW3 and NOAA OISST. Opens the newest ECMWF run">Waves</button>`) +
    // WA Maps (10-31, Benjamin 8:58 AM): the posted Washington state-view maps, own page (wamaps.html)
    (Q.get("embed") || Q.get("studio") ? "" : `<button type="button" data-t="wamaps" title="Washington state-view forecast maps">WA Maps</button>` +
      `<button type="button" data-t="compare" title="Two maps side by side: two models, or two runs of one model">Compare</button>` +
      `<button type="button" data-t="studio" title="Studio: 9:16 and 16:9 video frames for Reels / OBS">Studio</button>` +
      `<button type="button" data-t="social" title="Social: ECMWF 4K graphics (9:16 and 16:9) to browse and save">Social</button>`);
  $("tabs").onclick = e => { const b = e.target.closest("button[data-t]"); if (b && b.dataset.t === "wamaps") { location.href = "wamaps.html"; return; }
    if (b && b.dataset.t === "social") { location.href = "social.html"; return; }
    if (b && b.dataset.t === "studio") { location.href = `studio.html?run=${encodeURIComponent(S.run)}&prod=${S.prod}&view=${S.view}&f=${S.runs[S.run].steps[S.i].f}`; return; }
    if (b && b.dataset.t === "compare") { const R_ = S.runs[S.run], st = R_.steps[S.i], [m] = S.run.split("/"), rs = (S.man.runs[m] || []);
      const other = rs.length > 1 ? `${m}/${rs[rs.length - 1] === S.run.split("/")[1] ? rs[rs.length - 2] : rs[rs.length - 1]}` : S.run;
      location.href = `compare.html?l=${encodeURIComponent(S.run)}&r=${encodeURIComponent(other)}&prod=${S.prod}&view=${S.view}&valid=${encodeURIComponent(st.valid)}`; return; }
    if (b && b.dataset.t === "wav" && !tabs.some(x => x[0] === "wav")) {   // waves: ECMWF (or NOAA WW3) only -> newest ECMWF run, same valid time
      const rs = S.man.runs.ifs || []; if (!rs.length) return; S.prod = "waves"; S.tab = "wav"; $("run").value = `ifs/${rs[rs.length - 1]}`; $("run").onchange({ target: $("run") }); return; }
    if (b && b.dataset.wx) {   // weather tab from a WW3 / OISST run -> newest ECMWF run, same valid time
      const rs = S.man.runs.ifs || [], id = b.dataset.t; if (!rs.length) return; S.tab = id; S.prod = S.lastTab[id] || TABS.find(t => t[0] === id)[2][0];
      $("run").onchange({ target: { value: `ifs/${rs[rs.length - 1]}` } }); return; }
    if (!b || b.dataset.t === S.tab) return;
    const t = tabs.find(x => x[0] === b.dataset.t), keep = S.lastTab[t[0]];
    S.tab = t[0]; S.prod = t[2].some(([k]) => k === keep) ? keep : t[2][0][0]; setLists(); draw(); };
  if (!V[S.view]) S.view = V.wa ? "wa" : Object.keys(V)[0];
  const wavy = WAVE_PIDS.test(S.prod); if (V[S.view].waveOnly && !wavy) S.view = V.pnw ? "pnw" : "wa";
  fill($("prod"), tabs.find(t => t[0] === cur)[2].map(([k, p]) => [k, p.title]), S.prod);
  fill($("view"), Object.entries(V).filter(([k, v]) => !v.waveOnly || wavy).map(([k, v]) => [k, v.label]), S.view);
  $("step").max = R_.steps.length - 1; S.i = Math.min(S.i, R_.steps.length - 1);
  S.runMenu && S.runMenu();   // 11-03 (t2228u): Runs picker follows the open tab
}
function fill(sel, opts, cur) { sel.innerHTML = opts.map(([v, t]) => `<option value="${v}"${v === cur ? " selected" : ""}>${t}</option>`).join(""); }
function go(d, wrap) { const n = S.runs[S.run].steps.length; S.i = wrap ? (S.i + d + n) % n : Math.min(n - 1, Math.max(0, S.i + d)); $("step").value = S.i; draw(); }

// ---------------------------------------------------------------- static per view
async function viewStatic(vid) {
  // 11-04 t2314u: HRRR / RRFS / NBM wide view = pnwhr files, but its own (smaller-label) towns layer ("townsOwn", wawide_small_towns_lcc.py)
  const V0 = VIEWS()[vid] || {}, own = V0.townsOwn ? vid : null;
  vid = VSRC(vid); const m = S.run.split("/")[0], sk = m + "/" + vid + (own ? "~" + own : "");
  if (S.statics[sk]) return S.statics[sk];
  const V = VIEWS()[vid];
  const p = (async () => {
    const [lut, base] = await Promise.all([fetch(DATA + V.lut + SV()).then(r => r.arrayBuffer()).then(b => new Float32Array(b)),
                                           img(DATA + (V.base_png || `static/base_${vid}.png`) + SV())]);
    // towns layer is not needed for the first paint: draw without it, redraw when it lands (10-29 first-map speedup)
    const tP = (own ? V0.towns_png : V.towns_png) || `static/towns_${vid}.png`, tU = (tP[0] === "@" ? tP.slice(1) : DATA + tP) + SV();
    const townsP = img(tU).then(im => { obj.towns = im; if (VSRC(S.view) === vid && window.__drawn) draw(); return im; }, () => null);
    // per-pixel source index + weights, made once per view from the coarse LUT (bilinear in panel px)
    const [px, py, pw, ph] = V.panel, x0 = Math.round(px), y0 = Math.round(py), W = Math.round(px + pw) - x0, H = Math.round(py + ph) - y0;
    const { nx, ny, stride } = V, G = S.runs[S.run].grid, gnx = G.nx, gny = G.ny;
    const idx = new Int32Array(W * H), wx = new Float32Array(W * H), wy = new Float32Array(W * H);
    for (let y = 0; y < H; y++) {
      const gy = (y + 0.5) / stride, j0 = Math.min(ny - 2, gy | 0), ty = gy - j0;
      for (let x = 0; x < W; x++) {
        const gx = (x + 0.5) / stride, i0 = Math.min(nx - 2, gx | 0), tx = gx - i0;
        const a = (j0 * nx + i0) * 3, b = a + 3, c = a + nx * 3, d = c + 3;
        const fi = (lut[a] * (1 - tx) + lut[b] * tx) * (1 - ty) + (lut[c] * (1 - tx) + lut[d] * tx) * ty;
        const fj = (lut[a + 1] * (1 - tx) + lut[b + 1] * tx) * (1 - ty) + (lut[c + 1] * (1 - tx) + lut[d + 1] * tx) * ty;
        const k = y * W + x;
        // HRRR rows run south -> north; grid index fi = row, fj = column
        if (!(fi >= 0 && fj >= 0 && fi <= gny - 1 && fj <= gnx - 1)) { idx[k] = -1; continue; }
        const r0 = Math.min(gny - 2, fi | 0), c0 = Math.min(gnx - 2, fj | 0);
        idx[k] = r0 * gnx + c0; wy[k] = fi - r0; wx[k] = fj - c0;
      }
    }
    const obj = { lut, base, towns: null, townsP, x0, y0, W, H, idx, wx, wy, gnx, baseU: DATA + (V.base_png || `static/base_${vid}.png`) + SV(), townsU: tU }; return obj;
  })();
  S.statics[sk] = p; return p;
}
const keyImg = {}; const keyURL = (pid, vid) => { const K = PRODS()[pid].keys, V = VIEWS()[vid] || {}; const k = (V.keys && V.keys[pid]) || K[VSRC(vid)] || K[V.keysFrom] || K.wa; return (k[0] === "@" ? k.slice(1) : DATA + k) + SV(); };   // Studio-only view: Washington key
const getKey = (pid, vid) => { const u = keyURL(pid, vid); return keyImg[u] || (keyImg[u] = img(u)); };

// ---------------------------------------------------------------- data images
function fieldURL(run, name, f) {   // packed runs: several fields share one RGB PNG, one channel each (run.json steps[].packs)
  const R_ = S.runs[run], st = R_.steps.find(s => s.f === f), pk = st && st.packs && st.packs[name];
  const file = pk ? pk[0] : name, ch = pk ? pk[1] : 0, tile = (pk && pk[2]) || 0;   // 11-03 EPS members: packs [file, channel, tile] (tiles stacked top to bottom)
  return [`${DATA}${R_.base}/` + R_.file.replace("{mem}", memPad()).replace("{name}", file).replace("{f:03d}", String(f).padStart(3, "0")), ch, tile];
}
const pixCache = new Map();
function getPixels(url) {   // one fetch + decode per image, shared by every field packed in it
  if (pixCache.has(url)) return pixCache.get(url);
  const p = (async () => {
    const t0 = performance.now(); const r = await fetch(url); if (!r.ok) throw new Error(`${url}: HTTP ${r.status}`);
    const blob = await r.blob(), t1 = performance.now();
    const bm = await createImageBitmap(blob, { premultiplyAlpha: "none", colorSpaceConversion: "none" });
    const oc = new OffscreenCanvas(bm.width, bm.height), cx = oc.getContext("2d", { willReadFrequently: true });
    cx.drawImage(bm, 0, 0); const px = cx.getImageData(0, 0, bm.width, bm.height).data;
    S.timings.push({ key: url, bytes: blob.size, fetch: t1 - t0, decode: performance.now() - t1 });
    return { px, w: bm.width, h: bm.height, bytes: blob.size };
  })();
  p.catch(() => pixCache.delete(url)); pixCache.set(url, p); return p;
}
function getField(run, name, f) {
  const key = `${rk(run)}/${name}/${f}`;
  if (S.fields.has(key)) return S.fields.get(key);
  const p = (async () => {
    const st = S.runs[run].steps.find(s => s.f === f);
    if (!st || !st.ranges[name]) throw new Error(`nodata:${name}`);
    const [url, ch0, tile] = fieldURL(run, name, f), I0 = await getPixels(url), T = S.runs[run].tiles || 1;
    const I = T > 1 ? { w: I0.w, h: I0.h / T, bytes: I0.bytes } : I0, ch = ch0 + tile * I.w * I.h * 4;   // tile k = rows k*h .. (k+1)*h-1
    const [lo, hi] = st.ranges[name], sc = (hi - lo) / 255, n = I.w * I.h, out = new Float32Array(n), px = I0.px;
    // image row 0 = first (southern) grid row: the encoder writes the grid as-is
    if (st.ranges[name][2] === 2) { const d = hi - lo; for (let k = 0; k < n; k++) { const q = px[k * 4 + ch] / 255; out[k] = lo + q * q * d; } }   // sqrt-coded precip
    else for (let k = 0; k < n; k++) out[k] = lo + px[k * 4 + ch] * sc;
    const G = S.runs[run].grid;
    if (S.runs[run].half && G) return { v: upHalf(out, I.w, I.h, G.nx, G.ny), w: G.nx, h: G.ny, bytes: I.bytes };   // 0.5 deg member files -> the 0.25 deg crop grid
    return { v: out, w: I.w, h: I.h, bytes: I.bytes };
  })();
  p.catch(() => S.fields.delete(key)); S.fields.set(key, p); return p;
}
function memUI() {   // AIFS ENS / EPS members: type or pick 1-50 (or < > / arrow up-down); only that member's files load
  const lab = $("memlab"), inp = $("mem"); if (!lab || !inp) return;
  const on = isMemRun(S.run); lab.hidden = !on; if (!on) return;
  const ms = S.runs[S.run].members || []; inp.min = ms[0] || 1; inp.max = ms[ms.length - 1] || 50;
  if (S.mem > +inp.max || S.mem < +inp.min) S.mem = Math.min(+inp.max, Math.max(+inp.min, S.mem));
  inp.value = S.mem;
  const site = (S.man.models[S.run.split("/")[0]] || {}).site || "Ensemble member"; lab.title = `${site} (${inp.min}-${inp.max}): only this member's maps load. Arrow up / down = next / previous member`;
  if (!inp.dataset.wired) { inp.dataset.wired = 1;
    const set = n => { const lo = +inp.min, hi = +inp.max; n = Math.min(hi, Math.max(lo, n)); inp.value = n; if (n === S.mem) return; S.mem = n; draw(); };
    const go = () => { const v = Math.round(+inp.value); set(isFinite(v) && v ? v : S.mem); };
    const step = d => { const lo = +inp.min, hi = +inp.max; set(S.mem + d > hi ? lo : S.mem + d < lo ? hi : S.mem + d); };   // wraps 50 -> 1
    inp.addEventListener("change", go); inp.addEventListener("keydown", e => { if (e.key === "Enter") go();
      if (e.key === "ArrowUp" || e.key === "ArrowDown") { e.preventDefault(); e.stopPropagation(); step(e.key === "ArrowUp" ? 1 : -1); } });
    const bp = $("memprev"), bn = $("memnext");
    if (bp) bp.addEventListener("click", e => { e.preventDefault(); step(-1); });
    if (bn) bn.addEventListener("click", e => { e.preventDefault(); step(1); });
    addEventListener("keydown", e => { if (!isMemRun(S.run) || e.defaultPrevented || e.altKey || e.ctrlKey || e.metaKey) return;
      if (e.key !== "ArrowUp" && e.key !== "ArrowDown") return; if (/^(INPUT|SELECT|TEXTAREA)$/.test((e.target && e.target.tagName) || "") || (e.target && e.target.isContentEditable)) return;
      if (document.querySelector(".mg-open, dialog[open]")) return; e.preventDefault(); step(e.key === "ArrowUp" ? 1 : -1); }); }
}
function upHalf(a, w, h, W, H) {   // bilinear: point (i, j) of the half grid sits at (2i, 2j) of the full grid
  const o = new Float32Array(W * H);
  for (let y = 0; y < H; y++) { const fy = Math.min(h - 1, y / 2), y0 = Math.floor(fy), y1 = Math.min(h - 1, y0 + 1), ty = fy - y0;
    for (let x = 0; x < W; x++) { const fx = Math.min(w - 1, x / 2), x0 = Math.floor(fx), x1 = Math.min(w - 1, x0 + 1), tx = fx - x0;
      o[y * W + x] = (a[y0 * w + x0] * (1 - tx) + a[y0 * w + x1] * tx) * (1 - ty) + (a[y1 * w + x0] * (1 - tx) + a[y1 * w + x1] * tx) * ty; } }
  return o;
}
function blur(a, w, h, sigma) {               // separable gaussian (scipy gaussian_filter, mode reflect, truncate 4)
  const r = Math.ceil(4 * sigma), k = []; let s = 0;
  for (let i = -r; i <= r; i++) { const v = Math.exp(-i * i / (2 * sigma * sigma)); k.push(v); s += v; }
  for (let i = 0; i < k.length; i++) k[i] /= s;
  const refl = (i, n) => { while (i < 0 || i >= n) i = i < 0 ? -i - 1 : 2 * n - i - 1; return i; };
  const t = new Float32Array(a.length), o = new Float32Array(a.length);
  for (let y = 0; y < h; y++) for (let x = 0; x < w; x++) { let v = 0; for (let i = -r; i <= r; i++) v += k[i + r] * a[y * w + refl(x + i, w)]; t[y * w + x] = v; }
  for (let y = 0; y < h; y++) for (let x = 0; x < w; x++) { let v = 0; for (let i = -r; i <= r; i++) v += k[i + r] * t[refl(y + i, h) * w + x]; o[y * w + x] = v; }
  return o;
}
async function productFields(run, pid, f) {
  const P = allProds(S.man.models[run.split("/")[0]])[pid], key = `${rk(run)}/${pid}/${f}`;
  if (S.derived.has(key)) return S.derived.get(key);
  const p = (async () => {
    const F = {}; for (const n of P.fields) F[n] = await getField(run, n, f);
    for (const n of P.opt || []) { const x = await getField(run, n, f).catch(() => null); if (x) F[n] = x; }   // optional (e.g. 300 mb heights: newer runs only)
    const g = F[P.fields[0]]; const out = { w: g.w, h: g.h, raw: F };
    if (P.fill === "wspd") {   // wind speed from u/v (kt); MSLP + 10 m wind shows mph, upper-level winds kt
      const [un, vn] = P.wind || ["u10", "v10"], u = F[un].v, v = F[vn].v, sp = new Float32Array(u.length), mul = P.spd_mult ?? (2.23694 / 1.94384);
      for (let k = 0; k < u.length; k++) sp[k] = Math.hypot(u[k], v[k]) * mul;
      out.fill = blur(sp, g.w, g.h, P.spd_sigma ?? 1.0);
    } else if (P.anom === "pr") {   // precip since the run started vs the 1991-2020 normal for the same days (mm/day normals)
      const R_ = S.runs[run], t0 = Date.parse(R_.init), hrs = f, a = F.apcp.v, o = new Float32Array(a.length), N = new Float32Array(a.length);
      if (P.fill === "ppct" && f < 48) throw new Error("nodata:apcp");
      const ns = Math.max(1, Math.min(6, Math.round(hrs / 48))), Cs = await Promise.all(Array.from({ length: ns }, (_, i) =>
        climAt(run, "pr", new Date(t0 + (i + 0.5) / ns * hrs * 36e5).toISOString())));
      for (const C of Cs) for (let k = 0; k < a.length; k++) N[k] += C[k] / ns * hrs / 24 / 25.4;   // normal (in) for the period
      if (P.fill === "ppct") for (let k = 0; k < a.length; k++) o[k] = a[k] / Math.max(N[k], 0.05) * 100;   // normal floored at 0.05 in (very dry spots)
      else for (let k = 0; k < a.length; k++) o[k] = a[k] - N[k];
      out.fill = o;
    } else if (P.clim) {   // anomaly: field minus the 1991-2020 normal at the valid time (static climatology, see climAt)
      const fld = P.anom || "z500", C = await climAt(run, P.clim, S.runs[run].steps.find(x => x.f === f).valid), z = F[fld].v, o = new Float32Array(z.length);
      for (let k = 0; k < z.length; k++) o[k] = z[k] - C[k]; out.fill = fld === "z500" ? blur(o, g.w, g.h, 1.0) : o;
    } else if (P.window && (P.wmax || P.wsum || P.wmin)) {   // highest value over the steps in the last N hours (incl. this one)
      const fld = P.wfield || P.fields[0], fs = S.runs[run].steps.map(x => x.f).filter(x => x > f - P.window && x <= f && (!P.wstep || (f - x) % P.wstep === 0));
      if (f - P.window < 0 && !P.sofar) throw new Error(`nodata:${fld}`);
      if (P.wstep && f % P.wstep) throw new Error(`nodata:${fld}`);   // NBM sums of 6 h amounts: only at 6-hourly valid times
      const arrs = await Promise.all(fs.map(x => getField(run, fld, x).then(r => r.v, () => null))), ok = arrs.filter(Boolean);
      if (!ok.length) throw new Error(`nodata:${fld}`);
      const o = new Float32Array(ok[0]);
      if (P.wsum) { for (const a of ok.slice(1)) for (let k = 0; k < o.length; k++) o[k] += a[k]; }   // per-interval amounts -> total
      else if (P.wmin) { for (const a of ok.slice(1)) for (let k = 0; k < o.length; k++) if (a[k] < o[k]) o[k] = a[k]; }
      else for (const a of ok.slice(1)) for (let k = 0; k < o.length; k++) if (a[k] > o[k]) o[k] = a[k];
      if (P.wscale) for (let k = 0; k < o.length; k++) if (o[k] >= 0) o[k] *= P.wscale;   // e.g. max wave = 1.86 x significant height (land stays < 0)
      out.fill = o;
    } else if (P.window) {   // amount in the last N hours = run total now minus run total N hours ago (stage 2, browser-only)
      const fld = P.wfield || "apcp", a = F[fld].v, prev = f - P.window;
      if (prev < 0 || (prev > 0 && !S.runs[run].steps.find(x => x.f === prev))) throw new Error(`nodata:${fld}`);
      if (prev === 0) out.fill = a;
      else { const b = (await getField(run, fld, prev)).v, o = new Float32Array(a.length); for (let k = 0; k < a.length; k++) o[k] = Math.max(0, a[k] - b[k]); out.fill = o; }
    } else if (P.fill === "feels") {   // NWS wind chill (T <= 50F, wind > 3 mph) / heat index (T >= 80F, Rothfusz), else air temp
      const T = F.t2m.v, D_ = F.d2m.v, u = F.u10.v, v = F.v10.v, o = new Float32Array(T.length);
      for (let k = 0; k < T.length; k++) { const t = T[k], w = Math.hypot(u[k], v[k]) * 1.15078;
        if (t <= 50 && w > 3) { const p = Math.pow(w, 0.16); o[k] = 35.74 + 0.6215 * t - 35.75 * p + 0.4275 * t * p; }
        else if (t >= 80) { const es = Math.exp(17.625 * ((D_[k] - 32) / 1.8) / (243.04 + (D_[k] - 32) / 1.8)), e0 = Math.exp(17.625 * ((t - 32) / 1.8) / (243.04 + (t - 32) / 1.8)), R = Math.min(100, 100 * es / e0);
          o[k] = -42.379 + 2.04901523 * t + 10.14333127 * R - 0.22475541 * t * R - 0.00683783 * t * t - 0.05481717 * R * R + 0.00122874 * t * t * R + 0.00085282 * t * R * R - 0.00000199 * t * t * R * R; }
        else o[k] = t; }
      out.fill = o;
    } else if (P.fill === "fog") {   // old site's fog risk index (0-100): near-saturation x light wind (+ model visibility), damped in rain
      const T = F.t2m.v, D_ = F.d2m.v, u = F.u10.v, v = F.v10.v, o = new Float32Array(T.length), has = new Set(S.runs[run].fields);
      const vis = has.has("vis") ? await getField(run, "vis", f).then(r => r.v, () => null) : null;
      let rr = null;
      if (has.has("apcp")) { const st_ = S.runs[run].steps, k0 = st_.findIndex(x => x.f === f), f0 = k0 > 0 ? st_[k0 - 1].f : 0;
        const a = await getField(run, "apcp", f).then(r => r.v, () => null), b = f0 > 0 ? await getField(run, "apcp", f0).then(r => r.v, () => null) : null;
        if (a && (b || f0 === 0)) { rr = new Float32Array(a.length); for (let k = 0; k < a.length; k++) rr[k] = Math.max(0, a[k] - (b ? b[k] : 0)) / Math.max(1, f - f0); } }
      for (let k = 0; k < T.length; k++) {
        const sat = Math.min(1, Math.max(0, (5 - (T[k] - D_[k])) / 5)), calm = Math.min(1, Math.max(0, (15 - Math.hypot(u[k], v[k]) * 1.15078) / 12));
        let x = sat * calm; if (vis) x = 0.6 * x + 0.4 * Math.min(1, Math.max(0, (5 - vis[k]) / 4.5)) * sat;
        if (rr) x *= Math.min(1, Math.max(0.25, 1 - rr[k] / 0.08));
        o[k] = 100 * x; }
      out.fill = o;
    } else if (P.fill === "hmax") { const a = F.swh.v, o = new Float32Array(a.length); for (let k = 0; k < a.length; k++) o[k] = a[k] < 0 ? a[k] : a[k] * 1.86; out.fill = o;
    } else if (P.fill === "thick") { const a = F.z500.v, b = F.z1000.v, o = new Float32Array(a.length); for (let k = 0; k < a.length; k++) o[k] = (a[k] - b[k]) / 10; out.fill = blur(o, g.w, g.h, 1.0);
    } else if (P.fill === "snowlvl") { const a = F.frz.v, o = new Float32Array(a.length); for (let k = 0; k < a.length; k++) o[k] = Math.max(0, a[k] - 1000); out.fill = o; }
    else out.fill = F[P.fill] ? F[P.fill].v : g.v;
    if (P.lows && F.mslp) out.mslpRaw = F.mslp.v;   // ensemble-mean lows (L + central pressure)
    if (P.lows || P.spag) out.ens = await fetch(`${DATA}runs/${run}/single/ens_f${String(f).padStart(3, "0")}.json`).then(r => r.ok ? r.json() : null, () => null);
    if (P.isobars && F[P.isobars.field || "mslp"]) { const I = P.isobars, src = F[I.field || "mslp"].v, sc = I.scale || 1, a = new Float32Array(src.length);
      for (let k = 0; k < a.length; k++) a[k] = src[k] * sc; out.iso = blur(a, g.w, g.h, I.sigma);
      if (I.sea_only) for (let k = 0; k < a.length; k++) if (!(src[k] > 0)) out.iso[k] = NaN; }   // 11-03 swell period lines: none over land / no swell
    return out;
  })();
  S.derived.set(key, p); return p;
}

const climCache = new Map();
async function climMonth(m, varn, k) {   // static 16-bit (R*256+G) monthly mean on the model's cropped grid
  const key = `${m}/${varn}/${k}`; if (climCache.has(key)) return climCache.get(key);
  const p = (async () => {
    const C = S.man.models[m].clim[varn], I = await getPixels(DATA + C.files[k] + SV()), [lo, hi] = C.ranges[k], n = I.w * I.h, o = new Float32Array(n);
    for (let i = 0; i < n; i++) o[i] = lo + (I.px[i * 4] * 256 + I.px[i * 4 + 1]) / 65535 * (hi - lo);
    return o;
  })();
  climCache.set(key, p); return p;
}
async function climAt(run, varn, validIso) {   // months blended like aifs_maps.clim_at; t2m also between 00/06/12/18Z
  const m = run.split("/")[0], C = S.man.models[m].clim[varn], v = new Date(validIso), mo = v.getUTCMonth(), mid = Date.UTC(v.getUTCFullYear(), mo, 15);
  const m2 = (mo + (v.getTime() >= mid ? 1 : -1) + 12) % 12, w = Math.min(1, Math.abs(v.getTime() - mid) / (30.4 * 86400e3));
  let parts = [[mo, 1 - w], [m2, w]];
  if (C.hours) {
    const hx = (v.getUTCHours() + v.getUTCMinutes() / 60) / 6, h0 = Math.floor(hx) % 4, h1 = (h0 + 1) % 4, wh = hx - Math.floor(hx);
    parts = parts.flatMap(([k, wk]) => [[k * 4 + h0, wk * (1 - wh)], [k * 4 + h1, wk * wh]]);
  }
  parts = parts.filter(p => p[1] > 1e-6);
  const arrs = await Promise.all(parts.map(p => climMonth(m, varn, p[0]))), o = new Float32Array(arrs[0].length);
  arrs.forEach((a, j) => { const wj = parts[j][1]; for (let i = 0; i < a.length; i++) o[i] += wj * a[i]; });
  return o;
}

// ---------------------------------------------------------------- drawing
const hex = h => [parseInt(h.slice(1, 3), 16), parseInt(h.slice(3, 5), 16), parseInt(h.slice(5, 7), 16)];
const palCache = {};
function palette(pid) {
  const pk = S.run.split("/")[0] + pid; if (palCache[pk]) return palCache[pk];
  const P = PRODS()[pid], L = P.levels, cols = P.colors.map(hex);
  const dL = L[1] - L[0], uniform = L.every((x, k) => Math.abs(x - (L[0] + k * dL)) < 1e-6 * Math.max(1, Math.abs(dL)));
  return (palCache[pk] = { L, uniform, L0: L[0], dL, n: cols.length, cols, under: P.under && hex(P.under), over: P.over && hex(P.over), Lend: L[L.length - 1] });
}
function bin(pal, v) {   // index of the level band holding v (uniform: arithmetic, else binary search)
  if (pal.uniform) return Math.min(pal.n - 1, ((v - pal.L0) / pal.dL) | 0);
  let a = 0, b = pal.L.length - 1; while (b - a > 1) { const m = (a + b) >> 1; if (v >= pal.L[m]) a = m; else b = m; } return a;
}
function sampleNN(st, F, k) {   // nearest grid point (categorical fields: precip type)
  const i = st.idx[k]; if (i < 0) return NaN; return F[i + (st.wx[k] >= 0.5 ? 1 : 0) + (st.wy[k] >= 0.5 ? st.gnx : 0)];
}
// 11-03 (Benjamin: ECMWF "MSLP + precip type" less blocky, "a hair of blending"): instead of the nearest 0.25 deg cell, each pixel blends
// its 4 grid points: rate band = bilinear mix of the bands (dry = 0), so the edge of the precip area follows a smooth line; the type is
// the one with the most weight among the wet points (types never mix into new colors). Dry when the blended band is under 0.5.
function sampleType(st, F, k) {
  const i = st.idx[k]; if (i < 0) return NaN; const tx = st.wx[k], ty = st.wy[k], g = st.gnx;
  const c = [F[i], F[i + 1], F[i + g], F[i + g + 1]], w = [(1 - tx) * (1 - ty), tx * (1 - ty), (1 - tx) * ty, tx * ty];
  let band = 0, hi = 0; const tw = [0, 0, 0, 0];
  for (let q = 0; q < 4; q++) { const v = Math.round(c[q]), b = v & 15; if (!(v >= 1) || !b) continue; band += w[q] * b; tw[(v >> 4) & 3] += w[q]; if (b > hi) hi = b; }
  if (band < 0.5) return 0;
  let t = 0; for (let q = 1; q < 4; q++) if (tw[q] > tw[t]) t = q;
  return (t << 4) | Math.min(hi, Math.max(1, Math.round(band)));
}
function sample(st, F, k) {   // bilinear value at panel pixel k
  const i = st.idx[k]; if (i < 0) return NaN; const tx = st.wx[k], ty = st.wy[k], g = st.gnx;
  return (F[i] * (1 - tx) + F[i + 1] * tx) * (1 - ty) + (F[i + g] * (1 - tx) + F[i + g + 1] * tx) * ty;
}
// 11-03 (SST anomaly): fields with a "no data" code under min_show (land / ice) blend only their valid corners, so the coast gets
// no false dark-blue rim from mixing ocean values with the land code.
function sampleMask(st, F, k, mins) {
  const i = st.idx[k]; if (i < 0) return NaN; const tx = st.wx[k], ty = st.wy[k], g = st.gnx;
  let s = 0, w = 0; const add = (v, ww) => { if (v >= mins && ww > 0) { s += v * ww; w += ww; } };
  add(F[i], (1 - tx) * (1 - ty)); add(F[i + 1], tx * (1 - ty)); add(F[i + g], (1 - tx) * ty); add(F[i + g + 1], tx * ty);
  return w > 0.25 ? s / w : NaN;
}
function sampleRC(F, w, fi, fj) {
  const r = Math.floor(fi), c = Math.floor(fj), ty = fi - r, tx = fj - c;
  return (F[r * w + c] * (1 - tx) + F[r * w + c + 1] * tx) * (1 - ty) + (F[(r + 1) * w + c] * (1 - tx) + F[(r + 1) * w + c + 1] * tx) * ty;
}

// 10-29 8:45 PM (Benjamin: phone slider "a little janky"): redraws are coalesced to one per animation frame and never
// overlap; while the slider is being dragged the map is drawn in a lighter mode (fill at half resolution, URL not touched),
// then once at full quality when the finger lifts.
// 10-30 4:10 PM (Benjamin: "pressure lines disappear when scrubbing on the phone"): the lighter mode used to drop every
// line layer, so isobars / heights / H-L vanished while the finger was down. Lines now stay on while dragging: isobar and
// H/L geometry is cached per frame (GEO), isobars sample only the contour grid (same lines, ~16x fewer samples), the
// freezing line uses a 4 px grid while dragging.
let rafOn = false; S.waiters = [];
// 11-04 (Benjamin t2336u "It refreshes into a different product"): the address used to change only ~0.4 s after a map finished
// drawing, so a refresh while a new product / view / run was still loading (or one that failed to draw) reopened the previous one.
// A product, view or run change now goes into the address right away (hour moves stay on the settled update: iOS replaceState limit).
function urlNow() {
  if (Q.get("clean") || !S.run) return; try { const u = new URL(location), q = u.searchParams;
    if (q.get("prod") === S.prod && q.get("view") === S.view && q.get("run") === S.run) return;
    q.set("prod", S.prod); q.set("view", S.view); q.set("run", S.run); q.delete("model"); const st = (S.runs[S.run] || {}).steps; if (st && st[S.i]) q.set("f", st[S.i].f);
    history.replaceState(null, "", u);
    if (!Q.get("embed") && !Q.get("id") && !Q.get("slim") && !Q.get("make")) localStorage.setItem(Q.get("studio") ? "studio:last" : "viewer:last", u.search); } catch (e) { /* replaceState limit / private mode */ } }
function draw() {
  urlNow();
  return new Promise(res => { S.waiters.push(res); if (!rafOn) { rafOn = true; requestAnimationFrame(pump); } });
}
async function pump() {
  rafOn = false;
  if (S.busy) { S.again = true; return; }
  S.busy = true; const ws = S.waiters; S.waiters = [];
  // 11-02 (Benjamin t2098u, Mac: drag "still doesn't look as good" as the arrow keys): Studio with a mouse / trackpad draws
  // every drag frame on the full sharp path (light frames only on touch screens). Redraws stay coalesced: while one frame is
  // drawing, slider moves only update S.i and the next animation frame draws the newest hour (stale hours are skipped).
  const lite = !!S.dragging && !(FINE_PTR && Q.get("studio"));
  try { await render(lite); } catch (e) { showErr(e); }
  finally { S.busy = false; ws.forEach(r => r()); if (S.again || S.waiters.length) { S.again = false; if (!rafOn) { rafOn = true; requestAnimationFrame(pump); } } }
}
let drawSeq = 0, urlTimer = null;
// 10-31 3:18 PM (Benjamin: "make it jump to the next model run and not show the 'not in this model run'"): an hour where the product
// has no map (6 h precip at F+3, NBM 6 h sums off the 6-hourly times, ...) jumps to the nearest hour that has it, in the direction you
// were stepping (forward first otherwise). Only a product missing from the whole run shows a message, with a button to the nearest
// run of that model that has it. Studio recording turns this off (window.__vjNoJump) so a video never repeats hours.
async function findHour(run, pid, i, dir) {
  const st = S.runs[run].steps, order = [];
  const fw = [], bw = []; for (let j = i + 1; j < st.length; j++) fw.push(j); for (let j = i - 1; j >= 0; j--) bw.push(j);
  order.push(...(dir < 0 ? bw.concat(fw) : fw.concat(bw)));
  for (const j of order) {
    try { await productFields(run, pid, st[j].f); return j; }
    catch (e) { S.derived.delete(`${run}/${pid}/${st[j].f}`); if (!String(e && e.message).startsWith("nodata:")) throw e; }
  }
  return null;
}
function jumpNote(html, ms) {
  let n = $("jumpnote"); if (!n) { n = document.createElement("div"); n.id = "jumpnote"; $("wrap").appendChild(n); }
  n.innerHTML = html; n.hidden = false; clearTimeout(n._t); if (ms) n._t = setTimeout(() => { n.hidden = true; }, ms); return n;
}
async function otherRunWith(run, pid) {   // nearest run of the same model (newest first) whose fields cover this product
  const [m, c] = run.split("/"), need = (PRODS()[pid] || {}).fields || [], rs = [...(S.man.runs[m] || [])].filter(x => x !== c).sort((a, b) => Math.abs(+a.slice(0, 10) - +c.slice(0, 10)) - Math.abs(+b.slice(0, 10) - +c.slice(0, 10)) || (b > a ? 1 : -1));
  for (const x of rs.slice(0, 4)) { try { const R_ = await loadRun(`${m}/${x}`), has = new Set(R_.fields || []); if (need.every(f_ => has.has(f_))) return `${m}/${x}`; } catch (e) { /* skip */ } }
  return null;
}
let lastI = null, lastKey = "";
async function render(lite) {
  const seq = ++drawSeq, t0 = performance.now();
  const dir = lastKey === S.run && lastI !== null && S.i < lastI ? -1 : 1; lastI = S.i; lastKey = S.run;
  if ((VIEWS()[S.view] || {}).waveOnly && !WAVE_PIDS.test(S.prod)) setLists();   // wave-only view (West Coast) + another product
  const run = S.run, vid = S.view, pid = S.prod, step = S.runs[run].steps[S.i], f = step.f;
  let st, D, key;
  try { [st, D, key] = await Promise.all([viewStatic(vid), productFields(run, pid, f), getKey(pid, vid)]); }
  catch (e) {
    if (seq !== drawSeq) return;
    if (!String(e && e.message).startsWith("nodata:")) throw e;
    S.derived.delete(`${rk(run)}/${pid}/${f}`);
    if (!window.__vjNoJump && !S.dragging) {   // while dragging the slider: no jumping under the finger (it jumps when you let go)
      let alt = null; try { alt = await findHour(run, pid, S.i, dir); } catch (err) { /* network: fall through to the message */ }
      if (seq !== drawSeq || S.run !== run || S.prod !== pid) return;
      if (alt !== null) {
        const f2 = S.runs[run].steps[alt].f; S.i = alt; $("step").value = alt; lastI = alt;
        jumpNote(`No ${PRODS()[pid].title} map at F+${f}; showing F+${f2}`, 2500); if (typeof loadNote === "function") loadNote();
        return render(lite);
      }
      otherRunWith(run, pid).then((r2) => { if (S.run !== run || S.prod !== pid) return;
        const n = jumpNote(`This run has no ${PRODS()[pid].title} maps.` + (r2 ? ` <button type="button" id="jumprun">Open ${r2.split("/")[1].slice(8)}Z ${r2.split("/")[1].slice(4, 6)}-${r2.split("/")[1].slice(6, 8)} run</button>` : " Try another run in the Runs menu."), 0);
        const b = n.querySelector("#jumprun"); if (b) b.onclick = async () => { await loadRun(r2); S.run = r2; $("run").value = r2; n.hidden = true; setLists(); draw(); }; });
    }
    const V = VIEWS()[vid], cv = $("map"), st2 = await viewStatic(vid);
    const ctx = sizeMap(cv, V, lite), [LW, LH] = V.fig; ctx.fillStyle = S.man.style.BG; ctx.fillRect(0, 0, LW, LH); ctx.drawImage(layer(st2.base, st2.baseU, cv._rs), 0, 0, LW, LH);
    const miss = `${S.runs[run].runline}  \u00b7  ${V.label}  \u00b7  ${window.__vjNoJump || S.dragging ? "no map at this hour" : "not in this model run"}`;
    if (!coastShown(V)) header(ctx, V, PRODS()[pid].title, step.valid_line, miss, step.badge);
    showCoast(cv, V, { title: PRODS()[pid].title, valid: step.valid_line, sub: miss, badge: step.badge, P: PRODS()[pid], pid, towns: true });
    S.cur = null; window.__drawn = `${pid}/${vid}/${f}`; if (window.onStudioSkip) window.onStudioSkip();
    postCompare(run, pid, vid, step);   // 10-31: still report to the side-by-side page (else sync never starts when a frame opens on such an hour)
    return;
  }
  if (seq !== drawSeq) return;
  const t1 = performance.now();
  const V = VIEWS()[vid], P = PRODS()[pid], cv = $("map");
  const ctx = sizeMap(cv, V, lite), [LW, LH] = V.fig, rs = cv._rs; ctx.fillStyle = S.man.style.BG; ctx.fillRect(0, 0, LW, LH);
  // 1. color fill: value -> bin color, exactly the site's bins (contourf + BoundaryNorm)
  const smp = P.fill === "prt" ? (/^(ifs|ifs9)$/.test(run.split("/")[0]) ? sampleType : sampleNN) : (P.mask_edge || pid === "ssta") && P.min_show !== undefined ? (st_, F_, k_) => sampleMask(st_, F_, k_, P.min_show) : sample;
  const pal = palette(pid), mins = P.min_show, im = ctx.createImageData(st.W, st.H), o = im.data, F = D.fill, n = st.W * st.H;
  const vals = new Float32Array(n);
  if (lite) {   // half resolution: one sample per 2x2 block
    const W = st.W, H = st.H;
    for (let y = 0; y < H; y += 2) for (let x = 0; x < W; x += 2) {
      const k = y * W + x, v = smp(st, F, k); let c = null;
      if (!(v !== v || (mins !== undefined && v < mins))) c = v < pal.L0 ? pal.under : v >= pal.Lend ? pal.over : pal.cols[bin(pal, v)];
      for (let dy = 0; dy < 2 && y + dy < H; dy++) for (let dx = 0; dx < 2 && x + dx < W; dx++) {
        const kk = k + dy * W + dx; vals[kk] = v; if (!c) continue; const q = kk * 4; o[q] = c[0]; o[q + 1] = c[1]; o[q + 2] = c[2]; o[q + 3] = 255; }
    }
  } else if (rs > 1 && !S.timer) for (let k = 0; k < n; k++) vals[k] = smp(st, F, k);
  else for (let k = 0; k < n; k++) {
    const v = smp(st, F, k); vals[k] = v; if (v !== v || (mins !== undefined && v < mins)) continue;
    let c; if (v < pal.L0) c = pal.under; else if (v >= pal.Lend) c = pal.over; else c = pal.cols[bin(pal, v)];
    if (!c) continue; const q = k * 4; o[q] = c[0]; o[q + 1] = c[1]; o[q + 2] = c[2]; o[q + 3] = 255;
  }
  if (rs > 1 && !lite && !S.timer) fillSharp(ctx, st, vals, pal, mins, P.fill === "prt", rs);
  else { const tmp = new OffscreenCanvas(st.W, st.H); tmp.getContext("2d").putImageData(im, 0, 0); ctx.drawImage(tmp, st.x0, st.y0); }
  const t2 = performance.now();
  // 2. borders/coast/frame + header box (static layer)
  const kU = keyURL(pid, vid), L2 = { base: fitLayer(layer(st.base, st.baseU, rs), st.baseU, rs, LW, LH),
    towns: fitLayer(layer(st.towns, st.townsU, rs), st.townsU, rs, LW, LH), key: fitLayer(layer(key, kU, rs), kU, rs, LW, LH) };
  window.__layers = Object.fromEntries(Object.entries(L2).map(([k, v]) => [k, v ? (v.naturalWidth || v.width) : 0]));
  ctx.drawImage(L2.base, 0, 0, LW, LH);
  // 3. product lines
  ctx.save(); ctx.beginPath(); ctx.rect(st.x0, st.y0, st.W, st.H); ctx.clip();
  if (P.freeze !== undefined) {
    const lines = contour(st, vals, P.freeze, lite ? 4 : 3);   // lite: 4 px grid = only exact (even-pixel) samples
    strokeLines(ctx, lines, "#ffffff", pt(3.0), [pt(3.7 * P.freeze_lw), pt(1.6 * P.freeze_lw)]);   // matplotlib halo: 3 pt stroke, dashed with the line
    strokeLines(ctx, lines, P.freeze_color, pt(P.freeze_lw), [pt(3.7 * P.freeze_lw), pt(1.6 * P.freeze_lw)]);
  }
  const gk = `${rk(run)}/${pid}/${vid}/${f}`;
  // 11-03 small fixes (tight wave views: swell-period line labels hidden under town / buoy labels, leaving a gap cut in the line):
  // on wave maps the coast + buoy label boxes are worked out first (dry run, nothing drawn), and the line labels slide off them
  const coastAvoid = WAVE_PIDS.test(pid) && MD().grid === "ll" && P.isobars && P.isobars.shadow_lab ? () => coastTaken(st, D, P, V, LW, LH) : null;
  if (P.isobars && D.iso) drawIsobars(ctx, st, D, P, gk, V, coastAvoid);
  if (P.barbs) drawBarbs(ctx, st, D, P, V);
  S.lowPanel = null;
  if (P.lows || P.spag) drawEns(ctx, st, D, P, V, gk);
  if ((P.hl || (P.isobars && (P.isobars.field || "mslp") === "mslp")) && D.iso && !P.lows) drawHL(ctx, st, D, V, gk, P);   // every MSLP-isobar map (incl. MSLP + wind), not the ensemble-lows map
  ctx.restore();
  // 4. towns (dots + names static) and live numbers
  const tmode = P.towns || "numbers";
  const WT = WAVE_PIDS.test(pid) && MD().grid === "ll" ? coastPlan(ctx, st, V, LW, LH) : null;   // wave maps: coast towns (11-01 t1990u)
  if (st.towns && tmode !== "none" && !(WT && WT.own)) ctx.drawImage(WT && WT.erase.length ? erasedTowns(L2.towns, `${st.townsU}#${WT.vid}`, WT.erase, LW) : L2.towns, 0, 0, LW, LH);
  if (st.towns && tmode === "numbers") for (const t of V.towns) {
    if (WT && WT.re.has(t.name)) continue;   // re-placed with the coast towns
    if (!(t.fi >= 0 && t.fj >= 0 && t.fi < D.h - 1 && t.fj < D.w - 1)) continue;
    let v = sampleRC(D.fill, D.w, t.fi, t.fj); if (!isFinite(v)) continue;   // HRRR: integer = nearest 3 km point; global: bilinear at the pin
    if (pid === "t2m" && t.t2m_corr !== undefined) v += t.t2m_corr;          // pass summit height correction (temp_maps)
    haloText(ctx, fmtVal(P, v), t.x * LW, t.y * LH, `800 ${pt(t.size)}px Montserrat`, t.color, pt(3.0), "left", "middle");
  }
  // 11-01 8:32 AM (Benjamin t1987u: "Include known buoy locations off the coast, and have them show the wave height numbers, do the same for
  // significant wave height"; t1988u: "Just make them look like the other locations in the map"): NDBC buoys on the ECMWF wave maps only
  if (WT) drawCoast(ctx, st, D, P, V, LW, LH, WT);
  if (P.lows && S.lowPanel && !Q.get("studio")) paintLowPanel(ctx, st, V, S.lowPanel);   // 11-02 (Benjamin t2115u): not in Studio frames (Studio has its own dot key); kept on the viewer
  // 5. key + header text
  if (!V.studioOnly) ctx.drawImage(L2.key, 0, 0, LW, LH);   // Studio-only view: Studio draws its own color bar (the key file is another view's)
  if (!V.studioOnly) drawCredit(ctx, st, pid, P, LW, LH, st.towns && tmode !== "none");   // 11-01-26 legal audit: credit line redrawn over the key's baked one
  const [r0, r1, c0, c1] = V.cut;                                            // same rows/cols temp_maps.cut() keeps
  if (!D.pct) D.pct = {};
  if (!D.pct[vid]) { const a = new Float32Array(Math.ceil((r1 - r0) / 2) * Math.ceil((c1 - c0) / 2)); let n = 0;   // every 2nd cell
    for (let r = r0; r < r1; r += 2) for (let c = c0; c < c1; c += 2) a[n++] = D.fill[r * D.w + c]; D.pct[vid] = a.subarray(0, n).sort(); }
  const fin = D.pct[vid];
  const pc = p => fin[Math.min(fin.length - 1, Math.max(0, Math.round(p / 100 * (fin.length - 1))))];
  let extra = (P.isobars && !D.iso && P.extra_noh ? P.extra_noh : P.extra).replace("{lo}", pc(P.pct[0]).toFixed(P.dec || 0)).replace("{hi}", pc(P.pct[1]).toFixed(P.dec || 0));
  if (pid === "gust10" && run.startsWith("eps/") && f <= 144 && f % 3 === 0) extra = extra.replace("in the 6 h ending", "in the 3 h ending");   // 10-31 EPS 3-hourly to F+144
  const coastNow = coastShown(V);
  if (!coastNow) header(ctx, V, P.title, step.valid_line, `${S.runs[run].runline}  \u00b7  ${V.label}  \u00b7  ${extra}`, step.badge);
  S.peak = GUST_PIDS.test(pid) ? drawPeak(ctx, st, vals) : null;
  // 11-01 7:43 AM (Benjamin: "Add a 'max height:80ft' just underneath the bottom right of the graphic"): max wave maps show the tallest
  // value in this frame and view (true grid max over the view's rows/cols, nearest whole ft), right-aligned under the map's bottom-right corner
  let maxv = null;
  if (MAXH_PIDS.test(pid)) {
    if (!D.mx) D.mx = {};
    if (D.mx[vid] === undefined) { let mx = -Infinity; for (let r = r0; r < r1; r++) for (let c = c0; c < c1; c++) { const v = D.fill[r * D.w + c]; if (v > mx) mx = v; } D.mx[vid] = mx; }
    if (isFinite(D.mx[vid]) && D.mx[vid] >= 0) {
      maxv = D.mx[vid]; if (!coastNow) { const yb = st.y0 + st.H, yc = yb + (LH - yb) * 0.5;
      ctx.save(); ctx.font = `800 ${pt(11)}px Montserrat`; ctx.fillStyle = S.man.style.INK; ctx.textAlign = "right"; ctx.textBaseline = "middle";
      ctx.fillText(`Max height: ${Math.round(maxv)} ft`, st.x0 + st.W, yc); ctx.restore(); }
    }
  }
  const t3 = performance.now();
  S.cur = { st, D, vals, P, pid, V, run, f, maxv };
  S.last = { data_ms: t1 - t0, fill_ms: t2 - t1, overlay_ms: t3 - t2, total_ms: t3 - t0 };
  $("stat").textContent = `F+${f}  data ${S.last.data_ms.toFixed(0)} ms · fill ${S.last.fill_ms.toFixed(0)} ms · lines/labels ${S.last.overlay_ms.toFixed(0)} ms`;
  window.__drawn = `${pid}/${vid}/${f}` + (lite ? "~" : ""); window.__rs = rs;
  showCoast(cv, V, { title: P.title, valid: step.valid_line, sub: `${S.runs[run].runline}  \u00b7  ${V.label}  \u00b7  ${extra}` + (maxv != null ? `  ·  Max height ${Math.round(maxv)} ft` : ""), badge: step.badge, P, pid, towns: !!(st.towns && tmode !== "none") });
  postCompare(run, pid, vid, step);
  if (lite) { if (window.onStudioDraw && Q.get("studio")) window.onStudioDraw(cv_(), S.cur, step, true); return; }
  // iOS Safari throws after 100 history.replaceState calls in 10 s: update the URL once things settle
  if (!Q.get("clean")) clearTimeout(urlTimer), urlTimer = setTimeout(() => { const u = new URL(location); u.searchParams.set("prod", pid); u.searchParams.set("view", vid);
    u.searchParams.set("f", f); u.searchParams.set("run", run); u.searchParams.delete("model");
    if (isMemRun(run)) u.searchParams.set("mem", S.mem); else u.searchParams.delete("mem");
    u.searchParams.delete("mg"); u.searchParams.delete("obs"); try { history.replaceState(null, "", u); } catch (e) {}
    // 11-04 (t2283u): last map kept so a bare studio.html / index.html open (bookmark, home-screen app) comes back on it (not compare / embeds)
    if (!Q.get("embed") && !Q.get("id") && !Q.get("slim") && !Q.get("make")) try { localStorage.setItem(Q.get("studio") ? "studio:last" : "viewer:last", u.search); } catch (e) { /* private mode */ } }, 400);
  preload(run, pid, S.i);
  if (window.onStudioDraw) window.onStudioDraw(cv_(), S.cur, step);
}
// 11-01-26 legal audit (Benjamin t2020u "add all appropriate credits"): the key PNGs carry an older credit (no year, no GeoNames, no PRISM).
// Paint over that bottom-left credit row and write the full line: ECMWF CC BY 4.0 (c year, source, modified), GeoNames when town names
// are drawn, PRISM / CPC / GPCP normals on the precip anomaly maps. NOAA keeps "Data: NOAA (public domain)" as before.
const CREDIT_YEAR = new Date().getFullYear();
function creditLines(pid, P, towns) {
  const m = S.run.split("/")[0], name = (MD() && MD().name) || "", ec = /^ECMWF/.test(name) || /^(ifs|ifs9|aifs|eps|aens|aensm|epsm)$/.test(m);
  const L = [];
  if (P.clim === "pr" || /^qpf(a|pct)$/.test(pid)) L.push("Normals: PRISM Group, Oregon State University, https://prism.oregonstate.edu (accessed 30 Oct 2026); NOAA CPC & GPCP via NOAA PSL.");
  const a = [ec ? `Data: \u00a9 ${CREDIT_YEAR} ECMWF (www.ecmwf.int), CC BY 4.0. Modified.` : (pid === "t2m" ? "" : "Data: NOAA (public domain).")];
  if (towns) a.push("Places: GeoNames (geonames.org), CC BY 4.0."); a.push("Basemap: Natural Earth.");
  L.push(a.filter(Boolean).join("  "));
  return L;
}
window.creditLines = creditLines;
function drawCredit(ctx, st, pid, P, LW, LH, towns) {
  const yb = st.y0 + st.H, top = yb + Math.max(3, LH * 0.004), L = creditLines(pid, P, towns);
  const maxW = (MAXH_PIDS.test(pid) ? st.x0 + st.W - pt(11) * 9.5 : LW) - LW * 0.03;   // stay left of "Max height: NN ft"
  ctx.save(); ctx.fillStyle = S.man.style.BG; ctx.fillRect(0, top, LW * 0.985, LH - top);
  let fs = pt(9.5); ctx.font = `500 ${fs}px Montserrat`;
  const wid = () => Math.max(...L.map(l => ctx.measureText(l).width));
  while (fs > pt(6.5) && LW * 0.024 + wid() > maxW) { fs -= 0.5; ctx.font = `500 ${fs}px Montserrat`; }
  const lh = fs * 1.25, avail = LH - top;
  if (L.length * lh > avail) { fs = Math.max(pt(6), avail / L.length / 1.25); ctx.font = `500 ${fs}px Montserrat`; }
  ctx.fillStyle = S.man.style.MUTED; ctx.textAlign = "left"; ctx.textBaseline = "alphabetic";
  const y0 = LH - LH * 0.012 - fs * 0.22;
  L.forEach((l, i) => ctx.fillText(l, LW * 0.024, y0 - (L.length - 1 - i) * fs * 1.25));
  ctx.restore();
}
const cv_ = () => $("map");

function preload(run, pid, i) {   // next 6 steps first, then the rest of the run, 3 at a time
  const steps = S.runs[run].steps, order = [];
  for (let d = 1; d < steps.length; d++) order.push((i + d) % steps.length);
  if (S.pre) S.pre.cancel = true; const job = S.pre = { cancel: false };
  let k = 0; const next = () => { if (job.cancel || k >= order.length) return; const f = steps[order[k++]].f; productFields(run, pid, f).then(next, next); };
  for (let c = 0; c < 3; c++) next();
}

function fmtVal(P, v) {   // temp_maps fmt_int / fmt_vis
  if (P.fmt === "in2") return v < 0.005 ? "0" : v.toFixed(2);
  if (P.fmt === "in1s") return Math.abs(v) < 0.05 ? "0" : (v > 0 ? "+" : "") + (Math.abs(v) < 10 ? v.toFixed(1) : v.toFixed(0));
  if (P.fmt === "in1") return v < 0.05 ? "0" : v < 10 ? v.toFixed(1) : v.toFixed(0);
  if (P.fmt === "ft100") return String(Math.round(v / 100) * 100);
  if (P.fmt === "vis") return v >= 7 ? "7+" : v < 3 ? v.toFixed(1) : v.toFixed(0);
  return String(Math.round(v));
}
// ---- buoys (11-01): fixed NDBC offshore buoy list (tools/fast/site/buoys_ndbc.json, coordinates from NDBC activestations.xml).
// Drawn like the city labels (temp_maps.region_towns): small dark dot with a white edge, "Buoy 46041" in 600 8.5 pt on a white halo, then
// the MODEL value at the buoy point in bold 9.5 pt (same field as the fill, so it matches the colors; not a live observation).
// Placement: right of the dot, then left / above / below / diagonals; a buoy whose label would touch a city label, another buoy or the
// map edge is left out. Values: bilinear when the 4 grid points around the buoy are all sea, else the nearest sea point; none -> skipped.
const WAVE_PIDS = /^(waves|wavemax|wavemax24|swper|swellhs)$/;
const WC_BUOYS = ["46041", "46029", "46050", "46006", "46005", "46002", "46059", "46022", "46014", "46013", "46026", "46042", "46028", "46011", "46054",
  "46025", "46047", "46086", "46087", "46089", "46027", "46015", "46229", "46036", "46214"];
const LOCAL_VIEWS = new Set(["wa", "puget", "newa", "wwa"]), isWaB = (tag, loc) => tag === "wa" || (loc && /inner/.test(tag || ""));
const BUOYS = [["46041","Cape Elizabeth",47.351,-124.741,"wa"],["46029","Columbia River Bar",46.148,-124.508,"wa"],["46087","Neah Bay",48.493,-124.727,"wa"],["46005","West Washington",46.147,-131.077,"wa wide"],["46089","Tillamook",45.928,-125.815,"wa"],["46050","Stonewall Bank",44.679,-124.535,"wa"],["46002","West Oregon",42.56,-130.523,"wa wide"],["46211","Grays Harbor",46.857,-124.243,"wa"],["46088","New Dungeness",48.332,-123.179,"inner any"],["46267","Angeles Point",48.171,-123.6,"inner"],["46303","Southern Georgia Strait",49.02,-123.43,"inner"],["46120","Point Wells",47.761,-122.397,"inner"],["46118","Bellingham Bay",48.724,-122.576,"inner"],["46146","Halibut Bank",49.34,-123.73,"sog"],["46054","West Santa Barbara",34.265,-120.477,""],["46229","Umpqua Offshore",43.772,-124.549,""],["46015","Port Orford",42.754,-124.839,""],["46027","St Georges",41.84,-124.382,""],["46022","Eel River",40.716,-124.54,""],["46014","Point Arena",39.225,-123.98,""],["46013","Bodega Bay",38.235,-123.317,""],["46214","Point Reyes",37.944,-123.466,""],["46026","San Francisco",37.75,-122.838,""],["46042","Monterey",36.787,-122.408,""],["46028","Cape San Martin",35.763,-121.9,""],["46011","Santa Maria",34.937,-120.999,""],["46025","Santa Monica Basin",33.765,-119.077,""],["46047","Tanner Bank",32.418,-119.535,""],["46086","San Clemente Basin",32.504,-118.029,""],["46206","La Perouse Bank",48.84,-126.0,""],["46059","West California",38.067,-129.895,"wide"],["46006","Southeast Papa",40.73,-137.42,"wide"],["46036","South Nomad",48.36,-133.94,"wide"],["46004","Middle Nomad",50.93,-136.1,""],["46147","South Moresby",51.83,-131.22,""],["46208","West Moresby",52.52,-132.69,""],["46205","West Dixon Entrance",54.18,-134.32,""],["46184","North Nomad",53.92,-138.85,"wide"],["46246","Station Papa",49.903,-145.246,""],["46084","Cape Edgecumbe",56.614,-136.04,""],["46083","Fairweather Ground",58.276,-138.024,""],["46085","Central Gulf of Alaska",55.84,-142.895,"wide"],["46001","Western Gulf of Alaska",56.296,-148.027,"wide"],["46060","West Orca Bay",60.571,-146.795,""],["46078","Albatross Bank",55.561,-152.599,""],["46066","South Kodiak",52.776,-154.992,"wide"],["51001","NW Hawaii",24.475,-162.03,"wide"],["51000","Northern Hawaii",23.534,-153.752,""],["51003","Western Hawaii",19.151,-160.617,""],["51002","SW Hawaii",17.07,-157.755,""],["51004","SE Hawaii",17.504,-152.197,"wide"],["44025","Long Island",40.258,-73.175,""],["44008","Nantucket",40.5,-69.254,""],["44011","Georges Bank",41.088,-66.546,"wide"],["41001","East Hatteras",34.738,-72.503,"wide"],["41002","South Hatteras",31.743,-74.955,""],["41048","West Bermuda",31.878,-69.722,"wide"],["41010","Canaveral East",28.86,-78.478,"wide"],["41047","NE Bahamas",27.557,-71.48,""],["42002","West Gulf",25.95,-93.78,"wide"],["42001","Mid Gulf",25.922,-89.638,"wide"],["42003","East Gulf",25.925,-85.616,""]];
function drawBuoys(ctx, st, D, P, V, LW, LH, taken0) {
  const cr = MD().crop || [0, 0, 0, 0], X0 = st.x0, Y0 = st.y0, X1 = st.x0 + st.W, Y1 = st.y0 + st.H;
  if (!st.buoyPx) st.buoyPx = {};
  const F = D.fill, w = D.w, h = D.h, ok = (r, c) => r >= 0 && c >= 0 && r < h && c < w && F[r * w + c] >= 0;
  const fName = `600 ${pt(8.5)}px Montserrat`, fNum = `800 ${pt(9.5)}px Montserrat`, hh = pt(6.5), gap = pt(3.0), off = pt(5);
  window.__buoyLog = []; const taken = taken0 || [];   // [x0, y0, x1, y1] in figure px; drawCoast passes the city + coast town boxes (shared, buoys add theirs)
  ctx.save();
  const hit = (b, g = pt(2.5)) => b[0] < X0 + 2 || b[1] < Y0 + 2 || b[2] > X1 - 2 || b[3] > Y1 - 2 || taken.some(a => b[0] < a[2] + g && b[2] > a[0] - g && b[1] < a[3] + g && b[3] > a[1] - g);
  // 11-01 8:38 AM (Benjamin t1989u: "Make sure it doesn't look excessively crowded, the buoys I care about the most are the ones right off the
  // Washington coast in the PNW views"): Washington offshore buoys first; the North America view shows only the sparse "wide" set; any
  // buoy closer than 30 pt (Washington buoys) / 48 pt (others; na: 60 pt) to one already drawn is left out, so the ocean stays uncrowded. City labels keep priority.
  const wide = S.view === "na" || VSRC(S.view) === "na", drawn = [], loc = LOCAL_VIEWS.has(VSRC(S.view)), wcv = VSRC(S.view) === "wc";
  // West Coast view (t1999u): Benjamin's buoy list first (offshore + California coast), then the rest; 40 pt spacing
  const LIST = wcv ? WC_BUOYS.map(id => BUOYS.find(b => b[0] === id)).filter(Boolean).concat(BUOYS.filter(b => !WC_BUOYS.includes(b[0]))) : BUOYS;
  for (const [id, , la, lo, tag] of LIST) {
    // Coast view: only buoys both Studio frames show in full (t2300u tighter boxes: 9:16 west edge 127.35 W, south edge / keys ~46 N)
    if (VSRC(S.view) === "coast" && (lo < -126.9 || la < 45.57 || la > 49.2)) continue;   // t2311u: south edge / keys ~0.43 deg further south; 46146 (49.34 N) would touch the 16:9 top edge
    if (wide && !/wide/.test(tag || "")) continue;
    // 11-01 9:31 AM (Benjamin t1998u "See if there are any buoys in the puget sound and strait of Juan de Fuca ... Include a marker in the strait of
    // Georgia"): "inner" = Salish Sea buoys, Washington / Puget views only ("any": also elsewhere as before); "sog" = Halibut Bank, not in the local views
    if (/inner/.test(tag) && !loc && !/any/.test(tag)) continue;
    if (tag === "sog" && loc) continue;
    const fi = (90 - la) / 0.25 - cr[0], fj = ((lo + 360) % 360) / 0.25 - cr[2];
    if (!(fi >= 0 && fj >= 0 && fi < h - 1 && fj < w - 1)) continue;
    if (!(id in st.buoyPx)) { const q = gridInv(V, st, fi, fj, null); st.buoyPx[id] = q && q[0] >= 0 && q[1] >= 0 && q[0] <= st.W && q[1] <= st.H ? [X0 + q[0], Y0 + q[1]] : null; }
    const minD = pt(wide ? 60 : isWaB(tag, loc) ? 30 : wcv ? 40 : 48), p = st.buoyPx[id]; if (!p || drawn.some(([a, b]) => (a - p[0]) ** 2 + (b - p[1]) ** 2 < minD * minD)) { if (p) (window.__buoyLog = window.__buoyLog || []).push(`${id}: spacing`); continue; }
    const r = Math.floor(fi), c = Math.floor(fj); let v;
    if (ok(r, c) && ok(r, c + 1) && ok(r + 1, c) && ok(r + 1, c + 1)) v = sampleRC(F, w, fi, fj);
    else { let bd = Infinity; for (const [rr, cc] of [[r, c], [r, c + 1], [r + 1, c], [r + 1, c + 1]]) { const d = (rr - fi) ** 2 + (cc - fj) ** 2; if (ok(rr, cc) && d < bd) { bd = d; v = F[rr * w + cc]; } } }
    if (!isFinite(v)) continue;
    const nm = `Buoy ${id}`, s_ = fmtVal(P, v); ctx.font = fName; const nw = ctx.measureText(nm).width; ctx.font = fNum; const vw = ctx.measureText(s_).width, W_ = nw + gap + vw;
    const [x, y] = p, dot = [x - pt(3), y - pt(3), x + pt(3), y + pt(3)]; if (hit(dot, pt(0.5))) { (window.__buoyLog = window.__buoyLog || []).push(`${id}: dot blocked`); continue; }   // the dot only has to clear the labels themselves
    const cands = [[off, 0], [-off - W_, 0], [-W_ / 2, -pt(9.5)], [-W_ / 2, pt(9.5)], [off, -pt(6)], [off, pt(6)], [-off - W_, -pt(6)], [-off - W_, pt(6)]].concat(isWaB(tag, loc) ? [[-off - W_, -pt(12)], [-off - W_, pt(12)], [off, -pt(12)], [off, pt(12)]] : []);
    let at = null; for (const [gx, gy] of cands) { const b = [x + gx, y + gy - hh, x + gx + W_, y + gy + hh]; if (!hit(b)) { at = [gx, gy, b]; break; } }
    if (!at) { (window.__buoyLog = window.__buoyLog || []).push(`${id}: no room`); continue; }
    taken.push(dot, at[2]); drawn.push(p);
    ctx.beginPath(); ctx.arc(x, y, pt(1.6) + pt(0.45), 0, 2 * Math.PI); ctx.fillStyle = "#ffffff"; ctx.fill();
    ctx.beginPath(); ctx.arc(x, y, pt(1.6), 0, 2 * Math.PI); ctx.fillStyle = "#1b1d22"; ctx.fill();
    haloText(ctx, nm, x + at[0], y + at[1], fName, "#1b1d22", pt(2.4), "left", "middle");
    haloText(ctx, s_, x + at[0] + nw + gap, y + at[1], fNum, "#0d0f13", pt(3.0), "left", "middle");
  }
  ctx.restore();
}
// ---- coast towns on the wave maps (11-01 9:00 AM, Benjamin t1990u: "You can also include west port, Long Beach, ocean shores and La push on
// the Washington map wave map still, and the other town names we discussed a long time ago for waves"; house rules: Long Beach and Ocean
// Shores labeled over the ocean right next to the town, WA towns before OR / BC, no crowding, buoys off the WA coast matter most).
// Wave maps only (waves / wavemax / wavemax24, viewer + Studio). Towns from the WA marine wave map (wa_extras/wave_map.py TOWNS + La Push).
// "re": static-layer city labels lifted out of the town layer (erased there) and placed again together with the coast towns and the buoys,
// so the coast has room (Neah Bay's label covered buoy 46087, Aberdeen's covered Ocean Shores / Westport). Nothing is dropped: a re-placed
// city that finds no free spot goes back to its old spot. Same look as the city labels of that view (WA view: 9.5 pt name + 10.5 pt bold
// number; Pacific NW views: 8.5 pt + 9.5 pt). Number = MODEL wave value at the nearest sea grid point (the town pin is often land at 0.25°).
const COAST_TOWNS = { "Neah Bay": [48.37, -124.62, "a"], "La Push": [47.908, -124.636, "l"], "Forks": [47.95, -124.39, "r"], "Ocean Shores": [46.974, -124.156, "l"],
  "Westport": [46.89, -124.104, "l"], "Aberdeen": [46.98, -123.82, "r"], "Raymond": [46.686, -123.733, "r"], "Long Beach": [46.35, -124.05, "l"],
  "Port Angeles": [48.12, -123.43, "b"], "Astoria": [46.188, -123.831, "r"], "Cannon Beach": [45.89, -123.96, "r"], "Commencement Bay": [47.295, -122.475, "r"], "Victoria": [48.43, -123.36, "a"],
  "Admiralty Inlet": [48.135, -122.72, "r"], "Smith Island": [48.321, -122.831, "r"], "Birch Bay": [48.918, -122.765, "r"], "Elliott Bay": [47.605, -122.36, "r"],
  "Possession Sound": [47.985, -122.255, "r"], "Tatoosh Island": [48.392, -124.736, "a"],
  "Vancouver": [49.283, -123.12, "r"],
  // West Coast view (t1999u): Shore Acres (Cape Arago, OR) + major Oregon / California coast places (labels on the land side)
  "Shore Acres": [43.326, -124.383, "r"], "Coos Bay": [43.366, -124.217, "r"], "Newport": [44.637, -124.053, "r"], "Crescent City": [41.756, -124.201, "r"],
  "Eureka": [40.802, -124.164, "r"], "Cape Mendocino": [40.44, -124.409, "r"], "Fort Bragg": [39.446, -123.805, "r"], "Bodega Bay": [38.333, -123.048, "r"],
  "San Francisco": [37.76, -122.51, "r"], "Half Moon Bay": [37.463, -122.428, "r"], "Santa Cruz": [36.974, -122.03, "r"], "Monterey": [36.6, -121.894, "r"],
  "Morro Bay": [35.366, -120.85, "r"], "Santa Barbara": [34.42, -119.698, "r"], "Malibu": [34.026, -118.78, "r"], "Los Angeles": [33.99, -118.48, "r"],
  "San Diego": [32.715, -117.17, "r"] };   // BC (the lm / bc town pins for "Vancouver" sit at Vancouver WA)
const COAST_VIEWS = {   // order = priority; buoys: "first" = WA buoys placed before the added towns (Pacific NW views), else after
  // 11-01 9:31 AM (Benjamin t1998u "Remove any towns that aren't right on the water from this map. Replace oak harbor with smith island ... Don't
  // really want wave heights for seattle, everett, Tacoma, Olympia"): the Washington wave view drops the static town layer ("own") and draws only
  // saltwater towns (number = model wave value at the nearest sea point) plus Seattle / Everett / Tacoma / Olympia as plain names ("plain")
  wa: { style: "wa", own: true, re: [], add: [], buoys: "after",
        order: ["Tatoosh Island", "La Push", "Ocean Shores", "Westport", "Long Beach", "Admiralty Inlet", "Port Angeles", "Smith Island", "Birch Bay",
                "Elliott Bay", "Possession Sound", "Commencement Bay", "Cannon Beach"] },
  pnwt: { style: "region", own: true, re: [], add: ["Ocean Shores", "Westport", "La Push", "Long Beach", "Tatoosh Island"], buoys: "first", big: ["Vancouver"], plainLast: true },   // t2008u: water names (name only) placed last, regular size   // Tacoma's name covered buoy 46041
  wc: { style: "region", re: [], add: ["Shore Acres", "San Francisco", "Los Angeles", "San Diego", "Monterey", "Eureka", "Crescent City", "Newport",
        "Santa Barbara", "Half Moon Bay", "Santa Cruz", "Morro Bay", "Fort Bragg", "Bodega Bay", "Cape Mendocino", "Malibu", "Westport", "Tatoosh Island",
        "Coos Bay", "Cannon Beach", "Long Beach", "Ocean Shores", "La Push"], buoys: "after", side: "r" },
  pnw: { style: "region", re: [], add: ["Ocean Shores", "Long Beach", "La Push", "Westport", "Tatoosh Island"], buoys: "after", side: "r" },
  // Studio Coast view (t2289u / t2290u): like Pacific NW tight, coast towns + WA buoys first, water names last
  coast: { style: "region", own: true, re: [], add: ["Ocean Shores", "Westport", "La Push", "Long Beach", "Tatoosh Island", "Astoria"], buoys: "first", big: ["Vancouver"], plainLast: true,
    dotGap: 4, sides: { "Ocean Shores": "a", "Westport": "r" } } };   // t2300u: Westport always in (its dot sits ~5 pt below Ocean Shores': Ocean Shores above, Westport to the right);   // no other city labels here: town names go on the (empty) land side, buoy labels keep the ocean
const coastPx = (st, V) => (la, lo) => { const cr = MD().crop || [0, 0, 0, 0], k = `${la},${lo}`; if (!st.coastPx) st.coastPx = {};
  if (!(k in st.coastPx)) { const q = gridInv(V, st, (90 - la) / 0.25 - cr[0], ((lo + 360) % 360) / 0.25 - cr[2], null);
    st.coastPx[k] = q && q[0] >= 0 && q[1] >= 0 && q[0] <= st.W && q[1] <= st.H ? [st.x0 + q[0], st.y0 + q[1]] : null; } return st.coastPx[k]; };
// 11-01 9:36 AM (Benjamin t2001u "Remove all inland locations from the waves maps, except for the [ones] I mentioned in Washington"): on every wave
// view only towns on saltwater keep a label ("n": name + model wave value); Seattle / Everett / Tacoma / Olympia stay as plain names ("p", t1998u
// "Don't really want wave heights for seattle, everett, Tacoma, Olympia"); Oak Harbor -> Smith Island (t1998u). Everything else is left off.
const WAVE_KEEP = Object.fromEntries([..."Birch Bay|Port Angeles|Admiralty Inlet|Smith Island|Tatoosh Island|La Push|Long Beach|Cannon Beach|Ocean Shores|Westport|Anacortes|Coupeville|Friday Harbor|Bremerton|Poulsbo|Mukilteo|Edmonds|Kingston|Gig Harbor|Port Orchard|Bainbridge Is.|Port Ludlow|Vancouver|Richmond|North Vancouver|Delta (Ladner)|Tsawwassen|White Rock|Point Roberts|Nanaimo|Squamish|Port Alberni|Courtenay|Campbell River|Powell River|Sechelt|Tofino|Ucluelet|Parksville|Port Renfrew|Sooke".split("|").map(n => [n, "n"]),
  ..."Elliott Bay|Possession Sound|Commencement Bay".split("|").map(n => [n, "p"])]);
// 11-01 10:02 AM (Benjamin t2005u "Move the everett location to say possession sound, move the port Townsend location to admiralty inlet, change
// neah bay to the tattoosh island location, take Bellingham off, put birch bay on. Take Victoria off. Change seattle to the Elliot bay location.
// Change Tacoma to the western part of Commencement bay. Take Olympia off."): Neah Bay -> Tatoosh Island, Bellingham -> Birch Bay; Victoria and
// Olympia removed from WAVE_KEEP; Everett / Port Townsend / Seattle / Tacoma moved onto the water (COAST_TOWNS)
// 11-01 10:21 AM (Benjamin t2008u "I want those marine locations to be the names on the map too instead of the cities"): Everett -> Possession Sound,
// Port Townsend -> Admiralty Inlet, Seattle -> Elliott Bay, Tacoma -> Commencement Bay (same spots as t2005u)
const WAVE_RENAME = { "Oak Harbor": "Smith Island", "Neah Bay": "Tatoosh Island", "Bellingham": "Birch Bay", "Everett": "Possession Sound",
  "Port Townsend": "Admiralty Inlet", "Seattle": "Elliott Bay", "Tacoma": "Commencement Bay" };
// 11-01 10:34 AM (Benjamin t2011u "Remove irrelevant town names from the western Washington and puget sound views in waves too"): sheltered
// bay-head / inlet towns that don't help read waves are dropped on those two views (all wave products, viewer + Studio)
const WAVE_DROP = { wwa: new Set(["Bremerton", "Poulsbo", "Coupeville", "Friday Harbor"]),
  puget: new Set(["Bremerton", "Poulsbo", "Port Orchard", "Port Ludlow"]),
  coast: new Set(["Possession Sound", "Commencement Bay", "Elliott Bay"]) };   // t2300u: cut off at the 9:16 frame's right edge
const OWN_DEFAULT = { style: "wa", own: true, re: [], add: [], buoys: "after" };   // other views with a town layer (puget, wwa, ewa, passes, newa, lm, bc)
function coastPlan(ctx, st, V, LW, LH) {
  const vid = VSRC(S.view), C = COAST_VIEWS[vid] || ((V.towns || []).length ? OWN_DEFAULT : null), cr = MD().crop || [0, 0, 0, 0];
  if (!C) return { vid, erase: [], re: new Set(), C: null };
  if (C.own) {   // 11-01 t1998u / t2001u: own labels only (static town layer not drawn): saltwater towns + the four Puget Sound cities as plain names
    const xt = {}, keep = [];
    for (const t of V.towns || []) { const la = 90 - (t.fi + cr[0]) * 0.25, lo = (t.fj + cr[2]) * 0.25 - 360;
      const nm = WAVE_RENAME[t.name] || t.name, k = WAVE_KEEP[nm]; if (!k || (WAVE_DROP[vid] && WAVE_DROP[vid].has(nm)) || (nm === "Vancouver" && !["lm", "bc", "pnwt"].includes(vid))) continue;
      if (!COAST_TOWNS[nm]) xt[nm] = [la, lo, "r"]; keep.push(nm); }
    const nn = keep.filter(n => WAVE_KEEP[n] === "n"), pp = keep.filter(n => WAVE_KEEP[n] === "p");
    const pre = C.order || (C.plainLast ? nn : nn.concat(pp)), post = C.order ? [] : (C.add || []).filter(n => !pre.includes(n)).concat(C.plainLast ? pp : []);
    return (window.__coast = { vid, C, own: true, xt, pre, post, erase: [], re: new Set((V.towns || []).map(t => t.name)), boxes: [], px: coastPx(st, V), log: [] }); }
  const wa = C.style === "wa", gap = pt(wa ? 3.5 : 3.0), hh = pt(6.5), erase = [], re = new Set(), boxes = [];
  const px = coastPx(st, V);
  ctx.save();
  for (const t of V.towns || []) {   // static city labels: number at t.x / t.y, name just to its left
    ctx.font = wa ? `600 ${pt(9.5)}px Montserrat` : `700 ${pt(9.5)}px Montserrat`;
    const nx = t.x * LW, ny = t.y * LH, nw = ctx.measureText(t.name || "").width, b = [nx - nw - gap - pt(1), ny - hh, nx + pt(14), ny + hh];
    if (C.re.includes(t.name) && COAST_TOWNS[t.name]) { const T = COAST_TOWNS[t.name], d = px(T[0], T[1]); if (!d) { boxes.push(b); continue; }
      re.add(t.name); erase.push([b[0] - pt(2), ny - pt(8), nx + pt(1), ny + pt(8)], [d[0] - pt(3.5), d[1] - pt(3.5), d[0] + pt(3.5), d[1] + pt(3.5)]);
      boxes.push(null); C._old = C._old || {}; C._old[t.name] = [nx - nw - gap, ny]; }
    else boxes.push(b);
  }
  ctx.restore();
  return (window.__coast = { vid, C, erase, re, boxes: boxes.filter(Boolean), px, log: [] });
}
const TE = new Map();
function erasedTowns(im, key, rects, LW) {   // town layer copy with the re-placed cities cut out (cached per layer size)
  const w = im.naturalWidth || im.width, h = im.naturalHeight || im.height, s = w / LW, k = `${key}@${w}`; let c = TE.get(k);
  if (!c) { c = document.createElement("canvas"); c.width = w; c.height = h; const x = c.getContext("2d"); x.drawImage(im, 0, 0);
    for (const r of rects) x.clearRect(r[0] * s, r[1] * s, (r[2] - r[0]) * s, (r[3] - r[1]) * s);
    TE.set(k, c); while (TE.size > 6) TE.delete(TE.keys().next().value); }
  return c;
}
// 11-01 9:54 AM (Benjamin t2004u "Make the coastal town name wave heights pull a marker 1/2 mile off shore"): each saltwater town's number
// is read at a point ~0.5 mi (0.8 km) off its shore on the open-water side, not at the town. OFFSHORE = explicit points (towns whose pin
// sits back from the water or inside a bay / harbor: the point is 0.5 mi off the open shore); OFF_BRG = bearing (deg, 0 = N, 90 = E)
// toward the water, point = town + 0.8 km along it; other towns: due west. Sampled like before (bilinear when the 4 grid points around
// the marker are sea, else the nearest sea point within 1.5 cells of the MARKER), so at 0.25 deg most numbers only change where the
// nearest sea cell differs; no sea point near the marker -> the town point as before (logged).
const OFFSHORE = { "Tatoosh Island": [48.392, -124.75], "La Push": [47.908, -124.648], "Ocean Shores": [46.974, -124.19], "Westport": [46.89, -124.142],
  "Long Beach": [46.35, -124.077], "Cannon Beach": [45.89, -123.975], "Port Angeles": [48.13, -123.43],
  "Birch Bay": [48.91, -122.79], "Smith Island": [48.328, -122.831], "Admiralty Inlet": [48.135, -122.72], "Shore Acres": [43.326, -124.395],
  "Coos Bay": [43.35, -124.36], "Eureka": [40.80, -124.20], "San Francisco": [37.76, -122.52], "San Diego": [32.745, -117.265],
  "Monterey": [36.61, -121.88], "Santa Barbara": [34.395, -119.69], "Los Angeles": [33.98, -118.50], "Crescent City": [41.74, -124.21] };
const OFF_BRG = { "Anacortes": 0, "Coupeville": 0, "Friday Harbor": 90, "Bremerton": 180, "Poulsbo": 180, "Mukilteo": 315, "Edmonds": 270, "Kingston": 90,
  "Gig Harbor": 90, "Port Orchard": 0, "Bainbridge Is.": 90, "Port Ludlow": 90, "Vancouver": 270, "Richmond": 270, "North Vancouver": 180,
  "Delta (Ladner)": 270, "Tsawwassen": 270, "White Rock": 180, "Point Roberts": 270, "Nanaimo": 90, "Squamish": 180, "Port Alberni": 180,
  "Courtenay": 90, "Campbell River": 90, "Powell River": 270, "Sechelt": 180, "Parksville": 0, "Sooke": 180, "Bodega Bay": 200, "Santa Cruz": 180,
  "Malibu": 180 };
function offshorePt(name, la, lo) {
  if (OFFSHORE[name]) return OFFSHORE[name];
  const b = (OFF_BRG[name] ?? 270) * Math.PI / 180, km = 0.8;
  return [la + km * Math.cos(b) / 111.2, lo + km * Math.sin(b) / (111.2 * Math.cos(la * Math.PI / 180))];
}
function offVal(D, name, T, WT) {   // t2004u: the town's number from its 0.5 mi offshore marker (see OFFSHORE)
  const [a, b] = offshorePt(name, T[0], T[1]); let v = seaVal(D, a, b), how = "offshore";
  if (!isFinite(v)) { v = seaVal(D, T[0], T[1]); how = "town (no sea near the marker)"; }
  (WT.vals = WT.vals || {})[name] = [Math.round(seaVal(D, T[0], T[1])), Math.round(v), how]; return v;
}
function seaVal(D, la, lo) {   // model value at a coast town: bilinear when the 4 points around it are sea, else the nearest sea point (<= 2 cells)
  const cr = MD().crop || [0, 0, 0, 0], F = D.fill, w = D.w, h = D.h, fi = (90 - la) / 0.25 - cr[0], fj = ((lo + 360) % 360) / 0.25 - cr[2];
  const ok = (r, c) => r >= 0 && c >= 0 && r < h && c < w && F[r * w + c] >= 0, r = Math.floor(fi), c = Math.floor(fj);
  if (ok(r, c) && ok(r, c + 1) && ok(r + 1, c) && ok(r + 1, c + 1)) return sampleRC(F, w, fi, fj);
  let bd = 2.26, v; for (let rr = r - 1; rr <= r + 2; rr++) for (let cc = c - 1; cc <= c + 2; cc++) { const d = (rr - fi) ** 2 + (cc - fj) ** 2; if (ok(rr, cc) && d < bd) { bd = d; v = F[rr * w + cc]; } }
  return v;
}
function drawCoast(ctx, st, D, P, V, LW, LH, WT) {
  const C = WT.C; if (!C) { WT.taken = WT.boxes = WT.boxes || []; drawBuoys(ctx, st, D, P, V, LW, LH, WT.taken); return; }
  const wa = C.style === "wa", fs = WT.vid === "wawide" ? WAWIDE_FS : 1, fName = `600 ${pt((wa ? 9.5 : 8.5) * fs)}px Montserrat`, fNum = `800 ${pt((wa ? 10.5 : 9.5) * fs)}px Montserrat`, gap = pt(wa ? 3.5 : 3.0), hh = pt(6.5);
  const X0 = st.x0, Y0 = st.y0, X1 = st.x0 + st.W, Y1 = st.y0 + st.H, taken = WT.boxes.slice(), dots = [], resv = []; WT.taken = taken;
  const hit = (b, g = pt(2.5)) => b[0] < X0 + 2 || b[1] < Y0 + 2 || b[2] > X1 - 2 || b[3] > Y1 - 2 || taken.concat(resv).some(a => b[0] < a[2] + g && b[2] > a[0] - g && b[1] < a[3] + g && b[3] > a[1] - g);
  // the WA buoys' dots are kept free of town labels (Benjamin: those buoys matter most); the buoys themselves don't see this reserve
  // (only buoys the spacing rule will keep: same 30 pt rule as drawBuoys), and so are the re-placed cities' own dots
  const kept = [], loc = LOCAL_VIEWS.has(WT.vid); for (const [id, , la, lo, tag] of BUOYS) if (isWaB(tag, loc)) { const d = WT.px(la, lo); if (!d || kept.some(([a, b]) => (a - d[0]) ** 2 + (b - d[1]) ** 2 < pt(30) ** 2)) continue;
    kept.push(d); resv.push([d[0] - pt(3), d[1] - pt(3), d[0] + pt(3), d[1] + pt(3)]); }
  for (const n of (C.own ? [] : WT.re)) { const T = COAST_TOWNS[n], d = T && WT.px(T[0], T[1]); if (d) resv.push([d[0] - pt(2.5), d[1] - pt(2.5), d[0] + pt(2.5), d[1] + pt(2.5)]); }
  const place = (name, must) => {
    const T = COAST_TOWNS[name] || (WT.xt && WT.xt[name]), d = T && WT.px(T[0], T[1]); if (!d) { WT.log.push(`${name}: off map`); return; }
    const [x, y] = d, dot = [x - pt(2.5), y - pt(2.5), x + pt(2.5), y + pt(2.5)], big = (C.big || []).includes(name);
    if (must) { const k = resv.findIndex(b => Math.abs(b[0] + pt(2.5) - x) < 0.01 && Math.abs(b[1] + pt(2.5) - y) < 0.01); if (k >= 0) resv.splice(k, 1); }   // its own dot reserve
    if (!must && ((C.sides && C.sides[name] ? resv.some(a => dot[0] < a[2] && dot[2] > a[0] && dot[1] < a[3] && dot[3] > a[1]) : hit(dot, pt(1))) || dots.some(([a, b]) => (a - x) ** 2 + (b - y) ** 2 < pt(C.dotGap || (wa ? 9 : 11)) ** 2))) { WT.log.push(`${name}: dot blocked`); return; }
    const t0 = must && (V.towns || []).find(t => t.name === name);   // a re-placed city keeps its usual number (read at its pin, as before)
    const fN = big ? `700 ${pt(9.5 * fs)}px Montserrat` : fName;
    const v = t0 && t0.fi >= 0 && t0.fj >= 0 && t0.fi < D.h - 1 && t0.fj < D.w - 1 ? sampleRC(D.fill, D.w, t0.fi, t0.fj) : offVal(D, name, T, WT), s_ = isFinite(v) && !(WT.own && WAVE_KEEP[name] === "p") ? fmtVal(P, v) : "";
    ctx.font = fN; const nw = ctx.measureText(name).width; ctx.font = fNum; const vw = s_ ? ctx.measureText(s_).width : 0, W_ = nw + (s_ ? gap + vw : 0);
    const c = { r: [pt(5), 0], l: [-pt(5) - W_, 0], a: [-W_ / 2, -pt(9.5)], b: [-W_ / 2, pt(9.5)] };
    const sd = C.side || (C.sides && C.sides[name]) || T[2], cands = [c[sd], ...["r", "l", "a", "b"].filter(k => k !== sd).map(k => c[k]), [pt(5), -pt(6)], [pt(5), pt(6)], [-pt(5) - W_, -pt(6)], [-pt(5) - W_, pt(6)]];
    let at = null; for (const [gx, gy] of cands) { const b = [x + gx, y + gy - hh, x + gx + W_, y + gy + hh]; if (!hit(b)) { at = [gx, gy, b]; break; } }
    if (!at && must && C._old && C._old[name]) { const [ox, oy] = C._old[name]; at = [ox - x, oy - y, [ox, oy - hh, ox + W_, oy + hh]]; }   // never drop an existing city
    if (!at) { WT.log.push(`${name}: no room for the label`); return; }
    taken.push(dot, at[2]); dots.push(d); WT.log.push(`${name}: placed`);
    ctx.beginPath(); ctx.arc(x, y, pt(wa ? 1.8 : 1.6) + pt(wa ? 0.5 : 0.45), 0, 2 * Math.PI); ctx.fillStyle = "#ffffff"; ctx.fill();
    ctx.beginPath(); ctx.arc(x, y, pt(wa ? 1.8 : 1.6), 0, 2 * Math.PI); ctx.fillStyle = "#1b1d22"; ctx.fill();
    haloText(ctx, name, x + at[0], y + at[1], fN, "#1b1d22", pt(wa ? 2.6 : 2.4), "left", "middle");
    if (s_) haloText(ctx, s_, x + at[0] + nw + gap, y + at[1], fNum, "#0d0f13", pt(3.0), "left", "middle");
  };
  ctx.save();
  if (WT.own) for (const n of WT.pre) place(n, false);
  else if (C.order) for (const n of C.order) { if (WT.re.has(n)) place(n, true); else if (C.add.includes(n)) place(n, false); }
  else { for (const n of C.re) if (WT.re.has(n)) place(n, true); if (C.buoys === "after") for (const n of C.add) place(n, false); }
  ctx.restore();
  drawBuoys(ctx, st, D, P, V, LW, LH, taken);
  ctx.save();
  if (WT.own) for (const n of WT.post) place(n, false);
  else if (C.buoys === "first") for (const n of C.add) place(n, false);
  ctx.restore();
}
const MAXH_PIDS = /^wavemax(24)?$/;   // 11-01: products with the 'Max height: NN ft' line (viewer + Studio)
const UNITS = { ssta: "\u00b0F", ivt: " kg/m/s", fog: "", waves: " ft", wavemax: " ft", ehigh: "\u00b0F", elow: "\u00b0F", d2m: "\u00b0F", feels: "\u00b0F", gustmax: " mph", t925w: "\u00b0C", t850w: "\u00b0C", t700w: "\u00b0C", t500w: "\u00b0C", t300w: "\u00b0C", w850: " kt", thick: " dam", slp: " mb", pw: " in", pwa: " in", ptype: "", qpfa: " in", qpfpct: "%", eqpf90: " in", esnow: " in", esnow90: " in", egust90: " mph", epcape: "%", elows: "%", spag: " m", nqpf1: " in", nqpf6: " in", nsnow6: " in", ntstm: "%", nmaxt: "\u00b0F", nmint: "\u00b0F", dsnod: " in", qpf3: " in", qpf12: " in", qpf48: " in", snow1: " in", snow6: " in", gust6: " mph", ltng6: " /km\u00b2/5 min", qpf1: " in", qpf6: " in", qpf24: " in", mslpqpf: " in", t2ma: "\u00b0F", t850a: "\u00b0C", et2sd: "\u00b0F", ep32: "%", ez500: " m", w500: " kt", w300: " kt", w250: " kt", z500anom: " m", mucape: " J/kg", sbcape: " J/kg", ltng: " /km\u00b2/5 min", ltgp: " in", t2m: "\u00b0F", gust10: " mph", aifswind: " mph", t850: "\u00b0C", t700: "\u00b0C", tcc: "%", vis: " mi", ir: "\u00b0C",
                refc: " dBZ", qpf: " in", snow: " in", frz: " ft", snowlvl: " ft" };
// value under the cursor / tap (item 1) and swipe to step (item 6)
function readout(ev) {
  const C = S.cur, tip = $("tip"); if (!C || !tip) return;
  const cv = $("map"), r = cv.getBoundingClientRect(), LW = cv._lw || cv.width, LH = cv._lh || cv.height, X = (ev.clientX - r.left) * LW / r.width, Y = (ev.clientY - r.top) * LH / r.height;
  const x = Math.round(X - C.st.x0), y = Math.round(Y - C.st.y0);
  if (x < 0 || y < 0 || x >= C.st.W || y >= C.st.H) { tip.hidden = true; return; }
  const k = y * C.st.W + x; let v = C.vals[k]; if (!isFinite(v)) { tip.hidden = true; return; }
  let s = (C.P.fmt ? fmtVal(C.P, v) : C.P.dec ? v.toFixed(C.P.dec) : String(Math.round(v))) + (UNITS[C.pid] || "");
  if (C.pid === "ptype") { const c = Math.round(v), t = ["Rain", "Snow", "Sleet / mix", "Freezing rain"][c >> 4], b = c & 15;
    s = c < 1 || !t || !b ? "No precip" : `${t} \u00b7 ${["", "< 0.01", "0.01-0.02", "0.02-0.05", "0.05-0.1", "0.1-0.2", "0.2-0.4", "0.4+", "0.4+"][b] || ""} in/h`; }
  if (C.D.iso && C.P.isobars) { const m = sample(C.st, C.D.iso, k), mb = !C.P.isobars.field || C.P.isobars.field === "mslp";
    if (isFinite(m)) s += mb ? ` \u00b7 ${m.toFixed(C.pid === "aifswind" ? 1 : 0)} mb` : ` \u00b7 ${Math.round(m)} ${C.P.isobars.unit || "dam"}`; }
  tip.textContent = s; tip.hidden = false;
  const wr = $("wrap").getBoundingClientRect(); tip.style.left = (ev.clientX - wr.left + 14) + "px"; tip.style.top = (ev.clientY - wr.top - 30) + "px";
}
// Zoomable map (Benjamin's saved order): wheel / trackpad pinch / two-finger pinch zooms (1-6x) at the pointer, drag pans
// when zoomed, double-click / double-tap or the "Reset zoom" button resets. At 1x a one-finger swipe still steps hours and a
// tap reads the value. The zoom is a CSS transform of the drawn map, so it costs no redraw and survives hour/product changes.
const Z = { k: 1, x: 0, y: 0 };
function applyZoom() {
  const cv = $("map"), w = cv.offsetWidth, h = cv.offsetHeight;
  Z.k = Math.min(6, Math.max(1, Z.k)); if (Z.k <= 1.001) { Z.k = 1; Z.x = 0; Z.y = 0; }
  Z.x = Math.min(0, Math.max(w * (1 - Z.k), Z.x)); Z.y = Math.min(0, Math.max(h * (1 - Z.k), Z.y));
  cv.style.transform = Z.k === 1 ? "" : `translate(${Z.x}px,${Z.y}px) scale(${Z.k})`;
  const b = $("zreset"); if (b) b.hidden = Z.k === 1;
  if (Z.ok && w && !Q.get("studio") && !Q.get("embed")) try { sessionStorage.setItem("vw:zoom", JSON.stringify({ k: Z.k, x: Z.x / w, y: Z.y / h })); } catch (e) { /* private mode */ }   // 11-04 (t2269u): kept for a refresh
  schedSharp();
}
// 11-04 (t2269u): after a refresh the map comes back at the same zoom / pan (this tab only); before that, nothing is saved
function restoreZoom(n = 0) {
  const cv = $("map"); if (!cv || !cv.offsetWidth || !window.__drawn || n < 3) { if (n < 150) setTimeout(() => restoreZoom(n + 1), 100); else Z.ok = true; return; }
  let z = null; try { z = Q.get("studio") || Q.get("embed") ? null : JSON.parse(sessionStorage.getItem("vw:zoom") || "null"); } catch (e) { z = null; }
  Z.ok = true; if (z && z.k > 1) { Z.k = z.k; Z.x = z.x * cv.offsetWidth; Z.y = z.y * cv.offsetHeight; applyZoom(); }
}
function resetZoom() { Z.k = 1; Z.x = 0; Z.y = 0; applyZoom(); }
function zoomAt(cx, cy, k2) {   // keep the map point under (cx, cy) fixed
  const cv = $("map"), r = cv.getBoundingClientRect(), l0 = r.left - Z.x, t0 = r.top - Z.y;
  const px = (cx - l0 - Z.x) / Z.k, py = (cy - t0 - Z.y) / Z.k; k2 = Math.min(6, Math.max(1, k2));
  Z.x = cx - l0 - px * k2; Z.y = cy - t0 - py * k2; Z.k = k2; applyZoom();
}
function setupPointer() {
  restoreZoom();
  const cv = $("map"), P = new Map(); let down = null, pinch = null, lastTap = 0, moved = false;
  cv.style.transformOrigin = "0 0";
  const wr = $("wrap"); wr.style.overflow = "hidden";
  if (!$("zreset")) { const b = document.createElement("button"); b.id = "zreset"; b.type = "button"; b.textContent = "Reset zoom"; b.hidden = true; b.onclick = resetZoom; wr.appendChild(b); }
  cv.addEventListener("wheel", e => { e.preventDefault(); zoomAt(e.clientX, e.clientY, Z.k * Math.exp(-e.deltaY * (e.ctrlKey ? 0.01 : 0.0015))); }, { passive: false });
  cv.addEventListener("dblclick", e => { e.preventDefault(); if (Z.k > 1) resetZoom(); else zoomAt(e.clientX, e.clientY, 2.5); });
  cv.addEventListener("pointermove", e => {
    if (e.pointerType === "mouse" && !P.size) readout(e);
    if (!P.has(e.pointerId)) return; const p0 = P.get(e.pointerId); P.set(e.pointerId, { x: e.clientX, y: e.clientY });
    if (TP.on) { moved = true; return; }   // a touch pinch is handled by the touch handlers below (iPhone)
    if (P.size >= 2 && pinch) {
      const [a, b] = [...P.values()], d = Math.hypot(a.x - b.x, a.y - b.y), mx = (a.x + b.x) / 2, my = (a.y + b.y) / 2;
      zoomAt(pinch.mx, pinch.my, pinch.k * d / pinch.d); Z.x += mx - pinch.mx; Z.y += my - pinch.my; pinch.mx = mx; pinch.my = my; pinch.k = Z.k; pinch.d = d; applyZoom();
      moved = true; if ($("tip")) $("tip").hidden = true;
    } else if (P.size === 1 && Z.k > 1 && down) {
      Z.x += e.clientX - p0.x; Z.y += e.clientY - p0.y; applyZoom();
      if (Math.hypot(e.clientX - down.x, e.clientY - down.y) > 6) { moved = true; if ($("tip")) $("tip").hidden = true; }
    }
  });
  cv.addEventListener("pointerleave", () => { if ($("tip")) $("tip").hidden = true; });
  cv.addEventListener("pointerdown", e => {
    P.set(e.pointerId, { x: e.clientX, y: e.clientY }); try { cv.setPointerCapture(e.pointerId); } catch (_) {}
    if (P.size === 1) { down = { x: e.clientX, y: e.clientY, t: performance.now() }; moved = false; }
    if (P.size === 2) { const [a, b] = [...P.values()]; pinch = { d: Math.max(10, Math.hypot(a.x - b.x, a.y - b.y)), k: Z.k, mx: (a.x + b.x) / 2, my: (a.y + b.y) / 2 }; down = null; moved = true; }
  });
  const up = e => {
    P.delete(e.pointerId); if (P.size < 2) pinch = null;
    if (!down || P.size) { if (!P.size) down = null; return; }
    const dx = e.clientX - down.x, dy = e.clientY - down.y, d0 = down; down = null;
    if (e.type === "pointercancel" || moved) return;
    if (Z.k === 1 && Math.abs(dx) > 40 && Math.abs(dx) > 1.5 * Math.abs(dy)) { go(dx < 0 ? 1 : -1); return; }
    if (e.pointerType !== "mouse") {   // double-tap: zoom in 2.5x there, or reset when zoomed
      const now = performance.now(); if (now - lastTap < 300) { lastTap = 0; if (Z.k > 1) resetZoom(); else zoomAt(e.clientX, e.clientY, 2.5); return; }
      lastTap = now;
    }
    readout(e);
  };
  cv.addEventListener("pointerup", up); cv.addEventListener("pointercancel", up);
  addEventListener("resize", applyZoom);
  setupTouchPinch(wr, () => { moved = true; down = null; pinch = null; });
}
// 10-31 1:39 PM (Benjamin, iPhone: "zoom in and out on the map by pulling my thumbs apart or closer together"). The pointer pinch
// above only saw fingers that landed on the map canvas, and on a phone the map is ~250 px tall, so the second thumb often landed
// beside it and Safari zoomed the whole page instead. Touch pinch now: two fingers anywhere on the map area (#wrap, plus a 40 px
// margin around it) zoom the map about the midpoint of the fingers, and moving both fingers pans it; Safari's page zoom is
// blocked only while a map pinch is running (and for gestures that start on the map), so page zoom elsewhere is unchanged.
// One finger is untouched: swipe steps hours at 1x, drags when zoomed, tap reads the value, double-tap zooms.
const TP = { on: false, d: 0, mx: 0, my: 0 };
function setupTouchPinch(wr, onStart) {
  if (!("ontouchstart" in window)) return;
  const near = (t) => { const r = wr.getBoundingClientRect(), m = 40; return t.clientX > r.left - m && t.clientX < r.right + m && t.clientY > r.top - m && t.clientY < r.bottom + m; };
  const mid = (a, b) => [(a.clientX + b.clientX) / 2, (a.clientY + b.clientY) / 2];
  document.addEventListener("touchstart", (e) => {
    if (e.touches.length !== 2 || (!TP.on && !(near(e.touches[0]) || near(e.touches[1])))) return;
    if (document.body.classList.contains("embed") && !wr.contains(e.target)) return;
    const [a, b] = e.touches; [TP.mx, TP.my] = mid(a, b); if (!TP.on && !near({ clientX: TP.mx, clientY: TP.my })) return;
    TP.on = true; TP.d = Math.max(10, Math.hypot(a.clientX - b.clientX, a.clientY - b.clientY)); onStart(); e.preventDefault();
    if ($("tip")) $("tip").hidden = true;
  }, { passive: false });
  document.addEventListener("touchmove", (e) => {
    if (!TP.on) return; e.preventDefault(); if (e.touches.length < 2) return;
    const [a, b] = e.touches, d = Math.max(10, Math.hypot(a.clientX - b.clientX, a.clientY - b.clientY)), [mx, my] = mid(a, b);
    zoomAt(TP.mx, TP.my, Z.k * d / TP.d); Z.x += mx - TP.mx; Z.y += my - TP.my; applyZoom();
    TP.d = d; TP.mx = mx; TP.my = my; window.__pinch = { k: Z.k, x: Z.x, y: Z.y };
  }, { passive: false });
  const end = (e) => { if (TP.on && e.touches.length < 2) { TP.on = false; if (e.cancelable) e.preventDefault(); } };
  document.addEventListener("touchend", end, { passive: false }); document.addEventListener("touchcancel", end, { passive: false });
  // iOS Safari page-zoom gesture: cancel it while a map pinch runs or when it starts on the map
  for (const ev of ["gesturestart", "gesturechange"]) document.addEventListener(ev, (e) => { if (TP.on || wr.contains(e.target)) e.preventDefault(); }, { passive: false });
}
// "Save image" (Benjamin 10-29-26 7:48 PM): the map exactly as drawn (base, data, towns, key, title/time; no controls)
// as a PNG at the map's full size. Phones: share sheet with the file (iOS "Save Image"); no file sharing: long-press view
// (touch) or a download (desktop).
function saveName() {
  const [m, c] = S.run.split("/"), st = S.runs[S.run].steps[S.i], v = new Date(st.valid);
  const P = Object.fromEntries(new Intl.DateTimeFormat("en-US", { timeZone: "America/Los_Angeles", year: "numeric", month: "2-digit", day: "2-digit",
    hour: "2-digit", minute: "2-digit", hourCycle: "h23" }).formatToParts(v).map(x => [x.type, x.value]));
  const clean = t => String(t).replace(/[^A-Za-z0-9.+-]+/g, "-").replace(/^-|-$/g, "");
  return `${clean(S.man.models[m].site)}_${c.slice(8)}Z_${clean(S.prod)}_${clean(S.view)}_valid-${P.year}-${P.month}-${P.day}_${P.hour}${P.minute}PT_F${String(st.f).padStart(3, "0")}.png`;
}
function closeSaveView() { const o = $("saveview"); if (o) { URL.revokeObjectURL(o.dataset.url || ""); o.remove(); } }
// 11-03-26 (Benjamin t2242u: "when I zoom in on a map, whatever level I'm zoomed in, when I click the save image, it saves at the zoom
// in full res with the credit line at the zoomed crop"). Unzoomed: exactly as before. Zoomed: the map is redrawn once at a save
// resolution (RS up to 6; at most 48 MP desktop / 16 MP phones), the part you see is cut out, the title + color key strip is put
// on top (scaled to the crop width) and the credit lines are rewritten under the crop, wrapping to more lines when needed.
// The zoom (Z) is only read, never changed; afterwards the map is redrawn at the normal screen sharpness.
let saving = false;
async function saveImage() {
  const cv = $("map"); if (!cv.width || saving) return;
  if (Z.k <= 1.001) { saveCanvas(cv, saveName(), $("save")); return; }
  const btn = $("save"), V = VIEWS()[S.view], [LW, LH] = V.fig, touch = matchMedia("(pointer: coarse)").matches;
  const z = { k: Z.k, x: Z.x, y: Z.y };
  const cap = Math.sqrt((touch ? 16e6 : 48e6) / (LW * LH)), rs = Math.max(cv._rs || 1, Math.min(6, cap, Math.max(2, z.k * 1.5)));
  saving = true; if (btn) btn.textContent = "Saving\u2026";
  let out = null;
  try {
    window.__saveRS = Math.floor(rs * 4) / 4; await draw();
    const R = cv._rs, st = await viewStatic(S.view), P = PRODS()[S.prod];
    // the part on screen: the map box (zoomed) clipped to the map area, in figure px
    const r = cv.getBoundingClientRect(), wr = $("wrap").getBoundingClientRect();
    const cl = (v, a) => Math.max(0, Math.min(a, v)), fx = cl((wr.left - r.left) / r.width * LW, LW), fy = cl((wr.top - r.top) / r.height * LH, LH);
    const fw = cl((wr.right - r.left) / r.width * LW, LW) - fx, fh = cl((wr.bottom - r.top) / r.height * LH, LH) - fy;
    const sx = Math.max(0, Math.round(fx * R)), sy = Math.max(0, Math.round(fy * R));
    const W = Math.min(cv.width - sx, Math.round(fw * R)), H = Math.min(cv.height - sy, Math.round(fh * R));
    const hs = fy > st.y0 * 0.5 ? W / (LW * R) : 0, HH = Math.round(st.y0 * R * hs);   // title + key strip (skipped when it is already in view)
    const towns = st.towns && (P.towns || "numbers") !== "none", L0 = creditLines(S.prod, P, towns);
    const fs = Math.max(13, Math.round(Math.min(W, 2400) / 95)), font = `500 ${fs}px Montserrat`, mg = new OffscreenCanvas(8, 8).getContext("2d"); mg.font = font;
    const lines = []; for (const t of L0) { let cur = ""; for (const wd of t.split(" ")) { const tt = cur ? cur + " " + wd : wd; if (cur && mg.measureText(tt).width > W - fs * 1.6) { lines.push(cur); cur = wd; } else cur = tt; } if (cur) lines.push(cur); }
    const lh = Math.round(fs * 1.3), strip = Math.round(fs * 0.9) + lines.length * lh;
    out = document.createElement("canvas"); out.width = W; out.height = HH + H + strip;
    const g = out.getContext("2d"); g.imageSmoothingEnabled = true; g.imageSmoothingQuality = "high";
    g.fillStyle = S.man.style.BG; g.fillRect(0, 0, out.width, out.height);
    if (HH) g.drawImage(cv, 0, 0, cv.width, Math.round(st.y0 * R), 0, 0, W, HH);
    g.drawImage(cv, sx, sy, W, H, 0, HH, W, H);
    g.font = font; g.fillStyle = S.man.style.MUTED; g.textAlign = "left"; g.textBaseline = "alphabetic";
    lines.forEach((l, i) => g.fillText(l, Math.round(fs * 0.8), HH + H + Math.round(fs * 0.45) + (i + 1) * lh - Math.round(fs * 0.3)));
    window.__saveInfo = { w: out.width, h: out.height, rs: R, crop: [sx, sy, W, H], head: HH, lines };
  } catch (e) { showErr(e); }
  finally {
    window.__saveRS = 0; saving = false;
    if (Z.k !== z.k || Z.x !== z.x || Z.y !== z.y) { Z.k = z.k; Z.x = z.x; Z.y = z.y; applyZoom(); }   // never expected; zoom stays as you left it
    draw(); if (btn) btn.textContent = "Save image";
  }
  if (out) saveCanvas(out, saveName().replace(/\.png$/, `_zoom${z.k.toFixed(1)}x.png`), btn);
}
// shared by the map, the meteogram and the Pass Forecaster (Benjamin 10-31 8:49 AM "push to save passes meteograms graphics")
function saveCanvas(cv, name, btn) {
  // synchronous encode keeps the tap's user activation for navigator.share (iOS Safari is strict about it)
  const durl = cv.toDataURL("image/png"), bin = atob(durl.split(",")[1]), u8 = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) u8[i] = bin.charCodeAt(i);
  const blob = new Blob([u8], { type: "image/png" }), file = new File([blob], name, { type: "image/png" });
  const touch = matchMedia("(pointer: coarse)").matches;
  if (touch && navigator.canShare && navigator.share && navigator.canShare({ files: [file] })) {
    navigator.share({ files: [file], title: name }).catch(e => { if (e && e.name !== "AbortError") showSaveView(blob, name); });
    return;
  }
  if (touch) { showSaveView(blob, name); return; }
  const a = document.createElement("a"), url = URL.createObjectURL(blob); a.href = url; a.download = name;
  document.body.appendChild(a); a.click(); a.remove(); setTimeout(() => URL.revokeObjectURL(url), 4000);
  if (btn) { btn.textContent = "Saved"; setTimeout(() => btn.textContent = "Save image", 1500); }
}
// ---- meteogram / Pass Forecaster "Save image": the graphic plus a header with place, model and run time, as a PNG
const fileClean = t => String(t).replace(/[^A-Za-z0-9.+-]+/g, "-").replace(/^-|-$/g, "");
function mgRunText(run) {
  const [m, c] = run.split("/"), t = new Date(Date.UTC(+c.slice(0, 4), +c.slice(4, 6) - 1, +c.slice(6, 8), +c.slice(8)));
  return `${S.man.models[m].site} ${c.slice(8)}Z run ${fmtPT(t.toISOString(), { month: "numeric", day: "numeric", year: "2-digit" }).replace(/\//g, "-")} (${fmtPT(t.toISOString(), { hour: "numeric" })} PT)`;
}
function mgHeader(c, W, title, sub) {
  c.fillStyle = "#15171c"; c.fillRect(0, 0, W, 64); c.textBaseline = "top";
  c.font = "800 20px Montserrat"; c.fillStyle = "#f4f2ee"; c.fillText(title, 16, 10);
  c.font = "600 13px Montserrat"; c.fillStyle = "#ffd27a"; c.fillText(sub, 16, 38);
  c.font = "600 12px Montserrat"; c.fillStyle = "#a7abb3"; c.textAlign = "right"; c.fillText("WX Models", W - 16, 12); c.textAlign = "left";
  c.fillStyle = "#2c3039"; c.fillRect(0, 63, W, 1);
}
function passCanvas(body, title, sub) {   // the Pass Forecaster table (cells, colors, notes) redrawn on a canvas
  const tb = body.querySelector("table.pf"); if (!tb) return null;
  const note = [...body.querySelectorAll(".mg-note")].map(e => e.innerText.trim()).filter(Boolean).join("  ").replace(/\s*Tap a pass for its meteogram\.?/i, "");
  const rows = [...tb.rows].map(r => [...r.cells].map(td => { const cs = getComputedStyle(td); return { t: td.innerText.trim().split("\n"), bg: cs.backgroundColor, fg: cs.color, th: td.tagName === "TH" }; }));
  const m = document.createElement("canvas").getContext("2d"), F = (th, i) => `${th || i === 0 ? 700 : 500} 13px Montserrat`, SM = "500 11px Montserrat";
  const nc = Math.max(...rows.map(r => r.length)), cw = Array(nc).fill(60);
  rows.forEach(r => r.forEach((cell, j) => cell.t.forEach((ln, k) => { m.font = k ? SM : F(cell.th, j); cw[j] = Math.max(cw[j], m.measureText(ln).width + 18); })));
  const rh = r => 10 + Math.max(...r.map(cell => cell.t.length)) * 16, W = Math.max(720, Math.ceil(cw.reduce((a, b) => a + b, 0)) + 32);
  m.font = "500 12px Montserrat"; const words = note.split(/\s+/), lines = []; let ln = "";
  for (const w of words) { const t = ln ? ln + " " + w : w; if (m.measureText(t).width > W - 32 && ln) { lines.push(ln); ln = w; } else ln = t; } if (ln) lines.push(ln);
  const H = 64 + 12 + lines.length * 17 + 10 + rows.reduce((a, r) => a + rh(r), 0) + 16, dpr = 2;
  const cv = document.createElement("canvas"); cv.width = W * dpr; cv.height = H * dpr; const c = cv.getContext("2d"); c.scale(dpr, dpr);
  c.fillStyle = "#15171c"; c.fillRect(0, 0, W, H); mgHeader(c, W, title, sub);
  let y = 76; c.font = "500 12px Montserrat"; c.fillStyle = "#a7abb3"; c.textBaseline = "top"; lines.forEach(l => { c.fillText(l, 16, y); y += 17; }); y += 10;
  for (const r of rows) { const h = rh(r); let x = 16;
    r.forEach((cell, j) => { const bg = cell.bg && !/rgba\(0, 0, 0, 0\)|transparent/.test(cell.bg) ? cell.bg : (cell.th ? "#1d2027" : "#15171c");
      c.fillStyle = bg; c.fillRect(x, y, cw[j], h); c.strokeStyle = "#2c3039"; c.strokeRect(x + 0.5, y + 0.5, cw[j], h);
      cell.t.forEach((t, k) => { c.font = k ? SM : F(cell.th, j); c.fillStyle = k ? "#a7abb3" : (cell.fg || "#f4f2ee"); c.fillText(t, x + 9, y + 6 + k * 16); });
      x += cw[j]; });
    y += h; }
  return cv;
}
function mgSave() {
  const btn = $("mgsave"), sub = mgRunText(MG.run), [m, c] = MG.run.split("/");
  if (MG.open === "pass") {
    const cv = passCanvas($("mgbody"), "Pass Forecaster \u2013 Washington mountain passes", sub); if (!cv) return;
    return saveCanvas(cv, `Pass-Forecaster_${fileClean(S.man.models[m].site)}_${c}Z.png`, btn);
  }
  const ch = $("mgc"); if (!ch || !ch.width) return;
  const dpr = ch.width / ch.clientWidth || 1, W = ch.clientWidth, H = ch.clientHeight, cv = document.createElement("canvas");
  cv.width = W * dpr; cv.height = (H + 64) * dpr; const g = cv.getContext("2d"); g.scale(dpr, dpr);
  const isPass = /pass/i.test($("mgtown") && $("mgtown").selectedOptions[0] && $("mgtown").selectedOptions[0].parentNode.label || "");
  const place = isPass && !/pass/i.test(MG.town) ? `${MG.town} Pass` : MG.town;
  mgHeader(g, W, `${place} meteogram`, sub); g.drawImage(ch, 0, 64, W, H);
  saveCanvas(cv, `${fileClean(place)}_${fileClean(S.man.models[m].site)}_${c}Z.png`, btn);
}
function showSaveView(blob, name) {   // fallback: full-screen image to press and hold (Save to Photos / Download Image)
  closeSaveView(); const url = URL.createObjectURL(blob), o = document.createElement("div"); o.id = "saveview"; o.dataset.url = url;
  o.innerHTML = `<div class="sv-top"><span>Press and hold the map, then choose Save Image</span><a download="${name}" href="${url}">Download</a><button type="button">Close</button></div><img alt="${name}" src="${url}">`;
  o.querySelector("button").onclick = closeSaveView; document.body.appendChild(o);
}
async function share() {
  const u = location.href;
  try { if (navigator.share) await navigator.share({ title: document.title, url: u }); else { await navigator.clipboard.writeText(u); $("share").textContent = "Copied"; setTimeout(() => $("share").textContent = "Share", 1500); } } catch (e) {}
}
// Peak gust tag (Benjamin 10-31 1:53 AM "on the wind gust maps, include a peak wind gust number in one corner of the map"): the
// highest value of the plotted field over the visible map (every drawn pixel, so it follows the view's crop), rounded to mph,
// in a dark box in the map's lower-right corner, clear of the title, key, F badge and Save/Share (those sit above the map).
const GUST_PIDS = /^(gust(6|10|12|24|max)|egust90)$/;
function drawPeak(ctx, st, vals) {
  let hi = -Infinity; for (let k = 0; k < vals.length; k++) { const v = vals[k]; if (v > hi) hi = v; }
  if (!isFinite(hi)) return null;
  const v = Math.round(hi), s = `Peak gust: ${v} mph`, pad = pt(5), fs = pt(16);
  ctx.font = `800 ${fs}px Montserrat`; const w = ctx.measureText(s).width + 2 * pad, h = fs + 2 * pad;
  const x = st.x0 + st.W - w - pt(5), y = st.y0 + st.H - h - pt(5);
  ctx.fillStyle = "rgba(20,22,28,0.82)"; ctx.strokeStyle = "rgba(255,255,255,0.85)"; ctx.lineWidth = pt(0.8);
  ctx.beginPath(); if (ctx.roundRect) ctx.roundRect(x, y, w, h, pt(4)); else ctx.rect(x, y, w, h); ctx.fill(); ctx.stroke();
  ctx.fillStyle = "#ffffff"; ctx.textAlign = "left"; ctx.textBaseline = "middle"; ctx.fillText(s, x + pad, y + h / 2 + pt(0.5));
  return v;
}
function haloText(ctx, s, x, y, font, color, halo, align, base) {
  ctx.font = font; ctx.textAlign = align; ctx.textBaseline = base; ctx.lineJoin = "round";
  ctx.strokeStyle = "#ffffff"; ctx.lineWidth = halo; ctx.strokeText(s, x, y); ctx.fillStyle = color; ctx.fillText(s, x, y);
}

function fitFont(ctx, s, weight, size, maxw, min) {
  let z = size; for (; z > min; z -= 0.5) { ctx.font = `${weight} ${pt(z)}px Montserrat`; if (ctx.measureText(s).width <= maxw) break; }
  return `${weight} ${pt(z)}px Montserrat`;
}
function header(ctx, V, title, valid, sub, badge) {   // house_style.header, text only (box + badge shape are in the base layer)
  const [W, H] = V.fig, Hin = V.size_in[1], top = 0.985, h = 0.095, bw = 0.118, bh = h - 0.012, x = 0.024 * W;
  const Y = fr => (1 - fr) * H;
  ctx.textAlign = "left"; ctx.textBaseline = "top";
  ctx.fillStyle = S.man.style.INK; ctx.font = `800 ${pt(25)}px Montserrat`; ctx.fillText(title, x, Y(top - 0.004));
  ctx.fillStyle = S.man.style.ACCENT; ctx.font = `700 ${pt(18)}px Montserrat`; ctx.fillText(valid, x, Y(top - 0.040 * 12 / Hin));
  ctx.fillStyle = S.man.style.MUTED; ctx.font = fitFont(ctx, sub, 500, 12.5, (0.988 - bw - 0.012 - 0.024) * W, 9.5); ctx.fillText(sub, x, Y(top - 0.068 * 12 / Hin));
  ctx.textAlign = "center"; ctx.textBaseline = "middle"; const cx = (0.988 - bw / 2) * W;
  ctx.fillStyle = S.man.style.INK; ctx.font = `800 ${pt(26)}px Montserrat`; ctx.fillText(badge[0], cx, Y(top - bh * 0.40));
  ctx.fillStyle = S.man.style.MUTED; ctx.font = `600 ${pt(10.5)}px Montserrat`; ctx.fillText(badge[1], cx, Y(top - bh * 0.80));
}

// per-frame line geometry (isobars, H/L, ensemble height lines), so scrubbing back and forth redraws lines for free
const GEO = new Map();
function geo(key, make) {
  if (GEO.has(key)) { const v = GEO.get(key); GEO.delete(key); GEO.set(key, v); return v; }
  const v = make(); GEO.set(key, v); if (GEO.size > 160) GEO.delete(GEO.keys().next().value); return v;
}
// contour grid: panel pixels every s px (what contour() reads)
function cgrid(st, s, at) {
  const W = st.W, H = st.H, nx = Math.floor((W - 1) / s) + 1, ny = Math.floor((H - 1) / s) + 1, g = new Float32Array(nx * ny);
  for (let j = 0; j < ny; j++) for (let i = 0; i < nx; i++) g[j * nx + i] = at((j * s) * W + i * s);
  return { g, nx, ny, s };
}
// marching squares on panel pixels (every s px), segments joined into polylines (canvas coords)
function contour(st, vals, level, s) { return contourG(st, cgrid(st, s, k => vals[k]), level); }
function contourG(st, G, level) {
  const { g, nx, ny, s } = G;
  const segs = [];
  const P = (i, j) => [st.x0 + i * s, st.y0 + j * s];
  const lerp = (a, b, va, vb) => { const t = (level - va) / (vb - va); return [a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t]; };
  for (let j = 0; j < ny - 1; j++) for (let i = 0; i < nx - 1; i++) {
    const a = g[j * nx + i], b = g[j * nx + i + 1], c = g[(j + 1) * nx + i + 1], d = g[(j + 1) * nx + i];
    if (!(isFinite(a) && isFinite(b) && isFinite(c) && isFinite(d))) continue;
    const code = (a > level) | ((b > level) << 1) | ((c > level) << 2) | ((d > level) << 3);
    if (code === 0 || code === 15) continue;
    const pa = P(i, j), pb = P(i + 1, j), pc = P(i + 1, j + 1), pd = P(i, j + 1);
    const e = { t: () => lerp(pa, pb, a, b), r: () => lerp(pb, pc, b, c), b: () => lerp(pd, pc, d, c), l: () => lerp(pa, pd, a, d) };
    const add = (x, y) => segs.push([e[x](), e[y]()]);
    switch (code) {
      case 1: case 14: add("l", "t"); break; case 2: case 13: add("t", "r"); break; case 3: case 12: add("l", "r"); break;
      case 4: case 11: add("r", "b"); break; case 6: case 9: add("t", "b"); break; case 7: case 8: add("l", "b"); break;
      case 5: add("l", "t"); add("r", "b"); break; case 10: add("t", "r"); add("l", "b"); break;
    }
  }
  // join segments into polylines by shared end points
  const kf = p => `${Math.round(p[0] * 64)},${Math.round(p[1] * 64)}`, ends = new Map();
  segs.forEach((sg, n) => { for (const e of [0, 1]) { const k = kf(sg[e]); if (!ends.has(k)) ends.set(k, []); ends.get(k).push(n); } });
  const used = new Uint8Array(segs.length), lines = [];
  for (let n = 0; n < segs.length; n++) {
    if (used[n]) continue; used[n] = 1; const line = [segs[n][0], segs[n][1]];
    for (const dir of [1, 0]) {
      for (;;) {
        const tip = dir ? line[line.length - 1] : line[0], cand = (ends.get(kf(tip)) || []).find(m => !used[m]);
        if (cand === undefined) break; used[cand] = 1; const sg = segs[cand];
        const nxt = kf(sg[0]) === kf(tip) ? sg[1] : sg[0]; dir ? line.push(nxt) : line.unshift(nxt);
      }
    }
    lines.push(line);
  }
  return lines;
}
function strokeLines(ctx, lines, color, lw, dash) {
  ctx.strokeStyle = color; ctx.lineWidth = lw; ctx.lineJoin = "round"; ctx.lineCap = dash ? "butt" : "round"; ctx.setLineDash(dash || []);
  ctx.beginPath(); for (const l of lines) { ctx.moveTo(l[0][0], l[0][1]); for (let k = 1; k < l.length; k++) ctx.lineTo(l[k][0], l[k][1]); }
  ctx.stroke(); ctx.setLineDash([]);
}

function coastTaken(st, D, P, V, LW, LH) {   // boxes the coast towns + buoys will take (drawCoast on a 1 px scratch canvas)
  const c = document.createElement("canvas"); c.width = c.height = 1; const x = c.getContext("2d"), k0 = window.__coast, b0 = window.__buoyLog;
  try { const W2 = coastPlan(x, st, V, LW, LH); drawCoast(x, st, D, P, V, LW, LH, W2); return W2.taken || []; } catch (e) { return []; }
  finally { window.__coast = k0; window.__buoyLog = b0; }
}
function drawIsobars(ctx, st, D, P, gk, V, extraAvoid) {
  // 11-01 7:26 PM (Benjamin t2052u: "make sure it doesn't overlap other MSLP numbers, move other MSLP numbers out of the way"):
  // the H / L (or ensemble mean L) marker boxes are reserved first; isobar numbers that would land on one slide along their line
  const I = P.isobars, avoid = hlAvoid(ctx, st, D, P, V, gk);
  const { all, labels } = geo(`iso/${gk}`, () => isoGeom(ctx, st, D, I, extraAvoid ? avoid.concat(extraAvoid()) : avoid));
  paintIsobars(ctx, I, all, labels);
}
function isoGeom(ctx, st, D, I, avoid) {
  const G = cgrid(st, 4, k => sample(st, D.iso, k)), iso = G.g;   // only the 4 px points contour() reads: same lines
  let lo = Infinity, hi = -Infinity;
  for (let k = 0; k < iso.length; k++) { const v = iso[k]; if (v < lo) lo = v; if (v > hi) hi = v; }
  const labels = [], all = [], sep = I.lab_sep || 120, sfx = I.suffix || "";
  ctx.save(); ctx.font = isoLabFont(I);
  for (let L = Math.max(Math.ceil(lo / I.every) * I.every, I.min ?? -Infinity); L <= hi; L += I.every) {   // min: Radar + UH rings start at 75
    let lines = contourG(st, G, L);
    if (I.min_len) lines = lines.filter(l => { let n = 0; for (let k = 1; k < l.length && n < I.min_len; k++) n += Math.hypot(l[k][0] - l[k - 1][0], l[k][1] - l[k - 1][1]); return n >= I.min_len; });   // 11-03 swell lines: no specks
    all.push(lines);
    for (const l of lines) {   // one label per ~600 px of line, inline (line cut under the label)
      let len = 0; const cum = [0]; for (let k = 1; k < l.length; k++) { len += Math.hypot(l[k][0] - l[k - 1][0], l[k][1] - l[k - 1][1]); cum.push(len); }
      if (len < 160) continue;
      const nlab = Math.max(1, Math.floor(len / (I.lab_gap || 600)));
      for (let q = 0; q < nlab; q++) {
        const target0 = len * (q + 0.5) / nlab, w = ctx.measureText(String(L) + sfx).width + pt(6);
        // first the usual spot; if it sits on an H / L marker, the nearest clear spot along the line (both ways, up to LAB_SLIDE px)
        const tries = [0]; if (avoid && avoid.length) for (let d = 12; d <= LAB_SLIDE; d += 12) tries.push(d, -d);
        for (const dt of tries) {
          const target = target0 + dt; if (target < 0 || target > len) continue;
          const k = cum.findIndex(c => c >= target), p = l[Math.max(0, k)];
          if (labels.some(b => Math.hypot(b.x - p[0], b.y - p[1]) < sep)) { if (dt === 0) break; continue; }
          if (p[0] < st.x0 + 20 || p[0] > st.x0 + st.W - 20 || p[1] < st.y0 + 12 || p[1] > st.y0 + st.H - 12) { if (dt === 0) break; continue; }
          const a = l[Math.max(0, k - 3)], b = l[Math.min(l.length - 1, k + 3)]; let ang = Math.atan2(b[1] - a[1], b[0] - a[0]);
          if (ang > Math.PI / 2) ang -= Math.PI; if (ang < -Math.PI / 2) ang += Math.PI;
          if (avoid && avoid.length) { const c = Math.abs(Math.cos(ang)), s_ = Math.abs(Math.sin(ang)), ex = c * w / 2 + s_ * pt(6), ey = s_ * w / 2 + c * pt(6);
            if (avoid.some(B => p[0] + ex > B[0] && p[0] - ex < B[2] && p[1] + ey > B[1] && p[1] - ey < B[3])) continue; }
          labels.push({ x: p[0], y: p[1], ang, s: String(L) + sfx, w }); break;
        }
      }
    }
  }
  ctx.restore();
  return { all, labels };
}
function paintIsobars(ctx, I, all, labels) {
  // 11-03: Studio hides line labels that would sit under its color bar / credit rows (window.studioLabelHidden, studio.js); lines stay
  if (window.studioLabelHidden && Q.get("studio")) labels = labels.filter(b => { try { const c = Math.abs(Math.cos(b.ang || 0)), s_ = Math.abs(Math.sin(b.ang || 0)), hh = pt(I.lab_pt ? I.lab_pt * 0.6 : 6);   // 11-03 t2254u: the label's rotated half-size too (a vertical "12 s" reached into the bar)
    return !window.studioLabelHidden(b.x, b.y, c * b.w / 2 + s_ * hh, s_ * b.w / 2 + c * hh); } catch (e) { return true; } });
  ctx.save();   // clip out label boxes so lines break under the numbers (matplotlib clabel inline)
  ctx.beginPath(); ctx.rect(0, 0, ctx.canvas.width, ctx.canvas.height);
  for (const b of labels) {
    const c = Math.cos(b.ang), s = Math.sin(b.ang), hw = b.w / 2, hh = pt(I.lab_pt ? I.lab_pt * 0.6 : 6);
    const pts = [[-hw, -hh], [hw, -hh], [hw, hh], [-hw, hh]].map(([x, y]) => [b.x + x * c - y * s, b.y + x * s + y * c]);
    ctx.moveTo(...pts[0]); for (let k = 3; k >= 1; k--) ctx.lineTo(...pts[k]); ctx.closePath();   // opposite winding
  }
  ctx.clip("nonzero");
  for (const lines of all) strokeLines(ctx, lines, "#ffffff", pt(I.halo), null);
  for (const lines of all) strokeLines(ctx, lines, I.color, pt(I.lw), null);
  ctx.restore();
  for (const b of labels) {
    ctx.save(); ctx.translate(b.x, b.y); ctx.rotate(b.ang);
    if (I.shadow_lab) {   // 11-03 (Benjamin t2151u "make the swell period more clear"): white bold numbers, dark core + tight drop shadow (Studio text style)
      ctx.font = isoLabFont(I); ctx.textAlign = "center"; ctx.textBaseline = "middle"; ctx.lineJoin = "round";
      ctx.shadowColor = "rgba(0,0,0,0.9)"; ctx.shadowBlur = pt(1.2); ctx.shadowOffsetX = ctx.shadowOffsetY = pt(1.1);
      ctx.strokeStyle = "#0d0f13"; ctx.lineWidth = pt(2.4); ctx.strokeText(b.s, 0, 0);
      ctx.shadowColor = "transparent"; ctx.fillStyle = "#ffffff"; ctx.fillText(b.s, 0, 0);
    } else haloText(ctx, b.s, 0, 0, `700 ${pt(10)}px Montserrat`, I.color, pt(3.2), "center", "middle");
    ctx.restore();
  }
}
function isoLabFont(I) { return I && I.lab_pt ? `800 ${pt(I.lab_pt)}px Montserrat` : `700 ${pt(10)}px Montserrat`; }

function drawBarbs(ctx, st, D, P, V) {   // matplotlib barbs (length 5.6 pt, 5 kt rounding, flags 50 / barbs 10 / half 5)
  const B = P.barbs, nx = V.barbs_across, ny = Math.max(4, Math.round(nx * st.H / st.W)), Lp = B.length * 3.21 * S.man.dpi / 72;   // matplotlib barb units: 5.6 -> 25 px at 100 dpi (measured)
  const u = D.raw[B.u || "u10"].v, v = D.raw[B.v || "v10"].v;
  ctx.strokeStyle = B.color; ctx.fillStyle = B.color; ctx.lineWidth = pt(B.lw); ctx.lineJoin = "miter";
  const L = V, lutA = st.lut;
  for (let j = 0; j < ny; j++) for (let i = 0; i < nx; i++) {
    const x = (st.W - 1) * i / (nx - 1), y = (st.H - 1) * (1 - j / (ny - 1)), k = Math.round(y) * st.W + Math.round(x);
    const uu = sample(st, u, k), vv = sample(st, v, k); if (!isFinite(uu)) continue;
    const li = Math.min(L.nx - 1, Math.round(x / L.stride)), lj = Math.min(L.ny - 1, Math.round(y / L.stride)), a = lutA[(lj * L.nx + li) * 3 + 2];
    const nX = Math.cos(a), nY = -Math.sin(a);           // north, y up
    const eX = nY, eY = -nX;                              // east = north turned clockwise
    const wx = uu * eX + vv * nX, wy = uu * eY + vv * nY, sp = Math.hypot(uu, vv);
    if (B.arrows) { if (sp >= (B.min || 0)) arrow(ctx, st.x0 + x, st.y0 + y, wx / sp, wy / sp, B.fixed ? Lp * 0.9 : Lp * (0.55 + 0.75 * Math.min(1, sp / (B.ref || sp)))); }
    else barb(ctx, st.x0 + x, st.y0 + y, wx, wy, sp, Lp);
  }
}
function arrow(ctx, X, Y, dx, dy, L) {   // flow arrow centred on (X, Y), pointing downstream (dx, dy y-up unit vector)
  const x1 = X + dx * L / 2, y1 = Y - dy * L / 2, x0 = X - dx * L / 2, y0 = Y + dy * L / 2, h = Math.max(4, 0.3 * L), w = 0.45 * h;
  ctx.beginPath(); ctx.moveTo(x0, y0); ctx.lineTo(x1 - dx * h * 0.6, y1 + dy * h * 0.6); ctx.stroke();
  ctx.beginPath(); ctx.moveTo(x1, y1); ctx.lineTo(x1 - dx * h - dy * w, y1 + dy * h - dx * w); ctx.lineTo(x1 - dx * h + dy * w, y1 + dy * h + dx * w); ctx.closePath(); ctx.fill();
}
function barb(ctx, X, Y, wx, wy, sp, L) {
  const m = 5 * Math.round(sp / 5), nf = Math.floor(m / 50), nb = Math.floor((m % 50) / 10), half = (m % 10) >= 5;
  if (nf + nb === 0 && !half) { ctx.beginPath(); ctx.arc(X, Y, 0.15 * L, 0, 2 * Math.PI); ctx.stroke(); return; }
  const h = Math.hypot(wx, wy), dX = -wx / h, dY = -wy / h, pX = dY, pY = -dX;   // shaft toward the wind source; feathers on its clockwise side
  const S_ = (a, p) => [X + (dX * a + pX * p), Y - (dY * a + pY * p)];           // (along, perpendicular) y-up -> canvas
  const sp_ = 0.125 * L, ht = 0.4 * L, wd = 0.25 * L; let off = L;
  ctx.beginPath(); ctx.moveTo(X, Y); ctx.lineTo(...S_(L, 0)); ctx.stroke();
  for (let f = 0; f < nf; f++) {
    if (off !== L) off += sp_ / 2;
    ctx.beginPath(); ctx.moveTo(...S_(off, 0)); ctx.lineTo(...S_(off - wd / 2, ht)); ctx.lineTo(...S_(off - wd, 0)); ctx.closePath(); ctx.fill(); ctx.stroke();
    off -= wd + sp_;
  }
  for (let b = 0; b < nb; b++) { ctx.beginPath(); ctx.moveTo(...S_(off, 0)); ctx.lineTo(...S_(off + sp_, ht)); ctx.stroke(); off -= sp_; }
  if (half) {
    if (off === L) off -= 1.5 * sp_;
    ctx.beginPath(); ctx.moveTo(...S_(off, 0)); ctx.lineTo(...S_(off + sp_ / 2, ht / 2)); ctx.stroke();
  }
}

// ---------------------------------------------------------------- bench (headless): cold first frame, then scrubbing from cache

// ---- Stage 4 extras (10-30): ensemble member lines / low centres are shipped as cropped-grid (row, col) points; map them
// to canvas pixels by inverting the view's LUT (panel px -> grid) with a few Newton steps from the previous point.
function gridFwd(V, lut, x, y) {   // panel px (relative to panel) -> [fi, fj], same bilinear as viewStatic
  const { nx, ny, stride } = V, gx = (x + 0.5) / stride, gy = (y + 0.5) / stride;
  const i0 = Math.max(0, Math.min(nx - 2, gx | 0)), j0 = Math.max(0, Math.min(ny - 2, gy | 0)), tx = gx - i0, ty = gy - j0;
  const a = (j0 * nx + i0) * 3, b = a + 3, c = a + nx * 3, d = c + 3;
  return [(lut[a] * (1 - tx) + lut[b] * tx) * (1 - ty) + (lut[c] * (1 - tx) + lut[d] * tx) * ty,
          (lut[a + 1] * (1 - tx) + lut[b + 1] * tx) * (1 - ty) + (lut[c + 1] * (1 - tx) + lut[d + 1] * tx) * ty];
}
function gridInv(V, st, fi, fj, guess) {   // [fi, fj] -> panel px, or null when far outside the panel
  const lut = st.lut; let x, y;
  if (guess) [x, y] = guess;
  else { let best = Infinity; for (let j = 0; j < V.ny; j++) for (let i = 0; i < V.nx; i++) { const q = (j * V.nx + i) * 3, d = (lut[q] - fi) ** 2 + (lut[q + 1] - fj) ** 2;
           if (d < best) { best = d; x = i * V.stride; y = j * V.stride; } } }
  for (let it = 0; it < 6; it++) {
    const f0 = gridFwd(V, lut, x, y), fx = gridFwd(V, lut, x + 1, y), fy = gridFwd(V, lut, x, y + 1);
    const a = fx[0] - f0[0], b = fy[0] - f0[0], c = fx[1] - f0[1], d = fy[1] - f0[1], det = a * d - b * c; if (!det) break;
    const r0 = fi - f0[0], r1 = fj - f0[1], dx = (d * r0 - b * r1) / det, dy = (-c * r0 + a * r1) / det;
    x += Math.max(-200, Math.min(200, dx)); y += Math.max(-200, Math.min(200, dy)); if (Math.abs(dx) + Math.abs(dy) < 0.05) break;
  }
  if (x < -300 || y < -300 || x > st.W + 300 || y > st.H + 300) return null;
  return [x, y];
}
// H / L centres (Benjamin 10-31 1:26 AM: "a small red L in the middle of surface lows with the lowest pressure number, likewise
// with H ... highest pressure number"; 1:27 AM: also on MSLP + wind maps). Old site's house_style.find_centers ported: smoothed
// MSLP, neighbourhood extreme over a radius (km) per view, prominence vs the median of the ring at that radius, min spacing;
// the number is the raw (unsmoothed) min / max near the centre. Drawn on every map with MSLP isobars except ensemble lows.
const HL_VIEW = { na: [800, 3.0, 75], pnw: [400, 2.0, 50], pnwt: [400, 2.0, 50], pnwhr: [400, 2.0, 45] };   // radius km, prominence mb, smoothing km
const HL_WA = [250, 1.5, 35];   // Washington-type frames (old HL_RADIUS_KM / HL_PROMINENCE_MB "wa")
const HL_LOW_COLOR = "#d7191c", HL_HIGH_COLOR = "#1747c9";   // L red, H blue (Benjamin 10-31 1:42 AM; old site H blue #1747c9)
function drawHL(ctx, st, D, V, gk, P) {
  const out = hlMarks(ctx, st, D, P, V, gk);
  paintHL(ctx, out, P && P.isobars);
}
function hlGeom(st, D, V) {
  const raw = D.raw && D.raw.mslp ? D.raw.mslp.v : D.iso; if (!raw) return [];
  const m = S.run.split("/")[0], M = S.man.models[m], cr = M.crop || [0, 0, 0, 0], ll = M.grid === "ll";
  const ck = ll ? 27.8 : parseFloat(M.res) || 3, s = ll ? 1 : Math.max(1, Math.round(9 / ck)), w0 = D.w, h0 = D.h;
  const [rk, prom, smk] = HL_VIEW[VSRC(S.view)] || HL_WA, cell = ck * s;
  // decimated grid (s native cells), smoothed to ~smk km
  const w = Math.floor((w0 - 1) / s) + 1, h = Math.floor((h0 - 1) / s) + 1, a0 = new Float32Array(w * h);
  for (let i = 0; i < h; i++) for (let j = 0; j < w; j++) a0[i * w + j] = raw[i * s * w0 + j * s];
  const a = blur(a0, w, h, Math.max(0.6, smk / cell));
  const lat = i => ll ? 90 - (i * s + cr[0]) * 0.25 : 47;
  const [r0, r1, c0, c1] = V.cut || [0, h0, 0, w0];
  const ry = Math.max(2, Math.round(rk / cell)), rxOf = i => ll ? Math.max(2, Math.round(rk / (cell * Math.max(0.25, Math.cos(lat(i) * Math.PI / 180))))) : ry;
  const I0 = Math.max(1, Math.floor(r0 / s)), I1 = Math.min(h - 1, Math.ceil(r1 / s)), J0 = Math.max(1, Math.floor(c0 / s)), J1 = Math.min(w - 1, Math.ceil(c1 / s));
  const out = [], mg = pt(16);
  for (const sgn of [1, -1]) {   // highs, then lows
    const cand = [];
    for (let i = I0; i < I1; i++) for (let j = J0; j < J1; j++) { const v = sgn * a[i * w + j];
      if (v < sgn * a[i * w + j - 1] || v < sgn * a[i * w + j + 1] || v < sgn * a[(i - 1) * w + j] || v < sgn * a[(i + 1) * w + j]) continue;
      cand.push([v, i, j]); }
    cand.sort((x, y) => y[0] - x[0]); const placed = [];
    for (const [v, i, j] of cand) {
      if (placed.length >= 12) break;
      const rx = rxOf(i); let ok = true;
      for (let di = -ry; di <= ry && ok; di++) { const ii = i + di; if (ii < 0 || ii >= h) continue;
        for (let dj = -rx; dj <= rx; dj++) { const jj = j + dj; if (jj < 0 || jj >= w) continue; if (sgn * a[ii * w + jj] > v) { ok = false; break; } } }
      if (!ok) continue;
      const cl = ll ? Math.max(0.25, Math.cos(lat(i) * Math.PI / 180)) : 1, ring = []; let tot = 0;
      for (let t = 0; t < 48; t++) { const th = t / 48 * 2 * Math.PI, ii = Math.round(i + ry * Math.sin(th)), jj = Math.round(j + rx * Math.cos(th));
        tot++; if (ii >= 0 && jj >= 0 && ii < h && jj < w) ring.push(a[ii * w + jj]); }
      if (ring.length < 0.6 * tot) continue;   // too little of the ring in the data to call it closed
      ring.sort((x, y) => x - y); if (sgn * (sgn * v - ring[ring.length >> 1]) < prom) continue;
      if (placed.some(([pi, pj]) => (i - pi) ** 2 / ry ** 2 + (j - pj) ** 2 / rx ** 2 < 1)) continue;
      const p = gridInv(V, st, i * s, j * s, null);
      if (!p || p[0] < mg || p[1] < mg || p[0] > st.W - mg || p[1] > st.H - mg) continue;   // centre in view, clear of the frame edge
      placed.push([i, j]);
      const R = Math.max(1, Math.round(30 / ck)); let ex = -Infinity;   // raw extreme within ~30 km
      for (let di = -R; di <= R; di++) for (let dj = -R; dj <= R; dj++) { const ii = i * s + di, jj = j * s + dj; if (ii >= 0 && jj >= 0 && ii < h0 && jj < w0) ex = Math.max(ex, sgn * raw[ii * w0 + jj]); }
      out.push([st.x0 + p[0], st.y0 + p[1], sgn * ex, sgn > 0]);
    }
  }
  return out;
}
// 11-01 6:43 PM (Benjamin t2051u: "make the L for low center and the correlating number be the same as the rest of the numbers used on
// the isobars, same with H"): H / L and the centre pressure use the isobar value labels' exact style (paintIsobars: 700 10 pt Montserrat,
// the isobar colour, 3.2 pt white halo). Letter centred on the centre, number right under it. (Was: 900 16 pt red L / blue H, 800 9 pt number.)
const ISO_LAB_FONT = () => `700 ${pt(10)}px Montserrat`;
const LAB_SLIDE = 360;   // t2052u: an isobar number may slide this far (px along its line) off an H / L marker, else it is dropped
function hlBox(ctx, X, Y, v) {   // letter (centred on Y) + number under it, in the isobar-label font, plus the white halo
  ctx.save(); ctx.font = ISO_LAB_FONT(); const w = Math.max(ctx.measureText(String(Math.round(v))).width, ctx.measureText("H").width) + pt(4); ctx.restore();
  return [X - w / 2, Y - pt(7.5), X + w / 2, Y + pt(6.5) + pt(12)];
}
function hlDeclutter(ctx, out, vi, hiOf) {   // t2052u: markers never overlap each other; the stronger centre (|p - 1013|) wins
  const ord = out.map((o, n) => n).sort((a, b) => Math.abs(out[b][vi] - 1013) - Math.abs(out[a][vi] - 1013)), keep = [], boxes = [];
  for (const n of ord) { const o = out[n], B = hlBox(ctx, o[0], o[1], o[vi]);
    if (boxes.some(C => B[0] < C[2] && B[2] > C[0] && B[1] < C[3] && B[3] > C[1])) continue; boxes.push(B); keep.push(n); }
  keep.sort((a, b) => a - b); return keep.map(n => out[n]);
}
const hlOn = (P, D) => (P.hl || (P.isobars && (P.isobars.field || "mslp") === "mslp")) && D.iso && !P.lows;
function hlMarks(ctx, st, D, P, V, gk) {   // the markers that will be painted: [x, y, value]
  if (P.lows) { const g = geo(`elows/${gk}`, () => lowGeom(st, D, P, V)); return geo(`elowsm/${gk}`, () => hlDeclutter(ctx, g.means, 2)); }
  if (hlOn(P, D)) return geo(`hl/${gk}`, () => hlDeclutter(ctx, hlGeom(st, D, V), 2));
  return [];
}
function hlAvoid(ctx, st, D, P, V, gk) {
  if (!P.isobars || (P.isobars.field || "mslp") !== "mslp" || !(P.lows || hlOn(P, D))) return [];
  try { return hlMarks(ctx, st, D, P, V, gk).map(o => hlBox(ctx, o[0], o[1], o[2])); } catch (e) { return []; }
}
function isoLabText(ctx, I, s, x, y, base, col) { haloText(ctx, s, x, y, ISO_LAB_FONT(), col || (I && I.color) || "#15171c", pt(3.2), "center", base); }
function paintHL(ctx, out, I) {
  for (const [X, Y, v, hi] of out) {
    const col = hi ? HL_HIGH_COLOR : HL_LOW_COLOR;   // 11-01 7:43 PM (Benjamin t2053u): "make sure the L stays red and the H stays blue" (letter + number)
    isoLabText(ctx, I, hi ? "H" : "L", X, Y, "middle", col);
    isoLabText(ctx, I, String(Math.round(v)), X, Y + pt(6.5), "top", col); }
}
function drawEns(ctx, st, D, P, V, gk) {
  const E = D.ens; if (!E) return;
  if (P.spag) {
    for (const [L, col] of [["5520", "#2b6cd6"], ["5760", "#d63a2b"]]) {
      ctx.strokeStyle = col; ctx.globalAlpha = 0.7; ctx.lineWidth = pt(0.9); ctx.lineJoin = "round"; ctx.beginPath();
      for (const ln of E.spag[L] || []) { let g = null, on = false;
        for (let k = 1; k + 1 < ln.length; k += 2) { const p = gridInv(V, st, ln[k] / 10, ln[k + 1] / 10, g);
          if (!p) { on = false; g = null; continue; } g = p; const X = st.x0 + p[0], Y = st.y0 + p[1]; on ? ctx.lineTo(X, Y) : ctx.moveTo(X, Y); on = true; } }
      ctx.stroke(); ctx.globalAlpha = 1;
    }
    const z = D.raw.z500 && D.raw.z500.v; if (z) {
      const zl = geo(`spag/${gk}`, () => { const zb = blur(z, D.w, D.h, 1.0), G = cgrid(st, 3, k => sample(st, zb, k)); return [5520, 5760].map(L => contourG(st, G, L)); });
      for (const lines of zl) { strokeLines(ctx, lines, "#ffffff", pt(3.4), null); strokeLines(ctx, lines, "#101114", pt(1.8), null); } }
  }
  if (P.lows) {
    // 10-30 8:30 PM (Benjamin: "the ensemble low centers had the top 10 strongest, the weakest, and the ensemble mean pressure
    // at the center of the bullseye"): the old site's ens_maps.p_lows look. Navy core where 5+ members put a low within 25 km,
    // member dots in the old 8 pressure colors (deepest on top), red L + mean central pressure at each ensemble-mean low,
    // and the left list: mean lows, 10 strongest and 10 weakest member lows in view ("pressure #member").
    const g = geo(`elows/${gk}`, () => lowGeom(st, D, P, V));
    if (g.core.length) { ctx.fillStyle = (P.core && P.core.color) || "#0a1442";
      for (const [x, y, w, h] of g.core) ctx.fillRect(x - w / 2 - 0.5, y - h / 2 - 0.5, w + 1, h + 1); }
    const r = pt(V.label === "North America" ? 2.9 : 3.3);
    for (const [x, y, mb] of g.dots) { ctx.beginPath(); ctx.arc(x, y, r, 0, 2 * Math.PI); ctx.fillStyle = dotCol(mb); ctx.fill();
      ctx.lineWidth = pt(0.7); ctx.strokeStyle = "#ffffff"; ctx.stroke(); }
    for (const [x, y, v] of geo(`elowsm/${gk}`, () => hlDeclutter(ctx, g.means, 2))) {
      isoLabText(ctx, P.isobars, "L", x, y, "middle", HL_LOW_COLOR);   // t2053u: L red   // 11-01 t2051u: same style as the isobar numbers (was 900 18 pt red L, 900 11 pt mean)
      isoLabText(ctx, P.isobars, String(Math.round(v)), x, y + pt(6.5), "top", HL_LOW_COLOR); }
    S.lowPanel = g;
  }
}
const DOT_BOUNDS = [850, 920, 950, 970, 980, 988, 996, 1004, 1100];   // ens_maps.DOT_BOUNDS / DOT_COLS / DOT_LABELS
const DOT_COLS = ["#0b0010", "#2a2a9e", "#6a1b7a", "#b0186a", "#d7191c", "#ef6c2f", "#f2b134", "#9aa0a6"];
const DOT_LABELS = ["under 920", "920-949", "950-969", "970-979", "980-987", "988-995", "996-1003", "1004+"];
const dotCol = mb => { let k = 0; while (k < DOT_COLS.length - 1 && mb >= DOT_BOUNDS[k + 1]) k++; return DOT_COLS[k]; };
const LOWV = { na: [800, 4.0, 1.2], pnw: [400, 1.5, 0.8], pnwt: [300, 1.2, 0.6] };   // ens_maps.LOW: radius km, prominence mb, smoothing
function lowGeom(st, D, P, V) {
  const E = D.ens, m = S.run.split("/")[0], cr = S.man.models[m].crop || [0, 0, 0, 0];
  const lat = fi => 90 - (fi + cr[0]) * 0.25, lon = fj => (fj + cr[2]) * 0.25;
  const km = (a1, o1, a2, o2) => { const p1 = a1 * Math.PI / 180, p2 = a2 * Math.PI / 180, dl = (o2 - o1) * Math.PI / 180;
    return 6371 * Math.acos(Math.min(1, Math.max(-1, Math.sin(p1) * Math.sin(p2) + Math.cos(p1) * Math.cos(p2) * Math.cos(dl)))); };
  const inView = p => p && p[0] >= 0 && p[1] >= 0 && p[0] <= st.W && p[1] <= st.H;
  // member lows: pixel position, in view only (same rule as the old list: "in view")
  const L = [];
  for (const [mem, fi, fj, mb] of E.lows) { const p = gridInv(V, st, fi, fj, null); if (!inView(p)) continue;
    L.push({ mem: mem + 1, num: E.mnum ? E.mnum[mem] || null : null, fi, fj, mb, la: lat(fi), lo: lon(fj), x: st.x0 + p[0], y: st.y0 + p[1] }); }
  const dots = L.slice().sort((a, b) => b.mb - a.mb).map(o => [o.x, o.y, o.mb]);   // deepest drawn last (on top)
  // core: points where 5+ different members have a low within 25 km (old: contourf of that member count, navy)
  const C = P.core || { km: 25, min: 5 }, core = [], seen = new Set(), step = 0.05;
  const cand = L.filter(a => new Set(L.filter(b => km(a.la, a.lo, b.la, b.lo) <= 2 * C.km).map(b => b.mem)).size >= C.min);
  for (const a of cand) for (let di = -0.4; di <= 0.4 + 1e-6; di += step / 0.25) for (let dj = -0.8; dj <= 0.8 + 1e-6; dj += step / 0.25) {
    const fi = Math.round((a.fi + di) * 20) / 20, fj = Math.round((a.fj + dj) * 20) / 20, k = fi + "," + fj; if (seen.has(k)) continue; seen.add(k);
    const la = lat(fi), lo = lon(fj), mems = new Set();
    for (const b of L) if (Math.abs(b.la - la) < 0.3 && km(la, lo, b.la, b.lo) <= C.km) mems.add(b.mem);
    if (mems.size < C.min) continue;
    const p = gridInv(V, st, fi, fj, null), q = gridInv(V, st, fi + 0.2, fj + 0.2, null); if (!p || !q) continue;
    core.push([st.x0 + p[0], st.y0 + p[1], Math.abs(q[0] - p[0]) + 0.6, Math.abs(q[1] - p[1]) + 0.6]); }
  // ensemble-mean lows (old: find_centers on the smoothed mean MSLP, radius / prominence per view, value = raw min nearby)
  const means = [], raw = D.mslpRaw;
  if (raw) { const vid = VSRC(S.view), [rk, prom, sm] = LOWV[vid] || [300, 1.2, 0.6], w = D.w, h = D.h, a = blur(raw, w, h, sm);
    const vlat = lat((h - 1) / 2), ry = Math.max(2, Math.round(rk / (111.2 * 0.25))), rx = Math.max(2, Math.round(rk / (111.2 * 0.25 * Math.max(0.25, Math.cos(vlat * Math.PI / 180)))));
    const cands = [], [r0, r1, c0, c1] = V.cut || [1, h - 1, 1, w - 1];   // only the view's own rows / cols
    for (let i = Math.max(1, r0); i < Math.min(h - 1, r1); i++) for (let j = Math.max(1, c0); j < Math.min(w - 1, c1); j++) { const v = a[i * w + j];
      if (v > a[i * w + j - 1] || v > a[i * w + j + 1] || v > a[(i - 1) * w + j] || v > a[(i + 1) * w + j]) continue;   // quick 3x3 minimum first
      cands.push([v, i, j]); }
    cands.sort((x, y) => x[0] - y[0]); const placed = [];
    for (const [v, i, j] of cands) {
      let ok = true;
      for (let di = -ry; di <= ry && ok; di++) for (let dj = -rx; dj <= rx; dj++) { const ii = i + di, jj = j + dj;
        if (ii < 0 || jj < 0 || ii >= h || jj >= w) continue; if (a[ii * w + jj] < v) { ok = false; break; } }
      if (!ok) continue;
      const cl = Math.max(0.25, Math.cos(lat(i) * Math.PI / 180)), ring = [];
      for (let t = 0; t < 48; t++) { const th = t / 48 * 2 * Math.PI, ii = Math.round(i + ry * Math.sin(th)), jj = Math.round(j + rx * Math.cos(vlat * Math.PI / 180) / cl * Math.cos(th));
        if (ii >= 0 && jj >= 0 && ii < h && jj < w) ring.push(a[ii * w + jj]); }
      if (ring.length < 29) continue; ring.sort((x, y) => x - y); if (ring[ring.length >> 1] - v < prom) continue;
      if (placed.some(([a_, b_]) => (i - a_) ** 2 / ry ** 2 + (j - b_) ** 2 / rx ** 2 < 1)) continue;
      const p = gridInv(V, st, i, j, null); if (!inView(p)) continue;
      placed.push([i, j]); let mn = Infinity;
      for (let di = -2; di <= 2; di++) for (let dj = -2; dj <= 2; dj++) { const ii = i + di, jj = j + dj; if (ii >= 0 && jj >= 0 && ii < h && jj < w) mn = Math.min(mn, raw[ii * w + jj]); }
      means.push([st.x0 + p[0], st.y0 + p[1], mn]); }
  }
  // 11-01 (Benjamin: "include which ensemble member # is showing the individual strongest or lowest lows"): the list and the map
  // label use the real ECMWF member number (ens json "mnum"). Older files have none (their stack order was shuffled per step, so
  // the old "#k" was not the member) -> no number shown for them.
  // 11-03 small fixes ("EPS duplicate Mem 45"): one member can have two or more lows in view, so the same "Mem N" was listed twice.
  // Each list now shows a member once: "10 strongest" uses each member's deepest low in view, "10 weakest" each member's weakest.
  const byMem = pick => { const M = new Map(); for (const o of L) { const q = M.get(o.mem); if (!q || pick(o.mb, q.mb)) M.set(o.mem, o); } return [...M.values()].map(o => [o.mb, o.num]); };
  const strongL = byMem((a, b) => a < b).sort((x, y) => x[0] - y[0]), weakL = byMem((a, b) => a > b).sort((x, y) => y[0] - x[0]);
  const top = L.length ? L.reduce((a, b) => (b.mb < a.mb ? b : a)) : null;
  // list box on the side that hides fewer member dots / mean lows (old site: box outside the map, which a fixed basemap can't do)
  const PW = 0.092 * V.fig[0] + 0.03 * V.fig[0], hid = x0_ => dots.filter(d => d[0] >= x0_ && d[0] <= x0_ + PW).length + 10 * means.filter(d => d[0] >= x0_ && d[0] <= x0_ + PW).length;
  // 11-01 (Benjamin t2022u: "Scrolling through the low centers on AIFS ensembles is messed up, menus jump all over when scrubbing. ECMWF EPS
  // does the same thing"; t2023u: likes the list on the right): the side used to be re-picked every hour (whichever side hid fewer dots),
  // so the list and the dot legend flipped left/right while scrubbing. Now always the right side (AIFS ENS + ECMWF EPS, every view).
  const side = "right"; void hid;
  return { side, dots, core, means, top, hasNum: !!E.mnum, strong: strongL.slice(0, 10), weak: weakL.slice(0, 10), n: E.n || 50,
           meanVals: means.map(x => x[2]).sort((x, y) => x - y) };
}
function paintLowPanel(ctx, st, V, g) {   // ens_maps.low_panel, drawn inside the left edge of the map + the dot legend
  const [LW, LH] = V.fig, PW = Math.round(0.092 * LW), x0 = g.side === "right" ? st.x0 + st.W - PW - pt(3) : st.x0 + pt(3), y0 = st.y0 + pt(3), H = st.H - pt(6);
  const ms = g.meanVals.slice(0, 4), mrows = Math.max(1, Math.ceil(ms.length / 2));
  const need = 1.2 + 1.4 + (g.hasNum ? 0 : 0.6) + 1.05 + 1.2 * mrows + 0.4 + 2 * (1.05 + 10) + 0.5, lh = Math.min(pt(20.2), H / (need + 0.5));
  ctx.save(); ctx.globalAlpha = 0.95; ctx.fillStyle = "#f6f3ec"; ctx.strokeStyle = "#c9c4b8"; ctx.lineWidth = 1;
  ctx.beginPath(); ctx.roundRect ? ctx.roundRect(x0, y0, PW, H, pt(3)) : ctx.rect(x0, y0, PW, H); ctx.fill(); ctx.stroke(); ctx.globalAlpha = 1;
  ctx.textAlign = "left"; ctx.textBaseline = "top";
  const t = (x, y, s, w, sz, col) => { ctx.font = `${w} ${pt(sz)}px Montserrat`; ctx.fillStyle = col || "#1b1d22"; ctx.fillText(s, x, y); };
  const xl = x0 + 0.007 * LW, cw = (PW - 0.014 * LW) / 2; let y = y0 + 0.3 * lh;
  t(xl, y, "Lows (mb)", 800, 13.6); y += lh * 1.2;
  t(xl, y, `in view \u00b7 ${g.n} mem.`, 500, 10.0, "#5b5e66"); y += lh * 1.4;
  if (!g.hasNum) { t(xl, y - lh * 0.35, "member # n/a (older run)", 500, 7.6, "#8a8d94"); y += lh * 0.6; }
  t(xl, y, "Mean (red L)", 800, 12.0); y += lh * 1.05;
  if (!ms.length) { t(xl, y, "none", 500, 11, "#5b5e66"); y += lh; }
  ms.forEach((v, k) => { t(xl + (k % 2) * cw, y, String(Math.round(v)), 900, 15.0, "#d7191c"); if (k % 2 === 1 || k === ms.length - 1) y += lh * 1.2; });
  y += lh * 0.4;
  for (const [head, rows] of [["10 strongest", g.strong], ["10 weakest", g.weak]]) {
    t(xl, y, head, 800, 12.0); y += lh * 1.05;
    if (!rows.length) { t(xl, y, "none", 500, 11, "#5b5e66"); y += lh; }
    for (const [p, m] of rows) {
      ctx.beginPath(); ctx.arc(xl + 0.004 * LW, y + 0.42 * lh, 0.0031 * LW, 0, 2 * Math.PI); ctx.fillStyle = dotCol(p); ctx.fill();
      ctx.lineWidth = 0.6; ctx.strokeStyle = "#ffffff"; ctx.stroke();
      ctx.textBaseline = "middle";   // 11-01 (t2024u): row text centred on its dot like the legend
      t(xl + 0.011 * LW, y + 0.42 * lh, String(Math.round(p)), 800, 11.7); if (m) t(xl + 0.041 * LW, y + 0.42 * lh, `Mem ${m}`, 700, 10.6, "#2b2e35");
      ctx.textBaseline = "top"; y += lh; }
    y += lh * 0.5;
  }
  // strongest member low in view: ring around its dot + "Mem N · 952" (side away from the list / map edge / red L)
  const T = g.top; if (T && g.hasNum && T.num) {
    ctx.beginPath(); ctx.arc(T.x, T.y, pt(6.2), 0, 2 * Math.PI); ctx.lineWidth = pt(1.6); ctx.strokeStyle = "#ffffff"; ctx.stroke();
    ctx.lineWidth = pt(0.9); ctx.strokeStyle = "#0b0d12"; ctx.stroke();
    const s = `Mem ${T.num} \u00b7 ${Math.round(T.mb)}`; ctx.font = `800 ${pt(10.5)}px Montserrat`; const w = ctx.measureText(s).width, gap = pt(9), hh = pt(7.5);
    // 11-03 small fixes (EPS lows: "Mem 10 \u00b7 951" could sit on the mean red L): the label is a box tested against every mean L
    // (letter + number, hlBox), the list box, the dot key and the map edge; it tries up-right, up-left, down-right, down-left, level,
    // then further out, and if every spot touches something it takes the spot with the least overlap.
    const lwK = pt(78), lhK = pt(11) * (DOT_LABELS.length + 1) + pt(8), kx = g.side === "right" ? x0 - lwK - pt(5) : x0 + PW + pt(5), ky = st.y0 + st.H - lhK - pt(5);
    const obs = g.means.map(([mx, my, mv]) => hlBox(ctx, mx, my, mv)).concat([[x0, y0, x0 + PW, y0 + H], [kx, ky, kx + lwK, ky + lhK]]);
    const ov = (a, b) => Math.max(0, Math.min(a[2], b[2]) - Math.max(a[0], b[0])) * Math.max(0, Math.min(a[3], b[3]) - Math.max(a[1], b[1]));
    const pad = pt(2), cands = [];
    for (const k of [1, 1.9, 2.8]) for (const [sx, dy] of [[1, -1], [-1, -1], [1, 1], [-1, 1], [1, 0], [-1, 0]]) {
      const xa = sx > 0 ? T.x + gap * k : T.x - gap * k - w, yc = T.y + dy * pt(9) * k; cands.push([xa, yc]); }
    let best = null;
    for (const [xa, yc] of cands) { const R = [xa - pad, yc - hh - pad, xa + w + pad, yc + hh + pad];
      const out = R[0] < st.x0 + pt(3) || R[2] > st.x0 + st.W - pt(3) || R[1] < st.y0 + pt(3) || R[3] > st.y0 + st.H - pt(3);
      const cost = (out ? 1e9 : 0) + obs.reduce((a, b) => a + ov(R, b), 0);
      if (!best || cost < best[2]) best = [xa, yc, cost, R]; if (cost === 0) break; }
    window.__memLab = { s, rect: best[3], cost: best[2], means: g.means.length };   // QA hook (no effect on drawing)
    haloText(ctx, s, best[0], best[1], `800 ${pt(10.5)}px Montserrat`, "#0b0d12", pt(2.6), "left", "middle"); }
  // "Member low (mb)" legend, lower left of the map just right of the list (old: matplotlib legend, lower left)
  const lw = pt(78), rh = pt(11), lhgt = rh * (DOT_LABELS.length + 1) + pt(8), lx = g.side === "right" ? x0 - lw - pt(5) : x0 + PW + pt(5), ly = st.y0 + st.H - lhgt - pt(5);
  ctx.globalAlpha = 0.92; ctx.fillStyle = "#ffffff"; ctx.fillRect(lx, ly, lw, lhgt); ctx.globalAlpha = 1; ctx.strokeStyle = "#c9c4b8"; ctx.strokeRect(lx, ly, lw, lhgt);
  t(lx + pt(5), ly + pt(4), "Member low (mb)", 700, 7.5);
  DOT_LABELS.forEach((s, k) => { const yy = ly + pt(4) + rh * (k + 1); ctx.beginPath(); ctx.arc(lx + pt(9), yy + rh * 0.42, pt(2.8), 0, 2 * Math.PI);
    ctx.fillStyle = DOT_COLS[k]; ctx.fill(); ctx.strokeStyle = "#ffffff"; ctx.lineWidth = 0.6; ctx.stroke();
    // 11-01 (Benjamin t2024u screenshot: range labels sat above their dots): label vertically centred on its dot
    ctx.textBaseline = "middle"; t(lx + pt(16), yy + rh * 0.42, s, 500, 7.2); ctx.textBaseline = "top"; });
  ctx.restore();
}
// ---- Stage 5 (10-30): meteograms + Pass Forecaster. The runner samples every town / pass slot at full precision each step
// (single/pts_fFFF.json, order = run.json "points"), so a meteogram is ~1 small JSON per step, never map images.
const MG = { open: null, town: Q.get("town") || "Seattle", run: null, cache: new Map() };
const PTZ = "America/Los_Angeles";
const fmtPT = (iso, o) => new Intl.DateTimeFormat("en-US", Object.assign({ timeZone: PTZ }, o)).format(new Date(iso));
function mgRuns() {   // newest run of each model that carries town points
  const order = ["hrrr", "rrfs", "nbm", "gfs", "ifs", "ifs9", "aifs", "eps", "aens"], out = [];
  for (const m of order) for (const c of [...(S.man.runs[m] || [])].reverse()) { const r = `${m}/${c}`; if (S.runs[r] && !S.runs[r].points) continue; out.push(r); break; }
  return out;
}
async function mgSeries(r) {   // {points, steps:[{f, valid}], v: {field: [[town values] per step]}}
  if (MG.cache.has(r)) return MG.cache.get(r);
  const p = (async () => {
    const R_ = await loadRun(r); if (!R_.points) return null;
    const st = R_.steps, out = new Array(st.length); let k = 0;
    if ((R_.agg || []).includes("pts")) try {   // complete runs: one aggregated file (single/pts_all.json) instead of ~50
      const A = await (await fetch(`${DATA}runs/${r}/single/pts_all.json`)).json(), by = new Map(A.f.map((f, i) => [f, A.d[i]]));
      st.forEach((s, i) => { out[i] = by.get(s.f) || null; });
    } catch (e) { out.fill(null); }
    const one = async () => { while (k < st.length) { const i = k++; if (out[i]) continue; const f = String(st[i].f).padStart(3, "0");
      try { out[i] = await (await fetch(`${DATA}runs/${r}/single/pts_f${f}.json`)).json(); } catch (e) { out[i] = null; } } };
    await Promise.all(Array.from({ length: 8 }, one));
    const ok = st.map((s, i) => [s, out[i]]).filter(x => x[1]);
    return { points: R_.points, steps: ok.map(x => x[0]), d: ok.map(x => x[1]) };
  })();
  MG.cache.set(r, p); return p;
}
function mgTown(D, name) {   // per-step values of one town; derived wind / increments / snow
  const i = D.points.findIndex(p => p.n === name); if (i < 0) return null;
  const P = D.points[i], col = k => D.d.map(o => (o[k] ? o[k][i] : null)), has = k => D.d.some(o => o[k] && o[k][i] != null);
  const T = { P, f: D.steps.map(s => s.f), t: D.steps.map(s => s.valid) };
  if (has("t2m")) T.t2m = col("t2m").map(v => v == null ? v : v + (P.c || 0));
  if (has("t2sd")) T.t2sd = col("t2sd"); if (has("p32")) T.p32 = col("p32");
  if (has("u10")) { const u = col("u10"), v = col("v10"); T.wind = u.map((x, k) => x == null ? null : Math.hypot(x, v[k]) * 2.23694 / 1.94384); T.wdir = u.map((x, k) => x == null ? null : (Math.atan2(-x, -v[k]) * 180 / Math.PI + 360) % 360); }
  if (has("gust")) T.gust = col("gust"); if (has("tcc")) T.tcc = col("tcc"); if (has("mslp")) T.mslp = col("mslp"); if (has("frz")) T.frz = col("frz");
  const inc = a => a.map((x, k) => x == null ? null : Math.max(0, k ? x - (a[k - 1] ?? 0) : x));   // run totals -> per-step amounts
  if (has("apcp")) T.pcp = inc(col("apcp")); else if (has("nq1")) T.pcp = col("nq1").map((x, k) => (T.f[k] <= 36 ? x : null)), T.pcp6 = col("nq6");
  if (has("asnow")) T.snow = inc(col("asnow"));
  else if (has("ns6")) T.snow6 = col("ns6");
  else if (T.pcp && T.t2m) { T.snow = T.pcp.map((x, k) => x == null ? null : (T.t2m[k] <= 33 ? x * 10 : 0)); T.snowEst = true; }
  if (has("dsnod")) T.dsnod = col("dsnod");
  if (has("kinc")) T.kuch = col("kinc");
  return T;
}
const sumWin = (T, a, f0, f1) => { if (!a) return null; let s = 0, n = 0; T.f.forEach((f, k) => { if (f > f0 && f <= f1 && a[k] != null) { s += a[k]; n++; } }); return n ? s : null; };
const sum6 = (T, a, f0, f1) => { if (!a) return null; let s = 0, n = 0; T.f.forEach((f, k) => { if (f % 6 === 0 && f > f0 && f <= f1 && a[k] != null) { s += a[k]; n++; } }); return n ? s : null; };
const snowWin = (T, f0, f1) => T.snow ? sumWin(T, T.snow, f0, f1) : sum6(T, T.snow6, f0, f1);
const pcpWin = (T, f0, f1) => T.pcp6 ? sum6(T, T.pcp6, f0, f1) : sumWin(T, T.pcp, f0, f1);
const ext = (T, a, f0, f1, fn) => { if (!a) return null; const v = a.filter((x, k) => x != null && T.f[k] > f0 && T.f[k] <= f1); return v.length ? fn(...v) : null; };

function mgOpen(kind) {
  mgClose(); MG.open = kind; try { if (!Q.get("studio") && !Q.get("embed")) sessionStorage.setItem("vw:mg", kind); } catch (e) { /* private mode */ } MG.run = S.runs[S.run] && S.runs[S.run].points ? S.run : (mgRuns()[0] || S.run);
  const o = document.createElement("div"); o.id = "mg";
  o.innerHTML = `<div class="mg-top"><b>${kind === "pass" ? "Pass Forecaster" : "Meteogram"}</b>
    <label>Model <select id="mgrun"></select></label>${kind === "pass" ? "" : `<label>Place <select id="mgtown"></select></label>`}
    <a id="mgpage" href="meteograms" title="Full meteograms page (old-site layout: plumes, member grids, multi-run)"><span class="lg">Meteograms page</span><span class="sm">Full page</span></a><button type="button" id="mgsave" title="Save this graphic as a picture (phones: Share / Save Image)">Save image</button><button type="button" id="mgx">Close</button></div><div id="mgbody"><div class="mg-msg">Loading\u2026</div></div>`;
  document.body.appendChild(o); $("mgx").onclick = mgClose; $("mgsave").onclick = mgSave;
  const runLabel = r => { const [m, c] = r.split("/"); return `${S.man.models[m].site} ${c.slice(8)}Z ${c.slice(4, 6)}-${c.slice(6, 8)}`; };
  const rs = mgRuns(); if (!rs.includes(MG.run)) rs.unshift(MG.run);
  fill($("mgrun"), rs.map(r => [r, runLabel(r)]), MG.run);
  $("mgrun").onchange = e => { MG.run = e.target.value; mgDraw(); };
  if ($("mgtown")) $("mgtown").onchange = e => { MG.town = e.target.value; mgDraw(); };
  addEventListener("resize", mgResize); mgDraw();
}
function mgClose() { try { sessionStorage.removeItem("vw:mg"); } catch (e) { /* private mode */ } const o = $("mg"); if (o) o.remove(); MG.open = null; removeEventListener("resize", mgResize); }
let mgT = null; function mgResize() { clearTimeout(mgT); mgT = setTimeout(() => MG.open && mgDraw(), 150); }
async function mgDraw() {
  const body = $("mgbody"), D = await mgSeries(MG.run); if (!MG.open) return;
  if (!D) { body.innerHTML = `<div class="mg-msg">This run was made before town forecasts were added. Pick a newer run.</div>`; return; }
  if (MG.open === "pass") return passTable(body, D);
  const sel = $("mgtown"), towns = D.points.filter(p => p.k !== "pass"), passes = D.points.filter(p => p.k === "pass");
  if (!D.points.some(p => p.n === MG.town)) MG.town = (D.points.find(p => p.n === "Seattle") || D.points[0]).n;
  sel.innerHTML = [["Towns (A\u2013Z)", towns], ["Mountain passes (A\u2013Z)", passes]].filter(g => g[1].length).map(([l, a]) =>
    `<optgroup label="${l}">` + a.map(p => `<option${p.n === MG.town ? " selected" : ""}>${p.n}</option>`).join("") + "</optgroup>").join("");
  const pg = $("mgpage"); if (pg) pg.href = `meteograms#s=${MG.run.split("/")[0]}&w=${encodeURIComponent(MG.town)}`;
  const T = mgTown(D, MG.town); body.innerHTML = `<canvas id="mgc"></canvas>`; mgChart($("mgc"), T, body);
}
function mgChart(cv, T, box) {
  const dpr = Math.min(2, devicePixelRatio || 1), W = box.clientWidth, sm0 = W < 600;
  // Benjamin 10-31 8:58 AM "A snowfall graph on the pass meteograms would be cool": passes with snow data get their own Snow panel
  // (bars = snow per 6 h, inches; line = running total, right axis); the precip panel then shows precip only. Towns unchanged.
  const snowPan = !!(T.P && T.P.k === "pass" && (T.snow || T.snow6));
  const npan = [T.t2m, T.wind || T.gust, T.pcp || T.snow || T.snow6 || T.pcp6, snowPan, T.tcc].filter(Boolean).length;   // each panel has its own time axis (Benjamin 10-30)
  const H = Math.max(sm0 ? 520 : 560, 52 + 40 * npan + (sm0 ? 52 : 60) * 8, box.clientHeight - 4);
  cv.width = W * dpr; cv.height = H * dpr; cv.style.width = W + "px"; cv.style.height = H + "px";
  const c = cv.getContext("2d"); c.scale(dpr, dpr); c.fillStyle = "#15171c"; c.fillRect(0, 0, W, H);
  const [m] = MG.run.split("/"), site = S.man.models[m].site, small = W < 600;
  const L = small ? 38 : 52, Rm = small ? 34 : 50, top = small ? 46 : 52, bot = 34, n = T.f.length;   // bot / gap = room for the time axis under each panel
  const panels = [["temp", 3], ["wind", 2], ["pcp", 2], ["snow", 2], ["cloud", 1]].filter(([k]) => k === "temp" ? T.t2m : k === "wind" ? (T.wind || T.gust) :
    k === "pcp" ? (T.pcp || T.snow || T.snow6 || T.pcp6) : k === "snow" ? snowPan : T.tcc);
  const wsum = panels.reduce((a, p) => a + p[1], 0), gap = 40, ph = (H - top - bot - gap * (panels.length - 1)) / wsum;
  const t0 = Date.parse(T.t[0]), t1 = Date.parse(T.t[n - 1]), X = iso => L + (Date.parse(iso) - t0) / Math.max(1, t1 - t0) * (W - L - Rm);
  c.font = `800 ${small ? 14 : 17}px Montserrat`; c.fillStyle = "#f4f2ee"; c.textBaseline = "top";
  c.fillText(`${MG.town}${T.P.k === "pass" ? " (pass)" : ""} \u2013 ${site} ${MG.run.split("/")[1].slice(8)}Z`, L, 8);
  c.font = `500 ${small ? 10 : 12}px Montserrat`; c.fillStyle = "#a7abb3";
  c.fillText(`Times are Pacific. ${T.P.c !== undefined ? "Temperature corrected to pass summit height. " : ""}${T.snowEst ? "Snow estimated 10:1 where 2 m temp \u2264 33\u00b0F." : ""}`, L, small ? 26 : 30);
  let y = top;
  const tAxis = yb => {   // hours row + day row (Pacific) under one panel; ticks from clock time, so 3 h / 6 h steps label too
    const x0 = Date.parse(T.t[0]), x1 = Date.parse(T.t[n - 1]), span = (x1 - x0) / 36e5, every = span <= 30 ? 3 : span <= 54 ? 6 : span <= 100 ? 12 : 0;
    const Xm = ms => L + (ms - t0) / Math.max(1, t1 - t0) * (W - L - Rm);
    c.font = `600 ${small ? 9 : 11}px Montserrat`; c.fillStyle = "#cfd3da"; c.textBaseline = "top"; c.textAlign = "center";
    const mids = []; let lastX = -1e9;
    for (let t = Math.ceil(x0 / 36e5) * 36e5; t <= x1; t += 36e5) { const h = +fmtPT(t, { hour: "numeric", hourCycle: "h23" }) % 24; if (h === 0) mids.push(t);
      if (every && h % every === 0 && Xm(t) - lastX > (small ? 30 : 40)) { c.fillText(fmtPT(t, { hour: "numeric" }).replace(" ", "").toLowerCase(), Xm(t), yb); lastX = Xm(t); } }
    const dy = every ? 13 : 0, edges = [x0, ...mids, x1], dw = mids.length > 1 ? Xm(mids[1]) - Xm(mids[0]) : W;
    const long = d => fmtPT(d, { weekday: "short", month: "numeric", day: "numeric" }), short = d => fmtPT(d, { month: "numeric", day: "numeric" });
    if (dw > c.measureText("Wed, 10/28").width + 8) { for (let k = 0; k + 1 < edges.length; k++) { const xa = Xm(edges[k]), xb = Xm(edges[k + 1]), lab = long(edges[k] + 1); if (xb - xa > c.measureText(lab).width + 4) c.fillText(lab, (xa + xb) / 2, yb + dy); } }
    else { const kk = Math.max(1, Math.ceil((c.measureText("10/28").width + 10) / dw)); mids.forEach((m, k) => { if (k % kk) return; c.fillRect(Xm(m) - 0.5, yb - 4, 1, 4); c.fillText(short(m + 1), Xm(m), yb + dy); }); }
    c.textAlign = "left";
  };
  const days = []; for (let k = 0; k < n; k++) { const d = fmtPT(T.t[k], { weekday: "short", month: "numeric", day: "numeric" }); if (!days.length || days[days.length - 1].d !== d) days.push({ d, k }); }
  for (const [kind, wt] of panels) {
    const h = wt * ph, y0 = y, y1 = y + h; y += h + gap;
    c.save(); c.beginPath(); c.rect(0, y0 - 8, W, h + 10); c.clip();   // nothing from one panel draws into the next
    c.fillStyle = "#1d2027"; c.fillRect(L, y0, W - L - Rm, h);
    c.strokeStyle = "#2c3039"; c.lineWidth = 1; for (const dd of days) { const x = X(T.t[dd.k]); c.beginPath(); c.moveTo(x, y0); c.lineTo(x, y1); c.stroke(); }
    const scale = (lo, hi) => v => y1 - (v - lo) / (hi - lo || 1) * h;
    const axis = (lo, hi, sc, unit, right, color) => { c.font = `500 ${small ? 9 : 11}px Montserrat`; c.fillStyle = color || "#a7abb3"; c.textBaseline = "middle"; c.textAlign = right ? "left" : "right";
      const stp = niceStep((hi - lo) / 4); for (let v = Math.ceil(lo / stp) * stp; v <= hi + 1e-9; v += stp) { const yy = sc(v); if (!right) { c.strokeStyle = "#2c3039"; c.beginPath(); c.moveTo(L, yy); c.lineTo(W - Rm, yy); c.stroke(); }
        c.fillText(+v.toFixed(2) + unit, right ? W - Rm + 4 : L - 4, yy); } c.textAlign = "left"; };
    const line = (a, sc, color, lw, dash) => { c.strokeStyle = color; c.lineWidth = lw; c.setLineDash(dash || []); c.beginPath(); let on = false;
      a.forEach((v, k) => { if (v == null) { on = false; return; } const xx = X(T.t[k]), yy = sc(v); on ? c.lineTo(xx, yy) : c.moveTo(xx, yy); on = true; }); c.stroke(); c.setLineDash([]); };
    const label = (s, color, dx, dy) => { c.font = `700 ${small ? 10 : 12}px Montserrat`; c.fillStyle = color; c.textBaseline = "top"; c.fillText(s, L + 6 + (dx || 0), y0 + 4 + (dy || 0)); return c.measureText(s).width + 14; };
    const bars = (a, sc, color, wfrac) => { c.fillStyle = color; const bw = Math.max(1.5, (W - L - Rm) / n * (wfrac || 0.7)); a.forEach((v, k) => { if (v == null || v <= 0) return; const xx = X(T.t[k]); c.fillRect(xx - bw / 2, sc(v), bw, y1 - sc(v)); }); };
    if (kind === "temp") {
      const a = T.t2m.filter(v => v != null), sd = T.t2sd;
      let lo = Math.min(...a, 32), hi = Math.max(...a, 32); if (sd) { lo = Math.min(lo, ...T.t2m.map((v, k) => v - (sd[k] || 0))); hi = Math.max(hi, ...T.t2m.map((v, k) => v + (sd[k] || 0))); }
      lo = Math.floor(lo / 5) * 5 - 2; hi = Math.ceil(hi / 5) * 5 + 2; const sc = scale(lo, hi); axis(lo, hi, sc, "\u00b0");
      if (sd) { c.fillStyle = "#e0484d33"; c.beginPath(); T.t2m.forEach((v, k) => { const xx = X(T.t[k]); k ? c.lineTo(xx, sc(v + sd[k])) : c.moveTo(xx, sc(v + sd[k])); });
        for (let k = n - 1; k >= 0; k--) c.lineTo(X(T.t[k]), sc(T.t2m[k] - sd[k])); c.fill(); }
      line(T.t2m.map(() => 32), sc, "#5aa9ff", 1.5, [6, 4]); line(T.t2m, sc, "#ff5a5f", 2.5);
      let dx = label(sd ? "Temperature \u00b0F (ens. mean, shading = \u00b11 spread)" : "Temperature \u00b0F", "#ff8a8e");
      // Benjamin 10-31 1:20 AM: say what the dashed blue line is (dash sample + "= freezing (32°F)"), next to the title or on the next row
      const rowH = small ? 14 : 16; c.font = `700 ${small ? 10 : 12}px Montserrat`;
      const fzT = "= freezing (32\u00b0F)", fzW = 22 + c.measureText(fzT).width + 14, fzOn1 = L + 6 + dx + fzW < W - Rm - 4, fzX = fzOn1 ? dx : 0, fzY = fzOn1 ? 0 : rowH;
      const fzNote = () => {   // drawn after the data lines so nothing crosses it
        { const yy = y0 + 4 + fzY + (small ? 5 : 6); c.fillStyle = "rgba(24,26,31,0.85)"; c.fillRect(L + 3 + fzX, y0 + 2 + fzY, fzW - 8, rowH);   // backing so lines under it don't hide the note
        c.strokeStyle = "#5aa9ff"; c.lineWidth = 1.5; c.setLineDash([6, 4]); c.beginPath(); c.moveTo(L + 6 + fzX, yy); c.lineTo(L + 6 + fzX + 18, yy); c.stroke(); c.setLineDash([]); }
        label(fzT, "#5aa9ff", fzX + 22, fzY);
      };
      // Benjamin 10-31 8:55 AM: no "chance <= 32F" line / right % axis on PASS meteograms (towns keep it); the freezing note stays
      const p32 = T.P && T.P.k === "pass" ? null : T.p32;
      if (!p32) fzNote();
      if (p32) { const s2 = scale(0, 100); line(p32, s2, "#7fd1ff", 1.5, [2, 3]); axis(0, 100, s2, "%", true, "#7fd1ff"); fzNote(); { c.font = `700 ${small ? 10 : 12}px Montserrat`; const lab = "chance \u2264 32\u00b0F (right axis)", px0 = fzX + fzW + 10, fits = L + 6 + px0 + c.measureText(lab).width < W - Rm - 4; label(lab, "#7fd1ff", fits ? px0 : 0, fits ? fzY : fzY + rowH); } }
      const mx = [], mn = []; // daily hi/lo labels
      for (const dd of days) { const ks = T.t.map((t, k) => k).filter(k => fmtPT(T.t[k], { weekday: "short", month: "numeric", day: "numeric" }) === dd.d && T.t2m[k] != null);
        if (ks.length < 3) continue; const kH = ks.reduce((a, b) => T.t2m[b] > T.t2m[a] ? b : a), kL = ks.reduce((a, b) => T.t2m[b] < T.t2m[a] ? b : a);
        c.font = `800 ${small ? 10 : 12}px Montserrat`; c.textAlign = "center"; c.fillStyle = "#ffb0b2"; c.textBaseline = "bottom"; c.fillText(Math.round(T.t2m[kH]), X(T.t[kH]), sc(T.t2m[kH]) - 3);
        c.fillStyle = "#9fd0ff"; c.textBaseline = "top"; c.fillText(Math.round(T.t2m[kL]), X(T.t[kL]), sc(T.t2m[kL]) + 3); c.textAlign = "left"; }
    } else if (kind === "wind") {
      const a = [...(T.wind || []), ...(T.gust || [])].filter(v => v != null), hi = Math.max(10, Math.ceil(Math.max(...a) / 10) * 10), sc = scale(0, hi); axis(0, hi, sc, "");
      if (T.gust) line(T.gust, sc, "#ffb347", 2); if (T.wind) line(T.wind, sc, "#7fd1ff", 2);
      let dx = 0; if (T.wind) dx += label("Wind mph", "#7fd1ff"); if (T.gust) label("Gusts mph", "#ffb347", dx);
      if (T.wdir) { const every = Math.max(1, Math.ceil(n / ((W - L - Rm) / 26))); c.fillStyle = "#cfd3da"; for (let k = 0; k < n; k += every) { if (T.wdir[k] == null) continue;
        const xx = X(T.t[k]), yy = y1 - 9, r = (T.wdir[k] + 180) * Math.PI / 180; c.save(); c.translate(xx, yy); c.rotate(r); c.beginPath(); c.moveTo(0, -6); c.lineTo(3.5, 4); c.lineTo(-3.5, 4); c.closePath(); c.fill(); c.restore(); } }
    } else if (kind === "pcp") {
      const pc = T.pcp6 && !T.pcp ? null : T.pcp, sn = T.snow || null, sn6 = T.snow6 || null, p6 = T.pcp6 || null;
      const hiP = Math.max(0.1, ...(pc || []).filter(v => v != null), ...(p6 || []).filter(v => v != null));
      const runS = sn ? sn.reduce((acc, v, k) => (acc.push((acc[k - 1] || 0) + (v || 0)), acc), []) : sn6 ? (() => { let q = 0; return sn6.map((v, k) => T.f[k] % 6 === 0 ? (q += v || 0) : null); })() : [];
      const anySnow = (sn || sn6 || []).some(v => v > 0.05), hiS = Math.max(1, ...runS.filter(v => v != null)), topS = niceStep(hiS) * Math.ceil(hiS / niceStep(hiS)), scS = scale(0, topS);
      const pTop = Math.max(T.P && T.P.k === "pass" && pc && (T.f[1] - T.f[0] || 1) === 1 ? 3 : 0, niceStep(hiP) * Math.ceil(hiP / niceStep(hiP)));   /* t2305u: pass in per hour axis at least 3 in */
      const scP = scale(0, pTop); axis(0, pTop, scP, "\u2033", false, "#6fd38a");
      if (p6 && T.pcp) bars(p6.map((v, k) => T.f[k] % 6 === 0 && T.f[k] > 36 ? v : null), scP, "#3ea95888", 2.2);
      if (pc) bars(pc, scP, "#3ea958"); else if (p6) bars(p6.map((v, k) => T.f[k] % 6 === 0 ? v : null), scP, "#3ea958", 2.2);
      if (anySnow && !snowPan) { axis(0, topS, scS, "\u2033", true, "#d9ecff"); line(runS, scS, "#d9ecff", 2); }
      const tot = pc ? pc.reduce((a, v) => a + (v || 0), 0) : sum6(T, p6, -1, 1e9) || 0;
      let dx = label(`Precip per ${pc ? (T.f[1] - T.f[0] || 1) + " h" : "6 h"} (total ${tot.toFixed(2)}\u2033)`, "#6fd38a");
      if (anySnow && !snowPan) { const ts = (sn || []).reduce((a, v) => a + (v || 0), 0) || sum6(T, sn6, -1, 1e9) || 0; label(`Snow running total ${ts.toFixed(1)}\u2033${T.snowEst ? " (est.)" : ""}`, "#d9ecff", dx); }
    } else if (kind === "snow") {   // pass Snow panel: 6 h snowfall bars (each spans its 6 h window, ending at the step) + running total line
      const sn = T.snow || null, sn6 = T.snow6 || null;
      const s6 = T.f.map((f, k) => f % 6 !== 0 ? null : sn ? sumWin(T, sn, f - 6, f) : sn6[k]);
      let q = 0; const runS = sn ? sn.map(v => (q += v || 0)) : sn6.map((v, k) => T.f[k] % 6 === 0 ? (q += v || 0) : null), tot = q;
      const hiB = Math.max(12, ...s6.filter(v => v != null))   /* t2305u: pass snow per 6 h axis at least 12 in */, topB = niceStep(hiB) * Math.ceil(hiB / niceStep(hiB)), scB = scale(0, topB);
      const hiR = Math.max(1, ...runS.filter(v => v != null)), topR = niceStep(hiR) * Math.ceil(hiR / niceStep(hiR)), scR = scale(0, topR);
      axis(0, topB, scB, "\u2033", false, "#9fc8ff"); axis(0, topR, scR, "\u2033", true, "#f4f2ee");
      c.fillStyle = "#5b9dff"; const gap6 = Math.max(1, (X(T.t[n - 1]) - X(T.t[0])) / Math.max(1, (t1 - t0) / 216e5) * 0.12);
      s6.forEach((v, k) => { if (v == null || v < 0.05) return; const xb = X(T.t[k]), xa = X(new Date(Date.parse(T.t[k]) - 216e5).toISOString());
        const x0 = Math.max(L, xa + gap6 / 2), x1 = xb - gap6 / 2; if (x1 > x0) c.fillRect(x0, scB(v), x1 - x0, y1 - scB(v));
        if (x1 - x0 > (small ? 16 : 22) && v >= 0.5) { c.font = `700 ${small ? 9 : 11}px Montserrat`; c.fillStyle = "#d9ecff"; c.textAlign = "center"; c.textBaseline = "bottom";
          c.fillText(v.toFixed(v < 10 ? 1 : 0), (x0 + x1) / 2, scB(v) - 2); c.textAlign = "left"; c.fillStyle = "#5b9dff"; } });
      line(runS, scR, "#f4f2ee", 2);
      let dx = label(`Snow per 6 h, inches${T.snowEst ? " (est.)" : ""}`, "#9fc8ff");
      label(`Running total ${tot.toFixed(1)}\u2033 (right axis)`, "#f4f2ee", dx);
      if (!(tot >= 0.05)) label("No snow in this run", "#a7abb3", 0, small ? 16 : 18);
    } else {
      const sc = scale(0, 100); c.fillStyle = "#9aa3b2"; c.beginPath(); c.moveTo(X(T.t[0]), y1); T.tcc.forEach((v, k) => c.lineTo(X(T.t[k]), sc(v || 0))); c.lineTo(X(T.t[n - 1]), y1); c.closePath(); c.globalAlpha = 0.55; c.fill(); c.globalAlpha = 1;
      axis(0, 100, sc, "%"); label("Cloud cover", "#cfd3da");
    }
    c.restore(); tAxis(y1 + 4);
  }
  c.textAlign = "left";
}
function niceStep(x) { const p = Math.pow(10, Math.floor(Math.log10(x || 1))), r = x / p; return (r <= 1 ? 1 : r <= 2 ? 2 : r <= 2.5 ? 2.5 : r <= 5 ? 5 : 10) * p; }
// Pass summit elevations, ft (WSDOT MountainPass feed, wsdot.com/Travel/Real-time/Service/api/MountainPass/Details/<id>, read
// 10-30-26 8:15 PM; same as temp_maps.WA_PASSES, checked 10-24 against USGS 3DEP). BC: DriveBC summit heights (fast_encode).
const PASS_ELEV = { Snoqualmie: 3022, Stevens: 4061, White: 4500, Chinook: 5430, Blewett: 4102, Sherman: 5575, Satus: 3107, Wauconda: 4310,
                    Disautel: 3252, Coquihalla: 4081, Allison: 4403, Duffey: 4199 };
// 10-30 8:10 PM (Benjamin: "I don't see it on the phone. Show the lowest freezing level in feet. Next to every pass, show the
// elevation of the pass."): elevation under each pass name; lowest freezing level is the 2nd column (it was the last one, off
// the right edge of a phone); blue when it drops below the summit. Models without a freezing level (ECMWF IFS / AIFS / ensembles
// / NBM) borrow it from the newest HRRR, RRFS or GFS run over the same hours, and the header says which.
async function passTable(body, D) {
  const passes = D.points.filter(p => p.k === "pass"); if (!passes.length) { body.innerHTML = `<div class="mg-msg">No passes in this model's views.</div>`; return; }
  const T0 = mgTown(D, passes[0].n), fmax = T0.f[T0.f.length - 1], wins = [[0, 24], [24, 48], [48, 72]].filter(w => fmax > w[0]).map(([a, b]) => [a, Math.min(b, fmax)]);
  const f1 = x => x == null ? "\u2013" : x.toFixed(1), f2 = x => x == null ? "\u2013" : x.toFixed(2), r0 = x => x == null ? "\u2013" : Math.round(x);
  const ft = x => x == null || !isFinite(x) ? "\u2013" : (Math.round(x / 100) * 100).toLocaleString("en-US");
  const hdr = wins.map(([a, b]) => `${fmtPT(new Date(Date.parse(T0.t[0]) + (a - T0.f[0]) * 36e5).toISOString(), { weekday: "short", hour: "numeric" })}\u2013${fmtPT(new Date(Date.parse(T0.t[0]) + (b - T0.f[0]) * 36e5).toISOString(), { weekday: "short", hour: "numeric" })}`);
  const span = Math.min(fmax, 48), runAt = MG.run;
  // lowest freezing level over the first `span` hours: this run, or the newest HRRR / RRFS / GFS run over the same valid times
  let frzOf = p => ext(mgTown(D, p.n), mgTown(D, p.n).frz, -1, span, Math.min), frzSrc = "";
  if (!T0.frz) {
    frzOf = () => null;
    const vt0 = Date.parse(T0.t[0]) - 1, vt1 = Date.parse(T0.t[0]) + (span - T0.f[0]) * 36e5 + 1;
    for (const m of ["hrrr", "rrfs", "gfs"]) {
      const c = (S.man.runs[m] || []).slice(-1)[0]; if (!c) continue;
      const D2 = await mgSeries(`${m}/${c}`).catch(() => null); if (MG.run !== runAt || MG.open !== "pass") return;
      if (!D2 || !mgTown(D2, passes[0].n) || !mgTown(D2, passes[0].n).frz) continue;
      const lo = p => { const T = mgTown(D2, p.n); if (!T || !T.frz) return null; const v = T.frz.filter((x, k) => x != null && Date.parse(T.t[k]) >= vt0 && Date.parse(T.t[k]) <= vt1); return v.length ? Math.min(...v) : null; };
      if (passes.some(p => lo(p) != null)) { frzOf = lo; frzSrc = `${S.man.models[m].site} ${c.slice(8)}Z`; break; }
    }
  }
  let h = `<div class="mg-note">Run start ${fmtPT(new Date(Date.parse(T0.t[0]) - T0.f[0] * 36e5).toISOString(), { weekday: "short", month: "numeric", day: "numeric", hour: "numeric" })} PT. Elevation = highway summit (WSDOT). Temperatures corrected to summit height. Freezing level shaded blue when it is below the pass. ${T0.snowEst ? "Snow estimated 10:1 where 2 m temp \u2264 33\u00b0F. " : ""}Tap a pass for its meteogram.</div>
  <div class="mg-scroll"><table class="pf"><thead><tr><th>Pass<br><small>summit ft</small></th><th>Freezing lvl<br><small>lowest ft, ${span} h${frzSrc ? `<br>from ${frzSrc}` : ""}</small></th>${wins.map((w, k) => `<th>Snow \u2033<br><small>${hdr[k]}</small></th>`).join("")}${T0.kuch ? wins.map((w, k) => `<th>Kuchera \u2033<br><small>${hdr[k]}</small></th>`).join("") : ""}<th>Low \u00b0F<br><small>first ${span} h</small></th><th>High \u00b0F<br><small>first ${span} h</small></th><th>Precip \u2033<br><small>first ${span} h</small></th><th>Max gust<br><small>mph, ${span} h</small></th></tr></thead><tbody>`;
  for (const p of passes) { const T = mgTown(D, p.n), sn = wins.map(([a, b]) => snowWin(T, a, b)), el = PASS_ELEV[p.n], fz = frzOf(p);
    const col = x => x == null ? "" : x >= 12 ? ' class="s3"' : x >= 6 ? ' class="s2"' : x >= 1 ? ' class="s1"' : "";
    const fzc = fz != null && el && fz <= el ? ' class="fzb"' : "";
    h += `<tr data-n="${p.n}"><td>${p.n}<br><small class="el">${el ? el.toLocaleString("en-US") + " ft" : ""}</small></td><td${fzc}>${ft(fz)}</td>${sn.map(x => `<td${col(x)}>${f1(x)}</td>`).join("")}${T0.kuch ? wins.map(([a, b]) => { const x = sumWin(T, T.kuch, a, b); return `<td${col(x)}>${f1(x)}</td>`; }).join("") : ""}<td>${r0(ext(T, T.t2m, -1, span, Math.min))}</td><td>${r0(ext(T, T.t2m, -1, span, Math.max))}</td><td>${f2(pcpWin(T, -1, span))}</td><td>${r0(ext(T, T.gust, -1, span, Math.max))}</td></tr>`; }
  body.innerHTML = h + "</tbody></table></div>";
  body.querySelectorAll("tr[data-n]").forEach(tr => tr.onclick = () => { MG.town = tr.dataset.n; const r = MG.run; mgOpen("town"); MG.run = r; $("mgrun").value = r; mgDraw(); });
}
// 11-04 (Benjamin t2292u "Pass forecaster mode needs to have a studio tab usable for both views"): Studio > Pass Forecaster builds the same
// table (same data, same freezing-level borrowing) into a detached box and draws it in both frames. These hooks only read data.
window.studioPassRuns = () => mgRuns().map(r => { const [m, c] = r.split("/"); return [r, `${S.man.models[m].site} ${c.slice(8)}Z ${c.slice(4, 6)}-${c.slice(6, 8)}`]; });
window.studioPassBuild = async (run, body) => { MG.open = "pass"; MG.run = run; const D = await mgSeries(run).catch(() => null); if (MG.run !== run) return false;
  if (!D) { body.innerHTML = ""; return false; } await passTable(body, D); MG.open = null; return true; };
window.studioRunText = r => mgRunText(r);
window.studioIsEc = r => /^(ifs|ifs9|aifs|eps|aens|aensm|epsm)$/.test(r.split("/")[0]);
async function bench() {
  const out = { first: S.last };
  await new Promise(r => setTimeout(r, 4000));   // let the preloader fill the cache
  const tt = [];
  for (let k = 0; k < 12; k++) { go(1); await new Promise(r => setTimeout(r, 0)); await S.derived.get(`${S.run}/${S.prod}/${S.runs[S.run].steps[S.i].f}`); await new Promise(r => requestAnimationFrame(r)); tt.push(S.last.total_ms); }
  out.scrub_ms = tt; out.timings = S.timings.slice(0, 10);
  document.title = "BENCH " + JSON.stringify(out);
  const pre = document.createElement("pre"); pre.id = "bench"; pre.textContent = JSON.stringify(out); document.body.appendChild(pre);
}
function showErr(e) { const p = document.createElement("pre"); p.id = "err"; p.style.color = "#f88"; p.textContent = String(e && e.stack || e); document.body.appendChild(p); }
addEventListener("error", e => showErr(e.error || e.message)); addEventListener("unhandledrejection", e => showErr(e.reason));
boot();

// ---- Observations (old site's live obs module, unchanged: browser-drawn from NWS/IEM + Environment Canada, loaded on first open)
let obsLoad = null;
function obsOpen() {
  if (!$("obsov")) {
    const o = document.createElement("div"); o.id = "obsov"; o.hidden = true;
    o.innerHTML = `<div class="mg-top"><b>Observations</b><button type="button" id="obsx">Close</button></div><div id="obs-root"></div>`;
    document.body.appendChild(o); $("obsx").onclick = () => { $("obsov").hidden = true; if (window.Obs) Obs.hide(); try { sessionStorage.removeItem("vw:obs"); } catch (e) { /* private mode */ } };
  }
  $("obsov").hidden = false; try { if (!Q.get("studio") && !Q.get("embed")) sessionStorage.setItem("vw:obs", "1"); } catch (e) { /* private mode */ }
  obsLoad = obsLoad || new Promise((ok, bad) => {
    const l = document.createElement("link"); l.rel = "stylesheet"; l.href = "obs/obs.css"; document.head.appendChild(l);
    const sc = document.createElement("script"); sc.src = "obs/obs.js"; sc.onerror = bad; document.body.appendChild(sc);
    // 11-03: radar + GOES-West layers (obs/obsimg.js, off by default); the obs map still opens if it fails to load
    sc.onload = () => { const s2 = document.createElement("script"); s2.src = "obs/obsimg.js?v=20261104c"; s2.onload = ok; s2.onerror = ok; document.body.appendChild(s2); };
  });
  obsLoad.then(() => Obs.show(), () => { $("obs-root").textContent = "Observations could not load."; obsLoad = null; });
}
