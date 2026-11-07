// Side-by-side viewer (10-31, Benjamin: "a side by side viewer"): two copies of the map page in frames (index.html?embed=compare),
// each with its own Runs (model + run) / product / view / hour. With sync on, a change in one frame is sent to the other:
// valid time (nearest hour of that run, so two runs of one model line up by time), product (if the other run has it) and view.
// URL: compare.html?l=<model/cycle>&r=<model/cycle>&prod=&view=&valid=  (kept up to date, so a link reopens the same pair)
"use strict";
const Q = new URLSearchParams(location.search), $ = (id) => document.getElementById(id);
const ST = { L: null, R: null }, SYNC = { time: true, prod: true, view: true };
try { Object.assign(SYNC, JSON.parse(localStorage.getItem("cmpSync") || "{}")); } catch (e) { /* defaults */ }
for (const k of ["time", "prod", "view"]) { const b = $("s_" + k); b.checked = SYNC[k]; b.onchange = () => { SYNC[k] = b.checked; localStorage.setItem("cmpSync", JSON.stringify(SYNC)); if (b.checked) push("L"); }; }
// Studio Compare (?studio=1) reuses this page: same sync / swap / hour messages, menus in the panel, maps drawn off-screen
// (cmpstudio) so Studio can place them in the 16:9 and 9:16 frames. No second compare implementation.
const STUDIO = Q.get("studio") === "1";
const SLIM = !STUDIO && matchMedia("(max-width:820px)").matches;   // phones: menus folded in each map, maps sized to their frames
function src(id, run) {
  const u = new URLSearchParams({ embed: "compare", id }); if (SLIM) u.set("slim", "1");
  if (STUDIO) u.set("cmpstudio", "1");
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
// 11-01 (t2021u): equal maps. Each desktop frame reports the room its map has (w x h); both get the smaller of the two, so the
// first and second map always draw at exactly the same size (a frame whose menus wrap to more lines no longer gets a bigger/smaller map)
const BOX = { L: null, R: null }; let boxLast = "";
function sendBox() {
  if (!BOX.L || !BOX.R) return; const w = Math.min(BOX.L.w, BOX.R.w), h = Math.min(BOX.L.h, BOX.R.h), k = w + "x" + h;
  if (k === boxLast) return; boxLast = k; for (const id of ["L", "R"]) frame(id).postMessage({ wx: "box", w, h }, "*");
}
// 11-01 (t2021u: "a way to minimize the menus after I've opened them"): hide / show the menus in both frames at once
let MENUS = true;
$("menusall").onclick = () => { MENUS = !MENUS; $("menusall").textContent = MENUS ? "Hide menus" : "Show menus"; for (const id of ["L", "R"]) frame(id).postMessage({ wx: "menus", show: MENUS }, "*"); };

addEventListener("message", (e) => {
  if (e.data && e.data.wx === "box") return;   // 11-01 t2027u: maps are sized by the (equal) frame width now, menus sit under them; no size capping
  const d = e.data; if (d && d.wx === "size" && SLIM && ST.hasOwnProperty(d.id) && e.source === frame(d.id)) { $(d.id).style.height = Math.max(120, Math.min(1400, d.h)) + "px"; return; }
  if (!d || d.wx !== "state" || !ST.hasOwnProperty(d.id)) return;
  if (e.source !== frame(d.id)) return;
  const first = !ST[d.id]; ST[d.id] = d;
  if (SLIM && d.h) $(d.id).style.height = Math.max(150, Math.min(1400, d.h)) + "px";
  if (d.id === "R") hsync();
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
// shared hour slider: drives the main (right) map; with Valid-time sync on the other map follows
function hsync() { const r = ST.R; if (!r || !r.n) return; const s = $("hstep"); s.max = String(r.n - 1); if (!HP.drag) s.value = String(r.i); $("hlbl").textContent = `F+${r.f} \u00b7 ${(r.vline || "").replace(/^Valid /, "")}`; }
const HP = { t: 0, drag: false };
const hset = (i) => { const r = ST.R; if (!r) return; frame("R").postMessage({ wx: "set", i: (i + r.n) % r.n }, "*"); };
$("hstep").addEventListener("input", (e) => { HP.drag = true; hset(+e.target.value); });
$("hstep").addEventListener("change", () => { HP.drag = false; });
$("hprev").onclick = () => ST.R && hset(ST.R.i - 1); $("hnext").onclick = () => ST.R && hset(ST.R.i + 1);
$("hplay").onclick = () => { if (HP.t) { clearInterval(HP.t); HP.t = 0; $("hplay").textContent = "Play"; return; }
  $("hplay").textContent = "Stop"; HP.t = setInterval(() => ST.R && hset(ST.R.i + 1), 800); };
addEventListener("keydown", (e) => { if (e.target.tagName === "INPUT" && e.target.type !== "range") return; if (e.key === "ArrowRight") { e.preventDefault(); $("hnext").click(); } if (e.key === "ArrowLeft") { e.preventDefault(); $("hprev").click(); } });
$("syncbtn").onclick = () => $("cbar").classList.toggle("open");
$("tv").onclick = () => { const r = ST.R; if (!r) return;
  const u = new URL("studio.html", location.href); u.search = new URLSearchParams({ clean: "1", out: "h", run: r.run, model: r.run.split("/")[0], prod: r.prod, view: r.view, f: String(r.f), play: "1", dwell: "700", loop: "1" }).toString();
  window.open(u.toString(), "_blank"); };
$("swap").onclick = () => {
  if (!ST.L || !ST.R) return; const a = ST.L, b = ST.R;
  frame("L").postMessage({ wx: "set", run: b.run, prod: b.prod, view: b.view, valid: b.valid }, "*");
  frame("R").postMessage({ wx: "set", run: a.run, prod: a.prod, view: a.view, valid: a.valid }, "*");
};
// Studio drives the shared hour (its own scrubber) and reads both maps back. setHour is the same path as this page's slider.
window.__cmp = {
  get L() { return ST.L; }, get R() { return ST.R; },
  setHour: (i) => hset(i),
};
