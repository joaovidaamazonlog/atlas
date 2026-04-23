# Implementation Plan: GeoIntelligence Restructure

## Overview

Migrate all internal GeoIntelligence pipeline state from Turso to local SQLite, unify the geo daily execution path with the vanilla Phase 3–5 pipeline, remove the `--update-heatmap` CLI flag, and migrate `empresas_alvo` geocoding to a local Nominatim instance. The implementation proceeds in dependency order: storage layer first, then ETL, then orchestrator updates, then cleanup.

## Tasks

- [x] 1. Create `local_writer.py` — SQLite replacement for TursoWriter
  - Create `backend/geo_intelligence/local_writer.py`
  - Implement `LocalWriter.__init__` that reads `GEO_SQLITE_PATH` env var (default: `output/geo_intelligence/geo_intelligence.db`), calls `Path(db_path).parent.mkdir(parents=True, exist_ok=True)`, and opens a `sqlite3` connection
  - Implement `ensure_schema()` applying all `CREATE TABLE IF NOT EXISTS` and `CREATE INDEX IF NOT EXISTS` DDL for all InternalGeoTables: `geo_run_metadata`, `geo_territories`, `geo_h3_cells`, `geo_ideal_supply`, `geo_scorecard`, `geo_partner_cap_opportunities`, `geo_partner_history`, `geo_partner_profiles`; apply `ALTER TABLE` migrations gracefully (catch "duplicate column name" errors at DEBUG level)
  - Implement `upsert_run`, `finalize_run`, `upsert_territories`, `upsert_h3_cells`, `upsert_ideal_supply`, `upsert_scorecard`, `update_supply_match`, `update_territory_fit`, `upsert_partner_profiles`, `upsert_cap_opportunities`, `upsert_partner_history` — all with `INSERT OR REPLACE` / `INSERT … ON CONFLICT DO UPDATE` semantics matching `TursoWriter`
  - Implement `upsert_empresas_geo(rows)` and `upsert_empresas_alvo(rows)` for ETL use
  - Implement `close()` to close the SQLite connection
  - Use `executemany` for batch operations; no retry logic needed (local I/O)
  - _Requirements: 1.1, 1.2, 1.5, 1.7, 6.1, 6.2, 6.3, 6.4, 6.5_
  - _Design: Components → LocalWriter_

  - [x] 1.1 Implement `LocalWriter` class with schema creation and all upsert methods
    - Write the full class as described above
    - _Requirements: 1.1, 1.2, 1.5, 6.1, 6.2, 6.3, 6.4, 6.5_

  - [ ]* 1.2 Write property test for LocalWriter upsert idempotence
    - **Property 1: LocalWriter upsert idempotence**
    - Generate random `geo_run_metadata` rows with Hypothesis; write once, write again with the same primary key, verify row count and field values are unchanged
    - Tag: `# Feature: geo-intelligence-restructure, Property 1: LocalWriter upsert idempotence`
    - **Validates: Requirements 1.5, 6.1, 6.2, 6.3**

  - [ ]* 1.3 Write unit tests for `LocalWriter`
    - Test schema creation: verify all 9 tables exist after `ensure_schema()`
    - Test schema idempotence: call `ensure_schema()` twice, verify no error
    - Test `upsert_run` / `finalize_run`: write a run, read it back, verify fields
    - Test `update_supply_match`: write slots, update `matched_partner_id`, read back
    - Test `update_territory_fit`: write territories, update `attainment`/`accuracy`, read back
    - Test directory creation: point `GEO_SQLITE_PATH` to a non-existent directory, verify it is created
    - _Requirements: 1.1, 1.2, 1.5, 6.1, 6.2, 6.3, 6.4, 6.5_

- [x] 2. Add `empresas_alvo` local table schema to `LocalWriter`
  - Add `CREATE TABLE IF NOT EXISTS empresas_alvo` DDL to `ensure_schema()` with the exact same schema as the Turso `empresas_alvo` table (columns: `cnpj`, `razao_social`, `nome_fantasia`, `cnae_principal`, `cnae_secundaria`, `endereco`, `bairro`, `cep`, `uf`, `municipio`, `telefone_1`, `email`, `porte`, `situacao_cadastral`, `data_abertura`, `capital_social`, `synced_at`)
  - Add `CREATE INDEX IF NOT EXISTS idx_empresas_alvo_cep` and `idx_empresas_alvo_uf`
  - Ensure `upsert_empresas_alvo` uses `INSERT OR REPLACE` keyed on `cnpj`
  - _Requirements: 5.1, 5.14, 10.7_
  - _Design: Data Models → SQLite Schema → empresas_alvo_

  - [x] 2.1 Add `empresas_alvo` DDL and indexes to `LocalWriter.ensure_schema()`
    - _Requirements: 5.1, 5.14, 10.7_

  - [ ]* 2.2 Write unit test: verify `empresas_alvo` table and indexes exist after `ensure_schema()`
    - Also verify that `gmaps_leads` and `contactadas` are NOT in `sqlite_master` (SharedTursoTables must not be migrated)
    - _Requirements: 1.9, 5.14_

- [x] 3. Create `local_reader.py` — SQLite replacement for TursoReader
  - Create `backend/geo_intelligence/local_reader.py`
  - Implement `LocalReader.__init__` that opens the SQLite database (read-write mode; falls back gracefully if file does not exist yet) and initialises the same TTL cache as `TursoReader` (`_cache: dict[str, tuple[float, object]]`, `_cache_ttl_s`)
  - Implement `get_latest_run_id(station_code)`: query `geo_run_metadata` for the most recent `run_id` with `status='setup_complete'`; fall back to `status='completed'`; return `None` if neither exists
  - Implement `get_territories(station_code, run_id, region_type=None, min_gap=None)`, `get_h3_cells(territory_id, run_id)`, `get_h3_cells_for_station(station_code, run_id)`, `get_scorecard(station_code, run_id)`, `get_ideal_supply(station_code, run_id)`, `get_cap_opportunities(station_code, run_id=None, only_with_opportunity=False)` — all with the same signatures as `TursoReader`
  - Implement `invalidate(key=None)` to clear the TTL cache
  - Return rows as `list[dict]` (use `sqlite3.Row` with `row_factory = sqlite3.Row` and convert to dict)
  - _Requirements: 1.4, 1.6, 7.6_
  - _Design: Components → LocalReader_

  - [x] 3.1 Implement `LocalReader` class with all query methods and TTL cache
    - _Requirements: 1.4, 1.6, 7.6_

  - [ ]* 3.2 Write property test for setup round-trip (write via LocalWriter, read via LocalReader)
    - **Property 2: Setup round-trip — territories and ideal supply**
    - Generate random lists of territory and ideal supply dicts with Hypothesis; write via `LocalWriter`, read back via `LocalReader.get_territories()` and `LocalReader.get_ideal_supply()`, verify field equivalence for `territory_id`, `station_code`, `run_id`, `lat`, `lon`, `radius_km`, `capacity_day`, `origin_hex`
    - Tag: `# Feature: geo-intelligence-restructure, Property 2: Setup round-trip`
    - **Validates: Requirements 1.3, 1.4, 7.2, 7.3**

  - [ ]* 3.3 Write property test for `get_latest_run_id` correctness
    - **Property 6: `get_latest_run_id` returns the most recent `setup_complete` run**
    - Generate random lists of run records with mixed statuses and timestamps; write to SQLite; assert `get_latest_run_id` returns the most recent `setup_complete` run, or falls back to `completed`, or returns `None`
    - Tag: `# Feature: geo-intelligence-restructure, Property 6: get_latest_run_id correctness`
    - **Validates: Requirements 7.6**

  - [ ]* 3.4 Write unit tests for `LocalReader`
    - Test `get_latest_run_id` with `setup_complete` runs
    - Test `get_latest_run_id` fallback to `completed` when no `setup_complete` exists
    - Test `get_latest_run_id` returns `None` when no runs exist
    - Test `get_territories` with `region_type` and `min_gap` filters
    - Test `get_ideal_supply` returns correct rows
    - Test TTL cache: verify a second call within TTL does not hit the database (mock `sqlite3` connection)
    - _Requirements: 1.4, 1.6, 7.6_

- [x] 4. Checkpoint — LocalWriter and LocalReader pass all tests
  - Ensure all tests pass, ask the user if questions arise.

- [x] 5. Create `sync_empresas_alvo` function and `--sync-empresas` CLI flag
  - Add `sync_empresas_alvo(writer: LocalWriter, turso_client: TursoHTTP) -> dict` to `etl_geocode_empresas.py`
  - The function paginates through Turso's `empresas_alvo` table (PAGE_SIZE=5000), upserts each page into the local `empresas_alvo` table via `writer.upsert_empresas_alvo(rows)`, and returns `{"inserted": int, "updated": int, "total": int}`
  - Track inserted vs updated counts by checking existence before upsert (or use SQLite `changes()` / `total_changes()`)
  - Log the count of inserted and updated records when sync completes
  - Add `--sync-empresas` flag to `geo_orchestrator.py` CLI (`argparse`); when invoked, instantiate `LocalWriter` and `TursoHTTP`, call `sync_empresas_alvo`, print the summary, and exit — independent of `--mode`
  - If the Turso connection fails, print an error and exit with non-zero status without corrupting LocalSQLite
  - _Requirements: 5.1, 5.2, 5.3, 10.1, 10.2, 10.3, 10.4, 10.5, 10.6, 10.7_
  - _Design: Updated etl_geocode_empresas.py → sync_empresas_alvo_

  - [x] 5.1 Implement `sync_empresas_alvo` in `etl_geocode_empresas.py`
    - _Requirements: 5.1, 5.2, 5.3, 10.2, 10.3_

  - [x] 5.2 Add `--sync-empresas` flag to `geo_orchestrator.py` CLI
    - _Requirements: 10.1, 10.4, 10.5, 10.6_

  - [ ]* 5.3 Write unit tests for `sync_empresas_alvo`
    - Test pagination: mock Turso to return two pages; verify both are upserted
    - Test inserted vs updated counts are logged correctly
    - Test Turso connection failure: verify LocalSQLite is not corrupted and exit code is non-zero
    - _Requirements: 5.2, 5.3, 10.3, 10.6_

- [x] 6. Update `etl_geocode_empresas.py` — read from SQLite, write to SQLite, local Nominatim, no sleep
  - Replace `TursoHTTP` reads of `empresas_alvo` with `LocalReader` / direct `sqlite3` reads from LocalSQLite
  - Add `_get_nominatim_url()` that reads `NOMINATIM_LOCAL_URL` env var (default: `http://localhost:8080`); log a WARNING if the env var is not set
  - Rename `_geocode_nominatim` to `_geocode_local_nominatim(nominatim_base_url, endereco, bairro, cep, uf)` and replace the hardcoded `_NOMINATIM_URL` with `nominatim_base_url`
  - Remove the `time.sleep(_DELAY_S)` call from `_geocode_local_nominatim`
  - Replace `TursoHTTP` writes of `empresas_geo` with `LocalWriter.upsert_empresas_geo(rows)`
  - Resume mode: read existing `h3_r9_id` from LocalSQLite instead of Turso
  - Keep the same three-strategy fallback (full address → CEP only → bairro + UF)
  - Keep the same `--uf`, `--limit`, `--batch`, `--no-resume` CLI arguments
  - _Requirements: 5.4, 5.5, 5.6, 5.7, 5.8, 5.9, 5.10, 5.11, 5.12, 5.13_
  - _Design: Updated etl_geocode_empresas.py_

  - [x] 6.1 Refactor `etl_geocode_empresas.py` to use LocalSQLite and local Nominatim
    - _Requirements: 5.4, 5.5, 5.6, 5.7, 5.8, 5.9, 5.10, 5.11, 5.12, 5.13_

  - [ ]* 6.2 Write property test for geocoding fallback chain
    - **Property 7: Geocoding fallback chain is exhausted in order**
    - Generate random address tuples where strategy 1 always fails (mock HTTP to return empty); assert strategy 2 is called; generate tuples where strategies 1 and 2 fail; assert strategy 3 is called; assert `geocode_status='failed'` only after all three strategies fail
    - Tag: `# Feature: geo-intelligence-restructure, Property 7: Geocoding fallback chain`
    - **Validates: Requirements 5.6**

  - [ ]* 6.3 Write property test for ETL resume
    - **Property 8: ETL resume skips already-geocoded records**
    - Generate random sets of `empresas_alvo` records, a subset of which already have `h3_r9_id` in SQLite; run ETL with `resume=True`; assert the Nominatim mock was not called for already-geocoded records and the total geocoded count does not decrease
    - Tag: `# Feature: geo-intelligence-restructure, Property 8: ETL resume`
    - **Validates: Requirements 5.9, 5.12**

  - [ ]* 6.4 Write unit tests for updated `etl_geocode_empresas.py`
    - Test `NOMINATIM_LOCAL_URL` env var is used when set
    - Test default URL is used when env var is not set; WARNING is logged
    - Test `time.sleep` is not called (mock `time.sleep`, verify zero calls)
    - Test resume mode: records with existing `h3_r9_id` are skipped
    - Test three-strategy fallback: first strategy fails → second is tried
    - Test summary log is emitted at completion
    - _Requirements: 5.5, 5.7, 5.8, 5.9, 5.10, 5.12, 5.13_

- [x] 7. Create conversion layer functions in `geo_orchestrator.py`
  - Add `_selected_territories_to_territories_result(selected_territories, station_code, territories_geojson_path=None) -> TerritoriesResult` to `geo_orchestrator.py`
    - Build `territory_index` dict: for each `SelectedTerritory`, populate `station_code`, `hex_ids` (from `h3_ids_r8`), `potential_score`, `gap`, `region_type` (`.value` if enum), `model_confidence`, `high_opportunity`, `bdm_cluster` (via `Config.get_bdm_cluster`), `centroid_lat`/`centroid_lon` (mean of `h3.cell_to_latlng(h)` for all h in `h3_ids_r8`), `daily_demand` (set to 0 — demand map not available at conversion time)
    - Build `hex_to_territory` dict: for every `h3_id` in `territory.h3_ids_r8`, map `h3_id → territory.territory_id`
    - Set `geojson_path` to `territories_geojson_path` if the file exists, else `None`
  - Add `_sqlite_rows_to_ideal_supply_result(supply_rows) -> IdealSupplyResult` to `geo_orchestrator.py`
    - For each row, construct an `IdealSlot` with: `slot_id=row["supply_id"]`, `bucket_id=row["territory_id"]`, `station_code=row["station_code"]`, `lat=row["lat"]`, `lon=row["lon"]`, `radius_s=int(row["radius_km"] * 1000)` (default 1500 if missing, log WARNING), `capacity_s=row["capacity_day"]` (default 42 if missing, log WARNING), `origin_hex=row["origin_hex"]` (default `h3.latlng_to_cell(lat, lon, 9)` if NULL, log WARNING), `matched_partner_id=row.get("matched_partner_id")`, `allocations=[]`
    - Build `IdealSupplyResult` with `slots_by_territory` populated
  - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5_
  - _Design: Components → Conversion Layer_

  - [x] 7.1 Implement `_selected_territories_to_territories_result` in `geo_orchestrator.py`
    - _Requirements: 3.1, 3.3_

  - [x] 7.2 Implement `_sqlite_rows_to_ideal_supply_result` in `geo_orchestrator.py`
    - _Requirements: 3.2, 3.4, 3.5_

  - [ ]* 7.3 Write property test for `_selected_territories_to_territories_result` hex membership
    - **Property 3: SelectedTerritory → TerritoriesResult conversion preserves hex membership**
    - Generate random `SelectedTerritory` lists with Hypothesis; convert via `_selected_territories_to_territories_result`; for every `h3_id` in every territory's `h3_ids_r8`, assert `result.hex_to_territory[h3_id] == territory.territory_id`
    - Tag: `# Feature: geo-intelligence-restructure, Property 3: TerritoriesResult hex membership`
    - **Validates: Requirements 3.1, 3.3**

  - [ ]* 7.4 Write property test for `_sqlite_rows_to_ideal_supply_result` slot data
    - **Property 4: SQLite rows → IdealSupplyResult conversion preserves slot data**
    - Generate random `geo_ideal_supply` row dicts with Hypothesis; convert via `_sqlite_rows_to_ideal_supply_result`; for every row, assert `slot.slot_id == row["supply_id"]`, `slot.bucket_id == row["territory_id"]`, `slot.radius_s == int(row["radius_km"] * 1000)`, `slot.capacity_s == row["capacity_day"]`
    - Tag: `# Feature: geo-intelligence-restructure, Property 4: IdealSupplyResult slot data`
    - **Validates: Requirements 3.2, 3.4**

  - [ ]* 7.5 Write unit tests for conversion layer
    - Test `_selected_territories_to_territories_result`: verify `hex_to_territory` mapping
    - Test `_selected_territories_to_territories_result`: verify `territory_index` fields (`station_code`, `bdm_cluster`, `centroid_lat`, `centroid_lon`)
    - Test `_sqlite_rows_to_ideal_supply_result`: verify `IdealSlot` field mapping
    - Test `_sqlite_rows_to_ideal_supply_result`: missing `origin_hex` → default computed from lat/lon, WARNING logged
    - Test `_sqlite_rows_to_ideal_supply_result`: missing `radius_km` → default 1.5, WARNING logged
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5_

- [x] 8. Update `geo_orchestrator.run_setup` — replace TursoWriter with LocalWriter
  - Remove imports of `TursoWriter`, `TURSO_URL`, `TURSO_AUTH_TOKEN` from `run_setup`
  - Instantiate `LocalWriter` (no arguments — uses env var / default path) and call `writer.ensure_schema()`
  - Replace `writer.upsert_run(run_id, config)` call (same signature)
  - After Phase 1 completes, call `writer.upsert_territories(run_id, selected_territories_as_TerritoryOutput, station_code)` and `writer.upsert_h3_cells(...)` — adapt `SelectedTerritory` fields to `TerritoryOutput` fields as needed
  - After Phase 2 completes, call `writer.upsert_ideal_supply(run_id, supply_points)` (same dict format as current)
  - On success, call `writer.finalize_run(run_id, metadata)` with `status='setup_complete'` (not `'completed'`)
  - On failure, call `writer.finalize_run(run_id, metadata)` with `status='failed'`
  - Remove all references to `TursoWriter` and Turso credentials from `run_setup`
  - _Requirements: 1.3, 1.8, 7.1, 7.2, 7.3, 7.4, 7.5_
  - _Design: Updated geo_orchestrator.py → run_setup_

  - [x] 8.1 Refactor `run_setup` to use `LocalWriter` instead of `TursoWriter`
    - _Requirements: 1.3, 1.8, 7.1, 7.2, 7.3, 7.4, 7.5_

  - [ ]* 8.2 Write unit tests for updated `run_setup`
    - Mock `run_area_intelligence` and `run_phase2`; verify `LocalWriter.upsert_run`, `upsert_territories`, `upsert_ideal_supply`, and `finalize_run(status='setup_complete')` are called
    - Verify `finalize_run(status='failed')` is called when Phase 1 raises an exception
    - Verify no `TursoWriter` or Turso credentials are referenced
    - _Requirements: 1.3, 1.8, 7.1, 7.4, 7.5_

- [x] 9. Update `geo_orchestrator.run_daily` — replace TursoReader/geo_daily with LocalReader + vanilla Phase 3+4+5
  - Remove imports of `TursoReader`, `TursoWriter`, `geo_daily.run_daily`, `geo_phase3_5_cap_optimizer` (keep if still needed), `TURSO_URL`, `TURSO_AUTH_TOKEN` from `run_daily`
  - Add imports: `LocalReader`, `LocalWriter`, `run_phase3` (from `vanilla.phase3_partner_fit`), `run_phase4` (from `vanilla.phase4_webleads`), `run_phase5` (from `vanilla.phase5_reports`), `load_partners`, `load_packages`
  - Instantiate `LocalReader` and `LocalWriter`
  - For each station: call `reader.get_latest_run_id(station_code)`; if `None`, print warning and skip; call `reader.get_ideal_supply(station_code, run_id)`; if empty, print warning and skip
  - Call `reader.get_territories(station_code, run_id)` to get territory rows; convert to `TerritoriesResult` via `_selected_territories_to_territories_result` (or build `TerritoriesResult` directly from the SQLite rows)
  - Convert ideal supply rows to `IdealSupplyResult` via `_sqlite_rows_to_ideal_supply_result`
  - Load `partner_data = load_partners()` and `pkg = load_packages()`
  - Call `fit = run_phase3(territories, supply, partner_data, pkg, output_dir, stations)`
  - After Phase 3, call `writer.update_supply_match(run_id, matches)` and `writer.update_territory_fit(run_id, fits)`
  - Call `webleads = run_phase4(partner_data, territories, pkg)`
  - Call `run_phase5(territories, supply, fit, webleads, pkg, output_dir, stations)`
  - Remove all calls to `geo_daily.run_daily`, `TursoReader`, `TursoWriter`, and the old Phase 3.5 geo cap optimizer block (or keep Phase 3.5 if it still applies — wrap in try/except as before)
  - _Requirements: 1.4, 1.8, 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 2.8, 2.9, 2.10_
  - _Design: Updated geo_orchestrator.py → run_daily_

  - [x] 9.1 Refactor `run_daily` to use `LocalReader` and call vanilla Phase 3+4+5
    - _Requirements: 1.4, 1.8, 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 2.8, 2.9, 2.10_

  - [ ]* 9.2 Write property test for daily persistence round-trip
    - **Property 5: Daily persistence round-trip — matched_partner_id and territory fit**
    - Generate random `FitResult` objects (with matched slots and territory fits) with Hypothesis; write via `LocalWriter.update_supply_match` and `update_territory_fit`; read back via `LocalReader.get_ideal_supply` and `LocalReader.get_territories`; assert `matched_partner_id` and `attainment`/`accuracy` match the `FitResult` values
    - Tag: `# Feature: geo-intelligence-restructure, Property 5: Daily persistence round-trip`
    - **Validates: Requirements 2.10**

  - [ ]* 9.3 Write unit tests for updated `run_daily`
    - Mock `LocalReader`, `run_phase3`, `run_phase4`, `run_phase5`, `load_partners`, `load_packages`
    - Verify `run_phase3`, `run_phase4`, `run_phase5` are called in order
    - Verify `LocalWriter.update_supply_match` and `update_territory_fit` are called after Phase 3
    - Verify station is skipped (with warning) when `get_latest_run_id` returns `None`
    - Verify station is skipped (with warning) when `get_ideal_supply` returns empty list
    - Verify no `TursoReader`, `TursoWriter`, or `geo_daily` references remain
    - _Requirements: 1.4, 1.8, 2.1, 2.2, 2.3, 2.7, 2.10_

- [x] 10. Checkpoint — all pipeline integration tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 11. Remove `--update-heatmap` from `geo_orchestrator.py` CLI
  - Remove the `--update-heatmap` argument from `_parse_args()`
  - Remove the `run_update_geo_heatmap` function from `geo_orchestrator.py`
  - Remove the `if args.update_heatmap:` branch from `main()`
  - Update the CLI `epilog` / help text to document that `--mode daily` is the correct way to refresh all output files including the heatmap
  - _Requirements: 4.1, 4.2, 4.3, 4.4_
  - _Design: Updated geo_orchestrator.py → CLI_

  - [x] 11.1 Remove `--update-heatmap` argument, `run_update_geo_heatmap` function, and related branch from `geo_orchestrator.py`
    - _Requirements: 4.1, 4.2, 4.3, 4.4_

  - [ ]* 11.2 Write unit tests for updated CLI
    - Test `--update-heatmap` argument is rejected by argparse (raises `SystemExit`)
    - Test `--mode setup` without `--target` exits with error
    - Test `--sync-empresas` is accepted independently of `--mode`
    - Test `--mode daily` help text references `--mode daily` for heatmap refresh
    - _Requirements: 4.1, 4.4, 10.1, 10.5_

- [x] 12. Delete `geo_daily.py` and `geo_heatmap.py`
  - Delete `backend/geo_intelligence/geo_daily.py`
  - Delete `backend/geo_intelligence/geo_heatmap.py`
  - Search for any remaining imports of `geo_daily` or `geo_heatmap` in the codebase and remove them
  - _Requirements: 2.9, 4.2_
  - _Design: DELETED: geo_daily.py, geo_heatmap.py_

  - [x] 12.1 Delete `geo_daily.py` and `geo_heatmap.py` and remove all their imports
    - _Requirements: 2.9, 4.2_

- [x] 13. Final checkpoint — all tests pass
  - Run the full test suite under `backend/tests/geo_intelligence/`
  - Ensure all property-based tests (Hypothesis) pass with at least 100 examples each
  - Ensure all unit tests pass
  - Ensure no import errors remain for deleted modules
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Property tests validate universal correctness properties (Hypothesis, min 100 examples each)
- Unit tests validate specific examples and edge cases
- Checkpoints ensure incremental validation at key integration points
- The vanilla pipeline (`vanilla/orchestrator.py`, `phase3_partner_fit.py`, `phase4_webleads.py`, `phase5_reports.py`, `shared/`) must NOT be modified (Requirement 9)
- `TursoWriter` and `TursoReader` are NOT deleted — they remain for any future use; only their call sites in `geo_orchestrator.py` are replaced
- Property tests should be placed in `backend/tests/geo_intelligence/test_properties.py`
- Unit tests should be placed in `backend/tests/geo_intelligence/` (one file per module)
