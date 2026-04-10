# Plano de Implementação: Management Dashboard

## Visão Geral

Implementação do módulo `management-dashboard.js` que substitui o conteúdo do `#stats-panel` por um painel gerencial orientado a dados do `RELATORIO_EXECUTIVO.txt`. A implementação segue a arquitetura definida no design: parser puro, barra de filtros em cascata, KPI cards, gráficos Chart.js, tabela ordenável e listagem de hex_ids por território.

## Tasks

- [x] 1. Criar estrutura de arquivos e integrar ao ATLAS.html e main.js
  - Criar `js/modules/management-dashboard.js` com esqueleto do módulo exportando `init()` e `render()`
  - Criar `management_dashboard.css` com variáveis CSS e classes base (`.md-kpi-card`, `.md-filter-bar`, `.md-table`, `.status-green`, `.status-yellow`, `.status-red`)
  - Adicionar `<link rel="stylesheet" href="management_dashboard.css">` no `ATLAS.html`
  - Adicionar `<script src="https://cdn.jsdelivr.net/npm/chart.js">` no `ATLAS.html`
  - Substituir o conteúdo interno do `#stats-inner-panel` no `ATLAS.html` pelo container do dashboard (`<div id="management-dashboard-root">`)
  - Importar e chamar `ManagementDashboard.init()` no `js/main.js` ao abrir o painel (`stats-toggle-button` click)
  - Expor `ManagementDashboard` em `window` para compatibilidade com onclick handlers
  - _Requisitos: 7.1, 7.2, 7.4_

- [x] 2. Implementar o Report_Parser
  - [x] 2.1 Implementar a função `parse(text)` em `js/modules/management-dashboard.js`
    - Extrair `generatedAt` do cabeçalho do relatório via regex
    - Extrair blocos de cada Base (código, BDM, territórios, demanda, vagas ideais, match, aberto, cobertura, parceiros, attainment)
    - Extrair blocos de cada Território dentro de cada Base (id, CTL, demanda, vagas totais, aberto, ativos, onboarding, BG, prospects, inativos, attainment, acuracidade)
    - Usar `parseFloat` com fallback `0` para todos os campos numéricos; nunca lançar exceção
    - Retornar objeto `{ generatedAt, bases: [...] }` conforme interface `ReportData` do design
    - _Requisitos: 1.1, 1.2, 1.3, 1.5_

  - [x] 2.2 Escrever testes de propriedade para o parser (Property 1: Round-trip)
    - **Property 1: Round-trip do parser**
    - Gerador: texto de relatório sintético com bases/territórios aleatórios via `fc.record`
    - Verificação: `parse(serialize(parse(text)))` produz objeto equivalente ao original
    - Tag: `// Feature: management-dashboard, Property 1: Round-trip do parser`
    - **Valida: Requisitos 1.2, 1.3, 1.6**
    - Arquivo: `js/tests/report-parser.test.js`

  - [x] 2.3 Escrever testes de exemplo para o parser
    - Parser retorna `null` para campos ausentes sem lançar exceção
    - Data de geração extraída corretamente do cabeçalho
    - Arquivo: `js/tests/report-parser.test.js`
    - _Requisitos: 1.4, 1.5_

- [x] 3. Implementar carregamento de dados e estado interno
  - [x] 3.1 Implementar `init()` com fetch do `RELATORIO_EXECUTIVO.txt` e spinner de carregamento
    - Exibir spinner (`<div class="md-spinner">`) enquanto o fetch está em progresso
    - Chamar `parse(text)` e armazenar resultado em `_reportData`
    - Em caso de erro no fetch, exibir mensagem de erro descritiva no `#management-dashboard-root`
    - Chamar `render()` após carregamento bem-sucedido
    - Garantir que `init()` só faz fetch uma vez (flag `_initialized`)
    - _Requisitos: 1.1, 1.4, 7.3, 7.5_

  - [x] 3.2 Implementar carregamento lazy do `territories_index.json`
    - Função `_loadTerritoriesIndex()` com cache em `_territoriesIndex`
    - Em caso de erro, armazenar `null` e exibir "Identificadores geográficos não disponíveis"
    - _Requisitos: 6.1, 6.5_

- [x] 4. Implementar a Filter_Bar
  - [x] 4.1 Implementar `_renderFilterBar(container)` com quatro `<select>` (BDM, Base, CTL, Território)
    - Cada select com opção "Todos" como padrão
    - Popular opções a partir de `_reportData`
    - _Requisitos: 2.1, 2.5_

  - [x] 4.2 Implementar lógica de cascata dos filtros
    - Mudar BDM → filtra opções de Base → reseta CTL e Território
    - Mudar Base → filtra opções de CTL e Território → reseta CTL e Território
    - Mudar CTL → filtra opções de Território
    - Qualquer mudança dispara `render()`
    - _Requisitos: 2.2, 2.3, 2.4, 2.6_

  - [x] 4.3 Escrever testes de propriedade para filtragem em cascata (Property 2)
    - **Property 2: Filtragem em cascata preserva subconjunto correto**
    - Gerador: `ReportData` com BDMs/Bases/CTLs aleatórios + `FilterState` aleatório via `fc.record`
    - Verificação: todos os itens no resultado satisfazem todos os filtros ativos simultaneamente
    - Tag: `// Feature: management-dashboard, Property 2: Filtragem em cascata`
    - **Valida: Requisitos 2.2, 2.3, 2.4, 2.6**
    - Arquivo: `js/tests/management-dashboard.test.js`

- [x] 5. Checkpoint — Garantir que parser, init e filtros funcionam
  - Garantir que todos os testes passam, perguntar ao usuário se houver dúvidas.

- [x] 6. Implementar KPI Cards
  - [x] 6.1 Implementar `_computeKPIs(filteredBases)` retornando objeto `KPISummary`
    - Calcular: total de bases, territórios, demanda diária, vagas ideais, vagas em aberto, parceiros ativos, attainment médio, cobertura média
    - _Requisitos: 3.1, 3.2_

  - [x] 6.2 Implementar `_renderKPICards(container, kpis)` com formatação condicional de cores
    - Attainment: `status-green` ≥ 15%, `status-yellow` 5–14.9%, `status-red` < 5%
    - Cobertura: `status-green` ≥ 25%, `status-yellow` 10–24.9%, `status-red` < 10%
    - Exibir data de geração do relatório no topo do dashboard
    - _Requisitos: 3.1, 3.3, 3.4, 3.5_

  - [x] 6.3 Escrever testes de propriedade para KPIs (Property 3)
    - **Property 3: KPIs refletem exatamente os dados filtrados**
    - Gerador: `ReportData` filtrado aleatório via `fc.array(fc.record(...))`
    - Verificação: KPIs calculados pelo módulo == KPIs calculados manualmente no teste
    - Tag: `// Feature: management-dashboard, Property 3: KPIs refletem dados filtrados`
    - **Valida: Requisitos 2.6, 3.1, 3.2**
    - Arquivo: `js/tests/management-dashboard.test.js`

  - [x] 6.4 Escrever testes de propriedade para formatação condicional (Properties 4 e 5)
    - **Property 4: Formatação condicional de attainment é determinística**
    - Gerador: `fc.float({ min: 0, max: 1 })` para attainment
    - Verificação: classe CSS corresponde ao threshold sem sobreposição ou lacuna
    - Tag: `// Feature: management-dashboard, Property 4: Formatação condicional attainment`
    - **Valida: Requisitos 3.3, 5.4**
    - **Property 5: Formatação condicional de cobertura e acuracidade é determinística**
    - Gerador: `fc.float({ min: 0, max: 1 })` para cobertura e acuracidade
    - Verificação: classe CSS corresponde ao threshold correto
    - Tag: `// Feature: management-dashboard, Property 5: Formatação condicional cobertura/acuracidade`
    - **Valida: Requisitos 3.4, 5.5**
    - Arquivo: `js/tests/management-dashboard.test.js`

- [x] 7. Implementar Gráficos com Chart.js
  - [x] 7.1 Implementar `_renderCharts(container, filteredBases, selectedBase)`
    - Gráfico de barras horizontais: attainment (%) por Base, ordenado do maior para o menor
    - Gráfico de barras empilhadas: composição de parceiros por Base (ativos, onboarding, BG, prospects, inativos)
    - Quando uma Base específica está selecionada: gráfico de barras com attainment por Território
    - Destruir instâncias anteriores (`chart.destroy()`) antes de criar novas
    - Tooltips com valor exato e nome da base/território
    - _Requisitos: 4.1, 4.2, 4.3, 4.4, 4.6_

  - [x] 7.2 Implementar fallback de tabela quando Chart.js não está disponível
    - Verificar `typeof Chart === 'undefined'` antes de renderizar
    - Renderizar tabela HTML simples com os mesmos dados como fallback
    - _Requisito: 4.5_

  - [x] 7.3 Escrever testes de propriedade para dados do gráfico por território (Property 8)
    - **Property 8: Dados do gráfico por território correspondem ao filtro de base**
    - Gerador: `ReportData` com múltiplas bases + base selecionada aleatória via `fc.record`
    - Verificação: dados passados ao gráfico contêm exatamente os territórios da base selecionada
    - Tag: `// Feature: management-dashboard, Property 8: Dados do gráfico por território`
    - **Valida: Requisito 4.3**
    - Arquivo: `js/tests/management-dashboard.test.js`

- [x] 8. Implementar Tabela de Detalhamento por Território
  - [x] 8.1 Implementar `_renderTerritoryTable(container, filteredTerritories)`
    - Colunas: Base, CTL, Território, Demanda Diária, Vagas Totais, Vagas em Aberto, Ativos, Onboarding, BG, Prospects, Inativos, Attainment (%), Acuracidade (%)
    - Formatação condicional: Attainment (verde ≥ 15%, amarelo 5–14.9%, vermelho < 5%) e Acuracidade (verde ≥ 70%, amarelo 40–69.9%, vermelho < 40%)
    - Exibir mensagem "Nenhum dado encontrado para os filtros selecionados" quando lista vazia
    - _Requisitos: 5.1, 5.3, 5.4, 5.5, 2.7_

  - [x] 8.2 Implementar ordenação por clique no cabeçalho da tabela
    - Primeiro clique: ordem crescente; segundo clique na mesma coluna: ordem decrescente
    - Armazenar estado de ordenação em `_sortState`
    - _Requisito: 5.2_

  - [x] 8.3 Escrever testes de propriedade para ordenação da tabela (Property 6)
    - **Property 6: Ordenação da tabela é correta e reversível**
    - Gerador: array de `TerritoryData` com valores aleatórios + coluna aleatória via `fc.array` e `fc.constantFrom`
    - Verificação: array ordenado é monotônico; ordenar duas vezes pela mesma coluna restaura a ordem original
    - Tag: `// Feature: management-dashboard, Property 6: Ordenação da tabela`
    - **Valida: Requisito 5.2**
    - Arquivo: `js/tests/management-dashboard.test.js`

- [x] 9. Implementar Listagem de Identificadores Geográficos por Território
  - [x] 9.1 Implementar `_renderCepListing(container, selectedTerritory)`
    - Ocultar seção quando filtro de Território é "Todos"
    - Carregar `territories_index.json` via `_loadTerritoriesIndex()` (lazy com cache)
    - Exibir lista de `hex_ids` únicos do território selecionado (sem duplicatas)
    - Exibir total de hex_ids como KPI_Card adicional
    - Em caso de erro no fetch, exibir "Identificadores geográficos não disponíveis"
    - _Requisitos: 6.1, 6.3, 6.4, 6.5, 6.6_

  - [x] 9.2 Escrever testes de propriedade para unicidade de hex_ids (Property 7)
    - **Property 7: Lista de hex_ids por território não contém duplicatas**
    - Gerador: array de `hex_ids` com duplicatas aleatórias via `fc.array(fc.string())`
    - Verificação: `new Set(result).size === result.length`
    - Tag: `// Feature: management-dashboard, Property 7: Unicidade de hex_ids`
    - **Valida: Requisito 6.3**
    - Arquivo: `js/tests/management-dashboard.test.js`

- [x] 10. Implementar `render()` e integrar todos os componentes
  - Implementar `render()` que aplica `_activeFilters` sobre `_reportData` e chama todos os sub-renderizadores em sequência: `_renderFilterBar`, `_renderKPICards`, `_renderCharts`, `_renderTerritoryTable`, `_renderCepListing`
  - Garantir que `render()` é chamado a cada mudança de filtro
  - _Requisitos: 2.6, 7.1_

- [x] 11. Checkpoint final — Garantir que todos os testes passam
  - Garantir que todos os testes passam, perguntar ao usuário se houver dúvidas.

## Notas

- Tasks marcadas com `*` são opcionais e podem ser puladas para um MVP mais rápido
- Cada task referencia requisitos específicos para rastreabilidade
- Os arquivos `hexagons_res7.csv` e `hexagons_res7.geojson` **não devem ser usados** — a listagem geográfica usa apenas `territories_index.json` (hex_ids H3)
- Testes de propriedade usam **fast-check** com mínimo de 100 iterações por propriedade
- Checkpoints garantem validação incremental antes de avançar para a próxima fase
