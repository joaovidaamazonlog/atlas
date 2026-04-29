"""
Generate a CSV that replicates Plan B format but provides 100% coverage of the
canonical delivery-station jurisdictions it used to touch, EXCLUDING satellite
areas (PUM2, XCP1, ...) and DSP2.

Approach
--------
- Target set is the Plan B DSs restricted to *canonical* bases (any DS present
  in STATION_ALIASES keys is a satellite and is dropped), with DSP2 also
  removed per request.
- For each target DS polygon we tile it with a hexagonal grid of points spaced
  so that circles of radius = Demand Generation radius (4 mi) fully cover it
  (spacing = r * sqrt(3), plus an overshoot margin around the bbox).
- Any grid point whose buffer intersects the DS polygon is kept, then we clip
  to the set whose 4-mi buffer (or the DS polygon) keeps the DS fully covered.
- City label / Search radius are inherited from the closest Plan-B city, so the
  output schema matches the original "MKT Plans.xlsx" layout.

Writes: output_data/mkt_plan_b_full_coverage.csv
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import pandas as pd
from pyproj import Transformer
from shapely.geometry import Point, shape
from shapely.ops import transform, unary_union

ROOT = Path(__file__).resolve().parent.parent
GEOJSON_PATH = ROOT / "config" / "jurisdiction.geojson"
OUT_PATH = ROOT / "output_data" / "mkt_plan_b_full_coverage.csv"

# Campaign label for the generated plan.
# G = "Plan B, full coverage of canonical bases only (no satellites, no DSP2)".
NEW_CAMPAIGN = "G"

MILE_TO_KM = 1.609344
DEMAND_RADIUS_MI = 4  # same as Plan B demand generation everywhere
DEMAND_RADIUS_KM = DEMAND_RADIUS_MI * MILE_TO_KM

# Satellite codes — any DS present here is an area-satellite of a canonical
# base and must NOT be targeted directly by the plan. Kept in sync with
# backend/shared/config.py::STATION_ALIASES. Duplicated locally so this
# script has no dependency on the backend package.
SATELLITE_CODES = {
    "XBA1", "XCS1", "XGA2", "XPB1",
    "PUM2", "XRJ2", "XRJ4",
    "XSJ1", "XSP7", "XSP9", "XCP1",
}

# DSs originally touched by Plan B.
PLAN_B_DS_NAMES = {
    "DMG2", "DRJ3", "DSP2", "DPE4", "PUM2",
    "DBH5", "DSP4", "DBR9", "DSP5", "DCE3", "XCP1",
}
# Additional canonical DSs explicitly requested for plan G. They are added on
# top of the Plan-B-derived canonical set.
EXTRA_TARGET_DS = {
    "DCE3", "DPB3", "DPE4", "DSA8", "DES2", "DBS5", "DGO2", "DPR2", "DRS5",
}
# Explicit exclusions on top of the satellite filter.
EXCLUDED_DS = {"DSP2"}
# Target only canonical bases, minus explicit exclusions.
TARGET_DS = ((PLAN_B_DS_NAMES | EXTRA_TARGET_DS) - SATELLITE_CODES) - EXCLUDED_DS

# Plan B city -> (search radius mi, demand radius mi) and an anchor centroid.
CITY_RADII = {
    "Belo Horizonte": (4, 4),
    "Rio de Janeiro": (4, 4),
    "Sao Paulo": (1, 4),
    "Recife": (2, 4),
    "Fortaleza": (4, 4),
    # New canonical DSs added in a later expansion. Default to the same
    # 4 mi / 4 mi pair used by BH/RJ/Fortaleza unless told otherwise.
    "Salvador": (4, 4),
    "Brasilia": (4, 4),
    "Goiania": (4, 4),
    "Vitoria": (4, 4),
    "Joao Pessoa": (4, 4),
    "Curitiba": (4, 4),
    "Porto Alegre": (4, 4),
}
CITY_ANCHOR = {
    "Belo Horizonte": (-19.92, -43.94),
    "Rio de Janeiro": (-22.91, -43.20),
    "Sao Paulo": (-23.55, -46.63),
    "Recife": (-8.05, -34.90),
    "Fortaleza": (-3.73, -38.52),
    "Salvador": (-12.97, -38.50),
    "Brasilia": (-15.78, -47.92),
    "Goiania": (-16.68, -49.25),
    "Vitoria": (-20.32, -40.34),
    "Joao Pessoa": (-7.12, -34.86),
    "Curitiba": (-25.43, -49.27),
    "Porto Alegre": (-30.03, -51.22),
}


def nearest_city(lat: float, lon: float) -> str:
    best = None
    best_d = math.inf
    for city, (la, lo) in CITY_ANCHOR.items():
        d = (lat - la) ** 2 + (lon - lo) ** 2
        if d < best_d:
            best_d = d
            best = city
    return best or "Sao Paulo"


def local_projection(lat0: float, lon0: float):
    """Return (to_local, to_wgs) transformers in an AEQD metric frame."""
    proj_str = (
        f"+proj=aeqd +lat_0={lat0} +lon_0={lon0} +x_0=0 +y_0=0 "
        "+datum=WGS84 +units=m +no_defs"
    )
    to_local = Transformer.from_crs("EPSG:4326", proj_str, always_xy=True).transform
    to_wgs = Transformer.from_crs(proj_str, "EPSG:4326", always_xy=True).transform
    return to_local, to_wgs


def hex_cover_points(ds_poly, radius_m: float):
    """Tile a polygon with a hex grid whose circles (radius_m) fully cover it.

    All returned points are guaranteed to lie *inside* ``ds_poly`` so they do
    not fall inside neighbouring jurisdictions (e.g. satellite areas or
    excluded DSs). Returns a list of (lon, lat) points in WGS84.
    """
    # Project to a local AEQD at the polygon centroid so distances are metres.
    c = ds_poly.centroid
    to_local, to_wgs = local_projection(c.y, c.x)
    poly_local = transform(to_local, ds_poly)

    minx, miny, maxx, maxy = poly_local.bounds
    # Pad by one radius so the grid around the border has candidates on both
    # sides; points outside the polygon are filtered below.
    pad = radius_m
    minx -= pad
    miny -= pad
    maxx += pad
    maxy += pad

    # Hex grid with spacing r*sqrt(3) horizontally, 1.5*r vertically.
    # Every circle of radius r then covers every point within radius r,
    # and the lattice leaves no gap (circle radius > circumradius of hex cell).
    dx = radius_m * math.sqrt(3)
    dy = radius_m * 1.5

    candidates: list[Point] = []
    y = miny
    row = 0
    while y <= maxy:
        x_off = 0.0 if row % 2 == 0 else dx / 2
        x = minx + x_off
        while x <= maxx:
            p = Point(x, y)
            # Only keep candidates whose centre lies inside the polygon so the
            # plan does not target areas that belong to other (satellite)
            # jurisdictions.
            if poly_local.contains(p) and p.buffer(radius_m).intersects(poly_local):
                candidates.append(p)
            x += dx
        y += dy
        row += 1

    # Greedy trim: drop points whose buffer adds no new polygon coverage.
    # Sort points so those nearer the polygon centroid come first.
    candidates.sort(key=lambda p: p.distance(poly_local.centroid))
    kept_local: list[Point] = []
    covered = None
    for p in candidates:
        circle = p.buffer(radius_m).intersection(poly_local)
        if circle.is_empty:
            continue
        if covered is None:
            kept_local.append(p)
            covered = circle
            continue
        if covered.contains(poly_local):
            break
        remaining = poly_local.difference(covered)
        if remaining.is_empty:
            break
        if circle.intersects(remaining):
            kept_local.append(p)
            covered = covered.union(circle)

    # Fill any remaining slivers with interior points. We repeatedly pick the
    # representative_point() of the uncovered region, which is guaranteed to
    # lie inside the polygon (so we never emit coordinates outside the
    # canonical jurisdiction).
    for _ in range(50):
        if covered is None:
            remaining = poly_local
        else:
            remaining = poly_local.difference(covered)
        if remaining.is_empty:
            break
        # If remaining has multiple components, iterate across them.
        parts = list(getattr(remaining, "geoms", [remaining]))
        # Largest slivers first so we make progress quickly.
        parts.sort(key=lambda g: getattr(g, "area", 0.0), reverse=True)
        progress = False
        for part in parts:
            if part.is_empty or part.area < 1.0:  # skip sub-m² slivers
                continue
            rp = part.representative_point()
            # representative_point of `part` is inside `part` (which is inside
            # poly_local), so no extra containment check needed.
            circle = rp.buffer(radius_m).intersection(poly_local)
            if circle.is_empty:
                continue
            kept_local.append(rp)
            covered = circle if covered is None else covered.union(circle)
            progress = True
        if not progress:
            break

    # Guarantee at least one point even for microscopic polygons.
    if not kept_local:
        rp = poly_local.representative_point()
        kept_local.append(rp)

    # Reproject to WGS84.
    return [transform(to_wgs, p) for p in kept_local]


def main() -> None:
    with open(GEOJSON_PATH, encoding="utf-8") as f:
        gj = json.load(f)

    ds_polys = {}
    for feat in gj["features"]:
        name = feat["properties"]["delivery_station"]
        if name in TARGET_DS:
            ds_polys[name] = shape(feat["geometry"]).buffer(0)

    missing = TARGET_DS - ds_polys.keys()
    if missing:
        raise RuntimeError(f"Missing DS polygons in geojson: {missing}")

    rows: list[dict] = []
    summary: list[dict] = []

    for ds_name in sorted(ds_polys):
        poly = ds_polys[ds_name]
        c = poly.centroid
        city = nearest_city(c.y, c.x)
        r_search, r_demand = CITY_RADII[city]
        # Size the hex grid with the SMALLER of the two radii so that both the
        # Search circles and the Demand Generation circles fully cover the
        # canonical polygon.
        tile_radius_mi = min(r_search, r_demand)
        tile_radius_m = tile_radius_mi * MILE_TO_KM * 1000.0
        pts = hex_cover_points(poly, tile_radius_m)
        for p in pts:
            rows.append(
                {
                    "Campaign": NEW_CAMPAIGN,
                    "City": city,
                    "Latitude": round(p.y, 6),
                    "Longitude": round(p.x, 6),
                    "Target Radius SEARCH": r_search,
                    "Target Radius DEMAND GENERATION": r_demand,
                    "DeliveryStation": ds_name,
                }
            )
        summary.append(
            {
                "DS": ds_name,
                "city": city,
                "tile_r_mi": tile_radius_mi,
                "points": len(pts),
            }
        )

    out_df = pd.DataFrame(rows)
    OUT_PATH.parent.mkdir(exist_ok=True)
    out_df.to_csv(OUT_PATH, index=False)

    print(f"Wrote {OUT_PATH} with {len(out_df)} rows across {len(ds_polys)} DSs")
    print("Per-DS summary:")
    for s in summary:
        print(
            f"  {s['DS']:6s} ({s['city']:15s}) tile r={s['tile_r_mi']} mi "
            f"-> {s['points']} points"
        )

    # Sanity check: report total coverage vs DS area (projected) for both
    # Search and Demand Generation radii.
    print("\nCoverage check (should be ~100% for each DS, both radii):")
    for ds_name, poly in ds_polys.items():
        c = poly.centroid
        to_local, _ = local_projection(c.y, c.x)
        poly_local = transform(to_local, poly)
        ds_rows = out_df[out_df["DeliveryStation"] == ds_name]
        if ds_rows.empty:
            print(f"  {ds_name:6s}:   0.00% search |   0.00% demand")
            continue
        r_search_m = ds_rows.iloc[0]["Target Radius SEARCH"] * MILE_TO_KM * 1000.0
        r_demand_m = (
            ds_rows.iloc[0]["Target Radius DEMAND GENERATION"] * MILE_TO_KM * 1000.0
        )
        search_circles = []
        demand_circles = []
        for _, rr in ds_rows.iterrows():
            px, py = to_local(rr["Longitude"], rr["Latitude"])
            search_circles.append(Point(px, py).buffer(r_search_m))
            demand_circles.append(Point(px, py).buffer(r_demand_m))
        pct_search = (
            unary_union(search_circles).intersection(poly_local).area
            / poly_local.area
            * 100
        )
        pct_demand = (
            unary_union(demand_circles).intersection(poly_local).area
            / poly_local.area
            * 100
        )
        print(
            f"  {ds_name:6s}: {pct_search:6.2f}% search | {pct_demand:6.2f}% demand"
        )


if __name__ == "__main__":
    main()
