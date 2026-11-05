/* Active Alerts map for Studio (WA land + PZZ marine). Preview 2026-11-05.
   Structured so OR/ID can be added later via AREAS / zone packs.
   API mirrors Obs enough for Studio: show/hide/redraw/_state. */
"use strict";
const Alerts = (() => {
  const AREAS = ["WA"]; // extend later: "OR","ID"
  const REFRESH_MS = 5 * 60 * 1000;
  const UA = "WAWeatherChasersStudio/1.0 (alerts; benjamin@wawxchasers)";
  const NWS = "https://api.weather.gov/alerts/active?area=" + AREAS.join(",");
  const FALLBACK = "#888888";
  const OCEAN = "#0b3a5c";
  // WA-tight default view (opens on Washington)
  const VIEW0 = { lon0: -125.05, lon1: -116.85, lat0: 45.45, lat1: 49.05 };
  const CSS = 1600; // off-screen canvas CSS px (Studio crops like Obs)
  const SIDE_PREF = { "Oak Harbor": "left" };
  const S = {
    shown: false, inited: false, loaded: 0, timer: null, dpr: 1,
    cx: CSS / 2, cy: CSS / 2, k: 1, view: "wa",
    colors: {}, zones: new Map(), towns: [], alerts: [],
    selectedType: null, // null = All
    status: "", raf: 0, baseReady: false, tiles: new Map(),
    sig: ""
  };
  const $ = (id) => document.getElementById(id);
  const status = (t) => { S.status = t; const el = $("al-status"); if (el) el.textContent = t; };

  function hexToRgba(hex, a) {
    const h = String(hex || FALLBACK).replace("#", "");
    const n = parseInt(h.length === 3 ? h.split("").map((c) => c + c).join("") : h, 16);
    return `rgba(${(n >> 16) & 255},${(n >> 8) & 255},${n & 255},${a})`;
  }

  // equirectangular project lon/lat -> canvas px at identity (k=1, cx/cy center)
  function llToXY(lon, lat) {
    const { lon0, lon1, lat0, lat1 } = VIEW0;
    const x = ((lon - lon0) / (lon1 - lon0)) * CSS;
    const y = ((lat1 - lat) / (lat1 - lat0)) * CSS;
    return [x, y];
  }
  function worldToScreen(x, y) {
    return [(x - S.cx) * S.k + CSS / 2, (y - S.cy) * S.k + CSS / 2];
  }
  function screenToWorld(sx, sy) {
    return [(sx - CSS / 2) / S.k + S.cx, (sy - CSS / 2) / S.k + S.cy];
  }

  async function loadJSON(url, opts) {
    const r = await fetch(url, opts);
    if (!r.ok) throw new Error(url + " " + r.status);
    return r.json();
  }

  function colorFor(ev) { return S.colors[ev] || FALLBACK; }

  function zoneId(u) { return String(u || "").split("/").pop(); }

  function buildZoneIndex(fc) {
    S.zones.clear();
    for (const f of (fc.features || [])) {
      const id = f.id || (f.properties && f.properties.id) || "";
      if (!id) continue;
      S.zones.set(id, f);
      S.zones.set("https://api.weather.gov/zones/forecast/" + id, f);
      S.zones.set("https://api.weather.gov/zones/county/" + id, f);
    }
  }

  function geomFromZones(alert) {
    if (alert.geometry) return alert.geometry;
    const zones = (alert.properties && alert.properties.affectedZones) || [];
    const parts = [];
    for (const z of zones) {
      const f = S.zones.get(z) || S.zones.get(zoneId(z));
      if (f && f.geometry) parts.push(f.geometry);
    }
    if (!parts.length) return null;
    if (parts.length === 1) return parts[0];
    return { type: "GeometryCollection", geometries: parts };
  }

  function walkCoords(geom, fn) {
    if (!geom) return;
    const t = geom.type;
    if (t === "Polygon") geom.coordinates.forEach((ring) => fn(ring));
    else if (t === "MultiPolygon") geom.coordinates.forEach((poly) => poly.forEach((ring) => fn(ring)));
    else if (t === "GeometryCollection") (geom.geometries || []).forEach((g) => walkCoords(g, fn));
  }

  function pointInRing(x, y, ring) {
    let inside = false;
    for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
      const xi = ring[i][0], yi = ring[i][1], xj = ring[j][0], yj = ring[j][1];
      const inter = ((yi > y) !== (yj > y)) && (x < (xj - xi) * (y - yi) / ((yj - yi) || 1e-12) + xi);
      if (inter) inside = !inside;
    }
    return inside;
  }
  function pointInGeom(lon, lat, geom) {
    let ok = false;
    walkCoords(geom, (ring) => {
      if (ok) return;
      if (pointInRing(lon, lat, ring)) ok = true;
    });
    return ok;
  }

  function visibleAlerts() {
    if (!S.selectedType) return S.alerts;
    return S.alerts.filter((a) => (a.properties && a.properties.event) === S.selectedType);
  }

  function eventTypes() {
    const m = new Map();
    for (const a of S.alerts) {
      const ev = (a.properties && a.properties.event) || "Alert";
      if (!m.has(ev)) m.set(ev, { event: ev, color: colorFor(ev), n: 0 });
      m.get(ev).n += 1;
    }
    return [...m.values()].sort((a, b) => a.event.localeCompare(b.event));
  }

  // Progressive town density from zoom (S.k). Inside selected alerts preferred.
  function townBudget() {
    // k~1 statewide; k~2.5 region; k~4 county
    if (S.k < 1.15) return { maxTier: 0, n: 18 };
    if (S.k < 1.6) return { maxTier: 1, n: 28 };
    if (S.k < 2.2) return { maxTier: 2, n: 40 };
    if (S.k < 3.2) return { maxTier: 3, n: 55 };
    return { maxTier: 4, n: 80 };
  }

  function pickTowns() {
    const budget = townBudget();
    const vis = visibleAlerts();
    const geoms = vis.map((a) => a._geom).filter(Boolean);
    const inside = [], outside = [];
    for (const t of S.towns) {
      if (t.tier > budget.maxTier && !t.notable) continue;
      const hit = geoms.length ? geoms.some((g) => pointInGeom(t.lon, t.lat, g)) : false;
      (hit ? inside : outside).push(t);
    }
    // notables + higher pop first (already sorted); take inside first then a few around
    const out = [];
    const take = (arr, n) => { for (const t of arr) { if (out.length >= n) break; out.push(t); } };
    take(inside, budget.n);
    take(outside, Math.min(budget.n, out.length + Math.max(6, Math.floor(budget.n * 0.35))));
    return out;
  }

  function pathGeom(g, ctx) {
    walkCoords(g, (ring) => {
      if (!ring.length) return;
      const [x0, y0] = llToXY(ring[0][0], ring[0][1]);
      const [sx0, sy0] = worldToScreen(x0, y0);
      ctx.moveTo(sx0, sy0);
      for (let i = 1; i < ring.length; i++) {
        const [x, y] = llToXY(ring[i][0], ring[i][1]);
        const [sx, sy] = worldToScreen(x, y);
        ctx.lineTo(sx, sy);
      }
      ctx.closePath();
    });
  }

  // Esri World Imagery tiles (Sentinel-ish stand-in matching alert graphics look)
  function lonLatToTile(lon, lat, z) {
    const n = Math.pow(2, z);
    const x = Math.floor((lon + 180) / 360 * n);
    const latR = lat * Math.PI / 180;
    const y = Math.floor((1 - Math.log(Math.tan(latR) + 1 / Math.cos(latR)) / Math.PI) / 2 * n);
    return [x, y];
  }
  function tileUrl(z, x, y) {
    return `https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/${z}/${y}/${x}`;
  }
  function ensureTile(z, x, y) {
    const key = z + "/" + x + "/" + y;
    let t = S.tiles.get(key);
    if (t) return t;
    t = { img: new Image(), ok: false, bad: false };
    t.img.crossOrigin = "anonymous";
    t.img.onload = () => { t.ok = true; req(); };
    t.img.onerror = () => { t.bad = true; };
    t.img.src = tileUrl(z, x, y);
    S.tiles.set(key, t);
    return t;
  }
  function drawBasemap(ctx) {
    ctx.fillStyle = OCEAN;
    ctx.fillRect(0, 0, CSS * S.dpr, CSS * S.dpr);
    // choose z from current scale
    const span = (VIEW0.lon1 - VIEW0.lon0) / S.k;
    let z = 6;
    if (span < 6) z = 7;
    if (span < 3.5) z = 8;
    if (span < 2) z = 9;
    if (span < 1.1) z = 10;
    // corners of view in lon/lat
    const [w0x, w0y] = screenToWorld(0, 0);
    const [w1x, w1y] = screenToWorld(CSS, CSS);
    const lonA = VIEW0.lon0 + (w0x / CSS) * (VIEW0.lon1 - VIEW0.lon0);
    const lonB = VIEW0.lon0 + (w1x / CSS) * (VIEW0.lon1 - VIEW0.lon0);
    const latA = VIEW0.lat1 - (w0y / CSS) * (VIEW0.lat1 - VIEW0.lat0);
    const latB = VIEW0.lat1 - (w1y / CSS) * (VIEW0.lat1 - VIEW0.lat0);
    const lonMin = Math.min(lonA, lonB), lonMax = Math.max(lonA, lonB);
    const latMin = Math.min(latA, latB), latMax = Math.max(latA, latB);
    const [tx0, ty0] = lonLatToTile(lonMin, latMax, z);
    const [tx1, ty1] = lonLatToTile(lonMax, latMin, z);
    const n = Math.pow(2, z);
    for (let tx = Math.max(0, tx0 - 1); tx <= Math.min(n - 1, tx1 + 1); tx++) {
      for (let ty = Math.max(0, ty0 - 1); ty <= Math.min(n - 1, ty1 + 1); ty++) {
        const tile = ensureTile(z, tx, ty);
        if (!tile.ok) continue;
        // tile lon/lat bounds
        const lon0 = tx / n * 360 - 180;
        const lon1 = (tx + 1) / n * 360 - 180;
        const lat0 = Math.atan(Math.sinh(Math.PI * (1 - 2 * (ty + 1) / n))) * 180 / Math.PI;
        const lat1 = Math.atan(Math.sinh(Math.PI * (1 - 2 * ty / n))) * 180 / Math.PI;
        const [x0, y0] = llToXY(lon0, lat1);
        const [x1, y1] = llToXY(lon1, lat0);
        const [sx0, sy0] = worldToScreen(x0, y0);
        const [sx1, sy1] = worldToScreen(x1, y1);
        try { ctx.drawImage(tile.img, sx0 * S.dpr, sy0 * S.dpr, (sx1 - sx0) * S.dpr, (sy1 - sy0) * S.dpr); } catch (e) { /* tainted */ }
      }
    }
    // slight darken so alert fills read
    ctx.fillStyle = "rgba(8,14,24,0.22)";
    ctx.fillRect(0, 0, CSS * S.dpr, CSS * S.dpr);
  }

  function drawTowns(ctx) {
    const picks = pickTowns();
    const placed = [];
    const fs = Math.max(11, Math.min(16, 12 * Math.sqrt(S.k))) * S.dpr;
    ctx.font = `700 ${fs}px Montserrat, system-ui, sans-serif`;
    ctx.textBaseline = "middle";
    const pad = 4 * S.dpr;
    const collides = (b) => placed.some((p) => !(b[2] < p[0] || b[0] > p[2] || b[3] < p[1] || b[1] > p[3]));
    for (const t of picks) {
      const [wx, wy] = llToXY(t.lon, t.lat);
      const [sx, sy] = worldToScreen(wx, wy);
      if (sx < 20 || sy < 20 || sx > CSS - 20 || sy > CSS - 20) continue;
      const dx = sx * S.dpr, dy = sy * S.dpr;
      const tw = ctx.measureText(t.n).width;
      const side = t.side || SIDE_PREF[t.n] || "right";
      const gap = 8 * S.dpr;
      const cands = side === "left"
        ? [[dx - gap - tw, dy], [dx + gap, dy], [dx - tw / 2, dy - gap - fs], [dx - tw / 2, dy + gap + fs]]
        : [[dx + gap, dy], [dx - gap - tw, dy], [dx - tw / 2, dy - gap - fs], [dx - tw / 2, dy + gap + fs]];
      let spot = null;
      for (const [tx, ty] of cands) {
        const b = [tx - pad, ty - fs / 2 - pad, tx + tw + pad, ty + fs / 2 + pad];
        if (b[0] < 8 || b[1] < 8 || b[2] > CSS * S.dpr - 8 || b[3] > CSS * S.dpr - 8) continue;
        if (collides(b)) continue;
        spot = { tx, ty, b }; break;
      }
      if (!spot) continue;
      // dot
      ctx.beginPath();
      ctx.arc(dx, dy, 3.2 * S.dpr, 0, Math.PI * 2);
      ctx.fillStyle = "#fff"; ctx.fill();
      ctx.lineWidth = 1.5 * S.dpr; ctx.strokeStyle = "rgba(0,0,0,0.75)"; ctx.stroke();
      // label
      ctx.lineWidth = 3.5 * S.dpr; ctx.strokeStyle = "rgba(12,16,24,0.9)";
      ctx.fillStyle = "#f2f5fa";
      ctx.strokeText(t.n, spot.tx, spot.ty);
      ctx.fillText(t.n, spot.tx, spot.ty);
      placed.push(spot.b);
    }
  }

  function draw() {
    const c = $("al-canvas"); if (!c) return;
    const ctx = c.getContext("2d");
    const dpr = Math.min(2, window.devicePixelRatio || 1); S.dpr = dpr;
    if (c.width !== CSS * dpr || c.height !== CSS * dpr) { c.width = CSS * dpr; c.height = CSS * dpr; }
    ctx.setTransform(1, 0, 0, 1, 0, 0);
    drawBasemap(ctx);
    // alerts
    const vis = visibleAlerts();
    for (const a of vis) {
      const g = a._geom; if (!g) continue;
      const col = colorFor(a.properties.event);
      ctx.beginPath(); pathGeom(g, ctx);
      ctx.fillStyle = hexToRgba(col, 0.42);
      ctx.fill("evenodd");
      ctx.lineWidth = 2.2 * S.dpr;
      ctx.strokeStyle = hexToRgba(col, 0.95);
      ctx.stroke();
    }
    drawTowns(ctx);
    S.sig = [S.loaded, S.selectedType || "ALL", S.k.toFixed(3), S.cx.toFixed(1), S.cy.toFixed(1), vis.length].join("|");
  }

  function req() { if (S.raf) return; S.raf = requestAnimationFrame(() => { S.raf = 0; draw(); }); }

  function renderChips() {
    const box = $("al-chips"); if (!box) return;
    const types = eventTypes();
    const mk = (label, type, color, n) => {
      const b = document.createElement("button");
      b.type = "button"; b.className = "al-chip";
      b.setAttribute("aria-pressed", type === S.selectedType || (type === null && S.selectedType === null) ? "true" : "false");
      b.innerHTML = `<span class="sw" style="background:${color || '#7cb7ff'}"></span><span>${label}${n != null ? " · " + n : ""}</span>`;
      b.onclick = () => { S.selectedType = type; renderChips(); req(); };
      return b;
    };
    box.innerHTML = "";
    box.appendChild(mk("All", null, "#7cb7ff", S.alerts.length));
    for (const t of types) box.appendChild(mk(t.event, t.event, t.color, t.n));
  }

  async function loadAlerts() {
    status("Loading alerts…");
    try {
      let data;
      try {
        const land = await loadJSON(NWS, { headers: { Accept: "application/geo+json", "User-Agent": UA } });
        const byId = new Map();
        for (const a of (land.features || [])) byId.set(a.id || (a.properties && a.properties.id), a);
        // marine PZZ: one extra request using zones present in the local pack
        const pzz = [...S.zones.keys()].filter((k) => /^PZZ\d+$/.test(k));
        for (let i = 0; i < pzz.length; i += 15) {
          const chunk = pzz.slice(i, i + 15);
          try {
            const m = await loadJSON("https://api.weather.gov/alerts/active?zone=" + chunk.join(","), { headers: { Accept: "application/geo+json", "User-Agent": UA } });
            for (const a of (m.features || [])) byId.set(a.id || (a.properties && a.properties.id), a);
          } catch (e) { /* chunk skip */ }
        }
        data = { type: "FeatureCollection", features: [...byId.values()] };
      } catch (liveErr) { data = await loadJSON("alert/active_wa.json"); status("Using cached snapshot (live NWS unavailable)"); }
      const feats = (data.features || []).filter((a) => {
        // keep land WA + marine PZZ (and any geometry already present)
        const zones = (a.properties && a.properties.affectedZones) || [];
        if (!zones.length) return !!a.geometry;
        return zones.some((z) => {
          const id = zoneId(z);
          return id.startsWith("WAZ") || id.startsWith("PZZ") || id.startsWith("WA");
        });
      });
      for (const a of feats) a._geom = geomFromZones(a);
      S.alerts = feats;
      S.loaded = Date.now();
      status(`${feats.length} active · WA land + marine · updated ${new Date(S.loaded).toLocaleTimeString("en-US", { timeZone: "America/Los_Angeles" })} PT`);
      renderChips();
      req();
    } catch (e) {
      status("Alerts could not load (" + (e && e.message || e) + ")");
      req();
    }
  }

  function wireCanvas() {
    const c = $("al-canvas"); if (!c || c._wired) return; c._wired = true;
    let drag = null;
    c.addEventListener("pointerdown", (e) => { drag = { x: e.clientX, y: e.clientY, cx: S.cx, cy: S.cy }; c.setPointerCapture(e.pointerId); });
    c.addEventListener("pointermove", (e) => {
      if (!drag) return;
      const dx = (e.clientX - drag.x) / S.k, dy = (e.clientY - drag.y) / S.k;
      S.cx = drag.cx - dx; S.cy = drag.cy - dy; req();
    });
    c.addEventListener("pointerup", () => { drag = null; });
    c.addEventListener("wheel", (e) => {
      e.preventDefault();
      const rect = c.getBoundingClientRect();
      const sx = (e.clientX - rect.left) * (CSS / rect.width);
      const sy = (e.clientY - rect.top) * (CSS / rect.height);
      const [wx, wy] = screenToWorld(sx, sy);
      const factor = e.deltaY < 0 ? 1.12 : 1 / 1.12;
      S.k = Math.min(8, Math.max(0.7, S.k * factor));
      // keep point under cursor
      const [nx, ny] = screenToWorld(sx, sy);
      S.cx += wx - nx; S.cy += wy - ny;
      req();
    }, { passive: false });
  }

  function mount(sel) {
    const host = typeof sel === "string" ? document.querySelector(sel) : sel;
    if (!host) return;
    host.innerHTML = `
      <div class="al-root">
        <span class="al-title">Active Alerts · WA</span>
        <div class="al-chips" id="al-chips" role="listbox" aria-label="Alert types"></div>
        <button type="button" class="al-btn" id="al-refresh">Refresh</button>
        <button type="button" class="al-btn" id="al-reset">WA view</button>
        <span class="al-meta" id="al-status">…</span>
      </div>
      <div id="alstage"><canvas id="al-canvas" width="1600" height="1600" aria-label="Active NWS alerts for Washington"></canvas></div>`;
    $("al-refresh").onclick = () => loadAlerts();
    $("al-reset").onclick = () => { S.k = 1; S.cx = CSS / 2; S.cy = CSS / 2; req(); };
    wireCanvas();
    S.inited = true;
  }

  function hide() { S.shown = false; }

  async function show() {
    S.shown = true;
    if (!S.inited) {
      const root = document.createElement("div"); root.id = "al-root-wrap";
      const host = $("alertp") || document.body;
      host.appendChild(root);
      // prefer #alert-root if present
      const prefer = $("alert-root");
      mount(prefer || root);
    }
    if (!Object.keys(S.colors).length) {
      try { S.colors = await loadJSON("alert/nws_colors.json"); } catch (e) { S.colors = {}; }
    }
    if (!S.zones.size) {
      try { buildZoneIndex(await loadJSON("alert/zones_wa.json")); } catch (e) { status("Zone pack missing"); }
    }
    if (!S.towns.length) {
      try {
        const t = await loadJSON("alert/towns_wa.json");
        S.towns = (t.places || []).slice().sort((a, b) => (b.notable - a.notable) || (a.tier - b.tier) || (b.pop - a.pop));
      } catch (e) { S.towns = []; }
    }
    req();
    if (!S.loaded || Date.now() - S.loaded > REFRESH_MS) loadAlerts();
    clearInterval(S.timer);
    S.timer = setInterval(() => { if (S.shown && !document.hidden) loadAlerts(); }, REFRESH_MS);
  }

  function titleText() {
    return S.selectedType || "All Alerts";
  }

  return {
    show, hide, redraw: req, drawNow: draw, load: loadAlerts,
    titleText, eventTypes,
    _state: S
  };
})();
window.Alerts = Alerts;
