# Implementation Plan: prospect-ux-redesign

## Overview

Implementação incremental do redesign da feature "Prospectar" no atlas-react. As tarefas seguem a ordem de dependência: tipos → store → lógica pura → componentes de mapa → componentes de controle → integração final.

## Tasks

- [x] 1. Estender tipos e store com slice prospectState
  - [x] 1.1 Adicionar `ProspectCluster`, `ProspectState` em `store/types.ts` e estender `ProspectCompany` com `isMatch`, `contactada`, `territory_id`
    - Adicionar interface `ProspectCluster` com campos `centroid`, `count`, `match_count`, `priority`, `intensity`, `company_indices`
    - Adicionar interface `ProspectState` com campos `companies`, `clusters`, `isLoading`, `error`, `selectedStation`, `selectedBucket`
    - Adicionar campos `isMatch: boolean | null`, `contactada: boolean`, `territory_id?: string` à interface `ProspectCompany` existente
    - _Requirements: 6.1_

  - [x] 1.2 Adicionar slice `prospectState` em `store/index.ts` com actions `setCompanies`, `setClusters`, `setProspectLoading`, `setProspectError`, `clearProspect`
    - `setCompanies(companies)` atualiza `prospectState.companies`
    - `clearProspect()` reseta `companies: []`, `clusters: []`, `selectedStation: null`, `selectedBucket: null`
    - Expor `prospectState` no tipo `AtlasStore`
    - _Requirements: 6.1, 6.2, 6.3, 6.4_

  - [x] 1.3 Escrever testes de propriedade para o store (P4, P5, P14)
    - Criar `atlas-react/src/store/prospectStore.test.ts`
    - **Property 4: Round-trip de armazenamento** — `setCompanies(list)` → `prospectState.companies` igual a `list`
    - **Validates: Requirements 2.3, 6.2**
    - **Property 5: Limpeza em nova busca** — segunda chamada a `setCompanies` substitui completamente a primeira
    - **Validates: Requirements 2.6**
    - **Property 14: Limpeza total do prospectState** — `clearProspect()` zera companies, clusters, selectedStation, selectedBucket
    - **Validates: Requirements 6.4**

- [x] 2. Implementar algoritmo K-means++ e utilitários de prospecção
  - [x] 2.1 Criar `atlas-react/src/lib/kmeansUtils.ts` com `kmeansCluster` e `getLeadKey`
    - Implementar K-means++ com inicialização ponderada por distância
    - Iterar até convergência (máx 100 iterações, delta < 1e-6)
    - Se `n < k`, usar `k = n` (um cluster por empresa com coordenadas)
    - Calcular `match_count`, `priority` (1-based, maior `count + match_count` = prioridade 1) e `intensity` (`priority 1 → 1.0`, demais → `1.0 - (priority - 1) / k`)
    - Implementar `getLeadKey(company)`: retorna `google_maps_link` se não nulo e diferente de `'N/A'`, senão `"${nome}|${endereco}"`
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 3.14_

  - [x] 2.2 Escrever testes de propriedade para kmeansUtils (P10, P12, P13)
    - Criar `atlas-react/src/lib/kmeansUtils.test.ts`
    - **Property 10: lead_key correto** — `getLeadKey` retorna `google_maps_link` quando válido, senão `"nome|endereco"`
    - **Validates: Requirements 3.14, 3.16**
    - **Property 12: K-means produz min(n,4) clusters** — para qualquer lista com `n` empresas com coordenadas, resultado tem `min(n,4)` clusters com `count > 0`
    - **Validates: Requirements 4.1, 4.2**
    - **Property 13: Invariantes dos clusters** — soma de `count` = n válidos; `match_count <= count`; cluster `priority === 1` tem `intensity === 1.0`; intensidades decrescentes por prioridade
    - **Validates: Requirements 4.3, 4.4, 4.5**

- [x] 3. Implementar HeatmapLayer com leaflet.heat
  - [x] 3.1 Modificar `atlas-react/src/components/map/HeatmapLayer.tsx` para implementar `leaflet.heat` via `useEffect`
    - Instalar `leaflet.heat` e `@types/leaflet.heat` se necessário (verificar package.json)
    - Ler `prospectState.clusters` do store
    - Usar `useMap()` do react-leaflet para obter instância do mapa
    - Criar `L.heatLayer` com pontos `[centroid.lat, centroid.lon, intensity]` para cada cluster
    - Detectar suporte a WebGL: `radius=40, blur=25` com WebGL; `radius=25, blur=15` sem WebGL
    - Limpar layer no cleanup do `useEffect`
    - Não renderizar quando `clusters` está vazio
    - _Requirements: 5.1, 5.3, 5.5, 5.6, 6.3_

- [x] 4. Modificar PolygonLayer para filtrar por carteira quando heatmap ativo
  - [x] 4.1 Modificar `atlas-react/src/components/map/PolygonLayer.tsx` para ler `prospectState.selectedBucket` do store
    - Quando `prospectState.clusters` não está vazio (heatmap ativo), filtrar features para exibir apenas o polígono cujo `bucket_ade` ou `territory_id` corresponde a `prospectState.selectedBucket`
    - Quando `prospectState.clusters` está vazio, manter comportamento atual (filtro por `filterState`)
    - _Requirements: 5.3, 5.4_

- [x] 5. Implementar ProspectMarkers (alfinetes imperativos)
  - [x] 5.1 Criar `atlas-react/src/components/map/ProspectMarkers.tsx`
    - Usar `useMap()` e manter `Map<string, L.Marker>` em `useRef`
    - Receber `pinnedKeys: Set<string>` e `companies: ProspectCompany[]`
    - Quando uma chave entra em `pinnedKeys`: criar `L.marker` com popup (nome, endereço, telefone quando disponível) e centralizar mapa com zoom mínimo 15
    - Quando uma chave sai de `pinnedKeys`: remover o marcador correspondente
    - Limpar todos os marcadores no unmount
    - _Requirements: 3.9, 3.10, 3.11_

  - [x] 5.2 Escrever teste de propriedade para ProspectMarkers (P9)
    - Criar `atlas-react/src/components/map/ProspectMarkers.test.tsx`
    - **Property 9: Toggle de alfinete é round-trip** — fixar e desfixar uma empresa resulta em nenhum marcador ativo para ela
    - **Validates: Requirements 3.10**

- [x] 6. Implementar hook useGeolocation
  - [x] 6.1 Criar `atlas-react/src/hooks/useGeolocation.ts`
    - Retornar `{ position, isTracking, error, startTracking, stopTracking }`
    - `startTracking()` chama `navigator.geolocation.watchPosition` e armazena o `watchId`
    - `stopTracking()` chama `navigator.geolocation.clearWatch(watchId)` e limpa posição
    - Tratar erros: `PERMISSION_DENIED`, `POSITION_UNAVAILABLE`, `TIMEOUT` com mensagens em português
    - Limpar watch no unmount
    - _Requirements: 7.2, 7.3, 7.4, 7.5, 7.6_

  - [x] 6.2 Escrever teste de propriedade para useGeolocation (P15)
    - Criar `atlas-react/src/hooks/useGeolocation.test.ts`
    - **Property 15: Marcador reflete posição atual** — para qualquer sequência de posições emitidas pelo mock de `watchPosition`, o hook deve expor sempre a posição mais recente
    - **Validates: Requirements 7.4**

- [x] 7. Checkpoint — Garantir que todos os testes passam até aqui
  - Garantir que todos os testes passam, perguntar ao usuário se houver dúvidas.

- [x] 8. Implementar ResultPanel
  - [x] 8.1 Criar `atlas-react/src/components/controls/ResultPanel.tsx`
    - Aceitar props: `companies`, `selectedStation`, `selectedBucket`, `onClose`
    - Em desktop/tablet: renderizar via `createPortal(document.body)` como painel lateral fixo à esquerda (padrão `AreaAnalysisTab`)
    - Em mobile: renderizar inline (sem portal)
    - Cabeçalho: nome da DS, nome da Carteira, total de empresas, contagem de contactadas
    - Card por empresa: nome, endereço, tipo, telefone (quando disponível), link Google Maps (quando não `'N/A'`), botão alfinete (quando `lat != null && lon != null`), controle "Marcar como contactada"
    - Botão alfinete: opacidade total quando fixado, reduzida quando não fixado
    - Controle "Marcar como contactada": chamar `POST /api/empresas/contactada` com `action: 'add'` ou `'remove'`; atualização otimista do estado local; reverter em caso de falha (com `console.warn`)
    - Botão fechar: chamar `onClose`, limpar heatmap e alfinetes
    - Em mobile: exibir botão "Minha localização" usando `useGeolocation`
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8, 3.9, 3.10, 3.11, 3.12, 3.13, 3.14, 3.15, 3.16, 3.17, 7.1, 7.2, 7.3, 7.5, 7.7, 7.8_

  - [x] 8.2 Escrever testes de propriedade para ResultPanel (P6, P7, P8, P11)
    - Criar `atlas-react/src/components/controls/ResultPanel.test.tsx`
    - **Property 6: Contagem de empresas no cabeçalho** — total exibido igual a `companies.length`
    - **Validates: Requirements 3.2**
    - **Property 7: Campos obrigatórios no card** — nome, endereço e tipo sempre presentes; telefone presente quando não nulo; link presente quando não nulo e diferente de `'N/A'`
    - **Validates: Requirements 3.3**
    - **Property 8: Botão alfinete sse coordenadas válidas** — botão presente sse `lat != null && lon != null`
    - **Validates: Requirements 3.8**
    - **Property 11: Contagem de contactadas atualizada** — contagem no cabeçalho igual ao número de empresas com `contactada === true`
    - **Validates: Requirements 3.17**

- [x] 9. Implementar ProspectTab
  - [x] 9.1 Criar `atlas-react/src/components/controls/ProspectTab.tsx`
    - Seletor de Delivery Station: todas as estações únicas de `allMarkersData`
    - Seletor de Carteira: cascateado pela DS selecionada (apenas `bucket_ade` dos parceiros da DS escolhida); quando DS é `null`, exibir todas
    - Ao trocar DS: limpar seleção de Carteira
    - Botão "Buscar Empresas": habilitado apenas quando DS e Carteira estão selecionados
    - Ao clicar: setar `isLoading`, chamar `POST ${API_BASE_URL}/api/empresas` com DS e Carteira, despachar `setCompanies` no store, executar `kmeansCluster` e despachar `setClusters`
    - Em caso de erro HTTP: exibir mensagem descritiva; em falha de rede: "Erro de conexão. Verifique sua internet e tente novamente."
    - Em lista vazia: exibir "Nenhuma empresa encontrada para esta carteira." no ResultPanel
    - Gerenciar `pinnedKeys: Set<string>` localmente para passar ao `ProspectMarkers`
    - Renderizar `ResultPanel` quando há resultados (portal em desktop, inline em mobile)
    - Renderizar `ProspectMarkers` quando há alfinetes ativos
    - _Requirements: 1.4, 1.5, 1.6, 1.7, 1.8, 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 4.1, 4.2, 5.2_

  - [x] 9.2 Escrever testes de propriedade para ProspectTab (P1, P2, P3)
    - Criar `atlas-react/src/components/controls/ProspectTab.test.tsx`
    - **Property 1: Cascateamento de carteiras por DS** — para qualquer `selectedStation`, as carteiras exibidas são exatamente os `bucket_ade` únicos dos parceiros daquela DS
    - **Validates: Requirements 1.5, 1.6**
    - **Property 2: Limpeza de carteira ao trocar DS** — ao trocar de DS1 para DS2, a carteira selecionada é `null` independente do estado anterior
    - **Validates: Requirements 1.7**
    - **Property 3: Estado do botão Buscar** — botão habilitado sse `selectedStation != null && selectedBucket != null`
    - **Validates: Requirements 1.8**

- [x] 10. Adicionar aba "Prospectar" ao ControlPanel
  - [x] 10.1 Modificar `atlas-react/src/components/controls/ControlPanel.tsx` para incluir a aba "Prospectar"
    - Adicionar `'prospect'` ao tipo `TabId` e ao array `TABS` após "Rotas"
    - Importar e renderizar `ProspectTab` no painel de conteúdo correspondente
    - Manter todos os painéis sempre montados (padrão existente `hidden={activeTab !== ...}`)
    - _Requirements: 1.1, 1.2, 1.3_

- [x] 11. Checkpoint final — Garantir que todos os testes passam
  - Garantir que todos os testes passam, perguntar ao usuário se houver dúvidas.

## Notes

- Tarefas marcadas com `*` são opcionais e podem ser puladas para um MVP mais rápido
- Cada tarefa referencia requisitos específicos para rastreabilidade
- Os testes de propriedade usam **fast-check** (já presente em `devDependencies`)
- Os testes de exemplo usam **Vitest + React Testing Library** (já configurados)
- `ProspectMarkers` e `UserLocationMarker` são componentes imperativos Leaflet — não usam JSX de react-leaflet
- O padrão de portal para painel lateral segue exatamente o `AreaAnalysisTab` existente
