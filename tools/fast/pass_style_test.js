// Source checks: ECMWF EPS (and AIFS ENS) pass / town summaries share the HRRR stacked look.
// Compared against: pass_chart_guard.py (floors and panel presence on the map-page mgChart,
// not meteograms.html Surface / Winter colours, fonts, figPanels, or sameKind("summary")).
"use strict";
const fs = require("fs");
const path = require("path");
const site = path.join(__dirname, "site");
const mg = fs.readFileSync(path.join(site, "meteograms.js"), "utf8");
const html = fs.readFileSync(path.join(site, "meteograms.html"), "utf8");
const fails = [];
const check = (ok, msg) => { if (!ok) fails.push(msg); };

check(/\[`\$\{m\}_surface_summary`, "Surface Summary", "summary"\]/.test(mg), "ens() must include Surface Summary (kind summary)");
check(/\[`\$\{m\}_winter_summary`, "Winter Weather Summary", "winter"\]/.test(mg), "ens() must include Winter Weather Summary (kind winter)");
// Surface Summary is first so #s=eps&w=Stevens and a HRRR→EPS switch land on the same look
check(/const ens = \(m\) => \[\s*\/\/[^\n]*\s*\[`\$\{m\}_surface_summary`/.test(mg) ||
      mg.replace(/\s+/g, " ").includes('const ens = (m) => [ // 11-14') ||
      /const ens = \(m\) => \[[\s\S]{0,400}_surface_summary/.test(mg),
  "Surface Summary must be at the start of the ensemble product list");
check(/function stackedChart\(/.test(mg), "stackedChart must draw HRRR and EPS summaries from one function");
check(/k === "summary" \|\| k === "winter"/.test(mg) && /return stackedChart\(/.test(mg),
  "build() must route summary and winter through stackedChart for every model, including EPS");
check(/fig: "panels"/.test(mg) && /function figPanels\(/.test(mg), "summaries must use figPanels (the HRRR stacked look)");
check(/const K = \{ BG: "#15171c"/.test(mg) && /WARM: "#ff6a3d"/.test(mg) && /RAIN: "#3fbf5a"/.test(mg) && /COLD: "#5fa8ff"/.test(mg) && /SNOW: "#8fd3ff"/.test(mg),
  "shared colour tokens K must stay on the HRRR summary palette");
check(/const FONT = \(w, px\) => `\$\{w\} \$\{px\}px Montserrat, system-ui, sans-serif`/.test(mg),
  "charts must keep the Montserrat font");
check(/MG_FLOORS\.passPrecipIn/.test(mg) && /MG_FLOORS\.passSnow6In/.test(mg),
  "pass winter axes must still use MG_FLOORS (3 in precip / 12 in snow per 6 h)");
check(/withBands\(/.test(mg) && /sdFill\(/.test(mg), "EPS summaries must style member spread or t2sd behind the mean line");
check(/Temp \(ens\. mean\)/.test(mg) && /\\\u00b11 spread|±1 spread|\\\\u00b11 spread|±1 spread|\u00b11 spread/.test(mg) ||
      mg.includes("ens. mean") && mg.includes("spread"),
  "EPS-specific mean / spread labels must be present");
check(/function meteoSpecInfo\(/.test(mg) && /window\.__meteoSpec = meteoSpecInfo/.test(mg) && /window\.__meteoStyle = \{ K, FONT, MG_SC, MG_FLOORS \}/.test(mg),
  "the style guard hook __meteoSpec / __meteoStyle must be published after a successful draw");
check(/function sameKind\(/.test(mg), "sameKind must remain so a HRRR Surface Summary switch lands on EPS Surface Summary");
check(/meteograms\.js\?v=20261114eps1/.test(html), "meteograms.html must cache-bust the new meteograms.js token");

if (fails.length) {
  console.log(fails.map((f) => "FAIL " + f).join("\n"));
  console.log("pass_style_test: FAILS " + fails.length);
  process.exit(1);
}
console.log("pass_style_test: PASS");
