# Plano de Implementação: Atlas UX Improvements

## Visão Geral

Implementação incremental das sete melhorias de UX do ATLAS React. A ordem prioriza correções simples e independentes primeiro, depois novos componentes de UI, e por fim o dashboard renovado com sua lib de suporte. Cada etapa integra o que foi construído anteriormente.

**Princípio:** reutilizar funções existentes (`routeUtils.ts`, `popupUtils.ts`, `colorUtils.ts`, `management-dashboard.js`). Não reescrever lógica já implementada.

**Instalação necessária antes de iniciar:**
```
npm install leaflet-routing-machine @types/leaflet-routing-machine
```
(executar em `atlas-react/`)

---

## Tarefas

- [x] 1. Correções simples e independentes
  - [x] 1.1 Remover controles de zoom padrão do Leaflet em `MapView.tsx`
    - Adicionar `zoomControl={false}` ao `MapContainer`
    - Verificar que scroll, pinça e duplo clique continuam funcionando
    - _Requisitos: 6.1, 6.2, 6.3_

  - [x] 1.2 Smoke test: MapView renderiza sem controles de zoom
    - Verificar que os botões +/- não estão presentes no DOM após renderização
    - _Requisitos: 6.1, 6.3_

  - [x] 1.3 Corrigir FloatingPanel do ControlPanel no desktop em `AppShell.tsx`
    - Garantir que o `FloatingPanel` com `ControlPanel` está sempre montado no `DesktopLayout`, independente de qualquer estado de carregamento
    - Verificar se há renderização condicional baseada em `isLoading` que desmonta o painel e removê-la
    - _Requisitos: 5.1, 5.2, 5.3, 5.4_

  - [x] 1.4 Teste unitário: FloatingPanel permanece montado após transição isLoading
    - Simular transição `isLoading: true → false` no `DesktopLayout`
    - Verificar que o `FloatingPanel` permanece no DOM após a transição
    - _Requisitos: 5.1, 5.3_

  - [x] 1.5 Substituir `RouteLayer.tsx` por implementação com `leaflet-routing-machine`
    - Remover a `Polyline` atual
    - Implementar `useEffect` com `L.Routing.control` conforme design
    - Reutilizar `optimizeStops` de `routeUtils.ts` para ordenar paradas intermediárias
    - Configurar `lineOptions`, `createMarker`, `router` (OSRM) e handler de `routingerror`
    - Implementar cleanup no retorno do `useEffect` chamando `map.removeControl()`
    - _Requisitos: 7.1, 7.2, 7.3, 7.4, 7.5, 7.6, 7.7, 7.8, 7.9_

  - [x] 1.6 Teste unitário: ciclo de vida do RouteLayer
    - Mock de `L.Routing.control` e `useMap()`
    - Verificar que `addTo(map)` é chamado quando `route.length >= 2`
    - Verificar que `map.removeControl()` é chamado no cleanup e quando `route` é esvaziado
    - Verificar que `routingerror` chama `store.setError` com mensagem descritiva
    - _Requisitos: 7.2, 7.6, 7.7, 7.9_

  - [x] 1.7 Escrever teste de propriedade para `optimizeStops` (Propriedade 7)
    - **Propriedade 7: optimizeStops produz rota de distância mínima**
    - **Valida: Requisito 7.3**
    - Para qualquer origem, destino e até 8 paradas intermediárias, a distância total da rota retornada deve ser ≤ à distância de qualquer outra permutação das mesmas paradas
    - Arquivo: `src/lib/routeUtils.test.ts` (criar se não existir)

- [x] 2. Checkpoint — Correções simples
  - Garantir que todos os testes passam. Verificar manualmente no browser: zoom removido, ControlPanel visível no desktop após carregamento, rota exibida como trajeto real. Perguntar ao usuário se há dúvidas antes de continuar.

- [x] 3. Novos componentes de UI: DashboardToggle e ControlsToggle
  - [x] 3.1 Criar `DashboardToggle.tsx` em `src/components/ui/`
    - Semi-círculo fixo na borda direita, verticalmente centralizado
    - CSS: `position: fixed; right: 0; top: 50%; transform: translateY(-50%); width: 40px; height: 80px; border-radius: 40px 0 0 40px`
    - Props: `isOpen: boolean; onClick: () => void`
    - Ícone de gráfico de barras; mudar aparência visual quando `isOpen === true`
    - Área de toque mínima de 44px de altura
    - _Requisitos: 3.1, 3.2, 3.3, 3.6, 3.7, 3.8_

  - [x] 3.2 Criar `ControlsToggle.tsx` em `src/components/ui/`
    - Semi-círculo fixo na borda esquerda, verticalmente centralizado
    - CSS: `position: fixed; left: 0; top: 50%; transform: translateY(-50%); width: 40px; height: 80px; border-radius: 0 40px 40px 0`
    - Props: `isOpen: boolean; onClick: () => void`
    - Ícone de hamburguer; mudar aparência visual quando `isOpen === true`
    - Área de toque mínima de 44px de altura
    - _Requisitos: 4.1, 4.2, 4.3, 4.7, 4.8_

  - [x] 3.3 Integrar `DashboardToggle` e `ControlsToggle` no `AppShell.tsx`
    - Substituir os FABs de dashboard por `DashboardToggle` em todos os layouts (Mobile, Tablet, Desktop)
    - Substituir os FABs de controles por `ControlsToggle` em `MobileLayout` e `TabletLayout`
    - Ocultar `ControlsToggle` no `DesktopLayout` (requisito 4.9)
    - Conectar `onClick` e `isOpen` ao estado existente de cada layout
    - Adicionar animação de transição de 300ms no painel do Dashboard (slide da direita)
    - _Requisitos: 3.4, 3.5, 3.6, 4.4, 4.5, 4.6, 4.9_

  - [x] 3.4 Teste unitário: DashboardToggle e ControlsToggle
    - Verificar toggle de estado aberto/fechado ao clicar
    - Verificar que `ControlsToggle` não está presente no DOM no breakpoint desktop
    - Verificar classes CSS corretas para estado ativo/inativo
    - _Requisitos: 3.4, 3.5, 3.8, 4.4, 4.6, 4.8, 4.9_

- [x] 4. Novo componente: SearchBar
  - [x] 4.1 Criar `SearchBar.tsx` em `src/components/map/`
    - Componente overlay renderizado fora do `MapContainer` (não é filho do Leaflet)
    - Sub-componente interno `MapFlyTo` (filho do `MapContainer`) que recebe coordenadas via ref/callback e chama `useMap().flyTo()`
    - Estado: `query`, `suggestions`, `error`, `isOpen`
    - Reutilizar `useDebounce(query, 300)` do hook existente
    - Filtragem de parceiros: `partners.filter(p => p.name.toLowerCase().includes(debouncedQuery.toLowerCase()))` (mínimo 2 caracteres)
    - Geocodificação Nominatim para busca por endereço quando Enter é pressionado sem match de parceiro
    - Exibir mensagem de erro inline quando geocodificação não retorna resultado
    - Fechar autocomplete ao pressionar Escape
    - _Requisitos: 1.1, 1.4, 1.5, 1.6, 1.7, 1.8, 1.10_

  - [x] 4.2 Aplicar posicionamento responsivo ao `SearchBar`
    - Desktop: `top: 16px; left: 16px; width: clamp(280px, 30vw, 480px)`
    - Mobile/Tablet: `top: 16px; left: 50%; transform: translateX(-50%); maxWidth: 90vw`
    - z-index superior ao mapa e inferior aos modais
    - _Requisitos: 1.2, 1.3, 1.8, 1.9_

  - [x] 4.3 Integrar `SearchBar` no `AppShell.tsx`
    - Renderizar `SearchBar` no wrapper `div` do mapa em todos os layouts (acima do `MapView`)
    - Passar `partners` do store via `useStore`
    - _Requisitos: 1.1_

  - [x] 4.4 Teste unitário: SearchBar
    - Mock de `useMap()`, verificar que `flyTo` é chamado com coordenadas corretas ao selecionar sugestão
    - Verificar que autocomplete exibe apenas parceiros cujo nome contém a query
    - Verificar que mensagem de erro é exibida quando geocodificação retorna vazio
    - Verificar que Escape fecha o autocomplete
    - _Requisitos: 1.4, 1.5, 1.6, 1.7, 1.10_

  - [x] 4.5 Escrever teste de propriedade para autocomplete (Propriedade 6)
    - **Propriedade 6: Autocomplete retorna subconjunto válido**
    - **Valida: Requisito 1.4**
    - Para qualquer lista de parceiros e query ≥ 2 caracteres, todos os resultados devem conter a query (case-insensitive) e nenhum parceiro que não satisfaça o critério deve aparecer
    - Arquivo: `src/components/map/SearchBar.test.tsx` (criar)

- [x] 5. Checkpoint — Novos componentes de UI
  - Garantir que todos os testes passam. Verificar manualmente: semi-círculos visíveis e funcionais, SearchBar posicionada corretamente em cada breakpoint, busca por parceiro e por endereço funcionando. Perguntar ao usuário se há dúvidas antes de continuar.

- [x] 6. Dashboard renovado — lib/reportUtils.ts
  - [x] 6.1 Criar `src/lib/reportUtils.ts` portando funções puras de `management-dashboard.js`
    - Definir interfaces TypeScript: `TerritoryData`, `BaseData`, `ReportData`, `DashboardFilters`, `KPISummary`, `TerritoryRow`, `ChartData`
    - Portar `parse(text: string): ReportData` — sem alterar a lógica de regex
    - Portar `serialize(data: ReportData): string` — necessário para teste de round-trip
    - Portar `filterBases(reportData: ReportData, filters: DashboardFilters): BaseData[]`
    - Portar `computeKPIs(filteredBases: BaseData[]): KPISummary`
    - Portar `sortTerritories(territories: TerritoryRow[], column: string, direction: 'asc' | 'desc'): TerritoryRow[]`
    - Portar `getStatusClass(value: number, thresholds: { green: number; yellow: number }): 'status-green' | 'status-yellow' | 'status-red'`
    - Portar `getChartDataForBase(filteredBases: BaseData[], selectedBase: string): ChartData`
    - Tratar casos de borda: `parse` com texto inválido retorna `{ generatedAt: null, bases: [] }`; `filterBases` com `reportData` nulo retorna `[]`; `computeKPIs` com array vazio retorna KPIs zerados sem divisão por zero
    - _Requisitos: 2.3, 2.4, 2.5, 2.6, 2.7, 2.8, 2.9, 2.10, 2.11, 2.12_

  - [x] 6.2 Escrever teste de propriedade: Propriedade 1 — filterBases preserva consistência de cascata
    - **Propriedade 1: Filtragem em cascata preserva consistência**
    - **Valida: Requisitos 2.4, 2.5, 2.6**
    - Para qualquer `ReportData` e combinação de filtros, `filterBases` retorna apenas bases/territórios que satisfazem todos os filtros ativos
    - Arquivo: `src/lib/reportUtils.test.ts`

  - [x] 6.3 Escrever teste de propriedade: Propriedade 2 — computeKPIs é consistente com os dados de entrada
    - **Propriedade 2: computeKPIs é consistente com os dados de entrada**
    - **Valida: Requisitos 2.7, 2.8**
    - Para qualquer array não-vazio de `BaseData`: `totalBases === bases.length`, `totalTerritories === soma dos territories.length`, `totalDailyDemand === soma dos dailyDemand`, `avgAttainment ∈ [0, 1]`
    - Arquivo: `src/lib/reportUtils.test.ts`

  - [x] 6.4 Escrever teste de propriedade: Propriedade 3 — getChartDataForBase ordena attainment de forma decrescente
    - **Propriedade 3: getChartDataForBase ordena attainment de forma decrescente**
    - **Valida: Requisito 2.9**
    - Para qualquer array de `BaseData`, `getChartDataForBase(bases, 'all').attainmentByBase.data` deve ser não-crescente
    - Arquivo: `src/lib/reportUtils.test.ts`

  - [x] 6.5 Escrever teste de propriedade: Propriedade 4 — sortTerritories produz array ordenado
    - **Propriedade 4: sortTerritories produz array ordenado**
    - **Valida: Requisito 2.11**
    - Para qualquer array de `TerritoryRow` e coluna numérica válida, `sortTerritories(rows, col, 'asc')` produz array não-decrescente e `'desc'` produz não-crescente
    - Arquivo: `src/lib/reportUtils.test.ts`

  - [x] 6.6 Escrever teste de propriedade: Propriedade 5 — getStatusClass respeita os thresholds
    - **Propriedade 5: getStatusClass respeita os thresholds**
    - **Valida: Requisito 2.12**
    - Para qualquer `v ∈ [0, 1]` e thresholds `{ green, yellow }` com `green > yellow >= 0`: resultado correto para cada faixa
    - Arquivo: `src/lib/reportUtils.test.ts`

- [x] 7. Dashboard renovado — componentes React
  - [x] 7.1 Criar `FilterCascade.tsx` em `src/components/dashboard/`
    - Props: `reportData: ReportData; filters: DashboardFilters; onFilterChange: (filters: DashboardFilters) => void`
    - Calcular opções disponíveis para cada nível usando a lógica de `_applyFilterCascade` do módulo original (portada para React puro, sem DOM direto)
    - Quatro `<select>` na ordem: BDM → Base → CTL → Território
    - Resetar filtros dependentes ao mudar um filtro pai
    - Desabilitar controles enquanto `isLoadingReport === true`
    - _Requisitos: 2.3, 2.4, 2.5, 2.6, 2.13_

  - [x] 7.2 Substituir `Dashboard.tsx` pela implementação renovada
    - Fetch de `relatorio_executivo.json` no `useEffect` na primeira montagem
    - Estados: `reportData`, `isLoadingReport`, `reportError`, `filters`, `sortState`
    - Exibir spinner durante carregamento; mensagem de erro + botão "Tentar novamente" em caso de falha
    - Renderizar `FilterCascade` passando `reportData`, `filters` e `onFilterChange`
    - Calcular `filteredBases = filterBases(reportData, filters)` e `kpis = computeKPIs(filteredBases)` via `useMemo`
    - Renderizar KPI cards com os 8 indicadores de `KPISummary`
    - Renderizar dois gráficos via `react-chartjs-2` usando `getChartDataForBase`
    - Renderizar tabela de territórios com `sortTerritories` e colunas clicáveis para ordenação
    - Aplicar `getStatusClass` nas células de Attainment e Acuracidade
    - Preservar estado de filtros entre fechamentos (componente oculto via CSS, não desmontado)
    - _Requisitos: 2.1, 2.2, 2.3, 2.7, 2.8, 2.9, 2.10, 2.11, 2.12, 2.13, 2.14_

  - [x] 7.3 Teste unitário: Dashboard.tsx
    - Mock de `fetch`, verificar estados de loading/erro/sucesso
    - Verificar que spinner é exibido durante carregamento
    - Verificar que mensagem de erro e botão "Tentar novamente" aparecem em caso de falha
    - Verificar que KPI cards são renderizados com valores corretos após fetch bem-sucedido
    - _Requisitos: 2.1, 2.2, 2.7, 2.13_

- [x] 8. Integração final e checkpoint
  - [x] 8.1 Verificar integração completa no `AppShell.tsx`
    - Confirmar que `SearchBar` está presente em todos os layouts acima do `MapView`
    - Confirmar que `DashboardToggle` substitui todos os FABs de dashboard
    - Confirmar que `ControlsToggle` substitui os FABs de controles em mobile e tablet
    - Confirmar que `ControlsToggle` está ausente no layout desktop
    - Confirmar que o Dashboard renovado é carregado via `React.lazy` e exibido ao abrir o painel
    - _Requisitos: 1.1, 3.6, 4.9_

  - [x] 8.2 Smoke tests finais
    - `DashboardToggle` e `ControlsToggle` presentes no DOM com classes CSS corretas
    - `SearchBar` renderizado fora do `ControlPanel` e fora do `MapContainer`
    - `MapView` renderiza com `zoomControl: false`
    - _Requisitos: 1.1, 3.1, 4.1, 6.1_

- [x] 9. Checkpoint final — Garantir que todos os testes passam
  - Executar suite completa de testes. Perguntar ao usuário se há dúvidas ou ajustes antes de encerrar.

---

## Notas

- Tarefas marcadas com `*` são opcionais e podem ser puladas para um MVP mais rápido
- Cada tarefa referencia os requisitos específicos para rastreabilidade
- Os testes de propriedade usam `fast-check` (já instalado como `devDependency`)
- Arquivo de testes das funções puras: `src/lib/reportUtils.test.ts`
- O Dashboard deve ser ocultado via CSS (não desmontado) para preservar estado de filtros entre sessões (requisito 2.14)
