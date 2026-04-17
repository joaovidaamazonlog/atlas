"""
test_potential_calculator_properties.py
=========================================
Property-based tests for potential_calculator.py.

Properties tested:
    1. `potential_score` ∈ [0, 100] para todo hexágono  (Req 5.5)
    2. `gap = potential_score - (current_partners / ideal_slots * 100)`  (Req 5.6)
    3. Hexágonos com `delivery_density_r8 < threshold` têm `potential_score = 0`  (Req 5.4, 1.6)

Execution
---------
    pytest backend/geo_intelligence/phase1_area_intelligence/tests/test_potential_calculator_properties.py -v
"""

from __future__ import annotations

import sys
import os
import math

import numpy as np
import pytest
from hypothesis import given, settings, assume
from hypothesis import strategies as st

# Allow imports from backend/geo_intelligence without installing as a package
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

from geo_intelligence.phase1_area_intelligence.potential_calculator import (
    compute_similarity_scores,
    compute_territory_scores,
    TerritoryScore,
)
from geo_intelligence.pipeline import ReferenceProfiles, PartnerProfile
from geo_intelligence.geo_config import DELIVERY_DENSITY_THRESHOLD


# ---------------------------------------------------------------------------
# Helpers — build test fixtures
# ---------------------------------------------------------------------------

# Real H3 cells at resolution 8 in São Paulo area
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


def _make_reference_profiles(
    success_vector: np.ndarray,
    failure_vector: np.ndarray,
) -> ReferenceProfiles:
    """Build a minimal ReferenceProfiles with the given vectors."""
    return ReferenceProfiles(
        station_code="DSP_TEST",
        success_vector=success_vector,
        failure_vector=failure_vector,
        n_active=5,
        n_exited_area=2,
        avg_tenure_active=180.0,
        profile_coverage=50.0,
        low_coverage_warning=False,
        is_global_fallback=False,
    )


def _make_cell_embeddings(
    h3_ids: list[str],
    vectors: list[np.ndarray],
) -> dict[str, np.ndarray]:
    """Map h3_ids to embedding vectors."""
    return dict(zip(h3_ids, vectors))


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

@st.composite
def feature_vector(draw, dim: int = 4) -> np.ndarray:
    """Generate a random feature vector with values in [0, 1]."""
    values = draw(st.lists(
        st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False),
        min_size=dim,
        max_size=dim,
    ))
    return np.array(values, dtype=float)


@st.composite
def cell_embeddings_strategy(draw, n_cells: int = 3, dim: int = 4) -> dict[str, np.ndarray]:
    """Generate a dict of {h3_id: embedding_vector} for n_cells cells."""
    h3_ids = _SAO_PAULO_H3_R8[:n_cells]
    vectors = [draw(feature_vector(dim=dim)) for _ in range(n_cells)]
    return _make_cell_embeddings(h3_ids, vectors)


@st.composite
def reference_profiles_strategy(draw, dim: int = 4) -> ReferenceProfiles:
    """Generate random ReferenceProfiles with vectors in [0, 1]."""
    success_vec = draw(feature_vector(dim=dim))
    failure_vec = draw(feature_vector(dim=dim))
    return _make_reference_profiles(success_vec, failure_vec)


@st.composite
def delivery_density_above_threshold(draw, h3_ids: list[str]) -> dict[str, float]:
    """Generate delivery densities strictly above DELIVERY_DENSITY_THRESHOLD for all cells."""
    threshold = float(DELIVERY_DENSITY_THRESHOLD)
    densities = {
        h: draw(st.floats(
            min_value=threshold + 0.01,
            max_value=threshold + 1000.0,
            allow_nan=False,
            allow_infinity=False,
        ))
        for h in h3_ids
    }
    return densities


@st.composite
def territories_strategy(draw, h3_ids: list[str]) -> dict[str, list[str]]:
    """Generate a simple territory mapping: one territory per cell."""
    return {f"T_{h}": [h] for h in h3_ids}


# ---------------------------------------------------------------------------
# Property 1 — potential_score ∈ [0, 100] para todo hexágono
# Validates: Requirements 5.5
# ---------------------------------------------------------------------------

@settings(max_examples=300)
@given(
    n_cells=st.integers(min_value=1, max_value=6),
    dim=st.integers(min_value=2, max_value=6),
)
def test_potential_score_in_range_0_100(n_cells: int, dim: int) -> None:
    """
    **Validates: Requirements 5.5**

    Property 1: `potential_score` ∈ [0, 100] para todo hexágono.

    For any combination of cell embeddings, reference profiles, and delivery
    densities above the threshold, every TerritoryScore.potential_score must
    be in the closed interval [0, 100].
    """
    rng = np.random.default_rng(seed=n_cells * 100 + dim)

    h3_ids = _SAO_PAULO_H3_R8[:n_cells]
    cell_embeddings = {h: rng.random(dim) for h in h3_ids}

    success_vec = rng.random(dim)
    failure_vec = rng.random(dim)
    ref_profiles = _make_reference_profiles(success_vec, failure_vec)

    threshold = float(DELIVERY_DENSITY_THRESHOLD)
    delivery_density = {h: threshold + rng.random() * 100 for h in h3_ids}

    territories = {f"T_{h}": [h] for h in h3_ids}
    current_partners = {f"T_{h}": 0 for h in h3_ids}
    ideal_slots = {f"T_{h}": 5 for h in h3_ids}

    results = compute_similarity_scores(
        cell_embeddings=cell_embeddings,
        reference_profiles=ref_profiles,
        umap_model=None,  # raw vector fallback
        delivery_density_map=delivery_density,
        partner_profiles=[],
        territories=territories,
        current_partners=current_partners,
        ideal_slots=ideal_slots,
    )

    assert len(results) > 0, "Expected at least one TerritoryScore"
    for ts in results:
        assert 0.0 <= ts.potential_score <= 100.0, (
            f"potential_score={ts.potential_score} out of [0, 100] "
            f"for territory {ts.territory_id}"
        )


@settings(max_examples=300)
@given(
    embeddings=cell_embeddings_strategy(n_cells=4, dim=4),
    ref=reference_profiles_strategy(dim=4),
)
def test_potential_score_in_range_hypothesis(
    embeddings: dict[str, np.ndarray],
    ref: ReferenceProfiles,
) -> None:
    """
    **Validates: Requirements 5.5**

    Property 1 (Hypothesis-driven): For any randomly generated cell embeddings
    and reference profiles, all potential_scores must be in [0, 100].
    """
    h3_ids = list(embeddings.keys())
    threshold = float(DELIVERY_DENSITY_THRESHOLD)
    delivery_density = {h: threshold + 10.0 for h in h3_ids}
    territories = {f"T_{h}": [h] for h in h3_ids}
    current_partners = {f"T_{h}": 0 for h in h3_ids}
    ideal_slots = {f"T_{h}": 5 for h in h3_ids}

    results = compute_similarity_scores(
        cell_embeddings=embeddings,
        reference_profiles=ref,
        umap_model=None,
        delivery_density_map=delivery_density,
        partner_profiles=[],
        territories=territories,
        current_partners=current_partners,
        ideal_slots=ideal_slots,
    )

    for ts in results:
        assert 0.0 <= ts.potential_score <= 100.0, (
            f"potential_score={ts.potential_score} out of [0, 100] "
            f"for territory {ts.territory_id}"
        )


# ---------------------------------------------------------------------------
# Property 2 — gap = potential_score - (current_partners / ideal_slots * 100)
# Validates: Requirements 5.6
# ---------------------------------------------------------------------------

@settings(max_examples=500)
@given(
    potential_score=st.floats(min_value=0.0, max_value=100.0, allow_nan=False, allow_infinity=False),
    current_partners=st.integers(min_value=0, max_value=100),
    ideal_slots=st.integers(min_value=1, max_value=100),
)
def test_gap_formula_direct(
    potential_score: float,
    current_partners: int,
    ideal_slots: int,
) -> None:
    """
    **Validates: Requirements 5.6**

    Property 2: `gap = potential_score - (current_partners / ideal_slots * 100)`
    for every territory with `ideal_slots > 0`.

    Tests the formula directly via compute_territory_scores().
    """
    territory_id = "T_TEST"
    h3_id = _SAO_PAULO_H3_R8[0]

    # Build inputs so that the territory has exactly the desired potential_score.
    # We use a single-cell territory with a single raw score equal to potential_score,
    # and a single-cell DS so normalization maps it to 100 (max=100).
    # To get an arbitrary potential_score, we use two territories: one with
    # potential_score and one with 100.0 as the max anchor.
    territories = {
        territory_id: [h3_id],
        "T_ANCHOR": [_SAO_PAULO_H3_R8[1]],
    }
    # raw cell potentials: anchor=1.0 (will become 100), test=potential_score/100
    cell_potentials = {
        h3_id: potential_score / 100.0,
        _SAO_PAULO_H3_R8[1]: 1.0,
    }
    cell_volumes = {h3_id: 1, _SAO_PAULO_H3_R8[1]: 1}
    current_partners_map = {
        territory_id: current_partners,
        "T_ANCHOR": 0,
    }
    ideal_slots_map = {
        territory_id: ideal_slots,
        "T_ANCHOR": ideal_slots,
    }

    results = compute_territory_scores(
        territories=territories,
        cell_potentials=cell_potentials,
        cell_volumes=cell_volumes,
        current_partners=current_partners_map,
        ideal_slots=ideal_slots_map,
    )

    by_id = {ts.territory_id: ts for ts in results}
    ts = by_id[territory_id]

    expected_gap = ts.potential_score - (current_partners / ideal_slots * 100.0)
    assert ts.gap == pytest.approx(expected_gap, rel=1e-9, abs=1e-9), (
        f"gap formula violated: expected {expected_gap}, got {ts.gap} "
        f"(potential_score={ts.potential_score}, "
        f"current_partners={current_partners}, ideal_slots={ideal_slots})"
    )


@settings(max_examples=300)
@given(
    current_partners=st.integers(min_value=0, max_value=50),
    ideal_slots=st.integers(min_value=1, max_value=50),
    n_cells=st.integers(min_value=1, max_value=4),
)
def test_gap_formula_via_compute_similarity_scores(
    current_partners: int,
    ideal_slots: int,
    n_cells: int,
) -> None:
    """
    **Validates: Requirements 5.6**

    Property 2 (integration): When compute_similarity_scores() is called,
    every returned TerritoryScore satisfies:
        gap = potential_score - (current_partners / ideal_slots * 100)
    for territories with ideal_slots > 0.
    """
    rng = np.random.default_rng(seed=current_partners * 1000 + ideal_slots * 10 + n_cells)
    dim = 4
    h3_ids = _SAO_PAULO_H3_R8[:n_cells]

    cell_embeddings = {h: rng.random(dim) for h in h3_ids}
    success_vec = rng.random(dim)
    failure_vec = rng.random(dim)
    ref_profiles = _make_reference_profiles(success_vec, failure_vec)

    threshold = float(DELIVERY_DENSITY_THRESHOLD)
    delivery_density = {h: threshold + 10.0 for h in h3_ids}

    territories = {f"T_{h}": [h] for h in h3_ids}
    current_partners_map = {f"T_{h}": current_partners for h in h3_ids}
    ideal_slots_map = {f"T_{h}": ideal_slots for h in h3_ids}

    results = compute_similarity_scores(
        cell_embeddings=cell_embeddings,
        reference_profiles=ref_profiles,
        umap_model=None,
        delivery_density_map=delivery_density,
        partner_profiles=[],
        territories=territories,
        current_partners=current_partners_map,
        ideal_slots=ideal_slots_map,
    )

    for ts in results:
        expected_gap = ts.potential_score - (current_partners / ideal_slots * 100.0)
        assert ts.gap == pytest.approx(expected_gap, rel=1e-9, abs=1e-9), (
            f"gap formula violated for territory {ts.territory_id}: "
            f"expected {expected_gap}, got {ts.gap} "
            f"(potential_score={ts.potential_score}, "
            f"current_partners={current_partners}, ideal_slots={ideal_slots})"
        )


# ---------------------------------------------------------------------------
# Property 3 — Hexágonos com delivery_density_r8 < threshold têm potential_score = 0
# Validates: Requirements 5.4, 1.6
# ---------------------------------------------------------------------------

@settings(max_examples=300)
@given(
    density_below=st.floats(
        min_value=0.0,
        max_value=float(DELIVERY_DENSITY_THRESHOLD) - 0.01,
        allow_nan=False,
        allow_infinity=False,
    ),
    n_cells=st.integers(min_value=1, max_value=4),
)
def test_delivery_density_gate_sets_score_to_zero(
    density_below: float,
    n_cells: int,
) -> None:
    """
    **Validates: Requirements 5.4, 1.6**

    Property 3: Hexágonos com `delivery_density_r8 < DELIVERY_DENSITY_THRESHOLD`
    têm `potential_score = 0`.

    When ALL cells in a territory are below the threshold, the territory's
    potential_score must be 0.
    """
    assume(density_below < float(DELIVERY_DENSITY_THRESHOLD))

    rng = np.random.default_rng(seed=int(density_below * 100) + n_cells)
    dim = 4
    h3_ids = _SAO_PAULO_H3_R8[:n_cells]

    cell_embeddings = {h: rng.random(dim) for h in h3_ids}
    success_vec = rng.random(dim)
    failure_vec = rng.random(dim)
    ref_profiles = _make_reference_profiles(success_vec, failure_vec)

    # All cells below threshold
    delivery_density = {h: density_below for h in h3_ids}

    # One territory containing all below-threshold cells
    territory_id = "T_BELOW"
    territories = {territory_id: h3_ids}
    current_partners = {territory_id: 0}
    ideal_slots = {territory_id: 5}

    results = compute_similarity_scores(
        cell_embeddings=cell_embeddings,
        reference_profiles=ref_profiles,
        umap_model=None,
        delivery_density_map=delivery_density,
        partner_profiles=[],
        territories=territories,
        current_partners=current_partners,
        ideal_slots=ideal_slots,
    )

    assert len(results) == 1
    ts = results[0]
    assert ts.potential_score == pytest.approx(0.0, abs=1e-9), (
        f"Expected potential_score=0 for territory with all cells below density threshold "
        f"(density={density_below} < threshold={DELIVERY_DENSITY_THRESHOLD}), "
        f"got {ts.potential_score}"
    )


@settings(max_examples=300)
@given(
    density_below=st.floats(
        min_value=0.0,
        max_value=float(DELIVERY_DENSITY_THRESHOLD) - 0.01,
        allow_nan=False,
        allow_infinity=False,
    ),
    density_above=st.floats(
        min_value=float(DELIVERY_DENSITY_THRESHOLD) + 0.01,
        max_value=float(DELIVERY_DENSITY_THRESHOLD) + 1000.0,
        allow_nan=False,
        allow_infinity=False,
    ),
)
def test_delivery_density_gate_mixed_territories(
    density_below: float,
    density_above: float,
) -> None:
    """
    **Validates: Requirements 5.4, 1.6**

    Property 3 (mixed): When a territory contains only below-threshold cells,
    its potential_score = 0. A territory with above-threshold cells may have
    potential_score > 0 (when the above-threshold territory is the max).
    """
    assume(density_below < float(DELIVERY_DENSITY_THRESHOLD))
    assume(density_above >= float(DELIVERY_DENSITY_THRESHOLD))

    rng = np.random.default_rng(seed=42)
    dim = 4

    h_below = _SAO_PAULO_H3_R8[0]
    h_above = _SAO_PAULO_H3_R8[1]

    # Give the above-threshold cell a non-zero embedding to ensure non-zero score
    cell_embeddings = {
        h_below: rng.random(dim),
        h_above: np.ones(dim),  # strong signal
    }
    success_vec = np.ones(dim)  # perfect match for h_above
    failure_vec = np.zeros(dim)
    ref_profiles = _make_reference_profiles(success_vec, failure_vec)

    delivery_density = {
        h_below: density_below,
        h_above: density_above,
    }

    territories = {
        "T_BELOW": [h_below],
        "T_ABOVE": [h_above],
    }
    current_partners = {"T_BELOW": 0, "T_ABOVE": 0}
    ideal_slots = {"T_BELOW": 5, "T_ABOVE": 5}

    results = compute_similarity_scores(
        cell_embeddings=cell_embeddings,
        reference_profiles=ref_profiles,
        umap_model=None,
        delivery_density_map=delivery_density,
        partner_profiles=[],
        territories=territories,
        current_partners=current_partners,
        ideal_slots=ideal_slots,
    )

    by_id = {ts.territory_id: ts for ts in results}

    # The below-threshold territory must have potential_score = 0
    assert by_id["T_BELOW"].potential_score == pytest.approx(0.0, abs=1e-9), (
        f"Expected potential_score=0 for T_BELOW (density={density_below} < threshold), "
        f"got {by_id['T_BELOW'].potential_score}"
    )


@settings(max_examples=200)
@given(
    density=st.floats(
        min_value=0.0,
        max_value=float(DELIVERY_DENSITY_THRESHOLD) - 0.001,
        allow_nan=False,
        allow_infinity=False,
    ),
)
def test_delivery_density_gate_boundary(density: float) -> None:
    """
    **Validates: Requirements 5.4, 1.6**

    Property 3 (boundary): Any density strictly below DELIVERY_DENSITY_THRESHOLD
    must result in potential_score = 0, regardless of the cell's embedding.
    """
    assume(density < float(DELIVERY_DENSITY_THRESHOLD))

    rng = np.random.default_rng(seed=7)
    dim = 4
    h3_id = _SAO_PAULO_H3_R8[0]

    # Use a strong embedding that would otherwise produce a high score
    cell_embeddings = {h3_id: np.ones(dim)}
    success_vec = np.ones(dim)
    failure_vec = np.zeros(dim)
    ref_profiles = _make_reference_profiles(success_vec, failure_vec)

    delivery_density = {h3_id: density}
    territories = {"T_TEST": [h3_id]}
    current_partners = {"T_TEST": 0}
    ideal_slots = {"T_TEST": 5}

    results = compute_similarity_scores(
        cell_embeddings=cell_embeddings,
        reference_profiles=ref_profiles,
        umap_model=None,
        delivery_density_map=delivery_density,
        partner_profiles=[],
        territories=territories,
        current_partners=current_partners,
        ideal_slots=ideal_slots,
    )

    assert len(results) == 1
    assert results[0].potential_score == pytest.approx(0.0, abs=1e-9), (
        f"Expected potential_score=0 for density={density} < threshold={DELIVERY_DENSITY_THRESHOLD}, "
        f"got {results[0].potential_score}"
    )
