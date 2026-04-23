# Requirements Document

## Introduction

This feature restructures the GeoIntelligence pipeline to unify its daily execution path with the vanilla pipeline and migrates all internal pipeline state from Turso (remote libSQL) to local SQLite. After Phase 1 (Area Intelligence) and Phase 2 (CP-SAT ideal supply), the geo daily mode will call the exact same `run_phase3` → `run_phase4` → `run_phase5` functions as the vanilla pipeline, producing identical output files (`dados_mapa.json`, `heatmap.geojson`, etc.). Turso is retained only for the three tables shared with the frontend/API: `empresas_alvo`, `gmaps_leads`, and `contactadas`. All other geo pipeline tables are migrated to a local SQLite database at `output/geo_intelligence/geo_intelligence.db`. The `--update-heatmap` flag is removed from `geo_orchestrator.py`, and local geocoding of `empresas_alvo` is migrated from the public Nominatim API to a local Docker-hosted Nominatim instance.

## Glossary

- **GeoOrchestrator**: `backend/geo_intelligence/geo_orchestrator.py` — entry point for the GeoIntelligence pipeline.
- **VanillaOrchestrator**: `backend/vanilla/orchestrator.py` — entry point for the vanilla pipeline.
- **Phase1**: Area Intelligence — H3 enrichment, classification, potential scoring, and area selection (`phase1_area_intelligence.py`).
- **Phase2**: CP-SAT ideal supply solver (`phase2_ideal_supply.py`).
- **Phase3**: Partner matching (`vanilla/phase3_partner_fit.py`).
- **Phase4**: Weblead qualification (`vanilla/phase4_webleads.py`).
- **Phase5**: Report and artefact generation (`vanilla/phase5_reports.py`).
- **LocalSQLite**: The local SQLite database at `output/geo_intelligence/geo_intelligence.db`.
- **Turso**: The remote libSQL/Turso database accessed via `TursoHTTP`.
- **TursoWriter**: `backend/geo_intelligence/turso_writer.py` — writes pipeline state to Turso.
- **TursoReader**: `backend/geo_intelligence/turso_reader.py` — reads pipeline state from Turso.
- **LocalWriter**: New module that writes pipeline state to LocalSQLite, replacing TursoWriter for internal tables.
- **LocalReader**: New module that reads pipeline state from LocalSQLite, replacing TursoReader for internal tables.
- **GeoDailyResult**: Dataclass in `geo_daily.py` representing the current geo daily output — to be replaced by vanilla `FitResult`.
- **GeoPartnerMatch**: Dataclass in `geo_daily.py` representing a single partner match — to be replaced by vanilla `PartnerMetrics`.
- **FitResult**: Vanilla dataclass from `phase3_partner_fit.py` representing the full matching result.
- **PartnerMetrics**: Vanilla dataclass from `phase3_partner_fit.py` representing a single partner's metrics.
- **EtlGeocodeEmpresas**: `backend/geo_intelligence/etl_geocode_empresas.py` — geocodes `empresas_alvo` records.
- **EtlSyncEmpresas**: New command (`--sync-empresas`) that downloads `empresas_alvo` from Turso into LocalSQLite once, so all subsequent pipeline operations (geocoding, Phase 1 enrichment) run fully offline.
- **LocalNominatim**: A self-hosted Nominatim instance running in Docker, accessible at a configurable local URL (e.g., `http://localhost:8080`).
- **PublicNominatim**: The public `https://nominatim.openstreetmap.org` API used by the current ETL.
- **InternalGeoTables**: The set of Turso tables used exclusively by the pipeline internals: `geo_run_metadata`, `geo_territories`, `geo_h3_cells`, `geo_ideal_supply`, `geo_scorecard`, `geo_cap_opportunities`, `geo_partner_history`, `geo_partner_profiles`.
- **SharedTursoTables**: The three Turso tables shared with the frontend/API: `empresas_alvo`, `gmaps_leads`, `contactadas`.

---

## Requirements

### Requirement 1: Migrate Internal Geo Tables to LocalSQLite

**User Story:** As a pipeline operator, I want all internal GeoIntelligence pipeline state stored in a local SQLite file instead of Turso, so that the pipeline has no remote-DB dependency for its own execution and Turso is reserved for frontend-facing data only.

#### Acceptance Criteria

1. THE LocalWriter SHALL create and manage the LocalSQLite database at `output/geo_intelligence/geo_intelligence.db`.
2. THE LocalSQLite SHALL contain all InternalGeoTables: `geo_run_metadata`, `geo_territories`, `geo_h3_cells`, `geo_ideal_supply`, `geo_scorecard`, `geo_cap_opportunities`, `geo_partner_history`, and `geo_partner_profiles`.
3. WHEN the GeoOrchestrator runs `--mode setup`, THE LocalWriter SHALL persist all setup outputs (run metadata, territories, H3 cells, ideal supply, scorecard, partner profiles) to LocalSQLite instead of Turso.
4. WHEN the GeoOrchestrator runs `--mode daily`, THE LocalReader SHALL read run metadata and ideal supply from LocalSQLite instead of Turso.
5. THE LocalWriter SHALL implement the same upsert semantics as TursoWriter for all InternalGeoTables (INSERT … ON CONFLICT DO UPDATE).
6. THE LocalReader SHALL implement the same query interface as TursoReader for all InternalGeoTables, including `get_latest_run_id`, `get_territories`, `get_ideal_supply`, `get_h3_cells`, `get_scorecard`, and `get_cap_opportunities`.
7. IF the LocalSQLite file does not exist, THEN THE LocalWriter SHALL create it and apply the full schema on first use.
8. THE GeoOrchestrator SHALL NOT write to or read from Turso for any InternalGeoTable after this migration.
9. THE SharedTursoTables (`empresas_alvo`, `gmaps_leads`, `contactadas`) SHALL remain in Turso and SHALL NOT be migrated to LocalSQLite.

---

### Requirement 2: Unify Geo Daily with Vanilla Phase 3–5

**User Story:** As a pipeline operator, I want the GeoIntelligence daily mode to produce the same output files as the vanilla pipeline by reusing the exact same Phase 3, Phase 4, and Phase 5 functions, so that there is a single, maintained code path for matching, webleads, and reporting.

#### Acceptance Criteria

1. WHEN the GeoOrchestrator runs `--mode daily`, THE GeoOrchestrator SHALL call `run_phase3` from `vanilla/phase3_partner_fit.py` using the territories and ideal supply loaded from LocalSQLite.
2. WHEN the GeoOrchestrator runs `--mode daily`, THE GeoOrchestrator SHALL call `run_phase4` from `vanilla/phase4_webleads.py` after Phase 3 completes.
3. WHEN the GeoOrchestrator runs `--mode daily`, THE GeoOrchestrator SHALL call `run_phase5` from `vanilla/phase5_reports.py` after Phase 4 completes.
4. THE GeoOrchestrator daily mode SHALL produce `dados_mapa.json` in the configured output directory.
5. THE GeoOrchestrator daily mode SHALL produce `heatmap.geojson` with `covering_partners` and `hex_coverage` fields in the configured output directory.
6. THE GeoOrchestrator daily mode SHALL produce all other artefacts generated by `run_phase5` (e.g., `RELATORIO_EXECUTIVO.txt`, `OPORTUNIDADES_ESTRATEGICAS.txt`, `PARTNERS_PER_DS_BUCKET.csv`, `webleads_evaluated.csv`, `optimization_data.geojson`).
7. THE GeoOrchestrator SHALL load territories and ideal supply from LocalSQLite (via LocalReader) and convert them to the `TerritoriesResult` and `IdealSupplyResult` types expected by `run_phase3`.
8. THE `GeoDailyResult` dataclass and `GeoPartnerMatch` dataclass in `geo_daily.py` SHALL be replaced by `FitResult` and `PartnerMetrics` from `vanilla/phase3_partner_fit.py`.
9. THE `geo_daily.py` module's `run_daily` function SHALL be removed; its matching logic SHALL be superseded by `run_phase3`.
10. WHERE the geo daily previously persisted `matched_partner_id` and territory `attainment`/`accuracy` to Turso, THE GeoOrchestrator SHALL persist those values to LocalSQLite via LocalWriter after `run_phase3` completes.

---

### Requirement 3: Adapt Phase 1+2 Outputs as Inputs to Vanilla Phase 3

**User Story:** As a developer, I want the outputs of Phase 1 (selected territories) and Phase 2 (ideal supply slots) to be converted into the `TerritoriesResult` and `IdealSupplyResult` types used by the vanilla pipeline, so that Phase 3 can be called without modification.

#### Acceptance Criteria

1. THE GeoOrchestrator SHALL convert the list of `SelectedTerritory` objects produced by Phase 1 into a `TerritoriesResult` object before calling `run_phase3`.
2. THE GeoOrchestrator SHALL convert the ideal supply slots produced by Phase 2 (and stored in LocalSQLite) into an `IdealSupplyResult` object before calling `run_phase3`.
3. THE `TerritoriesResult` produced by the conversion SHALL contain a valid `hex_to_territory` mapping, `territory_index`, and `stations` set derived from the geo territories.
4. THE `IdealSupplyResult` produced by the conversion SHALL contain `IdealSlot` objects with all fields (`slot_id`, `lat`, `lon`, `radius_s`, `capacity_s`, `origin_hex`, `bucket_id`, `station_code`) populated from LocalSQLite rows.
5. IF a required field is missing from a LocalSQLite row, THEN THE GeoOrchestrator SHALL log a warning and use a safe default value rather than raising an exception.

---

### Requirement 4: Remove `--update-heatmap` from GeoOrchestrator

**User Story:** As a pipeline operator, I want the `--update-heatmap` flag removed from `geo_orchestrator.py`, so that the CLI is simplified and heatmap synchronisation is always achieved by running `--mode daily`.

#### Acceptance Criteria

1. THE GeoOrchestrator CLI SHALL NOT accept the `--update-heatmap` argument after this change.
2. THE `run_update_geo_heatmap` function and the `geo_heatmap.py` module SHALL be removed.
3. WHEN a user runs `geo_orchestrator.py --mode daily`, THE GeoOrchestrator SHALL produce an up-to-date heatmap as a natural output of Phase 5, making a separate `--update-heatmap` step unnecessary.
4. THE GeoOrchestrator CLI help text SHALL document that `--mode daily` is the correct way to refresh all output files including the heatmap.

---

### Requirement 5: Migrate `empresas_alvo` Geocoding to LocalNominatim

**User Story:** As a pipeline operator, I want `empresas_alvo` records to be synced locally and geocoded using a local Docker-hosted Nominatim instance, so that geocoding is not rate-limited, does not depend on external internet access during the pipeline run, and results are stored in LocalSQLite.

#### Acceptance Criteria

1. THE EtlSyncEmpresas SHALL download all records from the Turso `empresas_alvo` table and store them in a local `empresas_alvo` table in LocalSQLite.
2. THE EtlSyncEmpresas SHALL support incremental sync: records already present in LocalSQLite (matched by primary key) SHALL be updated with the latest values from Turso; new records SHALL be inserted.
3. WHEN sync completes, THE EtlSyncEmpresas SHALL log the count of inserted and updated records.
4. THE EtlGeocodeEmpresas SHALL read `empresas_alvo` records from LocalSQLite (not from Turso) after the sync step.
5. THE EtlGeocodeEmpresas SHALL geocode each record by calling LocalNominatim instead of PublicNominatim.
6. THE EtlGeocodeEmpresas SHALL store geocoded results (`empresas_geo`) in LocalSQLite.
7. THE EtlGeocodeEmpresas SHALL read the LocalNominatim base URL from the environment variable `NOMINATIM_LOCAL_URL`, defaulting to `http://localhost:8080`.
8. IF `NOMINATIM_LOCAL_URL` is not set, THEN THE EtlGeocodeEmpresas SHALL log a warning and use the default URL `http://localhost:8080`.
9. THE EtlGeocodeEmpresas SHALL apply the same three-strategy fallback (full address → CEP only → bairro + UF) when calling LocalNominatim.
10. THE EtlGeocodeEmpresas SHALL NOT enforce the 1.1-second inter-request delay when calling LocalNominatim, since rate limiting does not apply to a local instance.
11. THE EtlGeocodeEmpresas SHALL create the `empresas_geo` table in LocalSQLite with the same schema as the current Turso `empresas_geo` table.
12. THE EtlGeocodeEmpresas SHALL support `--resume` mode: records with an existing `h3_r9_id` in LocalSQLite SHALL be skipped.
13. WHEN geocoding completes, THE EtlGeocodeEmpresas SHALL log a summary with the count of successfully geocoded records and the count of failures.
14. THE `empresas_alvo` table in LocalSQLite SHALL have the same schema as the Turso `empresas_alvo` table so that Phase 1 enrichers can query it without modification.

---

### Requirement 6: LocalSQLite Schema Integrity

**User Story:** As a developer, I want the LocalSQLite schema to be versioned and self-migrating, so that schema changes can be applied without manual intervention and without data loss.

#### Acceptance Criteria

1. THE LocalWriter SHALL apply all DDL statements idempotently using `CREATE TABLE IF NOT EXISTS` and `CREATE INDEX IF NOT EXISTS`.
2. THE LocalWriter SHALL apply `ALTER TABLE … ADD COLUMN` migrations gracefully, ignoring "duplicate column name" errors as the current TursoWriter does.
3. WHEN the LocalSQLite database is opened, THE LocalWriter SHALL verify and apply any pending schema migrations before executing any read or write operation.
4. THE LocalSQLite file path SHALL be configurable via the `GEO_SQLITE_PATH` environment variable, defaulting to `output/geo_intelligence/geo_intelligence.db`.
5. IF the directory containing the LocalSQLite file does not exist, THEN THE LocalWriter SHALL create it before opening the database.

---

### Requirement 7: Geo Setup Mode Persists to LocalSQLite

**User Story:** As a pipeline operator, I want `--mode setup` to write all its outputs to LocalSQLite so that the daily mode can read them without any Turso dependency.

#### Acceptance Criteria

1. WHEN the GeoOrchestrator runs `--mode setup`, THE GeoOrchestrator SHALL call `LocalWriter.upsert_run` to record the run as started.
2. WHEN Phase 1 completes, THE GeoOrchestrator SHALL call `LocalWriter.upsert_territories` and `LocalWriter.upsert_h3_cells` to persist the selected territories and their H3 cell features.
3. WHEN Phase 2 completes, THE GeoOrchestrator SHALL call `LocalWriter.upsert_ideal_supply` to persist the ideal supply slots.
4. WHEN setup completes successfully, THE GeoOrchestrator SHALL call `LocalWriter.finalize_run` with `status='setup_complete'`.
5. IF setup fails for a station, THEN THE GeoOrchestrator SHALL call `LocalWriter.finalize_run` with `status='failed'` for that station's run.
6. THE `LocalReader.get_latest_run_id` SHALL return the most recent run with `status='setup_complete'` for a given station, falling back to `status='completed'` for backward compatibility.

---

### Requirement 8: Backward Compatibility of Output Files

**User Story:** As a frontend developer, I want the output files produced by the geo daily mode to be identical in format to those produced by the vanilla daily mode, so that the frontend and API can consume them without changes.

#### Acceptance Criteria

1. THE `dados_mapa.json` produced by the geo daily mode SHALL have the same top-level structure and field names as the one produced by the vanilla daily mode.
2. THE `heatmap.geojson` produced by the geo daily mode SHALL include `covering_partners` and `hex_coverage` fields on each feature's `properties` object, matching the vanilla output.
3. THE `PARTNERS_PER_DS_BUCKET.csv` produced by the geo daily mode SHALL have the same column names and row format as the vanilla output.
4. THE `webleads_evaluated.csv` produced by the geo daily mode SHALL have the same column names and row format as the vanilla output.
5. THE `optimization_data.geojson` produced by the geo daily mode SHALL have the same feature types (`TERRITORY_HEX`, `IDEAL_SLOT`) and property schemas as the vanilla output.

---

### Requirement 9: No Regression in Vanilla Pipeline

**User Story:** As a pipeline operator, I want the vanilla pipeline to remain completely unchanged by this restructure, so that existing vanilla deployments are not affected.

#### Acceptance Criteria

1. THE VanillaOrchestrator SHALL NOT be modified as part of this feature.
2. THE `vanilla/phase3_partner_fit.py`, `vanilla/phase4_webleads.py`, and `vanilla/phase5_reports.py` modules SHALL NOT be modified as part of this feature.
3. WHEN the vanilla pipeline runs `--mode daily`, THE VanillaOrchestrator SHALL produce the same outputs as before this change.
4. THE shared modules (`shared/load_partners.py`, `shared/load_packages.py`, `shared/models.py`) SHALL NOT be modified as part of this feature.

---

### Requirement 10: `empresas_alvo` Sync CLI Command

**User Story:** As a pipeline operator, I want a dedicated CLI command to sync `empresas_alvo` from Turso to LocalSQLite, so that I can refresh the local copy whenever new companies are added via the frontend/API without re-running the full pipeline.

#### Acceptance Criteria

1. THE GeoOrchestrator CLI SHALL accept a `--sync-empresas` flag that triggers the sync of `empresas_alvo` from Turso to LocalSQLite.
2. WHEN `--sync-empresas` is invoked, THE EtlSyncEmpresas SHALL connect to Turso, paginate through all `empresas_alvo` records, and upsert them into the local `empresas_alvo` table in LocalSQLite.
3. THE sync SHALL use pagination (e.g., 5000 records per page) to avoid Turso query timeouts.
4. WHEN `--sync-empresas` completes, THE GeoOrchestrator SHALL print a summary: total records synced, inserted count, updated count.
5. THE `--sync-empresas` flag SHALL be usable independently of `--mode` (i.e., it does not require `--mode setup` or `--mode daily` to be specified simultaneously).
6. IF the Turso connection fails during sync, THE GeoOrchestrator SHALL print an error message and exit with a non-zero status code without corrupting the existing LocalSQLite data.
7. THE local `empresas_alvo` table SHALL mirror the Turso schema exactly, so that Phase 1 enrichers that previously queried Turso can query LocalSQLite without any query changes.
