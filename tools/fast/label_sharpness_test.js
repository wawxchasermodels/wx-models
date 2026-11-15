"use strict";
// Static + vm checks for crisp label rendering and Coast font size (t3008u).
// Compared against: refresh_test / layout_test (they check layout and refresh, not font scale
// or whether towns are canvas text vs a baked PNG). This covers those two things only.
const fs = require("fs");
const path = require("path");
const vm = require("vm");
const fail = [];
const check = (c, m) => { if (!c) fail.push(m); };

const root = path.join(__dirname, "site");
const viewer = fs.readFileSync(path.join(root, "viewer.js"), "utf8");
const studio = fs.readFileSync(path.join(root, "studio.js"), "utf8");
const wamaps = fs.readFileSync(path.join(root, "wamaps.js"), "utf8");
const alertJs = fs.readFileSync(path.join(root, "alert/alert.js"), "utf8");
const obs = fs.readFileSync(path.join(__dirname, "../../web/forecast/obs/obs.js"), "utf8");

check(/const COAST_FS = 0\.83/.test(viewer), "COAST_FS must be 0.83 (~17% smaller, in the 15–20% range)");
check(/const PNWT_FS = 0\.83/.test(viewer), "PNWT_FS must stay 0.83");
check(/const PNWHR_FS = 0\.78/.test(viewer), "PNWHR_FS must stay 0.78");
check(/if \(v === "coast"\) return COAST_FS;/.test(viewer), "townFs(coast) must return COAST_FS");
check(/WT\.vid === "wawide" \? WAWIDE_FS : \(WT\.vid === "coast" \? COAST_FS : 1\)/.test(viewer),
  "drawCoast must apply COAST_FS only when the view is coast (not pnwt/wc/wa wave maps)");
check(!/WT\.vid === "wawide" \? WAWIDE_FS : 1, fName/.test(viewer), "drawCoast must not use the unsized fs=1 fallback for every non-wawide view");
check(/window\.__labelSharp/.test(viewer), "render must publish window.__labelSharp for the runtime guard");
check(/ctx\.setTransform\(rs, 0, 0, rs, 0, 0\)/.test(viewer), "viewer must draw at backing scale via setTransform(rs)");
check(/function haloText\(ctx/.test(viewer), "town/coast names must go through haloText (canvas text, not only a PNG)");
const wantFlat = viewer.replace(/\s+/g, " ");
check(/function wantRS\(/.test(viewer) && /if \(Q\.get\("studio"\)\) return Math\.max\(1/.test(wantFlat),
  "Studio wantRS must force a sharp backing store");

const m = viewer.match(/const SITE_LABELS = new Set\(\[([^\]]+)\]\)/);
check(!!m, "SITE_LABELS set is present");
const siteLabels = m ? m[1].match(/"([^"]+)"/g).map(s => s.slice(1, -1)) : [];
check(siteLabels.includes("wc"), "SITE_LABELS must include wc so West Coast cannot fall back to a soft PNG if the data-bucket JSON 404s");
const staticDir = path.join(root, "slayers/static");
const shipped = fs.readdirSync(staticDir).filter(f => /^labels_[\w]+\.json$/.test(f)).map(f => f.slice(7, -5)).sort();
for (const stem of shipped) {
  check(siteLabels.includes(stem), "SITE_LABELS missing shipped labels JSON: " + stem);
}
for (const stem of siteLabels) {
  check(fs.existsSync(path.join(staticDir, "labels_" + stem + ".json")), "SITE_LABELS entry has no shipped JSON: " + stem);
}

check(/ssFit\(F\[k\], REC\.flat \? 1 : PSS\)/.test(studio) && /every Studio frame is 2x/.test(studio),
  "Studio frames must keep the 2x backing (PSS) so cropped labels stay sharp");
check(/function paintStudioTowns\(/.test(studio) && /strokeText\(it\.t/.test(studio),
  "Studio map frames must paint town names as canvas text, not an upscaled towns PNG");
check(/const SC = 2/.test(wamaps), "WA forecast maps must keep 2x backing for titles, town values and credits");
check(/devicePixelRatio/.test(obs) && /city labels stay sharp/.test(obs),
  "Observations must size the canvas by devicePixelRatio so city labels stay sharp");
check(/fillText\(it\.n, it\.tx, it\.ty\)/.test(alertJs), "Active Alerts town names are canvas fillText");

// Run townFs in a stub so the mapping cannot drift from the comments.
function load() {
  const el = () => ({ style: {}, classList: { add() {}, toggle() {}, contains: () => false }, appendChild() {}, innerHTML: "", value: "", options: [], hidden: false, addEventListener() {} });
  const ctx = {
    console, setTimeout: () => 0, clearTimeout() {}, Promise, URL, URLSearchParams, Intl, Math, Date, Number, String, Array, Object, JSON,
    isFinite, Map, Set, RegExp, Error, parseInt, parseFloat, performance: { now: () => 0 },
    requestAnimationFrame: (fn) => 1, matchMedia: () => ({ matches: false, addEventListener() {} }),
    addEventListener() {}, location: { hash: "", search: "", pathname: "/index.html", href: "http://local/index.html" },
    history: { replaceState() {} }, localStorage: { getItem() { return null; }, setItem() {} },
    sessionStorage: { getItem() { return null; }, setItem() {}, removeItem() {} },
    navigator: {}, devicePixelRatio: 2, innerWidth: 1920, innerHeight: 1080, scrollY: 0,
    fetch: () => Promise.resolve({ ok: false, status: 404, text: async () => "", json: async () => { throw new Error("no"); } }),
    document: { getElementById: () => el(), body: el(), createElement: () => el(), addEventListener() {}, fonts: { load: () => Promise.resolve() }, querySelector: () => null, querySelectorAll: () => [] }
  };
  ctx.window = ctx; ctx.document.body.classList = { add() {}, contains: () => false };
  vm.createContext(ctx);
  vm.runInContext(viewer + "\nwindow.__api={townFs,COAST_FS,PNWT_FS,PNWHR_FS,SITE_LABELS};", ctx, { filename: "viewer.js" });
  return ctx;
}
const api = load().__api;
check(api.COAST_FS === 0.83, "runtime COAST_FS is 0.83, got " + api.COAST_FS);
check(api.townFs("coast") === 0.83, "townFs(coast) is 0.83, got " + api.townFs("coast"));
check(api.townFs("pnwt") === 0.83, "townFs(pnwt) unchanged");
check(api.townFs("pnwhr") === 0.78, "townFs(pnwhr) unchanged");
for (const v of ["wa", "wwa", "puget", "ewa", "passes", "newa", "lm", "bc", "pnw", "na", "wc", "wawide", ""]) {
  check(api.townFs(v) === 1, "townFs(" + (v || "empty") + ") must stay 1, got " + api.townFs(v));
}
check(api.SITE_LABELS.has("wc") && api.SITE_LABELS.has("wa") && api.SITE_LABELS.has("pnwt"), "runtime SITE_LABELS has wc, wa, pnwt");


// Washington Wide camera (11-15 t3093u): 10–15 % wider E-W than the previous Wide (that
// previous camera was 7.5 % more area than Washington), same center. Mid = 12.5 %.
// Compared against: layout_test / refresh_test (they open the wawide menu entry but do not
// pin the visible area or the 16:9 66 %-width / 27 % left-shift camera).
check(/const WAWIDE_EW = 1\.125/.test(studio), "WAWIDE_EW must be 1.125 (12.5 % wider E-W than the previous Wide, mid of 10–15 %)");
check(/const WAWIDE_AREA = window\.__WAWIDE_AREA = 1\.075 \* WAWIDE_EW \* WAWIDE_EW/.test(studio.replace(/\s+/g, " ")),
  "WAWIDE_AREA must be 1.075 * WAWIDE_EW * WAWIDE_EW");
const wawideArea = 1.075 * 1.125 * 1.125;
check(1.075 * 1.10 * 1.10 <= wawideArea && wawideArea <= 1.075 * 1.15 * 1.15,
  "WAWIDE_AREA stays inside the 10–15 % E-W-wider band");
check(/function waPanelFromState\(/.test(studio), "wawide camera must rebuild the Washington panel from the state box");
check(/k0 = Math\.max\(f\.W \/ pan\.w, f\.H \/ pan\.h\) \/ Math\.sqrt\(WAWIDE_AREA\)/.test(studio.replace(/\s+/g, " ")) ||
      /Math\.max\(f\.W \/ pan\.w, f\.H \/ pan\.h\) \/ Math\.sqrt\(WAWIDE_AREA\)/.test(studio),
  "wawide k0 must be the Washington cover-fit zoomed out by sqrt(WAWIDE_AREA), same panel center");
check(!/0\.66 \* f\.W \/ t\.w/.test(studio) && !/xl = V\.fit \? 0\.27 \* f\.W/.test(studio) && !/0\.84 \* f\.W \/ t\.w/.test(studio),
  "old loose wawide framing (66 % / 27 % shift / 84 % width) must not remain");
check(/window\.__wawideCam = \(\) =>/.test(studio), "studio must expose __wawideCam so the extent guard can read the live base() camera");
check(/typ = Math\.max\(f\.W \/ wp\[2\], f\.H \/ wp\[3\]\) \/ kk/.test(studio.replace(/\s+/g, " ")),
  "paintStudioTowns must scale Wide labels to the Washington view's on-screen size");


if (fail.length) {
  fail.forEach(m => console.log("FAIL " + m));
  console.log("label_sharpness_test: FAILS " + fail.length);
  process.exit(1);
}
console.log("label_sharpness_test: PASS");
