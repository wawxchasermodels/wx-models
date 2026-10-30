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

async function boot() {
  if (Q.get("bare")) document.body.classList.add("bare");
  // 10-29: manifest, fonts and the shown run's run.json in parallel; other runs load when picked
  const [man] = await Promise.all([fetch(DATA + "manifest.json", { cache: "no-cache" }).then(r => r.json()),
                                   document.fonts.load("800 20px Montserrat"), document.fonts.load("500 12px Montserrat")]);
  S.man = man;
  // runs: "model/cycle", newest first per model; models in a fixed order
  const order = ["hrrr", "gfs", "ifs", "aifs"].filter(m => S.man.models[m] && (S.man.runs[m] || []).length);
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
  setupPointer(); $("share") && ($("share").onclick = share); $("save") && ($("save").onclick = saveImage);
  $("prod").onchange = e => { S.prod = e.target.value; draw(); };
  $("view").onchange = e => { S.view = e.target.value; draw(); };
  const sl = $("step"), endDrag = () => { if (S.dragging) { S.dragging = false; draw(); } };
  sl.addEventListener("pointerdown", () => { S.dragging = true; });
  sl.addEventListener("touchstart", () => { S.dragging = true; }, { passive: true });
  for (const ev of ["pointerup", "pointercancel", "touchend", "touchcancel", "change"]) sl.addEventListener(ev, endDrag);
  sl.oninput = e => { const v = +e.target.value; if (v === S.i) return; S.i = v; draw(); };
  $("prev").onclick = () => go(-1); $("next").onclick = () => go(1);
  $("play").onclick = () => { if (S.timer) { clearInterval(S.timer); S.timer = null; $("play").textContent = "Play"; }
                              else { S.timer = setInterval(() => go(1, true), 250); $("play").textContent = "Stop"; } };
  addEventListener("keydown", e => { if (e.key === "ArrowRight") go(1); if (e.key === "ArrowLeft") go(-1); });
  await draw();
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
    for (let k = 0; k < n; k++) out[k] = lo + px[k * 4 + ch] * sc;
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
    if (pid === "aifswind") {
      const u = F.u10.v, v = F.v10.v, sp = new Float32Array(u.length);
      for (let k = 0; k < u.length; k++) sp[k] = Math.hypot(u[k], v[k]) * (2.23694 / 1.94384);   // kt -> mph
      out.fill = blur(sp, g.w, g.h, P.spd_sigma); out.iso = blur(F.mslp.v, g.w, g.h, P.isobars.sigma);
    } else if (P.fill === "snowlvl") { const a = F.frz.v, o = new Float32Array(a.length); for (let k = 0; k < a.length; k++) o[k] = Math.max(0, a[k] - 1000); out.fill = o; }
    else out.fill = F[P.fill] ? F[P.fill].v : g.v;
    return out;
  })();
  S.derived.set(key, p); return p;
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
    const V = VIEWS()[vid], cv = $("map"), st2 = await viewStatic(vid); if (cv.width !== V.fig[0]) { cv.width = V.fig[0]; cv.height = V.fig[1]; }
    const ctx = cv.getContext("2d"); ctx.fillStyle = S.man.style.BG; ctx.fillRect(0, 0, cv.width, cv.height); ctx.drawImage(st2.base, 0, 0, cv.width, cv.height);
    header(ctx, V, PRODS()[pid].title, step.valid_line, `${S.runs[run].runline}  \u00b7  ${V.label}  \u00b7  not in this model run at this hour`, step.badge);
    S.cur = null; window.__drawn = `${pid}/${vid}/${f}`; return;
  }
  if (seq !== drawSeq) return;
  const t1 = performance.now();
  const V = VIEWS()[vid], P = PRODS()[pid], cv = $("map");
  if (cv.width !== V.fig[0] || cv.height !== V.fig[1]) { cv.width = V.fig[0]; cv.height = V.fig[1]; }
  const ctx = cv.getContext("2d"); ctx.fillStyle = S.man.style.BG; ctx.fillRect(0, 0, cv.width, cv.height);
  // 1. color fill: value -> bin color, exactly the site's bins (contourf + BoundaryNorm)
  const pal = palette(pid), mins = P.min_show, im = ctx.createImageData(st.W, st.H), o = im.data, F = D.fill, n = st.W * st.H;
  const vals = new Float32Array(n);
  if (lite) {   // half resolution: one sample per 2x2 block
    const W = st.W, H = st.H;
    for (let y = 0; y < H; y += 2) for (let x = 0; x < W; x += 2) {
      const k = y * W + x, v = sample(st, F, k); let c = null;
      if (!(v !== v || (mins !== undefined && v < mins))) c = v < pal.L0 ? pal.under : v >= pal.Lend ? pal.over : pal.cols[bin(pal, v)];
      for (let dy = 0; dy < 2 && y + dy < H; dy++) for (let dx = 0; dx < 2 && x + dx < W; dx++) {
        const kk = k + dy * W + dx; vals[kk] = v; if (!c) continue; const q = kk * 4; o[q] = c[0]; o[q + 1] = c[1]; o[q + 2] = c[2]; o[q + 3] = 255; }
    }
  } else for (let k = 0; k < n; k++) {
    const v = sample(st, F, k); vals[k] = v; if (v !== v || (mins !== undefined && v < mins)) continue;
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
  if (P.fmt === "in1") return v < 0.05 ? "0" : v < 10 ? v.toFixed(1) : v.toFixed(0);
  if (P.fmt === "ft100") return String(Math.round(v / 100) * 100);
  if (P.fmt === "vis") return v >= 7 ? "7+" : v < 3 ? v.toFixed(1) : v.toFixed(0);
  return String(Math.round(v));
}
const UNITS = { mucape: " J/kg", sbcape: " J/kg", ltng: " /km\u00b2/5 min", ltgp: " in", t2m: "\u00b0F", gust10: " mph", aifswind: " mph", t850: "\u00b0C", t700: "\u00b0C", tcc: "%", vis: " mi", ir: "\u00b0C",
                refc: " dBZ", qpf: " in", snow: " in", frz: " ft", snowlvl: " ft" };
// value under the cursor / tap (item 1) and swipe to step (item 6)
function readout(ev) {
  const C = S.cur, tip = $("tip"); if (!C || !tip) return;
  const cv = $("map"), r = cv.getBoundingClientRect(), X = (ev.clientX - r.left) * cv.width / r.width, Y = (ev.clientY - r.top) * cv.height / r.height;
  const x = Math.round(X - C.st.x0), y = Math.round(Y - C.st.y0);
  if (x < 0 || y < 0 || x >= C.st.W || y >= C.st.H) { tip.hidden = true; return; }
  const k = y * C.st.W + x; let v = C.vals[k]; if (!isFinite(v)) { tip.hidden = true; return; }
  let s = (C.P.fmt ? fmtVal(C.P, v) : C.P.dec ? v.toFixed(C.P.dec) : String(Math.round(v))) + (UNITS[C.pid] || "");
  if (C.pid === "aifswind") { const m = sample(C.st, C.D.iso, k); if (isFinite(m)) s += ` \u00b7 ${m.toFixed(1)} mb`; }
  tip.textContent = s; tip.hidden = false;
  const wr = $("wrap").getBoundingClientRect(); tip.style.left = (ev.clientX - wr.left + 14) + "px"; tip.style.top = (ev.clientY - wr.top - 30) + "px";
}
function setupPointer() {
  const cv = $("map"); let down = null;
  cv.addEventListener("pointermove", e => { if (e.pointerType === "mouse") readout(e); });
  cv.addEventListener("pointerleave", () => { if ($("tip")) $("tip").hidden = true; });
  cv.addEventListener("pointerdown", e => { down = { x: e.clientX, y: e.clientY, t: performance.now() }; });
  cv.addEventListener("pointerup", e => {
    if (!down) return; const dx = e.clientX - down.x, dy = e.clientY - down.y; down = null;
    if (Math.abs(dx) > 40 && Math.abs(dx) > 1.5 * Math.abs(dy)) go(dx < 0 ? 1 : -1); else readout(e);
  });
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
  const u = D.raw.u10.v, v = D.raw.v10.v;
  ctx.strokeStyle = B.color; ctx.fillStyle = B.color; ctx.lineWidth = pt(B.lw); ctx.lineJoin = "miter";
  const L = V, lutA = st.lut;
  for (let j = 0; j < ny; j++) for (let i = 0; i < nx; i++) {
    const x = (st.W - 1) * i / (nx - 1), y = (st.H - 1) * (1 - j / (ny - 1)), k = Math.round(y) * st.W + Math.round(x);
    const uu = sample(st, u, k), vv = sample(st, v, k); if (!isFinite(uu)) continue;
    const li = Math.min(L.nx - 1, Math.round(x / L.stride)), lj = Math.min(L.ny - 1, Math.round(y / L.stride)), a = lutA[(lj * L.nx + li) * 3 + 2];
    const nX = Math.cos(a), nY = -Math.sin(a);           // north, y up
    const eX = nY, eY = -nX;                              // east = north turned clockwise
    const wx = uu * eX + vv * nX, wy = uu * eY + vv * nY, sp = Math.hypot(uu, vv);
    barb(ctx, st.x0 + x, st.y0 + y, wx, wy, sp, Lp);
  }
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
