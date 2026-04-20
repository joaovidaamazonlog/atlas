"""
test_load_h3_index_and_coverage.py
====================================
Unit tests for _load_h3_index and _build_coverage_index in
geo_phase3_5_cap_optimizer.py.

Execution
---------
    pytest backend/geo_intelligence/tests/test_load_h3_index_and_coverage.py -v
"""

from __future__ import annotations

import sys
import os
from dataclasses import dataclass
from typing import List, Optional
from unittest.mock import MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

import h3
import pytest

from geo_intelligence.geo_phase3_5_cap_optimizer import (
    _load_h3_index,
    _build_coverage_index,
    _disaggregate_r8_to_r9,
)

# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------

# A known valid res-8 hex in São Paulo area
_RES8_HEX = "88a8100c03fffff"
# Its res-9 children
_RES9_CHILDREN = list(h3.cell_to_children(_RES8_HEX, 9))

# Center of the res-8 hex
_RES8_CENTER_LAT, _RES8_CENTER_LON = h3.cell_to_latlng(_RES8_HEX)


@dataclass
class _FakePartner:
    """Minimal stand-in for GeoPartnerMatch."""
    partner_id: str
    lat: float
    lon: float
    radius: int
    status: str = "Active"
    capacity: int = 42


def _make_reader(records):
    """Return a mock TursoReader whose get_h3_cells_for_station returns records."""
    reader = MagicMock()
    reader.get_h3_cells_for_station.return_value = records
    return reader


# ---------------------------------------------------------------------------
# _load_h3_index — unit tests
# ---------------------------------------------------------------------------

class TestLoadH3Index:

    def test_returns_empty_dict_when_no_records(self):
        reader = _make_reader([])
        result = _load_h3_index(reader, "DSP2", "run_001")
        assert result == {}

    def test_calls_get_h3_cells_for_station_with_correct_args(self):
        reader = _make_reader([])
        _load_h3_index(reader, "DSP2", "run_001")
        reader.get_h3_cells_for_station.assert_called_once_with("DSP2", "run_001")

    def test_disaggregates_single_record(self):
        density = 70.0
        records = [{"h3_id": _RES8_HEX, "delivery_density_r8": density}]
        reader = _make_reader(records)

        result = _load_h3_index(reader, "DSP2", "run_001")

        # All res-9 children should be present
        for child in _RES9_CHILDREN:
            assert child in result

        # Density must be conserved
        assert abs(sum(result.values()) - density) < 1e-9

    def test_null_density_treated_as_zero(self):
        """Req 7.3: delivery_density_r8 null → 0.0 before disaggregation."""
        records = [{"h3_id": _RES8_HEX, "delivery_density_r8": None}]
        reader = _make_reader(records)

        result = _load_h3_index(reader, "DSP2", "run_001")

        # Children should exist with density 0.0
        for child in _RES9_CHILDREN:
            assert child in result
            assert result[child] == 0.0

    def test_missing_density_field_treated_as_zero(self):
        """delivery_density_r8 key absent → 0.0."""
        records = [{"h3_id": _RES8_HEX}]
        reader = _make_reader(records)

        result = _load_h3_index(reader, "DSP2", "run_001")

        for child in _RES9_CHILDREN:
            assert child in result
            assert result[child] == 0.0

    def test_multiple_records_aggregated(self):
        """Multiple res-8 records → all their children in the index."""
        hex2 = "88a8100c0bfffff"
        children2 = list(h3.cell_to_children(hex2, 9))

        records = [
            {"h3_id": _RES8_HEX, "delivery_density_r8": 14.0},
            {"h3_id": hex2, "delivery_density_r8": 7.0},
        ]
        reader = _make_reader(records)

        result = _load_h3_index(reader, "DSP2", "run_001")

        for child in _RES9_CHILDREN:
            assert child in result
        for child in children2:
            assert child in result

    def test_record_with_empty_h3_id_skipped(self):
        """Records with empty/missing h3_id are silently skipped."""
        records = [
            {"h3_id": "", "delivery_density_r8": 10.0},
            {"delivery_density_r8": 5.0},
        ]
        reader = _make_reader(records)

        result = _load_h3_index(reader, "DSP2", "run_001")
        assert result == {}

    def test_warns_when_no_records(self, caplog):
        import logging
        reader = _make_reader([])
        with caplog.at_level(logging.WARNING, logger="geo_intelligence.geo_phase3_5_cap_optimizer"):
            _load_h3_index(reader, "DSP2", "run_001")
        assert any("nenhum registro" in msg.lower() or "no records" in msg.lower() or "run_001" in msg
                   for msg in caplog.messages)


# ---------------------------------------------------------------------------
# _build_coverage_index — unit tests
# ---------------------------------------------------------------------------

class TestBuildCoverageIndex:

    def _h3_index_from_hex(self, h3_id_r8: str, density: float = 1.0) -> dict:
        """Build a small h3_index from a single res-8 hex."""
        return _disaggregate_r8_to_r9(h3_id_r8, density)

    def test_returns_empty_set_when_no_partners(self):
        h3_index = self._h3_index_from_hex(_RES8_HEX)
        result = _build_coverage_index([], h3_index)
        assert result == set()

    def test_partner_at_hex_center_covers_nearby_hexes(self):
        """A partner placed at the center of a res-8 hex with large radius covers its children."""
        h3_index = self._h3_index_from_hex(_RES8_HEX, density=10.0)
        partner = _FakePartner(
            partner_id="P1",
            lat=_RES8_CENTER_LAT,
            lon=_RES8_CENTER_LON,
            radius=2000,  # 2 km — should cover all res-9 children
        )

        covered = _build_coverage_index([partner], h3_index)

        # All children should be covered given the large radius
        for child in _RES9_CHILDREN:
            assert child in covered

    def test_partner_with_zero_radius_covers_only_coincident_hex(self):
        """A partner at the res-8 center with radius=0 covers at most the child whose
        center coincides exactly with the parent center (Haversine distance == 0)."""
        h3_index = self._h3_index_from_hex(_RES8_HEX, density=10.0)
        partner = _FakePartner(
            partner_id="P1",
            lat=_RES8_CENTER_LAT,
            lon=_RES8_CENTER_LON,
            radius=0,
        )

        covered = _build_coverage_index([partner], h3_index)
        # At most one child (the one whose center == parent center) can be covered
        assert len(covered) <= 1

    def test_exclude_partner_id_removes_that_partners_coverage(self):
        """Req 2.4: excluding a partner's own coverage reveals its hexes."""
        h3_index = self._h3_index_from_hex(_RES8_HEX, density=10.0)
        partner = _FakePartner(
            partner_id="P1",
            lat=_RES8_CENTER_LAT,
            lon=_RES8_CENTER_LON,
            radius=2000,
        )

        # Without exclusion: hexes are covered
        covered_all = _build_coverage_index([partner], h3_index)
        assert len(covered_all) > 0

        # With exclusion of P1: nothing covered
        covered_excl = _build_coverage_index([partner], h3_index, exclude_partner_id="P1")
        assert covered_excl == set()

    def test_multiple_partners_union_of_coverage(self):
        """Coverage is the union of all non-excluded partners."""
        hex2 = "88a8100c0bfffff"
        lat2, lon2 = h3.cell_to_latlng(hex2)
        children2 = list(h3.cell_to_children(hex2, 9))

        h3_index = {}
        h3_index.update(_disaggregate_r8_to_r9(_RES8_HEX, 5.0))
        h3_index.update(_disaggregate_r8_to_r9(hex2, 5.0))

        p1 = _FakePartner("P1", _RES8_CENTER_LAT, _RES8_CENTER_LON, radius=2000)
        p2 = _FakePartner("P2", lat2, lon2, radius=2000)

        covered = _build_coverage_index([p1, p2], h3_index)

        for child in _RES9_CHILDREN:
            assert child in covered
        for child in children2:
            assert child in covered

    def test_exclude_one_of_two_partners(self):
        """Excluding P1 still leaves P2's coverage intact."""
        hex2 = "88a8100c0bfffff"
        lat2, lon2 = h3.cell_to_latlng(hex2)
        children2 = list(h3.cell_to_children(hex2, 9))

        h3_index = {}
        h3_index.update(_disaggregate_r8_to_r9(_RES8_HEX, 5.0))
        h3_index.update(_disaggregate_r8_to_r9(hex2, 5.0))

        p1 = _FakePartner("P1", _RES8_CENTER_LAT, _RES8_CENTER_LON, radius=2000)
        p2 = _FakePartner("P2", lat2, lon2, radius=2000)

        covered = _build_coverage_index([p1, p2], h3_index, exclude_partner_id="P1")

        # P2's children should still be covered
        for child in children2:
            assert child in covered

    def test_empty_h3_index_returns_empty_set(self):
        partner = _FakePartner("P1", _RES8_CENTER_LAT, _RES8_CENTER_LON, radius=2000)
        covered = _build_coverage_index([partner], {})
        assert covered == set()

    def test_only_hexes_within_radius_are_covered(self):
        """Hexes beyond the partner radius must NOT be in the coverage set.
        Use a far-away partner so none of the res-9 children are within radius."""
        h3_index = self._h3_index_from_hex(_RES8_HEX, density=10.0)

        # Place partner far away (Tokyo) — no São Paulo hex should be within 500 m
        partner = _FakePartner("P1", lat=35.6762, lon=139.6503, radius=500)
        covered = _build_coverage_index([partner], h3_index)
        assert len(covered) == 0
