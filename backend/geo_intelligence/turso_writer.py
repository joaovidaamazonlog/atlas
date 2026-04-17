"""
turso_writer.py
===============
Persiste os outputs do pipeline GeoIntelligence no Turso via HTTP.
"""

from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone
from typing import Optional

from geo_intelligence.turso_http import TursoHTTP
from geo_intelligence.pipeline import GeoSetupConfig, H3CellFeatures, PartnerProfile, ReferenceProfiles, RunMetadata, TerritoryOutput

logger = logging.getLogger(__name__)

_BATCH_SIZE = 100
_MAX_RETRIES = 3
_BACKOFF_BASE_S = 1.0

_DDL_STATEMENTS = [
    """CREATE TABLE IF NOT EXISTS geo_territories (
        territory_id TEXT NOT NULL, station_code TEXT NOT NULL, run_id TEXT NOT NULL,
        region_type TEXT NOT NULL, potential_score REAL NOT NULL, current_partners INTEGER NOT NULL,
        ideal_slots INTEGER NOT NULL, gap REAL NOT NULL, model_confidence REAL NOT NULL,
        low_confidence INTEGER NOT NULL, high_opportunity INTEGER NOT NULL,
        geometry_geojson TEXT NOT NULL, h3_ids_json TEXT NOT NULL,
        attainment REAL, accuracy REAL, updated_at TEXT NOT NULL,
        PRIMARY KEY (territory_id, run_id))""",
    """CREATE TABLE IF NOT EXISTS geo_h3_cells (
        h3_id TEXT NOT NULL, territory_id TEXT NOT NULL, station_code TEXT NOT NULL, run_id TEXT NOT NULL,
        company_density REAL, cnae_diversity_index REAL, target_business_density REAL,
        building_density REAL, avg_building_size_m2 REAL, landuse_residential_ratio REAL,
        landuse_commercial_ratio REAL, poi_density REAL, road_connectivity_index REAL,
        avg_income REAL, population_density REAL, bars_restaurants_density REAL,
        churches_density REAL, schools_density REAL, dealerships_density REAL,
        petshops_density REAL, landuse_entropy REAL, road_centrality_index REAL,
        local_clustering_coefficient REAL, region_type TEXT, potential_score REAL, model_confidence REAL,
        PRIMARY KEY (h3_id, run_id))""",
    """CREATE TABLE IF NOT EXISTS geo_ideal_supply (
        supply_id TEXT NOT NULL, territory_id TEXT NOT NULL, station_code TEXT NOT NULL, run_id TEXT NOT NULL,
        lat REAL NOT NULL, lon REAL NOT NULL, radius_km REAL NOT NULL, capacity_day INTEGER NOT NULL,
        matched_partner_id TEXT, origin_hex TEXT,
        PRIMARY KEY (supply_id, run_id))""",
    """CREATE TABLE IF NOT EXISTS geo_scorecard (
        entity_id TEXT NOT NULL, entity_type TEXT NOT NULL, run_id TEXT NOT NULL,
        potential_score REAL NOT NULL, n_territories INTEGER, n_high_opportunity INTEGER,
        avg_gap REAL, coverage_pct REAL, updated_at TEXT NOT NULL,
        PRIMARY KEY (entity_id, entity_type, run_id))""",
    """CREATE TABLE IF NOT EXISTS geo_run_metadata (
        run_id TEXT PRIMARY KEY, station_code TEXT NOT NULL, expansion_target_pct REAL NOT NULL,
        timestamp_start TEXT NOT NULL, timestamp_end TEXT, n_h3_cells INTEGER, n_territories INTEGER,
        clustering_algorithm TEXT, silhouette_score REAL, supervised_model TEXT,
        supervised_f1_macro REAL, is_optimal INTEGER, solver_status TEXT, status TEXT NOT NULL)""",
    """CREATE TABLE IF NOT EXISTS geo_partner_profiles (
        id            INTEGER PRIMARY KEY AUTOINCREMENT,
        run_id        TEXT NOT NULL,
        station_code  TEXT NOT NULL,
        profile_type  TEXT NOT NULL,
        vector_json   TEXT NOT NULL,
        n_partners    INTEGER,
        avg_tenure_days REAL,
        profile_coverage REAL,
        low_coverage_warning INTEGER,
        is_global_fallback   INTEGER,
        created_at    TEXT NOT NULL
    )""",
    """CREATE TABLE IF NOT EXISTS geo_partner_history (
        salesforce_id        TEXT NOT NULL,
        station_code         TEXT NOT NULL,
        h3_id_r8             TEXT NOT NULL,
        status               TEXT NOT NULL,
        tenure_days          INTEGER,
        exit_reason_code     TEXT,
        exit_reason_class    TEXT,
        launch_date          TEXT,
        exited_date          TEXT,
        run_id               TEXT NOT NULL,
        PRIMARY KEY (salesforce_id, run_id)
    )""",
]

# ALTER TABLE statements for geo_run_metadata — SQLite does not support IF NOT EXISTS
# for ALTER TABLE, so we handle duplicate column errors gracefully in ensure_schema().
_ALTER_STATEMENTS = [
    "ALTER TABLE geo_run_metadata ADD COLUMN umap_params TEXT",
    "ALTER TABLE geo_run_metadata ADD COLUMN n_clusters INTEGER",
    "ALTER TABLE geo_run_metadata ADD COLUMN low_quality_clustering INTEGER",
    "ALTER TABLE geo_run_metadata ADD COLUMN profile_coverage REAL",
    "ALTER TABLE geo_ideal_supply ADD COLUMN origin_hex TEXT",
]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _chunks(lst: list, size: int):
    for i in range(0, len(lst), size):
        yield lst[i: i + size]


class TursoWriter:
    def __init__(self, url: str, auth_token: str) -> None:
        self._client = TursoHTTP(url=url, auth_token=auth_token)

    def ensure_schema(self) -> None:
        for ddl in _DDL_STATEMENTS:
            self._execute_with_retry(ddl, [])
        # ALTER TABLE statements — SQLite raises an error if the column already exists,
        # so we catch "duplicate column name" errors and continue gracefully.
        for alter in _ALTER_STATEMENTS:
            try:
                self._client.execute(alter, [])
            except Exception as exc:
                if "duplicate column name" in str(exc).lower():
                    logger.debug("Coluna já existe (ignorado): %s", alter)
                else:
                    logger.warning("ALTER TABLE falhou: %s | erro: %s", alter, exc)
        logger.info("Schema geo_* verificado/criado.")

    def upsert_run(self, run_id: str, config: GeoSetupConfig) -> None:
        self._execute_with_retry(
            """INSERT INTO geo_run_metadata (run_id, station_code, expansion_target_pct, timestamp_start, status)
               VALUES (?, ?, ?, ?, 'running')
               ON CONFLICT(run_id) DO UPDATE SET status='running', timestamp_start=excluded.timestamp_start""",
            [run_id, config.station_code, config.expansion_target_pct, _now_iso()],
        )

    def finalize_run(self, run_id: str, metadata: RunMetadata) -> None:
        umap_params_json = json.dumps(metadata.umap_params) if metadata.umap_params is not None else None
        self._execute_with_retry(
            """UPDATE geo_run_metadata SET timestamp_end=?, n_h3_cells=?, n_territories=?,
               clustering_algorithm=?, silhouette_score=?, supervised_model=?,
               supervised_f1_macro=?, is_optimal=?, solver_status=?, status=?,
               umap_params=?, n_clusters=?, low_quality_clustering=?, profile_coverage=?
               WHERE run_id=?""",
            [metadata.timestamp_end, metadata.n_h3_cells, metadata.n_territories,
             metadata.clustering_algorithm, metadata.silhouette_score, metadata.supervised_model,
             metadata.supervised_f1_macro,
             int(metadata.is_optimal) if metadata.is_optimal is not None else None,
             metadata.solver_status, metadata.status,
             umap_params_json, metadata.n_clusters,
             int(metadata.low_quality_clustering) if metadata.low_quality_clustering is not None else None,
             metadata.profile_coverage,
             run_id],
        )

    def _mark_run_failed(self, run_id: str) -> None:
        try:
            self._client.execute("UPDATE geo_run_metadata SET status='failed' WHERE run_id=?", [run_id])
        except Exception:
            pass

    def upsert_territories(self, run_id: str, territories: list[TerritoryOutput], station_code: str) -> None:
        sql = """INSERT INTO geo_territories
            (territory_id, station_code, run_id, region_type, potential_score, current_partners,
             ideal_slots, gap, model_confidence, low_confidence, high_opportunity,
             geometry_geojson, h3_ids_json, attainment, accuracy, updated_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(territory_id, run_id) DO UPDATE SET
            potential_score=excluded.potential_score, gap=excluded.gap,
            model_confidence=excluded.model_confidence, updated_at=excluded.updated_at"""
        now = _now_iso()
        for batch in _chunks(territories, _BATCH_SIZE):
            stmts = []
            for t in batch:
                stmts.append((sql, [
                    t.territory_id, station_code, run_id,
                    t.region_type.value if hasattr(t.region_type, "value") else t.region_type,
                    t.potential_score, t.current_partners, t.ideal_slots, t.gap,
                    t.model_confidence, int(t.low_confidence), int(t.high_opportunity),
                    json.dumps(t.geometry), json.dumps(t.h3_ids),
                    getattr(t, "attainment", None), getattr(t, "accuracy", None), now,
                ]))
            self._execute_batch_with_retry(stmts, run_id)
        logger.info("Upsert de %d territórios (run=%s).", len(territories), run_id)

    def upsert_h3_cells(self, run_id: str, cells: list[H3CellFeatures], territory_id: str, station_code: str) -> None:
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
            ON CONFLICT(h3_id, run_id) DO UPDATE SET potential_score=excluded.potential_score"""
        for batch in _chunks(cells, _BATCH_SIZE):
            stmts = []
            for c in batch:
                rt = None
                if hasattr(c, "region_type") and c.region_type is not None:
                    rt = c.region_type.value if hasattr(c.region_type, "value") else c.region_type
                stmts.append((sql, [
                    c.h3_id, territory_id, station_code, run_id,
                    c.company_density, c.cnae_diversity_index, c.target_business_density,
                    c.building_density, c.avg_building_size_m2, c.landuse_residential_ratio,
                    c.landuse_commercial_ratio, c.poi_density, c.road_connectivity_index,
                    c.avg_income, c.population_density, c.bars_restaurants_density,
                    c.churches_density, c.schools_density, c.dealerships_density,
                    c.petshops_density, c.landuse_entropy, c.road_centrality_index,
                    c.local_clustering_coefficient, rt,
                    getattr(c, "potential_score", None), getattr(c, "model_confidence", None),
                ]))
            self._execute_batch_with_retry(stmts, run_id)

    def upsert_ideal_supply(self, run_id: str, supply_points: list[dict]) -> None:
        sql = """INSERT INTO geo_ideal_supply (supply_id, territory_id, station_code, run_id, lat, lon, radius_km, capacity_day, origin_hex)
                 VALUES (?,?,?,?,?,?,?,?,?)
                 ON CONFLICT(supply_id, run_id) DO UPDATE SET lat=excluded.lat, lon=excluded.lon, origin_hex=excluded.origin_hex"""
        stmts = [(sql, [sp["supply_id"], sp["territory_id"], sp["station_code"], run_id,
                         sp["lat"], sp["lon"], sp["radius_km"], sp["capacity_day"],
                         sp.get("origin_hex")])
                 for sp in supply_points]
        if stmts:
            self._execute_batch_with_retry(stmts, run_id)

    def upsert_scorecard(self, run_id: str, scorecard_rows: list[dict]) -> None:
        sql = """INSERT INTO geo_scorecard (entity_id, entity_type, run_id, potential_score,
                 n_territories, n_high_opportunity, avg_gap, coverage_pct, updated_at)
                 VALUES (?,?,?,?,?,?,?,?,?)
                 ON CONFLICT(entity_id, entity_type, run_id) DO UPDATE SET potential_score=excluded.potential_score"""
        now = _now_iso()
        stmts = [(sql, [r["entity_id"], r["entity_type"], run_id, r["potential_score"],
                         r.get("n_territories"), r.get("n_high_opportunity"),
                         r.get("avg_gap"), r.get("coverage_pct"), now])
                 for r in scorecard_rows]
        if stmts:
            self._execute_batch_with_retry(stmts, run_id)

    def update_supply_match(self, run_id: str, matches) -> None:
        """Atualiza matched_partner_id nos slots após o daily.

        Aceita dois formatos:
        - list[dict]: [{"supply_id": str, "partner_id": str}]
        - dict[str, str]: {slot_id: partner_id}
        """
        if isinstance(matches, dict):
            matches_list = [{"supply_id": k, "partner_id": v} for k, v in matches.items()]
        else:
            matches_list = matches
        sql = "UPDATE geo_ideal_supply SET matched_partner_id=? WHERE supply_id=? AND run_id=?"
        stmts = [(sql, [m["partner_id"], m["supply_id"], run_id]) for m in matches_list]
        if stmts:
            self._execute_batch_with_retry(stmts, run_id)
        logger.info("update_supply_match: %d slots atualizados (run=%s).", len(stmts), run_id)

    def update_territory_fit(self, run_id: str, fits) -> None:
        """Atualiza attainment e accuracy por território após o daily.

        Aceita dois formatos:
        - list[dict]: [{"territory_id": str, "attainment": float, "accuracy": float}]
        - dict[str, dict]: {territory_id: {"attainment": float, "accuracy": float}}
        """
        if isinstance(fits, dict):
            fits_list = [{"territory_id": k, **v} for k, v in fits.items()]
        else:
            fits_list = fits
        sql = "UPDATE geo_territories SET attainment=?, accuracy=?, updated_at=? WHERE territory_id=? AND run_id=?"
        now = _now_iso()
        stmts = [(sql, [f["attainment"], f["accuracy"], now, f["territory_id"], run_id]) for f in fits_list]
        if stmts:
            self._execute_batch_with_retry(stmts, run_id)
        logger.info("update_territory_fit: %d territórios atualizados (run=%s).", len(stmts), run_id)

    def upsert_partner_profiles(self, run_id: str, station_code: str, profiles: ReferenceProfiles) -> None:
        """Persiste success e failure vectors como JSON em geo_partner_profiles."""
        sql = """INSERT INTO geo_partner_profiles
            (run_id, station_code, profile_type, vector_json, n_partners, avg_tenure_days,
             profile_coverage, low_coverage_warning, is_global_fallback, created_at)
            VALUES (?,?,?,?,?,?,?,?,?,?)"""
        now = _now_iso()
        stmts = []
        for profile_type, vector, n_partners in [
            ("success", profiles.success_vector, profiles.n_active),
            ("failure", profiles.failure_vector, profiles.n_exited_area),
        ]:
            # Convert numpy arrays to plain Python lists for JSON serialisation
            if vector is not None and hasattr(vector, "tolist"):
                vec_list = vector.tolist()
            elif vector is not None:
                vec_list = list(vector)
            else:
                vec_list = []
            stmts.append((sql, [
                run_id, station_code, profile_type,
                json.dumps(vec_list),
                n_partners,
                profiles.avg_tenure_active if profile_type == "success" else None,
                profiles.profile_coverage,
                int(profiles.low_coverage_warning),
                int(profiles.is_global_fallback),
                now,
            ]))
        self._execute_batch_with_retry(stmts, run_id)
        logger.info("upsert_partner_profiles: success+failure persistidos (run=%s, station=%s).", run_id, station_code)

    def upsert_partner_history(self, run_id: str, partner_profiles: list[PartnerProfile]) -> None:
        """Persiste histórico de parceiros em geo_partner_history."""
        sql = """INSERT INTO geo_partner_history
            (salesforce_id, station_code, h3_id_r8, status, tenure_days,
             exit_reason_code, exit_reason_class, launch_date, exited_date, run_id)
            VALUES (?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(salesforce_id, run_id) DO UPDATE SET
            status=excluded.status, tenure_days=excluded.tenure_days,
            exit_reason_code=excluded.exit_reason_code,
            exit_reason_class=excluded.exit_reason_class,
            launch_date=excluded.launch_date,
            exited_date=excluded.exited_date"""
        # Derive station_code from the profile if available, else use empty string
        for batch in _chunks(partner_profiles, _BATCH_SIZE):
            stmts = []
            for p in batch:
                station = getattr(p, "station_code", "") or ""
                exit_code = getattr(p, "exit_reason_code", None)
                launch = getattr(p, "launch_date", None)
                exited = getattr(p, "exited_date", None)
                stmts.append((sql, [
                    p.salesforce_id, station, p.h3_id_r8, p.status,
                    p.tenure_days, exit_code, p.exit_reason_class,
                    launch, exited, run_id,
                ]))
            self._execute_batch_with_retry(stmts, run_id)
        logger.info("upsert_partner_history: %d parceiros persistidos (run=%s).", len(partner_profiles), run_id)

    def _execute_with_retry(self, sql: str, args: list, run_id: Optional[str] = None) -> None:
        last_exc = None
        for attempt in range(1, _MAX_RETRIES + 1):
            try:
                self._client.execute(sql, args)
                return
            except Exception as exc:
                last_exc = exc
                wait = _BACKOFF_BASE_S * (2 ** (attempt - 1))
                logger.warning("Tentativa %d/%d falhou: %s | SQL: %s | args: %s", attempt, _MAX_RETRIES, exc, sql[:80], str(args)[:200])
                if attempt < _MAX_RETRIES:
                    time.sleep(wait)
        if run_id:
            self._mark_run_failed(run_id)
        raise RuntimeError(f"TursoWriter: falha após {_MAX_RETRIES} tentativas. Último erro: {last_exc}") from last_exc

    def _execute_batch_with_retry(self, stmts: list[tuple], run_id: Optional[str] = None) -> None:
        last_exc = None
        for attempt in range(1, _MAX_RETRIES + 1):
            try:
                self._client.execute_many(stmts)
                return
            except Exception as exc:
                last_exc = exc
                wait = _BACKOFF_BASE_S * (2 ** (attempt - 1))
                logger.warning("Batch tentativa %d/%d falhou: %s.", attempt, _MAX_RETRIES, exc)
                if attempt < _MAX_RETRIES:
                    time.sleep(wait)
        if run_id:
            self._mark_run_failed(run_id)
        raise RuntimeError(f"TursoWriter: falha batch após {_MAX_RETRIES} tentativas.") from last_exc
