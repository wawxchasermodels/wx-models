// Social tab MP4 loops (10-31-26, Benjamin 1:55 PM: "I also want these loop options for the social media files we made").
// Same options as Studio's Save MP4: start / end hour (+ "= now"), speed slider with live length and optional end speed, hold,
// start / end zoom, storm pan between pins A and B, 9:16 or 16:9, saved as MP4 in the browser (WebCodecs H.264 + vendor/mp4-muxer,
// MediaRecorder fallback). Source = the 4K social PNGs (2160x3840 / 3840x2160) drawn into a 1080x1920 / 1920x1080 frame.
// The social frames are finished graphics (title, date, color bar baked in), so when zoomed the title band and the color-bar band
// are redrawn unzoomed on top with a soft edge: the map zooms, the text stays put. Frames are every 24 h for now, so "Crossfade"
// blends one map into the next.
"use strict";
(() => {
const FPS = 30, OUT = { v: [1080, 1920], h: [1920, 1080] };
// text bands of make_social.py (fraction of height): solid to a, fading out by b
const BAND = { v: { top: [0.25, 0.272], bot: [0.80, 0.775] }, h: { top: [0.265, 0.292], bot: [0.85, 0.822] } };
const $s = (id) => document.getElementById(id), sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const lerp = (a, b, t) => a + (b - a) * t, ease = (t) => t * t * (3 - 2 * t);
const P = { on: false, cancel: false, pinMode: null };
const hours = () => [...$s("hour").options].map((o) => +o.value);
const cur = () => ({ run: S.run, prod: S.prod, view: S.view });
const pinKey = () => `social:pins:${S.view}`;
const getPins = () => { try { return JSON.parse(localStorage.getItem(pinKey()) || "{}"); } catch (e) { return {}; } };
const setPins = (p) => { try { localStorage.setItem(pinKey(), JSON.stringify(p)); } catch (e) { /* private mode */ } };
function fillHours() {
  const hs = hours(), a = $s("lpa"), b = $s("lpb"), oa = a.value, ob = b.value;
  const opts = hs.map((f) => `<option value="${f}">F+${f} \u00b7 ${validLbl(f)} PT</option>`).join(""); a.innerHTML = opts; b.innerHTML = opts;
  a.value = hs.includes(+oa) ? oa : String(hs[0]); b.value = hs.includes(+ob) && +ob > +a.value ? ob : String(hs[hs.length - 1]);
}
const pick = () => { const a = +$s("lpa").value, b = +$s("lpb").value; return hours().filter((f) => f >= a && f <= b); };
function times(n) { const s0 = +$s("lps").value, s1 = $s("lps1").value ? +$s("lps1").value : s0, T = [0];
  for (let j = 0; j < n; j++) T.push(T[j] + 1 / lerp(s0, s1, n > 1 ? j / (n - 1) : 0)); return T; }
function info() {
  const s0 = +$s("lps").value, s1 = $s("lps1").value, hs = pick(), T = times(hs.length), hold = +$s("lph").value, p = getPins(), pan = $s("lpmode").value === "pan";
  $s("lpsv").textContent = `${s0} map${s0 === 1 ? "" : "s"}/s`; $s("lpnow").textContent = `Showing now: F+${S.hour}`;
  $s("lppan").hidden = !pan; $s("lppins").textContent = pan ? `${p.a ? "A set" : "A not set"} \u00b7 ${p.b ? "B set" : "B not set"}` : "";
  $s("lpinfo").textContent = hs.length < 2 ? "Pick an end hour after the start hour." :
    `${hs.length} maps, F+${hs[0]} to F+${hs[hs.length - 1]} \u00b7 ${(T[hs.length] + hold).toFixed(1)} s of video${s1 && +s1 !== s0 ? ` (speed ${s0} \u2192 ${s1} maps/s)` : ""} \u00b7 zoom ${$s("lpz0").value}\u00d7 \u2192 ${$s("lpz1").value === "s" ? $s("lpz0").value : $s("lpz1").value}\u00d7`;
  drawPins();
}
// pins: fractions of the image (same spot on 9:16 and 16:9 is NOT the same place, so pins are per frame shape + view)
function pinsFor(k) { const p = getPins(); return { a: p[k + "a"], b: p[k + "b"] }; }
function drawPins() {
  for (const k of ["v", "h"]) {
    const img = $s("i" + k), box = img.parentNode; box.style.position = "relative";
    box.querySelectorAll(".lpin").forEach((e) => e.remove());
    if (!P.on || $s("lpmode").value !== "pan") continue;
    const p = pinsFor(k), r = img.getBoundingClientRect(), br = box.getBoundingClientRect();
    for (const n of ["a", "b"]) { if (!p[n]) continue; const d = document.createElement("div"); d.className = "lpin " + n; d.textContent = n.toUpperCase();
      d.style.left = (r.left - br.left + p[n].x * r.width) + "px"; d.style.top = (r.top - br.top + p[n].y * r.height) + "px"; box.appendChild(d); }
  }
}
function onImgClick(k, e) {
  if (!P.pinMode) return; e.preventDefault(); const r = $s("i" + k).getBoundingClientRect(), p = getPins();
  p[k + P.pinMode] = { x: (e.clientX - r.left) / r.width, y: (e.clientY - r.top) / r.height }; setPins(p);
  P.pinMode = null; $s("lphint").hidden = true; info();
}
async function loadBmp(u) { const b = await fetch(u).then((r) => { if (!r.ok) throw new Error(`${r.status} ${u.split("/").pop()}`); return r.blob(); }); return createImageBitmap(b); }
let muxP = null;
const loadMuxer = () => muxP || (muxP = new Promise((res, rej) => { const sc = document.createElement("script"); sc.src = "vendor/mp4-muxer.js?v=522"; sc.onload = res; sc.onerror = () => { muxP = null; rej(new Error("could not load the MP4 writer")); }; document.head.appendChild(sc); }));
async function makeEncoder(cv, W, H) {   // same as studio.js
  if (window.VideoEncoder && window.VideoFrame) {
    for (const codec of ["avc1.640028", "avc1.4d0028", "avc1.42002a"]) {
      const cfg = { codec, width: W, height: H, bitrate: 10e6, framerate: FPS, avc: { format: "avc" } };
      let ok = false; try { ok = (await VideoEncoder.isConfigSupported(cfg)).supported; } catch (e) { /* next */ }
      if (!ok) continue;
      await loadMuxer();
      const mux = new Mp4Muxer.Muxer({ target: new Mp4Muxer.ArrayBufferTarget(), video: { codec: "avc", width: W, height: H, frameRate: FPS }, fastStart: "in-memory" });
      let err = null; const ve = new VideoEncoder({ output: (ch, meta) => mux.addVideoChunk(ch, meta), error: (e) => { err = e; } }); ve.configure(cfg);
      return { how: `H.264 (${codec}) via WebCodecs`,
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
  return { how: `MediaRecorder (${type || "default"}, real time)`, seg: null,
    async add() { if (!this.seg) { rec.resume(); this.seg = { t: performance.now(), n: 0 }; } if (tr.requestFrame) tr.requestFrame();
      this.seg.n++; const due = this.seg.t + this.seg.n * 1000 / FPS - performance.now(); if (due > 0) await sleep(due); },
    idle() { if (this.seg) { rec.pause(); this.seg = null; } },
    async done() { if (tr.requestFrame) tr.requestFrame(); await sleep(1000 / FPS); return new Promise((res) => { rec.onstop = () => res(new Blob(parts, { type: rec.mimeType || type })); if (rec.state === "paused") rec.resume(); rec.stop(); }); },
    abort() { try { rec.stop(); } catch (e) { /* stopped */ } } };
}
// one output frame: image (or two, cross-faded) zoomed about (cx, cy) [fractions], bands redrawn unzoomed when zoomed
function paint(c, k, A, B, mix, cx, cy, z, tmp) {
  const [W, H] = OUT[k]; c.globalAlpha = 1; c.fillStyle = "#111316"; c.fillRect(0, 0, W, H);
  const draw1 = (ctx, bmp, zz, ccx, ccy) => { const sw = bmp.width / zz, sh = bmp.height / zz;
    const sx = Math.min(bmp.width - sw, Math.max(0, ccx * bmp.width - sw / 2)), sy = Math.min(bmp.height - sh, Math.max(0, ccy * bmp.height - sh / 2));
    ctx.drawImage(bmp, sx, sy, sw, sh, 0, 0, W, H); };
  const layer = (ctx, zz, ccx, ccy) => { ctx.globalAlpha = 1; draw1(ctx, A, zz, ccx, ccy); if (B && mix > 0) { ctx.globalAlpha = mix; draw1(ctx, B, zz, ccx, ccy); ctx.globalAlpha = 1; } };
  c.imageSmoothingQuality = "high"; layer(c, z, cx, cy);
  if (z > 1.001 || (B && mix > 0)) {   // title + colour-bar bands from ONE unzoomed frame (no doubled date text in a cross-fade), soft edge
    const t = tmp.getContext("2d"), bd = BAND[k]; t.globalCompositeOperation = "source-over"; t.clearRect(0, 0, W, H); t.imageSmoothingQuality = "high"; t.globalAlpha = 1;
    draw1(t, B && mix >= 0.5 ? B : A, 1, 0.5, 0.5);
    const g = t.createLinearGradient(0, 0, 0, H); g.addColorStop(0, "#000"); g.addColorStop(bd.top[0], "#000"); g.addColorStop(bd.top[1], "rgba(0,0,0,0)");
    g.addColorStop(bd.bot[1], "rgba(0,0,0,0)"); g.addColorStop(bd.bot[0], "#000"); g.addColorStop(1, "#000");
    t.globalCompositeOperation = "destination-in"; t.fillStyle = g; t.fillRect(0, 0, W, H); t.globalCompositeOperation = "source-over";
    c.drawImage(tmp, 0, 0);
  }
}
async function make() {
  if (P.busy) return; const k = $s("lpk").value, hs = pick(), [W, H] = OUT[k], pan = $s("lpmode").value === "pan", pins = pinsFor(k);
  if (hs.length < 2) { st("Pick an end hour after the start hour."); return; }
  if (pan && !(pins.a && pins.b)) { st("Tap Set pin A / Set pin B, then tap the " + (k === "v" ? "9:16" : "16:9") + " picture."); return; }
  const T = times(hs.length), holdN = Math.round(+$s("lph").value * FPS), xf = +$s("lpx").value, panN = Math.max(1, Math.round(T[hs.length] * FPS) - 1);
  const z0 = +$s("lpz0").value, z1 = $s("lpz1").value === "s" ? z0 : +$s("lpz1").value, zoomAt = (t) => z0 * Math.pow(z1 / z0, ease(t));
  const cv = document.createElement("canvas"); cv.width = W; cv.height = H; const tmp = document.createElement("canvas"); tmp.width = W; tmp.height = H; const c = cv.getContext("2d");
  const pv = $s("lpprev"); pv.width = W / 4; pv.height = H / 4; const pc = pv.getContext("2d"); pv.hidden = false;
  const t0 = performance.now(), C = cur(); let enc = null, A = null, B = null; P.busy = true; P.cancel = false; $s("lpgo").disabled = true; $s("lpstop").hidden = false; $s("lpout").hidden = true;
  try {
    enc = await makeEncoder(cv, W, H); let n = 0;
    const src = (f) => url(nm(k, f, C.prod, C.view));
    A = await loadBmp(src(hs[0]));
    for (let j = 0; j < hs.length; j++) {
      if (P.cancel) throw new Error("stopped");
      if (enc.idle) enc.idle();
      B = j + 1 < hs.length && xf > 0 ? await loadBmp(src(hs[j + 1])) : null;
      st(`Making video\u2026 F+${hs[j]} (${j + 1}/${hs.length})`);
      const n0 = Math.round(T[j] * FPS), n1 = Math.round(T[j + 1] * FPS) + (j === hs.length - 1 ? holdN : 0), nm_ = Math.round(T[j + 1] * FPS) - n0;
      for (; n < n1; n++) {
        const tt = Math.min(1, n / panN), q = (n - n0) / Math.max(1, nm_), mix = B ? Math.max(0, Math.min(1, (q - (1 - xf)) / xf)) : 0;
        const cx = pan ? lerp(pins.a.x, pins.b.x, ease(tt)) : 0.5, cy = pan ? lerp(pins.a.y, pins.b.y, ease(tt)) : 0.5;
        paint(c, k, A, B, ease(mix), cx, cy, zoomAt(tt), tmp); await enc.add(n);
        if (n % 3 === 0) pc.drawImage(cv, 0, 0, pv.width, pv.height);
      }
      if (A && A.close) A.close(); A = B || (j + 1 < hs.length ? await loadBmp(src(hs[j + 1])) : null); B = null;
    }
    st("Finishing\u2026"); const how = enc.how, blob = await enc.done(); enc = null;
    const name = `ECMWF_${C.run}_${C.prod}_${C.view}_F${hs[0]}-F${hs[hs.length - 1]}_${W}x${H}${pan ? "_track" : ""}.${blob.type.includes("mp4") ? "mp4" : "webm"}`;
    const u = URL.createObjectURL(blob), v = $s("lpv"), dl = $s("lpdl"); if (v.dataset.u) URL.revokeObjectURL(v.dataset.u); v.dataset.u = u; v.src = u; dl.href = u; dl.download = name;
    const file = new File([blob], name, { type: blob.type }); $s("lpshare").hidden = !(navigator.canShare && navigator.canShare({ files: [file] }));
    $s("lpshare").onclick = () => navigator.share({ files: [file] }).catch(() => {});
    $s("lpout").hidden = false; pv.hidden = true;
    window.__lmp4 = { name, bytes: blob.size, frames: n, seconds: n / FPS, how, ms: Math.round(performance.now() - t0) };
    st(`Done: ${(blob.size / 1e6).toFixed(1)} MB, ${(n / FPS).toFixed(1)} s, made in ${((performance.now() - t0) / 1000).toFixed(0)} s`);
  } catch (e) { if (enc) enc.abort(); st(e.message === "stopped" ? "Stopped." : "Could not make the video: " + (e.message || e)); window.__lmp4 = { error: String(e.message || e) }; }
  finally { P.busy = false; $s("lpgo").disabled = false; $s("lpstop").hidden = true; if (A && A.close) A.close(); }
}
const st = (t) => { $s("lpst").textContent = t; };
function open() { P.on = true; $s("lp").hidden = false; fillHours(); if (!$s("lpa").dataset.init) { $s("lpa").value = String(S.hour); $s("lpa").dataset.init = 1; fillHours(); } info(); }
function init() {
  $s("loopbtn").onclick = () => { if ($s("lp").hidden) open(); else { P.on = false; $s("lp").hidden = true; drawPins(); } };
  $s("lp").addEventListener("click", (e) => { const b = e.target.closest("button[data-m]"); if (!b) return; const m = b.dataset.m;
    if (m === "x") { P.on = false; $s("lp").hidden = true; drawPins(); }
    else if (m === "min") { const mn = $s("lp").classList.toggle("min"); b.innerHTML = mn ? "+" : "&ndash;"; }
    else if (m === "sa") { $s("lpa").value = String(S.hour); if (+$s("lpb").value <= S.hour) { const hs = hours(), i = hs.indexOf(S.hour); $s("lpb").value = String(hs[Math.min(hs.length - 1, i + 1)]); } info(); }
    else if (m === "sb") { $s("lpb").value = String(S.hour); if (+$s("lpa").value >= S.hour) { const hs = hours(), i = hs.indexOf(S.hour); $s("lpa").value = String(hs[Math.max(0, i - 1)]); } info(); }
    else if (m === "a" || m === "b") { P.pinMode = m; const h = $s("lphint"); h.hidden = false; h.textContent = `Tap the ${$s("lpk").value === "v" ? "9:16" : "16:9"} picture where the loop should ${m === "a" ? "START (pin A)" : "END (pin B)"}.`; }
    else if (m === "c") { const p = getPins(), k = $s("lpk").value; delete p[k + "a"]; delete p[k + "b"]; setPins(p); info(); }
    else if (m === "go") make(); else if (m === "stop") P.cancel = true; });
  for (const id of ["lpa", "lpb", "lps1", "lph", "lpz0", "lpz1", "lpx", "lpmode", "lpk"]) $s(id).addEventListener("change", info);
  $s("lps").addEventListener("input", info);
  $s("lp").addEventListener("keydown", (e) => { if (/^(SELECT|INPUT)$/.test(e.target.tagName) && /^Arrow/.test(e.key)) e.stopPropagation(); }, true);
  for (const k of ["v", "h"]) $s("i" + k).addEventListener("click", (e) => onImgClick(k, e));
  addEventListener("resize", drawPins);
  window.__socialShown = () => { if (P.on) { fillHours(); info(); } };   // social.js calls this after every show()
  window.__socialLoop = { getPins, setPins, make, open, info };
}
init();
})();
