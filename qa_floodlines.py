import asyncio, json, sys
from playwright.async_api import async_playwright
B = sys.argv[1].rstrip("/")
async def main():
    async with async_playwright() as p:
        br = await p.chromium.launch(args=["--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader"])
        pg = await br.new_page(viewport={"width": 1440, "height": 900}, device_scale_factor=1)
        errs = []; pg.on("pageerror", lambda e: errs.append(str(e))); pg.on("console", lambda m: errs.append(m.text) if m.type == "error" else None)
        out = {}
        sts = None
        for st in ["9441102"]:
            await pg.goto(f"{B}/tide/index.html?st={st}", wait_until="load"); await pg.wait_for_function("window.__tideDrawn > 0", timeout=90000)
            sts = await pg.evaluate("TIDE.stations.map(s => s[0])")
        for st in sts:
            await pg.goto(f"{B}/tide/index.html?st={st}", wait_until="load"); await pg.wait_for_function("window.__tideDrawn > 0", timeout=90000)
            q = await pg.evaluate("(() => { const q = TIDE.qa(); const D = TIDE.state(); let hi=-1e9; for (const a of [D.pred,D.obs,D.cond]) for (const [,v] of a) hi=Math.max(hi,v); return {st:q.st,sid:q.sid,name:q.name,floods:q.floods,skip:q.floodSkip,drawn:q.floodDrawn,dataHi:hi,obs:q.obs,cond:q.cond,method:q.method,ver:q.ver}; })()")
            out[st] = q; print(json.dumps(q), flush=True)
        print("ERRORS", errs)
        await br.close()
asyncio.run(main())
