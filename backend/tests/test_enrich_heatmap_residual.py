"""
test_enrich_heatmap_residual.py
================================
Unit tests for _enrich_heatmap_with_residual() in phase5_reports.py.

Tests:
- Hex covered by Active partner with allocation → is_covered=True, demand_residual=0
- Hex without coverage → is_covered=False, demand_residual=demand_daily
- Onboarding partners also cover hexes
- Partners with other statuses do NOT cover hexes
- Partial merge: hexes from other stations are preserved unchanged
- covering_partner_id is NOT written (replaced by covering_partners list)
- Partners without matched_slot_id are excluded
"""

from __future__ import annotations

import json
import sys
import os
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import h3

from shared.models import Allocation, PartnerMetrics, IdealSlot, TerritoriesResult
from vanilla.phase3_partner_fit import FitResult, TerritoryFit
from vanilla.phase5_reports import _enrich_heatmap_with_residual


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# A real H3 hex at resolution 9 in São Paulo area
HEX_A = "891f1d48177ffff"
HEX_B = "891f1d4817bffff"  # a different hex
HEX_OTHER_STATION = "891f1d4816fffff"  # used for other-station tests

SLOT_ID_A = "DSP2_T01_001"
SLOT_ID_B = "DSP2_T01_002"


def _make_slot(slot_id: str, origin_hex: str, station: str = "DSP2") -> IdealSlot:
    lat, lon = h3.cell_to_latlng(origin_hex)
    return IdealSlot(
        slot_id=slot_id,
        station_code=station,
        bucket_id="DSP2_T01",
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
    origin_hex: str = HEX_A,
    station: str = "DSP2",
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


def _make_fit(partners: List[PartnerMetrics], slots: List[IdealSlot]) -> FitResult:
    tf = TerritoryFit(
        territory_id="DSP2_T01",
        station_code="DSP2",
        bdm_cluster="BDM1",
        ctl_name="CTL1",
        slots=slots,
        partners=partners,
    )
    return FitResult(territories={"DSP2_T01": tf})


def _make_heatmap_file(features: List[dict], path: Path) -> None:
    geojson = {
        "type": "FeatureCollection",
        "features": features,
        "metadata": {"generated_at": "2024-01-01T00:00:00"},
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(geojson, f)


def _hex_feature(hex_id: str, demand_daily: float, station: str = "DSP2") -> dict:
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
            "territory_id": "DSP2_T01",
        },
    }


def _load_features(path: Path) -> List[dict]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)["features"]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestEnrichHeatmapResidual:

    def test_active_partner_covers_hex(self, tmp_path):
        """Hex covered by Active partner with allocation → is_covered=True, demand_residual=0."""
        slot = _make_slot(SLOT_ID_A, HEX_A)
        partner = _make_partner(
            "SF001", "Active", SLOT_ID_A, HEX_A,
            allocations=[Allocation(hex_id=HEX_A, packages_assigned=50)],
        )
        fit = _make_fit([partner], [slot])

        heatmap_path = tmp_path / "heatmap.geojson"
        _make_heatmap_file([_hex_feature(HEX_A, 50.0)], heatmap_path)

        _enrich_heatmap_with_residual(heatmap_path, fit, None, None, stations=["DSP2"])

        features = _load_features(heatmap_path)
        props = features[0]["properties"]

        assert props["is_covered"] is True
        assert props["demand_allocated"] == 50
        assert props["demand_residual"] == 0.0
        # New model: covering_partners list, NOT covering_partner_id
        assert "covering_partner_id" not in props
        assert isinstance(props["covering_partners"], list)
        assert len(props["covering_partners"]) == 1
        assert props["covering_partners"][0]["salesforce_id"] == "SF001"
        assert props["covering_partners"][0]["packages_allocated"] == 50

    def test_uncovered_hex(self, tmp_path):
        """Hex without any covering partner → is_covered=False, demand_residual=demand_daily."""
        fit = _make_fit([], [])

        heatmap_path = tmp_path / "heatmap.geojson"
        _make_heatmap_file([_hex_feature(HEX_A, 30.0)], heatmap_path)

        _enrich_heatmap_with_residual(heatmap_path, fit, None, None, stations=["DSP2"])

        features = _load_features(heatmap_path)
        props = features[0]["properties"]

        assert props["is_covered"] is False
        assert props["demand_allocated"] == 0
        assert props["demand_residual"] == 30.0
        # New model: covering_partners is empty list, NOT covering_partner_id
        assert "covering_partner_id" not in props
        assert props["covering_partners"] == []

    def test_onboarding_partner_covers_hex(self, tmp_path):
        """Onboarding partners also cover hexes."""
        slot = _make_slot(SLOT_ID_A, HEX_A)
        partner = _make_partner(
            "SF002", "Onboarding", SLOT_ID_A, HEX_A,
            allocations=[Allocation(hex_id=HEX_A, packages_assigned=20)],
        )
        fit = _make_fit([partner], [slot])

        heatmap_path = tmp_path / "heatmap.geojson"
        _make_heatmap_file([_hex_feature(HEX_A, 20.0)], heatmap_path)

        _enrich_heatmap_with_residual(heatmap_path, fit, None, None, stations=["DSP2"])

        features = _load_features(heatmap_path)
        props = features[0]["properties"]

        assert props["is_covered"] is True
        assert len(props["covering_partners"]) == 1
        assert props["covering_partners"][0]["salesforce_id"] == "SF002"

    @pytest.mark.parametrize("status", ["BG Checks", "Prospect", "Inactive", "Exited"])
    def test_non_active_partner_does_not_cover_hex(self, tmp_path, status):
        """Partners with status other than Active/Onboarding do NOT cover hexes."""
        slot = _make_slot(SLOT_ID_A, HEX_A)
        partner = _make_partner(
            "SF003", status, SLOT_ID_A, HEX_A,
            allocations=[Allocation(hex_id=HEX_A, packages_assigned=40)],
        )
        fit = _make_fit([partner], [slot])

        heatmap_path = tmp_path / "heatmap.geojson"
        _make_heatmap_file([_hex_feature(HEX_A, 40.0)], heatmap_path)

        _enrich_heatmap_with_residual(heatmap_path, fit, None, None, stations=["DSP2"])

        features = _load_features(heatmap_path)
        props = features[0]["properties"]

        assert props["is_covered"] is False, f"Status '{status}' should not cover hex"
        assert props["demand_residual"] == 40.0
        assert props["covering_partners"] == []

    def test_partial_merge_preserves_other_station_hexes(self, tmp_path):
        """Hexes from other stations are preserved without modification."""
        slot = _make_slot(SLOT_ID_A, HEX_A)
        partner = _make_partner(
            "SF001", "Active", SLOT_ID_A, HEX_A,
            allocations=[Allocation(hex_id=HEX_A, packages_assigned=50)],
        )
        fit = _make_fit([partner], [slot])

        # Two features: one for DSP2 (to be enriched), one for OTHER_DS (to be preserved)
        features = [
            _hex_feature(HEX_A, 50.0, station="DSP2"),
            _hex_feature(HEX_OTHER_STATION, 99.0, station="OTHER_DS"),
        ]
        heatmap_path = tmp_path / "heatmap.geojson"
        _make_heatmap_file(features, heatmap_path)

        _enrich_heatmap_with_residual(heatmap_path, fit, None, None, stations=["DSP2"])

        result_features = _load_features(heatmap_path)
        assert len(result_features) == 2

        other_feat = next(
            f for f in result_features
            if f["properties"]["delivery_station"] == "OTHER_DS"
        )
        other_props = other_feat["properties"]

        # Other station hex must NOT have been modified
        assert "is_covered" not in other_props
        assert "demand_residual" not in other_props
        assert "demand_allocated" not in other_props
        assert "covering_partner_id" not in other_props
        assert "covering_partners" not in other_props
        assert other_props["demand_daily"] == 99.0

    def test_missing_heatmap_file_does_not_raise(self, tmp_path):
        """If heatmap.geojson does not exist, function returns gracefully."""
        fit = _make_fit([], [])
        heatmap_path = tmp_path / "heatmap.geojson"
        # File does not exist — should not raise
        _enrich_heatmap_with_residual(heatmap_path, fit, None, None)

    def test_partner_without_matched_slot_does_not_cover(self, tmp_path):
        """Active partner with no matched_slot_id does not cover any hex."""
        partner = _make_partner(
            "SF004", "Active", matched_slot_id=None, origin_hex=HEX_A,
            allocations=[Allocation(hex_id=HEX_A, packages_assigned=25)],
        )
        fit = _make_fit([partner], [])

        heatmap_path = tmp_path / "heatmap.geojson"
        _make_heatmap_file([_hex_feature(HEX_A, 25.0)], heatmap_path)

        _enrich_heatmap_with_residual(heatmap_path, fit, None, None, stations=["DSP2"])

        features = _load_features(heatmap_path)
        props = features[0]["properties"]

        assert props["is_covered"] is False
        assert props["demand_residual"] == 25.0
        assert props["covering_partners"] == []

    def test_covering_partner_id_absent(self, tmp_path):
        """covering_partner_id must NOT be written to any hex feature properties."""
        slot = _make_slot(SLOT_ID_A, HEX_A)
        partner = _make_partner(
            "SF006", "Active", SLOT_ID_A, HEX_A,
            allocations=[Allocation(hex_id=HEX_A, packages_assigned=30)],
        )
        fit = _make_fit([partner], [slot])

        heatmap_path = tmp_path / "heatmap.geojson"
        _make_heatmap_file([_hex_feature(HEX_A, 30.0)], heatmap_path)

        _enrich_heatmap_with_residual(heatmap_path, fit, None, None, stations=["DSP2"])

        features = _load_features(heatmap_path)
        for ft in features:
            assert "covering_partner_id" not in ft["properties"], (
                "covering_partner_id must not be written by the new model"
            )

    def test_multiple_partners_share_hex(self, tmp_path):
        """Multiple Active/Onboarding partners can share a hex — all appear in covering_partners."""
        slot_a = _make_slot(SLOT_ID_A, HEX_A)
        slot_b = _make_slot(SLOT_ID_B, HEX_A)
        partner_a = _make_partner(
            "SF007", "Active", SLOT_ID_A, HEX_A,
            allocations=[Allocation(hex_id=HEX_A, packages_assigned=30)],
        )
        partner_b = _make_partner(
            "SF008", "Onboarding", SLOT_ID_B, HEX_A,
            allocations=[Allocation(hex_id=HEX_A, packages_assigned=20)],
        )
        fit = _make_fit([partner_a, partner_b], [slot_a, slot_b])

        heatmap_path = tmp_path / "heatmap.geojson"
        _make_heatmap_file([_hex_feature(HEX_A, 50.0)], heatmap_path)

        _enrich_heatmap_with_residual(heatmap_path, fit, None, None, stations=["DSP2"])

        features = _load_features(heatmap_path)
        props = features[0]["properties"]

        assert props["is_covered"] is True
        assert props["demand_allocated"] == 50
        assert props["demand_residual"] == 0.0
        assert len(props["covering_partners"]) == 2

        sfids = {cp["salesforce_id"] for cp in props["covering_partners"]}
        assert sfids == {"SF007", "SF008"}
