// GET/HEAD /d/<key> -> R2 bucket wx-models-data (binding DATA). The whole host is behind Cloudflare Access.
// Cache: run data is immutable (run + step in the key), static layers 1 day, manifest/run.json 30 s.
export async function onRequest({ request, params, env }) {
  if (request.method !== "GET" && request.method !== "HEAD") return new Response("method not allowed", { status: 405 });
  const key = [].concat(params.path || []).join("/");
  if (!key || key.includes("..") || !env.DATA) return new Response("not found", { status: 404 });
  const obj = await env.DATA.get(key, { onlyIf: request.headers, range: request.headers });
  if (!obj) return new Response("not found", { status: 404 });
  const h = new Headers(); obj.writeHttpMetadata(h); h.set("etag", obj.httpEtag);
  if (obj.uploaded) h.set("last-modified", obj.uploaded.toUTCString());   // meteograms page "Updated" stamp
  const live = key === "manifest.json" || key.endsWith("/run.json") || key.endsWith("/run_x.json");
  h.set("cache-control", live ? "private, max-age=30" : key.startsWith("runs/") ? "private, max-age=31536000, immutable" : "private, max-age=86400");
  if (!("body" in obj) || !obj.body) return new Response(null, { status: 304, headers: h });
  if (request.method === "HEAD") return new Response(null, { headers: h });
  return new Response(obj.body, { status: request.headers.has("range") && obj.range ? 206 : 200, headers: h });
}
