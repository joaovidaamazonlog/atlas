# Implementation Plan: Partner Cap Optimization

## Overview

Implement Phase 3.5 of the daily pipeline (backend) and three new frontend surfaces inside the existing `AreaAnalysisTab` / `ManualAnalysisPanel`: a cap-opportunity list panel, hex-click demand popup with accumulation, and what-if partner repositioning.

## Tasks

- [x] 1. Backend — Add `adv_opportunity` field to shared models
  - Add `adv_opportunity: Optional[dict] = None` to `PartnerMetrics` dataclass in `backend/shared/models.py`
  - Add `adv_opportunity: Optional[dict] = None` to `Partner` dataclass in `backend/shared/models.py` and include it in `to_dict()`
  - _Requirements: 2.6_

- [x] 2. Backend — Implement `phase3_5_cap_optimizer.py`
  - [x] 2.1 Create `backend/vanilla/phase3_5_cap_optimizer.py` with `_load_heatmap_index`, `_candidate_positions`, `_available_residual`, `_smallest_radius_for_cap`, `_build_opportunity`, `_patch_dados_mapa` helpers and `run_phase3_5` entry point
    - `_load_heatmap_index`: load `heatmap.geojson` into `{hex_id: properties}` dict
    - `_candidate_positions`: use `h3.grid_disk` at partner's H3 resolution to get hexes within ~300 m
    - `_available_residual`: sum `demand_residual` of hexes within `partner_radius` meters of a candidate hex
    - `_smallest_radius_for_cap`: iterate `Config.RADII` ascending, return first radius whose covered residual ≥ target cap
    - `_build_opportunity`: build `adv_opportunity` dict or return `None`
    - `_patch_dados_mapa`: read `dados_mapa.json`, patch `adv_opportunity` per partner, write back
    - `run_phase3_5`: iterate Active partners from `FitResult`, skip cap ≥ 80, call helpers, call `_patch_dados_mapa`
    - _Requirements: 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 1.8, 1.9, 1.10, 1.11, 2.1, 2.2, 2.3, 2.4, 2.5, 3.2, 3.3_

  - [x] 2.2 Write property test — Property 1: All Active partners evaluated
    - **Property 1: All Active partners are evaluated**
    - Generate random `FitResult` with varying Active partner counts; verify all are present in output
    - **Validates: Requirements 1.2**

  - [x] 2.3 Write property test — Property 2: Cap-80 partners yield null
    - **Property 2: Cap-80 partners always yield null opportunity**
    - Generate Active partners with `capacity` in `[80, 200]`; verify `adv_opportunity is None`
    - **Validates: Requirements 1.3**

  - [x] 2.4 Write property test — Property 3: Under-cap partners with demand yield non-null
    - **Property 3: Under-cap partners with available demand yield non-null opportunity**
    - Generate Active partners with `capacity` in `[1, 79]` and synthetic heatmap with sufficient residual; verify non-null result
    - **Validates: Requirements 1.4, 1.6**

  - [x] 2.5 Write property test — Property 4: suggested_cap invariant
    - **Property 4: suggested_cap invariant**
    - Generate valid opportunities; verify `current_cap < suggested_cap <= 80`
    - **Validates: Requirements 2.3**

  - [x] 2.6 Write property test — Property 5: estimated_adv_gain arithmetic invariant
    - **Property 5: estimated_adv_gain arithmetic invariant**
    - Generate valid opportunities; verify `estimated_adv_gain == suggested_cap - capacity`
    - **Validates: Requirements 2.4**

  - [x] 2.7 Write property test — Property 6: Best candidate selection
    - **Property 6: Best candidate selection**
    - Generate random candidate sets; verify best-gain selection with distance tiebreak
    - **Validates: Requirements 1.7**

  - [x] 2.8 Write property test — Property 7: Partner field preservation
    - **Property 7: Partner field preservation**
    - Generate random partner records; run phase 3.5; verify all non-`adv_opportunity` fields unchanged
    - **Validates: Requirements 1.10**

  - [x] 2.9 Write property test — Property 8: Station filter respected
    - **Property 8: Station filter respected**
    - Generate FitResult with partners from multiple stations; verify station filter
    - **Validates: Requirements 3.3**

- [x] 3. Backend — Wire Phase 3.5 into orchestrator
  - In `backend/vanilla/orchestrator.py`, inside `run_daily`, add try/except block calling `run_phase3_5(fit=fit, output_dir=output_dir, stations=stations)` after `run_phase3` and before `run_phase4`
  - _Requirements: 3.1, 3.2, 3.4_

- [x] 4. Checkpoint — Backend complete
  - Ensure all tests pass, ask the user if questions arise.

- [x] 5. Frontend — TypeScript types and Partner model
  - [x] 5.1 Add `AdvOpportunity` interface, `CapOpportunityState`, `HexSelectionState` to `atlas-react/src/store/types.ts`; add `adv_opportunity: AdvOpportunity | null` to `Partner` interface
    - _Requirements: 4.1, 4.2_

  - [x] 5.2 Map `adv_opportunity` in `Partner` constructor in `atlas-react/src/lib/models.ts`
    - Add `this.adv_opportunity = (raw as any).adv_opportunity ?? null;` and declare the field
    - Handle null, absent, and valid object cases
    - _Requirements: 4.3, 4.4_

  - [x] 5.3 Write unit tests for Partner model `adv_opportunity` mapping
    - Test null, absent, and valid object cases
    - _Requirements: 4.3, 4.4_

- [x] 6. Frontend — Zustand store slices
  - Add `capOpportunityState`, `hexSelectionState`, `whatIfModeActive` state and their actions (`setSelectedCapOpportunity`, `toggleHexSelection`, `clearHexSelection`, `setWhatIfModeActive`) to `atlas-react/src/store/index.ts`
  - _Requirements: 5.2, 6.2, 9.2, 9.4_

  - [x] 6.1 Write property test — Property 10: Hex selection accumulation
    - **Property 10: Hex selection accumulation**
    - Generate random hex click sequences; verify `totalDemandDaily` and `totalDemandResidual` equal sums of selected hexes
    - **Validates: Requirements 9.2**

  - [x] 6.2 Write property test — Property 11: Hex selection toggle idempotence
    - **Property 11: Hex selection toggle idempotence**
    - Generate random selected hex sets; verify toggle removes hex and reduces sums by exactly that hex's values
    - **Validates: Requirements 9.4**

- [x] 7. Frontend — `CapComparisonLayer` map component
  - Create `atlas-react/src/components/map/CapComparisonLayer.tsx`
  - Reads `capOpportunityState.selectedPartnerId` from store; finds partner in `allMarkersData`
  - Renders `CircleMarker` at current position (Active color), `CircleMarker` at `suggested_lat/lon` (amber, weight 3), `Circle` at current position with `partner.radius`, `Circle` at suggested position with `suggested_radius` (amber, dashed)
  - Returns null when no partner is selected
  - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5, 7.6_

- [x] 8. Frontend — `PartnerWhatIfLayer` map component
  - Create `atlas-react/src/components/map/PartnerWhatIfLayer.tsx`
  - Active only when `whatIfModeActive === true`
  - For each Active partner with coords: render draggable `Marker` and a 300 m `Circle` guardrail at original centroid (indigo dashed)
  - On `dragend`: check distance from original; if > 300 m snap back and dispatch warning; otherwise recalculate `suggested_cap` and `suggested_radius` from `heatmapData` and dispatch `atlas:whatif-result`
  - _Requirements: 6.2, 6.3, 6.4, 6.5, 6.6_

- [x] 9. Frontend — Wire new layers into `MapView`
  - Import and render `<CapComparisonLayer />` and `<PartnerWhatIfLayer />` inside `MapView.tsx`
  - _Requirements: 7.6, 6.2_

- [x] 10. Frontend — `HeatmapLayer` hex-click interaction
  - Modify `atlas-react/src/components/map/HeatmapLayer.tsx`
  - When `activeTab === 'area'`: render heatmap hexes as interactive `GeoJSON` polygons; on click dispatch `toggleHexSelection` with `demand_daily` and `demand_residual`; highlight selected hexes with white border (weight 2)
  - When `activeTab !== 'area'`: preserve existing heat-point behavior
  - On tab change or "Limpar Análise": call `clearHexSelection`
  - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.5, 9.6_

  - [x] 10.1 Write property test — Property 9: Opportunity list ordering (fast-check)
    - **Property 9: Opportunity list ordering**
    - Generate random opportunity lists; verify rendered order is descending by `estimated_adv_gain`
    - **Validates: Requirements 5.2**

- [x] 11. Frontend — `CapOpportunityPanel` and `CapOpportunitySection` in `AreaAnalysisTab`
  - Create `CapOpportunityPanel` component (portal, same pattern as existing `ResultPanel`)
    - Lists Active partners with `adv_opportunity != null`, sorted by `estimated_adv_gain` descending
    - Each item shows: partner name, cap atual → cap sugerido, raio atual → raio sugerido, ganho estimado de ADV
    - Clicking an item calls `setSelectedCapOpportunity` (toggle); clicking again deselects
    - Empty state message when no opportunities exist
  - Add "Oportunidades de Cap" section button to `AreaAnalysisTab.tsx` (same button style as existing sections); when triggered, opens `CapOpportunityPanel` via `createPortal` and applies `Active` filter
  - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 5.7_

- [x] 12. Frontend — What-if toggle in `ManualAnalysisPanel`
  - Add "Simular reposicionamento de parceiro" toggle inside `PanelContent` in `ManualAnalysisPanel.tsx`, after the existing analysis form
  - Toggle sets `whatIfModeActive` in store; closing the panel resets it to false
  - When `whatIfModeActive` and `heatmapData` is null: show error message
  - Listen for `atlas:whatif-result` event and display result (partner name, simulated lat/lon, simulated cap, simulated radius, simulated ADV gain)
  - _Requirements: 6.1, 6.2, 6.3, 6.7, 6.8_

- [x] 13. Frontend — Hex selection summary in `AreaAnalysisTab`
  - Add `HexSelectionSummary` sub-component inside `AreaAnalysisTab` that reads `hexSelectionState` from store
  - Displays `totalDemandDaily`, `totalDemandResidual`, and comparison with `minAdv` from `recruitableAnalysis.params` when available
  - Visible only when `activeTab === 'area'` and at least one hex is selected
  - _Requirements: 9.2, 9.7_

- [x] 14. Final checkpoint — Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Property tests use **Hypothesis** (Python backend) and **fast-check** (TypeScript frontend), minimum 100 iterations each
- Each property test is tagged: `# Feature: partner-cap-optimization, Property N: <text>`
- Checkpoints ensure incremental validation before moving to the next phase
