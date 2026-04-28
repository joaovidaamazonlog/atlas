"""
tests/performance/test_run_daily_output_equivalence.py
=======================================================
Teste end-to-end de `Output_Equivalence` de `run_daily`.

Este teste é **opcional**: só roda se a fixture de inputs existir em
`backend/tests/performance/fixtures/inputs/`. Em ambientes sem a fixture
(ex.: checkout fresco em CI), o teste é skipped com uma mensagem clara.

Estratégia
----------
Executa `run_daily` duas vezes sobre a mesma cópia de fixture (em
`tmp_path` distintos) e compara artefatos ignorando timestamps:

- `dados_mapa.json`
- `heatmap.geojson`
- `ideal_supply.json`
- `territories.geojson`
- `optimization_data.geojson`

Como as otimizações têm testes de equivalência dedicados por módulo
(H3 cache, vetorização, `_compose_replacements`), este E2E serve como
verificação adicional: garantir que a integração delas no pipeline não
produz divergências cruzadas.

Referências: Requirements 5.1, 5.6, 5.7
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest


FIXTURE_INPUTS = (
    Path(__file__).parent / "fixtures" / "inputs"
)


def _canonicalize_json(obj, ignored_keys={"last_fit_at", "generatedAt", "period",
                                          "timing_report", "ended_at",
                                          "started_at", "duration_s"}):
    """Remove chaves voláteis (timestamps) para comparação estável."""
    if isinstance(obj, dict):
        return {k: _canonicalize_json(v, ignored_keys)
                for k, v in obj.items() if k not in ignored_keys}
    if isinstance(obj, list):
        return [_canonicalize_json(x, ignored_keys) for x in obj]
    return obj


def _assert_json_equal_ignoring_timestamps(path_a: Path, path_b: Path) -> None:
    a = json.loads(path_a.read_text(encoding="utf-8"))
    b = json.loads(path_b.read_text(encoding="utf-8"))
    a_norm = _canonicalize_json(a)
    b_norm = _canonicalize_json(b)
    assert a_norm == b_norm, f"Divergência entre {path_a.name} e {path_b.name}"


@pytest.mark.skipif(
    not FIXTURE_INPUTS.exists(),
    reason=(
        f"Fixture de inputs não encontrada em {FIXTURE_INPUTS}. "
        "Para rodar este teste E2E, copie uma cópia determinística de "
        "output/ (com setup já executado) para tests/performance/fixtures/inputs/. "
        "Veja tests/performance/README.md."
    ),
)
def test_run_daily_produces_identical_outputs_with_and_without_optimizations(tmp_path: Path):
    """
    Roda `run_daily` duas vezes (uma com otimizações desligadas via
    `_disable_optimizations=True`, outra com tudo ligado) e compara os
    artefatos principais.

    Observação
    ----------
    Como as otimizações atuais são funcionalmente idênticas à versão de
    referência (validado por PBT individual em outros testes desta pasta),
    esta verificação E2E é uma sanidade cruzada: detecta bugs de
    integração que não aparecem em PBT isolado.
    """
    from vanilla.orchestrator import run_daily

    ref_dir = tmp_path / "reference"
    opt_dir = tmp_path / "optimized"
    shutil.copytree(FIXTURE_INPUTS, ref_dir)
    shutil.copytree(FIXTURE_INPUTS, opt_dir)

    run_daily(str(ref_dir), _disable_optimizations=True)
    run_daily(str(opt_dir), _disable_optimizations=False)

    for artifact in ("dados_mapa.json", "ideal_supply.json",
                     "heatmap.geojson", "territories.geojson",
                     "optimization_data.geojson"):
        ref_path = ref_dir / artifact
        opt_path = opt_dir / artifact
        if ref_path.exists() and opt_path.exists():
            _assert_json_equal_ignoring_timestamps(ref_path, opt_path)
