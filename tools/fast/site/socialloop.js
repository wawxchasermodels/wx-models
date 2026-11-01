// Social tab MP4 loops (10-31-26, Benjamin 1:55 PM: "I also want these loop options for the social media files we made").
// Same options as Studio's Save MP4: start / end hour (+ "= now"), speed slider with live length and optional end speed, hold,
// start / end zoom, storm pan between pins A and B, 9:16 or 16:9, saved as MP4 in the browser (WebCodecs H.264 + vendor/mp4-muxer,
// MediaRecorder fallback). Source = the 4K social PNGs (2160x3840 / 3840x2160) drawn into a 1080x1920 / 1920x1080 frame.
// The social frames are finished graphics (title, date, color bar baked in), so when zoomed the title band and the color-bar band
// are redrawn unzoomed on top with a soft edge: the map zooms, the text stays put. "Crossfade" blends one map into the next.
// Finer hours (10-31-26, Benjamin 2:02 PM "Only needs to be hd"): the latest run also has HD loop frames every 6 h
// (social/<run>/loop/<name>.jpg, 1920x1080 / 1080x1920, same layout as the 4K stills; index item .loop = {hours, every, size});
// "Step" picks 6 h / 12 h from those (default 6 h) or the 24 h 4K stills. Older runs: 24 h only.
"use strict";
(() => {
const FPS = 30, OUT = { v: [1080, 1920], h: [1920, 1080] };
// text bands of make_social.py (fraction of height): solid to a, fading out by b
const BAND = { v: { top: [0.25, 0.272], bot: [0.80, 0.775] }, h: { top: [0.265, 0.292], bot: [0.85, 0.822] } };
const $s = (id) => document.getElementById(id), sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const lerp = (a, b, t) => a + (b - a) * t, ease = (t) => t * t * (3 - 2 * t);
const P = { on: false, cancel: false, pinMode: null };
const stills = () => [...$s("hour").options].map((o) => +o.value);
const loopInfo = () => { const it = S.idx && S.idx.items && S.idx.items[S.run]; return it && it.loop && it.loop.hours && it.loop.hours.length ? it.loop : null; };
const step = () => +($s("lpstep").value || 24);
const useHD = () => !!loopInfo() && step() < 24;
const hours = () => { const L = loopInfo(), st_ = step(); return useHD() ? L.hours.filter((f) => (f - L.hours[0]) % st_ === 0) : stills(); };
function fillStep() {   // the Step menu follows the run: 6 h / 12 h HD only where loop frames exist
  const e = $s("lpstep"), L = loopInfo(), want = e.dataset.v || (L ? String(L.every || 6) : "24");
  const o = (L ? [[L.every || 6, `${L.every || 6} h (HD frames)`], [12, "12 h (HD frames)"]] : []).concat([[24, "24 h (4K stills)"]]);
  e.innerHTML = o.map(([v, t]) => `<option value="${v}">${t}</option>`).join(""); e.value = o.some(([v]) => String(v) === want) ? want : String(o[0][0]);
  $s("lpsteph").textContent = L ? "" : "This run has 24 h frames only (finer HD frames are kept for the newest run).";
}
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
  fillStep(); fillHours();
  const s0 = +$s("lps").value, s1 = $s("lps1").value, hs = pick(), T = times(hs.length), hold = +$s("lph").value, p = getPins(), pan = $s("lpmode").value === "pan";
  $s("lpsv").textContent = `${s0} map${s0 === 1 ? "" : "s"}/s`; $s("lpnow").textContent = `Showing now: F+${S.hour}`;
  const pk = pinsFor($s("lpk").value);   // pins are kept per frame shape (va/vb, ha/hb)
  $s("lppan").hidden = !pan; $s("lppins").textContent = pan ? `${pk.a ? "A set" : "A not set"} \u00b7 ${pk.b ? "B set" : "B not set"}` : "";
  $s("lpinfo").textContent = hs.length < 2 ? "Pick an end hour after the start hour." :
    `${hs.length} maps, F+${hs[0]} to F+${hs[hs.length - 1]} \u00b7 ${(T[hs.length] + hold).toFixed(1)} s of video${s1 && +s1 !== s0 ? ` (speed ${s0} \u2192 ${s1} maps/s)` : ""} \u00b7 zoom ${$s("lpz0").value}\u00d7 \u2192 ${$s("lpz1").value === "s" ? $s("lpz0").value : $s("lpz1").value}\u00d7`;
  drawPins();
}
// pins: fractions of the image (same spot on 9:16 and 16:9 is NOT the same place, so pins are per frame shape + view)
function pinsFor(k) { const p = getPins(); return { a: p[k + "a"], b: p[k + "b"] }; }
function drawPins() {
  for (const k of ["v", "h"]) {
    const img = $s("i" + k), box = img.parentNode; box.style.position = "relative";
    box.querySelectorAll(".lpin,.lptrk,.lpline,.lpdh").forEach((e) => e.remove());
    if (!P.on || $s("lpmode").value !== "pan") continue;
    const p = pinsFor(k), r = img.getBoundingClientRect(), br = box.getBoundingClientRect();
    const T = TRK.sel >= 0 && TRK.key === `${S.run}/${S.view}` ? TRK.list[TRK.sel] : null;
    if (T) for (const q of T.pts) { const f_ = frac(S.view, k, q.lat, q.lon), d = document.createElement("div"); d.className = "lptrk" + (T.landfall && q.f === T.landfall.f ? " lf" : "");
      d.style.left = (r.left - br.left + f_.x * r.width) + "px"; d.style.top = (r.top - br.top + f_.y * r.height) + "px"; box.appendChild(d); }
    const ox = r.left - br.left, oy = r.top - br.top;
    if (p.a && p.b) {   // the pan path A -> B (dashed), redrawn live while a pin is dragged
      const sv = document.createElementNS("http://www.w3.org/2000/svg", "svg"); sv.setAttribute("class", "lpline"); sv.style.left = ox + "px"; sv.style.top = oy + "px"; sv.setAttribute("width", r.width); sv.setAttribute("height", r.height);
      sv.innerHTML = `<line x1="${p.a.x * r.width}" y1="${p.a.y * r.height}" x2="${p.b.x * r.width}" y2="${p.b.y * r.height}"/>`; box.appendChild(sv); }
    for (const n of ["a", "b"]) { if (!p[n]) continue; const d = document.createElement("div"); d.className = "lpin " + n; d.textContent = n.toUpperCase(); d.dataset.k = k; d.dataset.n = n;
      d.title = `Drag to move pin ${n.toUpperCase()}`; d.style.left = (ox + p[n].x * r.width) + "px"; d.style.top = (oy + p[n].y * r.height) + "px"; box.appendChild(d); pinDrag(d, k, n); }
    const hp = p.a || p.b;
    if (hp && !P.pinMode) { const h = document.createElement("div"); h.className = "lpdh"; h.textContent = PD ? `Moving ${PD.n.toUpperCase()}` : "Drag A or B to move";
      h.style.left = (ox + hp.x * r.width) + "px"; h.style.top = (oy + hp.y * r.height + (hp.y > 0.85 ? -46 : 26)) + "px"; box.appendChild(h); }
  }
}
// 10-31 5:12 PM (Benjamin: "drag point a and b for the storm across the map either with my finger, or with my cursor"): pins are
// draggable (mouse + touch, 44 px target, touch-action none so the page doesn't scroll); the stored fraction updates live.
let PD = null;
function pinDrag(el, k, n) {
  el.addEventListener("pointerdown", (e) => { if (P.busy || PV) return; e.preventDefault(); e.stopPropagation(); el.setPointerCapture(e.pointerId); PD = { k, n, id: e.pointerId }; el.classList.add("drag"); });
  el.addEventListener("pointermove", (e) => {
    if (!PD || PD.id !== e.pointerId) return; e.preventDefault(); const r = $s("i" + k).getBoundingClientRect(), p = getPins();
    p[k + n] = { x: Math.min(1, Math.max(0, (e.clientX - r.left) / r.width)), y: Math.min(1, Math.max(0, (e.clientY - r.top) / r.height)) }; setPins(p);
    window.__pinDrag = { k, n, x: p[k + n].x, y: p[k + n].y }; $s("lppins").textContent = `Moving pin ${n.toUpperCase()}…`;
    // move this element in place (re-creating it would drop the pointer capture); path line + hint follow
    const box = $s("i" + k).parentNode, br = box.getBoundingClientRect(), ox = r.left - br.left, oy = r.top - br.top, q = p[k + n];
    el.style.left = (ox + q.x * r.width) + "px"; el.style.top = (oy + q.y * r.height) + "px";
    const ln = box.querySelector(".lpline line"); if (ln) { ln.setAttribute(n === "a" ? "x1" : "x2", q.x * r.width); ln.setAttribute(n === "a" ? "y1" : "y2", q.y * r.height); }
    const h = box.querySelector(".lpdh"); if (h) { h.textContent = `Moving ${n.toUpperCase()}`; const hp = p[k + "a"] || q; h.style.left = (ox + hp.x * r.width) + "px"; h.style.top = (oy + hp.y * r.height + (hp.y > 0.85 ? -46 : 26)) + "px"; }
  });
  const up = (e) => { if (!PD || PD.id !== e.pointerId) return; PD = null; el.classList.remove("drag"); info(); };
  el.addEventListener("pointerup", up); el.addEventListener("pointercancel", up);
}
function onImgClick(k, e) {
  if (!P.pinMode) return; e.preventDefault(); const r = $s("i" + k).getBoundingClientRect(), p = getPins();
  p[k + P.pinMode] = { x: (e.clientX - r.left) / r.width, y: (e.clientY - r.top) / r.height }; setPins(p);
  if (P.pinMode === "a" && !p[k + "b"]) { P.pinMode = "b"; $s("lphint").textContent = "Pin A set. Now tap where the loop should END (pin B). Esc cancels."; info(); return; }   // straight on to B
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
    // zoomed: keep the crop's title / colour-bar rows hidden under the unzoomed bands (no big doubled date line below the title):
    // output row bd.top[1] must come from at/below source row bd.top[1] and output row bd.bot[1] from at/above source row bd.bot[1]
    const bd = BAND[k], lo = zz > 1.001 ? bd.top[1] * bmp.height * (1 - 1 / zz) : 0, hi = zz > 1.001 ? bd.bot[1] * bmp.height * (1 - 1 / zz) : bmp.height - sh;
    const sx = Math.min(bmp.width - sw, Math.max(0, ccx * bmp.width - sw / 2)), sy = Math.min(hi, Math.max(lo, ccy * bmp.height - sh / 2));
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
  if (pan && !(pins.a && pins.b)) { st("Track storm needs pins: tap where the loop starts (A), then where it ends (B)."); startPin(pins.a ? "b" : "a"); return; }
  const T = times(hs.length), holdN = Math.round(+$s("lph").value * FPS), xf = +$s("lpx").value, panN = Math.max(1, Math.round(T[hs.length] * FPS) - 1);
  const z0 = +$s("lpz0").value, z1 = $s("lpz1").value === "s" ? z0 : +$s("lpz1").value, zoomAt = (t) => z0 * Math.pow(z1 / z0, ease(t));
  const cv = document.createElement("canvas"); cv.width = W; cv.height = H; const tmp = document.createElement("canvas"); tmp.width = W; tmp.height = H; const c = cv.getContext("2d");
  const pv = $s("lpprev"); pv.width = W / 4; pv.height = H / 4; const pc = pv.getContext("2d"); pv.hidden = false;
  const t0 = performance.now(), C = cur(); let enc = null, A = null, B = null; P.busy = true; P.cancel = false; $s("lpgo").disabled = true; $s("lpstop").hidden = false; $s("lpout").hidden = true;
  try {
    enc = await makeEncoder(cv, W, H); let n = 0; const totN = Math.round(T[hs.length] * FPS) + holdN, pg = $s("lpprog"); pg.hidden = false; pg.value = 0;
    const hd = useHD(), src = (f) => hd ? `${DATA}social/${C.run}/loop/${nm(k, f, C.prod, C.view)}.jpg` : url(nm(k, f, C.prod, C.view));
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
        if (n % 3 === 0) { pc.drawImage(cv, 0, 0, pv.width, pv.height); pg.value = n / totN; }
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
  finally { P.busy = false; $s("lpgo").disabled = false; $s("lpstop").hidden = true; $s("lpprog").hidden = true; if (A && A.close) A.close(); }
}
const st = (t) => { $s("lpst").textContent = t; };
// ---- usability (10-31 2:24 PM): remembered settings, presets, camera-move preview, progress bar, Enter / Esc
const OPT_IDS = ["lpk", "lpmode", "lpstep", "lps", "lps1", "lpx", "lph", "lpz0", "lpz1"], OPT_KEY = "social:loopopts";
function saveOpts() { const o = {}; for (const id of OPT_IDS) o[id] = $s(id).value; try { localStorage.setItem(OPT_KEY, JSON.stringify(o)); } catch (e) { /* private */ } }
function loadOpts() { let o = {}; try { o = JSON.parse(localStorage.getItem(OPT_KEY) || "{}"); } catch (e) { /* none */ }
  if (o.lpstep) $s("lpstep").dataset.v = o.lpstep;
  for (const id of OPT_IDS) { const el = $s(id); if (o[id] === undefined || id === "lpstep") continue; if (el.type === "range" || [...el.options].some((x) => x.value === o[id])) el.value = o[id]; } }
const PRESETS = {
  landfall: { lpmode: "pan", lps: "2", lps1: "1", lph: "2", lpz0: "1.2", lpz1: "2", lpx: "0.6" },
  overview: { lpmode: "loop", lps: "4", lps1: "", lph: "1", lpz0: "1", lpz1: "s", lpx: "0.3", all: true },
  zoomin: { lpmode: "loop", lps: "2", lps1: "", lph: "1.5", lpz0: "1", lpz1: "1.8", lpx: "0.6" },
};
function applyPreset(name) {
  const Q = PRESETS[name]; if (!Q) return;
  for (const [id, v] of Object.entries(Q)) if (id !== "all") $s(id).value = v;
  if (Q.all) { const hs = hours(); $s("lpa").value = String(hs[0]); $s("lpb").value = String(hs[hs.length - 1]); }
  saveOpts(); info(); $s("lppre").value = name;
  const k = $s("lpk").value, pk = pinsFor(k);
  if (Q.lpmode === "pan" && !(pk.a && pk.b)) startPin(pk.a ? "b" : "a", "Landfall zoom-in: ");
}
function startPin(m, pre) { P.pinMode = m; const h = $s("lphint"); h.hidden = false;
  h.textContent = `${pre || ""}Tap the ${$s("lpk").value === "v" ? "9:16" : "16:9"} picture where the loop should ${m === "a" ? "START (pin A)" : "END (pin B)"}. Esc cancels.`;
  $s("i" + $s("lpk").value).scrollIntoView({ block: "center", behavior: "smooth" }); }
// ---- storm finder (10-31 3:17 PM, Benjamin: "Oh I like this idea, yes develop that"): lows in the ECMWF run's sea-level pressure
// (the same L centres make_social.py draws), linked hour to hour over the loop's hours; the deepest track fills in the hours,
// pins A / B (both frame shapes) and landfall. Positions: make_social.py's Lambert conformal frames (stormfind.js lccProj).
const SVW = { na: { c: { h: [-108, 44.5], v: [-117, 46.0] }, half: { h: 4.4e6, v: 2.25e6 }, lon0: -110, sp: [33, 55], size: 25 },
  pnw: { c: { h: [-121.3, 46.4], v: [-121.0, 46.6] }, half: { h: 0.98e6, v: 0.56e6 }, lon0: -121, sp: [42, 50], size: 13 } };
const SHP = { h: [3840, 2160], v: [2160, 3840] }, TRK = { list: [], sel: -1, key: "" };
function frac(view, k, lat, lon) {   // lat / lon -> fraction across / down the social frame
  const V = SVW[view], pr = StormFind.lccProj(V.lon0, 47, V.sp[0], V.sp[1]), [cx, cy] = pr(V.c[k][0], V.c[k][1]), hx = V.half[k], hy = hx * SHP[k][1] / SHP[k][0], [x, y] = pr(lon, lat);
  return { x: (x - (cx - hx)) / (2 * hx), y: ((cy + hy) - y) / (2 * hy) };
}
const inFr = (k, q) => q.x > 0.04 && q.x < 0.96 && q.y > (k === "v" ? 0.30 : 0.28) && q.y < (k === "v" ? 0.80 : 0.76);   // make_social hl() bounds
async function findStorm() {
  if (P.busy || TRK.busy) return []; const view = S.view, run = S.run, k = $s("lpk").value;
  if (!SVW[view]) { st("The storm finder works on the North America and Pacific NW frames."); return []; }
  TRK.busy = true; $s("lpsf").disabled = true; st("Finding storms\u2026");
  try {
    const R = await fetch(`${DATA}runs/ifs/${run}/run.json`).then((r) => { if (!r.ok) throw new Error("this run's model data is no longer kept (newest ECMWF runs only)"); return r.json(); });
    if (!R.fields.includes("mslp")) throw new Error("no sea-level pressure in this run");
    const hs = hours(), H = [];
    for (const f of hs) {
      if (S.run !== run || S.view !== view) throw new Error("the run or view changed");
      if (!R.steps.some((x) => x.f === f)) continue;
      let F; try { F = await StormFind.decode(DATA, R, "mslp", f); } catch (e) { continue; }
      H.push({ f, lows: StormFind.lowsLL(F.v, F.w, F.h, SVW[view].size).filter((L) => inFr(k, frac(view, k, L.lat, L.lon))) });
      st(`Finding storms\u2026 F+${f}`);
    }
    if (!H.length) throw new Error("this run's model data is no longer kept (newest ECMWF runs only)");
    const land = await StormFind.landMask(DATA);
    TRK.list = StormFind.track(H).map((T) => StormFind.plan(T, StormFind.landfall(T, land))); TRK.key = `${run}/${view}`; TRK.sel = -1;
    const sel = $s("lpsfl"); sel.innerHTML = TRK.list.map((Q, i) => `<option value="${i}">${i + 1}. ${Math.round(Q.minP)} mb low \u00b7 F+${Q.pts[0].f}\u2013F+${Q.pts[Q.pts.length - 1].f} \u00b7 ${Q.landfall ? "landfall F+" + Q.landfall.f : "no landfall"}</option>`).join("");
    sel.hidden = TRK.list.length < 2;
    if (!TRK.list.length) { st("No closed low stays in this frame for 3+ of the loop's hours. Set pins by hand, or try a finer Step / the other view."); $s("lpsfi").textContent = ""; return []; }
    applyStorm(0); return TRK.list;
  } catch (e) { st("Storm finder: " + (e.message || e)); return []; }
  finally { TRK.busy = false; $s("lpsf").disabled = false; }
}
function applyStorm(n) {
  const Q = TRK.list[n]; if (!Q || TRK.key !== `${S.run}/${S.view}`) return; TRK.sel = n; $s("lpsfl").value = String(n);
  const p = getPins(); for (const k of ["v", "h"]) { p[k + "a"] = frac(S.view, k, Q.a.lat, Q.a.lon); p[k + "b"] = frac(S.view, k, Q.b.lat, Q.b.lon); } setPins(p);
  for (const [id, v] of Object.entries(PRESETS.landfall)) $s(id).value = v;
  // 10-31 3:53 PM (Benjamin: "make it autofill in the settings for the storm it found"): MSLP map, frame shape from the track's
  // direction, zooms from its size, speed for a ~7 s loop (slowing into landfall). All still editable.
  const pe = document.getElementById("prod");
  if (pe && !/mslp|slp/.test(S.prod) && [...pe.options].some((o) => o.value === "mslpqpf")) { pe.value = "mslpqpf"; pe.dispatchEvent(new Event("change")); }
  const dx = Math.abs(p.ha.x - p.hb.x) * 16, dy = Math.abs(p.ha.y - p.hb.y) * 9, k = dx >= dy ? "h" : "v"; $s("lpk").value = k;
  const d = Math.hypot(p[k + "a"].x - p[k + "b"].x, p[k + "a"].y - p[k + "b"].y), snap = (v, o) => o.reduce((b, x) => Math.abs(x - v) < Math.abs(b - v) ? x : b, o[0]), ZO = [1, 1.2, 1.4, 1.6, 1.8, 2, 2.5];
  const z1 = snap(Math.min(2.5, Math.max(1.6, 2.6 - 2.5 * d)), ZO), z0 = snap(Math.max(1, Math.min(z1 - 0.4, 1 / (0.5 + d))), ZO);
  $s("lpz0").value = String(z0); $s("lpz1").value = String(z1);
  info(); $s("lpa").value = String(Q.startF); $s("lpb").value = String(Q.endF); $s("lppre").value = "storm";
  const nM = pick().length, s0 = Math.min(6, Math.max(1.5, Math.round(nM / 7 * 2) / 2)); $s("lps").value = String(s0);
  $s("lps1").value = Q.landfall ? String(snap(Math.max(1, s0 / 2), [0.5, 1, 1.5, 2, 3, 4, 6])) : ""; saveOpts(); info();
  const lf = Q.landfall;
  $s("lpsfi").textContent = `Deepest ${Math.round(Q.minP)} mb at F+${Q.fMin}. ` + (lf ? `Landfall F+${lf.f} near ${StormFind.fmtLL(lf)}. ` : "No landfall in this frame: B is where the track ends. ") +
    `Loop F+${Q.startF} to F+${Q.endF}. Change any of it, or Set pin A / B by hand.`;
  st(`Found ${TRK.list.length} storm track${TRK.list.length === 1 ? "" : "s"}; using the deepest.`);
}
let PV = false;
async function previewMove() {
  if (PV || P.busy) return; const k = $s("lpk").value, hs = pick(), pan = $s("lpmode").value === "pan", pins = pinsFor(k), [W, H] = OUT[k];
  if (pan && !(pins.a && pins.b)) { st("Set pin A and pin B first."); startPin(pins.a ? "b" : "a"); return; }
  if (!hs.length) return; PV = true; st("Previewing the camera move\u2026");
  try {
    const hd = useHD(), A = await loadBmp(hd ? `${DATA}social/${S.run}/loop/${nm(k, hs[0], S.prod, S.view)}.jpg` : url(nm(k, hs[0], S.prod, S.view)));
    const cv = document.createElement("canvas"); cv.width = W; cv.height = H; const tmp = document.createElement("canvas"); tmp.width = W; tmp.height = H;
    const pv = $s("lpprev"); pv.width = W / 4; pv.height = H / 4; pv.hidden = false; const pc = pv.getContext("2d"); pv.scrollIntoView({ block: "nearest" });
    const z0 = +$s("lpz0").value, z1 = $s("lpz1").value === "s" ? z0 : +$s("lpz1").value, N = 60;
    for (let n = 0; n <= N; n++) { const tt = n / N, t = ease(tt);
      paint(cv.getContext("2d"), k, A, null, 0, pan ? lerp(pins.a.x, pins.b.x, t) : 0.5, pan ? lerp(pins.a.y, pins.b.y, t) : 0.5, z0 * Math.pow(z1 / z0, ease(tt)), tmp);
      pc.drawImage(cv, 0, 0, pv.width, pv.height); await sleep(1000 / 30); }
    if (A.close) A.close(); await sleep(600); st("Preview done (start hour only). Make MP4 runs the hours too.");
  } catch (e) { st("Could not preview: " + (e.message || e)); } finally { PV = false; }
}
function open() { P.on = true; $s("lp").hidden = false; if (!P.loaded) { loadOpts(); P.loaded = true; } fillStep(); fillHours(); if (!$s("lpa").dataset.init) { $s("lpa").value = String(S.hour); $s("lpa").dataset.init = 1; fillHours(); } info(); }
function init() {
  $s("loopbtn").onclick = () => { if ($s("lp").hidden) open(); else { P.on = false; $s("lp").hidden = true; drawPins(); } };
  $s("lp").addEventListener("click", (e) => { const b = e.target.closest("button[data-m]"); if (!b) return; const m = b.dataset.m;
    if (m === "x") { P.on = false; $s("lp").hidden = true; drawPins(); }
    else if (m === "min") { const mn = $s("lp").classList.toggle("min"); b.innerHTML = mn ? "+" : "&ndash;"; }
    else if (m === "sa") { $s("lpa").value = String(S.hour); if (+$s("lpb").value <= S.hour) { const hs = hours(), i = hs.indexOf(S.hour); $s("lpb").value = String(hs[Math.min(hs.length - 1, i + 1)]); } info(); }
    else if (m === "sb") { $s("lpb").value = String(S.hour); if (+$s("lpa").value >= S.hour) { const hs = hours(), i = hs.indexOf(S.hour); $s("lpa").value = String(hs[Math.max(0, i - 1)]); } info(); }
    else if (m === "a" || m === "b") startPin(m);
    else if (m === "pv") previewMove();
    else if (m === "sf") findStorm();
    else if (m === "c") { const p = getPins(), k = $s("lpk").value; delete p[k + "a"]; delete p[k + "b"]; setPins(p); info(); }
    else if (m === "go") make(); else if (m === "stop") P.cancel = true; });
  $s("lpstep").addEventListener("change", (e) => { e.target.dataset.v = e.target.value; info(); });
  for (const id of ["lpa", "lpb", "lps1", "lph", "lpz0", "lpz1", "lpx", "lpmode", "lpk"]) $s(id).addEventListener("change", info);
  $s("lps").addEventListener("input", info);
  for (const id of OPT_IDS) $s(id).addEventListener("change", (e) => { saveOpts(); if (e.isTrusted) $s("lppre").value = ""; });
  $s("lppre").addEventListener("change", (e) => { if (e.target.value === "storm") findStorm(); else applyPreset(e.target.value); });
  $s("lpsfl").addEventListener("change", (e) => applyStorm(+e.target.value));
  $s("lp").addEventListener("keydown", (e) => { if (e.key === "Enter" && !/^(SELECT|BUTTON|A)$/.test(e.target.tagName)) { e.preventDefault(); make(); } });
  addEventListener("keydown", (e) => { if (e.key !== "Escape" || !P.on) return;
    if (P.pinMode) { P.pinMode = null; $s("lphint").hidden = true; info(); } else if (P.busy) P.cancel = true; else { P.on = false; $s("lp").hidden = true; drawPins(); } });
  $s("lp").addEventListener("keydown", (e) => { if (/^(SELECT|INPUT)$/.test(e.target.tagName) && /^Arrow/.test(e.key)) e.stopPropagation(); }, true);
  for (const k of ["v", "h"]) $s("i" + k).addEventListener("click", (e) => onImgClick(k, e));
  addEventListener("resize", drawPins);
  window.__socialShown = () => { if (P.on) info(); };   // social.js calls this after every show()
  window.__socialLoop = { getPins, setPins, make, open, info, hours, useHD, findStorm, applyStorm, TRK, frac };
}
init();
})();
