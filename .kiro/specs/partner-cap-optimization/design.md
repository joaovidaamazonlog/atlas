# Design Document — Partner Cap Optimization

## Overview

This feature adds a new pipeline phase (Phase 3.5) and a set of frontend components to identify and visualize capacity optimization opportunities for Active partners.

The backend scans each Active partner with `capacity < 80` against the enriched `heatmap.geojson` (which already carries `demand_residual` and `is_covered` from the recruitable-area-analysis feature). For each partner it finds the best candidate position within 300 m, calculates `suggested_cap` and `suggested_radius`, and persists an `adv_opportunity` object into `dados_mapa.json`.

The frontend exposes this data through three new surfaces inside the existing `AreaAnalysisTab`:

1. **"Oportunidades de Cap"** — a list panel (right-side portal) showing Active partners with opportunities, sorted by estimated ADV gain. Clicking an item toggles `CapComparisonLayer` on the map.
2. **Hex-click demand popup** — when the "Área" tab is active, clicking a heatmap hex shows a popup with `demand_daily`, `demand_residual`, `is_covered`, and `covering_partner_id`, and accumulates a running sum across multiple selections.
3. **What-if repositioning** — a toggle inside the existing "Análise Manual" panel that makes Active partner markers draggable with a 300 m guardrail, recalculating cap/radius in real time via `PartnerWhatIfLayer`.

---

## Architecture

```mermaid
flowchart TD
    subgraph Backend Pipeline (daily mode)
        P3[Phase 3 — run_phase3] --> P35[Phase 3.5 — run_phase3_5]
        P35 --> P4[Phase 4 — run_phase4]
        P35 -->|writes adv_opportunity| DM[dados_mapa.json]
        P35 -->|reads| HM[heatmap.geojson\n(demand_residual, is_covered)]
    end

    subgraph Frontend Store (Zustand)
        DM -->|loadAll| Store[(AtlasStore)]
        Store --> capOpportunityState
        Store --> hexSelectionState
        Store --> whatIfMode
    end

    subgraph Frontend Components
        AreaAnalysisTab --> CapOpportunitySection
        AreaAnalysisTab --> HexSelectionSummary
        ManualAnalysisPanel --> WhatIfToggle

        CapOpportunitySection -->|createPortal| CapOpportunityPanel
        CapOpportunityPanel -->|selected item| CapComparisonLayer
        WhatIfToggle -->|active| PartnerWhatIfLayer
        HeatmapLayer -->|activeTab=area + click| hexSelectionState
    end
```

### Key Design Decisions

**Phase 3.5 as a standalone module** — keeping it in `phase3_5_cap_optimizer.py` (separate from phase3) preserves the single-responsibility principle and makes it easy to skip or mock in tests. The orchestrator wraps it in a try/except so a failure never aborts the pipeline.

**adv_opportunity persisted in dados_mapa.json** — the frontend already loads this file; adding the field there avoids a new endpoint and keeps the data co-located with the partner record.

**H3 neighbor scan at partner's resolution** — using `h3.grid_disk` at the partner's H3 resolution (from `Config.get_h3_res`) ensures the 300 m radius is approximated correctly regardless of whether the station uses resolution 8 or 9.

**suggested_radius via RADII lookup** — `suggested_radius` is the smallest value from `Config.RADII` that covers `suggested_cap` demand at the candidate position, keeping it consistent with how Phase 2 assigns radii.

**Store slices, not new stores** — `capOpportunityState` and `hexSelectionState` are added as slices to the existing Zustand store, following the established pattern.

**CapComparisonLayer as a separate component** — rendered inside `MapView` (same pattern as `RecruitableAreaLayer`), controlled by `capOpportunityState.selectedPartnerId` in the store.

**PartnerWhatIfLayer** — a separate map component that replaces `PartnerMarkers` for Active partners when what-if mode is active, using Leaflet's `draggable` marker option. The guardrail is a `Circle` at the original centroid.

---

## Components and Interfaces

### Backend

#### `backend/vanilla/phase3_5_cap_optimizer.py`

```python
def run_phase3_5(
    fit: FitResult,
    output_dir: str,
    stations: Optional[List[str]] = None,
) -> None
```

Internal helpers:
- `_load_heatmap_index(output_dir) -> Dict[str, dict]` — loads `heatmap.geojson` into a `{hex_id: properties}` dict for O(1) lookup.
- `_candidate_positions(partner: PartnerMetrics, h3_res: int) -> List[str]` — returns `h3.grid_disk(origin_hex, k)` where `k` is chosen so the disk radius ≈ 300 m at the given resolution.
- `_available_residual(candidate_hex: str, partner_radius: int, heatmap_index: Dict) -> float` — sums `demand_residual` of all hexes within `partner_radius` meters of `candidate_hex`.
- `_smallest_radius_for_cap(candidate_hex: str, target_cap: int, heatmap_index: Dict) -> int` — iterates `Config.RADII` ascending, returns first radius whose covered residual ≥ `target_cap`.
- `_build_opportunity(partner, candidate_hex, residual, heatmap_index) -> dict | None` — builds the `adv_opportunity` dict or returns `None`.
- `_patch_dados_mapa(output_dir, opportunities: Dict[str, dict | None]) -> None` — reads `dados_mapa.json`, patches `adv_opportunity` for each partner, writes back.

#### `backend/vanilla/orchestrator.py` (modification)

In `run_daily`, after `run_phase3` and before `run_phase4`:

```python
try:
    from vanilla.phase3_5_cap_optimizer import run_phase3_5
    run_phase3_5(fit=fit, output_dir=output_dir, stations=stations)
except Exception as e:
    print(f"  WARN Phase 3.5 falhou: {e}")
```

#### `backend/shared/models.py` (modification)

Add to `Partner` dataclass:

```python
adv_opportunity: Optional[dict] = None
```

### Frontend

#### `atlas-react/src/store/types.ts` (modification)

```typescript
export interface AdvOpportunity {
  suggested_lat: number;
  suggested_lon: number;
  suggested_cap: number;
  suggested_radius: number;
  estimated_adv_gain: number;
  distance_from_current: number;
}

// Add to Partner interface:
adv_opportunity: AdvOpportunity | null;

// New store slices:
export interface CapOpportunityState {
  selectedPartnerId: string | null;
}

export interface HexSelectionState {
  selectedHexIds: string[];
  totalDemandDaily: number;
  totalDemandResidual: number;
}
```

#### `atlas-react/src/lib/models.ts` (modification)

In `Partner` constructor:
```typescript
this.adv_opportunity = (raw as any).adv_opportunity ?? null;
```

#### `atlas-react/src/store/index.ts` (modification)

Add slices:
```typescript
capOpportunityState: CapOpportunityState;
hexSelectionState: HexSelectionState;
whatIfModeActive: boolean;

// Actions:
setSelectedCapOpportunity: (partnerId: string | null) => void;
toggleHexSelection: (hexId: string, demandDaily: number, demandResidual: number) => void;
clearHexSelection: () => void;
setWhatIfModeActive: (active: boolean) => void;
```

#### New: `atlas-react/src/components/map/CapComparisonLayer.tsx`

Renders when `capOpportunityState.selectedPartnerId` is set. Reads the partner from `allMarkersData`, reads `adv_opportunity` fields, and renders:
- `CircleMarker` at current position (Active color, normal weight)
- `CircleMarker` at suggested position (amber color, weight 3)
- `Circle` at current position with `partner.radius`
- `Circle` at suggested position with `adv_opportunity.suggested_radius` (amber, dashed)

#### New: `atlas-react/src/components/map/PartnerWhatIfLayer.tsx`

Active only when `whatIfModeActive === true`. For each Active partner with coords:
- Renders a draggable `Marker` (custom icon)
- Renders a `Circle` guardrail at original centroid (300 m, indigo dashed)
- On `dragend`: checks distance from original; if > 300 m, snaps back and dispatches a warning event; otherwise recalculates `suggested_cap` and `suggested_radius` from `heatmapData` and dispatches `atlas:whatif-result`

#### `atlas-react/src/components/controls/AreaAnalysisTab.tsx` (modification)

Add a third section "Oportunidades de Cap" between "Área Recrutável" and "Análise de Prospects". Uses the same button style as existing sections. When triggered, opens a `CapOpportunityPanel` via `createPortal`.

#### `atlas-react/src/components/controls/ManualAnalysisPanel.tsx` (modification)

Inside `PanelContent`, after the existing analysis form, add a toggle:
```
[ ] Simular reposicionamento de parceiro
```
When checked, sets `whatIfModeActive = true` in the store. Displays what-if results when `atlas:whatif-result` is received.

#### `atlas-react/src/components/map/HeatmapLayer.tsx` (modification)

When `activeTab === 'area'`:
- Render heatmap hexes as interactive `GeoJSON` polygons (not just heat points)
- On click: dispatch `toggleHexSelection` with the hex's `demand_daily` and `demand_residual`
- Highlight selected hexes with a distinct border (white, weight 2)

#### `atlas-react/src/components/map/MapView.tsx` (modification)

Add new layers:
```tsx
<CapComparisonLayer />
<PartnerWhatIfLayer />
```

---

## Data Models

### `adv_opportunity` object (in `dados_mapa.json`)

```json
{
  "suggested_lat": -23.5505,
  "suggested_lon": -46.6333,
  "suggested_cap": 72,
  "suggested_radius": 1200,
  "estimated_adv_gain": 30,
  "distance_from_current": 187.4
}
```

Field constraints:
- `suggested_cap`: integer, `current_cap + 1 ≤ suggested_cap ≤ 80`
- `estimated_adv_gain`: integer, `= suggested_cap - current_cap`
- `distance_from_current`: float in meters, geodesic distance
- `suggested_radius`: integer from `Config.RADII`, in meters
- When no opportunity: field is `null` (never omitted)

### `HexSelectionState`

```typescript
{
  selectedHexIds: string[];       // H3 hex IDs
  totalDemandDaily: number;       // sum of demand_daily
  totalDemandResidual: number;    // sum of demand_residual
}
```

### `CapOpportunityState`

```typescript
{
  selectedPartnerId: string | null;  // salesforce_id of selected item, or null
}
```

---

## Correctness Properties

*A property is a characteristic or behavior that should hold true across all valid executions of a system — essentially, a formal statement about what the system should do. Properties serve as the bridge between human-readable specifications and machine-verifiable correctness guarantees.*

### Property 1: All Active partners are evaluated

*For any* `FitResult` containing N Active partners, after `run_phase3_5` completes, the patched `dados_mapa.json` must contain an `adv_opportunity` entry (either an object or `null`) for every one of those N Active partners — no Active partner may be silently skipped.

**Validates: Requirements 1.2**

---

### Property 2: Cap-80 partners always yield null opportunity

*For any* Active partner whose `capacity >= 80`, `run_phase3_5` must set `adv_opportunity = null`, regardless of the heatmap content around that partner.

**Validates: Requirements 1.3**

---

### Property 3: Under-cap partners with available demand yield non-null opportunity

*For any* Active partner with `capacity < 80` and a heatmap where at least one neighbor hex has `demand_residual > capacity`, `run_phase3_5` must produce a non-null `adv_opportunity`.

**Validates: Requirements 1.4, 1.6**

---

### Property 4: suggested_cap invariant

*For any* non-null `adv_opportunity`, `suggested_cap` must satisfy `current_cap < suggested_cap ≤ 80`.

**Validates: Requirements 2.3**

---

### Property 5: estimated_adv_gain arithmetic invariant

*For any* non-null `adv_opportunity`, `estimated_adv_gain == suggested_cap - current_cap`.

**Validates: Requirements 2.4**

---

### Property 6: Best candidate selection

*For any* set of viable candidate positions for a given partner, the selected position must have the maximum `estimated_adv_gain`; among ties, the minimum `distance_from_current`.

**Validates: Requirements 1.7**

---

### Property 7: Partner field preservation

*For any* partner record in `dados_mapa.json`, after `run_phase3_5` runs, all fields except `adv_opportunity` must be byte-for-byte identical to their pre-run values.

**Validates: Requirements 1.10**

---

### Property 8: Station filter respected

*For any* `stations` list passed to `run_phase3_5`, partners whose `delivery_station` is not in that list must have their `adv_opportunity` field unchanged (not evaluated).

**Validates: Requirements 3.3**

---

### Property 9: Opportunity list ordering

*For any* set of Active partners with non-null `adv_opportunity`, the list rendered in `CapOpportunityPanel` must be sorted by `estimated_adv_gain` in descending order.

**Validates: Requirements 5.2**

---

### Property 10: Hex selection accumulation

*For any* sequence of hex clicks in the "Área" tab, the displayed `totalDemandDaily` and `totalDemandResidual` must equal the sum of the respective fields of all currently-selected hexes.

**Validates: Requirements 9.2**

---

### Property 11: Hex selection toggle idempotence

*For any* hex that is currently selected, clicking it again must remove it from the selection and reduce the accumulated sums by exactly that hex's `demand_daily` and `demand_residual`.

**Validates: Requirements 9.4**

---

## Error Handling

| Scenario | Behavior |
|---|---|
| `heatmap.geojson` missing | Log warning, return without modifying `dados_mapa.json` |
| `dados_mapa.json` missing | Log warning, skip patching |
| Partner has no `origin_hex` | Skip that partner, log warning |
| H3 library error on `grid_disk` | Skip that partner, log warning |
| Phase 3.5 raises unhandled exception | Orchestrator catches, logs, continues to Phase 4 |
| `heatmapData` not loaded in store (what-if) | Show error message in `ManualAnalysisPanel`, disable drag |
| Drag outside 300 m guardrail | Snap marker back to original position, show inline warning |
| `adv_opportunity` field absent in JSON | `Partner` constructor defaults to `null` |

---

## Testing Strategy

### Unit Tests

- `phase3_5_cap_optimizer.py`: test `_available_residual`, `_smallest_radius_for_cap`, `_build_opportunity` with fixture heatmap data
- `_patch_dados_mapa`: verify field preservation and correct patching
- `Partner` TypeScript class: verify `adv_opportunity` is mapped correctly from raw JSON (null, absent, and valid object cases)
- `CapOpportunityPanel`: render test verifying sort order and required fields per item
- `HeatmapLayer` hex selection: unit test for `toggleHexSelection` reducer logic

### Property-Based Tests

Using **Hypothesis** (Python) for backend and **fast-check** (TypeScript) for frontend. Minimum 100 iterations per property.

Each test is tagged with the corresponding design property:
> `# Feature: partner-cap-optimization, Property N: <property_text>`

- **Property 1** — generate random `FitResult` with varying Active partner counts; verify all are present in output
- **Property 2** — generate Active partners with `capacity` in `[80, 200]`; verify `adv_opportunity is None`
- **Property 3** — generate Active partners with `capacity` in `[1, 79]` and synthetic heatmap with sufficient residual; verify non-null result
- **Property 4** — generate valid opportunities; verify `current_cap < suggested_cap <= 80`
- **Property 5** — generate valid opportunities; verify `estimated_adv_gain == suggested_cap - capacity`
- **Property 6** — generate random candidate sets; verify best-gain selection with distance tiebreak
- **Property 7** — generate random partner records; run phase 3.5; verify all non-`adv_opportunity` fields unchanged
- **Property 8** — generate FitResult with partners from multiple stations; verify station filter
- **Property 9** — generate random opportunity lists; verify rendered order (fast-check)
- **Property 10** — generate random hex click sequences; verify accumulated sums (fast-check)
- **Property 11** — generate random selected hex sets; verify toggle removes and reduces sums (fast-check)

### Integration Tests

- Orchestrator call order: mock `run_phase3_5` and verify it is called between `run_phase3` and `run_phase4`
- End-to-end with real fixture files: run `run_daily` on a small fixture dataset and verify `dados_mapa.json` contains `adv_opportunity` fields
