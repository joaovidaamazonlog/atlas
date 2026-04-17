# Implementation Plan: Geo-Intelligence Expansion

## Overview

Pipeline GeoIntelligence completamente separado do pipeline de produção atual. Implementado em `backend/geo_intelligence/` com ponto de entrada `geo_orchestrator.py`. O frontend substitui apenas `Dashboard.tsx` por `GeoIntelligenceDashboard.tsx`; todo o resto do Atlas permanece inalterado.

Ordem de implementação: infraestrutura base → Fase 1 (Area Intelligence) → Fases 2 e 3 (vanilla adaptado) → TursoWriter → API → Frontend.

## Tasks

- [x] 1. Criar estrutura base do módulo `geo_intelligence`
  - Criar diretório `backend/geo_intelligence/` com `__init__.py`
  - Criar `geo_config.py` com `TURSO_URL`, `TURSO_AUTH_TOKEN`, pesos do `potential_calculator`, `HIGH_OPPORTUNITY_THRESHOLD = 20.0`, `CP_SOLVER_TIME_LIMIT_S = 300`, `CP_CAPACITY_TOLERANCE = 0.10`
  - Criar `geo_orchestrator.py` com CLI (`argparse`) espelhando os modos do `orchestrator.py` vanilla:
    - `--mode setup --target <pct>` — executa as 3 fases do pipeline GeoIntelligence
    - `--stations` — filtrar bases específicas (ex: `--stations DSP2 DSP4`), igual ao vanilla
    - `--workers` — paralelismo do solver CP-SAT, igual ao vanilla
    - `--update-heatmap` — regenera o heatmap GeoIntelligence com a base de pacotes atual sem refazer o setup completo, igual ao `--update-heatmap` do vanilla
    - Exemplo: `python geo_intelligence/geo_orchestrator.py --mode setup --target 50 --stations DSP2`
    - Exemplo: `python geo_intelligence/geo_orchestrator.py --update-heatmap --stations DSP2`
  - Definir dataclasses em `pipeline.py`: `GeoSetupConfig`, `H3CellFeatures`, `TerritoryOutput`, `SetupOutput`, `ActivatedArea`, `IdealSupplyPoint`, `RunMetadata`
  - Definir enum `RegionType` com os 8 valores: `favela_comunidade`, `residencial_baixa_renda`, `residencial_media_renda`, `residencial_alta_renda`, `comercial`, `industrial`, `rural`, `alto_padrao`
  - _Requirements: 1.1, 5.1, 11.1_

- [x] 2. Implementar ingestão e enriquecimento de dados (Fase 1 — parte 1)
  - [x] 2.1 Implementar `phase1_area_intelligence/ingestor.py`
    - Mapear cada entrega da base de pacotes para H3_Cell resolução 9 via `h3.latlng_to_cell`
    - Ler polígono de jurisdição da DS a partir do `territories.geojson` existente (leitura apenas, sem modificação)
    - Filtrar H3_Cells para apenas as que estão dentro da jurisdição da DS
    - _Requirements: 1.1, 1.7, 10.1_

  - [x] 2.2 Implementar `enrichers/cnpj_enricher.py`
    - Conectar ao Turso existente (empresas CNPJ + Google Maps) via `libsql-client` com `create_client_sync`
    - Query: `SELECT h3_id, cnae_code, lat, lng FROM empresas WHERE h3_id IN (?,...)`
    - Calcular por H3_Cell: `company_density` (empresas/km²), `cnae_diversity_index` (Shannon), `target_business_density`
    - Calcular features indiretas via Google Maps: `bars_restaurants_density`, `churches_density`, `schools_density`, `dealerships_density`, `petshops_density`
    - Degradação graciosa: se Turso indisponível, retornar `None` para todas as features e logar erro
    - _Requirements: 1.2, 2.1, 2.4_

  - [x] 2.3 Implementar `enrichers/osm_enricher.py`
    - Usar `osmnx` para extrair por H3_Cell: `building_density`, `avg_building_size_m2`, `landuse_residential_ratio`, `landuse_commercial_ratio`, `poi_density`, `road_connectivity_index`
    - Calcular features avançadas: `landuse_entropy` (Shannon sobre categorias), `road_centrality_index` (betweenness normalizado), `local_clustering_coefficient`
    - Degradação graciosa: se OSM indisponível, preencher features com `None` e logar erro
    - _Requirements: 1.3, 2.2, 2.5_

  - [x] 2.4 Implementar `enrichers/ibge_enricher.py`
    - Associar setores censitários IBGE às H3_Cells por interseção geográfica
    - Retornar `avg_income` e `population_density` por H3_Cell
    - Degradação graciosa: se IBGE indisponível, preencher com `None` e logar erro
    - _Requirements: 1.4, 2.3_

  - [x] 2.5 Implementar `enrichers/satellite_enricher.py`
    - Inicializar Google Earth Engine via `ee.Initialize()`
    - Extrair por H3_Cell: `ndvi_mean`, `urban_density_index` (GHSL), `built_up_ratio` (Sentinel-2), `morphology_class`
    - Degradação graciosa: se GEE indisponível, retornar `None` para todas as features de satélite e logar aviso; pipeline continua normalmente
    - _Requirements: 1.5_

- [x] 3. Implementar Feature Engineer e Classificador (Fase 1 — parte 2)
  - [x] 3.1 Implementar `phase1_area_intelligence/feature_engineer.py`
    - Consolidar features de todos os enrichers em `H3CellFeatures` por célula
    - Imputação de valores nulos: mediana dos vizinhos de primeiro anel H3 (`h3.grid_disk(h3_id, 1)`); se todos os vizinhos também forem nulos, manter `None`
    - Normalização min-max por Delivery_Station para intervalo `[0, 1]`; persistir parâmetros de normalização (min/max por feature) para uso na inferência
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7_

  - [x] 3.2 Escrever property test para imputação por mediana (Property 4)
    - **Property 4: Imputação por mediana dos vizinhos H3**
    - **Validates: Requirements 2.6**
    - Usar `hypothesis` com `st.lists` de floats e células H3 sintéticas

  - [x] 3.3 Escrever property test para normalização min-max (Property 3)
    - **Property 3: Normalização min-max preserva ordem e limites**
    - **Validates: Requirements 2.7**
    - Usar `hypothesis` com `st.lists(st.floats(min_value=0, max_value=1e6, allow_nan=False), min_size=2)`

  - [x] 3.4 Implementar `phase1_area_intelligence/classifier.py`
    - Executar HDBSCAN sobre vetor de features por H3_Cell; atribuir `region_type` via mapeamento configurável `cluster_id → RegionType`
    - Fallback: se HDBSCAN produzir < 3 clusters, executar KMeans k=6 e registrar evento no log
    - Calcular `model_confidence`: probabilidade da classe predita (supervisionado) ou distância normalizada ao centróide (não supervisionado)
    - Marcar `low_confidence = True` quando `model_confidence < 0.5`
    - Quando dados rotulados disponíveis (≥ 50 amostras/classe), treinar Random Forest (padrão) ou XGBoost; calcular accuracy, precision, recall, F1 por classe
    - Persistir modelos em `models/{station}_{timestamp}.joblib`; manter apenas os 3 últimos por DS
    - Calcular e registrar silhouette score; emitir alerta no log se < 0.2
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 9.1, 9.2, 9.3, 9.4, 9.5_

  - [x] 3.5 Escrever property test para Model_Confidence e low_confidence (Property 5)
    - **Property 5: Model_Confidence está em [0, 1] e low_confidence é consistente**
    - **Validates: Requirements 3.5, 3.6**

  - [x] 3.6 Escrever property test para Region_Type válido (Property 6)
    - **Property 6: Region_Type mapeado é sempre um valor válido do enum**
    - **Validates: Requirements 3.3**

  - [x] 3.7 Escrever property test para round-trip de serialização joblib (Property 7)
    - **Property 7: Serialização de modelo é round-trip fiel**
    - **Validates: Requirements 3.7**

- [x] 4. Implementar Potential Calculator e Area Selector (Fase 1 — parte 3)
  - [x] 4.1 Implementar `phase1_area_intelligence/potential_calculator.py`
    - Calcular `potential_score` por H3_Cell usando fórmula ponderada configurável: `f(target_business_density, avg_income, population_density, region_type_weight, road_connectivity_index, commercial_activity_index)`
    - Agregar por território (média ponderada por volume de pacotes) → normalizar para `[0, 100]` por DS (máximo = 100)
    - Agregar por DS (média ponderada por volume) → normalizar para `[0, 100]` dentro do grupo de DSs
    - Agregar por BDM (média ponderada por volume) → normalizar para `[0, 100]` dentro do grupo de BDMs
    - Calcular `gap = potential_score - (current_partners / ideal_slots * 100)`; marcar `high_opportunity = True` quando `gap > 20`
    - Gerar rankings por `gap` decrescente: por DS, por BDM, global
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7, 4.8_

  - [x] 4.2 Escrever property test para potential_score normalizado (Property 8)
    - **Property 8: potential_score normalizado está em [0, 100] com máximo = 100**
    - **Validates: Requirements 4.2, 4.5**

  - [x] 4.3 Escrever property test para agregação ponderada (Property 9)
    - **Property 9: Agregação ponderada está dentro do intervalo dos componentes**
    - **Validates: Requirements 4.3, 4.4**

  - [x] 4.4 Escrever property test para cálculo de gap (Property 10)
    - **Property 10: Cálculo de gap é determinístico e correto**
    - **Validates: Requirements 4.6, 4.7**

  - [x] 4.5 Escrever property test para ranking por gap (Property 11)
    - **Property 11: Ranking por gap é ordenado de forma decrescente**
    - **Validates: Requirements 4.8**

  - [x] 4.6 Implementar `phase1_area_intelligence/area_selector.py`
    - Receber `potential_score` por território e `target_pct` (ex: 50%)
    - Selecionar conjunto mínimo de territórios de maior `gap` cuja soma de `potential_score` atinja o percentual alvo do volume total de pacotes da DS
    - Produzir `geo_territories`: lista de territórios ativos com `h3_ids`, `region_type`, `potential_score`, `gap`, `model_confidence`
    - _Requirements: 4.9, 11.2_

- [x] 5. Checkpoint — Fase 1 completa
  - Garantir que `run_area_intelligence()` em `phase1_area_intelligence.py` orquestre ingestor → enrichers → feature_engineer → classifier → potential_calculator → area_selector
  - Verificar que todos os testes de propriedade da Fase 1 passam
  - Garantir que o pipeline continua com degradação graciosa quando qualquer fonte externa está indisponível
  - Ensure all tests pass, ask the user if questions arise.

- [x] 6. Implementar Fase 2: Ideal Supply (CP-SAT)
  - [x] 6.1 Criar `geo_intelligence/phase2_ideal_supply.py`
    - Copiar a lógica do `backend/phase2_ideal_supply.py` vanilla (worker `_solve_territory_worker`, `_dict_to_ideal_slot`, `run_phase2`)
    - Adaptar para receber `geo_territories` (output da Fase 1) no lugar de `territories_index.json`
    - Manter mesma estrutura de `IdealSlot`: `slot_id`, `station_code`, `territory_id`, `origin_hex`, `radius_s`, `capacity_s`, `lat`, `lon`, `allocations`
    - Garantir que `is_optimal = False` e `solver_status = 'suboptimal'` quando CP-SAT excede tempo limite
    - _Requirements: 11.1, 11.2, 11.3, 11.4, 11.5, 11.6, 11.7, 11.8_

  - [x] 6.2 Escrever property test para Ideal_Supply como centróide ponderado (Property 15)
    - **Property 15: Ideal_Supply é o centróide ponderado pelo potential_score**
    - **Validates: Requirements 11.4**

  - [x] 6.3 Escrever property test para capacidade total satisfaz Expansion_Target (Property 16)
    - **Property 16: Capacidade total dos parceiros satisfaz o Expansion_Target com tolerância**
    - **Validates: Requirements 11.7**

- [x] 7. Implementar Fase 3: Territory Fit (matching)
  - [x] 7.1 Criar `geo_intelligence/phase3_territory_fit.py`
    - Copiar a lógica do `backend/phase3_partner_fit.py` vanilla: `_evaluate_all_prospects`, `_match_station`, `run_phase3`
    - Adaptar para receber `geo_territories` (output da Fase 1) no lugar de `territories_index.json`
    - Manter mesma hierarquia de status: Active > Onboarding > BG Checks > Prospect > Inactive
    - Manter mesma nomenclatura de carteiras: `{station}_bucket-{nn}`, `CTL-{letra}`
    - Manter reasons canônicos para prospects: "Seguir cadastro", "Não avaliado por falta de coordenadas", "Sem oportunidade próxima", "Fora de jurisdição"
    - _Requirements: 10.2, 11.1_

- [x] 8. Implementar TursoWriter e TursoReader
  - [x] 8.1 Criar `geo_intelligence/turso_writer.py`
    - Implementar `TursoWriter` com `libsql_client.create_client_sync`
    - Métodos: `upsert_run`, `upsert_territories` (batch 100), `upsert_h3_cells` (batch 100), `upsert_ideal_supply`, `upsert_scorecard`, `finalize_run`
    - Criar tabelas DDL em `geo_config.py` ou em método `ensure_schema()`: `geo_territories`, `geo_h3_cells`, `geo_ideal_supply`, `geo_scorecard`, `geo_run_metadata`
    - Retry automático até 3x com backoff exponencial em caso de falha; se persistir, abortar e atualizar `geo_run_metadata.status = 'failed'`
    - _Requirements: 5.1, 5.4, 9.1_

  - [x] 8.2 Criar `geo_intelligence/turso_reader.py`
    - Implementar `TursoReader` com cache em memória TTL 5 min
    - Métodos: `get_latest_run_id`, `get_territories` (com filtros `region_type`, `min_gap`), `get_h3_cells`, `get_scorecard`, `get_ideal_supply`
    - Retornar `None` / lista vazia quando DS não tem dados processados
    - _Requirements: 6.1, 6.2, 6.3, 6.6, 6.7_

- [x] 9. Implementar Territory_Output e geração de GeoJSON
  - [x] 9.1 Implementar serialização de `TerritoryOutput` em `pipeline.py`
    - Gerar `TerritoryOutput` para cada território com todos os campos obrigatórios: `territory_id`, `h3_ids`, `region_type`, `potential_score`, `current_partners`, `ideal_slots`, `gap`, `model_confidence`, `low_confidence`, `high_opportunity`, `geometry`
    - Serializar para GeoJSON (`FeatureCollection`) com geometria (união dos polígonos H3) e propriedades
    - Serializar para JSON plano (sem geometria) para consumo pela API
    - Gerar arquivo de metadados de execução com todos os campos do schema `geo_run_metadata`
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5_

  - [x] 9.2 Escrever property test para campos obrigatórios no Territory_Output (Property 12)
    - **Property 12: Territory_Output contém todos os campos obrigatórios**
    - **Validates: Requirements 5.1**

  - [x] 9.3 Escrever property test para round-trip GeoJSON (Property 13)
    - **Property 13: Serialização GeoJSON de Territory_Output é round-trip fiel**
    - **Validates: Requirements 5.2, 5.3**

- [x] 10. Checkpoint — Pipeline backend completo
  - Integrar todas as fases em `geo_orchestrator.py`: `run_area_intelligence` → `run_ideal_supply` → `run_territory_fit` → `TursoWriter.write_all`
  - Verificar que `python geo_intelligence/geo_orchestrator.py --mode setup --target 50 --stations DSP2` executa sem erros com dados mock
  - Verificar que `orchestrator.py` original permanece inalterado e funcional
  - Ensure all tests pass, ask the user if questions arise.

- [x] 11. Implementar modos auxiliares do `geo_orchestrator.py`
  - [x] 11.1 Implementar `--update-heatmap` no `geo_orchestrator.py`
    - Criar `geo_intelligence/geo_heatmap.py` com `run_update_geo_heatmap(output_dir, stations)`
    - Regenerar o heatmap GeoIntelligence (H3_Cells com `potential_score`, `region_type`, `gap`) com a base de pacotes atual sem refazer o setup completo (sem re-rodar enrichers, classifier ou CP-SAT)
    - Ler `geo_h3_cells` do Turso para a última execução da DS, recalcular apenas o mapeamento de demanda atual e atualizar `geo_territories` no Turso com os novos valores de `attainment` e `accuracy`
    - Espelhar o comportamento do `run_update_heatmap` do vanilla: aceita `--stations` para filtrar bases, roda rápido sem re-processar fontes externas
    - Exemplo: `python geo_intelligence/geo_orchestrator.py --update-heatmap --stations DSP2`
    - _Requirements: 5.4, 9.1_

  - [x] 11.2 Garantir setup por base individual (`--stations`) com `--target` por base
    - Verificar que `--mode setup --target <pct> --stations <DS1> <DS2>` processa apenas as bases listadas com o mesmo target para todas, igual ao vanilla
    - Suportar `--target` diferente por base via chamadas separadas: `--mode setup --target 40 --stations DSP2` e `--mode setup --target 60 --stations DSP4` — cada execução gera seu próprio `run_id` independente em `geo_run_metadata`
    - Verificar que bases não listadas não são afetadas no Turso (upsert por `territory_id + run_id`, não delete global)
    - Exemplos:
      - `python geo_intelligence/geo_orchestrator.py --mode setup --target 50 --stations DSP2 DSP4` (mesmo target para ambas)
      - `python geo_intelligence/geo_orchestrator.py --mode setup --target 40 --stations DSP2` (target específico para DSP2)
    - _Requirements: 1.7, 5.4_

- [x] 12. Implementar GeoIntelligence API (FastAPI)
  - [x] 12.1 Criar `geo_intelligence/geo_api.py` com FastAPI
    - `GET /geo-intelligence/{station_code}/territories` — lista com filtros `region_type`, `min_gap`, `run_id` (default: latest)
    - `GET /geo-intelligence/{station_code}/territories/{territory_id}` — detalhe com breakdown por H3_Cell
    - `GET /geo-intelligence/{station_code}/geojson` — GeoJSON completo
    - `GET /geo-intelligence/{station_code}/scorecard` — KPIs DS + BDM
    - `GET /geo-intelligence/{station_code}/ideal-supply` — pontos de supply
    - `POST /geo-intelligence/{station_code}/expansion-targets` — body `{expansion_target_pct: float}`, calcula on-the-fly
    - `GET /geo-intelligence/{station_code}/runs` — histórico de execuções
    - `GET /geo-intelligence/runs/{run_id}` — metadados de execução específica
    - Retornar HTTP 404 com mensagem descritiva quando DS não tem dados processados
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 6.7_

  - [x] 12.2 Escrever property test para filtros da API (Property 14)
    - **Property 14: Filtro por region_type retorna apenas territórios do tipo solicitado**
    - **Validates: Requirements 6.6**
    - Usar FastAPI `TestClient` com dados mock no Turso

- [x] 13. Implementar slice Zustand e hook de fetch (Frontend)
  - [x] 13.1 Criar `atlas-react/src/store/geoIntelligenceSlice.ts`
    - Definir `GeoIntelligenceState`: `territories`, `geojson`, `scorecard`, `expansionTargetResult`, `selectedTerritoryId`, `filter`, `isLoading`, `error`
    - Definir `GeoIntelligenceFilter`: `regionTypes: RegionType[] | 'all'`, `minGap: number`
    - Adicionar ao `AtlasStore` em `store/index.ts`: campos `geoIntelligence`, actions `loadGeoIntelligence`, `setGeoFilter`, `setExpansionTarget`, `selectGeoTerritory`
    - Não modificar nenhum slice existente do store
    - _Requirements: 7.7, 8.1, 10.3_

  - [x] 13.2 Criar `atlas-react/src/hooks/useGeoIntelligence.ts`
    - Hook que chama `loadGeoIntelligence(stationCode)` e expõe `territories`, `geojson`, `scorecard`, `isLoading`, `error`
    - Cache local via Zustand (TTL alinhado com o cache da API de 5 min)
    - _Requirements: 6.7_

  - [x] 13.3 Criar `atlas-react/src/lib/geoIntelligenceUtils.ts`
    - `potentialScoreToColor(score: number): string` — gradiente frio→quente para `[0, 100]`
    - `regionTypeLabel(type: RegionType): string` — label em português
    - `formatGap(gap: number): string` — formatação com sinal
    - Exportar `RegionType` TypeScript
    - _Requirements: 7.1, 7.6_

  - [x] 13.4 Escrever property test para escala de cores (fast-check)
    - Testar que `potentialScoreToColor` retorna cor hex válida para qualquer score em `[0, 100]`
    - Usar `fc.float({ min: 0, max: 100 })` com `numRuns: 200`
    - _Requirements: 7.1_

- [x] 14. Implementar GeoIntelligenceLayer (camada de mapa)
  - [x] 14.1 Criar `atlas-react/src/components/map/GeoIntelligenceLayer.tsx`
    - Renderizar territórios como polígonos coloridos via `react-leaflet` usando `potentialScoreToColor`
    - Destacar territórios `high_opportunity` com borda mais espessa e cor diferenciada
    - Popup ao clicar: `territory_id`, `region_type`, `potential_score`, `current_partners`, `gap`, `model_confidence`, flag `low_confidence`
    - Filtrar por `regionTypes` do `GeoIntelligenceFilter` (ocultar territórios dos tipos não selecionados)
    - Exibir `LoadingIndicator` existente enquanto carrega
    - Ocultar camada automaticamente quando DS não tem dados (sem erro visível)
    - Renderizar `IdealSupplyPoint` como marcadores diferenciados dos parceiros ativos existentes
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5, 7.7, 10.3, 10.5, 11.9_

  - [x] 14.2 Integrar `GeoIntelligenceLayer` ao `MapView.tsx` existente
    - Adicionar a camada como opcional, ativável via toggle no `StyleTab` ou novo tab no `ControlPanel`
    - Não alterar comportamento das camadas existentes (heatmap, polígonos, rotas, marcadores)
    - _Requirements: 7.4, 10.3_

  - [x] 14.3 Integrar legenda de cores ao `MapLegend.tsx` existente
    - Adicionar seção de legenda de `potential_score` quando a camada GeoIntelligence estiver ativa
    - _Requirements: 7.6_

- [x] 15. Implementar GeoIntelligenceDashboard (substituição do Dashboard)
  - [x] 15.1 Criar `atlas-react/src/components/dashboard/GeoIntelligenceDashboard.tsx`
    - KPIs por DS: total de territórios, número `high_opportunity`, gap médio, potencial total, percentual de cobertura atual
    - KPIs por BDM: número de DSs, `potential_score` médio, total `high_opportunity`, gap médio consolidado
    - Tabela ranqueada de territórios por `gap` decrescente: `territory_id`, `region_type`, `potential_score`, `current_partners`, `gap`, `model_confidence`
    - Ranking de DSs por `potential_score` dentro do BDM
    - Ranking de BDMs por `potential_score`
    - Gráfico de distribuição de `RegionType` (barras ou pizza)
    - Input de `expansion_target_pct` com exibição da lista de territórios recomendados e potencial acumulado
    - Exportação da tabela de territórios em CSV (todas as colunas visíveis)
    - Ao selecionar território na tabela, disparar `selectGeoTerritory(territoryId)` para centralizar no mapa
    - Migrar KPIs e funcionalidades do `Dashboard.tsx` atual para que nenhuma informação seja perdida
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5, 8.6, 8.7, 8.8, 8.9, 8.10, 10.4_

  - [x] 15.2 Substituir `Dashboard.tsx` por `GeoIntelligenceDashboard.tsx` no `App.tsx`
    - Atualizar import em `App.tsx` (ou no componente que renderiza o dashboard)
    - Não alterar nenhum outro arquivo do frontend
    - _Requirements: 8.1, 10.4_

- [x] 16. Implementar testes de propriedade H3 e features econômicas
  - [x] 16.1 Escrever property test para mapeamento H3 (Property 1)
    - **Property 1: Mapeamento H3 é válido para qualquer coordenada**
    - **Validates: Requirements 1.1**
    - Usar `st.floats` para lat/lng dentro do bounding box do Brasil

  - [x] 16.2 Escrever property test para invariantes de features econômicas (Property 2)
    - **Property 2: Features econômicas respeitam invariantes de domínio**
    - **Validates: Requirements 1.2, 2.1**
    - Verificar `company_density >= 0`, `cnae_diversity_index in [0, 1]`, `target_business_density <= company_density`

- [x] 17. Checkpoint final — Ensure all tests pass, ask the user if questions arise.
  - Verificar que todos os testes de propriedade (Hypothesis + fast-check) passam
  - Verificar que `orchestrator.py` original e todos os arquivos do pipeline de produção permanecem inalterados
  - Verificar que o frontend compila sem erros TypeScript
  - Verificar que a API responde corretamente para DS com e sem dados processados

## Notes

- Tasks marcadas com `*` são opcionais e podem ser puladas para MVP mais rápido
- O pipeline de produção (`orchestrator.py`, `phase_setup.py`, etc.) nunca deve ser modificado
- Cada task referencia os requisitos específicos para rastreabilidade
- Checkpoints garantem validação incremental antes de avançar para a próxima fase
- Property tests usam Hypothesis (backend) e fast-check (frontend TypeScript)
- O banco Turso é compartilhado: tabela `empresas` (leitura) + tabelas `geo_*` (escrita/leitura)
