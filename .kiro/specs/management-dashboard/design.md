# Design Técnico: Management Dashboard

## Visão Geral

O Management Dashboard substitui o conteúdo atual do `#stats-panel` (abas Performance, Expansion, Routes) por um painel gerencial orientado a dados do `RELATORIO_EXECUTIVO.txt`. O objetivo é oferecer a BDMs e líderes de operação uma visão consolidada de KPIs, gráficos e detalhamento por território, acessível pelo mesmo botão "Estatísticas" já existente no ATLAS.

A feature é implementada como um módulo ES6 (`js/modules/management-dashboard.js`) que exporta `init()`, chamado pelo `js/main.js`. Nenhum framework frontend é introduzido — a stack permanece HTML/CSS/JS vanilla com Chart.js via CDN.

---

## Arquitetura

```mermaid
graph TD
    A[ATLAS.html - #stats-toggle-button] -->|click| B[main.js - init()]
    B --> C[management-dashboard.js]
    C --> D[Report_Parser - parse()]
    C --> E[Filter_Bar]
    C --> F[KPI_Cards]
    C --> G[Charts - Chart.js]
    C --> H[Territory Table]
    C --> I[CEP Listing]
    D -->|fetch| J[data/RELATORIO_EXECUTIVO.txt]
    I -->|fetch| K[data/territories_index.json]
```

### Fluxo de dados

1. `init()` é chamado quando o painel é aberto pela primeira vez
2. `Report_Parser.parse()` faz fetch do relatório e retorna a estrutura de dados
3. `Filter_Bar` é populada com os valores únicos extraídos (BDMs, Bases, CTLs, Territórios)
4. Qualquer mudança de filtro dispara `render()` que recalcula KPIs, gráficos e tabela
5. Quando um Território específico é selecionado, os `hex_ids` do `territories_index.json` são exibidos como identificadores geográficos

### Decisão técnica: listagem de identificadores por território

O `territories_index.json` contém `hex_ids` H3 (res7) por território. Esses `hex_ids` são os identificadores geográficos disponíveis no sistema e serão exibidos como a "lista de CEPs" do Requisito 6. Os arquivos `hexagons_res7.csv` e `hexagons_res7.geojson` **não são utilizados** — eles servem a outro propósito no projeto e não fazem parte deste módulo.

---

## Componentes e Interfaces

### `management-dashboard.js` — módulo principal

```js
// Interface pública
export function init()   // chamado pelo main.js ao abrir o painel pela primeira vez
export function render() // re-renderiza todos os componentes com os filtros ativos
```

Estado interno do módulo:
```js
let _reportData = null;      // { generatedAt, bases: [...] }
let _territoriesIndex = null; // { [territory_id]: { hex_ids: string[], ... } } — carregado de territories_index.json
let _activeFilters = { bdm: 'all', base: 'all', ctl: 'all', territory: 'all' };
let _sortState = { column: null, direction: 'asc' };
let _charts = {};            // instâncias Chart.js ativas
```

### `Report_Parser` — sub-módulo interno

```js
// Função pura — não faz fetch, recebe string e retorna objeto
export function parse(text)
// Retorna:
// {
//   generatedAt: string,       // "09/04/2026 18:14"
//   bases: [{
//     code: string,            // "DBH5"
//     bdm: string,             // "BH"
//     numTerritories: number,
//     dailyDemand: number,
//     idealSlots: number,
//     matchedSlots: number,
//     openSlots: number,
//     coverage: number,        // 0.055 (decimal)
//     partners: { active, onboarding, bgChecks, prospects, inactive },
//     attainment: number,      // 0.038 (decimal)
//     territories: [{
//       id: string,            // "DBH5_bucket-01"
//       ctl: string,           // "CTL-A"
//       dailyDemand: number,
//       totalSlots: number,
//       openSlots: number,
//       active: number,
//       onboarding: number,
//       bg: number,
//       prospects: number,
//       inactive: number,
//       attainment: number,    // decimal
//       accuracy: number       // decimal
//     }]
//   }]
// }
```

### `Filter_Bar` — componente de filtros

Renderiza quatro `<select>` no topo do dashboard. A lógica de cascata é:
- Mudar BDM → filtra opções de Base → reseta CTL e Território
- Mudar Base → filtra opções de CTL e Território → reseta CTL e Território
- Mudar CTL → filtra opções de Território

### `KPI_Cards` — componente de sumário

Calcula e renderiza 8 cards a partir dos dados filtrados. Attainment e Cobertura recebem classe CSS de cor baseada em thresholds.

### `Charts` — componente de gráficos

Gerencia instâncias Chart.js. Antes de criar um novo gráfico, destrói a instância anterior para evitar memory leaks (`chart.destroy()`).

### `TerritoryTable` — componente de tabela

Renderiza tabela com ordenação por clique no cabeçalho. Aplica formatação condicional via classes CSS.

### `CepListing` — componente de CEPs

Visível apenas quando um Território específico está selecionado. Carrega `territories_index.json` sob demanda (lazy load com cache).

---

## Modelos de Dados

### ReportData

```ts
interface ReportData {
  generatedAt: string;
  bases: BaseData[];
}

interface BaseData {
  code: string;
  bdm: string;
  numTerritories: number;
  dailyDemand: number;
  idealSlots: number;
  matchedSlots: number;
  openSlots: number;
  coverage: number;          // decimal 0-1
  partners: PartnerCounts;
  attainment: number;        // decimal 0-1
  territories: TerritoryData[];
}

interface PartnerCounts {
  active: number;
  onboarding: number;
  bgChecks: number;
  prospects: number;
  inactive: number;
}

interface TerritoryData {
  id: string;
  ctl: string;
  dailyDemand: number;
  totalSlots: number;
  openSlots: number;
  active: number;
  onboarding: number;
  bg: number;
  prospects: number;
  inactive: number;
  attainment: number;        // decimal 0-1
  accuracy: number;          // decimal 0-1
}
```

### FilterState

```ts
interface FilterState {
  bdm: string;        // "all" | valor específico
  base: string;       // "all" | código da base
  ctl: string;        // "all" | valor CTL
  territory: string;  // "all" | id do território
}
```

### KPISummary

```ts
interface KPISummary {
  totalBases: number;
  totalTerritories: number;
  totalDailyDemand: number;
  totalIdealSlots: number;
  totalOpenSlots: number;
  totalActivePartners: number;
  avgAttainment: number;     // decimal 0-1
  avgCoverage: number;       // decimal 0-1
}
```

---

## Propriedades de Corretude

*Uma propriedade é uma característica ou comportamento que deve ser verdadeiro em todas as execuções válidas do sistema — essencialmente, uma declaração formal sobre o que o sistema deve fazer. Propriedades servem como ponte entre especificações legíveis por humanos e garantias de corretude verificáveis por máquina.*

### Propriedade 1: Round-trip do parser

*Para qualquer* texto de relatório válido, parsear o texto, serializar o resultado para JSON e parsear novamente deve produzir um objeto equivalente ao original — todos os campos de bases e territórios devem ser preservados.

**Valida: Requisitos 1.2, 1.3, 1.6**

### Propriedade 2: Filtragem em cascata preserva subconjunto correto

*Para qualquer* conjunto de dados e qualquer combinação de filtros (BDM, Base, CTL, Território), os dados resultantes devem ser um subconjunto dos dados originais onde cada item satisfaz todos os filtros ativos simultaneamente.

**Valida: Requisitos 2.2, 2.3, 2.4, 2.6**

### Propriedade 3: KPIs refletem exatamente os dados filtrados

*Para qualquer* conjunto de dados filtrados, os valores dos KPI_Cards (total de bases, territórios, demanda, vagas, parceiros ativos, attainment médio, cobertura média) devem ser iguais aos valores calculados manualmente a partir do mesmo subconjunto filtrado.

**Valida: Requisitos 2.6, 3.1, 3.2**

### Propriedade 4: Formatação condicional de attainment é determinística

*Para qualquer* valor numérico de attainment, a classe CSS de cor aplicada deve ser: `status-green` se ≥ 0.15, `status-yellow` se ≥ 0.05 e < 0.15, `status-red` se < 0.05 — sem sobreposição ou lacuna entre os intervalos.

**Valida: Requisitos 3.3, 5.4**

### Propriedade 5: Formatação condicional de cobertura e acuracidade é determinística

*Para qualquer* valor numérico de cobertura (thresholds: 0.25 / 0.10) e acuracidade (thresholds: 0.70 / 0.40), a classe CSS de cor aplicada deve corresponder ao intervalo correto sem sobreposição ou lacuna.

**Valida: Requisitos 3.4, 5.5**

### Propriedade 6: Ordenação da tabela é correta e reversível

*Para qualquer* coluna da tabela e qualquer conjunto de dados, ordenar por aquela coluna deve produzir uma sequência onde cada elemento é ≤ (ou ≥ na ordem inversa) ao próximo, e ordenar duas vezes pela mesma coluna deve restaurar a ordem original.

**Valida: Requisito 5.2**

### Propriedade 7: Lista de CEPs por território não contém duplicatas

*Para qualquer* território com `hex_ids` associados (incluindo casos onde múltiplos hex_ids mapeiam para o mesmo identificador), a lista de identificadores geográficos retornada deve conter apenas valores únicos.

**Valida: Requisito 6.3**

### Propriedade 8: Dados do gráfico por território correspondem ao filtro de base

*Para qualquer* base selecionada no filtro, os dados passados ao gráfico de attainment por território devem conter exatamente os territórios pertencentes àquela base — nem mais, nem menos.

**Valida: Requisito 4.3**

---

## Tratamento de Erros

| Cenário | Comportamento |
|---|---|
| Fetch do `RELATORIO_EXECUTIVO.txt` falha | Exibe mensagem de erro descritiva no `#stats-panel`, não bloqueia o restante do ATLAS |
| Fetch do `territories_index.json` falha | Exibe "Identificadores geográficos não disponíveis" na seção de CEPs, demais componentes funcionam normalmente |
| Chart.js não disponível no `window` | Renderiza tabela de fallback com os mesmos dados |
| Texto do relatório com formato inesperado | Parser retorna `null` para campos não encontrados, sem lançar exceção |
| Filtros sem dados correspondentes | Exibe mensagem "Nenhum dado encontrado para os filtros selecionados" |

### Estratégia de parsing defensivo

O `Report_Parser` usa regex com grupos opcionais e `parseFloat` com fallback para `0`. Nunca lança exceção — retorna `null` para campos não parseáveis. O chamador é responsável por validar o resultado.

---

## Estratégia de Testes

### Abordagem dual

A feature combina testes de exemplo (para comportamentos específicos de UI e integração) com testes baseados em propriedades (para lógica de parsing, filtragem e formatação).

### Testes de propriedade (property-based)

Biblioteca: **fast-check** (JavaScript, disponível via npm/CDN).
Configuração: mínimo 100 iterações por propriedade.
Tag de referência: `// Feature: management-dashboard, Property N: <texto>`

As 8 propriedades definidas acima são implementadas como testes fast-check:

- **P1** — Gerador: texto de relatório sintético com bases/territórios aleatórios. Verificação: `parse(serialize(parse(text)))` produz objeto equivalente.
- **P2** — Gerador: `ReportData` com BDMs/Bases/CTLs aleatórios + `FilterState` aleatório. Verificação: todos os itens no resultado satisfazem os filtros.
- **P3** — Gerador: `ReportData` filtrado aleatório. Verificação: KPIs calculados pelo módulo == KPIs calculados pelo teste.
- **P4** — Gerador: `fc.float({ min: 0, max: 1 })`. Verificação: classe CSS corresponde ao threshold.
- **P5** — Gerador: `fc.float({ min: 0, max: 1 })` para cobertura e acuracidade. Verificação: classe CSS corresponde ao threshold.
- **P6** — Gerador: array de `TerritoryData` com valores aleatórios + coluna aleatória. Verificação: array ordenado é monotônico; ordenar duas vezes restaura a ordem.
- **P7** — Gerador: array de `hex_ids` com duplicatas aleatórias. Verificação: `new Set(result).size === result.length`.
- **P8** — Gerador: `ReportData` com múltiplas bases + base selecionada aleatória. Verificação: dados do gráfico contêm exatamente os territórios da base selecionada.

### Testes de exemplo (unit/integration)

- Parser retorna `null` para campos ausentes sem lançar exceção
- Fetch com erro exibe mensagem de erro no DOM
- Valor padrão dos filtros é "Todos"
- Mensagem "Nenhum dado encontrado" quando filtros não têm correspondência
- Spinner visível durante carregamento (mock de fetch com delay)
- Seção de CEPs oculta quando filtro de Território é "Todos"
- Fallback de tabela quando Chart.js não está disponível
- Data de geração do relatório extraída corretamente do cabeçalho

### Testes de integração

- Fetch real do `RELATORIO_EXECUTIVO.txt` retorna conteúdo parseável
- Fetch real do `territories_index.json` retorna estrutura com `hex_ids`
- Dashboard inicializa em menos de 3 segundos em rede local

### Arquivos de teste

```
js/tests/management-dashboard.test.js   # testes de propriedade e exemplos
js/tests/report-parser.test.js          # testes focados no parser
```
