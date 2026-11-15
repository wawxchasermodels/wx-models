#!/usr/bin/env python3
"""Walk every tide station and record flood-line QA (method, verification, drawn lines).

Uses the sanctioned Access-header helper (qa.add_hdr) so the preview/prod Pages host
can be opened the same way the other deploy guards do. Never print credentials.
"""
import asyncio, json, os, sys
sys.path.insert(0, "/workspace/studio_refresh_qa")
sys.path.insert(0, "/workspace/qa_realpreview_20261031")
import qa
from playwright.async_api import async_playwright

B = sys.argv[1].rstrip("/")

EVAL = """() => {
  if (!window.TIDE || typeof TIDE.qa !== "function") return { ready: false };
  const D = TIDE.state && TIDE.state();
  if (!D || !D.pred || D.pred.length < 2 || !D.cond || D.cond.length < 2) return { ready: false };
  const q = TIDE.qa();
  let hi = -1e9;
  for (const a of [D.pred, D.obs || [], D.cond]) for (const p of a) if (p && p[1] != null) hi = Math.max(hi, p[1]);
  return {
    ready: true,
    st: q.st, sid: q.sid, name: q.name, floods: q.floods, skip: q.floodSkip,
    drawn: q.floodDrawn, dataHi: hi, obs: q.obs, cond: q.cond, method: q.method,
    ver: q.ver, windOn: q.windOn
  };
}"""

async def read_qa(pg, timeout=90000):
    await pg.wait_for_function("() => { const r = (%s)(); return !!(r && r.ready); }" % EVAL.strip(), timeout=timeout)
    return await pg.evaluate(EVAL)

async def main():
    async with async_playwright() as p:
        br = await p.chromium.launch(args=["--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader"])
        ctx = await br.new_context(viewport={"width": 1440, "height": 900}, device_scale_factor=1)
        await ctx.route(B + "/**", qa.add_hdr)
        pg = await ctx.new_page()
        errs = []
        pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.on("console", lambda m: errs.append(m.text) if m.type == "error" else None)
        out = {}
        await pg.goto(f"{B}/tide/index.html?st=9441102", wait_until="load")
        await read_qa(pg)
        sts = await pg.evaluate("TIDE.stations.map(s => s[0])")
        fails = []
        for st in sts:
            # Increment-based wait: load() may clear D after a same-page or cached navigation
            # while __tideDrawn is already > 0, so wait for a ready state() instead.
            await pg.goto(f"{B}/tide/index.html?st={st}", wait_until="load")
            q = await read_qa(pg)
            out[st] = q
            print(json.dumps({k: v for k, v in q.items() if k != "ready"}), flush=True)
            meth = str(q.get("method") or "")
            if not meth.startswith("stofs-free"):
                fails.append(f"{st}: method {meth!r} (want stofs-free)")
            if q.get("cond", 0) < 2:
                fails.append(f"{st}: Conditional line not painted (cond={q.get('cond')})")
        print("ERRORS", errs)
        await br.close()
        if errs:
            fails.extend(["page/console: " + e for e in errs[:8]])
        if fails:
            print("FAIL", *fails, sep="\n")
            raise SystemExit(1)
        print("OK", len(out), "stations")

asyncio.run(main())
