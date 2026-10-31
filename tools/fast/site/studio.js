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
  if (PIN.show && !REC.on) drawPins(k, c, r);
  window.__studio = (window.__studio || 0) + 1;
}
const renderAll = () => { if (REC.on) return; if (CLEAN) render(OUTQ); else { render("v"); render("h"); } };
window.onStudioSkip = () => { if (PLAY.on) PLAY.next(); };
window.onStudioDraw = (cv, cur, step) => { last = { cv, cur, step }; renderAll(); if (PLAY.on) PLAY.next(); };
// drag / keys / zoom / buttons
for (const k of ["v", "h"]) {
  const f = F[k], cv = f.cv; let d = null;
  cv.addEventListener("pointerdown", (e) => { if (CLEAN || !last || REC.on) return; if (PIN.mode) { placePin(k, cv, e); return; } cv.setPointerCapture(e.pointerId); cv.focus(); cv.classList.add("drag"); d = { x: e.clientX, y: e.clientY, fr: getFr(k) }; });
  cv.addEventListener("pointermove", (e) => { if (!d) return; const s = f.W / cv.clientWidth, fr = getFr(k);
    fr.dx = d.fr.dx + (e.clientX - d.x) * s; fr.dy = d.fr.dy + (e.clientY - d.y) * s; const r = crop(k, fr);   // keep the stored offset inside the panel
    fr.dx = (r.px + r.pw / 2 - r.cx) * r.kk; fr.dy = (r.py + r.ph / 2 - r.cy) * r.kk; setFr(k, fr); render(k); });
  const up = () => { d = null; cv.classList.remove("drag"); }; cv.addEventListener("pointerup", up); cv.addEventListener("pointercancel", up);
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
  PIN.mode = null; $s("pinhint").hidden = true; $s("mp4p").hidden = false; mpInfo(); render("v"); render("h");
}
const lbl = (st) => { const d = new Date(st.valid); return `F+${st.f} \u00b7 ${d.toUTCString().slice(0, 3)} ${String(d.getUTCMonth() + 1).padStart(2, "0")}-${String(d.getUTCDate()).padStart(2, "0")} ${String(d.getUTCHours()).padStart(2, "0")}Z`; };
function openMp4(k) {
  if (!last) return; const st = S.runs[S.run].steps, a = $s("mpa"), b = $s("mpb");
  const opts = st.map((x, i) => `<option value="${i}">${lbl(x)}</option>`).join(""); a.innerHTML = opts; b.innerHTML = opts;
  const e5 = st.findIndex((x) => x.f >= st[S.i].f + 120);   // default: the next 5 days (or to the end of the run)
  a.value = String(S.i); b.value = String(e5 > S.i ? e5 : st.length - 1);
  $s("mpk").value = k; $s("mp4p").hidden = false; $s("mpout").hidden = true; mpMode(); mpInfo();
}
function pickIdx() {
  const st = S.runs[S.run].steps, a = +$s("mpa").value, b = +$s("mpb").value, e = +$s("mpe").value, out = [];
  for (let i = a; i <= b; i++) if (!out.length || !e || st[i].f - st[out[out.length - 1]].f >= e) out.push(i);
  return out;
}
function mpInfo() {
  const idx = pickIdx(), sp = +$s("mps").value, hold = +$s("mph").value, p = getPins(), pan = $s("mpmode").value === "pan";
  $s("mppins").textContent = pan ? (p.a ? "A set" : "A not set") + " \u00b7 " + (p.b ? "B set" : "B not set") : "";
  $s("mpinfo").textContent = idx.length < 2 ? "Pick an end hour after the start hour." :
    `${idx.length} maps, F+${S.runs[S.run].steps[idx[0]].f} to F+${S.runs[S.run].steps[idx[idx.length - 1]].f} \u00b7 about ${(idx.length / sp + hold).toFixed(1)} s of video at 30 fps`;
}
function mpMode() { const pan = $s("mpmode").value === "pan"; $s("mppan").hidden = !pan; PIN.show = pan; render("v"); render("h"); mpInfo(); }
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
  if (pan && !(pins.a && pins.b)) { mpSt("Set pin A and pin B on the map first."); return; }
  const per = FPS / +$s("mps").value, holdN = Math.round(+$s("mph").value * FPS), zoom = +$s("mpz").value, panN = Math.max(1, Math.round(idx.length * per) - 1);
  const run = S.run, keep = S.i, t0 = performance.now(); let enc = null;
  REC.on = true; REC.cancel = false; PLAY.on = false; $s("mpout").hidden = true; $s("mpgo").disabled = true; $s("mpstop").hidden = false; document.body.classList.add("rec");
  try {
    enc = await makeEncoder(f.cv, f.W, f.H);
    S.i = idx[0]; $("step").value = idx[0]; await draw(); await sleep(500); await draw();   // let this view's sharp (x2) layers land first
    let n = 0;
    for (let j = 0; j < idx.length; j++) {
      if (REC.cancel || S.run !== run) throw new Error("stopped");
      if (j) { if (enc.idle) enc.idle(); S.i = idx[j]; $("step").value = idx[j]; await draw(); }   // an hour missing from the run keeps the previous map
      mpSt(`Making video\u2026 F+${steps[idx[j]].f} (${j + 1}/${idx.length})`);
      const n1 = Math.round((j + 1) * per) + (j === idx.length - 1 ? holdN : 0); let drawn = false;
      for (; n < n1; n++) {
        if (pan) { const t = ease(Math.min(1, n / panN)); await render(k, frAt(k, lerp(pins.a.x, pins.b.x, t), lerp(pins.a.y, pins.b.y, t), zoom)); }
        else if (!drawn || enc.realtime) { await render(k); drawn = true; }   // real-time recorder: redraw so each frame is a fresh canvas frame
        await enc.add(n);
      }
    }
    mpSt("Finishing\u2026"); const how = enc.how, blob = await enc.done(); enc = null;
    const nm = `${run.replace("/", "_")}_${last.cur.pid}_${S.view}_F${steps[idx[0]].f}-F${steps[idx[idx.length - 1]].f}_${k === "v" ? "1080x1920" : "1920x1080"}${pan ? "_track" : ""}.${blob.type.includes("mp4") ? "mp4" : "webm"}`;
    const u = URL.createObjectURL(blob), v = $s("mpv"), dl = $s("mpdl"); if (v.dataset.u) URL.revokeObjectURL(v.dataset.u); v.dataset.u = u; v.src = u; dl.href = u; dl.download = nm;
    const file = new File([blob], nm, { type: blob.type }); $s("mpshare").hidden = !(navigator.canShare && navigator.canShare({ files: [file] })); $s("mpshare").onclick = () => navigator.share({ files: [file] }).catch(() => {});
    $s("mpout").hidden = false; window.__mp4 = { name: nm, bytes: blob.size, frames: n, seconds: n / FPS, how, ms: Math.round(performance.now() - t0) };
    mpSt(`Done: ${(blob.size / 1e6).toFixed(1)} MB, ${(n / FPS).toFixed(1)} s, made in ${((performance.now() - t0) / 1000).toFixed(0)} s`);
  } catch (e) { if (enc) enc.abort(); mpSt(e.message === "stopped" ? "Stopped." : "Could not make the video: " + (e.message || e)); window.__mp4 = { error: String(e.message || e) }; }
  finally { REC.on = false; $s("mpgo").disabled = false; $s("mpstop").hidden = true; document.body.classList.remove("rec"); if (S.run === run) { S.i = keep; $("step").value = keep; } draw(); }
}
if (!CLEAN && $s("mp4p")) {
  $s("mp4p").addEventListener("click", (e) => { const b = e.target.closest("button[data-m]"); if (!b) return; const m_ = b.dataset.m;
    if (m_ === "x") { if (!REC.on) { $s("mp4p").hidden = true; PIN.show = false; render("v"); render("h"); } }
    else if (m_ === "a" || m_ === "b") { PIN.mode = m_; PIN.show = true; $s("mp4p").hidden = true; const h = $s("pinhint"); h.hidden = false;
      h.textContent = `Tap either frame where the loop should ${m_ === "a" ? "START (pin A)" : "END (pin B)"}. Drag the frame first if you need to. Esc cancels.`; render("v"); render("h"); }
    else if (m_ === "c") { setPins({}); mpInfo(); render("v"); render("h"); }
    else if (m_ === "go") makeMp4(); else if (m_ === "stop") REC.cancel = true; });
  for (const id of ["mpa", "mpb", "mpe", "mps", "mph", "mpz"]) $s(id).addEventListener("change", mpInfo);
  $s("mpmode").addEventListener("change", mpMode);
  addEventListener("keydown", (e) => { if (e.key === "Escape" && PIN.mode) { PIN.mode = null; $s("pinhint").hidden = true; $s("mp4p").hidden = false; } });
  window.__studioMp4 = { getPins, setPins, makeMp4, openMp4 };
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
