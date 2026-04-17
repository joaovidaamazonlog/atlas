"""
feature_engineer.py
===================
Consolida features de todos os enrichers em instâncias de H3CellFeatures,
aplica imputação por mediana dos vizinhos H3 e normalização min-max por DS.
Persiste parâmetros de normalização em JSON por station_code.

Requirements: 2.1, 2.2, 2.3, 2.5, 2.6, 2.7
"""

from __future__ import annotations

import dataclasses
import json
import logging
import statistics
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import h3

from geo_intelligence.geo_config import DELIVERY_DENSITY_WEIGHT
from geo_intelligence.pipeline import H3CellFeatures

logger = logging.getLogger(__name__)

NUMERIC_FEATURES: tuple[str, ...] = (
    "company_density", "cnae_diversity_index", "target_business_density",
    "building_density", "avg_building_size_m2", "landuse_residential_ratio",
    "landuse_commercial_ratio", "poi_density", "road_connectivity_index",
    "avg_income", "population_density", "bars_restaurants_density",
    "churches_density", "schools_density", "dealerships_density",
    "petshops_density", "landuse_entropy", "road_centrality_index",
    "local_clustering_coefficient", "ndvi_mean", "urban_density_index",
    "built_up_ratio",
    # Derived feature (v2) — Req 2.7
    "commercial_activity_index",
    # Context feature (v2) — Req 2.2, weight capped at DELIVERY_DENSITY_WEIGHT
    "delivery_density_r8",
)


def build_features(
    h3_ids: list[str],
    cnpj_features: dict[str, dict],
    osm_features: dict[str, dict],
    ibge_features: dict[str, dict],
    satellite_features: dict[str, dict],
    delivery_density_map: dict[str, float] | None = None,
) -> list[H3CellFeatures]:
    """Merges enricher outputs into H3CellFeatures instances.

    Parameters
    ----------
    delivery_density_map:
        Optional mapping of h3_id → normalized delivery density (res 8).
        When provided, populates ``delivery_density_r8`` on each cell.
    """
    cells: list[H3CellFeatures] = []
    for h3_id in h3_ids:
        cnpj = cnpj_features.get(h3_id) or {}
        osm = osm_features.get(h3_id) or {}
        ibge = ibge_features.get(h3_id) or {}
        sat = satellite_features.get(h3_id) or {}

        landuse_commercial_ratio = osm.get("landuse_commercial_ratio")
        target_business_density = cnpj.get("target_business_density")

        # Req 2.7: commercial_activity_index = (landuse_commercial_ratio + target_business_density) / 2
        commercial_activity_index: Optional[float] = None
        if landuse_commercial_ratio is not None and target_business_density is not None:
            commercial_activity_index = (landuse_commercial_ratio + target_business_density) / 2

        delivery_density_r8: Optional[float] = None
        if delivery_density_map is not None:
            delivery_density_r8 = delivery_density_map.get(h3_id)

        cells.append(H3CellFeatures(
            h3_id=h3_id,
            company_density=cnpj.get("company_density"),
            cnae_diversity_index=cnpj.get("cnae_diversity_index"),
            target_business_density=target_business_density,
            building_density=osm.get("building_density"),
            avg_building_size_m2=osm.get("avg_building_size_m2"),
            landuse_residential_ratio=osm.get("landuse_residential_ratio"),
            landuse_commercial_ratio=landuse_commercial_ratio,
            poi_density=osm.get("poi_density"),
            road_connectivity_index=osm.get("road_connectivity_index"),
            avg_income=ibge.get("avg_income"),
            population_density=ibge.get("population_density"),
            bars_restaurants_density=cnpj.get("bars_restaurants_density"),
            churches_density=cnpj.get("churches_density"),
            schools_density=cnpj.get("schools_density"),
            dealerships_density=cnpj.get("dealerships_density"),
            petshops_density=cnpj.get("petshops_density"),
            landuse_entropy=osm.get("landuse_entropy"),
            road_centrality_index=osm.get("road_centrality_index"),
            local_clustering_coefficient=osm.get("local_clustering_coefficient"),
            ndvi_mean=sat.get("ndvi_mean"),
            urban_density_index=sat.get("urban_density_index"),
            built_up_ratio=sat.get("built_up_ratio"),
            morphology_class=sat.get("morphology_class"),
            commercial_activity_index=commercial_activity_index,
            delivery_density_r8=delivery_density_r8,
        ))
    return cells


def impute_missing(
    cells: list[H3CellFeatures],
    all_cells_map: dict[str, H3CellFeatures],
) -> list[H3CellFeatures]:
    """Imputes None values using median of first-ring H3 neighbors."""
    result: list[H3CellFeatures] = []
    for cell in cells:
        ring = h3.grid_disk(cell.h3_id, 1)
        neighbor_ids = ring - {cell.h3_id}
        updates: dict[str, Optional[float]] = {}
        for feat in NUMERIC_FEATURES:
            if getattr(cell, feat) is not None:
                continue
            neighbor_vals = [
                getattr(all_cells_map[nid], feat)
                for nid in neighbor_ids
                if nid in all_cells_map and getattr(all_cells_map[nid], feat) is not None
            ]
            if neighbor_vals:
                updates[feat] = statistics.median(neighbor_vals)
        if updates:
            cell = dataclasses.replace(cell, **updates)
        result.append(cell)
    return result


def normalize_features(
    cells: list[H3CellFeatures],
    station_code: str = "unknown",
) -> tuple[list[H3CellFeatures], dict[str, dict]]:
    """Applies min-max normalization. Returns (normalized_cells, norm_params).

    Persists norm_params as JSON in ``models/{station_code}_norm_params_{timestamp}.json``,
    keeping only the 3 most recent files per station.
    """
    if not cells:
        return [], {}

    norm_params: dict[str, dict] = {}
    for feat in NUMERIC_FEATURES:
        values = [getattr(c, feat) for c in cells if getattr(c, feat) is not None]
        if values:
            norm_params[feat] = {"min": min(values), "max": max(values)}

    normalized: list[H3CellFeatures] = []
    for cell in cells:
        updates: dict[str, Optional[float]] = {}
        for feat, params in norm_params.items():
            val = getattr(cell, feat)
            if val is None:
                continue
            feat_min, feat_max = params["min"], params["max"]
            updates[feat] = 0.0 if feat_max == feat_min else (val - feat_min) / (feat_max - feat_min)
        if updates:
            cell = dataclasses.replace(cell, **updates)
        normalized.append(cell)

    # Persist norm_params and keep only the 3 most recent files
    _persist_norm_params(norm_params, station_code)

    return normalized, norm_params


def _persist_norm_params(norm_params: dict[str, dict], station_code: str) -> None:
    """Saves norm_params to models/{station_code}_norm_params_{timestamp}.json.
    Keeps only the 3 most recent files for this station.
    """
    models_dir = Path("models")
    try:
        models_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        filename = models_dir / f"{station_code}_norm_params_{timestamp}.json"
        with filename.open("w", encoding="utf-8") as fh:
            json.dump(norm_params, fh)
        logger.info("Norm params persisted to %s", filename)

        # Purge old files — keep only the 3 most recent
        existing = sorted(
            models_dir.glob(f"{station_code}_norm_params_*.json"),
            key=lambda p: p.stat().st_mtime,
        )
        for old_file in existing[:-3]:
            old_file.unlink(missing_ok=True)
            logger.debug("Removed old norm params file: %s", old_file)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Could not persist norm params: %s", exc)


def run_feature_engineering(
    h3_ids: list[str],
    cnpj_features: dict[str, dict],
    osm_features: dict[str, dict],
    ibge_features: dict[str, dict],
    satellite_features: dict[str, dict],
    delivery_density_map: dict[str, float] | None = None,
    station_code: str = "unknown",
) -> tuple[list[H3CellFeatures], dict[str, dict]]:
    """Full pipeline: build → impute → normalize. Returns (cells, norm_params).

    Parameters
    ----------
    delivery_density_map:
        Optional mapping of h3_id → normalized delivery density (res 8).
        Passed through to ``build_features()``.
    station_code:
        Used to name the persisted norm_params JSON file.
    """
    cells = build_features(
        h3_ids, cnpj_features, osm_features, ibge_features, satellite_features,
        delivery_density_map=delivery_density_map,
    )
    all_cells_map = {c.h3_id: c for c in cells}
    cells = impute_missing(cells, all_cells_map)
    return normalize_features(cells, station_code=station_code)
