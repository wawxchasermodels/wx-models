/* Active Alerts map for Studio (WA land + PZZ marine). Preview 2026-11-05.
   Dark basemap, auto-fit, UNIFORM-SCALE Web Mercator (no lon/lat squish). */
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
  const C_COUNTY = "rgba(90,105,125,0.7)";
  const C_STATE = "rgba(200,215,235,0.9)";
  const WA0 = { lon0: -125.15, lon1: -116.7, lat0: 45.4, lat1: 49.1 };
  const CSS = 1600;
  const SIDE_PREF = { "Oak Harbor": "left" };
  const RIGHT_CLEAR = 0.13;
  const PAD = 0.12;
  // Cover of square canvas into frame: visible fraction of the square on the short axis
  // 16:9 (h): crops top/bottom → safe vertical band ~ H/W = 9/16 of width… = 0.5625 of CSS
  // 9:16 (v): crops left/right → safe horizontal band ~ 0.5625 of CSS
  function coverSafe() {
    const phone = typeof document !== "undefined" && document.body && document.body.classList.contains("phone");
    return { horiz: phone ? 0.56 : 1, vert: phone ? 1 : 0.56, phone: !!phone };
  }

  const S = {
    shown: false, inited: false, loaded: 0, timer: null, dpr: 1,
    // Mercator camera: cx/cy in mercator units, scale = CSS px per mercator-unit at k=1
    cx: 0, cy: 0, scale: 1, k: 1, view: "wa",
    viewLL: Object.assign({}, WA0), // diagnostic / legacy readout of approx lonlat window
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

  /** Web Mercator (EPSG:3857-ish) in radians: uniform scale on x and y — no geographic squish. */
  function mercXY(lon, lat) {
    const latc = Math.max(-85.05112878, Math.min(85.05112878, lat));
    const x = lon * Math.PI / 180;
    const y = Math.log(Math.tan(Math.PI / 4 + latc * Math.PI / 360));
    return [x, y];
  }
  function mercToLonLat(mx, my) {
    const lon = mx * 180 / Math.PI;
    const lat = (2 * Math.atan(Math.exp(my)) - Math.PI / 2) * 180 / Math.PI;
    return [lon, lat];
  }
  function scaleNow() { return S.scale * S.k; }
  /** lon/lat → CSS canvas px (identity camera then zoom). ONE uniform scale. */
  function llToXY(lon, lat) {
    const [mx, my] = mercXY(lon, lat);
    const s = scaleNow();
    return [(mx - S.cx) * s + CSS / 2, -(my - S.cy) * s + CSS / 2];
  }
  function worldToScreen(wx, wy) {
    // wx/wy already CSS-world at k=1 relative… kept for callers that pass merc deltas via cx
    return [(wx - S.cx) * S.k + CSS / 2, (wy - S.cy) * S.k + CSS / 2];
  }
  function screenToMerc(sx, sy) {
    const s = scaleNow() || 1;
    return [(sx - CSS / 2) / s + S.cx, -((sy - CSS / 2) / s) + S.cy];
  }
  function screenToWorld(sx, sy) { return screenToMerc(sx, sy); }
  function approxViewLL() {
    const corners = [[0, 0], [CSS, 0], [0, CSS], [CSS, CSS]].map(([x, y]) => mercToLonLat(...screenToMerc(x, y)));
    const lons = corners.map((c) => c[0]), lats = corners.map((c) => c[1]);
    return { lon0: Math.min(...lons), lon1: Math.max(...lons), lat0: Math.min(...lats), lat1: Math.max(...lats) };
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

  /** Fit so selected alerts fill the cover-safe band with UNIFORM mercator scale (crop, never stretch). */
  function fitToSelection() {
    const vis = visibleAlerts();
    let b = null;
    for (const a of vis) b = mergeBounds(b, geomBounds(a._geom));
    if (!b) b = Object.assign({}, WA0);
    const dlon = Math.max(0.12, (b.lon1 - b.lon0) * PAD);
    const dlat = Math.max(0.10, (b.lat1 - b.lat0) * PAD);
    const MAX = { lon0: -126.5, lon1: -116.5, lat0: 45.4, lat1: 49.15 };
    let lon0 = Math.max(b.lon0 - dlon, MAX.lon0), lon1 = Math.min(b.lon1 + dlon, MAX.lon1);
    let lat0 = Math.max(b.lat0 - dlat, MAX.lat0), lat1 = Math.min(b.lat1 + dlat, MAX.lat1);
    // Extra north pad so San Juans / N Inland Waters clear the 16:9 top crop
    lat1 = Math.min(MAX.lat1, lat1 + Math.max(0.15, (lat1 - lat0) * 0.12));
    // Soft-cap far-west marine for framing (still drawn; just don't dominate the fit bbox)
    lon0 = Math.max(lon0, -125.55);

    const [mx0, my0] = mercXY(lon0, lat0);
    const [mx1, my1] = mercXY(lon1, lat1);
    const mWest = Math.min(mx0, mx1), mEast = Math.max(mx0, mx1);
    const mSouth = Math.min(my0, my1), mNorth = Math.max(my0, my1);
    let mW = Math.max(1e-6, mEast - mWest), mH = Math.max(1e-6, mNorth - mSouth);

    const safe = coverSafe();
    const usableW = CSS * (1 - RIGHT_CLEAR) * (safe.horiz < 1 ? safe.horiz : 1);
    // Vertical: keep content inside the cover-visible band of the square
    const usableH = CSS * safe.vert * 0.92;
    // CONTAIN into usable band with one scale (never stretch axes independently)
    let scale = Math.min(usableW / mW, usableH / mH);
    scale = Math.max(scale * 0.92, 1e-6); // small pad inside the band

    const midX = (mWest + mEast) / 2;
    const midY = (mSouth + mNorth) / 2;
    // Place content in left usable band (face-cam clear on the right of the square / 16:9)
    const midFracX = (1 - RIGHT_CLEAR) * 0.48;
    // Screen x of content center = midFracX * CSS
    // (mx - cx) * scale + CSS/2 = midFracX * CSS  => cx = mx - (midFracX*CSS - CSS/2) / scale
    S.scale = scale;
    S.k = 1;
    S.cx = midX - (midFracX * CSS - CSS / 2) / scale;
    // Vertically center in the square (cover crops equal top/bottom on 16:9)
    S.cy = midY;
    S.viewLL = approxViewLL();
    // Ensure north mercator edge of alerts maps below the cropped top band
    const topSafe = (CSS - usableH) / 2 + 8;
    const [, syNorth] = llToXY((lon0 + lon1) / 2, lat1);
    if (syNorth < topSafe) {
      // shift camera north (increase cy) so north content moves down on screen
      const s = scaleNow();
      S.cy += (topSafe - syNorth) / s;
      S.viewLL = approxViewLL();
    }
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
      const [sx0, sy0] = llToXY(ring[0][0], ring[0][1]);
      ctx.moveTo(sx0, sy0);
      for (let i = 1; i < ring.length; i++) {
        const [sx, sy] = llToXY(ring[i][0], ring[i][1]);
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
    const [sx0, sy0] = llToXY(best[0][0], best[0][1]);
    ctx.moveTo(sx0, sy0);
    for (let i = 1; i < best.length; i++) {
      const [sx, sy] = llToXY(best[i][0], best[i][1]);
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
    // County lines (faint, exterior rings only — hole strokes looked like Sound marine borders)
    if (S.countyGeoms && S.countyGeoms.length) {
      ctx.beginPath();
      for (const g of S.countyGeoms) {
        const rings = []; exteriorRings(g, rings);
        for (const ring of rings) {
          if (!ring || !ring.length) continue;
          const [sx0, sy0] = llToXY(ring[0][0], ring[0][1]);
          ctx.moveTo(sx0, sy0);
          for (let i = 1; i < ring.length; i++) {
            const [sx, sy] = llToXY(ring[i][0], ring[i][1]);
            ctx.lineTo(sx, sy);
          }
          ctx.closePath();
        }
      }
      ctx.lineWidth = 1.1;
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
      const [sx, sy] = llToXY(t.lon, t.lat);
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
    S.viewLL = approxViewLL();
    S.sig = [S.loaded, S.selectedType || "ALL", S.fillAlpha.toFixed(2), S.k.toFixed(3), S.scale.toFixed(1),
      S.cx.toFixed(5), S.cy.toFixed(5), S.viewLL.lon0.toFixed(3), S.viewLL.lat0.toFixed(3), vis.length, dpr].join("|");
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
      // pointer CSS-px → mercator via uniform scale
      const s = scaleNow() || 1;
      const dx = (e.clientX - drag.x) / s, dy = (e.clientY - drag.y) / s;
      S.cx = drag.cx - dx; S.cy = drag.cy + dy; // +dy: screen y down, merc y north
      req();
    });
    c.addEventListener("pointerup", () => { drag = null; });
    c.addEventListener("wheel", (e) => {
      e.preventDefault();
      const rect = c.getBoundingClientRect();
      const sx = (e.clientX - rect.left) * (CSS / rect.width);
      const sy = (e.clientY - rect.top) * (CSS / rect.height);
      const [mx, my] = screenToMerc(sx, sy);
      S.k = Math.min(8, Math.max(0.55, S.k * (e.deltaY < 0 ? 1.12 : 1 / 1.12)));
      const [nx, ny] = screenToMerc(sx, sy);
      S.cx += mx - nx; S.cy += my - ny;
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
    fitToSelection, titleText, eventTypes, coverSafe, mercXY, llToXY, approxViewLL,
    setFillAlpha: (a) => { S.fillAlpha = Math.max(0.2, Math.min(1, +a || 1)); const op=$("al-opacity"), opv=$("al-opacity-val"); if (op) op.value=String(Math.round(S.fillAlpha*100)); if (opv) opv.textContent=Math.round(S.fillAlpha*100)+"%"; req(); },
    _state: S
  };
})();
window.Alerts = Alerts;
