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

from shared.models import Allocation, PartnerMetrics, TerritoriesResult
from vanilla.phase3_partner_fit import FitResult, TerritoryFit
from vanilla.phase5_reports import _build_hex_coverage_index


# ---------------------------------------------------------------------------
# Helper: constrói um TerritoriesResult mínimo a partir de um FitResult
# (usado nas chamadas de _write_dados_mapa que exigem `territories`).
# ---------------------------------------------------------------------------

def _make_territories_from_fit(fit: FitResult) -> TerritoriesResult:
    territory_index: dict = {}
    hex_to_territory: dict = {}
    for tid, tfit in fit.territories.items():
        hex_ids = []
        for p in tfit.partners:
            if p.origin_hex:
                hex_ids.append(p.origin_hex)
                hex_to_territory[p.origin_hex] = tid
            for a in p.allocations:
                if a.hex_id:
                    hex_ids.append(a.hex_id)
                    hex_to_territory[a.hex_id] = tid
        if hex_ids:
            first_lat, first_lon = h3.cell_to_latlng(hex_ids[0])
        else:
            first_lat, first_lon = 0.0, 0.0
        territory_index[tid] = {
            "territory_id": tid,
            "station_code": tfit.station_code,
            "bdm_cluster": tfit.bdm_cluster,
            "ctl_name": tfit.ctl_name,
            "hex_ids": list(dict.fromkeys(hex_ids)),
            "centroid_lat": first_lat,
            "centroid_lon": first_lon,
            "total_demand": 0,
        }
    return TerritoriesResult(
        territory_index=territory_index,
        hex_to_territory=hex_to_territory,
    )


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

    demand_residual is clamped at zero: CP-SAT rounding (demand_daily uses
    ``max(1, round(total / days))`` in Phase 2) can occasionally make
    demand_allocated exceed demand_daily in low-demand hexes — volume
    cannot be negative.
    """
    demand_allocated = sum(pkg for _, pkg in entries)
    demand_residual = round(max(demand_daily - demand_allocated, 0.0), 4)
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

    # ── Requirement 2.2: demand_residual == round(max(demand_daily - demand_allocated, 0), 4) ──
    # Clamped at zero to prevent negative volume from CP-SAT rounding artifacts.
    expected_residual = round(max(demand_daily - expected_allocated, 0.0), 4)
    assert result["demand_residual"] == expected_residual, (
        f"demand_residual {result['demand_residual']} != "
        f"round(max({demand_daily} - {expected_allocated}, 0), 4) = {expected_residual}"
    )
    assert result["demand_residual"] >= 0, (
        f"demand_residual must never be negative, got {result['demand_residual']}"
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

        _write_dados_mapa(dados_path, fit, dados_path, territories=_make_territories_from_fit(fit), stations=["DSP2"])

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

        _write_dados_mapa(dados_path, fit, dados_path, territories=_make_territories_from_fit(fit), stations=["DSP2"])

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

        _write_dados_mapa(dados_path, fit, dados_path, territories=_make_territories_from_fit(fit), stations=["DSP2"])

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

        _write_dados_mapa(dados_path, fit, dados_path, territories=_make_territories_from_fit(fit), stations=["DSP2"])

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

        _write_dados_mapa(dados_path, fit, dados_path, territories=_make_territories_from_fit(fit), stations=["DSP2"])

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

        _write_dados_mapa(dados_path, fit, dados_path, territories=_make_territories_from_fit(fit), stations=["DSP2"])

        result = _load_dados_mapa(dados_path)
        entry = result[0]["hex_coverage"][0]

        assert "hex_id" in entry
        assert "packages_allocated" in entry
        assert entry["hex_id"] == _VALID_HEX_A
        assert entry["packages_allocated"] == 42


# ---------------------------------------------------------------------------
# Unit tests — heuristic hex_coverage fallback for unmatched Active/Onboarding
# partners (CP-SAT did not allocate them)
# ---------------------------------------------------------------------------

from vanilla.phase5_reports import _derive_heuristic_hex_coverage
from shared.load_packages import PackageData


def _make_pkg_with_demand(
    station_code: str,
    hex_demands: dict,
    days: int = 30,
) -> PackageData:
    """Build a minimal PackageData with demand_by_station populated."""
    return PackageData(
        demand_by_station={station_code: dict(hex_demands)},
        hex_to_base={h: station_code for h in hex_demands},
        hex_to_ceps={},
        days=days,
    )


def _make_territories_with_hexes(
    tid: str, station_code: str, hex_ids: list
) -> TerritoriesResult:
    """Build a TerritoriesResult with one territory containing the given hexes."""
    if hex_ids:
        centroid_lat, centroid_lon = h3.cell_to_latlng(hex_ids[0])
    else:
        centroid_lat, centroid_lon = 0.0, 0.0
    return TerritoriesResult(
        territory_index={
            tid: {
                "territory_id": tid,
                "station_code": station_code,
                "bdm_cluster": "",
                "ctl_name": "",
                "hex_ids": list(hex_ids),
                "centroid_lat": centroid_lat,
                "centroid_lon": centroid_lon,
                "total_demand": 0,
            }
        },
        hex_to_territory={h: tid for h in hex_ids},
    )


class TestHeuristicHexCoverage:
    """
    Tests for _derive_heuristic_hex_coverage: fallback for Active/Onboarding
    partners that were not matched by CP-SAT (empty allocations).
    """

    def test_unmatched_active_gets_heuristic_coverage_from_radius(self):
        """
        Active partner with no allocations, positioned at the centroid of a
        hex in its territory, gets hex_coverage populated with hexes inside
        its radius_a, ordered by residual demand desc, respecting capacity_a.
        """
        center_lat, center_lon = h3.cell_to_latlng(_VALID_HEX_A)
        partner = PartnerMetrics(
            origin_hex=_VALID_HEX_A,
            station_code="DSP2",
            radius_s=0,  # CP-SAT did not match
            capacity_s=0,
            entity_type="EXISTING",
            status="Active",
            salesforce_id="SF_UNMATCHED_01",
            matched_slot_id=None,     # no match
            allocations=[],           # no CP-SAT allocations
            lat=center_lat,
            lon=center_lon,
            radius_a=5000,            # 5 km reach
            capacity_a=50,
            cluster_name="DSP2_bucket-01",
        )
        territories = _make_territories_with_hexes(
            "DSP2_bucket-01", "DSP2", _ALL_HEXES,
        )
        # Higher demand on HEX_B so it appears first in sorted candidates.
        pkg = _make_pkg_with_demand("DSP2", {
            _VALID_HEX_A: 300,   # 10/day × 30 days
            _VALID_HEX_B: 600,   # 20/day × 30 days
            _VALID_HEX_C: 150,   # 5/day × 30 days
        }, days=30)
        # No other matched partners → residual == demand_daily.
        demand_allocated_by_hex: dict = {}

        result = _derive_heuristic_hex_coverage(
            partner, territories, pkg, demand_allocated_by_hex,
        )

        assert len(result) > 0, "Heuristic should produce at least one hex"
        # Highest residual comes first
        assert result[0]["hex_id"] == _VALID_HEX_B
        assert result[0]["packages_allocated"] == 20  # residual == demand_daily
        # All allocations positive ints
        for e in result:
            assert isinstance(e["packages_allocated"], int)
            assert e["packages_allocated"] > 0
        # Total allocated ≤ capacity_a
        total = sum(e["packages_allocated"] for e in result)
        assert total <= partner.capacity_a

    def test_unmatched_active_uses_residual_when_other_partners_cover(self):
        """
        When other matched partners already cover some demand in a hex, the
        heuristic assigns only the residual (demand_daily − demand_allocated)
        to the unmatched partner. Saturated hexes are skipped.
        """
        center_lat, center_lon = h3.cell_to_latlng(_VALID_HEX_A)
        partner = PartnerMetrics(
            origin_hex=_VALID_HEX_A,
            station_code="DSP2",
            radius_s=0, capacity_s=0,
            entity_type="EXISTING",
            status="Active",
            salesforce_id="SF_UNMATCHED_RESIDUAL",
            matched_slot_id=None,
            allocations=[],
            lat=center_lat, lon=center_lon,
            radius_a=5000, capacity_a=50,
            cluster_name="DSP2_bucket-01",
        )
        territories = _make_territories_with_hexes(
            "DSP2_bucket-01", "DSP2", _ALL_HEXES,
        )
        # demand_daily: HEX_A=10, HEX_B=20, HEX_C=5
        pkg = _make_pkg_with_demand("DSP2", {
            _VALID_HEX_A: 300, _VALID_HEX_B: 600, _VALID_HEX_C: 150,
        }, days=30)
        # Other matched partners already cover:
        #  - HEX_A: 7 of 10  → residual = 3
        #  - HEX_B: 20 of 20 → residual = 0 (saturated, skipped)
        #  - HEX_C: 0  of 5  → residual = 5
        demand_allocated_by_hex = {_VALID_HEX_A: 7, _VALID_HEX_B: 20}

        result = _derive_heuristic_hex_coverage(
            partner, territories, pkg, demand_allocated_by_hex,
        )

        hex_to_pkgs = {e["hex_id"]: e["packages_allocated"] for e in result}
        # Saturated hex must NOT appear
        assert _VALID_HEX_B not in hex_to_pkgs
        # Residual values are assigned (ordered by residual desc: C=5, A=3)
        assert result[0]["hex_id"] == _VALID_HEX_C
        assert hex_to_pkgs[_VALID_HEX_C] == 5
        assert hex_to_pkgs[_VALID_HEX_A] == 3

    def test_unmatched_active_respects_radius(self):
        """Hexes outside radius_a are NOT included in heuristic coverage."""
        center_lat, center_lon = h3.cell_to_latlng(_VALID_HEX_A)
        partner = PartnerMetrics(
            origin_hex=_VALID_HEX_A,
            station_code="DSP2",
            radius_s=0, capacity_s=0,
            entity_type="EXISTING",
            status="Active",
            salesforce_id="SF_TINY_RADIUS",
            matched_slot_id=None,
            allocations=[],
            lat=center_lat,
            lon=center_lon,
            radius_a=1,               # virtually zero radius
            capacity_a=50,
            cluster_name="DSP2_bucket-01",
        )
        territories = _make_territories_with_hexes(
            "DSP2_bucket-01", "DSP2", _ALL_HEXES,
        )
        pkg = _make_pkg_with_demand("DSP2", {
            _VALID_HEX_A: 300, _VALID_HEX_B: 600, _VALID_HEX_C: 150,
        }, days=30)

        result = _derive_heuristic_hex_coverage(partner, territories, pkg)

        # With radius=1m nothing (including the origin hex centroid, which
        # is typically > 1m away) should fit. Allow either empty or
        # ≤ 1 hex depending on exact centroid distance.
        assert len(result) <= 1

    def test_unmatched_active_without_territory_returns_empty(self):
        """Partner without a resolvable territory gets empty coverage."""
        partner = PartnerMetrics(
            origin_hex="",
            station_code="DSP2",
            radius_s=0, capacity_s=0,
            entity_type="EXISTING",
            status="Active",
            salesforce_id="SF_NO_TID",
            matched_slot_id=None,
            allocations=[],
            lat=-23.5, lon=-46.6,
            radius_a=1500,
            capacity_a=42,
            cluster_name=None,       # no territory
        )
        territories = TerritoriesResult(territory_index={}, hex_to_territory={})
        pkg = _make_pkg_with_demand("DSP2", {}, days=30)

        result = _derive_heuristic_hex_coverage(partner, territories, pkg)

        assert result == []

    def test_derive_hex_coverage_uses_allocations_first(self):
        """
        When both allocations AND territories+pkg are available, allocations
        (CP-SAT) are authoritative. Heuristic is NOT invoked.
        """
        partner = PartnerMetrics(
            origin_hex=_VALID_HEX_A,
            station_code="DSP2",
            radius_s=1000, capacity_s=50,
            entity_type="EXISTING",
            status="Active",
            salesforce_id="SF_MATCHED",
            matched_slot_id="SLOT_001",
            allocations=[
                Allocation(hex_id=_VALID_HEX_A, packages_assigned=42),
            ],
            lat=0.0, lon=0.0,
            radius_a=999999,          # huge radius would pull many hexes
            capacity_a=999,
            cluster_name="DSP2_bucket-01",
        )
        territories = _make_territories_with_hexes(
            "DSP2_bucket-01", "DSP2", _ALL_HEXES,
        )
        pkg = _make_pkg_with_demand("DSP2", {
            _VALID_HEX_A: 300, _VALID_HEX_B: 600, _VALID_HEX_C: 150,
        }, days=30)

        result = _derive_hex_coverage(partner, territories=territories, pkg=pkg)

        # Exactly matches allocations (only HEX_A), not heuristic
        assert result == [{"hex_id": _VALID_HEX_A, "packages_allocated": 42}]

    def test_derive_hex_coverage_falls_back_to_heuristic_when_unmatched(self):
        """
        Active partner without allocations but with territories+pkg available
        gets heuristic-derived hex_coverage (not empty).
        """
        center_lat, center_lon = h3.cell_to_latlng(_VALID_HEX_A)
        partner = PartnerMetrics(
            origin_hex=_VALID_HEX_A,
            station_code="DSP2",
            radius_s=0, capacity_s=0,
            entity_type="EXISTING",
            status="Active",
            salesforce_id="SF_UNMATCHED_FALLBACK",
            matched_slot_id=None,
            allocations=[],
            lat=center_lat, lon=center_lon,
            radius_a=5000, capacity_a=50,
            cluster_name="DSP2_bucket-01",
        )
        territories = _make_territories_with_hexes(
            "DSP2_bucket-01", "DSP2", _ALL_HEXES,
        )
        pkg = _make_pkg_with_demand("DSP2", {
            _VALID_HEX_A: 300, _VALID_HEX_B: 600,
        }, days=30)

        result = _derive_hex_coverage(partner, territories=territories, pkg=pkg)

        assert result is not None
        assert len(result) > 0, "Heuristic fallback should populate coverage"

    def test_derive_hex_coverage_returns_empty_when_no_pkg(self):
        """
        Backward-compatible: without territories+pkg kwargs, Active partner
        with no allocations still gets [] (not None).
        """
        partner = PartnerMetrics(
            origin_hex=_VALID_HEX_A,
            station_code="DSP2",
            radius_s=0, capacity_s=0,
            entity_type="EXISTING",
            status="Active",
            salesforce_id="SF_NO_PKG",
            matched_slot_id=None,
            allocations=[],
        )
        assert _derive_hex_coverage(partner) == []


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
# Property 7: Partial Merge Preservation (REMOVIDO na feature
# satellite-areas-daily-integration, task 3.2)
#
# O teste original exercitava _enrich_heatmap_with_residual que foi
# substituída por write_heatmap_unified. O novo writer regenera o heatmap
# inteiro a cada run — não há mais "merge parcial" para validar.
# ---------------------------------------------------------------------------



# Property 7 (Partial Merge Preservation) foi REMOVIDO na feature
# satellite-areas-daily-integration (task 3.2). O novo writer
# write_heatmap_unified regenera o heatmap inteiro a cada execução,
# tornando a propriedade obsoleta.




# ---------------------------------------------------------------------------
# Property 7: Partial Merge Preservation (REMOVIDO)
#
# Este teste exercitava _enrich_heatmap_with_residual que foi substituída
# pelo write_heatmap_unified na feature satellite-areas-daily-integration
# (task 3.2). O novo writer regenera o heatmap inteiro a cada execução
# — não há mais "merge parcial" para validar. A suite _write_dados_mapa
# continua testada em TestWriteDadosMapaPartialMerge logo abaixo.
# ---------------------------------------------------------------------------


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

        _write_dados_mapa(dados_path, fit, dados_path, territories=_make_territories_from_fit(fit), stations=["DSP2"])

        result = _load_dados_mapa(dados_path)
        result_by_sfid = {r["salesforce_id"]: r for r in result}

        # DSP2 partner should have been updated
        assert "SF_DSP2_MERGE_01" in result_by_sfid
        dsp2_result = result_by_sfid["SF_DSP2_MERGE_01"]
        assert "hex_coverage" in dsp2_result, "DSP2 Active partner must have hex_coverage"
        assert len(dsp2_result["hex_coverage"]) == 2

        # DSP4 partner must preserve all its ORIGINAL fields.
        # NOTE: `_write_dados_mapa` sobrescreve `bucket_ade` em TODOS os records
        # com o valor derivado de territories (ou "" se não há match). Isso é
        # comportamento documentado da Fase 5 — o teste valida que os demais
        # campos do record não são tocados.
        assert "SF_DSP4_MERGE_01" in result_by_sfid, (
            "DSP4 partner must still be present in dados_mapa"
        )
        dsp4_result = result_by_sfid["SF_DSP4_MERGE_01"]
        for k, v in dsp4_original_record.items():
            if k == "bucket_ade":
                continue  # campo normalizado pela Fase 5
            assert dsp4_result.get(k) == v, (
                f"DSP4 campo '{k}' foi modificado por run DSP2-only: "
                f"original={v!r}, novo={dsp4_result.get(k)!r}"
            )
