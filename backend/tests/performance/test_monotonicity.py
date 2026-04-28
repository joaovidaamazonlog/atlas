"""
tests/performance/test_monotonicity.py
=======================================
Gate de monotonicidade de performance.

Lê `fixtures/baseline.json` (coletado na primeira execução pós-instrumentação)
e compara com um `TimingReport` novo executado sobre a mesma fixture.
Qualquer fase que regrida além de `TOLERANCE` (5%) faz o teste falhar,
reportando fase, tempo atual e baseline.

Como o teste E2E, este só roda se a fixture de inputs + baseline
existirem no repositório.

Referências: Requirements 6.1, 6.2, 6.3, 6.4, 6.5
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from shared.timing import TimingReport


FIXTURE_INPUTS = Path(__file__).parent / "fixtures" / "inputs"
BASELINE_PATH = Path(__file__).parent / "fixtures" / "baseline.json"

# Tolerância de 5% — absorve jitter de CI (I/O, cache de disco, etc.).
TOLERANCE = 1.05


@pytest.mark.skipif(
    not (FIXTURE_INPUTS.exists() and BASELINE_PATH.exists()),
    reason=(
        "Fixture de inputs ou baseline.json não encontrados. "
        "Gere-os com `python -m vanilla.orchestrator --mode daily --output "
        "<fixture_inputs>` e copie o timing_report.json resultante para "
        "tests/performance/fixtures/baseline.json. "
        "Veja tests/performance/README.md."
    ),
)
def test_phase_timings_do_not_regress(tmp_path: Path):
    """
    Cada fase do pipeline deve ter tempo <= baseline * TOLERANCE.
    """
    from vanilla.orchestrator import run_daily

    shutil.copytree(FIXTURE_INPUTS, tmp_path / "run")
    report = run_daily(
        str(tmp_path / "run"),
        timing_report=TimingReport(pipeline="daily"),
    )
    baseline = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
    baseline_phases = {p["name"]: p["duration_s"] for p in baseline.get("phases", [])}

    regressions = []
    for phase in report.phases:
        b = baseline_phases.get(phase.name)
        if b is None:
            continue  # fase nova — não há baseline ainda
        limit = b * TOLERANCE
        if phase.duration_s > limit:
            regressions.append(
                f"  {phase.name}: {phase.duration_s:.2f}s > "
                f"baseline {b:.2f}s × {TOLERANCE} = {limit:.2f}s"
            )

    assert not regressions, "Regressões de performance detectadas:\n" + "\n".join(regressions)


def test_baseline_schema_is_valid():
    """
    Sanity: se `baseline.json` existir, deve ter o schema do TimingReport.
    """
    if not BASELINE_PATH.exists():
        pytest.skip("baseline.json ausente — nada a validar.")
    baseline = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
    assert "pipeline" in baseline
    assert "total_s" in baseline
    assert "phases" in baseline
    for p in baseline["phases"]:
        assert "name" in p
        assert "duration_s" in p
