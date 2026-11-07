"use strict";
/* Save / export for the forecast viewer (runs entirely in the browser: no server, no build step, no extra hosted files).
   - Download image: the current frame's own JPEG, saved under a descriptive file name.
   - Download loop: the chosen frames as an animated GIF (own encoder below) or a video (MediaRecorder: MP4 where the
     browser records MP4, otherwise WebM). */
const LOOP_MAX = { gif: 72, video: 240 };   // GIF files grow fast (about 0.3-0.7 MB per 1000 px frame)
const pad = (n, w = 2) => String(n).padStart(w, "0");
const slug = (s) => String(s || "").toLowerCase().replace(/(\d)\s+km\b/g, "$1km").replace(/\+/g, "").replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "");

function initOf(fr) {   // run start (UTC); older frames without "init" fall back to the run text, e.g. "12Z run (5 AM PT 10-23)"
  if (!fr) return null;
  if (fr.init) return new Date(fr.init);
  const m = /(\d{1,2})Z run[^0-9]*(?:(\d{1,2})\s*(AM|PM)\s*PT\s*)?(\d{1,2})-(\d{1,2})/i.exec(fr.run || "");
  if (!m) return null;
  const hh = +m[1], mo = +m[4], dd = +m[5], y = new Date(fr.end || fr.start).getUTCFullYear();
  let add = 0;
  if (m[2]) { const lh = (+m[2] % 12) + (m[3].toUpperCase() === "PM" ? 12 : 0); const off = (hh - lh + 24) % 24; add = lh + off >= 24 ? 1 : 0; }
  return new Date(Date.UTC(y, mo - 1, dd + add, hh));
}
function runStamp(fr) {
  const d = initOf(fr); if (!d) return "run-unknown";
  return `${d.getUTCFullYear()}${pad(d.getUTCMonth() + 1)}${pad(d.getUTCDate())}_${pad(d.getUTCHours())}Z`;
}
function fHour(fr) {
  const d = initOf(fr); if (!d) return "";
  return "f" + pad(Math.max(0, Math.round((Date.parse(fr.end) - d) / 3600e3)), 3);
}
function namePart(fr) {
  const t = tabObj();
  const model = slug(fr.model || S.model || t.label.split(" ")[0]) || "model";
  const product = [slug(t.id), S.period && S.period !== "step" ? slug(S.period) : ""].filter(Boolean).join("-");
  return [model, product, slug(S.view), runStamp(fr)].join("_");
}
const extOf = (src) => (src.match(/\.(jpe?g|png|gif|webp)(?:$|\?)/i) || [, "jpg"])[1].toLowerCase().replace("jpeg", "jpg");
function frameFileName(fr) { return `${namePart(fr)}_${fHour(fr) || "frame"}.${extOf(fr.src)}`; }

/* ---------- Download image (map + meteogram) ---------- */
function updateSave() {
  const a = $("dl-img"); if (!a) return;
  const f = (S.tab !== "meteograms" && tabObj()) ? frames() : [];
  const fr = f[S.i];
  if (fr) { a.href = fr.src; a.download = frameFileName(fr); a.removeAttribute("aria-disabled"); a.title = `Save ${a.download}`; }
  else { a.removeAttribute("href"); a.setAttribute("aria-disabled", "true"); a.title = "No map for this choice"; }
  $("dl-loop-open").disabled = f.length < 2;
  if (!$("loop-panel").hidden) fillRange();
}
function updateMeteoSave(sec, p, townId, im) {
  const a = $("dl-meteo"); if (!a) return;
  if (im) {
    const run = slug(im.run || "") || "run";
    a.href = im.src; a.download = `${slug(sec.id)}_${slug(p.id)}_${slug(townId)}_${run}.${extOf(im.src)}`;
    a.removeAttribute("aria-disabled"); a.title = `Save ${a.download}`;
  } else { a.removeAttribute("href"); a.setAttribute("aria-disabled", "true"); a.title = "No chart for this choice"; }
}

/* ---------- loop panel ---------- */
const L = { busy: false, cancel: false };
function frameLabel(fr) {
  const d = initOf(fr), h = d ? Math.round((Date.parse(fr.end) - d) / 3600e3) : null;
  return `${h === null ? "" : `F+${Math.max(0, h)} \u00b7 `}${dayHr(new Date(fr.end))}`;
}
function fillRange() {
  const f = frames(); const a = $("loop-from"), b = $("loop-to");
  const key = f.map((x) => x.src).join("|");
  if (a._key !== key) {
    a.replaceChildren(); b.replaceChildren();
    f.forEach((fr, j) => { a.add(new Option(frameLabel(fr), j)); b.add(new Option(frameLabel(fr), j)); });
    a.value = 0; b.value = Math.max(0, f.length - 1); a._key = key;
  }
  loopInfo();
}
function loopSel() {
  let i0 = +$("loop-from").value, i1 = +$("loop-to").value; if (i1 < i0) [i0, i1] = [i1, i0];
  return frames().slice(i0, i1 + 1);
}
function loopInfo() {
  const n = loopSel().length, fmt = $("loop-fmt").value, max = LOOP_MAX[fmt === "gif" ? "gif" : "video"];
  const secs = (n * +$("loop-speed").value / 1000).toFixed(1);
  $("loop-info").textContent = n > max ? `${n} frames: too many for ${fmt === "gif" ? "a GIF" : "one video"} (max ${max}); narrow the range.`
    : `${n} frames, ${secs} s per loop.`;
  $("loop-go").disabled = L.busy || n < 2 || n > max;
}
function videoMime() {
  if (!window.MediaRecorder || !HTMLCanvasElement.prototype.captureStream) return "";
  return ["video/mp4;codecs=avc1", "video/mp4", "video/webm;codecs=vp9", "video/webm;codecs=vp8", "video/webm"]
    .find((m) => MediaRecorder.isTypeSupported(m)) || "";
}
function progress(done, total, text) {
  const p = $("loop-prog"); p.hidden = false; p.max = total; p.value = done;
  $("loop-status").textContent = text;
}
async function loadBitmap(src) {
  const r = await fetch(src); if (!r.ok) throw new Error(`${src}: HTTP ${r.status}`);
  return createImageBitmap(await r.blob());
}
function saveBlob(blob, name) {
  const url = URL.createObjectURL(blob); const a = document.createElement("a");
  a.href = url; a.download = name; document.body.appendChild(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 60000);
}
const tick = () => new Promise((r) => setTimeout(r, 0));
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function makeLoop() {
  const sel = loopSel(); if (sel.length < 2) return;
  const fmt = $("loop-fmt").value, delay = +$("loop-speed").value, width = +$("loop-size").value;
  L.busy = true; L.cancel = false; $("loop-go").disabled = true; $("loop-cancel").hidden = false; $("loop-result").textContent = "";
  try {
    const first = await loadBitmap(sel[0].src);
    const W = width && width < first.width ? width : first.width, H = Math.round(first.height * W / first.width); first.close();
    const cv = document.createElement("canvas"); cv.width = W; cv.height = H;
    const ctx = cv.getContext("2d", { willReadFrequently: fmt === "gif" });
    ctx.imageSmoothingQuality = "high";
    const base = `${namePart(sel[0])}_${fHour(sel[0]) || "f"}-${fHour(sel[sel.length - 1]) || "f"}`;
    let blob, ext;
    if (fmt === "gif") {
      const enc = new GifEncoder(W, H);
      for (let k = 0; k < sel.length; k++) {   // pass 1: shared palette from every frame
        if (L.cancel) throw new Error("cancelled");
        const bm = await loadBitmap(sel[k].src); ctx.drawImage(bm, 0, 0, W, H); bm.close();
        enc.sample(ctx.getImageData(0, 0, W, H).data);
        progress(k + 1, sel.length * 2, `Reading frame ${k + 1} of ${sel.length}…`); await tick();
      }
      enc.buildPalette();
      for (let k = 0; k < sel.length; k++) {   // pass 2: encode
        if (L.cancel) throw new Error("cancelled");
        const bm = await loadBitmap(sel[k].src); ctx.drawImage(bm, 0, 0, W, H); bm.close();
        enc.addFrame(ctx.getImageData(0, 0, W, H).data, k === sel.length - 1 ? delay * 2 : delay);
        progress(sel.length + k + 1, sel.length * 2, `Encoding GIF frame ${k + 1} of ${sel.length}…`); await tick();
      }
      blob = enc.finish(); ext = "gif";
    } else {
      const mime = videoMime(); if (!mime) throw new Error("this browser can't record video; pick GIF");
      ext = mime.includes("mp4") ? "mp4" : "webm";
      const bms = [];
      for (let k = 0; k < sel.length; k++) {
        if (L.cancel) throw new Error("cancelled");
        bms.push(await loadBitmap(sel[k].src)); progress(k + 1, sel.length * 2, `Loading frame ${k + 1} of ${sel.length}…`);
      }
      ctx.drawImage(bms[0], 0, 0, W, H);
      const stream = cv.captureStream(0), track = stream.getVideoTracks()[0];
      const rec = new MediaRecorder(stream, { mimeType: mime, videoBitsPerSecond: Math.round(W * H * 6) });
      const parts = []; rec.ondataavailable = (e) => e.data.size && parts.push(e.data);
      const stopped = new Promise((r) => { rec.onstop = r; });
      rec.start(250);
      for (let k = 0; k < bms.length; k++) {   // video records in real time: one frame per chosen frame speed
        if (L.cancel) break;
        ctx.drawImage(bms[k], 0, 0, W, H); track.requestFrame ? track.requestFrame() : null;
        progress(sel.length + k + 1, sel.length * 2, `Recording frame ${k + 1} of ${sel.length}…`);
        await sleep(k === bms.length - 1 ? delay * 2 : delay);
      }
      if (!L.cancel && track.requestFrame) {   // repeat the last frame once so players hold it for its full time
        ctx.drawImage(bms[bms.length - 1], 0, 0, W, H); track.requestFrame(); await sleep(100);
      }
      rec.stop(); await stopped; bms.forEach((b) => b.close()); track.stop();
      if (L.cancel) throw new Error("cancelled");
      blob = new Blob(parts, { type: mime.split(";")[0] });
    }
    const name = `${base}.${ext}`;
    saveBlob(blob, name);
    $("loop-status").textContent = "Done.";
    $("loop-result").textContent = `Saved ${name} (${(blob.size / 1048576).toFixed(1)} MB, ${sel.length} frames, ${W}×${H}).`;
  } catch (e) {
    $("loop-status").textContent = e.message === "cancelled" ? "Cancelled." : `Could not make the loop: ${e.message}`;
  } finally {
    L.busy = false; $("loop-cancel").hidden = true; loopInfo();
  }
}

function wireExport() {
  $("dl-loop-open").onclick = () => {
    const p = $("loop-panel"), open = p.hidden; p.hidden = !open; $("dl-loop-open").setAttribute("aria-expanded", String(open));
    if (open) { stop(); fillRange(); }
  };
  for (const id of ["loop-from", "loop-to", "loop-speed", "loop-fmt", "loop-size"]) $(id).onchange = loopInfo;
  $("loop-go").onclick = makeLoop;
  $("loop-cancel").onclick = () => { L.cancel = true; };
  const vm = videoMime(); const o = $("loop-fmt").querySelector('option[value="video"]');
  if (vm) o.textContent = `Video (${vm.includes("mp4") ? "MP4" : "WebM"})`; else { o.disabled = true; o.textContent = "Video (not supported in this browser)"; }
}

/* ---------- GIF89a encoder: one shared 256-color palette (median cut), LZW, looping ---------- */
class GifEncoder {
  constructor(w, h) { this.w = w; this.h = h; this.hist = new Uint32Array(32768); this.out = []; this.started = false; }
  sample(px) {   // 5-bit-per-channel histogram from every 3rd pixel
    const h = this.hist;
    for (let i = 0; i < px.length; i += 12) h[((px[i] >> 3) << 10) | ((px[i + 1] >> 3) << 5) | (px[i + 2] >> 3)]++;
  }
  buildPalette() {
    const cols = []; for (let c = 0; c < 32768; c++) if (this.hist[c]) cols.push(c);
    let boxes = [cols];
    const ch = (c, k) => k === 0 ? c >> 10 : k === 1 ? (c >> 5) & 31 : c & 31;
    while (boxes.length < 256) {   // split the box with the most pixels x widest channel
      let bi = -1, bs = -1, bk = 0;
      boxes.forEach((b, i) => {
        if (b.length < 2) return;
        let mn = [31, 31, 31], mx = [0, 0, 0], n = 0;
        for (const c of b) { for (let k = 0; k < 3; k++) { const v = ch(c, k); if (v < mn[k]) mn[k] = v; if (v > mx[k]) mx[k] = v; } n += this.hist[c]; }
        const r = [mx[0] - mn[0], mx[1] - mn[1], mx[2] - mn[2]]; const k = r.indexOf(Math.max(...r));
        const s = r[k] * Math.sqrt(n); if (r[k] > 0 && s > bs) { bs = s; bi = i; bk = k; }
      });
      if (bi < 0) break;
      const b = boxes[bi].sort((x, y) => ch(x, bk) - ch(y, bk));
      let tot = 0; for (const c of b) tot += this.hist[c];
      let acc = 0, cut = 1; for (let j = 0; j < b.length - 1; j++) { acc += this.hist[b[j]]; if (acc >= tot / 2) { cut = j + 1; break; } }
      boxes.splice(bi, 1, b.slice(0, cut), b.slice(cut));
    }
    const pal = new Uint8Array(768);
    boxes.forEach((b, i) => {
      let r = 0, g = 0, bl = 0, n = 0;
      for (const c of b) { const w = this.hist[c]; r += (c >> 10) * w; g += ((c >> 5) & 31) * w; bl += (c & 31) * w; n += w; }
      pal[i * 3] = Math.round((r / n) * 8.226); pal[i * 3 + 1] = Math.round((g / n) * 8.226); pal[i * 3 + 2] = Math.round((bl / n) * 8.226);
    });
    this.pal = pal; this.np = boxes.length; this.map = new Int16Array(32768).fill(-1);
  }
  nearest(c) {
    const r = ((c >> 10) << 3) + 4, g = (((c >> 5) & 31) << 3) + 4, b = ((c & 31) << 3) + 4, p = this.pal;
    let best = 0, bd = 1e9;
    for (let i = 0; i < this.np; i++) { const dr = p[i * 3] - r, dg = p[i * 3 + 1] - g, db = p[i * 3 + 2] - b; const d = dr * dr * 2 + dg * dg * 4 + db * db * 3; if (d < bd) { bd = d; best = i; } }
    return (this.map[c] = best);
  }
  head() {
    const b = this.bytes = []; const w16 = (v) => b.push(v & 255, (v >> 8) & 255);
    for (const c of "GIF89a") b.push(c.charCodeAt(0));
    w16(this.w); w16(this.h); b.push(0xf7, 0, 0);   // global color table, 256 entries
    for (let i = 0; i < 768; i++) b.push(this.pal[i] || 0);
    b.push(0x21, 0xff, 11); for (const c of "NETSCAPE2.0") b.push(c.charCodeAt(0)); b.push(3, 1, 0, 0, 0);   // loop forever
    this.out.push(new Uint8Array(b)); this.started = true;
  }
  addFrame(px, delayMs) {
    if (!this.started) this.head();
    const n = this.w * this.h, idx = new Uint8Array(n), map = this.map;
    for (let i = 0, j = 0; i < n; i++, j += 4) {
      const c = ((px[j] >> 3) << 10) | ((px[j + 1] >> 3) << 5) | (px[j + 2] >> 3);
      const m = map[c]; idx[i] = m >= 0 ? m : this.nearest(c);
    }
    const d = Math.max(2, Math.round(delayMs / 10));
    const hdr = [0x21, 0xf9, 4, 0x04, d & 255, d >> 8, 0, 0, 0x2c, 0, 0, 0, 0, this.w & 255, this.w >> 8, this.h & 255, this.h >> 8, 0];
    this.out.push(new Uint8Array(hdr), lzw(idx, 8));
  }
  finish() { this.out.push(new Uint8Array([0x3b])); return new Blob(this.out, { type: "image/gif" }); }
}
function lzw(idx, minBits) {
  const clear = 1 << minBits, eoi = clear + 1;
  const out = new Uint8Array(idx.length * 2 + 1024); let op = 0;
  const sub = new Uint8Array(255); let sp = 0;
  const emitByte = (v) => { sub[sp++] = v; if (sp === 255) { out[op++] = 255; out.set(sub, op); op += 255; sp = 0; } };
  let acc = 0, nb = 0, bits = minBits + 1, next = eoi + 1;
  const put = (code) => { acc |= code << nb; nb += bits; while (nb >= 8) { emitByte(acc & 255); acc >>>= 8; nb -= 8; } };
  const HS = 5003, hk = new Int32Array(HS), hv = new Int16Array(HS);
  const reset = () => { hk.fill(-1); bits = minBits + 1; next = eoi + 1; };
  reset(); put(clear);
  let cur = idx[0];
  for (let i = 1; i < idx.length; i++) {
    const c = idx[i], key = (cur << 8) | c;
    let h = ((c << 4) ^ cur) % HS; let found = -1;
    while (hk[h] !== -1) { if (hk[h] === key) { found = hv[h]; break; } h = (h + 1) % HS; }
    if (found >= 0) { cur = found; continue; }
    put(cur);
    if (next < 4096) { hk[h] = key; hv[h] = next++; if (next > (1 << bits) && bits < 12) bits++; }
    else { put(clear); reset(); }
    cur = c;
  }
  put(cur); put(eoi);
  if (nb > 0) emitByte(acc & 255);
  const body = out.subarray(0, op);   // full 255-byte sub-blocks so far
  const res = new Uint8Array(1 + body.length + (sp ? sp + 1 : 0) + 1);
  res[0] = minBits; res.set(body, 1); let rp = 1 + body.length;
  if (sp) { res[rp++] = sp; res.set(sub.subarray(0, sp), rp); rp += sp; }
  res[rp] = 0;   // block terminator
  return res;
}
