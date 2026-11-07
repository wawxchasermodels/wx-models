// Same-origin path for the meteogram charts when they live on the second Cloudflare Pages project (METEO_BASE="m/").
// The main site is behind Cloudflare Access, so only signed-in visitors reach this function. It fetches the chart from the
// meteogram project with an Access service credential (Pages project secrets METEO_ACCESS_ID / METEO_ACCESS_SECRET) and passes
// it through. Pages project variable METEO_HOST = the meteogram project's hostname, e.g. <project>.pages.dev.
// To merge the two sites back into one: unset METEO_BASE in the workflow and stop deploying this folder.
export async function onRequestGet({ params, env }) {
  const path = (params.path || []).join("/");
  if (!/^[a-z0-9_\-]+(\/[a-z0-9_\-]+)*\.(png|jpg|json)$/i.test(path)) return new Response("Not found", { status: 404 });
  const r = await fetch(`https://${env.METEO_HOST}/meteograms/${path}`, {
    headers: { "CF-Access-Client-Id": env.METEO_ACCESS_ID || "", "CF-Access-Client-Secret": env.METEO_ACCESS_SECRET || "" },
    redirect: "manual",
  });
  if (r.status !== 200) return new Response("Chart not available", { status: r.status === 404 ? 404 : 502 });
  const h = new Headers({ "Content-Type": r.headers.get("Content-Type") || "image/png", "Cache-Control": "private, max-age=600" });
  return new Response(r.body, { status: 200, headers: h });
}
