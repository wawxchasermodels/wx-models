import asyncio, sys
from playwright.async_api import async_playwright
B = sys.argv[1].rstrip("/"); O = "/workspace/wx-models-site/tide_floodlines_mock_20261114/shots/"
async def page(br, w, h, dpr):
    pg = await br.new_page(viewport={"width": w, "height": h}, device_scale_factor=dpr); return pg
async def load(pg, q):
    await pg.goto(f"{B}/tide/index.html?{q}", wait_until="load"); await pg.wait_for_function("window.__tideDrawn > 0", timeout=90000); await pg.wait_for_timeout(800)
async def main():
    async with async_playwright() as p:
        br = await p.chromium.launch(args=["--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader"])
        pg = await page(br, 1920, 1080, 2)
        for st, nm in [("9441102", "westport"), ("9447130", "seattle"), ("9449880", "fridayharbor"), ("birchbay", "birchbay"), ("9439040", "astoria")]:
            await load(pg, f"st={st}&days=9"); await pg.screenshot(path=f"{O}web_{nm}_floodlines_1920x1080@2x.png")
        # station list A to Z: render the <select> as an expanded listbox so the screenshot shows every option
        await load(pg, "st=9441102&days=9")
        await pg.evaluate("""() => { const s = document.getElementById('st'); s.size = s.options.length; s.style.position = 'absolute'; s.style.zIndex = 50; s.style.height = 'auto'; s.style.background = '#262931'; }""")
        await pg.screenshot(path=f"{O}station_list_AtoZ_1920x1080@2x.png", clip={"x": 0, "y": 0, "width": 900, "height": 520})
        ph = await page(br, 390, 844, 3)
        await load(ph, "st=9441102&days=9"); await ph.screenshot(path=f"{O}phone_westport_floodlines_390x844@3x.png")
        await load(ph, "st=birchbay&days=9"); await ph.screenshot(path=f"{O}phone_birchbay_390x844@3x.png")
        await br.close()
asyncio.run(main())
