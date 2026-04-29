"""
test_daily_satellite_heatmap.py
================================
Integration tests for the satellite-aware heatmap writer.

Scope
-----
Exercises ``vanilla.phase5_reports.write_heatmap_unified`` directly on a
minimal-but-realistic fixture that combines two canonical territories
(DSA8, DRJ3) and one satellite territory (XBA1 anchored on DSA8).

The full ``run_daily`` pipeline depends on many external artifacts
(Excel export, Salesforce partners, jurisdiction GeoJSON, CP-SAT solver,
webleads, CNPJ DB) and is therefore impractical to exercise end-to-end
inside pytest. Instead, these tests target the single surface that
implements the satellite-aware requirements: the unified heatmap writer.

Validates
---------
- Req 2.1, 2.2 — ``delivery_station`` on every hex reflects the ORIGINAL
  station code (canonical or satellite) of the owning territory.
- Req 2.3, 2.4 — no duplicate ``hex_id`` features and no orphan
  ``territory_id`` (every feature maps back to ``territories.territory_index``).
- Req 3.1, 3.4 — demand is isolated per station (satellite demand never
  leaks into canonical features and vice-versa).
- Req 5.4 — the writer is idempotent: calling it twice on the same
  input produces byte-identical feature arrays.
- Invariant guard — a duplicated hex in two territories raises
  ``ValueError`` naming both territories.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Dict, List, Tuple

import h3
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from shared.load_packages import PackageData
from shared.models import Allocation, PartnerMetrics, TerritoriesResult
from vanilla.phase3_partner_fit import FitResult, TerritoryFit
from vanilla.phase5_reports import write_heatmap_unified


# ---------------------------------------------------------------------------
# Geographic seed points. Using real H3 res-9 cells around Salvador/BA
# (DSA8 + XBA1 satellite) and Rio de Janeiro/RJ (DRJ3).
# ---------------------------------------------------------------------------

# Salvador — DSA8 canonical (3 hexes around the base)
_DSA8_SEEDS: List[Tuple[float, float]] = [
    (-12.910062, -38.460637),   # DSA8 HQ
    (-12.915000, -38.465000),
    (-12.905000, -38.455000),
]

# XBA1 satellite — geographically offset from DSA8 (around Feira de Santana)
_XBA1_SEEDS: List[Tuple[float, float]] = [
    (-12.265000, -38.965000),
    (-12.270000, -38.970000),
]

# Rio de Janeiro — DRJ3 canonical (2 hexes)
_DRJ3_SEEDS: List[Tuple[float, float]] = [
    (-22.940029, -43.377363),
    (-22.945000, -43.380000),
]


def _cells(seeds: List[Tuple[float, float]]) -> List[str]:
    return [h3.latlng_to_cell(lat, lon, 9) for lat, lon in seeds]


# ---------------------------------------------------------------------------
# Fixture builder
# ---------------------------------------------------------------------------


@pytest.fixture
def satellite_fixture():
    """
    Builds a minimal TerritoriesResult + PackageData + FitResult triple
    with:
      - DSA8_bucket-01    → canonical, 3 hex_ids, canonical_base=None
      - XBA1_bucket-01    → satellite of DSA8, 2 hex_ids, canonical_base="DSA8"
      - DRJ3_bucket-01    → canonical, 2 hex_ids, canonical_base=None

    Demand is explicitly disjoint between stations so isolation leaks
    are unambiguously detectable.
    """
    dsa8_hexes = _cells(_DSA8_SEEDS)
    xba1_hexes = _cells(_XBA1_SEEDS)
    drj3_hexes = _cells(_DRJ3_SEEDS)

    # Ensure no H3 collisions between the three seed sets.
    all_hexes = dsa8_hexes + xba1_hexes + drj3_hexes
    assert len(set(all_hexes)) == len(all_hexes), (
        "Seed points produced overlapping H3 cells — adjust seeds."
    )

    territory_index: Dict[str, dict] = {
        "DSA8_bucket-01": {
            "territory_id":   "DSA8_bucket-01",
            "station_code":   "DSA8",
            "canonical_base": None,
            "hex_ids":        list(dsa8_hexes),
            "bdm_cluster":    "RJ/CW",
        },
        "XBA1_bucket-01": {
            "territory_id":   "XBA1_bucket-01",
            "station_code":   "DSA8",   # remapped in memory (as in real load)
            "canonical_base": "DSA8",
            "hex_ids":        list(xba1_hexes),
            "bdm_cluster":    "RJ/CW",
        },
        "DRJ3_bucket-01": {
            "territory_id":   "DRJ3_bucket-01",
            "station_code":   "DRJ3",
            "canonical_base": None,
            "hex_ids":        list(drj3_hexes),
            "bdm_cluster":    "RJ/CW",
        },
    }

    hex_to_territory: Dict[str, str] = {}
    for tid, meta in territory_index.items():
        for h in meta["hex_ids"]:
            hex_to_territory[h] = tid

    territories = TerritoriesResult(
        territory_index=territory_index,
        hex_to_territory=hex_to_territory,
    )

    # Disjoint demand per station. Satellite demand values (10, 20) are
    # chosen so that leakage into DSA8 is trivially detectable.
    pkg = PackageData(
        demand_by_station={
            "DSA8": {
                dsa8_hexes[0]: 100,
                dsa8_hexes[1]: 200,
                dsa8_hexes[2]: 300,
            },
            "XBA1": {
                xba1_hexes[0]: 10,
                xba1_hexes[1]: 20,
            },
            "DRJ3": {
                drj3_hexes[0]: 50,
                drj3_hexes[1]: 60,
            },
        },
        hex_to_base={},
        hex_to_ceps={},
        days=30,
    )

    # FitResult with one partner per canonical territory that allocates
    # some hexes (so `covering_partners` is non-empty for those hexes).
    dsa8_partner = PartnerMetrics(
        origin_hex=dsa8_hexes[0],
        station_code="DSA8",
        radius_s=500,
        capacity_s=42,
        entity_type="EXISTING",
        status="Active",
        salesforce_id="sfid_dsa8_partner",
        partner_name="DSA8 Partner",
        matched_slot_id="DSA8_bucket-01_slot-01",
        allocations=[
            Allocation(hex_id=dsa8_hexes[0], packages_assigned=50),
            Allocation(hex_id=dsa8_hexes[1], packages_assigned=100),
        ],
    )
    drj3_partner = PartnerMetrics(
        origin_hex=drj3_hexes[0],
        station_code="DRJ3",
        radius_s=500,
        capacity_s=42,
        entity_type="EXISTING",
        status="Active",
        salesforce_id="sfid_drj3_partner",
        partner_name="DRJ3 Partner",
        matched_slot_id="DRJ3_bucket-01_slot-01",
        allocations=[
            Allocation(hex_id=drj3_hexes[0], packages_assigned=25),
        ],
    )

    fit = FitResult(
        territories={
            "DSA8_bucket-01": TerritoryFit(
                territory_id="DSA8_bucket-01",
                station_code="DSA8",
                bdm_cluster="RJ/CW",
                ctl_name="Test CTL",
                slots=[],
                partners=[dsa8_partner],
            ),
            "XBA1_bucket-01": TerritoryFit(
                territory_id="XBA1_bucket-01",
                station_code="DSA8",
                bdm_cluster="RJ/CW",
                ctl_name="Test CTL",
                slots=[],
                partners=[],
            ),
            "DRJ3_bucket-01": TerritoryFit(
                territory_id="DRJ3_bucket-01",
                station_code="DRJ3",
                bdm_cluster="RJ/CW",
                ctl_name="Test CTL",
                slots=[],
                partners=[drj3_partner],
            ),
        }
    )

    return {
        "territories":  territories,
        "pkg":          pkg,
        "fit":          fit,
        "dsa8_hexes":   dsa8_hexes,
        "xba1_hexes":   xba1_hexes,
        "drj3_hexes":   drj3_hexes,
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _load_features(path: Path) -> List[dict]:
    with open(path, "r", encoding="utf-8") as f:
        geojson = json.load(f)
    assert geojson["type"] == "FeatureCollection"
    return geojson["features"]


# ---------------------------------------------------------------------------
# Test A — Req 2.1, 2.2
# ---------------------------------------------------------------------------


def test_write_heatmap_unified_satellite_delivery_station(
    tmp_path: Path, satellite_fixture
) -> None:
    """Every feature exposes the ORIGINAL station code and correct canonical_base."""
    path = write_heatmap_unified(
        tmp_path,
        satellite_fixture["territories"],
        satellite_fixture["pkg"],
        satellite_fixture["fit"],
    )
    features = _load_features(path)

    xba1_features = [
        f for f in features if f["properties"]["territory_id"].startswith("XBA1_")
    ]
    dsa8_features = [
        f for f in features if f["properties"]["territory_id"].startswith("DSA8_")
    ]

    assert xba1_features, "Satellite territory produced no features"
    assert dsa8_features, "Canonical territory produced no features"

    for f in xba1_features:
        props = f["properties"]
        assert props["delivery_station"] == "XBA1", (
            f"Satellite feature has wrong delivery_station: {props}"
        )
        assert props["canonical_base"] == "DSA8", (
            f"Satellite feature missing canonical_base=DSA8: {props}"
        )

    for f in dsa8_features:
        props = f["properties"]
        assert props["delivery_station"] == "DSA8", (
            f"Canonical feature has wrong delivery_station: {props}"
        )
        assert props["canonical_base"] is None, (
            f"Canonical feature should have canonical_base=None: {props}"
        )


# ---------------------------------------------------------------------------
# Test B — Req 2.3, 2.4
# ---------------------------------------------------------------------------


def test_write_heatmap_unified_no_duplicates_or_orphans(
    tmp_path: Path, satellite_fixture
) -> None:
    """No duplicate hex_id and every territory_id references a known territory."""
    path = write_heatmap_unified(
        tmp_path,
        satellite_fixture["territories"],
        satellite_fixture["pkg"],
        satellite_fixture["fit"],
    )
    features = _load_features(path)

    hex_ids = [f["properties"]["hex_id"] for f in features]
    assert len(set(hex_ids)) == len(features), (
        f"Duplicate hex_ids detected: {len(hex_ids) - len(set(hex_ids))} duplicates"
    )

    territory_index = satellite_fixture["territories"].territory_index
    for f in features:
        tid = f["properties"]["territory_id"]
        assert tid in territory_index, f"Orphan territory_id in heatmap: {tid}"


# ---------------------------------------------------------------------------
# Test C — Req 3.1, 3.4
# ---------------------------------------------------------------------------


def test_write_heatmap_unified_demand_isolation(
    tmp_path: Path, satellite_fixture
) -> None:
    """
    Satellite demand (10, 20) never appears on canonical features and vice-versa.
    """
    path = write_heatmap_unified(
        tmp_path,
        satellite_fixture["territories"],
        satellite_fixture["pkg"],
        satellite_fixture["fit"],
    )
    features = _load_features(path)

    xba1_demand_values = {
        f["properties"]["demand_total"]
        for f in features
        if f["properties"]["territory_id"].startswith("XBA1_")
    }
    dsa8_demand_values = {
        f["properties"]["demand_total"]
        for f in features
        if f["properties"]["territory_id"].startswith("DSA8_")
    }

    assert xba1_demand_values == {10, 20}, (
        f"XBA1 features have unexpected demand_total values: {xba1_demand_values}"
    )
    assert dsa8_demand_values == {100, 200, 300}, (
        f"DSA8 features have unexpected demand_total values: {dsa8_demand_values}"
    )

    # Explicit leakage check: no DSA8 feature ever shows satellite-only demand.
    leaked = {10, 20} & dsa8_demand_values
    assert not leaked, f"Satellite demand leaked into canonical: {leaked}"


# ---------------------------------------------------------------------------
# Test D — Req 5.4
# ---------------------------------------------------------------------------


def test_write_heatmap_unified_idempotence(
    tmp_path: Path, satellite_fixture
) -> None:
    """Two runs on the same inputs yield identical feature arrays."""
    out_a = tmp_path / "run_a"
    out_b = tmp_path / "run_b"
    out_a.mkdir()
    out_b.mkdir()

    path_a = write_heatmap_unified(
        out_a,
        satellite_fixture["territories"],
        satellite_fixture["pkg"],
        satellite_fixture["fit"],
    )
    path_b = write_heatmap_unified(
        out_b,
        satellite_fixture["territories"],
        satellite_fixture["pkg"],
        satellite_fixture["fit"],
    )

    features_a = sorted(
        _load_features(path_a), key=lambda f: f["properties"]["hex_id"]
    )
    features_b = sorted(
        _load_features(path_b), key=lambda f: f["properties"]["hex_id"]
    )

    # Compare features only — the metadata block holds a generated_at
    # timestamp that is expected to differ between invocations.
    assert features_a == features_b, (
        "Heatmap feature arrays differ between runs — writer is not idempotent."
    )


# ---------------------------------------------------------------------------
# Test E — Invariant guard
# ---------------------------------------------------------------------------


def test_write_heatmap_unified_unrelated_duplicate_hex_raises(tmp_path: Path) -> None:
    """
    Hex shared by two UNRELATED canonicals aborts the writer naming both tids.

    (Duplicatas canônica↔satélite anexada NÃO abortam — a satélite vence
    a canônica e a canônica pula o hex com WARN; essa regra é validada
    em test_write_heatmap_unified_canonical_satellite_duplicate_sat_wins.)
    """
    shared_hex = h3.latlng_to_cell(-12.910062, -38.460637, 9)
    other_dsa8 = h3.latlng_to_cell(-12.915000, -38.465000, 9)
    other_drj3 = h3.latlng_to_cell(-22.945000, -43.380000, 9)

    territory_index: Dict[str, dict] = {
        "DSA8_bucket-01": {
            "territory_id":   "DSA8_bucket-01",
            "station_code":   "DSA8",
            "canonical_base": None,
            "hex_ids":        [shared_hex, other_dsa8],
        },
        "DRJ3_bucket-01": {
            "territory_id":   "DRJ3_bucket-01",
            "station_code":   "DRJ3",
            "canonical_base": None,
            "hex_ids":        [shared_hex, other_drj3],   # same hex, unrelated → raise
        },
    }

    territories = TerritoriesResult(
        territory_index=territory_index,
        hex_to_territory={},
    )
    pkg = PackageData(
        demand_by_station={"DSA8": {}, "DRJ3": {}},
        hex_to_base={},
        hex_to_ceps={},
        days=1,
    )
    fit = FitResult(territories={})

    with pytest.raises(ValueError) as exc_info:
        write_heatmap_unified(tmp_path, territories, pkg, fit)

    msg = str(exc_info.value)
    assert "DSA8_bucket-01" in msg, f"Error should name DSA8_bucket-01: {msg}"
    assert "DRJ3_bucket-01" in msg, f"Error should name DRJ3_bucket-01: {msg}"


# ---------------------------------------------------------------------------
# Test F — Regra "satélite vence canônica" em duplicatas relacionadas
# ---------------------------------------------------------------------------


def test_write_heatmap_unified_canonical_satellite_duplicate_sat_wins(
    tmp_path: Path,
) -> None:
    """
    Quando o mesmo hex está em hex_ids de uma canônica e de sua satélite
    anexada (cenário real de setup em duas passadas separadas), a feature
    é atribuída à satélite e a canônica pula aquele hex com WARN — não
    aborta.
    """
    shared_hex = h3.latlng_to_cell(-12.910062, -38.460637, 9)
    only_dsa8 = h3.latlng_to_cell(-12.915000, -38.465000, 9)
    only_xba1 = h3.latlng_to_cell(-12.270000, -38.970000, 9)

    territory_index: Dict[str, dict] = {
        "DSA8_bucket-01": {
            "territory_id":   "DSA8_bucket-01",
            "station_code":   "DSA8",
            "canonical_base": None,
            "hex_ids":        [shared_hex, only_dsa8],
        },
        "XBA1_bucket-01": {
            "territory_id":   "XBA1_bucket-01",
            "station_code":   "DSA8",
            "canonical_base": "DSA8",
            "hex_ids":        [shared_hex, only_xba1],
        },
    }

    territories = TerritoriesResult(
        territory_index=territory_index,
        hex_to_territory={},
    )
    pkg = PackageData(
        demand_by_station={"DSA8": {only_dsa8: 50}, "XBA1": {shared_hex: 10, only_xba1: 20}},
        hex_to_base={},
        hex_to_ceps={},
        days=1,
    )
    fit = FitResult(territories={})

    # Não deve levantar.
    path = write_heatmap_unified(tmp_path, territories, pkg, fit)
    features = _load_features(path)

    # Deve ter exatamente 3 features (shared_hex, only_dsa8, only_xba1),
    # nenhuma duplicata.
    assert len(features) == 3, (
        f"Esperado 3 features (sem duplicata do shared_hex), obtido {len(features)}"
    )
    hex_ids = [f["properties"]["hex_id"] for f in features]
    assert len(set(hex_ids)) == 3, f"hex_ids duplicados: {hex_ids}"

    # O shared_hex deve estar atribuído à satélite XBA1, não à canônica DSA8.
    shared_feat = next(f for f in features if f["properties"]["hex_id"] == shared_hex)
    assert shared_feat["properties"]["territory_id"] == "XBA1_bucket-01", (
        f"shared_hex deveria pertencer à satélite, obtido: "
        f"{shared_feat['properties']['territory_id']}"
    )
    assert shared_feat["properties"]["delivery_station"] == "XBA1"
    assert shared_feat["properties"]["canonical_base"] == "DSA8"
