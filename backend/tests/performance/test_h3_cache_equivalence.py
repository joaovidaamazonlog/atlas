"""
tests/performance/test_h3_cache_equivalence.py
===============================================
Property-based tests (Hypothesis) da equivalência funcional do `H3Cache`.

Propriedades validadas:
- `cache.grid_disk(cell, k)` ≡ `frozenset(h3.grid_disk(cell, k))` para todo
  `k ∈ [0, 5]` e toda célula H3 válida.
- `cache.grid_distance(a, b)` ≡ `h3.grid_distance(a, b)` para todo par de
  células H3 válidas (quando a distância é bem definida).
- Simetria: `cache.grid_distance(a, b) == cache.grid_distance(b, a)`.
- Exceções: se `h3.grid_disk`/`h3.grid_distance` levantam exceção, o
  cache levanta a **mesma** exceção (não memoriza falhas — a próxima
  chamada re-executa).
- Context manager: `cache.clear()` em `__exit__` zera os caches.

Referências: Requirements 2.3, 2.6, 5.2, 5.3
"""

from __future__ import annotations

import h3
import pytest
from hypothesis import HealthCheck, assume, example, given, settings, strategies as st

from shared.h3_cache import H3Cache


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------


@st.composite
def h3_cells(draw, min_res: int = 0, max_res: int = 11) -> str:
    """Gera uma célula H3 válida a partir de lat/lon + resolução."""
    lat = draw(st.floats(min_value=-85.0, max_value=85.0, allow_nan=False,
                         allow_infinity=False))
    lon = draw(st.floats(min_value=-180.0, max_value=180.0, allow_nan=False,
                         allow_infinity=False))
    res = draw(st.integers(min_value=min_res, max_value=max_res))
    return h3.latlng_to_cell(lat, lon, res)


@st.composite
def h3_cell_pairs_close(draw, max_distance_k: int = 6) -> tuple[str, str]:
    """
    Gera um par (a, b) de células H3 com distância bem definida: `b` é
    escolhido aleatoriamente do grid_disk(a, k), garantindo que
    `h3.grid_distance(a, b)` não levanta exceção.
    """
    a = draw(h3_cells(min_res=8, max_res=10))
    k = draw(st.integers(min_value=0, max_value=max_distance_k))
    neighbors = list(h3.grid_disk(a, k))
    b = draw(st.sampled_from(neighbors))
    return a, b


# ---------------------------------------------------------------------------
# grid_disk equivalence
# ---------------------------------------------------------------------------


@settings(max_examples=80, deadline=None,
          suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(cell=h3_cells(min_res=5, max_res=10),
       k=st.integers(min_value=0, max_value=5))
def test_grid_disk_equivalence(cell: str, k: int) -> None:
    """cache.grid_disk(cell, k) produz o mesmo conjunto que h3.grid_disk."""
    with H3Cache() as cache:
        cached = cache.grid_disk(cell, k)
        expected = frozenset(h3.grid_disk(cell, k))
        assert cached == expected


@settings(max_examples=40, deadline=None,
          suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(cell=h3_cells(min_res=5, max_res=10),
       k=st.integers(min_value=0, max_value=3))
def test_grid_disk_cache_hit_returns_same_result(cell: str, k: int) -> None:
    """Segunda chamada com mesmos args retorna o mesmo conjunto (hit do cache)."""
    with H3Cache() as cache:
        first = cache.grid_disk(cell, k)
        second = cache.grid_disk(cell, k)
        assert first == second
        stats = cache.stats()["grid_disk"]
        assert stats["hits"] >= 1


# ---------------------------------------------------------------------------
# grid_distance equivalence and symmetry
# ---------------------------------------------------------------------------


def _safe_grid_distance(a: str, b: str):
    """Retorna (distance, None) se definida, (None, exception) caso contrário."""
    try:
        return h3.grid_distance(a, b), None
    except Exception as exc:
        return None, exc


@settings(max_examples=80, deadline=None,
          suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(a=h3_cells(min_res=7, max_res=10),
       b=h3_cells(min_res=7, max_res=10))
def test_grid_distance_equivalence(a: str, b: str) -> None:
    """cache.grid_distance(a, b) ≡ h3.grid_distance(a, b) quando definida."""
    expected, err = _safe_grid_distance(a, b)
    with H3Cache() as cache:
        if err is None:
            assert cache.grid_distance(a, b) == expected
        else:
            # Exceções são propagadas sem mascarar o tipo original
            with pytest.raises(type(err)):
                cache.grid_distance(a, b)


@settings(max_examples=60, deadline=None,
          suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(pair=h3_cell_pairs_close())
def test_grid_distance_symmetry(pair: tuple[str, str]) -> None:
    """cache.grid_distance(a, b) == cache.grid_distance(b, a)."""
    a, b = pair
    with H3Cache() as cache:
        assert cache.grid_distance(a, b) == cache.grid_distance(b, a)


@settings(max_examples=40, deadline=None,
          suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(pair=h3_cell_pairs_close())
def test_grid_distance_normalization_maximizes_hits(pair: tuple[str, str]) -> None:
    """
    Propriedade de hit rate: (a, b) e (b, a) devem cair na MESMA entrada
    do cache — garantia de que a normalização (`a<b` swap) funciona.
    """
    a, b = pair
    assume(a != b)
    with H3Cache() as cache:
        cache.grid_distance(a, b)
        # segunda chamada com ordem invertida deve ser hit
        hits_before = cache.stats()["grid_distance"]["hits"]
        cache.grid_distance(b, a)
        hits_after = cache.stats()["grid_distance"]["hits"]
        assert hits_after > hits_before


# ---------------------------------------------------------------------------
# Exception propagation (não memoiza falhas)
# ---------------------------------------------------------------------------


def test_grid_disk_invalid_cell_propagates_exception():
    with H3Cache() as cache:
        with pytest.raises(Exception):
            cache.grid_disk("not_a_cell", 1)


def test_grid_disk_does_not_cache_exceptions():
    """lru_cache não memoriza exceções — 2ª chamada também levanta."""
    with H3Cache() as cache:
        with pytest.raises(Exception):
            cache.grid_disk("invalid", 1)
        with pytest.raises(Exception):
            cache.grid_disk("invalid", 1)
        # currsize deve ser 0 (nada armazenado para o caso inválido)
        assert cache.stats()["grid_disk"]["currsize"] == 0


# ---------------------------------------------------------------------------
# Context manager lifecycle
# ---------------------------------------------------------------------------


def test_context_manager_clears_on_exit():
    cache = H3Cache()
    cell = h3.latlng_to_cell(-23.5, -46.6, 9)
    with cache:
        cache.grid_disk(cell, 1)
        assert cache.stats()["grid_disk"]["currsize"] > 0
    # após __exit__
    assert cache.stats()["grid_disk"]["currsize"] == 0


def test_independent_caches_do_not_share_state():
    cell = h3.latlng_to_cell(-23.5, -46.6, 9)
    c1 = H3Cache()
    c2 = H3Cache()
    c1.grid_disk(cell, 1)
    assert c1.stats()["grid_disk"]["currsize"] >= 1
    assert c2.stats()["grid_disk"]["currsize"] == 0
    c1.clear()
    c2.clear()


def test_grid_disk_returns_frozenset():
    with H3Cache() as cache:
        cell = h3.latlng_to_cell(-23.5, -46.6, 9)
        result = cache.grid_disk(cell, 1)
        assert isinstance(result, frozenset)
