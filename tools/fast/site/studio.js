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
const MODES_OK = ["map", "mg", "obs", "pass", "wafc", "alert", "cmp", "web"];
// 11-05 (Benjamin: refresh on Observations Satellite jumped to the underlying map product, e.g. Integrated Vapor Transport):
// mode is still address-first (?smode=). saveMode also writes sessionStorage, but MODE0 used to ignore it — so a refresh whose
// address lost smode (iOS replaceState limit, or a write that rebuilt the query without it) fell back to Map and showed the
// previous map product under the satellite view. On a reload only, fall back to this tab's sessionStorage mode; a bare
// studio.html navigate (bookmark / new open) still starts on Map (t2337u).
const MODE0 = (() => { const u = SQ.get("smode"); if (MODES_OK.includes(u)) return u;
  let nav = ""; try { nav = (performance.getEntriesByType("navigation")[0] || {}).type || ""; } catch (e) { /* old webkit */ }
  if (nav === "reload") { try { const s = sessionStorage.getItem("studio:mode"); if (MODES_OK.includes(s)) return s; } catch (e) { /* private */ } }
  return "map"; })();
const saveMode = (m) => { try { sessionStorage.setItem("studio:mode", m); } catch (e) { /* private mode */ }
  if (CLEAN) return; try { const u = new URL(location); if (m === "map") u.searchParams.delete("smode"); else u.searchParams.set("smode", m); history.replaceState(null, "", u); } catch (e) { /* replaceState limit */ } };
const MG_KINDS = ["obs", "pass", "wafc", "alert", "cmp", "web"];
const MG = { on: !CLEAN && ["mg", ...MG_KINDS].includes(MODE0), kind: MG_KINDS.includes(MODE0) ? MODE0 : "mg", img: null, src: "" };
// 11-04 (t2310u/t2311u "my fancy Washington forecast maps ... into studio view", own tab): MG.kind "wafc" = the WA Maps page (wamaps.html: the
// posted-style NBM lows / highs, gusts, precip, snow) in a small panel iframe. Each frame crops that canvas with the same
// framing as the other Studio products (getFr / setFr, separate portrait and landscape, zoom bar, drag, reset). Drawn at 2x (PSS)
// so Save PNG stays 2160x3840 / 3840x2160. The map carries its own title, scale, logo and credits, so Studio adds nothing on top.
const WAFCM = () => MG.on && MG.kind === "wafc";
const PASSM = () => MG.on && MG.kind === "pass";
const PF = { run: "", rows: null, msg: "" };
const OBSM = () => MG.on && MG.kind === "obs";
const ALERTM = () => MG.on && MG.kind === "alert";
// Active Alerts zoom range (t2558u / t2559u): 1.5x further out, 2x further in than the old 1–2.5 map range.
const ALERT_ZMIN = 1 / 1.5, ALERT_ZMAX = 5;
const alertZ = (z) => Math.min(ALERT_ZMAX, Math.max(ALERT_ZMIN, +z || 1));
const CMPM = () => MG.on && MG.kind === "cmp";   // 11-07: Compare (compare.html) drawn into both frames
const WEBM = () => MG.on && MG.kind === "web";   // 11-07: any page, framed with the same zoom bar and drag as the maps
let cmpFrame = null;
const CMP = { L: null, R: null, view: { L: null, R: null }, play: 0 };
const WEB = { url: "" , mir: null };   // mir: live tab capture showing the 16:9 page in the 9:16 frame (Mirror)
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
  if (OBSM() || ALERTM()) { const f = F[k], iw = IW(MG.img), ih = IH(MG.img); return { cx: iw / 2, cy: ih / 2, k0: Math.max(f.W / iw, f.H / ih) }; }   // obs/alert: cover — map fills the frame
  const f = F[k], iw = IW(MG.img), ih = IH(MG.img);
  if (WAFCM()) { const k0 = Math.min(f.W / iw, f.H / ih); return { cx: iw / 2, cy: ih / 2, k0 }; }   // WA forecast: whole map centred; zoom 1 is that fit
  const padX = f.pad * 0.5, top = k === "v" ? 200 : 60, bot = k === "v" ? 200 : 70;
  const k0 = Math.min((f.W - 2 * padX) / iw, (f.H - top - bot) / ih);
  return { cx: iw / 2, cy: ih / 2 - ((top + (f.H - bot)) / 2 - f.H / 2) / k0, k0 };
}
function webBase(k) { const f = F[k]; return { cx: f.W / 2, cy: f.H / 2, k0: 1 }; }   // the page lays out at the frame's own pixels
function base(k) {   // camera at dx = dy = 0, zoom 1: centre (figure px) and scale (output px per figure px)
  if (WEBM()) return webBase(k);
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
// t2827u: 9:16 and 16:9 each keep their own pan/zoom (fr via studio:v:… / studio:h:…).
// Do not move the shared Obs camera (Obs._state / OZ) — that redrew one bitmap both frames crop, so
// dragging or zooming one view shifted the other.
function obsZoom(k, fr, z) {
  fr.zoom = Math.min(2.5, Math.max(0.05, +z || 1)); return fr;
}
function obsPan(k, fr) {
  const r = crop(k, fr); fr.dx = (r.bx - r.cx) * r.kk; fr.dy = (r.by - r.cy) * r.kk; return fr;
}
const obsZv = (fr) => Math.round((fr.zoom || 1) * 100);
function crop(k, fr) {   // source rect (map bitmap px) for frame k: base camera, then zoom / pan; the panel stays covering the frame when it
  // can, and when it is smaller than the frame (wide view) it stays wholly in the frame (the rest is background)
  if (WEBM()) {   // page is the frame itself: same 1–2.5× zoom and drag clamp as a meteogram (some of the page stays in view)
    const f = F[k], B = webBase(k), kk = B.k0 * Math.max(1, fr.zoom || 1), cl = (v, a, b) => Math.min(b, Math.max(a, v));
    const cx = cl(B.cx - (fr.dx || 0) / kk, -f.W / kk / 2 + 40 / kk, f.W + f.W / kk / 2 - 40 / kk);
    const cy = cl(B.cy - (fr.dy || 0) / kk, -f.H / kk / 2 + 40 / kk, f.H + f.H / kk / 2 - 40 / kk);
    return { kk, cx, cy, bx: B.cx, by: B.cy, sx: 0, sy: 0, sw: f.W / kk, sh: f.H / kk, px: 0, py: 0, pw: f.W, ph: f.H, rs: 1 };
  }
  if (ALERTM() && MG.img) {   // alert: cover fill; pan/zoom (z may be <1 — letterbox with ocean, clamp when view exceeds bitmap)
    const B = base(k), z = alertZ(fr.zoom || 1), kk = B.k0 * z, iw = IW(MG.img), ih = IH(MG.img), cl = (v, a, b) => Math.min(b, Math.max(a, v));
    const hw = F[k].W / kk / 2, hh = F[k].H / kk / 2;
    const cx = hw >= iw / 2 ? iw / 2 : cl(B.cx - (fr.dx || 0) / kk, hw, iw - hw);
    const cy = hh >= ih / 2 ? ih / 2 : cl(B.cy - (fr.dy || 0) / kk, hh, ih - hh);
    return { kk, cx, cy, bx: B.cx, by: B.cy, sx: 0, sy: 0, sw: F[k].W / kk, sh: F[k].H / kk, px: 0, py: 0, pw: iw, ph: ih, rs: 1 };
  }
  if (OBSM() && MG.img) {   // obs: cover fill; pan/zoom (z may be <1 — letterbox, do not move the shared Obs map)
    const B = base(k), z = Math.min(2.5, Math.max(0.05, fr.zoom || 1)), kk = B.k0 * z, iw = IW(MG.img), ih = IH(MG.img), cl = (v, a, b) => Math.min(b, Math.max(a, v));
    const hw = F[k].W / kk / 2, hh = F[k].H / kk / 2;
    const cx = hw >= iw / 2 ? iw / 2 : cl(B.cx - (fr.dx || 0) / kk, hw, iw - hw);
    const cy = hh >= ih / 2 ? ih / 2 : cl(B.cy - (fr.dy || 0) / kk, hh, ih - hh);
    return { kk, cx, cy, bx: B.cx, by: B.cy, sx: 0, sy: 0, sw: F[k].W / kk, sh: F[k].H / kk, px: 0, py: 0, pw: iw, ph: ih, rs: 1 };
  }
  if (MG.on && MG.img) {   // meteogram / WA forecast: pan freely while some of the chart stays in the frame
    const B = base(k), kk = B.k0 * Math.max(1, fr.zoom || 1), iw = IW(MG.img), ih = IH(MG.img), cl = (v, a, b) => Math.min(b, Math.max(a, v));
    const cx = cl(B.cx - (fr.dx || 0) / kk, -F[k].W / kk / 2 + 40 / kk, iw + F[k].W / kk / 2 - 40 / kk), cy = cl(B.cy - (fr.dy || 0) / kk, -F[k].H / kk / 2 + 40 / kk, ih + F[k].H / kk / 2 - 40 / kk);
    return { kk, cx, cy, bx: B.cx, by: B.cy, sx: 0, sy: 0, sw: F[k].W / kk, sh: F[k].H / kk, px: 0, py: 0, pw: iw, ph: ih, rs: 1 };
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
function ssFit(f, s) {
  const cv = f.cv, w = f.W * s, h = f.H * s;
  if (cv.width !== w || cv.height !== h) {
    // Lock the on-screen box first. A 2160x3840 / 3840x2160 bitmap with width:auto
    // becomes the flex min-content, overflows a 1920x1080 window, and the scrollbar
    // resize starts another alert paint before the first one can finish.
    if (cv.style && !cv.style.width) {
      const bw = cv.clientWidth, bh = cv.clientHeight;
      if (bw > 2 && bh > 2) { cv.style.width = bw + "px"; cv.style.height = bh + "px"; }
    }
    cv.width = w; cv.height = h;
  }
  f.ss = s;
}
function frameTx(c, f) { const z = (f && f.ss) || 1; c.setTransform(z, 0, 0, z, 0, 0); return z; }
// Opaque samples on the bitmap itself. Width/height and __studioAlert can all be ready while every pixel is still transparent.
function frameInk(cv) {
  if (!cv || !cv.width || !cv.height) return 0;
  const c = cv.getContext("2d");
  if (!c || (c.isContextLost && c.isContextLost())) return 0;
  const w = cv.width, h = cv.height;
  // One read of a few pixels. A grid of getImageData calls on the 2x frame flushes
  // the GPU once per sample; the refresh guard polls this and would stall the paint.
  try {
    const img = c.getImageData(0, 0, Math.min(w, 8), Math.min(h, 8)).data;
    let n = img[3] > 8 ? 1 : 0;
    const mid = c.getImageData(w >> 1, h >> 1, 1, 1).data;
    if (mid[3] > 8) n += 2;
    const br = c.getImageData(Math.max(0, w - 2), Math.max(0, h - 2), 1, 1).data;
    if (br[3] > 8) n += 4;
    return n;
  } catch (e) { return 0; }
}
function sharpShadow(c, k) { const z = ctxS(c); c.shadowColor = "rgba(0,0,0,0.92)"; c.shadowBlur = 1.5 * z; c.shadowOffsetX = (k === "v" ? 3 : 2.5) * z; c.shadowOffsetY = (k === "v" ? 3 : 2.5) * z; }
// 11-02 6:20 PM (Benjamin t2111u "drop shadow ... a little more pronounced with a bit of a fade so it doesn't look messy"): overlay text,
// badges and bars are drawn (with the tight sharp core shadow above) into an off-screen layer, then that layer goes onto the frame once
// with a soft short falloff shadow: sharp core + gentle fade, one pass, so overlapping glyph shadows never stack up into smudges.
function ovLayer(f) { const o = f.ov || (f.ov = document.createElement("canvas")), z = f.ss || 1; if (o.width !== f.W * z || o.height !== f.H * z) { o.width = f.W * z; o.height = f.H * z; }
  const oc = o.getContext("2d"); oc.setTransform(z, 0, 0, z, 0, 0); oc.clearRect(0, 0, f.W, f.H); return oc; }
function ovPut(c, f, k) {
  const src = f.ov; if (!src || !src.width) return;
  c.save();
  c.shadowColor = "rgba(0,0,0,0)"; c.shadowBlur = 0; c.shadowOffsetX = 0; c.shadowOffsetY = 0;
  // Soft halo at the logical frame size (1080x1920 / 1920x1080). Blurring the 2x backing
  // store stalled Active Alerts past the refresh guard, and a live shadowBlur on that
  // same draw cleared the store on some GPUs. The sharp text is the 2x overlay on top.
  const halo = f.ovHalo || (f.ovHalo = document.createElement("canvas"));
  if (halo.width !== f.W || halo.height !== f.H) { halo.width = f.W; halo.height = f.H; }
  const hc = halo.getContext("2d");
  hc.setTransform(1, 0, 0, 1, 0, 0); hc.globalAlpha = 1; hc.globalCompositeOperation = "source-over";
  hc.clearRect(0, 0, f.W, f.H);
  hc.shadowColor = "rgba(0,0,0,0.55)"; hc.shadowBlur = k === "v" ? 4 : 3; hc.shadowOffsetX = 0; hc.shadowOffsetY = k === "v" ? 0.5 : 0.4;
  hc.drawImage(src, 0, 0, f.W, f.H);
  hc.shadowColor = "rgba(0,0,0,0)"; hc.shadowBlur = 0; hc.shadowOffsetX = 0; hc.shadowOffsetY = 0;
  c.drawImage(halo, 0, 0, f.W, f.H);
  c.drawImage(src, 0, 0, f.W, f.H);
  c.restore();
}
// One scaled blit of the alert bitmap, in device pixels, with no shadow and no second copy.
// Tiling it into a 4096 canvas and then onto the 2x frame was a full extra pass per frame.
function drawAlertMap(c, img, dx, dy, dw, dh) {
  const iw0 = IW(img), ih0 = IH(img);
  if (!(iw0 > 0 && ih0 > 0 && dw > 0 && dh > 0)) return;
  const z = (c.getTransform ? c.getTransform().a : 1) || 1;
  c.save();
  c.setTransform(1, 0, 0, 1, 0, 0);
  c.imageSmoothingEnabled = true; c.imageSmoothingQuality = "low";
  c.shadowColor = "rgba(0,0,0,0)"; c.shadowBlur = 0; c.shadowOffsetX = 0; c.shadowOffsetY = 0;
  c.drawImage(img, dx * z, dy * z, dw * z, dh * z);
  c.restore();
}
function noShadow(c) { c.shadowColor = "rgba(0,0,0,0)"; c.shadowBlur = 0; c.shadowOffsetX = 0; c.shadowOffsetY = 0; }
function pill(c, x, y, txt, size, bg, fg) {
  c.font = `800 ${size}px Montserrat`; const w = c.measureText(txt).width + size * 0.9, h = size * 1.55;
  c.fillStyle = bg; c.beginPath(); c.roundRect ? c.roundRect(x, y, w, h, h / 2) : c.rect(x, y, w, h); c.fill();
  c.fillStyle = fg; c.textBaseline = "middle"; c.fillText(txt, x + size * 0.45, y + h / 2 + 1); c.textBaseline = "alphabetic"; return w;
}
function colorbar(c, P, x, y, w, h, size) {
  const L = P.levels, C = P.colors; if (!L || !C || L.length < 2) return false;
  // t2848u: ensemble low-centers share the website's P.core swatch (navy/black "within 25 km" = 100% core). Same fractions as viewer.js keyBox / drawViewerKey.
  let barW = w, coreX = 0, coreW = 0;
  if (P.core && P.core.color) {
    const full = 0.976 - 0.150, barF = 0.872 - 0.150, gapF = 0.888 - 0.872, swF = 0.088;
    barW = w * barF / full; coreX = x + w * (barF + gapF) / full; coreW = w * swF / full;
  }
  const lo = L[0], hi = L[L.length - 1], n = L.length - 1;   // equal-width bins (like the site's keys), ticks placed inside their bin
  // 11-01 9:16 AM (Benjamin t1996u "the numbers need to be fixed"): optional per-bin cell widths P.kw (max wave: 75-77.5 and 77.5-80 half a cell
  // each, so 75-80 is one cell like the other 5 ft steps and 75 / 80 / 85 stay evenly spaced on their color edges)
  const KW = Array.isArray(P.kw) && P.kw.length === n ? P.kw : null, CW = [0]; for (let i = 0; i < n; i++) CW.push(CW[i] + (KW ? KW[i] : 1));
  const X = (v) => { let i = 0; while (i < n - 1 && v > L[i + 1]) i++; const fr = Math.min(1, Math.max(0, (v - L[i]) / ((L[i + 1] - L[i]) || 1)));
    return x + (CW[i] + fr * (CW[i + 1] - CW[i])) / CW[n] * barW; };
  const sh = [c.shadowColor, c.shadowBlur, c.shadowOffsetX, c.shadowOffsetY];
  if (sh[1] || sh[2] || sh[3]) { c.fillStyle = "#000"; c.fillRect(x, y, barW, h); if (coreW) c.fillRect(coreX, y, coreW, h); c.shadowColor = "rgba(0,0,0,0)"; }
  for (let i = 0; i < C.length && i < L.length - 1; i++) { c.fillStyle = C[i]; c.fillRect(Math.floor(X(L[i])), y, Math.ceil(X(L[i + 1]) - X(L[i])) + 1, h); }
  c.strokeStyle = "rgba(255,255,255,0.55)"; c.lineWidth = 1.5; c.strokeRect(x, y, barW, h);
  if (coreW) { c.fillStyle = P.core.color; c.fillRect(coreX, y, coreW, h); c.strokeRect(coreX, y, coreW, h); }
  c.shadowColor = sh[0];
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
  if (coreW) {
    const lab = `within ${P.core.km || 25} km`;
    let zs = size; c.font = `700 ${zs}px Montserrat`; c.textAlign = "center"; c.fillStyle = "#e9ecf1";
    while (zs > 10 && c.measureText(lab).width > coreW - 4) { zs -= 0.5; c.font = `700 ${zs}px Montserrat`; }
    c.fillText(lab, coreX + coreW / 2, y + h + size * 1.35);
  }
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
// 11-04 (Benjamin t2353u "move the F+number a bit to the left, my face will be covering it"): one shared setting for the top-right
// badge (F+ hour / LIVE) and the tr corner logo under it, so every Studio mode (and any new one) inherits it. Fraction of frame width
// kept clear at the right edge for his face camera (~right 10 %): 13 % of width = 250 px at 1920 (16:9), 140 px at 1080 (9:16).
const BADGE_FACE_CLEAR = 0.13;
const badgeRight = (k) => F[k].W - F[k].pad - Math.round(F[k].W * BADGE_FACE_CLEAR);
function cornerBox(k, badgeBot, headBot, cbY) {
  const f = F[k], p = BR.cpos;
  if (p === "tr" || p === "tl") { const s = Math.round(f.W * (k === "v" ? 0.10 : 0.08)), gap = k === "v" ? 18 : 14; return { s, x: p === "tl" ? f.pad : badgeRight(k) - s, y: Math.round((p === "tl" ? headBot : badgeBot) + gap) }; }
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
  const f = F[k], step = last && last.step, lg = getLogo(), h = k === "v" ? 150 : 118, w = k === "v" ? f.W - 2 * f.pad : 860, x = f.pad, y = f.H - f.bot - h - (k === "v" ? 40 : 26);
  c.save(); c.fillStyle = "rgba(13,15,19,0.84)"; c.beginPath(); c.roundRect ? c.roundRect(x, y, w, h, 16) : c.rect(x, y, w, h); c.fill();
  c.fillStyle = "#2f8cff"; c.fillRect(x, y + 14, 8, h - 28);
  let tx = x + 28; const ls = h - 30;
  if (lg) { c.drawImage(lg, tx, y + 15, ls, ls); tx += ls + 22; }
  const cmpWhen = CMPM() ? (CMP.view.R || CMP.view.L) : null;
  const l1 = BR.storm || BR.title || (cmpWhen ? cmpHeadTitle() : (last && last.cur.P.title)) || "";
  const l2 = cmpWhen ? [cmpWhen.site, cmpWhen.step && String(cmpWhen.step.valid_line || "").replace(/^Valid /, "")].filter(Boolean).join("  \u00b7  ") : (step ? `${runText()} \u00b7 ${ptTime(step.valid, { weekday: "short", month: "short", day: "numeric", hour: "numeric" })} PT` : "");
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
  const OI = OBSM() ? obsInfo() : null, words = (BR.title || BR.storm || (OI ? OI.title : (CMPM() ? cmpHeadTitle() : last.cur.P.title))).split(" "), maxW = f.W - 2 * f.pad, lines = []; let line = "";
  for (const w_ of words) { const t = line ? line + " " + w_ : w_; if (c.measureText(t).width > maxW && line) { lines.push(line); line = w_; } else line = t; } lines.push(line);
  lines.slice(0, 3).forEach((t, i) => c.fillText(t, cx, y + i * (k === "v" ? 86 : 88))); y += (Math.min(3, lines.length) - 1) * (k === "v" ? 86 : 88) + (k === "v" ? 80 : 74);
  if (BR.storm && BR.title) { c.font = `800 ${k === "v" ? 48 : 46}px Montserrat`; c.fillStyle = "#ffc24d"; c.fillText(BR.storm, cx, y); y += k === "v" ? 70 : 64; }
  c.font = `600 ${k === "v" ? 38 : 36}px Montserrat`; c.fillStyle = "#cfd3da";
  if (OI) { c.fillText(`Station reports \u00b7 ${OI.when}`, cx, y); c.restore(); return; }
  if (CMPM()) { const when = CMP.view.R || CMP.view.L; c.fillText(when ? `${when.site}  \u00b7  ${when.title}` : "Compare", cx, y); c.restore(); return; }
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
  f.lowKeyBox = [x0 - pd, y0 - pd, x0 + w + pd, y0 + tot + pd];
  c.restore();
}
// ---- Observations in Studio (11-03, t2192u): same header / badge / credit style as the maps; the obs module's own map is the picture
// Select the deepest member centre inside THIS frame's crop, not the source view or the ensemble mean.
function strongestMember(c, f, k, cur, r, headBot, cbY) {
  const scale = f.W / r.sw, points = [];
  for (const o of cur.memberLows || []) {
    if (![o.x, o.y, o.mb].every(Number.isFinite)) continue;
    const x = (o.x * r.rs - r.sx) * scale, y = (o.y * r.rs - r.sy) * scale;
    if (x >= 0 && y >= 0 && x <= f.W && y <= f.H) points.push({ ...o, x, y });
  }
  const T = points.reduce((a, b) => !a || b.mb < a.mb ? b : a, null);
  window.__studioStrongest = window.__studioStrongest || {};
  window.__studioStrongest[k] = T ? { ...T, run: cur.run, frame: cur.f } : null;
  if (!T) return;
  c.save(); noShadow(c);
  c.beginPath(); c.arc(T.x, T.y, 9, 0, 2 * Math.PI); c.strokeStyle = "#fff"; c.lineWidth = 5; c.stroke();
  c.strokeStyle = "#0b0d12"; c.lineWidth = 2; c.stroke();
  const fs = k === "v" ? 17 : 15, text = `${Math.round(T.mb)} mb${T.num != null ? ` · Mem ${T.num}` : ""}`;   // t2767u: no prefix, no bar
  c.font = `800 ${fs}px Montserrat`;
  const w = c.measureText(text).width, pad = 8, h = fs + 2 * pad;
  const blocks = [f.hdr, f.badge, f.lowKeyBox, [0, cbY - 45, f.W, f.H]].concat(window.__studioTownBoxes || []).filter(Boolean);
  const overlap = (a, b) => Math.max(0, Math.min(a[2], b[2]) - Math.max(a[0], b[0])) * Math.max(0, Math.min(a[3], b[3]) - Math.max(a[1], b[1]));
  let best;
  for (const gap of [16, 45, 80, 125]) for (const [sx, sy] of [[1,-1],[-1,-1],[1,1],[-1,1]]) {
    const x = Math.max(pad, Math.min(f.W - w - 3 * pad, sx > 0 ? T.x + gap : T.x - gap - w - 2 * pad));
    const y = Math.max(pad, Math.min(f.H - h - pad, sy < 0 ? T.y - gap - h : T.y + gap));
    const box = [x, y, x + w + 2 * pad, y + h], cost = blocks.reduce((v, b) => v + overlap(box, b), 0);
    if (!best || cost < best.cost) best = { x, y, box, cost };
    if (!cost) break;
  }
  c.beginPath(); c.moveTo(T.x, T.y); c.lineTo(Math.max(best.x, Math.min(best.box[2], T.x)), Math.max(best.y, Math.min(best.box[3], T.y)));
  c.strokeStyle = "#fff"; c.lineWidth = 4; c.stroke(); c.strokeStyle = "#0b0d12"; c.lineWidth = 1.5; c.stroke();
  // t2767u (Benjamin): no black bar; t2773u: ~68% size (17/15 px, was 25/22); bold white text with a dark halo like the other map labels (ring marker + leader kept)
  c.textAlign = "left"; c.textBaseline = "middle"; c.lineJoin = "round"; c.strokeStyle = "#0b0d12"; c.lineWidth = Math.round(fs * 0.28);
  c.strokeText(text, best.x + pad, best.y + h / 2); c.fillStyle = "#fff"; c.fillText(text, best.x + pad, best.y + h / 2);
  window.__studioStrongest[k].label = text; window.__studioStrongest[k].box = best.box;
  c.restore();
}
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
  const f = F[k], c0 = f.cv.getContext("2d"), fr = frO || getFr(k); if (!frO) { f.zoom.min = "5"; f.zoom.max = "250"; f.zoom.value = obsZv(fr); }
  frameTx(c0, f); c0.clearRect(0, 0, f.W, f.H); c0.fillStyle = BG === "transparent" ? "#111316" : BG; c0.fillRect(0, 0, f.W, f.H);
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
  c.font = `800 ${Math.round(f.valid * 1.1)}px Montserrat`; const bt = "LIVE", bw = c.measureText(bt).width + 40, bx = badgeRight(k) - bw, by = k === "v" ? 120 : 34;
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

// Re-fit alert mercator camera when 16:9 ↔ 9:16 cover band changes (Benjamin t2443u: no squish on aspect switch)
function alertRefitForAspect() {
  if (!ALERTM() || typeof Alerts === "undefined" || !Alerts.fitToSelection) return;
  Alerts.fitToSelection();
  const k = document.body.classList.contains("phone") ? "v" : "h";
  const fr = getFr(k); fr.zoom = 1; fr.dx = 0; fr.dy = 0; setFr(k, fr);
  if (F[k] && F[k].zoom) F[k].zoom.value = "100";
  render(k);
}

(function alertAspectWatch() {
  if (window.__alertAspectWatch) return; window.__alertAspectWatch = true;
  let prev = document.body.classList.contains("phone");
  const mo = new MutationObserver(() => {
    const now = document.body.classList.contains("phone");
    if (now === prev) return; prev = now;
    if (typeof alertRefitForAspect === "function") alertRefitForAspect();
  });
  mo.observe(document.body, { attributes: true, attributeFilter: ["class"] });
  // Do not refit on every window resize. At 1920x1080 a 2x bitmap that changes the
  // scrollbar fires resize, and this used to restart the alert paint before it finished.
  // The cover band only changes with the phone class, which the observer above watches.
})();
// ---- Active Alerts in Studio (11-05): header + credit style as Observations; no LIVE badge (t2437u)
const ALERT_CREDIT = ["Places: GeoNames, CC BY 4.0.", "Basemap: US Census Bureau. Roads: Natural Earth."];  // alert mode only. Census boundaries are public domain; Natural Earth roads/BC context are public domain.
function alertInfo() {
  const S_ = typeof Alerts !== "undefined" && Alerts._state; if (!S_) return null;
  const title = (typeof Alerts.titleText === "function" ? Alerts.titleText() : null) || S_.selectedType || "All Alerts";
  const t = S_.loaded ? new Date(S_.loaded) : null;
  let when = ""; if (t) { const p = Object.fromEntries(new Intl.DateTimeFormat("en-US", { timeZone: "America/Los_Angeles", weekday: "short", month: "2-digit", day: "2-digit", hour: "numeric", minute: "2-digit" }).formatToParts(t).map((x) => [x.type, x.value])); when = `${p.weekday} ${p.month}-${p.day} \u00b7 ${p.hour}:${p.minute} ${p.dayPeriod} PT`; }
  const types = typeof Alerts.eventTypes === "function" ? Alerts.eventTypes() : [];
  return { title, when, t, types, n: (S_.alerts || []).length };
}
function alertPaintKey(fr, r, I) {
  const S_ = (typeof Alerts !== "undefined" && Alerts._state) || {};
  const sel = (S_.selectedTypes && S_.selectedTypes.size) ? [...S_.selectedTypes].sort().join(",") : "ALL";
  return [S_.sig || "", S_.loaded || 0, sel, S_.fillAlpha, fr.zoom, Math.round(fr.dx || 0), Math.round(fr.dy || 0),
    r.cx.toFixed(1), r.cy.toFixed(1), r.kk.toFixed(5), I.title, I.when, (I.types || []).length].join("|");
}
function renderAlert(k, frO) {
  const f = F[k], fr = frO || getFr(k);
  const c0 = f.cv.getContext("2d");
  if (!frO) {
    f.zoom.min = String(Math.round(ALERT_ZMIN * 100));
    f.zoom.max = String(Math.round(ALERT_ZMAX * 100));
    fr.zoom = alertZ(fr.zoom || 1);
    f.zoom.value = String(Math.round(fr.zoom * 100));
  }
  const I = alertInfo();
  if (MG.img && I && I.t) {
    const r0 = crop(k, fr), key = alertPaintKey(fr, r0, I) + "|" + f.cv.width;
    if (f._alertPaint === key) { noteAlertDrawn(k); return; }
  }
  c0.globalAlpha = 1; c0.globalCompositeOperation = "source-over"; c0.shadowBlur = 0; c0.shadowOffsetX = 0; c0.shadowOffsetY = 0;
  // One logical fill. The 2x transform covers the backing store; a second device-pixel fill was a full extra pass.
  const ocean = BG === "transparent" ? "#030912" : (BG || "#030912");
  frameTx(c0, f); c0.clearRect(0, 0, f.W, f.H); c0.fillStyle = ocean; c0.fillRect(0, 0, f.W, f.H);
  if (!MG.img || !I || !I.t) { c0.font = `700 ${k === "v" ? 40 : 34}px Montserrat`; c0.fillStyle = "#c9ced8"; c0.textAlign = "center"; c0.fillText(MG.msg || "Loading alerts\u2026", f.W / 2, f.H / 2); c0.textAlign = "left"; return; }
  const r = crop(k, fr);
  drawAlertMap(c0, MG.img, f.W / 2 - r.cx * r.kk, f.H / 2 - r.cy * r.kk, IW(MG.img) * r.kk, IH(MG.img) * r.kk);
  // Towns, highways and boundary strokes in this frame's pixels (t2499u / t2504u). Each frame keeps its own camera.
  const settle = !!(frO && frO._alertSettle) || !!(window.__alertSettle && window.__alertSettle[k]);
  if (window.__alertSettle) window.__alertSettle[k] = 0;
  if (typeof Alerts !== "undefined" && Alerts.paintFrameScene) Alerts.paintFrameScene(c0, { frame: k, dpr: (Alerts._state && Alerts._state.dpr) || 1, W: f.W, H: f.H, zoom: alertZ(fr.zoom || 1), cx: r.cx, cy: r.cy, kk: r.kk, avoidTop: k === "v" ? 360 : 210, avoidBot: k === "v" ? f.H - 220 : f.H - 140 }, settle ? { settle: true } : null);
  // Title, credits and pills go straight onto the frame. An offscreen copy of the 2x store plus a shadow blur of that copy
  // was another full-frame pass, and the readiness readback after it stalled the refresh guard.
  const c = c0, x = f.pad; let y = k === "v" ? 120 : 34;
  const by = y; // top-right anchor without a LIVE badge
  c.save(); sharpShadow(c, k);
  const pw = pill(c, x, y, "ALERTS", Math.round(f.run * 0.95), "#7c3aed", "#fff");
  c.font = `600 ${f.run}px Montserrat`; c.fillStyle = "#c9ced8"; c.fillText("NWS \u00b7 Washington", x + pw + 14, y + f.run * 1.08);
  y += f.run * 1.55 + f.title * 1.02; c.font = `800 ${f.title}px Montserrat`; c.fillStyle = "#fff"; c.fillText(I.title, x, y);
  y += f.day * 1.3; c.font = `800 ${f.day}px Montserrat`; c.fillStyle = "#ffc24d"; c.fillText(I.when, x, y);
  const headBot = y + f.day * 0.45;
  c.restore();
  const cnr = BR.corner && LOGOS[BR.logo] ? cornerBox(k, by, headBot, f.H - f.bot + (k === "v" ? 110 : 62)) : null;
  // bottom-left credits (keep ~13% right clear for face cam — credits already left on 9:16)
  c.save(); sharpShadow(c, k);
  const dl = ALERT_CREDIT; let dfs = k === "v" ? 15 : 14; c.font = `600 ${dfs}px Montserrat`;
  const dMax = k === "v" ? f.W - 2 * f.pad : Math.round(f.W * 0.52);
  while (dfs > 11 && Math.max(...dl.map((l) => c.measureText(l).width)) > dMax) { dfs -= 1; c.font = `600 ${dfs}px Montserrat`; }
  const dlh = dfs + 7, cB = cnr && (BR.cpos === "br" || BR.cpos === "bl") ? cnr : null;
  c.fillStyle = "rgba(236,239,244,0.95)";
  if (k === "v") dl.forEach((l, i) => c.fillText(l, f.pad + (cB && BR.cpos === "bl" ? cB.s + 18 : 0), f.H - 70 - (dl.length - 1 - i) * dlh));
  else { c.textAlign = "right"; dl.forEach((l, i) => c.fillText(l, f.W - f.pad - (cB && BR.cpos === "br" ? cB.s + 20 : 0), f.H - 24 - (dl.length - 1 - i) * dlh)); c.textAlign = "left"; }
  // legend pills: only toggled-on types (empty selection = All → show every type) (t2496u)
  let lx = f.pad, ly = k === "v" ? f.H - 70 - (dl.length - 1) * dlh - dfs - 30 - 30 * 1.55 : f.H - 24 - 30 * 1.55 + 30 * 0.35;
  const lgS = k === "v" ? 28 : 24;
  const Ssel = (typeof Alerts !== "undefined" && Alerts._state && Alerts._state.selectedTypes) || null;
  const legendTypes = (Ssel && Ssel.size) ? I.types.filter((t) => Ssel.has(t.event)) : I.types;
  // t2504u: every toggled-on type is listed: pills that don't fit the row wrap onto rows stacked ABOVE it (was: silently dropped)
  { c.font = `800 ${lgS}px Montserrat`; const h = lgS * 1.55, maxX = k === "v" ? f.W * 0.82 : f.W * 0.46, rows = [[]]; let rx = f.pad;   // keep right ~18% clear
    for (const t of legendTypes) { const w = c.measureText(t.event).width + lgS * 1.2;
      if (rx + w > maxX && rows[rows.length - 1].length) { rows.push([]); rx = f.pad; } rows[rows.length - 1].push([t, rx, w]); rx += w + 12; }
    rows.forEach((row, r) => { const y = ly - (rows.length - 1 - r) * (h + 8);
      for (const [t, x, w] of row) {
        noShadow(c); c.fillStyle = "rgba(17,19,22,0.78)"; c.beginPath(); c.roundRect ? c.roundRect(x, y, w, h, h / 2) : c.rect(x, y, w, h); c.fill(); sharpShadow(c, k);
        c.font = `800 ${lgS}px Montserrat`; c.fillStyle = t.color || "#ccc"; c.textBaseline = "middle"; c.fillText(t.event, x + lgS * 0.6, y + h / 2 + 1); c.textBaseline = "alphabetic"; } }); }
  c.restore();
  if (cnr) cornerLogo(c0, cnr);
  f._alertPaint = alertPaintKey(fr, r, I) + "|" + f.cv.width;
  noteAlertDrawn(k);
}
function noteAlertDrawn(k) {
  // Draw-complete flag. Do not read the 2x frame back: getImageData on that store is what made
  // a refresh take ~10 s and kept the layout guard from seeing a draw within 120 s.
  window.__studioFramePx = Object.assign({}, window.__studioFramePx, { [k]: 7 });
  window.__studio = (window.__studio || 0) + 1; window.__studioAlert = (window.__studioAlert || 0) + 1;
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
  const f = F[k]; ssFit(f, PSS); const c0 = f.cv.getContext("2d"); f.zoom.min = "100"; f.zoom.max = "250"; f.zoom.value = "100";
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
function renderWafc(k, frO) {
  const f = F[k]; ssFit(f, PSS); const c = f.cv.getContext("2d"), fr = frO || getFr(k);   // portrait and landscape keep their own framing (studio:v:wafc / studio:h:wafc)
  if (!frO) { f.zoom.min = "100"; f.zoom.max = "250"; f.zoom.value = Math.round((fr.zoom || 1) * 100); }
  c.setTransform(PSS, 0, 0, PSS, 0, 0); c.clearRect(0, 0, f.W, f.H); c.fillStyle = BG === "transparent" ? "#111316" : BG; c.fillRect(0, 0, f.W, f.H);
  const im = MG.img; if (!im) { c.font = `700 ${k === "v" ? 40 : 34}px Montserrat`; c.fillStyle = "#c9ced8"; c.textAlign = "center"; c.fillText(MG.msg || "Loading the WA forecast map\u2026", f.W / 2, f.H / 2); c.textAlign = "left"; return; }
  const r = crop(k, fr);   // same camera as the other products; zoom 1 still fits the whole map (mgBase)
  c.imageSmoothingEnabled = true; c.imageSmoothingQuality = "high";
  c.drawImage(im, f.W / 2 - r.cx * r.kk, f.H / 2 - r.cy * r.kk, IW(im) * r.kk, IH(im) * r.kk);
  window.__studio = (window.__studio || 0) + 1; window.__studioWafc = (window.__studioWafc || 0) + 1;
}
function webNormalize(raw) {
  let s = String(raw || "").trim(); if (!s) return "";
  if (!/^https?:\/\//i.test(s)) s = "https://" + s;
  try { const u = new URL(s); if (u.protocol !== "http:" && u.protocol !== "https:") return ""; return u.toString(); } catch (e) { return ""; }
}
// 11-07 (Benjamin t2692u, t2693u): the page is always live (click, scroll, type); the grab bar on top of each web frame drags the framing
// (same fr state as canvas drag). Pointer capture on the bar + iframe pointer-events off during the drag (body.webdrag) so it never loses the drag.
function webGrip(k, bar) {
  let d = null;
  bar.addEventListener("pointerdown", (e) => { if (!WEBM() || REC.on) return; e.preventDefault(); bar.setPointerCapture(e.pointerId); document.body.classList.add("webdrag"); d = { x: e.clientX, y: e.clientY, fr: getFr(k), id: e.pointerId }; });
  bar.addEventListener("pointermove", (e) => { if (!d || e.pointerId !== d.id) return; const f = F[k], s = f.W / (f.cv.clientWidth || 1), fr = getFr(k);
    fr.dx = d.fr.dx + (e.clientX - d.x) * s; fr.dy = d.fr.dy + (e.clientY - d.y) * s;
    const r = crop(k, fr); fr.dx = (r.bx - r.cx) * r.kk; fr.dy = (r.by - r.cy) * r.kk; setFr(k, fr); render(k); });
  const up = () => { d = null; document.body.classList.remove("webdrag"); };
  bar.addEventListener("pointerup", up); bar.addEventListener("pointercancel", up); bar.addEventListener("lostpointercapture", up);
}
// 11-07 (Benjamin): one page state in both frames. Two iframes can't share a cross-origin page, so Mirror captures this tab
// (getDisplayMedia, Chrome asks once) and draws the live 16:9 page into the 9:16 canvas each frame, with the 9:16 frame's own zoom/drag.
// Use the page in 16:9; the 9:16 frame follows clicks, scroll, navigation and typing. Stop or ending the share goes back to two pages.
function webMirDraw() {
  const m = WEB.mir, f = F.v, hov = F.h.web; if (!m || !hov || hov.hidden || !m.vid.videoWidth) return;
  const c = f.cv.getContext("2d"), r = hov.getBoundingClientRect(), q = m.vid.videoWidth / innerWidth, g = 22;   // skip the grab bar
  const sx = r.left * q, sy = (r.top + g) * q, sw = r.width * q, sh = (r.height - g) * q; if (sw < 2 || sh < 2) return;
  const fr = getFr("v"), z = fr.zoom || 1, k_ = Math.max(f.W / sw, f.H / sh) * z;
  c.setTransform(1, 0, 0, 1, 0, 0); c.fillStyle = "#111316"; c.fillRect(0, 0, f.W, f.H);
  c.drawImage(m.vid, sx, sy, sw, sh, f.W / 2 - sw * k_ / 2 + (fr.dx || 0), f.H / 2 - sh * k_ / 2 + (fr.dy || 0), sw * k_, sh * k_);
}
function webMirStop() { const m = WEB.mir; if (!m) return; WEB.mir = null; cancelAnimationFrame(m.raf); m.stream.getTracks().forEach((t) => t.stop()); const b = document.getElementById("webmir"); if (b) b.textContent = "Mirror 16:9 into 9:16"; if (WEBM()) renderAll(); }
async function webMirStart() {
  if (WEB.mir) { webMirStop(); return; }
  let stream; try { stream = await navigator.mediaDevices.getDisplayMedia({ video: { displaySurface: "browser", frameRate: 30 }, audio: false, preferCurrentTab: true, selfBrowserSurface: "include" }); } catch (e) { return; }
  const vid = document.createElement("video"); vid.muted = true; vid.playsInline = true; vid.srcObject = stream; await vid.play().catch(() => {});
  WEB.mir = { stream, vid, raf: 0 }; stream.getVideoTracks()[0].addEventListener("ended", webMirStop);
  const b = document.getElementById("webmir"); if (b) b.textContent = "Stop mirror";
  const tick = () => { if (!WEB.mir) return; if (WEBM()) webMirDraw(); WEB.mir.raf = requestAnimationFrame(tick); }; tick(); renderAll();
}
function webHide() { for (const k of ["v", "h"]) if (F[k].web) F[k].web.hidden = true; }
function webApply(url) {
  WEB.url = url || ""; try { if (url) localStorage.setItem("studio:weburl", url); } catch (e) { /* private */ }
  for (const k of ["v", "h"]) { const ifr = F[k].web && F[k].web.querySelector("iframe"); if (ifr && ifr.getAttribute("src") !== (url || "about:blank")) ifr.src = url || "about:blank"; }
  if (WEBM()) renderAll();
}
function placeWeb(k, frO) {
  const f = F[k], ov = f.web; if (!ov) return;
  if (!WEBM() || !WEB.url || (k === "v" && WEB.mir)) { ov.hidden = true; return; }
  const fr = frO || getFr(k), r = crop(k, fr), cv = f.cv;
  ov.hidden = false; ov.style.left = cv.offsetLeft + "px"; ov.style.top = cv.offsetTop + "px"; ov.style.width = cv.clientWidth + "px"; ov.style.height = cv.clientHeight + "px";
  const ifr = ov.querySelector("iframe"), s = (cv.clientWidth || 1) * r.kk / f.W, x0 = r.cx - f.W / (2 * r.kk), y0 = r.cy - f.H / (2 * r.kk);
  ifr.style.width = f.W + "px"; ifr.style.height = f.H + "px"; ifr.style.transformOrigin = "0 0"; ifr.style.transform = `translate(${-x0 * s}px, ${-y0 * s}px) scale(${s})`;
}
function renderWeb(k, frO) {
  const f = F[k], c = f.cv.getContext("2d"), fr = frO || getFr(k);
  if (!frO) { f.zoom.min = "100"; f.zoom.value = String(Math.round((fr.zoom || 1) * 100));
    const r = crop(k, fr); fr.dx = (r.bx - r.cx) * r.kk; fr.dy = (r.by - r.cy) * r.kk; setFr(k, fr); }
  frameTx(c, f); c.clearRect(0, 0, f.W, f.H); c.fillStyle = BG === "transparent" ? "#111316" : BG; c.fillRect(0, 0, f.W, f.H);
  c.font = `600 ${k === "v" ? 28 : 24}px Montserrat`; c.fillStyle = "#c9ced8"; c.textAlign = "center";
  const msg = WEB.url ? "If this stays blank, the site probably doesn't allow embedding." : "Paste a page address above, then Open.";
  const words = msg.split(" "), maxW = f.W - 2 * f.pad, lines = []; let line = "";
  for (const w_ of words) { const t = line ? line + " " + w_ : w_; if (c.measureText(t).width > maxW && line) { lines.push(line); line = w_; } else line = t; } if (line) lines.push(line);
  lines.forEach((t, i) => c.fillText(t, f.W / 2, f.H / 2 + (i - (lines.length - 1) / 2) * (k === "v" ? 40 : 34)));
  c.textAlign = "left"; if (k === "v" && WEB.mir) webMirDraw(); placeWeb(k, fr); window.__studio = (window.__studio || 0) + 1; window.__studioWeb = { url: WEB.url, fr: { v: getFr("v"), h: getFr("h") } };
}
function cmpApi() { try { return cmpFrame && cmpFrame.contentWindow && cmpFrame.contentWindow.__cmp; } catch (e) { return null; } }
// viewer.js keeps its state in a script binding (const S) and publishes it only as window.__S. A parent frame's
// contentWindow.S is undefined; contentWindow.__S is the live object. Fall back to .S if a build ever assigns it.
function cmpState(w) { return w && (w.__S || w.S) || null; }
function cmpSteps() {
  try { const S_ = cmpState(cmpFrame.contentDocument.getElementById("R").contentWindow), run = S_ && S_.run; return run && S_.runs[run] && S_.runs[run].steps; } catch (e) { return null; }
}
function cmpPickIdx(steps) {
  const a = +$s("mpa").value, b = +$s("mpb").value, e = +$s("mpe").value, out = []; if (!steps) return out;
  for (let i = a; i <= b && i < steps.length; i++) if (!out.length || !e || steps[i].f - steps[out[out.length - 1]].f >= e) out.push(i);
  return out;
}
function cmpGrab() {
  const api = cmpApi(); if (!api) return;
  CMP.L = api.L || null; CMP.R = api.R || null;
  let changed = false;
  for (const id of ["L", "R"]) {
    let next = null;
    try {
      const w = cmpFrame.contentDocument.getElementById(id).contentWindow, S_ = cmpState(w), cv = w.document.getElementById("map"), cur = S_ && S_.cur;
      if (cv && cv.width && cur && cur.V && cur.V.panel) {
        const m = String(cur.run || "").split("/")[0], step = S_.runs[cur.run].steps[S_.i];
        const sig = [cur.run, cur.pid, step && step.f, cv.width, cv.height, w.__drawn || ""].join("|");
        next = { cv, panel: cur.V.panel, rs: cv._rs || 1, title: (cur.P && cur.P.title) || "", pid: cur.pid, run: cur.run, model: m,
          site: (S_.man && S_.man.models[m] && S_.man.models[m].site) || m, step, sig };
      }
    } catch (e) { next = null; }
    if ((CMP.view[id] && CMP.view[id].sig) !== (next && next.sig)) { CMP.view[id] = next; changed = true; }
  }
  try { const u = new URL(cmpFrame.contentWindow.location.href); if (u.searchParams.get("l")) { u.searchParams.set("studio", "1"); sessionStorage.setItem("studio:cmpq", "?" + u.searchParams.toString()); } } catch (e) { /* iframe loading */ }
  if (CMPM()) { if (changed && !REC.on) renderAll(); cmpScrub(); }
}
// t2775u (Benjamin: glitchy jump while scrubbing): the hour readout's width followed its text, so the scrub bar and the slider
// changed width by a few px every hour and the thumb slid out from under the pointer. The readout now gets one fixed width per run:
// the widest label of that run (tabular numbers, measured once), so the bar and slider stay the same size while dragging.
let shourW = 0, shourKey = "";
function fixShourW(labels) {
  const lab = document.getElementById("shour"); if (!lab || !labels || !labels.length) return;
  const key = labels.length + "|" + labels[0] + "|" + labels[labels.length - 1]; if (key === shourKey) return; shourKey = key;
  if (document.fonts && document.fonts.status !== "loaded") document.fonts.ready.then(() => { shourKey = ""; fixShourW(labels); });   // re-measure once Montserrat is in
  const cs = getComputedStyle(lab), c = fixShourW.c || (fixShourW.c = document.createElement("canvas").getContext("2d"));
  c.font = `${cs.fontWeight} ${cs.fontSize} ${cs.fontFamily}`;
  let w = 0; for (const t of labels) w = Math.max(w, c.measureText(t).width);
  w = Math.ceil(w * 1.04 + 6); if (Math.abs(w - shourW) < 1) return; shourW = w;
  lab.style.setProperty("--shw", w + "px");
}
function cmpScrub() {
  const r = CMP.R || CMP.L; if (!r || !r.n) return;
  const sl = document.getElementById("hscrub"), lab = document.getElementById("shour"), step = document.getElementById("step");
  if (sl) { sl.max = String(r.n - 1); if (document.activeElement !== sl) sl.value = String(r.i); }
  if (step && CMPM()) { step.max = String(r.n - 1); if (document.activeElement !== step) step.value = String(r.i); }
  if (lab) lab.textContent = `F+${r.f}` + (r.vline ? `  \u00b7  ${String(r.vline).replace(/^Valid /, "")}` : "");
  const tk = document.getElementById("sticks"), steps = cmpSteps();
  if (steps && steps.length) fixShourW(steps.map(x => `F+${x.f}` + (x.vline || x.valid_line ? `  \u00b7  ${String(x.vline || x.valid_line).replace(/^Valid /, "")}` : "")));   // t2775u
  if (tk && steps && steps.length) { const key = (r.run || "") + ":" + steps.length; if (tk.dataset.key !== key) { tk.dataset.key = key; const n = steps.length;
    tk.innerHTML = steps.map((x, i) => x.f % 24 === 0 && (x.f % 48 === 0 || steps[n - 1].f <= 168) ? `<span style="left:calc(9px + (100% - 18px) * ${n > 1 ? i / (n - 1) : 0})">${x.f}</span>` : "").join(""); } }
}
function cmpSetHour(i) { const api = cmpApi(); if (!api || !CMP.R || !CMP.R.n) return; api.setHour((i + CMP.R.n) % CMP.R.n); }
function cmpStep(d) { if (CMP.R) cmpSetHour(CMP.R.i + d); }
// 11-07: Compare's two product menus sit in #cmpf. A fixed 320px iframe clipped the second menu after the first
// bar grew, and the nested map frames ate wheel / touch. The panel itself scrolls; nothing on it locks scroll.
function cmpFitPanel() {
  const pnl = document.getElementById("mgp");
  if (!CMPM() || !pnl || !cmpFrame) return;
  const top = Math.max(0, pnl.getBoundingClientRect().top);
  let maxH = Math.max(200, Math.min(window.innerHeight - top - 8, Math.round(window.innerHeight * 0.72)));
  // 11-07 (Benjamin t2699u): on desktop keep fitFrames' cap so Compare's frames sit exactly where Map's do (the panel scrolls)
  const fitCap = parseFloat(pnl.style.maxHeight); if (!CLEAN && innerWidth > 820 && fitCap > 0) maxH = Math.min(maxH, fitCap);
  pnl.style.setProperty("max-height", maxH + "px");
  pnl.style.setProperty("overflow-y", "auto");
  pnl.style.setProperty("overflow-x", "hidden");
  pnl.style.setProperty("touch-action", "pan-y");
  pnl.style.setProperty("-webkit-overflow-scrolling", "touch");
  pnl.style.setProperty("overscroll-behavior", "contain");
  cmpFrame.style.display = "block";
  cmpFrame.style.width = "100%";
  cmpFrame.style.border = "0";
  cmpFrame.style.touchAction = "pan-y";
  cmpFrame.style.overflow = "visible";
  cmpFrame.style.maxHeight = "none";
  const nudge = (dy) => {
    const max = pnl.scrollHeight - pnl.clientHeight; if (max <= 2) return false;
    const before = pnl.scrollTop; pnl.scrollTop = Math.max(0, Math.min(max, before + dy)); return pnl.scrollTop !== before;
  };
  const bind = (doc) => {
    if (!doc || doc.documentElement._cmpScroll) return;
    doc.documentElement._cmpScroll = true;
    doc.addEventListener("wheel", (e) => { if (nudge(e.deltaY)) e.preventDefault(); }, { passive: false, capture: true });
    let y0 = 0;
    doc.addEventListener("touchstart", (e) => { if (e.touches.length === 1) y0 = e.touches[0].clientY; }, { passive: true, capture: true });
    doc.addEventListener("touchmove", (e) => {
      if (e.touches.length !== 1) return;
      const tgt = e.target && e.target.closest && e.target.closest("select, input, textarea, button, a, option");
      if (tgt) return;
      const y = e.touches[0].clientY; if (nudge(y0 - y)) e.preventDefault(); y0 = y;
    }, { passive: false, capture: true });
  };
  try {
    const doc = cmpFrame.contentDocument; if (!doc || !doc.head || !doc.body) return;
    bind(doc);
    let st = doc.getElementById("cmp-scroll-fix");
    if (!st) { st = doc.createElement("style"); st.id = "cmp-scroll-fix"; doc.head.appendChild(st); }
    st.textContent = "html,body{height:auto!important;min-height:0!important;overflow:visible!important;touch-action:pan-y!important}#panes,#cbar,#L,#R{touch-action:pan-y!important}";
    for (const id of ["L", "R"]) {
      const fr = doc.getElementById(id); if (!fr || !fr.contentDocument || !fr.contentDocument.head || !fr.contentDocument.body) continue;
      const idoc = fr.contentDocument;
      bind(idoc);
      let s2 = idoc.getElementById("cmp-scroll-fix");
      if (!s2) { s2 = idoc.createElement("style"); s2.id = "cmp-scroll-fix"; idoc.head.appendChild(s2); }
      s2.textContent = "html,body{height:auto!important;overflow:visible!important;touch-action:pan-y!important}#bar,#bar *{touch-action:pan-y!important}";
      const bar = idoc.getElementById("bar");
      const bh = bar ? Math.ceil(bar.getBoundingClientRect().height) : 0;
      if (bh > 40) fr.style.height = (bh + 12) + "px";
    }
    const h = Math.max(doc.documentElement.scrollHeight, doc.body.scrollHeight);
    if (h > 80) cmpFrame.style.height = h + "px";
  } catch (e) { /* iframe not same-origin yet */ }
}
function cmpSrc() {
  let saved = ""; try { saved = sessionStorage.getItem("studio:cmpq") || ""; } catch (e) { /* private */ }
  if (saved) { const u = new URLSearchParams(saved.replace(/^\?/, "")); u.set("studio", "1"); return "compare.html?" + u.toString(); }
  const q = new URLSearchParams({ studio: "1" });
  try {
    if (S.run && S.runs[S.run]) { const st = S.runs[S.run].steps[S.i], [m, cyc] = S.run.split("/"), rs = (S.man.runs[m] || []);
      const otherC = rs.length > 1 ? (rs[rs.length - 1] === cyc ? rs[rs.length - 2] : rs[rs.length - 1]) : cyc;
      q.set("l", S.run); q.set("r", m + "/" + otherC); if (S.prod) q.set("prod", S.prod); if (S.view) q.set("view", S.view); if (st && st.valid) q.set("valid", st.valid); }
  } catch (e) { /* map not ready: compare opens on its own defaults */ }
  return "compare.html?" + q.toString();
}
function cmpHeadTitle() {
  const a = CMP.view.L, b = CMP.view.R, ta = a && a.title, tb = b && b.title;
  if (ta && tb && ta === tb) return ta; if (ta && tb) return "Compare"; return ta || tb || "Compare";
}
function cmpBadgeText(v) { if (!v || !v.step) return ""; return v.model === "oisst" && v.step.badge ? v.step.badge[0] : "F+" + v.step.f; }
function cmpDrawPanel(c, k, src, box) {
  const cap = k === "v" ? 40 : 34; c.fillStyle = "rgba(17,19,22,0.92)"; c.fillRect(box.x, box.y, box.w, cap);
  c.font = `700 ${k === "v" ? 22 : 20}px Montserrat`; c.fillStyle = "#fff"; c.textBaseline = "middle";
  const lab = src ? `${src.site}  \u00b7  ${src.title}${src.step ? "  \u00b7  " + cmpBadgeText(src) : ""}` : "Loading\u2026";
  let t = lab; while (c.measureText(t).width > box.w - 24 && t.length > 8) t = t.slice(0, -2); if (t !== lab) t += "\u2026";
  c.fillText(t, box.x + 12, box.y + cap / 2 + 1); c.textBaseline = "alphabetic";
  const inner = { x: box.x, y: box.y + cap, w: box.w, h: Math.max(10, box.h - cap) };
  if (!src || !src.cv || !src.panel) { c.fillStyle = "#1d2027"; c.fillRect(inner.x, inner.y, inner.w, inner.h); c.fillStyle = "#8e939c"; c.font = `700 ${k === "v" ? 28 : 24}px Montserrat`; c.textAlign = "center"; c.fillText(src ? "Loading\u2026" : "Loading the compare map\u2026", inner.x + inner.w / 2, inner.y + inner.h / 2); c.textAlign = "left"; return; }
  const [px, py, pw] = src.panel, rs = src.rs || 1, lh = src.cv._lh || (py + src.panel[3]);
  const ah = Math.max(src.panel[3], lh - py), sx = px * rs, sy = py * rs, sw = pw * rs, sh = ah * rs;
  const sc = Math.min(inner.w / pw, inner.h / ah), dw = pw * sc, dh = ah * sc;
  c.imageSmoothingEnabled = true; c.imageSmoothingQuality = "high";
  try { c.drawImage(src.cv, sx, sy, sw, sh, inner.x + (inner.w - dw) / 2, inner.y + (inner.h - dh) / 2, dw, dh); } catch (e) { /* a map canvas the browser will not read */ }
}
function renderCmp(k) {
  const f = F[k], c0 = f.cv.getContext("2d"); if (f.zoom) { f.zoom.min = "100"; f.zoom.value = "100"; }
  frameTx(c0, f); c0.clearRect(0, 0, f.W, f.H); c0.fillStyle = BG === "transparent" ? "#111316" : BG; c0.fillRect(0, 0, f.W, f.H);
  const main = CMP.view.R || CMP.view.L, c = ovLayer(f), x = f.pad; let y = k === "v" ? 120 : 34;
  c.save(); sharpShadow(c, k);
  const sites = [CMP.view.L, CMP.view.R].map((v) => v && v.site).filter(Boolean);
  const pillT = sites.length > 1 && sites[0] !== sites[1] ? "COMPARE" : (sites[0] || "COMPARE").toUpperCase();
  const pw = pill(c, x, y, pillT, Math.round(f.run * 0.95), "#2f8cff", "#fff");
  const runL = [CMP.view.L, CMP.view.R].map((v) => v && v.run ? `${v.site} ${String(v.run.split("/")[1] || "").slice(8)}Z` : "").filter(Boolean).join("  \u00b7  ");
  c.font = `600 ${f.run}px Montserrat`; c.fillStyle = "#c9ced8"; c.fillText(runL || "two models", x + pw + 14, y + f.run * 1.08);
  y += f.run * 1.55 + f.title * 1.02; c.font = `800 ${f.title}px Montserrat`; c.fillStyle = "#fff";
  const title = BR.title || cmpHeadTitle(), maxW = f.W - 2 * f.pad - (k === "h" ? 260 : 0);
  let t1 = title; while (c.measureText(t1).width > maxW && t1.length > 6) t1 = t1.slice(0, -2); if (t1 !== title) t1 += "\u2026";
  c.fillText(t1, x, y); y += f.day * 1.3;
  const vline = (main && main.step && main.step.valid_line || "").replace(/^Valid /, "");
  c.font = `800 ${f.day}px Montserrat`; c.fillStyle = "#ffc24d"; c.fillText(vline, x, y);
  const headBot = y + f.day * 0.45; c.restore();
  const bt = cmpBadgeText(main), by = k === "v" ? 120 : 34; let badgeBot = by;
  if (bt) { c.font = `800 ${Math.round(f.valid * 1.1)}px Montserrat`; const bw = c.measureText(bt).width + 40, bx = badgeRight(k) - bw;
    c.save(); sharpShadow(c, k); c.fillStyle = "rgba(17,19,22,0.85)"; c.strokeStyle = "rgba(255,255,255,0.35)"; c.lineWidth = 2;
    c.beginPath(); c.roundRect ? c.roundRect(bx, by, bw, f.valid * 1.9, 14) : c.rect(bx, by, bw, f.valid * 1.9); c.fill(); noShadow(c); c.stroke(); sharpShadow(c, k);
    c.fillStyle = "#fff"; c.textAlign = "center"; c.fillText(bt, bx + bw / 2, by + f.valid * 1.32); c.textAlign = "left"; c.restore();
    f.badge = [bx - 12, by - 12, bx + bw + 12, by + f.valid * 1.9 + 12]; badgeBot = by + f.valid * 1.9; }
  const cnr = BR.corner && LOGOS[BR.logo] ? cornerBox(k, badgeBot, headBot, f.H - 80) : null;
  ovPut(c0, f, k);
  const top = headBot + (k === "v" ? 28 : 18), bot = f.H - (k === "v" ? 36 : 24), gap = k === "v" ? 14 : 12;
  let rects;
  if (k === "h") { const w = (f.W - 2 * f.pad - gap) / 2, h = Math.max(40, bot - top); rects = [{ x: f.pad, y: top, w, h }, { x: f.pad + w + gap, y: top, w, h }]; }
  else { const h = Math.max(40, (bot - top - gap) / 2), w = f.W - 2 * f.pad; rects = [{ x: f.pad, y: top, w, h }, { x: f.pad, y: top + h + gap, w, h }]; }
  c0.save(); cmpDrawPanel(c0, k, CMP.view.L, rects[0]); cmpDrawPanel(c0, k, CMP.view.R, rects[1]);
  c0.fillStyle = "#2f8cff";
  if (k === "h") c0.fillRect(rects[0].x + rects[0].w + gap / 2 - 2, top, 4, rects[0].h); else c0.fillRect(f.pad, rects[0].y + rects[0].h + gap / 2 - 2, rects[0].w, 4);
  c0.restore();
  if (cnr) cornerLogo(c0, cnr);
  if (BR.lower && (last || BR.title || BR.storm)) lowerThird(k, c0);
  window.__studio = (window.__studio || 0) + 1; window.__studioCmp = { l: CMP.L && CMP.L.run, r: CMP.R && CMP.R.run, title };
}
function renderMg(k, frO) {
  if (WEBM()) return renderWeb(k, frO);
  if (CMPM()) return renderCmp(k);
  if (WAFCM()) return renderWafc(k, frO);
  if (ALERTM()) return renderAlert(k, frO);
  if (OBSM()) return renderObs(k, frO);
  if (PASSM()) return renderPass(k);
  const f = F[k], c = f.cv.getContext("2d"), fr = frO || getFr(k); f.zoom.min = "100"; f.zoom.max = "250"; f.zoom.value = Math.round((fr.zoom || 1) * 100);
  frameTx(c, f); c.clearRect(0, 0, f.W, f.H); c.fillStyle = BG === "transparent" ? "#111316" : BG; c.fillRect(0, 0, f.W, f.H);
  if (!MG.img) { c.font = `700 ${k === "v" ? 40 : 34}px Montserrat`; c.fillStyle = "#c9ced8"; c.textAlign = "center"; c.fillText(MG.msg || "Loading the meteogram\u2026", f.W / 2, f.H / 2); c.textAlign = "left"; return; }
  const r = crop(k, fr); c.imageSmoothingEnabled = true; c.imageSmoothingQuality = "high";
  c.drawImage(MG.img, f.W / 2 - r.cx * r.kk, f.H / 2 - r.cy * r.kk, MG.img.naturalWidth * r.kk, MG.img.naturalHeight * r.kk);
  // the chart carries its own title, run line and ECMWF / NOAA data credit; place names: GeoNames (locked credit, 11-01 legal audit)
  { const o = ovLayer(f); o.save(); o.font = `600 ${k === "v" ? 21 : 18}px Montserrat`; o.fillStyle = "rgba(236,239,244,0.95)"; sharpShadow(o, k);
    o.textAlign = k === "v" ? "left" : "right"; o.fillText("Places: GeoNames (geonames.org), CC BY 4.0.", k === "v" ? f.pad : f.W - f.pad, f.H - (k === "v" ? 70 : 24)); o.restore(); ovPut(c, f, k); }
  const cnr = BR.corner && LOGOS[BR.logo] ? cornerBox(k, k === "v" ? 120 : 40, k === "v" ? 120 : 40, f.H - (k === "v" ? 140 : 80)) : null; if (cnr) cornerLogo(c, cnr);
  window.__studio = (window.__studio || 0) + 1; window.__studioMg = (window.__studioMg || 0) + 1;
}
// Town names are left off the shared map bitmap in Studio (two frames, two crops). Each frame draws them
// at backing scale and drops or nudges any label that would sit in the title/date band, the footer, or past the frame edge.
function paintStudioTowns(c, k, r, top, bot) {
  const src = window.__studioTownSrc;
  if (!src || !src.items || !src.items.length || !r || !r.sw || !r.rs) { window.__studioTownBoxes = []; return; }
  const f = F[k], rs = r.rs, sc = f.W / r.sw, dpi = src.dpi || 100, kk = sc * rs;
  const toF = (figX, figY) => [(figX * rs - r.sx) * sc, (figY * rs - r.sy) * (f.H / r.sh)];
  const margin = 8, hits = (b) => b[0] < margin || b[1] < top || b[2] > f.W - margin || b[3] > bot;
  const shifts = [[0, 0], [0, -18], [0, -36], [20, 0], [-20, 0], [0, 16], [32, -14], [-32, -14], [0, -54]];
  c.save();
  const placed = [], overlap = (b) => placed.some((a) => b[0] < a[2] + 2 && b[2] > a[0] - 2 && b[1] < a[3] + 2 && b[3] > a[1] - 2);
  const kept = new Map();
  for (const it of src.items) if (it.k === "t") {
    const [x0, y0] = toF(it.x * src.LW, it.y * src.LH), fs = it.size * dpi / 72 * kk;
    const font = `${it.style === "italic" ? "italic " : ""}${it.w || 600} ${fs}px Montserrat`;
    c.font = font; const tw = c.measureText(it.t).width, hh = fs * 0.55, base = [x0, y0 - hh, x0 + tw, y0 + hh * 0.75];
    let shift = null;
    for (const [dx, dy] of shifts) { const b = [base[0] + dx, base[1] + dy, base[2] + dx, base[3] + dy]; if (hits(b) || overlap(b)) continue; shift = [dx, dy, b]; break; }
    if (!shift) continue;
    kept.set(it.t, shift); placed.push(shift[2]);
    c.font = font; c.textAlign = "left"; c.textBaseline = "middle"; c.lineJoin = "round";
    c.lineWidth = Math.max(1, (it.halo == null ? 2.6 : it.halo) * dpi / 72 * kk); c.strokeStyle = "#ffffff";
    c.strokeText(it.t, x0 + shift[0], y0 + shift[1]); c.fillStyle = it.fill || "#1b1d22"; c.fillText(it.t, x0 + shift[0], y0 + shift[1]);
  }
  for (const it of src.items) if (it.k === "m") {
    const [x, y] = toF(it.x * src.LW, it.y * src.LH);
    if (x < margin || y < top || x > f.W - margin || y > bot) continue;
    const rad = (it.ms || 3.6) / 2 * dpi / 72 * kk;
    c.beginPath();
    if (it.mk === "^") { const h = rad * 1.15; c.moveTo(x, y - h); c.lineTo(x + h * 0.95, y + h * 0.75); c.lineTo(x - h * 0.95, y + h * 0.75); c.closePath(); }
    else c.arc(x, y, Math.max(1, rad), 0, 2 * Math.PI);
    c.fillStyle = it.fill || "#1b1d22"; c.strokeStyle = it.stroke || "#ffffff"; c.lineWidth = (it.mew || 0) * dpi / 72 * kk;
    if (it.mew) c.stroke(); c.fill();
  }
  for (const n of src.nums || []) {
    if (src.items.some((t) => t.k === "t" && t.t === n.name) && !kept.has(n.name)) continue;
    const sh = kept.get(n.name), [x0, y0] = toF(n.x * src.LW, n.y * src.LH), dx = sh ? sh[0] : 0, dy = sh ? sh[1] : 0;
    const fs = n.size * dpi / 72 * kk; c.font = `800 ${fs}px Montserrat`;
    const tw = c.measureText(n.text).width, hh = fs * 0.55, b = [x0 + dx, y0 + dy - hh, x0 + dx + tw, y0 + dy + hh * 0.75];
    if (hits(b) || overlap(b)) continue;
    placed.push(b); c.textAlign = "left"; c.textBaseline = "middle"; c.lineJoin = "round";
    c.lineWidth = Math.max(1, 3 * dpi / 72 * kk); c.strokeStyle = "#ffffff"; c.strokeText(n.text, x0 + dx, y0 + dy);
    c.fillStyle = n.color || "#0d0f13"; c.fillText(n.text, x0 + dx, y0 + dy);
  }
  c.restore();
  window.__studioTownBoxes = placed;
}
async function render(k, frO) {   // frO: camera override (MP4 storm-track pan)
  ssFit(F[k], REC.flat ? 1 : PSS);   // every Studio frame is 2x so titles, keys, credits and labels rasterize at export size
  if (MG.on) return renderMg(k, frO);
  if (!last) return; const f = F[k], c0 = f.cv.getContext("2d"), fr = frO || getFr(k), { cv, cur, step } = last, P = cur.P, [m] = cur.run.split("/"); let c = c0;
  if (!frO) { f.zoom.min = "100"; f.zoom.max = "250"; f.zoom.value = Math.round((fr.zoom || 1) * 100); }
  const z = f.ss || 1; c.setTransform(z, 0, 0, z, 0, 0); c.clearRect(0, 0, f.W, f.H);
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
  // F+ badge (top right) — hidden on vertical 9:16 (t2495u) and on horizontal 16:9 (t2567u); OISST date badge kept
  let by = k === "v" ? 120 : 34, badgeBot = by;
  if (k !== "v" && m === "oisst" && step.badge) {
    c.font = `800 ${Math.round(f.valid * 1.1)}px Montserrat`; const bt = step.badge[0], bw = c.measureText(bt).width + 40, bx = badgeRight(k) - bw;
    c.fillStyle = "rgba(17,19,22,0.85)"; c.strokeStyle = "rgba(255,255,255,0.35)"; c.lineWidth = 2; c.beginPath(); c.roundRect ? c.roundRect(bx, by, bw, f.valid * 1.9, 14) : c.rect(bx, by, bw, f.valid * 1.9); c.fill(); noShadow(c); c.stroke(); sharpShadow(c, k);
    c.fillStyle = "#fff"; c.textAlign = "center"; c.fillText(bt, bx + bw / 2, by + f.valid * 1.32); c.textAlign = "left";
    f.badge = [bx - 12, by - 12, bx + bw + 12, by + f.valid * 1.9 + 12];
    badgeBot = by + f.valid * 1.9;
  } else { f.badge = null; }
  c.restore();
  const cnr = BR.corner && LOGOS[BR.logo] ? cornerBox(k, badgeBot, headBot, f.H - f.bot + (k === "v" ? 110 : 62)) : null;
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
  c.restore();
  paintStudioTowns(c0, k, r, headBot + 10, cbY - 16);
  c.save(); sharpShadow(c, k);
  if (P.lows) { lowKey(c, f, k, cbY, cbS); strongestMember(c, f, k, cur, r, headBot, cbY); }
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
  cv.addEventListener("pointerdown", (e) => { if (CLEAN || REC.on || CMPM()) return; if (!last && !WEBM()) return; if (PIN.mode) { placePin(k, cv, e); return; }
    const hit = pinHit(k, cv, e); if (hit) { e.preventDefault(); cv.setPointerCapture(e.pointerId); PD = { k, n: hit, id: e.pointerId, off: pinOff(k, cv, e, hit) }; cv.classList.add("pindrag"); return; }
    if (e.pointerType === "touch" && (S.dragging || !e.isPrimary)) return;   // 11-03: a second finger, or a finger while the scrubber is held: no frame drag
    e.preventDefault(); cv.setPointerCapture(e.pointerId); cv.focus({ preventScroll: true }); cv.classList.add("drag"); d = { x: e.clientX, y: e.clientY, fr: getFr(k), id: e.pointerId }; });
  const mgDragAtStart = MG.on;   // a mode opened later (WA forecast) still drags; modes that already dragged keep doing so
  cv.addEventListener("pointerdown", (e) => { if (!CLEAN && !last && MG.img && (mgDragAtStart || WAFCM())) { cv.setPointerCapture(e.pointerId); cv.focus(); cv.classList.add("drag"); d = { x: e.clientX, y: e.clientY, fr: getFr(k), id: e.pointerId }; } });
  cv.addEventListener("pointermove", (e) => { if (PD && PD.k === k && PD.id === e.pointerId) { pinMove(k, cv, e); return; }
    if (!d && !PD && PIN.show && !PIN.mode && e.pointerType === "mouse") cv.style.cursor = pinHit(k, cv, e) ? "grab" : "";
    if (!d || pz || (d.id !== undefined && e.pointerId !== d.id)) return; const s = f.W / cv.clientWidth, fr = getFr(k);
    fr.dx = d.fr.dx + (e.clientX - d.x) * s; fr.dy = d.fr.dy + (e.clientY - d.y) * s;
    // 11-05 t2480u: Active Alerts pan/zoom is per Studio frame (fr), not the shared Alerts mercator camera — so 9:16 and 16:9 move independently.
    if (OBSM()) { obsPan(k, fr); d.x = e.clientX; d.y = e.clientY; d.fr = Object.assign({}, fr); setFr(k, fr); render(k); return; }   // 11-04: free pan
    const r = crop(k, fr);   // keep the stored offset inside the panel
    fr.dx = (r.bx - r.cx) * r.kk; fr.dy = (r.by - r.cy) * r.kk; setFr(k, fr); render(k); });
  const up = (e) => {
    const wasDrag = !!d;
    if (PD && PD.k === k) { PD = null; cv.classList.remove("pindrag"); mpInfo(); renderAll(); }
    d = null; cv.classList.remove("drag");
    // After an Active Alerts pan, add labels for newly visible area without moving kept ones (t2557u).
    if (wasDrag && ALERTM() && typeof Alerts !== "undefined") {
      window.__alertSettle = window.__alertSettle || {}; window.__alertSettle[k] = 1;
      if (Alerts.settleFrameLabels) Alerts.settleFrameLabels(k);
      render(k);
    }
  }; cv.addEventListener("pointerup", up); cv.addEventListener("pointercancel", up); cv.addEventListener("lostpointercapture", (e) => { if (d && e.pointerId === d.id) up(e); });
  // 10-31 1:39 PM (Benjamin, iPhone): two-finger pinch zooms the frame (1-2.5x) about the fingers' midpoint; moving both fingers pans
  let pz = null;
  const oxy = (t) => { const b = cv.getBoundingClientRect(); return [(t.clientX - b.left) * f.W / b.width, (t.clientY - b.top) * f.H / b.height]; };
  cv.addEventListener("touchstart", (e) => {
    if (PD) { e.preventDefault(); return; }   // dragging a pin: no pinch / page scroll
    // 11-03 (Benjamin t2186u/t2187u "the zoom changes when I click on the hours scrubber"): the pinch counted every finger on the
    // screen (e.touches), so a finger on the hour scrubber (or the other frame, a button, ...) plus one resting on this frame was taken
    // as a pinch and zoomed the frame as the scrubber finger moved. Only a real two-finger pinch on this frame zooms it now
    // (targetTouches = fingers that started on this canvas, and no other finger on the screen).
    if (CLEAN || REC.on || PIN.mode || CMPM() || (!last && !WEBM() && !(WAFCM() && MG.img)) || e.targetTouches.length !== 2 || e.touches.length !== 2) { if (pz && e.targetTouches.length !== 2) pz = null; return; }
    cv._alertPinch = 1;
    e.preventDefault(); d = null;
    const [a, b] = [oxy(e.targetTouches[0]), oxy(e.targetTouches[1])], fr0 = getFr(k), r0 = crop(k, fr0), ox = (a[0] + b[0]) / 2, oy = (a[1] + b[1]) / 2;
    pz = { d: Math.max(10, Math.hypot(a[0] - b[0], a[1] - b[1])), z: OBSM() ? obsZv(fr0) / 100 : Math.max(1, fr0.zoom || 1), mx: r0.cx + (ox - f.W / 2) / r0.kk, my: r0.cy + (oy - f.H / 2) / r0.kk };
  }, { passive: false });
  cv.addEventListener("touchmove", (e) => {
    if (PD) { e.preventDefault(); return; }
    if (!pz) return; e.preventDefault(); if (e.targetTouches.length !== 2 || e.touches.length !== 2) return;   // a finger elsewhere (scrubber, other frame, a third one): hold the zoom
    const [a, b] = [oxy(e.targetTouches[0]), oxy(e.targetTouches[1])], ox = (a[0] + b[0]) / 2, oy = (a[1] + b[1]) / 2;
    if (OBSM()) { const zo = Math.min(2.5, Math.max(0.05, pz.z * Math.max(10, Math.hypot(a[0] - b[0], a[1] - b[1])) / pz.d)), fo = obsZoom(k, getFr(k), zo); setFr(k, fo); render(k); window.__spinch = { k, zoom: zo }; return; }   // 11-04: zoom out past 1x
    const zRaw = pz.z * Math.max(10, Math.hypot(a[0] - b[0], a[1] - b[1])) / pz.d;
    const z = ALERTM() ? alertZ(zRaw) : Math.min(2.5, Math.max(1, zRaw)), kk = base(k).k0 * z;
    const fr = frAt(k, pz.mx - (ox - f.W / 2) / kk, pz.my - (oy - f.H / 2) / kk, z), r = crop(k, fr);   // map point under the fingers stays under them
    fr.dx = (r.bx - r.cx) * r.kk; fr.dy = (r.by - r.cy) * r.kk; setFr(k, fr); render(k); window.__spinch = { k, zoom: z };
  }, { passive: false });
  const pend = (e) => { if (pz && e.targetTouches.length < 2) pz = null; if (e.targetTouches.length < 2) setTimeout(() => { cv._alertPinch = 0; }, 0); };
  cv.addEventListener("touchend", pend); cv.addEventListener("touchcancel", pend);
  cv.addEventListener("keydown", (e) => {
    const fr = getFr(k), st = e.shiftKey ? 10 : 1; let hit = true;
    if (OBSM() && ["+", "=", "-"].includes(e.key)) { obsZoom(k, fr, obsZv(fr) / 100 + (e.key === "-" ? -0.01 : 0.01)); e.preventDefault(); e.stopPropagation(); setFr(k, fr); render(k); return; }
    if (e.key === "ArrowLeft") fr.dx -= st; else if (e.key === "ArrowRight") fr.dx += st; else if (e.key === "ArrowUp") fr.dy -= st; else if (e.key === "ArrowDown") fr.dy += st;
    else if (e.key === "+" || e.key === "=") fr.zoom = ALERTM() ? alertZ((fr.zoom || 1) + 0.01) : Math.min(2.5, (fr.zoom || 1) + 0.01); else if (e.key === "-") fr.zoom = ALERTM() ? alertZ((fr.zoom || 1) - 0.01) : Math.max(1, (fr.zoom || 1) - 0.01);
    else if (e.key === "0") { fr.dx = fr.dy = 0; fr.zoom = 1; } else hit = false;
    if (hit && OBSM() && e.key.startsWith("Arrow")) obsPan(k, fr);
    if (hit) { e.preventDefault(); e.stopPropagation(); setFr(k, fr); render(k); }
  }, true);
  f.zoom.oninput = () => { const fr = getFr(k); if (CMPM()) { f.zoom.value = "100"; return; } if (OBSM()) obsZoom(k, fr, f.zoom.value / 100); else if (ALERTM()) { fr.zoom = alertZ(f.zoom.value / 100); } else { fr.zoom = Math.max(1, f.zoom.value / 100); } setFr(k, fr); render(k); };
  cv.parentNode.querySelector(".shd").addEventListener("click", async (e) => {
    const a = e.target.closest("button[data-a]"); if (!a || (!last && !WEBM() && !CMPM() && !WAFCM() && !OBSM())) return;
    if (a.dataset.a === "reset") { if (OBSM() && typeof Obs !== "undefined" && Obs.resetView) Obs.resetView(); setFr(k, { dx: 0, dy: 0, zoom: 1 }); if (f.zoom) f.zoom.value = "100"; render(k); if (OBSM()) render(k === "h" ? "v" : "h"); }
    if (a.dataset.a === "mp4" && (!MG.on || OBSM() || CMPM())) openMp4(k);
    if (a.dataset.a === "png" && ALERTM()) { if (!MG.img) return; const I = alertInfo(), st = I && I.t ? new Intl.DateTimeFormat("en-CA", { timeZone: "America/Los_Angeles", year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", hourCycle: "h23" }).format(I.t).replace(/[^0-9]/g, "") : "now";
      const nm = `alerts_wa_${(I && I.title || "all").replace(/[^a-z0-9]+/gi, "-").toLowerCase()}_${st}PT_${F[k].cv.width}x${F[k].cv.height}.png`;
      F[k].cv.toBlob((b) => { if (!b) return; const a2 = document.createElement("a"); a2.href = URL.createObjectURL(b); a2.download = nm; a2.click(); setTimeout(() => URL.revokeObjectURL(a2.href), 4000); }, "image/png"); return; }
    if (a.dataset.a === "png" && OBSM()) { if (!MG.img) return; const I = obsInfo(), st = I && I.t ? new Intl.DateTimeFormat("en-CA", { timeZone: "America/Los_Angeles", year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", hourCycle: "h23" }).format(I.t).replace(/[^0-9]/g, "") : "now";
      const nm = `obs_${I ? I.view : "pnw"}_${I ? I.on.map((l) => l[0]).join("-") : "plot"}_${st}_${F[k].cv.width}x${F[k].cv.height}.png`;
      cv.toBlob((b) => { const u = URL.createObjectURL(b), l = document.createElement("a"); l.href = u; l.download = nm; l.click(); setTimeout(() => URL.revokeObjectURL(u), 4000); }, "image/png"); return; }
    if (a.dataset.a === "png" && WAFCM()) { if (!MG.img) return; const nm = `wa-forecast_${(MG.src || "map").replace(/[^a-z0-9]+/gi, "-").replace(/^-|-$/g, "")}_${k === "v" ? "2160x3840" : "3840x2160"}.png`;
      cv.toBlob((b) => { const u = URL.createObjectURL(b), l = document.createElement("a"); l.href = u; l.download = nm; l.click(); setTimeout(() => URL.revokeObjectURL(u), 4000); }, "image/png"); return; }
    if (a.dataset.a === "png" && PASSM()) { if (!PF.rows) return; const nm = `pass-forecast_${PF.run.replace("/", "_")}Z_${k === "v" ? "2160x3840" : "3840x2160"}.png`;
      cv.toBlob((b) => { const u = URL.createObjectURL(b), l = document.createElement("a"); l.href = u; l.download = nm; l.click(); setTimeout(() => URL.revokeObjectURL(u), 4000); }, "image/png"); return; }
    if (a.dataset.a === "png" && CMPM()) { const nm = `compare_${F[k].cv.width}x${F[k].cv.height}.png`;
      cv.toBlob((b) => { if (!b) return; const u = URL.createObjectURL(b), l = document.createElement("a"); l.href = u; l.download = nm; l.click(); setTimeout(() => URL.revokeObjectURL(u), 4000); }, "image/png"); return; }
    if (a.dataset.a === "png" && WEBM()) { const nm = `web_${F[k].cv.width}x${F[k].cv.height}.png`;
      cv.toBlob((b) => { if (!b) return; const u = URL.createObjectURL(b), l = document.createElement("a"); l.href = u; l.download = nm; l.click(); setTimeout(() => URL.revokeObjectURL(u), 4000); }, "image/png"); return; }
    if (a.dataset.a === "png" && MG.on) { if (!MG.img) return; const nm = `meteogram_${(MG.src.split("#")[1] || "").replace(/[^a-z0-9=&_-]/gi, "").replace(/[=&]/g, "_")}_${F[k].cv.width}x${F[k].cv.height}.png`;
      cv.toBlob((b) => { const u = URL.createObjectURL(b), l = document.createElement("a"); l.href = u; l.download = nm; l.click(); setTimeout(() => URL.revokeObjectURL(u), 4000); }, "image/png"); return; }
    if (MG.on && a.dataset.a !== "reset") return;   // MP4 / OBS: maps only
    if (a.dataset.a === "png") { const st = last.step, nm = `${last.cur.run.replace("/", "_")}_${last.cur.pid}_${S.view}_f${String(st.f).padStart(3, "0")}_${cv.width}x${cv.height}.png`;
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
const REC = { on: false, cancel: false, flat: false }, PIN = { mode: null, show: false }, FPS = 30;
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
// t2827u: trackpad wheel / pinch on a frame pans or zooms only that frame. Without this, two-finger
// scroll and pinch zoomed or scrolled the page, so the 16:9 and 9:16 views moved together.
for (const k of ["v", "h"]) {
  const f = F[k], cv = f.cv;
  cv.addEventListener("wheel", (e) => {
    if (CLEAN || REC.on || CMPM() || PASSM() || (!last && !WEBM() && !(MG.on && MG.img))) return;
    e.preventDefault();
    const fr = getFr(k), s = f.W / (cv.clientWidth || 1);
    if (e.ctrlKey || e.metaKey) {
      const z0 = OBSM() ? (fr.zoom || 1) : ALERTM() ? alertZ(fr.zoom || 1) : Math.max(1, fr.zoom || 1);
      const zRaw = z0 * Math.exp(-e.deltaY * 0.01);
      const z = OBSM() ? Math.min(2.5, Math.max(0.05, zRaw)) : ALERTM() ? alertZ(zRaw) : Math.min(2.5, Math.max(1, zRaw));
      const b = cv.getBoundingClientRect(), ox = (e.clientX - b.left) * f.W / b.width, oy = (e.clientY - b.top) * f.H / b.height;
      const r0 = crop(k, fr), mx = r0.cx + (ox - f.W / 2) / r0.kk, my = r0.cy + (oy - f.H / 2) / r0.kk;
      const kk = base(k).k0 * z, fr2 = frAt(k, mx - (ox - f.W / 2) / kk, my - (oy - f.H / 2) / kk, z), r = crop(k, fr2);
      fr2.dx = (r.bx - r.cx) * r.kk; fr2.dy = (r.by - r.cy) * r.kk; setFr(k, fr2); render(k); return;
    }
    fr.dx -= (e.deltaX || 0) * s; fr.dy -= (e.deltaY || 0) * s;
    if (OBSM()) obsPan(k, fr);
    else { const r = crop(k, fr); fr.dx = (r.bx - r.cx) * r.kk; fr.dy = (r.by - r.cy) * r.kk; }
    setFr(k, fr); render(k);
  }, { passive: false });
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
  if (CMPM()) return openCmpMp4(k);
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
  if (CMPM()) {
    if ($s("mp4p").hidden) return; const st = cmpSteps(); if (!st || !st.length || !CMP.R) return;
    const i = Math.min(CMP.R.i || 0, st.length - 1), sl = $("hscrub") || $("step"), mx = Math.max(1, st.length - 1);
    if (+$s("mpa").options.length !== st.length) return;
    $s("mpnow").textContent = `Map now: ${lbl(st[i])}`;
    const a = +$s("mpa").value, b = +$s("mpb").value;
    if (sl) { sl.style.setProperty("--ra", String(Math.min(a, b) / mx)); sl.style.setProperty("--rb", String(Math.max(a, b) / mx)); }
    document.body.classList.add("mprange"); return;
  }
  const Rsync = S.run && S.runs[S.run];
  if ($s("mp4p").hidden || !Rsync || !Rsync.steps) return; const st = Rsync.steps, sl = $("step"), mx = Math.max(1, +sl.max || st.length - 1);
  if (+$s("mpa").options.length !== st.length) return;   // run changed: options rebuilt on next open
  $s("mpnow").textContent = `Map now: ${lbl(st[S.i])}`;
  const a = +$s("mpa").value, b = +$s("mpb").value; sl.style.setProperty("--ra", String(Math.min(a, b) / mx)); sl.style.setProperty("--rb", String(Math.max(a, b) / mx));
  const hs = $("hscrub"); if (hs) { hs.style.setProperty("--ra", String(Math.min(a, b) / mx)); hs.style.setProperty("--rb", String(Math.max(a, b) / mx)); }   // 11-04 t2315u: long scrubber in the bar shows the loop range too
  document.body.classList.add("mprange");
}
function mpInfo() {
  if (CMPM()) {
    mpSync(); const st = cmpSteps() || [], s0 = +$s("mps").value, s1 = $s("mps1").value; $s("mpsv").textContent = `${s0} map${s0 === 1 ? "" : "s"}/s`;
    const idx = cmpPickIdx(st), T = loopTimes(idx.length), hold = +$s("mph").value;
    $s("mppins").textContent = "";
    $s("mpinfo").textContent = idx.length < 2 || !st[idx[0]] ? "Pick an end hour after the start hour." :
      `${idx.length} maps, F+${st[idx[0]].f} to F+${st[idx[idx.length - 1]].f} · both panels · ${(T[idx.length] + hold).toFixed(1)} s of video at 30 fps${s1 && +s1 !== s0 ? ` (speed ${s0} → ${s1} maps/s)` : ""}`;
    return;
  }
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
function mpMode() { if (CMPM() && $s("mpmode").value === "pan") $s("mpmode").value = "loop"; const pan = $s("mpmode").value === "pan"; if (pan && $s("mpz0").value === "f") $s("mpz0").value = "1.8"; /* a pan needs room to move */ $s("mppan").hidden = !pan; PIN.show = pan && !CMPM(); render("v"); render("h"); mpInfo(); }
let muxP = null;
const loadMuxer = () => muxP || (muxP = new Promise((res, rej) => { const sc = document.createElement("script"); sc.src = "vendor/mp4-muxer.js?v=522"; sc.onload = res; sc.onerror = () => { muxP = null; rej(new Error("could not load the MP4 writer")); }; document.head.appendChild(sc); }));
async function makeEncoder(cv, W, H) {
  W = (cv && cv.width) || W; H = (cv && cv.height) || H;
  const big = W * H > 1080 * 1920 * 1.5;   // 2x model frames need H.264 level 5.1; keep the queue short so 8 MP frames don't pile up
  if (window.VideoEncoder && window.VideoFrame) {
    for (const codec of (big ? ["avc1.640033", "avc1.640034", "avc1.640028", "avc1.4d0028", "avc1.42002a"] : ["avc1.640028", "avc1.4d0028", "avc1.42002a"])) {
      const cfg = { codec, width: W, height: H, bitrate: big ? 14e6 : 10e6, framerate: FPS, avc: { format: "avc" } };
      let ok = false; try { ok = (await VideoEncoder.isConfigSupported(cfg)).supported; } catch (e) { /* next */ }
      if (!ok) continue;
      await loadMuxer();
      const mux = new Mp4Muxer.Muxer({ target: new Mp4Muxer.ArrayBufferTarget(), video: { codec: "avc", width: W, height: H, frameRate: FPS }, fastStart: "in-memory" });
      let err = null; const ve = new VideoEncoder({ output: (ch, meta) => mux.addVideoChunk(ch, meta), error: (e) => { err = e; } });
      ve.configure(cfg);
      return { how: `H.264 (${codec}) via WebCodecs`, ext: "mp4",
        async add(n) { if (err) throw err; while (ve.encodeQueueSize > (big ? 2 : 4)) await sleep(4);
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
function openCmpMp4(k) {
  const steps = cmpSteps(); if (!steps || steps.length < 2) { mpSt("Wait for the compare maps to load."); return; }
  const a = $s("mpa"), b = $s("mpb"), opts = steps.map((x, i) => `<option value="${i}">${lbl(x)}</option>`).join("");
  a.innerHTML = opts; b.innerHTML = opts;
  const now = Math.min((CMP.R && CMP.R.i) || 0, steps.length - 1), e5 = steps.findIndex((x) => x.f >= steps[now].f + 120);
  a.value = String(now); b.value = String(e5 > now ? e5 : steps.length - 1);
  loadOpts(); $s("mpk").value = k; $s("mpmode").value = "loop"; $s("mp4p").hidden = false; $s("mpout").hidden = true; mpMode(); mpInfo();
}
async function cmpGo(i) {
  const api = cmpApi(), steps = cmpSteps(); if (!api || !steps || !steps[i]) return;
  api.setHour(i); const want = steps[i].f, t0 = performance.now();
  while (performance.now() - t0 < 12000) { cmpGrab(); const got = CMP.view.R && CMP.view.R.step; if (CMP.R && CMP.R.i === i && got && got.f === want) return; await sleep(80); }
}
async function makeCmpMp4() {
  if (REC.on) return;
  const steps = cmpSteps(); if (!steps || steps.length < 2) { mpSt("Wait for the compare maps to load."); return; }
  const k = $s("mpk").value, f = F[k], idx = cmpPickIdx(steps);
  if (idx.length < 2) { mpSt("Pick an end hour after the start hour."); return; }
  if ((BR.corner || BR.card || BR.lower) && LOGOS[BR.logo]) { const t0 = performance.now(); while (!getLogo() && performance.now() - t0 < 4000) await sleep(50); }
  const T = loopTimes(idx.length), holdN = Math.round(+$s("mph").value * FPS), t0 = performance.now(); let enc = null;
  REC.on = true; REC.cancel = false; $s("mpout").hidden = true; $s("mpgo").disabled = true; $s("mpstop").hidden = false; document.body.classList.add("rec");
  try {
    enc = await makeEncoder(f.cv, f.W, f.H); const totN = Math.round(T[idx.length] * FPS) + holdN, pg = $s("mpprog"); pg.hidden = false; pg.value = 0;
    await cmpGo(idx[0]); await render(k); let n = 0, cardN = 0;
    if (BR.card) { const cN = Math.round(1.5 * FPS), fN = Math.round(0.5 * FPS), c = f.cv.getContext("2d");
      for (let j = 0; j < cN; j++) { await render(k); titleCard(k, c, j < cN - fN ? 1 : (cN - j) / fN, steps[idx[0]], steps[idx[idx.length - 1]]); await enc.add(j); }
      enc.off = cN; cardN = cN; }
    for (let j = 0; j < idx.length; j++) {
      if (REC.cancel) throw new Error("stopped");
      if (j) { if (enc.idle) enc.idle(); await cmpGo(idx[j]); }
      mpSt(`Making video… F+${steps[idx[j]].f} (${j + 1}/${idx.length})`);
      const n0 = Math.round(T[j] * FPS), n1 = Math.round(T[j + 1] * FPS) + (j === idx.length - 1 ? holdN : 0); let drawn = false;
      for (; n < n1; n++) { if (!drawn || enc.realtime) { await render(k); drawn = true; } await enc.add(n + (enc.off || 0)); if (n % 6 === 0) pg.value = n / totN; }
    }
    pg.value = 1; mpSt("Finishing…"); const how = enc.how, blob = await enc.done(); enc = null;
    const nm = `compare_F${steps[idx[0]].f}-F${steps[idx[idx.length - 1]].f}_${f.cv.width}x${f.cv.height}.${blob.type.includes("mp4") ? "mp4" : "webm"}`;
    const u = URL.createObjectURL(blob), v = $s("mpv"), dl = $s("mpdl"); if (v.dataset.u) URL.revokeObjectURL(v.dataset.u); v.dataset.u = u; v.src = u; dl.href = u; dl.download = nm;
    const file = new File([blob], nm, { type: blob.type }); $s("mpshare").hidden = !(navigator.canShare && navigator.canShare({ files: [file] })); $s("mpshare").onclick = () => navigator.share({ files: [file] }).catch(() => {});
    n += cardN; $s("mpout").hidden = false; window.__mp4 = { name: nm, bytes: blob.size, frames: n, seconds: n / FPS, how, ms: Math.round(performance.now() - t0), blob };
    mpSt(`Done: ${(blob.size / 1e6).toFixed(1)} MB, ${(n / FPS).toFixed(1)} s, made in ${((performance.now() - t0) / 1000).toFixed(0)} s`);
  } catch (e) { if (enc) enc.abort(); mpSt(e.message === "stopped" ? "Stopped." : "Could not make the video: " + (e.message || e)); window.__mp4 = { error: String(e.message || e) }; }
  finally { REC.on = false; $s("mpgo").disabled = false; $s("mpstop").hidden = true; $s("mpprog").hidden = true; document.body.classList.remove("rec"); const back = (CMP.R && CMP.R.i) || 0; cmpGo(back); }
}
async function makeMp4() {
  if (OBSM()) return makeObsMp4();
  if (CMPM()) return makeCmpMp4();
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
    try { enc = await makeEncoder(f.cv, f.cv.width, f.cv.height); }
    catch (e) { if ((f.ss || 1) > 1) { REC.flat = true; ssFit(f, 1); await render(k); enc = await makeEncoder(f.cv, f.cv.width, f.cv.height); } else throw e; }
    const totN = Math.round(T[idx.length] * FPS) + holdN, pg = $s("mpprog"); pg.hidden = false; pg.value = 0;
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
    const nm = `${run.replace("/", "_")}_${last.cur.pid}_${S.view}_F${steps[idx[0]].f}-F${steps[idx[idx.length - 1]].f}_${f.cv.width}x${f.cv.height}${pan ? "_track" : ""}.${blob.type.includes("mp4") ? "mp4" : "webm"}`;
    const u = URL.createObjectURL(blob), v = $s("mpv"), dl = $s("mpdl"); if (v.dataset.u) URL.revokeObjectURL(v.dataset.u); v.dataset.u = u; v.src = u; dl.href = u; dl.download = nm;
    const file = new File([blob], nm, { type: blob.type }); $s("mpshare").hidden = !(navigator.canShare && navigator.canShare({ files: [file] })); $s("mpshare").onclick = () => navigator.share({ files: [file] }).catch(() => {});
    n += cardN; $s("mpout").hidden = false; window.__mp4 = { name: nm, pan: pan ? { follow: trk ? "track" : "pins", a: pins.a, b: pins.b } : null, bytes: blob.size, frames: n, seconds: n / FPS, branded: !!(BR.card || BR.lower), corner: !!(BR.corner && LOGOS[BR.logo]) ? BR.cpos : null, how, ms: Math.round(performance.now() - t0), blob };
    mpSt(`Done: ${(blob.size / 1e6).toFixed(1)} MB, ${(n / FPS).toFixed(1)} s, made in ${((performance.now() - t0) / 1000).toFixed(0)} s`);
  } catch (e) { if (enc) enc.abort(); mpSt(e.message === "stopped" ? "Stopped." : "Could not make the video: " + (e.message || e)); window.__mp4 = { error: String(e.message || e) }; }
  finally { REC.on = false; REC.flat = false; window.__vjNoJump = false; $s("mpgo").disabled = false; $s("mpstop").hidden = true; $s("mpprog").hidden = true; document.body.classList.remove("rec"); if (S.run === run) { S.i = keep; $("step").value = keep; } draw(); }
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
    const nm = `obs_${I.view}_${I.on.map((l) => l[0]).join("-")}_${stp}_${f.cv.width}x${f.cv.height}${pan ? "_AtoB" : ""}.${blob.type.includes("mp4") ? "mp4" : "webm"}`;
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
  if (S.man && S.man.models && S.man.models.ifs) StormFind.IFS.setCrop(S.man.models.ifs.crop);
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
    if (S.man && S.man.models && S.man.models.ifs) StormFind.IFS.setCrop(S.man.models.ifs.crop);
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
      bg = f.badge || [badgeRight(k) - 220, top - 12, badgeRight(k) + 12, top + f.valid * 1.9 + 12], m_ = 30;
    return [hd, bg].some((b) => X + EX > b[0] - m_ && X - EX < b[2] + m_ && Y + EY > b[1] - m_ && Y - EY < b[3] + m_); });
};
function bxFill() {
  const ck = (id, v, t, on) => `<label><input type="checkbox" data-g="${id}" value="${v}"${on ? " checked" : ""}> ${t}</label>`, [m0] = S.run.split("/"), R_ = S.runs[S.run];
  $s("bxm").innerHTML = MORDER.filter((m) => S.man.models[m] && (S.man.runs[m] || []).length).map((m) => ck("m", m, S.man.models[m].site || m, m === m0)).join("");
  $s("bxp").innerHTML = Object.entries(PRODS()).filter(([, p]) => p.fields.every((fl) => R_.fields.includes(fl))).map(([k, p]) => ck("p", k, p.title, k === S.prod)).join("");
  $s("bxv").innerHTML = Object.entries(typeof rrfsMenuViews === "function" ? rrfsMenuViews() : VIEWS()).map(([k, v]) => ck("v", k, v.label, k === S.view)).join(""); bxCount();
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
      const now = CMPM() && CMP.R ? CMP.R.i : S.i, n = CMPM() ? ((cmpSteps() || []).length || 1) : S.runs[S.run].steps.length;
      if (m_ === "sa") { a.value = String(now); if (+z.value <= now) z.value = String(Math.min(n - 1, now + 1)); }
      else { z.value = String(now); if (+a.value >= now) a.value = String(Math.max(0, now - 1)); }
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
  $s("brcardpv").addEventListener("click", async () => { if ((!last && !CMPM()) || REC.on) return; const k = $s("mpk").value; getLogo(); await sleep(80); await render(k); titleCard(k, F[k].cv.getContext("2d"), 1, null, null); setTimeout(() => render(k), 2500); });
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
    const Rplay = S.runs[S.run]; if (!Rplay || !Rplay.steps) return; const st = Rplay.steps; let i = S.i + 1; if (stepH) while (i < st.length && st[i].f - st[S.i].f < stepH) i++;
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
  if (CLEAN || innerWidth <= 820) { clear(); if (typeof cmpFitPanel === "function") cmpFitPanel(); return; }
  const cs = getComputedStyle(st), padX = parseFloat(cs.paddingLeft) + parseFloat(cs.paddingRight), padB = parseFloat(cs.paddingBottom) + 2;
  const gap = parseFloat(cs.columnGap) || 18, hint = fh.querySelector(".shint"), MINV = 300;   // below ~300 px tall the page scrolls instead
  // STUDIO_NEW_MODE.md: every Studio mode draws into the same two canvases (#cv 9:16, #ch 16:9) and is sized ONLY here. A mode is a
  // body class "<name>mode"; any such class is taken off while the Map layout is measured, so a new mode gets Map's exact frames.
  // 11-04 (Benjamin t2316u-t2318u "satellite viewers ... same exact size as the model views", "same exact size and placement in the
  // window browser", "pass forecaster view too"): Observations / Meteogram / Pass Forecaster frames take the Map mode's size AND spot.
  // The Map layout is measured with the mode class off (same sync pass, never painted), then the mode's panel is padded or capped
  // (scrolls) so the frames start at the same y.
  const bd = document.body, MODES = [...bd.classList].filter((c) => /^[a-z0-9]+mode$/.test(c)), pnl = document.getElementById("mgp");
  if (pnl) { pnl.style.maxHeight = ""; pnl.style.overflowY = ""; pnl.style.touchAction = ""; } st.style.marginTop = "";
  const SHD = [fv, fh].map((f) => f.querySelector(".shd")); for (const e of SHD) e.style.minHeight = "";
  for (const c of MODES) bd.classList.remove(c);
  let wv = 0, wh = 0;
  for (let it = 0; it < 5; it++) {
    const availW = st.clientWidth - padX - gap, sy = scrollY;
    const availV = innerHeight - (cvv.getBoundingClientRect().top + sy) - padB;
    let under = 0; for (let e = cvh.nextElementSibling; e; e = e.nextElementSibling) if (!e.classList.contains("webov")) under += e.offsetHeight + 6;   // 11-07 t2698u: the Web overlay sits on the canvas (absolute), not under it   // hint, hour scrubber, request button
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
  if (WEBM()) { try { placeWeb("v"); placeWeb("h"); } catch (e) { /* frames not ready */ } }
  if (typeof cmpFitPanel === "function") cmpFitPanel();
}
// ---- 11-01 2 PM (Benjamin t2041u/t2042u): hour scrubber under the 16:9 frame (every forecast hour the model data has: the viewer's
// own steps, same as the top slider, which it drives), a hover value readout on both frames (the viewer's readout(): same numbers
// and units as the map page), and the "Request a change" button moved off the 9:16 frame into the space under the 16:9 frame.
let scrubSync = () => {};
if (!CLEAN) {
  const fh = document.getElementById("fh"), hint = fh.querySelector(".shint"), stp = document.getElementById("step");
  const box = document.createElement("div"); box.id = "scrub";
  box.innerHTML = `<div class="sr"><button type="button" id="sprev" aria-label="Previous hour">&lsaquo;</button><div class="sw"><input type="range" id="hscrub" min="0" max="0" value="0" aria-label="Forecast hour"><div id="sticks"></div></div><button type="button" id="snext" aria-label="Next hour">&rsaquo;</button><b id="shour"></b></div>`;
  // 11-04 (Benjamin t2315u "put the longer one underneath the Waves button, underneath the right side of the View button"): on desktop
  // the long scrubber (24 h ticks + F+ / valid readout) moves into the menu bar in place of the short slider, right after Prev / Play /
  // Next, and stretches across the row under the tabs and the View menu. The short #step stays in the page (hidden) and is still the
  // one the viewer reads; this one drives it. Phones keep it under the 16:9 frame (bottom dock unchanged).
  // 11-04 (t2343u): its own row under the menu items, starting under the View menu and running ~480 px toward Share (not on the menu line)
  // 11-05 (Benjamin t2444u): desktop second menu row = action buttons on the LEFT (Save image, Share, Meteogram, Pass Forecaster,
  // Observations, Request a change), then the long hour scrubber to their right filling the rest of the line (in flow, wraps on narrow).
  if (innerWidth > 820) { const bar_ = document.getElementById("bar"), ar = document.createElement("div"); ar.id = "actrow";
    ["save", "share", "mgbtn", "pfbtn", "obsbtn"].forEach(id => { const e = document.getElementById(id); if (e) ar.appendChild(e); });
    box.classList.add("inbar", "inrow"); document.body.classList.add("longscrub", "actrow"); ar.appendChild(box); const st_ = document.getElementById("stat"); bar_.insertBefore(ar, st_ && st_.parentNode === bar_ ? st_.nextSibling : null);
    const ln = document.getElementById("loadnote"); if (ln) box.querySelector(".sw").appendChild(ln);
    document.addEventListener("DOMContentLoaded", () => { const rq = document.getElementById("rqb"); if (rq) ar.insertBefore(rq, box); const st2 = document.getElementById("stat"); if (st2) ar.appendChild(st2); }); }
  else if (false) { const bar_ = document.getElementById("bar"); box.classList.add("inbar"); document.body.classList.add("longscrub"); bar_.appendChild(box);
    // t2343u: overlay row under the View menu (absolute, so the bar height and the frames stay exactly as in Map); the short #step keeps its space, invisible
    // Placement: nearest free spot under the View menu (scan down, then left toward Share) that touches no visible control or frame,
    // so the scrubber never covers a button and the frames never move.
    const vx = () => { const v = document.getElementById("view"), lb = v && v.closest("label"); if (!lb) return; const br = bar_.getBoundingClientRect(), r = lb.getBoundingClientRect();
      const w = Math.min(480, Math.max(240, br.width - 24 - 230)); box.style.setProperty("--scrw", w + "px");
      const obs = []; document.querySelectorAll("button,select,input,canvas,span,b,small,a,p").forEach(e => { if (box.contains(e) || e === stp || e.contains(box)) return; if (e.closest && e.closest("footer")) return;
        if (!e.offsetParent && getComputedStyle(e).position !== "fixed") return; const q = e.getBoundingClientRect(); if (q.width < 2 || q.height < 2 || q.bottom < 0 || q.top > 400 || q.left < -50) return;
        if (getComputedStyle(e).visibility === "hidden") return; if (/^(SPAN|B|SMALL|A|DIV|P)$/.test(e.tagName) && ![...e.childNodes].some(n => n.nodeType === 3 && n.textContent.trim())) return; obs.push(q); });
      box.style.setProperty("--scry", "-999px"); const bb = box.getBoundingClientRect(), bw = bb.width || (w + 230), bh = Math.max(24, Math.min(40, bb.height || 34));
      const hit = (x, y) => obs.some(q => x < q.right + 4 && x + bw > q.left - 4 && y < q.bottom + 2 && y + bh > q.top - 2);
      let best = null; for (let y = r.bottom + 2; y < 300 && !best; y += 2) { const x0 = Math.max(12, r.left - bw + 120), x1 = Math.min(r.right - 120, innerWidth - 12 - bw), xs = []; for (let x = x0; x <= x1; x += 8) xs.push(x); xs.sort((a, b) => Math.abs(a - r.left) - Math.abs(b - r.left)); for (const x of xs) if (!hit(x, y)) { best = [x, y]; break; } }
      if (!best) best = [Math.max(12, Math.min(r.left, innerWidth - 12 - bw)), r.bottom + 4];
      box.style.setProperty("--scrx", (best[0] - br.left) + "px"); box.style.setProperty("--scry", (best[1] - br.top) + "px"); };
    vx(); setTimeout(vx, 1500); setTimeout(vx, 5000); addEventListener("resize", vx); if ("ResizeObserver" in window) new ResizeObserver(vx).observe(bar_);
    const ln = document.getElementById("loadnote"); if (ln) box.querySelector(".sw").appendChild(ln); }
  else fh.insertBefore(box, hint);
  const sl = document.getElementById("hscrub"), tk = document.getElementById("sticks"), lab = document.getElementById("shour");
  const fwd = (type) => stp.dispatchEvent(new Event(type));
  sl.addEventListener("pointerdown", () => { if (!CMPM()) fwd("pointerdown"); });
  for (const ev of ["pointerup", "pointercancel", "change"]) sl.addEventListener(ev, () => { if (!CMPM()) fwd("change"); });
  sl.addEventListener("input", () => { if (CMPM()) { cmpSetHour(+sl.value); return; } stp.value = sl.value; fwd("input"); });
  document.getElementById("sprev").onclick = () => { if (CMPM()) { cmpStep(-1); return; } document.getElementById("prev").click(); };
  document.getElementById("snext").onclick = () => { if (CMPM()) { cmpStep(1); return; } document.getElementById("next").click(); };
  let tkKey = "";
  scrubSync = () => {
    if (CMPM()) { cmpScrub(); return; }
    const R_ = S.runs[S.run]; if (!R_ || !R_.steps) return; const st = R_.steps, n = st.length, s = st[S.i] || {};
    sl.max = Math.max(0, n - 1); sl.value = S.i;
    lab.textContent = `F+${s.f}` + (s.valid_line ? `  \u00b7  ${s.valid_line.replace(/^Valid /, "")}` : "");
    const key = S.run + ":" + n; if (key === tkKey) return; tkKey = key;   // tick labels every 24 h (by forecast hour), rebuilt per run / new hours
    fixShourW(st.map(x => `F+${x.f}` + (x.valid_line ? `  \u00b7  ${x.valid_line.replace(/^Valid /, "")}` : "")));   // t2775u: fixed readout width per run
    tk.innerHTML = st.map((x, i) => x.f % 24 === 0 && (x.f % 48 === 0 || st[n - 1].f <= 168) ? `<span style="left:calc(9px + (100% - 18px) * ${n > 1 ? i / (n - 1) : 0})">${x.f}</span>` : "").join("");
  };
  // 11-05 t2486u: Active Alerts hover — show alert type(s) under the cursor on Studio frames
  (function alertHoverTip() {
    const tip = document.getElementById("stip") || (() => { const d = document.createElement("div"); d.id = "stip"; d.hidden = true; document.body.appendChild(d); return d; })();
    for (const k of ["v", "h"]) {
      const f = F[k], cv = f.cv;
      cv.addEventListener("pointermove", (e) => {
        if (!ALERTM() || e.pointerType !== "mouse" || e.buttons || REC.on || typeof Alerts === "undefined" || !Alerts.hitAt || !MG.img) return;
        const r = crop(k, getFr(k)), b = cv.getBoundingClientRect();
        const ox = (e.clientX - b.left) * f.W / b.width, oy = (e.clientY - b.top) * f.H / b.height;
        const bx = r.cx + (ox - f.W / 2) / r.kk, by = r.cy + (oy - f.H / 2) / r.kk;  // bitmap CSS px (al-canvas space)
        const dpr = (Alerts._state && Alerts._state.dpr) || 1;
        const sx = bx / dpr, sy = by / dpr;
        if (sx < 0 || sy < 0 || sx > 1600 || sy > 1600) { tip.hidden = true; return; }
        const [lon, lat] = Alerts.cssToLonLat(sx, sy);
        const hits = Alerts.hitAt(lon, lat);
        if (!hits.length) { tip.hidden = true; cv.style.cursor = ""; return; }
        tip.textContent = hits.join(" · "); tip.hidden = false;
        tip.style.left = (e.clientX + 14) + "px"; tip.style.top = (e.clientY - 32) + "px";
        cv.style.cursor = "pointer";
      });
      cv.addEventListener("pointerleave", () => { if (ALERTM()) { tip.hidden = true; cv.style.cursor = ""; } });
      let down = null;
      cv.addEventListener("pointerdown", (e) => { if (!ALERTM() || CLEAN) { down = null; return; } down = { x: e.clientX, y: e.clientY, id: e.pointerId }; });
      cv.addEventListener("pointerup", (e) => {
        const d0 = down; down = null;
        if (!d0 || d0.id !== e.pointerId || !ALERTM() || CLEAN || cv._alertPinch) return;
        if (typeof Alerts === "undefined" || !Alerts.openAt || !Alerts.isMapClick(e.clientX - d0.x, e.clientY - d0.y)) return;
        const r = crop(k, getFr(k)), b = cv.getBoundingClientRect();
        const ox = (e.clientX - b.left) * f.W / b.width, oy = (e.clientY - b.top) * f.H / b.height;
        const bx = r.cx + (ox - f.W / 2) / r.kk, by = r.cy + (oy - f.H / 2) / r.kk;
        const dpr = (Alerts._state && Alerts._state.dpr) || 1;
        const [lon, lat] = Alerts.cssToLonLat(bx / dpr, by / dpr);
        Alerts.openAt(lon, lat);
      });
    }
  })();

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
  sw.innerHTML = `Studio <select id="smode"><option value="map">Map</option><option value="mg">Meteogram</option><option value="obs">Observations</option><option value="pass">Pass Forecaster</option><option value="wafc">WA Forecast Maps</option><option value="alert">Active Alerts</option><option value="cmp">Compare</option><option value="web">Web</option></select>`; bar.insertBefore(sw, bar.firstChild);
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
  // WA Forecast Maps: wamaps.html in a panel iframe (its own pickers; map hidden there); its URL (kind / model / day / window / view / run) is kept
  // in studio:wafcq so a refresh comes back on the same map; the finished canvas is grabbed after each draw (window.__drawn)
  let wf_ = null, wdrawn = -1; const wcss = `#wrap{position:absolute!important;left:-99999px!important;top:0}#save,#bar>a,#bar>b,.lic{display:none!important}body{margin:0!important;padding:6px 10px!important;background:#1d2027!important;overflow:hidden}#bar{margin:0!important;padding:0!important;position:static!important}`;
  const wgrab = () => { try { const w = wf_.contentWindow, d = wf_.contentDocument, cv_ = d && d.getElementById("map"); if (!w || !cv_) return;
    const q = w.location.search; if (q) { localStorage.setItem("studio:wafcq", q); try { sessionStorage.setItem("studio:wafcq", q); } catch (e) { /* private */ } }
    const m_ = d.getElementById("msg"), dn = w.__drawn || 0;
    if (dn !== wdrawn && cv_.width && dn > 0) { wdrawn = dn; MG.img = cv_; MG.src = q.replace(/^\?/, "").replace(/&?run=[^&]*/, ""); MG.msg = ""; renderAll(); }
    else if (!dn && m_ && /Could not|No /.test(m_.textContent) && MG.msg !== m_.textContent) { MG.msg = m_.textContent; renderAll(); } } catch (e) { /* iframe loading */ } };
  for (const k of ["v", "h"]) { const ov = document.createElement("div"); ov.className = "webov"; ov.hidden = true;
    const ifr = document.createElement("iframe"); ifr.title = k === "v" ? "Web page, 9:16" : "Web page, 16:9"; ifr.setAttribute("referrerpolicy", "no-referrer"); ov.appendChild(ifr);
    const bar = document.createElement("div"); bar.className = "webgrip"; bar.title = "Drag to move the page in the frame"; bar.textContent = "⠇⠇ drag to move"; ov.appendChild(bar); webGrip(k, bar);
    F[k].cv.parentNode.appendChild(ov); F[k].web = ov; }
  addEventListener("scroll", () => { if (WEBM()) { placeWeb("v"); placeWeb("h"); } }, true);
  const stopMainPlay = () => { if (S.timer) { clearInterval(S.timer); S.timer = null; const b = document.getElementById("play"); if (b) b.textContent = "Play"; } };
  const hourGuard = (el, fn) => { if (!el) return; el.addEventListener("click", (e) => { if (!CMPM()) return; e.preventDefault(); e.stopImmediatePropagation(); fn(); }, true); };
  hourGuard(document.getElementById("prev"), () => cmpStep(-1));
  hourGuard(document.getElementById("next"), () => cmpStep(1));
  hourGuard(document.getElementById("play"), () => {
    const b = document.getElementById("play");
    if (CMP.play) { clearInterval(CMP.play); CMP.play = 0; b.textContent = "Play"; return; }
    b.textContent = "Stop"; CMP.play = setInterval(() => cmpStep(1), 800);
  });
  const stepEl = document.getElementById("step");
  if (stepEl) stepEl.addEventListener("input", (e) => { if (!CMPM()) return; e.stopImmediatePropagation(); cmpSetHour(+stepEl.value); }, true);
  addEventListener("keydown", (e) => {
    if (!CMPM() || /^(INPUT|TEXTAREA|SELECT)$/.test(e.target.tagName)) return;
    if (e.key === "ArrowRight" || e.key === "ArrowLeft") { e.preventDefault(); e.stopPropagation(); cmpStep(e.key === "ArrowRight" ? 1 : -1); }
  }, true);
  const setMode = (mode) => {
    if (mode !== "web") { webHide(); webMirStop(); }
    if (mode !== "cmp" && CMP.play) { clearInterval(CMP.play); CMP.play = 0; const b = document.getElementById("play"); if (b && b.textContent === "Stop") b.textContent = "Play"; }
    document.body.classList.remove("cmpmode", "webmode", "webdrag");
    if (mode === "web") {
      MG.on = true; MG.kind = "web"; MG.img = null; MG.msg = ""; saveMode("web"); clearInterval(poll); stopMainPlay();
      document.body.classList.remove("mgmode", "obsmode", "passmode", "alertmode", "wafcmode"); document.body.classList.add("webmode");
      if (typeof Obs !== "undefined" && Obs.hide) Obs.hide(); if (typeof Alerts !== "undefined" && Alerts.hide) Alerts.hide();
      PIN.show = false; PIN.mode = null;
      if (!document.getElementById("webp")) { const wp = document.createElement("div"); wp.id = "webp";
        wp.innerHTML = `<label>Page <input id="weburl" type="url" inputmode="url" placeholder="https://example.com" spellcheck="false" autocomplete="url"></label><button type="button" id="webgo">Open</button><button type="button" id="webmir" title="Show the live 16:9 page in the 9:16 frame too (Chrome asks to share this tab)">Mirror 16:9 into 9:16</button><span class="mp-note">If this stays blank, the site probably doesn't allow embedding.</span>`;
        pnl.appendChild(wp);
        const go = () => { const inp = document.getElementById("weburl"), u = webNormalize(inp.value); if (!u) return; inp.value = u; webApply(u); };
        document.getElementById("webgo").onclick = go; document.getElementById("webmir").onclick = webMirStart;
        document.getElementById("weburl").addEventListener("keydown", (e) => { if (e.key === "Enter") { e.preventDefault(); go(); } });
        document.getElementById("weburl").addEventListener("change", go);
        let saved = ""; try { saved = localStorage.getItem("studio:weburl") || ""; } catch (e) { /* private */ }
        if (saved) { document.getElementById("weburl").value = saved; webApply(saved); } }
      renderAll(); fitFrames(); return;
    }
    if (mode === "cmp") {
      MG.on = true; MG.kind = "cmp"; MG.img = null; MG.msg = ""; saveMode("cmp"); clearInterval(poll); stopMainPlay();
      document.body.classList.remove("mgmode", "obsmode", "passmode", "alertmode", "wafcmode"); document.body.classList.add("cmpmode");
      if (typeof Obs !== "undefined" && Obs.hide) Obs.hide(); if (typeof Alerts !== "undefined" && Alerts.hide) Alerts.hide();
      PIN.show = false; PIN.mode = null;
      if (!cmpFrame) { cmpFrame = document.createElement("iframe"); cmpFrame.id = "cmpf"; cmpFrame.title = "Compare controls"; cmpFrame.src = cmpSrc(); cmpFrame.addEventListener("load", cmpFitPanel); pnl.appendChild(cmpFrame); }
      poll = setInterval(() => { cmpGrab(); cmpFitPanel(); }, 300); renderAll(); fitFrames(); cmpFitPanel(); return;
    }
    if (mode === "wafc") { MG.on = true; MG.kind = "wafc"; MG.img = null; MG.msg = ""; wdrawn = -1; saveMode("wafc"); clearInterval(poll);
      document.body.classList.remove("mgmode", "obsmode", "passmode", "alertmode"); document.body.classList.add("wafcmode"); if (typeof Obs !== "undefined" && Obs.hide) Obs.hide(); if (typeof Alerts !== "undefined" && Alerts.hide) Alerts.hide();
      if (!wf_) { wf_ = document.createElement("iframe"); wf_.id = "wff"; wf_.title = "WA forecast map pickers"; wf_.src = "wamaps.html" + ((() => { try { return sessionStorage.getItem("studio:wafcq"); } catch (e) { return null; } })() || localStorage.getItem("studio:wafcq") || "?kind=low&view=full");   // this tab first (refresh), else the last one used
        wf_.onload = () => { try { const st = wf_.contentDocument.createElement("style"); st.textContent = wcss; wf_.contentDocument.head.appendChild(st); } catch (e) { /* not ready */ } };
        pnl.appendChild(wf_); }
      poll = setInterval(wgrab, 300); renderAll(); fitFrames(); return; }
    document.body.classList.remove("wafcmode"); if (MG.kind === "wafc") { MG.img = null; MG.kind = "mg"; MG.on = false; }
    const wasPass = PASSM(); if (mode === "pass") { MG.on = true; MG.kind = "pass"; MG.img = null; saveMode("pass"); clearInterval(poll);
      document.body.classList.remove("mgmode", "obsmode", "alertmode"); document.body.classList.add("passmode"); if (typeof Obs !== "undefined" && Obs.hide) Obs.hide(); if (typeof Alerts !== "undefined" && Alerts.hide) Alerts.hide();
      pfLoad(); renderAll(); fitFrames(); return; }
    document.body.classList.remove("passmode"); if (wasPass) { MG.img = null; MG.kind = "mg"; }
    const wasAlert = ALERTM();
    if (mode === "alert") {
      MG.on = true; MG.kind = "alert"; MG.img = null; MG.src = ""; MG.msg = "";
      saveMode("alert"); clearInterval(poll);
      document.body.classList.remove("mgmode", "obsmode", "passmode", "wafcmode"); document.body.classList.add("alertmode");
      if (typeof Obs !== "undefined" && Obs.hide) Obs.hide();
      if (!document.getElementById("alertp")) { const ap = document.createElement("div"); ap.id = "alertp"; ap.innerHTML = `<div id="alert-root"></div>`; pnl.appendChild(ap); }
      window.__alertLoad = window.__alertLoad || new Promise((ok, bad) => {
        if (!document.querySelector('link[href^="alert/alert.css"]')) { const l = document.createElement("link"); l.rel = "stylesheet"; l.href = "alert/alert.css?v=20261106a4"; document.head.appendChild(l); }
        const sc = document.createElement("script"); sc.src = "alert/alert.js?v=20261110sh4"; sc.onload = ok; sc.onerror = bad; document.body.appendChild(sc); });
      MG.msg = "Loading alerts\u2026"; let asig = "";
      const agrab = () => { const S_ = typeof Alerts !== "undefined" && Alerts._state, cv_ = document.getElementById("al-canvas"); if (!S_ || !cv_ || !cv_.width) return;
        const sel = (S_.selectedTypes && S_.selectedTypes.size) ? [...S_.selectedTypes].sort().join(',') : 'ALL'; const sig = [S_.loaded, sel, S_.k, S_.cx, S_.cy, cv_.width, (S_.alerts || []).length, S_.sig || ""].join("|");
        if (sig !== asig || MG.img !== cv_) { asig = sig; MG.img = S_.loaded ? cv_ : null; MG.msg = S_.loaded ? "" : "Loading alerts\u2026"; if (!REC.on && !PV.on) renderAll(); } };
      window.__alertLoad.then(() => { if (ALERTM()) { Alerts.show(); fitFrames(); } }, () => { window.__alertLoad = null; MG.msg = "Alerts could not load."; renderAll(); });
      poll = setInterval(agrab, 400); renderAll(); fitFrames(); return;
    }
    document.body.classList.remove("alertmode"); if (wasAlert && typeof Alerts !== "undefined") Alerts.hide();
    const on = mode === "mg" || mode === "obs", wasObs = OBSM(); if (on && MG.kind !== mode) { MG.img = null; MG.src = ""; MG.msg = ""; }
    MG.on = on; if (on) MG.kind = mode; saveMode(on ? mode : "map"); clearInterval(poll);
    document.body.classList.toggle("mgmode", on && mode === "mg"); document.body.classList.toggle("obsmode", on && mode === "obs");
    if (wasObs && !OBSM() && typeof Obs !== "undefined") { Obs.hide(); PIN.show = false; PIN.mode = null; }
    if (on && mode === "obs") {
      if (!ob_) { ob_ = document.createElement("div"); ob_.id = "obsp"; ob_.innerHTML = `<div id="obs-root"></div>`; pnl.appendChild(ob_); }
      obsLoad = obsLoad || new Promise((ok, bad) => {
        const l = document.createElement("link"); l.rel = "stylesheet"; l.href = "obs/obs.css"; document.head.appendChild(l);
        const sc = document.createElement("script"); sc.src = "obs/obs.js?v=20261110full1"; sc.onerror = bad; document.body.appendChild(sc);
        // 11-03: radar + GOES-West layers (obs/obsimg.js, off by default); the obs map still opens if it fails to load
        sc.onload = () => { const s2 = document.createElement("script"); s2.src = "obs/obsimg.js?v=20261110satpair1"; s2.onload = ok; s2.onerror = ok; document.body.appendChild(s2); }; });
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
    MG.kind = "mg"; sel.value = "mg"; setMode("mg"); backSync(); window.__pfOpened = { name, hash: h, run: PF.run }; };
  // Same chart studioPassChart draws for this pass and this run. pfOpen replaces __pfOpened, so the chart is attached after it.
  window.__pfChart = async (name) => {
    const run = (document.getElementById("pfrun") && document.getElementById("pfrun").value) || PF.run;
    if (run) PF.run = run;
    const chart = await window.studioPassChart(run, name, 1800, 960);
    pfOpen(name);
    window.__pfOpened = Object.assign({}, window.__pfOpened, { name, run, chart });
    return chart;
  };
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
for (const k of ["v", "h"]) if (F[k].cv) {
  F[k].cv.addEventListener("contextlost", (e) => { e.preventDefault(); });
  F[k].cv.addEventListener("contextrestored", () => {
    const cv = F[k].cv; if (cv._restoring) return; cv._restoring = 1;
    requestAnimationFrame(() => { cv._restoring = 0; try { render(k); } catch (err) { /* redraw on restore */ } });
  });
}
window.__studioInk = () => { const px = window.__studioFramePx || {}; return { v: px.v || 0, h: px.h || 0 }; };
window.__studioSharp = { PSS, ssFit, ovPut, sharpShadow, colorbar, ctxS, F, paintStudioTowns, frameTx, frameInk };
window.__studioQA = () => ({ mode: PASSM() ? "pass" : MG.on ? MG.kind : "map", web: WEBM() ? WEB.url : "", cmp: CMPM() ? { l: CMP.L && CMP.L.run, r: CMP.R && CMP.R.run, title: cmpHeadTitle() } : null, mg: MG.kind === "mg" ? (MG.src.split("#")[1] || "") : "", alert: ALERTM() ? ((typeof Alerts !== "undefined" && Alerts.titleText && Alerts.titleText()) || "All Alerts") : "", pass: PF.run, passRows: PF.rows ? PF.rows.length : 0,
  pfL: F.h.pfL ? { x: F.h.pfL.x, y0: F.h.pfL.y0, w: F.h.pfL.w, rh: F.h.pfL.rh, names: F.h.pfL.names } : null, W: F.h.W, fr: { v: getFr("v"), h: getFr("h") }, px: window.__studioInk() });
})();
