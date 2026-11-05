"use strict";
const fs = require("fs");
const path = require("path");
const vm = require("vm");
const fail = [];
const check = (c, m) => { if (!c) fail.push(m); };
let checksDone = false;
process.on("unhandledRejection", (e) => {
  if (!checksDone) { console.error(e); process.exit(1); }
  console.log("stub page boot stopped after the checks: " + (e && e.message));
  process.exit(fail.length ? 1 : 0);
});

function load(search) {
  const canvases = [];
  function canvas() {
    const calls = [];
    const ctx = {
      setTransform() {}, fillRect() {}, fillText() {}, strokeRect() {},
      measureText: () => ({ width: 40 }), save() {}, restore() {}, beginPath() {},
      drawImage(...a) { calls.push(a); },
      fillStyle: "", font: "", textAlign: "", textBaseline: "", strokeStyle: "", lineWidth: 1
    };
    const c = { width: 100, height: 100, style: {}, calls, getContext: () => ctx };
    canvases.push(c); return c;
  }
  function el() {
    return { style: {}, classList: { add() {}, toggle() {}, contains: () => false }, appendChild() {}, innerHTML: "", value: "", options: [], hidden: false, addEventListener() {} };
  }
  const ids = { map: canvas(), wrap: el(), bar: el(), dock: el(), step: el(), run: el(), prod: el(), view: el() };
  const ctx = {
    console, setTimeout: () => 0, clearTimeout() {}, Promise, URL, URLSearchParams, Intl, Math, Date, Number, String, Array, Object, JSON,
    isFinite, Map, Set, RegExp, Error, parseInt, parseFloat, performance: { now: () => 0 },
    requestAnimationFrame: (fn) => (fn && fn(), 1), matchMedia: () => ({ matches: false, addEventListener() {} }),
    addEventListener() {}, location: { hash: "", search, pathname: "/index.html", href: "http://local/index.html" + search },
    history: { replaceState() {} }, localStorage: { getItem() { return null; }, setItem() {} },
    sessionStorage: { getItem() { return null; }, setItem() {}, removeItem() {} },
    navigator: {}, devicePixelRatio: 1, innerWidth: 1400, innerHeight: 900, scrollY: 0,
    fetch: () => Promise.resolve({ ok: false, status: 404, text: async () => "not found", json: async () => { throw new SyntaxError("not found"); } }),
    document: {
      getElementById: (id) => ids[id] || null, body: el(), createElement: (t) => t === "canvas" ? canvas() : el(),
      addEventListener() {}, fonts: { load: () => Promise.resolve() }, querySelector: () => null, querySelectorAll: () => []
    }
  };
  ctx.window = ctx; ctx.document.body.classList = { add() {}, contains: () => false };
  vm.createContext(ctx);
  vm.runInContext(fs.readFileSync(path.join(__dirname, "site/viewer.js"), "utf8") + "\nwindow.__api={addStudioViews,coastShown,showCoast};\n", ctx, { filename: "viewer.js" });
  return ctx;
}

const coastS = { label: "Coast view", fig: [1400, 1250], fit: [100, 80, 1100, 618], fitV: [200, 40, 400, 900], studioCoast: true, studioOnly: true, lut: "static/lut_ifs_coast_s.bin", towns: [{ name: "Westport" }, { name: "Ocean Shores" }], panel: [40, 40, 1320, 1160] };
const sv = { models: {
  ifs: { coast_s: coastS, coast_t: { label: "old", fit: [0, 0, 50, 50], studioCoast: true } },
  gfs: { coast_t: { label: "Coast view", fig: [1400, 1250], fit: [10, 20, 900, 500], studioCoast: true, towns: [{ name: "Westport" }] } },
  gfsw: { coast_s: Object.assign({}, coastS, { lut: "static/lut_gfsw_coast_s.bin" }) },
  oisst: { coast_s: Object.assign({}, coastS, { lut: "static/lut_oisst_coast_s.bin" }) }
}};
function man() {
  const view = () => ({ wa: { label: "Washington" }, pnwt: { label: "Pacific NW tight" }, pnw: { label: "Pacific Northwest" } });
  const hi = () => ({ wa: { label: "Washington" }, pnwhr: { label: "Pacific NW" } });
  return { models: { ifs: { name: "ECMWF IFS", views: view() }, gfs: { name: "GFS", views: view() }, gfsw: { name: "NOAA WW3", views: view() }, oisst: { name: "OISST", views: view() }, hrrr: { name: "HRRR", views: hi() }, rrfs: { name: "RRFS", views: hi() }, nbm: { name: "NBM", views: hi() } }, style: { BG: "#111", INK: "#fff", ACCENT: "#fc0", MUTED: "#aaa" } };
}

const reg = load("");
const M = man();
reg.__api.addStudioViews(M, sv);
check(M.models.ifs.views.coast && M.models.ifs.views.coast.label === "Coast view", "regular IFS View option is Coast view");
check(M.models.ifs.views.coast.base_png === "static/base_coast_s.png", "active file is coast_s, got " + (M.models.ifs.views.coast && M.models.ifs.views.coast.base_png));
check(M.models.ifs.views.coast.lut === "static/lut_ifs_coast_s.bin", "IFS keeps its coast_s LUT");
check((M.models.ifs.views.coast.towns || []).some((t) => t.name === "Westport"), "Westport stays on the coast town list");
check(Object.keys(M.models.ifs.views).slice(0, 3).join(",") === "wa,coast,pnwt", "Coast sits after Washington: " + Object.keys(M.models.ifs.views).join(","));
check(!M.models.ifs.views.wawide && !M.models.hrrr.views.wawide, "regular page does not add the Studio wide view");
check(!M.models.hrrr.views.coast && !M.models.rrfs.views.coast && !M.models.nbm.views.coast, "HRRR RRFS NBM are not offered a coast view");
check(M.models.gfs.views.coast.base_png === "static/base_coast_t.png", "coast_t is the fallback when coast_s is absent");
check(M.models.gfsw.views.coast && M.models.oisst.views.coast, "models that have a coast entry are listed");
check(!M.models.ifs.views.wc, "wave-only wc is not this view");
const menu = Object.entries(M.models.ifs.views).filter(([, v]) => !v.waveOnly).map(([, v]) => v.label);
check(menu.includes("Coast view") && menu.includes("Washington") && !menu.includes("Washington (wide, for loops)"), "View menu text: " + menu.join(" | "));

const shown = reg.__api.coastShown(M.models.ifs.views.coast);
check(shown && shown.w === 1100 && shown.h === 618 && shown.x === 100 && shown.y === 80, "regular camera is fit, not fitV: " + JSON.stringify(shown));
check(shown.h !== 900, "9:16 fitV is not the regular camera");
const cv = reg.document.getElementById("map");
cv.width = 2800; cv.height = 2500; cv._rs = 2; cv._lw = 1400; cv._lh = 1250;
reg.__S.man = M; reg.__S.run = "ifs/2026110512";
const P = { title: "2 m temperature", levels: [0, 10, 20], colors: ["#112233", "#445566"], ticks: [0, 20], key: "Temperature (°F)", extra: "" };
check(reg.__api.showCoast(cv, M.models.ifs.views.coast, { title: P.title, valid: "Valid Thu 12 PM", sub: "IFS  ·  Coast view", badge: ["18", "F+"], P, pid: "t2m", towns: true }) === true, "showCoast draws");
const crop = cv.calls.filter((a) => a.length === 9)[0];
check(crop && crop[1] === 200 && crop[2] === 160 && crop[3] === 2200 && crop[4] === 1236, "source rect is fit x rs: " + JSON.stringify(crop && crop.slice(1, 5)));
check(crop && crop[5] === 0 && crop[6] === shown.head && crop[7] === 1100 && crop[8] === 618, "dest is the fit box under the header: " + JSON.stringify(crop && crop.slice(5)));
check(crop && Math.abs(crop[7] / crop[8] - crop[3] / crop[4]) < 1e-9, "blit keeps aspect");
check(cv._lw === shown.W && cv._lh === shown.H && cv._lw / cv._lh !== 1400 / 1250, "page box is the camera plus bands, not the whole source figure");
const plain = { width: 1600, height: 1000, _rs: 1, _lw: 1600, _lh: 1000, style: {}, calls: [], getContext() { return { setTransform() {}, drawImage() {}, fillRect() {}, fillText() {} }; } };
check(reg.__api.showCoast(plain, M.models.ifs.views.wa, { P, pid: "t2m" }) === false && plain.width === 1600, "Washington and other views are not cropped");
check(reg.__api.coastShown({ studioCoast: true, fitV: [0, 0, 400, 900] }) === null, "a coast entry without fit is not shown");

const st = load("?studio=1");
const Ms = man();
st.__api.addStudioViews(Ms, sv);
check(Object.keys(Ms.models.ifs.views).slice(0, 4).join(",") === "wa,wawide,coast,pnwt", "Studio order stays wide then coast: " + Object.keys(Ms.models.ifs.views).join(","));
check(Ms.models.hrrr.views.wawide && !Ms.models.hrrr.views.coast, "Studio still has HRRR wide view and still no HRRR coast");
check(st.__api.coastShown(Ms.models.ifs.views.coast) === null, "Studio does not use the regular crop");
const scv = { width: 1400, height: 1250, _lw: 1400, _lh: 1250, style: {}, calls: [], getContext() { return { drawImage() {} }; } };
check(st.__api.showCoast(scv, Ms.models.ifs.views.coast, {}) === false && scv.width === 1400, "Studio canvas is left whole for its own camera");

console.log(JSON.stringify({ fails: fail, regularViews: Object.keys(M.models.ifs.views), menu, camera: shown }, null, 2));
checksDone = true;
if (fail.length) process.exit(1);
