// "Request a change" box (10-31, Benjamin 3:17 PM: "a little prompt box so I can request changes on website"): a small button
// bottom-left opens a text box; Send saves the request with the time, page and what is on screen (model run, product, view,
// hour, Studio pins) to the queue behind the site's own login (/req, Pages Function -> R2 requests/). Nothing runs by itself:
// the agent reads the queue. Shows "Sent, queued" and the newest requests.
"use strict";
(() => {
const q = new URLSearchParams(location.search);
if (q.get("embed") || q.get("clean") === "1" || q.get("make")) return;
const css = `#rqb{position:fixed;left:12px;bottom:12px;z-index:30;background:#262931;color:#f4f2ee;border:1px solid #7d828c;border-radius:18px;padding:6px 12px;font:600 13px Montserrat,system-ui,sans-serif;cursor:pointer;box-shadow:0 2px 10px #0008}
#rqp{position:fixed;left:12px;bottom:54px;z-index:31;width:min(380px,calc(100vw - 24px));box-sizing:border-box;background:#1d2027f8;color:#f4f2ee;border:1px solid #4a4f5a;border-radius:10px;padding:10px 12px;font:13px Montserrat,system-ui,sans-serif;box-shadow:0 6px 24px #000a}
#rqp[hidden]{display:none}#rqp textarea{width:100%;box-sizing:border-box;min-height:84px;background:#111316;color:#f4f2ee;border:1px solid #7d828c;border-radius:6px;padding:6px;font:inherit;font-size:16px;resize:vertical}
#rqp .rh{display:flex;justify-content:space-between;align-items:center;margin-bottom:6px}#rqp button{background:#262931;color:#f4f2ee;border:1px solid #7d828c;border-radius:6px;padding:4px 10px;font:inherit;cursor:pointer}
#rqp button.pri{background:#2f8cff;border-color:#2f8cff;font-weight:700}#rqst{margin-left:8px;color:#9fe3b0;font-weight:600}#rqst.err{color:#ff9b9b}
#rqctx{color:#8e939c;font-size:11.5px;margin:4px 0}#rql{margin:8px 0 0;padding:0;list-style:none;max-height:180px;overflow:auto;border-top:1px solid #4a4f5a}
#rql li{padding:5px 0;border-bottom:1px solid #2e323a;font-size:12px}#rql small{color:#8e939c}
body.rec #rqb,body.phone.cslim #rqb{display:none}@media (max-width:820px){#rqb{bottom:auto;top:auto;left:auto;right:12px;bottom:12px}#rqp{left:12px;right:12px;bottom:54px}}`;
const st = document.createElement("style"); st.textContent = css; document.head.appendChild(st);
const b = document.createElement("button"); b.id = "rqb"; b.type = "button"; b.textContent = "\u270e Request a change"; b.title = "Ask for a change to this website (queued for your agent)";
const p = document.createElement("div"); p.id = "rqp"; p.hidden = true;
p.innerHTML = `<div class="rh"><b>Request a change</b><button type="button" id="rqx" aria-label="Close">&times;</button></div>
<textarea id="rqt" maxlength="2000" placeholder="What should change on this page? e.g. &quot;make the L markers bigger on the 9:16 frame&quot;"></textarea>
<div id="rqctx"></div><div><button type="button" class="pri" id="rqs">Send</button><span id="rqst"></span></div>
<div style="margin-top:6px;color:#8e939c;font-size:11.5px">Saved to a queue for your agent; nothing changes by itself.</div><ul id="rql"></ul>`;
document.body.append(b, p);
const $r = (id) => document.getElementById(id);
function state() {
  const o = { page: location.pathname.split("/").pop() || "index.html", url: location.pathname + location.search };
  try { if (typeof S !== "undefined" && S) {
    o.run = S.run; o.prod = S.prod; o.view = S.view;
    if (S.runs && S.runs[S.run] && S.runs[S.run].steps) { const s = S.runs[S.run].steps[S.i]; if (s) { o.f = s.f; o.valid = s.valid; } }
    else if (S.hour !== undefined) o.f = S.hour;
    if (o.page.startsWith("studio")) { try { o.pins = JSON.parse(localStorage.getItem(`studio:pins:${S.view}`) || "{}"); } catch (e) { /* none */ } }
    if (o.page.startsWith("social")) { try { o.pins = JSON.parse(localStorage.getItem(`social:pins:${S.view}`) || "{}"); } catch (e) { /* none */ } }
  } } catch (e) { /* no viewer state */ }
  o.screen = `${innerWidth}x${innerHeight}`; return o;
}
const fmt = (t) => { try { return new Date(t).toLocaleString("en-US", { timeZone: "America/Los_Angeles", month: "short", day: "numeric", hour: "numeric", minute: "2-digit" }) + " PT"; } catch (e) { return t; } };
const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
async function list() {
  try { const r = await fetch("/req", { cache: "no-store" }); if (!r.ok) throw new Error(r.status); const d = await r.json();
    $r("rql").innerHTML = (d.items || []).map((x) => `<li>${esc(x.text)}<br><small>${fmt(x.time)} \u00b7 ${esc(x.page || "")} \u00b7 ${esc(x.status)}</small></li>`).join("") || "<li><small>No requests yet.</small></li>";
  } catch (e) { $r("rql").innerHTML = "<li><small>Could not load recent requests.</small></li>"; }
}
function ctx() { const s = state(); $r("rqctx").textContent = `Sends with it: ${s.page}${s.run ? " \u00b7 " + s.run : ""}${s.prod ? " \u00b7 " + s.prod : ""}${s.view ? " \u00b7 " + s.view : ""}${s.f !== undefined ? " \u00b7 F+" + s.f : ""}`; }
b.onclick = () => { p.hidden = !p.hidden; if (!p.hidden) { ctx(); list(); $r("rqt").focus(); } };
$r("rqx").onclick = () => { p.hidden = true; };
p.addEventListener("keydown", (e) => { e.stopPropagation(); if (e.key === "Escape") p.hidden = true; if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) send(); });
async function send() {
  const t = $r("rqt").value.trim(), sl = $r("rqst"); if (!t) { sl.className = "err"; sl.textContent = "Type a request first."; return; }
  $r("rqs").disabled = true; sl.className = ""; sl.textContent = "Sending\u2026";
  try { const s = state(), r = await fetch("/req", { method: "POST", headers: { "content-type": "application/json", "x-wx-req": "1" }, body: JSON.stringify({ text: t, page: s.page, state: s }) });
    const d = await r.json().catch(() => ({})); if (!r.ok || !d.ok) throw new Error(d.error || `HTTP ${r.status}`);
    sl.textContent = "Sent, queued \u2713"; $r("rqt").value = ""; window.__reqSent = d; list();
  } catch (e) { sl.className = "err"; sl.textContent = "Not sent: " + (e.message || e); }
  finally { $r("rqs").disabled = false; }
}
$r("rqs").onclick = send;
window.__reqbox = { state, send, list };
})();
