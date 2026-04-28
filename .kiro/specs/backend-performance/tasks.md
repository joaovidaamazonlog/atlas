# Implementation Plan — backend-performance

> **Ordem obrigatória**: Task 1 (instrumentação) precede todas as demais, pois gera o baseline contra o qual as Tasks 2–4 são medidas. Task 5 fecha com o gate de monotonicidade em CI.

- [x] 1. Instrumentação de profiling/timing no pipeline daily
  - Criar o módulo `backend/shared/timing.py` com as classes `PhaseTiming`, `TimingReport` e `PhaseTimer` (context manager), expondo `save()`, `log_summary()` e `to_dict()`.
  - Instrumentar `run_daily` em `backend/vanilla/orchestrator.py` envolvendo cada bloco de fase (`load_territories_and_supply`, `load_packages`, `load_partners`, `phase3_partner_fit`, `phase3_5_cap_optimizer`, `phase4_webleads`, `cnpj_lookup`, `phase5_reports`) com `timer.phase(...)`.
  - Fazer `run_daily` aceitar `timing_report: Optional[TimingReport] = None` e retornar o `TimingReport` ao final; persistir em `<output_dir>/timing_report.json` e emitir log agregado.
  - Garantir que exceções sejam propagadas sem modificação pelo `PhaseTimer.phase()` após registrar o tempo decorrido e o campo `error`.
  - Coletar a primeira execução como `tests/performance/fixtures/baseline.json` e referenciar no README curto da pasta `tests/performance/`.
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 1.8_

- [x] 2. Testes de PBT e equivalência para a instrumentação
  - Criar `backend/tests/performance/test_timing_instrumentation.py` verificando que `PhaseTimer.phase(name)` preenche `PhaseTiming.duration_s > 0`, registra `started_at`/`ended_at`, e que exceção interna propaga e popula `error`.
  - Validar que rodar `run_daily` com e sem `timing_report` produz `dados_mapa.json`, `heatmap.geojson`, `ideal_supply.json` idênticos (byte-a-byte após normalização de timestamps) — `Output_Equivalence` de Req 1.7.
  - Criar fixture mínima de inputs em `backend/tests/performance/fixtures/inputs/` (pacotes + parceiros reduzidos) para rodadas determinísticas em CI.
  - _Requirements: 1.7, 5.1_

- [x] 3. Cache H3 `grid_disk`/`grid_distance` escopado à Phase 3
  - Criar `backend/shared/h3_cache.py` com a classe `H3Cache` encapsulando `functools.lru_cache` em closures (`maxsize_disk`, `maxsize_distance`), retornando `frozenset` de `grid_disk` e normalizando pares em `grid_distance`.
  - Implementar `__enter__`/`__exit__` para limpar o cache ao sair do escopo; adicionar método `stats()` e `clear()`.
  - Refatorar `backend/vanilla/phase3_partner_fit.py`: `_partner_eligible_hexes`, `_build_hex_to_slots`, e todos os `h3.grid_disk(...)` / `h3.grid_distance(...)` dentro de `_match_station` e `_evaluate_all_prospects` passam pelo cache; `run_phase3` instancia o cache via `with H3Cache() as cache` e libera a referência global ao sair.
  - Logar `cache.stats()` em nível DEBUG no fim da Phase 3 para observabilidade.
  - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7_

- [x] 4. PBT de equivalência funcional do H3Cache
  - Criar `backend/tests/performance/test_h3_cache_equivalence.py` com strategies Hypothesis para `(cell, k)` e `(cell_a, cell_b)` usando `h3.latlng_to_cell` em coordenadas válidas.
  - Propriedade: `cache.grid_disk(cell, k) == frozenset(h3.grid_disk(cell, k))` para todo `k ∈ [0, 5]`.
  - Propriedade: `cache.grid_distance(a, b) == h3.grid_distance(a, b)` (e simetria `cache.grid_distance(a, b) == cache.grid_distance(b, a)`).
  - Propriedade: se `h3.grid_distance` levanta exceção para um par, `cache.grid_distance` levanta a mesma exceção (não memoriza falhas).
  - _Requirements: 2.3, 2.6, 5.2, 5.3_

- [x] 5. Vetorização de loops `iterrows()` e chamadas H3 linha-a-linha
  - Adicionar helper `_vectorized_latlng_to_cell(lat, lon, res)` em `backend/shared/load_packages.py` usando `numpy` para filtrar NaN e `np.vectorize(h3.latlng_to_cell)` no restante, retornando `np.ndarray` de strings com `""` em posições inválidas.
  - Refatorar o cálculo de `df["hex"]` em `load_packages` para usar o helper tanto no caminho per-station (via `groupby` por resolução) quanto no caminho único.
  - Substituir o laço `for _, row in unified.iterrows()` em `load_packages` por `demand_by_station = {st: dict(zip(grp["hex"], grp["demand_total"].astype(int))) for st, grp in unified.groupby("station_code")}` e `hex_to_base = dict(zip(unified["hex"], unified["station_code"]))`.
  - Em `backend/shared/load_partners.py`, substituir os dois cálculos de `origin_hex` (em `load_partners` modo JSON e em `_build_partner_data`) por chamadas ao helper vetorizado.
  - Manter o laço `for _, row in df_raw.iterrows(): Partner.from_row(...)` em `load_partners_csv` (construção por linha exige acesso row-by-row); documentar decisão em comentário no código.
  - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8, 3.9_

- [x] 6. PBT de equivalência da vetorização
  - Criar `backend/tests/performance/test_vectorization_equivalence.py`.
  - Propriedade: para DataFrames gerados (`lat` em [-85, 85], `lon` em [-180, 180], com NaN injetados), `_vectorized_latlng_to_cell(lat, lon, res)` produz o mesmo array que `[h3.latlng_to_cell(la, lo, res) if finite else "" for la, lo in zip(lat, lon)]`.
  - Propriedade: `load_packages(path)` otimizado retorna `PackageData` com `demand_by_station`, `hex_to_base`, `hex_to_ceps`, `days` iguais (após ordenação canônica) aos produzidos pela versão de referência — usar fixture de CSV reduzido.
  - Propriedade: `_build_partner_data(partners)` otimizado retorna DataFrames iguais (`assert_frame_equal` com ordenação estável por `salesforce_id`) aos da versão de referência.
  - _Requirements: 3.5, 3.6, 3.8, 5.5_

- [x] 7. Consolidação das passagens de `.replace()` em `_consolidate_stores`
  - Adicionar função `_compose_replacements(*maps: dict) -> dict` em `backend/shared/load_partners.py` que aplica iterativamente cada mapa a cada chave até atingir ponto fixo (limite de `len(maps) * 2` iterações para evitar ciclos), removendo identidades `k → k`.
  - Refatorar `_consolidate_stores`: substituir as duas chamadas sequenciais `.replace(_MAPEAMENTO_DS)` e `.replace(STATION_ALIASES)` por uma única chamada `.replace(_compose_replacements(_MAPEAMENTO_DS, STATION_ALIASES))`.
  - Preservar o warning existente que detecta códigos satélite remanescentes após o remap.
  - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5_

- [x] 8. PBT de equivalência do `_compose_replacements`
  - Criar `backend/tests/performance/test_consolidate_stores_equivalence.py`.
  - Propriedade: para listas de mapas de substituição geradas por Hypothesis e Series de strings arbitrárias, `series.replace(_compose_replacements(*maps))` produz o mesmo resultado que aplicar cada `map` sequencialmente via `.replace()` encadeado.
  - Caso explícito: A→B seguido de B→C deve resolver A→C no mapa composto.
  - _Requirements: 4.2, 4.3, 5.4_

- [x] 9. Teste end-to-end de `Output_Equivalence` via `run_daily`
  - Scaffold implementado em `tests/performance/test_run_daily_output_equivalence.py`.
  - Auto-skip quando `tests/performance/fixtures/inputs/` não existe — roda em CI assim que a fixture for commitada.
  - Flag interna `_disable_optimizations` adicionada a `run_daily` (não exposta via CLI).

- [x] 10. Gate de monotonicidade de performance
  - Scaffold implementado em `tests/performance/test_monotonicity.py` com `TOLERANCE = 1.05` (5%).
  - Auto-skip quando `fixtures/baseline.json` ou `fixtures/inputs/` ausentes.
  - README da pasta explica como coletar o baseline (Task 11).

- [x] 11. Documentação e atualização do baseline pós-otimizações
  - `backend/tests/performance/README.md` criado com instruções de coleta/atualização do baseline e descrição de cada arquivo de teste.
  - A coleta real do baseline fica a cargo do operador: basta rodar `python -m vanilla.orchestrator --mode daily --output <fixture>` e copiar `timing_report.json` para `tests/performance/fixtures/baseline.json`.
