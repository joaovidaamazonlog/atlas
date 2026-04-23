# Requirements Document

## Introduction

The Atlas logistics optimization platform currently models hex coverage as binary and exclusive: each hex has at most one `covering_partner_id`, and `demand_allocated` is either the full `demand_daily` or zero. This does not reflect reality — the CP-SAT solver already produces per-hex package allocations per slot, meaning multiple partners can legitimately share a hex.

This feature replaces the binary coverage model with a multi-partner, allocation-aware model across three layers:

1. **Backend heatmap enrichment** (`_enrich_heatmap_with_residual`): each hex gains a `covering_partners` list with per-partner allocation and share, replacing the single `covering_partner_id`.
2. **Backend partner data** (`dados_mapa.json`): each Active/Onboarding partner gains a `hex_coverage` list derived from CP-SAT allocations.
3. **Frontend what-if simulation** (`PartnerWhatIfLayer.tsx` / `ManualAnalysisPanel.tsx`): the simulation uses hex-diff logic against the new coverage data to compute accurate ADV gain/loss.

---

## Glossary

- **Atlas**: The logistics optimization platform (Python backend + React/TypeScript frontend).
- **Heatmap_Enricher**: The backend function `_enrich_heatmap_with_residual` in `phase5_reports.py`.
- **Partner_Serializer**: The backend function `_write_dados_mapa` in `phase5_reports.py`.
- **WhatIf_Engine**: The frontend component `PartnerWhatIfLayer.tsx` and its drag-end calculation logic.
- **Result_Panel**: The what-if result section rendered inside `ManualAnalysisPanel.tsx`.
- **CP-SAT Solver**: The constraint-programming solver in `phase_setup.py` that produces `ideal_supply.json`.
- **IdealSlot**: A solver-generated slot with a list of `Allocation` objects (`hex_id`, `packages_assigned`).
- **PartnerMetrics**: The backend dataclass holding a matched partner's data, including `matched_slot_id` and `allocations`.
- **FitResult**: The output of Phase 3 containing all `TerritoryFit` objects and their matched partners.
- **hex_id**: An H3 cell identifier string (e.g., `"89a88cdb183ffff"`).
- **demand_daily**: The average daily package demand for a hex, stored in `heatmap.geojson` feature properties.
- **demand_allocated**: The sum of packages allocated to a hex across all covering partners.
- **demand_residual**: `demand_daily` minus `demand_allocated` for a hex.
- **packages_allocated**: The number of packages a specific partner is allocated to deliver in a specific hex.
- **share**: A partner's `packages_allocated` for a hex divided by the total `demand_allocated` for that hex.
- **covering_partners**: The list of partners covering a hex, each with `salesforce_id`, `packages_allocated`, and `share`.
- **hex_coverage**: A per-partner list of `{hex_id, packages_allocated}` entries stored in `dados_mapa.json`.
- **hexes_original**: The set of heatmap hexes whose centroids fall within a partner's delivery radius at the original position.
- **hexes_simulated**: The set of heatmap hexes whose centroids fall within a partner's delivery radius at the simulated (dragged) position.
- **adv_simulated**: The estimated ADV (Average Daily Volume) of a partner after repositioning.
- **adv_gain**: `adv_simulated` minus the partner's current `capacity`.
- **MAX_CAP**: The maximum operational capacity cap (80 packages/day).
- **salesforce_id**: The Salesforce identifier for a partner.

---

## Requirements

### Requirement 1: Multi-Partner Hex Coverage Index

**User Story:** As a backend engineer, I want the heatmap enrichment to build a per-hex index of all covering partners and their CP-SAT allocations, so that the coverage model reflects the solver's actual output.

#### Acceptance Criteria

1. WHEN `_enrich_heatmap_with_residual` runs, THE Heatmap_Enricher SHALL build an index mapping each `hex_id` to all Active or Onboarding partners whose matched slot's `allocations` list contains that `hex_id`.
2. WHEN building the coverage index, THE Heatmap_Enricher SHALL use the `allocations` field of each `IdealSlot` (from `FitResult`) as the authoritative source of per-hex package assignments, not the `grid_disk` neighborhood heuristic.
3. WHEN a hex appears in the allocations of multiple partners, THE Heatmap_Enricher SHALL include all such partners in the coverage index for that hex.
4. IF a partner has no `matched_slot_id` or the matched slot has no allocations, THEN THE Heatmap_Enricher SHALL exclude that partner from the coverage index.

### Requirement 2: Enriched Heatmap Hex Properties

**User Story:** As a frontend developer, I want each heatmap hex to carry a `covering_partners` list with per-partner allocation data, so that the map and what-if simulation can use accurate coverage information.

#### Acceptance Criteria

1. WHEN `_enrich_heatmap_with_residual` enriches a hex feature, THE Heatmap_Enricher SHALL set `demand_allocated` to the sum of `packages_allocated` across all covering partners for that hex.
2. WHEN `_enrich_heatmap_with_residual` enriches a hex feature, THE Heatmap_Enricher SHALL set `demand_residual` to `demand_daily` minus `demand_allocated`, rounded to 4 decimal places.
3. WHEN `_enrich_heatmap_with_residual` enriches a hex feature, THE Heatmap_Enricher SHALL set `is_covered` to `true` if and only if `demand_allocated` is greater than zero.
4. WHEN `_enrich_heatmap_with_residual` enriches a hex feature, THE Heatmap_Enricher SHALL set `covering_partners` to a list of objects, each containing `salesforce_id` (string), `packages_allocated` (float), and `share` (float rounded to 2 decimal places).
5. WHEN a hex has no covering partners, THE Heatmap_Enricher SHALL set `covering_partners` to an empty list `[]`.
6. THE Heatmap_Enricher SHALL NOT write a `covering_partner_id` field to any hex feature properties.
7. WHEN `demand_allocated` for a hex is greater than zero, THE Heatmap_Enricher SHALL ensure the sum of all `share` values in `covering_partners` equals 1.0 (within floating-point tolerance of 0.01).

### Requirement 3: Per-Partner Hex Coverage in Partner Data

**User Story:** As a frontend developer, I want each Active and Onboarding partner in `dados_mapa.json` to include a `hex_coverage` field, so that the what-if simulation can look up which hexes a partner currently covers and how many packages are allocated there.

#### Acceptance Criteria

1. WHEN `_write_dados_mapa` processes a partner record, THE Partner_Serializer SHALL add a `hex_coverage` field to each Active or Onboarding partner whose `salesforce_id` matches a `PartnerMetrics` entry with a `matched_slot_id`.
2. WHEN building `hex_coverage`, THE Partner_Serializer SHALL derive the list from the `allocations` of the partner's matched `IdealSlot`, producing one entry per allocation with `hex_id` (string) and `packages_allocated` (float).
3. WHEN a partner has no matched slot or no allocations, THE Partner_Serializer SHALL set `hex_coverage` to an empty list `[]`.
4. THE Partner_Serializer SHALL only add `hex_coverage` to partners with status `Active` or `Onboarding`; all other statuses SHALL receive no `hex_coverage` field.

### Requirement 4: Frontend Type Definitions for New Coverage Model

**User Story:** As a frontend developer, I want TypeScript types for the new coverage fields, so that the what-if simulation and map components are type-safe.

#### Acceptance Criteria

1. THE Atlas frontend SHALL define a `CoveringPartner` interface with fields `salesforce_id: string`, `packages_allocated: number`, and `share: number`.
2. THE Atlas frontend SHALL define a `HexCoverageEntry` interface with fields `hex_id: string` and `packages_allocated: number`.
3. THE Atlas frontend SHALL extend the `Partner` interface with an optional `hex_coverage` field of type `HexCoverageEntry[]`.
4. THE Atlas frontend SHALL update the heatmap feature properties type (or relevant GeoJSON property access) to include `covering_partners: CoveringPartner[]` instead of `covering_partner_id`.

### Requirement 5: What-If Simulation Using Hex-Diff Logic

**User Story:** As an operations manager, I want the what-if partner repositioning simulation to calculate ADV gain and loss using the actual hex coverage data, so that the simulation result is accurate and not based on total residual demand.

#### Acceptance Criteria

1. WHEN a partner marker is dragged to a new position within the 300 m guardrail, THE WhatIf_Engine SHALL compute `hexes_original` as the set of heatmap hex IDs whose centroids are within the partner's configured `radiusMeters` of the partner's original position.
2. WHEN a partner marker is dragged to a new position within the 300 m guardrail, THE WhatIf_Engine SHALL compute `hexes_simulated` as the set of heatmap hex IDs whose centroids are within the partner's configured `radiusMeters` of the dragged position.
3. WHEN computing the simulation result, THE WhatIf_Engine SHALL compute `loss` as the sum of `packages_allocated` for the dragging partner across all hexes in `hexes_original` that are NOT in `hexes_simulated`, using the partner's `hex_coverage` data.
4. WHEN computing the simulation result, THE WhatIf_Engine SHALL compute `gain` as the sum of `demand_residual` for all hexes in `hexes_simulated` that are NOT in `hexes_original`.
5. WHEN computing the simulation result, THE WhatIf_Engine SHALL compute `adv_simulated` as `min(max(partner.capacity - loss + gain, 0), MAX_CAP)`.
6. WHEN computing the simulation result, THE WhatIf_Engine SHALL compute `adv_gain` as `adv_simulated` minus `partner.capacity`.
7. IF a partner's `hex_coverage` field is absent or empty, THEN THE WhatIf_Engine SHALL treat `loss` as 0 for that partner.
8. WHEN the partner's `hex_coverage` data is unavailable for the heatmap, THE WhatIf_Engine SHALL dispatch an `atlas:whatif-warning` event with a descriptive message and SHALL NOT dispatch `atlas:whatif-result`.

### Requirement 6: What-If Result Panel Displays ADV Simulado

**User Story:** As an operations manager, I want the what-if result panel to display "ADV simulado" instead of "cap simulado", so that the label accurately reflects the metric being shown.

#### Acceptance Criteria

1. WHEN the what-if result panel renders a simulation result, THE Result_Panel SHALL display the label "ADV simulado" for the simulated capacity value.
2. WHEN the what-if result panel renders a simulation result, THE Result_Panel SHALL display the label "Ganho ADV" for the `adv_gain` value.
3. THE Result_Panel SHALL display `adv_simulated` and `adv_gain` values rounded to the nearest integer.

### Requirement 7: Backward Compatibility and Merge Safety

**User Story:** As a backend engineer, I want the enrichment functions to continue supporting partial station merges, so that running the pipeline for a single station does not corrupt data for other stations.

#### Acceptance Criteria

1. WHEN `_enrich_heatmap_with_residual` is called with a `stations` list, THE Heatmap_Enricher SHALL only overwrite `covering_partners`, `demand_allocated`, `demand_residual`, and `is_covered` for hex features whose `delivery_station` property is in the provided `stations` list.
2. WHEN `_enrich_heatmap_with_residual` is called with a `stations` list, THE Heatmap_Enricher SHALL preserve all properties of hex features belonging to stations not in the `stations` list without modification.
3. WHEN `_write_dados_mapa` is called with a `stations` list, THE Partner_Serializer SHALL only update `hex_coverage` for partners whose `delivery_station` is in the provided `stations` list.
