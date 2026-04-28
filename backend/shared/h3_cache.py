"""
shared/h3_cache.py
==================
Cache escopado para chamadas repetitivas à biblioteca `h3` durante a Fase 3.

Contexto
--------
Na Fase 3 (matching parceiros × vagas), `h3.grid_disk(cell, k)` e
`h3.grid_distance(a, b)` são chamadas milhares de vezes com os mesmos
argumentos — especialmente `grid_disk(slot.origin_hex, 1)` dentro de
`_build_hex_to_slots` e no laço de matching. Cada chamada cruza o boundary
Python↔C do `h3`, somando overhead significativo.

Este módulo expõe `H3Cache`, um wrapper memoizado escopado ao ciclo de
vida da fase: instanciado por `run_phase3`, descartado ao sair do bloco
`with`. Isso evita crescimento ilimitado de memória entre execuções
distintas do processo.

Design
------
- `grid_disk(cell, k)` → retorna `frozenset[str]` (imutável, compartilhável
  pelos callers sem cópia defensiva).
- `grid_distance(a, b)` → normaliza o par `(a, b)` em ordem lexicográfica
  antes de consultar o cache, uma vez que a distância é simétrica: isto
  aumenta a taxa de acerto sem alterar o resultado.
- Exceções do `h3` (ex.: célula inválida) são propagadas sem serem
  memoizadas (`functools.lru_cache` não cacheia falhas — chamadas
  subsequentes re-executam e re-levantam).

Uso
---
    with H3Cache() as cache:
        neighbors = cache.grid_disk("8928308280fffff", 1)
        d = cache.grid_distance("8928308280fffff", "89283082803ffff")
"""

from __future__ import annotations

from functools import lru_cache
from typing import FrozenSet, Tuple

import h3


__all__ = ["H3Cache"]


class H3Cache:
    """
    Wrapper memoizado para `h3.grid_disk` e `h3.grid_distance`.

    Parâmetros
    ----------
    maxsize_disk : capacidade máxima do cache de `grid_disk`. Default 65_536.
    maxsize_distance : capacidade máxima do cache de `grid_distance`.
                       Default 262_144 (maior porque há mais combinações de pares).

    Atributos
    ---------
    O próprio `H3Cache` é um context manager: `cache.clear()` é chamado em
    `__exit__` para liberar memória ao sair do escopo.
    """

    def __init__(
        self,
        maxsize_disk: int = 65_536,
        maxsize_distance: int = 262_144,
    ) -> None:
        # Closures com lru_cache — cada instância tem seu próprio cache,
        # independente das demais (evita vazamento entre execuções).

        @lru_cache(maxsize=maxsize_disk)
        def _grid_disk(cell: str, k: int) -> FrozenSet[str]:
            return frozenset(h3.grid_disk(cell, k))

        @lru_cache(maxsize=maxsize_distance)
        def _grid_distance(pair: Tuple[str, str]) -> int:
            a, b = pair
            return h3.grid_distance(a, b)

        self._grid_disk = _grid_disk
        self._grid_distance = _grid_distance

    # ------------------------------------------------------------------ API

    def grid_disk(self, cell: str, k: int = 1) -> FrozenSet[str]:
        """Retorna o conjunto de células vizinhas a `cell` a distância `k`.

        Resultado imutável (`frozenset`) — caller deve converter para `set`
        se precisar de mutabilidade.
        """
        return self._grid_disk(cell, k)

    def grid_distance(self, a: str, b: str) -> int:
        """Retorna a distância em células entre `a` e `b`.

        O par é normalizado em ordem lexicográfica antes da consulta ao
        cache (distância é simétrica — maximiza hit rate).
        """
        pair = (a, b) if a <= b else (b, a)
        return self._grid_distance(pair)

    # ------------------------------------------------------------------ Ops

    def stats(self) -> dict:
        """Retorna `cache_info()` de ambos os caches como dict para logging."""
        return {
            "grid_disk": self._grid_disk.cache_info()._asdict(),
            "grid_distance": self._grid_distance.cache_info()._asdict(),
        }

    def clear(self) -> None:
        """Limpa ambos os caches. Chamado automaticamente no `__exit__`."""
        self._grid_disk.cache_clear()
        self._grid_distance.cache_clear()

    # -------------------------------------------------------- Context Manager

    def __enter__(self) -> "H3Cache":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.clear()
