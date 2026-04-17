"""
pipeline.py
===========
Dataclasses e enums do pipeline GeoIntelligence.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

try:
    import numpy as np
    _np_available = True
except ImportError:  # pragma: no cover
    _np_available = False


# ---------------------------------------------------------------------------
# Enumerações
# ---------------------------------------------------------------------------

class RegionType(str, Enum):
    FAVELA_COMUNIDADE = "favela_comunidade"
    RESIDENCIAL_BAIXA_RENDA = "residencial_baixa_renda"
    RESIDENCIAL_MEDIA_RENDA = "residencial_media_renda"
    RESIDENCIAL_ALTA_RENDA = "residencial_alta_renda"
    COMERCIAL = "comercial"
    INDUSTRIAL = "industrial"
    RURAL = "rural"
    ALTO_PADRAO = "alto_padrao"


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------

@dataclass
class GeoSetupConfig:
    station_code: str
    expansion_target_pct: float          # 0–100, passado via --target
    potential_weights: dict[str, float]  # pesos configuráveis
    cp_time_limit_s: int = 300
    supervised_min_samples: int = 50


@dataclass
class H3CellFeatures:
    h3_id: str
    # Econômicas (Turso: CNPJ + Google Maps)
    company_density: Optional[float]
    cnae_diversity_index: Optional[float]
    target_business_density: Optional[float]
    # Urbanas (OSM)
    building_density: Optional[float]
    avg_building_size_m2: Optional[float]
    landuse_residential_ratio: Optional[float]
    landuse_commercial_ratio: Optional[float]
    poi_density: Optional[float]
    road_connectivity_index: Optional[float]
    # Socioeconômicas (IBGE)
    avg_income: Optional[float]
    population_density: Optional[float]
    # Indiretas (Turso: Google Maps)
    bars_restaurants_density: Optional[float]
    churches_density: Optional[float]
    schools_density: Optional[float]
    dealerships_density: Optional[float]
    petshops_density: Optional[float]
    # Avançadas (OSM derivadas)
    landuse_entropy: Optional[float]
    road_centrality_index: Optional[float]
    local_clustering_coefficient: Optional[float]
    # Satélite (Google Earth Engine)
    ndvi_mean: Optional[float]
    urban_density_index: Optional[float]
    built_up_ratio: Optional[float]
    morphology_class: Optional[str]
    # Derivadas (v2)
    commercial_activity_index: Optional[float] = None
    # Contexto (v2) — peso máx DELIVERY_DENSITY_WEIGHT no score
    delivery_density_r8: Optional[float] = None


@dataclass
class TerritoryOutput:
    territory_id: str
    h3_ids: list[str]
    region_type: RegionType
    potential_score: float          # [0–100]
    current_partners: int
    ideal_slots: int
    gap: float
    model_confidence: float         # [0–1]
    low_confidence: bool
    high_opportunity: bool
    geometry: dict                  # GeoJSON geometry


@dataclass
class IdealSupplyPoint:
    lat: float
    lon: float
    radius_km: float
    capacity_day: int


@dataclass
class ActivatedArea:
    area_id: str
    h3_ids: list[str]
    n_partners: int
    ideal_supplies: list[IdealSupplyPoint]
    total_capacity: int


@dataclass
class SetupOutput:
    station_code: str
    expansion_target_pct: float
    activated_areas: list[ActivatedArea]
    is_optimal: bool
    solver_status: str
    execution_time_s: float


@dataclass
class RunMetadata:
    run_id: str
    station_code: str
    expansion_target_pct: float
    timestamp_start: str
    timestamp_end: Optional[str]
    n_h3_cells: Optional[int]
    n_territories: Optional[int]
    clustering_algorithm: Optional[str]
    silhouette_score: Optional[float]
    supervised_model: Optional[str]
    supervised_f1_macro: Optional[float]
    is_optimal: Optional[bool]
    solver_status: Optional[str]
    status: str                     # 'running' | 'completed' | 'failed'
    # v2 fields (with defaults for backward compatibility)
    umap_params: Optional[dict[str, Any]] = None
    n_clusters: Optional[int] = None
    low_quality_clustering: Optional[bool] = None
    profile_coverage: Optional[float] = None


# ---------------------------------------------------------------------------
# v2 Dataclasses
# ---------------------------------------------------------------------------

@dataclass
class PartnerProfile:
    salesforce_id: str
    status: str                    # Active | Exited
    h3_id_r8: str                  # hex res 8
    lat: float
    lon: float
    tenure_days: int
    tenure_weight: float           # log(1 + tenure_days)
    exit_reason_class: Optional[str]  # "area_signal" | "partner_signal" | None
    area_penalty: float            # 0.0 para Active, configurável para Exited
    features: dict[str, float]     # features normalizadas do hex res 8
    umap_embedding: list[float] = field(default_factory=list)  # preenchido após UMAP


@dataclass
class ReferenceProfiles:
    station_code: str
    success_vector: Any            # np.ndarray — média ponderada por tenure_weight dos Active
    failure_vector: Any            # np.ndarray — média ponderada por area_penalty * tenure dos Exited area_signal
    n_active: int
    n_exited_area: int
    avg_tenure_active: float
    profile_coverage: float        # % hexágonos com parceiro no raio grid_disk(1)
    low_coverage_warning: bool     # True se profile_coverage < 10%
    is_global_fallback: bool       # True se usou perfil global por falta de dados locais


@dataclass
class SelectedTerritory:
    territory_id: str
    h3_ids_r8: list[str]           # res 8 para análise
    h3_ids_r9: list[str]           # res 9 para CP-SAT
    region_type: RegionType
    potential_score: float
    gap: float
    model_confidence: float
    high_opportunity: bool
    repeated_failure: bool         # True se 2+ Exited area_signal neste território


# ---------------------------------------------------------------------------
# Serialization helpers
# ---------------------------------------------------------------------------

import json
import dataclasses
from datetime import datetime, timezone


def territory_output_to_geojson_feature(t: TerritoryOutput) -> dict:
    """Serializes a TerritoryOutput to a GeoJSON Feature."""
    return {
        "type": "Feature",
        "geometry": t.geometry,
        "properties": {
            "territory_id": t.territory_id,
            "h3_ids": t.h3_ids,
            "region_type": t.region_type.value if hasattr(t.region_type, "value") else t.region_type,
            "potential_score": t.potential_score,
            "current_partners": t.current_partners,
            "ideal_slots": t.ideal_slots,
            "gap": t.gap,
            "model_confidence": t.model_confidence,
            "low_confidence": t.low_confidence,
            "high_opportunity": t.high_opportunity,
        },
    }


def territories_to_geojson(territories: list[TerritoryOutput]) -> dict:
    """Serializes a list of TerritoryOutput to a GeoJSON FeatureCollection."""
    return {
        "type": "FeatureCollection",
        "features": [territory_output_to_geojson_feature(t) for t in territories],
    }


def territory_output_to_dict(t: TerritoryOutput) -> dict:
    """Serializes a TerritoryOutput to a plain JSON-safe dict (no geometry)."""
    return {
        "territory_id": t.territory_id,
        "h3_ids": t.h3_ids,
        "region_type": t.region_type.value if hasattr(t.region_type, "value") else t.region_type,
        "potential_score": t.potential_score,
        "current_partners": t.current_partners,
        "ideal_slots": t.ideal_slots,
        "gap": t.gap,
        "model_confidence": t.model_confidence,
        "low_confidence": t.low_confidence,
        "high_opportunity": t.high_opportunity,
    }


def territory_output_from_geojson_feature(feature: dict) -> TerritoryOutput:
    """Deserializes a GeoJSON Feature back to a TerritoryOutput."""
    props = feature["properties"]
    return TerritoryOutput(
        territory_id=props["territory_id"],
        h3_ids=props["h3_ids"],
        region_type=RegionType(props["region_type"]),
        potential_score=props["potential_score"],
        current_partners=props["current_partners"],
        ideal_slots=props["ideal_slots"],
        gap=props["gap"],
        model_confidence=props["model_confidence"],
        low_confidence=props["low_confidence"],
        high_opportunity=props["high_opportunity"],
        geometry=feature["geometry"],
    )


def build_run_metadata(
    run_id: str,
    station_code: str,
    expansion_target_pct: float,
    timestamp_start: str,
    n_h3_cells: Optional[int] = None,
    n_territories: Optional[int] = None,
    clustering_algorithm: Optional[str] = None,
    silhouette_score: Optional[float] = None,
    supervised_model: Optional[str] = None,
    supervised_f1_macro: Optional[float] = None,
    is_optimal: Optional[bool] = None,
    solver_status: Optional[str] = None,
    status: str = "completed",
    umap_params: Optional[dict[str, Any]] = None,
    n_clusters: Optional[int] = None,
    low_quality_clustering: Optional[bool] = None,
    profile_coverage: Optional[float] = None,
) -> RunMetadata:
    """Convenience constructor for RunMetadata."""
    return RunMetadata(
        run_id=run_id,
        station_code=station_code,
        expansion_target_pct=expansion_target_pct,
        timestamp_start=timestamp_start,
        timestamp_end=datetime.now(timezone.utc).isoformat(),
        n_h3_cells=n_h3_cells,
        n_territories=n_territories,
        clustering_algorithm=clustering_algorithm,
        silhouette_score=silhouette_score,
        supervised_model=supervised_model,
        supervised_f1_macro=supervised_f1_macro,
        is_optimal=is_optimal,
        solver_status=solver_status,
        status=status,
        umap_params=umap_params,
        n_clusters=n_clusters,
        low_quality_clustering=low_quality_clustering,
        profile_coverage=profile_coverage,
    )
