"""
local_reader.py
===============
SQLite replacement for TursoReader. Reads all internal GeoIntelligence
pipeline state from a local SQLite file with TTL cache.
"""

from __future__ import annotations

import logging
import os
import sqlite3
import time
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_DEFAULT_DB_PATH = "output/geo_intelligence/geo_intelligence.db"


class LocalReader:
    """SQLite-backed reader for all internal GeoIntelligence pipeline tables.

    Implements the same public interface as TursoReader so call sites in
    geo_orchestrator.py can swap TursoReader → LocalReader with no other changes.
    """

    def __init__(self, db_path: str | None = None, cache_ttl_s: int = 300) -> None:
        """
        Opens (or creates) the SQLite database.

        db_path defaults to GEO_SQLITE_PATH env var,
        then to 'output/geo_intelligence/geo_intelligence.db'.

        Opens in read-write mode (file may not exist yet on first run —
        LocalWriter.ensure_schema() will be called before any reads in normal flow).
        """
        if db_path is None:
            db_path = os.environ.get("GEO_SQLITE_PATH", _DEFAULT_DB_PATH)
        self._db_path = db_path
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._cache: dict[str, tuple[float, Any]] = {}
        self._cache_ttl_s = cache_ttl_s

    # ------------------------------------------------------------------
    # TTL cache helpers
    # ------------------------------------------------------------------

    def _get_cached(self, key: str) -> Any:
        """Returns cached value if within TTL, else None."""
        entry = self._cache.get(key)
        if entry is None:
            return None
        ts, value = entry
        if time.monotonic() - ts > self._cache_ttl_s:
            del self._cache[key]
            return None
        return value

    def _set_cached(self, key: str, value: Any) -> None:
        """Stores value with current timestamp."""
        self._cache[key] = (time.monotonic(), value)

    # ------------------------------------------------------------------
    # Internal query helper
    # ------------------------------------------------------------------

    def _query(self, sql: str, params: list) -> list[dict]:
        """Execute a SELECT and return rows as list of dicts."""
        cur = self._conn.execute(sql, params)
        return [dict(row) for row in cur.fetchall()]

    # ------------------------------------------------------------------
    # Public API (mirrors TursoReader)
    # ------------------------------------------------------------------

    def get_latest_run_id(self, station_code: str) -> Optional[str]:
        """
        Returns the most recent run_id with status='setup_complete' for the station.
        Falls back to status='completed' for backward compatibility.
        Returns None if neither exists.
        """
        key = f"latest_run:{station_code}"
        cached = self._get_cached(key)
        if cached is not None:
            return cached

        # Prefer 'setup_complete' status; fall back to 'completed'
        rows = self._query(
            "SELECT run_id FROM geo_run_metadata "
            "WHERE station_code=? AND status='setup_complete' "
            "ORDER BY timestamp_start DESC LIMIT 1",
            [station_code],
        )
        if not rows:
            rows = self._query(
                "SELECT run_id FROM geo_run_metadata "
                "WHERE station_code=? AND status='completed' "
                "ORDER BY timestamp_start DESC LIMIT 1",
                [station_code],
            )

        run_id = rows[0]["run_id"] if rows else None
        self._set_cached(key, run_id)
        return run_id

    def get_territories(
        self,
        station_code: str,
        run_id: str,
        region_type: Optional[str] = None,
        min_gap: Optional[float] = None,
    ) -> List[Dict]:
        """SELECT * FROM geo_territories WHERE station_code=? AND run_id=?

        Optional filters:
            region_type: AND region_type=?
            min_gap:     AND gap >= ?
        """
        sql = "SELECT * FROM geo_territories WHERE station_code=? AND run_id=?"
        params: list = [station_code, run_id]
        if region_type is not None:
            sql += " AND region_type=?"
            params.append(region_type)
        if min_gap is not None:
            sql += " AND gap >= ?"
            params.append(min_gap)
        return self._query(sql, params)

    def get_h3_cells(self, territory_id: str, run_id: str) -> List[Dict]:
        """SELECT * FROM geo_h3_cells WHERE territory_id=? AND run_id=?"""
        return self._query(
            "SELECT * FROM geo_h3_cells WHERE territory_id=? AND run_id=?",
            [territory_id, run_id],
        )

    def get_h3_cells_for_station(self, station_code: str, run_id: str) -> List[Dict]:
        """SELECT * FROM geo_h3_cells WHERE station_code=? AND run_id=?"""
        return self._query(
            "SELECT * FROM geo_h3_cells WHERE station_code=? AND run_id=?",
            [station_code, run_id],
        )

    def get_scorecard(self, station_code: str, run_id: str) -> dict:
        """Returns {'ds': [...], 'bdm': [...]} from geo_scorecard."""
        rows = self._query(
            "SELECT * FROM geo_scorecard WHERE run_id=?",
            [run_id],
        )
        return {
            "ds": [r for r in rows if r.get("entity_type") == "ds" and r.get("entity_id") == station_code],
            "bdm": [r for r in rows if r.get("entity_type") == "bdm"],
        }

    def get_ideal_supply(self, station_code: str, run_id: str) -> List[Dict]:
        """SELECT * FROM geo_ideal_supply WHERE station_code=? AND run_id=?"""
        key = f"ideal_supply:{station_code}:{run_id}"
        cached = self._get_cached(key)
        if cached is not None:
            return cached
        rows = self._query(
            "SELECT * FROM geo_ideal_supply WHERE station_code=? AND run_id=?",
            [station_code, run_id],
        )
        self._set_cached(key, rows)
        return rows

    def get_cap_opportunities(
        self,
        station_code: str,
        run_id: Optional[str] = None,
        only_with_opportunity: bool = False,
    ) -> List[Dict]:
        """SELECT * FROM geo_partner_cap_opportunities WHERE station_code=?

        Optional filters:
            run_id:                AND run_id=?
            only_with_opportunity: AND estimated_adv_gain > 0
        """
        sql = "SELECT * FROM geo_partner_cap_opportunities WHERE station_code=?"
        params: list = [station_code]
        if run_id is not None:
            sql += " AND run_id=?"
            params.append(run_id)
        if only_with_opportunity:
            sql += " AND estimated_adv_gain > 0"
        return self._query(sql, params)

    def invalidate(self, key: Optional[str] = None) -> None:
        """Clears the in-memory TTL cache.

        If key is None: clear entire cache.
        Else: remove key from cache if present.
        """
        if key is None:
            self._cache.clear()
        else:
            self._cache.pop(key, None)

    def close(self) -> None:
        """Closes the SQLite connection."""
        self._conn.close()
