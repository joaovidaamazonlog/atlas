# Implementation Plan: Hex Partner Coverage Model

## Overview

Replace the binary single-partner hex coverage model with a multi-partner, allocation-aware model. The implementation spans three layers: backend heatmap enrichment, backend partner serialization, and frontend what-if simulation. Each layer builds on the CP-SAT solver's actual per-hex allocations stored in `PartnerMetrics.allocations`.

## Tasks

- [x] 1. Build the hex coverage index in `_enrich_heatmap_with_residual`
  - In `backend/phase5_reports.py`, replace the existing `covering_partners` dict (origin_hex → one partner) with a `hex_coverage_index: Dict[str, List[Tuple[PartnerMetrics, int]]]` built by iterating `fit.all_partners()` and appending `(partner, alloc.packages_assigned)` for each `alloc` in `partner.allocations`, skipping partners whose `status` is not `Active`/`Onboarding` or whose `matched_slot_id` is falsy
  - Remove all `h3.grid_disk` neighborhood heuristic calls used for coverage detection
  - _Requirements: 1.1, 1.2, 1.3, 1.4_

  - [x] 1.1 Write property test for coverage index correctness
    - **Property 1: Coverage Index Correctness**
    - Generate arbitrary lists of `PartnerMetrics` with mixed statuses, matched/unmatched slots, and allocations; assert the resulting index contains exactly the Active/Onboarding partners with a `matched_slot_id` whose allocations include each hex — no more, no fewer
    - **Validates: Requirements 1.1, 1.3, 1.4**

- [x] 2. Rewrite hex enrichment logic in `_enrich_heatmap_with_residual`
  - For each heatmap feature in the target stations, look up `hex_coverage_index.get(hex_id, [])` and compute `demand_allocated` (sum of packages), `demand_residual` (rounded to 4 decimal places), `is_covered`, and `covering_partners` list (each entry: `salesforce_id`, `packages_allocated`, `share` rounded to 2 decimal places)
  - Write these four fields to `props`; do NOT write `covering_partner_id`
  - When `demand_allocated == 0`, set `share = 0.0` for all entries and skip division
  - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6_

  - [x] 2.1 Write property test for hex enrichment invariants
    - **Property 2: Hex Enrichment Invariants**
    - Generate arbitrary hex features and allocation lists; assert `demand_allocated` equals sum of packages, `demand_residual` equals `round(demand_daily - demand_allocated, 4)`, `is_covered` equals `demand_allocated > 0`, each `covering_partners` entry has the three required fields, and `covering_partner_id` is absent
    - **Validates: Requirements 2.1, 2.2, 2.3, 2.4, 2.5, 2.6**

  - [x] 2.2 Write property test for share sum invariant
    - **Property 3: Share Sum Invariant**
    - Generate arbitrary lists of positive `packages_allocated` floats (min_size=1); assert the sum of all computed `share` values equals 1.0 within tolerance 0.01
    - **Validates: Requirements 2.7**

  - [x] 2.3 Write unit test: `covering_partner_id` absent and partner with `matched_slot_id=None` excluded
    - Verify `covering_partner_id` is absent from enriched properties (Requirement 2.6)
    - Verify a partner with `matched_slot_id = None` does not appear in the coverage index (Requirement 1.4)

- [x] 3. Add `hex_coverage` field in `_write_dados_mapa`
  - In `backend/phase5_reports.py`, inside the partner update loop, add a block that sets `record["hex_coverage"]` to `[{"hex_id": a.hex_id, "packages_allocated": a.packages_assigned} for a in pm.allocations]` when `pm.status in ("Active", "Onboarding")`; set it to `[]` when the partner has no matched slot or no allocations; do not add the field for any other status
  - The existing `stations` filter on the outer loop already ensures only target-station partners are updated
  - _Requirements: 3.1, 3.2, 3.3, 3.4_

  - [x] 3.1 Write property test for hex coverage derivation round-trip
    - **Property 4: Hex Coverage Derivation Round-Trip**
    - Generate arbitrary Active/Onboarding partners with non-empty allocations; assert `hex_coverage` contains exactly one entry per allocation with matching `hex_id` and `packages_allocated`; generate non-Active/Onboarding partners and assert no `hex_coverage` field is written
    - **Validates: Requirements 3.1, 3.2, 3.3, 3.4**

  - [x] 3.2 Write unit test: `hex_coverage` absent for non-Active/Onboarding statuses
    - Verify `hex_coverage` is absent for partners with status `BG Checks`, `Inactive`, and `Exited` (Requirement 3.4)

- [x] 4. Checkpoint — Ensure all backend tests pass
  - Ensure all backend property and unit tests pass; ask the user if questions arise.

- [x] 5. Implement partial merge preservation for both backend functions
  - Verify that `_enrich_heatmap_with_residual` skips hex features whose `delivery_station` is not in the provided `stations` list, leaving all their properties untouched
  - Verify that `_write_dados_mapa` skips partner records whose `delivery_station` is not in the provided `stations` list
  - _Requirements: 7.1, 7.2, 7.3_

  - [x] 5.1 Write property test for partial merge preservation
    - **Property 7: Partial Merge Preservation**
    - Generate multi-station heatmaps and arbitrary `stations` lists; assert all hex features and partner records belonging to stations NOT in the list are byte-for-byte identical before and after running both functions
    - **Validates: Requirements 7.1, 7.2, 7.3**

  - [x] 5.2 Write unit test: single-station run does not modify other station's data
    - Run `_write_dados_mapa` with `stations=["DSP2"]` and assert no partner record from `DSP4` is modified (Requirement 7.3)

- [x] 6. Add TypeScript type definitions in `atlas-react/src/store/types.ts`
  - Add `CoveringPartner` interface with `salesforce_id: string`, `packages_allocated: number`, `share: number`
  - Add `HexCoverageEntry` interface with `hex_id: string`, `packages_allocated: number`
  - Extend the `Partner` interface with `hex_coverage?: HexCoverageEntry[]`
  - Update any runtime property access for heatmap features to use `covering_partners: CoveringPartner[]` instead of `covering_partner_id`
  - _Requirements: 4.1, 4.2, 4.3, 4.4_

  - [x] 6.1 Write unit test: TypeScript compilation verifies new type definitions
    - Confirm `CoveringPartner`, `HexCoverageEntry`, and `Partner.hex_coverage` compile without errors and that any reference to `covering_partner_id` in type-checked code is removed

- [x] 7. Build `heatmapIndex` in `PartnerWhatIfLayer.tsx`
  - Add a `useMemo` that builds `Map<string, GeoJSON.Feature>` keyed by `hex_id` from `heatmapFeatures`, skipping features without a `hex_id` property
  - Pass `heatmapIndex` down to each `WhatIfMarker` component
  - _Requirements: 5.1, 5.2_

- [x] 8. Implement hex-diff engine in `PartnerWhatIfLayer.tsx`
  - Replace `sumResidualWithinRadius` with `getHexesWithinRadius(features, lat, lon, radiusMeters): Set<string>` that computes the centroid of each feature (Point coordinates directly; Polygon/MultiPolygon via `turf.centroid`) and includes the hex if `turf.distance` ≤ `radiusMeters`
  - In `handleDragEnd`, compute `hexesOriginal` and `hexesSimulated`, derive `hexesLost` and `hexesGained` as set differences, build `hexCoverageMap` from `partner.hex_coverage ?? []`, compute `loss`, `gain`, `advSimulated`, and `advGain` per the formula `min(max(capacity - loss + gain, 0), MAX_CAP)`
  - Apply the guard: if `partner.hex_coverage` is absent or empty AND `hexesLost.size > 0`, dispatch `atlas:whatif-warning` and return without dispatching `atlas:whatif-result`; if no hexes are lost, treat `loss = 0` and proceed
  - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 5.7, 5.8_

  - [x] 8.1 Write property test for hex-diff disjointness
    - **Property 5: Hex-Diff Disjointness**
    - Generate arbitrary pairs of hex ID sets; assert `hexesLost ∩ hexesGained = ∅` for all inputs
    - **Validates: Requirements 5.1, 5.2**

  - [x] 8.2 Write property test for ADV simulation formula
    - **Property 6: ADV Simulation Formula**
    - Generate arbitrary `capacity` (integer 0–80), `loss` (float ≥ 0), `gain` (float ≥ 0); assert `advSimulated === Math.min(Math.max(capacity - loss + gain, 0), 80)` and `advGain === advSimulated - capacity`
    - **Validates: Requirements 5.5, 5.6**

  - [x] 8.3 Write unit test: warning dispatched when `hex_coverage` absent and hexes are lost
    - Verify `atlas:whatif-warning` is dispatched and `atlas:whatif-result` is NOT dispatched when `hex_coverage` is absent/empty and `hexesLost.size > 0` (Requirement 5.8)

- [x] 9. Update `WhatIfResult` interface and result panel labels in `ManualAnalysisPanel.tsx`
  - Rename `simulatedCap` → `advSimulated` and `simulatedAdvGain` → `advGain` in the `WhatIfResult` interface and all usages
  - Change the rendered label `"Cap simulado"` → `"ADV simulado"` and `"Ganho de ADV (cap simulado − cap atual)"` → `"Ganho ADV"`
  - Display values as `Math.round(advSimulated)` and `Math.round(advGain)`
  - _Requirements: 6.1, 6.2, 6.3_

  - [x] 9.1 Write unit test: result panel renders correct labels and rounded values
    - Verify the panel renders `"ADV simulado"` and `"Ganho ADV"` labels and that values are rounded to the nearest integer (Requirements 6.1, 6.2, 6.3)

- [x] 10. Checkpoint — Ensure all frontend tests pass
  - Ensure all frontend property and unit tests pass; ask the user if questions arise.

- [x] 11. Wire backend and frontend together with integration tests
  - [x] 11.1 Write backend integration test: full Phase 5 pipeline on fixture `FitResult`
    - Run the full Phase 5 pipeline on a fixture `FitResult` and verify the output `heatmap.geojson` contains `covering_partners` lists and no `covering_partner_id` fields; verify `dados_mapa.json` contains `hex_coverage` for Active/Onboarding partners and not for others
    - _Requirements: 1.1–1.4, 2.1–2.7, 3.1–3.4_

  - [x] 11.2 Write backend integration test: single-station run isolation
    - Verify that running the pipeline for station `DSP2` does not modify any hex or partner record belonging to `DSP4` in the output files
    - _Requirements: 7.1, 7.2, 7.3_

- [x] 12. Final checkpoint — Ensure all tests pass
  - Ensure all backend and frontend tests pass; ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for a faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation at the backend and frontend boundaries
- Property tests validate universal correctness properties using Hypothesis (Python) and fast-check (TypeScript)
- Unit tests validate specific examples and edge cases
- The `heatmapIndex` Map (Task 7) must be built before the hex-diff engine (Task 8) since it is passed as a prop
