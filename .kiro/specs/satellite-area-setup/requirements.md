# Requirements Document

## Introduction

This feature enables satellite areas (áreas satélite) to be set up independently — generating their own territories and ideal slots via the setup pipeline — while still being treated as annexed/aggregated areas of their canonical base during the daily pipeline. Currently, satellite codes are consolidated into the canonical base before setup runs, so satellites never produce their own territories. The desired behavior is: `run_setup` can be executed for satellite station codes (e.g., `XBA1`, `XCS1`) and produces a dedicated `territories_index.json` and `ideal_supply.json` scoped to that satellite; then `run_daily` reads those satellite territories and aggregates them under the canonical base for matching, reporting, and all downstream outputs.

## Glossary

- **Satellite_Area**: A delivery station whose code appears as a key in `STATION_ALIASES` (e.g., `XBA1`, `XCS1`). It has its own geographic jurisdiction polygon but is operationally subordinate to a canonical base.
- **Canonical_Base**: The delivery station that is the value in `STATION_ALIASES` for a given satellite (e.g., `DSA8` for `XBA1`). It owns the aggregated demand, reports, and partner matching.
- **Setup_Pipeline**: The execution of phases 1 and 2 (`run_setup`) that produces `territories_index.json` and `ideal_supply.json` for a given set of station codes.
- **Daily_Pipeline**: The execution of phases 3–5 (`run_daily`) that performs partner matching, weblead qualification, and report generation.
- **Territory**: A geographic cluster of H3 hexagons assigned to a single station code, identified by a `territory_id` of the form `{station_code}_bucket-{N}`.
- **Satellite_Territory**: A Territory whose `territory_id` prefix is a satellite station code (e.g., `XBA1_bucket-01`).
- **Canonical_Territory**: A Territory whose `territory_id` prefix is a canonical base code (e.g., `DSA8_bucket-01`).
- **Aggregation**: The process by which Satellite_Territories are logically grouped under their Canonical_Base during the Daily_Pipeline, without altering the `territory_id` stored on disk.
- **territories_index.json**: The JSON file persisted by the Setup_Pipeline containing territory metadata keyed by `territory_id`.
- **ideal_supply.json**: The JSON file persisted by the Setup_Pipeline containing ideal slot definitions per territory.
- **STATION_ALIASES**: The dictionary in `shared/config.py` mapping satellite station codes to their canonical base codes.
- **Demand_Map**: The per-hex package demand dictionary used by the Setup_Pipeline, keyed by H3 hex ID.
- **Jurisdiction_Polygon**: The Shapely polygon loaded from `jurisdiction.geojson` for a given station code, used to filter hexes during setup.

---

## Requirements

### Requirement 1: Independent Setup for Satellite Areas

**User Story:** As an operations analyst, I want to run the setup pipeline for a satellite station code, so that the satellite area gets its own territories and ideal slots independent of the canonical base.

#### Acceptance Criteria

1. WHEN `run_setup` is called with a satellite station code (a code present as a key in `STATION_ALIASES`), THE Setup_Pipeline SHALL execute phases 1 and 2 using only the hexes within the satellite's own jurisdiction polygon, without merging them into the canonical base's demand map.
2. WHEN the Setup_Pipeline completes for a satellite station code, THE Setup_Pipeline SHALL persist `territories_index.json` entries whose `station_code` field equals the satellite station code (e.g., `"XBA1"`), not the canonical base code.
3. WHEN the Setup_Pipeline completes for a satellite station code, THE Setup_Pipeline SHALL persist `ideal_supply.json` entries whose `station_code` field equals the satellite station code.
4. THE Setup_Pipeline SHALL accept satellite station codes in the `--stations` CLI argument without error or silent skip.
5. WHEN `run_setup` is called with a mix of canonical and satellite station codes (e.g., `--stations DSA8 XBA1`), THE Setup_Pipeline SHALL process each code independently, producing separate territory sets for each.

---

### Requirement 2: Satellite Demand Isolation During Setup

**User Story:** As an operations analyst, I want the satellite area's demand map to contain only packages delivered within the satellite's own jurisdiction, so that the resulting territories accurately reflect the satellite's geographic coverage.

#### Acceptance Criteria

1. WHEN `load_packages` is called for a setup run targeting a satellite station code, THE Demand_Map for that satellite SHALL contain only hexes whose centroid falls within the satellite's jurisdiction polygon.
2. WHEN `load_packages` is called for a setup run targeting a satellite station code, THE Setup_Pipeline SHALL NOT remap the satellite's packages to the canonical base via `STATION_ALIASES` before building the satellite's Demand_Map.
3. WHEN `load_packages` is called for a setup run targeting a canonical base, THE Demand_Map for the canonical base SHALL NOT include hexes that belong exclusively to a satellite's jurisdiction polygon (those hexes are reserved for the satellite's own setup).
4. IF a hex falls within both a satellite jurisdiction polygon and the canonical base jurisdiction polygon (overlap), THEN THE Setup_Pipeline SHALL assign that hex to the satellite's Demand_Map when the satellite setup is running, and to the canonical base's Demand_Map when the canonical base setup is running.

---

### Requirement 3: Satellite Territory Persistence and Identification

**User Story:** As a developer, I want satellite territories to be clearly identifiable in persisted artifacts, so that the daily pipeline can correctly aggregate them under the canonical base.

#### Acceptance Criteria

1. THE territories_index.json SHALL store each Satellite_Territory with a `station_code` field equal to the satellite station code (e.g., `"XBA1"`), not the canonical base code.
2. THE territories_index.json SHALL store each Satellite_Territory with a `canonical_base` field equal to the canonical base code (e.g., `"DSA8"`), derived from `STATION_ALIASES`.
3. WHEN a satellite station code is not present in `STATION_ALIASES`, THE Setup_Pipeline SHALL treat it as a canonical base and SHALL NOT write a `canonical_base` field (or SHALL write `null`).
4. THE ideal_supply.json SHALL store each slot for a Satellite_Territory with a `station_code` field equal to the satellite station code.

---

### Requirement 4: Daily Pipeline Aggregation of Satellite Territories

**User Story:** As an operations analyst, I want the daily pipeline to treat satellite territories as annexed areas of their canonical base, so that partner matching, weblead qualification, and reports reflect the full combined coverage of the canonical base and all its satellites.

#### Acceptance Criteria

1. WHEN `run_daily` loads `territories_index.json` and encounters a Satellite_Territory (identified by `canonical_base` field or by `STATION_ALIASES` lookup), THE Daily_Pipeline SHALL remap the territory's `station_code` in memory to the canonical base code before passing it to phases 3–5.
2. WHEN `run_daily` is called without a `--stations` filter, THE Daily_Pipeline SHALL include all Satellite_Territories from `territories_index.json` in the processing run, aggregated under their respective canonical bases.
3. WHEN `run_daily` is called with `--stations DSA8`, THE Daily_Pipeline SHALL include all Satellite_Territories whose canonical base is `DSA8` (e.g., `XBA1_bucket-*`) in addition to `DSA8`'s own territories.
4. WHEN `run_daily` is called with `--stations XBA1`, THE Daily_Pipeline SHALL process only the territories of `XBA1`, remapped to `DSA8`, and SHALL produce reports scoped to `DSA8` containing only those territories.
5. WHILE the Daily_Pipeline is running, THE Daily_Pipeline SHALL preserve the original `territory_id` (e.g., `XBA1_bucket-01`) in all output artifacts — it SHALL NOT rename territory IDs to use the canonical base prefix.

---

### Requirement 5: Report Aggregation Under Canonical Base

**User Story:** As an operations analyst, I want reports generated by the daily pipeline to aggregate satellite territories under the canonical base, so that I can see the full picture of a base's coverage including its satellite areas.

#### Acceptance Criteria

1. WHEN phase 5 generates `relatorio_executivo.json`, THE Report_Generator SHALL list Satellite_Territories under the canonical base's `territories` array, not as a separate base entry.
2. WHEN phase 5 generates `relatorio_executivo.json`, THE Report_Generator SHALL include a `satelliteOrigin` field on each territory object, set to the satellite station code for Satellite_Territories and `null` for Canonical_Territories.
3. WHEN phase 5 generates `relatorio_executivo.json`, THE Report_Generator SHALL aggregate demand, slot counts, and partner counts from Satellite_Territories into the canonical base's top-level metrics.
4. WHEN phase 5 generates `PARTNERS_PER_DS_BUCKET.csv`, THE Report_Generator SHALL use the satellite station code in the `station_code` column for partners matched to Satellite_Territories (preserving the original territory's station code).
5. WHEN phase 5 generates `optimization_data.geojson`, THE Report_Generator SHALL set the `delivery_station` property of Satellite_Territory hexes to the satellite station code (preserving the original), while the canonical base's `satelliteAreas` metadata field lists all satellite codes.

---

### Requirement 6: Backward Compatibility with Existing Canonical-Only Setup

**User Story:** As a developer, I want the new satellite setup behavior to be fully backward compatible, so that existing setups that do not use satellite codes continue to work without modification.

#### Acceptance Criteria

1. WHEN `run_setup` is called with only canonical base codes (no satellite codes), THE Setup_Pipeline SHALL behave identically to the current behavior, including the union of satellite jurisdiction polygons into the canonical base's jurisdiction (as currently done in `_load_jurisdiction_poly`).
2. WHEN `load_territories` loads a `territories_index.json` that was generated before this feature (no `canonical_base` field), THE Daily_Pipeline SHALL fall back to `STATION_ALIASES` lookup to determine if a territory belongs to a satellite, and SHALL remap it accordingly.
3. WHEN `run_daily` processes a `territories_index.json` that contains only Canonical_Territories (no satellite entries), THE Daily_Pipeline SHALL produce identical output to the current behavior.
4. THE Setup_Pipeline SHALL NOT break existing `CLUSTER_PER_STATION` configuration for canonical bases when satellite codes are added to a run.

---

### Requirement 7: CLI and Configuration Support

**User Story:** As an operations analyst, I want to be able to specify satellite station codes in the CLI and configuration, so that I can run setup and daily pipelines for satellite areas without modifying source code.

#### Acceptance Criteria

1. THE Orchestrator CLI SHALL accept satellite station codes in the `--stations` argument for both `--mode setup` and `--mode daily`.
2. WHEN a satellite station code is passed to `--mode setup` and that code is not present in `STATION_ALIASES`, THE Orchestrator SHALL log a warning identifying the unrecognized code and SHALL continue processing it as a canonical base.
3. THE `CLUSTER_PER_STATION` configuration in `shared/config.py` SHALL support satellite station codes as keys, allowing operators to specify the number of territory clusters for a satellite area independently.
4. WHEN `CLUSTER_PER_STATION` does not contain an entry for a satellite station code, THE Setup_Pipeline SHALL derive a default cluster count proportional to the satellite's demand relative to its canonical base's total demand.

---

### Requirement 8: Round-Trip Consistency of Territory Artifacts

**User Story:** As a developer, I want the territory artifacts written by setup and read by daily to be consistent, so that no data is lost or corrupted across pipeline runs.

#### Acceptance Criteria

1. FOR ALL satellite territories written to `territories_index.json` by the Setup_Pipeline, THE Daily_Pipeline SHALL be able to load and correctly identify them as satellite territories without error.
2. FOR ALL satellite slots written to `ideal_supply.json` by the Setup_Pipeline, THE Daily_Pipeline SHALL load them and associate them with the correct canonical base during matching.
3. WHEN `territories_index.json` is written and then read back by `load_territories`, THE loaded `TerritoriesResult` SHALL contain the same set of `territory_id` keys as were written, with `station_code` remapped to the canonical base in memory.
4. WHEN `ideal_supply.json` is written and then read back by `load_ideal_supply`, THE loaded `IdealSupplyResult` SHALL contain the same set of `slot_id` keys as were written, with `station_code` preserved as the satellite code.
