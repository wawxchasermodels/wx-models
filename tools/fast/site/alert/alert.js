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
  // Backing store is finer than the logical camera so a 250% Studio crop is still near 1 bitmap pixel per frame pixel.
  // Source shorelines are Census 1:500k, not a larger-scale coast. See basemap_wa.json "source".
  const MAP_PX = 4096;
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
    selectedTypes: new Set(), fillAlpha: 1,  // multi-select (t2490u); empty = All
    selectedType: null, // legacy single when exactly one type selected
    status: "", raf: 0, sig: "",
    landFeats: [], waterFeats: [], stateGeom: null, countyGeoms: [], contextGeoms: [], roads: null
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
    if (!S.selectedTypes || !S.selectedTypes.size) return S.alerts;
    return S.alerts.filter((a) => S.selectedTypes.has((a.properties && a.properties.event) || ""));
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

  // Match posted alert maps (alert_style MAIN cities + coastal) — t2491u/t2493u
  const MAIN_TOWNS = new Set([
    "Seattle", "Tacoma", "Spokane", "Olympia", "Everett", "Bellingham", "Vancouver",
    "Yakima", "Tri-Cities", "Wenatchee", "Walla Walla", "Aberdeen", "Longview",
    "Mount Vernon", "Ellensburg", "Port Angeles", "Bellevue", "Kent", "Renton",
    "Kennewick", "Richland", "Pasco", "Bremerton", "Pullman"
  ]);
  const COASTAL_TOWNS = new Set([
    "Aberdeen", "Hoquiam", "Westport", "Ocean Shores", "Long Beach", "Ilwaco",
    "Forks", "Neah Bay", "La Push", "Port Angeles", "Sequim", "Port Townsend",
    "Anacortes", "Friday Harbor", "Oak Harbor", "Blaine", "Birch Bay", "Raymond",
    "South Bend", "Tokeland", "Pacific Beach", "Moclips", "Copalis Beach",
    "Quinault", "Amanda Park", "Kalaloch", "Ozette"
  ]);
  function townPriority(t) {
    if (MAIN_TOWNS.has(t.n)) return 0;
    if (COASTAL_TOWNS.has(t.n)) return 1; // ahead of other notables so the coast is not crowded out (t2491u/t2493u)
    if (t.notable) return 2;
    return 3 + (t.tier || 0);
  }

  function townBudget(zoom) {
    // Frame zoom (Studio crop), not Alerts._state.k. Overview keeps the approved main + coastal density (t2491u/t2493u).
    // Past that, every town inside this frame is a candidate — offscreen towns never take a slot (t2499u).
    const z = Math.max(1, +zoom || 1);
    if (z < 1.25) return { maxTier: 2, n: 48 };
    if (z < 1.7) return { maxTier: 3, n: Infinity };
    if (z < 2.2) return { maxTier: 4, n: Infinity };
    return { maxTier: 4, n: Infinity };
  }
  // Zoom-1 label size on a 1920-long Studio frame (12 CSS px on the 1600 map). Does not grow with zoom (t2499u).
  function townFrameStyle(frameMax) {
    const u = (frameMax > 0 ? frameMax : 1920) / CSS;
    return { u, fs: 12 * u, gap: 8 * u, pad: 4 * u, dotR: 3.2 * u, halo: 3.5 * u, dotStroke: 1.5 * u };
  }
  function townOverlaps(a, b) {
    return !(a[2] < b[0] || a[0] > b[2] || a[3] < b[1] || a[1] > b[3]);
  }

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
    if (S.contextGeoms && S.contextGeoms.length) {
      ctx.beginPath();
      for (const g of S.contextGeoms) pathGeom(g, ctx);
      ctx.fillStyle = C_LAND; ctx.fill("evenodd");
    }
    if (S.stateGeom) {
      ctx.beginPath(); pathGeoJSON(S.stateGeom, ctx);
      ctx.fillStyle = C_LAND; ctx.fill("evenodd");
    } else {
      ctx.beginPath();
      for (const f of S.landFeats) if (f.geometry) pathGeom(f.geometry, ctx);
      ctx.fillStyle = C_LAND; ctx.fill("evenodd");
    }
    // County lines and state outlines are stroked in frame pixels (paintFrameEdges) so zoom does not blur them.
  }

  // Towns are laid out in final frame pixels (t2499u). The shared alert bitmap has no labels, so each
  // frame's own zoom/pan keeps labels the same size and only spends the budget on towns inside that frame.
  function layoutTowns(project, W, H, zoom, measure) {
    const budget = townBudget(zoom);
    const style = townFrameStyle(Math.max(W, H));
    const fs = style.fs, gap = style.gap, pad = style.pad;
    const vis = visibleAlerts();
    const geoms = vis.map((a) => a._geom).filter(Boolean);
    const edge = style.dotR + style.dotStroke;
    const inView = (x, y) => x >= edge && y >= edge && x <= W - edge && y <= H - edge;
    const cand = [];
    let offscreen = 0;
    for (const t of S.towns) {
      const force = MAIN_TOWNS.has(t.n) || COASTAL_TOWNS.has(t.n) || t.notable;
      if (!force && (t.tier || 0) > budget.maxTier) continue;
      const [sx, sy] = project(t.lon, t.lat);
      if (!inView(sx, sy)) { offscreen++; continue; }
      const hit = geoms.length ? geoms.some((g) => pointInGeom(t.lon, t.lat, g)) : false;
      cand.push({ t, hit, pri: townPriority(t), pop: t.pop || 0, sx, sy });
    }
    cand.sort((a, b) => (a.pri - b.pri) || (b.pop - a.pop) || ((b.hit ? 1 : 0) - (a.hit ? 1 : 0)));
    const placed = [], items = [], seen = new Set();
    const hitsAny = (b) => placed.some((p) => townOverlaps(b, p));
    let attempts = 0;
    for (const row of cand) {
      if (attempts >= budget.n) break;
      if (seen.has(row.t.n)) continue;
      seen.add(row.t.n);
      attempts++;
      const t = row.t, sx = row.sx, sy = row.sy;
      const tw = measure(t.n, fs);
      const side = t.side || SIDE_PREF[t.n] || "right";
      const dotBox = [sx - edge, sy - edge, sx + edge, sy + edge];
      const dotFree = !hitsAny(dotBox);
      const anchors = (side === "left"
        ? [[sx - gap - tw, sy], [sx + gap, sy], [sx - tw / 2, sy - gap - fs], [sx - tw / 2, sy + gap + fs]]
        : [[sx + gap, sy], [sx - gap - tw, sy], [sx - tw / 2, sy - gap - fs], [sx - tw / 2, sy + gap + fs]]
      ).map(([tx, ty]) => ({ tx, ty, b: [tx - pad, ty - fs / 2 - pad, tx + tw + pad, ty + fs / 2 + pad] }));
      let spot = null;
      if (dotFree) {
        for (const a of anchors) {
          const b = a.b;
          if (b[0] < 2 || b[1] < 2 || b[2] > W - 2 || b[3] > H - 2) continue;
          if (townOverlaps(b, dotBox) || hitsAny(b)) continue;
          spot = a; break;
        }
      }
      if (spot) {
        placed.push(dotBox, spot.b);
        items.push({ n: t.n, sx, sy, tx: spot.tx, ty: spot.ty, tw, label: true, b: spot.b, dotBox, tier: t.tier || 0, pri: row.pri });
      } else if (dotFree) {
        // Label lost the collision. Keep the dot so a later label cannot cover this town (t2499u).
        placed.push(dotBox);
        items.push({ n: t.n, sx, sy, tx: sx, ty: sy, tw, label: false, b: null, dotBox, tier: t.tier || 0, pri: row.pri });
      }
    }
    return { style, items, inView: cand.length, attempts, offscreen, labeled: items.filter((it) => it.label).length, dotted: items.length };
  }
  function paintTownItems(ctx, laid) {
    if (!ctx || !laid) return;
    const { fs, dotR, halo, dotStroke } = laid.style;
    ctx.save();
    ctx.font = `700 ${fs}px Montserrat, system-ui, sans-serif`;
    ctx.textAlign = "left";
    ctx.textBaseline = "middle";
    for (const it of laid.items) {
      ctx.beginPath();
      ctx.arc(it.sx, it.sy, dotR, 0, Math.PI * 2);
      ctx.fillStyle = "#fff"; ctx.fill();
      ctx.lineWidth = dotStroke; ctx.strokeStyle = "rgba(0,0,0,0.75)"; ctx.stroke();
      if (!it.label) continue;
      ctx.lineWidth = halo; ctx.strokeStyle = "rgba(12,16,24,0.9)";
      ctx.fillStyle = "#f2f5fa";
      ctx.strokeText(it.n, it.tx, it.ty);
      ctx.fillText(it.n, it.tx, it.ty);
    }
    ctx.restore();
  }
  function paintFrameTowns(ctx, cam) {
    if (!cam || !S.towns.length) return null;
    const dpr = cam.dpr || S.dpr || 1;
    const project = (lon, lat) => {
      const [sx, sy] = llToXY(lon, lat);
      return [cam.W / 2 + (sx * dpr - cam.cx) * cam.kk, cam.H / 2 + (sy * dpr - cam.cy) * cam.kk];
    };
    const measure = (name, fs) => {
      if (ctx && ctx.measureText) {
        ctx.font = `700 ${fs}px Montserrat, system-ui, sans-serif`;
        return ctx.measureText(name).width;
      }
      return fs * 0.56 * String(name).length;
    };
    const laid = layoutTowns(project, cam.W, cam.H, cam.zoom || 1, measure);
    paintTownItems(ctx, laid);
    return laid;
  }

  function draw() {
    const c = $("al-canvas"); if (!c) return;
    const ctx = c.getContext("2d");
    const dpr = MAP_PX / CSS; S.dpr = dpr;
    if (c.width !== MAP_PX || c.height !== MAP_PX) { c.width = MAP_PX; c.height = MAP_PX; }
    // ONE transform: basemap geometry shares CSS pixel space. Town labels are drawn in frame pixels.
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
    }
    // Town labels are painted per Studio frame (paintFrameTowns), not baked into this bitmap (t2499u).
    S.viewLL = approxViewLL();
    S.sig = [S.loaded, (S.selectedTypes && S.selectedTypes.size ? [...S.selectedTypes].sort().join(',') : 'ALL'), S.fillAlpha.toFixed(2), S.k.toFixed(3), S.scale.toFixed(1),
      S.cx.toFixed(5), S.cy.toFixed(5), S.viewLL.lon0.toFixed(3), S.viewLL.lat0.toFixed(3), vis.length, S.towns.length, (S.roads || []).length, (S.contextGeoms || []).length, dpr].join("|");
  }
  function req() { if (S.raf) return; S.raf = requestAnimationFrame(() => { S.raf = 0; draw(); }); }

  function renderChips() {
    const box = $("al-chips"); if (!box) return;
    if (!S.selectedTypes) S.selectedTypes = new Set();
    const types = eventTypes();
    const allOn = S.selectedTypes.size === 0;
    const mk = (label, type, color, n) => {
      const b = document.createElement("button");
      b.type = "button"; b.className = "al-chip";
      const on = type === null ? allOn : S.selectedTypes.has(type);
      b.setAttribute("aria-pressed", on ? "true" : "false");
      b.innerHTML = `<span class="sw" style="background:${color || '#7cb7ff'}"></span><span>${label}${n != null ? " · " + n : ""}</span>`;
      b.onclick = () => {
        // t2490u: multi-toggle; All clears the set. Tapping a type adds/removes; last type off → All.
        if (type === null) { S.selectedTypes.clear(); }
        else {
          if (S.selectedTypes.has(type)) S.selectedTypes.delete(type);
          else S.selectedTypes.add(type);
        }
        S.selectedType = S.selectedTypes.size === 1 ? [...S.selectedTypes][0] : null;
        renderChips(); req();
      };
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
      // Existing coverage: WA land alerts plus PZZ marine, with the box reaching the OR/ID border. Do not tighten this (t2504u).
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
        S.contextGeoms = bm.context || [];
      } catch (e) { /* optional */ }
    }
    if (!S.towns.length) {
      try {
        const t = await loadJSON("alert/towns_wa.json");
        S.towns = (t.places || []).slice().sort((a, b) => townPriority(a) - townPriority(b) || (b.pop || 0) - (a.pop || 0) || (a.tier - b.tier));
      } catch (e) { S.towns = []; }
    }
    if (!S.roads) {
      try { S.roads = (await loadJSON("alert/roads_wa.json")).roads || []; }
      catch (e) { S.roads = []; }
    }
    req();
    if (!S.loaded || Date.now() - S.loaded > REFRESH_MS) loadAlerts();
    else fitToSelection();
    clearInterval(S.timer);
    S.timer = setInterval(() => { if (S.shown && !document.hidden) loadAlerts(); }, REFRESH_MS);
  }


  function alertId(a) {
    const p = a && a.properties;
    return (a && a.id) || (p && (p.id || p["@id"])) || "";
  }
  function hitAt(lon, lat) {
    const hits = [];
    for (const a of alertsAt(lon, lat)) {
      const ev = (a.properties && a.properties.event) || "Alert";
      if (!hits.includes(ev)) hits.push(ev);
    }
    return hits;
  }
  /** Topmost drawn alert first. Only alerts the chips currently show. */
  function alertsAt(lon, lat) {
    const vis = visibleAlerts();
    const hits = [];
    for (let i = vis.length - 1; i >= 0; i--) {
      const a = vis[i], g = a._geom; if (!g) continue;
      if (pointInGeom(lon, lat, g)) hits.push(a);
    }
    return hits;
  }
  function propText(p, k) {
    const v = p && p[k];
    return v == null ? "" : String(v);
  }
  function fmtWhen(iso) {
    if (!iso) return "";
    const t = new Date(iso);
    if (isNaN(t.getTime())) return String(iso);
    try {
      return new Intl.DateTimeFormat("en-US", { timeZone: "America/Los_Angeles", weekday: "short", month: "short", day: "numeric", hour: "numeric", minute: "2-digit" }).format(t) + " PT";
    } catch (e) { return String(iso); }
  }
  function readoutModel(alert, note) {
    const p = (alert && alert.properties) || {};
    const description = propText(p, "description").trim();
    const instruction = propText(p, "instruction").trim();
    const headline = propText(p, "headline").trim();
    const times = [["Effective", propText(p, "effective")], ["Onset", propText(p, "onset")], ["Ends", propText(p, "ends")], ["Expires", propText(p, "expires")], ["Sent", propText(p, "sent")]].filter((x) => x[1]);
    return {
      id: alertId(alert),
      event: propText(p, "event") || "Alert",
      headline, description, instruction,
      area: propText(p, "areaDesc").trim(),
      severity: propText(p, "severity"),
      urgency: propText(p, "urgency"),
      certainty: propText(p, "certainty"),
      sender: propText(p, "senderName"),
      web: propText(p, "web"),
      times: times.map(([k, v]) => [k, fmtWhen(v)]),
      missing: !description && !instruction && !headline,
      note: note || ""
    };
  }
  const READ_MISS = "NWS did not include the full text for this alert.";
  const READ_STALE = "Could not refresh from NWS. Showing the copy already loaded.";
  const READ_GONE = "NWS no longer lists this alert. Showing the last copy loaded.";
  let readGen = 0, readStack = [], readIndex = 0;
  function ensureReadout() {
    let el = document.getElementById("alread");
    if (el) return el;
    el = document.createElement("div");
    el.id = "alread"; el.hidden = true; el.setAttribute("role", "dialog"); el.setAttribute("aria-label", "NWS alert text");
    document.body.appendChild(el);
    el.addEventListener("click", (e) => {
      const b = e.target.closest("button"); if (!b) return;
      if (b.dataset.act === "close") dismissReadout();
      else if (b.dataset.act === "next") { showReadout(readIndex + 1); refreshReadout(readStack[readIndex], readGen); }
      else if (b.dataset.act === "back") { showReadout(readIndex - 1); refreshReadout(readStack[readIndex], readGen); }
    });
    document.addEventListener("keydown", (e) => { if (e.key === "Escape" && el && !el.hidden) { dismissReadout(); e.preventDefault(); } });
    return el;
  }
  function addLine(parent, tag, text, cls) {
    const n = document.createElement(tag);
    if (cls) n.className = cls;
    n.textContent = text;
    parent.appendChild(n);
    return n;
  }
  function paintReadout(model, n, total) {
    const el = ensureReadout();
    el.innerHTML = "";
    const head = document.createElement("div"); head.className = "alr-h";
    addLine(head, "b", model.event || "Alert", "alr-ev");
    const tools = document.createElement("span"); tools.className = "alr-tools";
    if (total > 1) {
      const back = document.createElement("button"); back.type = "button"; back.dataset.act = "back"; back.textContent = "Back"; back.disabled = readIndex <= 0;
      const lab = document.createElement("span"); lab.textContent = (readIndex + 1) + " of " + total;
      const next = document.createElement("button"); next.type = "button"; next.dataset.act = "next"; next.textContent = "Next"; next.disabled = readIndex >= total - 1;
      tools.append(back, lab, next);
    }
    const close = document.createElement("button"); close.type = "button"; close.dataset.act = "close"; close.textContent = "Close";
    tools.appendChild(close); head.appendChild(tools); el.appendChild(head);
    if (model.note) addLine(el, "p", model.note, "alr-note");
    if (model.missing) addLine(el, "p", READ_MISS, "alr-note");
    if (model.headline) addLine(el, "p", model.headline, "alr-hd");
    const meta = [model.area, [model.severity, model.urgency, model.certainty].filter(Boolean).join(" · "), model.sender].filter(Boolean);
    meta.forEach((t) => addLine(el, "p", t, "alr-meta"));
    model.times.forEach(([k, v]) => addLine(el, "p", k + ": " + v, "alr-meta"));
    if (model.description) addLine(el, "p", model.description, "alr-body");
    if (model.instruction) addLine(el, "p", model.instruction, "alr-body");
    if (model.web) addLine(el, "p", model.web, "alr-web");
    addLine(el, "p", "Text: National Weather Service", "alr-src");
    el.hidden = false;
    const c = el.querySelector("button[data-act=close]"); if (c) c.focus();
  }
  function showReadout(i) {
    if (!readStack.length) return dismissReadout();
    readIndex = Math.max(0, Math.min(readStack.length - 1, i));
    paintReadout(readoutModel(readStack[readIndex], readStack[readIndex]._note || ""), readStack.length, readStack.length);
  }
  function dismissReadout() {
    readGen++; readStack = []; readIndex = 0;
    const el = document.getElementById("alread"); if (el) { el.hidden = true; el.innerHTML = ""; }
  }
  async function refreshReadout(alert, gen) {
    const id = alertId(alert);
    const url = /^https?:/i.test(id) ? id : "";
    if (!url) return;
    let note = "", gone = false, fresh = null;
    try {
      const ctrl = new AbortController();
      const timer = setTimeout(() => ctrl.abort(), 4500);
      const r = await fetch(url, { headers: { Accept: "application/geo+json, application/json", "User-Agent": UA }, signal: ctrl.signal });
      clearTimeout(timer);
      if (r.status === 404) gone = true;
      else if (!r.ok) note = READ_STALE;
      else fresh = await r.json();
    } catch (e) { note = READ_STALE; }
    if (gen !== readGen) return;
    const slot = readStack[readIndex];
    if (!slot || alertId(slot) !== id) return;
    if (fresh && fresh.properties) {
      fresh._geom = slot._geom;
      readStack[readIndex] = fresh;
      fresh._note = "";
    } else if (gone) slot._note = READ_GONE;
    else if (note) slot._note = note;
    showReadout(readIndex);
  }
  function openAt(lon, lat) {
    const hits = alertsAt(lon, lat);
    if (!hits.length) { dismissReadout(); return []; }
    readGen++; readStack = hits; readIndex = 0;
    showReadout(0);
    refreshReadout(hits[0], readGen);
    return hits.map(alertId);
  }
  function isMapClick(dx, dy) { return Math.hypot(dx, dy) < 8; }
  /** Bitmap CSS-px (alert canvas space) → lon/lat. */
  function cssToLonLat(sx, sy) {
    const [mx, my] = screenToMerc(sx, sy);
    return mercToLonLat(mx, my);
  }

  function frameProject(cam) {
    const dpr = cam.dpr || S.dpr || 1;
    return (lon, lat) => {
      const [sx, sy] = llToXY(lon, lat);
      return [cam.W / 2 + (sx * dpr - cam.cx) * cam.kk, cam.H / 2 + (sy * dpr - cam.cy) * cam.kk];
    };
  }
  function allRings(g, out) {
    if (!g) return;
    const t = g.type;
    if (t === "Polygon") (g.coordinates || []).forEach((r) => out.push(r));
    else if (t === "MultiPolygon") (g.coordinates || []).forEach((p) => (p || []).forEach((r) => out.push(r)));
    else if (t === "GeometryCollection") (g.geometries || []).forEach((gg) => allRings(gg, out));
    else if (t === "Feature") allRings(g.geometry, out);
    else if (t === "FeatureCollection") (g.features || []).forEach((f) => allRings(f.geometry, out));
  }
  function strokeProjected(ctx, geom, project) {
    const rings = []; allRings(geom, rings);
    for (const ring of rings) {
      if (!ring || ring.length < 2) continue;
      ctx.beginPath();
      for (let i = 0; i < ring.length; i++) {
        const [x, y] = project(ring[i][0], ring[i][1]);
        if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
      }
      ctx.closePath(); ctx.stroke();
    }
  }
  function paintFrameEdges(ctx, cam) {
    if (!ctx || !cam) return;
    const project = frameProject(cam);
    ctx.save();
    ctx.lineJoin = "round"; ctx.lineCap = "round";
    if (S.countyGeoms && S.countyGeoms.length) {
      ctx.lineWidth = 1.25; ctx.strokeStyle = C_COUNTY;
      for (const g of S.countyGeoms) strokeProjected(ctx, g, project);
    }
    if (S.contextGeoms && S.contextGeoms.length) {
      ctx.lineWidth = 1.5; ctx.strokeStyle = "rgba(170,186,206,0.55)";
      for (const g of S.contextGeoms) strokeProjected(ctx, g, project);
    }
    if (S.stateGeom) {
      ctx.lineWidth = 2.6; ctx.strokeStyle = C_STATE;
      strokeProjected(ctx, S.stateGeom, project);
    }
    ctx.lineWidth = 2.6;
    for (const a of visibleAlerts()) {
      if (!a._geom) continue;
      ctx.strokeStyle = hexToRgba(colorFor(a.properties && a.properties.event), 1);
      strokeProjected(ctx, a._geom, project);
    }
    ctx.restore();
  }
  function roadsForZoom(zoom) {
    const z = Math.max(1, +zoom || 1), list = S.roads || [];
    return list.filter((r) => {
      if (r.cls === "interstate") return true;
      if (r.cls === "us") return z >= 1.2 || (r.rank || 9) <= 6;
      return z >= 1.75;
    });
  }
  function layoutRoads(cam, towns, measure) {
    const project = frameProject(cam);
    const roads = roadsForZoom(cam.zoom);
    const blocks = [];
    if (towns && towns.items) for (const it of towns.items) { blocks.push(it.dotBox); if (it.b) blocks.push(it.b); }
    const hit = (b) => blocks.some((p) => townOverlaps(b, p));
    const shields = [];
    const lines = [];
    for (const r of roads) lines.push({ r, xy: r.pts.map(([lon, lat]) => project(lon, lat)) });
    for (const cls of ["interstate", "us", "state"]) for (const d of lines) if (d.r.cls === cls) {
      const inside = d.xy.filter(([x, y]) => x >= 8 && y >= 8 && x <= cam.W - 8 && y <= cam.H - 8);
      if (inside.length < 2) continue;
      const label = d.r.ref;
      const tw = measure ? measure(label) : 13 * 0.62 * String(label).length;
      const w = Math.max(22, tw + 10), h = 18;
      const spots = [0.5, 0.32, 0.68].map((t) => inside[Math.min(inside.length - 1, Math.round((inside.length - 1) * t))]);
      for (const [x, y] of spots) {
        const b = [x - w / 2 - 2, y - h / 2 - 2, x + w / 2 + 2, y + h / 2 + 2];
        if (b[0] < 2 || b[1] < 2 || b[2] > cam.W - 2 || b[3] > cam.H - 2) continue;
        if (hit(b) || shields.some((s) => townOverlaps(b, s.b))) continue;
        const sh = { x, y, b, label, cls };
        shields.push(sh); blocks.push(b); break;
      }
    }
    return { lines, shields, shown: roads.length };
  }
  function paintFrameRoads(ctx, cam, towns) {
    if (!ctx || !cam) return null;
    const measure = (label) => { ctx.font = "700 13px Montserrat, system-ui, sans-serif"; return ctx.measureText ? ctx.measureText(label).width : 13 * 0.62 * label.length; };
    const laid = layoutRoads(cam, towns, measure);
    ctx.save();
    ctx.lineJoin = "round"; ctx.lineCap = "round";
    for (const d of laid.lines) {
      ctx.beginPath();
      let on = false;
      for (const [x, y] of d.xy) {
        const vis = x >= -80 && y >= -80 && x <= cam.W + 80 && y <= cam.H + 80;
        if (!vis) { on = false; continue; }
        if (!on) ctx.moveTo(x, y); else ctx.lineTo(x, y);
        on = true;
      }
      ctx.lineWidth = d.r.cls === "interstate" ? 3.2 : d.r.cls === "us" ? 2.2 : 1.5;
      ctx.strokeStyle = d.r.cls === "interstate" ? "rgba(214,224,238,0.92)" : "rgba(168,184,204,0.8)";
      ctx.stroke();
    }
    ctx.font = "700 13px Montserrat, system-ui, sans-serif";
    ctx.textAlign = "center"; ctx.textBaseline = "middle";
    for (const s of laid.shields) {
      const w = s.b[2] - s.b[0] - 4, h = s.b[3] - s.b[1] - 4;
      ctx.beginPath();
      ctx.fillStyle = s.cls === "interstate" ? "#1c3e78" : "#f3f0e8";
      ctx.strokeStyle = s.cls === "interstate" ? "#e8eef8" : "#1c2430";
      ctx.lineWidth = 1.25;
      if (ctx.roundRect) ctx.roundRect(s.x - w / 2, s.y - h / 2, w, h, 4);
      else ctx.rect(s.x - w / 2, s.y - h / 2, w, h);
      ctx.fill(); ctx.stroke();
      ctx.fillStyle = s.cls === "interstate" ? "#f4f7fb" : "#1c2430";
      ctx.fillText(s.label, s.x, s.y + 0.5);
    }
    ctx.restore();
    return laid;
  }
  function paintFrameScene(ctx, cam) {
    paintFrameEdges(ctx, cam);
    const project = frameProject(cam);
    const measure = (name, fs) => {
      if (ctx && ctx.measureText) { ctx.font = `700 ${fs}px Montserrat, system-ui, sans-serif`; return ctx.measureText(name).width; }
      return fs * 0.56 * String(name).length;
    };
    const towns = S.towns.length ? layoutTowns(project, cam.W, cam.H, cam.zoom || 1, measure) : { items: [], style: townFrameStyle(Math.max(cam.W, cam.H)), labeled: 0 };
    const roads = paintFrameRoads(ctx, cam, towns);
    paintTownItems(ctx, towns);
    return { towns, roads };
  }

  function titleText() {
    if (!S.selectedTypes || !S.selectedTypes.size) return "All Alerts";
    if (S.selectedTypes.size === 1) return [...S.selectedTypes][0];
    return [...S.selectedTypes].sort().join(" · ");
  }

  return {
    show, hide, redraw: req, drawNow: draw, load: loadAlerts,
    fitToSelection, titleText, eventTypes, coverSafe, mercXY, llToXY, approxViewLL, hitAt, cssToLonLat,
    layoutTowns, paintFrameTowns, paintFrameScene, paintFrameEdges, paintFrameRoads, layoutRoads, roadsForZoom, townFrameStyle, townBudget,
    alertsAt, readoutModel, openAt, dismissReadout, isMapClick, frameProject, mapPixels: () => MAP_PX,
    setFillAlpha: (a) => { S.fillAlpha = Math.max(0.2, Math.min(1, +a || 1)); const op=$("al-opacity"), opv=$("al-opacity-val"); if (op) op.value=String(Math.round(S.fillAlpha*100)); if (opv) opv.textContent=Math.round(S.fillAlpha*100)+"%"; req(); },
    _state: S
  };
})();
window.Alerts = Alerts;
