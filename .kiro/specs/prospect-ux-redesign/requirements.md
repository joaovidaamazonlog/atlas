# Requirements Document

## Introduction

Redesign de UX da feature "Prospectar" (Find Business Nearby) do atlas-react. A feature atual busca empresas via API (Receita Federal + Google Maps) e exibe marcadores individuais no mapa. O redesign muda o ponto de entrada (nova aba "Prospectar" no ControlPanel com filtros cascateados DS → Carteira), substitui os marcadores individuais por clusters K-means visualizados como heatmap, e adiciona um painel lateral de resultados similar ao AreaAnalysisTab existente.

## Glossary

- **ControlPanel**: Componente `ControlPanel.tsx` — container principal com navegação por abas de controle do mapa.
- **ProspectTab**: Nova aba "Prospectar" a ser adicionada ao ControlPanel.
- **FiltersTab**: Aba de filtros existente com seleção de Status, Delivery Station, Carteira ADE, Initiatives e Jurisdiction.
- **AreaAnalysisTab**: Aba de análise de área existente — referência de padrão visual para o painel lateral de resultados.
- **Delivery_Station**: Unidade de distribuição Amazon. Campo `delivery_station` no modelo `Partner`.
- **Carteira**: Agrupamento de parceiros por território. Campo `bucket_ade` no modelo `Partner`.
- **ProspectCompany**: Empresa retornada pela API de prospecção. Interface `ProspectCompany` já definida em `store/types.ts`.
- **Prospect_API**: API de prospecção em `API_BASE_URL` (`https://api-cnpj-br.vercel.app`) que retorna empresas próximas a uma carteira.
- **ResultPanel**: Painel lateral fixo que exibe a lista de empresas retornadas pela Prospect_API.
- **K-means_Cluster**: Agrupamento geográfico de empresas prospectadas em 4 subgrupos por carteira, calculado via algoritmo K-means no frontend.
- **ProspectHeatmap**: Camada de heatmap no mapa que representa a densidade e prioridade dos K-means_Clusters.
- **HeatmapLayer**: Componente `HeatmapLayer.tsx` — camada de heatmap no mapa (atualmente placeholder).
- **PolygonLayer**: Componente `PolygonLayer.tsx` — camada de polígonos de território no mapa.
- **PartnerMarkers**: Componente `PartnerMarkers.tsx` — camada de marcadores individuais de parceiros no mapa.

## Requirements

### Requirement 1: Nova aba "Prospectar" no ControlPanel

**User Story:** Como usuário do atlas, quero uma aba dedicada "Prospectar" no ControlPanel, para que eu possa iniciar buscas de empresas prospectadas sem interferir nos filtros de parceiros ativos.

#### Acceptance Criteria

1. THE ControlPanel SHALL exibir uma aba com o rótulo "Prospectar" após as abas existentes ("Filtros", "Estilo", "Área", "Rotas").
2. WHEN a aba "Prospectar" é selecionada, THE ControlPanel SHALL renderizar o ProspectTab no painel de conteúdo.
3. WHEN a aba "Prospectar" é selecionada, THE ControlPanel SHALL preservar o estado das demais abas sem resetá-las.
4. THE ProspectTab SHALL exibir um seletor de Delivery_Station com todas as estações disponíveis em `allMarkersData`.
5. THE ProspectTab SHALL exibir um seletor de Carteira cascateado pela Delivery_Station selecionada, listando apenas as carteiras (`bucket_ade`) pertencentes à Delivery_Station escolhida.
6. WHEN nenhuma Delivery_Station está selecionada, THE ProspectTab SHALL exibir todas as carteiras disponíveis no seletor de Carteira.
7. WHEN a Delivery_Station selecionada é alterada, THE ProspectTab SHALL limpar a seleção de Carteira e atualizar a lista de carteiras disponíveis.
8. THE ProspectTab SHALL exibir um botão "Buscar Empresas" que só fica habilitado quando pelo menos uma Delivery_Station e uma Carteira estão selecionadas.

---

### Requirement 2: Busca de empresas via Prospect_API

**User Story:** Como usuário do atlas, quero buscar empresas próximas à carteira selecionada, para que eu possa identificar oportunidades de prospecção naquele território.

#### Acceptance Criteria

1. WHEN o botão "Buscar Empresas" é acionado, THE ProspectTab SHALL chamar a Prospect_API com os parâmetros da Delivery_Station e Carteira selecionadas.
2. WHILE a Prospect_API está sendo consultada, THE ProspectTab SHALL exibir um indicador de carregamento e desabilitar o botão "Buscar Empresas".
3. WHEN a Prospect_API retorna com sucesso, THE ProspectTab SHALL armazenar a lista de `ProspectCompany` retornada no estado local do componente.
4. IF a Prospect_API retorna um erro HTTP ou falha de rede, THEN THE ProspectTab SHALL exibir uma mensagem de erro descritiva ao usuário e reabilitar o botão "Buscar Empresas".
5. IF a Prospect_API retorna uma lista vazia, THEN THE ProspectTab SHALL exibir a mensagem "Nenhuma empresa encontrada para esta carteira." no ResultPanel.
6. WHEN uma nova busca é iniciada, THE ProspectTab SHALL descartar os resultados da busca anterior antes de exibir os novos.

---

### Requirement 3: Painel lateral de resultados (ResultPanel)

**User Story:** Como usuário do atlas, quero ver a lista de empresas encontradas em um painel lateral fixo, para que eu possa consultá-las enquanto navego no mapa.

#### Acceptance Criteria

1. WHEN a Prospect_API retorna resultados com sucesso, THE ResultPanel SHALL ser exibido como painel lateral fixo no lado esquerdo da tela, sobreposto ao mapa, com layout similar ao painel do AreaAnalysisTab.
2. THE ResultPanel SHALL exibir o total de empresas encontradas no cabeçalho do painel.
3. THE ResultPanel SHALL exibir para cada `ProspectCompany`: nome, endereço, tipo de empresa (`tipo`), telefone (quando disponível) e link para o Google Maps (`google_maps_link`).
4. THE ResultPanel SHALL exibir um botão de fechar que, quando acionado, oculta o painel e limpa o ProspectHeatmap do mapa.
5. WHILE o ResultPanel está visível em dispositivos desktop e tablet, THE ResultPanel SHALL permanecer fixo e não interferir na interação com o mapa.
6. WHEN o dispositivo é mobile, THE ResultPanel SHALL ser renderizado inline dentro do ProspectTab, abaixo dos filtros, em vez de como painel lateral.
7. THE ResultPanel SHALL exibir o nome da Delivery_Station e da Carteira selecionadas como contexto no cabeçalho.
8. THE ResultPanel SHALL exibir um botão de alfinete em cada card de `ProspectCompany` que possua coordenadas válidas (`lat` e `lon` não nulos).
9. WHEN o botão de alfinete é acionado para uma empresa não fixada, THE mapa SHALL adicionar um marcador `L.marker` na posição da empresa com popup contendo nome, endereço e telefone (quando disponível), e THE mapa SHALL centralizar na posição da empresa com zoom mínimo 15.
10. WHEN o botão de alfinete é acionado para uma empresa já fixada, THE mapa SHALL remover o marcador dessa empresa.
11. WHEN o ResultPanel é fechado, THE mapa SHALL remover todos os marcadores de alfinete ativos.
12. THE botão de alfinete SHALL exibir estado visual distinguível entre fixado (opacidade total) e não fixado (opacidade reduzida), usando classes Tailwind consistentes com o design system do atlas-react.
13. THE ResultPanel SHALL exibir em cada card um controle "Marcar como contactada".
14. WHEN o controle "Marcar como contactada" é acionado para uma empresa não contactada, THE ResultPanel SHALL chamar `POST /api/empresas/contactada` com os campos `lead_key` (valor de `google_maps_link` quando disponível e diferente de `'N/A'`, senão `nome|endereco`), `lead_nome`, `territorio` (valor do `bucket_ade` selecionado), `fonte` e `action: 'add'`.
15. WHEN a empresa é marcada como contactada com sucesso, THE card SHALL exibir estado visual de "contactada" (opacidade reduzida) e o controle SHALL refletir o estado atual.
16. WHEN o controle "Marcar como contactada" é acionado para uma empresa já contactada, THE ResultPanel SHALL chamar `POST /api/empresas/contactada` com `action: 'remove'` e THE card SHALL restaurar o visual padrão.
17. THE ResultPanel SHALL exibir no cabeçalho a contagem de empresas contactadas, atualizada em tempo real após cada toggle.

---

### Requirement 4: Clusterização K-means das oportunidades

**User Story:** Como usuário do atlas, quero que as empresas prospectadas sejam agrupadas geograficamente em clusters, para que eu possa identificar as regiões com maior concentração de oportunidades.

#### Acceptance Criteria

1. WHEN a Prospect_API retorna resultados com sucesso, THE ProspectTab SHALL executar o algoritmo K-means sobre as coordenadas (`lat`, `lon`) das `ProspectCompany` com coordenadas válidas, produzindo exatamente 4 K-means_Clusters por carteira.
2. IF o número de `ProspectCompany` com coordenadas válidas for menor que 4, THEN THE ProspectTab SHALL criar um K-means_Cluster por empresa disponível, sem forçar 4 clusters vazios.
3. THE ProspectTab SHALL calcular para cada K-means_Cluster: centróide geográfico, contagem de empresas (`count`) e `match_count` igual ao número de empresas do cluster onde `isMatch === true` — sendo `isMatch` verdadeiro quando a empresa tem coordenadas e a distância ao centróide do slot é menor ou igual a `radius_s`, ou quando a empresa não tem coordenadas e seu CEP pertence ao conjunto de CEPs do slot — independente da fonte (`_fonte`) da empresa.
4. THE ProspectTab SHALL classificar os K-means_Clusters por prioridade, onde o cluster com maior `count + match_count` combinado recebe prioridade 1 (mais alta).
5. THE ProspectTab SHALL atribuir intensidade de heatmap proporcional à prioridade: o cluster de prioridade 1 recebe intensidade máxima (1.0) e os demais recebem intensidade decrescente proporcional.

---

### Requirement 5: Visualização como ProspectHeatmap no mapa

**User Story:** Como usuário do atlas, quero ver as oportunidades prospectadas como heatmap no mapa, para que eu possa identificar visualmente as regiões prioritárias sem poluição visual de marcadores individuais.

#### Acceptance Criteria

1. WHEN os K-means_Clusters são calculados, THE HeatmapLayer SHALL renderizar um ProspectHeatmap usando os centróides dos clusters como pontos de calor, com intensidade proporcional à prioridade de cada cluster.
2. WHEN o ProspectHeatmap está ativo, THE PartnerMarkers SHALL não exibir marcadores individuais das empresas retornadas pela Prospect_API, pois essas empresas são representadas pelo heatmap; os marcadores de parceiros provenientes do `dados_mapa` (incluindo os de status `"Prospect"`) não são afetados.
3. WHEN o ProspectHeatmap está ativo, THE PolygonLayer SHALL exibir apenas o polígono do território da Carteira selecionada preenchido, sem exibir polígonos de outras carteiras.
4. WHEN o ResultPanel é fechado, THE HeatmapLayer SHALL remover o ProspectHeatmap do mapa e restaurar o comportamento padrão de exibição de marcadores e polígonos.
5. WHEN o ProspectHeatmap está ativo, THE HeatmapLayer SHALL implementar a camada usando `leaflet.heat` via `useEffect` com `L.heatLayer`, conforme o padrão documentado no placeholder existente em `HeatmapLayer.tsx`.
6. WHERE o dispositivo suporta WebGL, THE HeatmapLayer SHALL usar raio de 40px e blur de 25px para o heatmap; WHERE o dispositivo não suporta WebGL, THE HeatmapLayer SHALL usar raio de 25px e blur de 15px como fallback.

---

### Requirement 6: Integração com o estado global (Store)

**User Story:** Como desenvolvedor, quero que o estado da prospecção seja gerenciado de forma consistente no store Zustand, para que os componentes de mapa e de controle se mantenham sincronizados.

#### Acceptance Criteria

1. THE Store SHALL expor um slice `prospectState` contendo: `companies` (lista de `ProspectCompany`), `clusters` (lista de K-means_Clusters), `isLoading` (boolean), `error` (string ou null), `selectedStation` (string ou null) e `selectedBucket` (string ou null).
2. WHEN `prospectState.companies` é atualizado, THE Store SHALL recalcular `prospectState.clusters` automaticamente via selector ou action derivada.
3. WHEN `prospectState.clusters` está vazio ou nulo, THE HeatmapLayer SHALL não renderizar o ProspectHeatmap.
4. WHEN `prospectState.companies` é limpo (lista vazia), THE Store SHALL também limpar `prospectState.clusters` e resetar `selectedStation` e `selectedBucket` para null.

---

### Requirement 7: Geolocalização do usuário em dispositivos mobile

**User Story:** Como usuário mobile do atlas, quero ver minha posição atual no mapa enquanto prospecta, para que eu possa me orientar geograficamente em relação às empresas marcadas com alfinete.

#### Acceptance Criteria

1. WHEN o dispositivo é mobile E o ResultPanel está ativo, THE mapa SHALL exibir um botão "Minha localização" com ícone de GPS/localização.
2. WHEN o botão "Minha localização" é acionado, THE mapa SHALL solicitar permissão de geolocalização via `navigator.geolocation.watchPosition`.
3. WHEN a permissão é concedida, THE mapa SHALL exibir um marcador de posição do usuário com animação pulsante (similar ao Google Maps) e centralizar o mapa na posição do usuário.
4. WHEN a posição do usuário é atualizada, THE marcador SHALL se mover para a nova posição sem recarregar o mapa.
5. WHEN o botão "Minha localização" é acionado novamente com rastreamento ativo, THE mapa SHALL parar o rastreamento via `navigator.geolocation.clearWatch` e remover o marcador de posição do usuário.
6. IF a permissão de geolocalização é negada ou indisponível, THEN THE mapa SHALL exibir uma mensagem informativa ao usuário.
7. WHEN o ResultPanel é fechado, THE mapa SHALL parar o rastreamento de geolocalização e remover o marcador de posição do usuário.
8. WHERE o dispositivo é desktop ou tablet, THE botão "Minha localização" SHALL não ser exibido.
