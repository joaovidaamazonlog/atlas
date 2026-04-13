# Plano de Implementação: Migração React Responsiva do ATLAS

## Visão Geral

Migração "big bang" do frontend ATLAS de HTML/CSS/JS vanilla para React + Vite + TypeScript + Tailwind CSS + Zustand + react-leaflet. As tarefas seguem uma ordem incremental: infraestrutura → tipos e estado → mapa → controles → dashboard → responsividade → otimização.

## Tarefas

- [x] 1. Configurar projeto Vite + React + TypeScript + Tailwind CSS
  - Inicializar projeto com `vite create` usando template `react-ts`
  - Instalar e configurar Tailwind CSS com `tailwind.config.ts` incluindo tokens de cor do tema escuro (`#232f3e`, `#1e2a38`, `#16202c`, `#ecf0f1`)
  - Configurar `tsconfig.json` com `strict: true` e paths de alias (`@/` → `src/`)
  - Configurar ESLint e Prettier com regras para React e TypeScript
  - Criar `src/styles/globals.css` com variáveis CSS do tema escuro e import da fonte Inter
  - Criar `src/styles/leaflet-overrides.css` para overrides do Leaflet
  - Copiar e adaptar `manifest.json` existente; registrar ServiceWorker em `src/main.tsx`
  - _Requisitos: 1.1, 1.2, 1.3, 1.4, 1.6, 14.1, 14.2, 14.3_

  - [ ]* 1.1 Verificar build de produção com code splitting
    - Executar `vite build` e confirmar geração de múltiplos chunks (Dashboard e módulos pesados em chunks separados)
    - _Requisitos: 1.5_

- [x] 2. Definir tipos TypeScript e modelos de dados
  - Criar `src/store/types.ts` com todas as interfaces: `Partner`, `DeliveryStation`, `FilterState`, `StyleConfig`, `RouteStop`, `HcpState`, `OptimizationData`, `PartnerStatus`
  - Criar `src/lib/models.ts` migrando as classes de `frontend/js/models.js` para TypeScript
  - Criar `src/lib/config.ts` migrando `DATA_URLS`, `MAP_CONFIG`, `COLOR_PALETTES`, `HCP_CONFIG`, `COST_PER_SUPPLY_RUN`, `PERFORMANCE_GOALS` de `frontend/js/config.js`
  - _Requisitos: 2.2, 16.1_

  - [ ]* 2.1 Escrever testes de propriedade para modelos de dados
    - Configurar Vitest e fast-check (`fc.configureGlobal({ numRuns: 100 })`)
    - **Propriedade 6: Filtros aplicados corretamente** — para qualquer combinação de `FilterState` e `allMarkersData`, todos os itens em `currentFilteredData` devem satisfazer todos os critérios ativos
    - **Valida: Requisito 9.2**
    - **Propriedade 7: Limpar filtros restaura dados completos** — `resetFilters` deve resultar em `currentFilteredData` idêntico a `allMarkersData`
    - **Valida: Requisito 9.3**
    - **Propriedade 8: Opções dos selects refletem valores únicos** — opções de Delivery Station e Carteira ADE devem ser exatamente os valores únicos presentes nos dados
    - **Valida: Requisito 9.4**

- [x] 3. Implementar Store Zustand
  - Criar `src/store/index.ts` com a interface `AtlasStore` completa: todos os slices de dados (`allMarkersData`, `currentFilteredData`, `deliveryStations`, `polygonsData`, `jurisdictionData`, `optimizationData`, `idealSupplyData`, `heatmapData`, `period`), slices de UI (`isLoading`, `loadingMessage`, `error`, `styleConfig`, `filterState`, `route`, `hcp`) e todas as actions
  - Criar `src/store/actions/dataActions.ts` com `loadAll`, `applyFilters`, `resetFilters` — toda action assíncrona envolvida em `try/catch` com `store.setError` e preservação do estado anterior
  - Criar `src/store/actions/mapActions.ts` com `setStyleConfig`, `setRoute`, `clearRoute`, `setError`
  - _Requisitos: 2.1, 2.2, 2.3, 2.4, 2.5_

  - [ ]* 3.1 Escrever testes de propriedade para o Store
    - **Propriedade 2: Resiliência de action com falha** — para qualquer action que lança exceção, o estado após a falha deve ser idêntico ao estado anterior
    - **Valida: Requisito 2.5**
    - **Propriedade 1: Isolamento de re-render por seletor** — atualizar uma propriedade do store deve causar re-render apenas nos componentes com seletor ativo para aquela propriedade
    - **Valida: Requisito 2.3**

- [x] 4. Implementar Web Worker e hook de integração
  - Criar `src/workers/data-worker.ts` migrando a lógica de `frontend/data-worker.js`, compatível com Vite (`new Worker(new URL('./data-worker.ts', import.meta.url))`)
  - Implementar protocolo de mensagens: `WorkerInMessage` (`filter`, `loadData`) e `WorkerOutMessage` (`filterResult`, `dataLoaded`, `error`)
  - Criar `src/hooks/useDataWorker.ts` que instancia o worker, escuta `postMessage` e chama as actions do store correspondentes; em caso de erro, chama `store.setError`
  - Criar `src/hooks/useDebounce.ts` para debounce genérico (usado no autocomplete de busca)
  - _Requisitos: 4.1, 4.2, 4.3, 4.4, 4.5_

  - [ ]* 4.1 Escrever testes de propriedade para o DataWorker
    - **Propriedade 5: Store atualizado após postMessage do worker** — após o worker enviar `{ action: 'filterResult', filtered }`, o valor de `store.currentFilteredData` deve ser igual ao array `filtered` recebido
    - **Valida: Requisito 4.2**

- [x] 5. Checkpoint — Verificar fundação
  - Garantir que todos os testes passam, o build de produção funciona e o store está tipado corretamente. Perguntar ao usuário se há dúvidas antes de prosseguir.

- [x] 6. Implementar utilitários de mapa e lógica de negócio
  - Criar `src/lib/colorUtils.ts` com `generateColorMap` e `getMarkerStyle` (migrado de `map-manager.js`)
  - Criar `src/lib/popupUtils.ts` com `getPopupContent` e helpers de popup de comparação e slot (migrado de `map-manager.js`)
  - Criar `src/lib/hcpUtils.ts` com lógica de clusters HCP e sugestões (migrado de `route-manager.js`)
  - Criar `src/lib/routeUtils.ts` com otimização de paradas e OSRM matrix (migrado de `route-manager.js`)
  - _Requisitos: 16.1, 16.4, 16.5_

  - [ ]* 6.1 Escrever testes de propriedade para utilitários
    - **Propriedade 9: Cores dos marcadores correspondem à estilização selecionada** — para qualquer campo de estilização e `currentFilteredData`, cada marcador deve ter a cor correspondente ao valor do campo no `colorMap`
    - **Valida: Requisito 10.2**

- [x] 7. Implementar hooks de responsividade
  - Criar `src/hooks/useBreakpoint.ts` usando `window.matchMedia` com listeners reativos, retornando `'mobile' | 'tablet' | 'notebook' | 'desktop'`
  - _Requisitos: 5.1, 6.1, 7.1, 8.1_

- [x] 8. Implementar componentes de layout
  - Criar `src/components/layout/Header.tsx` responsivo: compacto em mobile (logo + "ATLAS"), completo em tablet/desktop (logo + título + período)
  - Criar `src/components/ui/LoadingIndicator.tsx` exibido no header enquanto `isLoading` é verdadeiro
  - Criar `src/components/ui/ErrorToast.tsx` para mensagens não-bloqueantes no canto superior direito
  - Criar `src/components/ui/Spinner.tsx` para estados de carregamento inline
  - Criar `src/components/ui/FAB.tsx` com área de toque mínima de 44x44px
  - Criar `src/components/layout/BottomSheet.tsx` com drag gesture via pointer events, snap points e animação `transform: translateY()`
  - Criar `src/components/layout/Drawer.tsx` com overlay mode, animação `transform: translateX()`, largura configurável
  - Criar `src/components/layout/FloatingPanel.tsx` com cabeçalho clicável para colapsar/expandir, posicionado absolutamente sobre o mapa
  - Criar `src/components/layout/AppShell.tsx` que usa `useBreakpoint` para renderizar o layout correto (MobileLayout / TabletLayout / DesktopLayout)
  - _Requisitos: 5.2, 5.3, 5.4, 5.6, 5.7, 6.2, 6.3, 6.5, 7.1, 7.2, 8.1, 8.2, 14.4, 14.5_

  - [ ]* 8.1 Escrever testes de exemplo para layouts responsivos
    - Testar renderização de BottomSheet em mobile (matchMedia mockado para ≤767px)
    - Testar renderização de Drawer em tablet (768px–1023px)
    - Testar renderização de FloatingPanel em notebook/desktop (≥1024px)
    - _Requisitos: 5.1, 6.1, 7.1, 8.1_

- [x] 9. Implementar componente MapView e camadas do mapa
  - Criar `src/components/map/MapView.tsx` com `MapContainer` do react-leaflet usando `MAP_CONFIG` (centro, zoom, tile URL Google Maps com subdomains), ocupando 100% da viewport
  - Criar `src/components/map/PartnerMarkers.tsx` com `React.memo`, seletor `currentFilteredData` e `styleConfig`, usando `useMemo` para recalcular `colorMap`
  - Criar `src/components/map/StationMarkers.tsx` para delivery stations
  - Criar `src/components/map/PolygonLayer.tsx` para territórios (migrado de `polygon-manager.js`)
  - Criar `src/components/map/JurisdictionLayer.tsx` (migrado de `polygon-manager.js`)
  - Criar `src/components/map/OptimizationLayer.tsx` (migrado de `polygon-manager.js`)
  - Criar `src/components/map/HeatmapLayer.tsx`
  - Criar `src/components/map/RouteLayer.tsx` integrando `leaflet-routing-machine` (migrado de `route-manager.js`)
  - Criar `src/components/map/MapLegend.tsx` (migrado de `map-manager.js`)
  - Criar `src/components/map/popups/PartnerPopup.tsx`, `ComparisonPopup.tsx` e `SlotPopup.tsx` (migrado de `map-manager.js`)
  - _Requisitos: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8, 16.1, 16.2, 16.7_

  - [ ]* 9.1 Escrever testes de propriedade para camadas do mapa
    - **Propriedade 3: Instância do mapa preservada na filtragem** — após qualquer atualização de `currentFilteredData`, `map._leaflet_id` deve ser o mesmo antes e depois
    - **Valida: Requisito 3.3**
    - **Propriedade 4: Popup exibido para qualquer marcador clicado** — para qualquer `Partner` com coordenadas válidas, simular clique deve exibir popup com o nome do parceiro
    - **Valida: Requisito 3.5**

- [x] 10. Checkpoint — Verificar mapa funcional
  - Garantir que o mapa renderiza com todas as camadas, marcadores respondem a cliques e popups são exibidos corretamente. Perguntar ao usuário se há dúvidas antes de prosseguir.

- [x] 11. Implementar ControlPanel e abas de controle
  - Criar `src/components/controls/ControlPanel.tsx` como container das abas com navegação por tabs
  - Criar `src/components/controls/FiltersTab.tsx` com campos: Status (multi-select), Delivery Station (multi-select), Carteira ADE (multi-select), Delivery Initiatives (select), Jurisdiction Type (select); botões "Aplicar Filtros" e "Limpar Filtros"; autocomplete de busca por nome com debounce de 300ms
  - Criar `src/components/controls/StyleTab.tsx` com selects "Estilizar por" e "Detalhar por" (opções: Delivery Station, Status, Hub Delivery Initiatives, Supply Run, Carteira) e checkboxes para Exibir Raios, Exibir Áreas de Prospecção, Exibir Jurisdições, Exibir Camada de Otimização
  - Criar `src/components/controls/AreaAnalysisTab.tsx` com filtros de Estado e Decisão (Go/No Go/Todos), filtro fixo Status = Prospect, botão "Analisar Área" e exibição de estatísticas
  - Criar `src/components/controls/RoutesTab.tsx` com campos de origem/destino com autocomplete, lista de paradas intermediárias com add/reorder/remove, botões "Buscar Melhor Rota" e "Limpar Rota", botão condicional "Sugerir HCP Initiatives"
  - _Requisitos: 9.1, 9.2, 9.3, 9.4, 9.5, 10.1, 10.2, 10.3, 10.4, 10.5, 11.1, 11.2, 11.3, 12.1, 12.2, 12.3, 12.4, 12.5, 12.6, 16.3, 16.4_

  - [ ]* 11.1 Escrever testes de exemplo para ControlPanel
    - Testar presença de todos os campos de filtro no FiltersTab
    - Testar que "Aplicar Filtros" chama `store.applyFilters` com os valores corretos
    - Testar que "Limpar Filtros" chama `store.resetFilters`
    - Testar autocomplete com debounce de 300ms
    - _Requisitos: 9.1, 9.2, 9.3, 9.5_

- [x] 12. Implementar Dashboard Gerencial
  - Criar `src/components/dashboard/KpiCard.tsx` para card individual de KPI
  - Criar `src/components/dashboard/KpiGrid.tsx` com os KPIs: parceiros ativos, ADV Overall, DEA, EAD, DCR, FDDS, FTDS, HCP Host Ratio, SPR Médio; grid de 2 colunas em mobile, 3+ colunas em desktop
  - Criar `src/components/dashboard/ChartsSection.tsx` integrando `react-chartjs-2` para gráficos de tendências e distribuições (migrado de `management-dashboard.js`)
  - Criar `src/components/dashboard/StationsTable.tsx` com virtualização via TanStack Virtual quando linhas > 100, ordenação por coluna (migrado de `management-dashboard.js`)
  - Criar `src/components/dashboard/Dashboard.tsx` como container com barra de filtros (período, delivery station), estados de loading/erro/vazio, lazy loading via `React.lazy` e `Suspense`
  - _Requisitos: 13.1, 13.2, 13.3, 13.4, 13.5, 13.6, 13.7, 13.8, 15.2, 15.3, 16.6_

  - [ ]* 12.1 Escrever testes de propriedade para virtualização
    - **Propriedade 10: Virtualização ativa para listas grandes** — para qualquer lista com N > 100 itens, o número de elementos `<tr>` no DOM deve ser menor que N
    - **Valida: Requisito 15.2**

  - [ ]* 12.2 Escrever testes de exemplo para Dashboard
    - Testar renderização de KPI cards com dados de exemplo
    - Testar exibição de spinner durante carregamento
    - Testar mensagem informativa quando dados não disponíveis
    - _Requisitos: 13.2, 13.6, 13.7_

- [x] 13. Checkpoint — Verificar Dashboard e ControlPanel
  - Garantir que todos os testes passam, Dashboard renderiza KPIs e gráficos, filtros funcionam corretamente. Perguntar ao usuário se há dúvidas antes de prosseguir.

- [x] 14. Integrar App.tsx e conectar todos os componentes
  - Criar `src/App.tsx` integrando `AppShell`, `MapView`, `ControlPanel`, `Dashboard` e `useDataWorker`
  - Atualizar `src/main.tsx` para montar o App, registrar ServiceWorker e inicializar o store via `loadAll`
  - Conectar `useDataWorker` ao store para que `postMessage` do worker atualize `allMarkersData`, `polygonsData`, `jurisdictionData`, `optimizationData`, `heatmapData` e `period`
  - Garantir que `LoadingIndicator` no header reflete `store.isLoading` durante processamento do worker
  - Garantir que `ErrorToast` exibe `store.error` quando não nulo
  - Adicionar `ErrorBoundary` envolvendo `MapView` e `Dashboard`
  - _Requisitos: 2.1, 4.2, 4.3, 4.4, 14.5_

  - [ ]* 14.1 Escrever testes de integração de wiring
    - Testar que `loadAll` dispara o worker e atualiza o store com os dados carregados
    - Testar que erro no worker exibe `ErrorToast` sem bloquear a aplicação
    - _Requisitos: 4.2, 4.4_

- [x] 15. Aplicar otimizações de performance
  - Adicionar `React.memo` em `PartnerMarkers`, `StationMarkers`, `KpiCard` e `StationsTable`
  - Adicionar `useMemo` para `colorMap` em `PartnerMarkers` e para dados processados em `KpiGrid`
  - Adicionar `useCallback` em handlers de eventos nos componentes de controle
  - Confirmar lazy loading de `Dashboard` e módulos pesados via `React.lazy` + `Suspense`
  - _Requisitos: 15.1, 15.3, 15.4_

- [x] 16. Checkpoint Final — Garantir qualidade e completude
  - Garantir que todos os testes passam, build de produção funciona sem erros, todas as funcionalidades do ATLAS original estão preservadas. Perguntar ao usuário se há dúvidas antes de finalizar.

## Notas

- Tarefas marcadas com `*` são opcionais e podem ser puladas para um MVP mais rápido
- Cada tarefa referencia requisitos específicos para rastreabilidade
- Os checkpoints garantem validação incremental a cada fase
- Os testes de propriedade usam fast-check com mínimo de 100 iterações (`fc.configureGlobal({ numRuns: 100 })`)
- Os testes de exemplo usam Vitest + React Testing Library
- A linguagem de implementação é TypeScript com React
