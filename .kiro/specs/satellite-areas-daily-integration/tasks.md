# Implementation Plan: Satellite Areas Daily Integration

## Overview

This plan implements the consolidation of satellite station handling into the `run_daily` pipeline. It is organized in seven phases, each independently testable and mergeable as a single PR. Backend is Python (pytest + Hypothesis) and frontend is TypeScript (vitest + fast-check).

The one-off cleanup (`scripts/cleanup_orphan_heatmap_features.py`) has already been executed and is NOT included as a task.

Each task references the specific acceptance criteria it implements using `_Requirements: X.Y_` annotations, and each property-based test sub-task references the correctness property it validates from the design document.

## Tasks

### Phase 1 — Backend: Automatic satellite detection in `run_daily`

- [x] 1. Wire satellite detection into the daily orchestrator
  - [x] 1.1 Implement `_detect_satellite_stations(territories)` helper
    - Add the helper in `backend/vanilla/orchestrator.py` (or a small module imported by it)
    - Extract satellite codes from `territories.territory_index` using the `canonical_base` truthy flag and the `territory_id` prefix (before the first `_`)
    - Return an empty `set()` when no satellites are present
    - _Requirements: 1.1, 8.1, 8.2_

  - [x] 1.2 Invoke `load_packages` with auto-detected `satellite_setup_stations` in `run_daily`
    - Call `_detect_satellite_stations(territories)` before `load_packages`
    - Pass the resulting set as `satellite_setup_stations` (or `None` when empty) to `load_packages`
    - Add a concise log line listing detected satellites when non-empty
    - _Requirements: 1.1, 1.2, 8.1, 8.2, 8.3_

  - [ ]* 1.3 Write unit tests for `_detect_satellite_stations`
    - Canonicals-only index → `set()`
    - Satellites-only index → all prefixes returned
    - Mixed index → only satellite prefixes returned
    - _Requirements: 1.1, 8.1, 8.2_

  - [ ]* 1.4 Write property test for automatic satellite detection
    - **Property 1: Automatic satellite detection**
    - **Validates: Requirements 1.1, 8.1, 8.2**
    - Hypothesis generator: `territories_index` with a random mixture of canonical territories (codes starting with `D`) and satellite territories (codes starting with `X`/`P`, `canonical_base` truthy)

  - [ ]* 1.5 Write property test for satellite isolation and volume conservation
    - **Property 2: Satellite isolation and volume conservation**
    - **Validates: Requirements 1.2, 1.3, 1.4, 1.5, 3.1, 3.2, 3.3, 3.4**
    - Hypothesis generator: random packages CSV with `station_code` drawn from `{canonicals ∪ satellites}`; exercise `load_packages(..., satellite_setup_stations=S)` over several `S` subsets

  - [ ]* 1.6 Write integration test that `run_daily` passes satellites to `load_packages`
    - Mock setup returns an index containing `XBA1`; assert `load_packages` is invoked with `satellite_setup_stations={"XBA1"}`
    - _Requirements: 1.1, 8.1, 8.2_

- [x] 2. Checkpoint — Phase 1
  - Ensure all tests pass, ask the user if questions arise.

### Phase 2 — Heatmap unification

- [x] 3. Replace the two `patch_heatmap_*` steps with a single unified writer
  - [x] 3.1 Implement `write_heatmap_unified(output_dir, territories, pkg, fit)`
    - New function in `backend/vanilla/phase5_reports.py` (or `backend/vanilla/heatmap_writer.py`)
    - One feature per hex, iterating over `territories.territory_index` as the single source of truth
    - `delivery_station` is the original code extracted from the `territory_id` prefix
    - Populate `canonical_base`, `demand_total`, `demand_daily`, `demand_residual`, `is_covered`, `in_jurisdiction=True`, `covering_partners`, `ceps`
    - Drop the legacy `demand_allocated` property
    - Abort with a clear error if a duplicate `hex_id` is encountered (violates setup invariant)
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 3.1, 3.2, 3.3, 3.4_

  - [x] 3.2 Wire `write_heatmap_unified` into `run_daily` and remove legacy patches
    - Call the unified writer in phase 5 (reports), right after the partner fit is available
    - Remove the calls to `patch_heatmap_satellite_stations` and `patch_heatmap_add_satellite_hexes` in `orchestrator.run_daily` (lines around 236 and 239)
    - Remove the function definitions from `backend/vanilla/phase_setup.py` and drop their imports from the orchestrator
    - _Requirements: 2.5_

  - [ ]* 3.3 Write unit test for `write_heatmap_unified`
    - Fixture: index with `DSA8_bucket-01` (3 hexes) + `XBA1_bucket-01` (2 hexes) and a `pkg` with packages in both stations
    - Assert: 5 features in output, each with correct `delivery_station`, zero duplicates, `territory_id` consistent with the index
    - _Requirements: 2.1, 2.2, 2.3, 2.4_

  - [ ]* 3.4 Write static test that legacy `patch_heatmap_*` calls are gone
    - Grep `backend/vanilla/orchestrator.py` for `patch_heatmap_` occurrences → must be empty
    - Verify the functions are absent from `backend/vanilla/phase_setup.py`
    - _Requirements: 2.5_

  - [ ]* 3.5 Write property test for heatmap `delivery_station` consistency
    - **Property 3: Heatmap delivery_station consistency**
    - **Validates: Requirements 2.1, 2.2**
    - Hypothesis generator: random `territories_index`, mock `pkg`; invoke `write_heatmap_unified` and assert `delivery_station == original_code(territory_id)` for every feature

  - [ ]* 3.6 Write property test for heatmap hex uniqueness
    - **Property 4: Heatmap hex uniqueness**
    - **Validates: Requirements 2.3**
    - Hypothesis generator: same as Property 3, with hex disjointness guaranteed between territories

  - [ ]* 3.7 Write property test for heatmap having no orphan features
    - **Property 5: Heatmap has no orphan features**
    - **Validates: Requirements 2.4**
    - Assert every output feature satisfies `territory_id in territories_index`

- [x] 4. Checkpoint — Phase 2
  - Ensure all tests pass, ask the user if questions arise.

### Phase 3 — Partner fit cross-station rule

- [x] 5. Make `_get_territory_for_partner` deterministic for canonical↔satellite coverage
  - [x] 5.1 Implement majority + alphabetical tiebreak in `backend/vanilla/phase3_partner_fit.py`
    - Detect the canonical↔satellite case (partner covers hexes in a canonical `C` and in at least one satellite anchored to `C`)
    - Pick the winner as the station with the most covered hexes; break ties by `min()` alphabetical order over tied station codes
    - Emit a `log.warning` identifying the partner, the stations involved, and the chosen winner
    - Within the winning station, attribute the partner to the territory with the most covered hexes
    - Preserve the existing behavior for partners that do not span canonical↔satellite
    - _Requirements: 4.1, 4.2, 4.3, 4.4_

  - [ ]* 5.2 Write unit test for the majority + alphabetical rule
    - 3 hexes in DSA8 and 1 in XBA1 → assigned to DSA8
    - 2 hexes in DSA8 and 2 in XBA1 → assigned to DSA8 (alphabetical tiebreak)
    - Verify `caplog` captures the warning with the partner id and involved stations
    - _Requirements: 4.4_

  - [ ]* 5.3 Write property test for partner purity preservation
    - **Property 6: Partner purity preservation**
    - **Validates: Requirements 4.1, 4.2, 4.3**
    - Hypothesis generator: partners whose `hex_coverage` is strictly contained in a single station's territories; assert partner is assigned to that station

  - [ ]* 5.4 Write property test for deterministic cross-station tiebreak
    - **Property 7: Partner cross-station deterministic tiebreak**
    - **Validates: Requirements 4.4**
    - Hypothesis generator: partners with canonical↔satellite coverage; run `_get_territory_for_partner` twice and assert equal output; assert winner is the majority station; assert alphabetical tiebreak on empate

- [x] 6. Checkpoint — Phase 3
  - Ensure all tests pass, ask the user if questions arise.

### Phase 4 — Idempotence and territory preservation

- [x] 7. Guarantee the daily is idempotent and preserves territory structure
  - [x] 7.1 Audit `run_daily` to confirm no mutation of `hex_ids`, `canonical_base`, or `territory_id`
    - Inspect `load_territories` and subsequent phases; ensure only `daily_demand` and `partners` are recomputed
    - If any mutation is found, fix it (e.g., stop writing back fields that should be immutable in daily)
    - _Requirements: 5.1, 5.2, 5.3_

  - [x] 7.2 Add an end-to-end integration test for the satellite daily pipeline
    - Location: `backend/tests/integration/test_daily_satellite_pipeline.py`
    - Fixture: pre-setup `territories_index.json` with DSA8 + XBA1, packages CSV with deliveries in both codes
    - Run `run_daily` twice in a row; capture `heatmap_1/2.geojson`, `territories_1/2.json`, `relatorio_1/2.json`
    - Assert `heatmap_1 == heatmap_2` (sorted by `hex_id`) and the same for the territories index
    - Assert features with `territory_id` starting with `XBA1_` have `delivery_station == "XBA1"`; features with `DSA8_` prefix have `delivery_station == "DSA8"`
    - Assert no `hex_id` appears twice in `heatmap_1`
    - _Requirements: 5.1, 5.2, 5.3, 5.4_

  - [ ]* 7.3 Write property test for territory structure preservation
    - **Property 8: Territory structure preservation**
    - **Validates: Requirements 5.1, 5.2, 5.3**
    - Hypothesis generator: mini end-to-end fixture; compare `set(territory_index.keys())`, `hex_ids`, and `canonical_base` before and after a daily run

  - [ ]* 7.4 Write property test for daily idempotence
    - **Property 9: Daily idempotence**
    - **Validates: Requirements 5.4**
    - Hypothesis generator: randomized packages and fixed partners; run `run_daily` twice and assert equal outputs (demand, residual, is_covered, partner lists, heatmap feature set)

- [x] 8. Checkpoint — Phase 4
  - Ensure all tests pass, ask the user if questions arise.

### Phase 5 — `relatorio_executivo.json` aggregation

- [x] 9. Emit `satellites[]` nested under their canonicals in the executive report
  - [x] 9.1 Update the report aggregator in `backend/vanilla/phase5_reports.py`
    - For each canonical base, attach a `satellites: BaseRow[]` array populated with its anchored satellites
    - Keep each satellite as a top-level entry in `bases[]` for backward compatibility, but set `parentCanonical` to the canonical code on the satellite entry and `null` on canonicals
    - Ensure canonical row metrics (`numTerritories`, `dailyDemand`, partner counters) count only the canonical's own territories and packages (do NOT sum satellites into the canonical row)
    - _Requirements: 7.3, 7.4_

  - [ ]* 9.2 Write unit test for the new aggregator output shape
    - Fixture with DSA8 + XBA1 (satellite) in the index
    - Assert `bases` contains DSA8 with `satellites: [{ code: "XBA1", parentCanonical: "DSA8", ... }]`
    - Assert XBA1 also exists as a top-level entry with `parentCanonical: "DSA8"`
    - Assert DSA8 metrics do not include XBA1's packages
    - _Requirements: 7.3, 7.4_

- [x] 10. Checkpoint — Phase 5
  - Ensure all tests pass, ask the user if questions arise.

### Phase 6 — Frontend evaluator: satellite preserves identity

- [x] 11. Update `recruitableAreaEvaluator` to stop collapsing satellites
  - [x] 11.1 Remove `resolveCanonical()` collapse in `atlas-react/src/lib/recruitableAreaEvaluator.ts`
    - Replace `return ds ? resolveCanonical(ds) : null;` with `return ds ?? null;` in the station-for-hex resolution
    - Ensure `hexesByStation` groups satellite codes separately from their canonicals (no `STATION_ALIASES` collapse)
    - Update the legacy-heatmap fallback in `stationForHex` to avoid `resolveCanonical`
    - _Requirements: 6.1, 6.3, 6.4_

  - [x] 11.2 Add `canonicalBaseFor(ds)` helper and export it
    - Return the satellite's canonical (e.g., `"XSP7" → "DSP5"`) using `SATELLITE_TO_CANONICAL`
    - Return `undefined` for canonical codes (e.g., `"DSP5" → undefined`)
    - _Requirements: 6.2_

  - [x] 11.3 Extend `EvaluatorResult` with `recommendedStation` and `canonicalBase`
    - Update the type in `atlas-react/src/store/types.ts`
    - Populate both fields at the end of `evaluateRecruitableArea` (`recommendedStation = dominantStation`; `canonicalBase = canonicalBaseFor(recommendedStation)`)
    - _Requirements: 6.1, 6.2_

  - [x] 11.4 Render "Anexo de {canonical}" badge in the evaluator UI panel
    - Wire the badge into the evaluator result panel, visible only when `canonicalBase` is defined
    - Keep degradation silent when `canonicalBase` is missing (e.g., legacy result)
    - _Requirements: 6.2_

  - [ ]* 11.5 Write unit tests for the evaluator changes (vitest)
    - 5 hexes in XBA1 inside the radius → `recommendedStation === "XBA1"`, `canonicalBase === "DSA8"`
    - 3 hexes XBA1 + 2 hexes DSA8 inside the radius → dominant is XBA1, `recommendedStation === "XBA1"`
    - `canonicalBaseFor("XSP7") === "DSP5"`; `canonicalBaseFor("DSP5") === undefined`
    - _Requirements: 6.1, 6.2, 6.3, 6.4_

  - [ ]* 11.6 Write property test for evaluator satellite recommendation
    - **Property 10: Evaluator satellite recommendation**
    - **Validates: Requirements 6.1, 6.2, 6.4**
    - fast-check generator: heatmap features with `delivery_station` drawn from `{canonical, satellite}`; random radius and center; assert `recommendedStation` and `canonicalBase` invariants

  - [ ]* 11.7 Write property test for evaluator group separation
    - **Property 11: Evaluator group separation**
    - **Validates: Requirements 6.3**
    - fast-check generator: mixed heatmap (canonical + anchored satellite inside the radius); inspect internal `hexesByStation` / selected cells and assert no collapse via `STATION_ALIASES`

- [x] 12. Checkpoint — Phase 6
  - Ensure all tests pass, ask the user if questions arise.

### Phase 7 — Dashboard operacional: parent-child rendering

- [x] 13. Render satellites as indented child rows under their canonical
  - [x] 13.1 Update `BaseReport` type and consumers in `atlas-react/src/lib/reportUtils.ts`
    - Add optional `parentCanonical?: string | null` and `satellites?: BaseReport[]`
    - Keep existing fields intact for backward compatibility
    - _Requirements: 7.1, 7.2_

  - [x] 13.2 Render nested rows in the `ManagementDashboard` component
    - For each canonical, render its own row, then (if expanded) render each satellite from `satellites[]` with `pl-8` indentation and a `└─` leading glyph
    - Suppress top-level rendering of satellite entries whose `parentCanonical` is populated (already rendered under the parent)
    - _Requirements: 7.1, 7.2_

  - [x] 13.3 Add expand/collapse state with localStorage persistence
    - Local state `expandedCanonicals: Set<string>` defaulting to all expanded
    - Chevron button on the canonical row toggles the state; persist across sessions via `localStorage`
    - _Requirements: 7.5_

  - [x] 13.4 Render the canonical + satellites total row
    - Compute the sum at render time (do not mutate the canonical metrics) and label it `Total {canonical} + satélites`
    - _Requirements: 7.4_

  - [ ]* 13.5 Write snapshot/DOM test for `ManagementDashboard`
    - Fixture `relatorio_executivo.json` with DSA8 and satellite XBA1 nested under it
    - Assert the DSA8 row is followed by an XBA1 row with `pl-8` indentation and the chevron toggle works
    - Assert the total row shows `Total DSA8 + satélites`
    - _Requirements: 7.1, 7.2, 7.4, 7.5_

- [x] 14. Final checkpoint — Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for a faster MVP; all core implementation tasks are non-optional.
- Each task references the specific acceptance criteria from `requirements.md` it validates.
- Property-based tests reference the numbered properties from the design's "Correctness Properties" section. Python PBTs use Hypothesis; TypeScript PBTs use fast-check. Each PBT runs at least 100 iterations.
- Checkpoints sit between phases so each phase can be reviewed and merged independently.
- The one-off cleanup (`scripts/cleanup_orphan_heatmap_features.py`) has already been executed in the environment and is intentionally not a task here.
