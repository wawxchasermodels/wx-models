/* Active Alerts map for Studio (WA land + PZZ marine). Preview 2026-11-05.
   Dark basemap, auto-fit, single shared equirect projection (dpr-safe). */
"use strict";
const Alerts = (() => {
  const AREAS = ["WA"];
  const REFRESH_MS = 5 * 60 * 1000;
  const UA = "WAWeatherChasersStudio/1.0 (alerts; benjamin@wawxchasers)";
  const NWS = "https://api.weather.gov/alerts/active?area=" + AREAS.join(",");
  const FALLBACK = "#888888";
  const C_OCEAN = "#030912";
  const C_WATER = "#153a58";
  const C_LAND = "#1a222e";
  const C_COUNTY = "rgba(170,185,205,0.55)";
  const C_STATE = "rgba(200,215,235,0.9)";
  const WA0 = { lon0: -125.15, lon1: -116.7, lat0: 45.4, lat1: 49.1 };
  const CSS = 1600;
  const SIDE_PREF = { "Oak Harbor": "left" };
  const RIGHT_CLEAR = 0.13;
  const PAD = 0.12;

  const S = {
    shown: false, inited: false, loaded: 0, timer: null, dpr: 1,
    cx: CSS / 2, cy: CSS / 2, k: 1, view: "wa",
    viewLL: Object.assign({}, WA0),
    colors: {}, zones: new Map(), towns: [], alerts: [],
    selectedType: null, fillAlpha: 1, status: "", raf: 0, sig: "",
    landFeats: [], waterFeats: [], stateGeom: null, countyGeoms: []
  };
  const $ = (id) => document.getElementById(id);
  const status = (t) => { S.status = t; const el = $("al-status"); if (el) el.textContent = t; };

  function hexToRgba(hex, a) {
    const h = String(hex || FALLBACK).replace("#", "");
    const n = parseInt(h.length === 3 ? h.split("").map((c) => c + c).join("") : h, 16);
    return `rgba(${(n >> 16) & 255},${(n >> 8) & 255},${n & 255},${a})`;
  }

  // Shared equirect: lon/lat -> world (canvas CSS px at identity)
  function llToXY(lon, lat) {
    const { lon0, lon1, lat0, lat1 } = S.viewLL;
    return [((lon - lon0) / (lon1 - lon0)) * CSS, ((lat1 - lat) / (lat1 - lat0)) * CSS];
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
      if (((yi > y) !== (yj > y)) && (x < (xj - xi) * (y - yi) / ((yj - yi) || 1e-12) + xi)) inside = !inside;
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
        if (!isFinite(p[0]) || !isFinite(p[1])) continue;
        if (p[0] < lo) lo = p[0]; if (p[0] > hi) hi = p[0];
        if (p[1] < la0) la0 = p[1]; if (p[1] > la1) la1 = p[1];
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

  /** Fit view so selected alerts fill the frame under Studio COVER crop, left-biased for 13% right clear. */
  function fitToSelection() {
    const vis = visibleAlerts();
    let b = null;
    for (const a of vis) b = mergeBounds(b, geomBounds(a._geom));
    if (!b) b = Object.assign({}, WA0);
    const dlon = Math.max(0.12, (b.lon1 - b.lon0) * PAD);
    const dlat = Math.max(0.08, (b.lat1 - b.lat0) * PAD);
    let lon0 = b.lon0 - dlon, lon1 = b.lon1 + dlon, lat0 = b.lat0 - dlat, lat1 = b.lat1 + dlat;
    // Clamp into WA theater so strays can't explode the view
    const MAX = { lon0: -126.5, lon1: -116.5, lat0: 45.4, lat1: 49.15 };
    lon0 = Math.max(lon0, MAX.lon0); lon1 = Math.min(lon1, MAX.lon1);
    lat0 = Math.max(lat0, MAX.lat0); lat1 = Math.min(lat1, MAX.lat1);
    if (lon1 <= lon0 || lat1 <= lat0) { lon0 = MAX.lon0; lon1 = MAX.lon1; lat0 = MAX.lat0; lat1 = MAX.lat1; }

    const usable = 1 - RIGHT_CLEAR; // content in left 87%
    // Soft-cap far-west marine so All/Gale don't leave a dark ocean "bar" on the left
    const frameLon0 = Math.max(lon0, -125.55);
    // Extra north pad so San Juans / Northern Inland Waters survive 16:9 cover crop
    // (cover of square into 16:9 crops ~22% top+bottom of the canvas)
    const COVER_SAFE = 0.56; // vertical fraction of square visible after 16:9 cover
    const midLon = (frameLon0 + lon1) / 2;
    let contentW = Math.max(0.35, lon1 - frameLon0), contentH = Math.max(0.25, lat1 - lat0);
    // Grow contentH so padded alerts fit inside the cover-safe band
    contentH = Math.max(contentH, contentH / COVER_SAFE * 0.92);
    let spanX = contentW / Math.max(0.55, usable * 0.92);
    let spanY = contentH / COVER_SAFE;
    const midLat = (lat0 + lat1) / 2;
    const latMid = midLat * Math.PI / 180;
    const lonUnit = Math.cos(latMid);
    if (spanX * lonUnit > spanY) spanY = spanX * lonUnit;
    else spanX = spanY / Math.max(lonUnit, 0.25);
    spanX = Math.min(Math.max(spanX, 0.8), MAX.lon1 - MAX.lon0);
    spanY = Math.min(Math.max(spanY, 0.5), MAX.lat1 - MAX.lat0);
    // Bias midLat slightly south of geometric center so north edge clears the crop
    const biasLat = midLat - Math.min(0.12, contentH * 0.04);
    const midFracX = usable * 0.48;
    let v0 = midLon - midFracX * spanX, v1 = v0 + spanX;
    if (v0 < frameLon0 - contentW * 0.2) { const shift = (frameLon0 - contentW * 0.2) - v0; v0 += shift; v1 += shift; }
    let vLat0 = biasLat - spanY / 2, vLat1 = biasLat + spanY / 2;
    // Guarantee alert lat1 (north) sits below the cropped top band
    const northNeed = lat1 + Math.max(0.05, (lat1 - lat0) * 0.08);
    if (vLat1 < northNeed) { const d = northNeed - vLat1; vLat0 += d; vLat1 += d; }
    if (vLat1 > MAX.lat1) { const d = vLat1 - MAX.lat1; vLat0 -= d; vLat1 -= d; }
    if (vLat0 < MAX.lat0) vLat0 = MAX.lat0;
    S.viewLL = { lon0: v0, lon1: v1, lat0: vLat0, lat1: vLat1 };
    S.k = 1; S.cx = CSS / 2; S.cy = CSS / 2;
    req();
  }

  function townBudget() {
    if (S.k < 1.15) return { maxTier: 0, n: 20 };
    if (S.k < 1.6) return { maxTier: 1, n: 32 };
    if (S.k < 2.2) return { maxTier: 2, n: 45 };
    if (S.k < 3.2) return { maxTier: 3, n: 60 };
    return { maxTier: 4, n: 85 };
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
    take(outside, Math.min(budget.n, out.length + Math.max(6, Math.floor(budget.n * 0.3))));
    return out;
  }

  // All drawing in CSS pixel space; caller sets ctx transform to dpr.
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
  function pathGeoJSON(gj, ctx) {
    if (!gj) return;
    if (gj.type === "Feature") return pathGeom(gj.geometry, ctx);
    if (gj.type === "FeatureCollection") return (gj.features || []).forEach((f) => pathGeom(f.geometry, ctx));
    return pathGeom(gj, ctx);
  }
  /** Collect exterior rings (Polygon / MultiPolygon / Feature*). */
  function exteriorRings(g, out) {
    if (!g) return;
    const t = g.type;
    if (t === "Polygon") out.push(g.coordinates[0]);
    else if (t === "MultiPolygon") g.coordinates.forEach((poly) => out.push(poly[0]));
    else if (t === "GeometryCollection") (g.geometries || []).forEach((gg) => exteriorRings(gg, out));
    else if (t === "Feature") exteriorRings(g.geometry, out);
    else if (t === "FeatureCollection") (g.features || []).forEach((f) => exteriorRings(f.geometry, out));
  }
  function ringArea(ring) {
    let a = 0;
    for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
      a += ring[j][0] * ring[i][1] - ring[i][0] * ring[j][1];
    }
    return Math.abs(a) * 0.5;
  }
  /** Stroke only the mainland exterior (largest ring). Island strokes looked like marine-zone borders. */
  function pathMainlandOutline(g, ctx) {
    const rings = []; exteriorRings(g, rings);
    if (!rings.length) return;
    let best = rings[0], bestA = ringArea(rings[0]);
    for (let i = 1; i < rings.length; i++) {
      const a = ringArea(rings[i]); if (a > bestA) { best = rings[i]; bestA = a; }
    }
    if (!best || !best.length) return;
    const [x0, y0] = llToXY(best[0][0], best[0][1]);
    const [sx0, sy0] = worldToScreen(x0, y0);
    ctx.moveTo(sx0, sy0);
    for (let i = 1; i < best.length; i++) {
      const [x, y] = llToXY(best[i][0], best[i][1]);
      const [sx, sy] = worldToScreen(x, y);
      ctx.lineTo(sx, sy);
    }
    ctx.closePath();
  }

  function drawBasemap(ctx) {
    // Plain ocean — do NOT fill/stroke individual PZZ zones (their edges read as white jagged borders)
    ctx.fillStyle = C_OCEAN;
    ctx.fillRect(0, 0, CSS, CSS);
    // Subtle inland-water tint: one flat wash under land, still no zone strokes
    ctx.fillStyle = C_WATER;
    ctx.globalAlpha = 0.35;
    ctx.fillRect(0, 0, CSS, CSS);
    ctx.globalAlpha = 1;
    // State land fill (islands included via evenodd)
    if (S.stateGeom) {
      ctx.beginPath(); pathGeoJSON(S.stateGeom, ctx);
      ctx.fillStyle = C_LAND; ctx.fill("evenodd");
    } else {
      ctx.beginPath();
      for (const f of S.landFeats) if (f.geometry) pathGeom(f.geometry, ctx);
      ctx.fillStyle = C_LAND; ctx.fill("evenodd");
    }
    // County lines (faint) — keep
    if (S.countyGeoms && S.countyGeoms.length) {
      ctx.beginPath();
      for (const g of S.countyGeoms) pathGeoJSON(g, ctx);
      ctx.lineWidth = 1.25;
      ctx.strokeStyle = C_COUNTY;
      ctx.stroke();
    }
    // Mainland WA outline only (skip island strokes that looked like marine zones)
    if (S.stateGeom) {
      ctx.beginPath(); pathMainlandOutline(S.stateGeom, ctx);
      ctx.lineWidth = 2.2;
      ctx.strokeStyle = C_STATE;
      ctx.stroke();
    }
    // Active alerts alone get colored strokes in draw().
  }

  function drawTowns(ctx) {
    const picks = pickTowns();
    const placed = [];
    const fs = Math.max(11, Math.min(16, 12 * Math.sqrt(S.k)));
    ctx.font = `700 ${fs}px Montserrat, system-ui, sans-serif`;
    ctx.textBaseline = "middle";
    const pad = 4;
    const maxX = CSS * (1 - RIGHT_CLEAR);
    const collides = (b) => placed.some((p) => !(b[2] < p[0] || b[0] > p[2] || b[3] < p[1] || b[1] > p[3]));
    for (const t of picks) {
      const [wx, wy] = llToXY(t.lon, t.lat);
      const [sx, sy] = worldToScreen(wx, wy);
      if (sx < 20 || sy < 20 || sx > maxX - 20 || sy > CSS - 20) continue;
      const tw = ctx.measureText(t.n).width;
      const side = t.side || SIDE_PREF[t.n] || "right";
      const gap = 8;
      const cands = side === "left"
        ? [[sx - gap - tw, sy], [sx + gap, sy], [sx - tw / 2, sy - gap - fs], [sx - tw / 2, sy + gap + fs]]
        : [[sx + gap, sy], [sx - gap - tw, sy], [sx - tw / 2, sy - gap - fs], [sx - tw / 2, sy + gap + fs]];
      let spot = null;
      for (const [tx, ty] of cands) {
        const b = [tx - pad, ty - fs / 2 - pad, tx + tw + pad, ty + fs / 2 + pad];
        if (b[0] < 8 || b[1] < 8 || b[2] > maxX - 8 || b[3] > CSS - 8) continue;
        if (collides(b)) continue;
        spot = { tx, ty, b }; break;
      }
      if (!spot) continue;
      ctx.beginPath();
      ctx.arc(sx, sy, 3.2, 0, Math.PI * 2);
      ctx.fillStyle = "#fff"; ctx.fill();
      ctx.lineWidth = 1.5; ctx.strokeStyle = "rgba(0,0,0,0.75)"; ctx.stroke();
      ctx.lineWidth = 3.5; ctx.strokeStyle = "rgba(12,16,24,0.9)";
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
    // ONE transform: all geometry + towns share CSS pixel space
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    drawBasemap(ctx);
    const vis = visibleAlerts();
    for (const a of vis) {
      const g = a._geom; if (!g) continue;
      const col = colorFor(a.properties.event);
      const aFill = Math.max(0.2, Math.min(1, S.fillAlpha));
      ctx.beginPath(); pathGeom(g, ctx);
      ctx.fillStyle = hexToRgba(col, aFill);
      ctx.fill("evenodd");
      ctx.lineWidth = 2.4;
      ctx.strokeStyle = hexToRgba(col, Math.max(0.85, aFill));
      ctx.stroke();
    }
    drawTowns(ctx);
    S.sig = [S.loaded, S.selectedType || "ALL", S.fillAlpha.toFixed(2), S.k.toFixed(3), S.cx.toFixed(1), S.cy.toFixed(1),
      S.viewLL.lon0.toFixed(3), S.viewLL.lat0.toFixed(3), vis.length, dpr].join("|");
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
          } catch (e) { /* skip */ }
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
      const miss = feats.filter((a) => !a._geom).length;
      status(`${feats.length} active · WA land + marine${miss ? " · " + miss + " without geometry" : ""} · updated ${new Date(S.loaded).toLocaleTimeString("en-US", { timeZone: "America/Los_Angeles" })} PT`);
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
      S.k = Math.min(8, Math.max(0.55, S.k * (e.deltaY < 0 ? 1.12 : 1 / 1.12)));
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
        <label class="al-opacity" title="Alert fill opacity">
          <span class="al-opacity-lab">Opacity</span>
          <input type="range" id="al-opacity" min="20" max="100" step="1" value="100" aria-label="Alert fill opacity" />
          <span class="al-opacity-val" id="al-opacity-val">100%</span>
        </label>
        <button type="button" class="al-btn" id="al-refresh">Refresh</button>
        <button type="button" class="al-btn" id="al-reset">Fit view</button>
        <span class="al-meta" id="al-status">…</span>
      </div>
      <div id="alstage"><canvas id="al-canvas" width="1600" height="1600" aria-label="Active NWS alerts for Washington"></canvas></div>`;
    $("al-refresh").onclick = () => loadAlerts();
    $("al-reset").onclick = () => fitToSelection();
    const op = $("al-opacity"), opv = $("al-opacity-val");
    const syncOp = () => {
      const pct = Math.max(20, Math.min(100, +op.value || 100));
      S.fillAlpha = pct / 100;
      if (opv) opv.textContent = pct + "%";
      req();
      // refresh Studio frame (opacity is on the offscreen canvas that Studio crops)
      if (typeof render === "function") {
        try { const k = document.body.classList.contains("phone") ? "v" : "h"; render(k); } catch (e) {}
      }
    };
    op.addEventListener("input", syncOp);
    op.addEventListener("change", syncOp);
    S.fillAlpha = 1; op.value = "100";
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
    if (!S.stateGeom) {
      try {
        const bm = await loadJSON("alert/basemap_wa.json");
        S.stateGeom = bm.state || null;
        S.countyGeoms = bm.counties || [];
      } catch (e) { /* optional */ }
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
    setFillAlpha: (a) => { S.fillAlpha = Math.max(0.2, Math.min(1, +a || 1)); const op=$("al-opacity"), opv=$("al-opacity-val"); if (op) op.value=String(Math.round(S.fillAlpha*100)); if (opv) opv.textContent=Math.round(S.fillAlpha*100)+"%"; req(); },
    _state: S
  };
})();
window.Alerts = Alerts;
