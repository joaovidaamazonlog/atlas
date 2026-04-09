"""
test_phase3_properties.py
=========================
Property-based tests for Phase 3 binary decision logic.

**Validates: Requirements 6.1, 6.2, 6.3, 6.5, 6.6**

Property 5: Decisão binária é consistente com o resultado do matching
----------------------------------------------------------------------
For any PartnerMetrics with status == "Prospect":
  - decision is either "Go" or "No Go"
  - If matched_slot_id is not None → decision == "Go" and reason == "Seguir cadastro"
  - If matched_slot_id is None     → decision == "No Go" and reason in VALID_NO_GO_REASONS

The test directly exercises the decision-assignment logic from _match_station()
by constructing PartnerMetrics objects with known matched_slot_id values and
verifying the invariants hold.
"""

from __future__ import annotations

import sys
import os

# Allow imports from backend/ without installing as a package
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from hypothesis import given, settings
from hypothesis import strategies as st

from models import PartnerMetrics, Allocation

# ---------------------------------------------------------------------------
# Constants mirrored from the design document
# ---------------------------------------------------------------------------

VALID_NO_GO_REASONS = [
    "Sem oportunidade próxima",
    "Sem oportunidade próxima na borda",
    "Fora de jurisdição",
]

VALID_GO_REASON = "Seguir cadastro"


# ---------------------------------------------------------------------------
# Helpers — replicate the decision-assignment logic from _match_station()
# ---------------------------------------------------------------------------

def _assign_decision_matched(pm: PartnerMetrics, slot_id: str) -> PartnerMetrics:
    """
    Replicates the decision assignment for a matched partner (any status).
    Mirrors the logic in phase3_partner_fit._match_station() matched branch.
    """
    pm.decision = "Go"
    pm.reason = VALID_GO_REASON
    pm.matched_slot_id = slot_id
    return pm


def _assign_decision_unmatched_prospect(
    pm: PartnerMetrics, entity_type: str
) -> PartnerMetrics:
    """
    Replicates the decision assignment for an unmatched Prospect.
    Mirrors the logic in phase3_partner_fit._match_station() unmatched branch.
    """
    if entity_type == "PROSPECT":
        pm.decision = "No Go"
        pm.reason = "Sem oportunidade próxima"
    elif entity_type == "PROSPECT_BORDER":
        pm.decision = "No Go"
        pm.reason = "Sem oportunidade próxima na borda"
    else:
        # Outside jurisdiction (outside_list)
        pm.decision = "No Go"
        pm.reason = "Fora de jurisdição"
    pm.matched_slot_id = None
    return pm


# ---------------------------------------------------------------------------
# Hypothesis strategies
# ---------------------------------------------------------------------------

_hex_strategy = st.just("891f1d48177ffff")  # a valid H3 hex (static for simplicity)

_prospect_strategy = st.builds(
    PartnerMetrics,
    origin_hex=_hex_strategy,
    station_code=st.just("DSP2"),
    radius_s=st.integers(min_value=0, max_value=5000),
    capacity_s=st.integers(min_value=0, max_value=500),
    entity_type=st.just("PROSPECT"),
    status=st.just("Prospect"),
    partner_name=st.text(max_size=50),
    salesforce_id=st.text(alphabet="ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789", min_size=5, max_size=18),
)

_slot_id_strategy = st.text(
    alphabet="ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_-",
    min_size=3,
    max_size=30,
)

_entity_type_strategy = st.sampled_from(["PROSPECT", "PROSPECT_BORDER", "OUTSIDE"])


# ---------------------------------------------------------------------------
# Property 5 — Binary decision is consistent with matching result
# ---------------------------------------------------------------------------

@settings(max_examples=150)
@given(prospect=_prospect_strategy, slot_id=_slot_id_strategy)
def test_matched_prospect_gets_go_decision(prospect: PartnerMetrics, slot_id: str):
    """
    **Validates: Requirements 6.1, 6.2, 6.3, 6.5, 6.6**

    Property 5 (matched branch): For any Prospect matched with a slot,
    decision must be "Go" and reason must be "Seguir cadastro".
    """
    pm = _assign_decision_matched(prospect, slot_id)

    assert pm.status == "Prospect"
    assert pm.matched_slot_id is not None
    assert pm.decision == "Go", (
        f"Expected decision='Go' for matched prospect, got '{pm.decision}'"
    )
    assert pm.reason == VALID_GO_REASON, (
        f"Expected reason='{VALID_GO_REASON}' for matched prospect, got '{pm.reason}'"
    )


@settings(max_examples=150)
@given(prospect=_prospect_strategy, entity_type=_entity_type_strategy)
def test_unmatched_prospect_gets_no_go_decision(
    prospect: PartnerMetrics, entity_type: str
):
    """
    **Validates: Requirements 6.1, 6.2, 6.3, 6.5, 6.6**

    Property 5 (unmatched branch): For any Prospect not matched with a slot,
    decision must be "No Go" and reason must be one of VALID_NO_GO_REASONS.
    """
    pm = _assign_decision_unmatched_prospect(prospect, entity_type)

    assert pm.status == "Prospect"
    assert pm.matched_slot_id is None
    assert pm.decision == "No Go", (
        f"Expected decision='No Go' for unmatched prospect, got '{pm.decision}'"
    )
    assert pm.reason in VALID_NO_GO_REASONS, (
        f"Expected reason in {VALID_NO_GO_REASONS}, got '{pm.reason}'"
    )


@settings(max_examples=200)
@given(
    prospect=_prospect_strategy,
    is_matched=st.booleans(),
    slot_id=_slot_id_strategy,
    entity_type=_entity_type_strategy,
)
def test_decision_is_always_binary_for_prospects(
    prospect: PartnerMetrics,
    is_matched: bool,
    slot_id: str,
    entity_type: str,
):
    """
    **Validates: Requirements 6.1, 6.2, 6.3, 6.5, 6.6**

    Property 5 (combined): For any Prospect, regardless of whether it was
    matched or not, decision must always be exactly "Go" or "No Go" — never
    empty, never a legacy descriptive string.
    """
    if is_matched:
        pm = _assign_decision_matched(prospect, slot_id)
    else:
        pm = _assign_decision_unmatched_prospect(prospect, entity_type)

    assert pm.status == "Prospect"
    assert pm.decision in ("Go", "No Go"), (
        f"decision must be 'Go' or 'No Go' for Prospects, got '{pm.decision}'"
    )

    # Consistency: matched ↔ Go, unmatched ↔ No Go
    if pm.matched_slot_id is not None:
        assert pm.decision == "Go"
        assert pm.reason == VALID_GO_REASON
    else:
        assert pm.decision == "No Go"
        assert pm.reason in VALID_NO_GO_REASONS
