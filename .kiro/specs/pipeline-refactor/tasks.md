# Implementation Plan: pipeline-refactor

## Overview

Migração em 4 fases do pipeline de dados do ATLAS. O objetivo é unificar o fluxo em `load_partners.py` lendo diretamente do Excel, serializar `dados_mapa.json` com schema limpo, e ajustar o frontend para consumir o novo schema — sem downtime em nenhuma fase.

**Arquivos fora do escopo (não modificar):**
- `backend/data_processing/excel_handler.py`
- `backend/data_processing/generate_scorecard_json.py`
- `backend/phase3_partner_fit.py`
- `backend/phase4_webleads.py`
- `backend/phase5_reports.py`
- `js/modules/ui-manager.js`
- `js/modules/map-manager.js`
- `js/modules/polygon-manager.js`
- `js/modules/route-manager.js`
- `js/modules/gmaps-scraper.js`
- `js/modules/management-dashboard.js`

---

## Tasks

- [x] 1. Fase 1 — Preparação: adicionar novas funções sem quebrar o fluxo atual
  - [x] 1.1 Adicionar dataclass `Partner` em `backend/models.py`
    - Criar a dataclass com todos os campos do Schema_Limpo: `salesforce_id`, `store_id`, `name`, `status`, `lead_source`, `lat`, `lon`, `zip_code`, `city`, `state`, `delivery_station`, `supply_run`, `radius`, `capacity`, `bucket`, `jurisdiction_type`, `hub_delivey_initiatives`, `HCP_rate_card`, `HCP_host_partner`, `launch_date`, `exited_date`, `telefone`, `owner_id`, `decision_status`, `tooltip`
    - Implementar `Partner.from_row(row, active_df, station_map, jurisdictions_map)`: aplica mapeamento DS (HSP2→DSP2), resolve HCP Host Partner por Id→Name, normaliza telefone (remove `(`, `)`, ` `, `-`, `+`), converte vírgula→ponto em coords, gera tooltip
    - Implementar `Partner.to_dict()`: serializa para o Schema_Limpo, converte NaN/None/NaT em `None` (→ JSON null), garante que campos numéricos ausentes viram `None`
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 7.1, 7.2, 7.3, 7.4_

  - [x] 1.2 Adicionar funções privadas novas em `backend/load_partners.py` (sem alterar o fluxo existente)
    - Adicionar `_consolidate_stores(dfs)`: migrado de `DataProcessor.consolidate_stores` — consolida Active + Launches + WebLeads, aplica mapeamento DS, resolve Bucket via Jurisdictions, normaliza coordenadas
    - Adicionar `_build_partners(consolidated_df) -> List[Partner]`: itera o DataFrame e constrói objetos `Partner` via `Partner.from_row()`
    - Adicionar `serialize_to_json(partners, period, output_path)`: serializa a lista de `Partner` para `dados_mapa.json` com Schema_Limpo; inclui `period` e `deliveryStations` (de `config.DELIVERY_STATIONS`) na raiz
    - Adicionar `_build_partner_data(partners) -> PartnerData`: separa web leads (`status="New"` AND `lead_source="Website Pardot Form"`), renomeia `delivery_station`→`station_code` e `name`→`partner_name`, remove parceiros sem lat/lon (exceto prospects), calcula `origin_hex` via H3, adiciona `zip_clean` em `web_leads_df`
    - O fluxo existente de `load_partners` (leitura via JSON) deve permanecer intacto nesta fase
    - _Requirements: 1.1, 1.2, 1.3, 4.1, 4.2, 4.3, 4.4, 5.1, 5.2, 5.3_

  - [x] 1.3 Criar `backend/tests/test_pipeline_properties.py` com as 4 propriedades Hypothesis
    - Implementar estratégias: `partner_strategy()`, `partner_with_coords_strategy()`, `mixed_records_strategy()`
    - Implementar helper `_build_partner_data_from_records(records)` e `_build_partner_data_from_partners(partners)` para isolar as funções testadas
    - **Property 1: Schema exato do JSON de saída** — `@given(st.lists(partner_strategy(), min_size=1, max_size=50))`: para qualquer lista de `Partner`, cada objeto em `allMarkerData` deve conter exatamente os campos do `SCHEMA_FIELDS`
      - **Validates: Requirements 3.1, 3.2, 8.1**
    - **Property 2: Ausência de NaN/None em strings serializadas** — `@given(st.lists(partner_strategy(), min_size=1, max_size=50))`: nenhum campo string deve conter `"nan"`, `"None"` ou `"NaN"` após `to_dict()`
      - **Validates: Requirements 3.3, 7.1, 7.2, 8.5**
    - **Property 3: Separação correta de web leads** — `@given(st.lists(mixed_records_strategy(), min_size=2, max_size=100))`: nenhum web lead em `partners_df`, nenhum parceiro operacional em `web_leads_df`
      - **Validates: Requirements 4.1, 4.2, 4.3, 8.3**
    - **Property 4: `origin_hex` é uma string H3 válida** — `@given(st.lists(partner_with_coords_strategy(), min_size=1, max_size=50))`: `h3.is_valid_cell(origin_hex)` deve ser `True` para todo parceiro com coords válidas
      - **Validates: Requirements 5.3, 8.2**
    - _Requirements: 8.1, 8.2, 8.3, 8.5_

  - [ ]* 1.4 Executar `test_pipeline_properties.py` e confirmar que as 4 propriedades passam
    - Rodar com `pytest backend/tests/test_pipeline_properties.py -v`
    - Todas as 4 propriedades devem passar antes de avançar para a Fase 2
    - _Requirements: 8.1, 8.2, 8.3, 8.5_

- [x] 2. Checkpoint Fase 1 — Testes passam, sistema em produção inalterado
  - Garantir que `pytest backend/tests/test_pipeline_properties.py` passa sem erros
  - Garantir que o fluxo existente (`orchestrator.py --mode daily`) ainda funciona via JSON
  - Perguntar ao usuário se há dúvidas antes de avançar

- [x] 3. Fase 2 — Ativar novo pipeline em paralelo
  - [x] 3.1 Modificar `load_partners` para usar o novo fluxo Excel quando `partners_path=None`
    - Quando `partners_path=None`: chamar `ExcelHandler.refresh_and_load_sheets(SHEETS_TO_LOAD, ...)`, depois `_consolidate_stores`, `_build_partners`, `serialize_to_json`, `_build_partner_data`
    - Manter suporte a `partners_path=str` (leitura via JSON) para rollback imediato
    - Lançar `FileNotFoundError` com mensagem descritiva se `terra.xlsm` não for encontrado
    - _Requirements: 1.1, 1.4, 1.5, 5.5, 5.6_

  - [x] 3.2 Comparar output do novo pipeline com o pipeline antigo
    - Executar o novo pipeline e o antigo sobre o mesmo `terra.xlsm`
    - Verificar que todos os `salesforce_id` presentes no JSON antigo estão no novo
    - Verificar que campos do Schema_Limpo têm os mesmos valores nos dois JSONs
    - Verificar que o frontend carrega o novo JSON sem erros no console
    - _Requirements: 3.1, 3.2, 3.3, 5.1, 5.2_

- [x] 4. Checkpoint Fase 2 — JSON novo é funcionalmente equivalente ao antigo
  - Garantir que `dados_mapa.json` gerado pelo novo pipeline é aceito pelo frontend sem erros
  - Garantir que `orchestrator.py --mode daily` completa com sucesso usando o novo fluxo
  - Perguntar ao usuário se há dúvidas antes de avançar

- [x] 5. Fase 3 — Atualizar frontend
  - [x] 5.1 Atualizar `js/models.js` — classe `Partner`
    - Renomear `this.exitedDate` → `this.exited_date` (lendo `raw.exited_date ?? null`)
    - Renomear `this.leadSource` → `this.lead_source` (lendo `raw.lead_source ?? null`)
    - Remover campos obsoletos do constructor: `main_store_data`, `overlap_data`, `ADV`
    - Adicionar campos ausentes: `zip_code`, `city`, `state`, `bucket`, `jurisdiction_type`, `owner_id`, `decision_status` (todos com `?? null`)
    - _Requirements: 6.1, 6.2, 6.3_

  - [x] 5.2 Verificar e corrigir referências a `exitedDate`/`leadSource` em `js/modules/data-manager.js`
    - Buscar todas as ocorrências de `exitedDate` e `leadSource` no arquivo
    - Substituir por `exited_date` e `lead_source` onde necessário
    - Confirmar que `_aggregateOptimizationData` permanece sem alteração (continua injetando `bucket_ade`, `decision`, `reason`, `optimization` via `optimization_data.geojson`)
    - _Requirements: 6.1, 6.2, 6.4, 6.5_

  - [x] 5.3 Remover `toggleMenu` e `#menuOptions` de `ATLAS.html`
    - Remover o elemento `<div id="menuOptions" class="menu-options">` e seu conteúdo
    - Remover a chamada `onclick="UIManager.toggleMenu()"` do botão de menu
    - _Requirements: 6.8_

  - [x] 5.4 Criar `js/tests/partner-schema.test.js` com as 2 propriedades Jest
    - Importar `Partner` de `../models.js`
    - Definir `SCHEMA_FIELDS` com todos os 25 campos do Schema_Limpo
    - **Property 5: Partner JavaScript sem `undefined`** — construir `new Partner(raw)` com objeto contendo todos os campos do Schema_Limpo (incluindo `null` para opcionais) e verificar que nenhuma propriedade é `undefined`
      - **Validates: Requirements 6.1, 6.2, 6.3, 8.4**
    - **Property 6: Round-trip de serialização** — verificar que `new Partner(raw)` preserva os campos chave `salesforce_id`, `lat`, `lon`, `status`, `exited_date`, `lead_source` com os mesmos valores do `raw`
      - **Validates: Requirements 3.5, 3.6, 6.1, 6.2, 8.6**
    - _Requirements: 6.1, 6.2, 6.3, 8.4, 8.6_

  - [ ]* 5.5 Executar `partner-schema.test.js` e confirmar que as 2 propriedades passam
    - Rodar com `node --experimental-vm-modules node_modules/.bin/jest js/tests/partner-schema.test.js`
    - Ambas as propriedades devem passar antes de avançar para a Fase 4
    - _Requirements: 8.4, 8.6_

- [x] 6. Checkpoint Fase 3 — Testes JS passam, frontend funcional com novo schema
  - Garantir que `jest js/tests/partner-schema.test.js` passa sem erros
  - Garantir que o frontend carrega sem erros de `undefined` no console
  - Perguntar ao usuário se há dúvidas antes de avançar

- [x] 7. Fase 4 — Limpeza: remover código legado
  - [x] 7.1 Remover métodos obsoletos de `backend/data_processing/data_processor.py`
    - Remover `calculate_historical_metrics`
    - Remover `calculate_perfect_mile_metrics`
    - Remover `calculate_overlaps`
    - Remover `enrich_with_overlaps`
    - Manter `consolidate_stores` (ainda referenciado durante período de transição)
    - _Requirements: 2.1, 2.2_

  - [x] 7.2 Deletar `backend/data_processing/json_generator.py`
    - Remover o arquivo `json_generator.py` do projeto
    - _Requirements: 2.4_

  - [x] 7.3 Simplificar `backend/main.py` para stub
    - Remover imports de `DataProcessor`, `JsonGenerator` e sheets obsoletas
    - Implementar `run_pipeline()` como stub: chama `load_partners()` (que já serializa o JSON) e `ScorecardGenerator` com a aba `Lead`
    - _Requirements: 2.3_

  - [x] 7.4 Atualizar `backend/config.py` — remover sheets obsoletas
    - Remover `"ADV - Coverage raw data"` e `"PerfectMile"` de `SHEETS_TO_LOAD`
    - Manter `"Active"`, `"Launches"`, `"Delivery Stations"`, `"Jurisdictions"`, `"WebLeads"` em `SHEETS_TO_LOAD`
    - Adicionar `SHEETS_SCORECARD = ["Lead"]` para uso exclusivo do scorecard em `main.py`
    - _Requirements: 2.3_

  - [x] 7.5 Atualizar `backend/orchestrator.py` — remover `partners_path` da chamada a `load_partners`
    - Remover o argumento `partners_path` da chamada a `load_partners` em `run_daily`
    - `load_partners()` passa a ser chamado sem argumentos, ativando o fluxo Excel por padrão
    - _Requirements: 5.5_

  - [x] 7.6 Atualizar `row_to_partner_metrics` e `PartnerMetrics` para `exited_date`
    - Em `backend/load_partners.py`: substituir `exitedDate` → `exited_date` em `row_to_partner_metrics`
    - Em `backend/models.py`: renomear campo `exitedDate` → `exited_date` em `PartnerMetrics`
    - Verificar que `phase3_partner_fit.py` e `phase5_reports.py` leem o campo correto (sem modificar esses arquivos — apenas confirmar que já usam o nome novo ou que a mudança é transparente)
    - _Requirements: 5.2, 5.4_

- [x] 8. Checkpoint Final — Todos os testes passam, nenhuma referência a código removido
  - Garantir que `pytest backend/tests/` passa sem erros (incluindo `test_pipeline_properties.py`)
  - Garantir que `jest js/tests/partner-schema.test.js` passa sem erros
  - Verificar que não há imports de `JsonGenerator`, `calculate_historical_metrics`, `calculate_perfect_mile_metrics`, `calculate_overlaps` ou `enrich_with_overlaps` em nenhum arquivo
  - Executar `orchestrator.py --mode daily` e confirmar que completa sem erros
  - Perguntar ao usuário se há dúvidas antes de encerrar

## Notes

- Tasks marcadas com `*` são opcionais e podem ser puladas para MVP mais rápido
- A ordem das fases é crítica: testes ANTES de deletar código legado, frontend ANTES de remover campos do JSON
- O rollback em qualquer fase é possível passando `partners_path=Config.BASE_PARTNERS` explicitamente em `orchestrator.py`
- Property tests validam invariantes universais; os checkpoints garantem que o sistema funciona end-to-end antes de cada fase destrutiva
