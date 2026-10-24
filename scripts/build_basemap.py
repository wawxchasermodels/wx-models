"""Turn public-domain shapefiles into clipped line JSON for the renderer.

Sources, both public domain:
- U.S. Census Bureau TIGER/Line 2023 cartographic boundaries, 1:5,000,000
- Natural Earth 10m coastline (naturalearthdata.com)

This script is a build tool. The site does not ship the shapefiles.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import shapefile

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "basemap"
WINDOW = (-155.0, -40.0, 2.0, 78.0)


def _rdp(points: list[tuple[float, float]], tol: float) -> list[tuple[float, float]]:
    if len(points) < 3:
        return points
    ax, ay = points[0]
    bx, by = points[-1]
    dx, dy = bx - ax, by - ay
    span = (dx * dx + dy * dy) ** 0.5 or 1.0
    pivot = 0
    best = -1.0
    for i in range(1, len(points) - 1):
        px, py = points[i]
        dist = abs(dy * px - dx * py + bx * ay - by * ax) / span
        if dist > best:
            best = dist
            pivot = i
    if best <= tol:
        return [points[0], points[-1]]
    left = _rdp(points[: pivot + 1], tol)
    right = _rdp(points[pivot:], tol)
    return left[:-1] + right


def _hits(xs, ys) -> bool:
    west, east, south, north = WINDOW
    return max(xs) >= west and min(xs) <= east and max(ys) >= south and min(ys) <= north


def _stride(points: list[tuple[float, float]], limit: int = 280) -> list[tuple[float, float]]:
    if len(points) <= limit:
        return points
    step = max(1, len(points) // limit)
    slim = points[::step]
    if slim[-1] != points[-1]:
        slim.append(points[-1])
    return slim


def _open_ring(points: list[tuple[float, float]]) -> tuple[list[tuple[float, float]], bool]:
    """Closed census polygons start and end on the same point. A zero-length chord collapses them."""
    closed = len(points) >= 4 and abs(points[0][0] - points[-1][0]) < 1e-6 and abs(points[0][1] - points[-1][1]) < 1e-6
    if closed:
        points = points[:-1]
    opened: list[tuple[float, float]] = []
    for point in points:
        if not opened or abs(point[0] - opened[-1][0]) > 1e-6 or abs(point[1] - opened[-1][1]) > 1e-6:
            opened.append(point)
    return opened, closed


def _clip_ring(points: list[tuple[float, float]], tol: float) -> list[list[float]] | None:
    if len(points) < 2:
        return None
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    if not _hits(xs, ys):
        return None
    opened, closed = _open_ring(points)
    if len(opened) < 2:
        return None
    simple = _rdp(_stride(opened), tol)
    if closed and simple[0] != simple[-1]:
        simple.append(simple[0])
    if len(simple) < 2:
        return None
    rounded = [[round(x, 3), round(y, 3)] for x, y in simple]
    distinct = [rounded[0]]
    for point in rounded[1:]:
        if point != distinct[-1]:
            distinct.append(point)
    if len(distinct) < 2:
        return None
    return distinct


def convert(path: Path, tol: float) -> list[list[list[float]]]:
    reader = shapefile.Reader(str(path))
    lines: list[list[list[float]]] = []
    for shape in reader.shapes():
        if shape.shapeType not in (3, 5, 13, 15, 23, 25):
            continue
        pts = [(float(x), float(y)) for x, y in shape.points]
        breaks = list(shape.parts) + [len(pts)]
        for start, end in zip(breaks, breaks[1:]):
            ring = _clip_ring(pts[start:end], tol)
            if ring and len(ring) >= 2:
                lines.append(ring)
    return lines


# Census cartographic files also contain Alaska, whose bbox crosses the dateline
# and therefore intersects every longitude window.
_SKIP_FIPS = {"02", "15", "60", "66", "69", "72", "78"}


def _wa_clip_box() -> tuple[float, float, float, float]:
    import sys

    sys.path.insert(0, str(ROOT))
    from wxmaps.project import view_lonlat, wa_view

    wide = 16.0 / ((1.0 - 0.132 - 0.138) * 9.0)
    reel = 9.0 / ((1.0 - 0.172 - 0.100) * 16.0)
    boxes = [view_lonlat(*wa_view(target), pad=0.8) for target in (wide, reel)]
    return (
        min(box[0] for box in boxes),
        max(box[1] for box in boxes),
        min(box[2] for box in boxes),
        max(box[3] for box in boxes),
    )


def _code(x: float, y: float, box: tuple[float, float, float, float]) -> int:
    west, east, south, north = box
    code = 0
    if x < west:
        code |= 1
    elif x > east:
        code |= 2
    if y < south:
        code |= 4
    elif y > north:
        code |= 8
    return code


def _clip_segment(p, q, box):
    west, east, south, north = box
    x0, y0 = p
    x1, y1 = q
    c0, c1 = _code(x0, y0, box), _code(x1, y1, box)
    for _ in range(12):
        if c0 == 0 and c1 == 0:
            return (x0, y0), (x1, y1)
        if c0 & c1:
            return None
        bit = c0 or c1
        if bit & 8:
            x = x0 + (x1 - x0) * (north - y0) / (y1 - y0)
            y = north
        elif bit & 4:
            x = x0 + (x1 - x0) * (south - y0) / (y1 - y0)
            y = south
        elif bit & 2:
            y = y0 + (y1 - y0) * (east - x0) / (x1 - x0)
            x = east
        else:
            y = y0 + (y1 - y0) * (west - x0) / (x1 - x0)
            x = west
        if bit == c0:
            x0, y0 = x, y
            c0 = _code(x0, y0, box)
        else:
            x1, y1 = x, y
            c1 = _code(x1, y1, box)
    return None


def _clip_polyline(points: list[tuple[float, float]], box, tol: float) -> list[list[list[float]]]:
    if len(points) < 2:
        return []
    pieces: list[list[tuple[float, float]]] = []
    current: list[tuple[float, float]] = []
    for start, end in zip(points, points[1:]):
        clipped = _clip_segment(start, end, box)
        if clipped is None:
            if len(current) >= 2:
                pieces.append(current)
            current = []
            continue
        a, b = clipped
        if not current:
            current = [a, b]
        else:
            if abs(current[-1][0] - a[0]) > 1e-9 or abs(current[-1][1] - a[1]) > 1e-9:
                pieces.append(current)
                current = [a, b]
            else:
                current.append(b)
    if len(current) >= 2:
        pieces.append(current)
    lines: list[list[list[float]]] = []
    for piece in pieces:
        opened, _closed = _open_ring(piece)
        simple = _rdp(opened, tol) if tol > 0 and len(opened) >= 3 else opened
        rounded = [[round(x, 4), round(y, 4)] for x, y in simple]
        distinct = [rounded[0]]
        for point in rounded[1:]:
            if point != distinct[-1]:
                distinct.append(point)
        if len(distinct) >= 2:
            lines.append(distinct)
    return lines


def _shape_lines(shape, box, tol: float) -> list[list[list[float]]]:
    pts = [(float(x), float(y)) for x, y in shape.points]
    breaks = list(shape.parts) + [len(pts)]
    lines: list[list[list[float]]] = []
    for start, end in zip(breaks, breaks[1:]):
        lines.extend(_clip_polyline(pts[start:end], box, tol))
    return lines


def _hit_x(a, b, x):
    span = b[0] - a[0]
    t = 0.0 if abs(span) < 1e-15 else (x - a[0]) / span
    return (x, a[1] + t * (b[1] - a[1]))


def _hit_y(a, b, y):
    span = b[1] - a[1]
    t = 0.0 if abs(span) < 1e-15 else (y - a[1]) / span
    return (a[0] + t * (b[0] - a[0]), y)


def _clip_polygon(points: list[tuple[float, float]], box) -> list[tuple[float, float]]:
    west, east, south, north = box

    def clip(poly, inside, cross):
        if not poly:
            return []
        out = []
        prev = poly[-1]
        for curr in poly:
            if inside(curr):
                if not inside(prev):
                    out.append(cross(prev, curr))
                out.append(curr)
            elif inside(prev):
                out.append(cross(prev, curr))
            prev = curr
        return out

    poly = clip(points, lambda p: p[0] >= west, lambda a, b: _hit_x(a, b, west))
    poly = clip(poly, lambda p: p[0] <= east, lambda a, b: _hit_x(a, b, east))
    poly = clip(poly, lambda p: p[1] >= south, lambda a, b: _hit_y(a, b, south))
    poly = clip(poly, lambda p: p[1] <= north, lambda a, b: _hit_y(a, b, north))
    return poly


def _ring(points: list[tuple[float, float]], tol: float) -> list[list[float]] | None:
    if len(points) < 3:
        return None
    opened, _closed = _open_ring(points)
    if len(opened) < 3:
        return None
    simple = _rdp(opened, tol)
    rounded = [[round(x, 4), round(y, 4)] for x, y in simple]
    distinct = [rounded[0]]
    for point in rounded[1:]:
        if point != distinct[-1]:
            distinct.append(point)
    if len(distinct) >= 2 and distinct[0] == distinct[-1]:
        distinct = distinct[:-1]
    if len(distinct) < 3:
        return None
    return distinct


def _drop_us_shore(lines: list[list[list[float]]], shore) -> list[list[list[float]]]:
    """Drop Natural Earth vertices that retrace the Census shoreline, and keep Canada."""
    import numpy as np

    if shore.size == 0:
        return lines
    cos = float(np.cos(np.deg2rad(47.5)))
    kept: list[list[list[float]]] = []
    shore_x = shore[:, 0] * cos
    shore_y = shore[:, 1]
    for line in lines:
        arr = np.asarray(line, dtype=np.float64)
        near = np.zeros(len(arr), dtype=bool)
        for start in range(0, len(arr), 250):
            chunk = arr[start : start + 250]
            dlon = chunk[:, 0:1] * cos - shore_x[None, :]
            dlat = chunk[:, 1:2] - shore_y[None, :]
            dist = np.sqrt(dlon * dlon + dlat * dlat).min(axis=1)
            near[start : start + 250] = dist < 0.02
        piece: list[list[float]] = []
        for point, drop in zip(line, near):
            if drop:
                if len(piece) >= 2:
                    kept.append(piece)
                piece = []
            else:
                piece.append(point)
        if len(piece) >= 2:
            kept.append(piece)
    return kept


def build_washington(src: Path) -> None:
    import numpy as np

    box = _wa_clip_box()
    state_path = src / "state500k" / "cb_2023_us_state_500k.shp"
    county_path = src / "county500k" / "cb_2023_us_county_500k.shp"
    coast_path = src / "coast" / "ne_10m_coastline.shp"
    land_path = src / "land" / "ne_10m_land.shp"
    for path in (state_path, county_path, coast_path, land_path):
        if not path.exists():
            raise SystemExit(f"missing {path}")

    state_lines: list[list[list[float]]] = []
    shore_pts: list[tuple[float, float]] = []
    states = shapefile.Reader(str(state_path))
    fields = [field[0] for field in states.fields[1:]]
    fips_i = fields.index("STATEFP")
    for rec, shape in zip(states.records(), states.shapes()):
        if str(rec[fips_i]) in _SKIP_FIPS:
            continue
        parts = _shape_lines(shape, box, 0.0008)
        if not parts:
            continue
        state_lines.extend(parts)
        for line in parts:
            shore_pts.extend((point[0], point[1]) for point in line)
    _write_lines(
        "wa_states",
        state_lines,
        "U.S. Census Bureau cartographic boundary 2023 state 500k, public domain",
    )

    county_lines: list[list[list[float]]] = []
    counties = shapefile.Reader(str(county_path))
    cfields = [field[0] for field in counties.fields[1:]]
    cfips = cfields.index("STATEFP")
    for rec, shape in zip(counties.records(), counties.shapes()):
        if str(rec[cfips]) != "53":
            continue
        county_lines.extend(_shape_lines(shape, box, 0.0012))
    _write_lines(
        "wa_counties",
        county_lines,
        "U.S. Census Bureau cartographic boundary 2023 county 500k, Washington, public domain",
    )

    coast_lines: list[list[list[float]]] = []
    coast = shapefile.Reader(str(coast_path))
    for shape in coast.shapes():
        coast_lines.extend(_shape_lines(shape, box, 0.0015))
    coast_lines = _drop_us_shore(coast_lines, np.asarray(shore_pts, dtype=np.float64) if shore_pts else np.zeros((0, 2)))
    _write_lines(
        "wa_coast",
        coast_lines,
        "Natural Earth 10m coastline outside the Census shoreline, public domain",
    )

    land_rings: list[list[list[float]]] = []
    land = shapefile.Reader(str(land_path))
    west, east, south, north = box
    for shape in land.shapes():
        pts = [(float(x), float(y)) for x, y in shape.points]
        breaks = list(shape.parts) + [len(pts)]
        for start, end in zip(breaks, breaks[1:]):
            part = pts[start:end]
            if len(part) < 3:
                continue
            xs = [point[0] for point in part]
            ys = [point[1] for point in part]
            if max(xs) < west or min(xs) > east or max(ys) < south or min(ys) > north:
                continue
            clipped = _clip_polygon(part, box)
            ring = _ring(clipped, 0.003)
            if ring:
                land_rings.append(ring)
    payload = {
        "source": "Natural Earth 10m land, public domain",
        "license": "public-domain",
        "polygons": land_rings,
    }
    dest = OUT / "wa_land.json"
    dest.write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")
    print(f"wa_land: {len(land_rings)} polygons, {dest.stat().st_size / 1e6:.2f} MB")


def _write_lines(name: str, lines: list[list[list[float]]], credit: str) -> None:
    dest = OUT / f"{name}.json"
    payload = {"source": credit, "license": "public-domain", "lines": lines}
    dest.write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")
    print(f"{name}: {len(lines)} lines, {dest.stat().st_size / 1e6:.2f} MB")


def main() -> int:
    src = Path(sys.argv[1] if len(sys.argv) > 1 else "/tmp/basemap-src")
    jobs = [
        ("states", src / "state" / "cb_2023_us_state_5m.shp", 0.012, "U.S. Census Bureau TIGER/Line 2023 state 5m, public domain"),
        ("counties", src / "county" / "cb_2023_us_county_5m.shp", 0.03, "U.S. Census Bureau TIGER/Line 2023 county 5m, public domain"),
        ("coast", src / "coast" / "ne_10m_coastline.shp", 0.02, "Natural Earth 10m coastline, public domain"),
    ]
    OUT.mkdir(parents=True, exist_ok=True)
    for name, path, tol, credit in jobs:
        if not path.exists():
            raise SystemExit(f"missing {path}")
        lines = convert(path, tol)
        payload = {"source": credit, "license": "public-domain", "lines": lines}
        dest = OUT / f"{name}.json"
        dest.write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")
        print(f"{name}: {len(lines)} lines, {dest.stat().st_size / 1e6:.2f} MB")
    if (src / "state500k" / "cb_2023_us_state_500k.shp").exists():
        build_washington(src)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
