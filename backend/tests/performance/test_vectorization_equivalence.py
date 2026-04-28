"""
tests/performance/test_vectorization_equivalence.py
====================================================
Property-based tests (Hypothesis) de equivalência funcional da vetorização.

Propriedades validadas:
- `_vectorized_latlng_to_cell(lat, lon, res)` ≡ versão linha-a-linha com
  `h3.latlng_to_cell`, para coordenadas válidas e com NaN.
- NaN em `lat` ou `lon` resulta em `""` (string vazia) — comportamento
  documentado e equivalente ao `dropna()` prévio + list-comp.
- `dict(zip(station_code, demand))` produzido pela versão vetorizada em
  `load_packages` coincide com o `dict` produzido pelo `iterrows()`
  original sobre o mesmo DataFrame.

Referências: Requirements 3.5, 3.6, 3.8, 5.5
"""

from __future__ import annotations

import math

import h3
import numpy as np
import pandas as pd
import pytest
from hypothesis import HealthCheck, assume, given, settings, strategies as st

from shared.load_packages import _vectorized_latlng_to_cell


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------


@st.composite
def lat_lon_pairs_with_nans(draw, min_size: int = 0, max_size: int = 100):
    """
    Gera pares (lat, lon) com probabilidade ~15% de NaN, simulando dados
    sujos típicos de entrada.
    """
    n = draw(st.integers(min_value=min_size, max_value=max_size))
    lats: list[float] = []
    lons: list[float] = []
    for _ in range(n):
        if draw(st.integers(min_value=0, max_value=99)) < 15:
            lats.append(float("nan"))
        else:
            lats.append(
                draw(st.floats(min_value=-85.0, max_value=85.0,
                               allow_nan=False, allow_infinity=False))
            )
        if draw(st.integers(min_value=0, max_value=99)) < 15:
            lons.append(float("nan"))
        else:
            lons.append(
                draw(st.floats(min_value=-180.0, max_value=180.0,
                               allow_nan=False, allow_infinity=False))
            )
    return lats, lons


def _reference_latlng_to_cell(lat_list, lon_list, res: int) -> list[str]:
    """Implementação linha-a-linha de referência (pré-vetorização)."""
    out: list[str] = []
    for la, lo in zip(lat_list, lon_list):
        if not (math.isfinite(la) and math.isfinite(lo)):
            out.append("")
        else:
            out.append(h3.latlng_to_cell(float(la), float(lo), res))
    return out


# ---------------------------------------------------------------------------
# Equivalência pontual
# ---------------------------------------------------------------------------


@settings(max_examples=80, deadline=None,
          suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(pairs=lat_lon_pairs_with_nans(min_size=0, max_size=80),
       res=st.integers(min_value=5, max_value=11))
def test_vectorized_equals_reference(pairs, res):
    """Vetorizado produz o MESMO array que o laço de referência."""
    lats, lons = pairs
    vec = _vectorized_latlng_to_cell(pd.Series(lats), pd.Series(lons), res)
    ref = _reference_latlng_to_cell(lats, lons, res)
    assert list(vec) == ref


def test_empty_input_returns_empty_array():
    out = _vectorized_latlng_to_cell(pd.Series([], dtype=float),
                                     pd.Series([], dtype=float), 9)
    assert len(out) == 0


def test_all_nan_input_returns_all_empty_strings():
    n = 5
    out = _vectorized_latlng_to_cell(
        pd.Series([float("nan")] * n),
        pd.Series([float("nan")] * n),
        9,
    )
    assert list(out) == [""] * n


def test_mixed_nan_and_valid_preserves_positions():
    """A posição da NaN no input determina a posição da string vazia no output."""
    lats = [-23.5, float("nan"), -22.9]
    lons = [-46.6, -46.6, float("nan")]
    out = _vectorized_latlng_to_cell(pd.Series(lats), pd.Series(lons), 9)
    assert out[0] != ""
    assert out[1] == ""
    assert out[2] == ""
    # valor válido coincide com a chamada escalar
    assert out[0] == h3.latlng_to_cell(-23.5, -46.6, 9)


# ---------------------------------------------------------------------------
# Equivalência do dict produced por groupby + zip (vs iterrows)
# ---------------------------------------------------------------------------


@st.composite
def demand_dataframes(draw, min_rows: int = 0, max_rows: int = 30):
    n = draw(st.integers(min_value=min_rows, max_value=max_rows))
    rows = []
    seen_pairs: set[tuple[str, str]] = set()
    for _ in range(n):
        # (station, hex) é a chave primária — evitar duplicatas
        while True:
            st_code = draw(st.sampled_from(["DSP2", "DSP4", "DBR9", "DRJ3"]))
            hex_id = draw(
                st.text(alphabet="0123456789abcdef",
                        min_size=15, max_size=15)
            )
            pair = (st_code, hex_id)
            if pair not in seen_pairs:
                seen_pairs.add(pair)
                break
        demand = draw(st.integers(min_value=0, max_value=10_000))
        rows.append({"station_code": st_code, "hex": hex_id,
                     "demand_total": demand})
    return pd.DataFrame(rows) if rows else pd.DataFrame(
        columns=["station_code", "hex", "demand_total"]
    )


def _reference_build_demand_dict(unified: pd.DataFrame) -> tuple[dict, dict]:
    """Versão iterrows() original (pré-vetorização)."""
    demand_by_station: dict = {}
    hex_to_base: dict = {}
    for _, row in unified.iterrows():
        station = row["station_code"]
        hex_id = row["hex"]
        demand = int(row["demand_total"])
        demand_by_station.setdefault(station, {})[hex_id] = demand
        hex_to_base[hex_id] = station
    return demand_by_station, hex_to_base


def _optimized_build_demand_dict(unified: pd.DataFrame) -> tuple[dict, dict]:
    """Versão vetorizada (atual em load_packages.py)."""
    demand_by_station = {
        st: dict(zip(grp["hex"], grp["demand_total"].astype(int)))
        for st, grp in unified.groupby("station_code")
    }
    hex_to_base = dict(zip(unified["hex"], unified["station_code"]))
    return demand_by_station, hex_to_base


@settings(max_examples=60, deadline=None,
          suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(df=demand_dataframes())
def test_demand_dict_optimized_equals_reference(df):
    """
    Vetorização via groupby + zip produz o MESMO `demand_by_station` e
    `hex_to_base` que `iterrows()`.
    """
    ref_demand, ref_hex_to_base = _reference_build_demand_dict(df)
    opt_demand, opt_hex_to_base = _optimized_build_demand_dict(df)
    assert ref_demand == opt_demand
    assert ref_hex_to_base == opt_hex_to_base
