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
const KINDS = [["low", "Lows"], ["high", "Highs"]];
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
const PRODUCTS = {
  low: { title: d => `${d.day} Predicted Low Temps`, sub: d => `Coldest Temps 4 AM to 8 AM ${d.day} ${d.md}`, pal: TEMP, extreme: ["Coldest", true] },
  high: { title: d => `${d.day} Predicted High Temps`, sub: d => `Afternoon highs ${d.day} ${d.md}`, pal: TEMP, extreme: ["Warmest", false] },
};
// ---------------------------------------------------------------- data (same R2 layout / decoding as viewer.js)
async function loadRun(c) { if (!WA.runs[c]) WA.runs[c] = await (await fetch(`${DATA}runs/nbm/${c}/run.json`, { cache: "no-cache" })).json(); return WA.runs[c]; }
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
  const I = await getPixels(url), [lo, hi] = st.ranges[name], sc = (hi - lo) / 255, n = I.w * I.h, o = new Float32Array(n);
  for (let k = 0; k < n; k++) o[k] = lo + I.px[k * 4 + ch] * sc;   // row 0 = southern grid row
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
async function viewKit(view) {
  if (WA.kits[view]) return WA.kits[view];
  return (WA.kits[view] = (async () => {
    const [lut, mask] = await Promise.all([fetch(KIT + view + "/lut.bin").then(r => { if (!r.ok) throw new Error("lut " + r.status); return r.arrayBuffer(); }).then(b => new Float32Array(b)),
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
    for (const q of [k - 1, k + 1, k - W, k + W]) { if (q < 0 || q >= n || B[q] < 0) continue; if ((V[q] >= T) !== hi) white = true; else if (B[q] !== bi) f = 0.55; }
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
function summaryLine1(K, vals) {
  const rng = ks => ks.filter(k => k in vals).map(k => vals[k]), f_ = g => Math.min(...g) === Math.max(...g) ? `${g[0]}` : `${Math.min(...g)} to ${Math.max(...g)}`;
  if (!K.region) { const lw = rng(["Seattle", "Tacoma", "Olympia", "Vancouver", "Bellingham", "Aberdeen"]),
    ea = rng(["Spokane", "Yakima", "Wenatchee", "Ellensburg", "Moses Lake", "Kennewick", "Walla Walla", "Pullman", "Omak", "Colville", "Goldendale"]);
    return `West side ${Math.min(...lw)} to ${Math.max(...lw)}, east side ${Math.min(...ea)} to ${Math.max(...ea)}`; }
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
// ---------------------------------------------------------------- page
const S = { c: null, kind: Q.get("kind") === "high" ? "high" : "low", view: VIEWS.some(v => v[0] === Q.get("view")) ? Q.get("view") : "full", day: Q.get("day"), busy: 0 };
const fillSel = (sel, opts, cur) => { sel.innerHTML = opts.map(([v, t]) => `<option value="${v}"${v === cur ? " selected" : ""}>${t}</option>`).join(""); };
function setDays() {
  const ds = daysFor(WA.runs[S.c], S.kind); S.days = ds;
  if (!ds.some(d => d.key === S.day)) S.day = ds.length ? ds[0].key : null;
  fillSel($("day"), ds.map(d => [d.key, `${d.day.slice(0, 3)} ${d.md}`]), S.day);
}
async function draw() {
  const my = ++S.busy, d = S.days.find(x => x.key === S.day); if (!d) { $("msg").textContent = "No data for this day in this run."; return; }
  $("msg").textContent = "Drawing…"; const t0 = performance.now();
  const cv = document.createElement("canvas");
  try { const info = await render(cv, S.c, S.kind, S.view, d); if (my !== S.busy) return;
    const old = $("map"); cv.id = "map"; old.replaceWith(cv); S.info = info; fit();
    const R_ = WA.runs[S.c]; $("msg").textContent = `${R_.runline} · ${S.kind === "low" ? "min of " + info.steps.length + " t2m steps" : "NBM 12 h max"} · ${Math.round(performance.now() - t0)} ms`;
    const u = new URL(location); u.searchParams.set("kind", S.kind); u.searchParams.set("view", S.view); u.searchParams.set("day", S.day); u.searchParams.set("run", S.c);
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
  const cv = $("map"), d = S.days.find(x => x.key === S.day), v = VIEWS.find(x => x[0] === S.view)[1].replace(/ /g, "-");
  const name = `${v}_${S.kind === "low" ? "Lows" : "Highs"}_${d.day}-${d.md}_NBM_${S.c.slice(8)}Z.jpg`;
  cv.toBlob(async b => {
    const f = new File([b], name, { type: "image/jpeg" });
    if (matchMedia("(max-width: 700px)").matches && navigator.canShare && navigator.canShare({ files: [f] })) { try { await navigator.share({ files: [f] }); return; } catch (e) { if (e.name === "AbortError") return; } }
    const a = document.createElement("a"); a.href = URL.createObjectURL(b); a.download = name; document.body.appendChild(a); a.click(); a.remove(); setTimeout(() => URL.revokeObjectURL(a.href), 60e3);
  }, "image/jpeg", 0.95);
}
async function boot() {
  const [man] = await Promise.all([fetch(DATA + "manifest.json", { cache: "no-cache" }).then(r => r.json()), document.fonts.load("800 40px Montserrat")]);
  WA.man = man; const runs = [...(man.runs.nbm || [])].reverse(); if (!runs.length) { $("msg").textContent = "No NBM run available."; return; }
  S.c = runs.includes(Q.get("run")) ? Q.get("run") : runs[0];
  fillSel($("run"), runs.map(c => [c, `NBM ${c.slice(8)}Z ${c.slice(4, 6)}-${c.slice(6, 8)}`]), S.c);
  fillSel($("kind"), KINDS, S.kind); fillSel($("view"), VIEWS, S.view);
  await loadRun(S.c); setDays();
  $("run").onchange = async e => { S.c = e.target.value; await loadRun(S.c); setDays(); draw(); };
  $("kind").onchange = e => { S.kind = e.target.value; setDays(); draw(); };
  $("day").onchange = e => { S.day = e.target.value; draw(); };
  $("view").onchange = e => { S.view = e.target.value; draw(); };
  $("save").onclick = save;
  const mq = matchMedia("(max-width: 700px)"), ph = () => { document.body.classList.toggle("phone", mq.matches); fit(); };
  ph(); (mq.addEventListener ? mq.addEventListener("change", ph) : mq.addListener(ph)); addEventListener("resize", fit);
  await draw(); window.__ready = true;
}
boot().catch(e => { console.error(e); $("msg").textContent = "Could not load: " + e.message; });
