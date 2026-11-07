"use strict";
const fs = require("fs");
const path = require("path");
const vm = require("vm");
const fail = [];
const check = (c, m) => { if (!c) fail.push(m); };
let checksDone = false;
process.on("unhandledRejection", (e) => {
  if (!checksDone) { console.error("unhandled", e); process.exit(1); }
  console.log("stub boot after checks: " + (e && e.message));
  process.exit(fail.length ? 1 : 0);
});

const ctx2d = new Proxy({
  font: "", fillStyle: "", strokeStyle: "", lineWidth: 1, textAlign: "left", textBaseline: "top", globalAlpha: 1,
  measureText: () => ({ width: 40 }),
  setLineDash() {}, save() {}, restore() {}, beginPath() {}, moveTo() {}, lineTo() {}, stroke() {}, fill() {},
  fillRect() {}, fillText() {}, arc() {}, translate() {}, rotate() {}, closePath() {}, rect() {}, clip() {}
}, { get: (t, k) => k in t ? t[k] : () => {} });
function el(tag) {
  return {
    tag, style: {}, children: [], id: "", hidden: false, className: "", clientWidth: 1800, clientHeight: 960,
    appendChild(c) { this.children.push(c); return c; }, setAttribute(k, v) { this[k] = v; },
    addEventListener() {}, getContext: () => ctx2d, classList: { add() {}, toggle() {}, contains: () => false },
    getBoundingClientRect: () => ({ left: 0, top: 0, width: 1800, height: 960 }),
    querySelector: () => null, querySelectorAll: () => []
  };
}
const body = el("body");
const ids = {};
["step", "run", "prod", "view", "loadnote", "map", "wrap", "bar", "dock", "err"].forEach((id) => { ids[id] = el(id); ids[id].value = ""; ids[id].options = []; });
const files = {};
function hours(n, big) {
  const steps = [], d = [];
  for (let f = 0; f <= n; f++) {
    steps.push({ f, valid: new Date(Date.UTC(2026, 10, 5, 12 + f)).toISOString(), ranges: {} });
    const pcp = big ? f * 4 : f * 0.01;
    d.push({ t2m: [30, 55], u10: [2, 2], v10: [1, 1], gust: [8, 8], apcp: [pcp, pcp * 0.2], tcc: [40, 50] });
  }
  return { steps, d, f: steps.map((s) => s.f) };
}
const low = hours(12, false), high = hours(12, true);
files["/d/manifest.json"] = { status: 200, body: JSON.stringify({ models: { ifs: { site: "ECMWF", views: { wa: { fig: [100, 80] } }, products: {} } }, runs: { ifs: ["2026110512"] }, style: { BG: "#111", INK: "#fff", ACCENT: "#fc0", MUTED: "#aaa" } }) };
files["/d/missing.json"] = { status: 404, body: "not found" };
files["/d/runs/ifs/2026110512/run.json"] = { status: 200, body: JSON.stringify({ points: [{ n: "Stevens", k: "pass", c: 0 }, { n: "Seattle", k: "town", c: 0 }], steps: low.steps, fields: ["t2m", "u10", "v10", "gust", "apcp", "tcc"], agg: ["pts"], init: "2026-11-05T12:00:00Z", base: "runs/ifs/2026110512/", file: "{name}_{f:03d}.png", runline: "IFS 12Z", complete: true }) };
files["/d/runs/ifs/2026110512/single/pts_all.json"] = { status: 200, body: JSON.stringify({ f: low.f, d: low.d }) };
files["/d/runs/ifs/2026110518/run.json"] = { status: 200, body: JSON.stringify({ points: [{ n: "Stevens", k: "pass", c: 0 }, { n: "Seattle", k: "town", c: 0 }], steps: high.steps.slice(0, 4), fields: ["t2m", "u10", "v10", "gust", "apcp", "tcc"], agg: ["pts"], init: "2026-11-05T18:00:00Z", base: "runs/ifs/2026110518/", file: "x", runline: "IFS 18Z", complete: false }) };
files["/d/runs/ifs/2026110518/single/pts_all.json"] = { status: 200, body: JSON.stringify({ f: high.f.slice(0, 4), d: high.d.slice(0, 4) }) };
files["/d/runs/ifs/2026110518b/run.json"] = { status: 200, body: JSON.stringify({ points: [{ n: "Stevens", k: "pass", c: 0 }], steps: high.steps, fields: ["t2m", "apcp", "tcc", "u10", "v10", "gust"], agg: ["pts"], init: "2026-11-05T18:00:00Z", base: "x", file: "x", runline: "IFS", complete: true }) };
files["/d/runs/ifs/2026110518b/single/pts_all.json"] = { status: 200, body: JSON.stringify({ f: high.f, d: high.d }) };
function stepped(id, step, n, pcpStep) {
  const steps = [], d = [];
  for (let i = 0; i <= n; i++) {
    const f = i * step;
    steps.push({ f, valid: new Date(Date.UTC(2026, 10, 6, f)).toISOString(), ranges: {} });
    const pcp = +(i * pcpStep).toFixed(3);
    d.push({ t2m: [30, 55], u10: [1, 1], v10: [1, 1], gust: [5, 5], apcp: [pcp, pcp * 0.2], tcc: [20, 30] });
  }
  files["/d/runs/" + id + "/run.json"] = { status: 200, body: JSON.stringify({ points: [{ n: "Stevens", k: "pass", c: 0 }, { n: "Seattle", k: "town", c: 0 }], steps, fields: ["t2m", "u10", "v10", "gust", "apcp", "tcc"], agg: ["pts"], init: "2026-11-06T00:00:00Z", base: "runs/" + id + "/", file: "x", runline: id, complete: true }) };
  files["/d/runs/" + id + "/single/pts_all.json"] = { status: 200, body: JSON.stringify({ f: steps.map((s) => s.f), d }) };
}
stepped("gfs/2026110600", 3, 8, 0.2);
stepped("aifs/2026110600", 6, 6, 0.15);
files["/d/runs/ifs9/2026110506/run.json"] = { status: 200, body: JSON.stringify({ points: [], steps: [{ f: 0, valid: "2026-11-05T06:00:00Z", ranges: {} }], fields: [], init: "2026-11-05T06:00:00Z", file: "x", runline: "IFS 9 km", complete: true }) };

const ctx = {
  console, setTimeout: () => 0, clearTimeout() {}, Promise, URL, URLSearchParams, Intl, Math, Date, Number, String, Array, Object, JSON,
  isFinite, Map, Set, RegExp, Error, SyntaxError, parseInt, parseFloat, performance: { now: () => 0 },
  requestAnimationFrame: (fn) => (fn && fn(), 1), matchMedia: () => ({ matches: false, addEventListener() {} }),
  addEventListener() {}, location: { hash: "", search: "", pathname: "/index.html", href: "http://local/index.html" },
  history: { replaceState() {} }, localStorage: { getItem() { return null; }, setItem() {} },
  sessionStorage: { getItem() { return null; }, setItem() {}, removeItem() {} },
  navigator: {}, devicePixelRatio: 1, innerWidth: 1400, innerHeight: 900, scrollY: 0,
  fetch(url) {
    const key = String(url).replace(/^https?:\/\/[^/]+/, "");
    const rec = files[key] || { status: 404, body: "not found" };
    ctx.fetched.push(key);
    return Promise.resolve({ ok: rec.status === 200, status: rec.status, text: async () => rec.body, json: async () => JSON.parse(rec.body) });
  },
  document: { getElementById: (id) => ids[id] || null, body, createElement: el, addEventListener() {}, fonts: { load: () => Promise.resolve() }, querySelector: () => null, querySelectorAll: () => [] },
  fetched: [], WX_DATA: "/d/"
};
ctx.window = ctx;
ctx.document.body.classList = { add() {}, contains: () => false };
vm.createContext(ctx);
vm.runInContext(fs.readFileSync(path.join(__dirname, "site/viewer.js"), "utf8") + "\nwindow.__api={readJSON,loadRun,refreshKeepsRun,studioPassChart};\n", ctx, { filename: "viewer.js" });

(async () => {
  let threw = null;
  try { await ctx.__api.readJSON("/d/missing.json"); } catch (e) { threw = e; }
  check(threw && !(threw instanceof SyntaxError) && /HTTP 404/.test(threw.message) && /missing\.json/.test(threw.message), "404 not found is an HTTP error: " + (threw && threw.message));
  const good = await ctx.__api.readJSON("/d/manifest.json");
  check(good.runs.ifs[0] === "2026110512", "valid manifest JSON still loads");
  const run = await ctx.__api.loadRun("ifs/2026110512");
  check(Array.isArray(run.steps) && run.steps.length === 13, "valid run keeps its hours");
  let missing = null;
  try { await ctx.__api.loadRun("ifs/1999010100"); } catch (e) { missing = e; }
  check(missing && /HTTP 404/.test(missing.message) && !ctx.__S.runs["ifs/1999010100"], "failed run is not stored");

  const oldSteps = []; for (let f = 0; f <= 36; f++) oldSteps.push({ f, valid: new Date(Date.UTC(2026, 10, 5, 12 + f)).toISOString() });
  const partial = high.steps.slice(0, 4);
  const keep = ctx.__api.refreshKeepsRun("ifs/2026110512", "ifs/2026110518", "36", null, (r) => r.endsWith("18") ? partial : oldSteps);
  check(keep === "ifs/2026110512", "partial newest run does not replace an hour it does not have: " + keep);
  const full = []; for (let f = 0; f <= 48; f++) full.push({ f, valid: new Date(Date.UTC(2026, 10, 5, 18 + f)).toISOString() });
  const roll = ctx.__api.refreshKeepsRun("ifs/2026110512", "ifs/2026110518b", "36", null, (r) => r.endsWith("18b") ? full : oldSteps);
  check(roll === "ifs/2026110518b", "newest run that has the hour is used: " + roll);

  ctx.__S.man = { models: { ifs: { site: "ECMWF" }, gfs: { site: "GFS" }, aifs: { site: "AIFS" }, ifs9: { site: "ECMWF 9 km" } }, style: { BG: "#111", INK: "#fff", ACCENT: "#fc0", MUTED: "#aaa" }, runs: { ifs9: ["2026110206", "2026110506"] } };
  const lowChart = await ctx.studioPassChart("ifs/2026110512", "Stevens", 1800, 960);
  check(lowChart && ["temp", "wind", "pcp", "snow", "cloud"].every((k) => lowChart.panels.includes(k)), "pass chart draws the five panels " + JSON.stringify(lowChart && lowChart.panels));
  check(lowChart.pcp >= 3 && lowChart.snow >= 12, "low pass floors " + JSON.stringify(lowChart));
  check(ctx.__mgAxisInfo.studio_h === lowChart, "studio_h is the drawn chart");
  const highChart = await ctx.studioPassChart("ifs/2026110518b", "Stevens", 1800, 960);
  check(highChart.pcp > 3, "high precip axis grows, got " + (highChart && highChart.pcp));
  const town = await ctx.studioPassChart("ifs/2026110512", "Seattle", 1800, 960);
  check(town.pcp < 3, "town precip is not forced to 3, got " + (town && town.pcp));
  const gfs = await ctx.studioPassChart("gfs/2026110600", "Stevens", 1800, 960);
  check(gfs.step === 3 && gfs.pcp >= 3 && gfs.snow >= 12, "3 h pass still floors precip at 3 and snow at 12: " + JSON.stringify(gfs));
  const aifs = await ctx.studioPassChart("aifs/2026110600", "Stevens", 1800, 960);
  check(aifs.step === 6 && aifs.pcp >= 3 && aifs.snow >= 12, "6 h pass still floors precip at 3 and snow at 12: " + JSON.stringify(aifs));
  const town6 = await ctx.studioPassChart("aifs/2026110600", "Seattle", 1800, 960);
  check(town6.pcp < 3, "6 h town precip is not forced to 3, got " + (town6 && town6.pcp));
  const listed = await ctx.loadListed(["ifs9/2026110206", "ifs9/2026110506"]);
  check(listed.run === "ifs9/2026110506", "missing listed run falls forward, got " + (listed && listed.run));
  check(!ctx.__S.runs["ifs9/2026110206"] && ctx.__S._gone && ctx.__S._gone.has("ifs9/2026110206"), "404 run is not stored");
  check(ctx.fetched.includes("/d/runs/ifs9/2026110206/run.json"), "the missing run.json is the request");
  check(ctx.MG_FLOORS.passPrecipIn === 3 && ctx.MG_FLOORS.passSnow6In === 12, "MG_FLOORS keys");
  const mg = fs.readFileSync(path.join(__dirname, "site/meteograms.js"), "utf8");
  check(mg.includes("passPrecipIn: 3") && mg.includes("passSnow6In: 12") && mg.includes("MG_FLOORS_MG") && !/window\.studioPassChart/.test(mg) && !mg.includes("every === 1 ? MG_FLOORS"), "meteograms floors match for every step length");
  const st = fs.readFileSync(path.join(__dirname, "site/studio.js"), "utf8");
  check(/window\.__pfChart = async/.test(st) && st.includes("studioPassChart(run, name, 1800, 960)") && st.includes("pfOpen(name)"), "__pfChart opens the same drawn chart");
  check(fs.readFileSync(path.join(__dirname, "site/viewer.js"), "utf8").includes("MG.run = r"), "pass row click keeps the run");
  console.log(JSON.stringify({ fails: fail, low: lowChart, highPcp: highChart.pcp, townPcp: town.pcp, gfs: gfs, aifs: aifs, town6: town6.pcp, listed: listed.run }, null, 2));
  checksDone = true;
  if (fail.length) process.exit(1);
})().catch((e) => { console.error(e); process.exit(1); });
