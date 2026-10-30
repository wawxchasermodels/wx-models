// PROTOTYPE fast viewer: draws HRRR maps in the browser from 8-bit data images (values stored in pixel colors).
// No framework. Static layers (borders, towns, color keys) are drawn once by the encoder with the site's own code.
"use strict";
const $ = id => document.getElementById(id);
const Q = new URLSearchParams(location.search);
const DATA = window.WX_DATA || "data/";   // "/d/" on the hosted fast page (Pages Function -> R2)
const S = { man: null, runs: {}, view: Q.get("view") || "wa", prod: Q.get("prod") || "t2m", run: null, i: 0,
            fields: new Map(), derived: new Map(), statics: {}, pix: {}, timings: [] };
window.__S = S;

const pt = v => v * S.man.dpi / 72;                 // points -> canvas px (same as matplotlib at the encoder dpi)
const img = src => new Promise((ok, no) => { const im = new Image(); im.onload = () => ok(im); im.onerror = no; im.src = src; });

function fitPhone() {   // phones: map as large as fits between the menus and the slider bar, placed right under the menus
  const cv = $("map"); if (!cv) return;
  if (!document.body.classList.contains("phone") || !cv.width) { cv.style.width = cv.style.height = ""; return; }
  const wr = $("wrap"), cs = getComputedStyle(wr), padX = parseFloat(cs.paddingLeft) + parseFloat(cs.paddingRight), padY = parseFloat(cs.paddingTop) + parseFloat(cs.paddingBottom);
  const vh = window.visualViewport ? visualViewport.height : innerHeight;
  const availW = document.documentElement.clientWidth - padX, availH = vh - $("bar").offsetHeight - $("dock").offsetHeight - padY;
  const k = Math.max(0.05, Math.min(availW / cv.width, availH / cv.height));
  cv.style.width = Math.floor(cv.width * k) + "px"; cv.style.height = Math.floor(cv.height * k) + "px";
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
  const f0 = Q.get("f"), steps = S.runs[S.run].steps; S.i = f0 ? Math.max(0, steps.findIndex(s => s.f == +f0)) : 0; $("step").value = S.i;
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
  $("prod").onchange = e => { S.prod = e.target.value; draw(); };
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
function setLists() {   // products this run carries (all their fields present), views this model has
  const R_ = S.runs[S.run], has = new Set(R_.fields), P = PRODS(), V = VIEWS();
  const prods = Object.entries(P).filter(([k, p]) => p.fields.every(f => has.has(f)));
  if (!prods.some(([k]) => k === S.prod)) S.prod = prods[0][0];
  if (!V[S.view]) S.view = V.wa ? "wa" : Object.keys(V)[0];
  fill($("prod"), prods.map(([k, p]) => [k, p.title]), S.prod);
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
    const obj = { lut, base, towns: null, townsP, x0, y0, W, H, idx, wx, wy, gnx }; return obj;
  })();
  S.statics[sk] = p; return p;
}
const keyImg = {}; const getKey = (pid, vid) => { const u = DATA + PRODS()[pid].keys[vid] + SV(); return keyImg[u] || (keyImg[u] = img(u)); };

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
    const g = F[P.fields[0]]; const out = { w: g.w, h: g.h, raw: F };
    if (P.fill === "wspd") {   // wind speed from u/v (kt); MSLP + 10 m wind shows mph, upper-level winds kt
      const [un, vn] = P.wind || ["u10", "v10"], u = F[un].v, v = F[vn].v, sp = new Float32Array(u.length), mul = P.spd_mult ?? (2.23694 / 1.94384);
      for (let k = 0; k < u.length; k++) sp[k] = Math.hypot(u[k], v[k]) * mul;
      out.fill = blur(sp, g.w, g.h, P.spd_sigma);
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
      const fld = P.wfield || P.fields[0], fs = S.runs[run].steps.map(x => x.f).filter(x => x > f - P.window && x <= f);
      if (f - P.window < 0 && !P.sofar) throw new Error(`nodata:${fld}`);
      const arrs = await Promise.all(fs.map(x => getField(run, fld, x).then(r => r.v, () => null))), ok = arrs.filter(Boolean);
      if (!ok.length) throw new Error(`nodata:${fld}`);
      const o = new Float32Array(ok[0]);
      if (P.wsum) { for (const a of ok.slice(1)) for (let k = 0; k < o.length; k++) o[k] += a[k]; }   // per-interval amounts -> total
      else if (P.wmin) { for (const a of ok.slice(1)) for (let k = 0; k < o.length; k++) if (a[k] < o[k]) o[k] = a[k]; }
      else for (const a of ok.slice(1)) for (let k = 0; k < o.length; k++) if (a[k] > o[k]) o[k] = a[k];
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
    if (P.lows || P.spag) out.ens = await fetch(`${DATA}runs/${run}/single/ens_f${String(f).padStart(3, "0")}.json`).then(r => r.ok ? r.json() : null, () => null);
    if (P.isobars) { const I = P.isobars, src = F[I.field || "mslp"].v, sc = I.scale || 1, a = new Float32Array(src.length);
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
// overlap; while the slider is being dragged the map is drawn in a lighter mode (fill at half resolution, no contour /
// isobar / barb lines, URL not touched), then once at full quality when the finger lifts.
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
    const V = VIEWS()[vid], cv = $("map"), st2 = await viewStatic(vid); if (cv.width !== V.fig[0]) { cv.width = V.fig[0]; cv.height = V.fig[1]; fitPhone(); }
    const ctx = cv.getContext("2d"); ctx.fillStyle = S.man.style.BG; ctx.fillRect(0, 0, cv.width, cv.height); ctx.drawImage(st2.base, 0, 0, cv.width, cv.height);
    header(ctx, V, PRODS()[pid].title, step.valid_line, `${S.runs[run].runline}  \u00b7  ${V.label}  \u00b7  not in this model run at this hour`, step.badge);
    S.cur = null; window.__drawn = `${pid}/${vid}/${f}`; return;
  }
  if (seq !== drawSeq) return;
  const t1 = performance.now();
  const V = VIEWS()[vid], P = PRODS()[pid], cv = $("map");
  if (cv.width !== V.fig[0] || cv.height !== V.fig[1]) { cv.width = V.fig[0]; cv.height = V.fig[1]; fitPhone(); }
  const ctx = cv.getContext("2d"); ctx.fillStyle = S.man.style.BG; ctx.fillRect(0, 0, cv.width, cv.height);
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
  } else for (let k = 0; k < n; k++) {
    const v = smp(st, F, k); vals[k] = v; if (v !== v || (mins !== undefined && v < mins)) continue;
    let c; if (v < pal.L0) c = pal.under; else if (v >= pal.Lend) c = pal.over; else c = pal.cols[bin(pal, v)];
    if (!c) continue; const q = k * 4; o[q] = c[0]; o[q + 1] = c[1]; o[q + 2] = c[2]; o[q + 3] = 255;
  }
  const tmp = new OffscreenCanvas(st.W, st.H); tmp.getContext("2d").putImageData(im, 0, 0); ctx.drawImage(tmp, st.x0, st.y0);
  const t2 = performance.now();
  // 2. borders/coast/frame + header box (static layer)
  ctx.drawImage(st.base, 0, 0, cv.width, cv.height);
  // 3. product lines
  ctx.save(); ctx.beginPath(); ctx.rect(st.x0, st.y0, st.W, st.H); ctx.clip();
  if (!lite && P.freeze !== undefined) {
    const lines = contour(st, vals, P.freeze, 3);
    strokeLines(ctx, lines, "#ffffff", pt(3.0), [pt(3.7 * P.freeze_lw), pt(1.6 * P.freeze_lw)]);   // matplotlib halo: 3 pt stroke, dashed with the line
    strokeLines(ctx, lines, P.freeze_color, pt(P.freeze_lw), [pt(3.7 * P.freeze_lw), pt(1.6 * P.freeze_lw)]);
  }
  if (!lite && P.isobars) drawIsobars(ctx, st, D, P);
  if (!lite && P.barbs) drawBarbs(ctx, st, D, P, V);
  if (!lite && (P.lows || P.spag)) drawEns(ctx, st, D, P, V);
  if (!lite && P.hl) drawHL(ctx, st, D, V);
  ctx.restore();
  // 4. towns (dots + names static) and live numbers
  const tmode = P.towns || "numbers";
  if (st.towns && tmode !== "none") ctx.drawImage(st.towns, 0, 0, cv.width, cv.height);
  if (st.towns && tmode === "numbers") for (const t of V.towns) {
    if (!(t.fi >= 0 && t.fj >= 0 && t.fi < D.h - 1 && t.fj < D.w - 1)) continue;
    let v = sampleRC(D.fill, D.w, t.fi, t.fj); if (!isFinite(v)) continue;   // HRRR: integer = nearest 3 km point; global: bilinear at the pin
    if (pid === "t2m" && t.t2m_corr !== undefined) v += t.t2m_corr;          // pass summit height correction (temp_maps)
    haloText(ctx, fmtVal(P, v), t.x * cv.width, t.y * cv.height, `800 ${pt(t.size)}px Montserrat`, t.color, pt(3.0), "left", "middle");
  }
  // 5. key + header text
  ctx.drawImage(key, 0, 0, cv.width, cv.height);
  const [r0, r1, c0, c1] = V.cut;                                            // same rows/cols temp_maps.cut() keeps
  if (!D.pct) D.pct = {};
  if (!D.pct[vid]) { const a = new Float32Array(Math.ceil((r1 - r0) / 2) * Math.ceil((c1 - c0) / 2)); let n = 0;   // every 2nd cell
    for (let r = r0; r < r1; r += 2) for (let c = c0; c < c1; c += 2) a[n++] = D.fill[r * D.w + c]; D.pct[vid] = a.subarray(0, n).sort(); }
  const fin = D.pct[vid];
  const pc = p => fin[Math.min(fin.length - 1, Math.max(0, Math.round(p / 100 * (fin.length - 1))))];
  const extra = P.extra.replace("{lo}", pc(P.pct[0]).toFixed(P.dec || 0)).replace("{hi}", pc(P.pct[1]).toFixed(P.dec || 0));
  header(ctx, V, P.title, step.valid_line, `${S.runs[run].runline}  \u00b7  ${V.label}  \u00b7  ${extra}`, step.badge);
  const t3 = performance.now();
  S.cur = { st, D, vals, P, pid, V, run, f };
  S.last = { data_ms: t1 - t0, fill_ms: t2 - t1, overlay_ms: t3 - t2, total_ms: t3 - t0 };
  $("stat").textContent = `F+${f}  data ${S.last.data_ms.toFixed(0)} ms · fill ${S.last.fill_ms.toFixed(0)} ms · lines/labels ${S.last.overlay_ms.toFixed(0)} ms`;
  window.__drawn = `${pid}/${vid}/${f}` + (lite ? "~" : "");
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
const UNITS = { ivt: " kg/m/s", fog: "", waves: " ft", wavemax: " ft", ehigh: "\u00b0F", elow: "\u00b0F", d2m: "\u00b0F", feels: "\u00b0F", gustmax: " mph", t925w: "\u00b0C", t850w: "\u00b0C", t700w: "\u00b0C", t500w: "\u00b0C", t300w: "\u00b0C", w850: " kt", thick: " dam", slp: " mb", pw: " in", pwa: " in", ptype: "", qpfa: " in", qpfpct: "%", eqpf90: " in", esnow: " in", esnow90: " in", egust90: " mph", epcape: "%", elows: "%", spag: " m", nqpf1: " in", nqpf6: " in", nsnow6: " in", ntstm: "%", nmaxt: "\u00b0F", nmint: "\u00b0F", dsnod: " in", qpf3: " in", qpf12: " in", qpf48: " in", snow1: " in", snow6: " in", gust6: " mph", ltng6: " /km\u00b2/5 min", qpf1: " in", qpf6: " in", qpf24: " in", mslpqpf: " in", t2ma: "\u00b0F", t850a: "\u00b0C", et2sd: "\u00b0F", ep32: "%", ez500: " m", w500: " kt", w250: " kt", z500anom: " m", mucape: " J/kg", sbcape: " J/kg", ltng: " /km\u00b2/5 min", ltgp: " in", t2m: "\u00b0F", gust10: " mph", aifswind: " mph", t850: "\u00b0C", t700: "\u00b0C", tcc: "%", vis: " mi", ir: "\u00b0C",
                refc: " dBZ", qpf: " in", snow: " in", frz: " ft", snowlvl: " ft" };
// value under the cursor / tap (item 1) and swipe to step (item 6)
function readout(ev) {
  const C = S.cur, tip = $("tip"); if (!C || !tip) return;
  const cv = $("map"), r = cv.getBoundingClientRect(), X = (ev.clientX - r.left) * cv.width / r.width, Y = (ev.clientY - r.top) * cv.height / r.height;
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

// marching squares on panel pixels (every s px), segments joined into polylines (canvas coords)
function contour(st, vals, level, s) {
  const W = st.W, H = st.H, nx = Math.floor((W - 1) / s) + 1, ny = Math.floor((H - 1) / s) + 1, g = new Float32Array(nx * ny);
  for (let j = 0; j < ny; j++) for (let i = 0; i < nx; i++) g[j * nx + i] = vals[(j * s) * W + i * s];
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

function drawIsobars(ctx, st, D, P) {
  const I = P.isobars, n = st.W * st.H, iso = new Float32Array(n);
  let lo = Infinity, hi = -Infinity;
  for (let k = 0; k < n; k++) { const v = sample(st, D.iso, k); iso[k] = v; if (v < lo) lo = v; if (v > hi) hi = v; }
  const labels = [], all = [];
  ctx.font = `700 ${pt(10)}px Montserrat`;
  for (let L = Math.ceil(lo / I.every) * I.every; L <= hi; L += I.every) {
    const lines = contour(st, iso, L, 4); all.push(lines);
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
function drawHL(ctx, st, D, V) {   // H / L centres: extremes of smoothed MSLP over a ~ 1/12-panel window, labelled with the pressure
  const w = D.w, h = D.h, a = D.iso, r = Math.max(4, Math.round(Math.min(w, h) / 14)), out = [];
  for (let i = r; i < h - r; i += 2) for (let j = r; j < w - r; j += 2) {
    const v = a[i * w + j]; let mx = true, mn = true;
    for (let di = -r; di <= r && (mx || mn); di += 2) for (let dj = -r; dj <= r; dj += 2) { const q = a[(i + di) * w + j + dj]; if (q > v) mx = false; if (q < v) mn = false; }
    if (mx || mn) out.push([i, j, v, mx]);
  }
  ctx.textAlign = "center"; ctx.textBaseline = "middle";
  for (const [i, j, v, hi] of out) { const p = gridInv(V, st, i, j, null); if (!p || p[0] < 8 || p[1] < 8 || p[0] > st.W - 8 || p[1] > st.H - 8) continue;
    const X = st.x0 + p[0], Y = st.y0 + p[1];
    haloText(ctx, hi ? "H" : "L", X, Y - pt(5), `900 ${pt(19)}px Montserrat`, hi ? "#1f4fd1" : "#d1261f", pt(3.2), "center", "middle");
    haloText(ctx, String(Math.round(v)), X, Y + pt(9), `800 ${pt(9)}px Montserrat`, hi ? "#1f4fd1" : "#d1261f", pt(2.6), "center", "middle"); }
}
function drawEns(ctx, st, D, P, V) {
  const E = D.ens; if (!E) return;
  if (P.spag) {
    for (const [L, col] of [["5520", "#2b6cd6"], ["5760", "#d63a2b"]]) {
      ctx.strokeStyle = col; ctx.globalAlpha = 0.7; ctx.lineWidth = pt(0.9); ctx.lineJoin = "round"; ctx.beginPath();
      for (const ln of E.spag[L] || []) { let g = null, on = false;
        for (let k = 1; k + 1 < ln.length; k += 2) { const p = gridInv(V, st, ln[k] / 10, ln[k + 1] / 10, g);
          if (!p) { on = false; g = null; continue; } g = p; const X = st.x0 + p[0], Y = st.y0 + p[1]; on ? ctx.lineTo(X, Y) : ctx.moveTo(X, Y); on = true; } }
      ctx.stroke(); ctx.globalAlpha = 1;
    }
    const z = D.raw.z500 && D.raw.z500.v; if (z) { const n = st.W * st.H, vals = new Float32Array(n), zb = blur(z, D.w, D.h, 1.0); for (let k = 0; k < n; k++) vals[k] = sample(st, zb, k);
      for (const L of [5520, 5760]) { const lines = contour(st, vals, L, 3); strokeLines(ctx, lines, "#ffffff", pt(3.4), null); strokeLines(ctx, lines, "#101114", pt(1.8), null); } }
  }
  if (P.lows) {
    const col = mb => mb <= 970 ? "#4b0f6b" : mb <= 980 ? "#b3123c" : mb <= 990 ? "#e8692f" : mb <= 1000 ? "#f2c12e" : "#8a919c";
    for (const [mem, fi, fj, mb] of E.lows) { const p = gridInv(V, st, fi, fj, null); if (!p || p[0] < 0 || p[1] < 0 || p[0] > st.W || p[1] > st.H) continue;
      ctx.beginPath(); ctx.arc(st.x0 + p[0], st.y0 + p[1], pt(3.2), 0, 2 * Math.PI); ctx.fillStyle = col(mb); ctx.fill(); ctx.lineWidth = pt(0.8); ctx.strokeStyle = "#ffffff"; ctx.stroke(); }
  }
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
    const one = async () => { while (k < st.length) { const i = k++; const f = String(st[i].f).padStart(3, "0");
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
    <button type="button" id="mgx">Close</button></div><div id="mgbody"><div class="mg-msg">Loading\u2026</div></div>`;
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
  const T = mgTown(D, MG.town); body.innerHTML = `<canvas id="mgc"></canvas>`; mgChart($("mgc"), T, body);
}
function mgChart(cv, T, box) {
  const dpr = Math.min(2, devicePixelRatio || 1), W = box.clientWidth, H = Math.max(420, box.clientHeight - 4);
  cv.width = W * dpr; cv.height = H * dpr; cv.style.width = W + "px"; cv.style.height = H + "px";
  const c = cv.getContext("2d"); c.scale(dpr, dpr); c.fillStyle = "#15171c"; c.fillRect(0, 0, W, H);
  const [m] = MG.run.split("/"), site = S.man.models[m].site, small = W < 600;
  const L = small ? 38 : 52, Rm = small ? 34 : 50, top = small ? 46 : 52, bot = 34, n = T.f.length;
  const panels = [["temp", 3], ["wind", 2], ["pcp", 2], ["cloud", 1]].filter(([k]) => k === "temp" ? T.t2m : k === "wind" ? (T.wind || T.gust) : k === "pcp" ? (T.pcp || T.snow || T.snow6 || T.pcp6) : T.tcc);
  const wsum = panels.reduce((a, p) => a + p[1], 0), gap = 18, ph = (H - top - bot - gap * (panels.length - 1)) / wsum;
  const t0 = Date.parse(T.t[0]), t1 = Date.parse(T.t[n - 1]), X = iso => L + (Date.parse(iso) - t0) / Math.max(1, t1 - t0) * (W - L - Rm);
  c.font = `800 ${small ? 14 : 17}px Montserrat`; c.fillStyle = "#f4f2ee"; c.textBaseline = "top";
  c.fillText(`${MG.town}${T.P.k === "pass" ? " (pass)" : ""} \u2013 ${site} ${MG.run.split("/")[1].slice(8)}Z`, L, 8);
  c.font = `500 ${small ? 10 : 12}px Montserrat`; c.fillStyle = "#a7abb3";
  c.fillText(`Times are Pacific. ${T.P.c !== undefined ? "Temperature corrected to pass summit height. " : ""}${T.snowEst ? "Snow estimated 10:1 where 2 m temp \u2264 33\u00b0F." : ""}`, L, small ? 26 : 30);
  let y = top;
  const days = []; for (let k = 0; k < n; k++) { const d = fmtPT(T.t[k], { weekday: "short", month: "numeric", day: "numeric" }); if (!days.length || days[days.length - 1].d !== d) days.push({ d, k }); }
  for (const [kind, wt] of panels) {
    const h = wt * ph, y0 = y, y1 = y + h; y += h + gap;
    c.fillStyle = "#1d2027"; c.fillRect(L, y0, W - L - Rm, h);
    c.strokeStyle = "#2c3039"; c.lineWidth = 1; for (const dd of days) { const x = X(T.t[dd.k]); c.beginPath(); c.moveTo(x, y0); c.lineTo(x, y1); c.stroke(); }
    const scale = (lo, hi) => v => y1 - (v - lo) / (hi - lo || 1) * h;
    const axis = (lo, hi, sc, unit, right, color) => { c.font = `500 ${small ? 9 : 11}px Montserrat`; c.fillStyle = color || "#a7abb3"; c.textBaseline = "middle"; c.textAlign = right ? "left" : "right";
      const stp = niceStep((hi - lo) / 4); for (let v = Math.ceil(lo / stp) * stp; v <= hi + 1e-9; v += stp) { const yy = sc(v); if (!right) { c.strokeStyle = "#2c3039"; c.beginPath(); c.moveTo(L, yy); c.lineTo(W - Rm, yy); c.stroke(); }
        c.fillText(+v.toFixed(2) + unit, right ? W - Rm + 4 : L - 4, yy); } c.textAlign = "left"; };
    const line = (a, sc, color, lw, dash) => { c.strokeStyle = color; c.lineWidth = lw; c.setLineDash(dash || []); c.beginPath(); let on = false;
      a.forEach((v, k) => { if (v == null) { on = false; return; } const xx = X(T.t[k]), yy = sc(v); on ? c.lineTo(xx, yy) : c.moveTo(xx, yy); on = true; }); c.stroke(); c.setLineDash([]); };
    const label = (s, color, dx) => { c.font = `700 ${small ? 10 : 12}px Montserrat`; c.fillStyle = color; c.textBaseline = "top"; c.fillText(s, L + 6 + (dx || 0), y0 + 4); return c.measureText(s).width + 14; };
    const bars = (a, sc, color, wfrac) => { c.fillStyle = color; const bw = Math.max(1.5, (W - L - Rm) / n * (wfrac || 0.7)); a.forEach((v, k) => { if (v == null || v <= 0) return; const xx = X(T.t[k]); c.fillRect(xx - bw / 2, sc(v), bw, y1 - sc(v)); }); };
    if (kind === "temp") {
      const a = T.t2m.filter(v => v != null), sd = T.t2sd;
      let lo = Math.min(...a, 32), hi = Math.max(...a, 32); if (sd) { lo = Math.min(lo, ...T.t2m.map((v, k) => v - (sd[k] || 0))); hi = Math.max(hi, ...T.t2m.map((v, k) => v + (sd[k] || 0))); }
      lo = Math.floor(lo / 5) * 5 - 2; hi = Math.ceil(hi / 5) * 5 + 2; const sc = scale(lo, hi); axis(lo, hi, sc, "\u00b0");
      if (sd) { c.fillStyle = "#e0484d33"; c.beginPath(); T.t2m.forEach((v, k) => { const xx = X(T.t[k]); k ? c.lineTo(xx, sc(v + sd[k])) : c.moveTo(xx, sc(v + sd[k])); });
        for (let k = n - 1; k >= 0; k--) c.lineTo(X(T.t[k]), sc(T.t2m[k] - sd[k])); c.fill(); }
      line(T.t2m.map(() => 32), sc, "#5aa9ff", 1.5, [6, 4]); line(T.t2m, sc, "#ff5a5f", 2.5);
      let dx = label(sd ? "Temperature \u00b0F (ens. mean, shading = \u00b11 spread)" : "Temperature \u00b0F", "#ff8a8e"); label("32\u00b0F", "#5aa9ff", dx);
      if (T.p32) { const s2 = scale(0, 100); line(T.p32, s2, "#7fd1ff", 1.5, [2, 3]); axis(0, 100, s2, "%", true, "#7fd1ff"); label("chance \u2264 32\u00b0F", "#7fd1ff", dx + 60); }
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
      const anySnow = (sn || sn6 || []).some(v => v > 0.05), hiS = Math.max(1, ...(sn || sn6 || []).filter(v => v != null)), topS = niceStep(hiS) * Math.ceil(hiS / niceStep(hiS)), scS = scale(0, topS);
      const pTop = niceStep(hiP) * Math.ceil(hiP / niceStep(hiP)); axis(0, pTop, scP, "\u2033", false, "#6fd38a");
      if (p6 && T.pcp) bars(p6.map((v, k) => T.f[k] % 6 === 0 && T.f[k] > 36 ? v : null), scP, "#3ea95888", 2.2);
      if (pc) bars(pc, scP, "#3ea958"); else if (p6) bars(p6.map((v, k) => T.f[k] % 6 === 0 ? v : null), scP, "#3ea958", 2.2);
      if (anySnow) { axis(0, topS, scS, "\u2033", true, "#d9ecff"); if (sn) line(sn.reduce((acc, v, k) => (acc.push((acc[k - 1] || 0) + (v || 0)), acc), []), scS, "#d9ecff", 2);
        else { let s = 0; line(sn6.map((v, k) => T.f[k] % 6 === 0 ? (s += v || 0) : null), scS, "#d9ecff", 2); } }
      const tot = pc ? pc.reduce((a, v) => a + (v || 0), 0) : sum6(T, p6, -1, 1e9) || 0;
      let dx = label(`Precip per ${pc ? (T.f[1] - T.f[0] || 1) + " h" : "6 h"} (total ${tot.toFixed(2)}\u2033)`, "#6fd38a");
      if (anySnow) { const ts = (sn || []).reduce((a, v) => a + (v || 0), 0) || sum6(T, sn6, -1, 1e9) || 0; label(`Snow running total ${ts.toFixed(1)}\u2033${T.snowEst ? " (est.)" : ""}`, "#d9ecff", dx); }
    } else {
      const sc = scale(0, 100); c.fillStyle = "#9aa3b2"; c.beginPath(); c.moveTo(X(T.t[0]), y1); T.tcc.forEach((v, k) => c.lineTo(X(T.t[k]), sc(v || 0))); c.lineTo(X(T.t[n - 1]), y1); c.closePath(); c.globalAlpha = 0.55; c.fill(); c.globalAlpha = 1;
      axis(0, 100, sc, "%"); label("Cloud cover", "#cfd3da");
    }
  }
  // time axis (Pacific)
  c.font = `600 ${small ? 9 : 11}px Montserrat`; c.fillStyle = "#cfd3da"; c.textBaseline = "top"; c.textAlign = "center";
  const yb = H - bot + 4; for (let k = 0; k < days.length; k++) { const xa = X(T.t[days[k].k]), xb = k + 1 < days.length ? X(T.t[days[k + 1].k]) : W - Rm; if (xb - xa > (small ? 34 : 50)) c.fillText(days[k].d, (xa + xb) / 2, yb + 13); }
  const hrs = n > 60 ? [0, 12] : n > 24 ? [0, 6, 12, 18] : null;
  let lastX = -1e9; T.t.forEach((t, k) => { if (X(t) - lastX < (small ? 30 : 40)) return; const hh = +fmtPT(t, { hour: "numeric", hourCycle: "h23" }); if (hrs ? hrs.includes(hh) && (k === 0 || +fmtPT(T.t[k - 1], { hour: "numeric", hourCycle: "h23" }) !== hh) : k % Math.max(1, Math.ceil(n / 12)) === 0)
    { c.fillText(fmtPT(t, { hour: "numeric" }).replace(" ", "").toLowerCase(), X(t), yb); lastX = X(t); } });
  c.textAlign = "left";
}
function niceStep(x) { const p = Math.pow(10, Math.floor(Math.log10(x || 1))), r = x / p; return (r <= 1 ? 1 : r <= 2 ? 2 : r <= 2.5 ? 2.5 : r <= 5 ? 5 : 10) * p; }
function passTable(body, D) {
  const passes = D.points.filter(p => p.k === "pass"); if (!passes.length) { body.innerHTML = `<div class="mg-msg">No passes in this model's views.</div>`; return; }
  const T0 = mgTown(D, passes[0].n), fmax = T0.f[T0.f.length - 1], wins = [[0, 24], [24, 48], [48, 72]].filter(w => fmax > w[0]).map(([a, b]) => [a, Math.min(b, fmax)]);
  const f1 = x => x == null ? "\u2013" : x.toFixed(1), f2 = x => x == null ? "\u2013" : x.toFixed(2), r0 = x => x == null ? "\u2013" : Math.round(x);
  const hdr = wins.map(([a, b]) => `${fmtPT(new Date(Date.parse(T0.t[0]) + (a - T0.f[0]) * 36e5).toISOString(), { weekday: "short", hour: "numeric" })}\u2013${fmtPT(new Date(Date.parse(T0.t[0]) + (b - T0.f[0]) * 36e5).toISOString(), { weekday: "short", hour: "numeric" })}`);
  const span = Math.min(fmax, 48);
  let h = `<div class="mg-note">Run start ${fmtPT(new Date(Date.parse(T0.t[0]) - T0.f[0] * 36e5).toISOString(), { weekday: "short", month: "numeric", day: "numeric", hour: "numeric" })} PT. Temperatures corrected to summit height. ${T0.snowEst ? "Snow estimated 10:1 where 2 m temp \u2264 33\u00b0F. " : ""}Tap a pass for its meteogram.</div>
  <div class="mg-scroll"><table class="pf"><thead><tr><th>Pass</th>${wins.map((w, k) => `<th>Snow \u2033<br><small>${hdr[k]}</small></th>`).join("")}${T0.kuch ? wins.map((w, k) => `<th>Kuchera \u2033<br><small>${hdr[k]}</small></th>`).join("") : ""}<th>Precip \u2033<br><small>first ${span} h</small></th><th>Low \u00b0F<br><small>first ${span} h</small></th><th>High \u00b0F<br><small>first ${span} h</small></th><th>Max gust<br><small>mph, ${span} h</small></th>${T0.frz ? `<th>Freezing lvl<br><small>lowest ft</small></th>` : ""}</tr></thead><tbody>`;
  for (const p of passes) { const T = mgTown(D, p.n), sn = wins.map(([a, b]) => snowWin(T, a, b));
    const col = x => x == null ? "" : x >= 12 ? ' class="s3"' : x >= 6 ? ' class="s2"' : x >= 1 ? ' class="s1"' : "";
    h += `<tr data-n="${p.n}"><td>${p.n}</td>${sn.map(x => `<td${col(x)}>${f1(x)}</td>`).join("")}${T0.kuch ? wins.map(([a, b]) => { const x = sumWin(T, T.kuch, a, b); return `<td${col(x)}>${f1(x)}</td>`; }).join("") : ""}<td>${f2(pcpWin(T, -1, span))}</td><td>${r0(ext(T, T.t2m, -1, span, Math.min))}</td><td>${r0(ext(T, T.t2m, -1, span, Math.max))}</td><td>${r0(ext(T, T.gust, -1, span, Math.max))}</td>${T0.frz ? `<td>${r0(ext(T, T.frz, -1, span, Math.min))}</td>` : ""}</tr>`; }
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
