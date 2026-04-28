"""
MKT Plans analysis.

Reads "MKT Plans.xlsx" (sheet with campaign coordinates + radii in MILES),
cleans the noisy coordinates, builds circle buffers per plan+type, computes
total area in km^2 (deduplicated via unary_union), intersects with the
delivery-station jurisdictions in config/jurisdiction.geojson and emits:

- output_data/mkt_plans_areas.csv           Total area km^2 per plan/type
- output_data/mkt_plans_coverage_by_ds.csv  Area km^2 per plan/type inside each DS
- output_data/mkt_plans_invalid_rows.csv    Rows whose coords could not be fixed
- output_data/mkt_plans_map.html            Interactive Leaflet map
"""
from __future__ import annotations

import json
import math
import re
from pathlib import Path

import folium
import pandas as pd
from folium.plugins import GroupedLayerControl
from pyproj import Transformer
from shapely.geometry import Point, mapping, shape
from shapely.ops import transform, unary_union

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

ROOT = Path(__file__).resolve().parent.parent
XLSX_PATH = ROOT / "MKT Plans.xlsx"
GEOJSON_PATH = ROOT / "config" / "jurisdiction.geojson"
OUT_DIR = ROOT / "output_data"
OUT_DIR.mkdir(exist_ok=True)

MILE_TO_KM = 1.609344

# Approximate city centres used as sanity anchors for coordinate cleaning.
CITY_ANCHORS = {
    "belo horizonte": (-19.92, -43.94),
    "rio de janeiro": (-22.91, -43.20),
    "sao paulo": (-23.55, -46.63),
    "são paulo": (-23.55, -46.63),
    "recife": (-8.05, -34.90),
    "salvador": (-12.97, -38.50),
    "fortaleza": (-3.73, -38.52),
    "porto alegre": (-30.03, -51.22),
}

# Plausible BR bounds (latitude, longitude).
LAT_RANGE = (-34.0, 6.0)
LON_RANGE = (-75.0, -33.0)

PLAN_COLORS = {
    "A": "#1f77b4",
    "B": "#d62728",
    "C": "#2ca02c",
    "D": "#ff7f0e",
    "E": "#9467bd",
    "F": "#17becf",
}

# ---------------------------------------------------------------------------
# Coordinate cleaning
# ---------------------------------------------------------------------------


def _candidates(raw: str) -> list[float]:
    """Return plausible numeric interpretations of a noisy coordinate string."""
    s = str(raw).strip()
    if not s:
        return []

    neg = s.startswith("-")
    digits = re.sub(r"\D", "", s)
    if not digits:
        return []

    # Drop leading zeros but keep at least one digit.
    digits = digits.lstrip("0") or "0"

    cands: list[float] = []
    for shift in range(0, len(digits) + 1):
        if shift == 0:
            value = float(digits)
        else:
            value = float(digits) / (10 ** shift)
        if neg:
            value = -value
        cands.append(value)

    # Also consider the raw string when it already looks numeric with a dot
    # (e.g. "-19.923" or "-43.94" from plan A).
    try:
        cands.append(float(s.replace(",", ".")))
    except ValueError:
        pass

    return cands


def _best_pair(
    raw_lat: str,
    raw_lon: str,
    city: str,
) -> tuple[float, float] | None:
    """Pick the (lat, lon) interpretation nearest the declared city anchor."""
    anchor = CITY_ANCHORS.get(city.strip().lower())

    lat_options = [
        v for v in _candidates(raw_lat) if LAT_RANGE[0] <= v <= LAT_RANGE[1]
    ]
    lon_options = [
        v for v in _candidates(raw_lon) if LON_RANGE[0] <= v <= LON_RANGE[1]
    ]
    if not lat_options or not lon_options:
        return None

    best: tuple[float, float] | None = None
    best_score = math.inf
    for lat in lat_options:
        for lon in lon_options:
            if anchor is not None:
                score = (lat - anchor[0]) ** 2 + (lon - anchor[1]) ** 2
            else:
                # Without an anchor, prefer the most "precise" option (more
                # decimals) which corresponds to the largest shift applied.
                score = abs(lat) + abs(lon)
            if score < best_score:
                best_score = score
                best = (lat, lon)

    # Reject if it still falls way outside the anchor (more than ~3 degrees,
    # roughly 330 km) when an anchor was available.
    if best is not None and anchor is not None:
        if math.hypot(best[0] - anchor[0], best[1] - anchor[1]) > 3.0:
            return None
    return best


# ---------------------------------------------------------------------------
# Load and clean
# ---------------------------------------------------------------------------


def load_plans() -> tuple[pd.DataFrame, pd.DataFrame]:
    raw = pd.read_excel(XLSX_PATH, sheet_name=0, header=None, dtype=str)

    # Find the header row (contains "Campaign").
    header_row = None
    for i, row in raw.iterrows():
        if row.astype(str).str.contains("Campaign", case=False, na=False).any():
            header_row = i
            break
    if header_row is None:
        raise RuntimeError("Could not locate header row in spreadsheet")

    header = raw.iloc[header_row].astype(str).str.strip().tolist()
    df = raw.iloc[header_row + 1 :].copy()
    df.columns = header

    # Map whatever header names exist to our canonical names.
    def _find(*needles: str) -> str:
        for col in df.columns:
            low = col.lower()
            if all(n in low for n in needles):
                return col
        raise KeyError(f"header not found: {needles}")

    rename = {
        _find("campaign"): "Campaign",
        _find("city"): "City",
        _find("latitude"): "Latitude",
        _find("longitude"): "Longitude",
        _find("search"): "RadiusSearchMi",
        _find("demand"): "RadiusDemandMi",
    }
    df = df.rename(columns=rename)[list(rename.values())]
    df = df.dropna(subset=["Campaign", "City", "Latitude", "Longitude"]).reset_index(drop=True)

    cleaned_rows = []
    invalid_rows = []
    for _, r in df.iterrows():
        pair = _best_pair(r["Latitude"], r["Longitude"], r["City"])
        rec = {
            "Campaign": r["Campaign"].strip(),
            "City": r["City"].strip(),
            "raw_lat": r["Latitude"],
            "raw_lon": r["Longitude"],
        }
        try:
            rs = float(str(r["RadiusSearchMi"]).replace(",", "."))
            rd = float(str(r["RadiusDemandMi"]).replace(",", "."))
        except (TypeError, ValueError):
            rs = rd = math.nan
        rec["radius_search_mi"] = rs
        rec["radius_demand_mi"] = rd
        rec["radius_search_km"] = rs * MILE_TO_KM if not math.isnan(rs) else math.nan
        rec["radius_demand_km"] = rd * MILE_TO_KM if not math.isnan(rd) else math.nan

        if pair is None or math.isnan(rs) or math.isnan(rd):
            invalid_rows.append(rec)
            continue
        rec["lat"], rec["lon"] = pair
        cleaned_rows.append(rec)

    cleaned = pd.DataFrame(cleaned_rows)
    invalid = pd.DataFrame(invalid_rows)
    return cleaned, invalid


# ---------------------------------------------------------------------------
# Geometry helpers
# ---------------------------------------------------------------------------


def buffer_km(lon: float, lat: float, radius_km: float):
    """Return a shapely polygon (WGS84) of a circle of radius_km around lon/lat."""
    # Azimuthal equidistant projection centred on the point keeps radial
    # distance faithful, so a Point buffered by radius_m in that plane becomes
    # an accurate circle when reprojected back to WGS84.
    proj_str = (
        f"+proj=aeqd +lat_0={lat} +lon_0={lon} +x_0=0 +y_0=0 "
        "+datum=WGS84 +units=m +no_defs"
    )
    to_local = Transformer.from_crs("EPSG:4326", proj_str, always_xy=True).transform
    to_wgs = Transformer.from_crs(proj_str, "EPSG:4326", always_xy=True).transform
    circle_local = Point(0, 0).buffer(radius_km * 1000, resolution=64)
    return transform(to_wgs, circle_local)


def area_km2(geom) -> float:
    """Equal-area projection over Brazil to get area in km^2."""
    proj = (
        "+proj=aea +lat_1=-10 +lat_2=-30 +lat_0=-20 +lon_0=-55 "
        "+x_0=0 +y_0=0 +datum=WGS84 +units=m +no_defs"
    )
    to_proj = Transformer.from_crs("EPSG:4326", proj, always_xy=True).transform
    return transform(to_proj, geom).area / 1_000_000.0


# ---------------------------------------------------------------------------
# Main analysis
# ---------------------------------------------------------------------------


def main() -> None:
    print("Loading spreadsheet...")
    df, invalid = load_plans()
    print(f"  valid rows: {len(df)}  |  invalid rows: {len(invalid)}")
    invalid.to_csv(OUT_DIR / "mkt_plans_invalid_rows.csv", index=False)

    print("Loading jurisdictions...")
    with open(GEOJSON_PATH, encoding="utf-8") as f:
        juris_geo = json.load(f)
    ds_polys = {
        feat["properties"]["delivery_station"]: shape(feat["geometry"]).buffer(0)
        for feat in juris_geo["features"]
    }

    print("Building circle buffers per row...")
    df["circle_search"] = df.apply(
        lambda r: buffer_km(r["lon"], r["lat"], r["radius_search_km"]), axis=1
    )
    df["circle_demand"] = df.apply(
        lambda r: buffer_km(r["lon"], r["lat"], r["radius_demand_km"]), axis=1
    )

    # -- Per-plan / per-type totals (deduplicated via union) -----------------
    area_rows = []
    unions: dict[tuple[str, str], object] = {}
    for campaign, sub in df.groupby("Campaign"):
        for label, col in (("Search", "circle_search"), ("Demand Generation", "circle_demand")):
            union = unary_union(sub[col].tolist())
            unions[(campaign, label)] = union
            area_rows.append(
                {
                    "Campaign": campaign,
                    "Type": label,
                    "Circles": len(sub),
                    "Sum of individual areas (km²)": round(
                        sum(area_km2(g) for g in sub[col]), 2
                    ),
                    "Union area (km²)": round(area_km2(union), 2),
                    "Active DSs": 0,              # filled later
                    "DS coverage (km²)": 0.0,     # filled later
                    "DS coverage %": 0.0,         # filled later
                }
            )

    # -- Coverage per delivery station --------------------------------------
    # A DS only counts for a given (plan, type) if at least one campaign point
    # falls inside it.
    ds_area_cache = {name: area_km2(poly) for name, poly in ds_polys.items()}

    active_ds: dict[tuple[str, str], list[str]] = {}
    for campaign, sub in df.groupby("Campaign"):
        for label in ("Search", "demand"):
            key_label = "Search" if label == "Search" else "Demand Generation"
            names: list[str] = []
            for ds_name, poly in ds_polys.items():
                has_point = any(
                    poly.contains(Point(lon, lat))
                    for lon, lat in zip(sub["lon"], sub["lat"])
                )
                if has_point:
                    names.append(ds_name)
            active_ds[(campaign, key_label)] = names

    cov_rows = []
    drilldown: dict[tuple[str, str], list[dict]] = {}
    for (campaign, label), union in unions.items():
        safe_union = union if union.is_valid else union.buffer(0)
        entries: list[dict] = []
        for ds_name in active_ds[(campaign, label)]:
            poly = ds_polys[ds_name]
            if not safe_union.intersects(poly):
                continue
            try:
                inter = safe_union.intersection(poly)
            except Exception:
                inter = safe_union.buffer(0).intersection(poly.buffer(0))
            if inter.is_empty:
                continue
            inter_area = area_km2(inter)
            ds_area = ds_area_cache[ds_name]
            row = {
                "Campaign": campaign,
                "Type": label,
                "delivery_station": ds_name,
                "DS area (km²)": round(ds_area, 2),
                "MKT area (km²)": round(inter_area, 2),
                "Diff mkt-ds (km²)": round(inter_area - ds_area, 2),
                "MKT/DS %": round(inter_area / ds_area * 100, 2),
            }
            cov_rows.append(row)
            entries.append(row)
        entries.sort(key=lambda r: r["MKT/DS %"], reverse=True)
        drilldown[(campaign, label)] = entries
    cov_df = pd.DataFrame(cov_rows).sort_values(
        ["Campaign", "Type", "MKT/DS %"], ascending=[True, True, False]
    )
    cov_df.to_csv(OUT_DIR / "mkt_plans_coverage_by_ds.csv", index=False)
    print(f"\nCoverage rows: {len(cov_df)}  (see mkt_plans_coverage_by_ds.csv)")

    # Patch the per-plan DS coverage %. Use the UNION of active DS polygons
    # as both numerator base (intersected with the plan's circle union) and
    # as denominator, so that overlaps between DSs don't double-count.
    for row in area_rows:
        key = (row["Campaign"], row["Type"])
        entries = drilldown[key]
        active_polys = [ds_polys[e["delivery_station"]] for e in entries]
        row["Active DSs"] = len(entries)
        if not active_polys:
            row["DS coverage (km²)"] = 0.0
            row["DS coverage %"] = 0.0
            continue
        active_union = unary_union(active_polys)
        active_union_area = area_km2(active_union)
        union = unions[key]
        safe_union = union if union.is_valid else union.buffer(0)
        try:
            inter = safe_union.intersection(active_union)
        except Exception:
            inter = safe_union.buffer(0).intersection(active_union.buffer(0))
        inter_area = area_km2(inter) if not inter.is_empty else 0.0
        row["DS coverage (km²)"] = round(inter_area, 2)
        row["DS coverage %"] = (
            round(inter_area / active_union_area * 100, 2) if active_union_area else 0.0
        )
    areas_df = pd.DataFrame(area_rows).sort_values(["Campaign", "Type"])
    areas_df.to_csv(OUT_DIR / "mkt_plans_areas.csv", index=False)
    print("\n=== Area per plan/type (DS % over active DSs only) ===")
    print(areas_df.to_string(index=False))

    # -- Map -----------------------------------------------------------------
    print("\nBuilding map...")
    # Use all valid points to find a sensible centre.
    centre_lat = df["lat"].mean()
    centre_lon = df["lon"].mean()
    fmap = folium.Map(location=[centre_lat, centre_lon], zoom_start=5, tiles="CartoDB positron")

    # Jurisdiction base layer.
    juris_group = folium.FeatureGroup(name="Delivery Stations", show=True)
    folium.GeoJson(
        juris_geo,
        name="jurisdictions",
        style_function=lambda _: {
            "fillColor": "#444",
            "color": "#111",
            "weight": 1.2,
            "fillOpacity": 0.08,
        },
        tooltip=folium.GeoJsonTooltip(fields=["delivery_station"], aliases=["DS:"]),
    ).add_to(juris_group)
    juris_group.add_to(fmap)

    # One layer per plan/type.
    plan_layers = []
    for (campaign, label), union in sorted(unions.items()):
        color = PLAN_COLORS.get(campaign, "#555")
        opacity = 0.35 if label == "Search" else 0.15
        group = folium.FeatureGroup(
            name=f"Plano {campaign} — {label}",
            show=(campaign == "A"),
        )
        sub = df[df["Campaign"] == campaign]
        circle_col = "circle_search" if label == "Search" else "circle_demand"
        for _, row in sub.iterrows():
            geojson_geom = mapping(row[circle_col])
            folium.GeoJson(
                geojson_geom,
                style_function=lambda _f, color=color, opacity=opacity: {
                    "fillColor": color,
                    "color": color,
                    "weight": 1,
                    "fillOpacity": opacity,
                },
                tooltip=(
                    f"Plano {campaign} — {label}<br>"
                    f"{row['City']}<br>"
                    f"raio: {row['radius_search_mi' if label == 'Search' else 'radius_demand_mi']} mi"
                ),
            ).add_to(group)
        group.add_to(fmap)
        plan_layers.append(group)

    folium.LayerControl(collapsed=False, position="topright").add_to(fmap)

    # Side panel with area summary + drill-down per DS.
    def _fmt(n: float, digits: int = 0) -> str:
        return f"{n:,.{digits}f}".replace(",", "\u00A0")

    rows_html: list[str] = []
    for _, row in areas_df.iterrows():
        key = (row["Campaign"], row["Type"])
        entries = drilldown.get(key, [])
        color = PLAN_COLORS.get(row["Campaign"], "#555")
        header = (
            f"<summary style='cursor:pointer; padding:4px 0; list-style:none;'>"
            f"<span style='display:inline-block; width:8px; height:8px;"
            f" background:{color}; margin-right:6px; vertical-align:middle;'></span>"
            f"<b>Plano {row['Campaign']}</b> — {row['Type']}"
            f" &nbsp;·&nbsp; {_fmt(row['Union area (km²)'])} km²"
            f" &nbsp;·&nbsp; DS cobertas: {row['Active DSs']}"
            f" ({_fmt(row['DS coverage %'], 1)}%)"
            f"</summary>"
        )
        if entries:
            inner = (
                "<table class='drill-table'><thead><tr>"
                "<th>DS</th><th>DS km²</th><th>MKT km²</th>"
                "<th>Diff</th><th>MKT/DS %</th>"
                "</tr></thead><tbody>"
                + "".join(
                    f"<tr><td>{e['delivery_station']}</td>"
                    f"<td>{_fmt(e['DS area (km²)'], 1)}</td>"
                    f"<td>{_fmt(e['MKT area (km²)'], 1)}</td>"
                    f"<td style='color:{'#c00' if e['Diff mkt-ds (km²)'] < 0 else '#060'};'>"
                    f"{_fmt(e['Diff mkt-ds (km²)'], 1)}</td>"
                    f"<td>{_fmt(e['MKT/DS %'], 1)}%</td></tr>"
                    for e in entries
                )
                + "</tbody></table>"
            )
        else:
            inner = "<div style='color:#888; padding:4px 12px;'>sem DSs ativas</div>"
        rows_html.append(
            f"<details style='border-bottom:1px solid #eee; padding:2px 0;'>"
            f"{header}{inner}</details>"
        )

    totals_note = (
        f"Jurisdições: {len(ds_polys)} DS no total<br>"
        f"Válidas: {len(df)} linhas · Descartadas: {len(invalid)}<br>"
        f"<span style='color:#888;'>% calculada só sobre DSs com ≥1 ponto do plano.</span>"
    )

    legend_html = f"""
    <div style="
        position: fixed; top: 12px; left: 12px; z-index: 9999;
        background: white; padding: 12px 14px; border: 1px solid #aaa;
        border-radius: 6px; font: 12px/1.3 Arial, sans-serif;
        width: 360px; max-height: 85vh; overflow: auto;
        box-shadow: 0 2px 6px rgba(0,0,0,.15);">
        <div style="font-weight: 600; margin-bottom: 6px;">
            Área por plano (km²) — clique para detalhar por DS
        </div>
        <style>
            .drill-table {{
                border-collapse: collapse; width: 100%; margin: 4px 0 8px 16px;
                font-size: 11px;
            }}
            .drill-table th, .drill-table td {{
                padding: 2px 6px; border-bottom: 1px solid #f0f0f0; text-align: right;
            }}
            .drill-table th:first-child, .drill-table td:first-child {{
                text-align: left;
            }}
            .drill-table th {{ color: #666; font-weight: 500; }}
            details[open] > summary {{ color: #000; }}
            summary::-webkit-details-marker {{ display: none; }}
            summary::before {{
                content: "▸"; display: inline-block; width: 10px;
                margin-right: 2px; color: #888;
            }}
            details[open] > summary::before {{ content: "▾"; }}
        </style>
        {''.join(rows_html)}
        <div style="margin-top: 10px; color: #666;">
            {totals_note}
        </div>
    </div>
    """
    fmap.get_root().html.add_child(folium.Element(legend_html))

    out_html = OUT_DIR / "mkt_plans_map.html"
    fmap.save(str(out_html))
    print(f"Map saved to {out_html}")


if __name__ == "__main__":
    main()
