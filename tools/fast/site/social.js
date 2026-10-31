// Social tab (10-31-26, Benjamin 12:35 PM: "Those social samples look great, let's get that on a tab"): browse / save the ECMWF social
// graphics rendered by tools/fast/social/make_social.py (9:16 2160x3840 + 16:9 3840x2160) and published to R2 social/<run>/ by
// publish_social.py (index: social/index.json). Euro only to start; product / view / hour pickers; full PNG or 1280 px JPG saves.
"use strict";
const DATA = window.WX_DATA || "data/", $ = id => document.getElementById(id), Q = new URLSearchParams(location.search);
const PNAME = { z500anom: "500 mb Height Anomaly", t2ma: "2 m Temperature Anomaly", t850a: "850 mb Temperature Anomaly", mslpqpf: "Pressure + 6 h Precip",
                mslpa: "MSLP Anomaly" };
const ORDER = ["z500anom", "mslpa", "t850a", "t2ma", "mslpqpf"], VNAME = { na: "North America", pnw: "Pacific NW" };
const S = { idx: null, run: Q.get("run"), prod: Q.get("prod"), view: Q.get("view"), hour: +Q.get("f") || null };
const fillSel = (sel, opts, cur) => { sel.innerHTML = opts.map(([v, t]) => `<option value="${v}"${String(v) === String(cur) ? " selected" : ""}>${t}</option>`).join(""); };
const nm = (k, f = S.hour, p = S.prod, v = S.view) => `${p}_${v}_f${String(f).padStart(3, "0")}_${k}`;
const url = (n, jpg) => `${DATA}social/${S.run}/${jpg ? "jpg/" + n + ".jpg" : n + ".png"}`;
const validLbl = f => { const c = S.run, t = Date.UTC(+c.slice(0, 4), +c.slice(4, 6) - 1, +c.slice(6, 8), +c.slice(8, 10)) + f * 3600e3;
  return new Intl.DateTimeFormat("en-US", { timeZone: "America/Los_Angeles", weekday: "short", month: "numeric", day: "numeric", hour: "numeric" }).format(new Date(t)); };
function setLists() {
  const it = S.idx.items[S.run], have = new Set(it.files);
  const prods = ORDER.filter(p => it.prods.includes(p)).concat(it.prods.filter(p => !ORDER.includes(p)));
  if (!prods.includes(S.prod)) S.prod = prods[0];
  if (!it.views.includes(S.view)) S.view = it.views.includes("pnw") ? "pnw" : it.views[0];
  const hrs = it.hours.filter(f => have.has(nm("h", f)) && have.has(nm("v", f)));
  if (!hrs.includes(S.hour)) S.hour = hrs.includes(72) ? 72 : hrs[0];
  fillSel($("run"), S.idx.runs.map(r => [r, `ECMWF ${r.slice(8)}Z ${r.slice(4, 6)}-${r.slice(6, 8)}`]), S.run);
  fillSel($("prod"), prods.map(p => [p, PNAME[p] || p]), S.prod);
  fillSel($("view"), it.views.map(v => [v, VNAME[v] || v]), S.view);
  fillSel($("hour"), hrs.map(f => [f, `F+${f} · ${validLbl(f)} PT`]), S.hour);
  $("strip").innerHTML = hrs.map(f => `<button type="button" data-f="${f}"${f === S.hour ? ' class="on"' : ""}><img loading="lazy" src="${url(nm("h", f), true)}" alt=""><div>F+${f}</div></button>`).join("");
}
function show() {
  for (const k of ["v", "h"]) { const n = nm(k); $("i" + k).src = url(n, true);
    const big = new Image(); big.onload = () => { if (nm(k) === n) $("i" + k).src = big.src; }; big.src = url(n);   // JPG first, the 4K PNG when it lands
    $("s" + k).href = url(n); $("s" + k).download = `ECMWF_${S.run}_${n}.png`; $("s" + k + "1").href = url(n, true); $("s" + k + "1").download = `ECMWF_${S.run}_${n}.jpg`; }
  for (const b of $("strip").children) b.classList.toggle("on", +b.dataset.f === S.hour);
  const it = S.idx.items[S.run]; $("msg").textContent = `ECMWF IFS 0.25° ${S.run.slice(8)}Z run · ${it.files.length} frames · rendered on the box (updated ${S.idx.updated.slice(0, 16).replace("T", " ")} UTC)`;
  const u = new URL(location); u.searchParams.set("run", S.run); u.searchParams.set("prod", S.prod); u.searchParams.set("view", S.view); u.searchParams.set("f", S.hour);
  try { history.replaceState(null, "", u); } catch (e) {}
  window.__shown = (window.__shown || 0) + 1;
}
async function boot() {
  S.idx = await fetch(DATA + "social/index.json", { cache: "no-cache" }).then(r => { if (!r.ok) throw new Error("index " + r.status); return r.json(); });
  if (!S.idx.runs.includes(S.run)) S.run = S.idx.runs[0];
  setLists(); show();
  $("run").onchange = e => { S.run = e.target.value; setLists(); show(); };
  $("prod").onchange = e => { S.prod = e.target.value; setLists(); show(); };
  $("view").onchange = e => { S.view = e.target.value; setLists(); show(); };
  $("hour").onchange = e => { S.hour = +e.target.value; show(); };
  $("strip").onclick = e => { const b = e.target.closest("button[data-f]"); if (b) { S.hour = +b.dataset.f; $("hour").value = S.hour; show(); } };
  addEventListener("keydown", e => { if (e.target.tagName === "SELECT") return; const o = [...$("hour").options].map(x => +x.value), i = o.indexOf(S.hour);
    if (e.key === "ArrowRight" && i < o.length - 1) { S.hour = o[i + 1]; $("hour").value = S.hour; show(); } if (e.key === "ArrowLeft" && i > 0) { S.hour = o[i - 1]; $("hour").value = S.hour; show(); } });
  window.__ready = true;
}
boot().catch(e => { console.error(e); $("msg").textContent = "Could not load: " + e.message; });
