"""
cnpj_enricher.py
================
Enriquece H3_Cells com features econômicas a partir do banco de empresas
(CNPJ + Google Maps) hospedado no Turso via HTTP.

Requirements: 1.2, 2.1, 2.4
"""

from __future__ import annotations

import logging
import math
from collections import Counter
from typing import Optional

logger = logging.getLogger(__name__)

H3_RES9_AREA_KM2: float = 0.1052

TARGET_CNAES: frozenset[str] = frozenset({
    "4930201", "4930202", "5320201", "5320202", "5310501", "5310502",
    "5229001", "5229002", "5212500", "5211701", "5211702", "5211799",
})

_BARS_RESTAURANTS_CNAES: frozenset[str] = frozenset({
    "5611201", "5611202", "5611203", "5612100", "5620101", "5620102",
})
_CHURCHES_CNAES: frozenset[str] = frozenset({"9491000"})
_SCHOOLS_CNAES: frozenset[str] = frozenset({
    "8511200", "8512100", "8513900", "8520100", "8531700", "8532500",
    "8533300", "8541400", "8542200", "8591100", "8593700", "8599601",
})
_DEALERSHIPS_CNAES: frozenset[str] = frozenset({
    "4511101", "4511102", "4512901", "4512902", "4541201", "4541202",
    "4541203", "4541204", "4541206", "4541207",
})
_PETSHOPS_CNAES: frozenset[str] = frozenset({"4789004", "7500100"})

_NULL_FEATURES: dict[str, None] = {
    "company_density": None, "cnae_diversity_index": None,
    "target_business_density": None, "bars_restaurants_density": None,
    "churches_density": None, "schools_density": None,
    "dealerships_density": None, "petshops_density": None,
}


def _null_result(h3_ids: list[str]) -> dict[str, dict]:
    return {h3_id: dict(_NULL_FEATURES) for h3_id in h3_ids}


def _normalized_shannon(counts: Counter) -> float:
    n = len(counts)
    if n <= 1:
        return 0.0
    total = sum(counts.values())
    if total == 0:
        return 0.0
    entropy = -sum((c / total) * math.log2(c / total) for c in counts.values() if c > 0)
    return entropy / math.log2(n)


def _density(count: int) -> float:
    return count / H3_RES9_AREA_KM2


class CnpjEnricher:
    H3_RES9_AREA_KM2 = H3_RES9_AREA_KM2
    TARGET_CNAES = TARGET_CNAES

    def __init__(self, url: str, auth_token: str) -> None:
        self._url = url
        self._auth_token = auth_token
        self._client = None
        self._has_pois_table: Optional[bool] = None

    def _get_client(self):
        if self._client is None:
            from geo_intelligence.turso_http import TursoHTTP
            self._client = TursoHTTP(url=self._url, auth_token=self._auth_token)
        return self._client

    def get_features_for_h3_cells(self, h3_ids: list[str]) -> dict[str, dict]:
        """Returns {h3_id: {feature_name: value}} for all requested cells."""
        if not h3_ids:
            return {}
        try:
            client = self._get_client()
            # Verifica qual tabela usar: empresas_geo (com h3_id) ou fallback
            tables = client.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name IN ('empresas_geo','empresas')"
            )
            table_names = {r["name"] for r in tables}

            if "empresas_geo" in table_names:
                placeholders = ",".join("?" * len(h3_ids))
                rows = client.execute(
                    f"SELECT h3_r8_id AS h3_id, cnae_principal as cnae_code FROM empresas_geo "
                    f"WHERE h3_r8_id IN ({placeholders}) AND h3_r8_id IS NOT NULL",
                    h3_ids,
                )
            elif "empresas" in table_names:
                placeholders = ",".join("?" * len(h3_ids))
                rows = client.execute(
                    f"SELECT h3_id, cnae_code FROM empresas WHERE h3_id IN ({placeholders})",
                    h3_ids,
                )
            else:
                logger.warning(
                    "CnpjEnricher: nenhuma tabela de empresas encontrada no Turso. "
                    "Execute: python -m geo_intelligence.etl_geocode_empresas --uf SP"
                )
                return _null_result(h3_ids)
        except Exception as exc:
            logger.error("CnpjEnricher: Turso falhou — %s. Retornando None.", exc)
            return _null_result(h3_ids)

        # Group by h3_id
        cell_rows: dict[str, list[dict]] = {h: [] for h in h3_ids}
        for row in rows:
            h = row.get("h3_id")
            if h in cell_rows:
                cell_rows[h].append(row)

        # Try POIs table
        pois_by_cell: dict[str, list[dict]] = {}
        try:
            client = self._get_client()
            if self._has_pois_table is None:
                check = client.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name='google_maps_pois'"
                )
                self._has_pois_table = len(check) > 0
            if self._has_pois_table:
                placeholders = ",".join("?" * len(h3_ids))
                # google_maps_pois usa h3_id no nível r8
                poi_rows = client.execute(
                    f"SELECT h3_id, place_type FROM google_maps_pois WHERE h3_id IN ({placeholders})",
                    h3_ids,
                )
                for row in poi_rows:
                    h = row.get("h3_id")
                    if h in pois_by_cell:
                        pois_by_cell[h].append(row)
                    else:
                        pois_by_cell[h] = [row]
        except Exception as exc:
            logger.warning("CnpjEnricher: google_maps_pois falhou — %s.", exc)

        # gmaps_leads como fonte adicional de POIs (h3_r8_id)
        try:
            client = self._get_client()
            placeholders = ",".join("?" * len(h3_ids))
            gmaps_rows = client.execute(
                f"SELECT h3_r8_id AS h3_id, tipo AS place_type FROM gmaps_leads "
                f"WHERE h3_r8_id IN ({placeholders}) AND h3_r8_id IS NOT NULL",
                h3_ids,
            )
            for row in gmaps_rows:
                h = row.get("h3_id")
                if h in pois_by_cell:
                    pois_by_cell[h].append(row)
                else:
                    pois_by_cell[h] = [row]
        except Exception as exc:
            logger.warning("CnpjEnricher: gmaps_leads falhou — %s.", exc)

        return {h: self._compute(cell_rows.get(h, []), pois_by_cell.get(h, [])) for h in h3_ids}

    def _compute(self, empresa_rows: list[dict], poi_rows: list[dict]) -> dict:
        total = len(empresa_rows)
        cnae_counts = Counter(r.get("cnae_code") for r in empresa_rows if r.get("cnae_code"))
        target_count = sum(1 for r in empresa_rows if r.get("cnae_code") in TARGET_CNAES)

        if poi_rows:
            bars = sum(1 for p in poi_rows if p.get("place_type") in {
                "bar", "restaurant", "cafe", "food", "lanchonete",
                "açaí e sorveteria", "disk agua e gas",
            })
            churches = sum(1 for p in poi_rows if p.get("place_type") in {"church", "place_of_worship"})
            schools = sum(1 for p in poi_rows if p.get("place_type") in {"school", "university"})
            dealers = sum(1 for p in poi_rows if p.get("place_type") in {"car_dealer", "car_repair"})
            pets = sum(1 for p in poi_rows if p.get("place_type") in {"pet_store", "veterinary_care"})
        else:
            bars = sum(1 for r in empresa_rows if r.get("cnae_code") in _BARS_RESTAURANTS_CNAES)
            churches = sum(1 for r in empresa_rows if r.get("cnae_code") in _CHURCHES_CNAES)
            schools = sum(1 for r in empresa_rows if r.get("cnae_code") in _SCHOOLS_CNAES)
            dealers = sum(1 for r in empresa_rows if r.get("cnae_code") in _DEALERSHIPS_CNAES)
            pets = sum(1 for r in empresa_rows if r.get("cnae_code") in _PETSHOPS_CNAES)

        return {
            "company_density": _density(total),
            "cnae_diversity_index": _normalized_shannon(cnae_counts),
            "target_business_density": _density(target_count),
            "bars_restaurants_density": _density(bars),
            "churches_density": _density(churches),
            "schools_density": _density(schools),
            "dealerships_density": _density(dealers),
            "petshops_density": _density(pets),
        }
