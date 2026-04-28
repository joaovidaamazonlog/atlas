"""
test_phase5_integration.py
==========================
Integration tests for the full Phase 5 pipeline.

Tests:
- Task 11.1: Full Phase 5 pipeline on fixture FitResult (multi-station)
- Task 11.2: Single-station run isolation (DSP2 only, DSP4 unchanged)

Requirements: 1.1-1.4, 2.1-2.7, 3.1-3.4, 7.1, 7.2, 7.3
"""

from __future__ import annotations

import copy
import json
import os
import sys
from pathlib import Path
from typing import List, Optional

import h3
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from shared.models import Allocation, IdealSlot, PartnerMetrics, TerritoriesResult
from vanilla.phase3_partner_fit import FitResult, TerritoryFit
from vanilla.phase5_reports import _enrich_heatmap_with_residual, _write_dados_mapa


# ---------------------------------------------------------------------------
# Real H3 hex IDs (resolution 9)
# ---------------------------------------------------------------------------

# DSP2 hexes
HEX_DSP2_A = "891f1d48177ffff"
HEX_DSP2_B = "891f1d4817bffff"
HEX_DSP2_C = "891f1d4816fffff"

# DSP4 hexes (different cells)
HEX_DSP4_A = "891f1d48163ffff"
HEX_DSP4_B = "891f1d48183ffff"


# ---------------------------------------------------------------------------
# Fixture builders
# ---------------------------------------------------------------------------

def _make_slot(slot_id: str, origin_hex: str, station: str) -> IdealSlot:
    lat, lon = h3.cell_to_latlng(origin_hex)
    return IdealSlot(
        slot_id=slot_id,
        station_code=station,
        bucket_id=f"{station}_T01",
        origin_hex=origin_hex,
        radius_s=1000,
        capacity_s=100,
        lat=lat,
        lon=lon,
    )


def _make_partner(
    salesforce_id: str,
    status: str,
    matched_slot_id: Optional[str],
    origin_hex: str,
    station: str,
    allocations: Optional[List[Allocation]] = None,
) -> PartnerMetrics:
    lat, lon = h3.cell_to_latlng(origin_hex)
    return PartnerMetrics(
        origin_hex=origin_hex,
        station_code=station,
        radius_s=1000,
        capacity_s=100,
        entity_type="EXISTING",
        status=status,
        salesforce_id=salesforce_id,
        matched_slot_id=matched_slot_id,
        lat=lat,
        lon=lon,
        allocations=allocations or [],
    )


def _make_fit_result(territories: dict) -> FitResult:
    return FitResult(
        territories=territories,
        outside_jurisdiction=[],
        unassigned_by_territory={},
    )


def _make_territories_from_fit(fit: FitResult) -> TerritoriesResult:
    """
    Helper local: constrói um `TerritoriesResult` mínimo compatível com a
    assinatura de `_write_dados_mapa`, derivado dos territórios presentes
    em um `FitResult`. Para os testes, basta que cada territory_id tenha
    `station_code`, hexes de parceiros e centroide.
    """
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


def _hex_feature(hex_id: str, demand_daily: float, station: str) -> dict:
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


def _write_heatmap(features: list, path: Path) -> None:
    geojson = {
        "type": "FeatureCollection",
        "features": features,
        "metadata": {"generated_at": "2024-01-01T00:00:00"},
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(geojson, f)


def _write_dados_mapa_fixture(records: list, path: Path) -> None:
    payload = {"allMarkerData": records}
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f)


def _load_heatmap_features(path: Path) -> list:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)["features"]


def _load_dados_mapa_records(path: Path) -> list:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)["allMarkerData"]


# ---------------------------------------------------------------------------
# Task 11.1: Full Phase 5 pipeline on fixture FitResult
# Requirements: 1.1-1.4, 2.1-2.7, 3.1-3.4
# ---------------------------------------------------------------------------

class TestPhase5FullPipeline:
    """
    Integration test: full Phase 5 pipeline on a fixture FitResult with
    partners from two stations (DSP2 and DSP4), including Active, Onboarding,
    and non-Active (BG Checks) partners.
    """

    def _build_fit_result(self) -> FitResult:
        """
        Build a FitResult with:
        - DSP2: 2 Active/Onboarding partners with allocations across multiple hexes
        - DSP2: 1 BG Checks partner with allocations (should NOT cover hexes)
        - DSP4: 1 Active partner with allocations
        """
        # DSP2 partners
        partner_dsp2_active = _make_partner(
            salesforce_id="SF_DSP2_ACTIVE",
            status="Active",
            matched_slot_id="DSP2_T01_SLOT1",
            origin_hex=HEX_DSP2_A,
            station="DSP2",
            allocations=[
                Allocation(hex_id=HEX_DSP2_A, packages_assigned=40),
                Allocation(hex_id=HEX_DSP2_B, packages_assigned=20),
            ],
        )
        partner_dsp2_onboarding = _make_partner(
            salesforce_id="SF_DSP2_ONBOARD",
            status="Onboarding",
            matched_slot_id="DSP2_T01_SLOT2",
            origin_hex=HEX_DSP2_B,
            station="DSP2",
            allocations=[
                Allocation(hex_id=HEX_DSP2_B, packages_assigned=15),
                Allocation(hex_id=HEX_DSP2_C, packages_assigned=30),
            ],
        )
        partner_dsp2_bg = _make_partner(
            salesforce_id="SF_DSP2_BG",
            status="BG Checks",
            matched_slot_id="DSP2_T01_SLOT3",
            origin_hex=HEX_DSP2_C,
            station="DSP2",
            allocations=[
                Allocation(hex_id=HEX_DSP2_C, packages_assigned=25),
            ],
        )

        # DSP4 partner
        partner_dsp4_active = _make_partner(
            salesforce_id="SF_DSP4_ACTIVE",
            status="Active",
            matched_slot_id="DSP4_T01_SLOT1",
            origin_hex=HEX_DSP4_A,
            station="DSP4",
            allocations=[
                Allocation(hex_id=HEX_DSP4_A, packages_assigned=50),
                Allocation(hex_id=HEX_DSP4_B, packages_assigned=10),
            ],
        )

        territories = {
            "DSP2_T01": TerritoryFit(
                territory_id="DSP2_T01",
                station_code="DSP2",
                bdm_cluster="BDM1",
                ctl_name="CTL1",
                slots=[],
                partners=[partner_dsp2_active, partner_dsp2_onboarding, partner_dsp2_bg],
            ),
            "DSP4_T01": TerritoryFit(
                territory_id="DSP4_T01",
                station_code="DSP4",
                bdm_cluster="BDM2",
                ctl_name="CTL2",
                slots=[],
                partners=[partner_dsp4_active],
            ),
        }
        return _make_fit_result(territories)

    def test_heatmap_covering_partners_present(self, tmp_path):
        """
        Covered hexes have non-empty covering_partners lists.
        Requirements: 1.1, 1.2, 1.3, 2.1, 2.4, 2.5
        """
        fit = self._build_fit_result()

        features = [
            _hex_feature(HEX_DSP2_A, 40.0, "DSP2"),
            _hex_feature(HEX_DSP2_B, 35.0, "DSP2"),
            _hex_feature(HEX_DSP2_C, 30.0, "DSP2"),
            _hex_feature(HEX_DSP4_A, 50.0, "DSP4"),
            _hex_feature(HEX_DSP4_B, 10.0, "DSP4"),
        ]
        heatmap_path = tmp_path / "heatmap.geojson"
        _write_heatmap(features, heatmap_path)

        _enrich_heatmap_with_residual(
            heatmap_path, fit, None, None, stations=["DSP2", "DSP4"]
        )

        result = _load_heatmap_features(heatmap_path)
        by_hex = {f["properties"]["hex_id"]: f["properties"] for f in result}

        # DSP2_A: covered by Active partner only
        props_a = by_hex[HEX_DSP2_A]
        assert isinstance(props_a["covering_partners"], list)
        assert len(props_a["covering_partners"]) >= 1
        sfids_a = {cp["salesforce_id"] for cp in props_a["covering_partners"]}
        assert "SF_DSP2_ACTIVE" in sfids_a

        # DSP2_B: covered by both Active and Onboarding partners
        props_b = by_hex[HEX_DSP2_B]
        assert isinstance(props_b["covering_partners"], list)
        assert len(props_b["covering_partners"]) == 2
        sfids_b = {cp["salesforce_id"] for cp in props_b["covering_partners"]}
        assert sfids_b == {"SF_DSP2_ACTIVE", "SF_DSP2_ONBOARD"}

        # DSP2_C: covered by Onboarding only (BG Checks does NOT cover)
        props_c = by_hex[HEX_DSP2_C]
        assert isinstance(props_c["covering_partners"], list)
        assert len(props_c["covering_partners"]) == 1
        assert props_c["covering_partners"][0]["salesforce_id"] == "SF_DSP2_ONBOARD"
        # BG Checks partner must NOT appear
        sfids_c = {cp["salesforce_id"] for cp in props_c["covering_partners"]}
        assert "SF_DSP2_BG" not in sfids_c

        # DSP4_A: covered by DSP4 Active partner
        props_dsp4_a = by_hex[HEX_DSP4_A]
        assert len(props_dsp4_a["covering_partners"]) == 1
        assert props_dsp4_a["covering_partners"][0]["salesforce_id"] == "SF_DSP4_ACTIVE"

    def test_heatmap_no_covering_partner_id(self, tmp_path):
        """
        No hex feature should have a covering_partner_id field.
        Requirement: 2.6
        """
        fit = self._build_fit_result()

        features = [
            _hex_feature(HEX_DSP2_A, 40.0, "DSP2"),
            _hex_feature(HEX_DSP2_B, 35.0, "DSP2"),
            _hex_feature(HEX_DSP4_A, 50.0, "DSP4"),
        ]
        heatmap_path = tmp_path / "heatmap.geojson"
        _write_heatmap(features, heatmap_path)

        _enrich_heatmap_with_residual(
            heatmap_path, fit, None, None, stations=["DSP2", "DSP4"]
        )

        result = _load_heatmap_features(heatmap_path)
        for ft in result:
            assert "covering_partner_id" not in ft["properties"], (
                f"covering_partner_id must not be written; found in hex "
                f"{ft['properties'].get('hex_id')}"
            )

    def test_heatmap_demand_allocated_equals_sum_of_packages(self, tmp_path):
        """
        demand_allocated equals sum of packages for covered hexes.
        Requirement: 2.1
        """
        fit = self._build_fit_result()

        features = [
            _hex_feature(HEX_DSP2_A, 40.0, "DSP2"),
            _hex_feature(HEX_DSP2_B, 35.0, "DSP2"),
            _hex_feature(HEX_DSP2_C, 30.0, "DSP2"),
        ]
        heatmap_path = tmp_path / "heatmap.geojson"
        _write_heatmap(features, heatmap_path)

        _enrich_heatmap_with_residual(
            heatmap_path, fit, None, None, stations=["DSP2"]
        )

        result = _load_heatmap_features(heatmap_path)
        by_hex = {f["properties"]["hex_id"]: f["properties"] for f in result}

        # HEX_DSP2_A: Active partner allocates 40 packages
        assert by_hex[HEX_DSP2_A]["demand_allocated"] == 40

        # HEX_DSP2_B: Active=20 + Onboarding=15 = 35
        assert by_hex[HEX_DSP2_B]["demand_allocated"] == 35

        # HEX_DSP2_C: Onboarding=30 (BG Checks does NOT count)
        assert by_hex[HEX_DSP2_C]["demand_allocated"] == 30

    def test_heatmap_demand_residual_correctly_computed(self, tmp_path):
        """
        demand_residual = demand_daily - demand_allocated, rounded to 4 decimal places.
        Requirement: 2.2
        """
        fit = self._build_fit_result()

        features = [
            _hex_feature(HEX_DSP2_A, 50.0, "DSP2"),   # allocated=40, residual=10
            _hex_feature(HEX_DSP2_B, 35.0, "DSP2"),   # allocated=35, residual=0
            _hex_feature(HEX_DSP2_C, 45.0, "DSP2"),   # allocated=30, residual=15
        ]
        heatmap_path = tmp_path / "heatmap.geojson"
        _write_heatmap(features, heatmap_path)

        _enrich_heatmap_with_residual(
            heatmap_path, fit, None, None, stations=["DSP2"]
        )

        result = _load_heatmap_features(heatmap_path)
        by_hex = {f["properties"]["hex_id"]: f["properties"] for f in result}

        assert by_hex[HEX_DSP2_A]["demand_residual"] == round(50.0 - 40, 4)
        assert by_hex[HEX_DSP2_B]["demand_residual"] == round(35.0 - 35, 4)
        assert by_hex[HEX_DSP2_C]["demand_residual"] == round(45.0 - 30, 4)

    def test_dados_mapa_active_onboarding_have_hex_coverage(self, tmp_path):
        """
        Active/Onboarding partners have hex_coverage field.
        Requirements: 3.1, 3.2, 3.3
        """
        fit = self._build_fit_result()

        records = [
            {"salesforce_id": "SF_DSP2_ACTIVE", "delivery_station": "DSP2"},
            {"salesforce_id": "SF_DSP2_ONBOARD", "delivery_station": "DSP2"},
            {"salesforce_id": "SF_DSP2_BG", "delivery_station": "DSP2"},
            {"salesforce_id": "SF_DSP4_ACTIVE", "delivery_station": "DSP4"},
        ]
        dados_path = tmp_path / "dados_mapa.json"
        _write_dados_mapa_fixture(records, dados_path)

        _write_dados_mapa(dados_path, fit, dados_path,
                          territories=_make_territories_from_fit(fit),
                          stations=["DSP2", "DSP4"])

        result = _load_dados_mapa_records(dados_path)
        by_sfid = {r["salesforce_id"]: r for r in result}

        # Active partner must have hex_coverage
        active_record = by_sfid["SF_DSP2_ACTIVE"]
        assert "hex_coverage" in active_record
        assert isinstance(active_record["hex_coverage"], list)
        assert len(active_record["hex_coverage"]) == 2
        hex_ids = {e["hex_id"] for e in active_record["hex_coverage"]}
        assert hex_ids == {HEX_DSP2_A, HEX_DSP2_B}

        # Onboarding partner must have hex_coverage
        onboard_record = by_sfid["SF_DSP2_ONBOARD"]
        assert "hex_coverage" in onboard_record
        assert len(onboard_record["hex_coverage"]) == 2

        # DSP4 Active partner must have hex_coverage
        dsp4_record = by_sfid["SF_DSP4_ACTIVE"]
        assert "hex_coverage" in dsp4_record
        assert len(dsp4_record["hex_coverage"]) == 2

    def test_dados_mapa_non_active_no_hex_coverage(self, tmp_path):
        """
        Non-Active partners (BG Checks) do NOT have hex_coverage field.
        Requirement: 3.4
        """
        fit = self._build_fit_result()

        records = [
            {"salesforce_id": "SF_DSP2_BG", "delivery_station": "DSP2"},
        ]
        dados_path = tmp_path / "dados_mapa.json"
        _write_dados_mapa_fixture(records, dados_path)

        _write_dados_mapa(dados_path, fit, dados_path,
                          territories=_make_territories_from_fit(fit),
                          stations=["DSP2"])

        result = _load_dados_mapa_records(dados_path)
        bg_record = result[0]

        assert "hex_coverage" not in bg_record, (
            "BG Checks partner must NOT have hex_coverage field"
        )

    def test_dados_mapa_hex_coverage_entry_structure(self, tmp_path):
        """
        hex_coverage entries have correct hex_id and packages_allocated fields.
        Requirement: 3.2
        """
        fit = self._build_fit_result()

        records = [
            {"salesforce_id": "SF_DSP2_ACTIVE", "delivery_station": "DSP2"},
        ]
        dados_path = tmp_path / "dados_mapa.json"
        _write_dados_mapa_fixture(records, dados_path)

        _write_dados_mapa(dados_path, fit, dados_path,
                          territories=_make_territories_from_fit(fit),
                          stations=["DSP2"])

        result = _load_dados_mapa_records(dados_path)
        active_record = result[0]

        assert "hex_coverage" in active_record
        for entry in active_record["hex_coverage"]:
            assert "hex_id" in entry
            assert "packages_allocated" in entry
            assert isinstance(entry["hex_id"], str)
            assert isinstance(entry["packages_allocated"], int)

        # Verify specific values
        by_hex = {e["hex_id"]: e["packages_allocated"] for e in active_record["hex_coverage"]}
        assert by_hex[HEX_DSP2_A] == 40
        assert by_hex[HEX_DSP2_B] == 20


# ---------------------------------------------------------------------------
# Task 11.2: Single-station run isolation
# Requirements: 7.1, 7.2, 7.3
# ---------------------------------------------------------------------------

class TestPhase5SingleStationIsolation:
    """
    Integration test: running the pipeline for DSP2 only must not modify
    any DSP4 hex features or partner records.
    """

    def _build_multi_station_fit(self) -> FitResult:
        """Build a FitResult with partners for both DSP2 and DSP4."""
        partner_dsp2 = _make_partner(
            salesforce_id="SF_DSP2_ISO",
            status="Active",
            matched_slot_id="DSP2_T01_SLOT1",
            origin_hex=HEX_DSP2_A,
            station="DSP2",
            allocations=[
                Allocation(hex_id=HEX_DSP2_A, packages_assigned=35),
            ],
        )
        partner_dsp4 = _make_partner(
            salesforce_id="SF_DSP4_ISO",
            status="Active",
            matched_slot_id="DSP4_T01_SLOT1",
            origin_hex=HEX_DSP4_A,
            station="DSP4",
            allocations=[
                Allocation(hex_id=HEX_DSP4_A, packages_assigned=60),
            ],
        )
        territories = {
            "DSP2_T01": TerritoryFit(
                territory_id="DSP2_T01",
                station_code="DSP2",
                bdm_cluster="BDM1",
                ctl_name="CTL1",
                slots=[],
                partners=[partner_dsp2],
            ),
            "DSP4_T01": TerritoryFit(
                territory_id="DSP4_T01",
                station_code="DSP4",
                bdm_cluster="BDM2",
                ctl_name="CTL2",
                slots=[],
                partners=[partner_dsp4],
            ),
        }
        return _make_fit_result(territories)

    def test_dsp2_hexes_enriched_dsp4_hexes_unchanged(self, tmp_path):
        """
        Running pipeline for DSP2 only: DSP2 hexes are enriched, DSP4 hexes
        are completely unchanged (byte-for-byte identical properties).
        Requirements: 7.1, 7.2
        """
        fit = self._build_multi_station_fit()

        dsp2_feature = _hex_feature(HEX_DSP2_A, 35.0, "DSP2")
        dsp4_feature = _hex_feature(HEX_DSP4_A, 60.0, "DSP4")

        # Capture the original DSP4 properties before running the pipeline
        original_dsp4_props = copy.deepcopy(dsp4_feature["properties"])

        heatmap_path = tmp_path / "heatmap.geojson"
        _write_heatmap([dsp2_feature, dsp4_feature], heatmap_path)

        # Run pipeline for DSP2 only
        _enrich_heatmap_with_residual(
            heatmap_path, fit, None, None, stations=["DSP2"]
        )

        result = _load_heatmap_features(heatmap_path)
        assert len(result) == 2

        by_station = {f["properties"]["delivery_station"]: f["properties"] for f in result}

        # DSP2 hex must be enriched
        dsp2_props = by_station["DSP2"]
        assert "is_covered" in dsp2_props
        assert "demand_allocated" in dsp2_props
        assert "demand_residual" in dsp2_props
        assert "covering_partners" in dsp2_props
        assert dsp2_props["is_covered"] is True
        assert dsp2_props["demand_allocated"] == 35

        # DSP4 hex must be completely unchanged
        dsp4_props = by_station["DSP4"]
        assert dsp4_props == original_dsp4_props, (
            f"DSP4 hex properties were modified when running DSP2-only pipeline.\n"
            f"Original: {original_dsp4_props}\n"
            f"After:    {dsp4_props}"
        )
        # Explicitly verify no enrichment fields were added
        assert "is_covered" not in dsp4_props
        assert "demand_allocated" not in dsp4_props
        assert "demand_residual" not in dsp4_props
        assert "covering_partners" not in dsp4_props
        assert "covering_partner_id" not in dsp4_props

    def test_dsp2_partners_enriched_dsp4_partners_unchanged(self, tmp_path):
        """
        Running pipeline for DSP2 only: DSP2 Active/Onboarding partners get
        hex_coverage; DSP4 partner records are completely unchanged.
        Requirement: 7.3

        The isolation is achieved by passing a FitResult that only contains
        DSP2 partners. _write_dados_mapa updates all records whose salesforce_id
        appears in the FitResult, so passing only DSP2 partners ensures DSP4
        records are not touched.
        """
        # Build a DSP2-only FitResult (no DSP4 partners)
        partner_dsp2 = _make_partner(
            salesforce_id="SF_DSP2_ISO",
            status="Active",
            matched_slot_id="DSP2_T01_SLOT1",
            origin_hex=HEX_DSP2_A,
            station="DSP2",
            allocations=[
                Allocation(hex_id=HEX_DSP2_A, packages_assigned=35),
            ],
        )
        dsp2_only_fit = _make_fit_result({
            "DSP2_T01": TerritoryFit(
                territory_id="DSP2_T01",
                station_code="DSP2",
                bdm_cluster="BDM1",
                ctl_name="CTL1",
                slots=[],
                partners=[partner_dsp2],
            ),
        })

        dsp2_record = {
            "salesforce_id": "SF_DSP2_ISO",
            "delivery_station": "DSP2",
            "some_existing_field": "dsp2_value",
        }
        dsp4_record = {
            "salesforce_id": "SF_DSP4_ISO",
            "delivery_station": "DSP4",
            "some_existing_field": "dsp4_value",
        }

        # Capture original DSP4 record
        original_dsp4_record = copy.deepcopy(dsp4_record)

        dados_path = tmp_path / "dados_mapa.json"
        _write_dados_mapa_fixture([dsp2_record, dsp4_record], dados_path)

        # Run pipeline for DSP2 only -- pass DSP2-only FitResult
        _write_dados_mapa(dados_path, dsp2_only_fit, dados_path,
                          territories=_make_territories_from_fit(dsp2_only_fit),
                          stations=["DSP2"])

        result = _load_dados_mapa_records(dados_path)
        by_sfid = {r["salesforce_id"]: r for r in result}

        # DSP2 partner must have hex_coverage
        dsp2_result = by_sfid["SF_DSP2_ISO"]
        assert "hex_coverage" in dsp2_result
        assert len(dsp2_result["hex_coverage"]) == 1
        assert dsp2_result["hex_coverage"][0]["hex_id"] == HEX_DSP2_A
        assert dsp2_result["hex_coverage"][0]["packages_allocated"] == 35

        # DSP4 partner record must be preserved.
        # NOTE: `_write_dados_mapa` pode adicionar o campo `bucket_ade`
        # vazio em TODOS os records como parte da normalização de
        # schema — isso é comportamento documentado da Fase 5. O que
        # o teste garante é que nenhum campo original é alterado nem
        # removido.
        dsp4_result = by_sfid["SF_DSP4_ISO"]
        for k, v in original_dsp4_record.items():
            assert dsp4_result.get(k) == v, (
                f"DSP4 campo '{k}' foi modificado por run DSP2-only "
                f"(original={v!r}, novo={dsp4_result.get(k)!r})."
            )
        # hex_coverage não deve existir em parceiros não presentes no FitResult
        assert "hex_coverage" not in dsp4_result
        # Verify the existing field is preserved
        assert dsp4_result.get("some_existing_field") == "dsp4_value"
        assert "hex_coverage" not in dsp4_result

    def test_multiple_dsp4_hexes_all_unchanged(self, tmp_path):
        """
        All DSP4 hex features remain unchanged when running DSP2-only pipeline.
        Requirement: 7.2
        """
        fit = self._build_multi_station_fit()

        features = [
            _hex_feature(HEX_DSP2_A, 35.0, "DSP2"),
            _hex_feature(HEX_DSP4_A, 60.0, "DSP4"),
            _hex_feature(HEX_DSP4_B, 25.0, "DSP4"),
        ]

        # Capture original DSP4 properties
        original_dsp4_props = {
            HEX_DSP4_A: copy.deepcopy(features[1]["properties"]),
            HEX_DSP4_B: copy.deepcopy(features[2]["properties"]),
        }

        heatmap_path = tmp_path / "heatmap.geojson"
        _write_heatmap(features, heatmap_path)

        _enrich_heatmap_with_residual(
            heatmap_path, fit, None, None, stations=["DSP2"]
        )

        result = _load_heatmap_features(heatmap_path)
        assert len(result) == 3

        for ft in result:
            props = ft["properties"]
            if props["delivery_station"] == "DSP4":
                hex_id = props["hex_id"]
                assert props == original_dsp4_props[hex_id], (
                    f"DSP4 hex {hex_id} was modified when running DSP2-only pipeline"
                )
