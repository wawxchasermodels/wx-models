/* Radar + GOES-West satellite layers for the Observations map (fast site only, 11-03-26, Benjamin: toggleable, both OFF by default,
   same zoom / pan as the map, loop of recent frames). Loaded after obs.js; plugs in through Obs.hook().
   Data is fetched straight from the browser (all three servers send CORS "*", so saved images and videos stay exportable). No keys,
   no server, nothing stored by us.
     Radar      NOAA/NWS NCEP MRMS quality-controlled base reflectivity mosaic, 1 km, new frame every ~2 min
                WMS https://opengeo.ncep.noaa.gov/geoserver/conus/conus_bref_qcd/ows  (US government work, public domain)
     Satellite  NOAA GOES-West (GOES-18) ABI via NASA GIBS (WMS epsg4326 "best"), 10-min frames, ~35-60 min behind real time
                GOES-West_ABI_Band13_Clean_Infrared (10.3 um "Clean IR") and GOES-West_ABI_GeoColor (CIRA/NOAA GeoColor)
                NASA: "We acknowledge the use of imagery provided by services from NASA's Global Imagery Browse Services (GIBS),
                part of NASA's Earth Science Data and Information System (ESDIS)." GeoColor: please credit CIRA/NOAA.
   Each frame is one lat/lon (plate carree) image of a fixed box; a WebGL pass reprojects it per pixel into the obs map's own
   Lambert projection and the current zoom / pan, then the result is drawn under the coastlines, borders, isobars and stations.
   Two boxes per source: "detail" (Pacific NW, used when zoomed in) and "wide" (West + western Canada view).
   11-03 (t2224u) Mid-level water vapor (GOES-West ABI band 9, 6.9 um). NASA GIBS has no band 9, so it comes from the Iowa Environmental
     Mesonet (IEM) GOES-West WMS https://mesonet.agron.iastate.edu/cgi-bin/wms/goes_west.cgi (CORS "*", AccessConstraints None; NOAA
     GOES-18 data via Unidata), IEM's colour WV table: PNW box = conus_ch09 (2 km, every 5 min) over fulldisk_ch09 (6 km, every 10 min,
     fills north of the CONUS sector); wide box = fulldisk_ch09. IEM only serves the newest image, so the loop is built here: each new
     frame is saved in this browser (IndexedDB, the site's own origin, last 3 hours) while the layer is on, and the loop grows to 12.
   11-03 (t2226u) "Hide menu" button: collapses the view / layer / satellite chips (choice kept in localStorage obsMenuMin). */
"use strict";
const ObsImg = (() => {
  const RAD_WMS = "https://opengeo.ncep.noaa.gov/geoserver/conus/conus_bref_qcd/ows";
  const GIBS_WMS = "https://gibs.earthdata.nasa.gov/wms/epsg4326/best/wms.cgi";
  const GIBS_DOM = (layer) => `https://gibs.earthdata.nasa.gov/wmts/epsg4326/best/1.0.0/${layer}/default/2km/all/`;
  // box = [west, south, east, north] degrees; px = image width x height (radar detail 0.0125 deg ~1 km, satellite detail 0.02 deg ~1.5-2 km)
  const SRC = {
    radar: { label: "Radar", kind: "rad", layer: "conus_bref_qcd", fmt: "image/png", alpha: 0.88, n: 12, stepMin: 5, refreshMin: 4,
      tiles: { detail: { box: [-130, 39, -104, 53], px: [2080, 1120] }, wide: { box: [-130, 30, -100, 55], px: [1200, 1250] } },
      credit: "Radar: NOAA/NWS MRMS base reflectivity (public domain)" },
    ir: { label: "Clean IR", kind: "gibs", layer: "GOES-West_ABI_Band13_Clean_Infrared", fmt: "image/jpeg", alpha: 1, n: 12, stepMin: 10, refreshMin: 10,
      tiles: { detail: { box: [-140, 37, -100, 57], px: [2000, 1000] }, wide: { box: [-170, 26, -94, 72], px: [1900, 1150] } },
      credit: "Satellite: NOAA GOES-West Clean IR (band 13) via NASA GIBS/ESDIS" },
    gc: { label: "GeoColor", kind: "gibs", layer: "GOES-West_ABI_GeoColor", fmt: "image/jpeg", alpha: 1, n: 12, stepMin: 10, refreshMin: 10,
      tiles: { detail: { box: [-140, 37, -100, 57], px: [2000, 1000] }, wide: { box: [-170, 26, -94, 72], px: [1900, 1150] } },
      credit: "Satellite: NOAA GOES-West GeoColor (CIRA/NOAA) via NASA GIBS/ESDIS" },
    wv: { label: "Water vapor", kind: "iem", alpha: 1, n: 12, stepMin: 5, refreshMin: 1,
      tiles: { detail: { box: [-140, 37, -100, 57], px: [2000, 1000] }, wide: { box: [-170, 26, -94, 72], px: [1900, 1150] } },
      credit: "Satellite: NOAA GOES-West Mid-Level Water Vapor (band 9) via Iowa Environmental Mesonet" },
  };
  const PILL = { radar: "Radar", ir: "Satellite Clean IR (band 13)", gc: "Satellite GeoColor", wv: "Satellite Mid-Level Water Vapor (band 9)" };
  const ST = { radar: false, sat: "", frames: { radar: [], ir: [], gc: [], wv: [] }, img: new Map(), idx: -1, playing: true, timer: 0, last: 0,
    timesAt: {}, hold: false, blank: new Set(), all: { radar: [], ir: [], gc: [], wv: [] }, gl: null, glFail: "", sig: 0, msg: "", obs: null };
  const tf = new Intl.DateTimeFormat("en-US", { timeZone: "America/Los_Angeles", hour: "numeric", minute: "2-digit" });
  const $ = (id) => document.getElementById(id);
  const on = () => [...(ST.radar ? ["radar"] : []), ...(ST.sat ? [ST.sat] : [])];
  const bump = () => { ST.sig++; if (ST.obs) ST.obs.imgSig = ST.sig + ":" + on().join() + ":" + ST.idx; };

  /* ---- frame times ---- */
  async function times(id) {
    const s = SRC[id], now = Date.now();
    if (s.kind === "iem") return wvTimes(id);
    if (ST.timesAt[id] && now - ST.timesAt[id] < s.refreshMin * 60e3 && ST.frames[id].length) return ST.frames[id];
    let all = [];
    // a frame that was still black last time gets another try with each new time list
    for (const k of [...ST.blank]) if (k.startsWith(id + "|")) { ST.blank.delete(k); const t = k.slice(id.length + 1); for (const tl of ["detail", "wide"]) ST.img.delete(id + "|" + tl + "|" + t); }
    if (s.kind === "rad") {
      const x = await (await fetch(RAD_WMS + "?service=WMS&request=GetCapabilities&version=1.3.0", { cache: "no-store" })).text();
      const m = x.match(/<Dimension[^>]*name="time"[^>]*>([^<]*)</); if (!m) throw new Error("radar times");
      all = m[1].split(",").map((t) => t.trim()).filter(Boolean);
    } else {
      const a = new Date(now - 8 * 3600e3).toISOString().slice(0, 19) + "Z", b = new Date(now + 600e3).toISOString().slice(0, 19) + "Z";
      const x = await (await fetch(GIBS_DOM(s.layer) + `${a}--${b}.xml`, { cache: "no-store" })).text();
      const m = x.match(/<Domain>([^<]*)<\/Domain>/); if (!m) throw new Error("satellite times");
      for (const part of m[1].split(",")) {   // "start/end/PT10M" or a single time
        const [t0, t1, per] = part.split("/"); if (!t1) { all.push(t0); continue; }
        const st = (+((per || "PT10M").match(/(\d+)M/) || [0, 10])[1]) * 60e3;
        for (let t = Date.parse(t1); t >= Date.parse(t0) && all.length < 400; t -= st) all.push(new Date(t).toISOString().replace(".000Z", "Z"));
      }
      all.sort();
    }
    // newest n frames at least stepMin apart (radar comes every ~2 min; a 5-min step gives a 1-hour loop)
    const pick = [], gap = s.stepMin * 60e3 - 30e3;
    for (let i = all.length - 1; i >= 0 && pick.length < s.n + (s.kind === "gibs" ? 4 : 0); i--) { const t = Date.parse(all[i]); if (!pick.length || Date.parse(pick[0]) - t >= gap) pick.unshift(all[i]); }
    ST.all[id] = pick; ST.timesAt[id] = now; return pickFrames(id);
  }
  function pickFrames(id) { const s = SRC[id]; ST.frames[id] = ST.all[id].filter((t) => !ST.blank.has(id + "|" + t)).slice(-s.n); return ST.frames[id]; }
  function url(id, tile, t) {
    const s = SRC[id], T = s.tiles[tile], [w, so, e, n] = T.box, [W, H] = T.px;
    if (s.kind === "rad") return `${RAD_WMS}?SERVICE=WMS&REQUEST=GetMap&VERSION=1.3.0&LAYERS=${s.layer}&STYLES=&CRS=CRS:84&BBOX=${w},${so},${e},${n}&WIDTH=${W}&HEIGHT=${H}&FORMAT=${encodeURIComponent(s.fmt)}&TRANSPARENT=TRUE&TIME=${t}`;
    return `${GIBS_WMS}?SERVICE=WMS&REQUEST=GetMap&VERSION=1.3.0&LAYERS=${s.layer}&STYLES=&CRS=EPSG:4326&BBOX=${so},${w},${n},${e}&WIDTH=${W}&HEIGHT=${H}&FORMAT=${encodeURIComponent(s.fmt)}&TIME=${t}`;
  }
  function getImg(id, tile, t) {   // cached Image (decoded); resolves null on failure
    const key = id + "|" + tile + "|" + t; let r = ST.img.get(key);
    if (!r && SRC[id].kind === "iem") {   // water vapor frames come from this browser's own store (blob: URL, same origin)
      const im = new Image(); im.decoding = "async"; r = { im, ok: false };
      r.p = wvGet(tile + "|" + t).then((rec) => !rec ? (r.bad = true, null) : new Promise((res) => {
        im.onload = () => { r.ok = true; res(im); bump(); if (ST.obs) Obs.redraw(); }; im.onerror = () => { r.bad = true; res(null); };
        r.u = URL.createObjectURL(rec.blob); im.src = r.u; }));
      ST.img.set(key, r);
    }
    if (!r) {
      const im = new Image(); im.crossOrigin = "anonymous"; im.decoding = "async";
      r = { im, ok: false, p: new Promise((res) => { im.onload = () => {
        // GIBS lists the newest times before every tile of them is filled in: such a frame comes back all black. Drop it (the loop uses the rest)
        if (SRC[id].kind === "gibs" && blank(im)) { r.bad = true; ST.blank.add(id + "|" + t); pickFrames(id); res(null); bump(); return; }
        r.ok = true; res(im); bump(); if (ST.obs) Obs.redraw(); }; im.onerror = () => { r.bad = true; res(null); }; }) };
      im.src = url(id, tile, t); ST.img.set(key, r);
    }
    return r;
  }
  function blank(im) {
    const c = document.createElement("canvas"); c.width = 32; c.height = 22; const g = c.getContext("2d", { willReadFrequently: true }); g.drawImage(im, 0, 0, 32, 22);
    const d = g.getImageData(0, 0, 32, 22).data; let m = 0; for (let i = 0; i < d.length; i += 4) m = Math.max(m, d[i], d[i + 1], d[i + 2]); return m < 12;
  }
  function prune() {   // keep only images of the current frame lists
    const keep = new Set(); for (const id of Object.keys(SRC)) for (const t of ST.all[id]) for (const tile of ["detail", "wide"]) keep.add(id + "|" + tile + "|" + t);
    for (const k of [...ST.img.keys()]) if (!keep.has(k) || !on().includes(k.split("|")[0])) { const r = ST.img.get(k); r.im.src = ""; if (r.u) URL.revokeObjectURL(r.u); ST.img.delete(k); }
  }
  const tileFor = (id) => { const S = ST.obs; if (!S) return "detail";
    const T = SRC[id].tiles.detail.box, kmpx = 1 / (S.k * Math.min(S.dpr || 1, 2));   // device-pixel scale
    if (kmpx > 2.2) return "wide";
    // zoomed in: detail box, unless the view centre is outside it
    const ll = inv(S.cx, S.cy); return ll && ll[0] > T[0] && ll[0] < T[2] && ll[1] > T[1] && ll[1] < T[3] ? "detail" : "wide"; };

  /* ---- water vapor (IEM, newest image only): capture each new frame into a small store, the loop is read back from it ---- */
  const IEM = "https://mesonet.agron.iastate.edu/cgi-bin/wms/goes_west.cgi";
  const IEMJ = (sec) => `https://mesonet.agron.iastate.edu/data/gis/images/GOES/${sec}/channel09/GOES-18_C09.json`;
  const WV_KEEP_MS = 3 * 3600e3, MEM = new Map(); let dbp = null, memLoaded = null;
  function db() {
    if (!dbp) dbp = new Promise((res) => { try { const q = indexedDB.open("obsimg-wv", 1);
      q.onupgradeneeded = () => q.result.createObjectStore("f", { keyPath: "k" }); q.onsuccess = () => res(q.result); q.onerror = () => res(null); q.onblocked = () => res(null);
    } catch (e) { res(null); } });
    return dbp;
  }
  const idb = async (mode, fn) => { const d = await db(); if (!d) return null; return new Promise((res) => { try { const tx = d.transaction("f", mode), q = fn(tx.objectStore("f"));
    tx.oncomplete = () => res(q && q.result); tx.onerror = tx.onabort = () => res(null); } catch (e) { res(null); } }); };
  function wvLoad() { return memLoaded || (memLoaded = idb("readonly", (o) => o.getAll()).then((all) => { for (const r of all || []) if (!MEM.has(r.k)) MEM.set(r.k, r); })); }
  async function wvGet(k) { await wvLoad(); return MEM.get(k) || null; }
  async function wvPrune() {
    for (const tile of ["detail", "wide"]) {
      const rs = [...MEM.values()].filter((r) => r.tile === tile).sort((a, b) => Date.parse(a.t) - Date.parse(b.t));
      const drop = rs.filter((r, i) => Date.now() - Date.parse(r.t) > WV_KEEP_MS || i < rs.length - 24);
      for (const r of drop) { MEM.delete(r.k); await idb("readwrite", (o) => o.delete(r.k)); }
    }
  }
  async function wvValid(sec) { const j = await (await fetch(IEMJ(sec), { cache: "no-store" })).json(); return new Date(Date.parse(j.meta.valid)).toISOString().replace(".000Z", "Z"); }
  const wms = (layer, T, v) => new Promise((res, rej) => { const im = new Image(); im.crossOrigin = "anonymous";
    im.onload = () => res(im); im.onerror = () => rej(new Error("water vapor image"));
    im.src = `${IEM}?SERVICE=WMS&REQUEST=GetMap&VERSION=1.1.1&LAYERS=${layer}&STYLES=&SRS=EPSG:4326&BBOX=${T.box.join(",")}&WIDTH=${T.px[0]}&HEIGHT=${T.px[1]}&FORMAT=image/png&TRANSPARENT=TRUE&v=${encodeURIComponent(v)}`; });
  const wvBusy = {};
  async function wvCapture(tile, again) {
    const sec = tile === "detail" ? "conus" : "fulldisk", T = SRC.wv.tiles[tile];
    const v0 = await wvValid(sec), k = tile + "|" + v0; await wvLoad(); if (MEM.has(k)) return;
    if (Date.now() - Date.parse(v0) > WV_KEEP_MS) throw new Error("no recent water vapor image");
    const fd = tile === "detail" ? await wvValid("fulldisk").catch(() => v0) : v0;
    const ims = await Promise.all([wms("fulldisk_ch09", T, fd), ...(tile === "detail" ? [wms("conus_ch09", T, v0)] : [])]);
    if (await wvValid(sec) !== v0) { if (!again) return wvCapture(tile, true); return; }   // the image changed while loading: take the new one
    const c = document.createElement("canvas"); c.width = T.px[0]; c.height = T.px[1]; const g = c.getContext("2d", { willReadFrequently: true });
    for (const im of ims) g.drawImage(im, 0, 0, c.width, c.height);   // full disk first, the 2 km CONUS sector on top
    if (blank(c)) return;
    const enc = (type) => new Promise((res) => c.toBlob(res, type, 0.9));
    let blob = await enc("image/webp"); if (!blob || blob.type !== "image/webp") blob = await enc("image/jpeg");   // Safari cannot write WebP
    if (!blob) return;
    const rec = { k, tile, t: v0, blob, saved: Date.now() }; MEM.set(k, rec); await idb("readwrite", (o) => o.put(rec)); await wvPrune();
  }
  async function wvTimes(id) {
    const s = SRC[id], tile = tileFor(id), now = Date.now();
    if (ST.timesAt[id] && ST.wvTile === tile && now - ST.timesAt[id] < s.refreshMin * 60e3 && ST.frames[id].length) return ST.frames[id];
    try { await (wvBusy[tile] = wvBusy[tile] || wvCapture(tile).finally(() => { wvBusy[tile] = null; })); } catch (e) { ST.wvErr = e.message || String(e); }
    await wvPrune();
    const ts = [...MEM.values()].filter((r) => r.tile === tile && now - Date.parse(r.t) <= WV_KEEP_MS).map((r) => r.t).sort();
    const pick = [], gap = (tile === "detail" ? s.stepMin : 10) * 60e3 - 30e3;
    for (let i = ts.length - 1; i >= 0 && pick.length < s.n; i--) { const t = Date.parse(ts[i]); if (!pick.length || Date.parse(pick[0]) - t >= gap) pick.unshift(ts[i]); }
    ST.all[id] = pick; ST.timesAt[id] = now; ST.wvTile = tile; return pickFrames(id);
  }

  /* ---- loading: newest frame first (shows at once), then the rest in the background ---- */
  let loading = null;
  async function refresh() {
    if (loading) return loading;
    loading = (async () => {
      ST.msg = "";
      for (const id of on()) {
        try { await times(id); } catch (e) { ST.msg = SRC[id].label + " times unavailable"; continue; }
        const fr = ST.frames[id]; if (!fr.length) { ST.msg = SRC[id].label + ": no recent frames"; continue; }
        const tile = tileFor(id);
        for (let tries = 0; tries < 5 && ST.frames[id].length; tries++) { const f = ST.frames[id]; if (await getImg(id, tile, f[f.length - 1]).p) break; }   // newest real frame first
      }
      prune(); if (ST.idx < 0 || ST.idx >= len()) ST.idx = len() - 1;
      ui(); bump(); Obs.redraw(); if (!ST.timer) tick();
      for (let pass = 0; pass < 2; pass++) {   // pass 2: frames that slid in after black ones dropped out
        const todo = []; for (const id of on()) { const tile = tileFor(id); for (const t of [...ST.frames[id]].reverse()) todo.push([id, tile, t]); }
        await Promise.all([0, 1, 2].map(async () => { while (todo.length) { const [id, tile, t] = todo.shift(); if (on().includes(id) && tileFor(id) === tile) await getImg(id, tile, t).p; } }));
      }
      ui(); bump(); Obs.redraw();
    })().finally(() => { loading = null; });
    return loading;
  }
  const len = () => Math.max(0, ...on().map((id) => ST.frames[id].length));
  // frame i of the loop for one source (sources with different counts are aligned at the newest frame)
  const tAt = (id, i) => { const fr = ST.frames[id], L = len(); if (!fr.length) return null; const j = fr.length - (L - i); return fr[Math.max(0, Math.min(fr.length - 1, j))]; };

  /* ---- loop ---- */
  function tick() {
    clearTimeout(ST.timer); ST.timer = 0; if (!on().length || ST.hold) return;
    if (!ST.playing || !ST.obs || !ST.obs.shown || document.hidden) { ST.timer = setTimeout(tick, 600); return; }
    const L = len(); if (L > 1) {
      const ready = (i) => on().every((id) => { const r = ST.img.get(id + "|" + tileFor(id) + "|" + tAt(id, i)); return r && r.ok; });
      for (let s = 1; s <= L; s++) { const nxt = (ST.idx + s) % L; if (ready(nxt)) { if (nxt !== ST.idx) { ST.idx = nxt; bump(); Obs.redraw(); uiTime(); } break; } }
    }
    ST.timer = setTimeout(tick, ST.idx === L - 1 ? 1600 : 380);   // dwell on the newest frame
  }

  /* ---- WebGL reprojection (lat/lon image -> obs map Lambert conformal at the current zoom / pan) ---- */
  const VS = "attribute vec2 p;void main(){gl_Position=vec4(p,0.,1.);}";
  const FS = `precision highp float;uniform sampler2D tex;uniform vec2 sz;uniform float dpr,k,cx,cy,n,F,rho0,L0,alpha;uniform vec4 box;
    const float R=6371.,D=0.017453292519943295;
    void main(){vec2 css=vec2(gl_FragCoord.x,sz.y-gl_FragCoord.y)/dpr;vec2 vp=sz/dpr;
      float x=(css.x-vp.x*.5)/k+cx, y=(css.y-vp.y*.5)/k+cy, yr=rho0+y, s=sign(n);
      float rho=s*sqrt(x*x+yr*yr), th=atan(s*x,s*yr), lon=(L0+th/n)/D, lat=(2.*atan(pow(R*F/rho,1./n))-1.5707963267948966)/D;
      vec2 uv=vec2((lon-box.x)/(box.z-box.x),(box.w-lat)/(box.w-box.y));
      if(uv.x<0.||uv.x>1.||uv.y<0.||uv.y>1.){discard;}
      vec4 c=texture2D(tex,uv);gl_FragColor=vec4(c.rgb*c.a*alpha,c.a*alpha);}`;
  function glInit() {
    if (ST.gl || ST.glFail) return ST.gl;
    const cv = document.createElement("canvas"), gl = cv.getContext("webgl", { premultipliedAlpha: true, preserveDrawingBuffer: true, antialias: false });
    if (!gl) { ST.glFail = "Radar / satellite need WebGL, which this browser has turned off"; return null; }
    const sh = (t, src) => { const s = gl.createShader(t); gl.shaderSource(s, src); gl.compileShader(s); if (!gl.getShaderParameter(s, gl.COMPILE_STATUS)) throw new Error(gl.getShaderInfoLog(s)); return s; };
    try {
      const pr = gl.createProgram(); gl.attachShader(pr, sh(gl.VERTEX_SHADER, VS)); gl.attachShader(pr, sh(gl.FRAGMENT_SHADER, FS)); gl.linkProgram(pr); gl.useProgram(pr);
      const b = gl.createBuffer(); gl.bindBuffer(gl.ARRAY_BUFFER, b); gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 1, -1, -1, 1, 1, 1]), gl.STATIC_DRAW);
      const loc = gl.getAttribLocation(pr, "p"); gl.enableVertexAttribArray(loc); gl.vertexAttribPointer(loc, 2, gl.FLOAT, false, 0, 0);
      const tex = [0, 1].map((u) => { const t = gl.createTexture(); gl.activeTexture(gl.TEXTURE0 + u); gl.bindTexture(gl.TEXTURE_2D, t);
        for (const [a, v] of [[gl.TEXTURE_MIN_FILTER, gl.LINEAR], [gl.TEXTURE_MAG_FILTER, gl.LINEAR], [gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE], [gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE]]) gl.texParameteri(gl.TEXTURE_2D, a, v);
        return t; });   // unit 0 = satellite, unit 1 = radar (each keeps its last frame, so panning never re-uploads)
      gl.enable(gl.BLEND); gl.blendFunc(gl.ONE, gl.ONE_MINUS_SRC_ALPHA);
      const U = {}; for (const u of ["tex", "sz", "dpr", "k", "cx", "cy", "n", "F", "rho0", "L0", "alpha", "box"]) U[u] = gl.getUniformLocation(pr, u);
      ST.gl = { cv, gl, U, tex, cur: [null, null] };
    } catch (e) { ST.glFail = "Radar / satellite could not start (" + (e.message || e) + ")"; return null; }
    return ST.gl;
  }
  let PJ = null;   // projection constants for the obs map's current Lambert (same formulas as obs.js makeProj)
  function projOf(S) {
    const key = S.P && S.P.key; if (!key) return null; if (PJ && PJ.key === key) return PJ;
    const [lon0, p1, p2, lat0] = key.split(",").map(Number), D = Math.PI / 180, R = 6371, t = (p) => Math.tan(Math.PI / 4 + p / 2);
    const P1 = p1 * D, P2 = p2 * D, n = Math.log(Math.cos(P1) / Math.cos(P2)) / Math.log(t(P2) / t(P1)), F = Math.cos(P1) * Math.pow(t(P1), n) / n;
    return (PJ = { key, n, F, rho0: R * F / Math.pow(t(lat0 * D), n), L0: lon0 * D });
  }
  function inv(x, y) { const S = ST.obs, J = S && projOf(S); if (!J) return null; const yr = J.rho0 + y, s = Math.sign(J.n), rho = s * Math.hypot(x, yr), th = Math.atan2(s * x, s * yr);
    return [(J.L0 + th / J.n) * 180 / Math.PI, (2 * Math.atan(Math.pow(6371 * J.F / rho, 1 / J.n)) - Math.PI / 2) * 180 / Math.PI]; }
  // the newest loaded frame at or before loop index i (so a frame still loading never blanks the layer)
  function frameImg(id, i) {
    const tile = tileFor(id), other = tile === "detail" ? "wide" : "detail";
    for (let j = i; j >= 0; j--) { const t = tAt(id, j); for (const tl of [tile, other]) { const r = ST.img.get(id + "|" + tl + "|" + t); if (r && r.ok) return { im: r.im, tile: tl, t }; } }
    return null;
  }
  function under(g, S) {
    ST.obs = S; if (!on().length) return;
    const G = glInit(); if (!G) return;
    const J = projOf(S); if (!J) return;
    const W = Math.round(S.w * S.dpr), H = Math.round(S.h * S.dpr), { gl, U, cv } = G;
    if (cv.width !== W || cv.height !== H) { cv.width = W; cv.height = H; }
    gl.viewport(0, 0, W, H); gl.clearColor(0, 0, 0, 0); gl.clear(gl.COLOR_BUFFER_BIT);
    gl.uniform2f(U.sz, W, H); gl.uniform1f(U.dpr, S.dpr); gl.uniform1f(U.k, S.k); gl.uniform1f(U.cx, S.cx); gl.uniform1f(U.cy, S.cy);
    gl.uniform1f(U.n, J.n); gl.uniform1f(U.F, J.F); gl.uniform1f(U.rho0, J.rho0); gl.uniform1f(U.L0, J.L0);     let drew = 0; ST.shown = {};
    for (const id of [ST.sat, ST.radar ? "radar" : ""].filter(Boolean)) {   // satellite first, radar on top
      const f = frameImg(id, ST.idx < 0 ? len() - 1 : ST.idx); if (!f) continue;
      const u = id === "radar" ? 1 : 0; gl.activeTexture(gl.TEXTURE0 + u); gl.bindTexture(gl.TEXTURE_2D, G.tex[u]); gl.uniform1i(U.tex, u);
      if (G.cur[u] !== f.im) { gl.pixelStorei(gl.UNPACK_PREMULTIPLY_ALPHA_WEBGL, false); gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, gl.RGBA, gl.UNSIGNED_BYTE, f.im); G.cur[u] = f.im; }
      const b = SRC[id].tiles[f.tile].box; gl.uniform4f(U.box, b[0], b[1], b[2], b[3]); gl.uniform1f(U.alpha, SRC[id].alpha);
      gl.drawArrays(gl.TRIANGLE_STRIP, 0, 4); drew++; ST.shown[id] = f.t;
    }
    if (drew) { g.setTransform(1, 0, 0, 1, 0, 0); g.imageSmoothingEnabled = true; g.drawImage(cv, 0, 0); }
    uiTime();
  }

  /* ---- UI: a second chip row under the obs layer chips ---- */
  const CSS = `.obs-root .obs-img{margin-top:-4px}.obs-root .obs-img .oi-sep{width:1px;height:22px;background:var(--o-rule);margin:0 4px}
    .obs-root .obs-img .oi-t{font:12.5px "IBM Plex Mono",ui-monospace,monospace;color:var(--o-muted);white-space:nowrap}
    .obs-root .obs-img input[type=range]{width:min(180px,32vw);accent-color:var(--o-verm)}
    #obsov .obs-img button[aria-pressed="true"],#obsp .obs-img button[aria-pressed="true"],.obs-root .obs-img button[aria-pressed="true"]{background:#f4f2ee;color:#15171c;border-color:#f4f2ee;font-weight:600}
    .obs-root .obs-img button.oi-play{min-width:38px;padding:5px 10px}.obs-root .obs-img .oi-loop{display:contents}.obs-root .obs-img .oi-loop[hidden]{display:none!important}
    .obs-root .obs-img .oi-lab{font-size:13px;color:var(--o-muted)}
    .obs-root.obs-min #oviews,.obs-root.obs-min #olayers,.obs-root.obs-min .obs-img>:not(.oi-loop),.obs-root.obs-min .obs-img .oi-loop>.oi-sep:first-child{display:none!important}
    .obs-root.obs-min .obs-img{margin-top:0}
    .obs-root .oi-mrow{margin:2px 0 6px}.obs-root .oi-mrow button,#obsov .mg-top #oi-menu{white-space:nowrap}
    #obsov .obs-root.obs-min .obs-stage{height:max(320px,calc(100dvh - 130px));max-height:none}`;
  function mountUi(root) {
    if ($("oimg")) return;
    const st = document.createElement("style"); st.textContent = CSS; document.head.appendChild(st);
    const bar = document.createElement("div"); bar.className = "obs-bar obs-img"; bar.id = "oimg"; bar.setAttribute("role", "group"); bar.setAttribute("aria-label", "Radar and satellite (off by default)");
    bar.innerHTML = `<button type="button" id="oi-radar" aria-pressed="false" title="NWS radar mosaic (MRMS base reflectivity), last hour">Radar</button>
      <span class="oi-sep"></span>
      <span class="oi-lab">Satellite:</span>
      <button type="button" id="oi-ir" aria-pressed="false" title="GOES-West Clean IR (band 13, 10.3 um): cloud-top temperature, day and night. Last 2 hours, about 40-60 min behind">Clean IR</button>
      <button type="button" id="oi-gc" aria-pressed="false" title="GOES-West GeoColor (true color by day, IR at night), last 2 hours, about 40-60 min behind">GeoColor</button>
      <button type="button" id="oi-wv" aria-pressed="false" title="GOES-West mid-level water vapor (band 9, 6.9 um): moisture around 500 mb (white/blue moist, yellow dry). Newest image about 5-15 min behind; the loop builds from the frames saved while this is on">Water vapor</button>
      <span class="oi-loop" id="oi-loop" hidden><span class="oi-sep"></span><button type="button" class="oi-play" id="oi-play" aria-label="Pause loop">&#10074;&#10074;</button>
      <input type="range" id="oi-slide" min="0" max="0" value="0" aria-label="Loop frame"><span class="oi-t" id="oi-t"></span></span>`;
    const ly = root.querySelector("#olayers"); ly.after(bar);
    $("oi-radar").onclick = () => set({ radar: !ST.radar });
    $("oi-ir").onclick = () => set({ sat: ST.sat === "ir" ? "" : "ir" });
    $("oi-gc").onclick = () => set({ sat: ST.sat === "gc" ? "" : "gc" });
    $("oi-wv").onclick = () => set({ sat: ST.sat === "wv" ? "" : "wv" });
    menuUi(root);
    $("oi-play").onclick = () => { ST.playing = !ST.playing; ui(); tick(); };
    $("oi-slide").oninput = (e) => { ST.playing = false; ST.idx = +e.target.value; bump(); ui(); Obs.drawNow(); };
    ui();
  }
  // "Hide menu" (t2226u): in the viewer's Observations window the button sits in its title bar, elsewhere (Studio) above the chips
  function menuUi(root) {
    if ($("oi-menu")) return;
    const b = document.createElement("button"); b.type = "button"; b.id = "oi-menu"; b.setAttribute("aria-controls", "oviews olayers oimg");
    const top = root.parentElement && root.parentElement.querySelector(":scope > .mg-top");
    if (top) top.insertBefore(b, top.querySelector("#obsx")); else { const row = document.createElement("div"); row.className = "obs-bar oi-mrow"; row.append(b); root.prepend(row); }
    let min = false; try { min = localStorage.getItem("obsMenuMin") === "1"; } catch (e) { /* private mode */ }
    const apply = () => { root.classList.toggle("obs-min", min); b.textContent = min ? "Show menu \u25be" : "Hide menu \u25b4"; b.setAttribute("aria-expanded", String(!min)); };
    b.onclick = () => { min = !min; try { localStorage.setItem("obsMenuMin", min ? "1" : "0"); } catch (e) { /* private mode */ } apply(); };
    apply();
  }
  function ui() {
    if (!$("oimg")) return;
    $("oi-radar").setAttribute("aria-pressed", String(ST.radar)); $("oi-ir").setAttribute("aria-pressed", String(ST.sat === "ir")); $("oi-gc").setAttribute("aria-pressed", String(ST.sat === "gc")); $("oi-wv").setAttribute("aria-pressed", String(ST.sat === "wv"));
    $("oi-loop").hidden = !on().length; $("oi-play").innerHTML = ST.playing ? "&#10074;&#10074;" : "&#9654;"; $("oi-play").setAttribute("aria-label", ST.playing ? "Pause loop" : "Play loop");
    const sl = $("oi-slide"); sl.max = String(Math.max(0, len() - 1)); sl.value = String(Math.max(0, ST.idx)); uiTime();
  }
  function uiTime() {
    const el = $("oi-t"); if (!el) return;
    const parts = on().map((id) => { const t = (ST.shown && ST.shown[id]) || tAt(id, Math.max(0, ST.idx)); return t ? `${id === "radar" ? "Radar" : SRC[id].label} ${tf.format(new Date(t))}` : ""; }).filter(Boolean);
    const wvN = ST.sat === "wv" ? ST.frames.wv.length : 99;
    const txt = ST.glFail || ST.msg || (parts.length ? parts.join(" \u00b7 ") + " PT" + (wvN < 4 ? " \u00b7 water vapor loop builds while open" : "") : "loading\u2026");
    if (el.textContent !== txt) el.textContent = txt; const sl = $("oi-slide"); if (sl && document.activeElement !== sl) sl.value = String(Math.max(0, ST.idx));
  }
  function set(o) {
    if ("radar" in o) ST.radar = !!o.radar; if ("sat" in o) ST.sat = SRC[o.sat] ? o.sat : "";
    if (!on().length) { clearTimeout(ST.timer); prune(); ST.idx = -1; ui(); bump(); Obs.redraw(); return; }
    ST.idx = -1; ST.playing = true; ui(); bump(); Obs.redraw();
    refresh().then(() => { ST.idx = len() - 1; bump(); ui(); Obs.redraw(); tick(); });
  }
  // refresh the frame lists while a layer is on and the map is showing; reload a tile when the zoom crosses detail / wide
  setInterval(() => { if (on().length && ST.obs && ST.obs.shown && !document.hidden && !ST.hold) refresh(); }, 60e3);
  let lastTiles = "";
  setInterval(() => { if (!on().length || !ST.obs || ST.hold) return; const tl = on().map(tileFor).join(); if (tl !== lastTiles) { lastTiles = tl; refresh(); } }, 1000);

  Obs.hook("under", under);
  Obs.hook("mount", mountUi);
  Obs.hook("credit", () => on().map((id) => SRC[id].credit).join(" · "));

  // Studio: credit lines, the shown frame times, and a hold + seek for the MP4 export (loop frames follow the video's progress)
  function credits() { return on().map((id) => SRC[id].credit); }
  function info() { return on().map((id) => ({ id, label: PILL[id], t: (ST.shown && ST.shown[id]) || tAt(id, Math.max(0, ST.idx)) })); }
  function hold(h) { ST.hold = !!h; if (!h) tick(); }
  function seek(p) { const L = len(); if (!L) return; ST.idx = Math.max(0, Math.min(L - 1, Math.floor(p * L * 0.999))); bump(); Obs.drawNow(); uiTime(); }
  return { set, state: () => ({ radar: ST.radar, sat: ST.sat, idx: ST.idx, n: len(), playing: ST.playing, frames: ST.frames, shown: ST.shown, msg: ST.msg, wvErr: ST.wvErr || "", glFail: ST.glFail, imgs: ST.img.size, loaded: [...ST.img.values()].filter((r) => r.ok).length }),
    active: () => on().length > 0, credits, info, hold, seek, refresh, ready: () => loading || Promise.resolve() };
})();
