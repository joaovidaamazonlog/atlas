"""
classifier.py
=============
Classifica H3_Cells usando pipeline UMAP → HDBSCAN (com fallback KMeans k=6) e,
quando dados rotulados suficientes estiverem disponíveis, treina um
modelo supervisionado (Random Forest ou XGBoost).

Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7, 9.1, 9.2, 9.3, 9.4, 9.5
"""

from __future__ import annotations

import glob
import logging
import os
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

import joblib
import numpy as np
from sklearn.cluster import KMeans
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score, f1_score, precision_score, recall_score
from sklearn.preprocessing import LabelEncoder

try:
    import hdbscan as hdbscan_lib
    _HDBSCAN_AVAILABLE = True
except ImportError:
    _HDBSCAN_AVAILABLE = False

try:
    from sklearn.metrics import silhouette_score as _silhouette_score
    _SILHOUETTE_AVAILABLE = True
except ImportError:
    _SILHOUETTE_AVAILABLE = False

try:
    import umap as umap_lib
    _UMAP_AVAILABLE = True
except ImportError:
    _UMAP_AVAILABLE = False

try:
    import matplotlib
    matplotlib.use("Agg")  # non-interactive backend
    import matplotlib.pyplot as plt
    _MATPLOTLIB_AVAILABLE = True
except ImportError:
    _MATPLOTLIB_AVAILABLE = False

from geo_intelligence.geo_config import (
    UMAP_N_COMPONENTS, UMAP_N_NEIGHBORS, UMAP_MIN_DIST, UMAP_RANDOM_STATE,
    SEMANTIC_ANCHORS,
)
from geo_intelligence.phase1_area_intelligence.feature_engineer import NUMERIC_FEATURES
from geo_intelligence.pipeline import H3CellFeatures, RegionType

logger = logging.getLogger(__name__)

LOW_CONFIDENCE_THRESHOLD = 0.5
SILHOUETTE_ALERT_THRESHOLD = 0.2
KMEANS_FALLBACK_K = 6
HDBSCAN_MIN_CLUSTER_THRESHOLD = 3
MAX_MODELS_PER_STATION = 3
SUPERVISED_MIN_SAMPLES_PER_CLASS = 50

_DEFAULT_REGION_TYPES: list[RegionType] = list(RegionType)


@dataclass
class CellClassification:
    h3_id: str
    region_type: RegionType
    model_confidence: float
    low_confidence: bool


def _build_feature_matrix(cells: list[H3CellFeatures]) -> np.ndarray:
    return np.array(
        [[float(getattr(c, f) or 0.0) for f in NUMERIC_FEATURES] for c in cells],
        dtype=np.float64,
    )


def _map_cluster_to_region(
    cluster_id: int,
    cluster_to_region_map: dict[int, str] | None,
    unique_cluster_ids: list[int],
) -> RegionType:
    if cluster_to_region_map and cluster_id in cluster_to_region_map:
        try:
            return RegionType(cluster_to_region_map[cluster_id])
        except ValueError:
            pass
    if cluster_id == -1:
        return _DEFAULT_REGION_TYPES[0]
    try:
        idx = unique_cluster_ids.index(cluster_id) % len(_DEFAULT_REGION_TYPES)
        return _DEFAULT_REGION_TYPES[idx]
    except ValueError:
        return _DEFAULT_REGION_TYPES[0]


def _compute_silhouette(X: np.ndarray, labels: np.ndarray) -> Optional[float]:
    if not _SILHOUETTE_AVAILABLE or len(set(labels)) < 2:
        return None
    try:
        return float(_silhouette_score(X, labels))
    except Exception:
        return None


def _confidence_from_distances(X: np.ndarray, labels: np.ndarray) -> np.ndarray:
    confidences = np.zeros(len(X), dtype=np.float64)
    for lbl in set(labels):
        mask = labels == lbl
        pts = X[mask]
        centroid = pts.mean(axis=0)
        dists = np.linalg.norm(pts - centroid, axis=1)
        max_dist = dists.max()
        confidences[mask] = 1.0 if max_dist == 0.0 else 1.0 - (dists / max_dist)
    return confidences


def _purge_old_models(models_dir: str, pattern: str) -> None:
    existing = sorted(glob.glob(os.path.join(models_dir, pattern)))
    for oldest in existing[:-MAX_MODELS_PER_STATION]:
        try:
            os.remove(oldest)
        except OSError:
            pass


def _persist_model(model: object, station_code: str, models_dir: str) -> str:
    os.makedirs(models_dir, exist_ok=True)
    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    path = os.path.join(models_dir, f"{station_code}_{ts}.joblib")
    joblib.dump(model, path)
    logger.info("Model persisted: %s", path)
    # Purge old supervised models (exclude umap_ prefixed ones)
    _purge_old_models(models_dir, f"{station_code}_[0-9]*.joblib")
    return path


def _persist_umap_model(umap_model: object, station_code: str, models_dir: str) -> str:
    """Saves UMAP model as {station_code}_umap_{timestamp}.joblib, keeps max 3."""
    os.makedirs(models_dir, exist_ok=True)
    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    path = os.path.join(models_dir, f"{station_code}_umap_{ts}.joblib")
    joblib.dump(umap_model, path)
    logger.info("UMAP model persisted: %s", path)
    # Purge old UMAP models (keep max 3)
    _purge_old_models(models_dir, f"{station_code}_umap_*.joblib")
    return path


def _persist_umap_scatter(
    embedding: np.ndarray,
    labels: np.ndarray,
    station_code: str,
    models_dir: str,
) -> Optional[str]:
    """Saves scatter plot as {station_code}_umap_scatter_{timestamp}.png, keeps max 3."""
    if not _MATPLOTLIB_AVAILABLE:
        logger.warning("matplotlib not available; skipping UMAP scatter plot.")
        return None
    os.makedirs(models_dir, exist_ok=True)
    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    path = os.path.join(models_dir, f"{station_code}_umap_scatter_{ts}.png")
    try:
        fig, ax = plt.subplots(figsize=(8, 6))
        unique_labels = sorted(set(labels.tolist()))
        cmap = plt.get_cmap("tab10")
        for i, lbl in enumerate(unique_labels):
            mask = labels == lbl
            color = "gray" if lbl == -1 else cmap(i % 10)
            label_str = "noise" if lbl == -1 else f"cluster {lbl}"
            ax.scatter(embedding[mask, 0], embedding[mask, 1], c=[color], label=label_str, s=10, alpha=0.7)
        ax.set_title(f"UMAP Embedding — {station_code}")
        ax.set_xlabel("UMAP-1")
        ax.set_ylabel("UMAP-2")
        ax.legend(markerscale=2, fontsize=8)
        fig.tight_layout()
        fig.savefig(path, dpi=100)
        plt.close(fig)
        logger.info("UMAP scatter plot saved: %s", path)
    except Exception as exc:
        logger.warning("Failed to save UMAP scatter plot: %s", exc)
        return None
    # Purge old scatter plots (keep max 3)
    _purge_old_models(models_dir, f"{station_code}_umap_scatter_*.png")
    return path


def _apply_semantic_anchors(
    h3_ids: list[str],
    labels: np.ndarray,
    station_code: str,
    semantic_anchors: dict,
) -> dict[int, RegionType]:
    """Maps cluster IDs to RegionType using semantic anchor hex IDs.

    For each anchor {region_name: hex_id} in semantic_anchors.get(station_code, {}),
    finds which cluster the anchor hex belongs to, then maps cluster_id → RegionType.
    """
    result: dict[int, RegionType] = {}
    station_anchors = semantic_anchors.get(station_code, {})
    if not station_anchors:
        return result
    h3_to_idx = {h: i for i, h in enumerate(h3_ids)}
    for region_name, anchor_hex in station_anchors.items():
        idx = h3_to_idx.get(anchor_hex)
        if idx is None:
            logger.warning(
                "Semantic anchor hex '%s' for region '%s' not found in cells for station '%s'.",
                anchor_hex, region_name, station_code,
            )
            continue
        cluster_id = int(labels[idx])
        if cluster_id == -1:
            logger.warning(
                "Semantic anchor hex '%s' was assigned to noise cluster (-1); skipping.",
                anchor_hex,
            )
            continue
        try:
            result[cluster_id] = RegionType(region_name)
        except ValueError:
            logger.warning(
                "Region name '%s' from semantic anchor is not a valid RegionType; skipping.",
                region_name,
            )
    return result


def _train_supervised(X, h3_ids, labeled_data, use_xgboost):
    indices, y_raw = zip(*[(i, labeled_data[h]) for i, h in enumerate(h3_ids) if h in labeled_data]) if any(h in labeled_data for h in h3_ids) else ([], [])
    if not indices:
        return None
    X_train = X[list(indices)]
    le = LabelEncoder()
    y_train = le.fit_transform(list(y_raw))
    _, counts = np.unique(y_train, return_counts=True)
    if counts.min() < SUPERVISED_MIN_SAMPLES_PER_CLASS:
        return None

    if use_xgboost:
        try:
            from xgboost import XGBClassifier
            model = XGBClassifier(n_estimators=100, use_label_encoder=False, eval_metric="mlogloss", random_state=42)
            model_name = "xgboost"
        except ImportError:
            model = RandomForestClassifier(n_estimators=100, random_state=42)
            model_name = "random_forest"
    else:
        model = RandomForestClassifier(n_estimators=100, random_state=42)
        model_name = "random_forest"

    model.fit(X_train, y_train)
    y_pred = model.predict(X_train)
    labels_list = list(range(len(le.classes_)))
    per_class = {
        cls: {
            "precision": float(precision_score(y_train, y_pred, labels=labels_list, average=None, zero_division=0)[i]),
            "recall": float(recall_score(y_train, y_pred, labels=labels_list, average=None, zero_division=0)[i]),
            "f1": float(f1_score(y_train, y_pred, labels=labels_list, average=None, zero_division=0)[i]),
        }
        for i, cls in enumerate(le.classes_)
    }
    metrics = {
        "model": model_name,
        "accuracy": float(accuracy_score(y_train, y_pred)),
        "f1_macro": float(f1_score(y_train, y_pred, average="macro", zero_division=0)),
        "per_class": per_class,
    }
    return model, le, metrics


def classify_cells(
    cells: list[H3CellFeatures],
    station_code: str,
    models_dir: str = "models",
    labeled_data: dict[str, str] | None = None,
    cluster_to_region_map: dict[int, str] | None = None,
    use_xgboost: bool = False,
    partner_profiles: list | None = None,  # list[PartnerProfile] to fill umap_embedding
) -> tuple[list[CellClassification], dict, object | None]:
    """Classifies H3 cells using UMAP → HDBSCAN pipeline.

    Returns (classifications, metrics_dict, umap_model).
    umap_model is None when UMAP is unavailable or cells is empty.
    """
    if not cells:
        return [], {"algorithm": "none", "silhouette_score": None}, None

    X = _build_feature_matrix(cells)
    h3_ids = [c.h3_id for c in cells]
    n = len(cells)

    # --- UMAP dimensionality reduction ---
    umap_model = None
    embedding = X  # fallback: use raw features if UMAP unavailable

    umap_params = {
        "n_components": UMAP_N_COMPONENTS,
        "n_neighbors": UMAP_N_NEIGHBORS,
        "min_dist": UMAP_MIN_DIST,
        "random_state": UMAP_RANDOM_STATE,
        "metric": "euclidean",
    }

    if _UMAP_AVAILABLE:
        try:
            umap_model = umap_lib.UMAP(
                n_components=UMAP_N_COMPONENTS,
                n_neighbors=UMAP_N_NEIGHBORS,
                min_dist=UMAP_MIN_DIST,
                random_state=UMAP_RANDOM_STATE,
                metric="euclidean",
            )
            embedding = umap_model.fit_transform(X)
            _persist_umap_model(umap_model, station_code, models_dir)
        except Exception as exc:
            logger.warning("UMAP failed (%s); falling back to raw features for clustering.", exc)
            umap_model = None
            embedding = X
    else:
        logger.warning("umap-learn not installed; running HDBSCAN directly on feature matrix.")

    # --- Clustering on embedding (or raw X if UMAP unavailable) ---
    algorithm = "hdbscan"
    if _HDBSCAN_AVAILABLE:
        clusterer = hdbscan_lib.HDBSCAN(min_cluster_size=max(5, n // 20))
        labels = clusterer.fit_predict(embedding)
        unique_clusters = [l for l in set(labels) if l != -1]
        if len(unique_clusters) < HDBSCAN_MIN_CLUSTER_THRESHOLD:
            logger.warning(
                "HDBSCAN produced %d cluster(s); falling back to KMeans k=%d.",
                len(unique_clusters), KMEANS_FALLBACK_K,
            )
            algorithm = "kmeans_fallback"
            labels = KMeans(n_clusters=KMEANS_FALLBACK_K, random_state=42, n_init="auto").fit_predict(embedding)
    else:
        algorithm = "kmeans_fallback"
        labels = KMeans(n_clusters=KMEANS_FALLBACK_K, random_state=42, n_init="auto").fit_predict(embedding)

    # --- Silhouette score on embedding ---
    sil_score = _compute_silhouette(embedding, labels)
    low_quality_clustering = False
    if sil_score is not None and sil_score < SILHOUETTE_ALERT_THRESHOLD:
        logger.warning(
            "Silhouette score %.3f below threshold for station %s.", sil_score, station_code
        )
        low_quality_clustering = True

    # --- Persist scatter plot ---
    if umap_model is not None:
        _persist_umap_scatter(embedding, labels, station_code, models_dir)

    # --- Semantic anchors ---
    anchor_map = _apply_semantic_anchors(h3_ids, labels, station_code, SEMANTIC_ANCHORS)
    # Merge anchor_map into cluster_to_region_map (anchor_map takes precedence)
    effective_region_map: dict[int, str] | None = None
    if anchor_map or cluster_to_region_map:
        effective_region_map = {}
        if cluster_to_region_map:
            effective_region_map.update(cluster_to_region_map)
        # anchor_map values are RegionType enums; convert to str for _map_cluster_to_region
        for cid, rt in anchor_map.items():
            effective_region_map[cid] = rt.value

    # --- Supervised training (still on raw X) ---
    supervised_result = _train_supervised(X, h3_ids, labeled_data, use_xgboost) if labeled_data else None
    if supervised_result:
        _persist_model(supervised_result[0], station_code, models_dir)

    unique_cluster_ids = sorted(set(labels.tolist()))
    n_clusters = len([c for c in unique_cluster_ids if c != -1])
    classifications: list[CellClassification] = []

    if supervised_result:
        sup_model, label_enc, _ = supervised_result
        proba = sup_model.predict_proba(X)
        pred_labels = label_enc.inverse_transform(proba.argmax(axis=1))
        confidences = proba.max(axis=1)
        for i, cell in enumerate(cells):
            try:
                rt = RegionType(pred_labels[i])
            except ValueError:
                rt = _DEFAULT_REGION_TYPES[0]
            conf = float(confidences[i])
            classifications.append(CellClassification(cell.h3_id, rt, conf, conf < LOW_CONFIDENCE_THRESHOLD))
    else:
        confidences = _confidence_from_distances(embedding, labels)
        for i, cell in enumerate(cells):
            rt = _map_cluster_to_region(int(labels[i]), effective_region_map, unique_cluster_ids)
            conf = float(confidences[i])
            classifications.append(CellClassification(cell.h3_id, rt, conf, conf < LOW_CONFIDENCE_THRESHOLD))

    # --- Fill umap_embedding on PartnerProfiles ---
    if umap_model is not None and partner_profiles:
        try:
            from geo_intelligence.pipeline import PartnerProfile
            for pp in partner_profiles:
                if not isinstance(pp, PartnerProfile):
                    continue
                if not pp.features:
                    continue
                try:
                    feat_vec = np.array(
                        [float(pp.features.get(f, 0.0) or 0.0) for f in NUMERIC_FEATURES],
                        dtype=np.float64,
                    ).reshape(1, -1)
                    emb = umap_model.transform(feat_vec)
                    pp.umap_embedding = emb[0].tolist()
                except Exception as exc:
                    logger.warning("Failed to compute UMAP embedding for partner %s: %s", pp.salesforce_id, exc)
        except ImportError:
            pass

    metrics: dict = {
        "algorithm": algorithm,
        "silhouette_score": sil_score,
        "umap_params": umap_params if umap_model is not None else None,
        "n_clusters": n_clusters,
        "low_quality_clustering": low_quality_clustering,
    }
    if supervised_result:
        metrics["supervised_metrics"] = supervised_result[2]

    return classifications, metrics, umap_model
