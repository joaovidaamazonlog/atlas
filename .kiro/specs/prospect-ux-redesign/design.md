# Design Document — prospect-ux-redesign

## Overview

Redesign da feature "Prospectar" do atlas-react. O objetivo é substituir o fluxo vanilla (popup DOM imperativo + marcadores individuais) por uma experiência React nativa integrada ao ControlPanel existente.

A mudança central é tripla:
1. **Ponto de entrada**: nova aba "Prospectar" no `ControlPanel` com filtros cascateados DS → Carteira, em vez de um botão no popup do slot.
2. **Visualização**: clusters K-means (4 por carteira) renderizados como `ProspectHeatmap` via `leaflet.heat`, em vez de marcadores individuais.
3. **Painel de resultados**: `ResultPanel` lateral fixo (desktop/tablet) ou inline (mobile), seguindo o padrão visual do `AreaAnalysisTab` existente.

O estado da prospecção é gerenciado por um slice `prospectState` no store Zustand, mantendo sincronização entre o painel de controle e as camadas do mapa.

---

## Architecture

### Fluxo de dados

```mermaid
flowchart TD
    A[ProspectTab\nfiltros DS → Carteira] -->|POST /api/empresas| B[Prospect_API]
    B -->|ProspectCompany[]| C[prospectState.companies]
    C -->|kmeansCluster\nfrontend| D[prospectState.clusters]
    D -->|centróides + intensidade| E[HeatmapLayer\nleaflet.heat]
    C -->|lista de empresas| F[ResultPanel\npainel lateral]
    F -->|alfinete| G[ProspectMarkers\nL.marker imperativo]
    F -->|POST /api/empresas/contactada| B
    H[useGeolocation hook] -->|watchPosition| I[UserLocationMarker\nmarcador pulsante]
```

### Componentes novos vs modificados

| Componente | Tipo | Descrição |
|---|---|---|
| `ProspectTab` | Novo | Aba com filtros DS/Carteira e botão de busca |
| `ResultPanel` | Novo | Painel lateral de resultados (portal no desktop) |
| `ProspectMarkers` | Novo | Gerencia marcadores L.marker imperativos (alfinetes) |
| `UserLocationMarker` | Novo | Marcador pulsante de geolocalização mobile |
| `HeatmapLayer` | Modificado | Implementa leaflet.heat com dados de clusters |
| `PolygonLayer` | Modificado | Filtra por carteira selecionada quando heatmap ativo |
| `ControlPanel` | Modificado | Adiciona aba "Prospectar" |
| `store/index.ts` | Modificado | Adiciona slice `prospectState` |
| `store/types.ts` | Modificado | Adiciona `ProspectCluster`, `ProspectState` |

---

## Components and Interfaces

### ProspectTab

Renderizado dentro do `ControlPanel` como nova aba. Responsável por:
- Seletores cascateados DS → Carteira (lógica idêntica ao `FiltersTab`)
- Botão "Buscar Empresas" (habilitado apenas com DS + Carteira selecionados)
- Chamada à `Prospect_API` e despacho para o store
- Renderização inline do `ResultPanel` em mobile

```tsx
// Props: nenhuma — lê tudo do store
export default function ProspectTab(): JSX.Element
```

### ResultPanel

Painel de resultados. Em desktop/tablet é renderizado via `createPortal` no `document.body` (padrão `AreaAnalysisTab`). Em mobile é renderizado inline no `ProspectTab`.

```tsx
interface ResultPanelProps {
  companies: ProspectCompany[];
  selectedStation: string;
  selectedBucket: string;
  onClose: () => void;
}
```

Cada card de empresa exibe: nome, endereço, tipo, telefone (quando disponível), link Google Maps, botão alfinete (quando tem coordenadas), controle "Marcar como contactada".

### ProspectMarkers

Componente que gerencia marcadores Leaflet imperativos (alfinetes). Usa `useMap()` do react-leaflet e mantém um `Map<string, L.Marker>` em ref para controle de ciclo de vida.

```tsx
interface ProspectMarkersProps {
  pinnedKeys: Set<string>;  // chaves das empresas fixadas
  companies: ProspectCompany[];
}
```

### UserLocationMarker

Hook + componente para geolocalização mobile. Usa `navigator.geolocation.watchPosition` e renderiza um marcador com CSS de animação pulsante.

```tsx
// Usado apenas quando isMobile && ResultPanel ativo
export function useGeolocation(): {
  position: [number, number] | null;
  isTracking: boolean;
  error: string | null;
  startTracking: () => void;
  stopTracking: () => void;
}
```

### HeatmapLayer (modificado)

Implementa `leaflet.heat` via `useEffect`. Recebe os clusters do store e renderiza pontos de calor nos centróides com intensidade proporcional à prioridade.

```tsx
// Lê prospectState.clusters do store
export default function HeatmapLayer(): null
```

Detecção de WebGL:
```ts
const supportsWebGL = (): boolean => {
  try {
    const canvas = document.createElement('canvas');
    return !!(canvas.getContext('webgl') || canvas.getContext('experimental-webgl'));
  } catch { return false; }
};
// WebGL: radius=40, blur=25 | fallback: radius=25, blur=15
```

---

## Data Models

### ProspectCluster (novo)

```ts
export interface ProspectCluster {
  centroid: { lat: number; lon: number };
  count: number;          // total de empresas no cluster
  match_count: number;    // empresas com isMatch === true
  priority: number;       // 1 = mais alta (maior count + match_count)
  intensity: number;      // 0.0–1.0, proporcional à prioridade
  company_indices: number[]; // índices em ProspectState.companies
}
```

### ProspectState (novo slice no store)

```ts
export interface ProspectState {
  companies: ProspectCompany[];
  clusters: ProspectCluster[];
  isLoading: boolean;
  error: string | null;
  selectedStation: string | null;
  selectedBucket: string | null;
}
```

### ProspectCompany (extensão do tipo existente)

O tipo `ProspectCompany` em `store/types.ts` precisa de dois campos adicionais:

```ts
export interface ProspectCompany {
  // ... campos existentes ...
  isMatch: boolean | null;   // dentro do raio do slot ou CEP pertence ao slot
  contactada: boolean;       // estado de contactada (toggle)
  territory_id?: string;     // bucket_ade selecionado no momento da busca
}
```

### Algoritmo K-means (frontend)

Implementado em `src/lib/kmeansUtils.ts` como função pura:

```ts
export function kmeansCluster(
  companies: ProspectCompany[],
  k: number = 4
): ProspectCluster[]
```

**Passos:**
1. Filtrar empresas com `lat != null && lon != null`
2. Se `n < k`, usar `k = n` (um cluster por empresa)
3. Inicializar centróides com K-means++ (evita clusters vazios)
4. Iterar até convergência (máx 100 iterações) ou delta < 1e-6
5. Calcular `match_count` por cluster
6. Ordenar por `count + match_count` decrescente → atribuir `priority` (1-based)
7. Calcular `intensity`: `priority 1 → 1.0`, demais → `1.0 - (priority - 1) / k`

**Cálculo de `isMatch`:**
- Se empresa tem `lat/lon`: `distância ao centróide do slot <= radius_s`
- Se empresa não tem `lat/lon`: `cep ∈ ceps_do_slot`
- O slot de referência é o `IDEAL_SLOT` do `idealSupplyData` correspondente ao `bucket_ade` selecionado

### lead_key (lógica de contactada)

```ts
function getLeadKey(company: ProspectCompany): string {
  if (company.google_maps_link && company.google_maps_link !== 'N/A') {
    return company.google_maps_link;
  }
  return `${company.nome}|${company.endereco}`;
}
```

---

## Correctness Properties

*A property is a characteristic or behavior that should hold true across all valid executions of a system — essentially, a formal statement about what the system should do. Properties serve as the bridge between human-readable specifications and machine-verifiable correctness guarantees.*

### Property 1: Cascateamento de carteiras por DS

*For any* conjunto de `allMarkersData` e qualquer `selectedStation` não nula, as carteiras exibidas no seletor de Carteira devem ser exatamente o conjunto de `bucket_ade` únicos dos parceiros cuja `delivery_station` é igual a `selectedStation` — nem mais, nem menos.

**Validates: Requirements 1.5, 1.6**

---

### Property 2: Limpeza de carteira ao trocar DS

*For any* par de Delivery Stations distintas (DS1, DS2), quando o usuário troca de DS1 para DS2, a carteira selecionada deve ser `null` independentemente de qual carteira estava selecionada antes.

**Validates: Requirements 1.7**

---

### Property 3: Estado do botão "Buscar Empresas"

*For any* combinação de (selectedStation, selectedBucket), o botão "Buscar Empresas" está habilitado se e somente se ambos são não nulos e não vazios.

**Validates: Requirements 1.8**

---

### Property 4: Round-trip de armazenamento de empresas

*For any* lista de `ProspectCompany` retornada pela API, após o dispatch para o store, `prospectState.companies` deve conter exatamente as mesmas empresas na mesma ordem.

**Validates: Requirements 2.3, 6.2**

---

### Property 5: Limpeza de resultados em nova busca

*For any* sequência de duas buscas com resultados distintos, após a segunda busca ser concluída, `prospectState.companies` deve conter apenas os resultados da segunda busca.

**Validates: Requirements 2.6**

---

### Property 6: Contagem de empresas no cabeçalho do ResultPanel

*For any* lista de `ProspectCompany` em `prospectState.companies`, o total exibido no cabeçalho do `ResultPanel` deve ser igual a `companies.length`.

**Validates: Requirements 3.2**

---

### Property 7: Campos obrigatórios no card de empresa

*For any* `ProspectCompany`, o card renderizado pelo `ResultPanel` deve conter o nome, endereço e tipo da empresa. Quando `telefone_1` ou `telefone_2` são não nulos, o telefone deve aparecer. Quando `google_maps_link` é não nulo e diferente de `'N/A'`, o link deve aparecer.

**Validates: Requirements 3.3**

---

### Property 8: Botão de alfinete presente sse coordenadas válidas

*For any* `ProspectCompany`, o botão de alfinete deve aparecer no card se e somente se `lat != null && lon != null`.

**Validates: Requirements 3.8**

---

### Property 9: Toggle de alfinete é round-trip

*For any* empresa com coordenadas válidas, fixar e depois desfixar deve resultar em nenhum marcador ativo para essa empresa no mapa.

**Validates: Requirements 3.10**

---

### Property 10: lead_key calculado corretamente

*For any* `ProspectCompany`, `getLeadKey(company)` deve retornar `company.google_maps_link` quando esse campo é não nulo e diferente de `'N/A'`, e `"${nome}|${endereco}"` caso contrário.

**Validates: Requirements 3.14, 3.16**

---

### Property 11: Contagem de contactadas atualizada em tempo real

*For any* lista de empresas com qualquer combinação de `contactada: true/false`, a contagem exibida no cabeçalho do `ResultPanel` deve ser igual ao número de empresas com `contactada === true`.

**Validates: Requirements 3.17**

---

### Property 12: K-means produz exatamente min(n, 4) clusters

*For any* lista de `ProspectCompany` com `n` empresas com coordenadas válidas, `kmeansCluster(companies, 4)` deve retornar exatamente `min(n, 4)` clusters, cada um com `count > 0`.

**Validates: Requirements 4.1, 4.2**

---

### Property 13: Invariantes dos clusters K-means

*For any* resultado de `kmeansCluster(companies, k)`, as seguintes invariantes devem ser satisfeitas simultaneamente:
- A soma de `count` de todos os clusters é igual ao número de empresas com coordenadas válidas
- `match_count <= count` para cada cluster
- O cluster com `priority === 1` tem `intensity === 1.0`
- `intensity[i] >= intensity[i+1]` para clusters ordenados por prioridade

**Validates: Requirements 4.3, 4.4, 4.5**

---

### Property 14: Limpeza total do prospectState

*For any* `prospectState` com `companies` não vazio, após a action de limpeza, `companies` deve ser `[]`, `clusters` deve ser `[]`, `selectedStation` deve ser `null` e `selectedBucket` deve ser `null`.

**Validates: Requirements 6.4**

---

### Property 15: Marcador de geolocalização reflete posição atual

*For any* sequência de posições GPS `[p1, p2, ..., pn]` emitidas pelo `watchPosition`, o marcador de geolocalização deve sempre estar na posição `pn` (a mais recente).

**Validates: Requirements 7.4**

---

## Error Handling

### Erros de API (Prospect_API)

- **HTTP 4xx/5xx**: exibir mensagem descritiva no `ProspectTab` (ex: "Erro ao buscar empresas: 503 Service Unavailable"). Reabilitar o botão "Buscar Empresas".
- **Falha de rede (fetch throw)**: exibir "Erro de conexão. Verifique sua internet e tente novamente."
- **Timeout**: não implementado na v1 (sem AbortController); pode ser adicionado em iteração futura.

### Erros de K-means

- Se `kmeansCluster` lançar exceção (ex: dados corrompidos), capturar no action do store e setar `prospectState.error`.
- Nunca deixar `prospectState.clusters` em estado inconsistente.

### Erros de geolocalização

- `PERMISSION_DENIED`: exibir "Permissão de localização negada. Habilite nas configurações do dispositivo."
- `POSITION_UNAVAILABLE`: exibir "Localização indisponível no momento."
- `TIMEOUT`: exibir "Tempo esgotado ao obter localização."

### Erros de contactada (POST /api/empresas/contactada)

- Falha silenciosa com `console.warn` (não bloquear o usuário).
- O estado local `contactada` é atualizado otimisticamente; em caso de falha, reverter para o estado anterior.

---

## Testing Strategy

### Abordagem dual

- **Testes de exemplo** (Vitest + React Testing Library): interações de UI específicas, estados de erro, comportamento responsivo.
- **Testes de propriedade** (fast-check): propriedades universais sobre lógica pura (K-means, cascateamento, lead_key, contagens).

### Testes de propriedade (fast-check)

A biblioteca escolhida é **fast-check** (já compatível com Vitest). Cada teste de propriedade deve rodar mínimo 100 iterações.

Tag de referência: `Feature: prospect-ux-redesign, Property {N}: {texto}`

| Propriedade | Arquivo de teste | Função testada |
|---|---|---|
| P1 — Cascateamento de carteiras | `ProspectTab.test.tsx` | lógica de `bucketOptions` |
| P2 — Limpeza de carteira ao trocar DS | `ProspectTab.test.tsx` | handler de mudança de DS |
| P3 — Estado do botão Buscar | `ProspectTab.test.tsx` | condição `disabled` do botão |
| P4 — Round-trip de armazenamento | `prospectStore.test.ts` | action `setCompanies` |
| P5 — Limpeza em nova busca | `prospectStore.test.ts` | action `setCompanies` |
| P6 — Contagem no cabeçalho | `ResultPanel.test.tsx` | renderização do cabeçalho |
| P7 — Campos obrigatórios no card | `ResultPanel.test.tsx` | renderização do card |
| P8 — Botão alfinete sse coordenadas | `ResultPanel.test.tsx` | renderização condicional |
| P9 — Toggle alfinete round-trip | `ProspectMarkers.test.tsx` | `togglePin` |
| P10 — lead_key correto | `kmeansUtils.test.ts` | `getLeadKey` |
| P11 — Contagem de contactadas | `ResultPanel.test.tsx` | contagem no cabeçalho |
| P12 — K-means produz min(n,4) clusters | `kmeansUtils.test.ts` | `kmeansCluster` |
| P13 — Invariantes dos clusters | `kmeansUtils.test.ts` | `kmeansCluster` |
| P14 — Limpeza total do prospectState | `prospectStore.test.ts` | action `clearProspect` |
| P15 — Marcador reflete posição atual | `useGeolocation.test.ts` | `useGeolocation` hook |

### Testes de exemplo (Vitest + RTL)

- Renderização da aba "Prospectar" no `ControlPanel`
- Loading state durante chamada à API
- Mensagem de erro em falha de API
- Mensagem "Nenhuma empresa encontrada" em lista vazia
- Painel lateral via portal em desktop
- Renderização inline em mobile (mock de `useBreakpoint`)
- Botão "Minha localização" visível apenas em mobile
- Parâmetros do `heatLayer` com/sem WebGL

### Arquivos de teste a criar

```
atlas-react/src/
  components/controls/ProspectTab.test.tsx
  components/controls/ResultPanel.test.tsx
  components/map/ProspectMarkers.test.tsx
  hooks/useGeolocation.test.ts
  lib/kmeansUtils.test.ts
  store/prospectStore.test.ts
```
