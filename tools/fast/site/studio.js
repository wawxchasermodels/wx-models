// Studio tab (10-31, Benjamin 10:35 AM: "Vertical model viewing canvas, next to a 1920x1080 model viewing canvas ... drag the map
// ever so slightly to make it line up right ... for reels and making videos on obs"). viewer.js draws the normal map off-screen at
// 2-3x (?studio=1); after every full draw this crops the map panel into two fixed frames (9:16 1080x1920, 16:9 1920x1080) and
// draws its own header (title, valid time, run, model tag, F+ badge) and color bar at full output size.
// Clean mode for OBS Browser Source: studio.html?clean=1&out=v|h&model=<m>&prod=&view=&f=&dx=&dy=&zoom=&bg=&play=1&dwell=&step=&loop=
"use strict";
(() => {
const SQ = new URLSearchParams(location.search), CLEAN = SQ.get("clean") === "1", OUTQ = SQ.get("out") || "v";
const F = {
  v: { cv: document.getElementById("cv"), zoom: document.getElementById("zv"), W: 1080, H: 1920, top: 250, bot: 330, title: 64, valid: 40, day: 51, run: 26, pad: 64 },
  h: { cv: document.getElementById("ch"), zoom: document.getElementById("zh"), W: 1920, H: 1080, top: 150, bot: 150, title: 58, valid: 36, day: 46, run: 24, pad: 56 },
};
const BG = SQ.get("bg") || "#111316";
if (CLEAN) {
  document.body.classList.add("clean"); document.getElementById(OUTQ === "h" ? "fh" : "fv").classList.add("on");
  document.body.style.setProperty("--sbg", BG === "transparent" ? "transparent" : BG); if (BG === "transparent") document.documentElement.style.background = "transparent";
}
// framing per frame x view: {dx, dy, zoom} in output px; URL params win in clean mode
// 11-02 (Benjamin t2095u): Meteogram mode. The meteograms page runs in a small iframe (its own Model / Town / Product pickers);
// its finished chart image is drawn into both frames with the same drag / zoom / keys as the maps (framing saved under "mg").
// 11-03 (Benjamin t2192u "the Observations map viewable in Studio mode"): MG.kind "obs" = the live obs module's canvas as the image source
// 11-04 (t2292u): MG.kind "pass" = the Pass Forecaster table, drawn straight into each frame with its own 16:9 / 9:16 layout (PF below)
// 11-04 (Benjamin t2319u: refresh on a model map reopened the SeaTac gust meteogram): the Studio mode lives per tab (sessionStorage,
// kept across a refresh); localStorage is shared by every Studio tab / window (OBS setups), so another tab's Meteogram mode won the refresh.
// localStorage is only the fallback for a brand-new tab.
// 11-04 (t2337u "refreshed ... and it loaded into a SNOW METEOGRAM"): the mode is per tab only: the address (?smode=, survives any
// refresh / restore, OBS included) and this tab's sessionStorage. The shared localStorage value is no longer read, so a Studio opened or
// re-opened without them starts on Map, never on another window's Meteogram / Observations / Pass Forecaster.
const MODES_OK = ["map", "mg", "obs", "pass"];
const MODE0 = MODES_OK.includes(SQ.get("smode")) ? SQ.get("smode") : "map";   // the address only: a bare studio.html always opens on Map
const saveMode = (m) => { try { sessionStorage.setItem("studio:mode", m); } catch (e) { /* private mode */ }
  if (CLEAN) return; try { const u = new URL(location); if (m === "map") u.searchParams.delete("smode"); else u.searchParams.set("smode", m); history.replaceState(null, "", u); } catch (e) { /* replaceState limit */ } };
const MG = { on: !CLEAN && ["mg", "obs", "pass"].includes(MODE0), kind: ["obs", "pass"].includes(MODE0) ? MODE0 : "mg", img: null, src: "" };
const PASSM = () => MG.on && MG.kind === "pass";
const PF = { run: "", rows: null, msg: "" };
const OBSM = () => MG.on && MG.kind === "obs";
const IW = (im) => im.naturalWidth || im.width, IH = (im) => im.naturalHeight || im.height;
const key = (k) => `studio:${k}:${MG.on ? MG.kind : S.view}`;
const getFr = (k) => {
  if (CLEAN && k === OUTQ && (SQ.has("dx") || SQ.has("dy") || SQ.has("zoom"))) return { dx: +SQ.get("dx") || 0, dy: +SQ.get("dy") || 0, zoom: +SQ.get("zoom") || 1 };
  try { return Object.assign({ dx: 0, dy: 0, zoom: 1 }, JSON.parse(localStorage.getItem(key(k)) || "{}")); } catch (e) { return { dx: 0, dy: 0, zoom: 1 }; }
};
const setFr = (k, fr) => { if (!CLEAN) localStorage.setItem(key(k), JSON.stringify(fr)); };
let last = null;   // {cv, cur, step}
const fmtTick = (v, P) => { if (P.levels && P.levels[0] === 0.01 && [12, 18].includes(P.levels[P.levels.length - 1])) return Math.abs(v - Math.round(v)) < 1e-6 ? String(Math.round(v)) : String(+(+v).toFixed(2));   // 11-03 t2254u: 18 in precip key, "4 6 8 10 12" not "4.0 6.0 ..." (crowded on 16:9)
   const a = P.ticks || []; const dec = a.some((t) => Math.abs(t - Math.round(t)) > 1e-6) ? (a.some((t) => Math.abs(t * 10 - Math.round(t * 10)) > 1e-6) ? 2 : 1) : 0; return Number(v).toFixed(dec); };

// 10-31 7:30 PM Studio wide Washington view (viewer.js addStudioViews): WT[model] = the normal Washington view's area, in the wide
// view's figure px (found by matching the two views' grid look-up tables, so it follows any model / projection); "pending" while loading
const WT = {};
function wideRect(m) {
  if (WT[m]) return WT[m] === "pending" ? null : WT[m];
  const V = S.man.models[m].views, Vw = V.wa, Vs = V.wawide; if (!Vw || !Vs) return null; WT[m] = "pending";
  const get = (u) => fetch(DATA + u + SV()).then((r) => { if (!r.ok) throw new Error(u); return r.arrayBuffer(); }).then((b) => new Float32Array(b));
  Promise.all([get(Vw.lut), get(Vs.lut)]).then(([lw, ls]) => {
    const pts = [], nxw = Vw.nx, nyw = Vw.ny;
    for (let t = 0; t <= 1.0001; t += 1 / 40) for (const [j, i] of [[0, t * (nxw - 1)], [nyw - 1, t * (nxw - 1)], [t * (nyw - 1), 0], [t * (nyw - 1), nxw - 1]]) {
      const q = (Math.round(j) * nxw + Math.round(i)) * 3; pts.push([lw[q], lw[q + 1]]); }
    let x0 = 1e9, y0 = 1e9, x1 = -1e9, y1 = -1e9; const n = Vs.nx * Vs.ny;
    for (const [a, b] of pts) { let best = 1e18, bk = 0; for (let q = 0; q < n; q++) { const d = (ls[q * 3] - a) ** 2 + (ls[q * 3 + 1] - b) ** 2; if (d < best) { best = d; bk = q; } }
      const x = (bk % Vs.nx + 0.5) * Vs.stride, y = ((bk / Vs.nx | 0) + 0.5) * Vs.stride; x0 = Math.min(x0, x); x1 = Math.max(x1, x); y0 = Math.min(y0, y); y1 = Math.max(y1, y); }
    WT[m] = { x: Vs.panel[0] + x0, y: Vs.panel[1] + y0, w: x1 - x0, h: y1 - y0 }; window.__studioWT = WT; renderAll();
  }).catch(() => { delete WT[m]; });
  return null;
}
// Washington's box inside the normal Washington view's area (temp_maps "wa" frame: state 242,275 1095x694 in panel 218.9,224.75 1162x778)
const WA_IN_WAVIEW = [0.0199, 0.0646, 0.942, 0.892];
function stateRect(V, m) {   // Washington's box in the wide view's figure px: the view's own "fit" (studio_views.py), else from WT
  if (V.fit) { const [x, y, w, h] = V.fit; return { x, y, w, h }; }
  const t = wideRect(m), q = WA_IN_WAVIEW; if (!t) return null;
  return { x: t.x + q[0] * t.w, y: t.y + q[1] * t.h, w: q[2] * t.w, h: q[3] * t.h };
}
function mgBase(k) {   // meteogram: whole chart fitted inside the frame (9:16: centred a little above the middle)
  if (OBSM()) { const f = F[k], iw = IW(MG.img), ih = IH(MG.img); return { cx: iw / 2, cy: ih / 2, k0: Math.max(f.W / iw, f.H / ih) }; }   // obs: the map covers the frame
  const f = F[k], im = MG.img, iw = im.naturalWidth, ih = im.naturalHeight, padX = f.pad * 0.5, top = k === "v" ? 200 : 60, bot = k === "v" ? 200 : 70;
  const k0 = Math.min((f.W - 2 * padX) / iw, (f.H - top - bot) / ih);
  return { cx: iw / 2, cy: ih / 2 - ((top + (f.H - bot)) / 2 - f.H / 2) / k0, k0 };
}
function base(k) {   // camera at dx = dy = 0, zoom 1: centre (figure px) and scale (output px per figure px)
  if (MG.on && MG.img) return mgBase(k);
  const f = F[k], V = last.cur.V, [px, py, pw, ph] = V.panel, t = V.studioWide ? stateRect(V, last.cur.run.split("/")[0]) : null;
  if (!t) return { cx: px + pw / 2, cy: py + ph / 2, k0: Math.max(f.W / pw, f.H / ph) };   // normal views: the map panel covers the frame
  // 11-04 Coast view (t2289u): its own camera box per frame shape (studio_views.py COAST_H / COAST_V) covers the frame: ocean in the left
  // two thirds, Washington's coast ~2/3 across
  if (V.studioCoast) { const r = k === "v" && V.fitV ? V.fitV : V.fit, [x, y, w, h] = r; return { cx: x + w / 2, cy: y + h / 2, k0: Math.max(f.W / w, f.H / h) }; }
  // wide view (10-31 7:55 PM, Benjamin: "a little tighter", whole state with a little margin): Washington fits a band between the
  // title and the color bar. 16:9: state from y 190 to H-120 and shifted right (its left edge at 27 % of the width) so the title,
  // top left, sits over the ocean / Vancouver Island instead of on Vancouver; 9:16: 84 % of the width, centred under the title.
  // (HRRR / RRFS / NBM, no own view: centred, since their grid's northwest corner would show top left)
  if (k === "h") { const y0 = 190, y1 = f.H - 120, k0 = Math.min((V.fit ? 0.66 : 0.86) * f.W / t.w, (y1 - y0) / t.h), xl = V.fit ? 0.27 * f.W : (f.W - t.w * k0) / 2;
    return { cx: t.x + t.w / 2 - (xl + t.w * k0 / 2 - f.W / 2) / k0, cy: t.y + t.h / 2 - ((y0 + y1) / 2 - f.H / 2) / k0, k0 }; }
  // 9:16: 84 % of the width, nudged 4 % right so the coast towns' names (Neah Bay, left of its dot) stay inside the frame
  const y0 = f.top + 80, y1 = f.H - f.bot + 40, k0 = Math.min(0.84 * f.W / t.w, (y1 - y0) / t.h);
  return { cx: t.x + t.w / 2 - 0.04 * f.W / k0, cy: t.y + t.h / 2 - ((y0 + y1) / 2 - f.H / 2) / k0, k0 };
}
// 11-04 (Benjamin t2264u "zoom the view out as much as I want, and move it around out over the ocean"): in Observations / satellite
// mode the frames crop the obs module's map bitmap, so zoom stopped at 1x and drags stopped at the bitmap's edge. Below 1x the obs map
// itself zooms out (about the frame's centre), and a drag past the edge pans the obs map; the frame zoom (1-2.5x) works as before.
const OZ = { ref: 0, sub: 1 };
function ozSync() { const S_ = Obs._state; if (!OZ.ref || Math.abs(S_.k - OZ.ref * OZ.sub) > 1e-6 * S_.k) { OZ.ref = S_.k; OZ.sub = 1; } return S_; }
function obsZoom(k, fr, z) {   // z = wanted total zoom (frame zoom x obs map zoom-out)
  if (typeof Obs === "undefined" || !MG.img) { fr.zoom = Math.max(1, z); return fr; }
  const S_ = ozSync(), r = crop(k, fr), X = S_.cx + (r.cx / S_.dpr - S_.w / 2) / S_.k, Y = S_.cy + (r.cy / S_.dpr - S_.h / 2) / S_.k;
  if (z < 1 || OZ.sub < 1) { OZ.sub = Math.min(1, Math.max(0.035 / OZ.ref, z)); S_.k = OZ.ref * OZ.sub; S_.cx = X; S_.cy = Y; S_.view = ""; fr.dx = fr.dy = 0; fr.zoom = Math.max(1, z); Obs.redraw(); }
  else fr.zoom = Math.min(2.5, z);
  return fr;
}
function obsPan(k, fr) {   // pan past the bitmap edge: move the obs map by the overflow, keep the frame offset at the edge
  const r = crop(k, fr); if (typeof Obs === "undefined" || !MG.img) { fr.dx = (r.bx - r.cx) * r.kk; fr.dy = (r.by - r.cy) * r.kk; return fr; }
  const S_ = ozSync(), ox = (r.bx - (fr.dx || 0) / r.kk) - r.cx, oy = (r.by - (fr.dy || 0) / r.kk) - r.cy;
  if (Math.abs(ox) > 0.01 || Math.abs(oy) > 0.01) { S_.cx += ox / S_.dpr / S_.k; S_.cy += oy / S_.dpr / S_.k; S_.view = ""; Obs.redraw(); }
  fr.dx = (r.bx - r.cx) * r.kk; fr.dy = (r.by - r.cy) * r.kk; return fr;
}
const obsZv = (fr) => Math.round((fr.zoom || 1) * (OBSM() && typeof Obs !== "undefined" && Obs._state ? (ozSync(), OZ.sub) : 1) * 100);
function crop(k, fr) {   // source rect (map bitmap px) for frame k: base camera, then zoom / pan; the panel stays covering the frame when it
  // can, and when it is smaller than the frame (wide view) it stays wholly in the frame (the rest is background)
  if (OBSM() && MG.img) {   // obs map: zoom in / pan, the map always covers the frame
    const B = base(k), kk = B.k0 * Math.max(1, fr.zoom || 1), iw = IW(MG.img), ih = IH(MG.img), cl = (v, a, b) => Math.min(b, Math.max(a, v)), hw = F[k].W / kk / 2, hh = F[k].H / kk / 2;
    const cx = cl(B.cx - (fr.dx || 0) / kk, hw, iw - hw), cy = cl(B.cy - (fr.dy || 0) / kk, hh, ih - hh);
    return { kk, cx, cy, bx: B.cx, by: B.cy, sx: 0, sy: 0, sw: F[k].W / kk, sh: F[k].H / kk, px: 0, py: 0, pw: iw, ph: ih, rs: 1 };
  }
  if (MG.on && MG.img) {   // meteogram: pan freely while some of the chart stays in the frame
    const B = base(k), kk = B.k0 * Math.max(1, fr.zoom || 1), im = MG.img, cl = (v, a, b) => Math.min(b, Math.max(a, v));
    const cx = cl(B.cx - (fr.dx || 0) / kk, -F[k].W / kk / 2 + 40 / kk, im.naturalWidth + F[k].W / kk / 2 - 40 / kk), cy = cl(B.cy - (fr.dy || 0) / kk, -F[k].H / kk / 2 + 40 / kk, im.naturalHeight + F[k].H / kk / 2 - 40 / kk);
    return { kk, cx, cy, bx: B.cx, by: B.cy, sx: 0, sy: 0, sw: F[k].W / kk, sh: F[k].H / kk, px: 0, py: 0, pw: im.naturalWidth, ph: im.naturalHeight, rs: 1 };
  }
  const f = F[k], { cv, cur } = last, rs = cv._rs || 1, [px, py, pw, ph] = cur.V.panel, B = base(k);
  const kk = B.k0 * Math.max(1, fr.zoom || 1), sw = f.W / kk, sh = f.H / kk;
  const cl = (v, a, b) => Math.min(Math.max(a, b), Math.max(Math.min(a, b), v));
  const cx = cl(B.cx - (fr.dx || 0) / kk, px + sw / 2, px + pw - sw / 2), cy = cl(B.cy - (fr.dy || 0) / kk, py + sh / 2, py + ph - sh / 2);
  return { sx: (cx - sw / 2) * rs, sy: (cy - sh / 2) * rs, sw: sw * rs, sh: sh * rs, kk, cx, cy, px, py, pw, ph, bx: B.cx, by: B.cy, rs };
}
function band(c, y0, y1, down) {
  const g = c.createLinearGradient(0, y0, 0, y1); const a = "rgba(13,15,19,0.90)", b = "rgba(13,15,19,0)";
  g.addColorStop(0, down ? a : b); g.addColorStop(1, down ? b : a); c.fillStyle = g; c.fillRect(0, y0, c.canvas.width, y1 - y0);
}
// 11-02 (Benjamin t2107u "a sharper drop shadow behind the text and bars"): one tight, dark, slightly offset shadow for the overlaid
// text, badges and color bar on every Studio mode (was a soft 6-8 px blur, no offset). Frames are fixed-size output px, so it is
// the same in the on-screen frames, Save PNG and Save MP4.
// 11-04 (t2295u "pass forecaster ... looks a little soft in studio"): the Pass Forecaster frame is drawn at PSS x the frame size (canvas backing
// 2160x3840 / 3840x2160, same CSS size and same layout in frame px via the transform), so text stays crisp on hi-dpi screens and Save PNG.
// Canvas shadows ignore the transform, so shadow px are scaled by the context's own scale (1 on every other mode: unchanged).
const PSS = 2;
const ctxS = (c) => (c.getTransform ? c.getTransform().a : 1) || 1;
function ssFit(f, s) { if (f.cv.width !== f.W * s || f.cv.height !== f.H * s) { f.cv.width = f.W * s; f.cv.height = f.H * s; } f.ss = s; }
function sharpShadow(c, k) { const z = ctxS(c); c.shadowColor = "rgba(0,0,0,0.92)"; c.shadowBlur = 1.5 * z; c.shadowOffsetX = (k === "v" ? 3 : 2.5) * z; c.shadowOffsetY = (k === "v" ? 3 : 2.5) * z; }
// 11-02 6:20 PM (Benjamin t2111u "drop shadow ... a little more pronounced with a bit of a fade so it doesn't look messy"): overlay text,
// badges and bars are drawn (with the tight sharp core shadow above) into an off-screen layer, then that layer goes onto the frame once
// with a soft short falloff shadow: sharp core + gentle fade, one pass, so overlapping glyph shadows never stack up into smudges.
function ovLayer(f) { const o = f.ov || (f.ov = document.createElement("canvas")), z = f.ss || 1; if (o.width !== f.W * z || o.height !== f.H * z) { o.width = f.W * z; o.height = f.H * z; }
  const oc = o.getContext("2d"); oc.setTransform(z, 0, 0, z, 0, 0); oc.clearRect(0, 0, f.W, f.H); return oc; }
function ovPut(c, f, k) { const z = ctxS(c); c.save(); c.shadowColor = "rgba(0,0,0,0.55)"; c.shadowBlur = (k === "v" ? 14 : 12) * z; c.shadowOffsetX = 0; c.shadowOffsetY = (k === "v" ? 2 : 1.5) * z;
  c.drawImage(f.ov, 0, 0, f.W, f.H); c.restore(); }
function noShadow(c) { c.shadowColor = "rgba(0,0,0,0)"; c.shadowBlur = 0; c.shadowOffsetX = 0; c.shadowOffsetY = 0; }
function pill(c, x, y, txt, size, bg, fg) {
  c.font = `800 ${size}px Montserrat`; const w = c.measureText(txt).width + size * 0.9, h = size * 1.55;
  c.fillStyle = bg; c.beginPath(); c.roundRect ? c.roundRect(x, y, w, h, h / 2) : c.rect(x, y, w, h); c.fill();
  c.fillStyle = fg; c.textBaseline = "middle"; c.fillText(txt, x + size * 0.45, y + h / 2 + 1); c.textBaseline = "alphabetic"; return w;
}
function colorbar(c, P, x, y, w, h, size) {
  const L = P.levels, C = P.colors; if (!L || !C || L.length < 2) return false;
  const lo = L[0], hi = L[L.length - 1], n = L.length - 1;   // equal-width bins (like the site's keys), ticks placed inside their bin
  // 11-01 9:16 AM (Benjamin t1996u "the numbers need to be fixed"): optional per-bin cell widths P.kw (max wave: 75-77.5 and 77.5-80 half a cell
  // each, so 75-80 is one cell like the other 5 ft steps and 75 / 80 / 85 stay evenly spaced on their color edges)
  const KW = Array.isArray(P.kw) && P.kw.length === n ? P.kw : null, CW = [0]; for (let i = 0; i < n; i++) CW.push(CW[i] + (KW ? KW[i] : 1));
  const X = (v) => { let i = 0; while (i < n - 1 && v > L[i + 1]) i++; const fr = Math.min(1, Math.max(0, (v - L[i]) / ((L[i + 1] - L[i]) || 1)));
    return x + (CW[i] + fr * (CW[i + 1] - CW[i])) / CW[n] * w; };
  const sh = [c.shadowColor, c.shadowBlur, c.shadowOffsetX, c.shadowOffsetY];
  if (sh[1] || sh[2] || sh[3]) { c.fillStyle = "#000"; c.fillRect(x, y, w, h); c.shadowColor = "rgba(0,0,0,0)"; }
  for (let i = 0; i < C.length && i < L.length - 1; i++) { c.fillStyle = C[i]; c.fillRect(Math.floor(X(L[i])), y, Math.ceil(X(L[i + 1]) - X(L[i])) + 1, h); }
  c.strokeStyle = "rgba(255,255,255,0.55)"; c.lineWidth = 1.5; c.strokeRect(x, y, w, h); c.shadowColor = sh[0];
  c.font = `600 ${size}px Montserrat`; c.fillStyle = "#e9ecf1"; c.textAlign = "center";
  // ticks: skip any whose label would touch the previous drawn one (precip keys bunch 0.01-0.5 into a few bins)
  // 11-01 8:55 AM (Benjamin t1992u "add a couple more numbers to the scale, maybe every 5 feet"): the max wave bars (5 ft numbers 40-85, one per bin)
  // allow a 0.3 em gap between numbers instead of 0.6 em, so 45 / 55 / 65 / 75 show; every other bar unchanged
  const tgap = /^Max wave/.test(P.key || "") ? 0.3 : 0.6;
  let lastR = -1e9; (P.ticks || []).filter((t) => t >= lo && t <= hi).forEach((t) => { const tx = X(t), s_ = fmtTick(t, P), tw = c.measureText(s_).width;
    if (tx - tw / 2 < lastR + size * tgap) {
      // 11-01 8:30 AM (Benjamin: "Yes fix the tick label"): the top tick (e.g. 85 on max wave height) sits on the bar's right end and got
      // skipped next to 80; draw it left-aligned from the end (hanging just past the bar) when that clears the previous label
      const lx = tx + size * 0.2; if (Math.abs(t - hi) > 1e-9 || lx < lastR + size * 0.3) return;
      c.fillRect(tx - 2, y + h, 2, size * 0.35); c.textAlign = "left"; c.fillText(s_, lx, y + h + size * 1.35); c.textAlign = "center"; lastR = lx + tw; return;
    }
    lastR = tx + tw / 2; c.fillRect(tx - 1, y + h, 2, size * 0.35); c.fillText(s_, tx, y + h + size * 1.35); });
  c.textAlign = "left"; c.font = `700 ${size}px Montserrat`; c.fillText(P.key || "", x, y - size * 0.55);
  return true;
}
// ---- branding (10-31 3:49 PM, Benjamin: "Yes to 3"): a title card at the start of a video and a lower third on every frame
// (logo, title / storm name, model + run, forecast date). Toggles in the Save MP4 panel (remembered); links: &brand=1 (both on),
// &title=, &storm=, &brandlogo=wa|usa|wawc|usawc|none, &card=0|1, &lower=0|1.
const LOGOS = { wa: "brand/wawx.png", usa: "brand/usawx.png", wawc: "brand/wawc.png", usawc: "brand/usawc.png" };
// 10-31 4:45 PM (Benjamin: "I think I liked it better without the logo and that bar"): OFF by default everywhere. The on / off
// toggles are never remembered (key studio:brand3 keeps only logo / title / storm; old studio:brand "on" values are dropped);
// links (make=loop, clean OBS) ignore saved settings and only brand when the link says brand=1 (or card=1 / lower=1).
try { localStorage.removeItem("studio:brand"); } catch (e) { /* private */ }
const BR = Object.assign({ card: false, lower: false, logo: "wa", title: "", storm: "" }, (() => { if (SQ.get("make") || CLEAN) return {};
  try { const o = JSON.parse(localStorage.getItem("studio:brand3") || "{}"); delete o.card; delete o.lower; delete o.corner; return o; } catch (e) { return {}; } })());
if (SQ.get("brand") === "1") { BR.card = true; BR.lower = true; }
// corner logo (10-31 4:51 PM, Benjamin: "a smaller logo in one of the top corners ... under the F+ hours", "Just the logo"):
// only the logo image, no text / panel. Off on every load (never remembered as on); corner + logo choice are remembered.
// Links: &corner=1, &cornerpos=br|bl|tr|tl (default br), &brandlogo=.
// 10-31 5:03 PM (Benjamin: "right where i circled ... about 50% transparent"): default bottom right on the credit-line row, 50 % opacity.
const CPOS = ["br", "bl", "tr", "tl"];
BR.corner = SQ.get("corner") === "1"; BR.cpos = CPOS.includes(SQ.get("cornerpos")) ? SQ.get("cornerpos") : CPOS.includes(BR.cpos2) ? BR.cpos2 : "br"; delete BR.cpos2;
for (const [q, k_] of [["card", "card"], ["lower", "lower"]]) if (SQ.has(q)) BR[k_] = SQ.get(q) === "1";
if (SQ.has("title")) BR.title = SQ.get("title"); if (SQ.has("storm")) BR.storm = SQ.get("storm"); if (SQ.has("brandlogo")) BR.logo = SQ.get("brandlogo");
const saveBR = () => { if (!SQ.get("make") && !CLEAN) try { localStorage.setItem("studio:brand3", JSON.stringify({ logo: BR.logo, cpos2: BR.cpos, title: BR.autoT ? "" : BR.title, storm: BR.autoS ? "" : BR.storm })); } catch (e) { /* private */ } };
const logoImg = {};
function getLogo() { const u = LOGOS[BR.logo]; if (!u) return null; if (!logoImg[u]) { const im = new Image(); im.src = u; logoImg[u] = im; im.onload = () => renderAll(); } const im = logoImg[u]; return im.complete && im.naturalWidth ? im : null; }
const ptTime = (iso, o) => { try { return new Date(iso).toLocaleString("en-US", Object.assign({ timeZone: "America/Los_Angeles" }, o)); } catch (e) { return iso; } };
function runText() { const [m, c] = last.cur.run.split("/"), site = (S.man.models[m] || {}).site || m; return `${site} ${c.slice(8)}Z ${c.slice(4, 6)}-${c.slice(6, 8)} run`; }
// just the logo image at 50 % opacity with a light dark halo (no panel). Sizes: top 10 % (9:16) / 8 % (16:9) of frame width;
// bottom a touch smaller (96 / 120 px). br: right-aligned on the credit-line row (16:9: the credit text moves left of it);
// bl: 9:16 left on the credit row (credit moves right of it), 16:9 just above the colour key's label (the key fills the bottom left);
// tr: under the F+ badge; tl: under the header text.
function cornerBox(k, badgeBot, headBot, cbY) {
  const f = F[k], p = BR.cpos;
  if (p === "tr" || p === "tl") { const s = Math.round(f.W * (k === "v" ? 0.10 : 0.08)), gap = k === "v" ? 18 : 14; return { s, x: p === "tl" ? f.pad : f.W - f.pad - s, y: Math.round((p === "tl" ? headBot : badgeBot) + gap) }; }
  const s = k === "v" ? 96 : 120;
  if (k === "v") return { s, x: p === "bl" ? f.pad : f.W - f.pad - s, y: Math.round(f.H - 70 - 8 - s / 2) };   // centred on the credit text (baseline H-70)
  if (p === "br") return { s, x: f.W - f.pad - s, y: f.H - 14 - s };
  return { s, x: f.pad, y: cbY - 30 - 16 - s };
}
function cornerLogo(c, b) {
  const lg = getLogo(); if (!lg || !b) return;
  c.save(); c.globalAlpha = 0.5; c.shadowColor = "rgba(0,0,0,0.45)"; c.shadowBlur = Math.round(b.s * 0.06) * ctxS(c); c.drawImage(lg, b.x, b.y, b.s, b.s); c.restore();
}
function lowerThird(k, c) {
  const f = F[k], step = last.step, lg = getLogo(), h = k === "v" ? 150 : 118, w = k === "v" ? f.W - 2 * f.pad : 860, x = f.pad, y = f.H - f.bot - h - (k === "v" ? 40 : 26);
  c.save(); c.fillStyle = "rgba(13,15,19,0.84)"; c.beginPath(); c.roundRect ? c.roundRect(x, y, w, h, 16) : c.rect(x, y, w, h); c.fill();
  c.fillStyle = "#2f8cff"; c.fillRect(x, y + 14, 8, h - 28);
  let tx = x + 28; const ls = h - 30;
  if (lg) { c.drawImage(lg, tx, y + 15, ls, ls); tx += ls + 22; }
  const l1 = BR.storm || BR.title || last.cur.P.title, l2 = `${runText()} \u00b7 ${ptTime(step.valid, { weekday: "short", month: "short", day: "numeric", hour: "numeric" })} PT`;
  c.fillStyle = "#fff"; c.font = `800 ${k === "v" ? 46 : 40}px Montserrat`; c.textBaseline = "alphabetic";
  let t1 = l1; while (c.measureText(t1).width > x + w - tx - 24 && t1.length > 4) t1 = t1.slice(0, -2); if (t1 !== l1) t1 += "\u2026";
  c.fillText(t1, tx, y + h * 0.5); c.font = `600 ${k === "v" ? 28 : 25}px Montserrat`; c.fillStyle = "#ffc24d"; c.fillText(l2, tx, y + h * 0.5 + (k === "v" ? 44 : 38));
  c.restore();
}
function titleCard(k, c, alpha, a0, a1) {   // over the first map; a0 / a1 = first / last step of the loop
  const f = F[k], lg = getLogo(); c.save(); c.globalAlpha = alpha;
  c.fillStyle = "rgba(10,12,16,0.86)"; c.fillRect(0, 0, f.W, f.H);
  const ls = k === "v" ? 380 : 300, cx = f.W / 2; let y = k === "v" ? 520 : 150;
  if (lg) { c.drawImage(lg, cx - ls / 2, y, ls, ls); y += ls + (k === "v" ? 110 : 90); } else y += k === "v" ? 300 : 220;
  c.textAlign = "center"; c.fillStyle = "#fff"; c.font = `900 ${k === "v" ? 76 : 80}px Montserrat`;
  const OI = OBSM() ? obsInfo() : null, words = (BR.title || BR.storm || (OI ? OI.title : last.cur.P.title)).split(" "), maxW = f.W - 2 * f.pad, lines = []; let line = "";
  for (const w_ of words) { const t = line ? line + " " + w_ : w_; if (c.measureText(t).width > maxW && line) { lines.push(line); line = w_; } else line = t; } lines.push(line);
  lines.slice(0, 3).forEach((t, i) => c.fillText(t, cx, y + i * (k === "v" ? 86 : 88))); y += (Math.min(3, lines.length) - 1) * (k === "v" ? 86 : 88) + (k === "v" ? 80 : 74);
  if (BR.storm && BR.title) { c.font = `800 ${k === "v" ? 48 : 46}px Montserrat`; c.fillStyle = "#ffc24d"; c.fillText(BR.storm, cx, y); y += k === "v" ? 70 : 64; }
  c.font = `600 ${k === "v" ? 38 : 36}px Montserrat`; c.fillStyle = "#cfd3da";
  if (OI) { c.fillText(`Station reports \u00b7 ${OI.when}`, cx, y); c.restore(); return; }
  c.fillText(`${runText()} \u00b7 ${last.cur.P.title}`, cx, y); y += k === "v" ? 58 : 54;
  if (a0 && a1) c.fillText(`${ptTime(a0.valid, { weekday: "short", month: "short", day: "numeric", hour: "numeric" })} \u2013 ${ptTime(a1.valid, { weekday: "short", month: "short", day: "numeric", hour: "numeric" })} PT`, cx, y);
  c.restore();
}
window.__studioBrand = { BR, titleCard: (k, a) => titleCard(k, F[k].cv.getContext("2d"), a == null ? 1 : a, null, null) };
// 11-02 (Benjamin t2111u "add the scale for what different colors represent on the ensemble lows on the right hand side"): member-dot key
// for the ensemble low-centre maps (AIFS ENS / EPS "elows"): each dot = one member's low centre, colored by its central pressure in the
// viewer's 8 bands (DOT_COLS / DOT_LABELS = ens_maps). Right edge, below the top-right webcam corner (16:9) / above the color bar (9:16).
function lowKey(c, f, k, cbY, cbS) {
  if (typeof DOT_COLS === "undefined") return;
  const fs = k === "v" ? 25 : 21, rh = Math.round(fs * 1.45), rr = k === "v" ? 9 : 8, n = DOT_COLS.length;
  c.save(); c.font = `700 ${fs}px Montserrat`; const head = ["Member low", "pressure (mb)"];
  const lw = Math.max(...DOT_LABELS.map(t => c.measureText(t).width)), hw = Math.max(...head.map(t => c.measureText(t).width));
  const w = Math.max(hw, rr * 2 + 12 + lw); let x0 = f.W - f.pad - w; const hH = fs * 2.5 + 8, tot = hH + n * rh;
  // t2115u: flush against the right edge of the frame, 50 % translucent card, text with the frame's shadow (sharp core here + soft fade in ovPut)
  const pd = k === "v" ? 18 : 15; x0 = f.W - w - pd; const y0 = k === "v" ? cbY - cbS * 1.6 - 22 - tot - pd : f.H - 150 - tot - 2 * pd;   // 9:16: just above the bar's label   // 16:9: lower right, above the credit lines
  // compact dark card (reads on the white map and over the map's own member list), keeps the frame's shadow style
  noShadow(c); c.fillStyle = "rgba(15,17,21,0.5)"; c.beginPath(); c.roundRect ? c.roundRect(x0 - pd, y0 - pd * 0.6, w + 2 * pd, tot + pd * 1.4, [14, 0, 0, 14]) : c.rect(x0 - pd, y0 - pd * 0.6, w + 2 * pd, tot + pd * 1.4); c.fill(); sharpShadow(c, k);
  c.fillStyle = "#e9ecf1"; c.textAlign = "left"; c.textBaseline = "alphabetic"; head.forEach((t, i) => c.fillText(t, x0, y0 + fs + i * fs * 1.2));
  c.font = `600 ${fs}px Montserrat`; c.textBaseline = "middle";
  for (let i = 0; i < n; i++) { const yy = y0 + hH + i * rh + rh / 2, cx = x0 + rr + 1;
    c.beginPath(); c.arc(cx, yy, rr, 0, 2 * Math.PI); c.fillStyle = DOT_COLS[i]; c.fill(); c.lineWidth = 2; c.strokeStyle = "#ffffff"; c.stroke();
    c.fillStyle = "#fff"; c.fillText(DOT_LABELS[i], cx + rr + 11, yy + 1); }
  c.restore();
}
// ---- Observations in Studio (11-03, t2192u): same header / badge / credit style as the maps; the obs module's own map is the picture
const OBS_LAYERS = [["plot", "Station plot", "#ffffff"], ["hi", "High", "#ff8a6e"], ["lo", "Low", "#7f97ff"], ["pk", "Peak gust", "#ffd23f"], ["feel", "Wind chill / heat index", "#c9a2ff"], ["mslp", "MSLP", "#7fe0b5"]];
// 11-04 (Benjamin "make the credit line smaller, and remove ones we don't legally need"): only the credits a licence asks for stay on
// the frames: ECCC (OGL-Canada attribution) when station layers show, GeoNames (CC BY 4.0), Natural Earth (standing rule). NOAA/NWS
// ASOS/AWOS, MRMS radar and NOAA/NESDIS STAR water vapor are public domain (credited on the site's Observations page instead).
const OBS_CREDIT_ST = "Contains information licensed under the Open Government Licence \u2013 Canada (ECCC).", OBS_CREDIT = ["Places: GeoNames, CC BY 4.0.  Basemap: Natural Earth."];
const OBS_TF = new Intl.DateTimeFormat("en-US", { timeZone: "America/Los_Angeles", weekday: "short", month: "2-digit", day: "2-digit", hour: "numeric", minute: "2-digit" });
function obsInfo() {
  const S_ = typeof Obs !== "undefined" && Obs._state; if (!S_) return null;
  const on = OBS_LAYERS.filter((l) => S_.on.has(l[0])), t = S_.loaded ? new Date(S_.loaded) : null;
  // 11-03 radar / GOES-West layers (obsimg.js): one legend pill each with the frame time shown
  const IM = typeof ObsImg !== "undefined" && ObsImg.active() ? ObsImg.info() : [], itf = (x) => (x ? " " + new Intl.DateTimeFormat("en-US", { timeZone: "America/Los_Angeles", hour: "numeric", minute: "2-digit" }).format(new Date(x)) + " PT" : "");
  const imPills = IM.map((m) => ["img_" + m.id, m.label + itf(m.t), m.id === "radar" ? "#7cf08c" : "#d6dee8"]);
  const T1 = { hi: "Today's High Temperatures", lo: "Today's Low Temperatures", pk: "Today's Peak Wind Gusts", feel: "Wind Chill / Heat Index", mslp: "Sea-Level Pressure" };
  const title = !on.length && IM.length ? (IM.length > 1 ? "Radar and Satellite" : IM[0].id === "radar" ? "Radar" : "GOES-West Satellite") : on.length === 1 && T1[on[0][0]] ? T1[on[0][0]] : on.length === 2 && S_.on.has("hi") && S_.on.has("lo") ? "Today's Highs and Lows" : "Current Observations";
  let when = ""; if (t) { const p = Object.fromEntries(OBS_TF.formatToParts(t).map((x) => [x.type, x.value])); when = `${p.weekday} ${p.month}-${p.day} \u00b7 ${p.hour}:${p.minute} ${p.dayPeriod} PT`; }
  return { on: [...on, ...imPills], t, title, when, view: S_.view, img: IM };
}
function renderObs(k, frO) {
  const f = F[k], c0 = f.cv.getContext("2d"), fr = frO || getFr(k); if (!frO) { f.zoom.min = "5"; f.zoom.value = obsZv(fr); }
  c0.setTransform(1, 0, 0, 1, 0, 0); c0.clearRect(0, 0, f.W, f.H); c0.fillStyle = BG === "transparent" ? "#111316" : BG; c0.fillRect(0, 0, f.W, f.H);
  const I = obsInfo();
  if (!MG.img || !I || !I.t) { c0.font = `700 ${k === "v" ? 40 : 34}px Montserrat`; c0.fillStyle = "#c9ced8"; c0.textAlign = "center"; c0.fillText(MG.msg || "Loading observations\u2026", f.W / 2, f.H / 2); c0.textAlign = "left"; return; }
  const r = crop(k, fr); c0.imageSmoothingEnabled = true; c0.imageSmoothingQuality = "high";
  c0.drawImage(MG.img, f.W / 2 - r.cx * r.kk, f.H / 2 - r.cy * r.kk, IW(MG.img) * r.kk, IH(MG.img) * r.kk);
  const c = ovLayer(f), x = f.pad; let y = k === "v" ? 120 : 34;
  // 11-04 (Benjamin): satellite / radar with no station layer on: no "OBSERVED station reports" line, the title and time move up
  const stOn0 = I.on.some((q) => !String(q[0]).startsWith("img_"));
  c.save(); sharpShadow(c, k);
  if (stOn0) { const pw = pill(c, x, y, "OBSERVED", Math.round(f.run * 0.95), "#16a34a", "#fff");
    c.font = `600 ${f.run}px Montserrat`; c.fillStyle = "#c9ced8"; c.fillText("station reports", x + pw + 14, y + f.run * 1.08);
    y += f.run * 1.55 + f.title * 1.02; } else y += f.title * 0.92; c.font = `800 ${f.title}px Montserrat`; c.fillStyle = "#fff"; c.fillText(I.title, x, y);
  y += f.day * 1.3; c.font = `800 ${f.day}px Montserrat`; c.fillStyle = "#ffc24d"; c.fillText(I.when, x, y);
  const headBot = y + f.day * 0.45;
  c.font = `800 ${Math.round(f.valid * 1.1)}px Montserrat`; const bt = "LIVE", bw = c.measureText(bt).width + 40, bx = f.W - f.pad - bw, by = k === "v" ? 120 : 34;
  c.fillStyle = "rgba(17,19,22,0.85)"; c.strokeStyle = "rgba(255,255,255,0.35)"; c.lineWidth = 2; c.beginPath(); c.roundRect ? c.roundRect(bx, by, bw, f.valid * 1.9, 14) : c.rect(bx, by, bw, f.valid * 1.9); c.fill(); noShadow(c); c.stroke(); sharpShadow(c, k);
  c.fillStyle = "#fff"; c.textAlign = "center"; c.fillText(bt, bx + bw / 2, by + f.valid * 1.32); c.textAlign = "left"; c.restore();
  const cnr = BR.corner && LOGOS[BR.logo] ? cornerBox(k, by + f.valid * 1.9, headBot, f.H - f.bot + (k === "v" ? 110 : 62)) : null;
  // bottom: a legend of the layers shown (number colours, like the obs page's chips) in place of the color bar, then the locked credit lines
  c.save(); sharpShadow(c, k);
  const stOn = I.on.some((x) => !String(x[0]).startsWith("img_"));
  const dl = [...(I.img && I.img.length && typeof ObsImg !== "undefined" ? ObsImg.credits() : []), ...(stOn ? [OBS_CREDIT_ST] : []), ...OBS_CREDIT], cB = cnr && (BR.cpos === "br" || BR.cpos === "bl") ? cnr : null;
  let dfs = k === "v" ? 15 : 14; c.font = `600 ${dfs}px Montserrat`;   // 11-04: smaller (was 19 / 17)
  const dMax = k === "v" ? f.W - 2 * f.pad : Math.round(f.W * 0.52);
  while (dfs > 11 && Math.max(...dl.map((l) => c.measureText(l).width)) > dMax) { dfs -= 1; c.font = `600 ${dfs}px Montserrat`; }
  const dlh = dfs + 7, lgS = k === "v" ? 30 : 26;
  c.fillStyle = "rgba(236,239,244,0.95)";
  if (k === "v") dl.forEach((l, i) => c.fillText(l, f.pad + (cB && BR.cpos === "bl" ? cB.s + 18 : 0), f.H - 70 - (dl.length - 1 - i) * dlh));
  else { c.textAlign = "right"; dl.forEach((l, i) => c.fillText(l, f.W - f.pad - (cB && BR.cpos === "br" ? cB.s + 20 : 0), f.H - 24 - (dl.length - 1 - i) * dlh)); c.textAlign = "left"; }
  let lx = f.pad + (k === "h" && cB && BR.cpos === "bl" ? cB.s + 20 : 0); let ly = k === "v" ? f.H - 70 - (dl.length - 1) * dlh - dfs - 30 - lgS * 1.55 : f.H - 24 - lgS * 1.55 + lgS * 0.35;
  // 11-04 (Benjamin t2301u "remove the satellite time ticker off of the bottom of studio ... I like the radar time in the bottom left"):
  // the bottom legend skips the satellite pills (their frame time ticked with the loop); radar pill + time stay. Top title / time unchanged.
  for (const [id, lab, col] of I.on.filter((q) => !String(q[0]).startsWith("img_") || q[0] === "img_radar")) {
    c.font = `800 ${lgS}px Montserrat`; const t = { plot: "Station plot: \u00b0F, gust mph, wind kt", hi: "High \u00b0F", lo: "Low \u00b0F", pk: "Peak gust mph", feel: "Feels like \u00b0F", mslp: "MSLP hPa" }[id] || lab, w = c.measureText(t).width + lgS * 1.2, h = lgS * 1.55;
    const img_ = String(id).startsWith("img_");
    if (lx + w > (k === "v" ? f.W - f.pad : f.W * 0.46) && lx > f.pad + 1) { if (img_) { lx = f.pad + (k === "h" && cB && BR.cpos === "bl" ? cB.s + 20 : 0); ly -= h + 10; } else if (k === "v") break; }   // 11-03: radar / satellite pills wrap to a row above
    noShadow(c); c.fillStyle = "rgba(17,19,22,0.78)"; c.beginPath(); c.roundRect ? c.roundRect(lx, ly, w, h, h / 2) : c.rect(lx, ly, w, h); c.fill(); sharpShadow(c, k);
    c.fillStyle = col; c.textBaseline = "middle"; c.fillText(t, lx + lgS * 0.6, ly + h / 2 + 1); c.textBaseline = "alphabetic"; lx += w + 12;
  }
  c.restore(); ovPut(c0, f, k);
  if (cnr) cornerLogo(c0, cnr);
  if (PIN.show && !REC.on) drawPins(k, c0, r);
  window.__studio = (window.__studio || 0) + 1; window.__studioObs = (window.__studioObs || 0) + 1;
}
// ---- Pass Forecaster in Studio (11-04, t2292u). Same table as the map page's Pass Forecaster (viewer.js passTable), laid out per frame:
// 16:9 every column; 9:16 drops Kuchera, then precip, then gust only if the pass names would get too small. Header like the maps
// (model pill + run, title, run start in amber), shading key at the bottom, and only the credit a licence needs (ECMWF runs).
const PFCOL = { s1: "#1f3b5c", s2: "#2a5d96", s3: "#4a3a9a", fzb: "#1e4f7a" };
function pfParse(body) {
  const tb = body.querySelector("table.pf"); if (!tb) return null; const tx = document.createElement("div");
  const lines = (el) => el.innerHTML.split(/<br\s*\/?>/i).map((h) => { tx.innerHTML = h; return tx.textContent.trim(); }).filter(Boolean);
  const rows = [...tb.rows].map((r) => [...r.cells].map((td) => ({ t: lines(td), cls: td.className || "", th: td.tagName === "TH" })));
  const note = body.querySelector(".mg-note"); return { head: rows[0], body: rows.slice(1), note: note ? note.textContent : "" };
}
function pfCols(head, k) {   // column indexes kept for this frame, most important last to drop
  const all = head.map((_, j) => j), isK = (j) => /Kuchera/.test(head[j].t[0]), isP = (j) => /^Precip/.test(head[j].t[0]), isG = (j) => /gust/i.test(head[j].t[0]);
  if (k === "h") return [all];
  const a = all.filter((j) => !isK(j)); return [a, a.filter((j) => !isP(j)), a.filter((j) => !isP(j) && !isG(j))];
}
function renderPass(k) {
  const f = F[k]; ssFit(f, PSS); const c0 = f.cv.getContext("2d"); f.zoom.min = "100"; f.zoom.value = "100";
  c0.setTransform(PSS, 0, 0, PSS, 0, 0); c0.clearRect(0, 0, f.W, f.H); c0.fillStyle = BG === "transparent" ? "#111316" : BG; c0.fillRect(0, 0, f.W, f.H);
  const D = PF.rows;
  if (!D) { c0.font = `700 ${k === "v" ? 40 : 34}px Montserrat`; c0.fillStyle = "#c9ced8"; c0.textAlign = "center"; c0.fillText(PF.msg || "Loading the Pass Forecaster\u2026", f.W / 2, f.H / 2); c0.textAlign = "left"; return; }
  const c = ovLayer(f), x = f.pad, [m, cyc] = PF.run.split("/"), site = (S.man.models[m] || {}).site || m; let y = k === "v" ? 120 : 34;
  c.save(); sharpShadow(c, k); const pw = pill(c, x, y, site.toUpperCase(), Math.round(f.run * 0.95), "#2f8cff", "#fff");
  c.font = `600 ${f.run}px Montserrat`; c.fillStyle = "#c9ced8"; c.fillText(`${cyc.slice(8)}Z run`, x + pw + 14, y + f.run * 1.08);
  y += f.run * 1.55 + f.title * 1.02; c.font = `800 ${f.title}px Montserrat`; c.fillStyle = "#fff";
  // 11-04 (t2313u): one-line title like the obs title when it fits the frame
  const ttl = k === "h" || c.measureText("Washington Pass Forecast").width <= f.W - 2 * f.pad ? ["Washington Pass Forecast"] : ["Washington", "Pass Forecast"]; ttl.forEach((t, i) => c.fillText(t, x, y + i * f.title * 1.08)); y += (ttl.length - 1) * f.title * 1.08 + f.day * 1.3;
  const rs = (D.note.match(/Run start ([^.]*PT)/) || [])[1] || ""; c.font = `800 ${f.day}px Montserrat`; c.fillStyle = "#ffc24d"; c.fillText(rs ? `Run start ${rs}` : "", x, y);
  let top = y + f.day * 0.9; const headBot = y + f.day * 0.45; c.restore(); ovPut(c0, f, k);   // header onto the frame now (the key below reuses the overlay layer)
  // bottom: shading key + notes + credit, measured first so the table gets the rest
  const ec = window.studioIsEc && window.studioIsEc(PF.run), cr = ec ? [`Data: \u00a9 ${new Date().getFullYear()} ECMWF (www.ecmwf.int), CC BY 4.0. Modified.`] : [];
  // 11-04 (t2313u "framed similar to the other products, for my obs setup"): bottom laid out like Observations: shading key where the
  // obs layer legend sits (16:9 bottom-left on the credit line, 9:16 just above the credits), notes + credit in the obs credit block
  // (16:9 bottom-right, 9:16 bottom-left at H-70), same 15 / 14 px credit size. The table then fills the space between header and key.
  const kfs = k === "v" ? 30 : 26, est = /estimated 10:1/.test(D.note);
  const dl = ["Elevation = highway summit (WSDOT). Temps corrected to summit height.", est ? "Snow estimated 10:1 where 2 m temp \u2264 33\u00b0F." : "", ...cr].filter(Boolean);
  let dfs = k === "v" ? 15 : 14; { const mc0 = document.createElement("canvas").getContext("2d"), dMax = k === "v" ? f.W - 2 * f.pad : Math.round(f.W * 0.52);
    mc0.font = `600 ${dfs}px Montserrat`; while (dfs > 11 && Math.max(...dl.map((l) => mc0.measureText(l).width)) > dMax) { dfs -= 1; mc0.font = `600 ${dfs}px Montserrat`; } }
  const dlh = dfs + 7, KEY = [["s1", "1\u20136\u2033 snow"], ["s2", "6\u201312\u2033"], ["s3", "12\u2033+"], ["fzb", "Freezing level below the pass"]];
  const kh = kfs * 1.55, kmx = k === "v" ? f.W - f.pad : (() => { const m_ = document.createElement("canvas").getContext("2d"); m_.font = `600 ${dfs}px Montserrat`; return f.W - f.pad - Math.max(...dl.map((l) => m_.measureText(l).width)) - 40; })();   // 16:9: key runs up to the credit block
  const krows = (() => { const mk = document.createElement("canvas").getContext("2d"); mk.font = `800 ${kfs}px Montserrat`; const rows = [[]]; let bx_ = x;
    for (const it of KEY) { const w = mk.measureText(it[1]).width + kfs * 1.2; if (bx_ + w > kmx && bx_ > x + 1) { rows.push([]); bx_ = x; } rows[rows.length - 1].push([...it, w]); bx_ += w + 12; } return rows; })();
  const ky0 = k === "v" ? f.H - 70 - (dl.length - 1) * dlh - dfs - 30 - kh : f.H - 24 - kh + kfs * 0.35;   // same y as the obs legend row
  const bot = ky0 - (krows.length - 1) * (kh + 10) - 24;
  // table: pick columns + font so it fits the frame width and the space between header and key
  const mc = document.createElement("canvas").getContext("2d"), avW = f.W - 2 * f.pad, avH = bot - top - 10;
  const fitT = (cols, fs) => { const hs = Math.round(fs * 0.62), pad = Math.round(fs * 0.55), cw = cols.map(() => 0);
    const sub = (s) => s.replace(/\u2013/g, "\u2013 ").split(/(?<=\u2013 |, )/);   // header detail lines may wrap after a dash or comma
    cols.forEach((j, q) => { mc.font = `800 ${fs}px Montserrat`; for (const r of D.body) { const cell = r[j]; if (!cell) continue; cw[q] = Math.max(cw[q], mc.measureText(cell.t[0] || "").width + 2 * pad);
        if (cell.t[1]) { mc.font = `600 ${hs}px Montserrat`; cw[q] = Math.max(cw[q], mc.measureText(cell.t[1]).width + 2 * pad); mc.font = `800 ${fs}px Montserrat`; } }
      const h = D.head[j]; mc.font = `800 ${hs * 1.12}px Montserrat`; cw[q] = Math.max(cw[q], mc.measureText(h.t[0]).width + 2 * pad);
      mc.font = `600 ${hs}px Montserrat`; for (const ln of h.t.slice(1)) for (const tk of sub(ln)) cw[q] = Math.max(cw[q], mc.measureText(tk.trim()).width + 2 * pad); });
    const extra = avW - cw.reduce((a, b) => a + b, 0); if (extra < 0) return null; cw.forEach((_, q) => cw[q] += q ? extra / cols.length * 0.9 : extra / cols.length * 1.9 - extra * 0.0);
    const tot = cw.reduce((a, b) => a + b, 0); if (tot > avW) { const sc = avW / tot; cw.forEach((_, q) => cw[q] *= sc); }
    // header height: wrap detail lines to the column width
    const hl = cols.map((j, q) => { mc.font = `600 ${hs}px Montserrat`; const out = []; for (const ln of D.head[j].t.slice(1)) { let cur = ""; for (const tk of sub(ln)) { const tt = cur + tk; if (cur && mc.measureText(tt.trim()).width > cw[q] - 2 * pad) { out.push(cur.trim()); cur = tk; } else cur = tt; } if (cur.trim()) out.push(cur.trim()); } return out; });
    const hh = Math.round(hs * 1.12 * 1.35 + Math.max(...hl.map((a) => a.length)) * hs * 1.25 + pad), sub2 = D.body.some((r) => r[0] && r[0].t[1]);
    const rh = Math.round(fs * 1.25 + (sub2 ? hs * 1.2 : 0) + pad * 1.1), H = hh + rh * D.body.length; if (H > avH) return null;
    return { cols, fs, hs, pad, cw, hl, hh, rh, H }; };
  let L = null; const opts = pfCols(D.head, k), f0 = k === "v" ? 34 : 30, fmin = k === "v" ? 22 : 18;
  for (const cols of opts) { for (let fs = f0; fs >= fmin && !L; fs -= 1) L = fitT(cols, fs); if (L) break; }
  if (!L) { const cols = opts[opts.length - 1]; for (let fs = fmin; fs >= 12 && !L; fs -= 1) L = fitT(cols, fs); }
  if (L) {
    { const rh2 = Math.min(L.rh * (k === "v" ? 2 : 1.6), (avH - L.hh) / D.body.length); if (rh2 > L.rh) { L.ro = (rh2 - L.rh) / 2; L.rh = rh2; L.H = L.hh + rh2 * D.body.length; } else L.ro = 0; }   // 11-04 (t2313u): rows grow to fill the frame (no empty band)
    const g = c0, ty = Math.round(top + Math.max(0, (avH - L.H) / 2));
    g.save(); g.fillStyle = "rgba(29,32,39,0.96)"; g.beginPath(); g.roundRect ? g.roundRect(x - 2, ty, avW + 4, L.H, 14) : g.rect(x - 2, ty, avW + 4, L.H); g.fill();
    g.fillStyle = "#262a33"; g.beginPath(); g.roundRect ? g.roundRect(x - 2, ty, avW + 4, L.hh, [14, 14, 0, 0]) : g.rect(x - 2, ty, avW + 4, L.hh); g.fill();
    let cx_ = x; g.textBaseline = "top";
    L.cols.forEach((j, q) => { const w = L.cw[q], al = q === 0 ? "left" : "right", tx = q === 0 ? cx_ + L.pad : cx_ + w - L.pad; g.textAlign = al;
      g.font = `800 ${Math.round(L.hs * 1.12)}px Montserrat`; g.fillStyle = "#f4f2ee"; g.fillText(D.head[j].t[0], tx, ty + L.pad * 0.6);
      g.font = `600 ${L.hs}px Montserrat`; g.fillStyle = "#a7abb3"; L.hl[q].forEach((ln, i) => g.fillText(ln, tx, ty + L.pad * 0.6 + L.hs * 1.12 * 1.35 + i * L.hs * 1.25));
      D.body.forEach((r, i) => { const cell = r[j]; if (!cell) return; const ry = ty + L.hh + i * L.rh, bg = cell.cls.split(" ").map((s_) => PFCOL[s_]).find(Boolean);
        if (bg) { g.fillStyle = bg; g.fillRect(cx_ + 3, ry + 3, w - 6, L.rh - 6); }
        g.font = `${q === 0 || /s3|fzb/.test(cell.cls) ? 800 : 700} ${L.fs}px Montserrat`; g.fillStyle = "#fff"; g.textAlign = al; g.fillText(cell.t[0] || "", tx, ry + L.ro + L.pad * 0.55);
        if (cell.t[1]) { g.font = `600 ${L.hs}px Montserrat`; g.fillStyle = "#b9bec7"; g.fillText(cell.t[1], tx, ry + L.ro + L.pad * 0.55 + L.fs * 1.2); } });
      cx_ += w; });
    g.strokeStyle = "#323743"; g.lineWidth = 1.5; for (let i = 1; i <= D.body.length - 1; i++) { const yy = Math.round(ty + L.hh + i * L.rh) + 0.5; g.beginPath(); g.moveTo(x + 8, yy); g.lineTo(x + avW - 8, yy); g.stroke(); }
    g.restore(); f.pfL = { fs: L.fs, cols: L.cols.length, of: D.head.length, top: ty, bot: ty + L.H, key: bot,
      x: x - 2, w: avW + 4, y0: ty + L.hh, rh: L.rh, names: D.body.map((r) => (r[0] && r[0].t[0]) || "") };   // row hit boxes (frame px) for click-to-meteogram
  } else f.pfL = null;
  window.__pfL = Object.assign(window.__pfL || {}, { [k]: f.pfL });
  // key + notes + credit (overlay layer, same shadow as the maps)
  const cnr = BR.corner && LOGOS[BR.logo] ? cornerBox(k, k === "v" ? 120 : 34, headBot, f.H - f.bot + (k === "v" ? 110 : 62)) : null, cB = cnr && (BR.cpos === "br" || BR.cpos === "bl") ? cnr : null;
  const o = ovLayer(f); o.save(); sharpShadow(o, k); const kx0 = x + (k === "h" && cB && BR.cpos === "bl" ? cB.s + 20 : 0); o.textBaseline = "middle";
  krows.forEach((row, ri) => { let bx = kx0; const by = ky0 - (krows.length - 1 - ri) * (kh + 10);
    for (const [cls, lab, w] of row) { o.font = `800 ${kfs}px Montserrat`; noShadow(o); o.fillStyle = PFCOL[cls]; o.beginPath(); o.roundRect ? o.roundRect(bx, by, w, kh, kh / 2) : o.rect(bx, by, w, kh); o.fill(); sharpShadow(o, k);
      o.fillStyle = "#fff"; o.fillText(lab, bx + kfs * 0.6, by + kh / 2 + 1); bx += w + 12; } });
  o.textBaseline = "alphabetic"; o.font = `600 ${dfs}px Montserrat`; o.fillStyle = "rgba(236,239,244,0.95)";
  if (k === "v") dl.forEach((l, i) => o.fillText(l, f.pad + (cB && BR.cpos === "bl" ? cB.s + 18 : 0), f.H - 70 - (dl.length - 1 - i) * dlh));
  else { o.textAlign = "right"; dl.forEach((l, i) => o.fillText(l, f.W - f.pad - (cB && BR.cpos === "br" ? cB.s + 20 : 0), f.H - 24 - (dl.length - 1 - i) * dlh)); o.textAlign = "left"; }
  o.restore(); ovPut(c0, f, k); if (cnr) cornerLogo(c0, cnr);
  window.__studio = (window.__studio || 0) + 1; window.__studioPass = (window.__studioPass || 0) + 1;
}
function renderMg(k, frO) {
  if (OBSM()) return renderObs(k, frO);
  if (PASSM()) return renderPass(k);
  const f = F[k], c = f.cv.getContext("2d"), fr = frO || getFr(k); f.zoom.min = "100"; f.zoom.value = Math.round((fr.zoom || 1) * 100);
  c.setTransform(1, 0, 0, 1, 0, 0); c.clearRect(0, 0, f.W, f.H); c.fillStyle = BG === "transparent" ? "#111316" : BG; c.fillRect(0, 0, f.W, f.H);
  if (!MG.img) { c.font = `700 ${k === "v" ? 40 : 34}px Montserrat`; c.fillStyle = "#c9ced8"; c.textAlign = "center"; c.fillText(MG.msg || "Loading the meteogram\u2026", f.W / 2, f.H / 2); c.textAlign = "left"; return; }
  const r = crop(k, fr); c.imageSmoothingEnabled = true; c.imageSmoothingQuality = "high";
  c.drawImage(MG.img, f.W / 2 - r.cx * r.kk, f.H / 2 - r.cy * r.kk, MG.img.naturalWidth * r.kk, MG.img.naturalHeight * r.kk);
  // the chart carries its own title, run line and ECMWF / NOAA data credit; place names: GeoNames (locked credit, 11-01 legal audit)
  { const o = ovLayer(f); o.save(); o.font = `600 ${k === "v" ? 21 : 18}px Montserrat`; o.fillStyle = "rgba(236,239,244,0.95)"; sharpShadow(o, k);
    o.textAlign = k === "v" ? "left" : "right"; o.fillText("Places: GeoNames (geonames.org), CC BY 4.0.", k === "v" ? f.pad : f.W - f.pad, f.H - (k === "v" ? 70 : 24)); o.restore(); ovPut(c, f, k); }
  const cnr = BR.corner && LOGOS[BR.logo] ? cornerBox(k, k === "v" ? 120 : 40, k === "v" ? 120 : 40, f.H - (k === "v" ? 140 : 80)) : null; if (cnr) cornerLogo(c, cnr);
  window.__studio = (window.__studio || 0) + 1; window.__studioMg = (window.__studioMg || 0) + 1;
}
async function render(k, frO) {   // frO: camera override (MP4 storm-track pan)
  ssFit(F[k], PASSM() ? PSS : 1);   // 11-04 (t2295u): Pass Forecaster draws at 2x; every other mode stays at native frame px
  if (MG.on) return renderMg(k, frO);
  if (!last) return; const f = F[k], c0 = f.cv.getContext("2d"), fr = frO || getFr(k), { cv, cur, step } = last, P = cur.P, [m] = cur.run.split("/"); let c = c0;
  if (!frO) f.zoom.value = Math.round((fr.zoom || 1) * 100);
  c.setTransform(1, 0, 0, 1, 0, 0); c.clearRect(0, 0, f.W, f.H);
  if (BG !== "transparent") { c.fillStyle = BG; c.fillRect(0, 0, f.W, f.H); }
  const r = crop(k, fr); c.imageSmoothingEnabled = true; c.imageSmoothingQuality = last.lite ? "low" : "high";   // lite: slider drag frame (RS 1 map)
  {   // only the map panel part of the source (the wide view can show past the panel's edges: background there)
    const s = f.W / r.sw, ax = Math.max(r.sx, r.px * r.rs), ay = Math.max(r.sy, r.py * r.rs), bx = Math.min(r.sx + r.sw, (r.px + r.pw) * r.rs), by = Math.min(r.sy + r.sh, (r.py + r.ph) * r.rs);
    if (bx > ax && by > ay) c.drawImage(cv, ax, ay, bx - ax, by - ay, (ax - r.sx) * s, (ay - r.sy) * s, (bx - ax) * s, (by - ay) * s); }
  // header (10-31 7:28 PM, Benjamin: "remove the shading on the top and the bottom of the studio views": no dark bands; text keeps its shadow)
  const site = m === "aensm" ? `AIFS ENS member ${S.mem}` : m === "epsm" ? `EPS member ${S.mem}` : (S.man.models[m] || {}).site || m, R_ = S.runs[cur.run], x = f.pad; let y = k === "v" ? 120 : 34;   // 11-03: member number in the pill
  c = ovLayer(f);   // header + bottom text / bars: off-screen layer, put on the frame with the soft falloff (ovPut)
  c.save(); sharpShadow(c, k); const pw = pill(c, x, y, site.toUpperCase(), Math.round(f.run * 0.95), "#2f8cff", "#fff");
  c.font = `600 ${f.run}px Montserrat`; c.fillStyle = "#c9ced8"; c.fillText(m === "oisst" ? "daily analysis" : `${cur.run.split("/")[1].slice(8)}Z run`, x + pw + 14, y + f.run * 1.08);
  y += f.run * 1.55 + f.title * 1.02;
  c.font = `800 ${f.title}px Montserrat`; c.fillStyle = "#fff";
  const words = P.title.split(" "), maxW = f.W - 2 * f.pad - (k === "h" ? 260 : BR.corner && BR.cpos === "tr" && LOGOS[BR.logo] ? Math.round(f.W * 0.10) + 24 : 0); let line = "", lines = [];   // 9:16: keep the title clear of a top-right logo
  for (const w_ of words) { const t = line ? line + " " + w_ : w_; if (c.measureText(t).width > maxW && line) { lines.push(line); line = w_; } else line = t; } lines.push(line);
  lines.forEach((t, i) => c.fillText(t, x, y + i * f.title * 1.08)); y += (lines.length - 1) * f.title * 1.08 + f.day * 1.3;
  // t2111u: the day / time line 27 % bigger (v 40 -> 51 px, h 36 -> 46 px) and extra bold, still under the title (64 / 58 px)
  c.font = `800 ${f.day}px Montserrat`; c.fillStyle = "#ffc24d"; c.fillText((step.valid_line || "").replace(/^Valid /, ""), x, y);
  const headBot = y + f.day * 0.45;
  // 11-03 small fixes: header box (pill + run, title lines, day line) kept for studioLabelHidden, so map line labels never sit under it
  { let hw = 0; c.font = `800 ${f.title}px Montserrat`; for (const t of lines) hw = Math.max(hw, c.measureText(t).width);
    c.font = `800 ${f.day}px Montserrat`; hw = Math.max(hw, c.measureText((step.valid_line || "").replace(/^Valid /, "")).width);
    c.font = `600 ${f.run}px Montserrat`; hw = Math.max(hw, pw + 14 + c.measureText("daily analysis").width);
    f.hdr = [x - 12, (k === "v" ? 120 : 34) - 12, x + hw + 16, headBot + 14]; }
  // F+ badge (top right)
  c.font = `800 ${Math.round(f.valid * 1.1)}px Montserrat`; const bt = m === "oisst" && step.badge ? step.badge[0] : `F+${step.f}`, bw = c.measureText(bt).width + 40, bx = f.W - f.pad - bw, by = k === "v" ? 120 : 34;
  c.fillStyle = "rgba(17,19,22,0.85)"; c.strokeStyle = "rgba(255,255,255,0.35)"; c.lineWidth = 2; c.beginPath(); c.roundRect ? c.roundRect(bx, by, bw, f.valid * 1.9, 14) : c.rect(bx, by, bw, f.valid * 1.9); c.fill(); noShadow(c); c.stroke(); sharpShadow(c, k);
  c.fillStyle = "#fff"; c.textAlign = "center"; c.fillText(bt, bx + bw / 2, by + f.valid * 1.32); c.textAlign = "left"; c.restore();
  f.badge = [bx - 12, by - 12, bx + bw + 12, by + f.valid * 1.9 + 12];
  const cnr = BR.corner && LOGOS[BR.logo] ? cornerBox(k, by + f.valid * 1.9, headBot, f.H - f.bot + (k === "v" ? 110 : 62)) : null;
  // bottom: color bar + credit (no dark band any more: their text gets a shadow so it stays readable on the map)
  c.save(); sharpShadow(c, k);
  // 11-02 (Benjamin t2115u "move the scale further down"): 9:16: the bar sits just above the credit line (tick numbers ~14 px clear of it;
  // the credit moves up for 3+ data lines and the bar with it); 16:9: 10 px lower (it was already at the bottom, credits are bottom right)
  const nDl = window.creditLines ? [].concat(...window.creditLines(cur.pid, cur.P, (cur.P.towns || "numbers") !== "none").map(l => (NE_KEEP.has(cur.pid) ? l : l.replace("  Basemap: Natural Earth.", "")).split("  "))).length : 0;
  const crY = f.H - 70 - Math.max(0, nDl - 2) * ((k === "v" ? 15 : 14) + 7);
  const cbW = k === "v" ? f.W - 2 * f.pad : Math.min(1100, f.W * 0.58), cbS = k === "v" ? 28 : 24, cbY = k === "v" ? Math.round(crY - 22 - 14 - 34 - cbS * 1.35) : f.H - f.bot + 72;
  if (!colorbar(c, P, f.pad, cbY, cbW, k === "v" ? 34 : 26, cbS)) {
    try { const im = await getKey(cur.pid, cur.V === VIEWS()[S.view] ? S.view : S.view); const s_ = cbW / im.naturalWidth; c.drawImage(im, f.pad, cbY - 30, cbW, im.naturalHeight * s_); } catch (e) { /* no key */ }
  }
  if (cur.maxv != null) {   // 11-01 7:43 AM (Benjamin: "when I show this on studio mode, include that somewhere on the canvas"): tallest wave in this
    // frame's crop (max of the drawn map values inside it, nearest whole ft), right-aligned above the color bar's right end
    const st = cur.st, v_ = cur.vals, X0 = Math.max(0, Math.floor(r.sx / r.rs - st.x0)), X1 = Math.min(st.W, Math.ceil((r.sx + r.sw) / r.rs - st.x0)),
      Y0 = Math.max(0, Math.floor(r.sy / r.rs - st.y0)), Y1 = Math.min(st.H, Math.ceil((r.sy + r.sh) / r.rs - st.y0));
    let mx = -Infinity; for (let yy = Y0; yy < Y1; yy++) for (let xx = X0, kq = yy * st.W + X0; xx < X1; xx++, kq++) if (v_[kq] > mx) mx = v_[kq];
    if (!(mx >= 0)) mx = cur.maxv;
    c.font = `800 ${Math.round(cbS * 1.15)}px Montserrat`; c.fillStyle = "#fff"; c.textAlign = "right";
    c.fillText(`Max height: ${Math.round(mx)} ft`, f.pad + cbW, cbY - cbS * 0.55); c.textAlign = "left";
  }
  c.font = `600 ${k === "v" ? 22 : 19}px Montserrat`; c.fillStyle = "rgba(236,239,244,0.95)";
  const credit = `${(R_.runline || "").split(" run ")[0]}  \u00b7  ${cur.V.label}`, logo = SQ.get("logo") || "";
  // 9:16: credit under the bar, logo right; 16:9: bar fills the left 58 %, so credit (and logo above it) sit bottom-right
  const cB = cnr && (BR.cpos === "br" || BR.cpos === "bl") ? cnr : null;   // the credit steps aside for a logo on its row
  if (k === "h") { let fs_ = 19; const room = f.W - 2 * f.pad - cbW - 40 - (cB && BR.cpos === "br" ? cB.s + 20 : 0);   // 11-03: long run lines (NOAA OISST) shrink to clear the color bar
    while (fs_ > 14 && c.measureText(credit).width > room) { fs_ -= 1; c.font = `600 ${fs_}px Montserrat`; } }
  if (k === "v") c.fillText(credit, f.pad + (cB && BR.cpos === "bl" ? cB.s + 18 : 0), crY); else { c.textAlign = "right"; c.fillText(credit, f.W - f.pad - (cB && BR.cpos === "br" ? cB.s + 20 : 0), f.H - 24); c.textAlign = "left"; }
  // 11-01-26 legal audit (Benjamin t2020u): data credit on every export (ECMWF: (c) year, www.ecmwf.int, CC BY 4.0, Modified; GeoNames when towns
  // show; PRISM normals on precip anomaly maps). 9:16: small lines under the credit; 16:9: right-aligned above it (logo text moves up for it)
  // 11-02 (t2112u, legibility): the locked credit sentences unchanged, but each "  "-joined sentence gets its own line (it used to shrink to
  // ~12-14 px to fit one line in 16:9), 600 weight, brighter, 17 / 16 px minimum 13, more line spacing
  const dl = window.creditLines ? [].concat(...window.creditLines(cur.pid, cur.P, (cur.P.towns || "numbers") !== "none").map(l => (NE_KEEP.has(cur.pid) ? l : l.replace("  Basemap: Natural Earth.", "")).split("  "))) : [];
  let dfs = k === "v" ? 15 : 14; c.font = `600 ${dfs}px Montserrat`; c.fillStyle = "rgba(236,239,244,0.95)";   // 11-04: smaller (was 19 / 17)
  const dMax = k === "v" ? f.W - 2 * f.pad : f.W - 2 * f.pad - cbW - 40;
  while (dfs > 11 && Math.max(0, ...dl.map(l => c.measureText(l).width)) > dMax) { dfs -= 1; c.font = `600 ${dfs}px Montserrat`; }
  const dlh = dfs + 7;
  if (k === "v") dl.forEach((l, i) => c.fillText(l, f.pad, f.H - 70 + dlh * (i + 1) - Math.max(0, dl.length - 2) * dlh));
  else { c.textAlign = "right"; dl.forEach((l, i) => c.fillText(l, f.W - f.pad, f.H - 24 - 30 - (dl.length - 1 - i) * dlh)); c.textAlign = "left"; }
  const dUp = k === "v" ? 0 : dl.length * dlh + 4;
  if (logo) { c.font = `800 ${k === "v" ? 34 : 28}px Montserrat`; c.fillStyle = "#fff"; c.textAlign = "right"; c.fillText(logo, f.W - f.pad, f.H - (k === "v" ? 70 : 60) - dUp); c.textAlign = "left"; }
  if (P.lows) lowKey(c, f, k, cbY, cbS);
  c.restore();
  c = c0; ovPut(c, f, k);
  if (cnr) cornerLogo(c, cnr);
  if (BR.lower) lowerThird(k, c);
  if (PIN.show && !REC.on) drawPins(k, c, r);
  window.__studio = (window.__studio || 0) + 1;
}
// slider drag (last.lite): only the frames on screen are redrawn per hour (the phone shows one at a time); all of them on release
const VIS = { v: true, h: true };
if ("IntersectionObserver" in window) for (const k of ["v", "h"]) new IntersectionObserver((es) => { for (const e of es) VIS[k] = e.isIntersecting; }).observe(F[k].cv);
const renderAll = () => { if (REC.on) return; if (CLEAN) render(OUTQ); else for (const k of ["v", "h"]) if (!(last && last.lite) || VIS[k]) render(k); };
window.onStudioSkip = () => { if (PLAY.on) PLAY.next(); };
// ---- 11-03 (Benjamin: "make the time scrubber on ALL models sit in exactly the same position as for ECMWF, on both 9:16 and 16:9"):
// the frames and the hour scrubber are laid out under the top menu bar, whose height and wrapping changed with the model (number of
// product tabs, Product / View menu widths, the AIFS ENS Member box, slider wrapping). The bar's parts now take the same space on
// every model: tabs reserve the full ECMWF tab set, the Product / View / Runs menus are as wide as their longest entry on any model,
// the Member box keeps its slot (hidden), and the hour readout next to the scrubber has a fixed width. Same bar -> same frames ->
// same scrubber, px for px.
// 11-03 (Benjamin t2184u "keep natural earth credit"): the NOAA ocean maps keep the "Basemap: Natural Earth." line on the Studio frames
const NE_KEEP = new Set(["ssta", "ssha"]);
let barPinned = "";
function pinBar() {
  if (CLEAN || !S.man) return; const bar = document.getElementById("bar"); if (!bar) return;
  const mlh = (document.getElementById("memlab") || {}).hidden, key = innerWidth + ":" + mlh + ":" + Object.keys(S.man.models).join(",") + ":" + Object.values(S.man.runs).map(r => r.length).join(","); if (key === barPinned) return; barPinned = key;
  const tabs = document.getElementById("tabs"), probe = (el, html) => { const c = el.cloneNode(false); c.removeAttribute("id"); c.style.cssText = "position:absolute;visibility:hidden;left:-9999px;top:0;width:auto;min-width:0"; c.innerHTML = html; el.parentNode.appendChild(c); const w = c.getBoundingClientRect().width; c.remove(); return w; };
  const ml = document.getElementById("memlab"), phone = innerWidth <= 820;
  if (ml) ml.classList.toggle("keep", phone);   // phones: the Member box keeps its slot (its own bar row); desktop: it floats in the tab space (placeMem)
  if (tabs && typeof TABS !== "undefined") {   // desktop: the full ECMWF tab set's width, less the Member box when it shows (AIFS ENS members)
    const keepH = tabs.innerHTML, keepW = tabs.style.minWidth; tabs.style.minWidth = "0px";   // measured in the real #tabs (its own button style), put back at once
    tabs.innerHTML = [...TABS.map(t => t[1]), "Other"].map(l => `<button type="button">${l}</button>`).join(""); const w7 = Math.ceil(tabs.getBoundingClientRect().width); tabs.innerHTML = keepH; tabs.style.minWidth = keepW;
    const gap = parseFloat(getComputedStyle(bar).columnGap) || 10;
    void gap; tabs.style.minWidth = phone ? "" : w7 + "px"; }
  const opts = a => [...new Set(a)].map(t => `<option>${t}</option>`).join("");
  const titles = [], views = []; for (const md of Object.values(S.man.models)) { try { for (const p of Object.values(allProds(md))) if (p && p.title) titles.push(p.title); } catch (e) { /* no products */ } for (const v of Object.values(md.views || {})) if (v && v.label) views.push(v.label); }
  const pin = (id, list, cap) => { const el = document.getElementById(id); if (el && list.length) el.style.width = Math.min(cap, Math.ceil(probe(el, opts(list)))) + "px"; };
  pin("prod", titles, 250); pin("view", views, 270);   // longest entry on any model (long names end in "..." in the closed menu)
  const run = document.getElementById("run"); if (run) pin("run", [...run.options].map(o => o.textContent).concat(["ECMWF AIFS ENS 0.25\u00b0 00Z 11-03 (loading, to F+360)"]), 300);
}
if (document.fonts && document.fonts.ready) document.fonts.ready.then(() => { barPinned = ""; try { pinBar(); } catch (e) { /* not ready */ } });   // widths measured with the real fonts
// desktop: the AIFS ENS Member box floats at the right end of the tab space (AIFS ENS members have 2 tabs; the space is reserved for 7)
function placeMem() {
  const ml = document.getElementById("memlab"), tabs = document.getElementById("tabs"); if (!ml || !tabs) return;
  if (CLEAN || innerWidth <= 820 || ml.hidden) { ml.style.position = ml.style.left = ml.style.top = ""; return; }
  ml.style.position = "absolute"; const w = ml.getBoundingClientRect().width, h = ml.getBoundingClientRect().height;
  ml.style.left = (tabs.offsetLeft + tabs.offsetWidth - w) + "px"; ml.style.top = (tabs.offsetTop + (tabs.offsetHeight - h) / 2) + "px";
}
addEventListener("resize", () => requestAnimationFrame(placeMem));
window.onStudioDraw = (cv, cur, step, lite) => { try { pinBar(); placeMem(); } catch (e) { /* bar not ready */ } const first_ = !last; last = { cv, cur, step, lite: !!lite }; if (first_ && !CLEAN) setTimeout(() => { try { fitFrames(); } catch (e) { /* layout not ready */ } }, 300); /* 11-04: remember the Map layout once the map is up */ renderAll(); try { scrubSync(); } catch (e) { /* scrubber not built */ } if (lite) return; if (PLAY.on) PLAY.next(); if (!REC.on && typeof mpSync === "function") try { mpSync(); } catch (e) { /* panel not ready */ } };
// drag / keys / zoom / buttons
for (const k of ["v", "h"]) {
  const f = F[k], cv = f.cv; let d = null;
  // 10-31 5:12 PM (Benjamin: "drag point a and b for the storm across the map either with my finger, or with my cursor"):
  // grabbing a shown pin drags it (live), anywhere else drags the frame as before
  cv.addEventListener("pointerdown", (e) => { if (CLEAN || !last || REC.on) return; if (PIN.mode) { placePin(k, cv, e); return; }
    const hit = pinHit(k, cv, e); if (hit) { e.preventDefault(); cv.setPointerCapture(e.pointerId); PD = { k, n: hit, id: e.pointerId, off: pinOff(k, cv, e, hit) }; cv.classList.add("pindrag"); return; }
    if (e.pointerType === "touch" && (S.dragging || !e.isPrimary)) return;   // 11-03: a second finger, or a finger while the scrubber is held: no frame drag
    cv.setPointerCapture(e.pointerId); cv.focus({ preventScroll: true }); cv.classList.add("drag"); d = { x: e.clientX, y: e.clientY, fr: getFr(k), id: e.pointerId }; });
  if (MG.on) cv.addEventListener("pointerdown", (e) => { if (!CLEAN && !last && MG.img) { cv.setPointerCapture(e.pointerId); cv.focus(); cv.classList.add("drag"); d = { x: e.clientX, y: e.clientY, fr: getFr(k) }; } });
  cv.addEventListener("pointermove", (e) => { if (PD && PD.k === k && PD.id === e.pointerId) { pinMove(k, cv, e); return; }
    if (!d && !PD && PIN.show && !PIN.mode && e.pointerType === "mouse") cv.style.cursor = pinHit(k, cv, e) ? "grab" : "";
    if (!d || pz || (d.id !== undefined && e.pointerId !== d.id)) return; const s = f.W / cv.clientWidth, fr = getFr(k);
    fr.dx = d.fr.dx + (e.clientX - d.x) * s; fr.dy = d.fr.dy + (e.clientY - d.y) * s;
    if (OBSM()) { obsPan(k, fr); d.x = e.clientX; d.y = e.clientY; d.fr = Object.assign({}, fr); setFr(k, fr); render(k); return; }   // 11-04: free pan
    const r = crop(k, fr);   // keep the stored offset inside the panel
    fr.dx = (r.bx - r.cx) * r.kk; fr.dy = (r.by - r.cy) * r.kk; setFr(k, fr); render(k); });
  const up = (e) => { if (PD && PD.k === k) { PD = null; cv.classList.remove("pindrag"); mpInfo(); renderAll(); } d = null; cv.classList.remove("drag"); }; cv.addEventListener("pointerup", up); cv.addEventListener("pointercancel", up); cv.addEventListener("lostpointercapture", (e) => { if (d && e.pointerId === d.id) up(e); });
  // 10-31 1:39 PM (Benjamin, iPhone): two-finger pinch zooms the frame (1-2.5x) about the fingers' midpoint; moving both fingers pans
  let pz = null;
  const oxy = (t) => { const b = cv.getBoundingClientRect(); return [(t.clientX - b.left) * f.W / b.width, (t.clientY - b.top) * f.H / b.height]; };
  cv.addEventListener("touchstart", (e) => {
    if (PD) { e.preventDefault(); return; }   // dragging a pin: no pinch / page scroll
    // 11-03 (Benjamin t2186u/t2187u "the zoom changes when I click on the hours scrubber"): the pinch counted every finger on the
    // screen (e.touches), so a finger on the hour scrubber (or the other frame, a button, ...) plus one resting on this frame was taken
    // as a pinch and zoomed the frame as the scrubber finger moved. Only a real two-finger pinch on this frame zooms it now
    // (targetTouches = fingers that started on this canvas, and no other finger on the screen).
    if (CLEAN || !last || REC.on || PIN.mode || e.targetTouches.length !== 2 || e.touches.length !== 2) { if (pz && e.targetTouches.length !== 2) pz = null; return; }
    e.preventDefault(); d = null;
    const [a, b] = [oxy(e.targetTouches[0]), oxy(e.targetTouches[1])], fr0 = getFr(k), r0 = crop(k, fr0), ox = (a[0] + b[0]) / 2, oy = (a[1] + b[1]) / 2;
    pz = { d: Math.max(10, Math.hypot(a[0] - b[0], a[1] - b[1])), z: OBSM() ? obsZv(fr0) / 100 : Math.max(1, fr0.zoom || 1), mx: r0.cx + (ox - f.W / 2) / r0.kk, my: r0.cy + (oy - f.H / 2) / r0.kk };
  }, { passive: false });
  cv.addEventListener("touchmove", (e) => {
    if (PD) { e.preventDefault(); return; }
    if (!pz) return; e.preventDefault(); if (e.targetTouches.length !== 2 || e.touches.length !== 2) return;   // a finger elsewhere (scrubber, other frame, a third one): hold the zoom
    const [a, b] = [oxy(e.targetTouches[0]), oxy(e.targetTouches[1])], ox = (a[0] + b[0]) / 2, oy = (a[1] + b[1]) / 2;
    if (OBSM()) { const zo = Math.min(2.5, Math.max(0.05, pz.z * Math.max(10, Math.hypot(a[0] - b[0], a[1] - b[1])) / pz.d)), fo = obsZoom(k, getFr(k), zo); setFr(k, fo); render(k); window.__spinch = { k, zoom: zo }; return; }   // 11-04: zoom out past 1x
    const z = Math.min(2.5, Math.max(1, pz.z * Math.max(10, Math.hypot(a[0] - b[0], a[1] - b[1])) / pz.d)), kk = base(k).k0 * z;
    const fr = frAt(k, pz.mx - (ox - f.W / 2) / kk, pz.my - (oy - f.H / 2) / kk, z), r = crop(k, fr);   // map point under the fingers stays under them
    fr.dx = (r.bx - r.cx) * r.kk; fr.dy = (r.by - r.cy) * r.kk; setFr(k, fr); render(k); window.__spinch = { k, zoom: z };
  }, { passive: false });
  const pend = (e) => { if (pz && e.targetTouches.length < 2) pz = null; };
  cv.addEventListener("touchend", pend); cv.addEventListener("touchcancel", pend);
  cv.addEventListener("keydown", (e) => {
    const fr = getFr(k), st = e.shiftKey ? 10 : 1; let hit = true;
    if (OBSM() && ["+", "=", "-"].includes(e.key)) { obsZoom(k, fr, obsZv(fr) / 100 + (e.key === "-" ? -0.01 : 0.01)); e.preventDefault(); e.stopPropagation(); setFr(k, fr); render(k); return; }
    if (e.key === "ArrowLeft") fr.dx -= st; else if (e.key === "ArrowRight") fr.dx += st; else if (e.key === "ArrowUp") fr.dy -= st; else if (e.key === "ArrowDown") fr.dy += st;
    else if (e.key === "+" || e.key === "=") fr.zoom = Math.min(2.5, (fr.zoom || 1) + 0.01); else if (e.key === "-") fr.zoom = Math.max(1, (fr.zoom || 1) - 0.01);
    else if (e.key === "0") { fr.dx = fr.dy = 0; fr.zoom = 1; } else hit = false;
    if (hit && OBSM() && e.key.startsWith("Arrow")) obsPan(k, fr);
    if (hit) { e.preventDefault(); e.stopPropagation(); setFr(k, fr); render(k); }
  }, true);
  f.zoom.oninput = () => { const fr = getFr(k); if (OBSM()) obsZoom(k, fr, f.zoom.value / 100); else fr.zoom = Math.max(1, f.zoom.value / 100); setFr(k, fr); render(k); };
  cv.parentNode.querySelector(".shd").addEventListener("click", async (e) => {
    const a = e.target.closest("button[data-a]"); if (!a || !last) return;
    if (a.dataset.a === "reset") { if (OBSM() && typeof Obs !== "undefined" && Obs._state && OZ.sub < 1) { ozSync(); Obs._state.k = OZ.ref; OZ.sub = 1; Obs.redraw(); } setFr(k, { dx: 0, dy: 0, zoom: 1 }); render(k); }
    if (a.dataset.a === "mp4" && (!MG.on || OBSM())) openMp4(k);
    if (a.dataset.a === "png" && OBSM()) { if (!MG.img) return; const I = obsInfo(), st = I && I.t ? new Intl.DateTimeFormat("en-CA", { timeZone: "America/Los_Angeles", year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", hourCycle: "h23" }).format(I.t).replace(/[^0-9]/g, "") : "now";
      const nm = `obs_${I ? I.view : "pnw"}_${I ? I.on.map((l) => l[0]).join("-") : "plot"}_${st}_${k === "v" ? "1080x1920" : "1920x1080"}.png`;
      cv.toBlob((b) => { const u = URL.createObjectURL(b), l = document.createElement("a"); l.href = u; l.download = nm; l.click(); setTimeout(() => URL.revokeObjectURL(u), 4000); }, "image/png"); return; }
    if (a.dataset.a === "png" && PASSM()) { if (!PF.rows) return; const nm = `pass-forecast_${PF.run.replace("/", "_")}Z_${k === "v" ? "2160x3840" : "3840x2160"}.png`;
      cv.toBlob((b) => { const u = URL.createObjectURL(b), l = document.createElement("a"); l.href = u; l.download = nm; l.click(); setTimeout(() => URL.revokeObjectURL(u), 4000); }, "image/png"); return; }
    if (a.dataset.a === "png" && MG.on) { if (!MG.img) return; const nm = `meteogram_${(MG.src.split("#")[1] || "").replace(/[^a-z0-9=&_-]/gi, "").replace(/[=&]/g, "_")}_${k === "v" ? "1080x1920" : "1920x1080"}.png`;
      cv.toBlob((b) => { const u = URL.createObjectURL(b), l = document.createElement("a"); l.href = u; l.download = nm; l.click(); setTimeout(() => URL.revokeObjectURL(u), 4000); }, "image/png"); return; }
    if (MG.on && a.dataset.a !== "reset") return;   // MP4 / OBS: maps only
    if (a.dataset.a === "png") { const st = last.step, nm = `${last.cur.run.replace("/", "_")}_${last.cur.pid}_${S.view}_f${String(st.f).padStart(3, "0")}_${k === "v" ? "1080x1920" : "1920x1080"}.png`;
      cv.toBlob((b) => { const u = URL.createObjectURL(b), l = document.createElement("a"); l.href = u; l.download = nm; l.click(); setTimeout(() => URL.revokeObjectURL(u), 4000); }, "image/png"); }
    if (a.dataset.a === "obs") { const fr = getFr(k), [m] = last.cur.run.split("/"), u = new URL("studio.html", location.href);
      u.search = new URLSearchParams({ clean: "1", out: k, model: m, prod: last.cur.pid, view: S.view, f: String(last.step.f), dx: fr.dx.toFixed(1), dy: fr.dy.toFixed(1), zoom: (fr.zoom || 1).toFixed(2), play: "1", dwell: "700", loop: "1" }).toString();
      try { await navigator.clipboard.writeText(u.toString()); a.textContent = "Copied"; } catch (err) { prompt("OBS Browser Source URL", u.toString()); }
      setTimeout(() => { a.textContent = "Copy OBS URL"; }, 1500); }
  });
}
// ---- MP4 loops (10-31, Benjamin 12:43 PM: "save mp4 loops of runs ... choose when the beginning of the saved loop starts, and
// when it ends" + "start this loop here at this pin, then finish the saved loop when you pan smoothly to this pin").
// Frames are drawn exactly like the Studio frames, one map per forecast hour, and encoded in the browser: WebCodecs H.264 +
// mp4-muxer (vendor/, MIT) at a constant 30 fps (each map is held for 30/speed frames). Browsers without WebCodecs fall back to
// MediaRecorder on the frame canvas (real time; MP4 where the browser offers it, otherwise WebM). Track mode: pins A and B are
// stored in map coordinates per view; the camera starts on A and eases (smoothstep) to B over the loop while the hours advance.
const REC = { on: false, cancel: false }, PIN = { mode: null, show: false }, FPS = 30;
const TRK = { list: [], sel: -1, run: null, view: null };   // storm finder tracks (see findStorms)
const $s = (id) => document.getElementById(id), sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const lerp = (a, b, t) => a + (b - a) * t, ease = (t) => t * t * (3 - 2 * t);
const pinKey = () => `studio:pins:${OBSM() ? "obs:" + ((typeof Obs !== "undefined" && Obs._state.view) || "pnw") : S.view}`;   // obs: per region (pins are obs-map px)
const getPins = () => { try { return JSON.parse(localStorage.getItem(pinKey()) || "{}"); } catch (e) { return {}; } };
const setPins = (p) => { try { localStorage.setItem(pinKey(), JSON.stringify(p)); } catch (e) { /* private mode */ } };
function frAt(k, x, y, zoom) {   // camera centred on map point (x, y) at this zoom, as a {dx, dy, zoom} framing
  const B = base(k), kk = B.k0 * zoom;
  return { dx: (B.cx - x) * kk, dy: (B.cy - y) * kk, zoom };
}
function drawPins(k, c, r) {
  const p = getPins(), f = F[k], pos = (q) => [f.W / 2 + (q.x - r.cx) * r.kk, f.H / 2 + (q.y - r.cy) * r.kk], R = k === "v" ? 30 : 26;
  const T = TRK.sel >= 0 && TRK.run === S.run && TRK.view === S.view ? TRK.list[TRK.sel] : null;
  if (T) {   // the found storm's track: dotted line + a dot per hour, landfall ringed (not in the video)
    c.strokeStyle = "rgba(255,214,90,0.95)"; c.lineWidth = 4; c.setLineDash([3, 9]); c.beginPath();
    T.pts.forEach((q, i) => { const [x, y] = pos(q); if (i) c.lineTo(x, y); else c.moveTo(x, y); }); c.stroke(); c.setLineDash([]);
    for (const q of T.pts) { const [x, y] = pos(q); c.fillStyle = "#ffd65a"; c.beginPath(); c.arc(x, y, 6, 0, 7); c.fill(); }
    if (T.landfall) { const [x, y] = pos(T.landfall); c.strokeStyle = "#ffd65a"; c.lineWidth = 5; c.beginPath(); c.arc(x, y, R + 14, 0, 7); c.stroke(); }
  }
  if (p.a && p.b) { const [x0, y0] = pos(p.a), [x1, y1] = pos(p.b); c.setLineDash([18, 12]); c.strokeStyle = "rgba(255,255,255,0.9)"; c.lineWidth = 5;
    c.beginPath(); c.moveTo(x0, y0); c.lineTo(x1, y1); c.stroke(); c.setLineDash([]); }
  for (const [n, col] of [["a", "#16a34a"], ["b", "#dc2626"]]) {
    if (!p[n]) continue; const [x, y] = pos(p[n]);
    const big = PD && PD.k === k && PD.n === n ? 1.15 : 1;   // the pin being dragged grows a little
    c.strokeStyle = "rgba(0,0,0,0.55)"; c.lineWidth = 11; c.beginPath(); c.arc(x, y, R * big, 0, 7); c.stroke();   // dark outer ring: readable on any map
    c.fillStyle = col; c.strokeStyle = "#fff"; c.lineWidth = 5; c.beginPath(); c.arc(x, y, R * big, 0, 7); c.fill(); c.stroke();
    c.fillStyle = "#fff"; c.font = `800 ${R}px Montserrat`; c.textAlign = "center"; c.textBaseline = "middle"; c.fillText(n.toUpperCase(), x, y + 2);
    c.textAlign = "left"; c.textBaseline = "alphabetic";
  }
  const hp = p.a || p.b;   // "Drag A or B to move" pill under pin A (above it near the bottom edge); not in videos (pins aren't drawn while recording)
  if (hp && !PIN.mode) { const [x, y] = pos(hp), fs = k === "v" ? 26 : 22, t = PD ? `Moving ${PD.n.toUpperCase()}` : "Drag A or B to move"; c.font = `700 ${fs}px Montserrat`;
    const w = c.measureText(t).width + 24, h = fs + 16, bx = Math.min(f.W - w - 8, Math.max(8, x - w / 2)), by = y + R + 18 + h > f.H - 8 ? y - R - 18 - h : y + R + 18;
    c.fillStyle = "rgba(17,19,22,0.82)"; c.beginPath(); c.roundRect ? c.roundRect(bx, by, w, h, h / 2) : c.rect(bx, by, w, h); c.fill();
    c.fillStyle = "#fff"; c.textBaseline = "middle"; c.fillText(t, bx + 12, by + h / 2 + 1); c.textBaseline = "alphabetic"; }
}
function placePin(k, cv, e) {
  const f = F[k], b = cv.getBoundingClientRect(), ox = (e.clientX - b.left) * f.W / b.width, oy = (e.clientY - b.top) * f.H / b.height, r = crop(k, getFr(k));
  const p = getPins(); p[PIN.mode] = { x: r.cx + (ox - f.W / 2) / r.kk, y: r.cy + (oy - f.H / 2) / r.kk }; setPins(p);
  // pin A placed and no pin B yet: go straight on to pin B (one less tap); Esc stops
  if (PIN.mode === "a" && !p.b) { PIN.mode = "b"; $s("pinhint").textContent = "Pin A set. Now tap where the loop should END (pin B). Esc cancels."; render("v"); render("h"); return; }
  PIN.mode = null; $s("pinhint").hidden = true; $s("mp4p").hidden = false; mpInfo(); render("v"); render("h");
}
// pin drag: hit area = the pin + a margin, at least a 44 px (CSS) touch target; the pin follows the pointer in map coordinates
// (stored per view exactly like a tapped pin), so presets / storm finder / links / batch keep working with the dragged spot.
let PD = null;
const evXY = (k, cv, e) => { const f = F[k], b = cv.getBoundingClientRect(); return [(e.clientX - b.left) * f.W / b.width, (e.clientY - b.top) * f.H / b.height, f.W / b.width]; };
function pinHit(k, cv, e) {
  if (!PIN.show || !last) return null; const p = getPins(); if (!p.a && !p.b) return null;
  const f = F[k], r = crop(k, getFr(k)), [ox, oy, sc] = evXY(k, cv, e), R = (k === "v" ? 30 : 26) + 12, hitR = Math.max(R, 22 * sc + (e.pointerType === "touch" ? 6 * sc : 0));
  let best = null, bd = Infinity;
  for (const n of ["b", "a"]) { if (!p[n]) continue; const dd = Math.hypot(f.W / 2 + (p[n].x - r.cx) * r.kk - ox, f.H / 2 + (p[n].y - r.cy) * r.kk - oy); if (dd <= hitR && dd < bd) { bd = dd; best = n; } }
  return best;
}
function pinOff(k, cv, e, n) {   // grab offset (frame px) so the pin doesn't jump to the finger / cursor
  const f = F[k], r = crop(k, getFr(k)), [ox, oy] = evXY(k, cv, e), q = getPins()[n];
  return [f.W / 2 + (q.x - r.cx) * r.kk - ox, f.H / 2 + (q.y - r.cy) * r.kk - oy];
}
function pinMove(k, cv, e) {
  const f = F[k], r = crop(k, getFr(k)), [ex, ey] = evXY(k, cv, e), ox = ex + PD.off[0], oy = ey + PD.off[1], x = Math.min(f.W, Math.max(0, ox)), y = Math.min(f.H, Math.max(0, oy));
  const p = getPins(); p[PD.n] = { x: r.cx + (x - f.W / 2) / r.kk, y: r.cy + (y - f.H / 2) / r.kk }; setPins(p);
  render(k); const t = $s("mppins"); if (t) t.textContent = `Moving pin ${PD.n.toUpperCase()}…`; window.__pinDrag = { k, n: PD.n, x: p[PD.n].x, y: p[PD.n].y };
}
// ---- usability (10-31 2:24 PM, Benjamin: "I want the studio to be as intuitive and functional as possible")
// remembered loop settings (not the frame: the Save MP4 button you press picks that), presets, a camera-move preview, progress bar,
// Enter / Esc keys, a draggable panel on desktop
const OPT_IDS = ["mpmode", "mpe", "mph", "mps", "mps1", "mpz0", "mpz1"], OPT_KEY = "studio:mp4opts";
function saveOpts() { const o = {}; for (const id of OPT_IDS) o[id] = $s(id).value; try { localStorage.setItem(OPT_KEY, JSON.stringify(o)); } catch (e) { /* private mode */ } }
function loadOpts() { let o = {}; try { o = JSON.parse(localStorage.getItem(OPT_KEY) || "{}"); } catch (e) { /* none */ }
  for (const id of OPT_IDS) if (o[id] !== undefined && [...($s(id).options || [])].concat($s(id).type === "range" ? [{ value: o[id] }] : []).some((x) => x.value === o[id])) $s(id).value = o[id]; }
const PRESETS = {
  landfall: { mpmode: "pan", mpe: "6", mps: "3", mps1: "1", mph: "2", mpz0: "1.2", mpz1: "2.2" },
  overview: { mpmode: "loop", mpe: "6", mps: "6", mps1: "", mph: "1", mpz0: "f", mpz1: "f", span: 120 },
  smooth: { mpmode: "loop", mpe: "0", mps: "10", mps1: "", mph: "1", mpz0: "f", mpz1: "f" },
  zoomin: { mpmode: "loop", mpe: "6", mps: "3", mps1: "", mph: "1.5", mpz0: "1", mpz1: "1.8" },
};
function applyPreset(name) {
  const P_ = PRESETS[name]; if (!P_) return;
  for (const [id, v] of Object.entries(P_)) if (id !== "span") $s(id).value = v;
  if (P_.span) { const st = S.runs[S.run].steps, a = +$s("mpa").value, e = st.findIndex((x) => x.f >= st[a].f + P_.span); $s("mpb").value = String(e > a ? e : st.length - 1); }
  mpMode(); saveOpts(); $s("mppre").value = name;
  const p = getPins();
  if (P_.mpmode === "pan" && !(p.a && p.b)) { PIN.mode = "a"; PIN.show = true; $s("mp4p").hidden = true; const h = $s("pinhint"); h.hidden = false;
    h.textContent = "Landfall zoom-in: tap where the storm is at the START (pin A), then where it makes landfall (pin B). Esc cancels."; render("v"); render("h");
    if (innerWidth <= 820) F[$s("mpk").value].cv.scrollIntoView({ block: "center", behavior: "smooth" }); }
}
const PV = { on: false };
async function previewMove() {
  if (PV.on || REC.on || !last) return; const k = $s("mpk").value, pan = $s("mpmode").value === "pan", pins = getPins();
  if (pan && !(pins.a && pins.b)) { mpSt("Set pin A and pin B first (Set pin A, then tap the frame)."); return; }
  const fr0 = getFr(k), z0 = $s("mpz0").value === "f" ? Math.max(1, fr0.zoom || 1) : +$s("mpz0").value, z1 = $s("mpz1").value === "f" ? z0 : +$s("mpz1").value, c0 = crop(k, fr0);
  PV.on = true; mpSt("Previewing the camera move…"); F[k].cv.scrollIntoView({ block: "nearest" });
  const N = 75;
  for (let n = 0; n <= N; n++) { const tt = n / N, z = z0 * Math.pow(z1 / z0, ease(tt)), t = ease(tt);
    await render(k, pan ? frAt(k, lerp(pins.a.x, pins.b.x, t), lerp(pins.a.y, pins.b.y, t), z) : frAt(k, c0.cx, c0.cy, z)); await sleep(1000 / FPS); }
  await sleep(500); PV.on = false; render(k); mpSt("");
}
const lbl = (st) => { const d = new Date(st.valid); return `F+${st.f} \u00b7 ${d.toUTCString().slice(0, 3)} ${String(d.getUTCMonth() + 1).padStart(2, "0")}-${String(d.getUTCDate()).padStart(2, "0")} ${String(d.getUTCHours()).padStart(2, "0")}Z`; };
function startPin(m_) { PIN.mode = m_; PIN.show = true; $s("mp4p").hidden = true; const h = $s("pinhint"); h.hidden = false;
  h.textContent = `Tap either frame where the loop should ${m_ === "a" ? "START (pin A)" : "END (pin B)"}. Drag the frame first if you need to. Esc cancels.`; render("v"); render("h");
  if (innerWidth <= 820) F[$s("mpk").value].cv.scrollIntoView({ block: "center", behavior: "smooth" }); }   // phone: bring the frame to the thumb
function openMp4(k) {
  if (!last) return; const st = S.runs[S.run].steps, a = $s("mpa"), b = $s("mpb");
  const opts = st.map((x, i) => `<option value="${i}">${lbl(x)}</option>`).join(""); a.innerHTML = opts; b.innerHTML = opts;
  const e5 = st.findIndex((x) => x.f >= st[S.i].f + 120);   // default: the next 5 days (or to the end of the run)
  a.value = String(S.i); b.value = String(e5 > S.i ? e5 : st.length - 1);
  loadOpts(); $s("mpk").value = k; $s("mp4p").hidden = false; $s("mpout").hidden = true; mpMode(); mpInfo();
}
function pickIdx() {
  const st = S.runs[S.run].steps, a = +$s("mpa").value, b = +$s("mpb").value, e = +$s("mpe").value, out = [];
  for (let i = a; i <= b; i++) if (!out.length || !e || st[i].f - st[out[out.length - 1]].f >= e) out.push(i);
  return out;
}
// 10-31 1:51 PM (Benjamin: "an option to change mp4 loop speed"): Speed slider 0.5-15 maps/s; optional End speed ramps the speed
// map by map (e.g. slow down into landfall). T[j] = time (s) at which map j starts.
function loopTimes(n) {
  const s0 = +$s("mps").value, s1 = $s("mps1").value ? +$s("mps1").value : s0, T = [0];
  for (let j = 0; j < n; j++) T.push(T[j] + 1 / lerp(s0, s1, n > 1 ? j / (n - 1) : 0));
  return T;
}
// ("when choosing the loop, I want to be able to still manipulate where I am in the model run"): the panel is not modal; the
// hour slider / buttons / arrow keys / Play keep working, "Start = now" / "End = now" take the hour on the map, and the loop
// range is shaded on the hour slider.
function mpSync() {
  if ($s("mp4p").hidden || !S.run) return; const st = S.runs[S.run].steps, sl = $("step"), mx = Math.max(1, +sl.max || st.length - 1);
  if (+$s("mpa").options.length !== st.length) return;   // run changed: options rebuilt on next open
  $s("mpnow").textContent = `Map now: ${lbl(st[S.i])}`;
  const a = +$s("mpa").value, b = +$s("mpb").value; sl.style.setProperty("--ra", String(Math.min(a, b) / mx)); sl.style.setProperty("--rb", String(Math.max(a, b) / mx));
  document.body.classList.add("mprange");
}
function mpInfo() {
  if (OBSM()) { const p = getPins(), pan = $s("mpmode").value === "pan", d = +($s("mpdur").value || 6), h = +$s("mph").value;
    $s("mpinfo").textContent = `Live observations: one map, ${d} s camera move + ${h} s hold = ${d + h} s at 30 fps` + (pan ? (p.a && p.b ? " \u00b7 pans A \u2192 B" : " \u00b7 set pins A and B") : "");
    const t = $s("mppins"); if (t) t.textContent = p.a && p.b ? "A and B set" : p.a ? "A set" : ""; return; }
  mpSync(); const s0 = +$s("mps").value, s1 = $s("mps1").value; $s("mpsv").textContent = `${s0} map${s0 === 1 ? "" : "s"}/s`;
  const idx = pickIdx(), T = loopTimes(idx.length), hold = +$s("mph").value, p = getPins(), pan = $s("mpmode").value === "pan";
  const zv = (id) => $s(id).value === "f" ? null : +$s(id).value, za = zv("mpz0"), zb = zv("mpz1");
  const zt = za === null && zb === null ? "" : ` \u00b7 zoom ${za === null ? "as framed" : za + "\u00d7"} \u2192 ${zb === null ? (za === null ? "as framed" : za + "\u00d7") : zb + "\u00d7"}`;
  $s("mppins").textContent = pan ? (p.a ? "A set" : "A not set") + " \u00b7 " + (p.b ? "B set" : "B not set") : "";
  $s("mpinfo").textContent = idx.length < 2 ? "Pick an end hour after the start hour." :
    `${idx.length} maps, F+${S.runs[S.run].steps[idx[0]].f} to F+${S.runs[S.run].steps[idx[idx.length - 1]].f} \u00b7 ${(T[idx.length] + hold).toFixed(1)} s of video at 30 fps${s1 && +s1 !== s0 ? ` (speed ${s0} \u2192 ${s1} maps/s)` : ""}${zt}`;
}
function mpMode() { const pan = $s("mpmode").value === "pan"; if (pan && $s("mpz0").value === "f") $s("mpz0").value = "1.8"; /* a pan needs room to move */ $s("mppan").hidden = !pan; PIN.show = pan; render("v"); render("h"); mpInfo(); }
let muxP = null;
const loadMuxer = () => muxP || (muxP = new Promise((res, rej) => { const sc = document.createElement("script"); sc.src = "vendor/mp4-muxer.js?v=522"; sc.onload = res; sc.onerror = () => { muxP = null; rej(new Error("could not load the MP4 writer")); }; document.head.appendChild(sc); }));
async function makeEncoder(cv, W, H) {
  if (window.VideoEncoder && window.VideoFrame) {
    for (const codec of ["avc1.640028", "avc1.4d0028", "avc1.42002a"]) {   // H.264 High / Main / Baseline, level 4.x (1080x1920 @ 30)
      const cfg = { codec, width: W, height: H, bitrate: 10e6, framerate: FPS, avc: { format: "avc" } };
      let ok = false; try { ok = (await VideoEncoder.isConfigSupported(cfg)).supported; } catch (e) { /* next */ }
      if (!ok) continue;
      await loadMuxer();
      const mux = new Mp4Muxer.Muxer({ target: new Mp4Muxer.ArrayBufferTarget(), video: { codec: "avc", width: W, height: H, frameRate: FPS }, fastStart: "in-memory" });
      let err = null; const ve = new VideoEncoder({ output: (ch, meta) => mux.addVideoChunk(ch, meta), error: (e) => { err = e; } });
      ve.configure(cfg);
      return { how: `H.264 (${codec}) via WebCodecs`, ext: "mp4",
        async add(n) { if (err) throw err; while (ve.encodeQueueSize > 4) await sleep(4);
          const vf = new VideoFrame(cv, { timestamp: Math.round(n * 1e6 / FPS), duration: Math.round(1e6 / FPS) }); ve.encode(vf, { keyFrame: n % (2 * FPS) === 0 }); vf.close(); },
        async done() { await ve.flush(); if (err) throw err; ve.close(); mux.finalize(); return new Blob([mux.target.buffer], { type: "video/mp4" }); },
        abort() { try { ve.close(); } catch (e) { /* closed */ } } };
    }
  }
  if (!cv.captureStream || !window.MediaRecorder) throw new Error("this browser can't make videos (no WebCodecs or MediaRecorder)");
  const type = ["video/mp4;codecs=avc1", "video/mp4", "video/webm;codecs=vp9", "video/webm"].find((t) => MediaRecorder.isTypeSupported(t)) || "";
  const stream = cv.captureStream(0), tr = stream.getVideoTracks()[0], rec = new MediaRecorder(stream, type ? { mimeType: type, videoBitsPerSecond: 10e6 } : {}), parts = [];
  rec.ondataavailable = (e) => { if (e.data && e.data.size) parts.push(e.data); }; rec.start(); rec.pause();
  return { how: `MediaRecorder (${type || "default"}, real time)`, ext: (rec.mimeType || type).includes("mp4") ? "mp4" : "webm",
    // recording runs in real time while frames are shown; it is paused while the next hour loads (idle), so load time is not in the video
    seg: null, realtime: true,
    async add() { if (!this.seg) { rec.resume(); this.seg = { t: performance.now(), n: 0 }; } if (tr.requestFrame) tr.requestFrame();
      this.seg.n++; const due = this.seg.t + this.seg.n * 1000 / FPS - performance.now(); if (due > 0) await sleep(due); },
    idle() { if (this.seg) { rec.pause(); this.seg = null; } },
    async done() { if (tr.requestFrame) tr.requestFrame(); await sleep(1000 / FPS); return new Promise((res) => { rec.onstop = () => res(new Blob(parts, { type: rec.mimeType || type })); if (rec.state === "paused") rec.resume(); rec.stop(); }); },
    abort() { try { rec.stop(); } catch (e) { /* stopped */ } } };
}
const mpSt = (t) => { $s("mpst").textContent = t; };
async function makeMp4() {
  if (OBSM()) return makeObsMp4();
  if (!last || REC.on) return;
  const k = $s("mpk").value, f = F[k], pan = $s("mpmode").value === "pan", pins = getPins(), idx = pickIdx(), steps = S.runs[S.run].steps;
  if (idx.length < 2) { mpSt("Pick an end hour after the start hour."); return; }
  // start on a real map: drop leading hours this product doesn't have (e.g. 6 h precip at F+3), so frame 1 is never a stale hour
  while (idx.length > 2) { const f_ = steps[idx[0]].f; try { await productFields(S.run, S.prod, f_); break; } catch (e) { S.derived.delete(`${S.run}/${S.prod}/${f_}`); if (!String(e && e.message).startsWith("nodata:")) break; idx.shift(); } }
  if ((BR.corner || BR.card || BR.lower) && LOGOS[BR.logo]) { const t_ = performance.now(); while (!getLogo() && performance.now() - t_ < 4000) await sleep(50); }   // logo on frame 1
  if (pan && !(pins.a && pins.b)) { mpSt("Track storm needs pins: tap the frame where the loop starts (A), then where it ends (B)."); startPin(pins.a ? "b" : "a"); return; }
  const T = loopTimes(idx.length), holdN = Math.round(+$s("mph").value * FPS), panN = Math.max(1, Math.round(T[idx.length] * FPS) - 1);
  // 10-31 1:35 PM (Benjamin: "starting zoom and ending zoom ... start zoom out a bit but zoom in slowly on the storm"): the zoom
  // eases from Start to End over the loop (geometric, so each step looks the same); with pins the centre eases A -> B at the
  // same time, without pins the centre is where the frame is framed now. "as framed" = the frame's own zoom.
  const fr0 = getFr(k), z0 = $s("mpz0").value === "f" ? Math.max(1, fr0.zoom || 1) : +$s("mpz0").value, z1 = $s("mpz1").value === "f" ? z0 : +$s("mpz1").value;
  const ramp = pan || Math.abs(z1 - z0) > 1e-6 || $s("mpz0").value !== "f", c0 = crop(k, fr0);
  const zoomAt = (t) => z0 * Math.pow(z1 / z0, ease(t));
  // storm finder track: camera centre at forecast hour f, straight between the track's hourly positions (A / B = the found ones)
  const TS = TRK.sel >= 0 && TRK.run === S.run && TRK.view === S.view ? TRK.list[TRK.sel] : null, near = (u, v) => u && v && Math.abs(u.x - v.x) < 1 && Math.abs(u.y - v.y) < 1;
  const trk = pan && TS && near(pins.a, TS.a) && near(pins.b, TS.b) ? (() => {
    const P = TS.pts.filter((q) => q.f >= TS.startF && q.f <= TS.endF); if (P.length < 2) return null;
    return (f) => { if (f <= P[0].f) return [P[0].x, P[0].y]; if (f >= P[P.length - 1].f) return [P[P.length - 1].x, P[P.length - 1].y];
      let i = 0; while (P[i + 1].f < f) i++; const u = (f - P[i].f) / (P[i + 1].f - P[i].f); return [lerp(P[i].x, P[i + 1].x, u), lerp(P[i].y, P[i + 1].y, u)]; };
  })() : null;
  const run = S.run, keep = S.i, t0 = performance.now(); let enc = null;
  REC.on = true; REC.cancel = false; PLAY.on = false; window.__vjNoJump = true;   // a video never repeats hours: missing hours keep the previous map $s("mpout").hidden = true; $s("mpgo").disabled = true; $s("mpstop").hidden = false; document.body.classList.add("rec");
  try {
    enc = await makeEncoder(f.cv, f.W, f.H); const totN = Math.round(T[idx.length] * FPS) + holdN, pg = $s("mpprog"); pg.hidden = false; pg.value = 0;
    S.i = idx[0]; $("step").value = idx[0]; await draw(); await sleep(500); await draw();   // let this view's sharp (x2) layers land first
    let n = 0, cardN = 0;
    if (BR.card) {   // title card: 1.5 s, fading out over the first map in the last 0.5 s (the loop timing starts after it)
      getLogo(); await sleep(50); const cN = Math.round(1.5 * FPS), fN = Math.round(0.5 * FPS), c = f.cv.getContext("2d"), fr1 = pan ? frAt(k, ...(trk ? trk(steps[idx[0]].f) : [pins.a.x, pins.a.y]), zoomAt(0)) : ramp ? frAt(k, c0.cx, c0.cy, zoomAt(0)) : null;
      for (let j = 0; j < cN; j++) { await render(k, fr1); titleCard(k, c, j < cN - fN ? 1 : (cN - j) / fN, steps[idx[0]], steps[idx[idx.length - 1]]); await enc.add(j); }
      enc.off = cN; cardN = cN;
    }
    for (let j = 0; j < idx.length; j++) {
      if (REC.cancel || S.run !== run) throw new Error("stopped");
      if (j) { if (enc.idle) enc.idle(); S.i = idx[j]; $("step").value = idx[j]; await draw(); }   // an hour missing from the run keeps the previous map
      mpSt(`Making video\u2026 F+${steps[idx[j]].f} (${j + 1}/${idx.length})`);
      const n0 = Math.round(T[j] * FPS), n1 = Math.round(T[j + 1] * FPS) + (j === idx.length - 1 ? holdN : 0); let drawn = false;
      for (; n < n1; n++) {
        const tt = Math.min(1, n / panN);
        if (pan && trk) {   // found storm, pins untouched: the camera follows the low hour by hour (not a straight line A -> B)
          const fNow = j + 1 < idx.length ? lerp(steps[idx[j]].f, steps[idx[j + 1]].f, Math.min(1, (n - n0) / Math.max(1, Math.round(T[j + 1] * FPS) - n0))) : steps[idx[j]].f, [cx, cy] = trk(fNow);
          await render(k, frAt(k, cx, cy, zoomAt(tt))); }
        else if (pan) { const t = ease(tt); await render(k, frAt(k, lerp(pins.a.x, pins.b.x, t), lerp(pins.a.y, pins.b.y, t), zoomAt(tt))); }
        else if (ramp) await render(k, frAt(k, c0.cx, c0.cy, zoomAt(tt)));
        else if (!drawn || enc.realtime) { await render(k); drawn = true; }   // real-time recorder: redraw so each frame is a fresh canvas frame
        await enc.add(n + (enc.off || 0)); if (n % 6 === 0) pg.value = n / totN;
      }
    }
    pg.value = 1; mpSt("Finishing\u2026"); const how = enc.how, blob = await enc.done(); enc = null;
    const nm = `${run.replace("/", "_")}_${last.cur.pid}_${S.view}_F${steps[idx[0]].f}-F${steps[idx[idx.length - 1]].f}_${k === "v" ? "1080x1920" : "1920x1080"}${pan ? "_track" : ""}.${blob.type.includes("mp4") ? "mp4" : "webm"}`;
    const u = URL.createObjectURL(blob), v = $s("mpv"), dl = $s("mpdl"); if (v.dataset.u) URL.revokeObjectURL(v.dataset.u); v.dataset.u = u; v.src = u; dl.href = u; dl.download = nm;
    const file = new File([blob], nm, { type: blob.type }); $s("mpshare").hidden = !(navigator.canShare && navigator.canShare({ files: [file] })); $s("mpshare").onclick = () => navigator.share({ files: [file] }).catch(() => {});
    n += cardN; $s("mpout").hidden = false; window.__mp4 = { name: nm, pan: pan ? { follow: trk ? "track" : "pins", a: pins.a, b: pins.b } : null, bytes: blob.size, frames: n, seconds: n / FPS, branded: !!(BR.card || BR.lower), corner: !!(BR.corner && LOGOS[BR.logo]) ? BR.cpos : null, how, ms: Math.round(performance.now() - t0), blob };
    mpSt(`Done: ${(blob.size / 1e6).toFixed(1)} MB, ${(n / FPS).toFixed(1)} s, made in ${((performance.now() - t0) / 1000).toFixed(0)} s`);
  } catch (e) { if (enc) enc.abort(); mpSt(e.message === "stopped" ? "Stopped." : "Could not make the video: " + (e.message || e)); window.__mp4 = { error: String(e.message || e) }; }
  finally { REC.on = false; window.__vjNoJump = false; $s("mpgo").disabled = false; $s("mpstop").hidden = true; $s("mpprog").hidden = true; document.body.classList.remove("rec"); if (S.run === run) { S.i = keep; $("step").value = keep; } draw(); }
}
// Observations MP4 (11-03, t2192u "A to B camera"): one live map, the camera eases pin A -> pin B (Pan mode) and / or Start -> End zoom
// over the chosen length, then holds; same encoder, branding and 30 fps as the map loops
async function makeObsMp4() {
  if (REC.on || !MG.img) return;
  const k = $s("mpk").value, f = F[k], pan = $s("mpmode").value === "pan", pins = getPins(), I = obsInfo();
  if (pan && !(pins.a && pins.b)) { mpSt("Pan A \u2192 B needs pins: tap the frame where the video starts (A), then where it ends (B)."); startPin(pins.a ? "b" : "a"); return; }
  if ((BR.corner || BR.card || BR.lower) && LOGOS[BR.logo]) { const t_ = performance.now(); while (!getLogo() && performance.now() - t_ < 4000) await sleep(50); }
  const fr0 = getFr(k), z0 = $s("mpz0").value === "f" ? Math.max(1, fr0.zoom || 1) : +$s("mpz0").value, z1 = $s("mpz1").value === "f" ? z0 : +$s("mpz1").value, c0 = crop(k, fr0);
  const zoomAt = (t) => z0 * Math.pow(z1 / z0, ease(t)), moveN = Math.round(+($s("mpdur").value || 6) * FPS), holdN = Math.round(+$s("mph").value * FPS), totN = moveN + holdN;
  const t0 = performance.now(); let enc = null;
  const OI_ = typeof ObsImg !== "undefined" && ObsImg.active() ? ObsImg : null; if (OI_) { mpSt("Loading radar / satellite frames\u2026"); await OI_.ready(); OI_.hold(true); }   // loop frames follow the video
  REC.on = true; REC.cancel = false; $s("mpout").hidden = true; $s("mpgo").disabled = true; $s("mpstop").hidden = false; document.body.classList.add("rec");
  try {
    enc = await makeEncoder(f.cv, f.W, f.H); const pg = $s("mpprog"); pg.hidden = false; pg.value = 0; let off = 0;
    const frT = (tt) => pan ? frAt(k, lerp(pins.a.x, pins.b.x, ease(tt)), lerp(pins.a.y, pins.b.y, ease(tt)), zoomAt(tt)) : frAt(k, c0.cx, c0.cy, zoomAt(tt));
    if (OI_) OI_.seek(0);
    if (BR.card) { const cN = Math.round(1.5 * FPS), fN = Math.round(0.5 * FPS), c = f.cv.getContext("2d"), fake = { valid: I.t.toISOString(), f: 0, valid_line: I.when };
      for (let j = 0; j < cN; j++) { await render(k, frT(0)); titleCard(k, c, j < cN - fN ? 1 : (cN - j) / fN, fake, fake); await enc.add(j); } off = cN; }
    for (let n = 0; n < totN; n++) {
      if (REC.cancel) throw new Error("stopped");
      if (n % 3 === 0) mpSt(`Making video\u2026 ${Math.round(100 * n / totN)} %`);
      if (OI_) OI_.seek(n / Math.max(1, totN - 1));
      await render(k, frT(Math.min(1, n / Math.max(1, moveN - 1)))); await enc.add(n + off); if (n % 6 === 0) { pg.value = n / totN; if (enc.idle) enc.idle(); }
    }
    pg.value = 1; mpSt("Finishing\u2026"); const how = enc.how, blob = await enc.done(); enc = null;
    const stp = new Intl.DateTimeFormat("en-CA", { timeZone: "America/Los_Angeles", year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", hourCycle: "h23" }).format(I.t).replace(/[^0-9]/g, "");
    const nm = `obs_${I.view}_${I.on.map((l) => l[0]).join("-")}_${stp}_${k === "v" ? "1080x1920" : "1920x1080"}${pan ? "_AtoB" : ""}.${blob.type.includes("mp4") ? "mp4" : "webm"}`;
    const u = URL.createObjectURL(blob), v = $s("mpv"), dl = $s("mpdl"); if (v.dataset.u) URL.revokeObjectURL(v.dataset.u); v.dataset.u = u; v.src = u; dl.href = u; dl.download = nm;
    const file = new File([blob], nm, { type: blob.type }); $s("mpshare").hidden = !(navigator.canShare && navigator.canShare({ files: [file] })); $s("mpshare").onclick = () => navigator.share({ files: [file] }).catch(() => {});
    const n = totN + off; $s("mpout").hidden = false; window.__mp4 = { name: nm, obs: true, pan: pan ? { a: pins.a, b: pins.b } : null, z0, z1, bytes: blob.size, frames: n, seconds: n / FPS, how, ms: Math.round(performance.now() - t0), blob };
    mpSt(`Done: ${(blob.size / 1e6).toFixed(1)} MB, ${(n / FPS).toFixed(1)} s, made in ${((performance.now() - t0) / 1000).toFixed(0)} s`);
  } catch (e) { if (enc) enc.abort(); mpSt(e.message === "stopped" ? "Stopped." : "Could not make the video: " + (e.message || e)); window.__mp4 = { error: String(e.message || e) }; }
  finally { if (OI_) OI_.hold(false); REC.on = false; $s("mpgo").disabled = false; $s("mpstop").hidden = true; $s("mpprog").hidden = true; document.body.classList.remove("rec"); renderAll(); }
}
// ---- storm finder (10-31 3:17 PM, Benjamin: "Oh I like this idea, yes develop that"): the lows in this view (the same L
// centres the map draws, from this model's sea-level pressure) are linked hour to hour into tracks; the deepest track gives the
// loop: start / end hour, pin A (where the low is at the start), pin B (landfall, else where it is at the end), landfall hour.
// It fills in the panel like a preset; everything stays editable. Land / sea from the ECMWF wave field (stormfind.js).
const lutC = {};
async function ifsLut(vid) {   // ECMWF 0.25 LUT of a view: figure px <-> lat / lon (every model's view has the same panel)
  const Vi = ((S.man.models.ifs || {}).views || {})[vid]; if (!Vi) return null;
  if (!lutC[vid]) lutC[vid] = fetch(DATA + Vi.lut + SV()).then((r) => r.arrayBuffer()).then((b) => new Float32Array(b)).catch(() => { delete lutC[vid]; return null; });
  const lut = await lutC[vid]; return lut ? { Vi, lut } : null;
}
async function llToFig(lat, lon) {
  const L = await ifsLut(S.view), st = await viewStatic(S.view); if (!L) return null;
  const [fi, fj] = StormFind.IFS.ij(lat, lon), p = gridInv(L.Vi, { lut: L.lut, W: st.W, H: st.H }, fi, fj, null);
  return p ? { x: st.x0 + p[0], y: st.y0 + p[1] } : null;
}
const stormLbl = (P_) => `${Math.round(P_.minP)} mb low \u00b7 F+${P_.pts[0].f}\u2013F+${P_.pts[P_.pts.length - 1].f} in view \u00b7 ` +
  (P_.landfall ? `landfall F+${P_.landfall.f}` : "no landfall");
async function findStorms() {
  if (!last || REC.on || TRK.busy) return [];
  const run = S.run, vid = S.view, R_ = S.runs[run];
  if (!R_.fields.includes("mslp")) { mpSt("This model has no sea-level pressure, so the storm finder can't run on it. Try ECMWF or GFS."); return []; }
  TRK.busy = true; $s("mpsf").disabled = true; mpSt("Finding storms\u2026");
  try {
    const V = VIEWS()[vid], st = await viewStatic(vid), steps = R_.steps, L = await ifsLut(vid);
    const use = steps.length > 48 ? steps.filter((x) => x.f % 6 === 0) : steps, hours = [];
    for (let n = 0; n < use.length; n++) {
      if (S.run !== run || S.view !== vid) throw new Error("the run or view changed");
      let Fm; try { Fm = await getField(run, "mslp", use[n].f); } catch (e) { continue; }
      const lows = hlGeom(st, { raw: { mslp: Fm }, w: Fm.w, h: Fm.h }, V).filter((o) => !o[3]).map(([x, y, p]) => {
        const q = { x, y, p }; if (L) { const [fi, fj] = gridFwd(L.Vi, L.lut, x - st.x0, y - st.y0); q.lat = StormFind.IFS.lat(fi); q.lon = StormFind.IFS.lon(fj); } return q; });
      hours.push({ f: use[n].f, lows }); if (n % 4 === 0) mpSt(`Finding storms\u2026 F+${use[n].f}`);
    }
    // without lat / lon (HRRR-only views): distance in map px, reach a tenth of the panel per 6 h
    const tr = StormFind.track(hours, L ? {} : { dist: (a, b) => Math.hypot(a.x - b.x, a.y - b.y), reach: (dh) => V.panel[2] * (0.04 + 0.016 * dh) });
    const land = L ? await StormFind.landMask(DATA) : () => null;
    TRK.list = tr.map((T) => StormFind.plan(T, StormFind.landfall(T, land))); TRK.run = run; TRK.view = vid; TRK.sel = -1;
    const sel = $s("mpsfl");
    sel.innerHTML = TRK.list.map((P_, i) => `<option value="${i}">${i + 1}. ${stormLbl(P_)}</option>`).join(""); sel.hidden = TRK.list.length < 2;
    if (!TRK.list.length) { mpSt("No closed low stays in this view for 3+ maps in this run. Pick pins by hand, or try a bigger view."); $s("mpsfi").textContent = ""; return []; }
    applyStorm(0); return TRK.list;
  } catch (e) { mpSt("Storm finder: " + (e.message || e)); return []; }
  finally { TRK.busy = false; $s("mpsf").disabled = false; }
}
function applyStorm(n) {
  const P_ = TRK.list[n]; if (!P_ || TRK.run !== S.run) return; TRK.sel = n; $s("mpsfl").value = String(n);
  const steps = S.runs[S.run].steps, ix = (f) => steps.findIndex((x) => x.f === f);
  setPins({ a: { x: P_.a.x, y: P_.a.y }, b: { x: P_.b.x, y: P_.b.y } });
  for (const [id, v] of Object.entries(PRESETS.landfall)) $s(id).value = v;   // the landfall look: pan A -> B, zoom in, slow down
  $s("mpa").value = String(ix(P_.startF)); $s("mpb").value = String(ix(P_.endF)); $s("mppre").value = "storm";
  // 10-31 3:53 PM (Benjamin: "After storm finds the storm, make it autofill in the settings for the storm it found"): a map with
  // isobars, the frame shape from the track's direction, zooms from its size, a speed for a ~7 s loop (slowing into landfall),
  // and the branding title / storm name. All still editable.
  const R_ = S.runs[S.run], has = (x) => PRODS()[x] && PRODS()[x].fields.every((fl) => R_.fields.includes(fl));
  if (!(PRODS()[S.prod] || {}).isobars) { const want = ["mslpqpf", "slp", "aifswind", "ptype"].find(has); if (want) { S.prod = want; setLists(); $("prod").value = want; } }
  const V = VIEWS()[S.view], dx = Math.abs(P_.b.x - P_.a.x), dy = Math.abs(P_.b.y - P_.a.y), d = Math.hypot(dx, dy) / V.panel[2];
  if (!(SQ.get("make") && SQ.get("shape"))) $s("mpk").value = dx >= dy ? "h" : "v";
  const snap = (v, opts) => opts.reduce((b, o) => Math.abs(o - v) < Math.abs(b - v) ? o : b, opts[0]), ZO = [1, 1.2, 1.4, 1.6, 1.8, 2, 2.2, 2.5, 2.8, 3];
  const z1 = snap(Math.min(2.5, Math.max(1.6, 2.6 - 2.5 * d)), ZO), z0 = snap(Math.max(1, Math.min(z1 - 0.4, 1 / (0.5 + d))), ZO);
  $s("mpz0").value = String(z0); $s("mpz1").value = String(z1);
  $s("mpe").value = P_.endF - P_.startF <= 48 ? "3" : "6";
  const nMaps = pickIdx().length, s0 = Math.min(6, Math.max(1.5, Math.round(nMaps / 7 * 2) / 2));
  $s("mps").value = String(s0); $s("mps1").value = P_.landfall ? String(snap(Math.max(1, s0 / 2), [0.5, 1, 1.5, 2, 3, 4, 5, 6])) : "";
  const vt = (f) => (steps.find((x) => x.f === f) || {}).valid, day = (f) => ptTime(vt(f), { weekday: "short", month: "short", day: "numeric", hour: "numeric" }) + " PT";
  if (!BR.title || BR.autoT) { BR.title = P_.landfall ? `Storm landfall ${day(P_.landfall.f)}` : `Deep low offshore ${day(P_.fMin)}`; BR.autoT = true; }
  if (!BR.storm || BR.autoS) { BR.storm = `${Math.round(P_.minP)} mb low`; BR.autoS = true; }
  brSync(); saveBR();
  mpMode(); saveOpts();
  const fi = ix(P_.landfall ? P_.landfall.f : P_.fMin); if (fi >= 0 && !REC.on) { S.i = fi; $("step").value = fi; draw(); }
  const lf = P_.landfall;
  $s("mpsfi").textContent = `Deepest ${Math.round(P_.minP)} mb at F+${P_.fMin}. ` + (lf ? `Landfall F+${lf.f}${lf.lat !== undefined ? " near " + StormFind.fmtLL(lf) : ""}. ` : "No landfall in this view: B is where the track ends. ") +
    `Loop F+${P_.startF} to F+${P_.endF}. A = start, B = ${lf ? "landfall" : "end"}. Change any of it below, or Set pin A / B by hand.`;
  mpSt(`Found ${TRK.list.length} storm track${TRK.list.length === 1 ? "" : "s"}; using the deepest.`); mpInfo();
}
function brSync() { if (!$s("brcard")) return; $s("brcard").checked = BR.card; $s("brlower").checked = BR.lower; if ($s("brcorner")) { $s("brcorner").checked = BR.corner; $s("brcpos").value = BR.cpos; } $s("brlogo").value = LOGOS[BR.logo] ? BR.logo : "none"; $s("brtitle").value = BR.title || ""; $s("brstorm").value = BR.storm || ""; }
// ---- batch export (10-31 3:49 PM, Benjamin: "Yes to 2"): tick models / products / views / frame shapes, one button makes every
// MP4 with the panel's settings (hours by forecast hour, speed, zoom, mode / pins of each view, preset; "Auto storm track" finds
// the storm per map) and packs them in one .zip (stored, MP4s don't compress). Result: window.__batchResult.
const BX = { on: false, cancel: false };
const MORDER = ["hrrr", "rrfs", "nbm", "gfs", "ifs", "ifs9", "aifs", "eps", "aens", "aensm", "epsm", "gfsw", "oisst"];
// 11-03 (WW3 swell-period labels under the 16:9 color bar): map line labels whose spot lands in the bottom color bar / credit band of
// either frame are not drawn (the viewer asks while painting; the lines themselves stay)
window.studioLabelHidden = (x, y, ex = 0, ey = 0) => {   // ex / ey: the label's half width / height in map px (11-03 t2254u)
  if (!last || MG.on) return false;
  return ["v", "h"].some((k) => { const f = F[k]; if (!f) return false; const r = crop(k, getFr(k)), X = (x - r.sx / r.rs) * r.kk, Y = (y - r.sy / r.rs) * r.kk, EX = ex * r.kk, EY = ey * r.kk;
    if (X + EX > -60 && X - EX < f.W + 60 && Y + EY > f.H - (k === "v" ? 250 : 135) && Y - EY < f.H + 30) return true;
    // 11-03 small fixes (a swell-period "10 s" sat under the 16:9 title): also the header block and the F+ badge (boxes from the last
    // frame paint; before the first paint an estimate from the frame's font sizes), with ~half a label of margin
    const top = k === "v" ? 120 : 34, hd = f.hdr || [0, 0, f.pad + (k === "v" ? f.W : f.W * 0.42), top + f.run * 1.55 + f.title * 1.02 + f.day * 1.75 + 14],
      bg = f.badge || [f.W - f.pad - 220, top - 12, f.W, top + f.valid * 1.9 + 12], m_ = 30;
    return [hd, bg].some((b) => X + EX > b[0] - m_ && X - EX < b[2] + m_ && Y + EY > b[1] - m_ && Y - EY < b[3] + m_); });
};
function bxFill() {
  const ck = (id, v, t, on) => `<label><input type="checkbox" data-g="${id}" value="${v}"${on ? " checked" : ""}> ${t}</label>`, [m0] = S.run.split("/"), R_ = S.runs[S.run];
  $s("bxm").innerHTML = MORDER.filter((m) => S.man.models[m] && (S.man.runs[m] || []).length).map((m) => ck("m", m, S.man.models[m].site || m, m === m0)).join("");
  $s("bxp").innerHTML = Object.entries(PRODS()).filter(([, p]) => p.fields.every((fl) => R_.fields.includes(fl))).map(([k, p]) => ck("p", k, p.title, k === S.prod)).join("");
  $s("bxv").innerHTML = Object.entries(VIEWS()).map(([k, v]) => ck("v", k, v.label, k === S.view)).join(""); bxCount();
}
const bxSel = (g) => [...document.querySelectorAll(`#mpbatch input[data-g="${g}"]:checked`)].map((e) => e.value);
function bxCount() { const n = bxSel("m").length * bxSel("p").length * bxSel("v").length * (+$s("bxsv").checked + +$s("bxsh").checked); $s("bxn").textContent = `${n} video${n === 1 ? "" : "s"} (at most 40)`; return n; }
const CRC = (() => { const t = new Uint32Array(256); for (let n = 0; n < 256; n++) { let c = n; for (let k = 0; k < 8; k++) c = c & 1 ? 0xEDB88320 ^ (c >>> 1) : c >>> 1; t[n] = c >>> 0; } return t; })();
const crc32 = (u) => { let c = 0xFFFFFFFF; for (let i = 0; i < u.length; i++) c = CRC[(c ^ u[i]) & 255] ^ (c >>> 8); return (c ^ 0xFFFFFFFF) >>> 0; };
async function zipStore(files) {   // plain "stored" zip (no compression), UTF-8 names
  const parts = [], cd = []; let off = 0;
  for (const f of files) {
    const data = new Uint8Array(await f.blob.arrayBuffer()), nm = new TextEncoder().encode(f.name), crc = crc32(data), L = new DataView(new ArrayBuffer(30)), C = new DataView(new ArrayBuffer(46));
    L.setUint32(0, 0x04034b50, true); L.setUint16(4, 20, true); L.setUint16(6, 0x0800, true); L.setUint16(12, 0x21, true); L.setUint32(14, crc, true); L.setUint32(18, data.length, true); L.setUint32(22, data.length, true); L.setUint16(26, nm.length, true);
    C.setUint32(0, 0x02014b50, true); C.setUint16(4, 20, true); C.setUint16(6, 20, true); C.setUint16(8, 0x0800, true); C.setUint16(14, 0x21, true); C.setUint32(16, crc, true); C.setUint32(20, data.length, true); C.setUint32(24, data.length, true); C.setUint16(28, nm.length, true); C.setUint32(42, off, true);
    parts.push(L, nm, data); cd.push(C, nm); off += 30 + nm.length + data.length;
  }
  const size = cd.reduce((a, x) => a + x.byteLength, 0), E_ = new DataView(new ArrayBuffer(22));
  E_.setUint32(0, 0x06054b50, true); E_.setUint16(8, files.length, true); E_.setUint16(10, files.length, true); E_.setUint32(12, size, true); E_.setUint32(16, off, true);
  return new Blob([...parts, ...cd, E_], { type: "application/zip" });
}
async function setCombo(m, p, v) {
  const rs = S.man.runs[m] || []; if (!rs.length) return "no run";
  if (!(S.man.models[m].views || {})[v]) return "view not in this model";
  const run = `${m}/${rs[rs.length - 1]}`; await loadRun(run); S.run = run; $("run").value = run; S.view = v; S.prod = p; setLists();
  if (S.prod !== p) return "product not in this run"; if (S.view !== v) return "view not in this model";
  $("prod").value = p; $("view").value = v; await draw(); return null;
}
async function batchExport(opts) {
  if (BX.on || REC.on || !last) return; const o = opts || {};
  const ms = o.models || bxSel("m"), ps = o.prods || bxSel("p"), vs = o.views || bxSel("v"), ks = o.shapes || ["v", "h"].filter((k) => $s("bxs" + k).checked);
  const steps0 = S.runs[S.run].steps, fA = steps0[+$s("mpa").value].f, fB = steps0[+$s("mpb").value].f, keepO = {}; for (const id of OPT_IDS) keepO[id] = $s(id).value;
  const pre = $s("mppre").value, back = { run: S.run, prod: S.prod, view: S.view, i: S.i }, res = window.__batchResult = { state: "making", items: [], skipped: [] };
  const combos = []; for (const m of ms) for (const p of ps) for (const v of vs) for (const k of ks) combos.push([m, p, v, k]);
  if (!combos.length) { $s("bxst").textContent = "Tick at least one model, product, view and frame shape."; res.state = "error"; return res; }
  if (combos.length > 40) { $s("bxst").textContent = `${combos.length} videos is too many at once (40 at most).`; res.state = "error"; return res; }
  BX.on = true; BX.cancel = false; $s("bxgo").disabled = true; $s("bxstop").hidden = false; $s("bxout").innerHTML = ""; const files = [];
  try {
    for (let j = 0; j < combos.length; j++) {
      if (BX.cancel) throw new Error("stopped"); const [m, p, v, k] = combos[j];
      $s("bxst").textContent = `${j + 1}/${combos.length}: ${S.man.models[m].site || m} \u00b7 ${p} \u00b7 ${v} \u00b7 ${k === "v" ? "9:16" : "16:9"}`;
      const why = await setCombo(m, p, v); if (why) { res.skipped.push({ m, p, v, k, why }); continue; }
      const st = S.runs[S.run].steps; openMp4(k); for (const [id, val] of Object.entries(keepO)) $s(id).value = val; $s("mpk").value = k;
      const ia = st.findIndex((x) => x.f >= fA); let ib = -1; st.forEach((x, i) => { if (x.f <= fB) ib = i; });
      if (ia < 0 || ib <= ia) { res.skipped.push({ m, p, v, k, why: `no hours F+${fA}..F+${fB}` }); continue; }
      $s("mpa").value = String(ia); $s("mpb").value = String(ib);
      if (pre === "storm") { const l = await findStorms(); $s("mpk").value = k; if (!l.length) $s("mpmode").value = "loop"; }
      else if ($s("mpmode").value === "pan" && !(getPins().a && getPins().b)) $s("mpmode").value = "loop";   // no pins for this view
      if (pre === "storm" && S.prod !== p) S.prod = p, setLists(), $("prod").value = p;   // keep the ticked product
      mpMode(); await makeMp4(); const r = window.__mp4 || {};
      if (!r.blob) { res.skipped.push({ m, p, v, k, why: r.error || "no video" }); if (r.error === "stopped") throw new Error("stopped"); continue; }
      files.push({ name: r.name, blob: r.blob }); res.items.push({ name: r.name, bytes: r.bytes, seconds: r.seconds, corner: r.corner });
      const a = document.createElement("a"); a.href = URL.createObjectURL(r.blob); a.download = r.name; a.textContent = `${r.name} (${(r.bytes / 1e6).toFixed(1)} MB)`; $s("bxout").appendChild(a);
    }
    if (!files.length) throw new Error("no videos were made" + (res.skipped.length ? ": " + res.skipped.map((x) => x.why).join("; ") : ""));
    $s("bxst").textContent = "Packing the .zip\u2026"; const zip = await zipStore(files), zn = `wx_studio_batch_${new Date().toISOString().slice(0, 16).replace(/[-:T]/g, "")}.zip`;
    const za = document.createElement("a"); za.id = "bxzip"; za.href = URL.createObjectURL(zip); za.download = zn; za.textContent = `Download all (${files.length} MP4s, ${(zip.size / 1e6).toFixed(1)} MB .zip)`; $s("bxout").prepend(za);
    Object.assign(res, { state: "done", ok: true, zipName: zn, zipBytes: zip.size, zipUrl: za.href });
    $s("bxst").textContent = `Done: ${files.length} video${files.length === 1 ? "" : "s"}${res.skipped.length ? `, ${res.skipped.length} skipped (not in that model / run)` : ""}.`;
  } catch (e) { Object.assign(res, { state: "error", ok: false, error: String(e.message || e) }); $s("bxst").textContent = e.message === "stopped" ? "Stopped." : "Batch: " + (e.message || e); }
  finally { BX.on = false; $s("bxgo").disabled = false; $s("bxstop").hidden = true;
    try { await loadRun(back.run); S.run = back.run; $("run").value = back.run; S.view = back.view; S.prod = back.prod; setLists(); S.i = Math.min(back.i, S.runs[S.run].steps.length - 1); $("step").value = S.i; draw(); } catch (e) { /* stay */ } }
  return res;
}
// ---- instant loop link (10-31 3:38 PM, Benjamin: "Yes go ahead and add the api"): studio.html?make=loop&model=ecmwf&product=mslp
// &view=na&from=24&to=144&shape=h [&step=6&speed=4&endspeed=1&startzoom=1.2&endzoom=2&pinA=lat,lon&pinB=lat,lon&preset=landfall|
// overview|smooth|zoomin|storm&hold=1&run=ifs/2026103112]. Builds the MP4 on open with no clicks; the result is in
// window.__loopResult ({state: loading|making|done|error, ok, name, bytes, seconds, url (blob), ...}), body[data-loop], and a
// download link (#loopdl, plus the panel's Save MP4). model / product aliases are mapped in studio.html before viewer.js boots.
function setSel(id, v) { const el = $s(id); v = String(v); if (el.type !== "range" && ![...el.options].some((o) => o.value === v)) { const o = document.createElement("option"); o.value = v; o.textContent = v; el.appendChild(o); } el.value = v; }
async function autoLoop() {
  const res = window.__loopResult = { state: "loading" }; document.body.dataset.loop = "loading";
  const num = (n) => (SQ.has(n) && SQ.get(n) !== "" && isFinite(+SQ.get(n)) ? +SQ.get(n) : null);
  try {
    for (let t = 0; !(window.__ready && last); t++) { if (t > 900) throw new Error("the map did not load"); await sleep(100); }
    const k = SQ.get("shape") === "v" ? "v" : "h", pre = SQ.get("preset") || ""; openMp4(k);
    const steps = S.runs[S.run].steps;
    // a link starts from the plain defaults, not from options remembered in this browser
    for (const [id, v] of Object.entries({ mpmode: "loop", mpe: "0", mps: "4", mps1: "", mph: "1", mpz0: "f", mpz1: "f", mppre: "" })) $s(id).value = v;
    if (PRESETS[pre]) { for (const [id, v] of Object.entries(PRESETS[pre])) if (id !== "span") $s(id).value = v; $s("mppre").value = pre; }
    if (pre === "storm") { const l = await findStorms(); if (!l.length && !SQ.get("pinA")) throw new Error("storm finder: " + $s("mpst").textContent); if (SQ.get("shape")) $s("mpk").value = k; }
    const from = num("from"), to = num("to");
    if (from !== null) { const i = steps.findIndex((x) => x.f >= from); if (i >= 0) $s("mpa").value = String(i); }
    if (to !== null) { let i = -1; steps.forEach((x, j) => { if (x.f <= to) i = j; }); if (i >= 0) $s("mpb").value = String(i); }
    else if (pre === "overview") { const a = +$s("mpa").value, e = steps.findIndex((x) => x.f >= steps[a].f + 120); $s("mpb").value = String(e > a ? e : steps.length - 1); }
    else if (pre !== "storm" && from !== null) $s("mpb").value = String(steps.length - 1);
    if (num("step") !== null) setSel("mpe", num("step"));
    if (num("speed") !== null) $s("mps").value = String(Math.min(15, Math.max(0.5, num("speed"))));
    if (num("endspeed") !== null) setSel("mps1", num("endspeed"));
    if (num("hold") !== null) setSel("mph", num("hold"));
    if (num("startzoom") !== null) setSel("mpz0", num("startzoom"));
    if (num("endzoom") !== null) setSel("mpz1", num("endzoom"));
    const pin = async (n) => { const q = (SQ.get(n) || "").split(",").map(Number); return q.length === 2 && q.every(isFinite) ? llToFig(q[0], q[1]) : null; };
    const pa = await pin("pinA"), pb = await pin("pinB");
    if (SQ.get("pinA") || SQ.get("pinB")) {
      if (!pa || !pb) throw new Error("pinA and pinB need lat,lon inside this view (e.g. pinA=46.5,-131&pinB=47.9,-124.6)");
      setPins({ a: pa, b: pb }); $s("mpmode").value = "pan";
    }
    if ($s("mpmode").value === "pan" && !(getPins().a && getPins().b)) $s("mpmode").value = "loop";   // e.g. preset=landfall without pins
    mpMode(); mpInfo();
    if (+$s("mpb").value <= +$s("mpa").value) throw new Error(`no hours between from=${from} and to=${to} in ${S.run}`);
    res.state = "making"; document.body.dataset.loop = "making";
    window.__mp4 = null; await makeMp4();
    const m = window.__mp4 || {}; if (m.error || !m.bytes) throw new Error(m.error || $s("mpst").textContent || "no video was made");
    const u = $s("mpdl").href, a = document.createElement("a"); a.id = "loopdl"; a.href = u; a.download = m.name; a.textContent = `Download ${m.name} (${(m.bytes / 1e6).toFixed(1)} MB)`;
    const bar = document.createElement("div"); bar.id = "loopbar"; bar.append("Loop ready: ", a); document.body.appendChild(bar);
    Object.assign(res, { state: "done", ok: true, name: m.name, bytes: m.bytes, seconds: m.seconds, frames: m.frames, how: m.how, ms: m.ms, url: u,
      run: S.run, prod: S.prod, view: S.view, shape: k, from: steps[+$s("mpa").value].f, to: steps[+$s("mpb").value].f, mode: $s("mpmode").value, pins: getPins(),
      storm: TRK.sel >= 0 ? { minP: TRK.list[TRK.sel].minP, landfall: TRK.list[TRK.sel].landfall && TRK.list[TRK.sel].landfall.f } : null });
    document.body.dataset.loop = "done";
  } catch (e) { Object.assign(res, { state: "error", ok: false, error: String(e.message || e) }); document.body.dataset.loop = "error"; mpSt("Instant loop: " + res.error); }
  return res;
}
if (!CLEAN && $s("mp4p")) {
  $s("mp4p").addEventListener("click", (e) => { const b = e.target.closest("button[data-m]"); if (!b) return; const m_ = b.dataset.m;
    if (m_ === "x") { if (!REC.on) { $s("mp4p").hidden = true; PIN.show = false; document.body.classList.remove("mprange"); render("v"); render("h"); } }
    else if (m_ === "min") { const mn = $s("mp4p").classList.toggle("min"); b.innerHTML = mn ? "+" : "&ndash;"; b.title = mn ? "Expand" : "Minimize"; }
    else if (m_ === "sa" || m_ === "sb") { if (REC.on) return; const a = $s("mpa"), z = $s("mpb");
      if (m_ === "sa") { a.value = String(S.i); if (+z.value <= S.i) z.value = String(Math.min(S.runs[S.run].steps.length - 1, S.i + 1)); }
      else { z.value = String(S.i); if (+a.value >= S.i) a.value = String(Math.max(0, S.i - 1)); }
      mpInfo(); }
    else if (m_ === "a" || m_ === "b") startPin(m_);
    else if (m_ === "pv") previewMove();
    else if (m_ === "sf") findStorms();
    else if (m_ === "c") { setPins({}); mpInfo(); render("v"); render("h"); }
    else if (m_ === "go") makeMp4(); else if (m_ === "stop") REC.cancel = true; });
  for (const id of ["mpa", "mpb", "mpe", "mps", "mps1", "mph", "mpz0", "mpz1", "mpdur"]) $s(id).addEventListener("change", mpInfo);
  for (const id of OPT_IDS) $s(id).addEventListener("change", (e) => { saveOpts(); if (e.isTrusted) $s("mppre").value = ""; });
  $s("mppre").addEventListener("change", (e) => { if (e.target.value === "storm") findStorms(); else applyPreset(e.target.value); });
  $s("mpsfl").addEventListener("change", (e) => applyStorm(+e.target.value));
  brSync();
  for (const id of ["brcard", "brlower"]) $s(id).addEventListener("change", (e) => { BR[id === "brcard" ? "card" : "lower"] = e.target.checked; saveBR(); renderAll(); });
  $s("brcorner").addEventListener("change", (e) => { BR.corner = e.target.checked; if (BR.corner && !LOGOS[BR.logo]) { BR.logo = "wa"; brSync(); } saveBR(); renderAll(); });
  $s("brcpos").addEventListener("change", (e) => { BR.cpos = e.target.value; saveBR(); renderAll(); });
  $s("brlogo").addEventListener("change", (e) => { BR.logo = e.target.value; saveBR(); renderAll(); });
  $s("brtitle").addEventListener("input", (e) => { BR.title = e.target.value; BR.autoT = false; saveBR(); renderAll(); });
  $s("brstorm").addEventListener("input", (e) => { BR.storm = e.target.value; BR.autoS = false; saveBR(); renderAll(); });
  $s("brcardpv").addEventListener("click", async () => { if (!last || REC.on) return; const k = $s("mpk").value; getLogo(); await sleep(80); await render(k); titleCard(k, F[k].cv.getContext("2d"), 1, null, null); setTimeout(() => render(k), 2500); });
  $s("mpbatch").addEventListener("toggle", (e) => { if (e.target.open) bxFill(); });
  $s("mpbatch").addEventListener("change", (e) => { if (e.target.matches("input[type=checkbox]")) bxCount(); });
  $s("bxgo").addEventListener("click", () => batchExport());
  $s("bxstop").addEventListener("click", () => { BX.cancel = true; REC.cancel = true; });
  $s("mpk").addEventListener("change", () => { mpInfo(); });
  // Enter = Make MP4 (not while typing in a menu that uses Enter itself)
  $s("mp4p").addEventListener("keydown", (e) => { if (e.key === "Enter" && e.target.tagName !== "SELECT" && e.target.tagName !== "BUTTON" && e.target.tagName !== "A") { e.preventDefault(); makeMp4(); } });
  // drag the panel by its title bar (desktop: the panel floats over the frames); position remembered
  (() => { const P_ = $s("mp4p"), hd = P_.querySelector(".mp-h"); let dd = null;
    const place = (x, y) => { x = Math.max(0, Math.min(innerWidth - 120, x)); y = Math.max(0, Math.min(innerHeight - 40, y)); P_.style.left = x + "px"; P_.style.top = y + "px"; P_.style.bottom = "auto"; };
    try { const q = JSON.parse(localStorage.getItem("studio:mp4pos") || "null"); if (q && innerWidth > 820) place(q.x, q.y); } catch (e) { /* none */ }
    hd.addEventListener("pointerdown", (e) => { if (innerWidth <= 820 || e.target.closest("button")) return; const r = P_.getBoundingClientRect(); dd = { dx: e.clientX - r.left, dy: e.clientY - r.top }; hd.setPointerCapture(e.pointerId); });
    hd.addEventListener("pointermove", (e) => { if (dd) place(e.clientX - dd.dx, e.clientY - dd.dy); });
    hd.addEventListener("pointerup", () => { if (!dd) return; dd = null; try { localStorage.setItem("studio:mp4pos", JSON.stringify({ x: parseFloat(P_.style.left), y: parseFloat(P_.style.top) })); } catch (e) { /* private */ } });
    hd.addEventListener("dblclick", () => { P_.style.left = P_.style.top = P_.style.bottom = ""; localStorage.removeItem("studio:mp4pos"); });
  })();
  $s("mps").addEventListener("input", mpInfo);
  // arrow keys inside the panel's menus / slider change those, not the hour (the viewer steps hours on arrows anywhere else)
  $s("mp4p").addEventListener("keydown", (e) => { if (/^(SELECT|INPUT)$/.test(e.target.tagName) && /^Arrow/.test(e.key)) e.stopPropagation(); });
  $("step").addEventListener("input", mpSync);
  $s("mpmode").addEventListener("change", mpMode);
  addEventListener("keydown", (e) => { if (e.key !== "Escape") return;
    if (PIN.mode) { PIN.mode = null; $s("pinhint").hidden = true; $s("mp4p").hidden = false; mpInfo(); render("v"); render("h"); }
    else if (REC.on) REC.cancel = true;
    else if (!$s("mp4p").hidden) { $s("mp4p").hidden = true; PIN.show = false; document.body.classList.remove("mprange"); render("v"); render("h"); } });
  // test hook: a pin's on-screen (client) position in frame k
  const pinXY = (k, n) => { const p = getPins()[n]; if (!p || !last) return null; const f = F[k], r = crop(k, getFr(k)), b = f.cv.getBoundingClientRect();
    return { x: b.left + (f.W / 2 + (p.x - r.cx) * r.kk) * b.width / f.W, y: b.top + (f.H / 2 + (p.y - r.cy) * r.kk) * b.height / f.H }; };
  const mapAt = (k, cx, cy) => { const f = F[k], r = crop(k, getFr(k)), b = f.cv.getBoundingClientRect(); return { x: r.cx + ((cx - b.left) * f.W / b.width - f.W / 2) / r.kk, y: r.cy + ((cy - b.top) * f.H / b.height - f.H / 2) / r.kk }; };
  window.__studioMp4 = { pinXY, mapAt, getFr, getPins, setPins, makeMp4, openMp4, findStorms, applyStorm, llToFig, TRK, BR, batchExport, bxFill };
  if (SQ.get("make") === "loop") autoLoop();
}
// auto-advance (clean mode or ?play=1): next hour after each finished frame + dwell; loops (or holds); newest run on loop when model= is used
const PLAY = { on: SQ.get("play") === "1", t: 0, next() {
  clearTimeout(PLAY.t); const dwell = +SQ.get("dwell") || 700, stepH = +SQ.get("step") || 0;
  PLAY.t = setTimeout(async () => {
    const st = S.runs[S.run].steps; let i = S.i + 1; if (stepH) while (i < st.length && st[i].f - st[S.i].f < stepH) i++;
    if (i >= st.length) {
      if (SQ.get("loop") === "0") return;
      if (SQ.get("model") && !SQ.get("run")) { try { const M2 = await (await fetch(DATA + "manifest.json", { cache: "no-cache" })).json(), rs = (M2.runs || {})[SQ.get("model")] || [];
        if (rs.length && `${SQ.get("model")}/${rs[rs.length - 1]}` !== S.run) { location.reload(); return; } } catch (e) { /* keep looping */ } }
      i = 0;
    }
    S.i = i; $("step").value = i; draw();
  }, dwell);
} };
// ---- 10-31 7:25 PM (Benjamin: "make sure that the vertical window and horizontal video stay exactly the correct format size and don't
// compress or get squished ... when I make the window smaller"): desktop frames sized here in px, exact 9:16 and 16:9, scaled down
// uniformly to fit both the window's width and height (whole frames on screen, no page scroll when there is room). Phones (<= 820 px
// wide, stacked full-width frames) and clean (OBS) mode keep their CSS sizes. Runs on load, window resize and menu-bar wrap changes.
function fitFrames() {
  const st = document.getElementById("studio"), fv = document.getElementById("fv"), fh = document.getElementById("fh"), cvv = F.v.cv, cvh = F.h.cv;
  const clear = () => { for (const e of [cvv, cvh, fv, fh]) { e.style.width = ""; e.style.height = ""; e.style.flex = ""; } };
  if (CLEAN || innerWidth <= 820) { clear(); return; }
  const cs = getComputedStyle(st), padX = parseFloat(cs.paddingLeft) + parseFloat(cs.paddingRight), padB = parseFloat(cs.paddingBottom) + 2;
  const gap = parseFloat(cs.columnGap) || 18, hint = fh.querySelector(".shint"), MINV = 300;   // below ~300 px tall the page scrolls instead
  // 11-04 (Benjamin t2316u-t2318u "satellite viewers ... same exact size as the model views", "same exact size and placement in the
  // window browser", "pass forecaster view too"): Observations / Meteogram / Pass Forecaster frames take the Map mode's size AND spot.
  // The Map layout is measured with the mode class off (same sync pass, never painted), then the mode's panel is padded or capped
  // (scrolls) so the frames start at the same y.
  const bd = document.body, MODES = ["mgmode", "obsmode", "passmode"].filter((c) => bd.classList.contains(c)), pnl = document.getElementById("mgp");
  if (pnl) { pnl.style.maxHeight = ""; pnl.style.overflowY = ""; } st.style.marginTop = "";
  const SHD = [fv, fh].map((f) => f.querySelector(".shd")); for (const e of SHD) e.style.minHeight = "";
  for (const c of MODES) bd.classList.remove(c);
  let wv = 0, wh = 0;
  for (let it = 0; it < 5; it++) {
    const availW = st.clientWidth - padX - gap, sy = scrollY;
    const availV = innerHeight - (cvv.getBoundingClientRect().top + sy) - padB;
    let under = 0; for (let e = cvh.nextElementSibling; e; e = e.nextElementSibling) under += e.offsetHeight + 6;   // hint, hour scrubber, request button
    const availH = innerHeight - (cvh.getBoundingClientRect().top + sy) - padB - under;
    const nv = Math.max(MINV * 9 / 16, Math.min(availV * 9 / 16, availW * 0.42));
    const nh = Math.max(240, Math.min(availW - nv, Math.max(MINV, availH) * 16 / 9));
    const same = Math.abs(nv - wv) < 0.5 && Math.abs(nh - wh) < 0.5; wv = nv; wh = nh;
    fv.style.flex = fh.style.flex = "0 0 auto"; fv.style.width = wv + "px"; fh.style.width = wh + "px";
    cvv.style.width = wv + "px"; cvv.style.height = wv * 16 / 9 + "px"; cvh.style.width = wh + "px"; cvh.style.height = wh * 9 / 16 + "px";
    if (same) break;
  }
  let topMap = cvh.getBoundingClientRect().top + scrollY;
  let shdH = SHD.map((e) => e.getBoundingClientRect().height);
  // 11-04 (t2340u, smaller windows): opened straight into a mode, the Map bar's menus measure narrower (one row instead of two), so the
  // real Map layout (drawn map, full bar) is remembered per window size and reused by the other modes.
  const FK = "studio:mapfit:" + innerWidth + "x" + innerHeight;
  if (!MODES.length && last) try { localStorage.setItem(FK, JSON.stringify({ wv, wh, topMap, shdH, sy: scrollY })); } catch (e) { /* private */ }
  else if (MODES.length) { let c = null; try { c = JSON.parse(localStorage.getItem(FK) || "null"); } catch (e) { c = null; }
    if (c && c.wv > 0 && c.wh > 0) { wv = c.wv; wh = c.wh; topMap = c.topMap; shdH = c.shdH;
      fv.style.width = wv + "px"; fh.style.width = wh + "px"; cvv.style.width = wv + "px"; cvv.style.height = wv * 16 / 9 + "px"; cvh.style.width = wh + "px"; cvh.style.height = wh * 9 / 16 + "px"; } }
  for (const c of MODES) bd.classList.add(c);
  if (pnl && window.__fitRO) for (const e of pnl.children) if (!e.__fitObs) { e.__fitObs = 1; window.__fitRO.observe(e); }   // panel content (obs chips) settles later
  if (MODES.length) {
    SHD.forEach((e, i) => { e.style.minHeight = shdH[i] + "px"; });   // a mode that hides header buttons keeps the header height
    let d = topMap - (cvh.getBoundingClientRect().top + scrollY);
    if (d > 0.25) st.style.marginTop = d + "px";
    else if (d < -0.25 && pnl) { pnl.style.maxHeight = Math.max(24, pnl.getBoundingClientRect().height + d) + "px"; pnl.style.overflowY = "auto";
      d = topMap - (cvh.getBoundingClientRect().top + scrollY); if (Math.abs(d) > 0.25) st.style.marginTop = d + "px"; }
  }
  window.__fitTop = MODES.length ? topMap : null;
  window.__studioFit = { v: [wv, wv * 16 / 9], h: [wh, wh * 9 / 16] };
}
// ---- 11-01 2 PM (Benjamin t2041u/t2042u): hour scrubber under the 16:9 frame (every forecast hour the model data has: the viewer's
// own steps, same as the top slider, which it drives), a hover value readout on both frames (the viewer's readout(): same numbers
// and units as the map page), and the "Request a change" button moved off the 9:16 frame into the space under the 16:9 frame.
let scrubSync = () => {};
if (!CLEAN) {
  const fh = document.getElementById("fh"), hint = fh.querySelector(".shint"), stp = document.getElementById("step");
  const box = document.createElement("div"); box.id = "scrub";
  box.innerHTML = `<div class="sr"><button type="button" id="sprev" aria-label="Previous hour">&lsaquo;</button><div class="sw"><input type="range" id="hscrub" min="0" max="0" value="0" aria-label="Forecast hour"><div id="sticks"></div></div><button type="button" id="snext" aria-label="Next hour">&rsaquo;</button><b id="shour"></b></div>`;
  fh.insertBefore(box, hint);
  const sl = document.getElementById("hscrub"), tk = document.getElementById("sticks"), lab = document.getElementById("shour");
  const fwd = (type) => stp.dispatchEvent(new Event(type));
  sl.addEventListener("pointerdown", () => fwd("pointerdown"));
  for (const ev of ["pointerup", "pointercancel", "change"]) sl.addEventListener(ev, () => fwd("change"));
  sl.addEventListener("input", () => { stp.value = sl.value; fwd("input"); });
  document.getElementById("sprev").onclick = () => document.getElementById("prev").click();
  document.getElementById("snext").onclick = () => document.getElementById("next").click();
  let tkKey = "";
  scrubSync = () => {
    const R_ = S.runs[S.run]; if (!R_ || !R_.steps) return; const st = R_.steps, n = st.length, s = st[S.i] || {};
    sl.max = Math.max(0, n - 1); sl.value = S.i;
    lab.textContent = `F+${s.f}` + (s.valid_line ? `  \u00b7  ${s.valid_line.replace(/^Valid /, "")}` : "");
    const key = S.run + ":" + n; if (key === tkKey) return; tkKey = key;   // tick labels every 24 h (by forecast hour), rebuilt per run / new hours
    tk.innerHTML = st.map((x, i) => x.f % 24 === 0 && (x.f % 48 === 0 || st[n - 1].f <= 168) ? `<span style="left:calc(9px + (100% - 18px) * ${n > 1 ? i / (n - 1) : 0})">${x.f}</span>` : "").join("");
  };
  // hover readout: frame px -> map figure px (same camera as crop()) -> a pointer position on the hidden map -> viewer readout()
  const tip = document.createElement("div"); tip.id = "stip"; tip.hidden = true; document.body.appendChild(tip);
  for (const k of ["v", "h"]) {
    const f = F[k], cv = f.cv;
    cv.addEventListener("pointermove", (e) => {
      if (e.pointerType !== "mouse" || e.buttons || !last || MG.on || REC.on || PIN.mode || typeof readout !== "function") { tip.hidden = true; return; }
      const r = crop(k, getFr(k)), b = cv.getBoundingClientRect(), X = r.cx + ((e.clientX - b.left) * f.W / b.width - f.W / 2) / r.kk, Y = r.cy + ((e.clientY - b.top) * f.H / b.height - f.H / 2) / r.kk;
      if (X < r.px || Y < r.py || X > r.px + r.pw || Y > r.py + r.ph) { tip.hidden = true; return; }   // outside the map panel (wide view background)
      const m = document.getElementById("map"), mr = m.getBoundingClientRect(), LW = m._lw || m.width, LH = m._lh || m.height, vt = document.getElementById("tip");
      readout({ clientX: mr.left + X * mr.width / LW, clientY: mr.top + Y * mr.height / LH });
      if (!vt || vt.hidden || !vt.textContent) { tip.hidden = true; return; }
      tip.textContent = vt.textContent; vt.hidden = true; tip.hidden = false;
      tip.style.left = (e.clientX + 14) + "px"; tip.style.top = (e.clientY - 32) + "px";
    });
    cv.addEventListener("pointerleave", () => { tip.hidden = true; });
    cv.addEventListener("pointerdown", () => { tip.hidden = true; });
  }
  // Request a change: 11-03 (Benjamin t2244u) reqbox.js puts #rqb in the top menu bar (it was in a slot under the 16:9 frame)
}
if (!CLEAN) {   // Studio: Map | Meteogram switch (first in the menu bar) + the meteograms page's pickers in a small iframe
  const bar = document.getElementById("bar"), sw = document.createElement("label"); sw.id = "smodel";
  sw.innerHTML = `Studio <select id="smode"><option value="map">Map</option><option value="mg">Meteogram</option><option value="obs">Observations</option><option value="pass">Pass Forecaster</option></select>`; bar.insertBefore(sw, bar.firstChild);
  const pnl = document.createElement("div"); pnl.id = "mgp"; bar.after(pnl);
  const sel = document.getElementById("smode"); sel.value = MG.on ? MG.kind : "map"; saveMode(sel.value);
  let fr_ = null, poll = 0;
  const grab = () => { try {
    const d = fr_.contentDocument, im = d && d.getElementById("meteo-img"), w = fr_.contentWindow;
    if (!im || !w || !w.MG_DONE) return; const em = d.getElementById("meteo-empty"), src = im.hidden ? "" : im.src;
    const h = w.location.hash; if (h) localStorage.setItem("studio:mghash", h);
    if (src && im.complete && im.naturalWidth && (src !== MG.src || MG.img !== im)) { MG.img = im; MG.src = src + h; MG.msg = ""; renderAll(); }
    else if (!src && em && !em.hidden && MG.msg !== em.textContent) { MG.img = null; MG.src = ""; MG.msg = (em.querySelector(".empty-title") || em).textContent; renderAll(); }
  } catch (e) { /* iframe loading */ } };
  const css = `.mast,.menubar,.skip,.meteo-grid,.colophon{display:none!important}body{margin:0;padding:6px 10px!important;background:#1d2027!important;min-height:0!important}.controls{margin:0!important;padding:0!important;gap:10px 18px!important}`;
  // Observations (11-03, t2192u): the live obs module (obs/, same as the viewer's Observations window) runs in the panel with its
  // region / layer chips and Refresh; its map canvas is drawn off-screen at a fixed 1600 x 1600 CSS px and both frames crop it
  let ob_ = null, obsLoad = null, osig = "";
  const ograb = () => { const S_ = typeof Obs !== "undefined" && Obs._state, cv_ = document.getElementById("obs-canvas"); if (!S_ || !cv_ || !cv_.width) return;
    const sig = [S_.loaded, S_.view, S_.cx, S_.cy, S_.k, [...S_.on].join(), cv_.width, cv_.height, S_.dayCAloaded, S_.st.length, S_.raf ? 1 : 0, S_.imgSig || ""].join("|");
    if (sig !== osig || MG.img !== cv_) { osig = sig; MG.img = S_.loaded ? cv_ : null; MG.msg = S_.loaded ? "" : "Loading observations\u2026"; if (!REC.on && !PV.on) renderAll(); } };
  let pp_ = null; const pfLoad = async () => {   // Pass Forecaster: model picker in the panel, table rebuilt from viewer.js passTable
    if (!window.studioPassRuns || !S.man) { setTimeout(pfLoad, 300); return; }
    const runs = window.studioPassRuns(); if (!pp_) { pp_ = document.createElement("div"); pp_.id = "pfp"; pnl.appendChild(pp_); }
    let want = localStorage.getItem("studio:passrun") || ""; const wm = want.split("/")[0];
    if (!runs.some((r) => r[0] === want)) want = (runs.find((r) => r[0].split("/")[0] === wm) || runs[0] || [""])[0];   // same model, newest run
    pp_.innerHTML = `<label>Model <select id="pfrun">${runs.map(([r, l]) => `<option value="${r}"${r === want ? " selected" : ""}>${l}</option>`).join("")}</select></label><span class="mp-note">Same table as the map page's Pass Forecaster. Save PNG on each frame.</span>`;
    document.getElementById("pfrun").onchange = (e) => pfGo(e.target.value); pfGo(want); };
  const pfGo = async (run) => { if (!run) { PF.rows = null; PF.msg = "No model run with pass forecasts yet."; renderAll(); return; }
    PF.run = run; PF.rows = null; PF.msg = ""; localStorage.setItem("studio:passrun", run); renderAll();
    const box = document.createElement("div"), ok = await window.studioPassBuild(run, box).catch(() => false); if (PF.run !== run || !PASSM()) return;
    PF.rows = ok ? pfParse(box) : null; if (!PF.rows) PF.msg = (box.textContent || "").trim() || "This run has no pass forecast."; renderAll(); };
  const setMode = (mode) => {
    const wasPass = PASSM(); if (mode === "pass") { MG.on = true; MG.kind = "pass"; MG.img = null; saveMode("pass"); clearInterval(poll);
      document.body.classList.remove("mgmode", "obsmode"); document.body.classList.add("passmode"); if (typeof Obs !== "undefined" && Obs.hide) Obs.hide();
      pfLoad(); renderAll(); fitFrames(); return; }
    document.body.classList.remove("passmode"); if (wasPass) { MG.img = null; MG.kind = "mg"; }
    const on = mode === "mg" || mode === "obs", wasObs = OBSM(); if (on && MG.kind !== mode) { MG.img = null; MG.src = ""; MG.msg = ""; }
    MG.on = on; if (on) MG.kind = mode; saveMode(on ? mode : "map"); clearInterval(poll);
    document.body.classList.toggle("mgmode", on && mode === "mg"); document.body.classList.toggle("obsmode", on && mode === "obs");
    if (wasObs && !OBSM() && typeof Obs !== "undefined") { Obs.hide(); PIN.show = false; PIN.mode = null; }
    if (on && mode === "obs") {
      if (!ob_) { ob_ = document.createElement("div"); ob_.id = "obsp"; ob_.innerHTML = `<div id="obs-root"></div>`; pnl.appendChild(ob_); }
      obsLoad = obsLoad || new Promise((ok, bad) => {
        const l = document.createElement("link"); l.rel = "stylesheet"; l.href = "obs/obs.css"; document.head.appendChild(l);
        const sc = document.createElement("script"); sc.src = "obs/obs.js"; sc.onerror = bad; document.body.appendChild(sc);
        // 11-03: radar + GOES-West layers (obs/obsimg.js, off by default); the obs map still opens if it fails to load
        sc.onload = () => { const s2 = document.createElement("script"); s2.src = "obs/obsimg.js?v=20261104b"; s2.onload = ok; s2.onerror = ok; document.body.appendChild(s2); }; });
      MG.msg = "Loading observations\u2026"; osig = "";
      obsLoad.then(() => { if (OBSM()) { Obs.show(); fitFrames(); } }, () => { obsLoad = null; MG.msg = "Observations could not load."; renderAll(); });
      poll = setInterval(ograb, 400);
      renderAll(); fitFrames(); return;
    }
    if (on && !fr_) { fr_ = document.createElement("iframe"); fr_.id = "mgf"; fr_.title = "Meteogram pickers";
      fr_.src = "meteograms.html" + (localStorage.getItem("studio:mghash") || "#s=eps&w=seattle&p=eps_gust_members");
      fr_.onload = () => { try { const st = fr_.contentDocument.createElement("style"); st.textContent = css; fr_.contentDocument.head.appendChild(st); } catch (e) { /* not ready */ } };
      pnl.appendChild(fr_); }
    if (on) poll = setInterval(grab, 300);
    renderAll(); if (!on && last && window.onStudioDraw) window.onStudioDraw(last.cv, last.cur, last.step); fitFrames();
  };
  // 11-04 (Benjamin t2296u "if I click one of the passes in studio mode, it goes to that pass meteogram"): a click / tap on a pass row
  // opens Studio > Meteogram on that pass, same model (the meteogram page's newest run = the Pass Forecaster's run). Hover = a DOM
  // outline over the canvas (never drawn into the frame, so Save PNG and recordings stay clean). A "Back to Pass Forecaster" button sits
  // in the menu panel; studio:mgfrom keeps it across a refresh.
  const PFSEC = { ifs9: "ifs" }, pfProd = (m) => (m === "eps" || m === "aens") ? `${m}_snow_plume` : `${m}_winter_summary`;
  const pfRow = (k, e) => { const f = F[k], L = f.pfL; if (!PASSM() || !PF.rows || !L || !L.names) return -1; const b = f.cv.getBoundingClientRect();
    const X = (e.clientX - b.left) * f.W / b.width, Y = (e.clientY - b.top) * f.H / b.height, i = Math.floor((Y - L.y0) / L.rh);
    return X >= L.x && X <= L.x + L.w && i >= 0 && i < L.names.length && L.names[i] ? i : -1; };
  const hov = document.createElement("div"); hov.id = "pfhov"; hov.hidden = true; document.body.appendChild(hov);
  const hovAt = (k, i) => { const f = F[k], L = f.pfL, b = f.cv.getBoundingClientRect(), s = b.width / f.W;
    Object.assign(hov.style, { left: b.left + L.x * s + "px", top: b.top + (L.y0 + i * L.rh) * s + "px", width: L.w * s + "px", height: L.rh * s + "px" }); hov.hidden = false; };
  const backBtn = document.createElement("button"); backBtn.type = "button"; backBtn.id = "pfback"; backBtn.textContent = "\u2190 Back to Pass Forecaster";
  const backSync = () => { const on = MG.on && MG.kind === "mg" && localStorage.getItem("studio:mgfrom") === "pass"; backBtn.hidden = !on; if (on && backBtn.parentNode !== pnl) pnl.insertBefore(backBtn, pnl.firstChild); };
  backBtn.onclick = () => { localStorage.removeItem("studio:mgfrom"); sel.value = "pass"; setMode("pass"); backSync(); };
  const pfOpen = (name) => { const m = PF.run.split("/")[0], h = "#" + new URLSearchParams({ s: PFSEC[m] || m, w: name, p: pfProd(PFSEC[m] || m) }).toString();
    localStorage.setItem("studio:mghash", h); localStorage.setItem("studio:mgfrom", "pass"); hov.hidden = true;
    if (fr_) { MG.img = null; MG.src = ""; try { fr_.contentWindow.location.hash = h; } catch (e) { fr_.src = "meteograms.html" + h; } }
    MG.kind = "mg"; sel.value = "mg"; setMode("mg"); backSync(); window.__pfOpened = { name, hash: h }; };
  for (const k of ["v", "h"]) { const cv = F[k].cv; let dn = null;
    cv.addEventListener("pointermove", (e) => { if (!PASSM()) return; const i = REC.on ? -1 : pfRow(k, e); cv.style.cursor = i >= 0 ? "pointer" : (PASSM() ? "default" : ""); if (i >= 0 && e.pointerType === "mouse") hovAt(k, i); else hov.hidden = true; });
    cv.addEventListener("pointerleave", () => { hov.hidden = true; if (PASSM()) cv.style.cursor = ""; });
    cv.addEventListener("pointerdown", (e) => { dn = PASSM() && !REC.on ? { x: e.clientX, y: e.clientY, i: pfRow(k, e) } : null; });
    cv.addEventListener("pointerup", (e) => { const d0 = dn; dn = null; if (!d0 || d0.i < 0 || !PASSM() || REC.on) return; if (Math.hypot(e.clientX - d0.x, e.clientY - d0.y) > 12) return;
      const i = pfRow(k, e); if (i === d0.i) pfOpen(F[k].pfL.names[i]); }); }
  addEventListener("scroll", () => { hov.hidden = true; }, true); addEventListener("resize", () => { hov.hidden = true; });
  sel.addEventListener("change", () => { localStorage.removeItem("studio:mgfrom"); backSync(); });
  window.__pfOpen = pfOpen;
  sel.onchange = () => setMode(sel.value);
  if (MG.on) setMode(MG.kind);
  backSync();
}
if (!CLEAN) {
  let fq = 0; const fitSoon = () => { cancelAnimationFrame(fq); fq = requestAnimationFrame(fitFrames); };
  addEventListener("resize", fitSoon); addEventListener("orientationchange", fitSoon);
  if ("ResizeObserver" in window) { new ResizeObserver(fitSoon).observe(document.getElementById("bar")); window.__fitRO = new ResizeObserver(fitSoon); }
  if (document.fonts && document.fonts.ready) document.fonts.ready.then(fitSoon);
  setInterval(() => { if (window.__fitTop != null && innerWidth > 820 && Math.abs(F.h.cv.getBoundingClientRect().top + scrollY - window.__fitTop) > 0.5) fitSoon(); }, 400);   // panel content that settles late
  fitFrames();
}
// 11-04 (t2335u guard): read-only state for the refresh regression test (refresh_test.py): what each frame shows right now
window.__studioQA = () => ({ mode: PASSM() ? "pass" : MG.on ? MG.kind : "map", mg: MG.kind === "mg" ? (MG.src.split("#")[1] || "") : "", pass: PF.run, passRows: PF.rows ? PF.rows.length : 0,
  pfL: F.h.pfL ? { x: F.h.pfL.x, y0: F.h.pfL.y0, w: F.h.pfL.w, rh: F.h.pfL.rh, names: F.h.pfL.names } : null, W: F.h.W, fr: { v: getFr("v"), h: getFr("h") } });
})();
