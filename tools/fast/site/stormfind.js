// Storm finder (10-31, Benjamin 3:17 PM: "Oh I like this idea, yes develop that"): from a model run's MSLP, find the lows in the
// view, link them hour to hour into tracks, pick the strongest (lowest central pressure), and propose a loop for it: start / end
// hour, pin A (where it is at the start), pin B (landfall, or the end of the track), and the landfall hour. Everything it fills
// in stays editable. Shared by Studio (studio.js, model-native lows = the L markers on the map) and Social (socialloop.js,
// ECMWF 0.25 deg lows projected onto the social frames). Land / sea comes from the ECMWF wave field (swh < 0 over land).
"use strict";
(() => {
const D2R = Math.PI / 180;
const hav = (a1, o1, a2, o2) => { const s = Math.sin((a2 - a1) * D2R / 2) ** 2 + Math.cos(a1 * D2R) * Math.cos(a2 * D2R) * Math.sin((o2 - o1) * D2R / 2) ** 2; return 12742 * Math.asin(Math.min(1, Math.sqrt(s))); };
// ECMWF 0.25 deg crop: lat/lon from the live manifest crop [i0, i1, j0, j1]
// (was row 0 = 88N / col 0 = 150E when j0 was 600; NA west1200 moved j0).
let CR = [8, 356, 557, 1421];
const IFS = {
  setCrop(cr) { if (cr && cr.length >= 4) CR = [+cr[0], +cr[1], +cr[2], +cr[3]]; },
  lat: (i) => 90 - (i + CR[0]) * 0.25,
  lon: (j) => { const l = (j + CR[2]) * 0.25; return l > 180 ? l - 360 : l; },
  ij: (lat, lon) => [(90 - lat) / 0.25 - CR[0], ((((lon % 360) + 360) % 360) / 0.25 - CR[2])]
};
let cropP = null;
function loadCrop(DATA) {
  return cropP || (cropP = (async () => {
    const manRes = await fetch(DATA + "manifest.json", { cache: "no-cache" });
    if (!manRes.ok) throw new Error("manifest.json HTTP " + manRes.status);
    const man = await manRes.json();
    IFS.setCrop(((man.models || {}).ifs || (man.models || {}).gfs || {}).crop);
    return man;
  })().catch((e) => { cropP = null; throw e; }));
}
function blurG(a, w, h, sigma) {   // separable gaussian, reflect (same as viewer.js blur)
  const r = Math.ceil(4 * sigma), k = []; let s = 0;
  for (let i = -r; i <= r; i++) { const v = Math.exp(-i * i / (2 * sigma * sigma)); k.push(v); s += v; }
  for (let i = 0; i < k.length; i++) k[i] /= s;
  const refl = (i, n) => { while (i < 0 || i >= n) i = i < 0 ? -i - 1 : 2 * n - i - 1; return i; };
  const t = new Float32Array(a.length), o = new Float32Array(a.length);
  for (let y = 0; y < h; y++) for (let x = 0; x < w; x++) { let v = 0; for (let i = -r; i <= r; i++) v += k[i + r] * a[y * w + refl(x + i, w)]; t[y * w + x] = v; }
  for (let y = 0; y < h; y++) for (let x = 0; x < w; x++) { let v = 0; for (let i = -r; i <= r; i++) v += k[i + r] * t[refl(y + i, h) * w + x]; o[y * w + x] = v; }
  return o;
}
function filt(a, w, h, size, mx) {   // scipy minimum_filter / maximum_filter, mode "nearest", square window
  const r0 = Math.floor(size / 2), r1 = size - 1 - r0, t = new Float32Array(a.length), o = new Float32Array(a.length), cmp = mx ? Math.max : Math.min;
  for (let y = 0; y < h; y++) for (let x = 0; x < w; x++) { let v = a[y * w + x]; for (let d = -r0; d <= r1; d++) v = cmp(v, a[y * w + Math.min(w - 1, Math.max(0, x + d))]); t[y * w + x] = v; }
  for (let y = 0; y < h; y++) for (let x = 0; x < w; x++) { let v = t[y * w + x]; for (let d = -r0; d <= r1; d++) v = cmp(v, t[Math.min(h - 1, Math.max(0, y + d)) * w + x]); o[y * w + x] = v; }
  return o;
}
async function px(url) {
  const r = await fetch(url); if (!r.ok) throw new Error(`HTTP ${r.status}`);
  const bm = await createImageBitmap(await r.blob(), { premultiplyAlpha: "none", colorSpaceConversion: "none" });
  const oc = new OffscreenCanvas(bm.width, bm.height), c = oc.getContext("2d", { willReadFrequently: true }); c.drawImage(bm, 0, 0);
  return { d: c.getImageData(0, 0, bm.width, bm.height).data, w: bm.width, h: bm.height };
}
async function decode(DATA, R, name, f) {   // viewer.js getField (packed channels, sqrt-coded precip)
  const st = R.steps.find((s) => s.f === f); if (!st || !st.ranges[name]) throw new Error(`nodata:${name}`);
  const pk = st.packs && st.packs[name], file = pk ? pk[0] : name, ch = pk ? pk[1] : 0;
  const I = await px(`${DATA}${R.base}/` + R.file.replace("{name}", file).replace("{f:03d}", String(f).padStart(3, "0")));
  const [lo, hi] = st.ranges[name], n = I.w * I.h, out = new Float32Array(n);
  if (st.ranges[name][2] === 2) for (let k = 0; k < n; k++) { const q = I.d[k * 4 + ch] / 255; out[k] = lo + q * q * (hi - lo); }
  else for (let k = 0; k < n; k++) out[k] = lo + I.d[k * 4 + ch] * (hi - lo) / 255;
  return { v: out, w: I.w, h: I.h };
}
let landP = null;
function landMask(DATA) {   // fn(lat, lon) -> true land / false sea / null unknown, from the newest ECMWF run's wave field
  return landP || (landP = (async () => {
    const man = await loadCrop(DATA), rs = (man.runs || {}).ifs || [];
    for (const r of rs.slice().reverse()) {
      const runRes = await fetch(`${DATA}runs/ifs/${r}/run.json`);
      if (!runRes.ok) continue;
      const R = await runRes.json(); if (!R.fields || !R.fields.includes("swh")) continue;
      const st = R.steps.find((s) => s.ranges && s.ranges.swh); if (!st) continue;
      const F = await decode(DATA, R, "swh", st.f);
      return (lat, lon) => { const [i, j] = IFS.ij(lat, lon), ii = Math.round(i), jj = Math.round(j);
        if (ii < 0 || jj < 0 || ii >= F.h || jj >= F.w) return null; return F.v[ii * F.w + jj] < 0; };
    }
    return () => null;
  })().catch(() => { landP = null; return () => null; }));
}
// lows on the ECMWF 0.25 grid, like make_social.py hl(): blur 2 cells, minimum over `size` cells, deeper than the highest
// pressure within 2 x size by more than 8 mb; one per centre (strongest first, >= size cells apart); value = raw minimum nearby
function lowsLL(raw, w, h, size) {
  const a = blurG(raw, w, h, 2.0), mn = filt(a, w, h, size, false), mx = filt(a, w, h, size * 2, true), c = [];
  for (let k = 0; k < a.length; k++) if (a[k] === mn[k] && mx[k] - mn[k] > 8) c.push(k);
  c.sort((x, y) => a[x] - a[y]); const keep = [];
  for (const k of c) { const i = (k / w) | 0, j = k % w; if (keep.some(([p, q]) => (i - p) ** 2 + (j - q) ** 2 < size * size)) continue; keep.push([i, j]); }
  return keep.map(([i, j]) => { let ex = Infinity; for (let di = -2; di <= 2; di++) for (let dj = -2; dj <= 2; dj++) { const ii = i + di, jj = j + dj; if (ii >= 0 && jj >= 0 && ii < h && jj < w) ex = Math.min(ex, raw[ii * w + jj]); }
    return { lat: IFS.lat(i), lon: IFS.lon(j), p: ex }; });
}
// hours: [{f, lows: [{p, lat?, lon?, x?, y?, ...}]}] (sorted by f). Tracks are grown from the deepest unused low forward and back,
// each hour taking the nearest low within reach (~120 km + 80 km/h; one missing hour bridged). Returns up to `max` tracks,
// deepest first, each {pts: [{f, ...low}], minP, fMin}.
function track(hours, opt = {}) {
  const dist = opt.dist || ((a, b) => hav(a.lat, a.lon, b.lat, b.lon)), reach = opt.reach || ((dh) => 120 + 80 * dh), max = opt.max || 5;
  const used = new Set(), key = (h, n) => h * 1000 + n, all = [];
  hours.forEach((H, h) => H.lows.forEach((L, n) => all.push([L.p, h, n])));
  all.sort((x, y) => x[0] - y[0]); const out = [];
  for (const [, h0, n0] of all) {
    if (used.has(key(h0, n0))) continue; const seed = hours[h0].lows[n0], pts = [{ h: h0, n: n0 }];
    for (const dir of [1, -1]) {
      let cur = { h: h0, L: seed }, h = h0 + dir, miss = 0;
      while (h >= 0 && h < hours.length && miss < 2) {
        const dh = Math.abs(hours[h].f - hours[cur.h].f); let best = null, bd = reach(dh);
        hours[h].lows.forEach((L, n) => { if (used.has(key(h, n))) return; const d = dist(cur.L, L); if (d < bd) { bd = d; best = n; } });
        if (best === null) { miss++; h += dir; continue; }
        miss = 0; pts.push({ h, n: best }); cur = { h, L: hours[h].lows[best] }; h += dir;
      }
    }
    pts.sort((a, b) => a.h - b.h); pts.forEach((p) => used.add(key(p.h, p.n)));
    if (pts.length < 3) continue;
    const P = pts.map((p) => Object.assign({ f: hours[p.h].f }, hours[p.h].lows[p.n])), mi = P.reduce((b, p, i) => p.p < P[b].p ? i : b, 0);
    out.push({ pts: P, minP: P[mi].p, fMin: P[mi].f });
    if (out.length >= max) break;
  }
  return out;
}
// landfall: first point over land that follows a point over sea (needs lat / lon); null when it stays over sea or land is unknown
function landfall(T, land) {
  let sea = false;
  for (const p of T.pts) { if (p.lat === undefined) return null; const l = land(p.lat, p.lon); if (l === false) sea = true; else if (l === true && sea) return p; }
  return null;
}
// the loop for a track: up to 72 h before landfall (or the deepest hour) to 12 h after landfall (or 36 h after the deepest hour);
// A = where the low is at the start, B = landfall (or where it is at the end)
function plan(T, lf) {
  const pts = T.pts, key = lf ? lf.f : T.fMin;
  const a = pts.find((p) => p.f >= key - 72) || pts[0], last = pts[pts.length - 1];
  // no landfall: end 36 h after the deepest hour (a whole two-week track makes a dull loop); B = where the low is then
  const endF = lf ? Math.min(last.f, lf.f + 12) : Math.min(last.f, T.fMin + 36), b = lf || [...pts].reverse().find((p) => p.f <= endF) || last;
  return { startF: a.f, endF: Math.max(endF, b.f), a, b, landfall: lf, minP: T.minP, fMin: T.fMin, pts };
}
// Lambert conformal (WGS84, as cartopy's LambertConformal) for the social frames
function lccProj(lon0, lat0, sp1, sp2) {
  const a = 6378137, e = 0.0818191908426215, m = (p) => Math.cos(p) / Math.sqrt(1 - (e * Math.sin(p)) ** 2);
  const t = (p) => Math.tan(Math.PI / 4 - p / 2) / Math.pow((1 - e * Math.sin(p)) / (1 + e * Math.sin(p)), e / 2);
  const p1 = sp1 * D2R, p2 = sp2 * D2R, n = (Math.log(m(p1)) - Math.log(m(p2))) / (Math.log(t(p1)) - Math.log(t(p2))), F = m(p1) / (n * Math.pow(t(p1), n));
  const rho = (p) => a * F * Math.pow(t(p), n), r0 = rho(lat0 * D2R);
  return (lon, lat) => { let dl = lon - lon0; while (dl > 180) dl -= 360; while (dl < -180) dl += 360; const r = rho(lat * D2R), th = n * dl * D2R; return [r * Math.sin(th), r0 - r * Math.cos(th)]; };
}
const fmtLL = (p) => p.lat === undefined ? "" : `${Math.abs(p.lat).toFixed(1)}\u00b0${p.lat >= 0 ? "N" : "S"} ${Math.abs(p.lon).toFixed(1)}\u00b0${p.lon < 0 ? "W" : "E"}`;
window.StormFind = { hav, IFS, loadCrop, blurG, decode, landMask, lowsLL, track, landfall, plan, lccProj, fmtLL };
})();
