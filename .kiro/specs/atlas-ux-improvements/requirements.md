# Documento de Requisitos

## Introdução

Este documento descreve um conjunto de melhorias de UX no frontend React do ATLAS. As melhorias abrangem sete áreas: (1) barra de busca flutuante e funcional sobre o mapa, (2) dashboard gerencial renovado com filtros em cascata e dados do `relatorio_executivo.json`, (3) botão do dashboard como semi-círculo deslizante à direita, (4) botão de controles como semi-círculo deslizante à esquerda em tablet/mobile, (5) correção do botão de filtro que desaparece no desktop após carregamento, (6) remoção dos controles de zoom padrão do Leaflet, e (7) correção do sistema de rotas para usar leaflet-routing-machine com rota real via OSRM em vez de linha reta.

**Princípio de implementação:** todas as melhorias devem reutilizar as funções e lógicas já existentes no projeto (`routeUtils.ts`, `popupUtils.ts`, `management-dashboard.js`, `colorUtils.ts`, etc.), sem reescrever funcionalidades já implementadas.

---

## Glossário

- **ATLAS**: Aplicação de mapeamento e análise geoespacial (Analytical Tracking for Location and Store performance).
- **App**: A aplicação React do ATLAS.
- **MapView**: Componente React responsável pela renderização do mapa Leaflet.
- **AppShell**: Componente raiz de layout que orquestra os painéis por breakpoint.
- **ControlPanel**: Painel de controles com abas (Filtros, Estilo, Área, Rotas).
- **Dashboard**: Painel gerencial com KPIs, gráficos e tabela de territórios.
- **SearchBar**: Componente de busca flutuante por parceiro ou endereço, sobreposto ao mapa.
- **DashboardToggle**: Botão semi-circular fixo na borda direita da tela que abre/fecha o Dashboard.
- **ControlsToggle**: Botão semi-circular fixo na borda esquerda da tela que abre/fecha o ControlPanel em tablet e mobile.
- **FloatingPanel**: Painel flutuante sobreposto ao mapa, usado no layout desktop/notebook.
- **BottomSheet**: Componente deslizante que emerge da parte inferior da tela em mobile.
- **Drawer**: Painel lateral deslizante usado em tablet.
- **FAB**: Floating Action Button — botão de ação flutuante circular.
- **ReportData**: Estrutura de dados carregada do `relatorio_executivo.json`, contendo bases, territórios, KPIs e metadados.
- **FilterCascade**: Mecanismo de filtros em cascata BDM → Base → CTL → Território, onde a seleção de um nível restringe as opções dos níveis seguintes.
- **KPI_Card**: Card visual que exibe um indicador-chave de performance.
- **Breakpoint_Mobile**: Largura de tela ≤ 767px.
- **Breakpoint_Tablet**: Largura de tela entre 768px e 1023px.
- **Breakpoint_Desktop**: Largura de tela ≥ 1024px (notebook e desktop grande).
- **Autocomplete**: Lista de sugestões exibida abaixo do campo de busca enquanto o usuário digita.
- **relatorio_executivo.json**: Arquivo JSON gerado pelo backend com dados consolidados de bases, territórios, KPIs de attainment e cobertura.
- **RoutingMachine**: Integração com `leaflet-routing-machine` via OSRM para cálculo e exibição de rotas reais entre parceiros.
- **RouteLayer**: Componente React responsável por renderizar a rota calculada no mapa usando `leaflet-routing-machine`.

---

## Requisitos

### Requisito 1: Barra de Busca Flutuante

**User Story:** Como usuário, quero uma barra de busca flutuante e funcional sobre o mapa, para que eu possa localizar parceiros por nome ou endereços no mapa sem precisar abrir o painel de controles.

#### Critérios de Aceitação

1. THE SearchBar SHALL ser um componente React independente, renderizado diretamente sobre o MapView em todos os breakpoints, sem estar contido dentro do ControlPanel.
2. WHILE a largura da tela está no Breakpoint_Desktop, THE SearchBar SHALL ser posicionada no topo do mapa, alinhada à esquerda, com margem de 16px em relação à borda esquerda e ao topo da área do mapa.
3. WHILE a largura da tela está no Breakpoint_Mobile ou Breakpoint_Tablet, THE SearchBar SHALL ser posicionada no topo do mapa, centralizada horizontalmente, com largura máxima de 90% da viewport.
4. WHEN o usuário digita 2 ou mais caracteres no SearchBar, THE SearchBar SHALL exibir um Autocomplete com sugestões de parceiros cujo nome contenha o texto digitado, com debounce de 300ms.
5. WHEN o usuário seleciona uma sugestão no Autocomplete, THE MapView SHALL centralizar o mapa nas coordenadas do parceiro selecionado e exibir o popup correspondente.
6. WHEN o usuário pressiona Enter no SearchBar com um texto que não corresponde a nenhum parceiro, THE SearchBar SHALL realizar uma busca por endereço via geocodificação e centralizar o mapa no resultado.
7. IF nenhum resultado de geocodificação é encontrado, THEN THE SearchBar SHALL exibir uma mensagem de erro não-bloqueante abaixo do campo de busca.
8. THE SearchBar SHALL ter z-index superior ao do mapa e inferior ao dos modais, garantindo visibilidade em todos os breakpoints.
9. THE SearchBar SHALL ter largura mínima de 280px e máxima de 480px no Breakpoint_Desktop.
10. WHEN o Autocomplete está visível e o usuário pressiona Escape, THE SearchBar SHALL fechar o Autocomplete e manter o foco no campo de texto.

---

### Requisito 2: Dashboard Renovado com Dados do Relatório Executivo

**User Story:** Como gestor, quero um dashboard renovado que carregue dados do `relatorio_executivo.json` e exiba filtros em cascata, KPI cards, gráficos e tabela de territórios, para que eu possa analisar a performance operacional de forma consolidada.

#### Critérios de Aceitação

1. THE Dashboard SHALL carregar os dados do `relatorio_executivo.json` via fetch ao ser aberto pela primeira vez, exibindo um spinner durante o carregamento.
2. IF o fetch do `relatorio_executivo.json` falha, THEN THE Dashboard SHALL exibir uma mensagem de erro descritiva e um botão de "Tentar novamente".
3. THE Dashboard SHALL exibir uma barra de filtros em cascata com quatro selects na ordem: BDM → Base → CTL → Território.
4. WHEN o usuário seleciona um valor no filtro BDM, THE Dashboard SHALL atualizar as opções dos filtros Base, CTL e Território para exibir apenas os valores relacionados ao BDM selecionado, e resetar os três filtros dependentes para "Todos".
5. WHEN o usuário seleciona um valor no filtro Base, THE Dashboard SHALL atualizar as opções dos filtros CTL e Território para exibir apenas os valores relacionados à Base selecionada, e resetar os dois filtros dependentes para "Todos".
6. WHEN o usuário seleciona um valor no filtro CTL, THE Dashboard SHALL atualizar as opções do filtro Território para exibir apenas os territórios pertencentes ao CTL selecionado, e resetar o filtro Território para "Todos".
7. THE Dashboard SHALL exibir KPI cards com os seguintes indicadores calculados a partir dos dados filtrados: Total de Bases, Total de Territórios, Demanda Diária (pacotes/dia), Vagas Ideais, Vagas em Aberto, Parceiros Ativos, Attainment Médio (%) e Cobertura Média (%).
8. WHEN os filtros são alterados, THE Dashboard SHALL recalcular e re-renderizar todos os KPI cards com os valores correspondentes aos dados filtrados.
9. THE Dashboard SHALL exibir pelo menos dois gráficos via react-chartjs-2: (a) gráfico de barras com Attainment por Base, ordenado do maior para o menor; (b) gráfico de barras empilhadas com composição de parceiros (Ativos, Onboarding, BG, Prospects, Inativos) por Base.
10. THE Dashboard SHALL exibir uma tabela de territórios com as colunas: Base, CTL, Território, Demanda Diária, Vagas Totais, Vagas em Aberto, Ativos, Onboarding, BG, Prospects, Inativos, Attainment (%), Acuracidade (%).
11. WHEN o usuário clica no cabeçalho de uma coluna da tabela de territórios, THE Dashboard SHALL ordenar as linhas pela coluna clicada, alternando entre ordem crescente e decrescente a cada clique.
12. THE Dashboard SHALL aplicar classes de cor (verde, amarelo, vermelho) nas células de Attainment e Acuracidade da tabela, de acordo com os thresholds definidos no módulo `management-dashboard.js`.
13. WHILE os dados do Dashboard estão sendo carregados, THE Dashboard SHALL exibir um spinner centralizado e desabilitar os controles de filtro.
14. THE Dashboard SHALL preservar os valores dos filtros selecionados ao ser fechado e reaberto dentro da mesma sessão.

---

### Requisito 3: Botão do Dashboard como Semi-Círculo Deslizante à Direita

**User Story:** Como usuário, quero um botão visualmente intuitivo na borda direita da tela para abrir o dashboard, para que eu entenda imediatamente que o painel desliza da direita para a esquerda.

#### Critérios de Aceitação

1. THE DashboardToggle SHALL ser um elemento semi-circular fixo, posicionado na borda direita da tela, verticalmente centralizado.
2. THE DashboardToggle SHALL ter a forma de um semi-círculo com a face plana voltada para a direita (borda da tela) e a face curva voltada para o interior da tela, sugerindo visualmente um deslizar da direita para a esquerda.
3. THE DashboardToggle SHALL exibir um ícone de gráfico de barras e o texto "Dashboard" rotacionado verticalmente ou disposto de forma legível dentro do semi-círculo.
4. WHEN o usuário clica no DashboardToggle, THE Dashboard SHALL abrir como painel lateral deslizando da direita para a esquerda com animação de transição de 300ms.
5. WHEN o Dashboard está aberto e o usuário clica no DashboardToggle novamente, THE Dashboard SHALL fechar deslizando da esquerda para a direita com animação de transição de 300ms.
6. THE DashboardToggle SHALL ser visível em todos os breakpoints (mobile, tablet e desktop).
7. THE DashboardToggle SHALL ter área de toque mínima de 44px de altura para acessibilidade.
8. WHEN o Dashboard está aberto, THE DashboardToggle SHALL mudar de aparência visual (ex: cor ou ícone) para indicar o estado ativo.

---

### Requisito 4: Botão de Controles como Semi-Círculo Deslizante à Esquerda (Mobile e Tablet)

**User Story:** Como usuário de tablet ou mobile, quero um botão visualmente intuitivo na borda esquerda da tela para abrir o painel de controles, para que eu entenda imediatamente que o painel desliza da esquerda para a direita.

#### Critérios de Aceitação

1. WHILE a largura da tela está no Breakpoint_Mobile ou Breakpoint_Tablet, THE ControlsToggle SHALL ser um elemento semi-circular fixo, posicionado na borda esquerda da tela, verticalmente centralizado.
2. THE ControlsToggle SHALL ter a forma de um semi-círculo com a face plana voltada para a esquerda (borda da tela) e a face curva voltada para o interior da tela, sugerindo visualmente um deslizar da esquerda para a direita.
3. THE ControlsToggle SHALL exibir um ícone de hamburguer (três linhas horizontais) ou ícone de controles dentro do semi-círculo.
4. WHEN o usuário clica no ControlsToggle em Breakpoint_Mobile, THE ControlPanel SHALL abrir como BottomSheet ou Drawer lateral deslizando da esquerda para a direita com animação de transição de 300ms.
5. WHEN o usuário clica no ControlsToggle em Breakpoint_Tablet, THE ControlPanel SHALL abrir como Drawer lateral deslizando da esquerda para a direita com animação de transição de 300ms.
6. WHEN o ControlPanel está aberto e o usuário clica no ControlsToggle novamente, THE ControlPanel SHALL fechar com animação de transição de 300ms.
7. THE ControlsToggle SHALL ter área de toque mínima de 44px de altura para acessibilidade.
8. WHEN o ControlPanel está aberto, THE ControlsToggle SHALL mudar de aparência visual para indicar o estado ativo.
9. WHILE a largura da tela está no Breakpoint_Desktop, THE ControlsToggle SHALL ser ocultado, pois o ControlPanel é exibido como FloatingPanel fixo.

---

### Requisito 5: Correção do Botão de Filtro Sumindo no Desktop

**User Story:** Como usuário de desktop, quero que o painel de controles permaneça visível e acessível após o carregamento dos dados, para que eu não perca acesso aos filtros e controles do mapa.

#### Critérios de Aceitação

1. WHILE a largura da tela está no Breakpoint_Desktop, THE ControlPanel SHALL permanecer visível como FloatingPanel após a conclusão do carregamento dos dados (transição de `isLoading: true` para `isLoading: false`).
2. THE AppShell SHALL garantir que o FloatingPanel do ControlPanel não seja desmontado ou ocultado em nenhuma transição de estado de carregamento no Breakpoint_Desktop.
3. WHEN `isLoading` muda de `true` para `false` no Breakpoint_Desktop, THE ControlPanel SHALL continuar renderizado e interativo sem necessidade de ação do usuário.
4. IF o ControlPanel estava visível antes do início do carregamento no Breakpoint_Desktop, THEN THE ControlPanel SHALL permanecer visível após o término do carregamento.

---

### Requisito 6: Remoção dos Controles de Zoom Padrão do Leaflet

**User Story:** Como usuário, quero que os botões de zoom padrão do Leaflet sejam removidos do mapa, para que a interface fique mais limpa e sem elementos redundantes.

#### Critérios de Aceitação

1. THE MapView SHALL inicializar o MapContainer do Leaflet com a opção `zoomControl: false`, removendo os botões de zoom padrão (+/-) da interface do mapa.
2. THE MapView SHALL preservar todas as demais funcionalidades de zoom do mapa, incluindo zoom por scroll do mouse, zoom por pinça (touch) e zoom por duplo clique.
3. WHEN o MapView é renderizado, THE MapView SHALL não exibir nenhum controle de zoom nativo do Leaflet em nenhum breakpoint.

---

### Requisito 7: Correção do Sistema de Rotas com Rota Real via OSRM

**User Story:** Como usuário, quero que ao calcular uma rota entre parceiros o mapa exiba o trajeto real pelas vias, com o painel de instruções, em vez de uma linha reta, para que eu possa planejar visitas de campo com precisão.

#### Critérios de Aceitação

1. THE RouteLayer SHALL integrar `leaflet-routing-machine` via `useEffect` com `L.Routing.control()` para calcular e exibir rotas reais usando o serviço OSRM (`https://router.project-osrm.org/route/v1`).
2. WHEN o store contém 2 ou mais `RouteStop` em `route`, THE RouteLayer SHALL criar um `L.Routing.control` com os waypoints correspondentes e adicioná-lo ao mapa.
3. THE RouteLayer SHALL reutilizar a função `optimizeStops` de `routeUtils.ts` para ordenar as paradas intermediárias antes de passar os waypoints ao `L.Routing.control`.
4. THE RouteLayer SHALL configurar o `L.Routing.control` com `lineOptions: { styles: [{ color: 'blue', opacity: 0.8, weight: 5 }] }` e `createMarker` retornando `L.marker` para cada waypoint.
5. WHEN a rota é calculada com sucesso, THE RouteLayer SHALL exibir o painel de instruções de navegação do `leaflet-routing-machine` (container de rotas).
6. WHEN `route` no store é limpo (array vazio), THE RouteLayer SHALL remover o `L.Routing.control` do mapa via `map.removeControl()`.
7. WHEN o componente RouteLayer é desmontado, THE RouteLayer SHALL remover o `L.Routing.control` do mapa para evitar memory leaks.
8. THE RouteLayer SHALL substituir completamente a implementação atual de `Polyline` simples, que traça linha reta entre os pontos.
9. IF o serviço OSRM retorna erro, THEN THE RouteLayer SHALL capturar o evento `routingerror` do `L.Routing.control` e chamar `store.setError` com uma mensagem descritiva.
