# Performance — Frontend (Atlas)

Este documento descreve as quatro otimizações aplicadas no frontend React
como parte da spec `frontend-performance` (`.kiro/specs/frontend-performance/`).

## Sumário das otimizações

| # | Área | O que mudou | Por quê |
|---|------|-------------|---------|
| 1 | `PolygonLayer` | Removida a `key={JSON.stringify(filterState)}`; camada `L.geoJSON` é criada uma vez e atualizada imperativamente via `ref` + `useEffect` ortogonais. | Evita desmontar/remontar a camada Leaflet a cada mudança de filtro. |
| 2 | `TerritoryTable` (Dashboard) e `PartnersByBucketTable` | Virtualização via `useRowVirtualization` (threshold = 100, seguindo `StationsTable`). | Tabelas com centenas/milhares de linhas renderizam só o que está visível. |
| 3 | `AreaAnalysisTab` | `useMemo` explícito em `overview`, `filteredProspects`, `filteredStats`, `stateRows`. Funções puras extraídas para `lib/areaAnalysisPure.ts`. | Recomputações evitadas quando inputs relevantes não mudam; permite PBT isolado. |
| 4 | `PartnerMarkers` | `key={partner.salesforce_id}` (sem `i18n.language`). Popup atualiza por re-render, não por remount. | Trocar idioma deixa de recriar todos os markers e quebrar refs. |

## Verificar

Todos os refinamentos são cobertos por testes:

```bash
npm test --run
```

Testes principais:

- `src/__tests__/dashboard/useRowVirtualization.test.ts` — comportamento do helper.
- `src/__tests__/dashboard/TerritoryTable.test.tsx` — equivalência de linhas (PBT sobre `sortTerritories`).
- `src/__tests__/dashboard/PartnersByBucketTable.test.tsx` — PBT de filtragem/busca/ordenação.
- `src/__tests__/map/PolygonLayer.test.ts` — PBT de `_filterFeatures` (regra pura alimenta a camada imperativa).
- `src/__tests__/map/PartnerMarkers.test.ts` — regressão estática garantindo que `i18n.language` não entra na `key`.
- `src/__tests__/controls/areaAnalysis.pure.test.ts` — PBT sobre `getGlobalOverview`, `getFilteredStats`, `getStatsByState`.
- `src/__tests__/controls/AreaAnalysisTab.memo.test.tsx` — estabilidade referencial dos `useMemo`.

## Arquivos-chave

- `src/components/dashboard/useRowVirtualization.ts` — helper compartilhado, referência de uso em `StationsTable.tsx`.
- `src/lib/areaAnalysisPure.ts` — funções puras extraídas do `AreaAnalysisTab` (exporta `getGlobalOverview`, `getFilteredStats`, `getStatsByState`, `NO_GO_REASONS`).
- `src/components/map/PolygonLayer.tsx` — também exporta `_filterFeatures` para testes (prefixo `_` indica uso interno).
