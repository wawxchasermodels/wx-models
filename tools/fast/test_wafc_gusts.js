"use strict";
// Change-scoped checks for the West-view gust menu and Studio WA-forecast framing.
// Run: node tools/fast/test_wafc_gusts.js
const fs = require("fs");
const path = require("path");
const vm = require("vm");
const assert = require("assert");

const ROOT = __dirname;
const wamaps = fs.readFileSync(path.join(ROOT, "site/wamaps.js"), "utf8");
const studio = fs.readFileSync(path.join(ROOT, "site/studio.js"), "utf8");
const html = fs.readFileSync(path.join(ROOT, "site/studio.html"), "utf8");
const enc = fs.readFileSync(path.join(ROOT, "fast_encode.py"), "utf8");
const yml = fs.readFileSync(path.join(ROOT, "../../.github/workflows/fast-models.yml"), "utf8");

function extractFn(src, name) {
  const token = `function ${name}`;
  const i = src.indexOf(token);
  if (i < 0) throw new Error("missing " + name);
  let j = src.indexOf("{", i), d = 0, inS = null, esc = false, inLine = false, inBlock = false;
  for (; j < src.length; j++) {
    const c = src[j], n = src[j + 1];
    if (inLine) { if (c === "\n") inLine = false; continue; }
    if (inBlock) { if (c === "*" && n === "/") { inBlock = false; j++; } continue; }
    if (inS) { if (esc) { esc = false; continue; } if (c === "\\") { esc = true; continue; } if (c === inS) inS = null; continue; }
    if (c === "/" && n === "/") { inLine = true; continue; }
    if (c === "/" && n === "*") { inBlock = true; continue; }
    if (c === '"' || c === "'" || c === "`") { inS = c; continue; }
    if (c === "{") d++;
    else if (c === "}") { d--; if (d === 0) return src.slice(i, j + 1); }
  }
  throw new Error("unclosed " + name);
}

global.ptHr = (ms) => ({ 0: "2 PM", 1: "11 PM" })[ms];
vm.runInThisContext([extractFn(wamaps, "gustModels"), extractFn(wamaps, "gustSteps"), extractFn(wamaps, "gustWindowLabel")].join("\n"));
const gust = global;

// West gust menu: HRRR and standard NBM only. Full / east keep EPS and IFS.
assert.deepStrictEqual(gust.gustModels("west", ["nbm", "ifs9", "ifs", "eps", "hrrr"]), ["nbm", "hrrr"]);
assert.deepStrictEqual(gust.gustModels("full", ["nbm", "ifs", "eps", "hrrr"]), ["nbm", "ifs", "eps", "hrrr"]);
assert.deepStrictEqual(gust.gustModels("east", ["eps", "hrrr"]), ["eps", "hrrr"]);
assert.ok(!gust.gustModels("west", ["nbm", "ifs", "eps", "hrrr"]).includes("eps"));
assert.ok(wamaps.includes('["gust", "Max gust"]'));
assert.strictEqual(gust.gustWindowLabel({ ms0: 0, ms1: 1, day: "Friday", md: "11-7" }), "Max gust over 2 PM to 11 PM Friday 11-7");

// Missing hours are skipped. NBM after F036 is 3-hourly but the gust is instantaneous, so a valid hour stays in the max.
const hole = [{ f: 1 }, { f: 2 }, { f: 4 }, { f: 5 }];
assert.deepStrictEqual(gust.gustSteps(hole, 1, 5, true), [1, 2, 4, 5]);
const nbm3 = [{ f: 36 }, { f: 39 }, { f: 42 }];
assert.deepStrictEqual(gust.gustSteps(nbm3, 37, 42, true), [39, 42]);
assert.deepStrictEqual(gust.gustSteps(nbm3, 37, 42, false), [42]);   // IFS / EPS period rule is unchanged
assert.deepStrictEqual(gust.gustSteps([{ f: 1 }, { f: 2 }, { f: 3 }], 10, 12, true), [3]);   // window not reached: last step
assert.deepStrictEqual(gust.gustSteps([{ f: 1 }, { f: 2 }, { f: 15 }], 10, 12, true), [15]);   // next step at or after the end
assert.deepStrictEqual(gust.gustSteps([], 1, 5, true), []);

// Town summary groups for the west view are still the ones the map labels.
assert.ok(wamaps.includes('["Puget Sound", ["Seattle", "Tacoma", "Everett", "Bellevue", "Olympia", "Bellingham", "Federal Way", "Mount Vernon"]]'));
assert.ok(wamaps.includes('["coast", ["Aberdeen", "Ocean Shores", "Westport", "Long Beach", "Forks", "Neah Bay", "Raymond", "Ilwaco", "La Push"]]'));

// NBM and HRRR gusts are already encoded on the automatic cycle. No second field, no re-encode.
assert.ok(enc.includes('"gust": (_nbm("GUST:10 m above ground"'));
assert.ok(enc.includes('return np.asarray(R.f("gust")[2], float) * 2.23694'));
assert.ok(/model:\s*\[[^\]]*nbm/.test(yml));
assert.ok(yml.includes("hrrr,rrfs,nbm,gfs,ifs,aifs"));

// Studio: zoom slider stays visible for wafc; pass and alerts still hide theirs.
assert.ok(!/wafcmode \.shd input/.test(html));
assert.ok(!/wafcmode \.shint/.test(html));
assert.ok(/wafcmode \.shd button\[data-a="mp4"\]/.test(html));
assert.ok(/passmode \.shd input/.test(html));
assert.ok(/alertmode \.shd input/.test(html));
assert.ok(html.includes("touch-action:manipulation"));
assert.ok(studio.includes("2160x3840"));
assert.ok(studio.includes("3840x2160"));
assert.ok(/fr\.zoom = Math\.max\(1, f\.zoom\.value \/ 100\)/.test(studio));
assert.ok(/setFr\(k, \{ dx: 0, dy: 0, zoom: 1 \}\)/.test(studio));
assert.ok(studio.includes("WAFCM() && MG.img"));
assert.ok(studio.includes('const MG_KINDS = ["obs", "pass", "wafc", "alert", "cmp", "web"]'));
assert.ok(studio.includes("const CMPM = () => MG.on && MG.kind === \"cmp\""));
assert.ok(studio.includes("const WEBM = () => MG.on && MG.kind === \"web\""));
assert.ok(studio.includes("const ALERT_ZMIN = 1 / 1.5"));
assert.ok(/const key = \(k\) => `studio:\$\{k\}:\$\{MG\.on \? MG\.kind : S\.view\}`/.test(studio));

function makeCv() {
  const calls = [];
  return { width: 0, height: 0, calls, getContext() { return {
    setTransform() {}, clearRect() {}, fillRect() {}, fillText() {},
    drawImage(...a) { calls.push(a); },
    font: "", fillStyle: "", textAlign: "", imageSmoothingEnabled: false, imageSmoothingQuality: "",
  }; } };
}
const F = {
  v: { W: 1080, H: 1920, pad: 64, cv: makeCv(), zoom: { min: "", value: "" } },
  h: { W: 1920, H: 1080, pad: 56, cv: makeCv(), zoom: { min: "", value: "" } },
};
const frame = vm.createContext({
  F, PSS: 2, BG: "#111316", window: {}, console,
  MG: { on: true, kind: "wafc", img: { width: 1600, height: 2400 }, msg: "" },
});
vm.runInContext(`
const IW = (im) => im.naturalWidth || im.width, IH = (im) => im.naturalHeight || im.height;
const WAFCM = () => MG.on && MG.kind === "wafc";
const WEBM = () => false;
const OBSM = () => false, ALERTM = () => false;
const store = {};
const localStorage = { getItem: (k) => (k in store ? store[k] : null), setItem: (k, v) => { store[k] = v; } };
const key = (k) => "studio:" + k + ":" + (MG.on ? MG.kind : "map");
const getFr = (k) => Object.assign({ dx: 0, dy: 0, zoom: 1 }, JSON.parse(localStorage.getItem(key(k)) || "{}"));
const setFr = (k, fr) => { localStorage.setItem(key(k), JSON.stringify(fr)); };
this.store = store; this.getFr = getFr; this.setFr = setFr; this.key = key;
${extractFn(studio, "ssFit")}
${extractFn(studio, "mgBase")}
${extractFn(studio, "base")}
${extractFn(studio, "crop")}
${extractFn(studio, "renderWafc")}
`, frame);

frame.renderWafc("v");
frame.renderWafc("h");
assert.strictEqual(F.v.cv.width, 2160);
assert.strictEqual(F.v.cv.height, 3840);
assert.strictEqual(F.h.cv.width, 3840);
assert.strictEqual(F.h.cv.height, 2160);
assert.strictEqual(F.v.zoom.value, 100);
const fit = F.v.cv.calls.at(-1);
const k0 = Math.min(1080 / 1600, 1920 / 2400);
assert.ok(Math.abs(fit[1] - (1080 / 2 - 800 * k0)) < 1e-6);
assert.ok(Math.abs(fit[2] - (1920 / 2 - 1200 * k0)) < 1e-6);
assert.ok(Math.abs(fit[3] - 1600 * k0) < 1e-6);
assert.ok(Math.abs(fit[4] - 2400 * k0) < 1e-6);

// Zoom and drag stick per frame, and a reload reads them back. The other frame is left alone.
frame.setFr("v", { dx: 0, dy: 0, zoom: 2 });
frame.renderWafc("v");
assert.strictEqual(F.v.zoom.value, 200);
const z2 = F.v.cv.calls.at(-1);
assert.ok(Math.abs(z2[3] - 1600 * k0 * 2) < 1e-6);
const fr = frame.getFr("v");
fr.dx += 180; fr.dy += -40;
const r = frame.crop("v", fr);
fr.dx = (r.bx - r.cx) * r.kk; fr.dy = (r.by - r.cy) * r.kk;
frame.setFr("v", fr);
frame.renderWafc("v");
const panned = F.v.cv.calls.at(-1);
assert.ok(Math.abs(panned[1] - z2[1]) > 1);
assert.strictEqual(frame.getFr("h").zoom, 1);
assert.strictEqual(frame.getFr("h").dx, 0);
const again = JSON.parse(frame.store[frame.key("v")]);
assert.strictEqual(again.zoom, 2);
assert.ok(Math.abs(again.dx - fr.dx) < 1e-6);

frame.setFr("v", { dx: 0, dy: 0, zoom: 1 });
frame.renderWafc("v");
const reset = F.v.cv.calls.at(-1);
assert.ok(Math.abs(reset[1] - fit[1]) < 1e-6);
assert.ok(Math.abs(reset[2] - fit[2]) < 1e-6);
assert.strictEqual(F.v.zoom.value, 100);

// Meteogram fit (padding, not the WA-forecast cover) is unchanged. A canvas source uses bitmap width.
frame.MG.kind = "mg";
frame.MG.img = { naturalWidth: 800, naturalHeight: 400, width: 10, height: 10 };
const padX = F.h.pad * 0.5, top = 60, bot = 70;
const mgK = Math.min((F.h.W - 2 * padX) / 800, (F.h.H - top - bot) / 400);
const mb = frame.mgBase("h");
assert.ok(Math.abs(mb.k0 - mgK) < 1e-9);
assert.strictEqual(mb.cx, 400);
assert.strictEqual(frame.crop("h", { dx: 0, dy: 0, zoom: 1 }).pw, 800);
frame.MG.kind = "wafc";
frame.MG.img = { width: 1600, height: 2400 };
assert.strictEqual(frame.crop("v", { dx: 0, dy: 0, zoom: 1 }).pw, 1600);

console.log("wafc gusts + framing: ok");
