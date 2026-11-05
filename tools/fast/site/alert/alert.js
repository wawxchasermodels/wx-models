/* Active Alerts map for Studio (WA land + PZZ marine). Preview 2026-11-05.
   Dark basemap (no satellite). Auto-fits to selected alert type bounds.
   OR/ID later via AREAS / zone packs. API: show/hide/redraw/fitToSelection/_state. */
"use strict";
const Alerts = (() => {
  const AREAS = ["WA"]; // extend later: "OR","ID"
  const REFRESH_MS = 5 * 60 * 1000;
  const UA = "WAWeatherChasersStudio/1.0 (alerts; benjamin@wawxchasers)";
  const NWS = "https://api.weather.gov/alerts/active?area=" + AREAS.join(",");
  const FALLBACK = "#888888";
  // Dark flat basemap (Benjamin t2433u): dark land, slightly lighter water, subtle outlines
  const C_OCEAN = "#0a1628";
  const C_WATER = "#12243a";
  const C_LAND = "#1b2433";
  const C_LAND_LINE = "rgba(120,140,170,0.35)";
  const C_COAST = "rgba(160,180,210,0.45)";
  // WA default extent (fallback before alerts load)
  const WA0 = { lon0: -125.15, lon1: -116.7, lat0: 45.4, lat1: 49.1 };
  const CSS = 1600;
  const SIDE_PREF = { "Oak Harbor": "left" };
  const RIGHT_CLEAR = 0.13; // keep right 13% of canvas clear for Studio face-cam overlays
  const PAD = 0.10; // padding around fitted bounds

  const S = {
    shown: false, inited: false, loaded: 0, timer: null, dpr: 1,
    cx: CSS / 2, cy: CSS / 2, k: 1, view: "wa",
    // dynamic lon/lat window the canvas currently covers at k=1,cx=cy=center
    viewLL: Object.assign({}, WA0),
    colors: {}, zones: new Map(), towns: [], alerts: [],
    selectedType: null, // null = All
    status: "", raf: 0, sig: "",
    landFeats: [], waterFeats: []
  };
  const $ = (id) => document.getElementById(id);
  const status = (t) => { S.status = t; const el = $("al-status"); if (el) el.textContent = t; };

  function hexToRgba(hex, a) {
    const h = String(hex || FALLBACK).replace("#", "");
    const n = parseInt(h.length === 3 ? h.split("").map((c) => c + c).join("") : h, 16);
    return `rgba(${(n >> 16) & 255},${(n >> 8) & 255},${n & 255},${a})`;
  }

  function llToXY(lon, lat) {
    const { lon0, lon1, lat0, lat1 } = S.viewLL;
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
  function xyToLL(x, y) {
    const { lon0, lon1, lat0, lat1 } = S.viewLL;
    return [lon0 + (x / CSS) * (lon1 - lon0), lat1 - (y / CSS) * (lat1 - lat0)];
  }

  async function loadJSON(url, opts) {
    const r = await fetch(url, opts);
    if (!r.ok) throw new Error(url + " " + r.status);
    return r.json();
  }
  function colorFor(ev) { return S.colors[ev] || FALLBACK; }
  function zoneId(u) { return String(u || "").split("/").pop(); }

  function buildZoneIndex(fc) {
    S.zones.clear(); S.landFeats = []; S.waterFeats = [];
    for (const f of (fc.features || [])) {
      const id = f.id || (f.properties && f.properties.id) || "";
      if (!id) continue;
      S.zones.set(id, f);
      S.zones.set("https://api.weather.gov/zones/forecast/" + id, f);
      S.zones.set("https://api.weather.gov/zones/county/" + id, f);
      if (String(id).startsWith("PZZ")) S.waterFeats.push(f);
      else S.landFeats.push(f);
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
    walkCoords(geom, (ring) => { if (!ok && pointInRing(lon, lat, ring)) ok = true; });
    return ok;
  }

  function geomBounds(geom) {
    let lo = Infinity, la0 = Infinity, hi = -Infinity, la1 = -Infinity, n = 0;
    walkCoords(geom, (ring) => {
      for (const p of ring) {
        const lon = p[0], lat = p[1];
        if (!isFinite(lon) || !isFinite(lat)) continue;
        if (lon < lo) lo = lon; if (lon > hi) hi = lon;
        if (lat < la0) la0 = lat; if (lat > la1) la1 = lat;
        n++;
      }
    });
    return n ? { lon0: lo, lon1: hi, lat0: la0, lat1: la1 } : null;
  }

  function mergeBounds(a, b) {
    if (!a) return b; if (!b) return a;
    return { lon0: Math.min(a.lon0, b.lon0), lon1: Math.max(a.lon1, b.lon1), lat0: Math.min(a.lat0, b.lat0), lat1: Math.max(a.lat1, b.lat1) };
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

  /** Fit canvas viewLL so visible alert bounds fill the usable area (left 87%, padded). */
  function fitToSelection() {
    const vis = visibleAlerts();
    let b = null;
    for (const a of vis) b = mergeBounds(b, geomBounds(a._geom));
    if (!b) b = Object.assign({}, WA0);
    // padding
    const dlon = Math.max(0.15, (b.lon1 - b.lon0) * PAD);
    const dlat = Math.max(0.1, (b.lat1 - b.lat0) * PAD);
    let lon0 = b.lon0 - dlon, lon1 = b.lon1 + dlon, lat0 = b.lat0 - dlat, lat1 = b.lat1 + dlat;
    // usable width = left (1 - RIGHT_CLEAR) of canvas; expand lon so content sits in that band centered vertically
    const usable = 1 - RIGHT_CLEAR;
    const contentW = lon1 - lon0, contentH = lat1 - lat0;
    // Make view square in lon/lat-scaled canvas space: aspect of CSS is 1:1
    // Horizontal: content must fit in usable*CSS width → view lon span = contentW / usable
    // Vertical: content fits in full height with same k
    const spanLon = contentW / usable;
    const spanLat = contentH; // will equalize to square world
    // Equalize so one CSS unit is consistent: use max of needed spans for square canvas
    // x uses spanLon across full CSS, but content only in left usable → 
    // view lon width = contentW / usable, centered in the left usable band
    let viewW = Math.max(spanLon, spanLat * (WA0.lon1 - WA0.lon0) / (WA0.lat1 - WA0.lat0) * 0.85);
    let viewH = Math.max(spanLat, spanLon * (WA0.lat1 - WA0.lat0) / (WA0.lon1 - WA0.lon0) * 0.85);
    // Prefer keeping geographic aspect ~ square canvas mapping
    const midLon = (lon0 + lon1) / 2;
    const midLat = (lat0 + lat1) / 2;
    // Place content center at horizontal position usable/2 (center of left 87% band)
    const contentCenterFracX = usable / 2; // 0.435
    // viewLL such that midLon maps to x = contentCenterFracX * CSS at identity
    // x = (lon - lon0) / (lon1-lon0) * CSS = contentCenterFracX * CSS
    // => (midLon - lon0) / viewW = contentCenterFracX => lon0 = midLon - contentCenterFracX * viewW
    viewW = Math.max(viewW, 0.8);
    viewH = Math.max(viewH, 0.5);
    S.viewLL = {
      lon0: midLon - contentCenterFracX * viewW,
      lon1: midLon - contentCenterFracX * viewW + viewW,
      lat0: midLat - viewH / 2,
      lat1: midLat + viewH / 2
    };
    // Clamp / floor: never zoom out past the WA theater (keeps CA/OR strays from blowing the view)
    const MAX = { lon0: -126.7, lon1: -116.4, lat0: 45.35, lat1: 49.2 };
    if (S.viewLL.lon0 < MAX.lon0 || S.viewLL.lon1 > MAX.lon1 || S.viewLL.lat0 < MAX.lat0 || S.viewLL.lat1 > MAX.lat1
        || (S.viewLL.lon1 - S.viewLL.lon0) > (MAX.lon1 - MAX.lon0) * 1.05) {
      // if bounds exceed WA theater, fit to intersection with MAX instead
      const iLon0 = Math.max(b.lon0 - dlon, MAX.lon0), iLon1 = Math.min(b.lon1 + dlon, MAX.lon1);
      const iLat0 = Math.max(b.lat0 - dlat, MAX.lat0), iLat1 = Math.min(b.lat1 + dlat, MAX.lat1);
      const midLon2 = (iLon0 + iLon1) / 2, midLat2 = (iLat0 + iLat1) / 2;
      let vW = Math.max((iLon1 - iLon0) / usable, 0.8);
      let vH = Math.max(iLat1 - iLat0, 0.5);
      // keep square-ish
      const asp = (MAX.lon1 - MAX.lon0) / (MAX.lat1 - MAX.lat0);
      if (vW / vH < asp) vW = vH * asp; else vH = vW / asp;
      S.viewLL = { lon0: midLon2 - contentCenterFracX * vW, lon1: midLon2 - contentCenterFracX * vW + vW, lat0: midLat2 - vH / 2, lat1: midLat2 + vH / 2 };
    }
    S.k = 1;
    S.cx = CSS / 2;
    S.cy = CSS / 2;
    req();
  }

  function townBudget() {
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

  function drawBasemap(ctx) {
    const W = CSS * S.dpr, H = CSS * S.dpr;
    ctx.fillStyle = C_OCEAN;
    ctx.fillRect(0, 0, W, H);
    // water (PZZ) slightly lighter
    ctx.beginPath();
    for (const f of S.waterFeats) if (f.geometry) pathGeom(f.geometry, ctx);
    ctx.fillStyle = C_WATER;
    ctx.fill("evenodd");
    // land
    ctx.beginPath();
    for (const f of S.landFeats) if (f.geometry) pathGeom(f.geometry, ctx);
    ctx.fillStyle = C_LAND;
    ctx.fill("evenodd");
    // subtle land outlines
    ctx.beginPath();
    for (const f of S.landFeats) if (f.geometry) pathGeom(f.geometry, ctx);
    ctx.lineWidth = 1.0 * S.dpr;
    ctx.strokeStyle = C_LAND_LINE;
    ctx.stroke();
    // coast / marine outlines a touch brighter
    ctx.beginPath();
    for (const f of S.waterFeats) if (f.geometry) pathGeom(f.geometry, ctx);
    ctx.lineWidth = 1.1 * S.dpr;
    ctx.strokeStyle = C_COAST;
    ctx.stroke();
  }

  function drawTowns(ctx) {
    const picks = pickTowns();
    const placed = [];
    const fs = Math.max(11, Math.min(16, 12 * Math.sqrt(S.k))) * S.dpr;
    ctx.font = `700 ${fs}px Montserrat, system-ui, sans-serif`;
    ctx.textBaseline = "middle";
    const pad = 4 * S.dpr;
    const maxX = CSS * S.dpr * (1 - RIGHT_CLEAR); // don't put labels in face-cam band
    const collides = (b) => placed.some((p) => !(b[2] < p[0] || b[0] > p[2] || b[3] < p[1] || b[1] > p[3]));
    for (const t of picks) {
      const [wx, wy] = llToXY(t.lon, t.lat);
      const [sx, sy] = worldToScreen(wx, wy);
      if (sx < 20 || sy < 20 || sx > CSS * (1 - RIGHT_CLEAR) - 20 || sy > CSS - 20) continue;
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
        if (b[0] < 8 || b[1] < 8 || b[2] > maxX - 8 || b[3] > CSS * S.dpr - 8) continue;
        if (collides(b)) continue;
        spot = { tx, ty, b }; break;
      }
      if (!spot) continue;
      ctx.beginPath();
      ctx.arc(dx, dy, 3.2 * S.dpr, 0, Math.PI * 2);
      ctx.fillStyle = "#fff"; ctx.fill();
      ctx.lineWidth = 1.5 * S.dpr; ctx.strokeStyle = "rgba(0,0,0,0.75)"; ctx.stroke();
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
    const vis = visibleAlerts();
    for (const a of vis) {
      const g = a._geom; if (!g) continue;
      const col = colorFor(a.properties.event);
      ctx.beginPath(); pathGeom(g, ctx);
      ctx.fillStyle = hexToRgba(col, 0.48);
      ctx.fill("evenodd");
      ctx.lineWidth = 2.2 * S.dpr;
      ctx.strokeStyle = hexToRgba(col, 0.95);
      ctx.stroke();
    }
    drawTowns(ctx);
    S.sig = [S.loaded, S.selectedType || "ALL", S.k.toFixed(3), S.cx.toFixed(1), S.cy.toFixed(1),
      S.viewLL.lon0.toFixed(3), S.viewLL.lat0.toFixed(3), vis.length].join("|");
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
      b.onclick = () => { S.selectedType = type; renderChips(); fitToSelection(); };
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
        const pzz = [...S.zones.keys()].filter((k) => /^PZZ\d+$/.test(k));
        for (let i = 0; i < pzz.length; i += 15) {
          const chunk = pzz.slice(i, i + 15);
          try {
            const m = await loadJSON("https://api.weather.gov/alerts/active?zone=" + chunk.join(","), { headers: { Accept: "application/geo+json", "User-Agent": UA } });
            for (const a of (m.features || [])) byId.set(a.id || (a.properties && a.properties.id), a);
          } catch (e) { /* chunk skip */ }
        }
        data = { type: "FeatureCollection", features: [...byId.values()] };
      } catch (liveErr) {
        data = await loadJSON("alert/active_wa.json");
        status("Using cached snapshot (live NWS unavailable)");
      }
      const WA_BOX = { lon0: -126.6, lon1: -116.5, lat0: 45.5, lat1: 49.2 };
      const feats0 = (data.features || []).filter((a) => {
        const zones = (a.properties && a.properties.affectedZones) || [];
        if (!zones.length) return !!a.geometry;
        return zones.some((z) => S.zones.has(zoneId(z)) || S.zones.has(z));
      });
      for (const a of feats0) a._geom = geomFromZones(a);
      const feats = feats0.filter((a) => {
        const b = geomBounds(a._geom); if (!b) return false;
        const cx = (b.lon0 + b.lon1) / 2, cy = (b.lat0 + b.lat1) / 2;
        return cx >= WA_BOX.lon0 && cx <= WA_BOX.lon1 && cy >= WA_BOX.lat0 && cy <= WA_BOX.lat1;
      });
      S.alerts = feats;
      S.loaded = Date.now();
      status(`${feats.length} active · WA land + marine · updated ${new Date(S.loaded).toLocaleTimeString("en-US", { timeZone: "America/Los_Angeles" })} PT`);
      renderChips();
      fitToSelection();
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
      S.k = Math.min(8, Math.max(0.55, S.k * factor));
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
        <button type="button" class="al-btn" id="al-reset">Fit view</button>
        <span class="al-meta" id="al-status">…</span>
      </div>
      <div id="alstage"><canvas id="al-canvas" width="1600" height="1600" aria-label="Active NWS alerts for Washington"></canvas></div>`;
    $("al-refresh").onclick = () => loadAlerts();
    $("al-reset").onclick = () => fitToSelection();
    wireCanvas();
    S.inited = true;
  }

  function hide() { S.shown = false; }

  async function show() {
    S.shown = true;
    if (!S.inited) {
      const prefer = $("alert-root");
      if (prefer) mount(prefer);
      else {
        const root = document.createElement("div"); root.id = "al-root-wrap";
        ($("alertp") || document.body).appendChild(root); mount(root);
      }
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
    else fitToSelection();
    clearInterval(S.timer);
    S.timer = setInterval(() => { if (S.shown && !document.hidden) loadAlerts(); }, REFRESH_MS);
  }

  function titleText() { return S.selectedType || "All Alerts"; }

  return {
    show, hide, redraw: req, drawNow: draw, load: loadAlerts,
    fitToSelection, titleText, eventTypes,
    _state: S
  };
})();
window.Alerts = Alerts;
