# Plano de Implementação: Geo Cap Optimization

## Visão Geral

Implementar a Fase 3.5 do pipeline GeoIntelligence daily (backend): identificar oportunidades de aumento de cap para parceiros Active com base na demanda não coberta de `geo_h3_cells` (res 9), persistir os resultados no Turso e expô-los via endpoint REST na `geo_api.py`.

## Tasks

- [x] 1. Backend — Adicionar DDL de `geo_partner_cap_opportunities` ao `TursoWriter`
  - Adicionar o DDL da tabela `geo_partner_cap_opportunities` à lista `_DDL_STATEMENTS` em `backend/geo_intelligence/turso_writer.py`
  - Schema: `partner_id TEXT NOT NULL`, `run_id TEXT NOT NULL`, `station_code TEXT NOT NULL`, `suggested_lat REAL`, `suggested_lon REAL`, `suggested_cap INTEGER`, `suggested_radius INTEGER`, `estimated_adv_gain INTEGER`, `distance_from_current REAL`, `created_at TEXT NOT NULL`, `PRIMARY KEY (partner_id, run_id)`
  - A tabela é criada automaticamente via `ensure_schema()` — nenhuma alteração adicional necessária
  - _Requirements: 3.1, 3.2_

- [x] 2. Backend — Implementar `TursoWriter.upsert_cap_opportunities`
  - Adicionar o método `upsert_cap_opportunities(self, run_id: str, opportunities: List[Dict]) -> None` em `backend/geo_intelligence/turso_writer.py`
  - Cada dict em `opportunities` deve conter: `partner_id`, `station_code`, `suggested_lat`, `suggested_lon`, `suggested_cap`, `suggested_radius`, `estimated_adv_gain`, `distance_from_current`, `created_at`
  - Usar `INSERT ... ON CONFLICT(partner_id, run_id) DO UPDATE` para idempotência
  - Usar `_execute_batch_with_retry` com batches de `_BATCH_SIZE` (padrão 100)
  - _Requirements: 3.3_

- [x] 3. Backend — Implementar `TursoReader.get_h3_cells_for_station` e `TursoReader.get_cap_opportunities`
  - [x] 3.1 Implementar `get_h3_cells_for_station(self, station_code: str, run_id: str) -> List[Dict]` em `backend/geo_intelligence/turso_reader.py`
    - Retorna todos os registros de `geo_h3_cells` para a base/run_id
    - Cache TTL 5 min com chave `h3_cells_station:{station_code}:{run_id}`
    - _Requirements: 7.1, 7.4_

  - [x] 3.2 Implementar `get_cap_opportunities(self, station_code: str, run_id: Optional[str] = None, only_with_opportunity: bool = False) -> List[Dict]` em `backend/geo_intelligence/turso_reader.py`
    - Se `run_id` não for fornecido, resolver via `get_latest_run_id(station_code)`
    - Se `only_with_opportunity=True`, filtrar apenas registros com `estimated_adv_gain IS NOT NULL`
    - Cache TTL 5 min com chave `cap_opportunities:{station_code}:{run_id}`
    - Retornar lista vazia (sem lançar exceção) se não houver registros
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5_

- [x] 4. Backend — Criar `geo_phase3_5_cap_optimizer.py` com helpers e entry point
  - [x] 4.1 Criar `backend/geo_intelligence/geo_phase3_5_cap_optimizer.py` com `_haversine_m` e `_disaggregate_r8_to_r9`
    - `_haversine_m(lat1, lon1, lat2, lon2) -> float`: distância geodésica em metros (fórmula de Haversine)
    - `_disaggregate_r8_to_r9(h3_id_r8, density_r8) -> Dict[str, float]`: usa `h3.cell_to_children(h3_id_r8, 9)`, distribui `density_r8 / n_children` por filho; retorna `{h3_id_r9: density_r9}`
    - _Requirements: 2.5, 7.2, 7.3_

  - [x] 4.2 Escrever teste de propriedade — Propriedade 8: Simetria e identidade de `_haversine_m`
    - **Propriedade 8: Simetria e identidade da distância Haversine**
    - Gerar pares de coordenadas aleatórias `(lat, lon)` em `[-90, 90] x [-180, 180]`; verificar `haversine(A, B) == haversine(B, A)`, `haversine(A, A) == 0` e `haversine(A, B) >= 0`
    - **Valida: Requisito 2.5**

  - [x] 4.3 Escrever teste de propriedade — Propriedade 7: Conservação de densidade na desagregação res 8 → res 9
    - **Propriedade 7: Conservação de densidade na desagregação res 8 → res 9**
    - Gerar hexes res 8 válidos com `density` aleatória em `[0.0, 1000.0]`; verificar que `sum(_disaggregate_r8_to_r9(h, d).values()) == d` (tolerância de ponto flutuante)
    - **Valida: Requisito 7.2**

  - [x] 4.4 Implementar `_load_h3_index` e `_build_coverage_index`
    - `_load_h3_index(reader, station_code, run_id) -> Dict[str, float]`: chama `reader.get_h3_cells_for_station`, desagrega cada registro res 8 via `_disaggregate_r8_to_r9`, retorna `{h3_id_r9: density_r9}`; retorna dict vazio com log de aviso se não houver registros
    - `_build_coverage_index(active_partners, h3_index, exclude_partner_id=None) -> Set[str]`: para cada parceiro Active (exceto `exclude_partner_id`), marca como cobertos os hexes de `h3_index` cujo centro (`h3.cell_to_latlng`) está a `<= partner.radius` metros do centroid do parceiro (Haversine); retorna set de `h3_id_r9` cobertos
    - _Requirements: 2.1, 2.2, 2.4, 7.1, 7.4, 7.5_

  - [x] 4.5 Implementar `_uncovered_demand` e `_smallest_radius_for_cap`
    - `_uncovered_demand(candidate_hex, radius_m, h3_index, coverage_index) -> float`: soma `delivery_density_r9` dos hexes de `h3_index` dentro de `radius_m` do centro de `candidate_hex` que **não** estão em `coverage_index`; trata density `None`/ausente como 0.0
    - `_smallest_radius_for_cap(candidate_hex, target_cap, h3_index, coverage_index) -> Optional[int]`: itera `Config.RADII` em ordem crescente; retorna o primeiro raio cujo `_uncovered_demand >= target_cap`; retorna `None` se nenhum raio for suficiente
    - _Requirements: 1.5, 1.6, 2.3, 2.6, 8.1, 8.2, 8.3_

  - [x] 4.6 Escrever teste de propriedade — Propriedade 3: Demanda não coberta exclui hexes cobertos
    - **Propriedade 3: Demanda não coberta exclui hexes cobertos por outros parceiros Active**
    - Gerar `h3_index` aleatório, `coverage_index` aleatório e posição candidata; verificar que `_uncovered_demand` soma apenas hexes dentro do raio que **não** estão em `coverage_index`
    - **Valida: Requisitos 1.5, 2.3**

  - [x] 4.7 Implementar `_select_best_candidate` e `_scan_partner`
    - `_select_best_candidate(candidates: List[Dict]) -> Optional[Dict]`: seleciona por maior `estimated_adv_gain`; desempate por menor `distance_from_current`; retorna `None` se lista vazia
    - `_scan_partner(partner, h3_index, coverage_index) -> Optional[Dict]`: obtém candidatos via `h3.grid_disk(origin_hex_r9, k=3)` (res 9); para cada candidato calcula `_uncovered_demand`; se demanda > `partner.capacity`, calcula `suggested_cap = min(int(demanda), 80)`, chama `_smallest_radius_for_cap`; descarta candidato se `suggested_radius` for `None`; chama `_select_best_candidate`; retorna dict com campos da oportunidade ou `None`
    - _Requirements: 1.4, 1.6, 1.7, 8.4, 8.5_

  - [x] 4.8 Escrever teste de propriedade — Propriedade 6: Seleção do melhor candidato
    - **Propriedade 6: Seleção do melhor candidato**
    - Gerar conjuntos aleatórios de candidatos viáveis com `estimated_adv_gain` e `distance_from_current` variados; verificar que `_select_best_candidate` retorna o de maior gain e, em empate, o de menor distância
    - **Valida: Requisitos 1.7, 10.5**

  - [x] 4.9 Implementar `run_geo_phase3_5` (entry point)
    - Assinatura: `run_geo_phase3_5(daily_result, run_id, station_code, writer, reader) -> int`
    - Carrega `h3_index` via `_load_h3_index`; encerra sem persistir se vazio
    - Itera todos os parceiros Active de `daily_result.matched + daily_result.unmatched`
    - Para parceiros com `capacity >= 80`: persiste registro com todos os campos de oportunidade `null`
    - Para parceiros com `capacity < 80`: chama `_build_coverage_index` (excluindo o próprio parceiro), `_scan_partner`; persiste resultado (oportunidade ou null)
    - Captura exceções por parceiro individualmente (log `WARNING`, persiste `null`, continua)
    - Chama `writer.upsert_cap_opportunities` ao final; captura exceção (log `ERROR`, encerra sem propagar)
    - Retorna número de oportunidades não nulas identificadas
    - _Requirements: 1.1, 1.2, 1.3, 1.8, 1.9, 1.10, 1.11, 9.1, 9.2, 9.3, 9.4, 9.5_

  - [x] 4.10 Escrever teste de propriedade — Propriedade 1: Cobertura total de parceiros Active
    - **Propriedade 1: Cobertura total de parceiros Active**
    - Gerar `GeoDailyResult` com lista aleatória de parceiros Active (0–50 parceiros) e `h3_index` sintético; verificar que a lista de oportunidades persistidas contém exatamente um registro para cada parceiro Active
    - **Valida: Requisitos 1.2, 10.6**

  - [x] 4.11 Escrever teste de propriedade — Propriedade 2: Parceiros com cap >= 80 resultam em oportunidade nula
    - **Propriedade 2: Parceiros com cap >= 80 sempre resultam em oportunidade nula**
    - Gerar parceiros Active com `capacity` em `[80, 200]` e `h3_index` aleatório; verificar que `suggested_cap` e `estimated_adv_gain` são `null` para todos
    - **Valida: Requisitos 1.3, 10.1**

  - [x] 4.12 Escrever teste de propriedade — Propriedade 4: Auto-exclusão revela demanda do próprio parceiro
    - **Propriedade 4: Auto-exclusão revela demanda do próprio parceiro**
    - Gerar parceiro P com cobertura exclusiva sobre hexes H (cobertos apenas por P); verificar que `_uncovered_demand` inclui hexes de H ao calcular oportunidade de P (pois a cobertura de P é excluída do índice)
    - **Valida: Requisito 2.4**

  - [x] 4.13 Escrever teste de propriedade — Propriedade 5: Invariante aritmético de `suggested_cap` e `estimated_adv_gain`
    - **Propriedade 5: Invariante aritmético de suggested_cap e estimated_adv_gain**
    - Gerar oportunidades válidas com `capacity` em `[1, 79]` e demanda suficiente; verificar `capacity_atual < suggested_cap <= 80` e `estimated_adv_gain == suggested_cap - capacity_atual`
    - **Valida: Requisitos 1.6, 3.4, 3.5, 10.3, 10.4**

  - [x] 4.14 Escrever teste de propriedade — Propriedade 9: Determinismo
    - **Propriedade 9: Determinismo**
    - Gerar `GeoDailyResult` e `h3_index` aleatórios; executar `run_geo_phase3_5` duas vezes com mocks determinísticos; verificar igualdade dos resultados (`partner_id`, `suggested_cap`, `suggested_lat`, `suggested_lon`, `estimated_adv_gain`)
    - **Valida: Requisito 10.7**

- [x] 5. Checkpoint — Backend core completo
  - Ensure all tests pass, ask the user if questions arise.

- [x] 6. Backend — Integrar Fase 3.5 Geo no orquestrador (`geo_orchestrator.py`)
  - Em `backend/geo_intelligence/geo_orchestrator.py`, dentro da função `run_daily`, adicionar bloco `try/except` chamando `run_geo_phase3_5` após `_run_daily(...)` e antes de `writer.update_supply_match`
  - Passar os argumentos: `daily_result=daily_result`, `run_id=run_id`, `station_code=station_code`, `writer=writer`, `reader=reader`
  - Em caso de exceção: logar `ERROR` e continuar para `update_supply_match` (não abortar o pipeline)
  - Logar número de oportunidades identificadas e número de parceiros Active avaliados ao final da fase
  - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5_

- [x] 7. Backend — Adicionar endpoint `GET /geo-intelligence/{station_code}/cap-opportunities` à `geo_api.py`
  - Adicionar o endpoint em `backend/geo_intelligence/geo_api.py` com query params: `run_id: Optional[str] = Query(default=None)` e `only_with_opportunity: bool = Query(default=False)`
  - Se `run_id` não fornecido: resolver via `reader.get_latest_run_id(station_code)`; retornar HTTP 404 com mensagem descritiva se não encontrado
  - Chamar `reader.get_cap_opportunities(station_code, run_id, only_with_opportunity)`
  - Ordenar resultados por `estimated_adv_gain` decrescente (nulls por último) antes de retornar
  - Retornar HTTP 200 com lista vazia se não houver oportunidades
  - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 6.7_

- [x] 8. Checkpoint final — Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marcadas com `*` são opcionais e podem ser puladas para um MVP mais rápido
- Testes de propriedade usam **Hypothesis** (Python), mínimo de 100 iterações por propriedade
- Cada teste de propriedade deve ser anotado com: `# Feature: geo-cap-optimization, Property N: <texto>`
- A Fase 3.5 Geo nunca propaga exceções ao orquestrador — falhas são logadas e o pipeline continua
- O índice `h3_index` é construído uma única vez por execução e reutilizado para todos os parceiros da base
