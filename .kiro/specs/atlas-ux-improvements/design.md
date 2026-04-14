# Documento de Design — Atlas UX Improvements

## Visão Geral

Este documento descreve o design técnico das sete melhorias de UX do frontend React do ATLAS. O princípio central é **reutilização**: nenhuma lógica já implementada em `routeUtils.ts`, `popupUtils.ts`, `colorUtils.ts` ou `management-dashboard.js` será reescrita — apenas portada ou importada.

As melhorias são:
1. **SearchBar** — componente flutuante de busca sobre o mapa
2. **Dashboard renovado** — carrega `relatorio_executivo.json`, filtros em cascata, reutiliza funções puras de `management-dashboard.js`
3. **DashboardToggle semi-círculo** — substitui o FAB atual na borda direita
4. **ControlsToggle semi-círculo** — substitui o FAB de controles na borda esquerda (mobile/tablet)
5. **Correção do ControlPanel no desktop** — FloatingPanel não deve desmontar após `isLoading: false`
6. **Remoção dos controles de zoom** — `zoomControl: false` no MapContainer
7. **RouteLayer com leaflet-routing-machine** — rota real via OSRM, substituindo Polyline simples

---

## Arquitetura

A aplicação segue a arquitetura já estabelecida:

```
AppShell (layout por breakpoint)
├── MobileLayout   → BottomSheet + ControlsToggle + DashboardToggle
├── TabletLayout   → Drawer + ControlsToggle + DashboardToggle
└── DesktopLayout  → FloatingPanel (fixo) + DashboardToggle
        │
        ├── MapView (MapContainer)
        │     ├── SearchBar (overlay, fora do MapContainer)
        │     ├── RouteLayer (useEffect + L.Routing.control)
        │     └── ... demais camadas
        │
        └── Dashboard (painel lateral deslizante)
              └── lib/reportUtils.ts (funções puras portadas)
```

**Fluxo de dados do Dashboard renovado:**

```
fetch(DATA_URLS.executiveReport)
  → parse(text): ReportData          [lib/reportUtils.ts]
  → filterBases(data, filters)       [lib/reportUtils.ts]
  → computeKPIs(filteredBases)       [lib/reportUtils.ts]
  → getChartDataForBase(bases, sel)  [lib/reportUtils.ts]
  → sortTerritories(terrs, col, dir) [lib/reportUtils.ts]
  → getStatusClass(value, thresholds)[lib/reportUtils.ts]
```

**Fluxo do RouteLayer:**

```
store.route (RouteStop[])
  → optimizeStops(from, to, stops)   [lib/routeUtils.ts — já existe]
  → L.Routing.control({ waypoints }) [leaflet-routing-machine]
  → map.addControl() / map.removeControl()
```

---

## Componentes e Interfaces

### 1. SearchBar

**Arquivo:** `src/components/map/SearchBar.tsx`

Componente independente renderizado como overlay sobre o `MapView`, fora do `MapContainer` (não é filho do Leaflet). Usa `useMap()` internamente via um sub-componente filho do `MapContainer` para executar `map.flyTo()`.

```typescript
// Posicionamento via CSS absoluto no wrapper do MapView
// Desktop: top: 16px, left: 16px, width: clamp(280px, 30vw, 480px)
// Mobile/Tablet: top: 16px, left: 50%, transform: translateX(-50%), maxWidth: 90vw

interface SearchBarProps {
  partners: Partner[];  // recebe do store via useStore
}
```

**Lógica interna:**
- `useState` para `query`, `suggestions`, `error`, `isOpen`
- `useDebounce(query, 300)` — reutiliza hook existente
- Filtragem de parceiros: `partners.filter(p => p.name.toLowerCase().includes(debouncedQuery.toLowerCase()))`
- Geocodificação Nominatim: `https://nominatim.openstreetmap.org/search?q={query}&format=json&limit=1`
- Sub-componente `MapFlyTo` (filho do MapContainer) recebe coordenadas via ref/callback e chama `useMap().flyTo()`

**Integração no AppShell:** O `SearchBar` é renderizado no wrapper `div` do mapa (acima do `MapView`), em todos os layouts.

---

### 2. Dashboard Renovado

**Arquivo principal:** `src/components/dashboard/Dashboard.tsx` (substituído)
**Nova lib:** `src/lib/reportUtils.ts`

#### 2a. lib/reportUtils.ts

Porta as funções puras exportadas de `management-dashboard.js` para TypeScript, sem alterar a lógica:

```typescript
export function parse(text: string): ReportData
export function filterBases(reportData: ReportData, filters: DashboardFilters): BaseData[]
export function computeKPIs(filteredBases: BaseData[]): KPISummary
export function sortTerritories(territories: TerritoryRow[], column: string, direction: 'asc' | 'desc'): TerritoryRow[]
export function getStatusClass(value: number, thresholds: { green: number; yellow: number }): 'status-green' | 'status-yellow' | 'status-red'
export function getChartDataForBase(filteredBases: BaseData[], selectedBase: string): ChartData
```

> `serialize()` também é portada para suportar o teste de round-trip.

#### 2b. Dashboard.tsx renovado

Estado local do componente:

```typescript
const [reportData, setReportData] = useState<ReportData | null>(null)
const [isLoadingReport, setIsLoadingReport] = useState(false)
const [reportError, setReportError] = useState<string | null>(null)
const [filters, setFilters] = useState<DashboardFilters>({ bdm: 'all', base: 'all', ctl: 'all', territory: 'all' })
const [sortState, setSortState] = useState<{ column: string | null; direction: 'asc' | 'desc' }>({ column: null, direction: 'asc' })
```

O fetch ocorre no `useEffect` na primeira montagem (ou quando `reportData === null`). Os filtros são preservados no estado local do componente — como o Dashboard é lazy-loaded e não desmontado entre aberturas (apenas ocultado via CSS), o estado persiste na sessão.

#### 2c. FilterCascade

Componente `FilterCascade.tsx` recebe `reportData` e `filters`, calcula as opções disponíveis para cada nível usando a mesma lógica de `_applyFilterCascade` do módulo original, e emite `onFilterChange`.

---

### 3. DashboardToggle (semi-círculo direita)

**Arquivo:** `src/components/ui/DashboardToggle.tsx`

Substitui o `FAB` de dashboard em todos os layouts. Posicionamento `fixed`, borda direita, verticalmente centralizado.

```css
/* CSS do semi-círculo */
position: fixed;
right: 0;
top: 50%;
transform: translateY(-50%);
width: 40px;
height: 80px;
border-radius: 40px 0 0 40px;  /* curvo à esquerda, plano à direita */
z-index: var(--z-overlay);
```

Interface:
```typescript
interface DashboardToggleProps {
  isOpen: boolean;
  onClick: () => void;
}
```

---

### 4. ControlsToggle (semi-círculo esquerda)

**Arquivo:** `src/components/ui/ControlsToggle.tsx`

Visível apenas em `mobile` e `tablet`. Posicionamento `fixed`, borda esquerda, verticalmente centralizado.

```css
position: fixed;
left: 0;
top: 50%;
transform: translateY(-50%);
width: 40px;
height: 80px;
border-radius: 0 40px 40px 0;  /* plano à esquerda, curvo à direita */
z-index: var(--z-overlay);
```

Interface:
```typescript
interface ControlsToggleProps {
  isOpen: boolean;
  onClick: () => void;
}
```

---

### 5. Correção do ControlPanel no Desktop

**Diagnóstico:** No `DesktopLayout`, o `FloatingPanel` com `ControlPanel` é renderizado incondicionalmente (não há `isLoading` guardando sua renderização). O problema provável é que o `FloatingPanel` usa `defaultCollapsed = false` e o estado interno `collapsed` é reiniciado quando o componente é remontado.

A causa raiz mais provável: o `DesktopLayout` é remontado quando `useBreakpoint()` retorna um valor diferente durante o carregamento, ou o `AppShell` re-renderiza de forma que destrói e recria o `DesktopLayout`. Verificar se `AppShell` usa renderização condicional que desmonta o layout.

**Solução:** Garantir que o `FloatingPanel` do `ControlPanel` nunca seja condicionalmente desmontado. Se necessário, elevar o estado `collapsed` para o `DesktopLayout` (fora do `FloatingPanel`) para que sobreviva a re-renders. Adicionalmente, verificar se `useBreakpoint` causa re-mount desnecessário durante o carregamento inicial.

**Mudança mínima:** Remover qualquer `{isLoading && ...}` ou `{!isLoading && <FloatingPanel>}` que possa existir no `DesktopLayout`. O `FloatingPanel` deve ser sempre montado no desktop, independente do estado de carregamento.

---

### 6. Remoção dos Controles de Zoom

**Arquivo:** `src/components/map/MapView.tsx`

Mudança de uma linha no `MapContainer`:

```tsx
<MapContainer
  center={MAP_CONFIG.center}
  zoom={MAP_CONFIG.zoom}
  zoomControl={false}   // ← adicionar
  className={...}
>
```

---

### 7. RouteLayer com leaflet-routing-machine

**Arquivo:** `src/components/map/RouteLayer.tsx` (substituído)

**Dependência:** `leaflet-routing-machine` (instalar via `npm install leaflet-routing-machine @types/leaflet-routing-machine`)

O componente usa `useMap()` (deve ser filho do `MapContainer`) e `useEffect` para gerenciar o ciclo de vida do `L.Routing.control`.

```typescript
import L from 'leaflet';
import 'leaflet-routing-machine';
import { useEffect, useRef } from 'react';
import { useMap } from 'react-leaflet';
import { useStore } from '../../store';
import { optimizeStops } from '../../lib/routeUtils';  // reutiliza função existente

export default function RouteLayer() {
  const map = useMap();
  const route = useStore((s) => s.route);
  const setError = useStore((s) => s.setError);
  const routingControlRef = useRef<L.Routing.Control | null>(null);

  useEffect(() => {
    // Limpar controle anterior
    if (routingControlRef.current) {
      map.removeControl(routingControlRef.current);
      routingControlRef.current = null;
    }

    if (route.length < 2) return;

    const [first, last, ...middle] = route;
    const optimized = optimizeStops(first, last, middle);  // reutiliza routeUtils.ts
    const allStops = [first, ...optimized, last];

    const control = L.Routing.control({
      waypoints: allStops.map(s => L.latLng(s.lat, s.lon)),
      router: L.Routing.osrmv1({ serviceUrl: 'https://router.project-osrm.org/route/v1' }),
      lineOptions: { styles: [{ color: 'blue', opacity: 0.8, weight: 5 }] },
      createMarker: (_i, wp) => L.marker(wp.latLng),
      show: true,
    });

    control.on('routingerror', (e) => {
      setError(`Erro ao calcular rota: ${e.error?.message ?? 'serviço OSRM indisponível'}`);
    });

    control.addTo(map);
    routingControlRef.current = control;

    return () => {
      map.removeControl(control);
      routingControlRef.current = null;
    };
  }, [route, map, setError]);

  return null;
}
```

---

## Modelos de Dados

### ReportData (lib/reportUtils.ts)

```typescript
export interface TerritoryData {
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
  attainment: number;   // decimal 0-1
  accuracy: number;     // decimal 0-1
}

export interface BaseData {
  code: string;
  bdm: string;
  numTerritories: number;
  dailyDemand: number;
  idealSlots: number;
  matchedSlots: number;
  openSlots: number;
  coverage: number;     // decimal 0-1
  partners: {
    active: number;
    onboarding: number;
    bgChecks: number;
    prospects: number;
    inactive: number;
  };
  attainment: number;   // decimal 0-1
  territories: TerritoryData[];
}

export interface ReportData {
  generatedAt: string | null;
  bases: BaseData[];
}

export interface DashboardFilters {
  bdm: string;
  base: string;
  ctl: string;
  territory: string;
}

export interface KPISummary {
  totalBases: number;
  totalTerritories: number;
  totalDailyDemand: number;
  totalIdealSlots: number;
  totalOpenSlots: number;
  totalActivePartners: number;
  avgAttainment: number;
  avgCoverage: number;
}

// TerritoryRow = TerritoryData & { baseCode: string }
export interface TerritoryRow extends TerritoryData {
  baseCode: string;
}
```

### NominatimResult (SearchBar)

```typescript
interface NominatimResult {
  lat: string;
  lon: string;
  display_name: string;
}
```

---

## Propriedades de Correção

*Uma propriedade é uma característica ou comportamento que deve ser verdadeiro em todas as execuções válidas do sistema — essencialmente, uma declaração formal sobre o que o sistema deve fazer. As propriedades servem como ponte entre especificações legíveis por humanos e garantias de correção verificáveis por máquina.*

### Propriedade 1: Filtragem em cascata preserva consistência

*Para qualquer* `ReportData` e qualquer combinação de filtros `{ bdm, base, ctl, territory }`, `filterBases(data, filters)` deve retornar apenas bases cujo `bdm` corresponde ao filtro de BDM (quando não for `'all'`), apenas bases cujo `code` corresponde ao filtro de Base (quando não for `'all'`), e apenas territórios cujo `ctl` e `id` correspondem aos filtros de CTL e Território respectivamente.

**Valida: Requisitos 2.4, 2.5, 2.6**

---

### Propriedade 2: computeKPIs é consistente com os dados de entrada

*Para qualquer* array não-vazio de `BaseData`, `computeKPIs(bases)` deve satisfazer: `totalBases === bases.length`, `totalTerritories === soma dos territories.length de cada base`, `totalDailyDemand === soma dos dailyDemand de cada base`, e `avgAttainment` deve estar no intervalo `[0, 1]`.

**Valida: Requisitos 2.7, 2.8**

---

### Propriedade 3: getChartDataForBase ordena attainment de forma decrescente

*Para qualquer* array de `BaseData`, `getChartDataForBase(bases, 'all').attainmentByBase.data` deve ser um array de números em ordem não-crescente (cada elemento ≥ o próximo).

**Valida: Requisito 2.9**

---

### Propriedade 4: sortTerritories produz array ordenado

*Para qualquer* array de `TerritoryRow` e qualquer coluna numérica válida, `sortTerritories(rows, column, 'asc')` deve produzir um array onde cada elemento é menor ou igual ao seguinte na coluna especificada; e `sortTerritories(rows, column, 'desc')` deve produzir o inverso.

**Valida: Requisito 2.11**

---

### Propriedade 5: getStatusClass respeita os thresholds

*Para qualquer* valor `v` no intervalo `[0, 1]` e thresholds `{ green, yellow }` com `green > yellow >= 0`: se `v >= green` então o resultado é `'status-green'`; se `yellow <= v < green` então o resultado é `'status-yellow'`; se `v < yellow` então o resultado é `'status-red'`.

**Valida: Requisito 2.12**

---

### Propriedade 6: Autocomplete retorna subconjunto válido

*Para qualquer* lista de parceiros e qualquer query de 2 ou mais caracteres, todos os resultados do autocomplete devem ser parceiros cujo `name` contém a query (comparação case-insensitive), e nenhum parceiro que não satisfaça esse critério deve aparecer nos resultados.

**Valida: Requisito 1.4**

---

### Propriedade 7: optimizeStops produz rota de distância mínima

*Para qualquer* origem, destino e conjunto de até 8 paradas intermediárias, a distância total da rota retornada por `optimizeStops(from, to, stops)` deve ser menor ou igual à distância total de qualquer outra permutação das mesmas paradas intermediárias.

**Valida: Requisito 7.3**

---

## Tratamento de Erros

| Cenário | Componente | Tratamento |
|---|---|---|
| Fetch de `relatorio_executivo.json` falha | Dashboard | Exibe mensagem descritiva + botão "Tentar novamente" |
| Geocodificação Nominatim retorna vazio | SearchBar | Mensagem de erro inline abaixo do campo |
| Serviço OSRM retorna erro | RouteLayer | `store.setError()` com mensagem descritiva |
| `parse()` recebe texto inválido | reportUtils | Retorna `{ generatedAt: null, bases: [] }` sem lançar exceção |
| `filterBases()` recebe `reportData` nulo | reportUtils | Retorna `[]` sem lançar exceção |
| `computeKPIs()` recebe array vazio | reportUtils | Retorna KPIs zerados sem divisão por zero |
| RouteLayer desmontado com controle ativo | RouteLayer | `useEffect` cleanup chama `map.removeControl()` |

---

## Estratégia de Testes

### Abordagem dual

- **Testes de unidade/exemplo:** comportamentos específicos, casos de borda, interações de UI
- **Testes de propriedade (fast-check):** propriedades universais das funções puras (já disponível no projeto via `fast-check` em `devDependencies`)

### Testes de propriedade (fast-check)

Cada propriedade listada acima deve ser implementada como um teste de propriedade com mínimo de **100 iterações**. Cada teste deve referenciar a propriedade correspondente no comentário:

```typescript
// Feature: atlas-ux-improvements, Propriedade 1: filterBases preserva consistência de cascata
it.prop([fc.record({ ... })])('filterBases cascata', (reportData, filters) => { ... })
```

**Biblioteca:** `fast-check` (já instalada como `devDependency`)

**Arquivo de testes:** `src/lib/reportUtils.test.ts`

### Testes de unidade (vitest)

- `SearchBar`: mock de `useMap()`, verificar `flyTo` chamado com coordenadas corretas
- `Dashboard`: mock de `fetch`, verificar estados de loading/erro/sucesso
- `RouteLayer`: mock de `L.Routing.control` e `useMap()`, verificar ciclo de vida (add/remove)
- `AppShell DesktopLayout`: verificar que `FloatingPanel` permanece montado após transição `isLoading: true → false`
- `DashboardToggle` / `ControlsToggle`: verificar toggle de estado aberto/fechado

### Testes de fumaça (smoke)

- `MapView` renderiza com `zoomControl: false`
- `DashboardToggle` e `ControlsToggle` presentes no DOM com classes CSS corretas
- `SearchBar` renderizado fora do `ControlPanel`

### Cobertura de integração

- `RouteLayer` com mock do OSRM: verificar que `routingerror` chama `store.setError`
- `Dashboard` fetch real (ambiente de staging): verificar que dados são carregados e KPIs calculados
