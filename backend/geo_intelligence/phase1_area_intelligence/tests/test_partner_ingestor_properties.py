"""
test_partner_ingestor_properties.py
=====================================
Property-based tests for partner_ingestor.py.

**Validates: Requirements 1.2, 3.1**

Property 5: `tenure_weight = log(1 + tenure_days)` é monotonicamente crescente
-------------------------------------------------------------------------------
For any two non-negative integers d1 < d2:
    log(1 + d1) < log(1 + d2)

This verifies that the tenure weighting function is strictly monotonically
increasing — partners with more tenure always receive strictly higher weight.

Also tests that `ingest_partners` correctly computes
`tenure_weight = log(1 + tenure_days)` for generated partner data.

Execution
---------
    pytest backend/geo_intelligence/phase1_area_intelligence/tests/test_partner_ingestor_properties.py -v
"""

from __future__ import annotations

import math
import sys
import os
from datetime import date, timedelta

import pandas as pd
import pytest
from hypothesis import given, settings, assume
from hypothesis import strategies as st

# Allow imports from backend/geo_intelligence without installing as a package
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

from geo_intelligence.phase1_area_intelligence.partner_ingestor import ingest_partners


# ---------------------------------------------------------------------------
# Property 5 — tenure_weight = log(1 + tenure_days) é monotonicamente crescente
# Validates: Requirements 1.2, 3.1
# ---------------------------------------------------------------------------

@settings(max_examples=500)
@given(
    d1=st.integers(min_value=0, max_value=10000),
    d2=st.integers(min_value=0, max_value=10000),
)
def test_tenure_weight_strictly_monotone(d1: int, d2: int) -> None:
    """
    **Validates: Requirements 1.2, 3.1**

    Property 5: For any two non-negative integers d1 < d2,
    log(1 + d1) < log(1 + d2) — tenure_weight is strictly monotonically increasing.
    """
    assume(d1 < d2)

    w1 = math.log(1 + d1)
    w2 = math.log(1 + d2)

    assert w1 < w2, (
        f"tenure_weight not strictly increasing: "
        f"log(1 + {d1}) = {w1} >= log(1 + {d2}) = {w2}"
    )


@settings(max_examples=200)
@given(d=st.integers(min_value=0, max_value=10000))
def test_tenure_weight_non_negative(d: int) -> None:
    """
    **Validates: Requirements 1.2, 3.1**

    Property 5 (corollary): tenure_weight is always >= 0 for any non-negative tenure_days.
    """
    w = math.log(1 + d)
    assert w >= 0.0, f"tenure_weight negative for tenure_days={d}: {w}"


@settings(max_examples=200)
@given(d=st.integers(min_value=0, max_value=10000))
def test_tenure_weight_zero_at_zero_tenure(d: int) -> None:
    """
    **Validates: Requirements 1.2, 3.1**

    Property 5 (boundary): tenure_weight = 0 when tenure_days = 0,
    and tenure_weight > 0 for any tenure_days > 0.
    """
    w = math.log(1 + d)
    if d == 0:
        assert w == 0.0, f"Expected tenure_weight=0 for tenure_days=0, got {w}"
    else:
        assert w > 0.0, f"Expected tenure_weight>0 for tenure_days={d}, got {w}"


# ---------------------------------------------------------------------------
# Integration: ingest_partners computes tenure_weight = log(1 + tenure_days)
# Validates: Requirements 1.2, 3.1
# ---------------------------------------------------------------------------

# A valid lat/lon in Brazil (São Paulo area) for H3 cell computation
_VALID_LAT = -23.5505
_VALID_LON = -46.6333


def _make_partner_df(tenure_days: int, status: str = "Active") -> pd.DataFrame:
    """Build a minimal partner DataFrame with the given tenure_days."""
    today = date.today()
    if status.upper() == "EXITED":
        launch = today - timedelta(days=tenure_days + 1)
        exited = launch + timedelta(days=tenure_days)
        return pd.DataFrame([{
            "salesforce_id": "SF001",
            "status": status,
            "lat": _VALID_LAT,
            "lon": _VALID_LON,
            "launch_date": launch.isoformat(),
            "exited_date": exited.isoformat(),
            "decision_reason_code": None,
            "delivery_station": "DSP1",
        }])
    else:
        launch = today - timedelta(days=tenure_days)
        return pd.DataFrame([{
            "salesforce_id": "SF001",
            "status": status,
            "lat": _VALID_LAT,
            "lon": _VALID_LON,
            "launch_date": launch.isoformat(),
            "exited_date": None,
            "decision_reason_code": None,
            "delivery_station": "DSP1",
        }])


@settings(max_examples=200)
@given(tenure_days=st.integers(min_value=0, max_value=10000))
def test_ingest_partners_tenure_weight_formula_active(tenure_days: int) -> None:
    """
    **Validates: Requirements 1.2, 3.1**

    Property 5 (integration — Active): ingest_partners correctly computes
    tenure_weight = log(1 + tenure_days) for Active partners.
    """
    df = _make_partner_df(tenure_days, status="Active")
    profiles = ingest_partners(df)

    assert len(profiles) == 1
    profile = profiles[0]

    expected_weight = math.log(1 + profile.tenure_days)
    assert profile.tenure_weight == pytest.approx(expected_weight, rel=1e-9), (
        f"tenure_weight mismatch: expected log(1 + {profile.tenure_days}) = {expected_weight}, "
        f"got {profile.tenure_weight}"
    )


@settings(max_examples=200)
@given(tenure_days=st.integers(min_value=1, max_value=10000))
def test_ingest_partners_tenure_weight_formula_exited(tenure_days: int) -> None:
    """
    **Validates: Requirements 1.2, 3.1**

    Property 5 (integration — Exited): ingest_partners correctly computes
    tenure_weight = log(1 + tenure_days) for Exited partners.
    """
    df = _make_partner_df(tenure_days, status="Exited")
    profiles = ingest_partners(df)

    assert len(profiles) == 1
    profile = profiles[0]

    expected_weight = math.log(1 + profile.tenure_days)
    assert profile.tenure_weight == pytest.approx(expected_weight, rel=1e-9), (
        f"tenure_weight mismatch: expected log(1 + {profile.tenure_days}) = {expected_weight}, "
        f"got {profile.tenure_weight}"
    )


@settings(max_examples=200)
@given(
    d1=st.integers(min_value=0, max_value=10000),
    d2=st.integers(min_value=0, max_value=10000),
)
def test_ingest_partners_tenure_weight_order_preserved(d1: int, d2: int) -> None:
    """
    **Validates: Requirements 1.2, 3.1**

    Property 5 (integration — ordering): When two Active partners have
    d1 < d2 tenure_days, their tenure_weights satisfy w1 < w2.
    """
    assume(d1 < d2)

    today = date.today()

    df = pd.DataFrame([
        {
            "salesforce_id": "SF001",
            "status": "Active",
            "lat": _VALID_LAT,
            "lon": _VALID_LON,
            "launch_date": (today - timedelta(days=d1)).isoformat(),
            "exited_date": None,
            "decision_reason_code": None,
            "delivery_station": "DSP1",
        },
        {
            "salesforce_id": "SF002",
            "status": "Active",
            "lat": _VALID_LAT + 0.001,
            "lon": _VALID_LON + 0.001,
            "launch_date": (today - timedelta(days=d2)).isoformat(),
            "exited_date": None,
            "decision_reason_code": None,
            "delivery_station": "DSP1",
        },
    ])

    profiles = ingest_partners(df)
    assert len(profiles) == 2

    by_id = {p.salesforce_id: p for p in profiles}
    p1 = by_id["SF001"]
    p2 = by_id["SF002"]

    assert p1.tenure_weight < p2.tenure_weight, (
        f"Expected tenure_weight({d1}) < tenure_weight({d2}), "
        f"got {p1.tenure_weight} >= {p2.tenure_weight}"
    )


# ---------------------------------------------------------------------------
# Property 6 — Parceiros Exited com `partner_signal` não contribuem para
#              `failure_vector` (area_penalty = 0.0)
# Validates: Requirements 1.3, 3.2
# ---------------------------------------------------------------------------

# Import EXIT_REASON_MAP directly so tests stay in sync with config changes.
from geo_intelligence.geo_config import EXIT_REASON_MAP as _EXIT_REASON_MAP  # noqa: E402

# Reason codes grouped by class, derived from EXIT_REASON_MAP in geo_config.py.
# "Pure" partner_signal codes are those with penalty=0.0 — these are the ones
# that must NOT contribute to the failure_vector at all.
_PURE_PARTNER_SIGNAL_CODES = [
    code
    for code, entry in _EXIT_REASON_MAP.items()
    if entry["class"] == "partner_signal" and entry["penalty"] == 0.0
]

# All partner_signal codes (including partial ones like "operacional" with penalty>0)
_ALL_PARTNER_SIGNAL_CODES = [
    code for code, entry in _EXIT_REASON_MAP.items()
    if entry["class"] == "partner_signal"
]

_AREA_SIGNAL_CODES = [
    code for code, entry in _EXIT_REASON_MAP.items()
    if entry["class"] == "area_signal"
]


def _make_exited_partner_df(reason_code: str, tenure_days: int = 90) -> pd.DataFrame:
    """Build a minimal Exited partner DataFrame with the given reason code."""
    today = date.today()
    launch = today - timedelta(days=tenure_days + 1)
    exited = launch + timedelta(days=tenure_days)
    return pd.DataFrame([{
        "salesforce_id": "SF_EXITED",
        "status": "Exited",
        "lat": _VALID_LAT,
        "lon": _VALID_LON,
        "launch_date": launch.isoformat(),
        "exited_date": exited.isoformat(),
        "decision_reason_code": reason_code,
        "delivery_station": "DSP1",
    }])


def _make_active_partner_df(tenure_days: int = 90) -> pd.DataFrame:
    """Build a minimal Active partner DataFrame."""
    today = date.today()
    launch = today - timedelta(days=tenure_days)
    return pd.DataFrame([{
        "salesforce_id": "SF_ACTIVE",
        "status": "Active",
        "lat": _VALID_LAT,
        "lon": _VALID_LON,
        "launch_date": launch.isoformat(),
        "exited_date": None,
        "decision_reason_code": None,
        "delivery_station": "DSP1",
    }])


@settings(max_examples=200)
@given(
    reason_code=st.sampled_from(_PURE_PARTNER_SIGNAL_CODES),
    tenure_days=st.integers(min_value=1, max_value=10000),
)
def test_partner_signal_exited_has_zero_area_penalty(
    reason_code: str, tenure_days: int
) -> None:
    """
    **Validates: Requirements 1.3, 3.2**

    Property 6: Exited partners with a pure `partner_signal` reason code
    (penalty=0.0 in EXIT_REASON_MAP) must have
    `exit_reason_class = "partner_signal"` and `area_penalty = 0.0`.
    They must NOT contribute to the failure_vector.
    """
    df = _make_exited_partner_df(reason_code, tenure_days)
    profiles = ingest_partners(df)

    assert len(profiles) == 1
    profile = profiles[0]

    assert profile.exit_reason_class == "partner_signal", (
        f"Expected exit_reason_class='partner_signal' for reason_code='{reason_code}', "
        f"got '{profile.exit_reason_class}'"
    )
    assert profile.area_penalty == 0.0, (
        f"Expected area_penalty=0.0 for partner_signal reason '{reason_code}', "
        f"got {profile.area_penalty}"
    )


@settings(max_examples=200)
@given(
    reason_code=st.sampled_from(_ALL_PARTNER_SIGNAL_CODES),
    tenure_days=st.integers(min_value=1, max_value=10000),
)
def test_partner_signal_exited_class_matches_config(
    reason_code: str, tenure_days: int
) -> None:
    """
    **Validates: Requirements 1.3, 3.2**

    Property 6 (config fidelity): For any partner_signal reason code,
    ingest_partners must set exit_reason_class = "partner_signal" and
    area_penalty exactly matching EXIT_REASON_MAP[reason_code]["penalty"].
    """
    expected_penalty = float(_EXIT_REASON_MAP[reason_code]["penalty"])

    df = _make_exited_partner_df(reason_code, tenure_days)
    profiles = ingest_partners(df)

    assert len(profiles) == 1
    profile = profiles[0]

    assert profile.exit_reason_class == "partner_signal", (
        f"Expected exit_reason_class='partner_signal' for reason_code='{reason_code}', "
        f"got '{profile.exit_reason_class}'"
    )
    assert profile.area_penalty == pytest.approx(expected_penalty), (
        f"area_penalty mismatch for '{reason_code}': "
        f"expected {expected_penalty}, got {profile.area_penalty}"
    )


@settings(max_examples=200)
@given(
    reason_code=st.sampled_from(_AREA_SIGNAL_CODES),
    tenure_days=st.integers(min_value=1, max_value=10000),
)
def test_area_signal_exited_has_positive_area_penalty(
    reason_code: str, tenure_days: int
) -> None:
    """
    **Validates: Requirements 1.3, 3.2**

    Property 6 (complement): Exited partners with an `area_signal` reason code
    must have `exit_reason_class = "area_signal"` and `area_penalty > 0.0`.
    They DO contribute to the failure_vector.
    """
    df = _make_exited_partner_df(reason_code, tenure_days)
    profiles = ingest_partners(df)

    assert len(profiles) == 1
    profile = profiles[0]

    assert profile.exit_reason_class == "area_signal", (
        f"Expected exit_reason_class='area_signal' for reason_code='{reason_code}', "
        f"got '{profile.exit_reason_class}'"
    )
    assert profile.area_penalty > 0.0, (
        f"Expected area_penalty>0.0 for area_signal reason '{reason_code}', "
        f"got {profile.area_penalty}"
    )


@settings(max_examples=200)
@given(tenure_days=st.integers(min_value=0, max_value=10000))
def test_active_partner_has_no_exit_reason_and_zero_penalty(
    tenure_days: int,
) -> None:
    """
    **Validates: Requirements 1.3, 3.2**

    Property 6 (Active): Active partners always have
    `exit_reason_class = None` and `area_penalty = 0.0`.
    They never contribute to the failure_vector.
    """
    df = _make_active_partner_df(tenure_days)
    profiles = ingest_partners(df)

    assert len(profiles) == 1
    profile = profiles[0]

    assert profile.exit_reason_class is None, (
        f"Expected exit_reason_class=None for Active partner, "
        f"got '{profile.exit_reason_class}'"
    )
    assert profile.area_penalty == 0.0, (
        f"Expected area_penalty=0.0 for Active partner, got {profile.area_penalty}"
    )


@settings(max_examples=100)
@given(
    partner_signal_code=st.sampled_from(_PURE_PARTNER_SIGNAL_CODES),
    area_signal_code=st.sampled_from(_AREA_SIGNAL_CODES),
    tenure_days=st.integers(min_value=1, max_value=10000),
)
def test_partner_signal_isolation_from_failure_vector(
    partner_signal_code: str,
    area_signal_code: str,
    tenure_days: int,
) -> None:
    """
    **Validates: Requirements 1.3, 3.2**

    Property 6 (isolation): When a batch contains both pure partner_signal
    (penalty=0.0) and area_signal Exited partners, only area_signal ones have
    area_penalty > 0. This verifies the isolation property — pure partner_signal
    partners are completely excluded from contributing to the failure_vector.
    """
    today = date.today()
    launch = today - timedelta(days=tenure_days + 1)
    exited = launch + timedelta(days=tenure_days)

    df = pd.DataFrame([
        {
            "salesforce_id": "SF_PARTNER_SIGNAL",
            "status": "Exited",
            "lat": _VALID_LAT,
            "lon": _VALID_LON,
            "launch_date": launch.isoformat(),
            "exited_date": exited.isoformat(),
            "decision_reason_code": partner_signal_code,
            "delivery_station": "DSP1",
        },
        {
            "salesforce_id": "SF_AREA_SIGNAL",
            "status": "Exited",
            "lat": _VALID_LAT + 0.001,
            "lon": _VALID_LON + 0.001,
            "launch_date": launch.isoformat(),
            "exited_date": exited.isoformat(),
            "decision_reason_code": area_signal_code,
            "delivery_station": "DSP1",
        },
    ])

    profiles = ingest_partners(df)
    assert len(profiles) == 2

    by_id = {p.salesforce_id: p for p in profiles}
    ps = by_id["SF_PARTNER_SIGNAL"]
    as_ = by_id["SF_AREA_SIGNAL"]

    # pure partner_signal: must NOT contribute to failure_vector
    assert ps.area_penalty == 0.0, (
        f"partner_signal '{partner_signal_code}' should have area_penalty=0.0, "
        f"got {ps.area_penalty}"
    )
    assert ps.exit_reason_class == "partner_signal"

    # area_signal: MUST contribute to failure_vector
    assert as_.area_penalty > 0.0, (
        f"area_signal '{area_signal_code}' should have area_penalty>0.0, "
        f"got {as_.area_penalty}"
    )
    assert as_.exit_reason_class == "area_signal"
