"""
local_writer.py
===============
SQLite replacement for TursoWriter. Persists all internal GeoIntelligence
pipeline state to a local SQLite file.
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from geo_intelligence.pipeline import (
    GeoSetupConfig,
    H3CellFeatures,
    PartnerProfile,
    ReferenceProfiles,
    RunMetadata,
    TerritoryOutput,
)

logger = logging.getLogger(__name__)

_DEFAULT_DB_PATH = "output/geo_intelligence/geo_intelligence.db"

_DDL_STATEMENTS = [
    """CREATE TABLE IF NOT EXISTS geo_run_metadata (
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
        is_optimal              INTEGER,
        solver_status           TEXT,
        status                  TEXT NOT NULL,
        umap_params             TEXT,
        n_clusters              INTEGER,
        low_quality_clustering  INTEGER,
        profile_coverage        REAL
    )""",
    """CREATE TABLE IF NOT EXISTS geo_territories (
        territory_id        TEXT NOT NULL,
        station_code        TEXT NOT NULL,
        run_id              TEXT NOT NULL,
        region_type         TEXT NOT NULL,
        potential_score     REAL NOT NULL,
        current_partners    INTEGER NOT NULL,
        ideal_slots         INTEGER NOT NULL,
        gap                 REAL NOT NULL,
        model_confidence    REAL NOT NULL,
        low_confidence      INTEGER NOT NULL,
        high_opportunity    INTEGER NOT NULL,
        geometry_geojson    TEXT NOT NULL,
        h3_ids_json         TEXT NOT NULL,
        attainment          REAL,
        accuracy            REAL,
        updated_at          TEXT NOT NULL,
        PRIMARY KEY (territory_id, run_id)
    )""",
    """CREATE TABLE IF NOT EXISTS geo_h3_cells (
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
    )""",
    """CREATE TABLE IF NOT EXISTS geo_ideal_supply (
        supply_id           TEXT NOT NULL,
        territory_id        TEXT NOT NULL,
        station_code        TEXT NOT NULL,
        run_id              TEXT NOT NULL,
        lat                 REAL NOT NULL,
        lon                 REAL NOT NULL,
        radius_km           REAL NOT NULL,
        capacity_day        INTEGER NOT NULL,
        matched_partner_id  TEXT,
        origin_hex          TEXT,
        PRIMARY KEY (supply_id, run_id)
    )""",
    """CREATE TABLE IF NOT EXISTS geo_scorecard (
        entity_id           TEXT NOT NULL,
        entity_type         TEXT NOT NULL,
        run_id              TEXT NOT NULL,
        potential_score     REAL NOT NULL,
        n_territories       INTEGER,
        n_high_opportunity  INTEGER,
        avg_gap             REAL,
        coverage_pct        REAL,
        updated_at          TEXT NOT NULL,
        PRIMARY KEY (entity_id, entity_type, run_id)
    )""",
    """CREATE TABLE IF NOT EXISTS geo_partner_cap_opportunities (
        partner_id              TEXT    NOT NULL,
        run_id                  TEXT    NOT NULL,
        station_code            TEXT    NOT NULL,
        suggested_lat           REAL,
        suggested_lon           REAL,
        suggested_cap           INTEGER,
        suggested_radius        INTEGER,
        estimated_adv_gain      INTEGER,
        distance_from_current   REAL,
        created_at              TEXT    NOT NULL,
        PRIMARY KEY (partner_id, run_id)
    )""",
    """CREATE TABLE IF NOT EXISTS geo_partner_history (
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
    )""",
    """CREATE TABLE IF NOT EXISTS geo_partner_profiles (
        id                  INTEGER PRIMARY KEY AUTOINCREMENT,
        run_id              TEXT NOT NULL,
        station_code        TEXT NOT NULL,
        profile_type        TEXT NOT NULL,
        vector_json         TEXT NOT NULL,
        n_partners          INTEGER,
        avg_tenure_days     REAL,
        profile_coverage    REAL,
        low_coverage_warning INTEGER,
        is_global_fallback  INTEGER,
        created_at          TEXT NOT NULL
    )""",
    """CREATE TABLE IF NOT EXISTS empresas_geo (
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
        h3_id               TEXT,
        geocode_status      TEXT,
        geocoded_at         TEXT
    )""",
    """CREATE TABLE IF NOT EXISTS empresas_alvo (
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
    )""",
]

_INDEX_STATEMENTS = [
    "CREATE INDEX IF NOT EXISTS idx_geo_territories_station_run ON geo_territories (station_code, run_id)",
    "CREATE INDEX IF NOT EXISTS idx_geo_h3_cells_territory_run ON geo_h3_cells (territory_id, run_id)",
    "CREATE INDEX IF NOT EXISTS idx_geo_h3_cells_station_run ON geo_h3_cells (station_code, run_id)",
    "CREATE INDEX IF NOT EXISTS idx_geo_ideal_supply_station_run ON geo_ideal_supply (station_code, run_id)",
    "CREATE INDEX IF NOT EXISTS idx_geo_run_metadata_station_status ON geo_run_metadata (station_code, status)",
    "CREATE INDEX IF NOT EXISTS idx_empresas_geo_h3_r8 ON empresas_geo (h3_r8_id)",
    "CREATE INDEX IF NOT EXISTS idx_empresas_geo_h3_r9 ON empresas_geo (h3_r9_id)",
    "CREATE INDEX IF NOT EXISTS idx_empresas_alvo_cep ON empresas_alvo (cep)",
    "CREATE INDEX IF NOT EXISTS idx_empresas_alvo_uf  ON empresas_alvo (uf)",
]

_ALTER_STATEMENTS = [
    "ALTER TABLE geo_run_metadata ADD COLUMN umap_params TEXT",
    "ALTER TABLE geo_run_metadata ADD COLUMN n_clusters INTEGER",
    "ALTER TABLE geo_run_metadata ADD COLUMN low_quality_clustering INTEGER",
    "ALTER TABLE geo_run_metadata ADD COLUMN profile_coverage REAL",
    "ALTER TABLE geo_ideal_supply ADD COLUMN origin_hex TEXT",
]

_BATCH_SIZE = 100


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _chunks(lst: list, size: int):
    for i in range(0, len(lst), size):
        yield lst[i: i + size]


class LocalWriter:
    """SQLite-backed writer for all internal GeoIntelligence pipeline tables."""

    def __init__(self, db_path: str | None = None) -> None:
        if db_path is None:
            db_path = os.environ.get("GEO_SQLITE_PATH", _DEFAULT_DB_PATH)
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self.ensure_schema()

    def ensure_schema(self) -> None:
        """Apply all DDL statements idempotently."""
        cur = self._conn.cursor()
        for ddl in _DDL_STATEMENTS:
            cur.execute(ddl)
        for idx in _INDEX_STATEMENTS:
            cur.execute(idx)
        self._conn.commit()

        # ALTER TABLE migrations — gracefully handle duplicate column errors
        for alter in _ALTER_STATEMENTS:
            try:
                cur.execute(alter)
                self._conn.commit()
            except sqlite3.OperationalError as exc:
                if "duplicate column name" in str(exc).lower():
                    logger.debug("Coluna já existe (ignorado): %s", alter)
                else:
                    logger.warning("ALTER TABLE falhou: %s | erro: %s", alter, exc)
                    raise

        logger.info("Schema geo_* verificado/criado.")

    # ------------------------------------------------------------------
    # Run lifecycle
    # ------------------------------------------------------------------

    def upsert_run(self, run_id: str, config: GeoSetupConfig) -> None:
        """INSERT OR REPLACE into geo_run_metadata with status='running'."""
        self._conn.execute(
            """INSERT INTO geo_run_metadata
               (run_id, station_code, expansion_target_pct, timestamp_start, status)
               VALUES (?, ?, ?, ?, 'running')
               ON CONFLICT(run_id) DO UPDATE SET
               status='running', timestamp_start=excluded.timestamp_start""",
            [run_id, config.station_code, config.expansion_target_pct, _now_iso()],
        )
        self._conn.commit()

    def finalize_run(self, run_id: str, metadata: RunMetadata) -> None:
        """UPDATE geo_run_metadata with final fields and status."""
        umap_params_json = (
            json.dumps(metadata.umap_params) if metadata.umap_params is not None else None
        )
        self._conn.execute(
            """UPDATE geo_run_metadata SET
               timestamp_end=?, n_h3_cells=?, n_territories=?,
               clustering_algorithm=?, silhouette_score=?, supervised_model=?,
               supervised_f1_macro=?, is_optimal=?, solver_status=?, status=?,
               umap_params=?, n_clusters=?, low_quality_clustering=?, profile_coverage=?
               WHERE run_id=?""",
            [
                metadata.timestamp_end,
                metadata.n_h3_cells,
                metadata.n_territories,
                metadata.clustering_algorithm,
                metadata.silhouette_score,
                metadata.supervised_model,
                metadata.supervised_f1_macro,
                int(metadata.is_optimal) if metadata.is_optimal is not None else None,
                metadata.solver_status,
                metadata.status,
                umap_params_json,
                metadata.n_clusters,
                int(metadata.low_quality_clustering) if metadata.low_quality_clustering is not None else None,
                metadata.profile_coverage,
                run_id,
            ],
        )
        self._conn.commit()

    # ------------------------------------------------------------------
    # Territories
    # ------------------------------------------------------------------

    def upsert_territories(
        self,
        run_id: str,
        territories: list[TerritoryOutput],
        station_code: str,
    ) -> None:
        """Batch upsert into geo_territories."""
        sql = """INSERT INTO geo_territories
            (territory_id, station_code, run_id, region_type, potential_score,
             current_partners, ideal_slots, gap, model_confidence, low_confidence,
             high_opportunity, geometry_geojson, h3_ids_json, attainment, accuracy, updated_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(territory_id, run_id) DO UPDATE SET
            potential_score=excluded.potential_score,
            gap=excluded.gap,
            model_confidence=excluded.model_confidence,
            updated_at=excluded.updated_at"""
        now = _now_iso()
        for batch in _chunks(territories, _BATCH_SIZE):
            rows = []
            for t in batch:
                rows.append((
                    t.territory_id,
                    station_code,
                    run_id,
                    t.region_type.value if hasattr(t.region_type, "value") else t.region_type,
                    t.potential_score,
                    t.current_partners,
                    t.ideal_slots,
                    t.gap,
                    t.model_confidence,
                    int(t.low_confidence),
                    int(t.high_opportunity),
                    json.dumps(t.geometry),
                    json.dumps(t.h3_ids),
                    getattr(t, "attainment", None),
                    getattr(t, "accuracy", None),
                    now,
                ))
            self._conn.executemany(sql, rows)
        self._conn.commit()
        logger.info("Upsert de %d territórios (run=%s).", len(territories), run_id)

    def update_territory_fit(self, run_id: str, fits) -> None:
        """UPDATE geo_territories.attainment and accuracy after Phase 3.

        Accepts two formats:
        - list[dict]: [{"territory_id": str, "attainment": float, "accuracy": float}]
        - dict[str, dict]: {territory_id: {"attainment": float, "accuracy": float}}
        """
        if isinstance(fits, dict):
            fits_list = [{"territory_id": k, **v} for k, v in fits.items()]
        else:
            fits_list = fits
        sql = """UPDATE geo_territories
                 SET attainment=?, accuracy=?, updated_at=?
                 WHERE territory_id=? AND run_id=?"""
        now = _now_iso()
        rows = [(f["attainment"], f["accuracy"], now, f["territory_id"], run_id) for f in fits_list]
        if rows:
            self._conn.executemany(sql, rows)
            self._conn.commit()
        logger.info("update_territory_fit: %d territórios atualizados (run=%s).", len(rows), run_id)

    # ------------------------------------------------------------------
    # H3 cells
    # ------------------------------------------------------------------

    def upsert_h3_cells(
        self,
        run_id: str,
        cells: list[H3CellFeatures],
        territory_id: str,
        station_code: str,
    ) -> None:
        """Batch upsert into geo_h3_cells."""
        sql = """INSERT INTO geo_h3_cells
            (h3_id, territory_id, station_code, run_id,
             company_density, cnae_diversity_index, target_business_density,
             building_density, avg_building_size_m2, landuse_residential_ratio,
             landuse_commercial_ratio, poi_density, road_connectivity_index,
             avg_income, population_density, bars_restaurants_density, churches_density,
             schools_density, dealerships_density, petshops_density,
             landuse_entropy, road_centrality_index, local_clustering_coefficient,
             region_type, potential_score, model_confidence)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(h3_id, run_id) DO UPDATE SET
            potential_score=excluded.potential_score"""
        for batch in _chunks(cells, _BATCH_SIZE):
            rows = []
            for c in batch:
                rt = None
                if hasattr(c, "region_type") and c.region_type is not None:
                    rt = c.region_type.value if hasattr(c.region_type, "value") else c.region_type
                rows.append((
                    c.h3_id,
                    territory_id,
                    station_code,
                    run_id,
                    c.company_density,
                    c.cnae_diversity_index,
                    c.target_business_density,
                    c.building_density,
                    c.avg_building_size_m2,
                    c.landuse_residential_ratio,
                    c.landuse_commercial_ratio,
                    c.poi_density,
                    c.road_connectivity_index,
                    c.avg_income,
                    c.population_density,
                    c.bars_restaurants_density,
                    c.churches_density,
                    c.schools_density,
                    c.dealerships_density,
                    c.petshops_density,
                    c.landuse_entropy,
                    c.road_centrality_index,
                    c.local_clustering_coefficient,
                    rt,
                    getattr(c, "potential_score", None),
                    getattr(c, "model_confidence", None),
                ))
            self._conn.executemany(sql, rows)
        self._conn.commit()

    # ------------------------------------------------------------------
    # Ideal supply
    # ------------------------------------------------------------------

    def upsert_ideal_supply(self, run_id: str, supply_points: list[dict]) -> None:
        """Batch upsert into geo_ideal_supply."""
        sql = """INSERT INTO geo_ideal_supply
                 (supply_id, territory_id, station_code, run_id, lat, lon,
                  radius_km, capacity_day, origin_hex)
                 VALUES (?,?,?,?,?,?,?,?,?)
                 ON CONFLICT(supply_id, run_id) DO UPDATE SET
                 lat=excluded.lat, lon=excluded.lon, origin_hex=excluded.origin_hex"""
        rows = [
            (
                sp["supply_id"],
                sp["territory_id"],
                sp["station_code"],
                run_id,
                sp["lat"],
                sp["lon"],
                sp["radius_km"],
                sp["capacity_day"],
                sp.get("origin_hex"),
            )
            for sp in supply_points
        ]
        if rows:
            self._conn.executemany(sql, rows)
            self._conn.commit()

    def update_supply_match(self, run_id: str, matches) -> None:
        """UPDATE geo_ideal_supply.matched_partner_id after Phase 3.

        Accepts two formats:
        - list[dict]: [{"supply_id": str, "partner_id": str}]
        - dict[str, str]: {slot_id: partner_id}
        """
        if isinstance(matches, dict):
            matches_list = [{"supply_id": k, "partner_id": v} for k, v in matches.items()]
        else:
            matches_list = matches
        sql = "UPDATE geo_ideal_supply SET matched_partner_id=? WHERE supply_id=? AND run_id=?"
        rows = [(m["partner_id"], m["supply_id"], run_id) for m in matches_list]
        if rows:
            self._conn.executemany(sql, rows)
            self._conn.commit()
        logger.info("update_supply_match: %d slots atualizados (run=%s).", len(rows), run_id)

    # ------------------------------------------------------------------
    # Scorecard
    # ------------------------------------------------------------------

    def upsert_scorecard(self, run_id: str, scorecard_rows: list[dict]) -> None:
        """Batch upsert into geo_scorecard."""
        sql = """INSERT INTO geo_scorecard
                 (entity_id, entity_type, run_id, potential_score,
                  n_territories, n_high_opportunity, avg_gap, coverage_pct, updated_at)
                 VALUES (?,?,?,?,?,?,?,?,?)
                 ON CONFLICT(entity_id, entity_type, run_id) DO UPDATE SET
                 potential_score=excluded.potential_score"""
        now = _now_iso()
        rows = [
            (
                r["entity_id"],
                r["entity_type"],
                run_id,
                r["potential_score"],
                r.get("n_territories"),
                r.get("n_high_opportunity"),
                r.get("avg_gap"),
                r.get("coverage_pct"),
                now,
            )
            for r in scorecard_rows
        ]
        if rows:
            self._conn.executemany(sql, rows)
            self._conn.commit()

    # ------------------------------------------------------------------
    # Partner profiles
    # ------------------------------------------------------------------

    def upsert_partner_profiles(
        self,
        run_id: str,
        station_code: str,
        profiles: ReferenceProfiles,
    ) -> None:
        """Upsert success and failure vectors into geo_partner_profiles."""
        sql = """INSERT INTO geo_partner_profiles
            (run_id, station_code, profile_type, vector_json, n_partners,
             avg_tenure_days, profile_coverage, low_coverage_warning,
             is_global_fallback, created_at)
            VALUES (?,?,?,?,?,?,?,?,?,?)"""
        now = _now_iso()
        rows = []
        for profile_type, vector, n_partners in [
            ("success", profiles.success_vector, profiles.n_active),
            ("failure", profiles.failure_vector, profiles.n_exited_area),
        ]:
            if vector is not None and hasattr(vector, "tolist"):
                vec_list = vector.tolist()
            elif vector is not None:
                vec_list = list(vector)
            else:
                vec_list = []
            rows.append((
                run_id,
                station_code,
                profile_type,
                json.dumps(vec_list),
                n_partners,
                profiles.avg_tenure_active if profile_type == "success" else None,
                profiles.profile_coverage,
                int(profiles.low_coverage_warning),
                int(profiles.is_global_fallback),
                now,
            ))
        self._conn.executemany(sql, rows)
        self._conn.commit()
        logger.info(
            "upsert_partner_profiles: success+failure persistidos (run=%s, station=%s).",
            run_id,
            station_code,
        )

    # ------------------------------------------------------------------
    # Cap opportunities
    # ------------------------------------------------------------------

    def upsert_cap_opportunities(self, run_id: str, opportunities: list[dict]) -> None:
        """Upsert into geo_partner_cap_opportunities."""
        sql = """INSERT INTO geo_partner_cap_opportunities
            (partner_id, run_id, station_code, suggested_lat, suggested_lon,
             suggested_cap, suggested_radius, estimated_adv_gain,
             distance_from_current, created_at)
            VALUES (?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(partner_id, run_id) DO UPDATE SET
            station_code=excluded.station_code,
            suggested_lat=excluded.suggested_lat,
            suggested_lon=excluded.suggested_lon,
            suggested_cap=excluded.suggested_cap,
            suggested_radius=excluded.suggested_radius,
            estimated_adv_gain=excluded.estimated_adv_gain,
            distance_from_current=excluded.distance_from_current,
            created_at=excluded.created_at"""
        for batch in _chunks(opportunities, _BATCH_SIZE):
            rows = [
                (
                    opp["partner_id"],
                    run_id,
                    opp["station_code"],
                    opp.get("suggested_lat"),
                    opp.get("suggested_lon"),
                    opp.get("suggested_cap"),
                    opp.get("suggested_radius"),
                    opp.get("estimated_adv_gain"),
                    opp.get("distance_from_current"),
                    opp["created_at"],
                )
                for opp in batch
            ]
            self._conn.executemany(sql, rows)
        self._conn.commit()
        logger.info(
            "upsert_cap_opportunities: %d oportunidades persistidas (run=%s).",
            len(opportunities),
            run_id,
        )

    # ------------------------------------------------------------------
    # Partner history
    # ------------------------------------------------------------------

    def upsert_partner_history(
        self, run_id: str, partner_profiles: list[PartnerProfile]
    ) -> None:
        """Upsert into geo_partner_history."""
        sql = """INSERT INTO geo_partner_history
            (salesforce_id, station_code, h3_id_r8, status, tenure_days,
             exit_reason_code, exit_reason_class, launch_date, exited_date, run_id)
            VALUES (?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(salesforce_id, run_id) DO UPDATE SET
            status=excluded.status,
            tenure_days=excluded.tenure_days,
            exit_reason_code=excluded.exit_reason_code,
            exit_reason_class=excluded.exit_reason_class,
            launch_date=excluded.launch_date,
            exited_date=excluded.exited_date"""
        for batch in _chunks(partner_profiles, _BATCH_SIZE):
            rows = []
            for p in batch:
                station = getattr(p, "station_code", "") or ""
                exit_code = getattr(p, "exit_reason_code", None)
                launch = getattr(p, "launch_date", None)
                exited = getattr(p, "exited_date", None)
                rows.append((
                    p.salesforce_id,
                    station,
                    p.h3_id_r8,
                    p.status,
                    p.tenure_days,
                    exit_code,
                    p.exit_reason_class,
                    launch,
                    exited,
                    run_id,
                ))
            self._conn.executemany(sql, rows)
        self._conn.commit()
        logger.info(
            "upsert_partner_history: %d parceiros persistidos (run=%s).",
            len(partner_profiles),
            run_id,
        )

    # ------------------------------------------------------------------
    # ETL tables
    # ------------------------------------------------------------------

    def upsert_empresas_geo(self, rows: list[dict]) -> None:
        """Batch upsert into empresas_geo (used by ETL)."""
        sql = """INSERT OR REPLACE INTO empresas_geo
            (cnpj, razao_social, nome_fantasia, cnae_principal, cnae_secundaria,
             endereco, bairro, cep, uf, municipio, telefone_1, email,
             lat, lng, h3_r8_id, h3_r9_id, h3_id, geocode_status, geocoded_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)"""
        data = [
            (
                r.get("cnpj"),
                r.get("razao_social"),
                r.get("nome_fantasia"),
                r.get("cnae_principal"),
                r.get("cnae_secundaria"),
                r.get("endereco"),
                r.get("bairro"),
                r.get("cep"),
                r.get("uf"),
                r.get("municipio"),
                r.get("telefone_1"),
                r.get("email"),
                r.get("lat"),
                r.get("lng"),
                r.get("h3_r8_id"),
                r.get("h3_r9_id"),
                r.get("h3_id"),
                r.get("geocode_status"),
                r.get("geocoded_at"),
            )
            for r in rows
        ]
        if data:
            self._conn.executemany(sql, data)
            self._conn.commit()

    def upsert_empresas_alvo(self, rows: list[dict]) -> None:
        """Batch upsert into empresas_alvo (used by --sync-empresas).

        Note: the empresas_alvo DDL is added in Task 2. This method body
        follows the same pattern as upsert_empresas_geo.
        """
        sql = """INSERT OR REPLACE INTO empresas_alvo
            (cnpj, razao_social, nome_fantasia, cnae_principal, cnae_secundaria,
             endereco, bairro, cep, uf, municipio, telefone_1, email,
             porte, situacao_cadastral, data_abertura, capital_social, synced_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)"""
        data = [
            (
                r.get("cnpj"),
                r.get("razao_social"),
                r.get("nome_fantasia"),
                r.get("cnae_principal"),
                r.get("cnae_secundaria"),
                r.get("endereco"),
                r.get("bairro"),
                r.get("cep"),
                r.get("uf"),
                r.get("municipio"),
                r.get("telefone_1"),
                r.get("email"),
                r.get("porte"),
                r.get("situacao_cadastral"),
                r.get("data_abertura"),
                r.get("capital_social"),
                r.get("synced_at"),
            )
            for r in rows
        ]
        if data:
            self._conn.executemany(sql, data)
            self._conn.commit()

    # ------------------------------------------------------------------
    # Connection management
    # ------------------------------------------------------------------

    def close(self) -> None:
        """Close the SQLite connection."""
        self._conn.close()
