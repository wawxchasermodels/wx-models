// Side-by-side viewer (10-31, Benjamin: "a side by side viewer"): two copies of the map page in frames (index.html?embed=compare),
// each with its own Runs (model + run) / product / view / hour. With sync on, a change in one frame is sent to the other:
// valid time (nearest hour of that run, so two runs of one model line up by time), product (if the other run has it) and view.
// URL: compare.html?l=<model/cycle>&r=<model/cycle>&prod=&view=&valid=  (kept up to date, so a link reopens the same pair)
"use strict";
const Q = new URLSearchParams(location.search), $ = (id) => document.getElementById(id);
const ST = { L: null, R: null }, SYNC = { time: true, prod: true, view: true };
try { Object.assign(SYNC, JSON.parse(localStorage.getItem("cmpSync") || "{}")); } catch (e) { /* defaults */ }
for (const k of ["time", "prod", "view"]) { const b = $("s_" + k); b.checked = SYNC[k]; b.onchange = () => { SYNC[k] = b.checked; localStorage.setItem("cmpSync", JSON.stringify(SYNC)); if (b.checked) push("L"); }; }
function src(id, run) {
  const u = new URLSearchParams({ embed: "compare", id });
  if (run) u.set("run", run);
  for (const k of ["prod", "view"]) if (Q.get(k)) u.set(k, Q.get(k));
  return "./?" + u;
}
$("L").src = src("L", Q.get("l")); $("R").src = src("R", Q.get("r"));
const frame = (id) => $(id).contentWindow, other = (id) => (id === "L" ? "R" : "L");
let firstR = !!Q.get("valid");
function push(from) {   // send the synced parts of `from` to the other frame
  const s = ST[from]; if (!s) return; const m = { wx: "set" };
  if (SYNC.time) m.valid = s.valid; if (SYNC.prod) m.prod = s.prod; if (SYNC.view) m.view = s.view;
  const o = ST[other(from)];   // already showing that: nothing to send (stops ping-pong between the frames)
  if (o && (!m.valid || o.valid === m.valid) && (!m.prod || o.prod === m.prod) && (!m.view || o.view === m.view)) return;
  if (Object.keys(m).length > 1) frame(other(from)).postMessage(m, "*");
}
let urlT = 0;
addEventListener("message", (e) => {
  const d = e.data; if (!d || d.wx !== "state" || !ST.hasOwnProperty(d.id)) return;
  if (e.source !== frame(d.id)) return;
  const first = !ST[d.id]; ST[d.id] = d;
  if (first && Q.get("valid") && firstR) {   // opened from the map page: both frames start at that valid time
    frame(d.id).postMessage({ wx: "set", valid: Q.get("valid") }, "*"); return;
  }
  if (!d.echo && ST[other(d.id)]) push(d.id);
  clearTimeout(urlT); urlT = setTimeout(() => {
    if (!ST.L || !ST.R) return; const u = new URL(location);
    u.searchParams.set("l", ST.L.run); u.searchParams.set("r", ST.R.run); u.searchParams.set("prod", ST.L.prod); u.searchParams.set("view", ST.L.view); u.searchParams.set("valid", ST.L.valid);
    try { history.replaceState(null, "", u); } catch (err) { /* iOS limit */ }
    $("back").href = `./?run=${encodeURIComponent(ST.L.run)}&prod=${ST.L.prod}&view=${ST.L.view}&f=${ST.L.f}`;
  }, 500);
});
$("swap").onclick = () => {
  if (!ST.L || !ST.R) return; const a = ST.L, b = ST.R;
  frame("L").postMessage({ wx: "set", run: b.run, prod: b.prod, view: b.view, valid: b.valid }, "*");
  frame("R").postMessage({ wx: "set", run: a.run, prod: a.prod, view: a.view, valid: a.valid }, "*");
};
