# Design Document — Area Analysis Panel

## Overview

Esta feature transforma a aba "Destaques" do painel de controles do ATLAS em um painel de "Análise de Área". O objetivo é permitir que analistas de expansão filtrem prospects por Estado e Decisão e visualizem estatísticas consolidadas em um popup flutuante sobre o mapa.

A mudança envolve duas camadas:

1. **Backend (Python)**: refatorar o campo `decision` de `PartnerMetrics` de uma string descritiva longa para um valor binário `"Go"` / `"No Go"`, adicionando um campo `reason` separado com o motivo específico. O `dados_mapa.json` passa a serializar ambos os campos.

2. **Frontend (JS/HTML)**: substituir o conteúdo da div `#highlight-content` por filtros de Estado e Decisão, implementar a lógica de filtragem e cálculo de estatísticas, renderizar o `Stats_Popup` e fechar o popup automaticamente ao trocar de aba.

---

## Architecture

```mermaid
graph TD
    subgraph Backend
        PM[PartnerMetrics<br/>decision: Go/No Go<br/>reason: string]
        P3[phase3_partner_fit.py<br/>_match_station()]
        P5[phase5_reports.py<br/>_write_geojson()]
        GEO[optimization_data.geojson<br/>PARTNER_POINT.properties<br/>decision + reason]
        P3 -->|preenche decision + reason| PM
        PM -->|serializado por| P5
        P5 -->|gera| GEO
    end

    subgraph Frontend
        GEO -->|carregado por| DM[data-manager.js<br/>_aggregateOptimizationData()]
        DM -->|partner.decision = info.properties.decision<br/>partner.reason = info.properties.reason| ST[state.allMarkersData]
        ST -->|subscribe allMarkersData| UI[ui-manager.js<br/>populateAreaAnalysisFilters()]
        UI -->|popula selects| HTML[ATLAS.html<br/>#highlight-content]
        HTML -->|clique Analisar Área| FILTER[filterAndAnalyse()<br/>ui-manager.js]
        FILTER -->|dados filtrados| STATS[renderStatsPopup()<br/>ui-manager.js]
        STATS -->|insere no DOM| POPUP[Stats_Popup<br/>div#stats-area-popup]
        TABS[Bootstrap tab events<br/>main.js] -->|shown.bs.tab| CLOSE[closeStatsPopup()]
    end
```

O fluxo de dados é unidirecional: backend gera → GeoJSON armazena → frontend consome. Não há chamadas de API em tempo real; toda a lógica de filtragem e cálculo ocorre no cliente sobre `state.allMarkersData`.

---

## Components and Interfaces

### Backend

#### `PartnerMetrics` (models.py)

Adicionar campo `reason: str = ""` ao dataclass. O campo `decision` já existe mas será restrito aos valores `"Go"` / `"No Go"` pela lógica da Fase 3.

```python
@dataclass
class PartnerMetrics:
    # ... campos existentes ...
    decision: str = ""   # "Go" | "No Go" | "" (para não-prospects)
    reason: str   = ""   # "Seguir cadastro" | "Sem oportunidade próxima" |
                         # "Sem oportunidade próxima na borda" | "Fora de jurisdição"
```

#### `phase3_partner_fit.py` — mapeamento de decisões

A função `_match_station()` atribui `decision` e agora também `reason` a cada `PartnerMetrics`. O mapeamento completo:

| Situação do parceiro | `decision` | `reason` |
|---|---|---|
| Matched com vaga (qualquer status) | `"Go"` | `"Seguir cadastro"` |
| Prospect sem vaga próxima (dentro da jurisdição) | `"No Go"` | `"Sem oportunidade próxima"` |
| Prospect de borda sem vaga (fora de jurisdição, próximo a slot) | `"No Go"` | `"Sem oportunidade próxima na borda"` |
| Prospect fora de jurisdição completamente | `"No Go"` | `"Fora de jurisdição"` |
| Parceiros não-Prospect (Active, Onboarding, etc.) | `""` | `""` |

> **Decisão de design**: apenas Prospects recebem `decision`/`reason` populados. Para os demais status, os campos ficam vazios — o frontend filtra por `status === "Prospect"` antes de usar esses campos.

#### `phase5_reports.py` — serialização no GeoJSON

A função `_write_geojson()` serializa cada `PartnerMetrics` como uma feature `PARTNER_POINT` no `optimization_data.geojson`. O campo `decision` já é serializado (`"decision": p.decision`). É necessário adicionar o campo `reason` na mesma feature:

```python
# Em _write_geojson(), bloco de PARTNER_POINT — adicionar "reason" junto com "decision"
"properties": {
    ...
    "decision": p.decision,
    "reason":   p.reason,   # campo a adicionar
    ...
}
```

O `dados_mapa.json` (gerado pelo `main.py`/`JsonGenerator` a partir do Excel) contém um campo `decision_status` que serve apenas para filtrar parceiros com status "Exited - Regretted". Esse campo **não** é o `decision` da Fase 3 e não deve ser confundido com ele.

### Frontend

#### `ATLAS.html` — `#highlight-content`

Substituir o conteúdo atual da aba por:

```html
<!-- Aba Análise de Área -->
<div class="tab-pane fade" id="highlight-content" role="tabpanel">
  <p class="text-muted small mb-2">
    <i class="fas fa-lock"></i> Filtro fixo: Status = Prospect
  </p>
  <div class="form-group">
    <label for="areaStateFilter">Estado:</label>
    <select class="form-control form-control-sm" id="areaStateFilter"></select>
  </div>
  <div class="form-group">
    <label for="areaDecisionFilter">Decisão:</label>
    <select class="form-control form-control-sm" id="areaDecisionFilter">
      <option value="all" selected>Todos</option>
      <option value="Go">Go</option>
      <option value="No Go">No Go</option>
    </select>
  </div>
  <button class="btn btn-primary btn-sm btn-block" id="analyseAreaBtn"
          onclick="UIManager.analyseArea()">
    <i class="fas fa-chart-pie"></i> Analisar Área
  </button>
</div>
```

A aba de navegação muda de rótulo:
```html
<!-- antes -->
<a class="nav-link" data-toggle="tab" href="#highlight-content">
  <i class="fas fa-highlighter"></i> Destaques
</a>
<!-- depois -->
<a class="nav-link" data-toggle="tab" href="#highlight-content">
  <i class="fas fa-map-marked-alt"></i> Análise de Área
</a>
```

#### `ui-manager.js` — novas funções exportadas

```typescript
// Popula o select de Estado com valores únicos e ordenados dos Prospects
export function populateAreaAnalysisFilters(): void

// Filtra allMarkersData e exibe o Stats_Popup
export function analyseArea(): void

// Fecha e remove o Stats_Popup do DOM (se existir)
export function closeStatsPopup(): void
```

**`populateAreaAnalysisFilters()`**

```javascript
export function populateAreaAnalysisFilters() {
    const prospects = state.allMarkersData.filter(m => m.status === 'Prospect');
    const states = [...new Set(prospects.map(m => m.state).filter(Boolean))].sort();
    const sel = document.getElementById('areaStateFilter');
    if (!sel) return;
    sel.innerHTML = '<option value="all" selected>Todos</option>';
    states.forEach(s => sel.innerHTML += `<option value="${s}">${s}</option>`);
}
```

**`analyseArea()`**

```javascript
export function analyseArea() {
    const selState    = document.getElementById('areaStateFilter')?.value ?? 'all';
    const selDecision = document.getElementById('areaDecisionFilter')?.value ?? 'all';

    let filtered = state.allMarkersData.filter(m => m.status === 'Prospect');
    if (selState    !== 'all') filtered = filtered.filter(m => m.state    === selState);
    if (selDecision !== 'all') filtered = filtered.filter(m => m.decision === selDecision);

    renderStatsPopup(filtered, { state: selState, decision: selDecision });
}
```

**`renderStatsPopup(prospects, filters)`** — função interna

Calcula as estatísticas e injeta o popup no DOM:

```javascript
function renderStatsPopup(prospects, { state: stateFilter, decision: decisionFilter }) {
    closeStatsPopup(); // remove popup anterior se existir

    const total   = prospects.length;
    const goCount = prospects.filter(p => p.decision === 'Go').length;
    const approvalRate = total > 0 ? ((goCount / total) * 100).toFixed(1) : '0.0';

    const NO_GO_REASONS = [
        'Sem oportunidade próxima',
        'Sem oportunidade próxima na borda',
        'Fora de jurisdição',
    ];
    const reasonCounts = {};
    NO_GO_REASONS.forEach(r => {
        reasonCounts[r] = prospects.filter(p => p.decision === 'No Go' && p.reason === r).length;
    });

    const stateLabel    = stateFilter    === 'all' ? 'Todos' : stateFilter;
    const decisionLabel = decisionFilter === 'all' ? 'Todos' : decisionFilter;

    const reasonRows = NO_GO_REASONS.map(r => {
        const count = reasonCounts[r];
        const pct   = total > 0 ? ((count / total) * 100).toFixed(1) : '0.0';
        return `<tr><td>${r}</td><td>${count}</td><td>${pct}%</td></tr>`;
    }).join('');

    const emptyMsg = total === 0
        ? '<p class="text-muted">Nenhum prospect encontrado para os filtros selecionados.</p>'
        : '';

    const html = `
      <div id="stats-area-popup" style="
        position:fixed; top:80px; right:20px; z-index:9999;
        background:#fff; padding:16px; border-radius:8px;
        box-shadow:0 2px 12px rgba(0,0,0,0.2); min-width:320px; max-width:420px;
        font-size:13px;">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;">
          <b>Análise de Área</b>
          <button onclick="UIManager.closeStatsPopup()"
                  style="border:none;background:none;font-size:1.4em;cursor:pointer;">&times;</button>
        </div>
        <p class="text-muted mb-1">Estado: <b>${stateLabel}</b> &nbsp;|&nbsp; Decisão: <b>${decisionLabel}</b></p>
        <hr class="my-2">
        ${emptyMsg}
        ${total > 0 ? `
        <table style="width:100%;margin-bottom:8px;">
          <tr><td><b>Total de Prospects</b></td><td>${total}</td></tr>
          <tr><td><b>Aprovados (Go)</b></td><td>${goCount}</td></tr>
          <tr><td><b>Índice de Aprovação</b></td><td>${approvalRate}%</td></tr>
        </table>
        <b>Motivos de Não Aprovação:</b>
        <table style="width:100%;margin-top:4px;">
          <thead><tr><th>Motivo</th><th>#</th><th>%</th></tr></thead>
          <tbody>${reasonRows}</tbody>
        </table>` : ''}
      </div>`;

    document.body.insertAdjacentHTML('beforeend', html);
}
```

**`closeStatsPopup()`**

```javascript
export function closeStatsPopup() {
    document.getElementById('stats-area-popup')?.remove();
}
```

#### `data-manager.js` — `_aggregateOptimizationData()`

A função já injeta `partner.decision = info.properties.decision` a partir das features `PARTNER_POINT` do `optimization_data.geojson`. É necessário adicionar a injeção de `partner.reason`:

```javascript
// Em _aggregateOptimizationData() — adicionar reason junto com decision
partner.decision = info.properties.decision;
partner.reason   = info.properties.reason;   // campo a adicionar
```

#### `main.js` — wiring

1. Adicionar `populateAreaAnalysisFilters` e `closeStatsPopup` ao subscriber de `allMarkersData`:

```javascript
subscribe('allMarkersData', () => {
    populateFilters();
    setupAutocomplete();
    populateAreaAnalysisFilters();   // novo
});
```

2. Registrar listener de troca de aba para fechar o popup:

```javascript
document.querySelectorAll('#controlTabs a[data-toggle="tab"]').forEach(tab => {
    tab.addEventListener('shown.bs.tab', e => {
        const target = e.target.getAttribute('href');
        if (target !== '#highlight-content') closeStatsPopup();
    });
});
```

3. Expor as novas funções no namespace global:

```javascript
window.UIManager = {
    // ... existentes ...
    analyseArea,
    closeStatsPopup,
};
```

---

## Data Models

### `PartnerMetrics` (backend/models.py)

| Campo | Tipo | Valores | Descrição |
|---|---|---|---|
| `decision` | `str` | `"Go"`, `"No Go"`, `""` | Decisão binária para Prospects; vazio para outros status |
| `reason` | `str` | ver tabela abaixo | Motivo específico da decisão |

**Valores válidos de `reason`:**

| `decision` | `reason` |
|---|---|
| `"Go"` | `"Seguir cadastro"` |
| `"No Go"` | `"Sem oportunidade próxima"` |
| `"No Go"` | `"Sem oportunidade próxima na borda"` |
| `"No Go"` | `"Fora de jurisdição"` |
| `""` | `""` |

### `optimization_data.geojson` — feature PARTNER_POINT de um Prospect

```json
{
  "type": "Feature",
  "geometry": { "type": "Point", "coordinates": [-46.6333, -23.5505] },
  "properties": {
    "type": "PARTNER_POINT",
    "salesforce_id": "0011X00001AbCdEfG",
    "name": "Parceiro Exemplo",
    "status": "Prospect",
    "entity": "PROSPECT",
    "delivery_station": "SAO5",
    "decision": "No Go",
    "reason": "Sem oportunidade próxima",
    ...
  }
}
```

> **Nota**: O `dados_mapa.json` (gerado pelo `main.py`/`JsonGenerator` a partir do Excel) contém um campo `decision_status` que serve apenas para filtrar parceiros "Exited - Regretted". Esse campo **não** é o `decision` da Fase 3 e não é consumido pelo painel de Análise de Área.

### Filtros ativos (estado local da UI)

Não há estado persistido — os valores dos selects são lidos diretamente do DOM no momento do clique em "Analisar Área".

---

## Correctness Properties

*A property is a characteristic or behavior that should hold true across all valid executions of a system — essentially, a formal statement about what the system should do. Properties serve as the bridge between human-readable specifications and machine-verifiable correctness guarantees.*

### Property 1: Select de Estado reflete exatamente os estados únicos dos Prospects

*Para qualquer* conjunto de dados em `state.allMarkersData`, após chamar `populateAreaAnalysisFilters()`, as opções do select `#areaStateFilter` devem ser exatamente `["Todos"] + sorted(unique(state for p in data if p.status === "Prospect" and p.state))`.

**Validates: Requirements 2.1, 2.2, 2.5**

---

### Property 2: Filtragem combinada satisfaz todos os predicados simultaneamente

*Para qualquer* dataset de parceiros e qualquer combinação de valores de filtro (estado ∈ estados válidos ∪ "all", decisão ∈ {"Go", "No Go", "all"}), o resultado de `analyseArea()` deve conter apenas registros que satisfaçam simultaneamente: `status === "Prospect"` AND (`state === filtroEstado` OR filtroEstado === "all") AND (`decision === filtroDecisão` OR filtroDecisão === "all").

**Validates: Requirements 3.1, 4.2, 4.3, 4.4**

---

### Property 3: Estatísticas do popup são aritmeticamente corretas

*Para qualquer* array de prospects filtrados, os valores exibidos no `Stats_Popup` devem satisfazer: `total === prospects.length`, `goCount === prospects.filter(p => p.decision === "Go").length`, `approvalRate === (goCount / total * 100)` (com uma casa decimal), e para cada `reason`, `reasonCount === prospects.filter(p => p.decision === "No Go" && p.reason === reason).length` e `reasonPct === (reasonCount / total * 100)`.

**Validates: Requirements 5.1, 5.2, 5.3, 5.4, 5.5**

---

### Property 4: Filtros ativos são exibidos corretamente no popup

*Para qualquer* combinação de valores de filtro (estado, decisão), o cabeçalho do `Stats_Popup` deve conter exatamente os valores selecionados (ou "Todos" quando o filtro é "all").

**Validates: Requirements 5.7**

---

### Property 5: Decisão binária é consistente com o resultado do matching

*Para qualquer* parceiro com `status === "Prospect"` processado pela Fase 3, se o parceiro foi matched com uma vaga então `decision === "Go"` e `reason === "Seguir cadastro"`; caso contrário `decision === "No Go"` e `reason` é um dos três valores válidos de não-aprovação.

**Validates: Requirements 6.1, 6.2, 6.3, 6.5, 6.6**

---

### Property 6: Serialização preserva decision e reason

*Para qualquer* `PartnerMetrics` com `decision` e `reason` preenchidos, serializar para `optimization_data.geojson` via `phase5_reports._write_geojson()` e ler de volta as `properties` da feature `PARTNER_POINT` deve produzir os mesmos valores nos campos `decision` e `reason`.

**Validates: Requirements 6.4**

---

## Error Handling

| Cenário | Comportamento esperado |
|---|---|
| `state.allMarkersData` vazio ao abrir a aba | Select de Estado exibe apenas "Todos"; botão "Analisar Área" funciona e exibe popup com mensagem de ausência de prospects |
| Nenhum Prospect após aplicar filtros | `Stats_Popup` exibe mensagem "Nenhum prospect encontrado para os filtros selecionados." em vez das tabelas de métricas |
| Campo `state` nulo em um Prospect | O registro é ignorado na população do select (filtrado por `filter(Boolean)`) |
| Campo `decision` ausente em um Prospect (dados legados) | Tratado como `""` — não conta como "Go" nem como "No Go"; o total ainda inclui o registro |
| Popup já aberto ao clicar "Analisar Área" novamente | `closeStatsPopup()` é chamado antes de renderizar o novo popup, garantindo que apenas um popup exista por vez |
| Troca de aba com popup fechado | `closeStatsPopup()` chama `?.remove()` — operação segura se o elemento não existe |

---

## Testing Strategy

### Abordagem dual

- **Testes unitários (exemplo-based)**: verificam comportamentos específicos e interações de UI
- **Testes de propriedade (property-based)**: verificam invariantes universais sobre lógica de filtragem e cálculo

### Biblioteca de PBT

Para o frontend JavaScript: **fast-check** (`npm install --save-dev fast-check`).
Para o backend Python: **hypothesis** (`pip install hypothesis`).

### Testes unitários (exemplos e edge cases)

| Teste | Critério |
|---|---|
| Aba exibe rótulo "Análise de Área" | Req 1.1 |
| `id="highlight-content"` existe no DOM | Req 1.2 |
| Conteúdo antigo (eligiblePackagesOp) não existe | Req 1.3 |
| Select de Decisão tem opções fixas ["Todos", "Go", "No Go"] | Req 2.3 |
| Texto informativo de filtro fixo está presente | Req 2.6 |
| Botão "Analisar Área" existe no DOM | Req 4.1 |
| Popup aparece no canto superior direito ao clicar | Req 4.5 |
| Botão × remove popup do DOM | Req 5.6 |
| Trocar para aba Filtros remove popup | Req 7.1 |
| Trocar para aba Rotas remove popup | Req 7.2 |
| Trocar para aba Análise de Área mantém popup | Req 7.3 |
| Filtro com zero prospects exibe mensagem de ausência | Req 3.3 |

### Testes de propriedade

Cada teste deve rodar mínimo **100 iterações**.

**Property 1 — Select de Estado** (fast-check, frontend)
```javascript
// Feature: area-analysis-panel, Property 1: select reflects unique sorted prospect states
fc.assert(fc.property(
    fc.array(fc.record({ status: fc.constantFrom('Prospect', 'Active', 'Inactive'), state: fc.option(fc.string()) })),
    (data) => {
        state.allMarkersData = data;
        populateAreaAnalysisFilters();
        const options = [...document.getElementById('areaStateFilter').options].map(o => o.value);
        const expected = ['all', ...[...new Set(data.filter(m => m.status === 'Prospect').map(m => m.state).filter(Boolean))].sort()];
        return JSON.stringify(options) === JSON.stringify(expected);
    }
));
```

**Property 2 — Filtragem combinada** (fast-check, frontend)
```javascript
// Feature: area-analysis-panel, Property 2: combined filter satisfies all predicates
fc.assert(fc.property(
    fc.array(fc.record({ status: fc.string(), state: fc.option(fc.string()), decision: fc.option(fc.constantFrom('Go', 'No Go')) })),
    fc.option(fc.string()),
    fc.constantFrom('Go', 'No Go', 'all'),
    (data, stateFilter, decisionFilter) => {
        state.allMarkersData = data;
        const result = computeFilteredProspects(data, stateFilter, decisionFilter);
        return result.every(p =>
            p.status === 'Prospect' &&
            (stateFilter === 'all' || p.state === stateFilter) &&
            (decisionFilter === 'all' || p.decision === decisionFilter)
        );
    }
));
```

**Property 3 — Estatísticas corretas** (fast-check, frontend)
```javascript
// Feature: area-analysis-panel, Property 3: popup stats are arithmetically correct
fc.assert(fc.property(
    fc.array(fc.record({ decision: fc.constantFrom('Go', 'No Go'), reason: fc.string() })),
    (prospects) => {
        const stats = computeStats(prospects);
        const goCount = prospects.filter(p => p.decision === 'Go').length;
        return stats.total === prospects.length &&
               stats.goCount === goCount &&
               Math.abs(stats.approvalRate - (prospects.length > 0 ? goCount / prospects.length * 100 : 0)) < 0.01;
    }
));
```

**Property 5 — Decisão binária do backend** (hypothesis, Python)
```python
# Feature: area-analysis-panel, Property 5: binary decision consistent with matching
@given(st.lists(prospect_strategy(), min_size=0, max_size=20),
       st.lists(slot_strategy(), min_size=0, max_size=10))
def test_decision_binary_consistency(prospects, slots):
    result = run_matching(prospects, slots)
    for partner in result:
        if partner.status == 'Prospect':
            assert partner.decision in ('Go', 'No Go')
            if partner.matched_slot_id:
                assert partner.decision == 'Go'
                assert partner.reason == 'Seguir cadastro'
            else:
                assert partner.decision == 'No Go'
                assert partner.reason in VALID_NO_GO_REASONS
```

**Property 6 — Serialização** (hypothesis, Python)
```python
# Feature: area-analysis-panel, Property 6: serialization round-trip preserves decision and reason
@given(st.text(alphabet=st.characters(whitelist_categories=('Lu', 'Ll')), min_size=0),
       st.sampled_from(['Seguir cadastro', 'Sem oportunidade próxima', 'Sem oportunidade próxima na borda', 'Fora de jurisdição', '']))
def test_serialization_round_trip(decision, reason):
    pm = PartnerMetrics(..., decision=decision, reason=reason)
    # Simula _write_geojson() → lê properties da feature PARTNER_POINT
    feature = build_partner_point_feature(pm)
    assert feature['properties']['decision'] == decision
    assert feature['properties']['reason'] == reason
```
