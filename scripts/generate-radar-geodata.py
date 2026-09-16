"""Build the lightweight Radar Caxx map asset from the source GeoPackages."""

from __future__ import annotations

import json
import math
import sqlite3
import struct
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BACKEND_SOURCE = ROOT / "backend" / "data" / "radar_caxx"
SOURCE = BACKEND_SOURCE
OUTPUT = ROOT / "frontend" / "js" / "data" / "radar-caxx-geodata.js"
MAINLAND_BOUNDS = (498_742.0, 9_445_216.0, 1_147_852.0, 10_162_547.0)


def _wkb_offset(blob: bytes) -> int:
    envelope_code = (blob[3] >> 1) & 0b111
    envelope_sizes = {0: 0, 1: 32, 2: 48, 3: 48, 4: 64}
    return 8 + envelope_sizes[envelope_code]


def _geometry(blob: bytes) -> list[list[list[float]]]:
    offset = _wkb_offset(blob)

    def read(position: int):
        byte_order = "<" if blob[position] == 1 else ">"
        geometry_type = struct.unpack_from(f"{byte_order}I", blob, position + 1)[0] % 1000
        position += 5
        if geometry_type == 3:
            ring_count = struct.unpack_from(f"{byte_order}I", blob, position)[0]
            position += 4
            rings = []
            for _ in range(ring_count):
                point_count = struct.unpack_from(f"{byte_order}I", blob, position)[0]
                position += 4
                ring = []
                for _ in range(point_count):
                    x, y = struct.unpack_from(f"{byte_order}dd", blob, position)
                    position += 16
                    ring.append([round(x, 1), round(y, 1)])
                rings.append(ring)
            return [rings], position
        if geometry_type == 6:
            polygon_count = struct.unpack_from(f"{byte_order}I", blob, position)[0]
            position += 4
            polygons = []
            for _ in range(polygon_count):
                nested, position = read(position)
                polygons.extend(nested)
            return polygons, position
        raise ValueError(f"Unsupported WKB geometry type: {geometry_type}")

    return read(offset)[0]


def _distance(point, start, end) -> float:
    dx, dy = end[0] - start[0], end[1] - start[1]
    if dx == dy == 0:
        return math.hypot(point[0] - start[0], point[1] - start[1])
    t = max(0.0, min(1.0, ((point[0] - start[0]) * dx + (point[1] - start[1]) * dy) / (dx * dx + dy * dy)))
    return math.hypot(point[0] - (start[0] + t * dx), point[1] - (start[1] + t * dy))


def _simplify(points, tolerance=850.0):
    if len(points) <= 4:
        return points
    source = points[:-1] if points[0] == points[-1] else points

    def reduce(part):
        if len(part) <= 2:
            return part
        distances = [_distance(point, part[0], part[-1]) for point in part[1:-1]]
        maximum = max(distances, default=0)
        if maximum <= tolerance:
            return [part[0], part[-1]]
        index = distances.index(maximum) + 1
        return reduce(part[: index + 1])[:-1] + reduce(part[index:])

    # A closed ring has coincident endpoints, so split it at the farthest vertex.
    anchor = source[0]
    split = max(range(1, len(source)), key=lambda index: math.dist(anchor, source[index]))
    reduced = reduce(source[: split + 1])[:-1] + reduce([*source[split:], source[0]])
    if reduced[0] != reduced[-1]:
        reduced.append(reduced[0])
    return reduced if len(reduced) >= 4 else points


def _load_country():
    with sqlite3.connect(SOURCE / "ecuador.gpkg") as connection:
        blob = connection.execute("SELECT geom FROM ecuador LIMIT 1").fetchone()[0]
    return [[_simplify(ring) for ring in polygon] for polygon in _geometry(blob)]


def _load_cantons():
    with sqlite3.connect(SOURCE / "Cantones_Ecuador.gpkg") as connection:
        rows = connection.execute("SELECT geom, CANTON FROM cantones_Ecuador").fetchall()
    cantons, cuenca = [], []
    min_x, min_y, max_x, max_y = MAINLAND_BOUNDS
    for blob, name in rows:
        polygons = _geometry(blob)
        mainland_polygons = []
        for polygon in polygons:
            simplified = [_simplify(ring) for ring in polygon]
            if any(min_x <= x <= max_x and min_y <= y <= max_y for ring in simplified for x, y in ring):
                mainland_polygons.append(simplified)
        if mainland_polygons:
            feature = {"name": str(name).title(), "polygons": mainland_polygons}
            (cuenca if str(name).upper() == "CUENCA" else cantons).append(feature)
    return cantons, cuenca


def _load_named_features(path: Path, table: str, name_column: str, tolerance: float):
    with sqlite3.connect(path) as connection:
        rows = connection.execute(f'SELECT geom, "{name_column}" FROM "{table}"').fetchall()
    features = []
    for index, (blob, name) in enumerate(rows, start=1):
        polygons = [
            [_simplify(ring, tolerance) for ring in polygon]
            for polygon in _geometry(blob)
        ]
        features.append({"name": str(name or index).title(), "polygons": polygons})
    return features


def _wgs84_to_utm17s(longitude: float, latitude: float):
    # Standard WGS84 transverse-Mercator equations for UTM zone 17 South.
    a, eccentricity_squared, scale = 6_378_137.0, 0.00669437999014, 0.9996
    lat, lon, central = map(math.radians, (latitude, longitude, -81.0))
    prime = a / math.sqrt(1 - eccentricity_squared * math.sin(lat) ** 2)
    tangent = math.tan(lat) ** 2
    second = eccentricity_squared / (1 - eccentricity_squared) * math.cos(lat) ** 2
    arc = math.cos(lat) * (lon - central)
    meridian = a * (
        (1 - eccentricity_squared / 4 - 3 * eccentricity_squared**2 / 64 - 5 * eccentricity_squared**3 / 256) * lat
        - (
            3 * eccentricity_squared / 8
            + 3 * eccentricity_squared**2 / 32
            + 45 * eccentricity_squared**3 / 1024
        )
        * math.sin(2 * lat)
        + (15 * eccentricity_squared**2 / 256 + 45 * eccentricity_squared**3 / 1024)
        * math.sin(4 * lat)
        - (35 * eccentricity_squared**3 / 3072) * math.sin(6 * lat)
    )
    easting_series = (
        arc
        + (1 - tangent + second) * arc**3 / 6
        + (
            5
            - 18 * tangent
            + tangent**2
            + 72 * second
            - 58 * eccentricity_squared / (1 - eccentricity_squared)
        )
        * arc**5
        / 120
    )
    northing_series = (
        arc**2 / 2
        + (5 - tangent + 9 * second + 4 * second**2) * arc**4 / 24
        + (
            61
            - 58 * tangent
            + tangent**2
            + 600 * second
            - 330 * eccentricity_squared / (1 - eccentricity_squared)
        )
        * arc**6
        / 720
    )
    easting = scale * prime * easting_series + 500_000
    northing = scale * (meridian + prime * math.tan(lat) * northing_series) + 10_000_000
    return [round(easting, 3), round(northing, 3)]


def main():
    cantons, cuenca = _load_cantons()
    payload = {
        "crs": "EPSG:32717",
        "bounds": MAINLAND_BOUNDS,
        "radar": _wgs84_to_utm17s(-79.246278, -2.759986),
        "radii": [20_000, 60_000, 100_000],
        "country": _load_country(),
        "cantons": cantons,
        "cuenca": cuenca,
        "subcuencas": _load_named_features(
            BACKEND_SOURCE / "Subcuencas.gpkg", "sub_paute", "Subcuenca", 350.0
        ),
        "zonaUrbana": _load_named_features(
            BACKEND_SOURCE / "ZonaUrbana.gpkg", "cuenca", "DESCRIP", 80.0
        ),
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(f"window.RADAR_CAXX_GEODATA={json.dumps(payload, separators=(',', ':'))};\n", encoding="utf-8")
    print(f"Generated {OUTPUT.relative_to(ROOT)} ({OUTPUT.stat().st_size:,} bytes); radar UTM {payload['radar']}")


if __name__ == "__main__":
    main()
