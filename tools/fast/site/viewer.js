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
const Q = new URLSearchParams(location.search);
const DATA = window.WX_DATA || "data/";   // "/d/" on the hosted fast page (Pages Function -> R2)
const S = { man: null, runs: {}, view: Q.get("view") || "wa", prod: Q.get("prod") || "t2m", run: null, i: 0,
            fields: new Map(), derived: new Map(), statics: {}, pix: {}, timings: [] };
window.__S = S;

const pt = v => v * S.man.dpi / 72;                 // points -> canvas px (same as matplotlib at the encoder dpi)
const img = src => new Promise((ok, no) => { const im = new Image(); im.onload = () => ok(im); im.onerror = no; im.src = src; });

function fitPhone() {   // phones: map as large as fits between the menus and the slider bar, placed right under the menus
  const cv = $("map"); if (!cv) return;
  const LW = cv._lw || cv.width, LH = cv._lh || cv.height;   // logical (figure px) size; the bitmap can be LW x RS (sharpMap)
  cv.style.maxWidth = `min(100%, ${LW}px)`; cv.style.maxHeight = document.body.classList.contains("phone") ? "none" : `min(100%, ${LH}px)`;
  if (!document.body.classList.contains("phone") || !cv.width) { cv.style.width = cv.style.height = ""; schedSharp(); return; }
  const wr = $("wrap"), cs = getComputedStyle(wr), padX = parseFloat(cs.paddingLeft) + parseFloat(cs.paddingRight), padY = parseFloat(cs.paddingTop) + parseFloat(cs.paddingBottom);
  const vh = window.visualViewport ? visualViewport.height : innerHeight;
  const availW = document.documentElement.clientWidth - padX, availH = vh - $("bar").offsetHeight - $("dock").offsetHeight - padY;
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
function sizeMap(cv, V, keepRS) {   // bitmap = figure px x RS; context transform = RS, so all drawing stays in figure px
  const [LW, LH] = V.fig, rs = keepRS && cv._lw === LW && cv._lh === LH ? (cv._rs || 1) : wantRS(LW, LH);
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
async function boot() {
  if (Q.get("bare")) document.body.classList.add("bare");
  // 10-29: manifest, fonts and the shown run's run.json in parallel; other runs load when picked
  const [man] = await Promise.all([fetch(DATA + "manifest.json", { cache: "no-cache" }).then(r => r.json()),
                                   document.fonts.load("800 20px Montserrat"), document.fonts.load("500 12px Montserrat")]);
  S.man = man;
  // runs: "model/cycle", newest first per model; models in a fixed order
  const order = ["hrrr", "rrfs", "nbm", "gfs", "ifs", "aifs", "eps", "aens"].filter(m => S.man.models[m] && (S.man.runs[m] || []).length);
  const all = []; for (const m of order) for (const c of [...S.man.runs[m]].reverse()) all.push(`${m}/${c}`);
  const qr = Q.get("run"), qm = Q.get("model");
  S.run = all.includes(qr) ? qr : (all.find(r => qm && r.startsWith(qm + "/")) || all[0]);
  await loadRun(S.run);
  // "Runs" menu (Benjamin 10-29 7:10 PM): every available run, grouped by model, newest first; picking one keeps the valid time
  const runLabel = r => { const [m, c] = r.split("/"); return `${S.man.models[m].site} ${c.slice(8)}Z ${c.slice(4, 6)}-${c.slice(6, 8)}`; };
  $("run").innerHTML = order.map(m => `<optgroup label="${S.man.models[m].site}">` +
    all.filter(r => r.startsWith(m + "/")).map(r => `<option value="${r}"${r === S.run ? " selected" : ""}>${runLabel(r)}</option>`).join("") + "</optgroup>").join("");
  setLists();
  const f0 = Q.get("f"), steps = S.runs[S.run].steps; S.i = f0 ? Math.max(0, steps.findIndex(s => s.f == +f0)) : 0;
  const vq = Date.parse(Q.get("valid") || ""); if (!f0 && vq) { let b = 0; steps.forEach((x, k) => { if (Math.abs(Date.parse(x.valid) - vq) < Math.abs(Date.parse(steps[b].valid) - vq)) b = k; }); S.i = b; }   // old-site links
  $("step").value = S.i;
  $("run").onchange = async e => {   // keep the same valid time when switching runs/models (nearest step)
    const vt = Date.parse(S.runs[S.run].steps[S.i].valid); S.run = e.target.value; await loadRun(S.run); setLists();
    const st = S.runs[S.run].steps; let b = 0; st.forEach((x, k) => { if (Math.abs(Date.parse(x.valid) - vt) < Math.abs(Date.parse(st[b].valid) - vt)) b = k; });
    S.i = b; $("step").value = b; draw(); };
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
  $("prod").onchange = e => { S.prod = e.target.value; S.lastTab[tabOf(S.prod)] = S.prod; draw(); };
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
  await draw();
  if (Q.get("obs")) obsOpen();
  if (Q.get("mg")) mgOpen(Q.get("mg") === "pass" ? "pass" : "town");
  window.__ready = true;
  if (Q.get("bench")) bench();
}
async function loadRun(r) { if (!S.runs[r]) S.runs[r] = await (await fetch(`${DATA}runs/${r}/run.json`, { cache: "no-cache" })).json(); return S.runs[r]; }
const SV = () => (S.man.static_v ? `?v=${S.man.static_v}` : "");   // cache-buster for static layers (they are cached 1 day)
const MD = () => S.man.models[S.run.split("/")[0]];
const PRODS = () => MD().products, VIEWS = () => MD().views;
// Product tabs (Benjamin 10-30 8:04 PM: "upper air tab, surface tab, precipitation tab, snow tab", Pivotal Weather style).
// The Product menu lists only the open tab's products, in the order below (Pivotal: winds by level, 250 -> 850 mb);
// product ids / URLs are unchanged (?prod= picks its tab). Products not listed here land in an "Other" tab.
const TABS = [
  ["sfc", "Surface", ["t2m", "feels", "d2m", "t2ma", "nmaxt", "nmint", "ehigh", "elow", "et2sd", "ep32", "gust10", "gust6", "gust12", "gust24", "gustmax", "egust90",
                      "aifswind", "slp", "elows", "tcc", "vis", "fog", "ir", "waves", "wavemax", "wavemax24"]],
  ["pcp", "Precip", ["qpf", "qpf1", "nqpf1", "qpf3", "qpf6", "nqpf6", "qpf12", "qpf24", "qpf48", "nqpf12", "nqpf24", "nqpf48", "nqpftot", "eqpf90", "mslpqpf", "ptype", "refc", "pw", "pwa", "ivt",
                     "qpfa", "qpfpct"]],
  ["snow", "Snow", ["snow", "kuchera", "esnow", "esnow90", "snow1", "snow6", "snow12", "snow24", "snow48", "nsnow6", "nsnow12", "nsnow24", "nsnow48", "nsnowtot", "esnow6", "esnow12", "esnow24", "esnow48", "kuch6", "kuch12", "kuch24", "kuch48", "dsnod", "fzra", "fzra6", "fzra12", "fzra24", "fzra48", "snowlvl", "frz", "thick"]],
  ["ua", "Upper Air", ["w250", "w300", "w500", "w850", "t300w", "t500w", "t700w", "t850w", "t925w", "t850", "t700", "t850a", "z500anom", "ez500", "spag"]],
  ["svr", "Severe", ["mucape", "sbcape", "epcape", "ltng", "ltng6", "ltgp", "ntstm"]],
];
const tabOf = pid => (TABS.find(t => t[2].includes(pid)) || ["other"])[0];
S.lastTab = {};
function setLists() {   // products this run carries (all their fields present), views this model has
  const R_ = S.runs[S.run], has = new Set(R_.fields), P = PRODS(), V = VIEWS();
  const prods = Object.entries(P).filter(([k, p]) => p.fields.every(f => has.has(f)));
  const tabs = [...TABS, ["other", "Other", []]].map(([id, label, ids]) => [id, label,
    prods.filter(([k]) => tabOf(k) === id).sort((a, b) => ids.indexOf(a[0]) - ids.indexOf(b[0]))]).filter(t => t[2].length);
  if (!prods.some(([k]) => k === S.prod)) {   // not in this run: stay in the same tab when it can
    const t = tabs.find(t => t[0] === tabOf(S.prod)); S.prod = (t ? t[2][0] : prods[0])[0]; }
  const cur = tabOf(S.prod); S.lastTab[cur] = S.prod;
  $("tabs").innerHTML = tabs.map(([id, label]) => `<button type="button" role="tab" data-t="${id}" aria-selected="${id === cur}"${id === cur ? ' class="on"' : ""}>${label}</button>`).join("");
  $("tabs").onclick = e => { const b = e.target.closest("button[data-t]"); if (!b || b.dataset.t === tabOf(S.prod)) return;
    const t = tabs.find(x => x[0] === b.dataset.t), keep = S.lastTab[t[0]];
    S.prod = t[2].some(([k]) => k === keep) ? keep : t[2][0][0]; setLists(); draw(); };
  if (!V[S.view]) S.view = V.wa ? "wa" : Object.keys(V)[0];
  fill($("prod"), tabs.find(t => t[0] === cur)[2].map(([k, p]) => [k, p.title]), S.prod);
  fill($("view"), Object.entries(V).map(([k, v]) => [k, v.label]), S.view);
  $("step").max = R_.steps.length - 1; S.i = Math.min(S.i, R_.steps.length - 1);
}
function fill(sel, opts, cur) { sel.innerHTML = opts.map(([v, t]) => `<option value="${v}"${v === cur ? " selected" : ""}>${t}</option>`).join(""); }
function go(d, wrap) { const n = S.runs[S.run].steps.length; S.i = wrap ? (S.i + d + n) % n : Math.min(n - 1, Math.max(0, S.i + d)); $("step").value = S.i; draw(); }

// ---------------------------------------------------------------- static per view
async function viewStatic(vid) {
  const m = S.run.split("/")[0], sk = m + "/" + vid;
  if (S.statics[sk]) return S.statics[sk];
  const V = VIEWS()[vid];
  const p = (async () => {
    const [lut, base] = await Promise.all([fetch(DATA + V.lut + SV()).then(r => r.arrayBuffer()).then(b => new Float32Array(b)),
                                           img(DATA + `static/base_${vid}.png` + SV())]);
    // towns layer is not needed for the first paint: draw without it, redraw when it lands (10-29 first-map speedup)
    const townsP = img(DATA + `static/towns_${vid}.png` + SV()).then(im => { obj.towns = im; if (S.view === vid && window.__drawn) draw(); return im; }, () => null);
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
    const obj = { lut, base, towns: null, townsP, x0, y0, W, H, idx, wx, wy, gnx, baseU: DATA + `static/base_${vid}.png` + SV(), townsU: DATA + `static/towns_${vid}.png` + SV() }; return obj;
  })();
  S.statics[sk] = p; return p;
}
const keyImg = {}; const keyURL = (pid, vid) => DATA + PRODS()[pid].keys[vid] + SV();
const getKey = (pid, vid) => { const u = keyURL(pid, vid); return keyImg[u] || (keyImg[u] = img(u)); };

// ---------------------------------------------------------------- data images
function fieldURL(run, name, f) {   // packed runs: several fields share one RGB PNG, one channel each (run.json steps[].packs)
  const R_ = S.runs[run], st = R_.steps.find(s => s.f === f), pk = st && st.packs && st.packs[name];
  const file = pk ? pk[0] : name, ch = pk ? pk[1] : 0;
  return [`${DATA}${R_.base}/` + R_.file.replace("{name}", file).replace("{f:03d}", String(f).padStart(3, "0")), ch];
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
  const key = `${run}/${name}/${f}`;
  if (S.fields.has(key)) return S.fields.get(key);
  const p = (async () => {
    const st = S.runs[run].steps.find(s => s.f === f);
    if (!st || !st.ranges[name]) throw new Error(`nodata:${name}`);
    const [url, ch] = fieldURL(run, name, f), I = await getPixels(url);
    const [lo, hi] = st.ranges[name], sc = (hi - lo) / 255, n = I.w * I.h, out = new Float32Array(n), px = I.px;
    // image row 0 = first (southern) grid row: the encoder writes the grid as-is
    if (st.ranges[name][2] === 2) { const d = hi - lo; for (let k = 0; k < n; k++) { const q = px[k * 4 + ch] / 255; out[k] = lo + q * q * d; } }   // sqrt-coded precip
    else for (let k = 0; k < n; k++) out[k] = lo + px[k * 4 + ch] * sc;
    return { v: out, w: I.w, h: I.h, bytes: I.bytes };
  })();
  p.catch(() => S.fields.delete(key)); S.fields.set(key, p); return p;
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
  const P = S.man.models[run.split("/")[0]].products[pid], key = `${run}/${pid}/${f}`;
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
      for (let k = 0; k < a.length; k++) a[k] = src[k] * sc; out.iso = blur(a, g.w, g.h, I.sigma); }
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
function sample(st, F, k) {   // bilinear value at panel pixel k
  const i = st.idx[k]; if (i < 0) return NaN; const tx = st.wx[k], ty = st.wy[k], g = st.gnx;
  return (F[i] * (1 - tx) + F[i + 1] * tx) * (1 - ty) + (F[i + g] * (1 - tx) + F[i + g + 1] * tx) * ty;
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
function draw() {
  return new Promise(res => { S.waiters.push(res); if (!rafOn) { rafOn = true; requestAnimationFrame(pump); } });
}
async function pump() {
  rafOn = false;
  if (S.busy) { S.again = true; return; }
  S.busy = true; const ws = S.waiters; S.waiters = [];
  try { await render(!!S.dragging); } catch (e) { showErr(e); }
  finally { S.busy = false; ws.forEach(r => r()); if (S.again || S.waiters.length) { S.again = false; if (!rafOn) { rafOn = true; requestAnimationFrame(pump); } } }
}
let drawSeq = 0, urlTimer = null;
async function render(lite) {
  const seq = ++drawSeq, t0 = performance.now();
  const run = S.run, vid = S.view, pid = S.prod, step = S.runs[run].steps[S.i], f = step.f;
  let st, D, key;
  try { [st, D, key] = await Promise.all([viewStatic(vid), productFields(run, pid, f), getKey(pid, vid)]); }
  catch (e) {
    if (seq !== drawSeq) return;
    if (!String(e && e.message).startsWith("nodata:")) throw e;
    S.derived.delete(`${run}/${pid}/${f}`);
    const V = VIEWS()[vid], cv = $("map"), st2 = await viewStatic(vid);
    const ctx = sizeMap(cv, V, lite), [LW, LH] = V.fig; ctx.fillStyle = S.man.style.BG; ctx.fillRect(0, 0, LW, LH); ctx.drawImage(layer(st2.base, st2.baseU, cv._rs), 0, 0, LW, LH);
    header(ctx, V, PRODS()[pid].title, step.valid_line, `${S.runs[run].runline}  \u00b7  ${V.label}  \u00b7  not in this model run at this hour`, step.badge);
    S.cur = null; window.__drawn = `${pid}/${vid}/${f}`; return;
  }
  if (seq !== drawSeq) return;
  const t1 = performance.now();
  const V = VIEWS()[vid], P = PRODS()[pid], cv = $("map");
  const ctx = sizeMap(cv, V, lite), [LW, LH] = V.fig, rs = cv._rs; ctx.fillStyle = S.man.style.BG; ctx.fillRect(0, 0, LW, LH);
  // 1. color fill: value -> bin color, exactly the site's bins (contourf + BoundaryNorm)
  const smp = P.fill === "prt" ? sampleNN : sample;
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
  const gk = `${run}/${pid}/${vid}/${f}`;
  if (P.isobars && D.iso) drawIsobars(ctx, st, D, P, gk);
  if (P.barbs) drawBarbs(ctx, st, D, P, V);
  S.lowPanel = null;
  if (P.lows || P.spag) drawEns(ctx, st, D, P, V, gk);
  if ((P.hl || (P.isobars && (P.isobars.field || "mslp") === "mslp")) && D.iso && !P.lows) drawHL(ctx, st, D, V, gk);   // every MSLP-isobar map (incl. MSLP + wind), not the ensemble-lows map
  ctx.restore();
  // 4. towns (dots + names static) and live numbers
  const tmode = P.towns || "numbers";
  if (st.towns && tmode !== "none") ctx.drawImage(L2.towns, 0, 0, LW, LH);
  if (st.towns && tmode === "numbers") for (const t of V.towns) {
    if (!(t.fi >= 0 && t.fj >= 0 && t.fi < D.h - 1 && t.fj < D.w - 1)) continue;
    let v = sampleRC(D.fill, D.w, t.fi, t.fj); if (!isFinite(v)) continue;   // HRRR: integer = nearest 3 km point; global: bilinear at the pin
    if (pid === "t2m" && t.t2m_corr !== undefined) v += t.t2m_corr;          // pass summit height correction (temp_maps)
    haloText(ctx, fmtVal(P, v), t.x * LW, t.y * LH, `800 ${pt(t.size)}px Montserrat`, t.color, pt(3.0), "left", "middle");
  }
  if (P.lows && S.lowPanel) paintLowPanel(ctx, st, V, S.lowPanel);
  // 5. key + header text
  ctx.drawImage(L2.key, 0, 0, LW, LH);
  const [r0, r1, c0, c1] = V.cut;                                            // same rows/cols temp_maps.cut() keeps
  if (!D.pct) D.pct = {};
  if (!D.pct[vid]) { const a = new Float32Array(Math.ceil((r1 - r0) / 2) * Math.ceil((c1 - c0) / 2)); let n = 0;   // every 2nd cell
    for (let r = r0; r < r1; r += 2) for (let c = c0; c < c1; c += 2) a[n++] = D.fill[r * D.w + c]; D.pct[vid] = a.subarray(0, n).sort(); }
  const fin = D.pct[vid];
  const pc = p => fin[Math.min(fin.length - 1, Math.max(0, Math.round(p / 100 * (fin.length - 1))))];
  const extra = (P.isobars && !D.iso && P.extra_noh ? P.extra_noh : P.extra).replace("{lo}", pc(P.pct[0]).toFixed(P.dec || 0)).replace("{hi}", pc(P.pct[1]).toFixed(P.dec || 0));
  header(ctx, V, P.title, step.valid_line, `${S.runs[run].runline}  \u00b7  ${V.label}  \u00b7  ${extra}`, step.badge);
  const t3 = performance.now();
  S.cur = { st, D, vals, P, pid, V, run, f };
  S.last = { data_ms: t1 - t0, fill_ms: t2 - t1, overlay_ms: t3 - t2, total_ms: t3 - t0 };
  $("stat").textContent = `F+${f}  data ${S.last.data_ms.toFixed(0)} ms · fill ${S.last.fill_ms.toFixed(0)} ms · lines/labels ${S.last.overlay_ms.toFixed(0)} ms`;
  window.__drawn = `${pid}/${vid}/${f}` + (lite ? "~" : ""); window.__rs = rs;
  if (lite) return;
  // iOS Safari throws after 100 history.replaceState calls in 10 s: update the URL once things settle
  clearTimeout(urlTimer); urlTimer = setTimeout(() => { const u = new URL(location); u.searchParams.set("prod", pid); u.searchParams.set("view", vid);
    u.searchParams.set("f", f); u.searchParams.set("run", run); u.searchParams.delete("model"); try { history.replaceState(null, "", u); } catch (e) {} }, 400);
  preload(run, pid, S.i);
}

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
const UNITS = { ivt: " kg/m/s", fog: "", waves: " ft", wavemax: " ft", ehigh: "\u00b0F", elow: "\u00b0F", d2m: "\u00b0F", feels: "\u00b0F", gustmax: " mph", t925w: "\u00b0C", t850w: "\u00b0C", t700w: "\u00b0C", t500w: "\u00b0C", t300w: "\u00b0C", w850: " kt", thick: " dam", slp: " mb", pw: " in", pwa: " in", ptype: "", qpfa: " in", qpfpct: "%", eqpf90: " in", esnow: " in", esnow90: " in", egust90: " mph", epcape: "%", elows: "%", spag: " m", nqpf1: " in", nqpf6: " in", nsnow6: " in", ntstm: "%", nmaxt: "\u00b0F", nmint: "\u00b0F", dsnod: " in", qpf3: " in", qpf12: " in", qpf48: " in", snow1: " in", snow6: " in", gust6: " mph", ltng6: " /km\u00b2/5 min", qpf1: " in", qpf6: " in", qpf24: " in", mslpqpf: " in", t2ma: "\u00b0F", t850a: "\u00b0C", et2sd: "\u00b0F", ep32: "%", ez500: " m", w500: " kt", w300: " kt", w250: " kt", z500anom: " m", mucape: " J/kg", sbcape: " J/kg", ltng: " /km\u00b2/5 min", ltgp: " in", t2m: "\u00b0F", gust10: " mph", aifswind: " mph", t850: "\u00b0C", t700: "\u00b0C", tcc: "%", vis: " mi", ir: "\u00b0C",
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
    if (isFinite(m)) s += mb ? ` \u00b7 ${m.toFixed(C.pid === "aifswind" ? 1 : 0)} mb` : ` \u00b7 ${Math.round(m)} dam`; }
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
  schedSharp();
}
function resetZoom() { Z.k = 1; Z.x = 0; Z.y = 0; applyZoom(); }
function zoomAt(cx, cy, k2) {   // keep the map point under (cx, cy) fixed
  const cv = $("map"), r = cv.getBoundingClientRect(), l0 = r.left - Z.x, t0 = r.top - Z.y;
  const px = (cx - l0 - Z.x) / Z.k, py = (cy - t0 - Z.y) / Z.k; k2 = Math.min(6, Math.max(1, k2));
  Z.x = cx - l0 - px * k2; Z.y = cy - t0 - py * k2; Z.k = k2; applyZoom();
}
function setupPointer() {
  const cv = $("map"), P = new Map(); let down = null, pinch = null, lastTap = 0, moved = false;
  cv.style.transformOrigin = "0 0";
  const wr = $("wrap"); wr.style.overflow = "hidden";
  if (!$("zreset")) { const b = document.createElement("button"); b.id = "zreset"; b.type = "button"; b.textContent = "Reset zoom"; b.hidden = true; b.onclick = resetZoom; wr.appendChild(b); }
  cv.addEventListener("wheel", e => { e.preventDefault(); zoomAt(e.clientX, e.clientY, Z.k * Math.exp(-e.deltaY * (e.ctrlKey ? 0.01 : 0.0015))); }, { passive: false });
  cv.addEventListener("dblclick", e => { e.preventDefault(); if (Z.k > 1) resetZoom(); else zoomAt(e.clientX, e.clientY, 2.5); });
  cv.addEventListener("pointermove", e => {
    if (e.pointerType === "mouse" && !P.size) readout(e);
    if (!P.has(e.pointerId)) return; const p0 = P.get(e.pointerId); P.set(e.pointerId, { x: e.clientX, y: e.clientY });
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
function saveImage() {
  const cv = $("map"); if (!cv.width) return;
  const name = saveName();
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
  $("save").textContent = "Saved"; setTimeout(() => $("save").textContent = "Save image", 1500);
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

function drawIsobars(ctx, st, D, P, gk) {
  const I = P.isobars, { all, labels } = geo(`iso/${gk}`, () => isoGeom(ctx, st, D, I));
  paintIsobars(ctx, I, all, labels);
}
function isoGeom(ctx, st, D, I) {
  const G = cgrid(st, 4, k => sample(st, D.iso, k)), iso = G.g;   // only the 4 px points contour() reads: same lines
  let lo = Infinity, hi = -Infinity;
  for (let k = 0; k < iso.length; k++) { const v = iso[k]; if (v < lo) lo = v; if (v > hi) hi = v; }
  const labels = [], all = [];
  ctx.save(); ctx.font = `700 ${pt(10)}px Montserrat`;
  for (let L = Math.ceil(lo / I.every) * I.every; L <= hi; L += I.every) {
    const lines = contourG(st, G, L); all.push(lines);
    for (const l of lines) {   // one label per ~600 px of line, inline (line cut under the label)
      let len = 0; const cum = [0]; for (let k = 1; k < l.length; k++) { len += Math.hypot(l[k][0] - l[k - 1][0], l[k][1] - l[k - 1][1]); cum.push(len); }
      if (len < 160) continue;
      const nlab = Math.max(1, Math.floor(len / 600));
      for (let q = 0; q < nlab; q++) {
        const target = len * (q + 0.5) / nlab, k = cum.findIndex(c => c >= target), p = l[Math.max(0, k)];
        if (labels.some(b => Math.hypot(b.x - p[0], b.y - p[1]) < 120)) continue;
        if (p[0] < st.x0 + 20 || p[0] > st.x0 + st.W - 20 || p[1] < st.y0 + 12 || p[1] > st.y0 + st.H - 12) continue;
        const a = l[Math.max(0, k - 3)], b = l[Math.min(l.length - 1, k + 3)]; let ang = Math.atan2(b[1] - a[1], b[0] - a[0]);
        if (ang > Math.PI / 2) ang -= Math.PI; if (ang < -Math.PI / 2) ang += Math.PI;
        labels.push({ x: p[0], y: p[1], ang, s: String(L), w: ctx.measureText(String(L)).width + pt(6) });
      }
    }
  }
  ctx.restore();
  return { all, labels };
}
function paintIsobars(ctx, I, all, labels) {
  ctx.save();   // clip out label boxes so lines break under the numbers (matplotlib clabel inline)
  ctx.beginPath(); ctx.rect(0, 0, ctx.canvas.width, ctx.canvas.height);
  for (const b of labels) {
    const c = Math.cos(b.ang), s = Math.sin(b.ang), hw = b.w / 2, hh = pt(6);
    const pts = [[-hw, -hh], [hw, -hh], [hw, hh], [-hw, hh]].map(([x, y]) => [b.x + x * c - y * s, b.y + x * s + y * c]);
    ctx.moveTo(...pts[0]); for (let k = 3; k >= 1; k--) ctx.lineTo(...pts[k]); ctx.closePath();   // opposite winding
  }
  ctx.clip("nonzero");
  for (const lines of all) strokeLines(ctx, lines, "#ffffff", pt(I.halo), null);
  for (const lines of all) strokeLines(ctx, lines, I.color, pt(I.lw), null);
  ctx.restore();
  for (const b of labels) {
    ctx.save(); ctx.translate(b.x, b.y); ctx.rotate(b.ang);
    haloText(ctx, b.s, 0, 0, `700 ${pt(10)}px Montserrat`, I.color, pt(3.2), "center", "middle"); ctx.restore();
  }
}

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
function drawHL(ctx, st, D, V, gk) {
  const out = geo(`hl/${gk}`, () => hlGeom(st, D, V));
  paintHL(ctx, out);
}
function hlGeom(st, D, V) {
  const raw = D.raw && D.raw.mslp ? D.raw.mslp.v : D.iso; if (!raw) return [];
  const m = S.run.split("/")[0], M = S.man.models[m], cr = M.crop || [0, 0, 0, 0], ll = M.grid === "ll";
  const ck = ll ? 27.8 : parseFloat(M.res) || 3, s = ll ? 1 : Math.max(1, Math.round(9 / ck)), w0 = D.w, h0 = D.h;
  const [rk, prom, smk] = HL_VIEW[S.view] || HL_WA, cell = ck * s;
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
function paintHL(ctx, out) {
  for (const [X, Y, v, hi] of out) { const col = hi ? HL_HIGH_COLOR : HL_LOW_COLOR;
    haloText(ctx, hi ? "H" : "L", X, Y, `900 ${pt(16)}px Montserrat`, col, pt(2.4), "center", "middle");
    haloText(ctx, String(Math.round(v)), X, Y + pt(9.5), `800 ${pt(9)}px Montserrat`, col, pt(2.2), "center", "top"); }
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
    for (const [x, y, v] of g.means) {
      haloText(ctx, "L", x, y, `900 ${pt(18)}px Montserrat`, "#d7191c", pt(2.4), "center", "middle");
      haloText(ctx, String(Math.round(v)), x, y + pt(14), `900 ${pt(11)}px Montserrat`, "#1b1d22", pt(2.4), "center", "top"); }
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
    L.push({ mem: mem + 1, fi, fj, mb, la: lat(fi), lo: lon(fj), x: st.x0 + p[0], y: st.y0 + p[1] }); }
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
  if (raw) { const vid = S.view, [rk, prom, sm] = LOWV[vid] || [300, 1.2, 0.6], w = D.w, h = D.h, a = blur(raw, w, h, sm);
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
  const tagged = L.map(o => [o.mb, o.mem]).sort((x, y) => x[0] - y[0]);
  // list box on the side that hides fewer member dots / mean lows (old site: box outside the map, which a fixed basemap can't do)
  const PW = 0.092 * V.fig[0] + 0.03 * V.fig[0], hid = x0_ => dots.filter(d => d[0] >= x0_ && d[0] <= x0_ + PW).length + 10 * means.filter(d => d[0] >= x0_ && d[0] <= x0_ + PW).length;
  const side = hid(st.x0) <= hid(st.x0 + st.W - PW) ? "left" : "right";
  return { side, dots, core, means, strong: tagged.slice(0, 10), weak: tagged.slice().reverse().slice(0, 10), n: E.n || 50,
           meanVals: means.map(x => x[2]).sort((x, y) => x - y) };
}
function paintLowPanel(ctx, st, V, g) {   // ens_maps.low_panel, drawn inside the left edge of the map + the dot legend
  const [LW, LH] = V.fig, PW = Math.round(0.092 * LW), x0 = g.side === "right" ? st.x0 + st.W - PW - pt(3) : st.x0 + pt(3), y0 = st.y0 + pt(3), H = st.H - pt(6);
  const ms = g.meanVals.slice(0, 4), mrows = Math.max(1, Math.ceil(ms.length / 2));
  const need = 1.2 + 1.4 + 1.05 + 1.2 * mrows + 0.4 + 2 * (1.05 + 10) + 0.5, lh = Math.min(pt(20.2), H / (need + 0.5));
  ctx.save(); ctx.globalAlpha = 0.95; ctx.fillStyle = "#f6f3ec"; ctx.strokeStyle = "#c9c4b8"; ctx.lineWidth = 1;
  ctx.beginPath(); ctx.roundRect ? ctx.roundRect(x0, y0, PW, H, pt(3)) : ctx.rect(x0, y0, PW, H); ctx.fill(); ctx.stroke(); ctx.globalAlpha = 1;
  ctx.textAlign = "left"; ctx.textBaseline = "top";
  const t = (x, y, s, w, sz, col) => { ctx.font = `${w} ${pt(sz)}px Montserrat`; ctx.fillStyle = col || "#1b1d22"; ctx.fillText(s, x, y); };
  const xl = x0 + 0.007 * LW, cw = (PW - 0.014 * LW) / 2; let y = y0 + 0.3 * lh;
  t(xl, y, "Lows (mb)", 800, 13.6); y += lh * 1.2;
  t(xl, y, `in view \u00b7 ${g.n} mem.`, 500, 10.0, "#5b5e66"); y += lh * 1.4;
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
      t(xl + 0.011 * LW, y, String(Math.round(p)), 800, 11.7); t(xl + 0.041 * LW, y, `#${m}`, 500, 10.6, "#5b5e66"); y += lh; }
    y += lh * 0.5;
  }
  // "Member low (mb)" legend, lower left of the map just right of the list (old: matplotlib legend, lower left)
  const lw = pt(78), rh = pt(11), lhgt = rh * (DOT_LABELS.length + 1) + pt(8), lx = g.side === "right" ? x0 - lw - pt(5) : x0 + PW + pt(5), ly = st.y0 + st.H - lhgt - pt(5);
  ctx.globalAlpha = 0.92; ctx.fillStyle = "#ffffff"; ctx.fillRect(lx, ly, lw, lhgt); ctx.globalAlpha = 1; ctx.strokeStyle = "#c9c4b8"; ctx.strokeRect(lx, ly, lw, lhgt);
  t(lx + pt(5), ly + pt(4), "Member low (mb)", 700, 7.5);
  DOT_LABELS.forEach((s, k) => { const yy = ly + pt(4) + rh * (k + 1); ctx.beginPath(); ctx.arc(lx + pt(9), yy + rh * 0.42, pt(2.8), 0, 2 * Math.PI);
    ctx.fillStyle = DOT_COLS[k]; ctx.fill(); ctx.strokeStyle = "#ffffff"; ctx.lineWidth = 0.6; ctx.stroke(); t(lx + pt(16), yy, s, 500, 7.2); });
  ctx.restore();
}
// ---- Stage 5 (10-30): meteograms + Pass Forecaster. The runner samples every town / pass slot at full precision each step
// (single/pts_fFFF.json, order = run.json "points"), so a meteogram is ~1 small JSON per step, never map images.
const MG = { open: null, town: Q.get("town") || "Seattle", run: null, cache: new Map() };
const PTZ = "America/Los_Angeles";
const fmtPT = (iso, o) => new Intl.DateTimeFormat("en-US", Object.assign({ timeZone: PTZ }, o)).format(new Date(iso));
function mgRuns() {   // newest run of each model that carries town points
  const order = ["hrrr", "rrfs", "nbm", "gfs", "ifs", "aifs", "eps", "aens"], out = [];
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
  mgClose(); MG.open = kind; MG.run = S.runs[S.run] && S.runs[S.run].points ? S.run : (mgRuns()[0] || S.run);
  const o = document.createElement("div"); o.id = "mg";
  o.innerHTML = `<div class="mg-top"><b>${kind === "pass" ? "Pass Forecaster" : "Meteogram"}</b>
    <label>Model <select id="mgrun"></select></label>${kind === "pass" ? "" : `<label>Place <select id="mgtown"></select></label>`}
    <a id="mgpage" href="meteograms" title="Full meteograms page (old-site layout: plumes, member grids, multi-run)"><span class="lg">Meteograms page</span><span class="sm">Full page</span></a><button type="button" id="mgx">Close</button></div><div id="mgbody"><div class="mg-msg">Loading\u2026</div></div>`;
  document.body.appendChild(o); $("mgx").onclick = mgClose;
  const runLabel = r => { const [m, c] = r.split("/"); return `${S.man.models[m].site} ${c.slice(8)}Z ${c.slice(4, 6)}-${c.slice(6, 8)}`; };
  const rs = mgRuns(); if (!rs.includes(MG.run)) rs.unshift(MG.run);
  fill($("mgrun"), rs.map(r => [r, runLabel(r)]), MG.run);
  $("mgrun").onchange = e => { MG.run = e.target.value; mgDraw(); };
  if ($("mgtown")) $("mgtown").onchange = e => { MG.town = e.target.value; mgDraw(); };
  addEventListener("resize", mgResize); mgDraw();
}
function mgClose() { const o = $("mg"); if (o) o.remove(); MG.open = null; removeEventListener("resize", mgResize); }
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
  const npan = [T.t2m, T.wind || T.gust, T.pcp || T.snow || T.snow6 || T.pcp6, T.tcc].filter(Boolean).length;   // each panel has its own time axis (Benjamin 10-30)
  const H = Math.max(sm0 ? 520 : 560, 52 + 40 * npan + (sm0 ? 52 : 60) * 8, box.clientHeight - 4);
  cv.width = W * dpr; cv.height = H * dpr; cv.style.width = W + "px"; cv.style.height = H + "px";
  const c = cv.getContext("2d"); c.scale(dpr, dpr); c.fillStyle = "#15171c"; c.fillRect(0, 0, W, H);
  const [m] = MG.run.split("/"), site = S.man.models[m].site, small = W < 600;
  const L = small ? 38 : 52, Rm = small ? 34 : 50, top = small ? 46 : 52, bot = 34, n = T.f.length;   // bot / gap = room for the time axis under each panel
  const panels = [["temp", 3], ["wind", 2], ["pcp", 2], ["cloud", 1]].filter(([k]) => k === "temp" ? T.t2m : k === "wind" ? (T.wind || T.gust) : k === "pcp" ? (T.pcp || T.snow || T.snow6 || T.pcp6) : T.tcc);
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
      if (!T.p32) fzNote();
      if (T.p32) { const s2 = scale(0, 100); line(T.p32, s2, "#7fd1ff", 1.5, [2, 3]); axis(0, 100, s2, "%", true, "#7fd1ff"); fzNote(); { c.font = `700 ${small ? 10 : 12}px Montserrat`; const lab = "chance \u2264 32\u00b0F (right axis)", px0 = fzX + fzW + 10, fits = L + 6 + px0 + c.measureText(lab).width < W - Rm - 4; label(lab, "#7fd1ff", fits ? px0 : 0, fits ? fzY : fzY + rowH); } }
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
      const hiP = Math.max(0.1, ...(pc || []).filter(v => v != null), ...(p6 || []).filter(v => v != null)), scP = scale(0, niceStep(hiP) * Math.ceil(hiP / niceStep(hiP)));
      const runS = sn ? sn.reduce((acc, v, k) => (acc.push((acc[k - 1] || 0) + (v || 0)), acc), []) : sn6 ? (() => { let q = 0; return sn6.map((v, k) => T.f[k] % 6 === 0 ? (q += v || 0) : null); })() : [];
      const anySnow = (sn || sn6 || []).some(v => v > 0.05), hiS = Math.max(1, ...runS.filter(v => v != null)), topS = niceStep(hiS) * Math.ceil(hiS / niceStep(hiS)), scS = scale(0, topS);
      const pTop = niceStep(hiP) * Math.ceil(hiP / niceStep(hiP)); axis(0, pTop, scP, "\u2033", false, "#6fd38a");
      if (p6 && T.pcp) bars(p6.map((v, k) => T.f[k] % 6 === 0 && T.f[k] > 36 ? v : null), scP, "#3ea95888", 2.2);
      if (pc) bars(pc, scP, "#3ea958"); else if (p6) bars(p6.map((v, k) => T.f[k] % 6 === 0 ? v : null), scP, "#3ea958", 2.2);
      if (anySnow) { axis(0, topS, scS, "\u2033", true, "#d9ecff"); line(runS, scS, "#d9ecff", 2); }
      const tot = pc ? pc.reduce((a, v) => a + (v || 0), 0) : sum6(T, p6, -1, 1e9) || 0;
      let dx = label(`Precip per ${pc ? (T.f[1] - T.f[0] || 1) + " h" : "6 h"} (total ${tot.toFixed(2)}\u2033)`, "#6fd38a");
      if (anySnow) { const ts = (sn || []).reduce((a, v) => a + (v || 0), 0) || sum6(T, sn6, -1, 1e9) || 0; label(`Snow running total ${ts.toFixed(1)}\u2033${T.snowEst ? " (est.)" : ""}`, "#d9ecff", dx); }
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
    document.body.appendChild(o); $("obsx").onclick = () => { $("obsov").hidden = true; if (window.Obs) Obs.hide(); };
  }
  $("obsov").hidden = false;
  obsLoad = obsLoad || new Promise((ok, bad) => {
    const l = document.createElement("link"); l.rel = "stylesheet"; l.href = "obs/obs.css"; document.head.appendChild(l);
    const sc = document.createElement("script"); sc.src = "obs/obs.js"; sc.onload = ok; sc.onerror = bad; document.body.appendChild(sc);
  });
  obsLoad.then(() => Obs.show(), () => { $("obs-root").textContent = "Observations could not load."; obsLoad = null; });
}
