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
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
