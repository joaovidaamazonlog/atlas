"""
shared/timing.py
================
Instrumentação de tempo por fase para o pipeline `daily` (e `setup`).

Uso típico
----------
    from shared.timing import PhaseTimer, TimingReport

    report = TimingReport(pipeline="daily")
    timer  = PhaseTimer(report)

    with timer.phase("load_packages"):
        pkg = load_packages(...)

    with timer.phase("phase3_partner_fit"):
        fit = run_phase3(...)

    timer.end_pipeline()
    report.log_summary()
    report.save(Path(output_dir) / "timing_report.json")

O `TimingReport` é serializável para JSON (persistido em disco como
baseline/artefato) e também acessível por testes via `report.phase(name)`.

Contrato de preservação de output
---------------------------------
A instrumentação NÃO altera o fluxo funcional do pipeline. Exceções
levantadas dentro de `timer.phase(...)` são propagadas sem modificação
após o tempo decorrido ser registrado no `PhaseTiming.error`.
"""

from __future__ import annotations

import json
import logging
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterator, List, Optional

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# DATA CLASSES
# ---------------------------------------------------------------------------

@dataclass
class PhaseTiming:
    """Métricas de uma única fase do pipeline."""

    name: str
    duration_s: float
    started_at: float
    ended_at: float
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, object]:
        return {
            "name": self.name,
            "duration_s": round(self.duration_s, 3),
            "started_at": self.started_at,
            "ended_at": self.ended_at,
            "error": self.error,
        }


@dataclass
class TimingReport:
    """Relatório agregado de uma execução do pipeline."""

    pipeline: str = "daily"
    phases: List[PhaseTiming] = field(default_factory=list)
    total_s: float = 0.0
    started_at: float = 0.0
    ended_at: float = 0.0

    # ------------------------------------------------------------------ API

    def phase(self, name: str) -> Optional[PhaseTiming]:
        """Retorna o último `PhaseTiming` com o nome dado (ou None)."""
        for p in reversed(self.phases):
            if p.name == name:
                return p
        return None

    def to_dict(self) -> Dict[str, object]:
        return {
            "pipeline": self.pipeline,
            "total_s": round(self.total_s, 3),
            "started_at": self.started_at,
            "ended_at": self.ended_at,
            "phases": [p.to_dict() for p in self.phases],
        }

    def save(self, path: Path) -> None:
        """Serializa o relatório como JSON indentado."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(self.to_dict(), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    def log_summary(self) -> None:
        """Emite um sumário por fase + tempo total via logging.INFO."""
        log.info("-" * 60)
        log.info("  TIMING REPORT — pipeline=%s", self.pipeline)
        for p in self.phases:
            status = f" [FAIL: {p.error}]" if p.error else ""
            log.info(f"    {p.name:32s} {p.duration_s:9.2f}s{status}")
        log.info(f"    {'TOTAL':32s} {self.total_s:9.2f}s")
        log.info("-" * 60)


# ---------------------------------------------------------------------------
# CONTEXT MANAGER
# ---------------------------------------------------------------------------

class PhaseTimer:
    """
    Context manager reutilizável que acumula tempos em um `TimingReport`.

    O relógio do pipeline é iniciado automaticamente no primeiro `phase(...)`
    chamado, e deve ser fechado com `end_pipeline()` para consolidar o total.
    """

    def __init__(self, report: TimingReport) -> None:
        self.report = report
        self._pipeline_started = False

    def start_pipeline(self) -> None:
        if not self._pipeline_started:
            self.report.started_at = time.time()
            self._pipeline_started = True

    def end_pipeline(self) -> None:
        self.report.ended_at = time.time()
        self.report.total_s = self.report.ended_at - self.report.started_at

    @contextmanager
    def phase(self, name: str) -> Iterator[None]:
        """
        Mede o tempo decorrido do bloco e anexa ao relatório.

        Se o bloco levanta exceção, o tempo decorrido até a exceção é
        registrado e o `error` preenchido; a exceção é re-propagada sem
        modificação.
        """
        if not self._pipeline_started:
            self.start_pipeline()

        t0 = time.time()
        err: Optional[str] = None
        try:
            yield
        except BaseException as exc:  # noqa: BLE001 — captura todas para registrar tempo
            err = f"{type(exc).__name__}: {exc}"
            raise
        finally:
            t1 = time.time()
            self.report.phases.append(
                PhaseTiming(
                    name=name,
                    duration_s=t1 - t0,
                    started_at=t0,
                    ended_at=t1,
                    error=err,
                )
            )
            suffix = f" (FAIL: {err})" if err else ""
            log.info("[timing] %s: %.2fs%s", name, t1 - t0, suffix)


__all__ = ["PhaseTiming", "TimingReport", "PhaseTimer"]
