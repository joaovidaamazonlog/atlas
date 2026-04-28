# Implementation Plan — frontend-performance

> As 4 otimizações são independentes entre si. Sugere-se implementar na ordem abaixo (maior impacto percebido → menor) e gerar um PR por bloco para facilitar revisão visual. Os testes acompanham cada bloco.

- [x] 1. Helper compartilhado de virtualização
  - Criar `atlas-react/src/components/dashboard/useRowVirtualization.ts` com o hook `useRowVirtualization({ rowCount, rowHeight, threshold = 100, maxHeight = 400 })` retornando `{ parentRef, virtualizer, enabled, containerStyle }`.
  - Usar `useVirtualizer` de `@tanstack/react-virtual` com `overscan: 10`, `getScrollElement: () => parentRef.current`, `estimateSize: () => rowHeight`, `enabled = rowCount > threshold`.
  - Exportar tipos `RowVirtualizationOptions` e `RowVirtualizationResult`.
  - Criar teste `atlas-react/src/__tests__/dashboard/useRowVirtualization.test.ts` validando `enabled` abaixo e acima do threshold e o tamanho do `containerStyle`.
  - _Requirements: 2.1, 2.2, 2.3, 3.1, 3.2, 3.3_

- [x] 2. Virtualização da `TerritoryTable` (Dashboard.tsx)
  - Em `atlas-react/src/components/dashboard/Dashboard.tsx`, refatorar `TerritoryTable` para consumir `useRowVirtualization({ rowCount: rows.length, rowHeight: 36 })`.
  - Dividir o markup em duas `<table className="table-fixed">` — uma só para o `<thead>` sticky, outra para o `<tbody>` dentro do container scrollável referenciado por `parentRef`.
  - Adicionar `<colgroup>` ou larguras explícitas nas colunas para manter alinhamento entre a tabela do header e a tabela do corpo.
  - Quando `enabled === false`, renderizar `rows` diretamente dentro de um contêiner `max-h-[400px] overflow-y-auto` (comportamento atual preservado).
  - Quando `enabled === true`, renderizar apenas `virtualizer.getVirtualItems()` com `position: 'absolute'`, `top: v.start`, `width: '100%'`, `height: 36`, sobre um `<table>` de altura total `virtualizer.getTotalSize()`.
  - Mensagem `dashboard.no_territory_found` permanece ativa quando `rows.length === 0`, sem ativar o virtualizador.
  - Preservar ordenação via `sortTerritories` e as classes `STATUS_CLASS_MAP` aplicadas sobre `getStatusClass`.
  - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 2.8_

- [x] 3. Virtualização da `PartnersByBucketTable`
  - Em `atlas-react/src/components/dashboard/PartnersByBucketTable.tsx`, aplicar o mesmo padrão da Task 2 operando sobre `filtered` (não sobre `rows` pré-busca).
  - Manter `useMemo` existente para `rows` (filtro por base/bucket + `localeCompare`) e `filtered` (filtro por `search`).
  - Garantir que o clique em "Exportar CSV" recebe `filtered`, mesma lista que o virtualizador apresenta (AC 3.7).
  - Quando `filtered.length === 0`, exibir `dashboard.no_territory_found` dentro da tabela sem ativar o virtualizador (AC 3.8).
  - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8_

- [x] 4. Testes de equivalência de linhas nas tabelas virtualizadas
  - Criar `atlas-react/src/__tests__/dashboard/TerritoryTable.test.tsx` com teste PBT (fast-check) gerando arrays de `TerritoryRow` de tamanho variável e verificando que o conjunto de linhas acessíveis via scroll (combinando conteúdo inicial + após `scrollToEnd`) coincide com o conjunto esperado produzido pela referência não virtualizada.
  - Criar `atlas-react/src/__tests__/dashboard/PartnersByBucketTable.test.tsx` com PBT sobre `data`, `filters`, `reportData` e `search`, validando que: (a) as linhas visíveis coincidem com o conjunto filtrado; (b) o CSV exportado contém exatamente as linhas filtradas; (c) a ordenação por `bucket_ade` com `{numeric: true}` é preservada.
  - _Requirements: 2.5, 2.6, 3.5, 3.6, 3.7, 6.2, 6.3_

- [x] 5. `PolygonLayer` — atualização imperativa via ref
  - Em `atlas-react/src/components/map/PolygonLayer.tsx`, remover a `key={JSON.stringify(filterState) + ...}` e substituir por uma implementação baseada em `useRef<LGeoJSON>` + `useEffect`.
  - Criar a camada `L.geoJSON(undefined, { style, onEachFeature, pane: 'polygonsPane' })` uma vez na montagem do componente, armazenar em `layerRef.current` e remover no cleanup.
  - `useEffect` separado controla visibilidade (`addTo`/`remove`) conforme `showPolygons` e `prospectClusters.length > 0`.
  - `useEffect` separado atualiza dados: `layer.clearLayers()` seguido de `layer.addData(filteredData)` e `layer.setStyle(styleFunc)`.
  - `useEffect` separado reaplica `styleFunc` quando `polygonColorField` muda sem tocar em features.
  - Envolver cada chamada Leaflet em `try/catch`, logando `console.error` e preservando o último estado válido (não lançar ao React).
  - Retornar `null` do componente (a camada vive no DOM do Leaflet, não do React).
  - Preservar `styleFunc` via `useMemo` dependendo de `[colorMap, polygonColorField]` e `onEachFeature` via `useMemo` estável.
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 1.8_

- [x] 6. Teste de estabilidade da instância Leaflet em `PolygonLayer`
  - Criar `atlas-react/src/__tests__/map/PolygonLayer.test.tsx` com um wrapper de teste que expõe `layerRef.current` (via `data-testid` no `useMap` fake ou via inspeção do componente).
  - Verificar: após mutações sequenciais em `filterState.selectedStations`, `filterState.selectedBuckets`, `polygonColorField`, `prospectState.clusters`, a instância `L.GeoJSON` acessada pelo ref permanece a **mesma** (`layerRefAfter === layerRefBefore`).
  - Verificar: o conjunto de `features` renderizado após mutação coincide com o esperado pela regra de filtro atual (comparando contra uma função pura `filterFeatures(polygonsData, filterState, prospectClusters, selectedBucket)` extraída para facilitar teste).
  - Verificar: mudar `polygonColorField` aciona apenas `setStyle` (não há `clearLayers` + `addData`) — usar spy nos métodos do layer mock.
  - _Requirements: 1.1, 1.2, 1.3, 1.5, 6.4_

- [x] 7. `PartnerMarkers` — `Stable_Marker_Key` e popup reativo
  - Em `atlas-react/src/components/map/PartnerMarkers.tsx`, alterar a `key` do `React.Fragment` de `` `${partner.salesforce_id}-${i18n.language}` `` para `partner.salesforce_id`.
  - Remover qualquer uso implícito de `i18n.language` em chaves de filhos.
  - Confirmar que `getPartnerPopupHtml(partner, routeOriginActive)` continua sendo chamado no corpo do `map` — React Leaflet atualizará o `<Popup>` existente quando `children` mudarem, sem desmontar o marker.
  - Garantir que o callback do `ref` do `CircleMarker` mantém `markerRefs.current.set(salesforce_id, ref)` / `delete` intactos, para que `OpenPartnerPopupListener` continue funcionando após troca de idioma.
  - Manter `React.memo(PartnerMarkers)` e os `useMemo` de `visibleData` e `colorMaps`.
  - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 5.7, 5.8_

- [x] 8. Teste de estabilidade de refs em `PartnerMarkers` na troca de idioma
  - Criar `atlas-react/src/__tests__/map/PartnerMarkers.test.tsx`.
  - Renderizar `PartnerMarkers` com fixture de 3 parceiros; capturar `markerRefs.current.get(sid)` para cada `sid`.
  - Alternar o idioma via `i18n.changeLanguage('en')` e aguardar o re-render.
  - Asserção: `markerRefs.current.get(sid)` permanece a mesma instância Leaflet (`===`) para cada `sid`.
  - Asserção adicional: o conteúdo do popup renderizado contém textos traduzidos no novo idioma (via inspeção do `innerHTML`).
  - _Requirements: 5.1, 5.2, 5.3, 5.4, 6.5_

- [x] 9. `AreaAnalysisTab` — memoização explícita das computações derivadas
  - Em `atlas-react/src/components/controls/AreaAnalysisTab.tsx` (componente `AreaAnalysisTab` principal), adicionar:
    - `const overview = useMemo(() => getGlobalOverview(allMarkersData), [allMarkersData])`
    - `const filteredProspects = useMemo(() => [...filtragem de status/decision/state...], [allMarkersData, selectedState, selectedDecision])`
    - `const filteredStats = useMemo(() => getFilteredStats(filteredProspects), [filteredProspects])`
    - `const stateRows = useMemo(() => getStatsByState(filteredProspects), [filteredProspects])`
    - `const leads = useMemo(() => filteredProspects, [filteredProspects])` (ou a ordenação adequada se `LeadsPanel` pré-ordenar).
  - Simplificar `handleAnalyze` para apenas compor esses memos em `setAnalysisResult`, sem recomputar.
  - Preservar os `useMemo` existentes em `LeadsPanel` (`[leads, search]`) e `CapOpportunityPanel` (`[allMarkersData]`).
  - Garantir que `handleAnalyze` inclua nos seus `deps` do `useCallback` os memos usados.
  - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7, 4.8, 4.9_

- [x] 10. PBT sobre funções puras de `AreaAnalysisTab`
  - Criar `atlas-react/src/__tests__/controls/areaAnalysis.pure.test.ts`.
  - Extrair `getGlobalOverview`, `getFilteredStats`, `getStatsByState` para um módulo `atlas-react/src/lib/areaAnalysisPure.ts` (import relativo a partir de `AreaAnalysisTab.tsx`) para viabilizar import limpo nos testes. A extração deve ser apenas mecânica, sem mudanças de lógica.
  - Strategies fast-check gerando parceiros com `status`, `decision`, `reason`, `state`, `lat`, `lon` variados.
  - Propriedades:
    - `getGlobalOverview: go + nogo === total evaluated`.
    - `getFilteredStats: soma de nogoReasonRows.count ≤ nogo` e `go + nogo === total`.
    - `getStatsByState: soma de (go + nogo) por UF === len(prospects com state não nulo)`.
  - _Requirements: 6.1, 6.7, 6.9_

- [x] 11. Teste de estabilidade referencial de `useMemo` em `AreaAnalysisTab`
  - Criar `atlas-react/src/__tests__/controls/AreaAnalysisTab.memo.test.tsx` usando `renderHook` para isolar cada memo.
  - Verificar que, quando as deps não mudam entre re-renders, `result.current === previousResult.current` (mesma referência).
  - Verificar que, quando uma dep muda, o valor retornado é estruturalmente igual ao produzido pela função pura aplicada diretamente sobre as novas deps.
  - _Requirements: 4.8, 4.9, 6.6, 6.7_

- [x] 12. Limpeza e documentação
  - Adicionar comentário curto no topo de `useRowVirtualization.ts` referenciando `StationsTable.tsx` como padrão de origem.
  - Adicionar seção "Performance" no `atlas-react/README.md` (ou `docs/`) listando as 4 otimizações e apontando para os testes correspondentes.
  - Rodar `npm run typecheck` e `npm test --run` (Vitest single-run) e corrigir qualquer regressão detectada.
  - _Requirements: 6.9_
