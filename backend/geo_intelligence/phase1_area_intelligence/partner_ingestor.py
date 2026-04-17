"""
partner_ingestor.py
===================
Maps partner data to PartnerProfile dataclasses with H3 res 8 cells,
tenure calculations, exit reason classification, and tenure weighting.

Requirements: 1.1, 1.2, 1.3, 1.4, 1.7
"""

from __future__ import annotations

import logging
import math
from datetime import date, datetime
from typing import Optional

import h3
import pandas as pd

from geo_intelligence.geo_config import EXIT_REASON_MAP
from geo_intelligence.pipeline import PartnerProfile

logger = logging.getLogger(__name__)


def _parse_date(value) -> Optional[date]:
    """Parse a date value from various formats, returning None on failure."""
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, str):
        value = value.strip()
        if not value:
            return None
        for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%Y/%m/%d"):
            try:
                return datetime.strptime(value, fmt).date()
            except ValueError:
                continue
    try:
        return pd.Timestamp(value).date()
    except Exception:  # noqa: BLE001
        return None


def _classify_exit_reason(
    reason_code: Optional[str],
) -> tuple[Optional[str], float]:
    """
    Returns (exit_reason_class, area_penalty) for a given reason code.

    Falls back to (None, 0.0) for unknown or missing codes.
    """
    if not reason_code or not isinstance(reason_code, str):
        return None, 0.0
    key = reason_code.strip().lower()
    entry = EXIT_REASON_MAP.get(key)
    if entry is None:
        logger.debug("Unknown exit reason code '%s' — treating as unclassified.", reason_code)
        return None, 0.0
    return entry["class"], float(entry["penalty"])


def ingest_partners(partner_data_df: pd.DataFrame) -> list[PartnerProfile]:
    """
    Convert a raw partner DataFrame into a list of PartnerProfile objects.

    Parameters
    ----------
    partner_data_df:
        DataFrame with columns: ``salesforce_id``, ``status``, ``lat``,
        ``lon``, ``launch_date``, ``exited_date``,
        ``decision_reason_code``, ``delivery_station``.

    Returns
    -------
    list[PartnerProfile]
        One profile per valid row.  Partners without ``launch_date`` are
        included (for matching purposes) but receive ``tenure_days=0`` and
        ``tenure_weight=0.0``.  Partners with invalid lat/lon are skipped.
    """
    if partner_data_df is None or (
        isinstance(partner_data_df, pd.DataFrame) and partner_data_df.empty
    ):
        logger.warning(
            "partner_data_df is empty or None — returning empty partner profile list."
        )
        return []

    today = date.today()
    profiles: list[PartnerProfile] = []

    for idx, row in partner_data_df.iterrows():
        # ------------------------------------------------------------------ #
        # 1. Extract core fields
        # ------------------------------------------------------------------ #
        salesforce_id = str(row.get("salesforce_id", "")).strip() or f"unknown_{idx}"
        status = str(row.get("status", "")).strip()
        delivery_station = str(row.get("delivery_station", "")).strip()
        decision_reason_code = row.get("decision_reason_code")

        # ------------------------------------------------------------------ #
        # 2. Validate and parse lat/lon
        # ------------------------------------------------------------------ #
        try:
            lat = float(row["lat"])
            lon = float(row["lon"])
            if math.isnan(lat) or math.isnan(lon):
                raise ValueError("NaN coordinate")
        except (KeyError, TypeError, ValueError) as exc:
            logger.debug(
                "Skipping partner '%s' — invalid lat/lon: %s", salesforce_id, exc
            )
            continue

        # ------------------------------------------------------------------ #
        # 3. Compute H3 cell at resolution 8
        # ------------------------------------------------------------------ #
        try:
            origin_hex = h3.latlng_to_cell(lat, lon, 8)
        except Exception as exc:  # noqa: BLE001
            logger.debug(
                "Skipping partner '%s' — H3 cell computation failed: %s",
                salesforce_id,
                exc,
            )
            continue

        # ------------------------------------------------------------------ #
        # 4. Parse dates
        # ------------------------------------------------------------------ #
        launch_date = _parse_date(row.get("launch_date"))
        exited_date = _parse_date(row.get("exited_date"))

        # ------------------------------------------------------------------ #
        # 5. Compute tenure_days
        #    Partners without launch_date → tenure_days=0, tenure_weight=0.0
        # ------------------------------------------------------------------ #
        if launch_date is None:
            tenure_days = 0
            tenure_weight = 0.0
        else:
            status_upper = status.upper()
            if status_upper == "EXITED" and exited_date is not None:
                tenure_days = max(0, (exited_date - launch_date).days)
            else:
                # Active (and any other status with a launch_date)
                tenure_days = max(0, (today - launch_date).days)
            tenure_weight = math.log(1 + tenure_days)

        # ------------------------------------------------------------------ #
        # 6. Classify exit reason
        # ------------------------------------------------------------------ #
        if status.upper() == "EXITED":
            exit_reason_class, area_penalty = _classify_exit_reason(decision_reason_code)
        else:
            # Active partners have no exit reason
            exit_reason_class = None
            area_penalty = 0.0

        # ------------------------------------------------------------------ #
        # 7. Build PartnerProfile
        # ------------------------------------------------------------------ #
        profile = PartnerProfile(
            salesforce_id=salesforce_id,
            status=status,
            h3_id_r8=origin_hex,
            lat=lat,
            lon=lon,
            tenure_days=tenure_days,
            tenure_weight=tenure_weight,
            exit_reason_class=exit_reason_class,
            area_penalty=area_penalty,
            features={},
            umap_embedding=[],
        )
        profiles.append(profile)

    logger.info(
        "ingest_partners: %d rows processed → %d profiles built.",
        len(partner_data_df),
        len(profiles),
    )
    return profiles
