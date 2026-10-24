"""Render one synthetic plate and assemble a tiny site."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from wxmaps.assemble import assemble
from wxmaps.attribution import ecmwf_map_credit
from wxmaps.derive import Payload
from wxmaps.plot import render_plate


def test_synthetic_plate_writes_a_webp_with_basemap_and_credit(tmp_path: Path):
    lats = np.linspace(49.0, 45.5, 30)
    lons = np.linspace(-125.0, -116.8, 40)
    values = 20 + (lats[:, None] - 47) * 6 + (lons[None, :] + 121)
    payload = Payload(
        field_id="t2m",
        title="2 m temperature",
        unit="°F",
        subtitle="32°F is the light-blue step",
        scale="temp_f",
        values=values.astype(np.float32),
        u=None,
        v=None,
        contours=None,
        contour_kind="none",
        categories=None,
        mask_below=None,
        lats=lats.astype(np.float32),
        lons=lons.astype(np.float32),
        regular=True,
    )
    dest = tmp_path / "wide.webp"
    render_plate(
        payload,
        "wa",
        "wide",
        datetime(2026, 10, 21, 12, tzinfo=timezone.utc),
        12,
        "ECMWF IFS 9 km",
        "ecmwf",
        dest,
    )
    blob = dest.read_bytes()
    assert blob[:4] == b"RIFF"
    assert b"WEBP" in blob[:16]
    assert dest.stat().st_size > 5000
    assert "CC BY 4.0" in ecmwf_map_credit(2026)
    from PIL import Image

    image = Image.open(dest).convert("RGB")
    width, height = image.size
    # The colored strip sits in the footer, above the tick baseline.
    row = height - int(0.075 * height)
    pixels = [image.getpixel((x, row)) for x in range(int(width * 0.15), int(width * 0.85), 12)]
    frame = (201, 187, 166)
    colored = [px for px in pixels if max(abs(px[i] - frame[i]) for i in range(3)) > 18]
    assert len(colored) > 8
    assert len({px for px in colored}) > 4
    # Image rows start at the top. The map slot runs from the header to the footer and reaches the side.
    mid = (0.132 + (1.0 - 0.138)) / 2.0
    edge = image.getpixel((4, int(mid * height)))
    assert max(abs(edge[i] - frame[i]) for i in range(3)) > 18


def test_assemble_stamps_the_footer(tmp_path: Path):
    store = tmp_path / "store"
    init = store / "ecmwf" / "2026102112"
    init.mkdir(parents=True)
    (init / "_chunk_00.json").write_text(
        '{"model":"ecmwf","init":"2026102112","model_label":"ECMWF IFS 9 km","attribution":"ecmwf","fields":{"t2m":{"label":"2 m temperature","unit":"°F","hours":[12]}}}',
        encoding="utf-8",
    )
    frame = init / "t2m" / "us" / "wide" / "f012.webp"
    frame.parent.mkdir(parents=True)
    frame.write_bytes(b"RIFF")
    dest = tmp_path / "dist"
    manifest = assemble(store, dest, keep=2)
    html = (dest / "index.html").read_text(encoding="utf-8")
    assert "WX Models" in html
    assert "Source: ECMWF open data, CC BY 4.0" in html
    assert "SIL Open Font License" in html
    assert manifest["models"]["ecmwf"]["label"] == "ECMWF IFS 9 km"
    assert (dest / "frames" / "ecmwf" / "2026102112" / "t2m" / "us" / "wide" / "f012.webp").exists()
    assert (dest / "fonts" / "OFL-Outfit.txt").exists()
