# Implementation Plan: Area Analysis Panel

## Overview

Implementação em duas camadas: backend Python (models + phase3 + phase5) e frontend JS/HTML (data-manager, ui-manager, main.js, ATLAS.html). O backend produz os campos `decision`/`reason` binários; o frontend os consome para filtrar prospects e exibir o Stats_Popup.

## Tasks

- [x] 1. Backend — Adicionar campo `reason` ao `PartnerMetrics`
  - Em `backend/models.py`, adicionar `reason: str = ""` ao dataclass `PartnerMetrics`, logo após o campo `decision`
  - _Requirements: 6.3_

- [x] 2. Backend — Refatorar decisões da Fase 3 para Go/No Go + reason
  - [x] 2.1 Substituir strings descritivas de `decision` por `"Go"` / `"No Go"` em `_match_station()` (`phase3_partner_fit.py`)
    - Parceiros matched (qualquer status): `decision = "Go"`, `reason = "Seguir cadastro"`
    - Prospects não-matched (`PROSPECT`): `decision = "No Go"`, `reason = "Sem oportunidade próxima"`
    - Prospects de borda não-matched (`PROSPECT_BORDER`): `decision = "No Go"`, `reason = "Sem oportunidade próxima na borda"`
    - Prospects fora de jurisdição (`outside_list`): `decision = "No Go"`, `reason = "Fora de jurisdição"`
    - Parceiros não-Prospect não-matched (Active, Onboarding, BG Checks, Inactive): manter `decision` descritivo existente, `reason = ""`
    - _Requirements: 6.1, 6.2, 6.3, 6.5, 6.6_

  - [x] 2.2 Escrever property test para decisão binária (hypothesis)
    - **Property 5: Decisão binária é consistente com o resultado do matching**
    - Para qualquer prospect processado: se matched → `decision == "Go"` e `reason == "Seguir cadastro"`; se não matched → `decision == "No Go"` e `reason` em `VALID_NO_GO_REASONS`
    - Criar `backend/tests/test_phase3_properties.py` com `@given` usando `hypothesis`
    - **Validates: Requirements 6.1, 6.2, 6.3, 6.5, 6.6**

- [x] 3. Backend — Serializar `reason` no GeoJSON (phase5)
  - Em `phase5_reports.py`, função `_write_geojson()`, bloco `PARTNER_POINT`: adicionar `"reason": p.reason` nas `properties`, logo após `"decision": p.decision`
  - _Requirements: 6.4_

  - [x] 3.1 Escrever property test para serialização round-trip (hypothesis)
    - **Property 6: Serialização preserva decision e reason**
    - Para qualquer `PartnerMetrics` com `decision`/`reason` preenchidos, a feature `PARTNER_POINT` gerada deve ter os mesmos valores
    - Criar `backend/tests/test_phase5_properties.py`
    - **Validates: Requirements 6.4**

- [x] 4. Checkpoint — Backend
  - Garantir que `models.py`, `phase3_partner_fit.py` e `phase5_reports.py` estão sem erros de sintaxe/importação. Perguntar ao usuário se há dúvidas antes de prosseguir.

- [x] 5. Frontend — Injetar `partner.reason` no data-manager
  - Em `js/modules/data-manager.js`, função `_aggregateOptimizationData()`: adicionar `partner.reason = info.properties.reason ?? '';` logo após a linha que injeta `partner.decision`
  - _Requirements: 6.4_

- [x] 6. Frontend — Refatorar `#highlight-content` no ATLAS.html
  - [x] 6.1 Renomear aba de "Destaques" para "Análise de Área" (ícone `fa-map-marked-alt`)
    - _Requirements: 1.1_
  - [x] 6.2 Substituir o conteúdo interno da div `#highlight-content` pelos filtros de Estado e Decisão e botão "Analisar Área" conforme o design
    - Remover campos `eligiblePackagesOp`, `overlappingOp`, `allocatedCurrentOp`, `statusHighlightFilter` e botões `highlight-btn` / `highlight-btn-clear`
    - Adicionar texto informativo de filtro fixo, `<select id="areaStateFilter">`, `<select id="areaDecisionFilter">` e `<button id="analyseAreaBtn">`
    - _Requirements: 1.2, 1.3, 2.1, 2.2, 2.3, 2.4, 2.6, 4.1_

- [x] 7. Frontend — Implementar funções em `ui-manager.js`
  - [x] 7.1 Implementar `populateAreaAnalysisFilters()`
    - Filtrar `state.allMarkersData` por `status === 'Prospect'`, extrair valores únicos e ordenados de `state`, popular `#areaStateFilter` com "Todos" + estados
    - Exportar a função
    - _Requirements: 2.1, 2.2, 2.5_

  - [x] 7.2 Escrever property test para `populateAreaAnalysisFilters` (fast-check)
    - **Property 1: Select de Estado reflete exatamente os estados únicos dos Prospects**
    - Criar `js/tests/area-analysis.test.js` com `fc.assert` usando `fast-check`
    - **Validates: Requirements 2.1, 2.2, 2.5**

  - [x] 7.3 Implementar função interna `renderStatsPopup(prospects, filters)`
    - Calcular `total`, `goCount`, `approvalRate`, `reasonCounts` para os três motivos de No Go
    - Gerar HTML do popup com título, filtros ativos, tabela de métricas e botão ×
    - Exibir mensagem de ausência quando `total === 0`
    - Inserir no DOM via `document.body.insertAdjacentHTML('beforeend', html)`
    - _Requirements: 4.5, 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 5.7_

  - [x] 7.4 Escrever property test para estatísticas do popup (fast-check)
    - **Property 3: Estatísticas do popup são aritmeticamente corretas**
    - Extrair `computeStats()` como função pura e testá-la com arrays arbitrários de prospects
    - **Validates: Requirements 5.1, 5.2, 5.3, 5.4, 5.5**

  - [x] 7.5 Implementar `analyseArea()`
    - Ler valores de `#areaStateFilter` e `#areaDecisionFilter`
    - Filtrar `state.allMarkersData` por `status === 'Prospect'`, depois por estado e decisão
    - Chamar `renderStatsPopup(filtered, { state, decision })`
    - Exportar a função
    - _Requirements: 3.1, 3.2, 4.2, 4.3, 4.4_

  - [x] 7.6 Escrever property test para filtragem combinada (fast-check)
    - **Property 2: Filtragem combinada satisfaz todos os predicados simultaneamente**
    - Extrair `computeFilteredProspects()` como função pura e testá-la
    - **Validates: Requirements 3.1, 4.2, 4.3, 4.4**

  - [x] 7.7 Implementar `closeStatsPopup()`
    - `document.getElementById('stats-area-popup')?.remove()`
    - Exportar a função
    - _Requirements: 5.6, 7.1, 7.2_

- [x] 8. Frontend — Wiring em `main.js`
  - [x] 8.1 Importar `populateAreaAnalysisFilters` e `closeStatsPopup` de `ui-manager.js`
  - [x] 8.2 Adicionar `populateAreaAnalysisFilters()` ao subscriber de `allMarkersData`
    - _Requirements: 2.5_
  - [x] 8.3 Registrar listener `shown.bs.tab` nos tabs de `#controlTabs` para chamar `closeStatsPopup()` ao trocar para qualquer aba diferente de `#highlight-content`
    - _Requirements: 7.1, 7.2, 7.3_
  - [x] 8.4 Expor `analyseArea` e `closeStatsPopup` em `window.UIManager`
    - _Requirements: 4.1_

- [x] 9. Checkpoint final — Garantir que todos os testes passam
  - Verificar ausência de erros de diagnóstico em todos os arquivos modificados. Perguntar ao usuário se há dúvidas antes de encerrar.

## Notes

- Tarefas marcadas com `*` são opcionais e podem ser puladas para um MVP mais rápido
- O campo `reason` é populado apenas para Prospects; para outros status fica `""`
- `closeStatsPopup()` usa `?.remove()` — seguro quando o popup não existe
- Property tests do backend requerem `pip install hypothesis`; do frontend requerem `npm install --save-dev fast-check`
