# Requirements Document

## Introduction

Esta spec define um conjunto de quatro otimizações de alto impacto e baixo esforço no frontend React (Atlas), identificadas em auditoria de performance. As otimizações focam em eliminar re-renders caros, remounts desnecessários de camadas do mapa Leaflet, tabelas sem virtualização em listas grandes e recálculos de computações derivadas sem memoização.

Os quatro itens cobertos são:
1. `PolygonLayer` — evitar remount completo da camada Leaflet ao alterar filtros, substituindo `JSON.stringify(filterState)` como `key` por atualização imperativa (via ref) ou `useEffect` com dependências específicas, preservando a instância da camada.
2. Virtualização de `TerritoryTable` (em `Dashboard.tsx`) e `PartnersByBucketTable`, adotando o padrão já implementado em `StationsTable.tsx` com `@tanstack/react-virtual`.
3. `AreaAnalysisTab` — envolver computações derivadas (filtragens, agregações, estatísticas) com `useMemo` com dependências corretas, evitando recálculos quando o input relevante não muda.
4. `PartnerMarkers` — separar `i18n.language` da `key` dos markers, usando apenas identificador estável do parceiro como `key`; o texto internacionalizado deve atualizar reativamente no tooltip/popup sem recriar o marker.

O critério inviolável destas otimizações é **preservação de comportamento observável pelo usuário**: mesmos markers no mapa, mesmas linhas (visíveis e acessíveis por scroll) nas tabelas, mesma lógica de filtro e agregação, mesmos textos internacionalizados após troca de idioma. Toda mudança deve ser verificada por testes que comparam o comportamento das versões otimizada e não otimizada para inputs variados, combinando testes de render (React Testing Library) e property-based testing (fast-check) para funções puras de filtragem e agregação.

## Glossary

- **PolygonLayer**: Componente em `atlas-react/src/components/map/PolygonLayer.tsx` que renderiza a camada `GeoJSON` de polígonos territoriais sobre o mapa Leaflet.
- **PartnerMarkers**: Componente em `atlas-react/src/components/map/PartnerMarkers.tsx` que renderiza os markers circulares dos parceiros no mapa.
- **TerritoryTable**: Subcomponente interno de `atlas-react/src/components/dashboard/Dashboard.tsx` que renderiza a tabela de territórios.
- **PartnersByBucketTable**: Componente em `atlas-react/src/components/dashboard/PartnersByBucketTable.tsx` que renderiza a tabela de parceiros ativos agrupados por bucket.
- **StationsTable_Reference**: Componente em `atlas-react/src/components/dashboard/StationsTable.tsx`, referência de virtualização correta usando `useVirtualizer` de `@tanstack/react-virtual`.
- **AreaAnalysisTab**: Componente em `atlas-react/src/components/controls/AreaAnalysisTab.tsx` e suas funções puras de computação derivada (`getGlobalOverview`, `getFilteredStats`, `getStatsByState`, ordenação de leads, filtragem de oportunidades).
- **Filter_State**: Estado de filtros aplicados ao mapa (stations, buckets, status, cluster de prospecção) mantido no store e consumido por `PolygonLayer`.
- **Row_Virtualizer**: Instância de `useVirtualizer` do `@tanstack/react-virtual` configurada conforme o padrão de `StationsTable_Reference`, com `getScrollElement`, `estimateSize` e `enabled` controlado por `VIRTUALIZE_THRESHOLD`.
- **VIRTUALIZE_THRESHOLD**: Número mínimo de linhas a partir do qual a virtualização é ativada. Na referência (`StationsTable.tsx`), este valor é 100.
- **Optimized_Component**: Versão do componente (`PolygonLayer`, `PartnerMarkers`, `TerritoryTable`, `PartnersByBucketTable`, `AreaAnalysisTab`) após a aplicação da otimização descrita nesta spec.
- **Reference_Component**: Versão do componente imediatamente antes da aplicação da otimização em análise, usada como baseline de correctness.
- **Behavior_Equivalence**: Propriedade de que, para o mesmo input (props, estado do store, idioma ativo), `Optimized_Component` e `Reference_Component` produzem o mesmo output observável pelo usuário: mesmo conjunto de polígonos exibidos com as mesmas cores/estilo, mesmo conjunto de markers exibidos nas mesmas posições, mesmas linhas renderizadas nas tabelas (considerando o conjunto completo, independentemente de virtualização), e os mesmos valores numéricos/textuais nas estatísticas agregadas.
- **Stable_Marker_Key**: `key` de React usada nos markers de `PartnerMarkers` composta apenas de identificador estável do parceiro (`salesforce_id`) e independente de `i18n.language`.
- **Leaflet_Layer_Instance**: Instância viva da camada GeoJSON do Leaflet gerenciada por `PolygonLayer`; é preservada (não desmontada/remontada) entre mudanças de `Filter_State` na versão otimizada.

## Requirements

### Requirement 1: `PolygonLayer` preserva a instância da camada Leaflet ao alterar filtros

**User Story:** Como usuário do Atlas, eu quero que a camada de polígonos do mapa atualize suavemente ao mudar filtros, para que eu não veja flicker visual nem pague o custo de desmontar e remontar a camada a cada ajuste de filtro.

#### Acceptance Criteria

1. WHEN `Filter_State` muda (alteração em `selectedStations`, `selectedBuckets`, `prospectClusters`, `selectedBucket` ou `polygonColorField`), THE PolygonLayer SHALL atualizar os polígonos exibidos sem descartar a `Leaflet_Layer_Instance` previamente criada.
2. THE PolygonLayer SHALL NOT utilizar `JSON.stringify(Filter_State)` (nem concatenação equivalente de valores de filtro) como `key` da camada `GeoJSON`, para evitar remount completo da camada a cada mudança de filtro.
3. WHEN `Filter_State` muda, THE PolygonLayer SHALL recomputar o conjunto de features exibidas e aplicar o novo estilo (`StyleFunction`) sobre a `Leaflet_Layer_Instance` existente, via API imperativa do Leaflet (ex.: `clearLayers` + `addData`, ou `setStyle` conforme apropriado) ou via `useEffect` com dependências explícitas em cada campo relevante.
4. WHEN `Filter_State` muda, THE PolygonLayer SHALL exibir exatamente o mesmo conjunto de features que seria filtrado pela regra atual de `filteredData` (station match ∧ bucket match, ou regra de `heatmapActive`), para o mesmo estado do store (`Behavior_Equivalence`).
5. WHEN `polygonColorField` muda, THE PolygonLayer SHALL aplicar o mesmo estilo por feature que seria produzido pela `StyleFunction` original para o mesmo estado do store.
6. WHEN `showPolygons` passa a `false` e não há `heatmapActive`, THE PolygonLayer SHALL deixar de renderizar polígonos, mantendo `Behavior_Equivalence` com a versão de referência.
7. IF ocorrer um erro ao atualizar a camada imperativamente, THEN THE PolygonLayer SHALL registrar o erro no console e manter o último estado válido da camada, sem lançar exceção para o React que quebre a árvore de renderização.
8. THE PolygonLayer SHALL preservar o comportamento de `onEachFeature` (popup com DS, BDM, CTL, n_slots, attainment, accuracy) para cada feature exibida, com conteúdo idêntico ao do `Reference_Component` para a mesma feature.

### Requirement 2: Virtualização de `TerritoryTable` seguindo o padrão de `StationsTable_Reference`

**User Story:** Como usuário do dashboard, eu quero que a tabela de territórios renderize rapidamente mesmo com centenas ou milhares de linhas, para que a interação (scroll, ordenação, filtragem) permaneça fluida.

#### Acceptance Criteria

1. WHEN o número de linhas em `TerritoryTable` excede `VIRTUALIZE_THRESHOLD`, THE TerritoryTable SHALL renderizar somente as linhas visíveis na viewport (mais buffer do virtualizador) via `Row_Virtualizer` de `@tanstack/react-virtual`.
2. WHEN o número de linhas em `TerritoryTable` é menor ou igual a `VIRTUALIZE_THRESHOLD`, THE TerritoryTable SHALL renderizar todas as linhas diretamente, sem ativar o virtualizador, seguindo o mesmo padrão de `StationsTable_Reference`.
3. THE TerritoryTable SHALL configurar o `Row_Virtualizer` com `getScrollElement`, `estimateSize` e `enabled` análogos aos de `StationsTable_Reference`, usando um elemento scrollável dedicado.
4. WHEN o usuário rola a tabela virtualizada, THE TerritoryTable SHALL manter as linhas do cabeçalho fixas (sticky) e apresentar apenas as linhas de corpo correspondentes ao intervalo visível.
5. THE TerritoryTable SHALL preservar o conjunto completo de linhas logicamente presentes: para qualquer input `rows` e `sortState`, o conjunto de linhas acessíveis por scroll na versão virtualizada SHALL ser igual ao conjunto renderizado pela versão de referência (`Behavior_Equivalence`).
6. THE TerritoryTable SHALL preservar o comportamento de ordenação: ao clicar em uma coluna, a ordem das linhas exibidas SHALL ser a mesma produzida por `sortTerritories` com `(column, direction)` correspondentes.
7. THE TerritoryTable SHALL preservar as classes de status de `attainment` e `accuracy` (`STATUS_CLASS_MAP` aplicado sobre `getStatusClass`) para cada linha, idêntica à versão de referência.
8. WHEN `rows.length === 0`, THE TerritoryTable SHALL exibir a mensagem `dashboard.no_territory_found`, sem ativar o virtualizador.

### Requirement 3: Virtualização de `PartnersByBucketTable` seguindo o padrão de `StationsTable_Reference`

**User Story:** Como usuário do dashboard, eu quero que a tabela de parceiros ativos por bucket renderize rapidamente mesmo com muitos parceiros, para que a busca e a exportação permaneçam responsivas.

#### Acceptance Criteria

1. WHEN o número de linhas em `PartnersByBucketTable` (após filtragem por busca) excede `VIRTUALIZE_THRESHOLD`, THE PartnersByBucketTable SHALL renderizar somente as linhas visíveis na viewport via `Row_Virtualizer` de `@tanstack/react-virtual`.
2. WHEN o número de linhas em `PartnersByBucketTable` (após filtragem por busca) é menor ou igual a `VIRTUALIZE_THRESHOLD`, THE PartnersByBucketTable SHALL renderizar todas as linhas diretamente, sem ativar o virtualizador.
3. THE PartnersByBucketTable SHALL configurar o `Row_Virtualizer` com `getScrollElement`, `estimateSize` e `enabled` análogos aos de `StationsTable_Reference`.
4. WHEN o usuário altera o texto do campo de busca, THE PartnersByBucketTable SHALL aplicar o filtro sobre `rows` antes de calcular o conjunto virtualizado, preservando a lógica atual de filtragem (match case-insensitive em `name` e `store_id`).
5. THE PartnersByBucketTable SHALL preservar o conjunto completo de linhas logicamente presentes após filtragem por busca: para qualquer input `data`, `filters`, `reportData` e `search`, o conjunto de linhas acessíveis por scroll na versão virtualizada SHALL ser igual ao conjunto renderizado pela versão de referência (`Behavior_Equivalence`).
6. THE PartnersByBucketTable SHALL preservar a ordenação por `bucket_ade` (localeCompare com `numeric: true`) na versão virtualizada.
7. WHEN o usuário clica em exportar CSV, THE PartnersByBucketTable SHALL exportar exatamente o mesmo conjunto de linhas que a versão de referência exportaria para o mesmo `data`, `filters`, `reportData` e `search`, independentemente de a virtualização estar ativa ou não.
8. WHEN `filtered.length === 0`, THE PartnersByBucketTable SHALL exibir a mensagem `dashboard.no_territory_found` dentro da tabela, sem ativar o virtualizador.

### Requirement 4: Memoização de computações derivadas em `AreaAnalysisTab`

**User Story:** Como usuário da aba de análise de área, eu quero que estatísticas e listas recalculem somente quando seus inputs relevantes mudam, para que mudanças em outras partes do estado não causem travamentos por recomputação desnecessária.

#### Acceptance Criteria

1. WHEN um render de `AreaAnalysisTab` ocorre sem alteração dos inputs de uma computação derivada (ex.: `allMarkersData`, `selectedState`, `selectedDecision`, `search`), THE AreaAnalysisTab SHALL reutilizar o resultado memoizado anterior dessa computação, sem reexecutar a função pura correspondente.
2. THE AreaAnalysisTab SHALL envolver `getGlobalOverview(allMarkersData)` em `useMemo` com array de dependências exato `[allMarkersData]`.
3. THE AreaAnalysisTab SHALL envolver `getFilteredStats(filteredProspects)` (ou computação equivalente para `filtered`) em `useMemo` com array de dependências exato incluindo `allMarkersData`, `selectedState` e `selectedDecision`.
4. THE AreaAnalysisTab SHALL envolver `getStatsByState(filteredProspects)` em `useMemo` com array de dependências exato incluindo `allMarkersData`, `selectedState` e `selectedDecision`.
5. THE AreaAnalysisTab SHALL envolver a ordenação e filtragem de leads em `LeadsPanel` em `useMemo` com dependências `[leads, search]`, como já ocorre na versão de referência, e SHALL preservar esse padrão em eventuais extrações.
6. THE AreaAnalysisTab SHALL envolver a ordenação de `opportunities` em `CapOpportunityPanel` em `useMemo` com dependência `[allMarkersData]`, como já ocorre na versão de referência, e SHALL preservar esse padrão em eventuais extrações.
7. THE AreaAnalysisTab SHALL preservar o output: para o mesmo input de props/estado, os valores exibidos (contagens, taxas, listas ordenadas, linhas da tabela por estado) SHALL ser iguais aos da versão de referência (`Behavior_Equivalence`).
8. FOR ALL inputs válidos de `allMarkersData`, `selectedState` e `selectedDecision`, a chamada memoizada da computação derivada SHALL produzir o mesmo objeto/estrutura por igualdade estrutural que a chamada não memoizada.
9. IF as dependências de uma computação derivada não mudam entre dois renders consecutivos, THEN THE AreaAnalysisTab SHALL retornar a mesma referência (igualdade por `===`) para o resultado memoizado, permitindo propagação eficiente da memoização para filhos memoizados.

### Requirement 5: `PartnerMarkers` separa `i18n.language` da `key` dos markers

**User Story:** Como usuário do Atlas, eu quero que trocar o idioma da interface não recrie todos os markers do mapa, para que a troca de idioma seja instantânea e não perca estado visual (popup aberto, tooltip, foco).

#### Acceptance Criteria

1. THE PartnerMarkers SHALL usar como `key` de cada marker um identificador estável do parceiro (`salesforce_id`) isolado, sem concatenar `i18n.language` nem qualquer outro valor que mude com a troca de idioma (`Stable_Marker_Key`).
2. WHEN `i18n.language` muda, THE PartnerMarkers SHALL atualizar o conteúdo internacionalizado (popup, tooltip) do marker existente, sem desmontar nem recriar a instância do marker.
3. WHEN `i18n.language` muda, THE PartnerMarkers SHALL preservar os refs em `markerRefs` para cada `salesforce_id` estável, garantindo que listeners externos (ex.: `atlas:open-partner-popup`) continuem funcionando sem reattach.
4. WHEN `i18n.language` muda, THE PartnerMarkers SHALL exibir os mesmos textos traduzidos no popup e no tooltip que seriam produzidos pela versão de referência após a troca de idioma, para o mesmo parceiro (`Behavior_Equivalence` de textos).
5. WHEN `data` muda (conjunto de parceiros), THE PartnerMarkers SHALL criar/destruir markers apenas para os parceiros adicionados/removidos, sem recriar markers cujo `salesforce_id` permanece presente.
6. THE PartnerMarkers SHALL preservar o comportamento de `visibleData` para `whatIfModeActive` e `prospectActive`, exibindo o mesmo conjunto de parceiros que a versão de referência para o mesmo estado do store.
7. THE PartnerMarkers SHALL preservar o estilo visual por parceiro (`getMarkerStyle` com `primaryField`, `secondaryField`, `colorMaps`), idêntico ao da versão de referência.
8. THE PartnerMarkers SHALL preservar o comportamento de `showRadii`, renderizando o `Circle` de raio quando habilitado com os mesmos parâmetros (`center`, `radius`, `pathOptions`) da versão de referência.

### Requirement 6: Correctness properties e testes de regressão visual/funcional

**User Story:** Como engenheiro de frontend, eu quero testes automatizados que garantam que cada otimização preserva o comportamento observável, para que eu possa refatorar com confiança e detectar regressões rapidamente.

#### Acceptance Criteria

1. FOR ALL inputs gerados pelo property-based testing (fast-check) sobre `allMarkersData`, `selectedState` e `selectedDecision`, `getGlobalOverview`, `getFilteredStats` e `getStatsByState` otimizados SHALL retornar valores iguais por igualdade estrutural aos produzidos pelas versões de referência (round-trip de equivalência funcional).
2. FOR ALL inputs gerados pelo property-based testing sobre `data`, `filters`, `reportData` e `search`, o conjunto de linhas renderizáveis em `PartnersByBucketTable` otimizado (acessíveis via scroll na versão virtualizada) SHALL ser igual, como conjunto ordenado, ao conjunto renderizado pela versão de referência.
3. FOR ALL inputs gerados pelo property-based testing sobre `rows` e `sortState`, o conjunto de linhas renderizáveis em `TerritoryTable` otimizado SHALL ser igual, como conjunto ordenado, ao conjunto renderizado pela versão de referência.
4. WHEN `Filter_State` é mutado em qualquer combinação de `selectedStations`, `selectedBuckets`, `prospectClusters`, `selectedBucket`, `polygonColorField` ou `showPolygons`, THE PolygonLayer otimizado SHALL exibir o mesmo conjunto de features com os mesmos estilos que a versão de referência, verificado por teste de renderização (React Testing Library + mock de Leaflet ou snapshot de features + styles).
5. WHEN `i18n.language` é alternado entre os idiomas suportados, THE PartnerMarkers otimizado SHALL preservar as `key`s dos markers (nenhum marker é desmontado/recriado) e SHALL atualizar os textos internacionalizados, verificado por teste de renderização que observa a estabilidade de refs em `markerRefs`.
6. WHEN as dependências de uma computação memoizada em `AreaAnalysisTab` não mudam entre renders consecutivos, THE test SHALL verificar que o resultado retornado por `useMemo` é a mesma referência (`===`) do render anterior.
7. WHEN as dependências de uma computação memoizada em `AreaAnalysisTab` mudam entre renders consecutivos, THE test SHALL verificar que o resultado retornado é estruturalmente igual àquele produzido pela função pura correspondente executada diretamente sobre as novas dependências.
8. IF um teste de property-based testing encontra um input para o qual `Optimized_Component` e `Reference_Component` divergem, THEN THE test SHALL falhar reportando o input reduzido (shrink) para facilitar diagnóstico.
9. THE suite de testes SHALL cobrir, no mínimo, um teste de render (React Testing Library) por componente otimizado e um teste de propriedade (fast-check) por função pura de agregação/filtragem em `AreaAnalysisTab`.
