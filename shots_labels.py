import asyncio, sys, json, base64
from playwright.async_api import async_playwright
B = sys.argv[1].rstrip("/"); O = "/workspace/wx-models-site/tide_floodlines_mock_20261114/shots/"
async def load(pg, q):
    await pg.goto(f"{B}/tide/index.html?{q}", wait_until="load"); await pg.wait_for_function("window.__tideDrawn > 0", timeout=90000); await pg.wait_for_timeout(800)
async def main():
    async with async_playwright() as p:
        br = await p.chromium.launch(args=["--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader"])
        pg = await br.new_page(viewport={"width": 1920, "height": 1080}, device_scale_factor=2)
        for st, nm in [("9441102", "westport"), ("9447130", "seattle"), ("birchbay", "birchbay"), ("9449880", "fridayharbor")]:
            await load(pg, f"st={st}&days=9"); await pg.screenshot(path=f"{O}web_{nm}_floodlines_1920x1080@2x.png")
            L = await pg.evaluate("TIDE.qa().floodLabels"); print(nm, json.dumps(L))
            if nm == "westport":
                b = await pg.evaluate("(() => { const r = document.getElementById('tc').getBoundingClientRect(); return [r.left, r.top]; })()")
                xs = [l["x0"] for l in L] + [l["x1"] for l in L]; ys = [l["yc"] for l in L]
                clip = {"x": b[0] + min(xs) - 40, "y": b[1] + min(ys) - 45, "width": max(xs) - min(xs) + 260, "height": max(ys) - min(ys) + 90}
                await pg.screenshot(path=f"{O}crop_westport_flood_labels@2x.png", clip=clip)
        ph = await br.new_page(viewport={"width": 390, "height": 844}, device_scale_factor=3)
        await load(ph, "st=9441102&days=9"); await ph.screenshot(path=f"{O}phone_westport_floodlines_390x844@3x.png")
        sp = await br.new_page(viewport={"width": 1920, "height": 1080})
        await sp.goto(B + "/studio.html", wait_until="load"); await sp.wait_for_timeout(5000)
        await sp.select_option("#smode", "tide"); await sp.wait_for_function("() => window.__studioTide > 0", timeout=90000)
        await sp.frame_locator("#tdf").locator("#st").select_option("9441102")
        await sp.wait_for_function("() => document.getElementById('tdf').contentWindow.TIDE.qa().st === '9441102'", timeout=90000); await sp.wait_for_timeout(3000)
        d = await sp.evaluate("() => document.getElementById('ch').toDataURL('image/png')")
        open(f"{O}studio_frame16x9_westport_3840x2160.png", "wb").write(base64.b64decode(d.split(',')[1]))
        await br.close()
asyncio.run(main())
