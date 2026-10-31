// Studio tab (10-31, Benjamin 10:35 AM: "Vertical model viewing canvas, next to a 1920x1080 model viewing canvas ... drag the map
// ever so slightly to make it line up right ... for reels and making videos on obs"). viewer.js draws the normal map off-screen at
// 2-3x (?studio=1); after every full draw this crops the map panel into two fixed frames (9:16 1080x1920, 16:9 1920x1080) and
// draws its own header (title, valid time, run, model tag, F+ badge) and color bar at full output size.
// Clean mode for OBS Browser Source: studio.html?clean=1&out=v|h&model=<m>&prod=&view=&f=&dx=&dy=&zoom=&bg=&play=1&dwell=&step=&loop=
"use strict";
(() => {
const SQ = new URLSearchParams(location.search), CLEAN = SQ.get("clean") === "1", OUTQ = SQ.get("out") || "v";
const F = {
  v: { cv: document.getElementById("cv"), zoom: document.getElementById("zv"), W: 1080, H: 1920, top: 250, bot: 330, title: 64, valid: 40, run: 26, pad: 64 },
  h: { cv: document.getElementById("ch"), zoom: document.getElementById("zh"), W: 1920, H: 1080, top: 150, bot: 150, title: 58, valid: 36, run: 24, pad: 56 },
};
const BG = SQ.get("bg") || "#111316";
if (CLEAN) {
  document.body.classList.add("clean"); document.getElementById(OUTQ === "h" ? "fh" : "fv").classList.add("on");
  document.body.style.setProperty("--sbg", BG === "transparent" ? "transparent" : BG); if (BG === "transparent") document.documentElement.style.background = "transparent";
}
// framing per frame x view: {dx, dy, zoom} in output px; URL params win in clean mode
const key = (k) => `studio:${k}:${S.view}`;
const getFr = (k) => {
  if (CLEAN && k === OUTQ && (SQ.has("dx") || SQ.has("dy") || SQ.has("zoom"))) return { dx: +SQ.get("dx") || 0, dy: +SQ.get("dy") || 0, zoom: +SQ.get("zoom") || 1 };
  try { return Object.assign({ dx: 0, dy: 0, zoom: 1 }, JSON.parse(localStorage.getItem(key(k)) || "{}")); } catch (e) { return { dx: 0, dy: 0, zoom: 1 }; }
};
const setFr = (k, fr) => { if (!CLEAN) localStorage.setItem(key(k), JSON.stringify(fr)); };
let last = null;   // {cv, cur, step}
const fmtTick = (v, P) => { const a = P.ticks || []; const dec = a.some((t) => Math.abs(t - Math.round(t)) > 1e-6) ? (a.some((t) => Math.abs(t * 10 - Math.round(t * 10)) > 1e-6) ? 2 : 1) : 0; return Number(v).toFixed(dec); };

function crop(k, fr) {   // source rect (map bitmap px) for frame k: "cover" the frame with the map panel, then zoom / pan, kept inside the panel
  const f = F[k], { cv, cur } = last, rs = cv._rs || 1, [px, py, pw, ph] = cur.V.panel;
  const kk = Math.max(f.W / pw, f.H / ph) * Math.max(1, fr.zoom || 1), sw = f.W / kk, sh = f.H / kk;
  let cx = px + pw / 2 - (fr.dx || 0) / kk, cy = py + ph / 2 - (fr.dy || 0) / kk;
  cx = Math.min(px + pw - sw / 2, Math.max(px + sw / 2, cx)); cy = Math.min(py + ph - sh / 2, Math.max(py + sh / 2, cy));
  return { sx: (cx - sw / 2) * rs, sy: (cy - sh / 2) * rs, sw: sw * rs, sh: sh * rs, kk, cx, cy, px, py, pw, ph };
}
function band(c, y0, y1, down) {
  const g = c.createLinearGradient(0, y0, 0, y1); const a = "rgba(13,15,19,0.90)", b = "rgba(13,15,19,0)";
  g.addColorStop(0, down ? a : b); g.addColorStop(1, down ? b : a); c.fillStyle = g; c.fillRect(0, y0, c.canvas.width, y1 - y0);
}
function pill(c, x, y, txt, size, bg, fg) {
  c.font = `800 ${size}px Montserrat`; const w = c.measureText(txt).width + size * 0.9, h = size * 1.55;
  c.fillStyle = bg; c.beginPath(); c.roundRect ? c.roundRect(x, y, w, h, h / 2) : c.rect(x, y, w, h); c.fill();
  c.fillStyle = fg; c.textBaseline = "middle"; c.fillText(txt, x + size * 0.45, y + h / 2 + 1); c.textBaseline = "alphabetic"; return w;
}
function colorbar(c, P, x, y, w, h, size) {
  const L = P.levels, C = P.colors; if (!L || !C || L.length < 2) return false;
  const lo = L[0], hi = L[L.length - 1], n = L.length - 1;   // equal-width bins (like the site's keys), ticks placed inside their bin
  const X = (v) => { let i = 0; while (i < n - 1 && v > L[i + 1]) i++; return x + (i + Math.min(1, Math.max(0, (v - L[i]) / ((L[i + 1] - L[i]) || 1)))) / n * w; };
  for (let i = 0; i < C.length && i < L.length - 1; i++) { c.fillStyle = C[i]; c.fillRect(Math.floor(X(L[i])), y, Math.ceil(X(L[i + 1]) - X(L[i])) + 1, h); }
  c.strokeStyle = "rgba(255,255,255,0.55)"; c.lineWidth = 1.5; c.strokeRect(x, y, w, h);
  c.font = `600 ${size}px Montserrat`; c.fillStyle = "#e9ecf1"; c.textAlign = "center";
  // ticks: skip any whose label would touch the previous drawn one (precip keys bunch 0.01-0.5 into a few bins)
  let lastR = -1e9; (P.ticks || []).filter((t) => t >= lo && t <= hi).forEach((t) => { const tx = X(t), s_ = fmtTick(t, P), tw = c.measureText(s_).width;
    if (tx - tw / 2 < lastR + size * 0.6) return; lastR = tx + tw / 2; c.fillRect(tx - 1, y + h, 2, size * 0.35); c.fillText(s_, tx, y + h + size * 1.35); });
  c.textAlign = "left"; c.font = `700 ${size}px Montserrat`; c.fillText(P.key || "", x, y - size * 0.55);
  return true;
}
// ---- branding (10-31 3:49 PM, Benjamin: "Yes to 3"): a title card at the start of a video and a lower third on every frame
// (logo, title / storm name, model + run, forecast date). Toggles in the Save MP4 panel (remembered); links: &brand=1 (both on),
// &title=, &storm=, &brandlogo=wa|usa|wawc|usawc|none, &card=0|1, &lower=0|1.
const LOGOS = { wa: "brand/wawx.png", usa: "brand/usawx.png", wawc: "brand/wawc.png", usawc: "brand/usawc.png" };
const BR = Object.assign({ card: false, lower: false, logo: "wa", title: "", storm: "" }, (() => { try { return JSON.parse(localStorage.getItem("studio:brand") || "{}"); } catch (e) { return {}; } })());
if (SQ.get("brand") === "1") { BR.card = true; BR.lower = true; }
for (const [q, k_] of [["card", "card"], ["lower", "lower"]]) if (SQ.has(q)) BR[k_] = SQ.get(q) === "1";
if (SQ.has("title")) BR.title = SQ.get("title"); if (SQ.has("storm")) BR.storm = SQ.get("storm"); if (SQ.has("brandlogo")) BR.logo = SQ.get("brandlogo");
const saveBR = () => { if (!SQ.get("make") && !CLEAN) try { localStorage.setItem("studio:brand", JSON.stringify(BR)); } catch (e) { /* private */ } };
const logoImg = {};
function getLogo() { const u = LOGOS[BR.logo]; if (!u) return null; if (!logoImg[u]) { const im = new Image(); im.src = u; logoImg[u] = im; im.onload = () => renderAll(); } const im = logoImg[u]; return im.complete && im.naturalWidth ? im : null; }
const ptTime = (iso, o) => { try { return new Date(iso).toLocaleString("en-US", Object.assign({ timeZone: "America/Los_Angeles" }, o)); } catch (e) { return iso; } };
function runText() { const [m, c] = last.cur.run.split("/"), site = (S.man.models[m] || {}).site || m; return `${site} ${c.slice(8)}Z ${c.slice(4, 6)}-${c.slice(6, 8)} run`; }
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
  const words = (BR.title || BR.storm || last.cur.P.title).split(" "), maxW = f.W - 2 * f.pad, lines = []; let line = "";
  for (const w_ of words) { const t = line ? line + " " + w_ : w_; if (c.measureText(t).width > maxW && line) { lines.push(line); line = w_; } else line = t; } lines.push(line);
  lines.slice(0, 3).forEach((t, i) => c.fillText(t, cx, y + i * (k === "v" ? 86 : 88))); y += (Math.min(3, lines.length) - 1) * (k === "v" ? 86 : 88) + (k === "v" ? 80 : 74);
  if (BR.storm && BR.title) { c.font = `800 ${k === "v" ? 48 : 46}px Montserrat`; c.fillStyle = "#ffc24d"; c.fillText(BR.storm, cx, y); y += k === "v" ? 70 : 64; }
  c.font = `600 ${k === "v" ? 38 : 36}px Montserrat`; c.fillStyle = "#cfd3da";
  c.fillText(`${runText()} \u00b7 ${last.cur.P.title}`, cx, y); y += k === "v" ? 58 : 54;
  if (a0 && a1) c.fillText(`${ptTime(a0.valid, { weekday: "short", month: "short", day: "numeric", hour: "numeric" })} \u2013 ${ptTime(a1.valid, { weekday: "short", month: "short", day: "numeric", hour: "numeric" })} PT`, cx, y);
  c.restore();
}
window.__studioBrand = { BR, titleCard: (k, a) => titleCard(k, F[k].cv.getContext("2d"), a == null ? 1 : a, null, null) };
async function render(k, frO) {   // frO: camera override (MP4 storm-track pan)
  if (!last) return; const f = F[k], c = f.cv.getContext("2d"), fr = frO || getFr(k), { cv, cur, step } = last, P = cur.P, [m] = cur.run.split("/");
  if (!frO) f.zoom.value = Math.round((fr.zoom || 1) * 100);
  c.setTransform(1, 0, 0, 1, 0, 0); c.clearRect(0, 0, f.W, f.H);
  if (BG !== "transparent") { c.fillStyle = BG; c.fillRect(0, 0, f.W, f.H); }
  const r = crop(k, fr); c.imageSmoothingEnabled = true; c.imageSmoothingQuality = "high";
  c.drawImage(cv, r.sx, r.sy, r.sw, r.sh, 0, 0, f.W, f.H);
  // header
  band(c, 0, f.top + f.title * 1.6, true);
  const site = (S.man.models[m] || {}).site || m, R_ = S.runs[cur.run], x = f.pad; let y = k === "v" ? 120 : 34;
  const pw = pill(c, x, y, site.toUpperCase(), Math.round(f.run * 0.95), "#2f8cff", "#fff");
  c.font = `600 ${f.run}px Montserrat`; c.fillStyle = "#b9c0cc"; c.fillText(`${cur.run.split("/")[1].slice(8)}Z run`, x + pw + 14, y + f.run * 1.08);
  y += f.run * 1.55 + f.title * 1.02;
  c.font = `800 ${f.title}px Montserrat`; c.fillStyle = "#fff"; c.shadowColor = "rgba(0,0,0,0.6)"; c.shadowBlur = 8;
  const words = P.title.split(" "), maxW = f.W - 2 * f.pad - (k === "h" ? 260 : 0); let line = "", lines = [];
  for (const w_ of words) { const t = line ? line + " " + w_ : w_; if (c.measureText(t).width > maxW && line) { lines.push(line); line = w_; } else line = t; } lines.push(line);
  lines.forEach((t, i) => c.fillText(t, x, y + i * f.title * 1.08)); y += (lines.length - 1) * f.title * 1.08 + f.valid * 1.4;
  c.font = `700 ${f.valid}px Montserrat`; c.fillStyle = "#ffc24d"; c.fillText((step.valid_line || "").replace(/^Valid /, ""), x, y);
  c.shadowBlur = 0;
  // F+ badge (top right)
  c.font = `800 ${Math.round(f.valid * 1.1)}px Montserrat`; const bt = `F+${step.f}`, bw = c.measureText(bt).width + 40, bx = f.W - f.pad - bw, by = k === "v" ? 120 : 34;
  c.fillStyle = "rgba(17,19,22,0.85)"; c.strokeStyle = "rgba(255,255,255,0.35)"; c.lineWidth = 2; c.beginPath(); c.roundRect ? c.roundRect(bx, by, bw, f.valid * 1.9, 14) : c.rect(bx, by, bw, f.valid * 1.9); c.fill(); c.stroke();
  c.fillStyle = "#fff"; c.textAlign = "center"; c.fillText(bt, bx + bw / 2, by + f.valid * 1.32); c.textAlign = "left";
  // bottom: color bar + credit
  band(c, f.H - f.bot - 40, f.H, false);
  const cbW = k === "v" ? f.W - 2 * f.pad : Math.min(1100, f.W * 0.58), cbY = f.H - f.bot + (k === "v" ? 110 : 62), cbS = k === "v" ? 28 : 24;
  if (!colorbar(c, P, f.pad, cbY, cbW, k === "v" ? 34 : 26, cbS)) {
    try { const im = await getKey(cur.pid, cur.V === VIEWS()[S.view] ? S.view : S.view); const s_ = cbW / im.naturalWidth; c.drawImage(im, f.pad, cbY - 30, cbW, im.naturalHeight * s_); } catch (e) { /* no key */ }
  }
  c.font = `500 ${k === "v" ? 22 : 18}px Montserrat`; c.fillStyle = "rgba(220,224,230,0.85)";
  const credit = `${(R_.runline || "").split(" run ")[0]}  \u00b7  ${cur.V.label}`, logo = SQ.get("logo") || "";
  // 9:16: credit under the bar, logo right; 16:9: bar fills the left 58 %, so credit (and logo above it) sit bottom-right
  if (k === "v") c.fillText(credit, f.pad, f.H - 70); else { c.textAlign = "right"; c.fillText(credit, f.W - f.pad, f.H - 24); c.textAlign = "left"; }
  if (logo) { c.font = `800 ${k === "v" ? 34 : 28}px Montserrat`; c.fillStyle = "#fff"; c.textAlign = "right"; c.fillText(logo, f.W - f.pad, f.H - (k === "v" ? 70 : 60)); c.textAlign = "left"; }
  if (BR.lower) lowerThird(k, c);
  if (PIN.show && !REC.on) drawPins(k, c, r);
  window.__studio = (window.__studio || 0) + 1;
}
const renderAll = () => { if (REC.on) return; if (CLEAN) render(OUTQ); else { render("v"); render("h"); } };
window.onStudioSkip = () => { if (PLAY.on) PLAY.next(); };
window.onStudioDraw = (cv, cur, step) => { last = { cv, cur, step }; renderAll(); if (PLAY.on) PLAY.next(); if (!REC.on && typeof mpSync === "function") try { mpSync(); } catch (e) { /* panel not ready */ } };
// drag / keys / zoom / buttons
for (const k of ["v", "h"]) {
  const f = F[k], cv = f.cv; let d = null;
  cv.addEventListener("pointerdown", (e) => { if (CLEAN || !last || REC.on) return; if (PIN.mode) { placePin(k, cv, e); return; } cv.setPointerCapture(e.pointerId); cv.focus(); cv.classList.add("drag"); d = { x: e.clientX, y: e.clientY, fr: getFr(k) }; });
  cv.addEventListener("pointermove", (e) => { if (!d || pz) return; const s = f.W / cv.clientWidth, fr = getFr(k);
    fr.dx = d.fr.dx + (e.clientX - d.x) * s; fr.dy = d.fr.dy + (e.clientY - d.y) * s; const r = crop(k, fr);   // keep the stored offset inside the panel
    fr.dx = (r.px + r.pw / 2 - r.cx) * r.kk; fr.dy = (r.py + r.ph / 2 - r.cy) * r.kk; setFr(k, fr); render(k); });
  const up = () => { d = null; cv.classList.remove("drag"); }; cv.addEventListener("pointerup", up); cv.addEventListener("pointercancel", up);
  // 10-31 1:39 PM (Benjamin, iPhone): two-finger pinch zooms the frame (1-2.5x) about the fingers' midpoint; moving both fingers pans
  let pz = null;
  const oxy = (t) => { const b = cv.getBoundingClientRect(); return [(t.clientX - b.left) * f.W / b.width, (t.clientY - b.top) * f.H / b.height]; };
  cv.addEventListener("touchstart", (e) => {
    if (CLEAN || !last || REC.on || PIN.mode || e.touches.length !== 2) return; e.preventDefault(); d = null;
    const [a, b] = [oxy(e.touches[0]), oxy(e.touches[1])], fr0 = getFr(k), r0 = crop(k, fr0), ox = (a[0] + b[0]) / 2, oy = (a[1] + b[1]) / 2;
    pz = { d: Math.max(10, Math.hypot(a[0] - b[0], a[1] - b[1])), z: Math.max(1, fr0.zoom || 1), mx: r0.cx + (ox - f.W / 2) / r0.kk, my: r0.cy + (oy - f.H / 2) / r0.kk };
  }, { passive: false });
  cv.addEventListener("touchmove", (e) => {
    if (!pz) return; e.preventDefault(); if (e.touches.length < 2) return;
    const [a, b] = [oxy(e.touches[0]), oxy(e.touches[1])], ox = (a[0] + b[0]) / 2, oy = (a[1] + b[1]) / 2;
    const z = Math.min(2.5, Math.max(1, pz.z * Math.max(10, Math.hypot(a[0] - b[0], a[1] - b[1])) / pz.d)), [px, py, pw, ph] = last.cur.V.panel, kk = Math.max(f.W / pw, f.H / ph) * z;
    const fr = frAt(k, pz.mx - (ox - f.W / 2) / kk, pz.my - (oy - f.H / 2) / kk, z), r = crop(k, fr);   // map point under the fingers stays under them
    fr.dx = (r.px + r.pw / 2 - r.cx) * r.kk; fr.dy = (r.py + r.ph / 2 - r.cy) * r.kk; setFr(k, fr); render(k); window.__spinch = { k, zoom: z };
  }, { passive: false });
  const pend = (e) => { if (pz && e.touches.length < 2) pz = null; };
  cv.addEventListener("touchend", pend); cv.addEventListener("touchcancel", pend);
  cv.addEventListener("keydown", (e) => {
    const fr = getFr(k), st = e.shiftKey ? 10 : 1; let hit = true;
    if (e.key === "ArrowLeft") fr.dx -= st; else if (e.key === "ArrowRight") fr.dx += st; else if (e.key === "ArrowUp") fr.dy -= st; else if (e.key === "ArrowDown") fr.dy += st;
    else if (e.key === "+" || e.key === "=") fr.zoom = Math.min(2.5, (fr.zoom || 1) + 0.01); else if (e.key === "-") fr.zoom = Math.max(1, (fr.zoom || 1) - 0.01);
    else if (e.key === "0") { fr.dx = fr.dy = 0; fr.zoom = 1; } else hit = false;
    if (hit) { e.preventDefault(); e.stopPropagation(); setFr(k, fr); render(k); }
  }, true);
  f.zoom.oninput = () => { const fr = getFr(k); fr.zoom = f.zoom.value / 100; setFr(k, fr); render(k); };
  cv.parentNode.querySelector(".shd").addEventListener("click", async (e) => {
    const a = e.target.closest("button[data-a]"); if (!a || !last) return;
    if (a.dataset.a === "reset") { setFr(k, { dx: 0, dy: 0, zoom: 1 }); render(k); }
    if (a.dataset.a === "mp4") openMp4(k);
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
const pinKey = () => `studio:pins:${S.view}`;
const getPins = () => { try { return JSON.parse(localStorage.getItem(pinKey()) || "{}"); } catch (e) { return {}; } };
const setPins = (p) => { try { localStorage.setItem(pinKey(), JSON.stringify(p)); } catch (e) { /* private mode */ } };
function frAt(k, x, y, zoom) {   // camera centred on map point (x, y) at this zoom, as a {dx, dy, zoom} framing
  const f = F[k], [px, py, pw, ph] = last.cur.V.panel, kk = Math.max(f.W / pw, f.H / ph) * zoom;
  return { dx: (px + pw / 2 - x) * kk, dy: (py + ph / 2 - y) * kk, zoom };
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
    c.fillStyle = col; c.strokeStyle = "#fff"; c.lineWidth = 5; c.beginPath(); c.arc(x, y, R, 0, 7); c.fill(); c.stroke();
    c.fillStyle = "#fff"; c.font = `800 ${R}px Montserrat`; c.textAlign = "center"; c.textBaseline = "middle"; c.fillText(n.toUpperCase(), x, y + 2);
    c.textAlign = "left"; c.textBaseline = "alphabetic";
  }
}
function placePin(k, cv, e) {
  const f = F[k], b = cv.getBoundingClientRect(), ox = (e.clientX - b.left) * f.W / b.width, oy = (e.clientY - b.top) * f.H / b.height, r = crop(k, getFr(k));
  const p = getPins(); p[PIN.mode] = { x: r.cx + (ox - f.W / 2) / r.kk, y: r.cy + (oy - f.H / 2) / r.kk }; setPins(p);
  // pin A placed and no pin B yet: go straight on to pin B (one less tap); Esc stops
  if (PIN.mode === "a" && !p.b) { PIN.mode = "b"; $s("pinhint").textContent = "Pin A set. Now tap where the loop should END (pin B). Esc cancels."; render("v"); render("h"); return; }
  PIN.mode = null; $s("pinhint").hidden = true; $s("mp4p").hidden = false; mpInfo(); render("v"); render("h");
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
  if (!last || REC.on) return;
  const k = $s("mpk").value, f = F[k], pan = $s("mpmode").value === "pan", pins = getPins(), idx = pickIdx(), steps = S.runs[S.run].steps;
  if (idx.length < 2) { mpSt("Pick an end hour after the start hour."); return; }
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
    n += cardN; $s("mpout").hidden = false; window.__mp4 = { name: nm, bytes: blob.size, frames: n, seconds: n / FPS, branded: !!(BR.card || BR.lower), how, ms: Math.round(performance.now() - t0), blob };
    mpSt(`Done: ${(blob.size / 1e6).toFixed(1)} MB, ${(n / FPS).toFixed(1)} s, made in ${((performance.now() - t0) / 1000).toFixed(0)} s`);
  } catch (e) { if (enc) enc.abort(); mpSt(e.message === "stopped" ? "Stopped." : "Could not make the video: " + (e.message || e)); window.__mp4 = { error: String(e.message || e) }; }
  finally { REC.on = false; window.__vjNoJump = false; $s("mpgo").disabled = false; $s("mpstop").hidden = true; $s("mpprog").hidden = true; document.body.classList.remove("rec"); if (S.run === run) { S.i = keep; $("step").value = keep; } draw(); }
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
function brSync() { if (!$s("brcard")) return; $s("brcard").checked = BR.card; $s("brlower").checked = BR.lower; $s("brlogo").value = LOGOS[BR.logo] ? BR.logo : "none"; $s("brtitle").value = BR.title || ""; $s("brstorm").value = BR.storm || ""; }
// ---- batch export (10-31 3:49 PM, Benjamin: "Yes to 2"): tick models / products / views / frame shapes, one button makes every
// MP4 with the panel's settings (hours by forecast hour, speed, zoom, mode / pins of each view, preset; "Auto storm track" finds
// the storm per map) and packs them in one .zip (stored, MP4s don't compress). Result: window.__batchResult.
const BX = { on: false, cancel: false };
const MORDER = ["hrrr", "rrfs", "nbm", "gfs", "ifs", "ifs9", "aifs", "eps", "aens"];
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
      files.push({ name: r.name, blob: r.blob }); res.items.push({ name: r.name, bytes: r.bytes, seconds: r.seconds });
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
  for (const id of ["mpa", "mpb", "mpe", "mps", "mps1", "mph", "mpz0", "mpz1"]) $s(id).addEventListener("change", mpInfo);
  for (const id of OPT_IDS) $s(id).addEventListener("change", (e) => { saveOpts(); if (e.isTrusted) $s("mppre").value = ""; });
  $s("mppre").addEventListener("change", (e) => { if (e.target.value === "storm") findStorms(); else applyPreset(e.target.value); });
  $s("mpsfl").addEventListener("change", (e) => applyStorm(+e.target.value));
  brSync();
  for (const id of ["brcard", "brlower"]) $s(id).addEventListener("change", (e) => { BR[id === "brcard" ? "card" : "lower"] = e.target.checked; saveBR(); renderAll(); });
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
  window.__studioMp4 = { getPins, setPins, makeMp4, openMp4, findStorms, applyStorm, llToFig, TRK, BR, batchExport, bxFill };
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
})();
