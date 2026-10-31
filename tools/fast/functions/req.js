// /req: change requests typed into the site's "Request a change" box (10-31, Benjamin 3:17 PM: "a little prompt box so I can
// request changes on website"). POST saves one request as R2 requests/<time>_<id>.json; GET lists the newest 10. Nothing is
// ever run from here: the agent reads the queue (tools/fast/read_requests.py). Only on the hidden page (Cloudflare Access);
// on top of Access this checks the Access JWT itself (signature against the team's certs, issuer, expiry), so there is no
// write without an Access login. POST also needs JSON + the X-WX-Req header (no cross-site form posts).
const TEAM = "https://wawxchaserswxmodeldata.cloudflareaccess.com";
const b64u = (s) => Uint8Array.from(atob(s.replace(/-/g, "+").replace(/_/g, "/") + "===".slice((s.length + 3) % 4)), (c) => c.charCodeAt(0));
let certs = null, certsAt = 0;
async function accessUser(request) {
  const jwt = request.headers.get("cf-access-jwt-assertion"); if (!jwt) return null;
  const [h, p, s] = jwt.split("."); if (!s) return null;
  const head = JSON.parse(new TextDecoder().decode(b64u(h))), body = JSON.parse(new TextDecoder().decode(b64u(p)));
  if (body.iss !== TEAM || !(body.exp * 1000 > Date.now())) return null;
  if (!certs || Date.now() - certsAt > 3600e3) { certs = (await (await fetch(`${TEAM}/cdn-cgi/access/certs`)).json()).keys || []; certsAt = Date.now(); }
  const jwk = certs.find((k) => k.kid === head.kid); if (!jwk) return null;
  const key = await crypto.subtle.importKey("jwk", jwk, { name: "RSASSA-PKCS1-v1_5", hash: "SHA-256" }, false, ["verify"]);
  const ok = await crypto.subtle.verify("RSASSA-PKCS1-v1_5", key, b64u(s), new TextEncoder().encode(`${h}.${p}`));
  return ok ? (body.email || "service-token") : null;   // service tokens: never store their client id
}
const J = (o, st = 200) => new Response(JSON.stringify(o), { status: st, headers: { "content-type": "application/json", "cache-control": "no-store" } });
export async function onRequest({ request, env }) {
  if (!env.DATA) return J({ error: "no storage" }, 500);
  let who = null; try { who = await accessUser(request); } catch (e) { who = null; }
  if (!who) return J({ error: "Access login needed" }, 403);
  if (request.method === "GET") {
    const ls = await env.DATA.list({ prefix: "requests/", limit: 1000 }), keys = ls.objects.map((o) => o.key).filter((k) => /^requests\/\d/.test(k)).sort().reverse().slice(0, 10);
    const items = await Promise.all(keys.map(async (k) => { const o = await env.DATA.get(k); return o ? Object.assign({ key: k }, await o.json()) : null; }));
    return J({ items: items.filter(Boolean).map((x) => ({ key: x.key, time: x.time, text: x.text, page: x.page, status: x.status || "queued" })) });
  }
  if (request.method !== "POST") return J({ error: "method not allowed" }, 405);
  if (request.headers.get("x-wx-req") !== "1" || !(request.headers.get("content-type") || "").includes("application/json")) return J({ error: "bad request" }, 400);
  const raw = await request.text(); if (raw.length > 8000) return J({ error: "too long" }, 413);
  let d; try { d = JSON.parse(raw); } catch (e) { return J({ error: "bad json" }, 400); }
  const text = String(d.text || "").trim().slice(0, 2000); if (!text) return J({ error: "empty" }, 400);
  const sj = JSON.stringify(d.state && typeof d.state === "object" ? d.state : {});
  const now = new Date(), id = crypto.randomUUID().slice(0, 8), key = `requests/${now.toISOString().replace(/[:.]/g, "-")}_${id}.json`;
  const rec = { id, time: now.toISOString(), who, text, page: String(d.page || "").slice(0, 300), state: sj.length <= 3000 ? JSON.parse(sj) : { truncated: sj.slice(0, 3000) }, status: "queued" };
  await env.DATA.put(key, JSON.stringify(rec, null, 1), { httpMetadata: { contentType: "application/json" } });
  return J({ ok: true, key, id, time: rec.time });
}
