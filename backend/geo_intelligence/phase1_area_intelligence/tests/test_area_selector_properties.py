"""
test_area_selector_properties.py
=================================
Property-based tests for area_selector.py.

Properties tested:
    4. `sum(volume[t] for t in selected) >= target_pct * total_volume`  (Req 6.1)
    8. `repeated_failure = True` iff `count(exited_area_signal in territory) >= 2`  (Req 6.5)

Execution
---------
    pytest backend/geo_intelligence/phase1_area_intelligence/tests/test_area_selector_properties.py -v
"""

from __future__ import annotations

import sys
import os

import pytest
from hypothesis import given, settings, assume
from hypothesis import strategies as st

# Allow imports from backend/geo_intelligence without installing as a package
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

from geo_intelligence.phase1_area_intelligence.area_selector import select_areas
from geo_intelligence.phase1_area_intelligence.potential_calculator import TerritoryScore
from geo_intelligence.pipeline import PartnerProfile, RegionType

# ---------------------------------------------------------------------------
# Real H3 cells at resolution 8 in São Paulo area
# ---------------------------------------------------------------------------

_SAO_PAULO_H3_R8 = [
    "88a8a06989fffff",
    "88a8a069b1fffff",
    "88a8a069b3fffff",
    "88a8a069b5fffff",
    "88a8a069b7fffff",
    "88a8a069b9fffff",
    "88a8a069bbfffff",
    "88a8a069bdfffff",
]

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_territory_score(territory_id: str, gap: float = 10.0) -> TerritoryScore:
    return TerritoryScore(
        territory_id=territory_id,
        potential_score=50.0,
        gap=gap,
        high_opportunity=gap > 20.0,
        rank=1,
    )


def _make_partner_profile(
    salesforce_id: str,
    h3_id_r8: str,
    status: str = "Active",
    exit_reason_class: str | None = None,
) -> PartnerProfile:
    return PartnerProfile(
        salesforce_id=salesforce_id,
        status=status,
        h3_id_r8=h3_id_r8,
        lat=-23.5,
        lon=-46.6,
        tenure_days=180,
        tenure_weight=5.19,
        exit_reason_class=exit_reason_class,
        area_penalty=1.0 if exit_reason_class == "area_signal" else 0.0,
        features={},
        umap_embedding=[],
    )


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

@st.composite
def territories_with_volumes(draw, min_n: int = 1, max_n: int = 6):
    """
    Generate a list of TerritoryScore objects and a matching volumes dict.
    Each territory gets a unique ID and a random volume.
    """
    n = draw(st.integers(min_value=min_n, max_value=max_n))
    territory_ids = [f"T_{i}" for i in range(n)]

    scores = []
    volumes = {}
    for tid in territory_ids:
        gap = draw(st.floats(min_value=-50.0, max_value=100.0, allow_nan=False, allow_infinity=False))
        vol = draw(st.integers(min_value=1, max_value=1000))
        scores.append(_make_territory_score(tid, gap=gap))
        volumes[tid] = vol

    return scores, volumes


@st.composite
def target_pct_strategy(draw) -> float:
    return draw(st.floats(min_value=0.0, max_value=100.0, allow_nan=False, allow_infinity=False))


# ---------------------------------------------------------------------------
# Property 4 — Volume coverage
# Validates: Requirements 6.1
# ---------------------------------------------------------------------------

@settings(max_examples=500)
@given(
    data=territories_with_volumes(min_n=1, max_n=6),
    target_pct=st.floats(min_value=0.01, max_value=99.99, allow_nan=False, allow_infinity=False),
)
def test_volume_coverage_property(data, target_pct: float) -> None:
    """
    **Validates: Requirements 6.1**

    Property 4: `sum(volume[t] for t in selected) >= target_pct / 100 * total_volume`

    For any set of territories with positive volumes and any target_pct in (0, 100),
    the selected territories must cover at least target_pct% of total volume.
    """
    territory_scores, territory_volumes = data
    n = len(territory_scores)
    h3_r8 = {ts.territory_id: [_SAO_PAULO_H3_R8[i % len(_SAO_PAULO_H3_R8)]] for i, ts in enumerate(territory_scores)}
    h3_r9 = {ts.territory_id: [] for ts in territory_scores}
    region_types = {ts.territory_id: RegionType.RESIDENCIAL_MEDIA_RENDA for ts in territory_scores}
    model_confidence = {ts.territory_id: 0.8 for ts in territory_scores}

    selected = select_areas(
        territory_scores=territory_scores,
        territory_h3_ids_r8=h3_r8,
        territory_h3_ids_r9=h3_r9,
        territory_region_types=region_types,
        territory_model_confidence=model_confidence,
        territory_volumes=territory_volumes,
        partner_profiles=[],
        target_pct=target_pct,
    )

    total_volume = sum(territory_volumes.values())
    covered_volume = sum(territory_volumes.get(t.territory_id, 0) for t in selected)
    volume_target = target_pct / 100.0 * total_volume

    assert covered_volume >= volume_target - 1e-9, (
        f"Volume coverage violated: covered={covered_volume}, "
        f"target={volume_target} (target_pct={target_pct}, total={total_volume})"
    )


@settings(max_examples=200)
@given(
    data=territories_with_volumes(min_n=1, max_n=6),
)
def test_volume_coverage_target_pct_zero_returns_empty(data) -> None:
    """
    **Validates: Requirements 6.1, 6.3**

    Edge case: target_pct = 0 → empty list.
    """
    territory_scores, territory_volumes = data
    h3_r8 = {ts.territory_id: [_SAO_PAULO_H3_R8[0]] for ts in territory_scores}
    h3_r9 = {ts.territory_id: [] for ts in territory_scores}
    region_types = {ts.territory_id: RegionType.RESIDENCIAL_MEDIA_RENDA for ts in territory_scores}
    model_confidence = {ts.territory_id: 0.8 for ts in territory_scores}

    selected = select_areas(
        territory_scores=territory_scores,
        territory_h3_ids_r8=h3_r8,
        territory_h3_ids_r9=h3_r9,
        territory_region_types=region_types,
        territory_model_confidence=model_confidence,
        territory_volumes=territory_volumes,
        partner_profiles=[],
        target_pct=0.0,
    )

    assert selected == [], f"Expected empty list for target_pct=0, got {len(selected)} territories"


@settings(max_examples=200)
@given(
    data=territories_with_volumes(min_n=1, max_n=6),
)
def test_volume_coverage_target_pct_100_returns_all_with_positive_gap(data) -> None:
    """
    **Validates: Requirements 6.1, 6.3**

    Edge case: target_pct = 100 → all territories with gap > 0.
    """
    territory_scores, territory_volumes = data
    h3_r8 = {ts.territory_id: [_SAO_PAULO_H3_R8[0]] for ts in territory_scores}
    h3_r9 = {ts.territory_id: [] for ts in territory_scores}
    region_types = {ts.territory_id: RegionType.RESIDENCIAL_MEDIA_RENDA for ts in territory_scores}
    model_confidence = {ts.territory_id: 0.8 for ts in territory_scores}

    selected = select_areas(
        territory_scores=territory_scores,
        territory_h3_ids_r8=h3_r8,
        territory_h3_ids_r9=h3_r9,
        territory_region_types=region_types,
        territory_model_confidence=model_confidence,
        territory_volumes=territory_volumes,
        partner_profiles=[],
        target_pct=100.0,
    )

    expected_ids = {ts.territory_id for ts in territory_scores if ts.gap > 0}
    selected_ids = {t.territory_id for t in selected}

    assert selected_ids == expected_ids, (
        f"target_pct=100 should return all territories with gap>0. "
        f"Expected {expected_ids}, got {selected_ids}"
    )


# ---------------------------------------------------------------------------
# Property 8 — repeated_failure
# Validates: Requirements 6.5
# ---------------------------------------------------------------------------

@settings(max_examples=500)
@given(
    n_area_signal=st.integers(min_value=0, max_value=5),
    n_partner_signal=st.integers(min_value=0, max_value=3),
    n_active=st.integers(min_value=0, max_value=3),
)
def test_repeated_failure_iff_two_or_more_area_signal(
    n_area_signal: int,
    n_partner_signal: int,
    n_active: int,
) -> None:
    """
    **Validates: Requirements 6.5**

    Property 8: `repeated_failure = True` iff
    `count(exited_area_signal in territory) >= 2`

    Tests with 0, 1, 2, 3+ area_signal partners in a territory.
    partner_signal and active partners must NOT affect repeated_failure.
    """
    # Single territory using the first H3 cell
    territory_hex = _SAO_PAULO_H3_R8[0]
    territory_id = "T_TEST"

    territory_scores = [_make_territory_score(territory_id, gap=10.0)]
    territory_volumes = {territory_id: 100}
    h3_r8 = {territory_id: [territory_hex]}
    h3_r9 = {territory_id: []}
    region_types = {territory_id: RegionType.RESIDENCIAL_MEDIA_RENDA}
    model_confidence = {territory_id: 0.8}

    # Build partner profiles
    partner_profiles: list[PartnerProfile] = []

    for i in range(n_area_signal):
        partner_profiles.append(_make_partner_profile(
            salesforce_id=f"area_{i}",
            h3_id_r8=territory_hex,
            status="Exited",
            exit_reason_class="area_signal",
        ))

    for i in range(n_partner_signal):
        partner_profiles.append(_make_partner_profile(
            salesforce_id=f"partner_{i}",
            h3_id_r8=territory_hex,
            status="Exited",
            exit_reason_class="partner_signal",
        ))

    for i in range(n_active):
        partner_profiles.append(_make_partner_profile(
            salesforce_id=f"active_{i}",
            h3_id_r8=territory_hex,
            status="Active",
            exit_reason_class=None,
        ))

    selected = select_areas(
        territory_scores=territory_scores,
        territory_h3_ids_r8=h3_r8,
        territory_h3_ids_r9=h3_r9,
        territory_region_types=region_types,
        territory_model_confidence=model_confidence,
        territory_volumes=territory_volumes,
        partner_profiles=partner_profiles,
        target_pct=50.0,
    )

    assert len(selected) == 1
    result = selected[0]

    expected_repeated_failure = n_area_signal >= 2
    assert result.repeated_failure == expected_repeated_failure, (
        f"repeated_failure={result.repeated_failure} but expected {expected_repeated_failure} "
        f"(n_area_signal={n_area_signal}, n_partner_signal={n_partner_signal}, n_active={n_active})"
    )


@settings(max_examples=300)
@given(
    n_area_signal_in=st.integers(min_value=0, max_value=4),
    n_area_signal_out=st.integers(min_value=0, max_value=4),
)
def test_repeated_failure_only_counts_partners_in_territory(
    n_area_signal_in: int,
    n_area_signal_out: int,
) -> None:
    """
    **Validates: Requirements 6.5**

    Property 8 (isolation): Partners in OTHER territories must not affect
    `repeated_failure` of the target territory.
    """
    territory_hex = _SAO_PAULO_H3_R8[0]
    other_hex = _SAO_PAULO_H3_R8[1]
    territory_id = "T_TEST"

    territory_scores = [_make_territory_score(territory_id, gap=10.0)]
    territory_volumes = {territory_id: 100}
    h3_r8 = {territory_id: [territory_hex]}  # only territory_hex, not other_hex
    h3_r9 = {territory_id: []}
    region_types = {territory_id: RegionType.RESIDENCIAL_MEDIA_RENDA}
    model_confidence = {territory_id: 0.8}

    partner_profiles: list[PartnerProfile] = []

    # Partners inside the territory
    for i in range(n_area_signal_in):
        partner_profiles.append(_make_partner_profile(
            salesforce_id=f"in_{i}",
            h3_id_r8=territory_hex,
            status="Exited",
            exit_reason_class="area_signal",
        ))

    # Partners outside the territory (different hex)
    for i in range(n_area_signal_out):
        partner_profiles.append(_make_partner_profile(
            salesforce_id=f"out_{i}",
            h3_id_r8=other_hex,
            status="Exited",
            exit_reason_class="area_signal",
        ))

    selected = select_areas(
        territory_scores=territory_scores,
        territory_h3_ids_r8=h3_r8,
        territory_h3_ids_r9=h3_r9,
        territory_region_types=region_types,
        territory_model_confidence=model_confidence,
        territory_volumes=territory_volumes,
        partner_profiles=partner_profiles,
        target_pct=50.0,
    )

    assert len(selected) == 1
    result = selected[0]

    # Only in-territory partners count
    expected_repeated_failure = n_area_signal_in >= 2
    assert result.repeated_failure == expected_repeated_failure, (
        f"repeated_failure={result.repeated_failure} but expected {expected_repeated_failure} "
        f"(n_area_signal_in={n_area_signal_in}, n_area_signal_out={n_area_signal_out})"
    )
