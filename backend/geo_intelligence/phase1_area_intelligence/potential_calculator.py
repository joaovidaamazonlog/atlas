"""
potential_calculator.py
=======================
Calcula potential_score por H3_Cell, agrega por território, DS e BDM,
computa gap e high_opportunity, e gera rankings por gap decrescente.

Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7, 4.8, 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 5.7, 5.8
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Optional

import numpy as np

from geo_intelligence.geo_config import (
    DELIVERY_DENSITY_THRESHOLD,
    FAILURE_PENALTY_WEIGHT,
    FAST_EXIT_PENALTY,
    FAST_EXIT_THRESHOLD_DAYS,
)
from geo_intelligence.pipeline import H3CellFeatures, PartnerProfile, ReferenceProfiles, RegionType

if TYPE_CHECKING:
    from geo_intelligence.phase1_area_intelligence.classifier import CellClassification

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------

@dataclass
class TerritoryScore:
    territory_id: str
    potential_score: float   # [0, 100]
    gap: float
    high_opportunity: bool
    rank: int                # rank by gap descending


@dataclass
class AggregatedScore:
    entity_id: str
    potential_score: float   # [0, 100]
    rank: int


# ---------------------------------------------------------------------------
# Cell-level potential
# ---------------------------------------------------------------------------

def compute_cell_potential(
    cell: H3CellFeatures,
    classification: CellClassification,
    weights: dict[str, float],
    region_type_weights: dict[str, float],
) -> float:
    """Computes raw potential score for a single H3 cell.

    Formula:
        f(target_business_density, avg_income, population_density,
          region_type_weight, road_connectivity_index, commercial_activity_index)

    where:
        commercial_activity_index = (landuse_commercial_ratio + target_business_density) / 2

    All feature values are expected to be already normalised to [0, 1] by the
    Feature_Engineer.  Missing values (None) are treated as 0.0.
    """
    def _v(val: Optional[float]) -> float:
        return float(val) if val is not None else 0.0

    tbd = _v(cell.target_business_density)
    income = _v(cell.avg_income)
    pop = _v(cell.population_density)
    road = _v(cell.road_connectivity_index)
    lc_ratio = _v(cell.landuse_commercial_ratio)

    # Derived feature
    commercial_activity_index = (lc_ratio + tbd) / 2.0

    # Region type weight (default 0.5 if unknown)
    rt_key = classification.region_type.value if classification else RegionType.RESIDENCIAL_MEDIA_RENDA.value
    rt_weight = region_type_weights.get(rt_key, 0.5)

    components = {
        "target_business_density": tbd,
        "avg_income": income,
        "population_density": pop,
        "region_type_weight": rt_weight,
        "road_connectivity_index": road,
        "commercial_activity_index": commercial_activity_index,
    }

    total_weight = sum(weights.get(k, 0.0) for k in components)
    if total_weight == 0.0:
        return 0.0

    raw = sum(weights.get(k, 0.0) * v for k, v in components.items())
    return raw / total_weight


# ---------------------------------------------------------------------------
# Normalisation helpers
# ---------------------------------------------------------------------------

def normalize_scores_to_100(scores: list[float]) -> list[float]:
    """Normalizes a list of scores to [0, 100] where max = 100.

    Negative raw scores are clamped to 0 before normalization so that the
    output is always in the closed interval [0, 100] (Requirement 5.5).

    If all scores are equal (including the degenerate single-element case),
    every score maps to 100.
    """
    if not scores:
        return []
    # Clamp negatives to 0 — below-zero raw scores mean "no potential"
    clamped = [max(0.0, s) for s in scores]
    max_val = max(clamped)
    if max_val == 0.0:
        return [0.0] * len(scores)
    return [min(100.0, s / max_val * 100.0) for s in clamped]


def _weighted_average(values: list[float], weights: list[float]) -> float:
    """Returns the weighted average of *values* using *weights*.

    Falls back to a simple average when the total weight is zero.
    """
    total_w = sum(weights)
    if total_w == 0.0:
        return sum(values) / len(values) if values else 0.0
    return sum(v * w for v, w in zip(values, weights)) / total_w


# ---------------------------------------------------------------------------
# Territory-level aggregation
# ---------------------------------------------------------------------------

def compute_territory_scores(
    territories: dict[str, list[str]],   # {territory_id: [h3_ids]}
    cell_potentials: dict[str, float],    # {h3_id: raw_potential}
    cell_volumes: dict[str, int],         # {h3_id: delivery_count}
    current_partners: dict[str, int],     # {territory_id: n_partners}
    ideal_slots: dict[str, int],          # {territory_id: n_slots}
    high_opportunity_threshold: float = 20.0,
) -> list[TerritoryScore]:
    """Computes territory-level scores, gaps, and rankings.

    Steps:
    1. Aggregate raw potential per territory (volume-weighted average of cells).
    2. Normalise territory potentials to [0, 100] within the DS (max = 100).
    3. Compute gap = potential_score - (current_partners / ideal_slots * 100).
    4. Mark high_opportunity when gap > threshold.
    5. Rank by gap descending.
    """
    if not territories:
        return []

    # Step 1 — raw territory potentials (volume-weighted mean of cells)
    raw_potentials: dict[str, float] = {}
    for tid, h3_ids in territories.items():
        vals = [cell_potentials.get(h, 0.0) for h in h3_ids]
        vols = [float(cell_volumes.get(h, 0)) for h in h3_ids]
        raw_potentials[tid] = _weighted_average(vals, vols)

    # Step 2 — normalise to [0, 100]
    tids = list(raw_potentials.keys())
    raw_vals = [raw_potentials[t] for t in tids]
    normalised = normalize_scores_to_100(raw_vals)
    norm_map: dict[str, float] = dict(zip(tids, normalised))

    # Step 3-4 — gap and high_opportunity
    results: list[TerritoryScore] = []
    for tid in tids:
        score = norm_map[tid]
        partners = current_partners.get(tid, 0)
        slots = ideal_slots.get(tid, 0)

        if slots > 0:
            gap = score - (partners / slots * 100.0)
        else:
            # No ideal slots defined — treat coverage as 0 (full gap = score)
            gap = score
            logger.warning("Territory %s has ideal_slots=0; gap set to potential_score.", tid)

        high_opp = gap > high_opportunity_threshold
        results.append(TerritoryScore(
            territory_id=tid,
            potential_score=score,
            gap=gap,
            high_opportunity=high_opp,
            rank=0,  # filled below
        ))

    # Step 5 — rank by gap descending
    results.sort(key=lambda t: t.gap, reverse=True)
    for i, ts in enumerate(results, start=1):
        ts.rank = i

    return results


# ---------------------------------------------------------------------------
# DS-level aggregation
# ---------------------------------------------------------------------------

def compute_ds_scores(
    ds_territories: dict[str, list[str]],   # {ds_id: [territory_ids]}
    territory_scores: dict[str, TerritoryScore],  # {territory_id: TerritoryScore}
    territory_volumes: dict[str, int],       # {territory_id: total_delivery_count}
) -> list[AggregatedScore]:
    """Aggregates territory scores to DS level (volume-weighted), normalised to [0, 100].

    Requirements: 4.3, 4.5
    """
    if not ds_territories:
        return []

    ds_ids = list(ds_territories.keys())
    raw_ds: dict[str, float] = {}
    for ds_id in ds_ids:
        tids = ds_territories[ds_id]
        vals = [territory_scores[t].potential_score for t in tids if t in territory_scores]
        vols = [float(territory_volumes.get(t, 0)) for t in tids if t in territory_scores]
        if not vals:
            raw_ds[ds_id] = 0.0
        else:
            raw_ds[ds_id] = _weighted_average(vals, vols)

    raw_vals = [raw_ds[d] for d in ds_ids]
    normalised = normalize_scores_to_100(raw_vals)

    results = [
        AggregatedScore(entity_id=ds_id, potential_score=norm, rank=0)
        for ds_id, norm in zip(ds_ids, normalised)
    ]
    results.sort(key=lambda x: x.potential_score, reverse=True)
    for i, s in enumerate(results, start=1):
        s.rank = i
    return results


# ---------------------------------------------------------------------------
# BDM-level aggregation
# ---------------------------------------------------------------------------

def compute_bdm_scores(
    bdm_ds: dict[str, list[str]],           # {bdm_id: [ds_ids]}
    ds_scores: dict[str, AggregatedScore],  # {ds_id: AggregatedScore}
    ds_volumes: dict[str, int],             # {ds_id: total_delivery_count}
) -> list[AggregatedScore]:
    """Aggregates DS scores to BDM level (volume-weighted), normalised to [0, 100].

    Requirements: 4.4, 4.5
    """
    if not bdm_ds:
        return []

    bdm_ids = list(bdm_ds.keys())
    raw_bdm: dict[str, float] = {}
    for bdm_id in bdm_ids:
        ds_ids = bdm_ds[bdm_id]
        vals = [ds_scores[d].potential_score for d in ds_ids if d in ds_scores]
        vols = [float(ds_volumes.get(d, 0)) for d in ds_ids if d in ds_scores]
        if not vals:
            raw_bdm[bdm_id] = 0.0
        else:
            raw_bdm[bdm_id] = _weighted_average(vals, vols)

    raw_vals = [raw_bdm[b] for b in bdm_ids]
    normalised = normalize_scores_to_100(raw_vals)

    results = [
        AggregatedScore(entity_id=bdm_id, potential_score=norm, rank=0)
        for bdm_id, norm in zip(bdm_ids, normalised)
    ]
    results.sort(key=lambda x: x.potential_score, reverse=True)
    for i, s in enumerate(results, start=1):
        s.rank = i
    return results


# ---------------------------------------------------------------------------
# Rankings
# ---------------------------------------------------------------------------

def rank_territories_by_gap(
    territory_scores: list[TerritoryScore],
) -> list[TerritoryScore]:
    """Returns a copy of *territory_scores* sorted by gap descending with updated ranks.

    Requirements: 4.8
    """
    ranked = sorted(territory_scores, key=lambda t: t.gap, reverse=True)
    for i, ts in enumerate(ranked, start=1):
        ts.rank = i
    return ranked


def rank_by_gap_per_ds(
    ds_territories: dict[str, list[str]],        # {ds_id: [territory_ids]}
    territory_scores: dict[str, TerritoryScore], # {territory_id: TerritoryScore}
) -> dict[str, list[TerritoryScore]]:
    """Returns per-DS rankings of territories by gap descending.

    Requirements: 4.8
    """
    rankings: dict[str, list[TerritoryScore]] = {}
    for ds_id, tids in ds_territories.items():
        ts_list = [territory_scores[t] for t in tids if t in territory_scores]
        ts_list.sort(key=lambda t: t.gap, reverse=True)
        for i, ts in enumerate(ts_list, start=1):
            ts.rank = i
        rankings[ds_id] = ts_list
    return rankings


def rank_by_gap_per_bdm(
    bdm_ds: dict[str, list[str]],                # {bdm_id: [ds_ids]}
    ds_territories: dict[str, list[str]],        # {ds_id: [territory_ids]}
    territory_scores: dict[str, TerritoryScore], # {territory_id: TerritoryScore}
) -> dict[str, list[TerritoryScore]]:
    """Returns per-BDM rankings of territories by gap descending.

    Requirements: 4.8
    """
    rankings: dict[str, list[TerritoryScore]] = {}
    for bdm_id, ds_ids in bdm_ds.items():
        all_tids: list[str] = []
        for ds_id in ds_ids:
            all_tids.extend(ds_territories.get(ds_id, []))
        ts_list = [territory_scores[t] for t in all_tids if t in territory_scores]
        ts_list.sort(key=lambda t: t.gap, reverse=True)
        for i, ts in enumerate(ts_list, start=1):
            ts.rank = i
        rankings[bdm_id] = ts_list
    return rankings


# ---------------------------------------------------------------------------
# Similarity score helpers (v2)
# ---------------------------------------------------------------------------

def _cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """Returns cosine similarity between two vectors.

    Returns 0.0 when either vector has zero norm to avoid division by zero.
    """
    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return float(np.dot(a, b) / (norm_a * norm_b))


def _has_fast_exit_history(
    h3_id: str,
    partner_profiles: list[PartnerProfile],
    threshold_days: int,
) -> bool:
    """Returns True if any Exited area_signal partner in this hex had tenure < threshold_days."""
    for p in partner_profiles:
        if (
            p.h3_id_r8 == h3_id
            and p.status == "Exited"
            and p.exit_reason_class == "area_signal"
            and p.tenure_days < threshold_days
        ):
            return True
    return False


# ---------------------------------------------------------------------------
# Similarity score — main function (v2)
# ---------------------------------------------------------------------------

def compute_similarity_scores(
    cell_embeddings: dict[str, np.ndarray],
    reference_profiles: ReferenceProfiles,
    umap_model: object,
    delivery_density_map: dict[str, float],
    partner_profiles: list[PartnerProfile],
    territories: dict[str, list[str]],
    current_partners: dict[str, int],
    ideal_slots: dict[str, int],
    failure_penalty_weight: float = FAILURE_PENALTY_WEIGHT,
    fast_exit_threshold_days: int = FAST_EXIT_THRESHOLD_DAYS,
    fast_exit_penalty: float = FAST_EXIT_PENALTY,
    delivery_density_threshold: float = DELIVERY_DENSITY_THRESHOLD,
    high_opportunity_threshold: float = 20.0,
) -> list[TerritoryScore]:
    """Computes similarity-based potential scores for territories.

    Steps:
    1. Project reference profiles into UMAP space (or use raw vectors as fallback).
    2. For each hex res 8, compute raw_score from cosine similarity with success/failure profiles.
    3. Apply fast-exit penalty and delivery density gate.
    4. Normalize raw_scores to [0, 100] per DS.
    5. Aggregate to territories via delivery_density-weighted average.
    6. Compute gap = potential_score - (current_partners / ideal_slots * 100).

    Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 5.7, 5.8
    """
    if not cell_embeddings:
        return []

    success_vector = np.asarray(reference_profiles.success_vector, dtype=float)
    failure_vector = np.asarray(reference_profiles.failure_vector, dtype=float)

    # Determine whether failure profile is meaningful (non-zero)
    has_failure_profile = bool(np.any(failure_vector != 0.0))

    # Step 1 — project reference profiles into UMAP space
    if umap_model is not None:
        try:
            success_umap: np.ndarray = umap_model.transform([success_vector])[0]
            failure_umap: np.ndarray = umap_model.transform([failure_vector])[0] if has_failure_profile else failure_vector
        except Exception as exc:
            logger.warning("UMAP transform failed (%s); falling back to raw feature vectors.", exc)
            success_umap = success_vector
            failure_umap = failure_vector
    else:
        # Fallback: use raw feature vectors directly
        success_umap = success_vector
        failure_umap = failure_vector

    # Step 2-3 — per-hex raw scores
    raw_scores: dict[str, float] = {}
    for h3_id, cell_umap in cell_embeddings.items():
        cell_arr = np.asarray(cell_umap, dtype=float)

        sim_positive = _cosine_similarity(cell_arr, success_umap)
        sim_negative = (
            _cosine_similarity(cell_arr, failure_umap) if has_failure_profile else 0.0
        )

        raw = sim_positive - (failure_penalty_weight * sim_negative)

        # Fast-exit penalty
        if _has_fast_exit_history(h3_id, partner_profiles, fast_exit_threshold_days):
            raw -= fast_exit_penalty

        # Delivery density gate (binary filter)
        if delivery_density_map.get(h3_id, 0.0) < delivery_density_threshold:
            raw = 0.0

        raw_scores[h3_id] = raw

    # Step 4 — normalize raw scores to [0, 100]
    all_h3_ids = list(raw_scores.keys())
    raw_vals = [raw_scores[h] for h in all_h3_ids]
    normalised_vals = normalize_scores_to_100(raw_vals)
    potential_scores: dict[str, float] = dict(zip(all_h3_ids, normalised_vals))

    # Step 5-6 — aggregate to territories and compute gap
    results: list[TerritoryScore] = []
    for tid, h3_ids in territories.items():
        scores = [potential_scores.get(h, 0.0) for h in h3_ids]
        densities = [delivery_density_map.get(h, 0.0) for h in h3_ids]
        territory_score = min(100.0, max(0.0, _weighted_average(scores, densities)))

        partners = current_partners.get(tid, 0)
        slots = ideal_slots.get(tid, 0)
        if slots > 0:
            gap = territory_score - (partners / slots * 100.0)
        else:
            gap = territory_score
            logger.warning(
                "Territory %s has ideal_slots=0; gap set to potential_score.", tid
            )

        high_opp = gap > high_opportunity_threshold
        results.append(TerritoryScore(
            territory_id=tid,
            potential_score=territory_score,
            gap=gap,
            high_opportunity=high_opp,
            rank=0,
        ))

    # Rank by gap descending
    results.sort(key=lambda t: t.gap, reverse=True)
    for i, ts in enumerate(results, start=1):
        ts.rank = i

    return results
