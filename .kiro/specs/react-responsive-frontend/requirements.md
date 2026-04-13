# Documento de Requisitos

## Introdução

Migração do frontend do ATLAS (Analytical Tracking for Location and Store performance) de HTML/CSS/JS vanilla para React com TypeScript, utilizando Vite como build tool, Tailwind CSS para estilização e react-leaflet para mapas. A migração é do tipo "big bang" — substituição completa do ATLAS.html por uma aplicação React moderna, responsiva para mobile, tablet, notebook e desktops grandes. O design será modernizado mantendo o tema escuro. O suporte a PWA (service worker + manifest) e o Web Worker para processamento de dados serão preservados.

---

## Glossário

- **ATLAS**: Aplicação de mapeamento e análise geoespacial (Analytical Tracking for Location and Store performance).
- **App**: A aplicação React resultante da migração.
- **MapView**: Componente React responsável pela renderização do mapa Leaflet.
- **ControlPanel**: Conjunto de painéis de controle (filtros, análise de área, rotas).
- **Dashboard**: Painel gerencial com KPIs, gráficos e tabelas de performance.
- **BottomSheet**: Componente deslizante que emerge da parte inferior da tela em dispositivos móveis.
- **Drawer**: Painel lateral deslizante utilizado em tablets e desktops.
- **FAB**: Floating Action Button — botão de ação flutuante sobre o mapa.
- **DataWorker**: Web Worker responsável pelo processamento de dados geoespaciais em background.
- **ServiceWorker**: Worker de service que habilita funcionalidades PWA (cache offline, instalação).
- **Store**: Gerenciador de estado global da aplicação (Zustand).
- **Breakpoint_Mobile**: Largura de tela ≤ 767px.
- **Breakpoint_Tablet**: Largura de tela entre 768px e 1023px.
- **Breakpoint_Notebook**: Largura de tela entre 1024px e 1439px.
- **Breakpoint_Desktop**: Largura de tela ≥ 1440px.
- **Partner**: Entidade de parceiro logístico representada como marcador no mapa.
- **DeliveryStation**: Estação de entrega representada no mapa.
- **GeoJSON**: Formato de dados geoespaciais utilizado para territórios, jurisdições e camadas de otimização.

---

## Requisitos

### Requisito 1: Configuração do Projeto React com Vite e TypeScript

**User Story:** Como desenvolvedor, quero um projeto React configurado com Vite, TypeScript e Tailwind CSS, para que eu tenha uma base moderna, tipada e com build rápido.

#### Critérios de Aceitação

1. THE App SHALL ser inicializado com Vite utilizando o template `react-ts`.
2. THE App SHALL ter Tailwind CSS configurado como solução principal de estilização.
3. THE App SHALL ter o compilador TypeScript configurado com `strict: true`.
4. THE App SHALL ter ESLint e Prettier configurados para garantir qualidade de código.
5. WHEN o comando de build é executado, THE App SHALL gerar artefatos otimizados com code splitting automático por rota e por componente pesado.
6. THE App SHALL manter o arquivo `manifest.json` existente e registrar o `ServiceWorker` para suporte a PWA.

---

### Requisito 2: Gerenciamento de Estado Global com Zustand

**User Story:** Como desenvolvedor, quero um gerenciador de estado global tipado e reativo, para que os componentes React se comuniquem sem acoplamento direto, substituindo o state.js atual.

#### Critérios de Aceitação

1. THE Store SHALL conter todas as propriedades de estado atualmente definidas em `state.js`, incluindo `allMarkersData`, `currentFilteredData`, `deliveryStations`, `polygonsData`, `jurisdictionData`, `optimizationData`, `idealSupplyData`, `heatmapData`, `period`, camadas do mapa e estado do HCP.
2. THE Store SHALL ser tipado com TypeScript, com interfaces definidas para `Partner`, `DeliveryStation` e `FilterState`.
3. WHEN qualquer propriedade do Store é atualizada, THE App SHALL re-renderizar apenas os componentes que consomem aquela propriedade específica.
4. THE Store SHALL expor actions para `applyFilters`, `resetFilters`, `loadAll` e demais operações de negócio atualmente em `data-manager.js`.
5. IF uma action do Store lança uma exceção, THEN THE Store SHALL registrar o erro no console e manter o estado anterior sem corromper o Store.

---

### Requisito 3: Integração do Mapa com react-leaflet

**User Story:** Como usuário, quero visualizar o mapa interativo com todas as camadas existentes, para que eu possa analisar a distribuição geoespacial dos parceiros e territórios.

#### Critérios de Aceitação

1. THE MapView SHALL renderizar o mapa Leaflet utilizando `react-leaflet` com as mesmas configurações de `MAP_CONFIG` (centro, zoom, tile URL Google Maps).
2. THE MapView SHALL suportar todas as camadas existentes: marcadores de parceiros, marcadores de delivery stations, polígonos de territórios, camada de jurisdição, camada de otimização e heatmap.
3. WHEN `currentFilteredData` é atualizado no Store, THE MapView SHALL re-renderizar os marcadores de parceiros sem recriar a instância do mapa.
4. THE MapView SHALL preservar todos os comportamentos de popup existentes, incluindo popup de comparação e popup de slot.
5. WHEN o usuário clica em um marcador, THE MapView SHALL exibir o popup correspondente com as informações do Partner ou DeliveryStation.
6. THE MapView SHALL ocupar 100% da área disponível da viewport em todos os breakpoints.
7. THE MapView SHALL preservar a funcionalidade de roteamento via `leaflet-routing-machine`.
8. THE MapView SHALL preservar a funcionalidade de medição de distância via `leaflet.polyline.measure`.

---

### Requisito 4: Processamento de Dados com Web Worker

**User Story:** Como usuário, quero que o carregamento e processamento de dados geoespaciais não bloqueie a interface, para que o mapa permaneça responsivo durante operações pesadas.

#### Critérios de Aceitação

1. THE DataWorker SHALL processar o carregamento e parsing dos dados de `dados_mapa.json`, `territories.geojson`, `jurisdiction.geojson`, `optimization_data.geojson` e `heatmap.geojson` fora do thread principal.
2. WHEN o DataWorker conclui o processamento de um dataset, THE App SHALL atualizar o Store com os dados processados via `postMessage`.
3. WHILE o DataWorker está processando dados, THE App SHALL exibir um indicador de carregamento no header.
4. IF o DataWorker falha ao carregar um dataset, THEN THE App SHALL exibir uma mensagem de erro não-bloqueante e continuar operando com os dados disponíveis.
5. THE DataWorker SHALL ser compatível com o Vite utilizando a sintaxe `new Worker(new URL('./data-worker.ts', import.meta.url))`.

---

### Requisito 5: Layout Responsivo — Mobile (≤ 767px)

**User Story:** Como usuário mobile, quero usar o ATLAS no celular com uma experiência otimizada para toque, para que eu possa consultar dados geoespaciais em campo.

#### Critérios de Aceitação

1. WHILE a largura da tela está no Breakpoint_Mobile, THE MapView SHALL ocupar 100% da altura e largura da viewport.
2. WHILE a largura da tela está no Breakpoint_Mobile, THE ControlPanel SHALL ser renderizado como BottomSheet deslizante, emergindo da parte inferior da tela.
3. WHILE a largura da tela está no Breakpoint_Mobile, THE App SHALL exibir FABs para acesso rápido ao ControlPanel e ao Dashboard, posicionados sobre o mapa.
4. WHILE a largura da tela está no Breakpoint_Mobile, THE BottomSheet SHALL suportar gestos de arrastar (drag) para expandir e recolher.
5. WHILE a largura da tela está no Breakpoint_Mobile, THE Dashboard SHALL ser exibido como modal em tela cheia ao ser ativado.
6. WHILE a largura da tela está no Breakpoint_Mobile, THE App SHALL ter todos os elementos interativos com área de toque mínima de 44x44px.
7. WHILE a largura da tela está no Breakpoint_Mobile, THE App SHALL exibir o header de forma compacta, mostrando apenas o logo e o título abreviado "ATLAS".

---

### Requisito 6: Layout Responsivo — Tablet (768px–1023px)

**User Story:** Como usuário de tablet, quero usar o ATLAS com uma experiência adaptada ao tamanho intermediário de tela, para que eu tenha acesso aos controles sem sacrificar a área do mapa.

#### Critérios de Aceitação

1. WHILE a largura da tela está no Breakpoint_Tablet, THE MapView SHALL ocupar 100% da altura e largura da viewport.
2. WHILE a largura da tela está no Breakpoint_Tablet, THE ControlPanel SHALL ser renderizado como Drawer lateral esquerdo, recolhível via botão de toggle.
3. WHILE a largura da tela está no Breakpoint_Tablet, THE Drawer SHALL ter largura de 320px quando expandido e ficar sobreposto ao mapa (overlay mode).
4. WHILE a largura da tela está no Breakpoint_Tablet, THE Dashboard SHALL ser exibido como painel lateral direito com largura de 85% da viewport.
5. WHILE a largura da tela está no Breakpoint_Tablet, THE App SHALL exibir o header completo com logo, título e informação de período.

---

### Requisito 7: Layout Responsivo — Notebook (1024px–1439px)

**User Story:** Como usuário de notebook, quero usar o ATLAS com os painéis de controle visíveis sem precisar abrir menus, para que eu tenha uma experiência produtiva.

#### Critérios de Aceitação

1. WHILE a largura da tela está no Breakpoint_Notebook, THE App SHALL exibir o ControlPanel como painéis flutuantes sobrepostos ao mapa no canto superior esquerdo, com largura de 320px.
2. WHILE a largura da tela está no Breakpoint_Notebook, THE ControlPanel SHALL ser recolhível por painel individualmente via cabeçalho clicável.
3. WHILE a largura da tela está no Breakpoint_Notebook, THE Dashboard SHALL ser exibido como painel lateral direito com largura de 480px.
4. WHILE a largura da tela está no Breakpoint_Notebook, THE MapView SHALL ocupar toda a área restante após os painéis flutuantes.

---

### Requisito 8: Layout Responsivo — Desktop Grande (≥ 1440px)

**User Story:** Como usuário de desktop com monitor grande, quero aproveitar o espaço extra de tela para visualizar mais informações simultaneamente, para que eu tenha máxima produtividade.

#### Critérios de Aceitação

1. WHILE a largura da tela está no Breakpoint_Desktop, THE App SHALL exibir o ControlPanel como painéis flutuantes com largura de 360px.
2. WHILE a largura da tela está no Breakpoint_Desktop, THE Dashboard SHALL ser exibido como painel lateral direito com largura de 560px.
3. WHILE a largura da tela está no Breakpoint_Desktop, THE App SHALL escalar tipografia e espaçamentos proporcionalmente para melhor legibilidade em telas grandes.
4. WHILE a largura da tela está no Breakpoint_Desktop, THE MapView SHALL ocupar toda a área restante após os painéis flutuantes.

---

### Requisito 9: Componente de Filtros

**User Story:** Como usuário, quero filtrar os parceiros exibidos no mapa por status, delivery station, carteira ADE e iniciativas, para que eu possa focar na análise de um subconjunto específico de dados.

#### Critérios de Aceitação

1. THE ControlPanel SHALL conter um componente de filtros com os campos: Status (multi-select), Delivery Station (multi-select), Carteira ADE (multi-select), Delivery Initiatives (select) e Jurisdiction Type (select).
2. WHEN o usuário clica em "Aplicar Filtros", THE Store SHALL atualizar `currentFilteredData` com os parceiros que satisfazem todos os critérios selecionados.
3. WHEN o usuário clica em "Limpar Filtros", THE Store SHALL restaurar `currentFilteredData` para `allMarkersData` e resetar todos os selects para os valores padrão.
4. WHEN `allMarkersData` é carregado, THE App SHALL popular automaticamente as opções dos selects de Delivery Station e Carteira ADE com os valores únicos presentes nos dados.
5. THE ControlPanel SHALL preservar o autocomplete de busca por nome de parceiro com debounce de 300ms.

---

### Requisito 10: Componente de Estilização do Mapa

**User Story:** Como usuário, quero controlar a aparência visual dos marcadores e camadas do mapa, para que eu possa identificar padrões por diferentes dimensões de dados.

#### Critérios de Aceitação

1. THE ControlPanel SHALL conter um componente de estilização com selects para "Estilizar por" (primário) e "Detalhar por" (secundário), com as opções: Delivery Station, Status, Hub Delivery Initiatives, Supply Run e Carteira.
2. WHEN o usuário altera qualquer select de estilização, THE MapView SHALL re-renderizar os marcadores com as cores correspondentes à seleção sem recarregar os dados.
3. THE ControlPanel SHALL conter checkboxes para: Exibir Raios, Exibir Áreas de Prospecção, Exibir Jurisdições e Exibir Camada de Otimização.
4. WHEN um checkbox de camada é marcado, THE MapView SHALL adicionar a camada correspondente ao mapa.
5. WHEN um checkbox de camada é desmarcado, THE MapView SHALL remover a camada correspondente do mapa.

---

### Requisito 11: Componente de Análise de Área

**User Story:** Como usuário, quero analisar prospects por estado e decisão (Go/No Go), para que eu possa avaliar oportunidades de expansão por região.

#### Critérios de Aceitação

1. THE ControlPanel SHALL conter uma aba de Análise de Área com filtros de Estado e Decisão (Go/No Go/Todos), com filtro fixo de Status = Prospect.
2. WHEN o usuário clica em "Analisar Área", THE MapView SHALL destacar os prospects filtrados e THE App SHALL exibir estatísticas da área analisada.
3. THE App SHALL preservar a funcionalidade `showStateDetail` para exibição de detalhes por estado.

---

### Requisito 12: Componente de Rotas

**User Story:** Como usuário, quero calcular rotas entre parceiros com paradas intermediárias, para que eu possa planejar visitas de campo.

#### Critérios de Aceitação

1. THE ControlPanel SHALL conter uma aba de Rotas com campos de origem, destino e lista de paradas intermediárias.
2. THE ControlPanel SHALL ter autocomplete nos campos de origem e destino, buscando por nome de parceiro nos dados carregados.
3. WHEN o usuário clica em "Buscar Melhor Rota", THE MapView SHALL renderizar a rota calculada via `leaflet-routing-machine`.
4. THE ControlPanel SHALL permitir adicionar, reordenar (mover para cima/baixo) e remover paradas intermediárias.
5. WHEN o usuário clica em "Limpar Rota", THE MapView SHALL remover a rota renderizada e THE ControlPanel SHALL resetar todos os campos de rota.
6. WHERE a funcionalidade HCP está ativa para uma delivery station selecionada, THE ControlPanel SHALL exibir o botão "Sugerir HCP Initiatives".

---

### Requisito 13: Dashboard Gerencial

**User Story:** Como gestor, quero visualizar KPIs, gráficos e tabelas de performance dos parceiros, para que eu possa tomar decisões baseadas em dados.

#### Critérios de Aceitação

1. THE Dashboard SHALL conter uma barra de filtros com selects de período, delivery station e outros filtros relevantes.
2. THE Dashboard SHALL renderizar KPI cards com os indicadores: parceiros ativos, ADV Overall, DEA, EAD, DCR, FDDS, FTDS, HCP Host Ratio e SPR Médio.
3. THE Dashboard SHALL renderizar gráficos via Chart.js (ou react-chartjs-2) para visualização de tendências e distribuições.
4. THE Dashboard SHALL renderizar uma tabela ordenável com dados por delivery station.
5. WHEN o Dashboard é aberto, THE App SHALL inicializar os dados do dashboard via `management-dashboard.js` (ou seu equivalente React).
6. WHILE os dados do Dashboard estão sendo carregados, THE Dashboard SHALL exibir um spinner de carregamento.
7. IF os dados do Dashboard não estão disponíveis, THEN THE Dashboard SHALL exibir uma mensagem informativa não-bloqueante.
8. WHILE a largura da tela está no Breakpoint_Mobile, THE Dashboard SHALL reorganizar os KPI cards em grid de 2 colunas e os gráficos em coluna única.

---

### Requisito 14: Design System Moderno com Tema Escuro

**User Story:** Como usuário, quero uma interface visualmente moderna com tema escuro consistente, para que a experiência de uso seja agradável durante longas sessões de análise.

#### Critérios de Aceitação

1. THE App SHALL implementar um design system com tokens de cor, tipografia e espaçamento definidos como variáveis CSS e configurados no `tailwind.config`.
2. THE App SHALL manter o tema escuro como padrão, com paleta de cores baseada nos valores atuais (`#232f3e`, `#1e2a38`, `#16202c`, `#ecf0f1`).
3. THE App SHALL utilizar a fonte Inter (Google Fonts) como tipografia principal.
4. THE App SHALL ter transições suaves (150–300ms) em interações como hover, abertura de painéis e troca de abas.
5. THE App SHALL exibir estados de loading, erro e vazio de forma consistente em todos os componentes que consomem dados assíncronos.

---

### Requisito 15: Performance e Otimização

**User Story:** Como usuário, quero que a aplicação carregue rapidamente e responda sem travamentos mesmo com grandes volumes de dados geoespaciais, para que a experiência de análise seja fluida.

#### Critérios de Aceitação

1. THE App SHALL utilizar `React.memo`, `useMemo` e `useCallback` nos componentes e funções que recebem dados de grande volume (listas de marcadores, tabelas do dashboard).
2. THE App SHALL implementar virtualização de lista (ex: `react-window` ou `react-virtual`) na tabela do Dashboard quando o número de linhas exceder 100.
3. THE App SHALL fazer lazy loading dos componentes Dashboard e módulos pesados via `React.lazy` e `Suspense`.
4. THE App SHALL preservar o uso do DataWorker para que o processamento de GeoJSON e filtragem de grandes datasets não bloqueie o thread principal.
5. THE App SHALL atingir uma pontuação de Performance ≥ 80 no Lighthouse em conexão simulada de 4G.

---

### Requisito 16: Preservação das Funcionalidades Existentes

**User Story:** Como usuário atual do ATLAS, quero que todas as funcionalidades existentes continuem funcionando após a migração, para que não haja regressão de capacidades.

#### Critérios de Aceitação

1. THE App SHALL preservar todas as funcionalidades de `map-manager.js`: inicialização do mapa, criação de marcadores, re-estilização, toggle de raios e toggle da camada de otimização.
2. THE App SHALL preservar todas as funcionalidades de `polygon-manager.js`: atualização de polígonos filtrados, toggle de polígonos, jurisdições, camada de otimização e seleção de otimização.
3. THE App SHALL preservar todas as funcionalidades de `ui-manager.js`: busca de localização, atualização de stats, toggle de painéis, requisição de assistência, análise de área, popup de stats e detalhe de estado.
4. THE App SHALL preservar todas as funcionalidades de `route-manager.js`: geração de rota, início de rota a partir de marcador, adição/remoção/reordenação de paradas, sugestão HCP e reset de sugestões HCP.
5. THE App SHALL preservar todas as funcionalidades de `gmaps-scraper.js`: busca de estabelecimentos próximos a partir do estado e busca direta.
6. THE App SHALL preservar todas as funcionalidades de `management-dashboard.js`: inicialização, filtros, KPIs, gráficos e tabela.
7. THE App SHALL preservar a funcionalidade de popup de comparação entre parceiros.
8. THE App SHALL preservar a funcionalidade de legenda de cores do mapa.
