"""
profile_builder.py
==================
Builds Success and Failure reference profiles from historical partner data.

The Success_Profile is a tenure-weighted average of feature vectors for Active
partners.  The Failure_Profile is a weighted average for Exited partners whose
exit was caused by an area problem (exit_reason_class = "area_signal").

Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6
"""

from __future__ import annotations

import logging
import math
import os
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import h3
import numpy as np

from geo_intelligence.geo_config import LOW_COVERAGE_WARNING_PCT
from geo_intelligence.pipeline import PartnerProfile, ReferenceProfiles

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Package root — models/ directory lives here
# ---------------------------------------------------------------------------

_GEO_INTELLIGENCE_ROOT = Path(__file__).parent.parent
_MODELS_DIR = _GEO_INTELLIGENCE_ROOT / "models"


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _ensure_models_dir() -> Path:
    """Create the models/ directory if it does not exist."""
    _MODELS_DIR.mkdir(parents=True, exist_ok=True)
    return _MODELS_DIR


def _timestamp_str() -> str:
    """Return a compact UTC timestamp string suitable for filenames."""
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _purge_old_npy(models_dir: Path, station_code: str, vector_type: str, keep: int = 3) -> None:
    """
    Delete all but the *keep* most recent .npy files for a given
    station_code and vector_type (success | failure).
    """
    pattern = f"{station_code}_{vector_type}_*.npy"
    files = sorted(models_dir.glob(pattern))
    # sorted() on Path objects uses lexicographic order; because the timestamp
    # is ISO-like (YYYYMMDDTHHMMSSz) lexicographic == chronological.
    if len(files) > keep:
        for old_file in files[: len(files) - keep]:
            try:
                old_file.unlink()
                logger.debug("Purged old profile file: %s", old_file)
            except OSError as exc:
                logger.warning("Could not purge %s: %s", old_file, exc)


def _save_vector(
    vector: np.ndarray,
    station_code: str,
    vector_type: str,
    timestamp: str,
) -> Path:
    """
    Persist *vector* as a .npy file and purge older files for the same
    station/type, keeping only the 3 most recent.

    Returns the path of the saved file.
    """
    models_dir = _ensure_models_dir()
    filename = f"{station_code}_{vector_type}_{timestamp}.npy"
    filepath = models_dir / filename
    np.save(filepath, vector)
    logger.debug("Saved %s vector to %s", vector_type, filepath)
    _purge_old_npy(models_dir, station_code, vector_type, keep=3)
    return filepath


def _weighted_average(
    vectors: list[np.ndarray], weights: list[float]
) -> np.ndarray:
    """
    Compute a weighted average of *vectors* using *weights*.

    Returns a zero vector of the same shape if the total weight is zero.
    """
    total_weight = sum(weights)
    if total_weight == 0.0 or not vectors:
        return np.zeros_like(vectors[0]) if vectors else np.array([])
    stacked = np.stack(vectors, axis=0)          # (n, d)
    w = np.array(weights, dtype=float)           # (n,)
    return np.dot(w, stacked) / total_weight     # (d,)


def _compute_profile_coverage(
    partner_profiles: list[PartnerProfile],
    cells_features: dict[str, np.ndarray],
) -> float:
    """
    profile_coverage = |{h ∈ hexágonos : ∃ parceiro em grid_disk(h, 1)}| / |hexágonos|

    For each hex h in cells_features, check whether any partner's h3_id_r8
    falls within grid_disk(h, 1) (i.e. h itself or one of its 6 neighbours).
    """
    all_hexes = set(cells_features.keys())
    if not all_hexes:
        return 0.0

    partner_hexes = {p.h3_id_r8 for p in partner_profiles}

    covered = 0
    for h in all_hexes:
        try:
            neighborhood = set(h3.grid_disk(h, 1))
        except Exception:  # noqa: BLE001
            neighborhood = {h}
        if neighborhood & partner_hexes:
            covered += 1

    return covered / len(all_hexes)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def build_reference_profiles(
    partner_profiles: list[PartnerProfile],
    cells_features: dict[str, np.ndarray],  # {h3_id_r8: feature_vector}
    exit_reason_map: dict[str, dict],
    min_tenure_days: int = 30,
    global_fallback_profiles: Optional[ReferenceProfiles] = None,
    station_code: str = "unknown",
) -> ReferenceProfiles:
    """
    Build Success and Failure reference profiles from partner history.

    Parameters
    ----------
    partner_profiles:
        List of PartnerProfile objects (Active and Exited).
    cells_features:
        Mapping from H3 cell id (res 8) to its normalised feature vector.
    exit_reason_map:
        Mapping from exit reason code to {"class": ..., "penalty": ...}.
        Typically ``geo_config.EXIT_REASON_MAP``.
    min_tenure_days:
        Minimum tenure for an Active partner to be included in the
        Success_Profile (default: 30).
    global_fallback_profiles:
        Pre-built global profiles to use when local data is insufficient
        (n_active < 3).
    station_code:
        Identifier used for file naming and logging.

    Returns
    -------
    ReferenceProfiles
    """
    # ------------------------------------------------------------------
    # Edge case: empty inputs
    # ------------------------------------------------------------------
    if not cells_features:
        logger.warning(
            "[%s] cells_features is empty — returning zero-vector fallback profiles.",
            station_code,
        )
        zero = np.array([])
        return ReferenceProfiles(
            station_code=station_code,
            success_vector=zero,
            failure_vector=zero,
            n_active=0,
            n_exited_area=0,
            avg_tenure_active=0.0,
            profile_coverage=0.0,
            low_coverage_warning=True,
            is_global_fallback=True,
        )

    # Determine feature dimensionality from the first available vector
    feature_dim = next(iter(cells_features.values())).shape[0]
    zero_vector = np.zeros(feature_dim)

    if not partner_profiles:
        logger.warning(
            "[%s] No partner profiles provided — returning zero-vector fallback profiles.",
            station_code,
        )
        return ReferenceProfiles(
            station_code=station_code,
            success_vector=zero_vector.copy(),
            failure_vector=zero_vector.copy(),
            n_active=0,
            n_exited_area=0,
            avg_tenure_active=0.0,
            profile_coverage=0.0,
            low_coverage_warning=True,
            is_global_fallback=True,
        )

    # ------------------------------------------------------------------
    # Separate Active and Exited area_signal partners
    # ------------------------------------------------------------------
    active_vectors: list[np.ndarray] = []
    active_weights: list[float] = []
    active_tenures: list[int] = []

    failure_vectors: list[np.ndarray] = []
    failure_weights: list[float] = []

    n_exited_by_class: Counter = Counter()

    for p in partner_profiles:
        # Skip partners whose hex is not in cells_features
        if p.h3_id_r8 not in cells_features:
            continue

        fv = cells_features[p.h3_id_r8]

        if p.status.upper() == "ACTIVE":
            if p.tenure_days >= min_tenure_days:
                tenure_weight = math.log(1 + p.tenure_days)
                active_vectors.append(fv)
                active_weights.append(tenure_weight)
                active_tenures.append(p.tenure_days)

        elif p.status.upper() == "EXITED":
            cls = p.exit_reason_class
            if cls:
                n_exited_by_class[cls] += 1
            if cls == "area_signal" and p.area_penalty > 0.0:
                failure_weight = p.area_penalty * math.log(1 + p.tenure_days)
                failure_vectors.append(fv)
                failure_weights.append(failure_weight)

    n_active = len(active_vectors)
    n_exited_area = n_exited_by_class.get("area_signal", 0)
    avg_tenure_active = (
        float(sum(active_tenures)) / len(active_tenures) if active_tenures else 0.0
    )

    # ------------------------------------------------------------------
    # Success vector — with global fallback when n_active < 3
    # ------------------------------------------------------------------
    is_global_fallback = False

    if n_active < 3:
        if global_fallback_profiles is not None:
            logger.warning(
                "[%s] Only %d active partner(s) with tenure >= %d days — "
                "using global fallback Success_Profile.",
                station_code,
                n_active,
                min_tenure_days,
            )
            success_vector = global_fallback_profiles.success_vector
            is_global_fallback = True
        else:
            logger.warning(
                "[%s] Only %d active partner(s) with tenure >= %d days and "
                "no global fallback provided — using zero vector.",
                station_code,
                n_active,
                min_tenure_days,
            )
            success_vector = zero_vector.copy()
            is_global_fallback = True
    else:
        success_vector = _weighted_average(active_vectors, active_weights)

    # ------------------------------------------------------------------
    # Failure vector
    # ------------------------------------------------------------------
    if failure_vectors:
        failure_vector = _weighted_average(failure_vectors, failure_weights)
    else:
        failure_vector = zero_vector.copy()

    # ------------------------------------------------------------------
    # Profile coverage
    # ------------------------------------------------------------------
    profile_coverage = _compute_profile_coverage(partner_profiles, cells_features)
    low_coverage_warning = profile_coverage < (LOW_COVERAGE_WARNING_PCT / 100.0)

    # ------------------------------------------------------------------
    # Logging (Requirement 3.6)
    # ------------------------------------------------------------------
    logger.info(
        "[%s] build_reference_profiles: n_active=%d, n_exited_area=%d, "
        "n_exited_partner=%d, avg_tenure_active=%.1f days, "
        "profile_coverage=%.2f%%, low_coverage_warning=%s, "
        "is_global_fallback=%s",
        station_code,
        n_active,
        n_exited_area,
        n_exited_by_class.get("partner_signal", 0),
        avg_tenure_active,
        profile_coverage * 100.0,
        low_coverage_warning,
        is_global_fallback,
    )

    # ------------------------------------------------------------------
    # Persist vectors (Requirement 3.3)
    # ------------------------------------------------------------------
    if success_vector.size > 0:
        try:
            ts = _timestamp_str()
            _save_vector(success_vector, station_code, "success", ts)
            _save_vector(failure_vector, station_code, "failure", ts)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "[%s] Could not persist reference profile vectors: %s",
                station_code,
                exc,
            )

    return ReferenceProfiles(
        station_code=station_code,
        success_vector=success_vector,
        failure_vector=failure_vector,
        n_active=n_active,
        n_exited_area=n_exited_area,
        avg_tenure_active=avg_tenure_active,
        profile_coverage=profile_coverage,
        low_coverage_warning=low_coverage_warning,
        is_global_fallback=is_global_fallback,
    )
