/* Radar + GOES-West satellite layers for the Observations map (fast site only, 11-03-26, Benjamin: toggleable, both OFF by default,
   same zoom / pan as the map, loop of recent frames). Loaded after obs.js; plugs in through Obs.hook().
   Data is fetched straight from the browser (all three servers send CORS "*", so saved images and videos stay exportable). No keys,
   no server, nothing stored by us.
     Radar      NOAA/NWS NCEP MRMS quality-controlled base reflectivity mosaic, 1 km, new frame every ~2 min
                WMS https://opengeo.ncep.noaa.gov/geoserver/conus/conus_bref_qcd/ows  (US government work, public domain)
     Satellite  NOAA GOES-West (GOES-18) ABI via NASA GIBS (WMS epsg4326 "best"), 10-min frames, ~35-60 min behind real time
                GOES-West_ABI_Band13_Clean_Infrared (10.3 um "Clean IR") and GOES-West_ABI_GeoColor (CIRA/NOAA GeoColor)
                NASA: "We acknowledge the use of imagery provided by services from NASA's Global Imagery Browse Services (GIBS),
                part of NASA's Earth Science Data and Information System (ESDIS)." (shown in the page credits, downloads and Studio)
                GeoColor: imagery provided by NOAA/NESDIS/STAR; "Please credit CIRA/NOAA".
   Each frame is one lat/lon (plate carree) image of a fixed box; a WebGL pass reprojects it per pixel into the obs map's own
   Lambert projection and the current zoom / pan, then the result is drawn under the coastlines, borders, isobars and stations.
   Two boxes per source: "detail" (Pacific NW, used when zoomed in) and "wide" (West + western Canada view).
   11-03 (t2224u, t2238u) Mid-level water vapor (GOES-West ABI band 9, 6.9 um) straight from NOAA: NOAA/NESDIS/STAR CDN
     https://cdn.star.nesdis.noaa.gov/GOES18/ABI/SECTOR/{pnw,wus}/09/ (CORS "*"; STAR: "Users are free to use the images ... as they
     wish, as long as credit is given to the NOAA / NESDIS Center for Satellite Applications and Research"). Each JPG is a crop of the
     GOES-18 ABI fixed grid (geostationary view, sub-point 137.0 W); the crop offsets / pixel sizes below were fitted to the red map lines
     NOAA draws on the image (99% of them within 1 px, stable over the 10 days kept) and are re-checked on every frame (alignment test
     below: a frame that no longer lines up is not shown). Before use the burned-in red lines are masked and filled from the pixels
     around them, and the NOAA logo + time bar are cut off (our own coastlines / borders draw on top). PNW sector (1200 px, every 5 min)
     over the West US sector (1000 px = 2 km, every 10 min) over the full disk (1808 px = 6 km, every 10 min, fills the rest). The CDN lists ~10 days of frames, so the full loop is there on first open.
   11-03 (t2226u) "Hide menu" button: collapses the view / layer / satellite chips (choice kept in localStorage obsMenuMin). */
"use strict";
const ObsImg = (() => {
  const RAD_WMS = "https://opengeo.ncep.noaa.gov/geoserver/conus/conus_bref_qcd/ows";
  const GIBS_WMS = "https://gibs.earthdata.nasa.gov/wms/epsg4326/best/wms.cgi";
  const GIBS_ACK = "We acknowledge the use of imagery provided by services from NASA's Global Imagery Browse Services (GIBS), part of NASA's Earth Science Data and Information System (ESDIS).";
  const GIBS_ACK2 = ["We acknowledge the use of imagery provided by services from NASA's Global Imagery Browse Services (GIBS),", "part of NASA's Earth Science Data and Information System (ESDIS)."];   // Studio: two lines
  const GIBS_DOM = (layer) => `https://gibs.earthdata.nasa.gov/wmts/epsg4326/best/1.0.0/${layer}/default/2km/all/`;
  // box = [west, south, east, north] degrees; px = image width x height (radar detail 0.0125 deg ~1 km, satellite detail 0.02 deg ~1.5-2 km)
  const SRC = {
    radar: { label: "Radar", kind: "rad", layer: "conus_bref_qcd", fmt: "image/png", alpha: 0.88, n: 24, stepMin: 5, refreshMin: 4,
      tiles: { detail: { box: [-130, 39, -104, 53], px: [2080, 1120] }, wide: { box: [-130, 30, -100, 55], px: [1200, 1250] } },
      credit: "Radar: NOAA/NWS MRMS base reflectivity (public domain)" },
    ir: { label: "Clean IR", kind: "gibs", layer: "GOES-West_ABI_Band13_Clean_Infrared", fmt: "image/jpeg", alpha: 1, n: 24, stepMin: 10, refreshMin: 10,
      tiles: { detail: { box: [-140, 37, -100, 57], px: [2000, 1000] }, wide: { box: [-180, -10, -55, 78], px: [3125, 2200] } },   // 11-04: south to 10S for zoomed-out Studio / ocean views
      credit: "Satellite: NOAA GOES-West Clean IR (band 13) via NASA GIBS/ESDIS" },
    gc: { label: "GeoColor", kind: "gibs", layer: "GOES-West_ABI_GeoColor", fmt: "image/jpeg", alpha: 1, n: 24, stepMin: 10, refreshMin: 10,
      tiles: { detail: { box: [-140, 37, -100, 57], px: [2000, 1000] }, wide: { box: [-180, -10, -55, 78], px: [3125, 2200] } },
      credit: "Satellite: NOAA GOES-West GeoColor, NOAA/NESDIS/STAR, CIRA/NOAA via NASA GIBS/ESDIS" },
    // detail = PNW sector over the West US sector; wide = West US sector (the box is only used to pick the tile)
    wv: { label: "Water vapor", kind: "star", alpha: 1, n: 24, stepMin: 5, refreshMin: 4,
      tiles: { detail: { box: [-126, 32, -108, 50] }, wide: { box: [-160, 20, -100, 62] } },
      credit: "Satellite: NOAA GOES-West Mid-Level Water Vapor (band 9), NOAA/NESDIS/STAR" },
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
    if (s.kind === "star") return starTimes(id);
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
    // newest n frames at least stepMin apart (radar comes every ~2 min; a 5-min step gives a 2-hour loop, about all the radar server keeps)
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
  // Clean IR paints two GIBS images: detail (the east / center box) and wide (the only pixels west of 140W).
  // decoding stays async until decode() finishes, then the bitmap is copied into one canvas per size so the
  // GPU upload is the whole frame. A half-decoded wide JPEG used to land a frame later than the smaller detail image.
  const fullPx = new WeakSet(), pxPool = {};
  function gpuSrc(im) {
    if (!im || !fullPx.has(im)) return im;
    const w = im.naturalWidth, h = im.naturalHeight; if (!w || !h) return im;
    const k = w + "x" + h; let c = pxPool[k];
    if (!c) { c = pxPool[k] = document.createElement("canvas"); c.width = w; c.height = h; }
    if (c._im !== im) { c.getContext("2d").drawImage(im, 0, 0); c._im = im; }
    return c;
  }
  function getImg(id, tile, t) {   // cached Image; r.ok means loaded and decoded (null on failure)
    const key = id + "|" + tile + "|" + t; let r = ST.img.get(key);
    if (!r && SRC[id].kind === "star") {   // NOAA STAR water vapor: cleaned in this page, then shown from a blob: URL (same origin)
      const im = new Image(); im.decoding = "async"; r = { im, ok: false, sec: secOf(tile) }; r.p = starImg(r, r.sec, t); ST.img.set(key, r);
    }
    if (!r) {
      const im = new Image(); im.crossOrigin = "anonymous"; im.decoding = "async";
      r = { im, ok: false, p: new Promise((res) => {
        let settled = false; const done = (v) => { if (!settled) { settled = true; res(v); } };
        im.onload = async () => {
          try {
            if (ST.img.get(key) !== r) { done(null); return; }
            try { if (im.decode) await im.decode(); } catch (e) { /* drawImage below still uses whatever decoded */ }
            if (ST.img.get(key) !== r) { done(null); return; }
            // GIBS lists the newest times before every tile of them is filled in: such a frame comes back all black. Drop it (the loop uses the rest)
            if (SRC[id].kind === "gibs" && blank(im)) { r.bad = true; ST.blank.add(id + "|" + t); pickFrames(id); done(null); bump(); uiTime(); return; }
            try { im.decoding = "sync"; } catch (e) {}
            if (id === "ir") fullPx.add(im);
            r.ok = true; done(im); bump();
            // do not paint Clean IR when only the detail (east) image has decoded
            if (ST.obs && (id !== "ir" || layersReady(id, t))) Obs.redraw(); else uiTime();
          } catch (e) { if (!r.ok) { r.bad = true; done(null); } }
        };
        // 11-04 (t2299u) a failed request (GIBS is uncached and slow, ~3 s detail / ~6-10 s wide) gets one retry before the frame is dropped
        im.onerror = () => { if (!r.retried) { r.retried = true; setTimeout(() => { if (ST.img.get(key) === r) im.src = url(id, tile, t) + "&r=1"; else done(null); }, 1500); return; } r.bad = true; done(null); }; }) };
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
    if (ST.sat) for (const t of ST.all[ST.sat]) for (const [tl, u] of undersOf(ST.sat, listTile(ST.sat), t)) keep.add(ST.sat + "|" + tl + "|" + u);   // frames drawn under the loop frames
    for (const k of [...ST.img.keys()]) if (!keep.has(k) || !on().includes(k.split("|")[0])) { const r = ST.img.get(k); r.im.src = ""; if (r.u) URL.revokeObjectURL(r.u); ST.img.delete(k); }
  }
  const tileFor = (id) => { const S = ST.obs; if (!S) return "detail";
    const T = SRC[id].tiles.detail.box, kmpx = 1 / (S.k * Math.min(S.dpr || 1, 2));   // device-pixel scale
    if (kmpx > 2.2) return "wide";
    // zoomed in: detail box, unless the view centre is outside it
    const ll = inv(S.cx, S.cy); return ll && ll[0] > T[0] && ll[0] < T[2] && ll[1] > T[1] && ll[1] < T[3] ? "detail" : "wide"; };

  // the tile a source's frame list was made for (water vapor PNW and West US frames have different times: never mix them while the list reloads)
  const listTile = (id) => (SRC[id].kind === "star" && ST.wvTile ? ST.wvTile : tileFor(id));
  /* ---- water vapor: NOAA/NESDIS/STAR band 9 sector JPGs (ABI fixed grid), map lines / logo / time bar removed ---- */
  const STAR = (sec) => `https://cdn.star.nesdis.noaa.gov/GOES18/ABI/${sec === "fd" ? "FD" : "SECTOR/" + sec}/09/`, TAG = (sec) => (sec === "fd" ? "FD" : sec);
  // g = [x0, y0, dx, dy]: scan angle (rad) of the image's left / top edge and the size of one pixel; cut = [time bar top, logo right, logo top]
  // (fractions of the image); ref = pixels (x, y pairs) that sit on NOAA's state / border lines when the sector has not moved
  const SEC = {
    pnw: { sz: "1200x1200", W: 1200, H: 1200, g: [0.021729093900522235, 0.12716812531352942, 2.8015897504006866e-05, 2.8001904067229945e-05], cut: [1172 / 1200, 108 / 1200, 1102 / 1200],
      ref: [1177,578,1178,581,965,556,977,585,979,588,989,613,994,624,1001,642,1012,667,1024,696,1030,711,1040,736,1043,744,1053,770,1057,781,1072,819,1075,826,1079,838,1081,842,1088,861,1091,868,1093,876,1098,888,1141,916,1183,918,1190,919,619,4,623,5,625,6,653,27,656,31,615,4,676,63,683,64,685,65,707,82,708,85,682,64,677,64,725,91,716,86,927,39,933,47,935,50,956,81,250,269,248,267,213,243,602,269,563,267,530,266,524,265,511,265,494,267,469,268,451,272,393,280,390,280,387,282,365,283,341,276,324,276,302,281,375,282,532,528,524,528,503,527,495,527,481,526,466,526,444,525,401,524,313,521,298,521,290,521,246,519,644,268,641,260,638,257,603,198,589,169,586,163,569,129,567,123,564,117,553,94,669,366,671,365,672,363,683,310,685,305,665,282,698,392,696,393,741,516,730,488,717,454,714,448,708,434,706,428,700,414,698,411,700,410,700,407,765,233,764,232,723,205,685,187,680,185,678,175,667,166,642,150,639,144,624,115,622,112,618,103,774,235,772,232,815,299,808,292,811,279,806,277,804,271,803,266,799,261,799,258,798,250,796,243,796,242,795,238,794,237,792,236,844,307,833,312,821,306,918,357,897,337,937,364,1079,387,1049,370,1045,372,995,380,1049,382,1025,380,1005,379,1018,380,1083,394,1093,414,1109,444,1111,447,1144,512,1153,529,1160,543,1165,553,1073,376,1064,360,1065,355,1068,355,1074,355,1097,356,1138,359,1172,361,1188,362,742,536,724,535,720,535,706,535,692,534,688,534,684,534,670,533,634,532,612,531,583,530,576,530,568,529,539,528,841,540,870,542,905,543,953,546,1119,1076,1122,991,1128,981,1125,965,1124,961,1100,1026,1091,1010,1086,980,1116,989,1101,982,993,547,1077,552,1071,551,1058,551,1032,549,1006,548,1154,556,1135,555,1103,553,1090,552,1160,556,1117,1071,1107,1065,1083,1049,1074,1042,1059,1033,1045,1023,1040,1020,988,986,974,976,969,973,950,961,945,957,912,936,907,933,903,930,884,918,870,909,851,897,837,888,827,882,813,873,808,870,780,852,771,846,762,841,692,799,660,780,655,778,613,753,600,745,598,738,589,709,587,702,582,688,574,659,563,624,543,562,541,555,206,245,190,237,176,238,167,238,163,239,156,237,151,234,193,75,209,75,313,79,326,79,329,80,361,81,384,82,396,82,409,83,454,85,466,85,479,86,485,86,530,88,533,88,548,89,552,89,605,91,608,92,617,92,648,93,651,94,694,96,704,96,716,97,722,97,728,98,783,101,813,102,822,103,831,103,849,104,867,105,879,106,888,107,897,107,906,108,920,109,926,109,938,110,956,111,967,112,979,112,1002,114,1031,116,1040,116,1057,118,1077,119,1095,120,1151,124,1157,125,1160,125,1188,127] },
    wus: { sz: "1000x1000", W: 1000, H: 1000, g: [-0.0031457580672190942, 0.13670993915230234, 5.6004591692701455e-05, 5.60198112612544e-05], cut: [974 / 1000, 86 / 1000, 920 / 1000],
      ref: [930,457,931,459,945,491,952,507,952,509,959,525,962,533,967,546,972,559,978,574,984,589,989,604,992,610,518,5,522,11,530,24,531,25,534,31,535,32,537,36,539,40,542,45,544,48,546,52,559,75,569,86,567,86,570,89,580,92,589,96,607,101,594,98,609,101,610,102,621,108,624,110,627,112,631,117,632,118,648,122,647,123,650,125,638,118,662,127,663,127,660,127,657,127,693,141,711,152,716,153,730,161,733,162,734,163,738,166,743,168,757,173,762,176,767,179,777,190,777,192,781,196,781,197,787,202,789,207,791,208,808,217,811,218,802,213,756,5,762,12,767,16,771,20,777,27,804,57,830,88,834,92,836,95,838,97,839,99,846,107,876,146,888,162,894,170,898,176,900,178,902,181,922,210,923,212,929,220,916,4,924,11,928,14,933,18,948,31,975,55,977,56,576,310,569,305,563,296,556,293,745,304,742,304,732,304,729,304,712,303,709,303,694,304,683,304,663,307,657,309,627,312,626,311,609,308,592,311,653,310,635,311,695,434,692,433,688,433,659,432,648,432,630,431,622,431,611,431,600,431,593,430,585,430,763,299,759,295,755,290,750,278,746,269,744,266,741,260,740,258,729,234,722,220,780,359,781,346,784,339,788,319,787,317,793,366,793,364,808,411,794,377,794,375,823,284,815,278,810,275,799,268,796,268,789,264,786,261,785,261,781,256,774,250,831,287,852,322,851,321,849,317,851,314,852,313,850,310,843,301,844,298,843,293,838,288,835,289,872,322,866,323,861,326,857,324,853,323,904,350,903,349,927,364,916,355,913,352,911,351,906,349,982,363,969,355,967,355,967,358,943,360,966,360,928,364,940,362,996,387,975,347,991,348,994,348,811,438,806,438,790,437,786,437,772,436,757,436,754,436,728,435,719,434,836,439,844,439,868,440,889,441,893,441,910,442,914,442,917,443,994,685,991,677,990,675,984,662,941,444,934,443,979,446,957,445,992,446,986,694,962,678,960,677,948,669,940,664,936,661,929,656,919,650,917,649,905,641,893,633,888,630,881,626,879,624,874,621,862,614,860,612,841,600,827,592,825,590,813,583,809,581,767,556,753,548,741,532,736,517,733,507,729,493,724,479,722,472,720,465,714,448,712,441,541,290,532,289,523,289,535,207,597,209,615,210,642,211,645,211,674,212,684,213,688,213,696,213,710,214,731,215,734,215,759,216,762,217,763,217,770,217,780,217,784,218,799,218,808,219,811,219,832,220,860,222,872,222,878,223,887,223,888,223,895,224,915,225,919,225,928,226,929,226,938,227,942,227,948,227,958,228,973,229,984,230,990,230,994,230,199,3,199,4,208,7,253,19,249,19] },
    fd: { sz: "1808x1808", W: 1808, H: 1808, g: [-0.151872, 0.151872, 0.000168, 0.000168], cut: [1776 / 1808, 180 / 1808, 1652 / 1808],   // full disk (6 km): fills past the West US sector
      ref: [1001,24,1006,25,1196,245,1207,270,1207,271,1212,283,1236,300,1254,301,1282,309,1290,328,1297,346,1290,255,1275,293,1278,300,1341,306,1295,303,1287,303,1357,327,1359,330,1371,356,1372,359,1378,373,1360,373,1356,373,1274,199,1281,210,1338,206,1325,257,1309,234,1304,233,1334,236,1355,240,1348,288,1402,275,1397,275,1376,273,1340,270,1349,308,1363,314,1378,315,1389,327,1388,326,1400,343,1404,343,1455,357,1449,353,1433,352,1427,352,1421,313,1377,309,1375,309,1384,257,1384,257,1010,70,1000,70,972,69,938,69,934,69,925,69,913,69,902,69,909,31,928,37,934,40,935,39,936,42,941,44,949,46,952,47,954,48,954,48,956,50,961,54,961,54,961,54,963,55,968,57,973,58,977,60,986,65,1003,64,992,65,990,65,987,65,1012,70,1038,25,1033,19,1019,24,1031,25,1029,36,1026,35,1016,33,1015,33,1014,32,999,27,1164,80,1058,91,1064,102,1064,102,1070,112,1088,124,1095,129,1112,136,1106,132,1117,137,1127,143,1134,147,1144,154,1145,156,1154,161,1051,72,1106,75,1111,75,1125,79,1170,129,1178,140,1189,156,1288,114,1289,119,1290,123,1290,124,1290,125,1291,128,1294,145,1199,83,1203,84,1216,85,1179,83,1182,85,1188,89,1189,91,1216,113,1220,117,1224,121,1232,128,1242,137,1400,451,1397,446,1434,439,1433,448,1431,457,1445,473,1444,476,1369,449,1368,452,1390,456,1411,476,1429,477,1424,476,1434,482,1444,485,1422,479,1418,486,1444,445,1462,464,1458,485,1071,188,1129,191,1107,192,1098,193,1099,234,1139,191,1144,208,1149,212,1148,178,1146,176,1135,163,1169,197,1167,192,1166,191,1166,191,1173,198,1194,211,1189,207,1203,210,1228,207,1235,207,1267,209,1276,210,1157,236,1230,354,1215,310,1216,317,1215,313,1215,239,1458,298,1468,307,1465,306,1496,373,1502,390,1503,395,1527,409,1486,346,1485,337,1208,318,1153,283,1130,262,1125,244,1408,280,1410,283,1420,293,1429,307,1433,315,1405,269,1408,270,1440,325,1444,321,1461,323,1464,323,1467,323,1470,324,1486,326,1486,326,1490,407,1480,368,1489,344,1497,345,1501,346,1514,364,1525,387,1531,397,1535,405,1536,406,1324,188,1321,186,1357,225,1357,225,1349,215,1404,238,1411,243,1416,248,1417,248,1370,203,1373,211,1374,210,1407,238,1397,231,1380,219,1423,252,1431,272,1429,262,1485,318,1432,252,1435,252,1529,411,1068,187,1067,188,1059,186,1065,159,1104,161,1114,161,1142,162,1144,162,1146,162,1154,163,1180,164,1213,166,1237,168,1259,170,1265,171,1304,174,1323,176,1331,179,1332,180,1334,180,1336,181,1345,182,1347,183,1351,185,1382,190,1282,378,1254,368,1237,363,1236,362,1216,357,1330,374,1333,374,1338,375,1336,375,1348,381,1345,380,1343,378,1438,436,1430,426,1395,412,1394,417,1455,457,1457,459,1478,467,1478,467,880,24,878,30,872,59,897,73,880,67,933,78,933,78,941,83,942,84,905,74] },
  };
  const secOf = (tile) => (tile === "detail" ? "pnw" : tile === "fd" ? "fd" : "wus");
  try { indexedDB.deleteDatabase("obsimg-wv"); } catch (e) { /* frames saved by the 11-03 browser-built loop are no longer used */ }
  const doy2iso = (s) => new Date(Date.UTC(+s.slice(0, 4), 0, +s.slice(4, 7), +s.slice(7, 9), +s.slice(9, 11))).toISOString().replace(".000Z", "Z");
  async function starList(sec) {
    const x = await (await fetch(STAR(sec), { cache: "no-store" })).text(), re = new RegExp(`(\\d{11})_GOES18-ABI-${TAG(sec)}-09-${SEC[sec].sz}\\.jpg`, "g");
    const set = new Set(); let m; while ((m = re.exec(x))) set.add(m[1]);
    return [...set].sort().slice(-40).map(doy2iso);
  }
  const fname = (sec, t) => { const d = new Date(t), y = d.getUTCFullYear(), j = Math.round((Date.UTC(y, d.getUTCMonth(), d.getUTCDate()) - Date.UTC(y, 0, 1)) / 864e5) + 1, p = (v, n) => String(v).padStart(n, "0");
    return `${STAR(sec)}${y}${p(j, 3)}${p(d.getUTCHours(), 2)}${p(d.getUTCMinutes(), 2)}_GOES18-ABI-${TAG(sec)}-09-${SEC[sec].sz}.jpg`; };
  async function starTimes(id) {
    const s = SRC[id], tile = tileFor(id), now = Date.now();
    if (ST.timesAt[id] && ST.wvTile === tile && now - ST.timesAt[id] < s.refreshMin * 60e3 && ST.frames[id].length) return ST.frames[id];
    const [wus, fd] = await Promise.all([starList("wus"), starList("fd")]); ST.wusT = wus.slice(-30); ST.fdT = fd.slice(-30);
    const all = tile === "detail" ? await starList("pnw") : wus;
    const pick = [], gap = (tile === "detail" ? 5 : 10) * 60e3 - 30e3;
    for (let i = all.length - 1; i >= 0 && pick.length < s.n + 2; i--) { const t = Date.parse(all[i]); if (!pick.length || Date.parse(pick[0]) - t >= gap) pick.unshift(all[i]); }
    // frames that failed (not on the CDN yet, or did not line up) get another try with each new list
    for (const k of [...ST.blank]) if (k.startsWith(id + "|")) { ST.blank.delete(k); const t = k.slice(id.length + 1); for (const tl of ["detail", "wide", "fd"]) { const r = ST.img.get(id + "|" + tl + "|" + t); if (r && r.bad) ST.img.delete(id + "|" + tl + "|" + t); } }
    ST.wvMoved = false;
    ST.all[id] = pick; ST.timesAt[id] = now; ST.wvTile = tile; return pickFrames(id);
  }
  // frames drawn under a main frame (bottom first): full disk, then West US under a PNW frame; each the newest at or before it
  function underT(L, t) { L = L || []; for (let i = L.length - 1; i >= 0; i--) if (Date.parse(L[i]) <= Date.parse(t) + 60e3) return L[i]; return L[0] || null; }
  const unders = (tile, t) => [["fd", underT(ST.fdT, t)], ...(tile === "detail" ? [["wide", underT(ST.wusT, t)]] : [])].filter((x) => x[1]);
  // 11-03 (t2248u) what is drawn under a frame so the whole map stays covered at every zoom / pan: water vapor = full disk (+ West US
  // under PNW); GIBS zoomed in = the wide box under the sharper detail box. Clean IR uses that wide box at the same time as the
  // detail box. GeoColor still steps the wide box every 30 min (it is only seen past the detail edge).
  const undersOf = (id, tile, t) => (SRC[id].kind === "star" ? unders(tile, t) : id === "ir" && tile === "detail" ? [["wide", t]] : SRC[id].kind === "gibs" && tile === "detail" ? [["wide", wideT(id, t)]] : []);
  // 11-04 (t2299u) GeoColor's wide frame under a zoomed-in frame (only seen past the detail box edge) is ~1.1 MB and 6-10 s from GIBS:
  // use one every 30 min (newest back), so a 4-hour loop loads 9 of them instead of 24. Clean IR does not use this.
  function wideT(id, t) { const f = ST.frames[id], i = f.indexOf(t); if (i < 0) return t; const L = f.length; return f[Math.max(0, L - 1 - 3 * Math.round((L - 1 - i) / 3))]; }
  // red / pink map-line pixels (STAR draws them pure red; JPEG blurs them into the background). Yellow / orange (dry air) is not a line.
  const lineAt = (d, i) => { const r = d[i], g = d[i + 1], b = d[i + 2]; return (r - g > 60 && g - b < 60) || (r - g > 12 && Math.abs(g - b) < 31); };
  let procQ = Promise.resolve();
  function starClean(im, sec) {   // -> Promise<Blob | "moved" | null>, one image at a time so the page stays responsive
    const run = async () => {
      const S = SEC[sec], W = im.naturalWidth, H = im.naturalHeight; if (W !== S.W || H !== S.H) return "moved";
      const c = document.createElement("canvas"); c.width = W; c.height = H; const g = c.getContext("2d", { willReadFrequently: true }); g.drawImage(im, 0, 0);
      const id = g.getImageData(0, 0, W, H), d = id.data, N = W * H, bad = new Uint8Array(N);
      for (let p = 0, i = 0; p < N; p++, i += 4) if (lineAt(d, i)) bad[p] = 1;
      // 11-03 (t2254u) faint pink JPEG traces of the lines (e.g. over the Prairies / Dakotas on blue or yellow): red-minus-green clearly above its 9x9 neighbourhood mean
      { const I = new Float64Array((W + 1) * (H + 1)), e = (p) => d[p * 4] - d[p * 4 + 1];
        for (let y = 0; y < H; y++) { let row = 0; for (let x = 0; x < W; x++) { row += e(y * W + x); I[(y + 1) * (W + 1) + x + 1] = I[y * (W + 1) + x + 1] + row; } }
        for (let y = 0; y < H; y++) { const y0 = Math.max(0, y - 4), y1 = Math.min(H, y + 5);
          for (let x = 0; x < W; x++) { const p = y * W + x; if (bad[p]) continue; const x0 = Math.max(0, x - 4), x1 = Math.min(W, x + 5);
            const m = (I[y1 * (W + 1) + x1] - I[y0 * (W + 1) + x1] - I[y1 * (W + 1) + x0] + I[y0 * (W + 1) + x0]) / ((y1 - y0) * (x1 - x0));
            if (e(p) - m > 16) bad[p] = 1; } } }
      // alignment test: NOAA's own state / border lines must still be where the fitted geometry puts them
      let hit = 0; const R = S.ref, n = R.length / 2;
      for (let k = 0; k < R.length; k += 2) { const x = R[k], y = R[k + 1]; let h = 0; for (let dy = -1; dy <= 1 && !h; dy++) for (let dx = -1; dx <= 1; dx++) if (bad[(y + dy) * W + x + dx]) { h = 1; break; } hit += h; }
      if (hit / n < 0.8) return "moved";
      // grow the mask 2 px (3 on the 6 km full disk: JPEG halo), then fill it from the edges inward with the mean of the known neighbours
      const m = new Uint8Array(N), gr = sec === "fd" ? 3 : 2;
      for (let y = 0; y < H; y++) for (let x = 0; x < W; x++) if (bad[y * W + x]) for (let yy = Math.max(0, y - gr); yy <= Math.min(H - 1, y + gr); yy++) for (let xx = Math.max(0, x - gr); xx <= Math.min(W - 1, x + gr); xx++) m[yy * W + xx] = 1;
      let todo = []; for (let p = 0; p < N; p++) if (m[p]) todo.push(p);
      for (let it = 0; it < 40 && todo.length; it++) {
        const fill = [], rest = [];
        for (const p of todo) {
          const x = p % W, y = (p - x) / W; let r = 0, gg = 0, b = 0, k = 0;
          for (let dy = -1; dy <= 1; dy++) for (let dx = -1; dx <= 1; dx++) { if (!dx && !dy) continue; const xx = x + dx, yy = y + dy; if (xx < 0 || yy < 0 || xx >= W || yy >= H) continue; const q = yy * W + xx; if (!m[q]) { const i = q * 4; r += d[i]; gg += d[i + 1]; b += d[i + 2]; k++; } }
          if (k) fill.push(p, r / k, gg / k, b / k); else rest.push(p);
        }
        for (let j = 0; j < fill.length; j += 4) { const p = fill[j], i = p * 4; d[i] = fill[j + 1]; d[i + 1] = fill[j + 2]; d[i + 2] = fill[j + 3]; m[p] = 0; }
        todo = rest;
      }
      g.putImageData(id, 0, 0);
      const enc = (type) => new Promise((res) => c.toBlob(res, type, 0.92));
      let blob = await enc("image/webp"); if (!blob || blob.type !== "image/webp") blob = await enc("image/jpeg");   // Safari cannot write WebP
      return blob;
    };
    const p = procQ.then(run, run); procQ = p.catch(() => null); return p;
  }
  function starImg(r, sec, t) {   // raw NOAA JPG -> cleaned copy (blob: URL on this page) -> r.im
    const raw = new Image(); raw.crossOrigin = "anonymous"; raw.decoding = "async";
    return new Promise((res) => { raw.onerror = () => { r.bad = true; res(null); };
      raw.onload = async () => {
        let out = null; try { out = await starClean(raw, sec); } catch (e) { out = null; } raw.onload = raw.onerror = null; raw.src = "";   // free the raw copy
        if (out === "moved") { ST.wvMoved = true; r.bad = true; res(null); return; }
        if (!out) { r.bad = true; res(null); return; }
        r.u = URL.createObjectURL(out); r.im.onload = () => { r.ok = true; res(r.im); bump(); if (ST.obs) Obs.redraw(); };
        r.im.onerror = () => { r.bad = true; res(null); }; r.im.src = r.u; };
      raw.src = fname(sec, t); });
  }

  /* ---- loading: newest frame first (stays on screen), then the rest; the loop starts only once that window is loaded ---- */
  // 11-04 (t2299u) GeoColor under frame not loaded (yet) or failed: use the nearest loaded one in time, so those map edges never blink empty.
  // Clean IR does not: the wide ocean must be the same time as the detail center, or it is left out until that frame is ready.
  function underOk(id, tl, tu) { const r = ST.img.get(id + "|" + tl + "|" + tu); if (r && r.ok) return r; if (id === "ir") return null; const T = Date.parse(tu); let best = null, bd = 1e15;
    for (const [k, q] of ST.img) if (q.ok && k.startsWith(id + "|" + tl + "|")) { const d = Math.abs(Date.parse(k.slice(id.length + tl.length + 2)) - T); if (d < bd) { bd = d; best = q; } } return best; }
  // Layers a frame has to have before it can play. Clean IR always needs detail and wide at that same timestamp.
  // Wide is the west side (west of 140W); detail is the east / center. Both have to be decoded, not just loaded.
  function needLayers(id, t) { return id === "ir" ? [["detail", t], ["wide", t]] : [[listTile(id), t]]; }
  function layersReady(id, t) { return !!t && needLayers(id, t).every(([tl, u]) => { const r = ST.img.get(id + "|" + tl + "|" + u); return !!(r && r.ok); }); }
  function dropFailed() {   // blank or retry-failed layers are already marked bad; drop that time so it cannot stall the loop
    for (const id of on()) { let cut = false;
      for (const t of [...ST.frames[id]]) if (needLayers(id, t).some(([tl, u]) => { const r = ST.img.get(id + "|" + tl + "|" + u); return r && r.bad && !r.ok; })) { ST.blank.add(id + "|" + t); cut = true; }
      if (cut) pickFrames(id); }
    if (ST.idx >= len()) ST.idx = Math.max(0, len() - 1);
  }
  function loopReady() {
    const ids = on(); if (!ids.length) return false;
    for (const id of ids) for (const t of ST.frames[id]) if (!layersReady(id, t)) return false;
    return true;
  }
  function loadNote() {
    let n = 0, N = 0;
    for (const id of on()) for (const t of ST.frames[id]) { N++; if (layersReady(id, t)) n++; }
    return N && n < N ? "Loading loop " + n + "/" + N : "";
  }
  let loading = null;
  async function refresh() {
    if (loading) return loading;
    loading = (async () => {
      ST.msg = "";
      for (const id of on()) {
        try { await times(id); } catch (e) { ST.msg = SRC[id].label + " times unavailable"; continue; }
        const fr = ST.frames[id]; if (!fr.length) { ST.msg = SRC[id].label + ": no recent frames"; continue; }
        const tile = listTile(id);
        for (let tries = 0; tries < 5 && ST.frames[id].length; tries++) { const f = ST.frames[id], t = f[f.length - 1];
          const need = id === "ir" ? [["detail", t], ["wide", t]] : [[tile, t]];   // IR still waits for both layers of this time
          if (id !== "ir") for (const [tl, u] of undersOf(id, tile, t)) getImg(id, tl, u);
          const rs = need.map(([tl, u]) => getImg(id, tl, u));
          if ((await Promise.all(rs.map((r) => r.p))).every(Boolean)) break;
          if (id === "wv" || id === "ir") { ST.blank.add(id + "|" + t); pickFrames(id); } }   // newest real frame first; keep it on screen while the rest load
        if (id === "wv" && ST.wvMoved && !ST.frames.wv.some((t) => { const r = ST.img.get("wv|" + tile + "|" + t); return r && r.ok; })) ST.msg = "Water vapor paused: NOAA moved its image sector, so it would not line up with this map";
      }
      prune(); if (ST.idx < 0 || ST.idx >= len()) ST.idx = len() - 1;
      ui(); bump(); Obs.redraw();   // newest still stays up; do not start the loop until the window below has loaded
      for (let pass = 0; pass < 2; pass++) {   // pass 2: frames that slid in after black ones dropped out
        // 11-04 (t2299u) every loop frame first (newest back), then the bigger frames drawn under them, so the loop fills in quickly
        // 11-07 Clean IR also queues the other box at the same time, so detail and wide stay paired
        const todo = [], und = []; for (const id of on()) { const tile = listTile(id); for (const t of [...ST.frames[id]].reverse()) { todo.push([id, tile, t]); if (id === "ir") und.push([id, tile === "detail" ? "wide" : "detail", t, tile]); else for (const [tl, u] of undersOf(id, tile, t)) und.push([id, tl, u, tile]); } }
        todo.push(...und);
        await Promise.all([0, 1, 2, 3, 4, 5].map(async () => {   // 11-04 (t2299u) 6 at a time: GIBS builds each image on request (~3-10 s, never cached), so waiting on 3 left the loop half empty for a minute
        while (todo.length) { const [id, tile, t, under_] = todo.shift(); if (on().includes(id) && (id === "ir" || listTile(id) === (under_ || tile))) { const r = getImg(id, tile, t); await r.p; if (r.bad && (id === "ir" || (id === "wv" && !under_))) { ST.blank.add(id + "|" + t); pickFrames(id); } } } }));
      }
      dropFailed(); if (ST.idx < 0 || ST.idx >= len()) ST.idx = Math.max(0, len() - 1);
      ui(); bump(); Obs.redraw();
    })().finally(() => { loading = null; });
    return loading;
  }
  const len = () => Math.max(0, ...on().map((id) => ST.frames[id].length));
  // frame i of the loop for one source (sources with different counts are aligned at the newest frame)
  const tAt = (id, i) => { const fr = ST.frames[id], L = len(); if (!fr.length) return null; const j = fr.length - (L - i); return fr[Math.max(0, Math.min(fr.length - 1, j))]; };

  /* ---- loop ---- */
  // 11-04 loop speed (0.25x - 4x, 1x = the old 380 ms per frame / 1.6 s on the newest); remembered for the session
  const spd = () => { let v = 1; try { v = +sessionStorage.getItem("oiSpeed") || 1; } catch (e) { /* private mode */ } return Math.max(0.25, Math.min(4, v)); };
  let stepping = false;
  function arm(ms) { clearTimeout(ST.timer); ST.timer = setTimeout(tick, ms); }
  function tick() {
    clearTimeout(ST.timer); ST.timer = 0; if (stepping || !on().length || ST.hold) return;
    if (!ST.playing || !ST.obs || !ST.obs.shown || document.hidden) { arm(600); return; }
    dropFailed(); const L = len(); if (ST.idx >= L) ST.idx = Math.max(0, L - 1);
    if (!loopReady()) { uiTime(); arm(300); return; }   // hold the newest valid still; do not skip frames that are still loading
    const pace = () => Math.round((ST.idx === L - 1 ? 1600 : 380) / spd());   // 11-04 (t2266u) loop speed slider; dwell on the newest frame
    if (L > 1) {
      const nxt = (ST.idx + 1) % L, tOk = (id) => layersReady(id, tAt(id, nxt));
      if (on().every(tOk) && nxt !== ST.idx) {
        const dec = [];
        for (const id of on()) for (const [tl, u] of needLayers(id, tAt(id, nxt))) { const r = ST.img.get(id + "|" + tl + "|" + u); if (r && r.im && r.im.decode) dec.push(r.im.decode().catch(() => {})); }
        const go = () => { try { ST.idx = nxt; bump(); Obs.drawNow(); uiTime(); } finally { arm(pace()); } };
        if (dec.length) { stepping = true; Promise.all(dec).then(() => { stepping = false; if (!ST.playing || ST.hold || !ST.obs || !ST.obs.shown || document.hidden) { tick(); return; } go(); }); return; }
        go(); return;
      }
    }
    arm(pace());
  }

  /* ---- WebGL reprojection (lat/lon image -> obs map Lambert conformal at the current zoom / pan) ---- */
  const VS = "attribute vec2 p;void main(){gl_Position=vec4(p,0.,1.);}";
  const FS = `precision highp float;uniform sampler2D tex;uniform vec2 sz;uniform float dpr,k,cx,cy,n,F,rho0,L0,alpha,geo,lim;uniform vec4 box,gg;uniform vec3 cut;
    const float R=6371.,D=0.017453292519943295;
    void main(){vec2 css=vec2(gl_FragCoord.x,sz.y-gl_FragCoord.y)/dpr;vec2 vp=sz/dpr;
      float x=(css.x-vp.x*.5)/k+cx, y=(css.y-vp.y*.5)/k+cy, yr=rho0+y, s=sign(n);
      float rho=s*sqrt(x*x+yr*yr), th=atan(s*x,s*yr), lon=(L0+th/n)/D, lat=(2.*atan(pow(R*F/rho,1./n))-1.5707963267948966)/D;
      vec2 uv=vec2((lon-box.x)/(box.z-box.x),(box.w-lat)/(box.w-box.y));
      if(geo>.5){   // GOES-18 ABI fixed grid (GOES-R PUG navigation; GRS80, sub-point 137.0 W, H = 42164.16 km)
        float la=lat*D,lo=(lon+137.)*D,lc=atan(.993305616*tan(la)),cl=cos(lc),rc=6356.75231414/sqrt(1.-.00669438*cl*cl);
        float sx=42164.16-rc*cl*cos(lo),sy=-rc*cl*sin(lo),sz=rc*sin(lc);
        if(42164.16*(42164.16-sx)<sy*sy+1.006739501*sz*sz){discard;}   // far side of the Earth
        uv=vec2((asin(-sy/sqrt(sx*sx+sy*sy+sz*sz))-gg.x)/gg.z,(gg.y-atan(sz/sx))/gg.w);
        if(uv.y>cut.x||(uv.x<cut.y&&uv.y>cut.z)){discard;}
      }
      if(uv.x<0.||uv.x>1.||uv.y<0.||uv.y>1.){discard;}
      if(cos(lat*D)*cos((lon+137.)*D)<lim){discard;}   // GIBS GOES-West: past ~81 deg from the sub-point is no-data black
      vec4 c=texture2D(tex,uv);if(geo>.5&&c.r+c.g+c.b<.13){discard;}   // space / no-data black on the NOAA images
      gl_FragColor=vec4(c.rgb*c.a*alpha,c.a*alpha);}`;
  function glInit() {
    if (ST.gl || ST.glFail) return ST.gl;
    const cv = document.createElement("canvas"), gl = cv.getContext("webgl", { premultipliedAlpha: true, preserveDrawingBuffer: true, antialias: false });
    if (!gl) { ST.glFail = "Radar / satellite need WebGL, which this browser has turned off"; return null; }
    const sh = (t, src) => { const s = gl.createShader(t); gl.shaderSource(s, src); gl.compileShader(s); if (!gl.getShaderParameter(s, gl.COMPILE_STATUS)) throw new Error(gl.getShaderInfoLog(s)); return s; };
    try {
      const pr = gl.createProgram(); gl.attachShader(pr, sh(gl.VERTEX_SHADER, VS)); gl.attachShader(pr, sh(gl.FRAGMENT_SHADER, FS)); gl.linkProgram(pr); gl.useProgram(pr);
      const b = gl.createBuffer(); gl.bindBuffer(gl.ARRAY_BUFFER, b); gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 1, -1, -1, 1, 1, 1]), gl.STATIC_DRAW);
      const loc = gl.getAttribLocation(pr, "p"); gl.enableVertexAttribArray(loc); gl.vertexAttribPointer(loc, 2, gl.FLOAT, false, 0, 0);
      const tex = [0, 1, 2, 3].map((u) => { const t = gl.createTexture(); gl.activeTexture(gl.TEXTURE0 + u); gl.bindTexture(gl.TEXTURE_2D, t);
        for (const [a, v] of [[gl.TEXTURE_MIN_FILTER, gl.LINEAR], [gl.TEXTURE_MAG_FILTER, gl.LINEAR], [gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE], [gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE]]) gl.texParameteri(gl.TEXTURE_2D, a, v);
        return t; });   // unit 0 = satellite, unit 1 = radar, unit 2 / 3 = water vapor West US / full disk under the main frame (each keeps its last frame)
      gl.enable(gl.BLEND); gl.blendFunc(gl.ONE, gl.ONE_MINUS_SRC_ALPHA);
      const U = {}; for (const u of ["tex", "sz", "dpr", "k", "cx", "cy", "n", "F", "rho0", "L0", "alpha", "box", "geo", "gg", "cut", "lim"]) U[u] = gl.getUniformLocation(pr, u);
      ST.gl = { cv, gl, U, tex, cur: [null, null, null, null] };
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
    const tile = listTile(id), other = tile === "detail" ? "wide" : "detail";
    for (let j = i; j >= 0; j--) {
      const t = tAt(id, j); if (!t) continue;
      if (id === "ir" && !layersReady(id, t)) continue;   // never show the detail box while its wide (west) image is still decoding
      for (const tl of [tile, other]) { const r = ST.img.get(id + "|" + tl + "|" + t); if (r && r.ok) return { im: r.im, tile: tl, t }; }
    }
    if (id === "ir") return null;
    // still loading after a zoom / view change: keep showing the newest frame already here (any box) rather than nothing
    let best = null; for (const [k, r] of ST.img) { const [kid, tl, t] = k.split("|"); if (kid === id && r.ok && (tl === "detail" || tl === "wide") && (!best || t > best.t)) best = { im: r.im, tile: tl, t }; }
    return best;
  }
  function under(g, S) {
    ST.obs = S; if (!on().length) return;
    if (ST.gl && ST.gl.gl.isContextLost()) { ST.gl = null; ST.glLost = (ST.glLost || 0) + 1; }   // GPU dropped the context: start a fresh one
    const G = glInit(); if (!G) return;
    const J = projOf(S); if (!J) return;
    const W = Math.round(S.w * S.dpr), H = Math.round(S.h * S.dpr), { gl, U, cv } = G;
    if (cv.width !== W || cv.height !== H) { cv.width = W; cv.height = H; }
    gl.viewport(0, 0, W, H); gl.clearColor(0, 0, 0, 0); gl.clear(gl.COLOR_BUFFER_BIT);
    gl.uniform2f(U.sz, W, H); gl.uniform1f(U.dpr, S.dpr); gl.uniform1f(U.k, S.k); gl.uniform1f(U.cx, S.cx); gl.uniform1f(U.cy, S.cy);
    gl.uniform1f(U.n, J.n); gl.uniform1f(U.F, J.F); gl.uniform1f(U.rho0, J.rho0); gl.uniform1f(U.L0, J.L0);     let drew = 0; ST.shown = {};
    const draw1 = (u, im, setBox) => { try { const src = gpuSrc(im), token = (src && src._im) || src; gl.activeTexture(gl.TEXTURE0 + u); gl.bindTexture(gl.TEXTURE_2D, G.tex[u]); gl.uniform1i(U.tex, u);
      if (G.cur[u] !== token) { gl.pixelStorei(gl.UNPACK_PREMULTIPLY_ALPHA_WEBGL, false); gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, gl.RGBA, gl.UNSIGNED_BYTE, src); G.cur[u] = token; }
      setBox(); gl.drawArrays(gl.TRIANGLE_STRIP, 0, 4); drew++; } catch (e) { ST.drawErr = (ST.drawErr || 0) + 1; G.cur[u] = null; } };
    const geoBox = (sec) => () => { const S_ = SEC[sec], q = S_.g; gl.uniform1f(U.geo, 1); gl.uniform1f(U.lim, -2); gl.uniform4f(U.gg, q[0], q[1], q[2] * S_.W, q[3] * S_.H); gl.uniform3f(U.cut, S_.cut[0], S_.cut[1], S_.cut[2]); gl.uniform4f(U.box, 0, 0, 1, 1); gl.uniform1f(U.alpha, 1); };
    for (const id of [ST.sat, ST.radar ? "radar" : ""].filter(Boolean)) {   // satellite first, radar on top
      const f = frameImg(id, ST.idx < 0 ? len() - 1 : ST.idx); if (!f) continue;
      const u = id === "radar" ? 1 : 0;
      if (SRC[id].kind === "star") {
        for (const [tl, tu] of unders(f.tile, f.t)) { const ru = ST.img.get("wv|" + tl + "|" + tu), rw = ru && ru.ok ? ru : [...ST.img.entries()].filter(([k, r]) => k.startsWith("wv|" + tl + "|") && r.ok).map(([, r]) => r).pop();
          if (rw) draw1(tl === "fd" ? 3 : 2, rw.im, geoBox(secOf(tl))); }
        draw1(u, f.im, geoBox(secOf(f.tile))); ST.shown[id] = f.t; continue;
      }
      const unders = undersOf(id, f.tile, f.t);
      if (id === "ir" && unders.some(([tl, tu]) => !underOk(id, tl, tu))) continue;   // wide (west) not decoded: do not paint the detail box alone
      for (const [tl, tu] of unders) { const ru = underOk(id, tl, tu); if (ru) draw1(2, ru.im, () => { const b = SRC[id].tiles[tl].box; gl.uniform1f(U.geo, 0); gl.uniform1f(U.lim, SRC[id].kind === "gibs" ? 0.165 : -2); gl.uniform4f(U.box, b[0], b[1], b[2], b[3]); gl.uniform1f(U.alpha, SRC[id].alpha); }); }
      draw1(u, f.im, () => { const b = SRC[id].tiles[f.tile].box; gl.uniform1f(U.geo, 0); gl.uniform1f(U.lim, SRC[id].kind === "gibs" ? 0.165 : -2); gl.uniform4f(U.box, b[0], b[1], b[2], b[3]); gl.uniform1f(U.alpha, SRC[id].alpha); });
      ST.shown[id] = f.t;
    }
    if (drew) { g.setTransform(1, 0, 0, 1, 0, 0); g.imageSmoothingEnabled = true; g.drawImage(cv, 0, 0); }
    uiTime();
  }

  /* ---- UI: a second chip row under the obs layer chips ---- */
  const CSS = `.obs-root .obs-img{margin-top:-4px}.obs-root .obs-img .oi-sep{width:1px;height:22px;background:var(--o-rule);margin:0 4px}
    .obs-root .obs-img .oi-t{font:12.5px "IBM Plex Mono",ui-monospace,monospace;color:var(--o-muted);white-space:nowrap}
    .obs-root .obs-img input[type=range]{width:min(180px,32vw);accent-color:var(--o-verm)}
    #obsov .obs-img button[aria-pressed="true"],#obsp .obs-img button[aria-pressed="true"],.obs-root .obs-img button[aria-pressed="true"]{background:#f4f2ee;color:#15171c;border-color:#f4f2ee;font-weight:600}
    .obs-root .obs-img button.oi-play{min-width:38px;padding:5px 10px}.obs-root .obs-img .oi-loop{display:contents}.obs-root .obs-img .oi-loop[hidden]{display:none!important}.obs-root .obs-img .oi-spd{display:inline-flex;align-items:center;gap:5px;font-size:12px;opacity:.9;white-space:nowrap}.obs-root .obs-img .oi-spd input{width:80px}.obs-root .obs-img .oi-spd b{min-width:30px;font-weight:700}
    .obs-root .obs-img .oi-lab{font-size:13px;color:var(--o-muted)}
    .obs-root.obs-min #oviews,.obs-root.obs-min #olayers,.obs-root.obs-min .obs-img>:not(.oi-loop),.obs-root.obs-min .obs-img .oi-loop>.oi-sep:first-child{display:none!important}
    .obs-root.obs-min .obs-img{margin-top:0}
    .obs-root .oi-mrow{margin:2px 0 6px}.obs-root .oi-mrow button,#obsov .mg-top #oi-menu{white-space:nowrap}
    #obsov .obs-root.obs-min .obs-stage{height:max(320px,calc(100dvh - 130px));max-height:none}`;
  function mountUi(root) {
    if ($("oimg")) return;
    const st = document.createElement("style"); st.textContent = CSS; document.head.appendChild(st);
    const bar = document.createElement("div"); bar.className = "obs-bar obs-img"; bar.id = "oimg"; bar.setAttribute("role", "group"); bar.setAttribute("aria-label", "Radar and satellite (off by default)");
    bar.innerHTML = `<button type="button" id="oi-radar" aria-pressed="false" title="NWS radar mosaic (MRMS base reflectivity), last 2 hours">Radar</button>
      <span class="oi-sep"></span>
      <span class="oi-lab">Satellite:</span>
      <button type="button" id="oi-ir" aria-pressed="false" title="GOES-West Clean IR (band 13, 10.3 um): cloud-top temperature, day and night. Last 4 hours, about 40-60 min behind">Clean IR</button>
      <button type="button" id="oi-gc" aria-pressed="false" title="GOES-West GeoColor (true color by day, IR at night), last 4 hours, about 40-60 min behind">GeoColor</button>
      <button type="button" id="oi-wv" aria-pressed="false" title="GOES-West mid-level water vapor (band 9, 6.9 um) from NOAA/NESDIS/STAR: moisture around 500 mb (white / green moist, blue drier, yellow dry). Every 5 min (10 min on the wide view), about 5-10 min behind. Last 2 hours (4 hours wide)">Water vapor</button>
      <span class="oi-loop" id="oi-loop" hidden><span class="oi-sep"></span><button type="button" class="oi-play" id="oi-play" aria-label="Pause loop">&#10074;&#10074;</button>
      <input type="range" id="oi-slide" min="0" max="0" value="0" aria-label="Loop frame"><span class="oi-t" id="oi-t"></span><label class="oi-spd" title="Loop speed">Speed <input type="range" id="oi-speed" min="0.25" max="4" step="0.25" value="1" aria-label="Loop speed"><b id="oi-spdv">1x</b></label></span>`;
    const ly = root.querySelector("#olayers"); ly.after(bar);
    $("oi-radar").onclick = () => set({ radar: !ST.radar });
    $("oi-ir").onclick = () => set({ sat: ST.sat === "ir" ? "" : "ir" });
    $("oi-gc").onclick = () => set({ sat: ST.sat === "gc" ? "" : "gc" });
    $("oi-wv").onclick = () => set({ sat: ST.sat === "wv" ? "" : "wv" });
    menuUi(root);
    const pc = root.querySelector(".obs-credit");
    if (pc && !$("oi-credit")) { const p = document.createElement("p"); p.className = "obs-credit"; p.id = "oi-credit";
      p.innerHTML = `Radar: NOAA/NWS NCEP MRMS base reflectivity (public domain). Satellite: NOAA GOES-West (GOES-18) ABI. Clean IR (band 13) and GeoColor via <a href="https://nasa-gibs.github.io/gibs-api-docs/">NASA GIBS</a>/ESDIS; GeoColor imagery: NOAA/NESDIS/STAR, CIRA/NOAA. ${GIBS_ACK} Mid-level water vapor (band 9): <a href="https://www.star.nesdis.noaa.gov/GOES/">NOAA/NESDIS/STAR</a>; NOAA's map lines, logo and time bar are removed so the image sits under this map's own lines. Not an official NOAA or NASA product.`;
      pc.after(p); }
    $("oi-play").onclick = () => { ST.playing = !ST.playing; ui(); tick(); };
    { const sp = $("oi-speed"), sv = $("oi-spdv"); sp.value = String(spd()); sv.textContent = spd() + "x";
      sp.oninput = () => { try { sessionStorage.setItem("oiSpeed", sp.value); } catch (e) { /* private mode */ } sv.textContent = +sp.value + "x"; tick(); }; }
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
    const note = loadNote();
    const txt = ST.glFail || ST.msg || (parts.length ? parts.join(" \u00b7 ") + " PT" + (note ? " \u00b7 " + note : "") : (note || "loading\u2026"));
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

  // 11-04 (Benjamin t2269u "when I refresh ... it refreshes onto the same exact product and view"): radar / satellite choice and the
  // map's zoom / pan are kept for this tab (sessionStorage) and put back after a refresh; frames always load fresh
  const VKEY = { "-121,44,50,47": "pnw", "-122,45,60,52": "west", "-123,46,50,48.5": "salish" };
  let rsDone = false;
  setInterval(() => { const S_ = Obs._state; if (!rsDone || !S_ || !S_.w || !S_.P) return;
    try { sessionStorage.setItem("oiState", JSON.stringify({ radar: ST.radar, sat: ST.sat, view: S_.view, pv: VKEY[S_.P.key] || "", cx: S_.cx, cy: S_.cy, k: S_.k })); } catch (e) { /* private mode */ } }, 1000);
  function restore(n = 0) {
    const S_ = Obs._state; let o = null; try { o = JSON.parse(sessionStorage.getItem("oiState") || "null"); } catch (e) { o = null; }
    if (!o) { rsDone = true; return; }
    if (!n && o.pv && Obs.viewId() !== o.pv) Obs.setView(o.pv);
    if (!S_.w || S_.pending) { if (n < 200) setTimeout(() => restore(n + 1), 100); else rsDone = true; return; }
    if (!o.view && isFinite(o.k) && o.k > 0) { S_.cx = o.cx; S_.cy = o.cy; S_.k = o.k; S_.view = ""; }
    rsDone = true; Obs.redraw();
    if (o.radar || o.sat) set({ radar: !!o.radar, sat: o.sat || "" });
  }
  Obs.hook("mount", () => setTimeout(restore, 0));
  Obs.hook("under", under);
  Obs.hook("mount", mountUi);
  Obs.hook("credit", () => [...on().map((id) => SRC[id].credit), ...(on().some((id) => SRC[id].kind === "gibs") ? [GIBS_ACK] : [])].join(" · "));

  // Studio: credit lines, the shown frame times, and a hold + seek for the MP4 export (loop frames follow the video's progress)
  // 11-04: Studio frames carry only a short GIBS line (NASA asks for acknowledgement); radar (MRMS) and water vapor (STAR) are public
  // domain, so their credit stays on the Observations page / downloads and the site credits, not on the Studio frames
  function credits() { return on().filter((id) => SRC[id].kind === "gibs").map((id) => (id === "gc" ? "Satellite: GOES-West GeoColor (CIRA/NOAA) via NASA GIBS." : "Satellite: NOAA GOES-West via NASA GIBS.")); }
  function info() { return on().map((id) => ({ id, label: PILL[id], t: (ST.shown && ST.shown[id]) || tAt(id, Math.max(0, ST.idx)) })); }
  function hold(h) { ST.hold = !!h; if (!h) tick(); }
  function seek(p) { const L = len(); if (!L) return; ST.idx = Math.max(0, Math.min(L - 1, Math.floor(p * L * 0.999))); bump(); Obs.drawNow(); uiTime(); }
  return { set, state: () => ({ speed: spd(), radar: ST.radar, sat: ST.sat, idx: ST.idx, n: len(), playing: ST.playing, frames: ST.frames, shown: ST.shown, msg: ST.msg, wvMoved: !!ST.wvMoved, drawErr: ST.drawErr || 0, glLost: ST.glLost || 0, glFail: ST.glFail, imgs: ST.img.size, loaded: [...ST.img.values()].filter((r) => r.ok).length }),
    _imgs: () => [...ST.img.entries()].map(([k, r]) => [k, !!r.ok, !!r.bad]), _tile: (id) => tileFor(id),   // test hooks (QA)
    active: () => on().length > 0, credits, info, hold, seek, refresh, ready: () => loading || Promise.resolve() };
})();
