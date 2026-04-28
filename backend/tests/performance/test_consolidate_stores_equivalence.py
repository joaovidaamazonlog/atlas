"""
tests/performance/test_consolidate_stores_equivalence.py
=========================================================
Property-based tests (Hypothesis) da equivalência entre a versão
consolidada (`_compose_replacements` + única `.replace(dict)`) e a
versão sequencial original (`.replace(m1).replace(m2)...`).

Propriedades validadas:
- Para toda lista de mapas `(m1, ..., mn)` e toda Series de strings `s`,
  `s.replace(_compose_replacements(*maps))` ≡ cadeia sequencial
  `s.replace(m1).replace(m2).(...).replace(mn)`.
- Caso explícito de cadeia: `A → B` seguido de `B → C` se resolve em
  `A → C` no mapa composto (equivalente à aplicação sequencial).
- `_compose_replacements()` sem argumentos retorna `{}` (identidade).
- Identidades (`k → k`) são removidas do resultado, mas a semântica de
  `.replace()` permanece preservada.

Referências: Requirements 4.2, 4.3, 5.4
"""

from __future__ import annotations

import pandas as pd
import pytest
from hypothesis import HealthCheck, given, settings, strategies as st

from shared.load_partners import _compose_replacements


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------


# Alfabeto pequeno intencional — aumenta a chance de colisões entre mapas
# e de formação de cadeias transitivas (A→B→C).
_ALPHABET = "ABCDEFGH"


def _small_string():
    return st.text(alphabet=_ALPHABET, min_size=1, max_size=3)


def _map_strategy(min_size: int = 0, max_size: int = 6):
    return st.dictionaries(_small_string(), _small_string(),
                           min_size=min_size, max_size=max_size)


def _maps_list_strategy(min_lists: int = 1, max_lists: int = 4):
    return st.lists(_map_strategy(), min_size=min_lists, max_size=max_lists)


def _values_strategy(max_size: int = 30):
    return st.lists(_small_string(), min_size=0, max_size=max_size)


# ---------------------------------------------------------------------------
# Propriedade principal: equivalência com cadeia sequencial
# ---------------------------------------------------------------------------


@settings(max_examples=150, deadline=None,
          suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(maps=_maps_list_strategy(), values=_values_strategy())
def test_compose_replacements_matches_sequential(maps: list[dict], values: list[str]):
    """
    `s.replace(composed)` produz o MESMO resultado que aplicar cada mapa
    sequencialmente via `.replace()` encadeado.
    """
    s = pd.Series(values, dtype=object)

    # Referência: sequencial
    ref = s.copy()
    for m in maps:
        if m:
            ref = ref.replace(m)

    # Otimizado: passagem única com mapa composto
    composed = _compose_replacements(*maps)
    opt = s.replace(composed) if composed else s.copy()

    # Ambas as Series devem ser iguais (conteúdo e posição)
    assert list(opt) == list(ref), (
        f"divergência: maps={maps}, values={values}, "
        f"composed={composed}, ref={list(ref)}, opt={list(opt)}"
    )


# ---------------------------------------------------------------------------
# Casos explícitos
# ---------------------------------------------------------------------------


def test_transitive_chain_two_maps():
    """A→B seguido de B→C resolve A→C no mapa composto."""
    composed = _compose_replacements({"A": "B"}, {"B": "C"})
    assert composed["A"] == "C"
    assert composed["B"] == "C"


def test_transitive_chain_three_maps():
    """A→B, B→C, C→D resolve A→D."""
    composed = _compose_replacements({"A": "B"}, {"B": "C"}, {"C": "D"})
    assert composed["A"] == "D"
    assert composed["B"] == "D"
    assert composed["C"] == "D"


def test_empty_maps_return_empty_dict():
    assert _compose_replacements() == {}
    assert _compose_replacements({}, {}, {}) == {}


def test_identity_mappings_are_removed():
    """`k → k` não aparece no resultado final (otimização de output)."""
    composed = _compose_replacements({"A": "A", "B": "C"})
    assert "A" not in composed
    assert composed["B"] == "C"


def test_no_overlap_preserves_both_maps():
    """Mapas disjuntos compõem-se sem perder entradas."""
    composed = _compose_replacements({"A": "B"}, {"X": "Y"})
    assert composed == {"A": "B", "X": "Y"}


def test_disjoint_values_applied_via_series():
    """Propriedade concreta sobre pandas."""
    s = pd.Series(["A", "B", "X", "Y", "Z"])
    maps = ({"A": "B"}, {"B": "C"})
    ref = s.replace(maps[0]).replace(maps[1])
    opt = s.replace(_compose_replacements(*maps))
    assert list(ref) == list(opt)


# ---------------------------------------------------------------------------
# Robustez: cadeias cíclicas
# ---------------------------------------------------------------------------


def test_single_map_swap_is_identity_after_compose():
    """
    Swap dentro de um MESMO mapa (`{"A": "B", "B": "A"}`) é atômico em
    `pd.replace` — A e B são trocados em paralelo, sem ciclo.

    Em `_compose_replacements` com um único mapa, cada chave sofre UMA
    aplicação: `A → B` e `B → A`. Depois identidades são removidas,
    então o output final é `{"A": "B", "B": "A"}` — equivalente ao mapa
    original.
    """
    composed = _compose_replacements({"A": "B", "B": "A"})
    assert composed == {"A": "B", "B": "A"}


def test_cyclic_chain_does_not_hang():
    """
    Mapas encadeados `{"A": "B"}` e `{"B": "A"}` produzem A→A (identidade
    após 2 aplicações sequenciais), portanto removido do output.
    """
    composed = _compose_replacements({"A": "B"}, {"B": "A"})
    # A→B pelo m1, depois B→A pelo m2 ⇒ A→A (removido)
    assert "A" not in composed
    # B é chave de m2 mas não de m1: B→A pelo m2, m1 não transforma A.
    assert composed.get("B") == "A"
