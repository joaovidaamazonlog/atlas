"""
test_pipeline_properties.py
============================
Testes de propriedade (Hypothesis) para o pipeline refatorado do ATLAS.

Propriedades verificadas
------------------------
Property 1 — Schema exato do JSON de saída
Property 2 — Ausência de NaN/None em strings serializadas
Property 3 — Separação correta de web leads
Property 4 — origin_hex é uma string H3 válida

Execução
--------
    pytest backend/tests/test_pipeline_properties.py -v
"""

from __future__ import annotations

import sys
import os

# Garante que o diretório backend está no path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import h3
import pandas as pd
import pytest
from hypothesis import given, settings, HealthCheck
from hypothesis import strategies as st

from models import Partner, Config
from load_partners import _build_partner_data, serialize_to_json

# ---------------------------------------------------------------------------
# SCHEMA esperado (25 campos exatos)
# ---------------------------------------------------------------------------

SCHEMA_FIELDS = frozenset({
    "salesforce_id", "store_id", "name", "status", "lead_source",
    "lat", "lon", "zip_code", "city", "state",
    "delivery_station", "supply_run", "radius", "capacity",
    "bucket", "jurisdiction_type", "hub_delivey_initiatives",
    "HCP_rate_card", "HCP_host_partner",
    "launch_date", "exited_date", "telefone",
    "owner_id", "decision_status", "tooltip",
})

STRING_FIELDS = {
    "salesforce_id", "store_id", "name", "status", "lead_source",
    "zip_code", "city", "state", "delivery_station", "supply_run",
    "bucket", "jurisdiction_type", "hub_delivey_initiatives",
    "HCP_rate_card", "HCP_host_partner", "launch_date", "exited_date",
    "telefone", "owner_id", "decision_status", "tooltip",
}

INVALID_STRINGS = {"nan", "None", "NaN", "NaT", "none", "nat"}

# ---------------------------------------------------------------------------
# Estratégias Hypothesis
# ---------------------------------------------------------------------------

_statuses = st.sampled_from([
    "Active", "Onboarding", "BG Checks", "Prospect", "Inactive", "Exited", "New"
])

_opt_text = st.one_of(st.none(), st.text(min_size=1, max_size=50).filter(
    lambda s: s.strip().lower() not in INVALID_STRINGS
))


def partner_strategy():
    """Gera objetos Partner com campos válidos e opcionais variados."""
    return st.builds(
        Partner,
        salesforce_id           = st.text(min_size=1, max_size=18),
        store_id                = _opt_text,
        name                    = st.text(min_size=1, max_size=100),
        status                  = _statuses,
        lead_source             = _opt_text,
        lat                     = st.one_of(st.none(), st.floats(min_value=-33.7, max_value=5.3, allow_nan=False)),
        lon                     = st.one_of(st.none(), st.floats(min_value=-73.9, max_value=-34.7, allow_nan=False)),
        zip_code                = _opt_text,
        city                    = _opt_text,
        state                   = _opt_text,
        delivery_station        = st.text(min_size=1, max_size=10),
        supply_run              = _opt_text,
        radius                  = st.integers(min_value=200, max_value=5000),
        capacity                = st.integers(min_value=1, max_value=200),
        bucket                  = _opt_text,
        jurisdiction_type       = _opt_text,
        hub_delivey_initiatives = _opt_text,
        HCP_rate_card           = _opt_text,
        HCP_host_partner        = _opt_text,
        launch_date             = _opt_text,
        exited_date             = _opt_text,
        telefone                = _opt_text,
        owner_id                = _opt_text,
        decision_status         = _opt_text,
        tooltip                 = st.text(min_size=1, max_size=200),
    )


def partner_with_coords_strategy():
    """Gera Partners com lat/lon sempre válidos (para testar origin_hex)."""
    return st.builds(
        Partner,
        salesforce_id           = st.text(min_size=1, max_size=18),
        store_id                = _opt_text,
        name                    = st.text(min_size=1, max_size=100),
        status                  = _statuses,
        lead_source             = _opt_text,
        lat                     = st.floats(min_value=-33.7, max_value=5.3, allow_nan=False),
        lon                     = st.floats(min_value=-73.9, max_value=-34.7, allow_nan=False),
        zip_code                = _opt_text,
        city                    = _opt_text,
        state                   = _opt_text,
        delivery_station        = st.text(min_size=1, max_size=10),
        supply_run              = _opt_text,
        radius                  = st.integers(min_value=200, max_value=5000),
        capacity                = st.integers(min_value=1, max_value=200),
        bucket                  = _opt_text,
        jurisdiction_type       = _opt_text,
        hub_delivey_initiatives = _opt_text,
        HCP_rate_card           = _opt_text,
        HCP_host_partner        = _opt_text,
        launch_date             = _opt_text,
        exited_date             = _opt_text,
        telefone                = _opt_text,
        owner_id                = _opt_text,
        decision_status         = _opt_text,
        tooltip                 = st.text(min_size=1, max_size=200),
    )


def mixed_records_strategy():
    """
    Gera dicts com mistura de web leads e parceiros operacionais.
    Web lead: status='New' AND lead_source='Website Pardot Form'
    """
    web_lead = st.fixed_dictionaries({
        "status":       st.just("New"),
        "lead_source":  st.just("Website Pardot Form"),
        "salesforce_id": st.text(min_size=1, max_size=18),
        "store_id":     st.none(),
        "name":         st.text(min_size=1, max_size=50),
        "lat":          st.one_of(st.none(), st.floats(min_value=-33.7, max_value=5.3, allow_nan=False)),
        "lon":          st.one_of(st.none(), st.floats(min_value=-73.9, max_value=-34.7, allow_nan=False)),
        "zip_code":     _opt_text,
        "city":         _opt_text,
        "state":        _opt_text,
        "delivery_station": st.text(min_size=1, max_size=10),
        "supply_run":   st.none(),
        "radius":       st.integers(min_value=200, max_value=5000),
        "capacity":     st.integers(min_value=1, max_value=200),
        "bucket":       _opt_text,
        "jurisdiction_type": st.none(),
        "hub_delivey_initiatives": st.none(),
        "HCP_rate_card": st.none(),
        "HCP_host_partner": st.none(),
        "launch_date":  st.none(),
        "exited_date":  st.none(),
        "telefone":     _opt_text,
        "owner_id":     st.none(),
        "decision_status": st.none(),
        "tooltip":      st.text(min_size=1, max_size=100),
    })

    operational = st.fixed_dictionaries({
        "status":       st.sampled_from(["Active", "Onboarding", "BG Checks", "Prospect", "Inactive", "Exited"]),
        "lead_source":  st.one_of(st.none(), st.text(min_size=1, max_size=30).filter(lambda s: s != "Website Pardot Form")),
        "salesforce_id": st.text(min_size=1, max_size=18),
        "store_id":     _opt_text,
        "name":         st.text(min_size=1, max_size=50),
        "lat":          st.floats(min_value=-33.7, max_value=5.3, allow_nan=False),
        "lon":          st.floats(min_value=-73.9, max_value=-34.7, allow_nan=False),
        "zip_code":     _opt_text,
        "city":         _opt_text,
        "state":        _opt_text,
        "delivery_station": st.text(min_size=1, max_size=10),
        "supply_run":   _opt_text,
        "radius":       st.integers(min_value=200, max_value=5000),
        "capacity":     st.integers(min_value=1, max_value=200),
        "bucket":       _opt_text,
        "jurisdiction_type": _opt_text,
        "hub_delivey_initiatives": _opt_text,
        "HCP_rate_card": _opt_text,
        "HCP_host_partner": _opt_text,
        "launch_date":  _opt_text,
        "exited_date":  _opt_text,
        "telefone":     _opt_text,
        "owner_id":     _opt_text,
        "decision_status": _opt_text,
        "tooltip":      st.text(min_size=1, max_size=100),
    })

    return st.one_of(web_lead, operational)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _partners_from_dicts(records: list[dict]) -> list[Partner]:
    """Constrói objetos Partner a partir de dicts (para Property 3 e 4)."""
    partners = []
    for d in records:
        partners.append(Partner(
            salesforce_id           = d.get("salesforce_id", ""),
            store_id                = d.get("store_id"),
            name                    = d.get("name", ""),
            status                  = d.get("status", ""),
            lead_source             = d.get("lead_source"),
            lat                     = d.get("lat"),
            lon                     = d.get("lon"),
            zip_code                = d.get("zip_code"),
            city                    = d.get("city"),
            state                   = d.get("state"),
            delivery_station        = d.get("delivery_station", ""),
            supply_run              = d.get("supply_run"),
            radius                  = d.get("radius", 1500),
            capacity                = d.get("capacity", 42),
            bucket                  = d.get("bucket"),
            jurisdiction_type       = d.get("jurisdiction_type"),
            hub_delivey_initiatives = d.get("hub_delivey_initiatives"),
            HCP_rate_card           = d.get("HCP_rate_card"),
            HCP_host_partner        = d.get("HCP_host_partner"),
            launch_date             = d.get("launch_date"),
            exited_date             = d.get("exited_date"),
            telefone                = d.get("telefone"),
            owner_id                = d.get("owner_id"),
            decision_status         = d.get("decision_status"),
            tooltip                 = d.get("tooltip", ""),
        ))
    return partners


# ---------------------------------------------------------------------------
# Property 1 — Schema exato do JSON de saída
# Feature: pipeline-refactor
# ---------------------------------------------------------------------------

@settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
@given(st.lists(partner_strategy(), min_size=1, max_size=50))
def test_schema_exact_fields(partners: list[Partner]):
    """
    Para qualquer lista de Partners, cada objeto em allMarkerData deve conter
    exatamente os campos do SCHEMA_FIELDS — nem mais, nem menos.
    """
    for p in partners:
        record = p.to_dict()
        assert set(record.keys()) == SCHEMA_FIELDS, (
            f"Campos inesperados: {set(record.keys()) - SCHEMA_FIELDS} | "
            f"Campos faltando: {SCHEMA_FIELDS - set(record.keys())}"
        )


# ---------------------------------------------------------------------------
# Property 2 — Ausência de NaN/None em strings serializadas
# Feature: pipeline-refactor
# ---------------------------------------------------------------------------

@settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
@given(st.lists(partner_strategy(), min_size=1, max_size=50))
def test_no_nan_in_strings(partners: list[Partner]):
    """
    Nenhum campo string do Schema_Limpo deve conter 'nan', 'None' ou 'NaN'
    após to_dict(). Valores ausentes devem ser null (None em Python).
    """
    for p in partners:
        d = p.to_dict()
        for field in STRING_FIELDS:
            val = d.get(field)
            if val is not None:
                assert str(val).lower() not in {s.lower() for s in INVALID_STRINGS}, (
                    f"Campo '{field}' contém valor inválido: {val!r}"
                )


# ---------------------------------------------------------------------------
# Property 3 — Separação correta de web leads
# Feature: pipeline-refactor
# ---------------------------------------------------------------------------

@settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow, HealthCheck.filter_too_much])
@given(st.lists(mixed_records_strategy(), min_size=2, max_size=100))
def test_web_leads_separation(records: list[dict]):
    """
    Nenhum web lead deve aparecer em partners_df.
    Nenhum parceiro operacional deve aparecer em web_leads_df.
    """
    partners = _partners_from_dicts(records)
    partner_data = _build_partner_data(partners)

    # Nenhum web lead em partners_df
    if not partner_data.partners_df.empty and "lead_source" in partner_data.partners_df.columns:
        wl_in_partners = partner_data.partners_df[
            (partner_data.partners_df.get("status", pd.Series()) == "New") &
            (partner_data.partners_df["lead_source"] == "Website Pardot Form")
        ]
        assert len(wl_in_partners) == 0, (
            f"{len(wl_in_partners)} web lead(s) encontrado(s) em partners_df"
        )

    # Nenhum parceiro operacional em web_leads_df
    if not partner_data.web_leads_df.empty:
        status_col = partner_data.web_leads_df.get("status", pd.Series())
        lead_col   = partner_data.web_leads_df.get("lead_source", pd.Series())
        non_wl = partner_data.web_leads_df[
            ~((status_col == "New") & (lead_col == "Website Pardot Form"))
        ]
        assert len(non_wl) == 0, (
            f"{len(non_wl)} parceiro(s) operacional(is) encontrado(s) em web_leads_df"
        )


# ---------------------------------------------------------------------------
# Property 4 — origin_hex é uma string H3 válida
# Feature: pipeline-refactor
# ---------------------------------------------------------------------------

@settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
@given(st.lists(partner_with_coords_strategy(), min_size=1, max_size=50))
def test_origin_hex_valid(partners: list[Partner]):
    """
    Para todo parceiro com lat/lon válidos, origin_hex deve ser uma
    string H3 válida na resolução Config.H3_RES.
    """
    partner_data = _build_partner_data(partners)

    if partner_data.partners_df.empty:
        return  # todos eram web leads ou sem coords — ok

    assert "origin_hex" in partner_data.partners_df.columns, (
        "Coluna 'origin_hex' ausente em partners_df"
    )

    for _, row in partner_data.partners_df.iterrows():
        hex_id = row["origin_hex"]
        assert h3.is_valid_cell(hex_id), (
            f"origin_hex inválido: {hex_id!r} para lat={row.get('lat')}, lon={row.get('lon')}"
        )
