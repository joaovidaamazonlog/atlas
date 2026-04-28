"""
tests/performance/test_timing_instrumentation.py
=================================================
Testes unitários do módulo `shared.timing`.

Valida:
- `PhaseTimer.phase(name)` preenche `PhaseTiming.duration_s`, `started_at`
  e `ended_at` corretamente.
- Exceção interna é propagada sem modificação E o `error` do `PhaseTiming`
  é preenchido com o tipo e mensagem da exceção.
- `TimingReport.phase(name)` retorna o último `PhaseTiming` com o nome dado.
- `TimingReport.save(path)` produz um JSON serializável com todos os campos.
- Múltiplas fases acumulam no `phases` na ordem de chamada.
- `TimingReport` roundtrip JSON preserva os dados relevantes.

Referências: Requirements 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 1.8
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from shared.timing import PhaseTimer, PhaseTiming, TimingReport


# ---------------------------------------------------------------------------
# PhaseTimer — casos felizes
# ---------------------------------------------------------------------------


def test_phase_timer_records_positive_duration():
    report = TimingReport(pipeline="unit")
    timer = PhaseTimer(report)

    with timer.phase("a"):
        time.sleep(0.01)

    timer.end_pipeline()

    assert len(report.phases) == 1
    p = report.phases[0]
    assert p.name == "a"
    assert p.duration_s >= 0.009  # folga para jitter do relógio
    assert p.ended_at >= p.started_at
    assert p.error is None
    assert report.total_s >= p.duration_s


def test_phase_timer_multiple_phases_in_order():
    report = TimingReport(pipeline="unit")
    timer = PhaseTimer(report)

    with timer.phase("first"):
        pass
    with timer.phase("second"):
        pass
    with timer.phase("third"):
        pass

    timer.end_pipeline()

    assert [p.name for p in report.phases] == ["first", "second", "third"]
    # started_at monotonicamente crescente
    for i in range(len(report.phases) - 1):
        assert report.phases[i].started_at <= report.phases[i + 1].started_at


def test_phase_timer_auto_starts_pipeline():
    """`phase(...)` chamado antes de `start_pipeline()` inicia automaticamente."""
    report = TimingReport(pipeline="unit")
    timer = PhaseTimer(report)
    # não chamamos start_pipeline explicitamente

    with timer.phase("a"):
        pass

    assert report.started_at > 0.0


# ---------------------------------------------------------------------------
# PhaseTimer — exceções
# ---------------------------------------------------------------------------


def test_phase_timer_propagates_exception_unchanged():
    report = TimingReport(pipeline="unit")
    timer = PhaseTimer(report)

    class _CustomError(RuntimeError):
        pass

    with pytest.raises(_CustomError, match="boom"):
        with timer.phase("will_fail"):
            raise _CustomError("boom")

    # duração e campo de erro foram registrados
    assert len(report.phases) == 1
    p = report.phases[0]
    assert p.name == "will_fail"
    assert p.duration_s >= 0
    assert p.error is not None
    assert "_CustomError" in p.error
    assert "boom" in p.error


def test_phase_timer_records_time_even_on_exception():
    report = TimingReport(pipeline="unit")
    timer = PhaseTimer(report)

    with pytest.raises(ValueError):
        with timer.phase("slow_fail"):
            time.sleep(0.005)
            raise ValueError("x")

    p = report.phases[0]
    assert p.duration_s >= 0.004


# ---------------------------------------------------------------------------
# TimingReport — lookup, dict, save
# ---------------------------------------------------------------------------


def test_report_phase_lookup_returns_last_occurrence():
    report = TimingReport(pipeline="unit")
    timer = PhaseTimer(report)

    with timer.phase("repeated"):
        pass
    first_end = report.phases[0].ended_at

    with timer.phase("repeated"):
        pass
    second_end = report.phases[1].ended_at

    assert report.phase("repeated").ended_at == second_end
    assert second_end >= first_end
    assert report.phase("missing") is None


def test_report_to_dict_shape():
    report = TimingReport(pipeline="unit")
    timer = PhaseTimer(report)

    with timer.phase("a"):
        pass
    timer.end_pipeline()

    d = report.to_dict()
    assert d["pipeline"] == "unit"
    assert isinstance(d["total_s"], float)
    assert isinstance(d["phases"], list)
    assert len(d["phases"]) == 1
    assert d["phases"][0]["name"] == "a"
    assert d["phases"][0]["error"] is None


def test_report_save_produces_valid_json(tmp_path: Path):
    report = TimingReport(pipeline="unit")
    timer = PhaseTimer(report)

    with timer.phase("a"):
        pass
    with timer.phase("b"):
        pass
    timer.end_pipeline()

    out = tmp_path / "nested" / "timing.json"
    report.save(out)

    assert out.exists()
    loaded = json.loads(out.read_text(encoding="utf-8"))
    assert loaded["pipeline"] == "unit"
    assert [p["name"] for p in loaded["phases"]] == ["a", "b"]
    assert loaded["total_s"] >= 0.0


def test_phase_timing_to_dict_round_numbers():
    pt = PhaseTiming(
        name="x",
        duration_s=1.23456789,
        started_at=100.0,
        ended_at=101.23456789,
    )
    d = pt.to_dict()
    assert d["name"] == "x"
    # arredondamento a 3 casas decimais
    assert d["duration_s"] == 1.235
    assert d["error"] is None


# ---------------------------------------------------------------------------
# Output_Equivalence: `timing_report` não altera o comportamento funcional
# ---------------------------------------------------------------------------
# O teste end-to-end completo vive em test_run_daily_output_equivalence.py
# (Task 9). Aqui validamos apenas o contrato da instrumentação em isolamento.


def test_phase_timer_does_not_mutate_yielded_context():
    """O bloco `with timer.phase(...)` entrega `None` como valor yielded."""
    report = TimingReport(pipeline="unit")
    timer = PhaseTimer(report)

    with timer.phase("a") as yielded:
        assert yielded is None

    assert len(report.phases) == 1


def test_report_phases_preserve_insertion_order_on_mixed_success_failure():
    report = TimingReport(pipeline="unit")
    timer = PhaseTimer(report)

    with timer.phase("ok1"):
        pass

    with pytest.raises(RuntimeError):
        with timer.phase("fail"):
            raise RuntimeError("x")

    with timer.phase("ok2"):
        pass

    timer.end_pipeline()

    assert [p.name for p in report.phases] == ["ok1", "fail", "ok2"]
    assert report.phases[0].error is None
    assert report.phases[1].error is not None
    assert report.phases[2].error is None
