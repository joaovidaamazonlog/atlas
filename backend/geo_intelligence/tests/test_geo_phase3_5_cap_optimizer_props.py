"""
test_geo_phase3_5_cap_optimizer_props.py
=========================================
Property-based tests for geo_phase3_5_cap_optimizer.py.

Properties tested:
    8. Symmetry and identity of `_haversine_m`  (Req 2.5)

Execution
---------
    pytest backend/geo_intelligence/tests/test_geo_phase3_5_cap_optimizer_props.py -v
"""

from __future__ import annotations

import sys
import os

# Allow imports from backend/ without installing as a package
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from hypothesis import given, settings
from hypothesis import strategies as st

from geo_intelligence.geo_phase3_5_cap_optimizer import _haversine_m

# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

_lat_strategy = st.floats(min_value=-90.0, max_value=90.0, allow_nan=False, allow_infinity=False)
_lon_strategy = st.floats(min_value=-180.0, max_value=180.0, allow_nan=False, allow_infinity=False)

_coord_strategy = st.tuples(_lat_strategy, _lon_strategy)


# ---------------------------------------------------------------------------
# Property 8 — Symmetry and identity of _haversine_m
# Feature: geo-cap-optimization, Property 8: Simetria e identidade da distância Haversine
# ---------------------------------------------------------------------------

@settings(max_examples=100)
@given(
    point_a=_coord_strategy,
    point_b=_coord_strategy,
)
def test_haversine_symmetry_identity_non_negativity(
    point_a: tuple[float, float],
    point_b: tuple[float, float],
) -> None:
    """
    **Validates: Requirements 2.5**

    Property 8: For any two geographic points A and B:
    - haversine(A, B) == haversine(B, A)  (symmetry)
    - haversine(A, A) == 0                (identity)
    - haversine(A, B) >= 0                (non-negativity)
    """
    # Feature: geo-cap-optimization, Property 8: Simetria e identidade da distância Haversine

    lat_a, lon_a = point_a
    lat_b, lon_b = point_b

    dist_ab = _haversine_m(lat_a, lon_a, lat_b, lon_b)
    dist_ba = _haversine_m(lat_b, lon_b, lat_a, lon_a)
    dist_aa = _haversine_m(lat_a, lon_a, lat_a, lon_a)

    # Non-negativity: distance must always be >= 0
    assert dist_ab >= 0.0, (
        f"haversine({point_a}, {point_b}) = {dist_ab} is negative"
    )

    # Symmetry: haversine(A, B) == haversine(B, A)
    assert abs(dist_ab - dist_ba) < 1e-6, (
        f"haversine symmetry violated: "
        f"haversine({point_a}, {point_b}) = {dist_ab} != "
        f"haversine({point_b}, {point_a}) = {dist_ba}"
    )

    # Identity: haversine(A, A) == 0
    assert dist_aa == 0.0, (
        f"haversine identity violated: haversine({point_a}, {point_a}) = {dist_aa} != 0"
    )


# ---------------------------------------------------------------------------
# Property 7 — Conservação de densidade na desagregação res 8 → res 9
# Feature: geo-cap-optimization, Property 7: Conservação de densidade na desagregação res 8 → res 9
# ---------------------------------------------------------------------------

# Known valid res 8 H3 hex IDs from Brazil/São Paulo area used as a sampled strategy
# Generated via: h3.latlng_to_cell(lat, lon, 8) for various São Paulo coordinates
_VALID_RES8_HEXES = [
    "88a8100c03fffff",
    "88a8100c0bfffff",
    "88a8100c35fffff",
    "88a8100c51fffff",
    "88a8100dc1fffff",
    "88a8100ee5fffff",
    "88a8100dc7fffff",
    "88a8100e17fffff",
    "88a8100de3fffff",
    "88a8100e1bfffff",
    "88a8100dadfffff",
    "88a8100525fffff",
    "88a810729bfffff",
    "88a8100529fffff",
    "88a8107297fffff",
    "88a810050dfffff",
    "88a81072b3fffff",
    "88a8100541fffff",
    "88a81070d1fffff",
    "88a8100735fffff",
]

_res8_hex_strategy = st.sampled_from(_VALID_RES8_HEXES)
_density_strategy = st.floats(
    min_value=0.0,
    max_value=1000.0,
    allow_nan=False,
    allow_infinity=False,
)


@settings(max_examples=100)
@given(
    h3_id_r8=_res8_hex_strategy,
    density=_density_strategy,
)
def test_disaggregate_r8_to_r9_density_conservation(
    h3_id_r8: str,
    density: float,
) -> None:
    """
    **Validates: Requirements 7.2**

    Property 7: For any valid res 8 H3 hex with delivery_density_r8 = D,
    the sum of delivery_density_r9 of all its res 9 children must equal D
    (within floating point tolerance).
    """
    # Feature: geo-cap-optimization, Property 7: Conservação de densidade na desagregação res 8 → res 9
    from geo_intelligence.geo_phase3_5_cap_optimizer import _disaggregate_r8_to_r9

    result = _disaggregate_r8_to_r9(h3_id_r8, density)

    # The result must not be empty for valid res 8 hexes
    assert len(result) > 0, (
        f"_disaggregate_r8_to_r9({h3_id_r8!r}, {density}) returned empty dict"
    )

    total = sum(result.values())

    # Density must be conserved within floating point tolerance
    assert abs(total - density) < 1e-9, (
        f"Density conservation violated for hex {h3_id_r8!r}: "
        f"input={density}, sum_of_children={total}, diff={abs(total - density)}"
    )


# ---------------------------------------------------------------------------
# Property 3 — Demanda não coberta exclui hexes cobertos por outros parceiros Active
# Feature: geo-cap-optimization, Property 3: Demanda não coberta exclui hexes cobertos por outros parceiros Active
# ---------------------------------------------------------------------------

# Known valid res 9 H3 hexes (children of known res 8 hexes from São Paulo area).
# These are used to build realistic h3_index and coverage_index inputs.
_VALID_RES9_HEXES = [
    "89a8100c023ffff", "89a8100c027ffff", "89a8100c02bffff", "89a8100c02fffff",
    "89a8100c033ffff", "89a8100c037ffff", "89a8100c03bffff",
    "89a8100c0a3ffff", "89a8100c0a7ffff", "89a8100c0abffff", "89a8100c0afffff",
    "89a8100c0b3ffff", "89a8100c0b7ffff", "89a8100c0bbffff",
    "89a8100c343ffff", "89a8100c347ffff", "89a8100c34bffff", "89a8100c34fffff",
    "89a8100c353ffff", "89a8100c357ffff", "89a8100c35bffff",
    "89a8100c503ffff", "89a8100c507ffff", "89a8100c50bffff", "89a8100c50fffff",
    "89a8100c513ffff", "89a8100c517ffff", "89a8100c51bffff",
    "89a8100dc03ffff", "89a8100dc07ffff", "89a8100dc0bffff", "89a8100dc0fffff",
    "89a8100dc13ffff", "89a8100dc17ffff", "89a8100dc1bffff",
]

# Strategy: build a dict mapping a random subset of res9 hexes to random densities
_h3_index_strategy = st.dictionaries(
    keys=st.sampled_from(_VALID_RES9_HEXES),
    values=st.floats(min_value=0.0, max_value=500.0, allow_nan=False, allow_infinity=False),
    min_size=1,
    max_size=len(_VALID_RES9_HEXES),
)


@settings(max_examples=100)
@given(
    h3_index=_h3_index_strategy,
    coverage_fraction=st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False),
    candidate_hex=st.sampled_from(_VALID_RES9_HEXES),
)
def test_uncovered_demand_excludes_covered_hexes(
    h3_index: dict,
    coverage_fraction: float,
    candidate_hex: str,
) -> None:
    """
    **Validates: Requirements 1.5, 2.3**

    Property 3: For any candidate position C, h3_index, and coverage_index,
    _uncovered_demand(C, radius, h3_index, coverage_index) must equal the sum
    of densities of hexes in h3_index that are:
      (1) within radius_m of the center of C (Haversine), AND
      (2) NOT in coverage_index.
    """
    # Feature: geo-cap-optimization, Property 3: Demanda não coberta exclui hexes cobertos por outros parceiros Active
    import math
    import h3 as h3lib

    from geo_intelligence.geo_phase3_5_cap_optimizer import _uncovered_demand, _haversine_m

    # Build coverage_index as a deterministic subset of h3_index keys
    # driven by coverage_fraction (0.0 = none covered, 1.0 = all covered)
    all_hexes = list(h3_index.keys())
    n_covered = int(len(all_hexes) * coverage_fraction)
    # Use a stable sort so the subset is deterministic given the same inputs
    sorted_hexes = sorted(all_hexes)
    coverage_index = set(sorted_hexes[:n_covered])

    # Use a large radius (2000 m) to ensure a meaningful number of hexes are in range
    radius_m = 2000

    # Call the function under test
    result = _uncovered_demand(candidate_hex, radius_m, h3_index, coverage_index)

    # Compute the expected value manually (reference implementation)
    cand_lat, cand_lon = h3lib.cell_to_latlng(candidate_hex)
    expected = 0.0
    for hex_id, density in h3_index.items():
        if hex_id in coverage_index:
            continue
        hex_lat, hex_lon = h3lib.cell_to_latlng(hex_id)
        dist = _haversine_m(cand_lat, cand_lon, hex_lat, hex_lon)
        if dist <= radius_m:
            expected += density if density is not None else 0.0

    assert abs(result - expected) < 1e-9, (
        f"_uncovered_demand mismatch: got {result}, expected {expected}. "
        f"candidate={candidate_hex!r}, radius={radius_m}, "
        f"coverage_index size={len(coverage_index)}, h3_index size={len(h3_index)}"
    )


# ---------------------------------------------------------------------------
# Property 6 — Seleção do melhor candidato
# Feature: geo-cap-optimization, Property 6: Seleção do melhor candidato
# ---------------------------------------------------------------------------

# Strategy: generate a list of candidate dicts with random estimated_adv_gain
# (integers 1-79) and distance_from_current (floats 0-2000).
_candidate_strategy = st.fixed_dictionaries({
    "estimated_adv_gain": st.integers(min_value=1, max_value=79),
    "distance_from_current": st.floats(
        min_value=0.0,
        max_value=2000.0,
        allow_nan=False,
        allow_infinity=False,
    ),
})

_candidates_list_strategy = st.lists(_candidate_strategy, min_size=1, max_size=20)


@settings(max_examples=100)
@given(candidates=_candidates_list_strategy)
def test_select_best_candidate_max_gain(candidates: list) -> None:
    """
    **Validates: Requirements 1.7, 10.5**

    Property 6 (part 1): _select_best_candidate must return the candidate
    with the highest estimated_adv_gain from any non-empty list.
    """
    # Feature: geo-cap-optimization, Property 6: Seleção do melhor candidato
    from geo_intelligence.geo_phase3_5_cap_optimizer import _select_best_candidate

    result = _select_best_candidate(candidates)

    assert result is not None, "_select_best_candidate returned None for non-empty list"

    max_gain = max(c["estimated_adv_gain"] for c in candidates)
    assert result["estimated_adv_gain"] == max_gain, (
        f"Expected estimated_adv_gain={max_gain}, got {result['estimated_adv_gain']}"
    )


@settings(max_examples=100)
@given(
    base_gain=st.integers(min_value=1, max_value=79),
    tied_distances=st.lists(
        st.floats(min_value=0.0, max_value=2000.0, allow_nan=False, allow_infinity=False),
        min_size=2,
        max_size=10,
    ),
    other_candidates=st.lists(
        st.fixed_dictionaries({
            "estimated_adv_gain": st.integers(min_value=1, max_value=78),
            "distance_from_current": st.floats(
                min_value=0.0,
                max_value=2000.0,
                allow_nan=False,
                allow_infinity=False,
            ),
        }),
        min_size=0,
        max_size=5,
    ),
)
def test_select_best_candidate_tiebreak_by_distance(
    base_gain: int,
    tied_distances: list,
    other_candidates: list,
) -> None:
    """
    **Validates: Requirements 1.7, 10.5**

    Property 6 (part 2): When multiple candidates share the same max
    estimated_adv_gain, _select_best_candidate must return the one with
    the smallest distance_from_current.
    """
    # Feature: geo-cap-optimization, Property 6: Seleção do melhor candidato
    from geo_intelligence.geo_phase3_5_cap_optimizer import _select_best_candidate

    # Build tied candidates — all share base_gain as their estimated_adv_gain.
    # Ensure base_gain is strictly greater than any gain in other_candidates.
    tied_candidates = [
        {"estimated_adv_gain": base_gain, "distance_from_current": d}
        for d in tied_distances
    ]

    # Filter other_candidates to have strictly lower gain than base_gain
    lower_candidates = [
        c for c in other_candidates if c["estimated_adv_gain"] < base_gain
    ]

    all_candidates = tied_candidates + lower_candidates

    result = _select_best_candidate(all_candidates)

    assert result is not None, "_select_best_candidate returned None for non-empty list"

    # The result must have the max gain (base_gain)
    assert result["estimated_adv_gain"] == base_gain, (
        f"Expected estimated_adv_gain={base_gain}, got {result['estimated_adv_gain']}"
    )

    # Among tied candidates, the result must have the minimum distance
    min_distance = min(c["distance_from_current"] for c in tied_candidates)
    assert result["distance_from_current"] == min_distance, (
        f"Tiebreak failed: expected distance_from_current={min_distance}, "
        f"got {result['distance_from_current']}"
    )


def test_select_best_candidate_empty_list() -> None:
    """
    **Validates: Requirements 1.7, 10.5**

    Property 6 (part 3): _select_best_candidate must return None for an
    empty list.
    """
    # Feature: geo-cap-optimization, Property 6: Seleção do melhor candidato
    from geo_intelligence.geo_phase3_5_cap_optimizer import _select_best_candidate

    result = _select_best_candidate([])
    assert result is None, f"Expected None for empty list, got {result}"


# ---------------------------------------------------------------------------
# Property 1 — Cobertura total de parceiros Active
# Feature: geo-cap-optimization, Property 1: Cobertura total de parceiros Active
# ---------------------------------------------------------------------------

from unittest.mock import MagicMock
from geo_intelligence.geo_daily import GeoDailyResult, GeoPartnerMatch


def _make_active_partner(partner_id: str, capacity: int, origin_hex: str) -> GeoPartnerMatch:
    """Helper: cria um GeoPartnerMatch Active com coordenadas derivadas do hex."""
    import h3 as h3lib
    try:
        lat, lon = h3lib.cell_to_latlng(origin_hex)
    except Exception:
        lat, lon = -23.55, -46.63
    return GeoPartnerMatch(
        partner_id=partner_id,
        status="Active",
        origin_hex=origin_hex,
        lat=lat,
        lon=lon,
        matched_slot_id=None,
        territory_id=None,
        decision="Go",
        reason="Seguir cadastro",
        radius=1500,
        capacity=capacity,
    )


def _make_h3_cells_records(h3_index_r8: list) -> list:
    """Helper: cria registros sintéticos de geo_h3_cells a partir de hexes res 8."""
    return [
        {"h3_id": h, "delivery_density_r8": 100.0}
        for h in h3_index_r8
    ]


_active_partner_strategy = st.builds(
    _make_active_partner,
    partner_id=st.text(
        alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Nd")),
        min_size=4,
        max_size=18,
    ),
    capacity=st.integers(min_value=1, max_value=79),
    origin_hex=st.sampled_from(_VALID_RES9_HEXES),
)


@settings(max_examples=100)
@given(
    active_partners=st.lists(_active_partner_strategy, min_size=0, max_size=50),
)
def test_property1_all_active_partners_have_exactly_one_record(
    active_partners: list,
) -> None:
    """
    **Validates: Requirements 1.2, 10.6**

    Property 1: For any GeoDailyResult with N Active partners, after
    run_geo_phase3_5 the list of persisted opportunities must contain
    exactly one record for each Active partner — no silent omissions.
    """
    # Feature: geo-cap-optimization, Property 1: Cobertura total de parceiros Active
    from geo_intelligence.geo_phase3_5_cap_optimizer import run_geo_phase3_5

    # Deduplicate partner_ids to avoid ambiguity in the assertion
    seen_ids: set = set()
    unique_partners = []
    for p in active_partners:
        if p.partner_id not in seen_ids:
            seen_ids.add(p.partner_id)
            unique_partners.append(p)

    daily_result = GeoDailyResult(
        station_code="DSP2",
        run_id="run_test_001",
        matched=unique_partners,
        unmatched=[],
    )

    # Mock reader: return synthetic h3_cells so h3_index is non-empty
    reader = MagicMock()
    reader.get_h3_cells_for_station.return_value = _make_h3_cells_records(
        _VALID_RES8_HEXES[:5]
    )

    # Mock writer: capture the opportunities list passed to upsert_cap_opportunities
    writer = MagicMock()
    captured: list = []

    def _capture(run_id, opportunities):
        captured.extend(opportunities)

    writer.upsert_cap_opportunities.side_effect = _capture

    run_geo_phase3_5(
        daily_result=daily_result,
        run_id="run_test_001",
        station_code="DSP2",
        writer=writer,
        reader=reader,
    )

    # If there are no active partners, upsert may not be called at all
    if not unique_partners:
        # Either not called or called with empty list — both are valid
        total_records = len(captured)
        assert total_records == 0, (
            f"Expected 0 records for 0 active partners, got {total_records}"
        )
        return

    # Verify upsert was called exactly once
    writer.upsert_cap_opportunities.assert_called_once()

    # Verify exactly one record per Active partner
    persisted_ids = [opp["partner_id"] for opp in captured]
    expected_ids = [p.partner_id for p in unique_partners]

    assert len(persisted_ids) == len(expected_ids), (
        f"Expected {len(expected_ids)} records, got {len(persisted_ids)}. "
        f"Missing: {set(expected_ids) - set(persisted_ids)}, "
        f"Extra: {set(persisted_ids) - set(expected_ids)}"
    )
    assert set(persisted_ids) == set(expected_ids), (
        f"Partner IDs mismatch. Expected: {set(expected_ids)}, Got: {set(persisted_ids)}"
    )


# ---------------------------------------------------------------------------
# Property 2 — Parceiros com cap >= 80 resultam em oportunidade nula
# Feature: geo-cap-optimization, Property 2: Parceiros com cap >= 80 sempre resultam em oportunidade nula
# ---------------------------------------------------------------------------

_high_cap_partner_strategy = st.builds(
    _make_active_partner,
    partner_id=st.text(
        alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Nd")),
        min_size=4,
        max_size=18,
    ),
    capacity=st.integers(min_value=80, max_value=200),
    origin_hex=st.sampled_from(_VALID_RES9_HEXES),
)


@settings(max_examples=100)
@given(
    active_partners=st.lists(_high_cap_partner_strategy, min_size=1, max_size=20),
)
def test_property2_high_cap_partners_always_null_opportunity(
    active_partners: list,
) -> None:
    """
    **Validates: Requirements 1.3, 10.1**

    Property 2: For any Active partner with capacity >= 80, run_geo_phase3_5
    must produce suggested_cap = null and estimated_adv_gain = null,
    regardless of the h3_index content.
    """
    # Feature: geo-cap-optimization, Property 2: Parceiros com cap >= 80 sempre resultam em oportunidade nula
    from geo_intelligence.geo_phase3_5_cap_optimizer import run_geo_phase3_5

    # Deduplicate partner_ids
    seen_ids: set = set()
    unique_partners = []
    for p in active_partners:
        if p.partner_id not in seen_ids:
            seen_ids.add(p.partner_id)
            unique_partners.append(p)

    daily_result = GeoDailyResult(
        station_code="DSP2",
        run_id="run_test_002",
        matched=unique_partners,
        unmatched=[],
    )

    # Reader returns rich h3_cells data — should not matter for cap >= 80
    reader = MagicMock()
    reader.get_h3_cells_for_station.return_value = _make_h3_cells_records(
        _VALID_RES8_HEXES
    )

    writer = MagicMock()
    captured: list = []

    def _capture(run_id, opportunities):
        captured.extend(opportunities)

    writer.upsert_cap_opportunities.side_effect = _capture

    run_geo_phase3_5(
        daily_result=daily_result,
        run_id="run_test_002",
        station_code="DSP2",
        writer=writer,
        reader=reader,
    )

    # Every record for a high-cap partner must have null suggested_cap and estimated_adv_gain
    high_cap_ids = {p.partner_id for p in unique_partners}
    for opp in captured:
        if opp["partner_id"] in high_cap_ids:
            assert opp["suggested_cap"] is None, (
                f"Partner {opp['partner_id']} has capacity >= 80 but "
                f"suggested_cap={opp['suggested_cap']} (expected null)"
            )
            assert opp["estimated_adv_gain"] is None, (
                f"Partner {opp['partner_id']} has capacity >= 80 but "
                f"estimated_adv_gain={opp['estimated_adv_gain']} (expected null)"
            )


# ---------------------------------------------------------------------------
# Property 4 — Auto-exclusão revela demanda do próprio parceiro
# Feature: geo-cap-optimization, Property 4: Auto-exclusão revela demanda do próprio parceiro
# ---------------------------------------------------------------------------

@settings(max_examples=100)
@given(
    # Pick a partner hex from res9 list
    partner_hex=st.sampled_from(_VALID_RES9_HEXES),
    # Density assigned to the partner's exclusive hexes
    exclusive_density=st.floats(
        min_value=10.0,
        max_value=500.0,
        allow_nan=False,
        allow_infinity=False,
    ),
    # Radius to use for the uncovered demand calculation
    radius_m=st.sampled_from([500, 800, 1100, 1500]),
)
def test_property4_self_exclusion_reveals_own_demand(
    partner_hex: str,
    exclusive_density: float,
    radius_m: int,
) -> None:
    """
    **Validates: Requirement 2.4**

    Property 4: When partner P has exclusive coverage over hexes H (covered
    only by P), the _uncovered_demand for P's position must include hexes H
    because P's own coverage is excluded from the coverage_index when
    evaluating P's opportunity.
    """
    # Feature: geo-cap-optimization, Property 4: Auto-exclusão revela demanda do próprio parceiro
    import h3 as h3lib
    from geo_intelligence.geo_phase3_5_cap_optimizer import (
        _build_coverage_index,
        _uncovered_demand,
        _haversine_m,
    )

    # Build a small h3_index using the partner_hex and its immediate neighbors
    try:
        neighbors = list(h3lib.grid_disk(partner_hex, 1))
    except Exception:
        neighbors = [partner_hex]

    # Assign exclusive_density to all neighbor hexes
    h3_index = {h: exclusive_density for h in neighbors}

    # Create partner P at the partner_hex location
    try:
        p_lat, p_lon = h3lib.cell_to_latlng(partner_hex)
    except Exception:
        p_lat, p_lon = -23.55, -46.63

    partner_p = GeoPartnerMatch(
        partner_id="PARTNER_P_EXCLUSIVE",
        status="Active",
        origin_hex=partner_hex,
        lat=p_lat,
        lon=p_lon,
        matched_slot_id=None,
        territory_id=None,
        decision="Go",
        reason="Seguir cadastro",
        radius=radius_m,
        capacity=10,
    )

    # Build coverage_index WITH P included — all neighbor hexes should be covered by P
    coverage_with_p = _build_coverage_index(
        active_partners=[partner_p],
        h3_index=h3_index,
        exclude_partner_id=None,  # include P
    )

    # Build coverage_index WITHOUT P (auto-exclusion) — hexes exclusively covered by P
    # should NOT be in the coverage index
    coverage_without_p = _build_coverage_index(
        active_partners=[partner_p],
        h3_index=h3_index,
        exclude_partner_id="PARTNER_P_EXCLUSIVE",  # exclude P
    )

    # Identify hexes exclusively covered by P (in coverage_with_p but not coverage_without_p)
    exclusive_hexes = coverage_with_p - coverage_without_p

    # If P covers any hexes exclusively, those hexes must contribute to uncovered demand
    # when P is excluded from the coverage index
    if exclusive_hexes:
        demand_with_exclusion = _uncovered_demand(
            partner_hex, radius_m, h3_index, coverage_without_p
        )

        # The demand with P excluded must be > 0 (exclusive hexes contribute)
        assert demand_with_exclusion > 0.0, (
            f"Expected uncovered demand > 0 when P is excluded from coverage, "
            f"but got {demand_with_exclusion}. "
            f"exclusive_hexes={exclusive_hexes}, partner_hex={partner_hex}"
        )

        # Verify that without exclusion (P included), those hexes are covered
        # and thus do NOT contribute to uncovered demand
        demand_without_exclusion = _uncovered_demand(
            partner_hex, radius_m, h3_index, coverage_with_p
        )

        # demand_with_exclusion must be >= demand_without_exclusion
        # (auto-exclusion can only reveal more demand, never less)
        assert demand_with_exclusion >= demand_without_exclusion, (
            f"Auto-exclusion should reveal >= demand: "
            f"with_exclusion={demand_with_exclusion}, "
            f"without_exclusion={demand_without_exclusion}"
        )


# ---------------------------------------------------------------------------
# Property 5 — Invariante aritmético de suggested_cap e estimated_adv_gain
# Feature: geo-cap-optimization, Property 5: Invariante aritmético de suggested_cap e estimated_adv_gain
# ---------------------------------------------------------------------------

@settings(max_examples=100)
@given(
    capacity=st.integers(min_value=1, max_value=79),
    partner_hex=st.sampled_from(_VALID_RES9_HEXES),
    # Use a high density to ensure demand > capacity and an opportunity is triggered
    density=st.floats(
        min_value=200.0,
        max_value=500.0,
        allow_nan=False,
        allow_infinity=False,
    ),
)
def test_property5_arithmetic_invariant_suggested_cap_and_adv_gain(
    capacity: int,
    partner_hex: str,
    density: float,
) -> None:
    """
    **Validates: Requirements 1.6, 3.4, 3.5, 10.3, 10.4**

    Property 5: For any non-null opportunity generated by _scan_partner:
    - capacity_atual < suggested_cap <= 80
    - estimated_adv_gain == suggested_cap - capacity_atual
    """
    # Feature: geo-cap-optimization, Property 5: Invariante aritmético de suggested_cap e estimated_adv_gain
    import h3 as h3lib
    from geo_intelligence.geo_phase3_5_cap_optimizer import _scan_partner

    # Build a rich h3_index: partner_hex + all disk-3 neighbors with high density
    try:
        candidate_hexes = list(h3lib.grid_disk(partner_hex, 3))
    except Exception:
        candidate_hexes = [partner_hex]

    h3_index = {h: density for h in candidate_hexes}

    # Empty coverage_index so all demand is uncovered
    coverage_index: set = set()

    try:
        p_lat, p_lon = h3lib.cell_to_latlng(partner_hex)
    except Exception:
        p_lat, p_lon = -23.55, -46.63

    partner = GeoPartnerMatch(
        partner_id="PARTNER_PROP5",
        status="Active",
        origin_hex=partner_hex,
        lat=p_lat,
        lon=p_lon,
        matched_slot_id=None,
        territory_id=None,
        decision="Go",
        reason="Seguir cadastro",
        radius=1500,
        capacity=capacity,
    )

    result = _scan_partner(partner, h3_index, coverage_index)

    # With high density and empty coverage, an opportunity should be found
    if result is not None:
        suggested_cap = result["suggested_cap"]
        estimated_adv_gain = result["estimated_adv_gain"]

        # Invariant: capacity_atual < suggested_cap <= 80
        assert suggested_cap > capacity, (
            f"suggested_cap={suggested_cap} must be > capacity={capacity}"
        )
        assert suggested_cap <= 80, (
            f"suggested_cap={suggested_cap} must be <= 80"
        )

        # Invariant: estimated_adv_gain == suggested_cap - capacity_atual
        expected_gain = suggested_cap - capacity
        assert estimated_adv_gain == expected_gain, (
            f"estimated_adv_gain={estimated_adv_gain} != "
            f"suggested_cap - capacity = {suggested_cap} - {capacity} = {expected_gain}"
        )


# ---------------------------------------------------------------------------
# Property 9 — Determinismo
# Feature: geo-cap-optimization, Property 9: Determinismo
# ---------------------------------------------------------------------------

@settings(max_examples=100)
@given(
    active_partners=st.lists(
        st.builds(
            _make_active_partner,
            partner_id=st.text(
                alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Nd")),
                min_size=4,
                max_size=18,
            ),
            capacity=st.integers(min_value=1, max_value=79),
            origin_hex=st.sampled_from(_VALID_RES9_HEXES),
        ),
        min_size=1,
        max_size=10,
    ),
    h3_cells_hexes=st.lists(
        st.sampled_from(_VALID_RES8_HEXES),
        min_size=1,
        max_size=10,
    ),
)
def test_property9_determinism(
    active_partners: list,
    h3_cells_hexes: list,
) -> None:
    """
    **Validates: Requirement 10.7**

    Property 9: For any fixed GeoDailyResult and h3_index, executing
    run_geo_phase3_5 twice with deterministic mocks must produce identical
    results (same partner_id, suggested_cap, suggested_lat, suggested_lon,
    estimated_adv_gain).
    """
    # Feature: geo-cap-optimization, Property 9: Determinismo
    from geo_intelligence.geo_phase3_5_cap_optimizer import run_geo_phase3_5

    # Deduplicate partner_ids
    seen_ids: set = set()
    unique_partners = []
    for p in active_partners:
        if p.partner_id not in seen_ids:
            seen_ids.add(p.partner_id)
            unique_partners.append(p)

    h3_cells_records = _make_h3_cells_records(list(set(h3_cells_hexes)))

    def _make_mocks():
        reader = MagicMock()
        reader.get_h3_cells_for_station.return_value = h3_cells_records

        writer = MagicMock()
        captured: list = []

        def _capture(run_id, opportunities):
            captured.extend(opportunities)

        writer.upsert_cap_opportunities.side_effect = _capture
        return reader, writer, captured

    daily_result = GeoDailyResult(
        station_code="DSP2",
        run_id="run_det_001",
        matched=unique_partners,
        unmatched=[],
    )

    # First execution
    reader1, writer1, captured1 = _make_mocks()
    run_geo_phase3_5(
        daily_result=daily_result,
        run_id="run_det_001",
        station_code="DSP2",
        writer=writer1,
        reader=reader1,
    )

    # Second execution (same inputs, fresh mocks)
    reader2, writer2, captured2 = _make_mocks()
    run_geo_phase3_5(
        daily_result=daily_result,
        run_id="run_det_001",
        station_code="DSP2",
        writer=writer2,
        reader=reader2,
    )

    # Both runs must produce the same number of records
    assert len(captured1) == len(captured2), (
        f"Determinism violated: run1 produced {len(captured1)} records, "
        f"run2 produced {len(captured2)} records"
    )

    # Sort by partner_id for stable comparison
    key_fn = lambda o: o["partner_id"]
    sorted1 = sorted(captured1, key=key_fn)
    sorted2 = sorted(captured2, key=key_fn)

    _FIELDS_TO_COMPARE = [
        "partner_id",
        "suggested_cap",
        "suggested_lat",
        "suggested_lon",
        "estimated_adv_gain",
    ]

    for rec1, rec2 in zip(sorted1, sorted2):
        for field_name in _FIELDS_TO_COMPARE:
            v1 = rec1.get(field_name)
            v2 = rec2.get(field_name)
            if isinstance(v1, float) and isinstance(v2, float):
                assert abs(v1 - v2) < 1e-9, (
                    f"Determinism violated for field '{field_name}' "
                    f"on partner '{rec1['partner_id']}': "
                    f"run1={v1}, run2={v2}"
                )
            else:
                assert v1 == v2, (
                    f"Determinism violated for field '{field_name}' "
                    f"on partner '{rec1['partner_id']}': "
                    f"run1={v1}, run2={v2}"
                )
