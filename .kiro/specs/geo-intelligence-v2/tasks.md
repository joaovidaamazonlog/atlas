# Implementation Plan: GeoIntelligence v2

## Overview

Evolução incremental do pipeline existente. As tarefas seguem a ordem natural do pipeline: configuração e dataclasses → ingestão de parceiros → perfis de referência → UMAP+HDBSCAN → similarity score → area selector → persistência Turso → daily matching → orquestrador CLI.

## Tasks

- [x] 1. Atualizar `geo_config.py` e `pipeline.py` com novos tipos e configurações
  - Adicionar constantes em `geo_config.py`: `H3_RES_ANALYSIS = 8`, `H3_RES_SUPPLY = 9`, `DELIVERY_DENSITY_THRESHOLD`, `MIN_TENURE_DAYS_FOR_PROFILE`, `FAST_EXIT_THRESHOLD_DAYS`, `FAST_EXIT_PENALTY`, `FAILURE_PENALTY_WEIGHT`, `LOW_COVERAGE_WARNING_PCT`, `UMAP_N_COMPONENTS`, `UMAP_N_NEIGHBORS`, `UMAP_MIN_DIST`, `UMAP_RANDOM_STATE`, `DELIVERY_DENSITY_WEIGHT`, `EXIT_REASON_MAP`, `SEMANTIC_ANCHORS`
  - Adicionar dataclasses em `pipeline.py`: `PartnerProfile`, `ReferenceProfiles`, `SelectedTerritory` (com `h3_ids_r8`, `h3_ids_r9`, `repeated_failure`)
  - Atualizar `RunMetadata` com campos: `umap_params`, `n_clusters`, `low_quality_clustering`, `profile_coverage`
  - _Requirements: 1.3, 2.1, 3.1, 4.1, 5.3, 10.3_

- [x] 2. Implementar `partner_ingestor.py` (novo)
  - [x] 2.1 Criar `phase1_area_intelligence/partner_ingestor.py` com função `ingest_partners(partner_data_df) -> list[PartnerProfile]`
    - Extrair campos: `salesforce_id`, `status`, `lat`, `lon`, `launch_date`, `exited_date`, `decision_reason_code`, `delivery_station`
    - Calcular `origin_hex` via `h3.latlng_to_cell(lat, lon, 8)`
    - Calcular `tenure_days`: `(today - launch_date).days` para Active, `(exited_date - launch_date).days` para Exited
    - Classificar `exit_reason_class` via `EXIT_REASON_MAP` de `geo_config.py`
    - Calcular `tenure_weight = log(1 + tenure_days)` e `area_penalty` por motivo
    - Excluir parceiros sem `launch_date` do perfil de referência (manter no matching)
    - Tratar falha/DataFrame vazio com log de aviso e retorno de lista vazia
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.7_

  - [x] 2.2 Escrever property test para `tenure_weight` monotonicamente crescente
    - **Property 5: `tenure_weight = log(1 + tenure_days)` é monotonicamente crescente**
    - **Validates: Requirements 1.2, 3.1**

  - [x] 2.3 Escrever property test para isolamento de `partner_signal` no failure vector
    - **Property 6: Parceiros Exited com `partner_signal` não contribuem para `failure_vector`**
    - **Validates: Requirements 1.3, 3.2**

- [x] 3. Implementar `profile_builder.py` (novo)
  - [x] 3.1 Criar `phase1_area_intelligence/profile_builder.py` com `build_reference_profiles(partner_profiles, cells_features, exit_reason_map, min_tenure_days, global_fallback_profiles) -> ReferenceProfiles`
    - Construir `success_vector` como média ponderada por `tenure_weight` dos Active com `tenure_days >= min_tenure_days`
    - Construir `failure_vector` como média ponderada por `failure_weight = area_penalty * log(1 + tenure_days)` dos Exited `area_signal`
    - Aplicar fallback para perfil global quando `n_active < 3`, registrar `is_global_fallback = True`
    - Calcular `profile_coverage = |{h : ∃ parceiro em grid_disk(h,1)}| / |hexágonos|`
    - Setar `low_coverage_warning = True` se `profile_coverage < LOW_COVERAGE_WARNING_PCT`
    - Persistir vetores como `.npy` por `station_code` com timestamp, mantendo apenas os 3 mais recentes
    - Registrar no log: n_active, n_exited por class, tenure médio, profile_coverage
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6_

  - [x] 3.2 Escrever property test para fórmula de `profile_coverage`
    - **Property 7: `profile_coverage = |{h ∈ hexágonos : ∃ parceiro em grid_disk(h, 1)}| / |hexágonos|`**
    - **Validates: Requirements 3.5**

- [x] 4. Atualizar `ingestor.py` e `feature_engineer.py` para resolução 8
  - Atualizar `ingestor.py`: trocar resolução H3 de res 9 para res 8 em `ingest_packages()`; agregar `delivery_count` por `h3_id_r8`; aplicar `DELIVERY_DENSITY_THRESHOLD` como filtro de viabilidade
  - Atualizar `feature_engineer.py`: garantir que `build_features()`, `impute_missing()` e `normalize_features()` operem em res 8; adicionar `delivery_density_r8` como feature de contexto com peso máx `DELIVERY_DENSITY_WEIGHT`; adicionar `commercial_activity_index = (landuse_commercial_ratio + target_business_density) / 2`; persistir parâmetros de normalização por DS
  - _Requirements: 2.1, 2.2, 2.3, 2.5, 2.6, 2.7_

- [x] 5. Atualizar `classifier.py` com UMAP antes do HDBSCAN
  - [x] 5.1 Substituir clustering direto por pipeline UMAP → HDBSCAN em `classifier.py`
    - Instanciar `umap.UMAP(n_components=2, n_neighbors=15, min_dist=0.1, random_state=42, metric="euclidean")` e chamar `fit_transform(features_matrix)`
    - Executar `hdbscan.HDBSCAN(min_cluster_size=max(5, n_cells // 20))` sobre o embedding UMAP
    - Implementar fallback KMeans k=6 sobre embedding UMAP quando `n_clusters < 3`
    - Aplicar âncoras semânticas de `SEMANTIC_ANCHORS` para nomear clusters quando configurado
    - Calcular silhouette score sobre embedding UMAP; emitir alerta e setar `low_quality_clustering = True` se < 0.2
    - Persistir modelo UMAP em `models/{station_code}_umap_{timestamp}.joblib` (máx 3 por base)
    - Gerar e persistir scatter plot 2D colorido por cluster em `models/{station_code}_umap_scatter_{timestamp}.png`
    - Preencher `umap_embedding` em cada `PartnerProfile` via `umap_model.transform()`
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7_

  - [x] 5.2 Escrever testes unitários para fallback KMeans e âncoras semânticas
    - Testar que KMeans é acionado quando HDBSCAN retorna < 3 clusters
    - Testar que âncoras semânticas nomeiam clusters corretamente
    - _Requirements: 4.4, 4.5_

- [x] 6. Atualizar `potential_calculator.py` com similarity score
  - [x] 6.1 Implementar cálculo de similarity score em `potential_calculator.py`
    - Projetar `success_vector` e `failure_vector` no espaço UMAP via `umap_model.transform()`
    - Calcular `sim_positive = cosine_similarity(cell_umap, success_umap)` e `sim_negative = cosine_similarity(cell_umap, failure_umap)` para cada hex res 8
    - Calcular `raw_score = sim_positive - (FAILURE_PENALTY_WEIGHT * sim_negative)`
    - Aplicar penalidade `FAST_EXIT_PENALTY` para hexágonos com histórico de saída rápida (< `FAST_EXIT_THRESHOLD_DAYS` por `area_signal`)
    - Aplicar `DELIVERY_DENSITY_THRESHOLD` como gate binário: `raw_score = 0.0` se abaixo do threshold
    - Normalizar `raw_score` para [0, 100] por DS
    - Calcular `gap = potential_score - (current_partners / ideal_slots * 100)` por território
    - Agregar scores de células res 8 para territórios via média ponderada por `delivery_density_r8`
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 5.7, 5.8_

  - [x] 6.2 Escrever property test para `potential_score` no intervalo [0, 100]
    - **Property 1: `potential_score` ∈ [0, 100] para todo hexágono**
    - **Validates: Requirements 5.5**

  - [x] 6.3 Escrever property test para fórmula de `gap`
    - **Property 2: `gap = potential_score - (current_partners / ideal_slots * 100)` para todo território com `ideal_slots > 0`**
    - **Validates: Requirements 5.6**

  - [x] 6.4 Escrever property test para gate de `delivery_density`
    - **Property 3: Hexágonos com `delivery_density_r8 < threshold` têm `potential_score = 0`**
    - **Validates: Requirements 5.4, 1.6**

- [x] 7. Atualizar `area_selector.py` com `h3_ids_r8`, `h3_ids_r9` e `repeated_failure`
  - [x] 7.1 Atualizar assinatura de `select_areas()` para receber `territory_h3_ids_r8`, `territory_h3_ids_r9` e `partner_profiles`
    - Retornar `SelectedTerritory[]` com `h3_ids_r8`, `h3_ids_r9`, `repeated_failure`
    - Implementar lógica de seleção: ordenar por `gap` decrescente, selecionar conjunto mínimo com `sum(volume) >= target_pct * total_volume`
    - Calcular `repeated_failure = True` quando `count(exited_area_signal in territory) >= 2`
    - Tratar casos extremos: `target_pct = 0` → lista vazia; `target_pct = 100` → todos com `gap > 0`
    - Calcular e retornar `coverage_summary`: % volume coberto, n territórios, distribuição de RegionTypes
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5_

  - [x] 7.2 Escrever property test para cobertura de volume
    - **Property 4: `sum(volume[t] for t in selected) >= target_pct * total_volume`**
    - **Validates: Requirements 6.1**

  - [x] 7.3 Escrever property test para `repeated_failure`
    - **Property 8: `repeated_failure = True` iff `count(exited_area_signal in territory) >= 2`**
    - **Validates: Requirements 6.5**

- [x] 8. Checkpoint — Garantir que todos os testes passam
  - Garantir que todos os testes passam, perguntar ao usuário se houver dúvidas.

- [x] 9. Atualizar schema Turso e `turso_writer.py` / `turso_reader.py`
  - [x] 9.1 Adicionar migrations DDL para novas tabelas e colunas
    - Criar `geo_partner_profiles` com colunas: `run_id`, `station_code`, `profile_type`, `vector_json`, `n_partners`, `avg_tenure_days`, `profile_coverage`, `low_coverage_warning`, `is_global_fallback`, `created_at`
    - Criar `geo_partner_history` com colunas: `salesforce_id`, `station_code`, `h3_id_r8`, `status`, `tenure_days`, `exit_reason_code`, `exit_reason_class`, `launch_date`, `exited_date`, `run_id`
    - Adicionar colunas em `geo_run_metadata`: `umap_params TEXT`, `n_clusters INTEGER`, `low_quality_clustering INTEGER`, `profile_coverage REAL`
    - _Requirements: 9.1, 9.2, 9.3_

  - [x] 9.2 Implementar novos métodos em `turso_writer.py`
    - `upsert_partner_profiles(run_id, station_code, profiles: ReferenceProfiles)` → persiste success e failure como JSON em `geo_partner_profiles`
    - `upsert_partner_history(run_id, partner_profiles: list[PartnerProfile])` → persiste histórico em `geo_partner_history`
    - `update_supply_match(run_id, matches: dict[str, str])` → atualiza `matched_partner_id` em `geo_ideal_supply`
    - `update_territory_fit(run_id, fits: dict[str, dict])` → persiste `attainment` e `accuracy` por território
    - _Requirements: 9.1, 9.3, 9.4_

  - [x] 9.3 Implementar/atualizar métodos em `turso_reader.py`
    - `get_latest_run_id(station_code) -> str` filtrando por `status = 'setup_complete'`
    - `get_ideal_supply(station_code, run_id) -> list[dict]`
    - _Requirements: 9.5_

- [x] 10. Atualizar `phase1_area_intelligence/_orchestrator.py`
  - Integrar `partner_ingestor.ingest_partners()` após `ingestor.ingest_packages()`
  - Integrar `profile_builder.build_reference_profiles()` após feature engineering
  - Passar `partner_profiles` e `reference_profiles` para `classifier`, `potential_calculator` e `area_selector`
  - Passar `h3_ids_r9` dos `SelectedTerritory` para `phase2_ideal_supply`
  - Registrar métricas de clustering (`umap_params`, `silhouette_score`, `n_clusters`, `low_quality_clustering`) no `RunMetadata`
  - _Requirements: 1.7, 3.6, 4.6, 9.2_

- [x] 11. Criar `geo_daily.py` e atualizar `geo_orchestrator.py`
  - [x] 11.1 Criar `geo_daily.py` com `run_daily(station_codes, config) -> GeoDailyResult`
    - Carregar parceiros via `load_partners()` e slots via `TursoReader.get_ideal_supply(station_code, run_id)`
    - Carregar `territories.geojson` para point-in-polygon e `territories_index.json` para fallback
    - Executar matching hierárquico: Active (1) > Onboarding (2) > BG Checks (3) > Prospect (4) > Inactive/Exited (5)
    - Determinar `territory_id` com hierarquia de fallback: hex exato → point-in-polygon (Shapely) → centroide geométrico → centroide dos slots
    - Persistir `matched_partner_id` via `TursoWriter.update_supply_match()`
    - Persistir `attainment` e `accuracy` via `TursoWriter.update_territory_fit()`
    - Retornar `GeoDailyResult` com `matched`, `unmatched` e métricas por território
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5, 8.6, 8.7_

  - [x] 11.2 Atualizar `geo_orchestrator.py` com `--mode daily`
    - Adicionar argparse `--mode {setup,daily}` (padrão: setup para retrocompatibilidade)
    - Rotear `--mode setup` para `phase1_area_intelligence._orchestrator` + `phase2_ideal_supply`
    - Rotear `--mode daily` para `geo_daily.run_daily()`
    - Manter suporte a `--update-heatmap` e `--stations`
    - _Requirements: 8.1, 10.5, 10.6_

- [x] 12. Checkpoint final — Garantir que todos os testes passam
  - Garantir que todos os testes passam, perguntar ao usuário se houver dúvidas.

## Notes

- Tasks marcadas com `*` são opcionais e podem ser puladas para MVP mais rápido
- Cada task referencia requirements específicos para rastreabilidade
- Properties 1-8 do design mapeiam diretamente para sub-tasks de PBT (Hypothesis)
- `phase2_ideal_supply.py` não requer alterações — recebe `h3_ids_r9` dos `SelectedTerritory`
- Enrichers (`cnpj_enricher.py`, `osm_enricher.py`, etc.) não requerem alterações
