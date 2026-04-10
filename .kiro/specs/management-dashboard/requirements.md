# Documento de Requisitos

## Introdução

Remodelação do painel de estatísticas existente (`.floating-panel-statistics`) para uma visão de **Dashboard Gerencial**, permitindo que gestores (BDMs e líderes de operação) visualizem de forma consolidada os dados do `RELATORIO_EXECUTIVO.txt`. O dashboard substitui as abas atuais (Performance, Expansion, Routes) por uma visão orientada a gestão: sumário geral, análise por base/território, gráficos e cards de KPIs, e listagem de CEPs únicos por território.

Os dados são lidos diretamente do arquivo `data/RELATORIO_EXECUTIVO.txt` (já existente), parseado no frontend via JavaScript. O dashboard é acessado pelo mesmo botão "Estatísticas" já presente no `ATLAS.html`.

---

## Glossário

- **Dashboard**: Painel gerencial com visão consolidada de métricas operacionais.
- **Dashboard_Manager**: Módulo JavaScript responsável por orquestrar o dashboard gerencial.
- **Report_Parser**: Módulo JavaScript responsável por ler e parsear o `RELATORIO_EXECUTIVO.txt`.
- **Base (DS)**: Delivery Station — unidade operacional identificada por código (ex: DBH5, DBR9).
- **BDM**: Business Development Manager — gestor responsável por um conjunto de bases.
- **CTL**: Cluster de Território Local — agrupamento de territórios dentro de uma base.
- **Território (Bucket)**: Subdivisão geográfica de uma base (ex: DBH5_bucket-01).
- **CEP**: Código de Endereçamento Postal — identificador de área geográfica associado a um território via `territories_index.json` e `hexagons_res7.csv`.
- **Attainment**: Percentual de vagas ideais preenchidas por parceiros ativos (Ativos / Vagas Ideais).
- **Acuracidade**: Percentual de parceiros ativos com match em relação ao total de parceiros existentes no território.
- **Cobertura**: Razão entre vagas com match e vagas ideais totais (match / total).
- **KPI_Card**: Componente visual que exibe uma métrica com valor em destaque.
- **Filter_Bar**: Barra de filtros do dashboard com seletores de BDM, Base, CTL e Território.

---

## Requisitos

### Requisito 1: Parser do Relatório Executivo

**User Story:** Como gestor, quero que o sistema leia e interprete automaticamente o arquivo `RELATORIO_EXECUTIVO.txt`, para que os dados estejam disponíveis no dashboard sem necessidade de upload manual.

#### Critérios de Aceitação

1. WHEN o Dashboard_Manager é inicializado, THE Report_Parser SHALL ler o arquivo `data/RELATORIO_EXECUTIVO.txt` via `fetch` e parsear seu conteúdo em uma estrutura de dados JavaScript.
2. THE Report_Parser SHALL extrair, para cada Base, os campos: código da base, BDM, número de territórios, demanda diária total, vagas ideais, vagas com match, vagas em aberto, cobertura, parceiros existentes (ativos, onboarding, BG checks, prospects, inativos) e attainment.
3. THE Report_Parser SHALL extrair, para cada Território dentro de uma Base, os campos: identificador do território, CTL, demanda diária, vagas totais, vagas em aberto, ativos, onboarding, BG, prospects, inativos, attainment e acuracidade.
4. IF o arquivo `RELATORIO_EXECUTIVO.txt` não puder ser carregado, THEN THE Dashboard_Manager SHALL exibir uma mensagem de erro descritiva no painel, indicando que o relatório não está disponível.
5. THE Report_Parser SHALL expor uma função `parse(text)` que recebe o conteúdo do arquivo como string e retorna um objeto estruturado com as bases e territórios.
6. FOR ALL textos válidos de relatório, parsear e depois serializar e parsear novamente SHALL produzir um objeto equivalente ao original (propriedade de round-trip).

---

### Requisito 2: Barra de Filtros Gerenciais

**User Story:** Como gestor, quero filtrar os dados do dashboard por BDM, Delivery Station (Base), CTL e Território, para que eu possa focar na área de minha responsabilidade.

#### Critérios de Aceitação

1. THE Filter_Bar SHALL exibir quatro seletores independentes: BDM, Base (Delivery Station), CTL e Território.
2. WHEN o usuário seleciona um valor no filtro de BDM, THE Filter_Bar SHALL atualizar o seletor de Base para exibir apenas as bases associadas ao BDM selecionado.
3. WHEN o usuário seleciona um valor no filtro de Base, THE Filter_Bar SHALL atualizar o seletor de Território para exibir apenas os territórios pertencentes à base selecionada.
4. WHEN o usuário seleciona um valor no filtro de CTL, THE Filter_Bar SHALL atualizar o seletor de Território para exibir apenas os territórios com o CTL correspondente.
5. THE Filter_Bar SHALL oferecer a opção "Todos" como valor padrão em cada seletor, resultando em nenhum filtro aplicado para aquela dimensão.
6. WHEN qualquer filtro é alterado, THE Dashboard_Manager SHALL recalcular e re-renderizar todos os KPI_Cards, gráficos e tabelas com os dados filtrados.
7. IF nenhum dado corresponder aos filtros selecionados, THEN THE Dashboard_Manager SHALL exibir uma mensagem "Nenhum dado encontrado para os filtros selecionados" no lugar dos componentes de visualização.

---

### Requisito 3: Sumário Geral (KPI Cards)

**User Story:** Como gestor, quero ver um sumário com os principais indicadores consolidados, para que eu possa ter uma visão rápida da situação operacional.

#### Critérios de Aceitação

1. THE Dashboard_Manager SHALL exibir KPI_Cards com os seguintes indicadores consolidados (respeitando os filtros ativos): total de bases, total de territórios, demanda diária total (pacotes/dia), total de vagas ideais, total de vagas em aberto, total de parceiros ativos, attainment médio (%) e cobertura média (%).
2. WHILE os filtros estão aplicados, THE Dashboard_Manager SHALL calcular os KPI_Cards somando ou calculando a média apenas dos dados que correspondem aos filtros ativos.
3. THE Dashboard_Manager SHALL exibir o attainment médio com uma cor de destaque verde WHEN o valor for maior ou igual a 15%, amarelo WHEN entre 5% e 14,9%, e vermelho WHEN menor que 5%.
4. THE Dashboard_Manager SHALL exibir a cobertura média com uma cor de destaque verde WHEN o valor for maior ou igual a 25%, amarelo WHEN entre 10% e 24,9%, e vermelho WHEN menor que 10%.
5. THE Dashboard_Manager SHALL exibir a data de geração do relatório (extraída do cabeçalho do `RELATORIO_EXECUTIVO.txt`) no topo do dashboard.

---

### Requisito 4: Gráficos de Visualização

**User Story:** Como gestor, quero visualizar gráficos com a distribuição dos dados por base e território, para que eu possa identificar padrões e prioridades de ação.

#### Critérios de Aceitação

1. THE Dashboard_Manager SHALL exibir um gráfico de barras horizontais com o attainment (%) por Base, ordenado do maior para o menor valor.
2. THE Dashboard_Manager SHALL exibir um gráfico de barras empilhadas com a composição de parceiros por Base (ativos, onboarding, BG checks, prospects, inativos).
3. WHEN o usuário seleciona uma Base específica no filtro, THE Dashboard_Manager SHALL exibir um gráfico de barras com o attainment por Território dentro da base selecionada.
4. THE Dashboard_Manager SHALL renderizar os gráficos utilizando a biblioteca Chart.js (carregada via CDN), sem dependências adicionais de backend.
5. IF a biblioteca Chart.js não estiver disponível, THEN THE Dashboard_Manager SHALL exibir os dados em formato de tabela como fallback.
6. WHEN o usuário passa o cursor sobre uma barra de um gráfico, THE Dashboard_Manager SHALL exibir um tooltip com o valor exato da métrica e o nome da base ou território correspondente.

---

### Requisito 5: Tabela de Detalhamento por Território

**User Story:** Como gestor, quero ver uma tabela detalhada com todas as métricas por território, para que eu possa analisar a situação de cada área individualmente.

#### Critérios de Aceitação

1. THE Dashboard_Manager SHALL exibir uma tabela com as seguintes colunas por território: Base, CTL, Território, Demanda Diária, Vagas Totais, Vagas em Aberto, Ativos, Onboarding, BG, Prospects, Inativos, Attainment (%) e Acuracidade (%).
2. WHEN o usuário clica no cabeçalho de uma coluna, THE Dashboard_Manager SHALL ordenar a tabela pela coluna selecionada em ordem crescente; WHEN clicado novamente, SHALL ordenar em ordem decrescente.
3. WHILE os filtros da Filter_Bar estão ativos, THE Dashboard_Manager SHALL exibir na tabela apenas os territórios que correspondem aos filtros selecionados.
4. THE Dashboard_Manager SHALL aplicar formatação condicional na coluna Attainment: verde para valores ≥ 15%, amarelo para valores entre 5% e 14,9%, e vermelho para valores < 5%.
5. THE Dashboard_Manager SHALL aplicar formatação condicional na coluna Acuracidade: verde para valores ≥ 70%, amarelo para valores entre 40% e 69,9%, e vermelho para valores < 40%.

---

### Requisito 6: Listagem de CEPs por Território

**User Story:** Como gestor, quero ver a lista de CEPs únicos associados a cada território, para que eu possa entender a cobertura geográfica de cada área.

#### Critérios de Aceitação

1. THE Dashboard_Manager SHALL carregar o arquivo `data/territories_index.json` para obter os `hex_ids` associados a cada território.
2. THE Dashboard_Manager SHALL carregar o arquivo `data/hexagons_res7.csv` para mapear cada `hex_id` ao seu CEP correspondente.
3. WHEN o usuário seleciona um Território específico no filtro, THE Dashboard_Manager SHALL exibir a lista de CEPs únicos associados a esse território, sem duplicatas.
4. THE Dashboard_Manager SHALL exibir o total de CEPs únicos do território selecionado como um KPI_Card adicional.
5. IF o arquivo `territories_index.json` ou `hexagons_res7.csv` não puder ser carregado, THEN THE Dashboard_Manager SHALL exibir a mensagem "CEPs não disponíveis" na seção correspondente, sem interromper o funcionamento dos demais componentes do dashboard.
6. WHERE o filtro de Território não estiver definido (opção "Todos"), THE Dashboard_Manager SHALL ocultar a seção de listagem de CEPs e exibir apenas os demais componentes do dashboard.

---

### Requisito 7: Integração com o Painel Existente

**User Story:** Como usuário do ATLAS, quero acessar o dashboard gerencial pelo mesmo botão "Estatísticas" já existente, para que a experiência de navegação seja consistente.

#### Critérios de Aceitação

1. THE Dashboard_Manager SHALL substituir o conteúdo atual do `#stats-panel` (abas Performance, Expansion, Routes) pelo novo dashboard gerencial, mantendo o mesmo comportamento de abertura/fechamento via botão `#stats-toggle-button`.
2. THE Dashboard_Manager SHALL reutilizar os estilos base do `atlas_stats_panel.css` e adicionar estilos específicos do dashboard em um novo arquivo `management_dashboard.css`.
3. WHEN o painel de estatísticas é aberto, THE Dashboard_Manager SHALL inicializar o carregamento dos dados do relatório e renderizar o dashboard em até 3 segundos em condições normais de rede local.
4. THE Dashboard_Manager SHALL ser implementado como um módulo ES6 em `js/modules/management-dashboard.js`, exportando uma função `init()` chamada pelo `js/main.js`.
5. WHILE o carregamento dos dados está em progresso, THE Dashboard_Manager SHALL exibir um indicador de carregamento (spinner) no lugar dos componentes de visualização.
