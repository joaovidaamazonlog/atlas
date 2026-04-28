# Testes de performance — backend-performance

Esta pasta agrupa os testes da spec `backend-performance`:

- `test_timing_instrumentation.py` — Unidade do `shared.timing` (`PhaseTimer`, `TimingReport`).
- `test_h3_cache_equivalence.py` — PBT da equivalência funcional do H3Cache (Task 4).
- `test_vectorization_equivalence.py` — PBT da vetorização (Task 6).
- `test_consolidate_stores_equivalence.py` — PBT do `_compose_replacements` (Task 8).
- `test_run_daily_output_equivalence.py` — E2E de `Output_Equivalence` via `run_daily` (Task 9).
- `test_monotonicity.py` — Gate de regressão de performance contra `fixtures/baseline.json` (Task 10).

## Baseline

O arquivo `fixtures/baseline.json` contém o `TimingReport` de referência.
Ele é coletado na primeira execução pós-instrumentação e atualizado apenas
quando uma otimização aprovada reduz os tempos.

### Como coletar/atualizar o baseline

```bash
# A partir de backend/
python -m vanilla.orchestrator --mode daily --output <fixture_dir>
# O timing_report.json é gerado automaticamente em <fixture_dir>/timing_report.json.
# Copie para tests/performance/fixtures/baseline.json se os números forem representativos.
```

Em CI, `test_monotonicity.py` compara a execução atual com o baseline e
falha se qualquer fase regride mais de 5% (tolerância configurável).
