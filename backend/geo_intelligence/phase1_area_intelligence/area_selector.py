"""
area_selector.py
================
Selects the minimum set of territories (by highest gap) whose combined
delivery volume reaches target_pct% of the total DS volume.

Requirements: 6.1, 6.2, 6.3, 6.4, 6.5
"""

from __future__ import annotations

import logging
from collections import Counter

from geo_intelligence.pipeline import PartnerProfile, RegionType, SelectedTerritory
from geo_intelligence.phase1_area_intelligence.potential_calculator import TerritoryScore

logger = logging.getLogger(__name__)


def select_areas(
    territory_scores: list[TerritoryScore],
    territory_h3_ids_r8: dict[str, list[str]],
    territory_h3_ids_r9: dict[str, list[str]],
    territory_region_types: dict[str, RegionType],
    territory_model_confidence: dict[str, float],
    territory_volumes: dict[str, int],
    partner_profiles: list[PartnerProfile],
    target_pct: float,
) -> list[SelectedTerritory]:
    """
    Selects the minimum set of territories (by highest gap) whose combined
    volume reaches target_pct% of the total DS volume.

    Args:
        territory_scores: Scored territories from potential_calculator.
        territory_h3_ids_r8: Mapping territory_id → H3 cells at res 8 (for analysis).
        territory_h3_ids_r9: Mapping territory_id → H3 cells at res 9 (for CP-SAT).
        territory_region_types: Dominant RegionType per territory.
        territory_model_confidence: Model confidence per territory.
        territory_volumes: Delivery volume per territory.
        partner_profiles: All partner profiles (used to compute repeated_failure).
        target_pct: Target percentage of total volume to cover [0, 100].

    Returns:
        List of SelectedTerritory ordered by gap descending.
    """
    if not territory_scores:
        return []

    if not (0.0 <= target_pct <= 100.0):
        raise ValueError(f"target_pct must be in [0, 100], got {target_pct}")

    # Edge case: target_pct = 0 → empty list (Req 6.3)
    if target_pct == 0.0:
        return []

    # Pre-compute repeated_failure per territory (Req 6.5)
    # A territory has repeated_failure=True when count(exited area_signal partners
    # whose h3_id_r8 is in territory's h3_ids_r8) >= 2
    exited_area_signal_hexes: list[str] = [
        p.h3_id_r8
        for p in partner_profiles
        if p.status == "Exited" and p.exit_reason_class == "area_signal"
    ]

    territory_repeated_failure: dict[str, bool] = {}
    for ts in territory_scores:
        t_hexes_r8 = set(territory_h3_ids_r8.get(ts.territory_id, []))
        count = sum(1 for h in exited_area_signal_hexes if h in t_hexes_r8)
        territory_repeated_failure[ts.territory_id] = count >= 2

    # Edge case: target_pct = 100 → all territories with gap > 0 (Req 6.3)
    if target_pct == 100.0:
        result = [
            _make_selected(
                ts,
                territory_h3_ids_r8,
                territory_h3_ids_r9,
                territory_region_types,
                territory_model_confidence,
                territory_repeated_failure,
            )
            for ts in territory_scores
            if ts.gap > 0
        ]
        _log_coverage_summary(result, territory_volumes, sum(territory_volumes.values()), target_pct)
        return result

    sorted_scores = sorted(territory_scores, key=lambda ts: ts.gap, reverse=True)
    total_volume = sum(territory_volumes.get(ts.territory_id, 0) for ts in sorted_scores)

    if total_volume == 0:
        logger.warning("Total DS volume is 0; selecting all territories.")
        result = [
            _make_selected(
                ts,
                territory_h3_ids_r8,
                territory_h3_ids_r9,
                territory_region_types,
                territory_model_confidence,
                territory_repeated_failure,
            )
            for ts in sorted_scores
        ]
        _log_coverage_summary(result, territory_volumes, total_volume, target_pct)
        return result

    volume_target = total_volume * target_pct / 100.0
    selected: list[SelectedTerritory] = []
    cumulative = 0.0

    for ts in sorted_scores:
        selected.append(
            _make_selected(
                ts,
                territory_h3_ids_r8,
                territory_h3_ids_r9,
                territory_region_types,
                territory_model_confidence,
                territory_repeated_failure,
            )
        )
        cumulative += territory_volumes.get(ts.territory_id, 0)
        if cumulative >= volume_target:
            break

    _log_coverage_summary(selected, territory_volumes, total_volume, target_pct)
    return selected


def _make_selected(
    ts: TerritoryScore,
    territory_h3_ids_r8: dict[str, list[str]],
    territory_h3_ids_r9: dict[str, list[str]],
    territory_region_types: dict[str, RegionType],
    territory_model_confidence: dict[str, float],
    territory_repeated_failure: dict[str, bool],
) -> SelectedTerritory:
    return SelectedTerritory(
        territory_id=ts.territory_id,
        h3_ids_r8=territory_h3_ids_r8.get(ts.territory_id, []),
        h3_ids_r9=territory_h3_ids_r9.get(ts.territory_id, []),
        region_type=territory_region_types.get(ts.territory_id, RegionType.RESIDENCIAL_MEDIA_RENDA),
        potential_score=ts.potential_score,
        gap=ts.gap,
        model_confidence=territory_model_confidence.get(ts.territory_id, 0.0),
        high_opportunity=ts.high_opportunity,
        repeated_failure=territory_repeated_failure.get(ts.territory_id, False),
    )


def _log_coverage_summary(
    selected: list[SelectedTerritory],
    territory_volumes: dict[str, int],
    total_volume: int,
    target_pct: float,
) -> None:
    """Calculates and logs coverage_summary (Req 6.4)."""
    n_selected = len(selected)
    covered_volume = sum(territory_volumes.get(t.territory_id, 0) for t in selected)
    pct_covered = (covered_volume / total_volume * 100.0) if total_volume > 0 else 0.0

    region_type_dist = Counter(t.region_type.value for t in selected)

    coverage_summary = {
        "pct_volume_covered": round(pct_covered, 2),
        "n_territories_selected": n_selected,
        "region_type_distribution": dict(region_type_dist),
    }

    logger.info(
        "select_areas: selected %d territories (%.1f%% volume covered, target %.1f%%). "
        "RegionType distribution: %s.",
        n_selected,
        pct_covered,
        target_pct,
        region_type_dist,
    )
    return coverage_summary
