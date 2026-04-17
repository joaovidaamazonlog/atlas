"""
phase1_area_intelligence.py
===========================
Orquestrador da Fase 1: Area Intelligence.

Fluxo:
  ingestor → enrichers (CNPJ, OSM, IBGE, Satélite) → feature_engineer
  → classifier → potential_calculator → area_selector

Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 2.1–2.7, 3.1–3.7, 4.1–4.9, 11.2
"""

from __future__ import annotations

import logging
from typing import Optional

import pandas as pd

from geo_intelligence.pipeline import RegionType, SelectedTerritory
from geo_intelligence.phase1_area_intelligence.ingestor import ingest_packages
from geo_intelligence.phase1_area_intelligence.enrichers.cnpj_enricher import CnpjEnricher
from geo_intelligence.phase1_area_intelligence.enrichers.osm_enricher import OsmEnricher
from geo_intelligence.phase1_area_intelligence.enrichers.ibge_enricher import IbgeEnricher
from geo_intelligence.phase1_area_intelligence.enrichers.satellite_enricher import SatelliteEnricher
from geo_intelligence.phase1_area_intelligence.feature_engineer import run_feature_engineering
from geo_intelligence.phase1_area_intelligence.classifier import classify_cells
from geo_intelligence.phase1_area_intelligence.potential_calculator import (
    compute_cell_potential,
    compute_territory_scores,
)
from geo_intelligence.phase1_area_intelligence.area_selector import select_areas

logger = logging.getLogger(__name__)

# Default potential weights (configurable via geo_config.py)
_DEFAULT_POTENTIAL_WEIGHTS: dict[str, float] = {
    "target_business_density": 0.25,
    "avg_income": 0.20,
    "population_density": 0.15,
    "region_type_weight": 0.20,
    "road_connectivity_index": 0.10,
    "commercial_activity_index": 0.10,
}

_DEFAULT_REGION_TYPE_WEIGHTS: dict[str, float] = {
    "comercial": 1.0,
    "residencial_alta_renda": 0.9,
    "alto_padrao": 0.85,
    "residencial_media_renda": 0.7,
    "residencial_baixa_renda": 0.5,
    "favela_comunidade": 0.4,
    "industrial": 0.3,
    "rural": 0.1,
}


def run_area_intelligence(
    station_code: str,
    target_pct: float,
    packages_df: pd.DataFrame,
    territories_geojson_path: str,
    territories_index: dict,  # {territory_id: {h3_ids: [...], current_partners: int, ideal_slots: int}}
    turso_url: str,
    turso_auth_token: str,
    ibge_census_path: str = "",
    models_dir: str = "models",
) -> tuple[list[SelectedTerritory], dict]:
    """
    Runs Phase 1: Area Intelligence.
    Returns (selected_territories, metrics_dict).

    Orchestrates: ingestor → enrichers → feature_engineer → classifier
                  → potential_calculator → area_selector

    Each enricher is wrapped in try/except for graceful degradation — if any
    external source is unavailable, its features are filled with None and the
    pipeline continues normally.
    """
    metrics: dict = {
        "station_code": station_code,
        "target_pct": target_pct,
        "enrichers": {},
        "classifier": {},
        "n_h3_cells": 0,
        "n_territories": 0,
    }

    # ------------------------------------------------------------------
    # Step 1: Ingest packages → {h3_id: delivery_count}
    # ------------------------------------------------------------------
    logger.info("[Phase 1] Station %s — ingesting packages.", station_code)
    h3_delivery_counts: dict[str, int] = ingest_packages(
        packages_df=packages_df,
        station_code=station_code,
        territories_geojson_path=territories_geojson_path,
    )

    if not h3_delivery_counts:
        logger.warning("[Phase 1] No H3 cells found for station %s. Returning empty.", station_code)
        return [], metrics

    h3_ids: list[str] = list(h3_delivery_counts.keys())
    metrics["n_h3_cells"] = len(h3_ids)
    logger.info("[Phase 1] %d H3 cells to enrich.", len(h3_ids))

    # ------------------------------------------------------------------
    # Step 2: Enrich — each enricher wrapped for graceful degradation
    # ------------------------------------------------------------------

    # 2a. CNPJ Enricher
    cnpj_features: dict[str, dict] = {}
    try:
        logger.info("[Phase 1] Running CnpjEnricher.")
        cnpj_enricher = CnpjEnricher(url=turso_url, auth_token=turso_auth_token)
        cnpj_features = cnpj_enricher.get_features_for_h3_cells(h3_ids)
        metrics["enrichers"]["cnpj"] = "ok"
    except Exception as exc:
        logger.error("[Phase 1] CnpjEnricher failed: %s. Continuing with empty features.", exc)
        cnpj_features = {h3_id: {} for h3_id in h3_ids}
        metrics["enrichers"]["cnpj"] = f"failed: {exc}"

    # 2b. OSM Enricher
    osm_features: dict[str, dict] = {}
    try:
        logger.info("[Phase 1] Running OsmEnricher.")
        osm_enricher = OsmEnricher()
        osm_features = osm_enricher.get_features_for_h3_cells(h3_ids)
        metrics["enrichers"]["osm"] = "ok"
    except Exception as exc:
        logger.error("[Phase 1] OsmEnricher failed: %s. Continuing with empty features.", exc)
        osm_features = {h3_id: {} for h3_id in h3_ids}
        metrics["enrichers"]["osm"] = f"failed: {exc}"

    # 2c. IBGE Enricher
    ibge_features: dict[str, dict] = {}
    try:
        logger.info("[Phase 1] Running IbgeEnricher.")
        ibge_enricher = IbgeEnricher(census_sectors_path=ibge_census_path)
        ibge_features = ibge_enricher.get_features_for_h3_cells(h3_ids)
        metrics["enrichers"]["ibge"] = "ok"
    except Exception as exc:
        logger.error("[Phase 1] IbgeEnricher failed: %s. Continuing with empty features.", exc)
        ibge_features = {h3_id: {} for h3_id in h3_ids}
        metrics["enrichers"]["ibge"] = f"failed: {exc}"

    # 2d. Satellite Enricher
    satellite_features: dict[str, dict] = {}
    try:
        logger.info("[Phase 1] Running SatelliteEnricher.")
        satellite_enricher = SatelliteEnricher()
        satellite_features = satellite_enricher.get_features_for_h3_cells(h3_ids)
        metrics["enrichers"]["satellite"] = "ok"
    except Exception as exc:
        logger.error("[Phase 1] SatelliteEnricher failed: %s. Continuing with empty features.", exc)
        satellite_features = {h3_id: {} for h3_id in h3_ids}
        metrics["enrichers"]["satellite"] = f"failed: {exc}"

    # ------------------------------------------------------------------
    # Step 3: Feature engineering (build → impute → normalize)
    # ------------------------------------------------------------------
    logger.info("[Phase 1] Running feature engineering.")
    cells, norm_params = run_feature_engineering(
        h3_ids=h3_ids,
        cnpj_features=cnpj_features,
        osm_features=osm_features,
        ibge_features=ibge_features,
        satellite_features=satellite_features,
    )
    metrics["norm_params"] = norm_params

    # ------------------------------------------------------------------
    # Step 4: Classify cells (HDBSCAN / KMeans fallback / supervised)
    # ------------------------------------------------------------------
    logger.info("[Phase 1] Classifying cells.")
    classifications, classifier_metrics, _umap_model = classify_cells(
        cells=cells,
        station_code=station_code,
        models_dir=models_dir,
    )
    metrics["classifier"] = classifier_metrics

    # Build lookup: h3_id → CellClassification
    classification_map = {c.h3_id: c for c in classifications}

    # ------------------------------------------------------------------
    # Step 5: Compute cell-level potential scores
    # ------------------------------------------------------------------
    logger.info("[Phase 1] Computing cell potentials.")
    cell_potentials: dict[str, float] = {}
    for cell in cells:
        classification = classification_map.get(cell.h3_id)
        score = compute_cell_potential(
            cell=cell,
            classification=classification,
            weights=_DEFAULT_POTENTIAL_WEIGHTS,
            region_type_weights=_DEFAULT_REGION_TYPE_WEIGHTS,
        )
        cell_potentials[cell.h3_id] = score

    # ------------------------------------------------------------------
    # Step 6: Build territory-level aggregations from territories_index
    # ------------------------------------------------------------------
    logger.info("[Phase 1] Building territory aggregations.")

    # territories_index: {territory_id: {h3_ids: [...], current_partners: int, ideal_slots: int}}
    territory_h3_ids: dict[str, list[str]] = {}
    current_partners: dict[str, int] = {}
    ideal_slots: dict[str, int] = {}

    for territory_id, info in territories_index.items():
        territory_h3_ids[territory_id] = info.get("h3_ids", [])
        current_partners[territory_id] = info.get("current_partners", 0)
        ideal_slots[territory_id] = info.get("ideal_slots", 0)

    # If territories_index is empty, create a single territory from all H3 cells
    if not territory_h3_ids:
        logger.warning(
            "[Phase 1] territories_index is empty — grouping all H3 cells into one territory."
        )
        territory_id = f"{station_code}_default"
        territory_h3_ids[territory_id] = h3_ids
        current_partners[territory_id] = 0
        ideal_slots[territory_id] = 0

    # Territory volumes: sum of delivery counts for all H3 cells in the territory
    territory_volumes: dict[str, int] = {
        tid: sum(h3_delivery_counts.get(h, 0) for h in h3s)
        for tid, h3s in territory_h3_ids.items()
    }

    # ------------------------------------------------------------------
    # Step 7: Compute territory scores
    # ------------------------------------------------------------------
    logger.info("[Phase 1] Computing territory scores.")
    territory_scores = compute_territory_scores(
        territories=territory_h3_ids,
        cell_potentials=cell_potentials,
        cell_volumes=h3_delivery_counts,
        current_partners=current_partners,
        ideal_slots=ideal_slots,
    )
    metrics["n_territories"] = len(territory_scores)

    # ------------------------------------------------------------------
    # Step 8: Build auxiliary dicts for area_selector
    # ------------------------------------------------------------------
    # Determine dominant region_type per territory (most common among its cells)
    territory_region_types: dict[str, RegionType] = {}
    territory_model_confidence: dict[str, float] = {}

    for tid, h3s in territory_h3_ids.items():
        region_counts: dict[RegionType, int] = {}
        confidences: list[float] = []

        for h3_id in h3s:
            clf = classification_map.get(h3_id)
            if clf:
                region_counts[clf.region_type] = region_counts.get(clf.region_type, 0) + 1
                confidences.append(clf.model_confidence)

        if region_counts:
            territory_region_types[tid] = max(region_counts, key=region_counts.get)
        else:
            territory_region_types[tid] = RegionType.RESIDENCIAL_MEDIA_RENDA

        territory_model_confidence[tid] = (
            sum(confidences) / len(confidences) if confidences else 0.0
        )

    # ------------------------------------------------------------------
    # Step 9: Select areas
    # ------------------------------------------------------------------
    logger.info("[Phase 1] Selecting areas (target_pct=%.1f%%).", target_pct)
    selected_territories = select_areas(
        territory_scores=territory_scores,
        territory_h3_ids_r8=territory_h3_ids,
        territory_h3_ids_r9={tid: [] for tid in territory_h3_ids},
        territory_region_types=territory_region_types,
        territory_model_confidence=territory_model_confidence,
        territory_volumes=territory_volumes,
        partner_profiles=[],
        target_pct=target_pct,
    )

    logger.info(
        "[Phase 1] Done. Selected %d territories out of %d.",
        len(selected_territories),
        len(territory_scores),
    )
    metrics["n_selected_territories"] = len(selected_territories)

    return selected_territories, metrics
