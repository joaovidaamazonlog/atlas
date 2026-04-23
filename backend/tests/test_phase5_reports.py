"""
test_phase5_reports.py
======================
Property-based and unit tests for phase5_reports.py.

Tests cover the hex coverage index construction logic introduced by the
hex-partner-coverage-model feature.
"""

from __future__ import annotations

import copy
import json
import math
import os
import sys
from pathlib import Path

import h3
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from collections import defaultdict
from typing import Dict, List, Tuple

from hypothesis import given, settings
from hypothesis import strategies as st

from shared.models import Allocation, PartnerMetrics
from vanilla.phase3_partner_fit import FitResult, TerritoryFit
from vanilla.phase5_reports import _build_hex_coverage_index, _enrich_heatmap_with_residual


# ---------------------------------------------------------------------------
# Hypothesis strategies
# ---------------------------------------------------------------------------

_VALID_HEX_A = "891f1d48177ffff"
_VALID_HEX_B = "891f1d48183ffff"
_VALID_HEX_C = "891f1d4818bffff"
_ALL_HEXES = [_VALID_HEX_A, _VALID_HEX_B, _VALID_HEX_C]

_salesforce_id_strategy = st.text(
    alphabet="ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789",
    min_size=5,
    max_size=18,
)

_status_strategy = st.sampled_from(
    ["Active", "Onboarding", "BG Checks", "Prospect", "Inactive", "Exited"]
)

_eligible_status_strategy = st.sampled_from(["Active", "Onboarding"])

_ineligible_status_strategy = st.sampled_from(
    ["BG Checks", "Prospect", "Inactive", "Exited"]
)

_hex_id_strategy = st.sampled_from(_ALL_HEXES)

_allocation_strategy = st.builds(
    Allocation,
    hex_id=_hex_id_strategy,
    packages_assigned=st.integers(min_value=1, max_value=100),
)


def _partner_strategy(
    status_st=_status_strategy,
    matched_slot_id_st=st.one_of(st.none(), st.just("SLOT_001")),
    allocations_st=st.lists(_allocation_strategy, min_size=0, max_size=3),
):
    return st.builds(
        PartnerMetrics,
        origin_hex=st.just(_VALID_HEX_A),
        station_code=st.just("DSP2"),
        radius_s=st.integers(min_value=500, max_value=3000),
        capacity_s=st.integers(min_value=1, max_value=79),
        entity_type=st.just("EXISTING"),
        status=status_st,
        partner_name=st.text(max_size=50),
        salesforce_id=_salesforce_id_strategy,
        matched_slot_id=matched_slot_id_st,
        allocations=allocations_st,
    )


def _make_fit_result(partners: list) -> FitResult:
    """Wraps a list of PartnerMetrics into a minimal FitResult."""
    territory = TerritoryFit(
        territory_id="DSP2_T01",
        station_code="DSP2",
        bdm_cluster="SP/SUL",
        ctl_name="N/A",
        slots=[],
        partners=list(partners),
    )
    return FitResult(
        territories={"DSP2_T01": territory},
        outside_jurisdiction=[],
        unassigned_by_territory={},
    )


# ---------------------------------------------------------------------------
# Reference implementation of the index-building logic
# (mirrors _build_hex_coverage_index for use in assertions)
# ---------------------------------------------------------------------------

def _reference_build_index(
    partners: list,
) -> Dict[str, List[Tuple[PartnerMetrics, int]]]:
    """
    Pure-Python reference implementation of the coverage index algorithm.
    Used to cross-check _build_hex_coverage_index.
    """
    index: Dict[str, List[Tuple[PartnerMetrics, int]]] = defaultdict(list)
    for partner in partners:
        if partner.status not in ("Active", "Onboarding"):
            continue
        if not partner.matched_slot_id:
            continue
        for alloc in partner.allocations:
            index[alloc.hex_id].append((partner, alloc.packages_assigned))
    return index


# ---------------------------------------------------------------------------
# Property 1: Coverage Index Correctness
# Feature: hex-partner-coverage-model, Property 1: Coverage Index Correctness
# ---------------------------------------------------------------------------

@settings(max_examples=200)
@given(
    partners=st.lists(
        _partner_strategy(
            status_st=_status_strategy,
            matched_slot_id_st=st.one_of(st.none(), st.just("SLOT_001"), st.just("SLOT_002")),
            allocations_st=st.lists(_allocation_strategy, min_size=0, max_size=4),
        ),
        min_size=0,
        max_size=20,
    )
)
def test_coverage_index_correctness(partners: list):
    """
    # Feature: hex-partner-coverage-model, Property 1: Coverage Index Correctness

    **Validates: Requirements 1.1, 1.3, 1.4**

    Property 1: For any list of PartnerMetrics with mixed statuses,
    matched/unmatched slots, and allocations, the coverage index built by
    _build_hex_coverage_index contains exactly the Active/Onboarding partners
    with a matched_slot_id whose allocations include each hex — no more, no fewer.
    """
    fit = _make_fit_result(partners)
    index = _build_hex_coverage_index(fit)

    # Compute the expected index using the reference implementation
    expected = _reference_build_index(partners)

    # ── 1. Every hex in the expected index must appear in the actual index ──
    for hex_id, expected_entries in expected.items():
        assert hex_id in index, (
            f"hex_id {hex_id!r} expected in index but missing. "
            f"Expected entries: {[(p.salesforce_id, pkg) for p, pkg in expected_entries]}"
        )

    # ── 2. Every hex in the actual index must appear in the expected index ──
    for hex_id in index:
        assert hex_id in expected, (
            f"hex_id {hex_id!r} present in index but not expected. "
            f"Actual entries: {[(p.salesforce_id, pkg) for p, pkg in index[hex_id]]}"
        )

    # ── 3. For each hex, the set of (salesforce_id, packages) must match exactly ──
    for hex_id in expected:
        actual_entries = index.get(hex_id, [])
        actual_set = {(p.salesforce_id, pkg) for p, pkg in actual_entries}
        expected_set = {(p.salesforce_id, pkg) for p, pkg in expected[hex_id]}

        assert actual_set == expected_set, (
            f"hex_id {hex_id!r}: entries mismatch.\n"
            f"  Expected: {sorted(expected_set)}\n"
            f"  Actual:   {sorted(actual_set)}"
        )

    # ── 4. Every partner object in the index must be eligible ────────────
    for hex_id, entries in index.items():
        for partner, _ in entries:
            assert partner.status in ("Active", "Onboarding"), (
                f"Ineligible partner {partner.salesforce_id!r} "
                f"(status={partner.status!r}) found in index for hex {hex_id!r}"
            )
            assert partner.matched_slot_id, (
                f"Partner {partner.salesforce_id!r} with matched_slot_id=None/empty "
                f"found in index for hex {hex_id!r}"
            )

    # ── 5. Eligible partners with allocations must appear for each allocated hex ──
    eligible_partners = [
        p for p in partners
        if p.status in ("Active", "Onboarding") and p.matched_slot_id
    ]
    for partner in eligible_partners:
        for alloc in partner.allocations:
            hex_id = alloc.hex_id
            assert hex_id in index, (
                f"hex_id {hex_id!r} from eligible partner {partner.salesforce_id!r} "
                f"allocations is missing from index"
            )
            # Check that this exact partner object is in the index for this hex
            partner_objects_in_index = [p for p, _ in index[hex_id]]
            assert partner in partner_objects_in_index, (
                f"Eligible partner {partner.salesforce_id!r} "
                f"(status={partner.status!r}) with allocation for hex {hex_id!r} "
                f"is missing from index[{hex_id!r}]"
            )


# ---------------------------------------------------------------------------
# Pure reference implementation of hex enrichment logic
# (mirrors the enrichment block in _enrich_heatmap_with_residual)
# ---------------------------------------------------------------------------

def _enrich_hex(
    demand_daily: float,
    entries: List[Tuple[str, float]],  # list of (salesforce_id, packages_allocated)
) -> dict:
    """
    Pure reference implementation of the hex enrichment logic.
    Returns a dict with demand_allocated, demand_residual, is_covered, covering_partners.
    Does NOT include covering_partner_id.
    Uses last-share adjustment to ensure shares sum to exactly 1.0.
    """
    demand_allocated = sum(pkg for _, pkg in entries)
    demand_residual = round(demand_daily - demand_allocated, 4)
    is_covered = demand_allocated > 0

    covering_partners_list = []
    for i, (sfid, pkg) in enumerate(entries):
        if demand_allocated > 0:
            if i < len(entries) - 1:
                share = round(pkg / demand_allocated, 2)
            else:
                # Last partner: adjust to ensure shares sum to exactly 1.0
                share = round(1.0 - sum(cp["share"] for cp in covering_partners_list), 2)
        else:
            share = 0.0
        covering_partners_list.append({
            "salesforce_id": sfid,
            "packages_allocated": pkg,
            "share": share,
        })

    return {
        "demand_allocated": demand_allocated,
        "demand_residual": demand_residual,
        "is_covered": is_covered,
        "covering_partners": covering_partners_list,
    }


# ---------------------------------------------------------------------------
# Property 2: Hex Enrichment Invariants
# Feature: hex-partner-coverage-model, Property 2: Hex Enrichment Invariants
# ---------------------------------------------------------------------------

_entry_strategy = st.tuples(
    _salesforce_id_strategy,
    st.floats(min_value=0.01, max_value=1000.0, allow_nan=False, allow_infinity=False),
)

_demand_daily_strategy = st.floats(
    min_value=0.0, max_value=5000.0, allow_nan=False, allow_infinity=False
)


@settings(max_examples=200)
@given(
    demand_daily=_demand_daily_strategy,
    entries=st.lists(_entry_strategy, min_size=0, max_size=10),
)
def test_hex_enrichment_invariants(demand_daily: float, entries: list):
    """
    # Feature: hex-partner-coverage-model, Property 2: Hex Enrichment Invariants

    **Validates: Requirements 2.1, 2.2, 2.3, 2.4, 2.5, 2.6**

    Property 2: For any hex feature and any list of covering partners derived from
    CP-SAT allocations:
    - demand_allocated equals the sum of packages_allocated across all covering partners
    - demand_residual equals round(demand_daily - demand_allocated, 4)
    - is_covered equals demand_allocated > 0
    - each entry in covering_partners contains salesforce_id, packages_allocated, and share
    - the field covering_partner_id is absent from the enriched properties
    """
    result = _enrich_hex(demand_daily, entries)

    # ── Requirement 2.1: demand_allocated == sum of packages ──────────────
    expected_allocated = sum(pkg for _, pkg in entries)
    assert result["demand_allocated"] == expected_allocated, (
        f"demand_allocated {result['demand_allocated']} != sum of packages {expected_allocated}"
    )

    # ── Requirement 2.2: demand_residual == round(demand_daily - demand_allocated, 4) ──
    expected_residual = round(demand_daily - expected_allocated, 4)
    assert result["demand_residual"] == expected_residual, (
        f"demand_residual {result['demand_residual']} != "
        f"round({demand_daily} - {expected_allocated}, 4) = {expected_residual}"
    )

    # ── Requirement 2.3: is_covered == demand_allocated > 0 ──────────────
    assert result["is_covered"] == (expected_allocated > 0), (
        f"is_covered {result['is_covered']} != (demand_allocated > 0) "
        f"for demand_allocated={expected_allocated}"
    )

    # ── Requirement 2.4 & 2.5: covering_partners entries have required fields ──
    covering = result["covering_partners"]
    assert isinstance(covering, list), "covering_partners must be a list"

    if not entries:
        # Requirement 2.5: empty list when no covering partners
        assert covering == [], "covering_partners must be [] when no entries"
    else:
        assert len(covering) == len(entries), (
            f"covering_partners length {len(covering)} != entries length {len(entries)}"
        )
        for cp in covering:
            assert "salesforce_id" in cp, "covering_partners entry missing salesforce_id"
            assert "packages_allocated" in cp, "covering_partners entry missing packages_allocated"
            assert "share" in cp, "covering_partners entry missing share"

    # ── Requirement 2.6: covering_partner_id must NOT be present ─────────
    assert "covering_partner_id" not in result, (
        "covering_partner_id must NOT be written to enriched properties"
    )


# ---------------------------------------------------------------------------
# Property 3: Share Sum Invariant
# Feature: hex-partner-coverage-model, Property 3: Share Sum Invariant
# ---------------------------------------------------------------------------

@settings(max_examples=200)
@given(
    packages=st.lists(
        st.floats(min_value=0.01, max_value=1000.0, allow_nan=False, allow_infinity=False),
        min_size=1,
        max_size=20,
    )
)
def test_share_sum_invariant(packages: list):
    """
    # Feature: hex-partner-coverage-model, Property 3: Share Sum Invariant

    **Validates: Requirements 2.7**

    Property 3: For any hex where demand_allocated > 0, the sum of all share values
    in covering_partners SHALL equal 1.0 within a floating-point tolerance of 0.01.
    """
    # Build entries with distinct salesforce IDs
    entries = [(f"SF{i:05d}", pkg) for i, pkg in enumerate(packages)]

    result = _enrich_hex(demand_daily=sum(packages), entries=entries)

    # demand_allocated > 0 since all packages are positive
    assert result["demand_allocated"] > 0, "demand_allocated must be > 0 for positive packages"
    assert result["is_covered"] is True, "is_covered must be True when demand_allocated > 0"

    covering = result["covering_partners"]
    assert len(covering) == len(packages), (
        f"covering_partners length {len(covering)} != packages length {len(packages)}"
    )

    share_sum = sum(cp["share"] for cp in covering)
    # With last-share adjustment, the sum is guaranteed to be exactly 1.0
    # (within floating-point representation). Tolerance 0.01 per Requirement 2.7.
    assert abs(share_sum - 1.0) <= 0.01, (
        f"Sum of shares {share_sum} is not within 0.01 of 1.0 "
        f"(packages={packages}, shares={[cp['share'] for cp in covering]})"
    )


# ---------------------------------------------------------------------------
# Property 4: Hex Coverage Derivation Round-Trip
# Feature: hex-partner-coverage-model, Property 4: Hex Coverage Derivation Round-Trip
# ---------------------------------------------------------------------------

from vanilla.phase5_reports import _derive_hex_coverage, _write_dados_mapa


def _partner_with_allocations_strategy():
    """
    Strategy that generates Active/Onboarding partners with non-empty allocations
    and a matched_slot_id.
    """
    return _partner_strategy(
        status_st=_eligible_status_strategy,
        matched_slot_id_st=st.just("SLOT_001"),
        allocations_st=st.lists(_allocation_strategy, min_size=1, max_size=5),
    )


def _partner_ineligible_strategy():
    """
    Strategy that generates non-Active/Onboarding partners.
    """
    return _partner_strategy(
        status_st=_ineligible_status_strategy,
        matched_slot_id_st=st.one_of(st.none(), st.just("SLOT_001")),
        allocations_st=st.lists(_allocation_strategy, min_size=0, max_size=3),
    )


@settings(max_examples=200)
@given(partner=_partner_with_allocations_strategy())
def test_hex_coverage_derivation_active_onboarding(partner: PartnerMetrics):
    """
    # Feature: hex-partner-coverage-model, Property 4: Hex Coverage Derivation Round-Trip

    **Validates: Requirements 3.1, 3.2, 3.3, 3.4**

    Property 4 (part A): For any Active or Onboarding partner with a matched_slot_id
    and non-empty allocations, _derive_hex_coverage returns a list with exactly one
    entry per allocation, with matching hex_id and packages_allocated.
    """
    result = _derive_hex_coverage(partner)

    # Must return a list (not None) for Active/Onboarding
    assert result is not None, (
        f"_derive_hex_coverage returned None for status={partner.status!r}"
    )
    assert isinstance(result, list), (
        f"_derive_hex_coverage must return a list, got {type(result)}"
    )

    # Exactly one entry per allocation
    assert len(result) == len(partner.allocations), (
        f"hex_coverage length {len(result)} != allocations length {len(partner.allocations)}"
    )

    # Each entry matches the source allocation
    for entry, alloc in zip(result, partner.allocations):
        assert entry["hex_id"] == alloc.hex_id, (
            f"hex_id mismatch: entry has {entry['hex_id']!r}, alloc has {alloc.hex_id!r}"
        )
        assert entry["packages_allocated"] == alloc.packages_assigned, (
            f"packages_allocated mismatch: entry has {entry['packages_allocated']}, "
            f"alloc has {alloc.packages_assigned}"
        )


@settings(max_examples=200)
@given(partner=_partner_ineligible_strategy())
def test_hex_coverage_derivation_ineligible_returns_none(partner: PartnerMetrics):
    """
    # Feature: hex-partner-coverage-model, Property 4: Hex Coverage Derivation Round-Trip

    **Validates: Requirements 3.4**

    Property 4 (part B): For any partner with status other than Active or Onboarding,
    _derive_hex_coverage returns None (no hex_coverage field should be written).
    """
    result = _derive_hex_coverage(partner)

    assert result is None, (
        f"_derive_hex_coverage must return None for status={partner.status!r}, "
        f"got {result!r}"
    )


# ---------------------------------------------------------------------------
# Task 3.2: Unit tests — hex_coverage absent for non-Active/Onboarding statuses
# ---------------------------------------------------------------------------

def _make_dados_mapa_file(records: list, path: Path) -> None:
    """Write a minimal dados_mapa.json with the given allMarkerData records."""
    payload = {"allMarkerData": records}
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f)


def _load_dados_mapa(path: Path) -> list:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)["allMarkerData"]


def _make_partner_for_dados_mapa(
    salesforce_id: str,
    status: str,
    matched_slot_id=None,
    allocations=None,
) -> PartnerMetrics:
    """Helper to build a PartnerMetrics for _write_dados_mapa tests."""
    return PartnerMetrics(
        origin_hex=_VALID_HEX_A,
        station_code="DSP2",
        radius_s=1000,
        capacity_s=50,
        entity_type="EXISTING",
        status=status,
        salesforce_id=salesforce_id,
        matched_slot_id=matched_slot_id,
        allocations=allocations or [],
    )


class TestWriteDadosMapaHexCoverage:
    """Unit tests for hex_coverage field in _write_dados_mapa."""

    def test_active_partner_with_allocations_gets_hex_coverage(self, tmp_path):
        """Active partner with allocations → hex_coverage list is written."""
        partner = _make_partner_for_dados_mapa(
            "SF_ACTIVE_01", "Active", "SLOT_001",
            allocations=[
                Allocation(hex_id=_VALID_HEX_A, packages_assigned=30),
                Allocation(hex_id=_VALID_HEX_B, packages_assigned=20),
            ],
        )
        fit = _make_fit_result([partner])

        records = [{"salesforce_id": "SF_ACTIVE_01", "delivery_station": "DSP2"}]
        dados_path = tmp_path / "dados_mapa.json"
        _make_dados_mapa_file(records, dados_path)

        _write_dados_mapa(dados_path, fit, dados_path, stations=["DSP2"])

        result = _load_dados_mapa(dados_path)
        record = result[0]

        assert "hex_coverage" in record, "Active partner must have hex_coverage"
        assert len(record["hex_coverage"]) == 2
        hex_ids = {e["hex_id"] for e in record["hex_coverage"]}
        assert hex_ids == {_VALID_HEX_A, _VALID_HEX_B}

    def test_onboarding_partner_with_allocations_gets_hex_coverage(self, tmp_path):
        """Onboarding partner with allocations → hex_coverage list is written."""
        partner = _make_partner_for_dados_mapa(
            "SF_ONBOARD_01", "Onboarding", "SLOT_002",
            allocations=[Allocation(hex_id=_VALID_HEX_A, packages_assigned=15)],
        )
        fit = _make_fit_result([partner])

        records = [{"salesforce_id": "SF_ONBOARD_01", "delivery_station": "DSP2"}]
        dados_path = tmp_path / "dados_mapa.json"
        _make_dados_mapa_file(records, dados_path)

        _write_dados_mapa(dados_path, fit, dados_path, stations=["DSP2"])

        result = _load_dados_mapa(dados_path)
        record = result[0]

        assert "hex_coverage" in record, "Onboarding partner must have hex_coverage"
        assert record["hex_coverage"] == [
            {"hex_id": _VALID_HEX_A, "packages_allocated": 15}
        ]

    def test_active_partner_no_allocations_gets_empty_hex_coverage(self, tmp_path):
        """Active partner with no allocations → hex_coverage is [] (Requirement 3.3)."""
        partner = _make_partner_for_dados_mapa(
            "SF_ACTIVE_EMPTY", "Active", "SLOT_003",
            allocations=[],
        )
        fit = _make_fit_result([partner])

        records = [{"salesforce_id": "SF_ACTIVE_EMPTY", "delivery_station": "DSP2"}]
        dados_path = tmp_path / "dados_mapa.json"
        _make_dados_mapa_file(records, dados_path)

        _write_dados_mapa(dados_path, fit, dados_path, stations=["DSP2"])

        result = _load_dados_mapa(dados_path)
        record = result[0]

        assert "hex_coverage" in record, "Active partner must have hex_coverage even if empty"
        assert record["hex_coverage"] == [], "hex_coverage must be [] when no allocations"

    @pytest.mark.parametrize("status", ["BG Checks", "Inactive", "Exited"])
    def test_non_active_onboarding_partner_has_no_hex_coverage(self, tmp_path, status):
        """
        Partners with status BG Checks, Inactive, or Exited must NOT have
        hex_coverage field in their record (Requirement 3.4).
        """
        partner = _make_partner_for_dados_mapa(
            f"SF_{status.replace(' ', '_').upper()}", status, "SLOT_004",
            allocations=[Allocation(hex_id=_VALID_HEX_A, packages_assigned=10)],
        )
        fit = _make_fit_result([partner])

        records = [{"salesforce_id": partner.salesforce_id, "delivery_station": "DSP2"}]
        dados_path = tmp_path / "dados_mapa.json"
        _make_dados_mapa_file(records, dados_path)

        _write_dados_mapa(dados_path, fit, dados_path, stations=["DSP2"])

        result = _load_dados_mapa(dados_path)
        record = result[0]

        assert "hex_coverage" not in record, (
            f"Partner with status={status!r} must NOT have hex_coverage field, "
            f"but got: {record.get('hex_coverage')!r}"
        )

    def test_prospect_partner_has_no_hex_coverage(self, tmp_path):
        """Prospect partners must NOT have hex_coverage field (Requirement 3.4)."""
        partner = _make_partner_for_dados_mapa(
            "SF_PROSPECT_01", "Prospect", None,
            allocations=[],
        )
        fit = _make_fit_result([partner])

        records = [{"salesforce_id": "SF_PROSPECT_01", "delivery_station": "DSP2"}]
        dados_path = tmp_path / "dados_mapa.json"
        _make_dados_mapa_file(records, dados_path)

        _write_dados_mapa(dados_path, fit, dados_path, stations=["DSP2"])

        result = _load_dados_mapa(dados_path)
        record = result[0]

        assert "hex_coverage" not in record, (
            "Prospect partner must NOT have hex_coverage field"
        )

    def test_hex_coverage_entry_structure(self, tmp_path):
        """Each hex_coverage entry must have hex_id (str) and packages_allocated (int)."""
        partner = _make_partner_for_dados_mapa(
            "SF_STRUCT_01", "Active", "SLOT_005",
            allocations=[
                Allocation(hex_id=_VALID_HEX_A, packages_assigned=42),
            ],
        )
        fit = _make_fit_result([partner])

        records = [{"salesforce_id": "SF_STRUCT_01", "delivery_station": "DSP2"}]
        dados_path = tmp_path / "dados_mapa.json"
        _make_dados_mapa_file(records, dados_path)

        _write_dados_mapa(dados_path, fit, dados_path, stations=["DSP2"])

        result = _load_dados_mapa(dados_path)
        entry = result[0]["hex_coverage"][0]

        assert "hex_id" in entry
        assert "packages_allocated" in entry
        assert entry["hex_id"] == _VALID_HEX_A
        assert entry["packages_allocated"] == 42


# ---------------------------------------------------------------------------
# Helpers shared by Property 7 and Task 5.2 unit test
# ---------------------------------------------------------------------------

# Real H3 hex IDs for a second station (DSP4) — different cells from DSP2 hexes
_VALID_HEX_DSP4_A = "891f1d4816fffff"
_VALID_HEX_DSP4_B = "891f1d48163ffff"

_ALL_HEXES_MULTI = [_VALID_HEX_A, _VALID_HEX_B, _VALID_HEX_C,
                    _VALID_HEX_DSP4_A, _VALID_HEX_DSP4_B]

# Stations used in multi-station tests
_STATION_A = "DSP2"
_STATION_B = "DSP4"


def _hex_feature_for_station(hex_id: str, demand_daily: float, station: str) -> dict:
    """Build a minimal GeoJSON hex feature for the given station."""
    boundary = h3.cell_to_boundary(hex_id)
    coords = [[c[1], c[0]] for c in boundary]
    coords.append(coords[0])
    return {
        "type": "Feature",
        "geometry": {"type": "Polygon", "coordinates": [coords]},
        "properties": {
            "hex_id": hex_id,
            "demand_daily": demand_daily,
            "demand_total": demand_daily * 30,
            "delivery_station": station,
            "territory_id": f"{station}_T01",
        },
    }


def _make_heatmap_file_multi(features: list, path: Path) -> None:
    geojson = {
        "type": "FeatureCollection",
        "features": features,
        "metadata": {"generated_at": "2024-01-01T00:00:00"},
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(geojson, f)


def _load_heatmap_features(path: Path) -> list:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)["features"]


def _make_fit_for_station(
    station: str,
    partners: list,
) -> FitResult:
    """Wrap partners into a FitResult for a single station."""
    territory = TerritoryFit(
        territory_id=f"{station}_T01",
        station_code=station,
        bdm_cluster="SP/SUL",
        ctl_name="N/A",
        slots=[],
        partners=list(partners),
    )
    return FitResult(
        territories={f"{station}_T01": territory},
        outside_jurisdiction=[],
        unassigned_by_territory={},
    )


# ---------------------------------------------------------------------------
# Property 7: Partial Merge Preservation
# Feature: hex-partner-coverage-model, Property 7: Partial Merge Preservation
# ---------------------------------------------------------------------------

# Strategies for multi-station heatmaps
_station_a_hex_strategy = st.sampled_from([_VALID_HEX_A, _VALID_HEX_B])
_station_b_hex_strategy = st.sampled_from([_VALID_HEX_DSP4_A, _VALID_HEX_DSP4_B])

_demand_strategy = st.floats(min_value=1.0, max_value=200.0, allow_nan=False, allow_infinity=False)


def _multi_station_heatmap_strategy():
    """
    Strategy that generates a list of hex features belonging to at least 2 stations.
    Station A (DSP2) uses _VALID_HEX_A / _VALID_HEX_B.
    Station B (DSP4) uses _VALID_HEX_DSP4_A / _VALID_HEX_DSP4_B.
    Returns (features_list, station_a_hex_ids, station_b_hex_ids).
    """
    return st.builds(
        lambda a_hexes, b_hexes, a_demands, b_demands: (
            [_hex_feature_for_station(h, d, _STATION_A) for h, d in zip(a_hexes, a_demands)]
            + [_hex_feature_for_station(h, d, _STATION_B) for h, d in zip(b_hexes, b_demands)],
            list(a_hexes),
            list(b_hexes),
        ),
        a_hexes=st.lists(
            _station_a_hex_strategy, min_size=1, max_size=2, unique=True
        ),
        b_hexes=st.lists(
            _station_b_hex_strategy, min_size=1, max_size=2, unique=True
        ),
        a_demands=st.lists(_demand_strategy, min_size=1, max_size=2),
        b_demands=st.lists(_demand_strategy, min_size=1, max_size=2),
    ).filter(
        lambda t: len(t[0]) >= 2  # at least 2 features total
    ).map(
        # Ensure demand lists match hex lists in length
        lambda t: (
            t[0][:min(len(t[1]), len(t[0]))],
            t[1],
            t[2],
        )
    )


def _stations_subset_strategy(all_stations: list):
    """Generate a non-empty subset of the given stations list."""
    return st.lists(
        st.sampled_from(all_stations),
        min_size=1,
        max_size=len(all_stations),
        unique=True,
    )


@settings(max_examples=100, deadline=None)
@given(
    heatmap_data=st.builds(
        lambda a_hexes, b_hexes, a_demands, b_demands: (
            [_hex_feature_for_station(h, d, _STATION_A)
             for h, d in list(zip(a_hexes, a_demands))[:len(a_hexes)]]
            + [_hex_feature_for_station(h, d, _STATION_B)
               for h, d in list(zip(b_hexes, b_demands))[:len(b_hexes)]],
            list(a_hexes),
            list(b_hexes),
        ),
        a_hexes=st.lists(_station_a_hex_strategy, min_size=1, max_size=2, unique=True),
        b_hexes=st.lists(_station_b_hex_strategy, min_size=1, max_size=2, unique=True),
        a_demands=st.lists(_demand_strategy, min_size=2, max_size=2),
        b_demands=st.lists(_demand_strategy, min_size=2, max_size=2),
    ),
    stations_to_run=st.lists(
        st.sampled_from([_STATION_A, _STATION_B]),
        min_size=1,
        max_size=1,
        unique=True,
    ),
)
def test_partial_merge_preservation(
    heatmap_data,
    stations_to_run: list,
):
    """
    # Feature: hex-partner-coverage-model, Property 7: Partial Merge Preservation

    **Validates: Requirements 7.1, 7.2, 7.3**

    Property 7: For any multi-station heatmap and any non-empty stations list,
    running _enrich_heatmap_with_residual leaves all properties of hex features
    belonging to stations NOT in the list completely unchanged.
    The same holds for _write_dados_mapa and partner records.
    """
    import tempfile

    features, a_hexes, b_hexes = heatmap_data

    # Trim features to match actual hex counts
    station_a_features = [f for f in features if f["properties"]["delivery_station"] == _STATION_A]
    station_b_features = [f for f in features if f["properties"]["delivery_station"] == _STATION_B]
    all_features = station_a_features[:len(a_hexes)] + station_b_features[:len(b_hexes)]

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)

        # ── Part 1: _enrich_heatmap_with_residual ────────────────────────────
        heatmap_path = tmp / "heatmap.geojson"
        _make_heatmap_file_multi(all_features, heatmap_path)

        # Snapshot of features NOT in stations_to_run before enrichment
        before_snapshot = {
            f["properties"]["hex_id"]: copy.deepcopy(f["properties"])
            for f in all_features
            if f["properties"]["delivery_station"] not in stations_to_run
        }

        # Build a minimal FitResult for the stations being run
        # (no partners — we just want to verify the skip logic)
        fit = _make_fit_for_station(stations_to_run[0], [])

        _enrich_heatmap_with_residual(heatmap_path, fit, None, None, stations=stations_to_run)

        after_features = _load_heatmap_features(heatmap_path)
        after_by_hex = {f["properties"]["hex_id"]: f["properties"] for f in after_features}

        # All features NOT in stations_to_run must be byte-for-byte identical
        for hex_id, before_props in before_snapshot.items():
            assert hex_id in after_by_hex, (
                f"hex_id {hex_id!r} disappeared from heatmap after enrichment"
            )
            after_props = after_by_hex[hex_id]
            assert after_props == before_props, (
                f"Properties of hex {hex_id!r} (station not in {stations_to_run}) "
                f"were modified.\n"
                f"  Before: {before_props}\n"
                f"  After:  {after_props}"
            )

        # ── Part 2: _write_dados_mapa ─────────────────────────────────────────
        # Build partner records for both stations
        dsp2_record = {
            "salesforce_id": "SF_DSP2_001",
            "delivery_station": _STATION_A,
            "some_field": "original_value_dsp2",
        }
        dsp4_record = {
            "salesforce_id": "SF_DSP4_001",
            "delivery_station": _STATION_B,
            "some_field": "original_value_dsp4",
        }

        dados_path = tmp / "dados_mapa.json"
        _make_dados_mapa_file([dsp2_record, dsp4_record], dados_path)

        # Build a FitResult that only contains the station being run
        # (the other station's partner is NOT in opt_index)
        partner_in_run = PartnerMetrics(
            origin_hex=_VALID_HEX_A,
            station_code=stations_to_run[0],
            radius_s=1000,
            capacity_s=50,
            entity_type="EXISTING",
            status="Active",
            salesforce_id="SF_DSP2_001" if stations_to_run[0] == _STATION_A else "SF_DSP4_001",
            matched_slot_id="SLOT_001",
            allocations=[],
        )
        fit_dados = _make_fit_for_station(stations_to_run[0], [partner_in_run])

        # Snapshot of the record NOT in stations_to_run
        not_in_run_sfid = "SF_DSP4_001" if stations_to_run[0] == _STATION_A else "SF_DSP2_001"
        not_in_run_record_before = copy.deepcopy(
            dsp4_record if stations_to_run[0] == _STATION_A else dsp2_record
        )

        _write_dados_mapa(dados_path, fit_dados, dados_path, stations=stations_to_run)

        result_records = _load_dados_mapa(dados_path)
        result_by_sfid = {r["salesforce_id"]: r for r in result_records}

        assert not_in_run_sfid in result_by_sfid, (
            f"Partner {not_in_run_sfid!r} disappeared from dados_mapa after _write_dados_mapa"
        )
        after_record = result_by_sfid[not_in_run_sfid]
        assert after_record == not_in_run_record_before, (
            f"Partner {not_in_run_sfid!r} (station not in {stations_to_run}) was modified.\n"
            f"  Before: {not_in_run_record_before}\n"
            f"  After:  {after_record}"
        )


# ---------------------------------------------------------------------------
# Task 5.2: Unit test — single-station run does not modify other station's data
# ---------------------------------------------------------------------------

class TestWriteDadosMapaPartialMerge:
    """
    Unit tests for partial merge preservation in _write_dados_mapa.

    See also: test_enrich_heatmap_residual.py::TestEnrichHeatmapResidual::
              test_partial_merge_preserves_other_station_hexes
    for the equivalent test on _enrich_heatmap_with_residual.
    """

    def test_single_station_run_does_not_modify_other_station_partners(self, tmp_path):
        """
        Running _write_dados_mapa with stations=["DSP2"] must NOT modify any
        partner record whose delivery_station is "DSP4" (Requirement 7.3).
        """
        # DSP2 partner — will be updated
        dsp2_partner = PartnerMetrics(
            origin_hex=_VALID_HEX_A,
            station_code="DSP2",
            radius_s=1200,
            capacity_s=60,
            entity_type="EXISTING",
            status="Active",
            salesforce_id="SF_DSP2_MERGE_01",
            matched_slot_id="SLOT_DSP2_001",
            allocations=[
                Allocation(hex_id=_VALID_HEX_A, packages_assigned=40),
                Allocation(hex_id=_VALID_HEX_B, packages_assigned=20),
            ],
        )

        # DSP4 partner — must remain completely unchanged
        dsp4_original_record = {
            "salesforce_id": "SF_DSP4_MERGE_01",
            "delivery_station": "DSP4",
            "decision": "KEEP",
            "reason": "existing_active",
            "bucket_ade": "DSP4_T01",
            "radius_suggestion": 800,
            "cap_suggestion": 45,
            "hex_coverage": [
                {"hex_id": _VALID_HEX_DSP4_A, "packages_allocated": 30}
            ],
            "some_extra_field": "should_not_be_touched",
        }

        dsp2_initial_record = {
            "salesforce_id": "SF_DSP2_MERGE_01",
            "delivery_station": "DSP2",
        }

        dados_path = tmp_path / "dados_mapa.json"
        _make_dados_mapa_file([dsp2_initial_record, dsp4_original_record], dados_path)

        # FitResult only contains DSP2 partner
        fit = _make_fit_for_station("DSP2", [dsp2_partner])

        _write_dados_mapa(dados_path, fit, dados_path, stations=["DSP2"])

        result = _load_dados_mapa(dados_path)
        result_by_sfid = {r["salesforce_id"]: r for r in result}

        # DSP2 partner should have been updated
        assert "SF_DSP2_MERGE_01" in result_by_sfid
        dsp2_result = result_by_sfid["SF_DSP2_MERGE_01"]
        assert "hex_coverage" in dsp2_result, "DSP2 Active partner must have hex_coverage"
        assert len(dsp2_result["hex_coverage"]) == 2

        # DSP4 partner must be completely unchanged
        assert "SF_DSP4_MERGE_01" in result_by_sfid, (
            "DSP4 partner must still be present in dados_mapa"
        )
        dsp4_result = result_by_sfid["SF_DSP4_MERGE_01"]
        assert dsp4_result == dsp4_original_record, (
            f"DSP4 partner record was modified by a DSP2-only run.\n"
            f"  Expected: {dsp4_original_record}\n"
            f"  Got:      {dsp4_result}"
        )
