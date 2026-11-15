import asyncio, sys
from playwright.async_api import async_playwright
async def main():
    B = sys.argv[1]; O = sys.argv[2]
    async with async_playwright() as p:
        br = await p.chromium.launch(args=["--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader"])
        pg = await br.new_page(viewport={"width":1920,"height":1080}, device_scale_factor=1)
        errs=[]; pg.on("pageerror", lambda e: errs.append(str(e)[:200]))
        await pg.goto(B + "/studio.html", wait_until="load"); await pg.wait_for_timeout(5000)
        await pg.select_option("#smode", "tide")
        try:
            await pg.wait_for_function("() => window.__studioTide > 0", timeout=90000)
        except Exception as e: print("no tide frames", e)
        fr = pg.frame_locator("#tdf")
        await fr.locator("#st").select_option(sys.argv[3])
        await pg.wait_for_function("(k) => document.getElementById('tdf').contentWindow.TIDE.qa().st === k", arg=sys.argv[3], timeout=90000)
        await pg.wait_for_timeout(3000)
        q = await pg.evaluate("() => { const q = document.getElementById('tdf').contentWindow.TIDE.qa(); return {st:q.st, floods:q.floods, drawn:q.floodDrawn}; }")
        print(q, "studioTide", await pg.evaluate("window.__studioTide"))
        await pg.screenshot(path=O)
        # full-res 16:9 frame canvas
        data = await pg.evaluate("() => document.getElementById('ch').toDataURL('image/png')")
        import base64; open(O.replace('.png','_frame16x9_3840x2160.png'),'wb').write(base64.b64decode(data.split(',')[1]))
        data = await pg.evaluate("() => document.getElementById('cv').toDataURL('image/png')")
        open(O.replace('.png','_frame9x16_2160x3840.png'),'wb').write(base64.b64decode(data.split(',')[1]))
        print("errs", errs)
        await br.close()
asyncio.run(main())
