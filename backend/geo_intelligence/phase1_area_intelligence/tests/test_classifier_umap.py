"""
test_classifier_umap.py
=======================
Unit tests for KMeans fallback and semantic anchors in classifier.py.

Requirements: 4.4, 4.5
"""

from __future__ import annotations

import contextlib
import sys
import types
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

# ---------------------------------------------------------------------------
# Real H3 cells at res 8 in São Paulo area
# ---------------------------------------------------------------------------

SAO_PAULO_HEXES = [
    "88a8a06a41fffff",
    "88a8a06a43fffff",
    "88a8a06a45fffff",
    "88a8a06a47fffff",
    "88a8a06a49fffff",
    "88a8a06a4bfffff",
    "88a8a06a4dfffff",
    "88a8a06a4fffffff",
    "88a8a06a51fffff",
    "88a8a06a53fffff",
    "88a8a06a55fffff",
    "88a8a06a57fffff",
    "88a8a06a59fffff",
    "88a8a06a5bfffff",
    "88a8a06a5dfffff",
    "88a8a06a5fffffff",
    "88a8a06a61fffff",
    "88a8a06a63fffff",
    "88a8a06a65fffff",
    "88a8a06a67fffff",
]


def _make_cell(h3_id: str, seed: int = 0):
    """Create a minimal H3CellFeatures with non-null numeric values."""
    from geo_intelligence.pipeline import H3CellFeatures

    rng = np.random.default_rng(seed)
    vals = rng.random(24).tolist()

    return H3CellFeatures(
        h3_id=h3_id,
        company_density=vals[0],
        cnae_diversity_index=vals[1],
        target_business_density=vals[2],
        building_density=vals[3],
        avg_building_size_m2=vals[4],
        landuse_residential_ratio=vals[5],
        landuse_commercial_ratio=vals[6],
        poi_density=vals[7],
        road_connectivity_index=vals[8],
        avg_income=vals[9],
        population_density=vals[10],
        bars_restaurants_density=vals[11],
        churches_density=vals[12],
        schools_density=vals[13],
        dealerships_density=vals[14],
        petshops_density=vals[15],
        landuse_entropy=vals[16],
        road_centrality_index=vals[17],
        local_clustering_coefficient=vals[18],
        ndvi_mean=vals[19],
        urban_density_index=vals[20],
        built_up_ratio=vals[21],
        morphology_class=None,
        commercial_activity_index=vals[22],
        delivery_density_r8=vals[23],
    )


def _make_cells(n: int = 20) -> list:
    hexes = SAO_PAULO_HEXES[:n] if n <= len(SAO_PAULO_HEXES) else [
        f"88a8a06a{i:02x}fffff" for i in range(n)
    ]
    return [_make_cell(h, seed=i) for i, h in enumerate(hexes)]


# ---------------------------------------------------------------------------
# Dummy UMAP — returns fast 2D embeddings without real computation
# ---------------------------------------------------------------------------

class _DummyUMAP:
    def __init__(self, **kwargs):
        pass

    def fit_transform(self, X):
        return np.random.default_rng(42).random((len(X), 2))

    def transform(self, X):
        return np.random.default_rng(0).random((len(X), 2))


def _classify_with_mocks(
    cells,
    station_code,
    tmp_path,
    hdbscan_labels,
    semantic_anchors=None,
):
    """Run classify_cells with mocked UMAP and HDBSCAN.

    hdbscan_labels: np.ndarray of cluster labels to return from HDBSCAN.
    semantic_anchors: optional dict to patch SEMANTIC_ANCHORS.
    Returns (classifications, metrics, umap_model).
    """
    from geo_intelligence.phase1_area_intelligence.classifier import classify_cells

    mock_hdbscan_instance = MagicMock()
    mock_hdbscan_instance.fit_predict.return_value = hdbscan_labels
    mock_hdbscan_cls = MagicMock(return_value=mock_hdbscan_instance)

    dummy_umap_module = types.ModuleType("umap")
    dummy_umap_module.UMAP = _DummyUMAP

    patches = [
        patch.dict(sys.modules, {"umap": dummy_umap_module}),
        patch("geo_intelligence.phase1_area_intelligence.classifier._HDBSCAN_AVAILABLE", True),
        patch("geo_intelligence.phase1_area_intelligence.classifier._UMAP_AVAILABLE", True),
        patch(
            "geo_intelligence.phase1_area_intelligence.classifier.umap_lib",
            dummy_umap_module,
            create=True,
        ),
        patch(
            "geo_intelligence.phase1_area_intelligence.classifier.hdbscan_lib",
            create=True,
        ),
        patch(
            "geo_intelligence.phase1_area_intelligence.classifier._persist_umap_model",
            return_value=str(tmp_path / "umap.joblib"),
        ),
        patch(
            "geo_intelligence.phase1_area_intelligence.classifier._persist_umap_scatter",
            return_value=None,
        ),
    ]
    if semantic_anchors is not None:
        patches.append(
            patch(
                "geo_intelligence.phase1_area_intelligence.classifier.SEMANTIC_ANCHORS",
                semantic_anchors,
            )
        )

    with contextlib.ExitStack() as stack:
        entered = [stack.enter_context(p) for p in patches]
        # entered[4] is the hdbscan_lib mock
        mock_hdbscan_lib = entered[4]
        mock_hdbscan_lib.HDBSCAN = mock_hdbscan_cls

        return classify_cells(
            cells=cells,
            station_code=station_code,
            models_dir=str(tmp_path),
        )


# ---------------------------------------------------------------------------
# Test 1 — KMeans fallback when HDBSCAN returns < 3 clusters
# ---------------------------------------------------------------------------

class TestKMeansFallback:
    """Req 4.4: WHEN HDBSCAN produces < 3 clusters, KMeans k=6 SHALL be used."""

    def test_kmeans_fallback_when_hdbscan_returns_one_cluster(self, tmp_path):
        """Mock HDBSCAN to return only 1 cluster; verify metrics['algorithm'] == 'kmeans_fallback'."""
        cells = _make_cells(20)
        labels = np.zeros(len(cells), dtype=int)  # all in cluster 0

        classifications, metrics, _ = _classify_with_mocks(
            cells, "DSP_TEST", tmp_path, labels
        )

        assert metrics["algorithm"] == "kmeans_fallback", (
            f"Expected 'kmeans_fallback' but got '{metrics['algorithm']}'"
        )
        assert len(classifications) == len(cells)

    def test_kmeans_fallback_when_hdbscan_returns_two_clusters(self, tmp_path):
        """Exactly 2 clusters from HDBSCAN should also trigger KMeans fallback."""
        cells = _make_cells(20)
        labels = np.array([i % 2 for i in range(len(cells))], dtype=int)

        _, metrics, _ = _classify_with_mocks(cells, "DSP_TEST", tmp_path, labels)

        assert metrics["algorithm"] == "kmeans_fallback"

    def test_hdbscan_not_fallback_when_enough_clusters(self, tmp_path):
        """When HDBSCAN returns >= 3 clusters, algorithm should remain 'hdbscan'."""
        cells = _make_cells(20)
        labels = np.array([i % 4 for i in range(len(cells))], dtype=int)

        _, metrics, _ = _classify_with_mocks(cells, "DSP_TEST", tmp_path, labels)

        assert metrics["algorithm"] == "hdbscan"


# ---------------------------------------------------------------------------
# Test 2 — Semantic anchors name clusters correctly
# ---------------------------------------------------------------------------

class TestSemanticAnchors:
    """Req 4.5: Semantic anchors SHALL map cluster IDs to RegionType."""

    def test_apply_semantic_anchors_maps_cluster_to_region(self):
        """_apply_semantic_anchors maps anchor hex cluster to the correct RegionType."""
        from geo_intelligence.phase1_area_intelligence.classifier import _apply_semantic_anchors
        from geo_intelligence.pipeline import RegionType

        anchor_hex = SAO_PAULO_HEXES[3]  # index 3 → cluster 2 in labels below
        h3_ids = SAO_PAULO_HEXES[:10]
        labels = np.array([0, 1, 0, 2, 1, 0, 2, 1, 0, 1], dtype=int)

        result = _apply_semantic_anchors(
            h3_ids, labels, "DSP2", {"DSP2": {"comercial": anchor_hex}}
        )

        assert 2 in result, "Cluster 2 should be in the anchor map"
        assert result[2] == RegionType.COMERCIAL

    def test_semantic_anchors_via_classify_cells(self, tmp_path):
        """classify_cells uses semantic anchors to assign RegionType to the anchor hex."""
        from geo_intelligence.pipeline import RegionType

        anchor_hex = SAO_PAULO_HEXES[0]  # index 0 → cluster 0
        cells = _make_cells(20)
        labels = np.array([i % 4 for i in range(len(cells))], dtype=int)

        classifications, _, _ = _classify_with_mocks(
            cells,
            "DSP2",
            tmp_path,
            labels,
            semantic_anchors={"DSP2": {"comercial": anchor_hex}},
        )

        anchor_cls = next(c for c in classifications if c.h3_id == anchor_hex)
        assert anchor_cls.region_type == RegionType.COMERCIAL, (
            f"Expected COMERCIAL for anchor hex, got {anchor_cls.region_type}"
        )

    def test_semantic_anchor_missing_hex_is_skipped(self):
        """If anchor hex is not in h3_ids, it should be skipped gracefully."""
        from geo_intelligence.phase1_area_intelligence.classifier import _apply_semantic_anchors

        h3_ids = SAO_PAULO_HEXES[:5]
        labels = np.zeros(5, dtype=int)

        result = _apply_semantic_anchors(
            h3_ids, labels, "DSP2", {"DSP2": {"comercial": "88fffffffffffff"}}
        )
        assert result == {}

    def test_semantic_anchor_noise_cluster_is_skipped(self):
        """If anchor hex is in noise cluster (-1), it should be skipped."""
        from geo_intelligence.phase1_area_intelligence.classifier import _apply_semantic_anchors

        anchor_hex = SAO_PAULO_HEXES[1]
        h3_ids = SAO_PAULO_HEXES[:5]
        labels = np.array([-1, -1, 0, 1, 2], dtype=int)  # anchor at index 1 → noise

        result = _apply_semantic_anchors(
            h3_ids, labels, "DSP2", {"DSP2": {"comercial": anchor_hex}}
        )
        assert result == {}

    def test_semantic_anchor_invalid_region_name_is_skipped(self):
        """If anchor region name is not a valid RegionType, it should be skipped."""
        from geo_intelligence.phase1_area_intelligence.classifier import _apply_semantic_anchors

        anchor_hex = SAO_PAULO_HEXES[0]
        h3_ids = SAO_PAULO_HEXES[:5]
        labels = np.array([0, 1, 2, 0, 1], dtype=int)

        result = _apply_semantic_anchors(
            h3_ids, labels, "DSP2", {"DSP2": {"not_a_valid_region": anchor_hex}}
        )
        assert result == {}
