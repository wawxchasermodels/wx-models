"use strict";
const $ = (id) => document.getElementById(id);
const S = { m: null, tab: "", period: "", view: "", model: "", run: 0, keepEnd: "", i: 0, playing: 0, msec: "", town: "", prod: "" };
const TZ = "America/Los_Angeles";
const PREF_PERIOD = ["24h", "6h", "step", "12h", "48h", "total", "max24h", "max12h", "max6h", "daily"];
const INSTANT_TABS = new Set(["gusts", "waves", "aifs500", "aifsmslp", "aifswind", "t2m", "t2manom", "t850", "t850anom", "gust10", "feels", "td2m", "t925", "t700", "t500", "t300", "mslpptype", "ivt", "pw", "pwanom", "w850", "w500", "w250", "thick", "tcc", "ir", "vis", "fog", "elows", "e500"]);
const cache = new Map(); // src -> Image (preloaded)

const fmt = (opts) => new Intl.DateTimeFormat("en-US", { timeZone: TZ, ...opts });
const fDay = fmt({ weekday: "short" }), fMD = fmt({ month: "numeric", day: "numeric" }), fHr = fmt({ hour: "numeric" });
const dayHr = (d) => `${fDay.format(d)} ${fMD.format(d).replace("/", "-")} ${fHr.format(d)}`;
const fullStamp = fmt({ weekday: "short", month: "numeric", day: "numeric", hour: "numeric", minute: "2-digit" });

function btn(label, onClick, attrs = {}) {
  const b = document.createElement("button");
  b.type = "button"; b.textContent = label; b.onclick = onClick;
  for (const [k, v] of Object.entries(attrs)) if (v !== undefined && v !== null) b.setAttribute(k, v);
  return b;
}
const tabObj = (id = S.tab) => S.m.tabs.find((t) => t.id === id);
const allFrames = (t = tabObj(), p = S.period, v = S.view) => (t.frames[`${p}/${v}`] || []);
// Two-run models (HRRR, AIFS; 10-25-26): manifest.runs lists the runs on the site, newest first; frames carry `cycle`.
// S.run = 0 newest / 1 previous. A tab that only has one of the runs for this model shows that run (no toggle).
const siteRuns = (m) => (S.m && S.m.runs && S.m.runs[m]) || [];
const runsOf = (t, m = S.model) => {
  const all = siteRuns(m); if (all.length < 2) return [];
  const have = new Set(Object.values(t.frames).flat().filter((f) => (f.model || "") === m && f.cycle).map((f) => f.cycle));
  return all.filter((r) => have.has(r.cycle));
};
const runCycle = (t, m = S.model) => { const rs = runsOf(t, m); return rs.length ? (rs[S.run] || rs[0]).cycle : ""; };
const frames = (t = tabObj(), p = S.period, v = S.view, m = S.model) => {
  const rc = m ? runCycle(t, m) : "";
  return allFrames(t, p, v).filter((f) => (!m || (f.model || "") === m) && (!rc || f.cycle === rc));
};
const modelsOf = (t) => [...new Set(Object.values(t.frames).flat().map((f) => f.model || "").filter(Boolean))];
const modelList = (t) => t.models ? [...t.models, ...modelsOf(t).filter((m) => !t.models.includes(m))] : modelsOf(t);
const groupOf = (t) => t.group || t.id;
const tabCount = (t) => Object.values(t.frames).reduce((a, v) => a + v.length, 0);
const periodHas = (t, p, m = S.model) => t.views.some((v) => frames(t, p, v.id, m).length);
const viewHas = (t, v, p = S.period, m = S.model) => frames(t, p, v, m).length > 0;
const modelHas = (t, m) => Object.values(t.frames).flat().some((f) => (f.model || "") === m);

function remember() { if (S.tab === "meteograms" || S.tab === "obs" || !tabObj()) return; const f = frames()[S.i]; if (f) S.keepEnd = f.end; }
function nearestIndex() {
  const f = frames(); if (!f.length) return 0;
  if (!S.keepEnd) { // first frame that is still current or upcoming
    const now = Date.now(); const j = f.findIndex((fr) => Date.parse(fr.end) >= now);
    return j < 0 ? f.length - 1 : j;
  }
  const k = Date.parse(S.keepEnd); let best = 0, d = Infinity;
  f.forEach((fr, j) => { const x = Math.abs(Date.parse(fr.end) - k); if (x < d) { d = x; best = j; } });
  return best;
}

function writeHash() {
  const q = S.tab === "obs" ? { t: "obs", v: (typeof Obs !== "undefined" && Obs.viewId()) || "" } : S.tab === "meteograms"
    ? { t: S.tab, s: S.msec, w: S.town, p: S.prod }
    : { t: S.tab, m: S.model, ...(runsOf(tabObj()).length > 1 ? { r: String(S.run) } : {}), p: S.period, v: S.view, e: (frames()[S.i] || {}).end || "" };
  history.replaceState(null, "", "#" + new URLSearchParams(q));
}

/* ---------- tabs ---------- */
function groups() {
  const seen = new Map();
  for (const t of S.m.tabs) {
    const g = groupOf(t);
    if (!seen.has(g)) seen.set(g, { id: g, label: t.groupLabel || t.label, members: [] });
    seen.get(g).members.push(t);
  }
  return [...seen.values()];
}
function selectTab(id) {
  stop(); remember();
  if (id !== "meteograms" && id !== "obs") { // jump to the first product in the group that has maps
    const g = groups().find((x) => x.id === id || x.members.some((m) => m.id === id));
    if (g && !g.members.some((m) => m.id === id)) id = (g.members.find((m) => tabCount(m)) || g.members[0]).id;
  }
  S.tab = id; pickDefaults(); render();
}
// Menu v2: the top bar holds one dropdown per section (Washington, Ground level, Aloft, Combo maps) plus the
// Meteograms and Observations tabs. A section button opens its menu (products under sub-headings); arrow keys on
// the bar still jump straight to the next section's first product. The product pills below list the section's siblings.
let MENU_OPEN = "";
function sectionTarget(g) { return (g.members.find((m) => tabCount(m)) || g.members[0]).id; }
function renderTabs() {
  const nav = $("tabs"); nav.replaceChildren();
  const cur = S.tab === "meteograms" || S.tab === "obs" ? S.tab : groupOf(tabObj());
  const items = groups().map((g) => ({ id: g.id, label: g.label, n: g.members.reduce((a, m) => a + tabCount(m), 0), target: sectionTarget(g), menu: true }));
  const mg = S.m.meteograms.sections.reduce((a, s) => a + s.products.reduce((b, p) => b + Object.keys(p.images || {}).length, 0), 0);
  items.push({ id: "meteograms", label: "Meteograms", n: mg, target: "meteograms" });
  items.push({ id: "obs", label: "Observations", n: 1, target: "obs" });   // live station plots (obs.js)
  for (const it of items) {
    const sel = it.id === cur;
    const b = btn(it.label, () => (it.menu ? toggleMenu(it.id, b) : (closeMenu(), selectTab(it.target))), {
      role: "tab", "aria-selected": String(sel), tabindex: sel ? "0" : "-1", id: sel ? "tab-current" : null,
      "aria-controls": it.id === "meteograms" ? "meteo-pane" : it.id === "obs" ? "obs-pane" : "map-pane", class: (it.n ? "" : "none") + (it.menu ? " has-menu" : ""),
      title: it.n ? null : "Not generated yet", "aria-haspopup": it.menu ? "menu" : null, "aria-expanded": it.menu ? String(MENU_OPEN === it.id) : null,
      "data-sec": it.id, "data-target": it.target });
    if (it.menu) { const c = document.createElement("span"); c.className = "caret"; c.setAttribute("aria-hidden", "true"); c.textContent = "\u25BE"; b.appendChild(c); }
    nav.appendChild(b);
  }
  nav.onkeydown = (e) => {
    const bs = [...nav.querySelectorAll("button")]; const k = bs.indexOf(document.activeElement);
    if (k < 0) return;
    if (e.key === "ArrowDown" && bs[k].dataset.sec && groups().some((g) => g.id === bs[k].dataset.sec)) { e.preventDefault(); openMenu(bs[k].dataset.sec, bs[k], true); return; }
    let j = null;
    if (e.key === "ArrowRight") j = (k + 1) % bs.length;
    if (e.key === "ArrowLeft") j = (k - 1 + bs.length) % bs.length;
    if (e.key === "Home") j = 0;
    if (e.key === "End") j = bs.length - 1;
    if (j === null) return;
    e.preventDefault(); e.stopPropagation(); closeMenu(); selectTab(bs[j].dataset.target); $("tabs").querySelectorAll("button")[j].focus();
  };
}
function placeMenu() {   // under its section button; follows the bar when it scrolls sideways on phones
  if (!MENU_OPEN) return;
  const b = $("tabs").querySelector(`button[data-sec="${MENU_OPEN}"]`), pop = $("menu-pop"); if (!b) return;
  const r = b.getBoundingClientRect(), w = $("menubar").getBoundingClientRect();
  pop.style.left = `${Math.max(0, Math.min(r.left - w.left, w.width - pop.offsetWidth))}px`; pop.style.top = `${r.bottom - w.top}px`;
}
function toggleMenu(id, b) { if (MENU_OPEN === id) closeMenu(true); else openMenu(id, b, false); }
function closeMenu(refocus = false) {
  const pop = $("menu-pop"); if (!MENU_OPEN) return;
  const sec = MENU_OPEN; MENU_OPEN = ""; pop.hidden = true; pop.replaceChildren();
  const b = $("tabs").querySelector(`button[data-sec="${sec}"]`); if (b) { b.setAttribute("aria-expanded", "false"); if (refocus) b.focus(); }
}
function openMenu(id, b, focusFirst) {
  closeMenu(); const g = groups().find((x) => x.id === id); if (!g) return;
  MENU_OPEN = id; b.setAttribute("aria-expanded", "true");
  const pop = $("menu-pop"); pop.replaceChildren(); pop.setAttribute("aria-label", `${g.label} maps`);
  let lastSub = null;
  for (const t of g.members) {
    if ((t.sub || "") !== lastSub) {
      lastSub = t.sub || ""; if (lastSub) { const h = document.createElement("p"); h.className = "menu-sub"; h.setAttribute("role", "presentation"); h.textContent = lastSub; pop.appendChild(h); }
    }
    const n = tabCount(t); const cur = t.id === S.tab;
    const it = btn(t.label, () => { closeMenu(); if (t.id !== S.tab) selectTab(t.id); $("tabs").querySelector(`button[data-sec="${id}"]`)?.focus(); },
      { role: "menuitem", class: "menu-item" + (n ? "" : " none"), "aria-current": cur ? "true" : null, "data-tab": t.id });
    const tag = document.createElement("span"); tag.className = "menu-tag";
    tag.textContent = n ? (t.models && t.models.length ? t.models.filter((m) => modelHas(t, m)).join(", ") : modelsOf(t).join(", ")) : "not generated yet";
    it.appendChild(tag); pop.appendChild(it);
  }
  pop.hidden = false; placeMenu();
  const items = [...pop.querySelectorAll(".menu-item")];
  pop.onkeydown = (e) => {
    const k = items.indexOf(document.activeElement);
    if (e.key === "Escape") { e.preventDefault(); closeMenu(true); return; }
    if (e.key === "Tab") { closeMenu(); return; }
    let j = null;
    if (e.key === "ArrowDown") j = (k + 1) % items.length;
    if (e.key === "ArrowUp") j = (k - 1 + items.length) % items.length;
    if (e.key === "Home") j = 0;
    if (e.key === "End") j = items.length - 1;
    if (j !== null) { e.preventDefault(); items[j].focus(); }
  };
  if (focusFirst) (items.find((x) => x.getAttribute("aria-current")) || items[0]).focus();
}
document.addEventListener("pointerdown", (e) => { if (MENU_OPEN && !e.target.closest("#menu-pop") && !e.target.closest("#tabs button.has-menu")) closeMenu(); });
document.addEventListener("keydown", (e) => { if (MENU_OPEN && e.key === "Escape") closeMenu(true); });
window.addEventListener("resize", () => placeMenu());
$("tabs").addEventListener("scroll", () => placeMenu(), { passive: true });

/* ---------- defaults ---------- */
function pickDefaults() {
  if (S.tab === "obs") return;
  if (S.tab === "meteograms") {
    const ms = S.m.meteograms;
    if (!ms.sections.some((s) => s.id === S.msec)) S.msec = (ms.sections.find((s) => s.products.some((p) => Object.keys(p.images || {}).length)) || ms.sections[0]).id;
    const sec = ms.sections.find((s) => s.id === S.msec);
    if (!ms.towns.some((t) => t.id === S.town)) S.town = (ms.towns.find((t) => t.id === "seattle" && sec.products.some((p) => p.images && p.images[t.id])) || ms.towns.find((t) => sec.products.some((p) => p.images && p.images[t.id])) || ms.towns[0]).id;   // Seattle is the default town
    if (!sec.products.some((p) => p.id === S.prod)) S.prod = (sec.products.find((p) => p.images && p.images[S.town]) || sec.products[0]).id;
    return;
  }
  const t = tabObj();
  const ms = modelList(t);
  if (!ms.includes(S.model) || (!modelHas(t, S.model) && ms.some((m) => modelHas(t, m)))) S.model = ms.find((m) => modelHas(t, m)) || ms[0] || "";
  if (!ms.length) S.model = "";
  const ids = t.periods.map((p) => p.id);
  if (!ids.includes(S.period) || !periodHas(t, S.period)) {
    const rank = (x) => { const k = PREF_PERIOD.indexOf(x); return k < 0 ? 99 : k; };
    const ranked = [...ids].sort((a, b) => rank(a) - rank(b));
    const keep = ids.includes(S.period) ? S.period : null;
    S.period = ranked.find((p) => periodHas(t, p)) || keep || ids[0];
  }
  if (!t.views.some((v) => v.id === S.view) || (!viewHas(t, S.view) && t.views.some((v) => viewHas(t, v.id)))) {
    S.view = (t.views.find((v) => viewHas(t, v.id)) || t.views[0]).id;
  }
  S.i = nearestIndex();
}

/* ---------- render ---------- */
function render() {
  renderTabs();
  const meteo = S.tab === "meteograms", obs = S.tab === "obs";
  $("map-pane").hidden = meteo || obs; $("meteo-pane").hidden = !meteo; $("obs-pane").hidden = !obs;
  if (obs) Obs.show(); else { Obs.hide(); meteo ? renderMeteo() : renderMaps(); }
  revealActive();
  writeHash();
}
// on narrow screens pill rows scroll sideways: keep the active pill (and tab) in view without moving the page
function revealActive() {
  for (const row of document.querySelectorAll(".chips, .tabs")) {
    if (row.scrollWidth <= row.clientWidth) continue;
    const b = row.querySelector('[aria-pressed="true"], [aria-selected="true"]'); if (!b) continue;
    const l = b.offsetLeft, r = l + b.offsetWidth; // row is position:relative, so offsetLeft is row-relative
    if (l < row.scrollLeft || r > row.scrollLeft + row.clientWidth) row.scrollLeft = Math.max(0, l - (row.clientWidth - b.offsetWidth) / 2);
  }
}
function pills(el, items, cur, onPick, hasFn) {
  el.replaceChildren();
  for (const it of items) {
    const has = hasFn(it.id);
    el.appendChild(btn(it.label, () => { if (it.id === cur) return; stop(); remember(); onPick(it.id); pickDefaultsKeep(); render(); }, {
      "aria-pressed": String(it.id === cur), class: has ? "" : "none", title: has ? null : "Not generated yet" }));
  }
}
// after a pill click keep the user's choice even if empty (the empty state explains), only fix the index
function pickDefaultsKeep() { S.i = nearestIndex(); }

function renderMaps() {
  const t = tabObj();
  const members = S.m.tabs.filter((x) => groupOf(x) === groupOf(t));
  $("ctl-products").hidden = members.length < 2;
  pills($("products"), members.map((x) => ({ id: x.id, label: x.label })), S.tab,
    (id) => { S.tab = id; const nt = tabObj(); if (!nt.periods.some((p) => p.id === S.period) || !nt.views.some((v) => v.id === S.view)) pickDefaults(); },
    (id) => tabCount(tabObj(id)) > 0);
  const ms = modelList(t);
  $("ctl-models").hidden = ms.length < 2 && !(t.models && t.models.length);   // a declared model list always shows its pill(s)
  pills($("models"), ms.map((m) => ({ id: m, label: m })), S.model, (m) => { S.model = m; }, (m) => modelHas(t, m));
  // Run toggle (two-run models HRRR/AIFS) only where this tab has both runs: older run left, newest right ("12Z | 18Z"),
  // newest picked by default; the valid time is kept when switching runs (remember() + nearestIndex())
  const rs = runsOf(t);
  $("ctl-runs").hidden = rs.length < 2;
  if (rs.length > 1) {
    pills($("runs"), rs.map((r, j) => ({ id: j, label: r.label })).reverse(), Math.min(S.run, rs.length - 1), (j) => { S.run = j; }, () => true);
    [...$("runs").children].forEach((b, k) => { const r = rs[rs.length - 1 - k]; b.title = `${r.run}${k === rs.length - 1 ? " (newest)" : ""}`; });
  }
  const note = ms.length > 1 && S.m.modelNotes ? S.m.modelNotes[S.model] : "";
  $("model-note").hidden = !note; $("model-note").textContent = note || "";
  $("ctl-periods").hidden = t.periods.length < 2;
  pills($("periods"), t.periods, S.period, (p) => { S.period = p; }, (p) => periodHas(t, p));
  $("ctl-views").hidden = t.views.length < 2;
  pills($("views"), t.views, S.view, (v) => { S.view = v; }, (v) => viewHas(t, v));
  showFrame();
}

function timeText(t, fr) {
  const s = new Date(fr.start || fr.end), e = new Date(fr.end);
  const init = fr.init ? Date.parse(fr.init) : null;
  const fh = (d) => init === null ? null : Math.round((d - init) / 3600e3);
  const instant = S.period === "daily" ? false : (INSTANT_TABS.has(t.id) && S.period === "step") || +s === +e;
  if (S.period === "daily") return { valid: `${fDay.format(s)} ${fMD.format(s).replace("/", "-")}`, fh: "" };
  if (instant) { const h = fh(e); return { valid: `Valid ${dayHr(e)} PT`, fh: h === null ? "" : `F+${h}` }; }
  const a = fh(s), b = fh(e);
  return { valid: `${dayHr(s)} \u2192 ${dayHr(e)} PT`, fh: a === null ? "" : `F+${Math.max(0, a)} to F+${b}` };
}

function setLoading(on, which = "map") {
  const el = $(`${which}-loader`);
  clearTimeout(el._t);
  if (on) el._t = setTimeout(() => { el.hidden = false; }, 120); else el.hidden = true;
}
function loadInto(img, src, which, onFail) {
  const pre = cache.get(src);
  if (img.getAttribute("src") === src && img.complete && img.naturalWidth) { setLoading(false, which); return; }
  setLoading(!(pre && pre.complete && pre.naturalWidth), which);
  img.onload = () => { setLoading(false, which); img.classList.remove("fade"); };
  img.onerror = () => { setLoading(false, which); onFail(); reloadIfStale(); };
  img.src = src;
}
// 10-26-26: every deploy can rename or drop map files; a page opened before the deploy then asks for files that are gone.
// On a failed image, look at the live manifest once a minute at most and reload the page (state is kept in the URL hash)
// when the site has been rebuilt since this page loaded.
let staleAt = 0;
async function reloadIfStale() {
  if (!S.m || Date.now() - staleAt < 60000) return;
  staleAt = Date.now();
  try {
    const r = await fetch("manifest.json", { cache: "no-store" });
    if (r.ok && (await r.json()).generated !== S.m.generated) location.reload();
  } catch (e) { /* offline or signed out: keep the message on screen */ }
}
function preload(f, i, n = 2) {
  for (let d = 1; d <= n; d++) for (const j of [i + d, i - d]) {
    const fr = f[(j + f.length) % f.length]; if (!fr || cache.has(fr.src)) continue;
    const im = new Image(); im.decoding = "async"; im.src = fr.src; cache.set(fr.src, im);
  }
}

function emptyState(el, title, body, suggestions = []) {
  el.replaceChildren();
  const h = document.createElement("p"); h.className = "empty-title"; h.textContent = title;
  const p = document.createElement("p"); p.className = "empty-body"; p.textContent = body;
  el.append(h, p);
  if (suggestions.length) {
    const w = document.createElement("div"); w.className = "empty-try";
    const l = document.createElement("span"); l.textContent = "Available:"; w.appendChild(l);
    for (const [label, fn] of suggestions.slice(0, 6)) w.appendChild(btn(label, fn));
    el.appendChild(w);
  }
  el.hidden = false;
}

function suggestionsFor(t) {
  const out = [];
  for (const p of t.periods) for (const v of t.views) for (const m of (modelList(t).length ? modelList(t) : [""])) {
    if (!frames(t, p.id, v.id, m).length) continue;
    const parts = [p.label, v.label]; if (m && modelList(t).length > 1) parts.unshift(m);
    out.push([parts.join(" \u00b7 "), () => { stop(); remember(); S.period = p.id; S.view = v.id; S.model = m; S.i = nearestIndex(); render(); }]);
  }
  return out;
}

function showFrame() {
  const t = tabObj(); const f = frames(); const n = f.length;
  const sl = $("slider"); sl.max = Math.max(0, n - 1); S.i = Math.min(S.i, Math.max(0, n - 1)); sl.value = S.i; sl.disabled = n < 2;
  for (const id of ["prev", "next", "play"]) $(id).disabled = n < 2;
  renderTicks(f);
  const img = $("map-img"); const empty = $("map-empty"); const stage = $("stage");
  const pl = t.periods.find((p) => p.id === S.period).label; const vl = t.views.find((v) => v.id === S.view).label;
  $("cap-left").textContent = [t.groupLabel ? `${t.groupLabel}: ${t.label}` : t.label, S.model && modelList(t).length > 1 ? S.model : "", pl, vl].filter(Boolean).join(" \u00b7 ");
  if (!n) {
    img.hidden = true; img.removeAttribute("src"); setLoading(false);
    stage.style.aspectRatio = "";
    const any = tabCount(t) > 0;
    emptyState(empty, "Not generated yet",
      any ? `There are no ${t.label.toLowerCase()} maps for ${[S.model && modelList(t).length > 1 ? S.model : "", pl, vl].filter(Boolean).join(" \u00b7 ")} in the current run.`
          : `No ${t.label.toLowerCase()} maps have been generated yet. They will appear here after the next map run.`,
      suggestionsFor(t));
    $("valid").textContent = "Not generated yet"; $("meta").textContent = ""; $("cap-right").textContent = "";
    updateSave(); writeHash(); return;
  }
  const fr = f[S.i];
  empty.hidden = true; img.hidden = false;
  if (fr.w && fr.h) stage.style.aspectRatio = `${fr.w} / ${fr.h}`;
  const tt = timeText(t, fr);
  img.alt = `${t.label} map, ${tt.valid}${tt.fh ? ", " + tt.fh : ""}, ${vl}`;
  loadInto(img, fr.src, "map", () => {
    img.hidden = true;
    emptyState(empty, "Image could not be loaded", "This map file is missing or failed to download. Try the next time step, or reload the page.");
  });
  $("valid").textContent = tt.valid;
  $("meta").textContent = [tt.fh, fr.run, `${S.i + 1} of ${n}`].filter(Boolean).join("  \u00b7  ");
  sl.setAttribute("aria-valuetext", `${tt.valid}${tt.fh ? ", " + tt.fh : ""}`);
  $("cap-right").textContent = fr.run || "";
  preload(f, S.i, S.playing ? 4 : 2);
  updateSave();
  writeHash();
}

function renderTicks(f) {
  const el = $("ticks"); el.replaceChildren();
  if (f.length < 2) return;
  let last = "";
  f.forEach((fr, j) => {
    const d = new Date(fr.end); const day = fDay.format(d);
    if (day === last) return; last = day;
    const s = document.createElement("span"); s.textContent = day;
    s.style.left = `calc(${(j / (f.length - 1)) * 100}% + ${(0.5 - j / (f.length - 1)) * 26}px)`;
    el.appendChild(s);
  });
}

function step(d) {
  const n = frames().length; if (n < 2) return;
  S.i = (S.i + d + n) % n; remember(); showFrame();
}
function stop() { clearInterval(S.playing); S.playing = 0; const p = $("play"); p.innerHTML = "&#9654;"; p.setAttribute("aria-label", "Play"); }
function togglePlay() {
  if (S.playing) return stop();
  const p = $("play"); p.innerHTML = "&#10074;&#10074;"; p.setAttribute("aria-label", "Pause");
  S.playing = setInterval(() => step(1), 800);
  preload(frames(), S.i, 4);
}

/* ---------- meteograms ---------- */
function renderMeteo() {
  const ms = S.m.meteograms; const sec = ms.sections.find((s) => s.id === S.msec);
  const sc = $("msections"); sc.replaceChildren();
  for (const s of ms.sections) {
    const has = s.products.some((p) => Object.keys(p.images || {}).length);
    sc.appendChild(btn(s.label, () => { S.msec = s.id; S.prod = ""; pickDefaults(); render(); },
      { "aria-pressed": String(s.id === S.msec), class: has ? "" : "none" }));
  }
  const town = $("town"); town.replaceChildren();
  for (const t of ms.towns) {
    const n = sec.products.filter((p) => p.images && p.images[t.id]).length;
    town.add(new Option(t.label + (n ? "" : " (not generated yet)"), t.id));
  }
  town.value = S.town; town.onchange = () => { S.town = town.value; render(); };
  const list = $("prodlist"); list.replaceChildren();
  const sel = $("mproduct"); sel.replaceChildren();
  for (const p of sec.products) {
    const has = p.images && p.images[S.town];
    const tag = p.status !== "doable" ? "not in free data" : has ? "" : "not generated yet";
    const li = document.createElement("li"); if (p.status !== "doable") li.className = "na"; else if (!has) li.className = "missing";
    const b = btn(p.label, () => { S.prod = p.id; render(); }, { "aria-current": p.id === S.prod ? "true" : null });
    if (tag) { const s = document.createElement("span"); s.className = "tagx"; s.textContent = tag; b.appendChild(s); }
    li.appendChild(b); list.appendChild(li);
    sel.add(new Option(p.label + (tag ? ` (${tag})` : ""), p.id));
  }
  sel.value = S.prod; sel.onchange = () => { S.prod = sel.value; render(); };
  const p = sec.products.find((x) => x.id === S.prod);
  const im = p.images && p.images[S.town];
  const img = $("meteo-img"); const empty = $("meteo-empty");
  const townLabel = ms.towns.find((t) => t.id === S.town).label;
  $("mcap-left").textContent = `${sec.label} \u00b7 ${p.label} \u00b7 ${townLabel}`;
  $("mcap-right").textContent = im ? im.run : "";
  updateMeteoSave(sec, p, S.town, im);
  if (im) {
    empty.hidden = true; img.hidden = false; img.alt = `${sec.label} ${p.label}, ${townLabel}`;
    loadInto(img, im.src, "meteo", () => { img.hidden = true; emptyState(empty, "Image could not be loaded", "This chart file is missing or failed to download. Reload the page to try again."); });
  } else {
    img.hidden = true; img.removeAttribute("src"); setLoading(false, "meteo");
    if (p.status !== "doable") emptyState(empty, "Not available with free data", p.note || "This product needs data that is not openly licensed.");
    else {
      const towns = ms.towns.filter((t) => p.images && p.images[t.id]);
      const prods = sec.products.filter((x) => x.images && x.images[S.town]);
      let sug = towns.map((t) => [t.label, () => { S.town = t.id; render(); }])
        .concat(prods.map((x) => [x.label, () => { S.prod = x.id; render(); }]));
      if (!sug.length) { // nothing for this product or town: point at any chart in this model
        const any = []; for (const x of sec.products) for (const tw of Object.keys(x.images || {})) any.push([x, tw]);
        sug = any.map(([x, tw]) => [`${x.label} \u00b7 ${ms.towns.find((t) => t.id === tw).label}`, () => { S.prod = x.id; S.town = tw; render(); }]);
      }
      emptyState(empty, "Not generated yet", `${p.label} has not been generated for ${townLabel} yet.`, sug);
    }
  }
}

/* ---------- input ---------- */
function wire() {
  $("prev").onclick = () => { stop(); step(-1); };
  $("next").onclick = () => { stop(); step(1); };
  $("play").onclick = togglePlay;
  $("slider").addEventListener("input", (e) => { stop(); S.i = Number(e.target.value); remember(); showFrame(); });
  document.addEventListener("keydown", (e) => {
    if (S.tab === "meteograms" || S.tab === "obs" || !S.m) return;
    const tg = e.target; const tag = tg.tagName;
    if (tag === "SELECT" || tag === "TEXTAREA" || (tag === "INPUT" && tg.type !== "range") || tg.closest("[role=tablist]")) return;
    if (e.altKey || e.ctrlKey || e.metaKey) return;
    if (tag === "INPUT") return; // the slider handles its own arrows
    if (e.key === "ArrowRight") { stop(); step(1); e.preventDefault(); }
    else if (e.key === "ArrowLeft") { stop(); step(-1); e.preventDefault(); }
    else if (e.key === "Home") { stop(); S.i = 0; remember(); showFrame(); e.preventDefault(); }
    else if (e.key === "End") { stop(); S.i = Math.max(0, frames().length - 1); remember(); showFrame(); e.preventDefault(); }
    else if (e.key === " " && tag !== "BUTTON") { togglePlay(); e.preventDefault(); }
  });
  const stage = $("stage");
  let x0 = null, y0 = null;
  stage.addEventListener("touchstart", (e) => { x0 = e.touches[0].clientX; y0 = e.touches[0].clientY; }, { passive: true });
  stage.addEventListener("touchend", (e) => {
    if (x0 === null) return;
    const dx = e.changedTouches[0].clientX - x0, dy = e.changedTouches[0].clientY - y0;
    if (Math.abs(dx) > 40 && Math.abs(dx) > 1.3 * Math.abs(dy)) { stop(); step(dx < 0 ? 1 : -1); }
    x0 = null;
  }, { passive: true });
}

async function boot() {
  wire(); wireExport();
  const r = await fetch("manifest.json", { cache: "no-store" });
  if (!r.ok) throw new Error(`manifest.json HTTP ${r.status}`);
  S.m = await r.json();
  const g = Date.parse(S.m.generated);
  $("stamp").textContent = Number.isNaN(g) ? `Updated ${S.m.generated_label}` : `Updated ${fullStamp.format(new Date(g))} PT`;
  const q = new URLSearchParams(location.hash.slice(1));
  const first = (S.m.tabs.find((t) => tabCount(t)) || S.m.tabs[0]).id;
  S.tab = q.get("t") || first;
  if (S.tab === "obs") Obs.setView(q.get("v") || "");
  else if (S.tab === "meteograms") { S.msec = q.get("s") || ""; S.town = q.get("w") || ""; S.prod = q.get("p") || ""; }
  else {
    if (!tabObj()) S.tab = first;
    S.period = q.get("p") || ""; S.view = q.get("v") || ""; S.model = q.get("m") || ""; S.keepEnd = q.get("e") || "";
    S.run = q.get("r") === "1" ? 1 : 0;
  }
  pickDefaults(); render();
}
boot().catch((e) => {
  console.warn(e);
  $("stamp").textContent = "Could not load the map list";
  emptyState($("map-empty"), "Maps could not be loaded", "The map list (manifest.json) is missing or unreadable. Reload the page; if this keeps happening the site has not been built yet.");
});
