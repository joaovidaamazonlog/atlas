"""
turso_reader.py
===============
Leitura dos dados GeoIntelligence do Turso via HTTP com cache TTL 5 min.
"""

from __future__ import annotations

import logging
import time
from typing import Optional

from geo_intelligence.turso_http import TursoHTTP

logger = logging.getLogger(__name__)

_DEFAULT_TTL_S = 300


class TursoReader:
    def __init__(self, url: str, auth_token: str, cache_ttl_s: int = _DEFAULT_TTL_S) -> None:
        self._client = TursoHTTP(url=url, auth_token=auth_token)
        self._cache_ttl_s = cache_ttl_s
        self._cache: dict[str, tuple[float, object]] = {}

    def _cache_get(self, key: str) -> tuple[bool, object]:
        entry = self._cache.get(key)
        if entry is None:
            return False, None
        ts, value = entry
        if time.monotonic() - ts > self._cache_ttl_s:
            del self._cache[key]
            return False, None
        return True, value

    def _cache_set(self, key: str, value: object) -> None:
        self._cache[key] = (time.monotonic(), value)

    def invalidate(self, key: Optional[str] = None) -> None:
        if key is None:
            self._cache.clear()
        else:
            self._cache.pop(key, None)

    def _query(self, sql: str, params: list) -> list[dict]:
        return self._client.execute(sql, params)

    def get_latest_run_id(self, station_code: str) -> Optional[str]:
        key = f"latest_run_id:{station_code}"
        hit, cached = self._cache_get(key)
        if hit:
            return cached
        # Prefer 'setup_complete' status (Requirement 9.5); fall back to 'completed' for backward compatibility
        rows = self._query(
            "SELECT run_id FROM geo_run_metadata WHERE station_code=? AND status='setup_complete' ORDER BY timestamp_start DESC LIMIT 1",
            [station_code],
        )
        if not rows:
            rows = self._query(
                "SELECT run_id FROM geo_run_metadata WHERE station_code=? AND status='completed' ORDER BY timestamp_start DESC LIMIT 1",
                [station_code],
            )
        run_id = rows[0]["run_id"] if rows else None
        self._cache_set(key, run_id)
        return run_id

    def get_territories(self, station_code: str, run_id: str,
                        region_type: Optional[str] = None, min_gap: Optional[float] = None) -> list[dict]:
        key = f"territories:{station_code}:{run_id}:{region_type}:{min_gap}"
        hit, cached = self._cache_get(key)
        if hit:
            return cached
        sql = "SELECT * FROM geo_territories WHERE station_code=? AND run_id=?"
        params: list = [station_code, run_id]
        if region_type is not None:
            sql += " AND region_type=?"
            params.append(region_type)
        if min_gap is not None:
            sql += " AND gap>=?"
            params.append(min_gap)
        rows = self._query(sql, params)
        self._cache_set(key, rows)
        return rows

    def get_h3_cells(self, territory_id: str, run_id: str) -> list[dict]:
        key = f"h3_cells:{territory_id}:{run_id}"
        hit, cached = self._cache_get(key)
        if hit:
            return cached
        rows = self._query("SELECT * FROM geo_h3_cells WHERE territory_id=? AND run_id=?", [territory_id, run_id])
        self._cache_set(key, rows)
        return rows

    def get_scorecard(self, station_code: str, run_id: str) -> dict:
        key = f"scorecard:{station_code}:{run_id}"
        hit, cached = self._cache_get(key)
        if hit:
            return cached
        rows = self._query("SELECT * FROM geo_scorecard WHERE run_id=?", [run_id])
        result = {
            "ds": [r for r in rows if r.get("entity_type") == "ds" and r.get("entity_id") == station_code],
            "bdm": [r for r in rows if r.get("entity_type") == "bdm"],
        }
        self._cache_set(key, result)
        return result

    def get_ideal_supply(self, station_code: str, run_id: str) -> list[dict]:
        key = f"ideal_supply:{station_code}:{run_id}"
        hit, cached = self._cache_get(key)
        if hit:
            return cached
        rows = self._query("SELECT * FROM geo_ideal_supply WHERE station_code=? AND run_id=?", [station_code, run_id])
        self._cache_set(key, rows)
        return rows
