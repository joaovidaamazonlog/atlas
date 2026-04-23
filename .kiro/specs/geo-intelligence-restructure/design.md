# Design Document: GeoIntelligence Restructure


## Overview

This design restructures the GeoIntelligence pipeline to eliminate its parallel daily execution path and unify it with the vanilla pipeline. The core insight is that after Phase 1 (Area Intelligence) and Phase 2 (CP-SAT ideal supply) produce geo-specific outputs, the downstream work — partner matching, weblead qualification, and report generation — is identical to what the vanilla pipeline already does. Rather than maintaining a separate `geo_daily.py` with duplicated matching logic, the geo orchestrator will convert its Phase 1+2 outputs into the `TerritoriesResult` and `IdealSupplyResult` types that `run_phase3`, `run_phase4`, and `run_phase5` already accept, then call those functions directly.

The second major change is storage: all internal pipeline state (run metadata, territories, H3 cells, ideal supply, scorecard, partner profiles) moves from Turso (remote libSQL) to a local SQLite file at `output/geo_intelligence/geo_intelligence.db`. Turso is retained only for the three tables shared with the frontend/API: `empresas_alvo`, `gmaps_leads`, and `contactadas`. This removes the remote-DB dependency from the pipeline's own execution path and simplifies the operational model.

The third change is geocoding: `etl_geocode_empresas.py` is updated to call a local Docker-hosted Nominatim instance instead of the public API, removing rate-limiting constraints and storing results in LocalSQLite.

### Key Design Decisions

- **No modification to vanilla modules.** `vanilla/phase3_partner_fit.py`, `phase4_webleads.py`, `phase5_reports.py`, and `vanilla/orchestrator.py` are untouched. The geo orchestrator adapts to their interfaces, not the other way around.
- **Conversion layer in the orchestrator.** The `SelectedTerritory` → `TerritoriesResult` and `GeoIdealSlot` → `IdealSupplyResult` conversions live in `geo_orchestrator.py`, keeping the vanilla phases unaware of geo-specific types.
- **SQLite over file-based JSON.** The vanilla pipeline uses `territories_index.json` and `ideal_supply.json` as its persistence layer. The geo pipeline uses SQLite for richer querying (latest run by station, filtering by status) and to support multiple stations in a single file.
- **`geo_daily.py` and `geo_heatmap.py` are deleted.** Their logic is superseded by the vanilla phases and the conversion layer.
- **`--update-heatmap` is removed.** The heatmap is always regenerated as part of `--mode daily` via `run_phase5`.

---

## Architecture

### Phase Flow

```
GEO-SPECIFIC (setup mode)                    VANILLA-SHARED (daily mode)
─────────────────────────────────────────    ──────────────────────────────────────────────
packages_df + territories_index
        │
        ▼
┌─────────────────────┐
│  Phase 1            │  run_area_intelligence()
│  Area Intelligence  │  → List[SelectedTerritory]
│  (H3 enrichment,    │  → phase1_metrics
│   classifier,       │
│   potential score,  │
│   area selector)    │
└─────────────────────┘
        │
        ▼
┌─────────────────────┐
│  Phase 2            │  run_phase2()
│  CP-SAT Ideal       │  → Dict[territory_id, List[GeoIdealSlot]]
│  Supply             │
└─────────────────────┘
        │
        ▼
┌─────────────────────┐
│  LocalWriter        │  upsert_run / upsert_territories /
│  (SQLite)           │  upsert_h3_cells / upsert_ideal_supply /
│                     │  finalize_run(status='setup_complete')
└─────────────────────┘

                                    LocalReader.get_latest_run_id()
                                    LocalReader.get_territories()
                                    LocalReader.get_ideal_supply()
                                            │
                                            ▼
                                    ┌───────────────────────┐
                                    │  Conversion Layer      │
                                    │  (in geo_orchestrator) │
                                    │                        │
                                    │  selected_territories  │
                                    │    → TerritoriesResult │
                                    │                        │
                                    │  geo_ideal_supply rows │
                                    │    → IdealSupplyResult │
                                    └───────────────────────┘
                                            │
                                            ▼
                                    ┌───────────────────────┐
                                    │  Phase 3              │
                                    │  run_phase3()         │
                                    │  (vanilla, unchanged) │
                                    │  → FitResult          │
                                    └───────────────────────┘
                                            │
                                            ├──► LocalWriter.update_supply_match()
                                            ├──► LocalWriter.update_territory_fit()
                                            │
                                            ▼
                                    ┌───────────────────────┐
                                    │  Phase 4              │
                                    │  run_phase4()         │
                                    │  (vanilla, unchanged) │
                                    │  → WebleadResult      │
                                    └───────────────────────┘
                                            │
                                            ▼
                                    ┌───────────────────────┐
                                    │  Phase 5              │
                                    │  run_phase5()         │
                                    │  (vanilla, unchanged) │
                                    │  → output files       │
                                    └───────────────────────┘
                                            │
                                            ▼
                                    dados_mapa.json
                                    heatmap.geojson
                                    RELATORIO_EXECUTIVO.txt
                                    OPORTUNIDADES_ESTRATEGICAS.txt
                                    PARTNERS_PER_DS_BUCKET.csv
                                    webleads_evaluated.csv
                                    optimization_data.geojson
```

### Storage Boundary

```
┌─────────────────────────────────────────────────────────────────┐
│  LOCAL SQLite  (output/geo_intelligence/geo_intelligence.db)    │
│                                                                 │
│  Pipeline state (read/write by pipeline):                       │
│    geo_run_metadata        geo_territories                      │
│    geo_h3_cells            geo_ideal_supply                     │
│    geo_scorecard           geo_cap_opportunities                │
│    geo_partner_history     geo_partner_profiles                 │
│    empresas_geo            (geocoded results from ETL)          │
│                                                                 │
│  Synced from Turso (--sync-empresas, then read locally):        │
│    empresas_alvo           (local mirror of Turso table)        │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│  TURSO  (remote libSQL — shared with frontend/API)              │
│                                                                 │
│  Source of truth for frontend-facing data:                      │
│    empresas_alvo           gmaps_leads                          │
│    contactadas                                                  │
└─────────────────────────────────────────────────────────────────┘

Sync flow:
  Turso.empresas_alvo  ──[--sync-empresas]──►  SQLite.empresas_alvo
  SQLite.empresas_alvo ──[etl_geocode]──────►  SQLite.empresas_geo
  SQLite.empresas_geo  ──[Phase 1 enricher]──► pipeline
```

### Module Dependency Map

```
geo_orchestrator.py
    ├── phase1_area_intelligence.py   (unchanged)
    ├── phase2_ideal_supply.py        (unchanged — geo version)
    ├── local_writer.py               (NEW — replaces TursoWriter for internal tables)
    ├── local_reader.py               (NEW — replaces TursoReader for internal tables)
    ├── vanilla/phase3_partner_fit.py (unchanged — called directly)
    ├── vanilla/phase4_webleads.py    (unchanged — called directly)
    └── vanilla/phase5_reports.py     (unchanged — called directly)

etl_geocode_empresas.py
    ├── turso_http.py                 (reads empresas_alvo from Turso — unchanged)
    └── local_writer.py              (writes empresas_geo to SQLite — NEW)

DELETED:
    geo_daily.py
    geo_heatmap.py
```

---

## Components and Interfaces

### LocalWriter (`backend/geo_intelligence/local_writer.py`)

Replaces `TursoWriter` for all InternalGeoTables. Uses Python's built-in `sqlite3` module — no additional dependencies.

```python
class LocalWriter:
    def __init__(self, db_path: str | None = None) -> None:
        """
        Opens (or creates) the SQLite database.
        db_path defaults to GEO_SQLITE_PATH env var,
        then to 'output/geo_intelligence/geo_intelligence.db'.
        Creates parent directories if they do not exist.
        """

    def ensure_schema(self) -> None:
        """
        Applies all CREATE TABLE IF NOT EXISTS and CREATE INDEX IF NOT EXISTS
        DDL statements. Applies ALTER TABLE migrations gracefully (ignores
        'duplicate column name' errors). Idempotent — safe to call on every startup.
        """

    def upsert_run(self, run_id: str, config: GeoSetupConfig) -> None:
        """INSERT OR REPLACE into geo_run_metadata with status='running'."""

    def finalize_run(self, run_id: str, metadata: RunMetadata) -> None:
        """UPDATE geo_run_metadata with final fields and status."""

    def upsert_territories(
        self, run_id: str, territories: list[TerritoryOutput], station_code: str
    ) -> None:
        """Batch upsert into geo_territories."""

    def upsert_h3_cells(
        self, run_id: str, cells: list[H3CellFeatures],
        territory_id: str, station_code: str
    ) -> None:
        """Batch upsert into geo_h3_cells."""

    def upsert_ideal_supply(self, run_id: str, supply_points: list[dict]) -> None:
        """Batch upsert into geo_ideal_supply."""

    def upsert_scorecard(self, run_id: str, scorecard_rows: list[dict]) -> None:
        """Batch upsert into geo_scorecard."""

    def update_supply_match(self, run_id: str, matches: list[dict] | dict) -> None:
        """UPDATE geo_ideal_supply.matched_partner_id after Phase 3."""

    def update_territory_fit(self, run_id: str, fits: list[dict] | dict) -> None:
        """UPDATE geo_territories.attainment and accuracy after Phase 3."""

    def upsert_partner_profiles(
        self, run_id: str, station_code: str, profiles: ReferenceProfiles
    ) -> None:
        """Upsert into geo_partner_profiles."""

    def upsert_cap_opportunities(
        self, run_id: str, opportunities: list[dict]
    ) -> None:
        """Upsert into geo_partner_cap_opportunities."""

    def upsert_partner_history(
        self, run_id: str, partner_profiles: list[PartnerProfile]
    ) -> None:
        """Upsert into geo_partner_history."""

    def upsert_empresas_geo(self, rows: list[dict]) -> None:
        """Batch upsert into empresas_geo (used by ETL)."""

    def upsert_empresas_alvo(self, rows: list[dict]) -> None:
        """Batch upsert into empresas_alvo (used by --sync-empresas)."""

    def close(self) -> None:
        """Closes the SQLite connection."""
```

**Implementation notes:**
- Uses `sqlite3.connect(db_path, check_same_thread=False)` with `isolation_level=None` (autocommit) for simplicity, or explicit `BEGIN`/`COMMIT` for batch operations.
- Batch upserts use `executemany` with `INSERT OR REPLACE` or `INSERT … ON CONFLICT DO UPDATE` (SQLite 3.24+).
- No retry logic needed (local file I/O is not subject to network failures).
- Thread safety: the orchestrator is single-threaded per station; no locking needed.

---

### LocalReader (`backend/geo_intelligence/local_reader.py`)

Replaces `TursoReader` for all InternalGeoTables. Implements the same public interface so call sites in `geo_orchestrator.py` can swap `TursoReader` → `LocalReader` with no other changes.

```python
class LocalReader:
    def __init__(self, db_path: str | None = None, cache_ttl_s: int = 300) -> None:
        """
        Opens the SQLite database (read-only mode: uri=True, ?mode=ro).
        Falls back to read-write if the file does not exist yet (first run).
        Implements the same TTL cache as TursoReader.
        """

    def get_latest_run_id(self, station_code: str) -> str | None:
        """
        Returns the most recent run_id with status='setup_complete' for the station.
        Falls back to status='completed' for backward compatibility.
        """

    def get_territories(
        self, station_code: str, run_id: str,
        region_type: str | None = None, min_gap: float | None = None
    ) -> list[dict]:
        """SELECT * FROM geo_territories WHERE station_code=? AND run_id=?"""

    def get_h3_cells(self, territory_id: str, run_id: str) -> list[dict]:
        """SELECT * FROM geo_h3_cells WHERE territory_id=? AND run_id=?"""

    def get_h3_cells_for_station(self, station_code: str, run_id: str) -> list[dict]:
        """SELECT * FROM geo_h3_cells WHERE station_code=? AND run_id=?"""

    def get_scorecard(self, station_code: str, run_id: str) -> dict:
        """Returns {'ds': [...], 'bdm': [...]} from geo_scorecard."""

    def get_ideal_supply(self, station_code: str, run_id: str) -> list[dict]:
        """SELECT * FROM geo_ideal_supply WHERE station_code=? AND run_id=?"""

    def get_cap_opportunities(
        self, station_code: str, run_id: str | None = None,
        only_with_opportunity: bool = False
    ) -> list[dict]:
        """SELECT * FROM geo_partner_cap_opportunities WHERE station_code=? AND run_id=?"""

    def invalidate(self, key: str | None = None) -> None:
        """Clears the in-memory TTL cache."""
```

---

### Conversion Layer (in `geo_orchestrator.py`)

Two pure functions that convert geo-specific types to vanilla types. These live in `geo_orchestrator.py` (not in a separate module) to keep the vanilla phases unaware of geo types.

```python
def _selected_territories_to_territories_result(
    selected_territories: list[SelectedTerritory],
    station_code: str,
    territories_geojson_path: str | None = None,
) -> TerritoriesResult:
    """
    Converts Phase 1 output to the TerritoriesResult expected by run_phase3.

    Mapping:
        SelectedTerritory.territory_id  → territory_index key
        SelectedTerritory.h3_ids_r8     → hex_to_territory entries
                                        → territory_index[tid]["hex_ids"]
        SelectedTerritory.potential_score → territory_index[tid]["potential_score"]
        SelectedTerritory.gap           → territory_index[tid]["gap"]
        SelectedTerritory.region_type   → territory_index[tid]["region_type"]
        station_code                    → territory_index[tid]["station_code"]

    The territory_index dict also needs:
        "daily_demand": computed from demand_map (passed separately or set to 0)
        "bdm_cluster":  Config.get_bdm_cluster(station_code)
        "centroid_lat", "centroid_lon": computed from h3_ids_r8 centroid

    Returns a TerritoriesResult with:
        territory_index: {territory_id: metadata_dict}
        hex_to_territory: {h3_id: territory_id}  (from h3_ids_r8)
        geojson_path: territories_geojson_path if it exists, else None
    """

def _sqlite_rows_to_ideal_supply_result(
    supply_rows: list[dict],
) -> IdealSupplyResult:
    """
    Converts geo_ideal_supply SQLite rows to the IdealSupplyResult expected by run_phase3.

    SQLite row fields:
        supply_id       → IdealSlot.slot_id
        territory_id    → IdealSlot.bucket_id
        station_code    → IdealSlot.station_code
        lat, lon        → IdealSlot.lat, IdealSlot.lon
        radius_km * 1000 → IdealSlot.radius_s  (convert km → m)
        capacity_day    → IdealSlot.capacity_s
        origin_hex      → IdealSlot.origin_hex
        matched_partner_id → IdealSlot.matched_partner_id

    Missing fields use safe defaults:
        origin_hex missing → log WARNING, use h3.latlng_to_cell(lat, lon, 9)
        radius_km missing  → log WARNING, use 1.5 (1500m)
        capacity_day missing → log WARNING, use 42

    Returns IdealSupplyResult with slots_by_territory populated.
    """
```

---

### Updated `geo_orchestrator.py`

#### `run_setup` (updated)

```python
def run_setup(
    target_pct: float,
    output_dir: str,
    stations: list[str] | None = None,
    max_workers: int = 4,
) -> None:
    """
    Executes Phase 1 + Phase 2 for each station and persists to LocalSQLite.

    Changes from current implementation:
    - Replaces TursoWriter with LocalWriter
    - Calls LocalWriter.upsert_run, upsert_territories, upsert_h3_cells,
      upsert_ideal_supply, finalize_run(status='setup_complete')
    - No longer calls TursoWriter at all
    """
```

#### `run_daily` (updated)

```python
def run_daily(
    output_dir: str,
    stations: list[str] | None = None,
) -> None:
    """
    Executes Phase 3 + Phase 4 + Phase 5 for each station.

    Changes from current implementation:
    - Replaces TursoReader with LocalReader
    - Replaces geo_daily.run_daily() with run_phase3() from vanilla
    - Calls _selected_territories_to_territories_result() for conversion
    - Calls _sqlite_rows_to_ideal_supply_result() for conversion
    - Calls run_phase3(territories, supply, partner_data, pkg, output_dir, stations)
    - Calls run_phase4(partner_data, territories, pkg)
    - Calls run_phase5(territories, supply, fit, webleads, pkg, output_dir, stations)
    - Persists matched_partner_id via LocalWriter.update_supply_match()
    - Persists attainment/accuracy via LocalWriter.update_territory_fit()
    - No longer calls TursoReader or TursoWriter
    - No longer calls geo_daily.run_daily()
    """
```

#### CLI (updated)

```
--mode setup   --target <pct>   [--stations ...]  [--workers N]  [--output DIR]
--mode daily                    [--stations ...]                  [--output DIR]

REMOVED: --update-heatmap
```

---

### Updated `etl_geocode_empresas.py`

Key changes:
1. **Sync step** (`--sync-empresas` in `geo_orchestrator.py`): a new `sync_empresas_alvo(writer: LocalWriter)` function paginates through Turso's `empresas_alvo` table and upserts all records into the local `empresas_alvo` table in SQLite. This is a one-time or on-demand operation, not part of the daily pipeline.
2. Reads `empresas_alvo` from **LocalSQLite** (not Turso) during geocoding.
3. Reads `NOMINATIM_LOCAL_URL` from environment (default: `http://localhost:8080`). Logs a warning if not set.
4. Calls `{NOMINATIM_LOCAL_URL}/search` instead of `https://nominatim.openstreetmap.org/search`.
5. Removes the `time.sleep(_DELAY_S)` call between requests (no rate limiting on local instance).
6. Writes `empresas_geo` to LocalSQLite via `LocalWriter.upsert_empresas_geo()`.
7. Resume mode reads existing `h3_r9_id` from LocalSQLite.

```python
# New sync function
def sync_empresas_alvo(writer: LocalWriter, turso_client: TursoHTTP) -> dict:
    """
    Downloads all empresas_alvo records from Turso and upserts them into
    the local empresas_alvo table in SQLite.

    Returns {"inserted": int, "updated": int, "total": int}.
    Uses pagination (PAGE_SIZE=5000) to avoid Turso query timeouts.
    """

_NOMINATIM_LOCAL_URL_DEFAULT = "http://localhost:8080"

def _get_nominatim_url() -> str:
    url = os.environ.get("NOMINATIM_LOCAL_URL", "")
    if not url:
        logger.warning(
            "NOMINATIM_LOCAL_URL not set — using default %s",
            _NOMINATIM_LOCAL_URL_DEFAULT,
        )
        return _NOMINATIM_LOCAL_URL_DEFAULT
    return url.rstrip("/")

def _geocode_local_nominatim(
    nominatim_base_url: str,
    endereco: str, bairro: str, cep: str, uf: str,
) -> tuple[float, float] | None:
    """
    Same three-strategy fallback as current _geocode_nominatim,
    but calls nominatim_base_url/search and omits time.sleep().
    """
```

---

## Data Models

### SQLite Schema (all InternalGeoTables)

The schema is identical to the existing Turso DDL in `turso_writer.py`, adapted for local SQLite. All tables use `CREATE TABLE IF NOT EXISTS` and `CREATE INDEX IF NOT EXISTS` for idempotent application.

```sql
-- Run lifecycle tracking
CREATE TABLE IF NOT EXISTS geo_run_metadata (
    run_id                  TEXT PRIMARY KEY,
    station_code            TEXT NOT NULL,
    expansion_target_pct    REAL NOT NULL,
    timestamp_start         TEXT NOT NULL,
    timestamp_end           TEXT,
    n_h3_cells              INTEGER,
    n_territories           INTEGER,
    clustering_algorithm    TEXT,
    silhouette_score        REAL,
    supervised_model        TEXT,
    supervised_f1_macro     REAL,
    is_optimal              INTEGER,   -- 0/1 boolean
    solver_status           TEXT,
    status                  TEXT NOT NULL,  -- 'running' | 'setup_complete' | 'failed' | 'completed'
    umap_params             TEXT,      -- JSON
    n_clusters              INTEGER,
    low_quality_clustering  INTEGER,   -- 0/1 boolean
    profile_coverage        REAL
);

-- Selected territories from Phase 1
CREATE TABLE IF NOT EXISTS geo_territories (
    territory_id        TEXT NOT NULL,
    station_code        TEXT NOT NULL,
    run_id              TEXT NOT NULL,
    region_type         TEXT NOT NULL,
    potential_score     REAL NOT NULL,
    current_partners    INTEGER NOT NULL,
    ideal_slots         INTEGER NOT NULL,
    gap                 REAL NOT NULL,
    model_confidence    REAL NOT NULL,
    low_confidence      INTEGER NOT NULL,  -- 0/1 boolean
    high_opportunity    INTEGER NOT NULL,  -- 0/1 boolean
    geometry_geojson    TEXT NOT NULL,     -- JSON GeoJSON geometry
    h3_ids_json         TEXT NOT NULL,     -- JSON array of h3_id strings
    attainment          REAL,              -- filled by daily mode
    accuracy            REAL,              -- filled by daily mode
    updated_at          TEXT NOT NULL,
    PRIMARY KEY (territory_id, run_id)
);

-- H3 cell features from Phase 1 enrichers
CREATE TABLE IF NOT EXISTS geo_h3_cells (
    h3_id                       TEXT NOT NULL,
    territory_id                TEXT NOT NULL,
    station_code                TEXT NOT NULL,
    run_id                      TEXT NOT NULL,
    company_density             REAL,
    cnae_diversity_index        REAL,
    target_business_density     REAL,
    building_density            REAL,
    avg_building_size_m2        REAL,
    landuse_residential_ratio   REAL,
    landuse_commercial_ratio    REAL,
    poi_density                 REAL,
    road_connectivity_index     REAL,
    avg_income                  REAL,
    population_density          REAL,
    bars_restaurants_density    REAL,
    churches_density            REAL,
    schools_density             REAL,
    dealerships_density         REAL,
    petshops_density            REAL,
    landuse_entropy             REAL,
    road_centrality_index       REAL,
    local_clustering_coefficient REAL,
    region_type                 TEXT,
    potential_score             REAL,
    model_confidence            REAL,
    PRIMARY KEY (h3_id, run_id)
);

-- Ideal supply slots from Phase 2 CP-SAT solver
CREATE TABLE IF NOT EXISTS geo_ideal_supply (
    supply_id           TEXT NOT NULL,
    territory_id        TEXT NOT NULL,
    station_code        TEXT NOT NULL,
    run_id              TEXT NOT NULL,
    lat                 REAL NOT NULL,
    lon                 REAL NOT NULL,
    radius_km           REAL NOT NULL,
    capacity_day        INTEGER NOT NULL,
    matched_partner_id  TEXT,              -- filled by daily mode
    origin_hex          TEXT,
    PRIMARY KEY (supply_id, run_id)
);

-- Territory-level potential scorecard
CREATE TABLE IF NOT EXISTS geo_scorecard (
    entity_id           TEXT NOT NULL,
    entity_type         TEXT NOT NULL,     -- 'ds' | 'bdm'
    run_id              TEXT NOT NULL,
    potential_score     REAL NOT NULL,
    n_territories       INTEGER,
    n_high_opportunity  INTEGER,
    avg_gap             REAL,
    coverage_pct        REAL,
    updated_at          TEXT NOT NULL,
    PRIMARY KEY (entity_id, entity_type, run_id)
);

-- Partner capacity optimisation opportunities (Phase 3.5)
CREATE TABLE IF NOT EXISTS geo_partner_cap_opportunities (
    partner_id              TEXT NOT NULL,
    run_id                  TEXT NOT NULL,
    station_code            TEXT NOT NULL,
    suggested_lat           REAL,
    suggested_lon           REAL,
    suggested_cap           INTEGER,
    suggested_radius        INTEGER,
    estimated_adv_gain      INTEGER,
    distance_from_current   REAL,
    created_at              TEXT NOT NULL,
    PRIMARY KEY (partner_id, run_id)
);

-- Historical partner data used for profile building
CREATE TABLE IF NOT EXISTS geo_partner_history (
    salesforce_id       TEXT NOT NULL,
    station_code        TEXT NOT NULL,
    h3_id_r8            TEXT NOT NULL,
    status              TEXT NOT NULL,
    tenure_days         INTEGER,
    exit_reason_code    TEXT,
    exit_reason_class   TEXT,
    launch_date         TEXT,
    exited_date         TEXT,
    run_id              TEXT NOT NULL,
    PRIMARY KEY (salesforce_id, run_id)
);

-- UMAP-based success/failure reference profiles
CREATE TABLE IF NOT EXISTS geo_partner_profiles (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id              TEXT NOT NULL,
    station_code        TEXT NOT NULL,
    profile_type        TEXT NOT NULL,     -- 'success' | 'failure'
    vector_json         TEXT NOT NULL,     -- JSON array of floats
    n_partners          INTEGER,
    avg_tenure_days     REAL,
    profile_coverage    REAL,
    low_coverage_warning INTEGER,          -- 0/1 boolean
    is_global_fallback  INTEGER,           -- 0/1 boolean
    created_at          TEXT NOT NULL
);

-- Local mirror of Turso empresas_alvo (synced via --sync-empresas)
-- Schema mirrors Turso exactly so Phase 1 enrichers can query without changes
CREATE TABLE IF NOT EXISTS empresas_alvo (
    cnpj                TEXT PRIMARY KEY,
    razao_social        TEXT,
    nome_fantasia       TEXT,
    cnae_principal      TEXT,
    cnae_secundaria     TEXT,
    endereco            TEXT,
    bairro              TEXT,
    cep                 TEXT,
    uf                  TEXT,
    municipio           TEXT,
    telefone_1          TEXT,
    email               TEXT,
    porte               TEXT,
    situacao_cadastral  TEXT,
    data_abertura       TEXT,
    capital_social      REAL,
    synced_at           TEXT
);
CREATE INDEX IF NOT EXISTS idx_empresas_alvo_cep ON empresas_alvo (cep);
CREATE INDEX IF NOT EXISTS idx_empresas_alvo_uf  ON empresas_alvo (uf);

-- Geocoded empresas_alvo results (written by ETL, read by Phase 1 CNPJ enricher)
CREATE TABLE IF NOT EXISTS empresas_geo (
    cnpj                TEXT PRIMARY KEY,
    razao_social        TEXT,
    nome_fantasia       TEXT,
    cnae_principal      TEXT,
    cnae_secundaria     TEXT,
    endereco            TEXT,
    bairro              TEXT,
    cep                 TEXT,
    uf                  TEXT,
    municipio           TEXT,
    telefone_1          TEXT,
    email               TEXT,
    lat                 REAL,
    lng                 REAL,
    h3_r8_id            TEXT,
    h3_r9_id            TEXT,
    h3_id               TEXT,              -- alias for h3_r9_id (backward compat)
    geocode_status      TEXT,              -- 'ok' | 'failed'
    geocoded_at         TEXT
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_geo_territories_station_run
    ON geo_territories (station_code, run_id);
CREATE INDEX IF NOT EXISTS idx_geo_h3_cells_territory_run
    ON geo_h3_cells (territory_id, run_id);
CREATE INDEX IF NOT EXISTS idx_geo_h3_cells_station_run
    ON geo_h3_cells (station_code, run_id);
CREATE INDEX IF NOT EXISTS idx_geo_ideal_supply_station_run
    ON geo_ideal_supply (station_code, run_id);
CREATE INDEX IF NOT EXISTS idx_geo_run_metadata_station_status
    ON geo_run_metadata (station_code, status);
CREATE INDEX IF NOT EXISTS idx_empresas_geo_h3_r8
    ON empresas_geo (h3_r8_id);
CREATE INDEX IF NOT EXISTS idx_empresas_geo_h3_r9
    ON empresas_geo (h3_r9_id);
```

### ALTER TABLE Migrations

The following `ALTER TABLE` statements are applied on startup (gracefully ignoring "duplicate column name" errors, matching the existing `TursoWriter` behaviour):

```sql
ALTER TABLE geo_run_metadata ADD COLUMN umap_params TEXT;
ALTER TABLE geo_run_metadata ADD COLUMN n_clusters INTEGER;
ALTER TABLE geo_run_metadata ADD COLUMN low_quality_clustering INTEGER;
ALTER TABLE geo_run_metadata ADD COLUMN profile_coverage REAL;
ALTER TABLE geo_ideal_supply ADD COLUMN origin_hex TEXT;
```

### Turso vs SQLite: What Stays Where

| Table | Location | Rationale |
|---|---|---|
| `geo_run_metadata` | **SQLite** | Pipeline-internal state |
| `geo_territories` | **SQLite** | Pipeline-internal state |
| `geo_h3_cells` | **SQLite** | Pipeline-internal state |
| `geo_ideal_supply` | **SQLite** | Pipeline-internal state |
| `geo_scorecard` | **SQLite** | Pipeline-internal state |
| `geo_partner_cap_opportunities` | **SQLite** | Pipeline-internal state |
| `geo_partner_history` | **SQLite** | Pipeline-internal state |
| `geo_partner_profiles` | **SQLite** | Pipeline-internal state |
| `empresas_geo` | **SQLite** | ETL output, read by Phase 1 |
| `empresas_alvo` | **SQLite** (mirror) + **Turso** (source) | Synced locally via `--sync-empresas`; Turso remains source of truth for frontend/API |
| `gmaps_leads` | **Turso** | Shared with frontend/API, not used by pipeline |
| `contactadas` | **Turso** | Shared with frontend/API, not used by pipeline |

### `TerritoriesResult` Mapping

The `TerritoriesResult` dataclass (from `shared/models.py`) requires a `territory_index` dict where each entry has specific fields consumed by `run_phase3` and `run_phase5`. The conversion from `SelectedTerritory` populates these fields:

| `territory_index[tid]` field | Source |
|---|---|
| `station_code` | `SelectedTerritory.territory_id` prefix (e.g. `"DSP2"`) or passed explicitly |
| `hex_ids` | `SelectedTerritory.h3_ids_r8` |
| `potential_score` | `SelectedTerritory.potential_score` |
| `gap` | `SelectedTerritory.gap` |
| `region_type` | `SelectedTerritory.region_type.value` |
| `model_confidence` | `SelectedTerritory.model_confidence` |
| `high_opportunity` | `SelectedTerritory.high_opportunity` |
| `daily_demand` | Sum of `demand_map.get(h, 0)` for all `h` in `h3_ids_r8`, divided by `pkg.days` |
| `bdm_cluster` | `Config.get_bdm_cluster(station_code)` |
| `centroid_lat`, `centroid_lon` | Mean of `h3.cell_to_latlng(h)` for all `h` in `h3_ids_r8` |

### `IdealSupplyResult` Mapping

| `IdealSlot` field | SQLite `geo_ideal_supply` column | Notes |
|---|---|---|
| `slot_id` | `supply_id` | |
| `bucket_id` | `territory_id` | |
| `station_code` | `station_code` | |
| `lat` | `lat` | |
| `lon` | `lon` | |
| `radius_s` | `radius_km * 1000` | Convert km → m |
| `capacity_s` | `capacity_day` | |
| `origin_hex` | `origin_hex` | Default: `h3.latlng_to_cell(lat, lon, 9)` if NULL |
| `matched_partner_id` | `matched_partner_id` | NULL → `None` |
| `allocations` | *(not stored in SQLite)* | Default: `[]` |

---

## Correctness Properties

*A property is a characteristic or behavior that should hold true across all valid executions of a system — essentially, a formal statement about what the system should do. Properties serve as the bridge between human-readable specifications and machine-verifiable correctness guarantees.*

### Property 1: LocalWriter upsert idempotence

*For any* valid InternalGeoTable record (run metadata, territory, H3 cell, ideal supply slot, scorecard entry, cap opportunity, partner history, or partner profile), upserting it twice via `LocalWriter` should leave the database in the same state as upserting it once.

**Validates: Requirements 1.5, 6.1, 6.2, 6.3**

---

### Property 2: Setup round-trip — territories and ideal supply

*For any* list of `SelectedTerritory` objects and corresponding `GeoIdealSlot` lists written to LocalSQLite via `LocalWriter` during setup, reading them back via `LocalReader.get_territories()` and `LocalReader.get_ideal_supply()` should return rows that contain equivalent `territory_id`, `station_code`, `run_id`, `lat`, `lon`, `radius_km`, `capacity_day`, and `origin_hex` values.

**Validates: Requirements 1.3, 1.4, 7.2, 7.3**

---

### Property 3: SelectedTerritory → TerritoriesResult conversion preserves hex membership

*For any* list of `SelectedTerritory` objects, the `TerritoriesResult` produced by `_selected_territories_to_territories_result()` should satisfy: for every `h3_id` in `territory.h3_ids_r8`, `result.hex_to_territory[h3_id] == territory.territory_id`.

**Validates: Requirements 3.1, 3.3**

---

### Property 4: SQLite rows → IdealSupplyResult conversion preserves slot data

*For any* list of `geo_ideal_supply` SQLite rows with valid `supply_id`, `territory_id`, `station_code`, `lat`, `lon`, `radius_km`, and `capacity_day`, the `IdealSupplyResult` produced by `_sqlite_rows_to_ideal_supply_result()` should contain an `IdealSlot` for each row where `slot.slot_id == row["supply_id"]`, `slot.bucket_id == row["territory_id"]`, `slot.radius_s == int(row["radius_km"] * 1000)`, and `slot.capacity_s == row["capacity_day"]`.

**Validates: Requirements 3.2, 3.4**

---

### Property 5: Daily persistence round-trip — matched_partner_id and territory fit

*For any* `FitResult` produced by `run_phase3`, after calling `LocalWriter.update_supply_match()` and `LocalWriter.update_territory_fit()`, reading back via `LocalReader.get_ideal_supply()` and `LocalReader.get_territories()` should return rows where `matched_partner_id` and `attainment`/`accuracy` match the values in the `FitResult`.

**Validates: Requirements 2.10**

---

### Property 6: `get_latest_run_id` returns the most recent `setup_complete` run

*For any* set of runs with mixed statuses (`running`, `setup_complete`, `failed`, `completed`) for a given station, `LocalReader.get_latest_run_id(station_code)` should return the `run_id` with `status='setup_complete'` that has the latest `timestamp_start`. If no `setup_complete` run exists, it should fall back to the most recent `completed` run. If neither exists, it should return `None`.

**Validates: Requirements 7.6**

---

### Property 7: Geocoding fallback chain is exhausted in order

*For any* address where the first Nominatim strategy (full address) returns no results, the ETL should attempt the second strategy (CEP only). If the second strategy also returns no results, it should attempt the third strategy (bairro + UF). The ETL should only record `geocode_status='failed'` after all three strategies have been tried.

**Validates: Requirements 5.6**

---

### Property 8: ETL resume skips already-geocoded records

*For any* set of `empresas_alvo` records where a subset already has `h3_r9_id IS NOT NULL` in LocalSQLite, running the ETL with `--resume` should not call the Nominatim API for those records, and the total count of geocoded records in LocalSQLite should not decrease.

**Validates: Requirements 5.9**

---

### Property 9: `optimization_data.geojson` feature property schema is preserved

*For any* `TerritoriesResult` and `IdealSupplyResult` passed to `run_phase5`, every `TERRITORY_HEX` feature in the output `optimization_data.geojson` should have the properties `type`, `hex_id`, `territory_id`, `delivery_station`, `bdm`, `ctl`, `demand_total`, `demand_daily`, and `ceps`; and every `IDEAL_SLOT` feature should have the properties `type`, `slot_id`, `territory_id`, `delivery_station`, `radius_s`, `capacity_day`, `ceps`, `h3_r9_id`, and `h3_r8_id`.

**Validates: Requirements 8.5**

---

### Property 10: `heatmap.geojson` features contain `covering_partners` and `hex_coverage`

*For any* `FitResult` with at least one Active or Onboarding partner with a `matched_slot_id`, the `heatmap.geojson` produced by `run_phase5` should have `covering_partners` and `hex_coverage` fields on the `properties` object of every feature whose `hex_id` is covered by at least one such partner.

**Validates: Requirements 2.5, 8.2**

---

## Error Handling

### LocalWriter / LocalReader

- **Database not found on read:** `LocalReader` opens the database in read-write mode if the file does not exist (first run after setup). If `get_latest_run_id` is called before any setup has run, it returns `None` and the orchestrator prints a user-friendly message: `"No setup run found for {station_code} — run --mode setup first."`.
- **Directory does not exist:** `LocalWriter.__init__` calls `Path(db_path).parent.mkdir(parents=True, exist_ok=True)` before opening the connection.
- **Schema migration errors:** `ALTER TABLE … ADD COLUMN` errors with "duplicate column name" are caught and logged at DEBUG level. All other `ALTER TABLE` errors are logged at WARNING level but do not abort the pipeline.
- **SQLite constraint violations:** `INSERT OR REPLACE` / `ON CONFLICT DO UPDATE` semantics prevent primary key violations. Any unexpected `sqlite3.Error` is re-raised as a `RuntimeError` with the original error message.
- **Missing fields in SQLite rows (conversion layer):** `_sqlite_rows_to_ideal_supply_result` logs a WARNING for each missing required field and substitutes a safe default (see Data Models section). It never raises an exception for missing fields.

### `run_setup` error handling

- If Phase 1 or Phase 2 raises an exception for a station, the orchestrator catches it, logs the traceback, calls `LocalWriter.finalize_run(run_id, status='failed')`, and continues to the next station.
- If `LocalWriter.finalize_run` itself fails, the error is logged but does not propagate (best-effort cleanup).

### `run_daily` error handling

- If `LocalReader.get_latest_run_id` returns `None` for a station, the orchestrator skips that station with a printed warning.
- If `LocalReader.get_ideal_supply` returns an empty list, the orchestrator skips that station with a printed warning.
- If `run_phase3`, `run_phase4`, or `run_phase5` raises an exception, it propagates normally (same behaviour as the vanilla orchestrator).
- Phase 3.5 (cap optimizer) is wrapped in `try/except` and logs errors without aborting the pipeline.

### ETL error handling

- If `NOMINATIM_LOCAL_URL` is not set, a WARNING is logged and the default URL is used.
- If all three geocoding strategies fail for a record, `geocode_status='failed'` is stored and the record is counted in the failure summary.
- If the LocalSQLite write fails for a batch, the error is logged and the batch is skipped (not retried). The ETL continues with the next batch.
- At completion, a summary log line is always emitted: `"ETL completed: {ok_count} geocoded, {fail_count} failures"`.

---

## Testing Strategy

### Unit Tests

Unit tests verify specific examples, edge cases, and error conditions. They should be placed in `backend/tests/geo_intelligence/`.

**`test_local_writer.py`**
- Schema creation: verify all 9 tables exist after `ensure_schema()`.
- Schema idempotence: call `ensure_schema()` twice, verify no error.
- `upsert_run` / `finalize_run`: write a run, read it back, verify fields.
- `update_supply_match`: write slots, update matched_partner_id, read back.
- `update_territory_fit`: write territories, update attainment/accuracy, read back.
- Directory creation: point `GEO_SQLITE_PATH` to a non-existent directory, verify it is created.
- Shared tables absent: verify `empresas_alvo`, `gmaps_leads`, `contactadas` are not in `sqlite_master`.

**`test_local_reader.py`**
- `get_latest_run_id` with `setup_complete` runs.
- `get_latest_run_id` fallback to `completed` when no `setup_complete` exists.
- `get_latest_run_id` returns `None` when no runs exist.
- `get_territories` with `region_type` and `min_gap` filters.
- `get_ideal_supply` returns correct rows.
- TTL cache: verify a second call within TTL does not hit the database.

**`test_conversion_layer.py`**
- `_selected_territories_to_territories_result`: verify `hex_to_territory` mapping.
- `_selected_territories_to_territories_result`: verify `territory_index` fields.
- `_sqlite_rows_to_ideal_supply_result`: verify `IdealSlot` field mapping.
- `_sqlite_rows_to_ideal_supply_result`: missing `origin_hex` → default computed from lat/lon.
- `_sqlite_rows_to_ideal_supply_result`: missing `radius_km` → default 1.5.

**`test_geo_orchestrator_cli.py`**
- `--update-heatmap` argument is rejected by argparse.
- `--mode setup` without `--target` exits with error.
- `--mode daily` help text references `--mode daily` for heatmap refresh.

**`test_etl_geocode_empresas.py`**
- `NOMINATIM_LOCAL_URL` env var is used when set.
- Default URL is used when env var is not set; WARNING is logged.
- `time.sleep` is not called (mock `time.sleep`, verify zero calls).
- Resume mode: records with existing `h3_r9_id` are skipped.
- Three-strategy fallback: first strategy fails → second is tried.
- Summary log is emitted at completion.

### Property-Based Tests

Property-based tests use [Hypothesis](https://hypothesis.readthedocs.io/) and are placed in `backend/tests/geo_intelligence/test_properties.py`. Each test runs a minimum of 100 iterations.

Each test is tagged with a comment referencing the design property:
```python
# Feature: geo-intelligence-restructure, Property N: <property_text>
```

**Property 1 — LocalWriter upsert idempotence**
Generate random `geo_run_metadata` rows. Write once, write again with the same primary key, verify the row count and field values are unchanged.

**Property 2 — Setup round-trip**
Generate random lists of `SelectedTerritory` objects and `GeoIdealSlot` lists. Write via `LocalWriter`, read back via `LocalReader`, verify field equivalence.

**Property 3 — TerritoriesResult hex membership**
Generate random `SelectedTerritory` lists. Convert via `_selected_territories_to_territories_result`. For every `h3_id` in every territory's `h3_ids_r8`, assert `result.hex_to_territory[h3_id] == territory.territory_id`.

**Property 4 — IdealSupplyResult slot data**
Generate random `geo_ideal_supply` row dicts. Convert via `_sqlite_rows_to_ideal_supply_result`. For every row, assert the corresponding `IdealSlot` has the correct field values.

**Property 5 — Daily persistence round-trip**
Generate random `FitResult` objects (with matched slots and territory fits). Write via `LocalWriter.update_supply_match` and `update_territory_fit`. Read back via `LocalReader`. Assert field equivalence.

**Property 6 — `get_latest_run_id` correctness**
Generate random lists of run records with mixed statuses and timestamps. Write to SQLite. Assert `get_latest_run_id` returns the most recent `setup_complete` run, or falls back to `completed`, or returns `None`.

**Property 7 — Geocoding fallback chain**
Generate random address tuples where strategy 1 always fails (mock HTTP to return empty). Assert strategy 2 is called. Generate tuples where strategies 1 and 2 fail. Assert strategy 3 is called.

**Property 8 — ETL resume**
Generate random sets of `empresas_alvo` records, a subset of which already have `h3_r9_id` in SQLite. Run ETL with `resume=True`. Assert the Nominatim mock was not called for the already-geocoded records.

**Property 9 — `optimization_data.geojson` schema**
Generate random `TerritoriesResult` and `IdealSupplyResult`. Call `run_phase5` (with mocked file I/O). For every feature in the output GeoJSON, assert the required property keys are present.

**Property 10 — `heatmap.geojson` coverage fields**
Generate random `FitResult` with Active partners having `matched_slot_id` and `allocations`. Call the heatmap enrichment function. For every covered hex, assert `covering_partners` and `hex_coverage` are present in `properties`.
