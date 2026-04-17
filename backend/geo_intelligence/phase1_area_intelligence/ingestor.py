"""
ingestor.py
===========
Maps package deliveries to H3 cells (resolution 8) and filters them to
those within the DS jurisdiction polygon read from territories.geojson.
Applies DELIVERY_DENSITY_THRESHOLD to filter out low-demand cells.

Requirements: 1.1, 1.5, 1.6, 1.7, 2.1, 10.1
"""

from __future__ import annotations

import json
import logging
from collections import Counter
from pathlib import Path

import h3
import pandas as pd
from shapely.geometry import MultiPolygon, Point, Polygon, shape

from geo_intelligence.geo_config import DELIVERY_DENSITY_THRESHOLD

logger = logging.getLogger(__name__)


def _load_jurisdiction_polygon(
    territories_geojson_path: str,
    station_code: str,
) -> MultiPolygon | Polygon | None:
    """
    Reads territories.geojson and returns the union of all polygons that
    belong to *station_code* (matched via the ``delivery_station`` property).

    Returns None if the file is not found or the station has no features.
    The file is opened in read-only mode and never modified.
    """
    path = Path(territories_geojson_path)
    if not path.exists():
        logger.warning(
            "territories.geojson not found at '%s'. "
            "Jurisdiction filtering will be skipped.",
            territories_geojson_path,
        )
        return None

    with path.open("r", encoding="utf-8") as fh:
        geojson = json.load(fh)

    features = [
        f
        for f in geojson.get("features", [])
        if f.get("properties", {}).get("delivery_station") == station_code
    ]

    if not features:
        logger.warning(
            "No features found for station '%s' in '%s'. "
            "Jurisdiction filtering will be skipped.",
            station_code,
            territories_geojson_path,
        )
        return None

    # Build a single unified geometry from all territory polygons of this DS.
    geometries = [shape(f["geometry"]) for f in features]
    if len(geometries) == 1:
        return geometries[0]

    # Merge all polygons into one MultiPolygon (or Polygon after union).
    from shapely.ops import unary_union  # local import to keep top-level light

    return unary_union(geometries)


def _h3_cell_centroid(h3_id: str) -> tuple[float, float]:
    """Returns (lat, lng) centroid of an H3 cell."""
    lat, lng = h3.cell_to_latlng(h3_id)
    return lat, lng


def _is_within_jurisdiction(h3_id: str, jurisdiction: Polygon | MultiPolygon) -> bool:
    """
    Checks whether the centroid of *h3_id* lies within *jurisdiction*.
    Using the centroid is fast and accurate enough for resolution-9 cells
    (~0.1 km²), where the centroid is always well inside the cell boundary.
    """
    lat, lng = _h3_cell_centroid(h3_id)
    return jurisdiction.contains(Point(lng, lat))


def ingest_packages(
    packages_df: pd.DataFrame,
    station_code: str,
    territories_geojson_path: str,
    lat_col: str = "lat",
    lng_col: str = "lng",
) -> dict[str, int]:
    """
    Maps package deliveries to H3 cells (res 8) within the DS jurisdiction,
    then applies DELIVERY_DENSITY_THRESHOLD to filter out low-demand cells.

    Parameters
    ----------
    packages_df:
        DataFrame with at least *lat_col* and *lng_col* columns.
    station_code:
        Delivery-station code used to look up the jurisdiction polygon
        (e.g. ``"DSP2"``).
    territories_geojson_path:
        Path to the existing ``territories.geojson`` file.  Read-only.
    lat_col:
        Name of the latitude column in *packages_df*.
    lng_col:
        Name of the longitude column in *packages_df*.

    Returns
    -------
    dict[str, int]
        ``{h3_id: delivery_count}`` for H3 cells (res 8) inside the
        jurisdiction that meet the DELIVERY_DENSITY_THRESHOLD.
        If the jurisdiction polygon cannot be loaded, all H3 cells that
        meet the threshold are returned (graceful degradation).
    """
    if packages_df.empty:
        logger.warning("packages_df is empty — returning empty result.")
        return {}

    # --- Step 1: map each delivery to an H3 cell at resolution 8 ----------
    def _to_h3(row: pd.Series) -> str | None:
        try:
            return h3.latlng_to_cell(float(row[lat_col]), float(row[lng_col]), 8)
        except Exception as exc:  # noqa: BLE001
            logger.debug("Could not map row to H3 cell: %s", exc)
            return None

    h3_series = packages_df.apply(_to_h3, axis=1)
    valid_mask = h3_series.notna()
    if not valid_mask.any():
        logger.warning("No valid H3 cells could be computed from packages_df.")
        return {}

    h3_counts: dict[str, int] = Counter(h3_series[valid_mask].tolist())

    # --- Step 2: load jurisdiction polygon (read-only) ---------------------
    jurisdiction = _load_jurisdiction_polygon(territories_geojson_path, station_code)

    if jurisdiction is None:
        # Graceful degradation: return all cells without filtering.
        logger.warning(
            "Returning all %d H3 cells without jurisdiction filtering.",
            len(h3_counts),
        )
        jurisdiction_filtered = dict(h3_counts)
    else:
        # --- Step 3: filter to cells inside the jurisdiction --------------
        jurisdiction_filtered = {
            h3_id: count
            for h3_id, count in h3_counts.items()
            if _is_within_jurisdiction(h3_id, jurisdiction)
        }
        logger.info(
            "Station %s: %d H3 cells mapped, %d within jurisdiction.",
            station_code,
            len(h3_counts),
            len(jurisdiction_filtered),
        )

    # --- Step 4: apply delivery density threshold (viability filter) ------
    before_threshold = len(jurisdiction_filtered)
    filtered: dict[str, int] = {
        h3_id: count
        for h3_id, count in jurisdiction_filtered.items()
        if count >= DELIVERY_DENSITY_THRESHOLD
    }
    filtered_out = before_threshold - len(filtered)
    if filtered_out > 0:
        logger.info(
            "Station %s: %d H3 cells filtered out by DELIVERY_DENSITY_THRESHOLD=%d "
            "(%d cells remaining).",
            station_code,
            filtered_out,
            DELIVERY_DENSITY_THRESHOLD,
            len(filtered),
        )

    return filtered
