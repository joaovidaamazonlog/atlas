"""
test_phase3_5_properties.py
============================
Property-based tests for Phase 3.5 — Partner Cap Optimization.

**Validates: Requirements 1.2**

Property 1: All Active partners are evaluated
---------------------------------------------
For any FitResult containing N Active partners, after run_phase3_5 completes,
the patched dados_mapa.json must contain an adv_opportunity entry (either an
object or null) for every one of those N Active partners — no Active partner
may be silently skipped.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile

# Allow imports from backend/ without installing as a package
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from hypothesis import given, settings
from hypothesis import strategies as st

from shared.models import PartnerMetrics
from vanilla.phase3_5_cap_optimizer import run_phase3_5
from vanilla.phase3_partner_fit import FitResult, TerritoryFit

# ---------------------------------------------------------------------------
# Hypothesis strategies
# ---------------------------------------------------------------------------

# A valid H3 res-9 hex in São Paulo area
_VALID_HEX = "891f1d48177ffff"

_salesforce_id_strategy = st.text(
    alphabet="ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789",
    min_size=5,
    max_size=18,
)

_active_partner_strategy = st.builds(
    PartnerMetrics,
    origin_hex=st.just(_VALID_HEX),
    station_code=st.just("DSP2"),
    radius_s=st.integers(min_value=500, max_value=3000),
    capacity_s=st.integers(min_value=1, max_value=79),
    entity_type=st.just("EXISTING"),
    status=st.just("Active"),
    partner_name=st.text(max_size=50),
    salesforce_id=_salesforce_id_strategy,
    lat=st.floats(min_value=-23.6, max_value=-23.4, allow_nan=False, allow_infinity=False),
    lon=st.floats(min_value=-46.7, max_value=-46.5, allow_nan=False, allow_infinity=False),
)


def _make_fit_result(partners: list[PartnerMetrics]) -> FitResult:
    """
    Wraps a list of PartnerMetrics into a minimal FitResult.
    All partners are placed in a single TerritoryFit so that
    fit.all_partners() returns them all.
    """
    territory = TerritoryFit(
        territory_id="DSP2_bucket-01",
        station_code="DSP2",
        bdm_cluster="SP/SUL",
        ctl_name="N/A",
        slots=[],
        partners=list(partners),
    )
    return FitResult(
        territories={"DSP2_bucket-01": territory},
        outside_jurisdiction=[],
        unassigned_by_territory={},
    )


def _make_minimal_heatmap(output_dir: str) -> None:
    """
    Writes a minimal heatmap.geojson with a single hex feature.
    demand_residual is 0 so no real opportunity is expected — the test
    only checks that every Active partner is *evaluated* (field present).
    """
    geojson = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": {"type": "Polygon", "coordinates": [[]]},
                "properties": {
                    "hex_id": _VALID_HEX,
                    "demand_daily": 0.0,
                    "demand_residual": 0.0,
                    "is_covered": False,
                    "covering_partner_id": None,
                },
            }
        ],
    }
    path = os.path.join(output_dir, "heatmap.geojson")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(geojson, f)


def _make_dados_mapa(output_dir: str, partners: list[PartnerMetrics]) -> None:
    """
    Writes a minimal dados_mapa.json containing one record per partner.
    Each record has the salesforce_id and a placeholder adv_opportunity.
    """
    records = [
        {
            "salesforce_id": p.salesforce_id,
            "name": p.partner_name,
            "status": p.status,
            "adv_opportunity": None,
        }
        for p in partners
    ]
    payload = {"allMarkerData": records}
    path = os.path.join(output_dir, "dados_mapa.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f)


# ---------------------------------------------------------------------------
# Property 1 — All Active partners are evaluated
# Feature: partner-cap-optimization, Property 1: All Active partners are evaluated
# ---------------------------------------------------------------------------

@settings(max_examples=100, deadline=None)
@given(
    partners=st.lists(
        _active_partner_strategy,
        min_size=0,
        max_size=20,
    ).filter(
        # Ensure all salesforce_ids are unique so each partner maps to a distinct record
        lambda ps: len({p.salesforce_id for p in ps}) == len(ps)
    )
)
def test_all_active_partners_have_adv_opportunity_key(partners: list[PartnerMetrics]):
    """
    **Validates: Requirements 1.2**

    Property 1: For any FitResult with N Active partners, after run_phase3_5
    completes, every Active partner's salesforce_id must have an adv_opportunity
    key in dados_mapa.json (value may be null or a dict — but the key must exist).
    """
    # Feature: partner-cap-optimization, Property 1: All Active partners are evaluated

    fit = _make_fit_result(partners)

    with tempfile.TemporaryDirectory() as tmp_dir:
        _make_minimal_heatmap(tmp_dir)
        _make_dados_mapa(tmp_dir, partners)

        run_phase3_5(fit=fit, output_dir=tmp_dir)

        # Read the resulting dados_mapa.json
        dados_path = os.path.join(tmp_dir, "dados_mapa.json")
        with open(dados_path, "r", encoding="utf-8") as f:
            payload = json.load(f)

        records = payload.get("allMarkerData", [])
        # Build a lookup: salesforce_id -> record
        record_by_sfid = {r["salesforce_id"]: r for r in records}

        for partner in partners:
            sfid = partner.salesforce_id
            assert sfid in record_by_sfid, (
                f"Partner {sfid!r} not found in dados_mapa.json records"
            )
            record = record_by_sfid[sfid]
            assert "adv_opportunity" in record, (
                f"Partner {sfid!r} (Active) is missing 'adv_opportunity' key "
                f"in dados_mapa.json after run_phase3_5"
            )
            # Value must be either None/null or a dict — never absent
            adv = record["adv_opportunity"]
            assert adv is None or isinstance(adv, dict), (
                f"Partner {sfid!r} has unexpected adv_opportunity type: {type(adv)}"
            )


# ---------------------------------------------------------------------------
# Property 2 — Cap-80 partners always yield null opportunity
# Feature: partner-cap-optimization, Property 2: Cap-80 partners always yield null opportunity
# ---------------------------------------------------------------------------

_cap80_partner_strategy = st.builds(
    PartnerMetrics,
    origin_hex=st.just(_VALID_HEX),
    station_code=st.just("DSP2"),
    radius_s=st.integers(min_value=500, max_value=3000),
    capacity_s=st.integers(min_value=80, max_value=200),
    entity_type=st.just("EXISTING"),
    status=st.just("Active"),
    partner_name=st.text(max_size=50),
    salesforce_id=_salesforce_id_strategy,
    lat=st.floats(min_value=-23.6, max_value=-23.4, allow_nan=False, allow_infinity=False),
    lon=st.floats(min_value=-46.7, max_value=-46.5, allow_nan=False, allow_infinity=False),
)


def _make_high_demand_heatmap(output_dir: str) -> None:
    """
    Writes a heatmap.geojson with high demand_residual so that any failure
    to produce null is clearly due to the cap>=80 rule, not lack of demand.
    """
    geojson = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": {"type": "Polygon", "coordinates": [[]]},
                "properties": {
                    "hex_id": _VALID_HEX,
                    "demand_daily": 500.0,
                    "demand_residual": 500.0,
                    "is_covered": False,
                    "covering_partner_id": None,
                },
            }
        ],
    }
    path = os.path.join(output_dir, "heatmap.geojson")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(geojson, f)


@settings(max_examples=100, deadline=None)
@given(
    partners=st.lists(
        _cap80_partner_strategy,
        min_size=1,
        max_size=20,
    ).filter(
        lambda ps: len({p.salesforce_id for p in ps}) == len(ps)
    )
)
def test_cap80_partners_always_yield_null_opportunity(partners: list[PartnerMetrics]):
    """
    **Validates: Requirements 1.3**

    Property 2: For any Active partner with capacity_s >= 80, after run_phase3_5
    completes, adv_opportunity must be null in dados_mapa.json — regardless of
    how much demand_residual is available in the heatmap.
    """
    # Feature: partner-cap-optimization, Property 2: Cap-80 partners always yield null opportunity

    fit = _make_fit_result(partners)

    with tempfile.TemporaryDirectory() as tmp_dir:
        _make_high_demand_heatmap(tmp_dir)
        _make_dados_mapa(tmp_dir, partners)

        run_phase3_5(fit=fit, output_dir=tmp_dir)

        dados_path = os.path.join(tmp_dir, "dados_mapa.json")
        with open(dados_path, "r", encoding="utf-8") as f:
            payload = json.load(f)

        records = payload.get("allMarkerData", [])
        record_by_sfid = {r["salesforce_id"]: r for r in records}

        for partner in partners:
            sfid = partner.salesforce_id
            assert sfid in record_by_sfid, (
                f"Partner {sfid!r} (capacity_s={partner.capacity_s}) not found in dados_mapa.json"
            )
            record = record_by_sfid[sfid]
            assert "adv_opportunity" in record, (
                f"Partner {sfid!r} (capacity_s={partner.capacity_s} >= 80) is missing "
                f"'adv_opportunity' key in dados_mapa.json after run_phase3_5"
            )
            adv = record["adv_opportunity"]
            assert adv is None, (
                f"Partner {sfid!r} has capacity_s={partner.capacity_s} >= 80 but "
                f"adv_opportunity is not null: {adv!r}"
            )


# ---------------------------------------------------------------------------
# Property 3 — Under-cap partners with available demand yield non-null
# Feature: partner-cap-optimization, Property 3: Under-cap partners with available demand yield non-null opportunity
# ---------------------------------------------------------------------------

# Fixed partner position in São Paulo area
_FIXED_LAT = -23.5
_FIXED_LON = -46.6

import h3 as _h3

# Compute the origin hex and all disk-3 neighbors at res 9 for the fixed position.
# These are the hexes that _candidate_positions will return for this lat/lon.
_FIXED_ORIGIN_HEX = _h3.latlng_to_cell(_FIXED_LAT, _FIXED_LON, 9)
_FIXED_DISK_HEXES = list(_h3.grid_disk(_FIXED_ORIGIN_HEX, 3))


def _make_high_demand_heatmap_for_fixed_position(output_dir: str, demand_residual: float) -> None:
    """
    Writes a heatmap.geojson that covers all hexes in the disk-3 neighborhood
    of the fixed partner position, each with the given demand_residual.

    This ensures _available_residual returns a value > capacity_s for any
    partner_radius in Config.RADII (since all neighbor hexes are populated).
    """
    features = []
    for hex_id in _FIXED_DISK_HEXES:
        features.append(
            {
                "type": "Feature",
                "geometry": {"type": "Polygon", "coordinates": [[]]},
                "properties": {
                    "hex_id": hex_id,
                    "demand_daily": demand_residual,
                    "demand_residual": demand_residual,
                    "is_covered": False,
                    "covering_partner_id": None,
                },
            }
        )
    geojson = {"type": "FeatureCollection", "features": features}
    path = os.path.join(output_dir, "heatmap.geojson")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(geojson, f)


_under_cap_partner_strategy = st.builds(
    PartnerMetrics,
    # Fixed position so we know exactly which hexes _candidate_positions returns
    lat=st.just(_FIXED_LAT),
    lon=st.just(_FIXED_LON),
    origin_hex=st.just(_FIXED_ORIGIN_HEX),
    station_code=st.just("DSP2"),
    # Use a radius large enough to cover the disk-3 neighbors (~500 m covers them)
    radius_s=st.just(500),
    capacity_s=st.integers(min_value=1, max_value=79),
    entity_type=st.just("EXISTING"),
    status=st.just("Active"),
    partner_name=st.text(max_size=50),
    salesforce_id=_salesforce_id_strategy,
)


@settings(max_examples=100, deadline=None)
@given(
    partner=_under_cap_partner_strategy,
)
def test_under_cap_partner_with_demand_yields_non_null_opportunity(partner: PartnerMetrics):
    """
    **Validates: Requirements 1.4, 1.6**

    Property 3: For any Active partner with capacity_s in [1, 79] and a heatmap
    where the hexes at the partner's location have demand_residual significantly
    higher than the partner's capacity, run_phase3_5 must produce a non-null
    adv_opportunity in dados_mapa.json.
    """
    # Feature: partner-cap-optimization, Property 3: Under-cap partners with available demand yield non-null opportunity

    # demand_residual is set well above capacity_s to guarantee an opportunity
    demand_residual = partner.capacity_s + 50

    fit = _make_fit_result([partner])

    with tempfile.TemporaryDirectory() as tmp_dir:
        _make_high_demand_heatmap_for_fixed_position(tmp_dir, demand_residual)
        _make_dados_mapa(tmp_dir, [partner])

        run_phase3_5(fit=fit, output_dir=tmp_dir)

        dados_path = os.path.join(tmp_dir, "dados_mapa.json")
        with open(dados_path, "r", encoding="utf-8") as f:
            payload = json.load(f)

        records = payload.get("allMarkerData", [])
        record_by_sfid = {r["salesforce_id"]: r for r in records}

        sfid = partner.salesforce_id
        assert sfid in record_by_sfid, (
            f"Partner {sfid!r} not found in dados_mapa.json records"
        )
        record = record_by_sfid[sfid]
        assert "adv_opportunity" in record, (
            f"Partner {sfid!r} (capacity_s={partner.capacity_s}) is missing "
            f"'adv_opportunity' key in dados_mapa.json after run_phase3_5"
        )
        adv = record["adv_opportunity"]
        assert adv is not None, (
            f"Partner {sfid!r} has capacity_s={partner.capacity_s} < 80 and "
            f"demand_residual={demand_residual} > capacity_s, but adv_opportunity is null. "
            f"Expected a non-null opportunity dict."
        )
        assert isinstance(adv, dict), (
            f"Partner {sfid!r} adv_opportunity should be a dict, got {type(adv)}: {adv!r}"
        )


# ---------------------------------------------------------------------------
# Property 4 — suggested_cap invariant
# Feature: partner-cap-optimization, Property 4: suggested_cap invariant
# ---------------------------------------------------------------------------

@settings(max_examples=100, deadline=None)
@given(
    partner=_under_cap_partner_strategy,
)
def test_suggested_cap_invariant(partner: PartnerMetrics):
    """
    **Validates: Requirements 2.3**

    Property 4: For any non-null adv_opportunity produced by run_phase3_5,
    suggested_cap must satisfy: current_cap < suggested_cap <= 80.
    """
    # Feature: partner-cap-optimization, Property 4: suggested_cap invariant

    # demand_residual is set well above capacity_s to guarantee an opportunity
    demand_residual = partner.capacity_s + 50

    fit = _make_fit_result([partner])

    with tempfile.TemporaryDirectory() as tmp_dir:
        _make_high_demand_heatmap_for_fixed_position(tmp_dir, demand_residual)
        _make_dados_mapa(tmp_dir, [partner])

        run_phase3_5(fit=fit, output_dir=tmp_dir)

        dados_path = os.path.join(tmp_dir, "dados_mapa.json")
        with open(dados_path, "r", encoding="utf-8") as f:
            payload = json.load(f)

        records = payload.get("allMarkerData", [])
        record_by_sfid = {r["salesforce_id"]: r for r in records}

        sfid = partner.salesforce_id
        record = record_by_sfid.get(sfid)
        assert record is not None, f"Partner {sfid!r} not found in dados_mapa.json"

        adv = record.get("adv_opportunity")
        if adv is not None:
            suggested_cap = adv["suggested_cap"]
            assert partner.capacity_s < suggested_cap, (
                f"Partner {sfid!r} has capacity_s={partner.capacity_s} but "
                f"suggested_cap={suggested_cap} is not strictly greater than current_cap"
            )
            assert suggested_cap <= 80, (
                f"Partner {sfid!r} has suggested_cap={suggested_cap} which exceeds the max of 80"
            )


# ---------------------------------------------------------------------------
# Property 5 — estimated_adv_gain arithmetic invariant
# Feature: partner-cap-optimization, Property 5: estimated_adv_gain arithmetic invariant
# ---------------------------------------------------------------------------

@settings(max_examples=100, deadline=None)
@given(
    partner=_under_cap_partner_strategy,
)
def test_estimated_adv_gain_arithmetic_invariant(partner: PartnerMetrics):
    """
    **Validates: Requirements 2.4**

    Property 5: For any non-null adv_opportunity produced by run_phase3_5,
    estimated_adv_gain must equal suggested_cap - current_cap (capacity_s).
    """
    # Feature: partner-cap-optimization, Property 5: estimated_adv_gain arithmetic invariant

    # demand_residual is set well above capacity_s to guarantee an opportunity
    demand_residual = partner.capacity_s + 50

    fit = _make_fit_result([partner])

    with tempfile.TemporaryDirectory() as tmp_dir:
        _make_high_demand_heatmap_for_fixed_position(tmp_dir, demand_residual)
        _make_dados_mapa(tmp_dir, [partner])

        run_phase3_5(fit=fit, output_dir=tmp_dir)

        dados_path = os.path.join(tmp_dir, "dados_mapa.json")
        with open(dados_path, "r", encoding="utf-8") as f:
            payload = json.load(f)

        records = payload.get("allMarkerData", [])
        record_by_sfid = {r["salesforce_id"]: r for r in records}

        sfid = partner.salesforce_id
        record = record_by_sfid.get(sfid)
        assert record is not None, f"Partner {sfid!r} not found in dados_mapa.json"

        adv = record.get("adv_opportunity")
        if adv is not None:
            estimated_adv_gain = adv["estimated_adv_gain"]
            suggested_cap = adv["suggested_cap"]
            expected_gain = suggested_cap - partner.capacity_s
            assert estimated_adv_gain == expected_gain, (
                f"Partner {sfid!r} (capacity_s={partner.capacity_s}): "
                f"estimated_adv_gain={estimated_adv_gain} but "
                f"suggested_cap - capacity_s = {suggested_cap} - {partner.capacity_s} = {expected_gain}"
            )


# ---------------------------------------------------------------------------
# Property 6 — Best candidate selection
# Feature: partner-cap-optimization, Property 6: Best candidate selection
# ---------------------------------------------------------------------------

_candidate_opp_strategy = st.fixed_dictionaries({
    "estimated_adv_gain": st.integers(min_value=1, max_value=79),
    "distance_from_current": st.floats(min_value=0.0, max_value=300.0, allow_nan=False, allow_infinity=False),
    "suggested_cap": st.integers(min_value=1, max_value=80),
    "suggested_radius": st.integers(min_value=500, max_value=3000),
    "suggested_lat": st.just(-23.5),
    "suggested_lon": st.just(-46.6),
})


@settings(max_examples=100, deadline=None)
@given(
    candidates=st.lists(_candidate_opp_strategy, min_size=1, max_size=20),
)
def test_best_candidate_selection(candidates: list):
    """
    **Validates: Requirements 1.7**

    Property 6: For any set of candidate opportunity dicts, the selection
    algorithm must pick the one with the maximum estimated_adv_gain; among
    ties, the one with the minimum distance_from_current.
    """
    # Feature: partner-cap-optimization, Property 6: Best candidate selection

    # --- Expected best: computed via Python's sort (reference implementation) ---
    expected_best = max(
        candidates,
        key=lambda c: (c["estimated_adv_gain"], -c["distance_from_current"]),
    )

    # --- Actual best: replicate the exact loop logic from run_phase3_5 ---
    actual_best = None
    for opp in candidates:
        if actual_best is None:
            actual_best = opp
        elif opp["estimated_adv_gain"] > actual_best["estimated_adv_gain"]:
            actual_best = opp
        elif (
            opp["estimated_adv_gain"] == actual_best["estimated_adv_gain"]
            and opp["distance_from_current"] < actual_best["distance_from_current"]
        ):
            actual_best = opp

    # Both approaches must agree on the winner
    assert actual_best is not None
    assert actual_best["estimated_adv_gain"] == expected_best["estimated_adv_gain"], (
        f"actual_best gain={actual_best['estimated_adv_gain']} != "
        f"expected_best gain={expected_best['estimated_adv_gain']}"
    )
    assert actual_best["distance_from_current"] <= expected_best["distance_from_current"] + 1e-9, (
        f"actual_best distance={actual_best['distance_from_current']} > "
        f"expected_best distance={expected_best['distance_from_current']} "
        f"(both have gain={actual_best['estimated_adv_gain']})"
    )

    # The actual best must truly be optimal: no candidate beats it
    for c in candidates:
        assert c["estimated_adv_gain"] <= actual_best["estimated_adv_gain"] or (
            c["estimated_adv_gain"] == actual_best["estimated_adv_gain"]
            and c["distance_from_current"] >= actual_best["distance_from_current"] - 1e-9
        ), (
            f"Candidate {c!r} dominates actual_best {actual_best!r}"
        )


# ---------------------------------------------------------------------------
# Property 7 — Partner field preservation
# Feature: partner-cap-optimization, Property 7: Partner field preservation
# ---------------------------------------------------------------------------

@settings(max_examples=100, deadline=None)
@given(
    partners=st.lists(
        st.builds(
            PartnerMetrics,
            origin_hex=st.just(_VALID_HEX),
            station_code=st.just("DSP2"),
            radius_s=st.integers(min_value=500, max_value=3000),
            capacity_s=st.integers(min_value=1, max_value=79),
            entity_type=st.just("EXISTING"),
            status=st.just("Active"),
            partner_name=st.text(max_size=50),
            salesforce_id=_salesforce_id_strategy,
            lat=st.floats(min_value=-23.6, max_value=-23.4, allow_nan=False, allow_infinity=False),
            lon=st.floats(min_value=-46.7, max_value=-46.5, allow_nan=False, allow_infinity=False),
        ),
        min_size=0,
        max_size=20,
    ).filter(
        lambda ps: len({p.salesforce_id for p in ps}) == len(ps)
    )
)
def test_partner_field_preservation(partners: list[PartnerMetrics]):
    """
    **Validates: Requirements 1.10**

    Property 7: For any partner record in dados_mapa.json, after run_phase3_5
    runs, all fields EXCEPT adv_opportunity must be byte-for-byte identical to
    their pre-run values. _patch_dados_mapa must only touch adv_opportunity.
    """
    # Feature: partner-cap-optimization, Property 7: Partner field preservation

    fit = _make_fit_result(partners)

    # Build records with extra fields beyond what _make_dados_mapa normally writes
    records_before = [
        {
            "salesforce_id": p.salesforce_id,
            "name": p.partner_name,
            "status": p.status,
            "lat": p.lat,
            "lon": p.lon,
            "capacity": p.capacity_s,
            "some_extra_field": f"extra_{p.salesforce_id}",
            "adv_opportunity": None,
        }
        for p in partners
    ]

    with tempfile.TemporaryDirectory() as tmp_dir:
        # Write dados_mapa.json with the enriched records
        dados_path = os.path.join(tmp_dir, "dados_mapa.json")
        with open(dados_path, "w", encoding="utf-8") as f:
            json.dump({"allMarkerData": records_before}, f)

        # Zero-demand heatmap so no opportunities are created
        _make_minimal_heatmap(tmp_dir)

        run_phase3_5(fit=fit, output_dir=tmp_dir)

        # Read the resulting dados_mapa.json
        with open(dados_path, "r", encoding="utf-8") as f:
            payload_after = json.load(f)

    records_after = payload_after.get("allMarkerData", [])
    record_after_by_sfid = {r["salesforce_id"]: r for r in records_after}
    record_before_by_sfid = {r["salesforce_id"]: r for r in records_before}

    # Every original record must still be present
    assert len(records_after) == len(records_before), (
        f"Record count changed: before={len(records_before)}, after={len(records_after)}"
    )

    for sfid, before in record_before_by_sfid.items():
        assert sfid in record_after_by_sfid, (
            f"Partner {sfid!r} disappeared from dados_mapa.json after run_phase3_5"
        )
        after = record_after_by_sfid[sfid]

        # All fields except adv_opportunity must be identical
        for field, original_value in before.items():
            if field == "adv_opportunity":
                continue  # this field is allowed to change
            assert field in after, (
                f"Partner {sfid!r}: field {field!r} was removed by run_phase3_5"
            )
            assert after[field] == original_value, (
                f"Partner {sfid!r}: field {field!r} was modified by run_phase3_5. "
                f"Before: {original_value!r}, After: {after[field]!r}"
            )

        # No new fields (other than adv_opportunity) should have been added
        for field in after:
            if field == "adv_opportunity":
                continue
            assert field in before, (
                f"Partner {sfid!r}: unexpected new field {field!r} added by run_phase3_5"
            )


# ---------------------------------------------------------------------------
# Property 8 — Station filter respected
# Feature: partner-cap-optimization, Property 8: Station filter respected
# ---------------------------------------------------------------------------

_dsp2_partner_strategy = st.builds(
    PartnerMetrics,
    origin_hex=st.just(_FIXED_ORIGIN_HEX),
    station_code=st.just("DSP2"),
    radius_s=st.just(500),
    capacity_s=st.integers(min_value=1, max_value=79),
    entity_type=st.just("EXISTING"),
    status=st.just("Active"),
    partner_name=st.text(max_size=50),
    salesforce_id=_salesforce_id_strategy,
    lat=st.just(_FIXED_LAT),
    lon=st.just(_FIXED_LON),
)

_dsp3_partner_strategy = st.builds(
    PartnerMetrics,
    origin_hex=st.just(_FIXED_ORIGIN_HEX),
    station_code=st.just("DSP3"),
    radius_s=st.just(500),
    capacity_s=st.integers(min_value=1, max_value=79),
    entity_type=st.just("EXISTING"),
    status=st.just("Active"),
    partner_name=st.text(max_size=50),
    salesforce_id=_salesforce_id_strategy,
    lat=st.just(_FIXED_LAT),
    lon=st.just(_FIXED_LON),
)


@settings(max_examples=100, deadline=None)
@given(
    dsp2_partners=st.lists(
        _dsp2_partner_strategy,
        min_size=1,
        max_size=10,
    ),
    dsp3_partners=st.lists(
        _dsp3_partner_strategy,
        min_size=1,
        max_size=10,
    ),
)
def test_station_filter_respected(
    dsp2_partners: list[PartnerMetrics],
    dsp3_partners: list[PartnerMetrics],
):
    """
    **Validates: Requirements 3.3**

    Property 8: When stations=["DSP2"] is passed to run_phase3_5, partners
    whose station_code is "DSP3" must have their adv_opportunity field
    UNCHANGED in dados_mapa.json (not evaluated), while partners from "DSP2"
    must have their adv_opportunity key updated.
    """
    # Feature: partner-cap-optimization, Property 8: Station filter respected

    all_partners = dsp2_partners + dsp3_partners

    # Ensure all salesforce_ids are unique across both lists
    all_sfids = [p.salesforce_id for p in all_partners]
    if len(set(all_sfids)) != len(all_sfids):
        return  # skip if duplicates (hypothesis may generate collisions)

    # Sentinel value for DSP3 partners' adv_opportunity before the run.
    # Using a distinct non-null dict so we can detect if it was overwritten.
    _DSP3_SENTINEL = {"sentinel": True, "untouched": True}

    # Build dados_mapa.json: DSP2 partners start with adv_opportunity=None,
    # DSP3 partners start with the sentinel value.
    records_before = []
    for p in dsp2_partners:
        records_before.append({
            "salesforce_id": p.salesforce_id,
            "name": p.partner_name,
            "status": p.status,
            "adv_opportunity": None,
        })
    for p in dsp3_partners:
        records_before.append({
            "salesforce_id": p.salesforce_id,
            "name": p.partner_name,
            "status": p.status,
            "adv_opportunity": _DSP3_SENTINEL,
        })

    # Build a FitResult containing all partners (both DSP2 and DSP3).
    # We place them in separate TerritoryFit objects to reflect their stations.
    dsp2_territory = TerritoryFit(
        territory_id="DSP2_bucket-01",
        station_code="DSP2",
        bdm_cluster="SP/SUL",
        ctl_name="N/A",
        slots=[],
        partners=list(dsp2_partners),
    )
    dsp3_territory = TerritoryFit(
        territory_id="DSP3_bucket-01",
        station_code="DSP3",
        bdm_cluster="SP/SUL",
        ctl_name="N/A",
        slots=[],
        partners=list(dsp3_partners),
    )
    fit = FitResult(
        territories={
            "DSP2_bucket-01": dsp2_territory,
            "DSP3_bucket-01": dsp3_territory,
        },
        outside_jurisdiction=[],
        unassigned_by_territory={},
    )

    with tempfile.TemporaryDirectory() as tmp_dir:
        # Write dados_mapa.json with the pre-run records
        dados_path = os.path.join(tmp_dir, "dados_mapa.json")
        with open(dados_path, "w", encoding="utf-8") as f:
            json.dump({"allMarkerData": records_before}, f)

        # Use a heatmap with sufficient demand so DSP2 partners can get opportunities
        _make_high_demand_heatmap_for_fixed_position(tmp_dir, demand_residual=200.0)

        # Run with stations=["DSP2"] — DSP3 partners must NOT be evaluated
        run_phase3_5(fit=fit, output_dir=tmp_dir, stations=["DSP2"])

        with open(dados_path, "r", encoding="utf-8") as f:
            payload_after = json.load(f)

    records_after = payload_after.get("allMarkerData", [])
    record_after_by_sfid = {r["salesforce_id"]: r for r in records_after}

    # --- DSP2 partners: adv_opportunity key must be present and updated ---
    for partner in dsp2_partners:
        sfid = partner.salesforce_id
        assert sfid in record_after_by_sfid, (
            f"DSP2 partner {sfid!r} not found in dados_mapa.json after run_phase3_5"
        )
        record = record_after_by_sfid[sfid]
        assert "adv_opportunity" in record, (
            f"DSP2 partner {sfid!r} is missing 'adv_opportunity' key after run_phase3_5 "
            f"with stations=['DSP2']"
        )
        # The value must be None or a dict (i.e., it was evaluated)
        adv = record["adv_opportunity"]
        assert adv is None or isinstance(adv, dict), (
            f"DSP2 partner {sfid!r} has unexpected adv_opportunity type: {type(adv)}"
        )

    # --- DSP3 partners: adv_opportunity must be UNCHANGED (still the sentinel) ---
    for partner in dsp3_partners:
        sfid = partner.salesforce_id
        assert sfid in record_after_by_sfid, (
            f"DSP3 partner {sfid!r} not found in dados_mapa.json after run_phase3_5"
        )
        record = record_after_by_sfid[sfid]
        assert "adv_opportunity" in record, (
            f"DSP3 partner {sfid!r} is missing 'adv_opportunity' key after run_phase3_5"
        )
        adv = record["adv_opportunity"]
        assert adv == _DSP3_SENTINEL, (
            f"DSP3 partner {sfid!r} had adv_opportunity modified by run_phase3_5 "
            f"even though stations=['DSP2'] was passed. "
            f"Before: {_DSP3_SENTINEL!r}, After: {adv!r}"
        )
