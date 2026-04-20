# Implementation Plan: Recruitable Area Analysis

## Overview

Adiciona à aba "Análise de Área" (`AreaAnalysisTab`) um módulo explícito de avaliação de viabilidade de recrutamento de parceiros logísticos last-mile. A implementação tem duas partes: (1) enriquecimento do `heatmap.geojson` no backend com campos de demanda alocada e residual após o matching hierárquico, e (2) novo evaluator no frontend que consome esses campos diretamente, sem recalcular cobertura.

## Tasks

- [x] 0. Enriquecer `heatmap.geojson` com demanda alocada e residual no backend
  - Criar função `_enrich_heatmap_with_residual(heatmap_path, fit, pkg, territories)` em `backend/vanilla/phase5_reports.py`
  - Para cada hex do `heatmap.geojson`, verificar se existe parceiro `Active` ou `Onboarding` com `matched_slot_id` cujo `origin_hex` está em `h3.grid_disk(hex_id, 1)` — se sim, o hex é considerado coberto
  - Adicionar campos ao `properties` de cada feature do heatmap:
    - `demand_allocated`: `demand_daily` do hex se coberto por parceiro ativo, senão `0`
    - `demand_residual`: `demand_daily - demand_allocated`
    - `is_covered`: `true` se coberto, `false` caso contrário
    - `covering_partner_id`: `salesforce_id` do parceiro que cobre o hex (ou `null`)
  - Chamar `_enrich_heatmap_with_residual` ao final de `run_phase5`, após o matching já estar consolidado no `fit`
  - Fazer merge parcial: preservar hexes de outras stations não processadas (mesmo padrão do `_write_geojson`)
  - _Requirements: 3.2, 3.3_

  - [x] 0.1 Escrever testes unitários para `_enrich_heatmap_with_residual`
    - Testar que hex coberto por parceiro Active recebe `is_covered=True` e `demand_residual=0`
    - Testar que hex sem cobertura recebe `is_covered=False` e `demand_residual=demand_daily`
    - Testar que parceiros Onboarding também cobrem hexes
    - Testar que parceiros com status diferente de Active/Onboarding não cobrem hexes
    - Testar merge parcial: hexes de outras stations são preservados sem alteração

- [x] 1. Adicionar tipos e interfaces ao store
  - Adicionar `RecruitableAnalysisParams`, `RecruitableAnalysisResult` e `RecruitableAnalysisState` em `src/store/types.ts`
  - Adicionar `EvaluatorResult`, `EvaluatorError` e `ReasonCode` como tipos exportados em `src/store/types.ts` (ou em arquivo separado `src/lib/recruitableAreaEvaluator.ts` — definir junto ao evaluator)
  - _Requirements: 1.1, 1.2, 2.1, 3.2, 3.3, 4.4_

- [x] 2. Adicionar slice `recruitableAnalysis` ao store Zustand
  - Adicionar estado inicial `recruitableAnalysisState` em `src/store/index.ts` com valores padrão: `minAdv: 40`, `radiusMeters: 1500`, `centerLat: ''`, `centerLon: ''`, `selectedLeadId: null`, `result: null`, `error: null`, `isStale: false`
  - Implementar actions: `setRecruitableParams`, `setRecruitableResult`, `clearRecruitableAnalysis`
  - `setRecruitableParams` deve marcar `isStale: true` quando há resultado existente
  - `clearRecruitableAnalysis` deve limpar `result`, `error`, `centerLat`, `centerLon`, `selectedLeadId` e `isStale`, preservando `minAdv` e `radiusMeters`
  - _Requirements: 1.6, 8.2, 8.3, 8.4_

  - [x] 2.1 Escrever property test para limpeza preserva configuração (Property 8)
    - **Property 8: Limpeza preserva configuração**
    - **Validates: Requirements 8.2, 8.3**
    - Usar fast-check para gerar estados arbitrários com `minAdv` e `radiusMeters` e verificar que após `clearRecruitableAnalysis` esses valores são preservados

  - [x] 2.2 Escrever property test para alteração de parâmetro invalida resultado (Property 9)
    - **Property 9: Alteração de parâmetro invalida resultado**
    - **Validates: Requirements 8.4**
    - Verificar que qualquer chamada a `setRecruitableParams` com resultado existente resulta em `isStale: true`

- [x] 3. Implementar `recruitableAreaEvaluator.ts`
  - Criar `src/lib/recruitableAreaEvaluator.ts` com a função pura `evaluateRecruitableArea(input: EvaluatorInput): EvaluatorResult | EvaluatorError`
  - Implementar extração de centroide: `Point` → usar `coordinates` diretamente; `Polygon` → usar `turf.centroid`
  - Implementar filtragem de células por raio: `turf.distance(center, hexCentroid, { units: 'meters' }) <= radiusMeters`
  - Usar campos `demand_residual` e `is_covered` do heatmap (gerados pelo backend na task 0) para calcular demanda residual — **não recalcular cobertura no frontend**
  - `totalDemand` = soma de `demand_daily` das células selecionadas; `residualDemand` = soma de `demand_residual` das células selecionadas
  - `residualCells` = células selecionadas onde `is_covered === false`
  - Implementar lógica de `ReasonCode`: `selectedCells.length === 0` → `NO_HEATMAP_COVERAGE`; `totalDemand < minAdv` → `INSUFFICIENT_TOTAL_DEMAND`; senão → `INSUFFICIENT_RESIDUAL_DEMAND`
  - Implementar type guard `isEvaluatorError`
  - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 4.1, 4.2, 4.3, 4.4_

  - [x] 3.1 Escrever property test para filtragem de células por raio (Property 2)
    - **Property 2: Filtragem de células por raio**
    - **Validates: Requirements 3.1**
    - Gerar conjuntos arbitrários de células com centroides e verificar que `selectedCells` contém exatamente as células com distância ≤ raio

  - [x] 3.2 Escrever property test para demanda total (Property 3)
    - **Property 3: Demanda total é soma das células selecionadas**
    - **Validates: Requirements 3.2**
    - Verificar que `totalDemand === sum(selectedCells.demand_daily)`

  - [x] 3.3 Escrever property test para demanda residual (Property 4)
    - **Property 4: Demanda residual é soma das células não cobertas**
    - **Validates: Requirements 3.3**
    - Verificar que `residualDemand === sum(residualCells.demand_daily)` onde `residualCells ⊆ selectedCells`

  - [x] 3.4 Escrever property test para classificação binária de viabilidade (Property 5)
    - **Property 5: Classificação binária de viabilidade**
    - **Validates: Requirements 4.1, 4.2**
    - Gerar pares `(residualDemand, minAdv)` arbitrários e verificar `viable === (residualDemand >= minAdv)`

  - [x] 3.5 Escrever property test para estrutura completa do resultado (Property 6)
    - **Property 6: Estrutura completa do resultado**
    - **Validates: Requirements 4.3, 4.4**
    - Verificar que toda execução válida retorna objeto com todos os campos obrigatórios preenchidos

  - [x] 3.6 Escrever testes unitários para `recruitableAreaEvaluator`
    - Testar retorno `MISSING_HEATMAP` quando `heatmapFeatures` é array vazio/null
    - Testar retorno `MISSING_CENTER` quando `centerLat`/`centerLon` são inválidos
    - Testar resultado com `totalDemand: 0` e `reason: NO_HEATMAP_COVERAGE` quando nenhuma célula está no raio
    - Testar que células com `is_covered=true` não entram em `residualCells`
    - Testar que `demand_residual` do heatmap é usado diretamente (sem recalcular cobertura)
    - _Requirements: 3.4, 3.5_

- [x] 4. Checkpoint — Verificar evaluator
  - Garantir que todos os testes do evaluator passam. Perguntar ao usuário se há dúvidas antes de prosseguir.

- [x] 5. Criar `MapClickCapture.tsx`
  - Criar `src/components/map/MapClickCapture.tsx` como componente interno do mapa
  - Usar `useMapEvents` do react-leaflet para capturar evento `click`
  - Emitir `CustomEvent('atlas:map-click-coords', { detail: { lat, lng } })` no `document` quando a aba "Área" está ativa
  - Receber prop `isActive: boolean` para habilitar/desabilitar a captura
  - _Requirements: 2.2_

- [x] 6. Criar `RecruitableAreaLayer.tsx`
  - Criar `src/components/map/RecruitableAreaLayer.tsx` como camada Leaflet
  - Ler `recruitableAnalysisState` do store Zustand
  - Renderizar `Circle` do react-leaflet centrado em `centerLat`/`centerLon` com raio `radiusMeters` quando ponto central está definido
  - Renderizar `GeoJSON` com as `selectedCells` destacadas: células em `residualCells` com cor diferente das células cobertas
  - Retornar `null` quando `result === null` e ponto central não está definido
  - _Requirements: 2.4, 2.5, 7.1, 7.2, 7.3, 7.4_

  - [x] 6.1 Escrever testes unitários para `RecruitableAreaLayer`
    - Testar renderização condicional: sem resultado → sem camadas
    - Testar que `Circle` aparece quando ponto central está definido
    - Testar que células residuais e cobertas recebem estilos diferentes
    - _Requirements: 7.1, 7.2, 7.3_

- [x] 7. Integrar novas camadas ao `MapView.tsx`
  - Importar e renderizar `RecruitableAreaLayer` em `src/components/map/MapView.tsx`
  - Importar e renderizar `MapClickCapture` passando prop `isActive` baseada no estado da aba ativa
  - Adicionar pane `recruitablePane` com zIndex adequado (acima do heatmap) em `LayerPanesSetup`
  - _Requirements: 2.2, 7.4_

- [x] 8. Refatorar `AreaAnalysisTab.tsx` — formulário de parâmetros e integração com lead
  - Adicionar seção "Área Recrutável" ao `AreaAnalysisTab` existente, preservando a seção de análise de prospects atual
  - Implementar campos numéricos para ADV mínimo (padrão 40, unidade "pacotes/dia") e raio de entrega (padrão 1500, unidade "metros") conectados ao store via `setRecruitableParams`
  - Implementar campos de latitude e longitude do ponto central
  - Implementar listener para `atlas:map-click-coords` que preenche lat/lon automaticamente
  - Implementar validação inline: valores ≤ 0, não-numéricos ou vazios exibem mensagem e desabilitam botão de análise
  - Implementar seção "Analisar Lead" com `<select>` de prospects (status `Prospect`) que pré-preenche `centerLat`, `centerLon`, `radiusMeters` e `minAdv` a partir de `optimization.radius_suggestion`, `optimization.cap_suggestion`, `lat` e `lon` do lead
  - Exibir aviso inline quando lead selecionado não possui coordenadas
  - Exibir motivo do No Go do lead quando `decision === 'No Go'`
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 2.1, 2.2, 2.3, 6.1, 6.2, 6.3, 6.4, 6.5_

  - [x] 8.1 Escrever property test para validação de campos numéricos positivos (Property 1)
    - **Property 1: Validação de campos numéricos positivos**
    - **Validates: Requirements 1.3, 1.4, 1.5**
    - Gerar valores inteiros positivos e verificar que são aceitos; gerar valores ≤ 0 e verificar que são rejeitados

  - [x] 8.2 Escrever property test para preenchimento automático a partir de lead (Property 7)
    - **Property 7: Preenchimento automático a partir de lead**
    - **Validates: Requirements 6.2, 6.3**
    - Gerar leads arbitrários com lat/lon e optimization definidos e verificar que os campos são preenchidos com os valores exatos do lead

  - [x] 8.3 Escrever testes unitários para `AreaAnalysisTab` — seção recrutável
    - Testar renderização dos campos com valores padrão (ADV=40, raio=1500)
    - Testar que botão de análise fica desabilitado com valores inválidos
    - Testar que aviso de lead sem coordenadas é exibido
    - Testar que motivo No Go do lead é exibido
    - _Requirements: 1.1, 1.2, 1.5, 6.4, 6.5_

- [x] 9. Implementar lógica de análise e painel de resultado no `AreaAnalysisTab.tsx`
  - Implementar handler do botão "Analisar Área Recrutável" que chama `evaluateRecruitableArea` com dados do store e salva resultado via `setRecruitableResult`
  - Implementar painel de resultado separado visualmente dos controles de configuração
  - Exibir classificação de viabilidade com destaque visual: verde para Viável, vermelho para Não Viável
  - Exibir valores numéricos: demanda total, demanda residual, ADV mínimo e gap
  - Exibir barra de progresso visual `(residualDemand / minAdv) * 100` com escala 0–100%+
  - Exibir motivo da não viabilidade quando `viable === false`
  - Exibir decisão atual do lead (Go/No Go) e motivo quando lead está selecionado
  - Exibir indicação visual de resultado desatualizado quando `isStale === true`
  - _Requirements: 4.3, 4.4, 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 8.4_

- [x] 10. Implementar botão "Limpar Análise" no `AreaAnalysisTab.tsx`
  - Exibir botão "Limpar Análise" somente após execução de uma análise (`result !== null`)
  - Acionar `clearRecruitableAnalysis` do store ao clicar
  - _Requirements: 8.1, 8.2, 8.3_

- [x] 11. Checkpoint final — Garantir integração completa
  - Garantir que todos os testes passam (`vitest --run`)
  - Verificar que o círculo de raio e o highlight de H3 cells aparecem no mapa após análise
  - Verificar que "Limpar Análise" remove elementos visuais
  - Perguntar ao usuário se há ajustes antes de encerrar.

## Notes

- Tarefas marcadas com `*` são opcionais e podem ser puladas para MVP mais rápido
- **Task 0 é pré-requisito das tasks de frontend** — o evaluator depende dos campos `demand_residual` e `is_covered` no heatmap
- O design usa TypeScript — todos os exemplos de código devem seguir tipagem estrita
- `@turf/turf` já é dependência do projeto; `fast-check` já está disponível como devDependency
- Cada tarefa referencia requisitos específicos para rastreabilidade
- Os checkpoints garantem validação incremental antes de avançar para a próxima fase
