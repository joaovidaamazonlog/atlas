"""
test_profile_builder_properties.py
====================================
Property-based tests for profile_builder.py.

**Validates: Requirements 3.5**

Property 7: `profile_coverage = |{h ∈ hexágonos : ∃ parceiro em grid_disk(h, 1)}| / |hexágonos|`
-------------------------------------------------------------------------------------------------
For any set of H3 cells (cells_features) and any set of partner hexes,
profile_coverage must equal the fraction of cells that have at least one
partner in their grid_disk(h, 1) neighbourhood (h itself or its 6 neighbours).

Execution
---------
    pytest backend/geo_intelligence/phase1_area_intelligence/tests/test_profile_builder_properties.py -v
"""

from __future__ import annotations

import math
import os
import sys
from datetime import date, timedelta

import h3
import numpy as np
import pytest
from hypothesis import given, settings, assume
from hypothesis import strategies as st

# Allow imports from backend/ without installing as a package
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

from geo_intelligence.geo_config import EXIT_REASON_MAP
from geo_intelligence.phase1_area_intelligence.profile_builder import (
    _compute_profile_coverage,
    build_reference_profiles,
)
from geo_intelligence.pipeline import PartnerProfile

# ---------------------------------------------------------------------------
# Known H3 cells at resolution 8 in the São Paulo area
# ---------------------------------------------------------------------------

_SP_CENTER = h3.latlng_to_cell(-23.5505, -46.6333, 8)

# Build a pool of ~30 known cells: the center + its k=2 disk
_KNOWN_HEXES: list[str] = sorted(h3.grid_disk(_SP_CENTER, 2))

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_FEATURE_DIM = 4  # small fixed dimension for test vectors


def _dummy_features(hexes: set[str]) -> dict[str, np.ndarray]:
    """Return a cells_features dict with a constant feature vector per hex."""
    return {h: np.ones(_FEATURE_DIM, dtype=float) for h in hexes}


def _make_partner(h3_id: str, status: str = "Active", tenure_days: int = 90) -> PartnerProfile:
    """Build a minimal PartnerProfile located at the given H3 cell."""
    lat, lon = h3.cell_to_latlng(h3_id)
    return PartnerProfile(
        salesforce_id=f"SF_{h3_id[:8]}",
        status=status,
        h3_id_r8=h3_id,
        lat=lat,
        lon=lon,
        tenure_days=tenure_days,
        tenure_weight=math.log(1 + tenure_days),
        exit_reason_class=None,
        area_penalty=0.0,
        features={},
        umap_embedding=[],
    )


def _compute_expected_coverage(
    cells: set[str], partner_hexes: set[str]
) -> float:
    """
    Reference implementation of the profile_coverage formula:
        |{h ∈ cells : grid_disk(h, 1) ∩ partner_hexes ≠ ∅}| / |cells|
    """
    if not cells:
        return 0.0
    covered = sum(
        1 for h in cells if set(h3.grid_disk(h, 1)) & partner_hexes
    )
    return covered / len(cells)


# ---------------------------------------------------------------------------
# Property 7 — profile_coverage formula
# Validates: Requirements 3.5
# ---------------------------------------------------------------------------


@settings(max_examples=300)
@given(
    cells=st.sets(st.sampled_from(_KNOWN_HEXES), min_size=1, max_size=len(_KNOWN_HEXES)),
    partner_hexes=st.sets(st.sampled_from(_KNOWN_HEXES), min_size=0, max_size=len(_KNOWN_HEXES)),
)
def test_profile_coverage_formula_via_compute_function(
    cells: set[str], partner_hexes: set[str]
) -> None:
    """
    **Validates: Requirements 3.5**

    Property 7: _compute_profile_coverage returns exactly
        |{h ∈ cells : ∃ partner in grid_disk(h, 1)}| / |cells|
    for any combination of cells and partner hexes.
    """
    partners = [_make_partner(h) for h in partner_hexes]
    cells_features = _dummy_features(cells)

    result = _compute_profile_coverage(partners, cells_features)
    expected = _compute_expected_coverage(cells, partner_hexes)

    assert result == pytest.approx(expected, abs=1e-9), (
        f"profile_coverage mismatch: got {result}, expected {expected} "
        f"(cells={len(cells)}, partner_hexes={len(partner_hexes)})"
    )


@settings(max_examples=300)
@given(
    cells=st.sets(st.sampled_from(_KNOWN_HEXES), min_size=1, max_size=len(_KNOWN_HEXES)),
    partner_hexes=st.sets(st.sampled_from(_KNOWN_HEXES), min_size=0, max_size=len(_KNOWN_HEXES)),
)
def test_profile_coverage_formula_via_build_reference_profiles(
    cells: set[str], partner_hexes: set[str]
) -> None:
    """
    **Validates: Requirements 3.5**

    Property 7 (integration): build_reference_profiles returns a
    ReferenceProfiles whose profile_coverage equals
        |{h ∈ cells : ∃ partner in grid_disk(h, 1)}| / |cells|
    """
    # Build enough active partners to avoid global-fallback path (need >= 3)
    # We use partners placed at partner_hexes; if fewer than 3, pad with
    # partners from cells so the success_vector is computed locally.
    active_partners = [
        _make_partner(h, status="Active", tenure_days=90)
        for h in partner_hexes
    ]
    # Pad to at least 3 active partners so we don't trigger global fallback
    extra_cells = list(cells)
    idx = 0
    while len(active_partners) < 3 and idx < len(extra_cells):
        h = extra_cells[idx]
        if h not in partner_hexes:
            active_partners.append(_make_partner(h, status="Active", tenure_days=90))
        idx += 1

    cells_features = _dummy_features(cells)

    ref = build_reference_profiles(
        partner_profiles=active_partners,
        cells_features=cells_features,
        exit_reason_map=EXIT_REASON_MAP,
        min_tenure_days=30,
        global_fallback_profiles=None,
        station_code="TEST",
    )

    # The expected coverage uses ALL partners (active_partners), not just partner_hexes,
    # because build_reference_profiles passes all partner_profiles to _compute_profile_coverage.
    all_partner_hexes = {p.h3_id_r8 for p in active_partners}
    expected = _compute_expected_coverage(cells, all_partner_hexes)

    assert ref.profile_coverage == pytest.approx(expected, abs=1e-9), (
        f"build_reference_profiles profile_coverage mismatch: "
        f"got {ref.profile_coverage}, expected {expected}"
    )


# ---------------------------------------------------------------------------
# Boundary cases
# ---------------------------------------------------------------------------


def test_profile_coverage_no_partners_is_zero() -> None:
    """
    **Validates: Requirements 3.5**

    Boundary: When no partners are provided, profile_coverage = 0.0.
    """
    cells = set(_KNOWN_HEXES[:5])
    cells_features = _dummy_features(cells)

    result = _compute_profile_coverage([], cells_features)
    assert result == 0.0, f"Expected 0.0 with no partners, got {result}"


def test_profile_coverage_empty_cells_is_zero() -> None:
    """
    **Validates: Requirements 3.5**

    Boundary: When cells_features is empty, profile_coverage = 0.0.
    """
    partners = [_make_partner(_KNOWN_HEXES[0])]
    result = _compute_profile_coverage(partners, {})
    assert result == 0.0, f"Expected 0.0 with empty cells_features, got {result}"


def test_profile_coverage_empty_cells_via_build_reference_profiles() -> None:
    """
    **Validates: Requirements 3.5**

    Boundary: build_reference_profiles with empty cells_features returns
    profile_coverage = 0.0.
    """
    ref = build_reference_profiles(
        partner_profiles=[_make_partner(_KNOWN_HEXES[0])],
        cells_features={},
        exit_reason_map=EXIT_REASON_MAP,
        station_code="TEST",
    )
    assert ref.profile_coverage == 0.0


def test_profile_coverage_all_cells_covered_is_one() -> None:
    """
    **Validates: Requirements 3.5**

    Boundary: When every cell has a partner in its grid_disk(h, 1),
    profile_coverage = 1.0.
    """
    # Place a partner at the center cell — its grid_disk(1) covers itself
    # and all 6 immediate neighbours.  Use only those 7 cells as our cell set.
    center = _SP_CENTER
    neighborhood = set(h3.grid_disk(center, 1))  # 7 cells

    cells_features = _dummy_features(neighborhood)
    # One partner at the center covers all 7 cells (center is in each cell's disk)
    partners = [_make_partner(center)]

    result = _compute_profile_coverage(partners, cells_features)
    assert result == pytest.approx(1.0, abs=1e-9), (
        f"Expected 1.0 when all cells are covered, got {result}"
    )


def test_profile_coverage_is_fraction_between_zero_and_one() -> None:
    """
    **Validates: Requirements 3.5**

    Sanity: profile_coverage is always in [0.0, 1.0].
    """
    cells = set(_KNOWN_HEXES)
    # Place partners at only half the cells
    half = list(cells)[: len(cells) // 2]
    partners = [_make_partner(h) for h in half]
    cells_features = _dummy_features(cells)

    result = _compute_profile_coverage(partners, cells_features)
    assert 0.0 <= result <= 1.0, f"profile_coverage out of [0,1]: {result}"


@settings(max_examples=200)
@given(
    cells=st.sets(st.sampled_from(_KNOWN_HEXES), min_size=1, max_size=len(_KNOWN_HEXES)),
    partner_hexes=st.sets(st.sampled_from(_KNOWN_HEXES), min_size=0, max_size=len(_KNOWN_HEXES)),
)
def test_profile_coverage_always_in_unit_interval(
    cells: set[str], partner_hexes: set[str]
) -> None:
    """
    **Validates: Requirements 3.5**

    Property 7 (range): profile_coverage is always in [0.0, 1.0].
    """
    partners = [_make_partner(h) for h in partner_hexes]
    cells_features = _dummy_features(cells)

    result = _compute_profile_coverage(partners, cells_features)
    assert 0.0 <= result <= 1.0, (
        f"profile_coverage={result} is outside [0, 1]"
    )


@settings(max_examples=200)
@given(
    cells=st.sets(st.sampled_from(_KNOWN_HEXES), min_size=1, max_size=len(_KNOWN_HEXES)),
)
def test_profile_coverage_monotone_in_partners(cells: set[str]) -> None:
    """
    **Validates: Requirements 3.5**

    Property 7 (monotonicity): Adding more partners never decreases
    profile_coverage — coverage is monotonically non-decreasing as the
    partner set grows.
    """
    cells_features = _dummy_features(cells)
    cell_list = list(cells)

    # Start with no partners
    prev_coverage = _compute_profile_coverage([], cells_features)
    assert prev_coverage == 0.0

    # Add partners one by one and verify coverage never decreases
    partners: list[PartnerProfile] = []
    for h in cell_list:
        partners.append(_make_partner(h))
        new_coverage = _compute_profile_coverage(partners, cells_features)
        assert new_coverage >= prev_coverage - 1e-12, (
            f"profile_coverage decreased after adding partner at {h}: "
            f"{prev_coverage} → {new_coverage}"
        )
        prev_coverage = new_coverage
