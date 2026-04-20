"""
geo_intelligence/geo_daily.py
==============================
Modo daily do pipeline GeoIntelligence.

Recebe parceiros reais (via load_partners), carrega os slots ideais do Turso
(run mais recente por base) e executa o matching com a mesma hierarquia de
fallback do pipeline vanilla (phase3_partner_fit.py):

  1. Busca exata: origin_hex do parceiro está em hex_ids do território
  2. Point-in-polygon: lat/lon dentro do polígono (territories.geojson via Shapely)
  3. Proximidade do centroide geométrico do polígono
  4. Proximidade do centroide calculado pelos slots (territories_index.json)

Hierarquia de status para matching:
  Active (1) > Onboarding (2) > BG Checks (3) > Prospect (4) > Inactive/Exited (5)

Outputs persistidos no Turso via TursoWriter:
  - geo_ideal_supply.matched_partner_id  (update_supply_match)
  - geo_territories.attainment + accuracy (update_territory_fit)
"""

from __future__ import annotations

import json
import logging
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

import h3

logger = logging.getLogger(__name__)

STATUS_PRIORITY: Dict[str, int] = {
    "Active": 1,
    "Onboarding": 2,
    "BG Checks": 3,
    "Prospect": 4,
    "Inactive": 5,
    "Exited": 5,
}

CANONICAL_REASONS = {
    "go": "Seguir cadastro",
    "no_coords": "Não avaliado por falta de coordenadas",
    "no_opportunity": "Sem oportunidade próxima",
    "out_of_jurisdiction": "Fora de jurisdição",
}


# ---------------------------------------------------------------------------
# Dataclasses de resultado
# ---------------------------------------------------------------------------

@dataclass
class GeoPartnerMatch:
    partner_id: str
    status: str
    origin_hex: str
    lat: float
    lon: float
    matched_slot_id: Optional[str]
    territory_id: Optional[str]
    decision: str
    reason: str
    radius: int = 1500
    capacity: int = 42


@dataclass
class GeoTerritoryResult:
    territory_id: str
    station_code: str
    total_slots: int
    filled_slots: int
    active_partners: int

    @property
    def attainment(self) -> float:
        return (self.active_partners / self.total_slots * 100) if self.total_slots else 0.0

    @property
    def accuracy(self) -> float:
        return (self.filled_slots / self.total_slots * 100) if self.total_slots else 0.0


@dataclass
class GeoDailyResult:
    station_code: str
    run_id: str
    territories: Dict[str, GeoTerritoryResult] = field(default_factory=dict)
    matched: List[GeoPartnerMatch] = field(default_factory=list)
    unmatched: List[GeoPartnerMatch] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Territory lookup — mesma hierarquia do vanilla
# ---------------------------------------------------------------------------

def _load_territory_polygons(territories_geojson_path: str) -> Dict[str, object]:
    """Carrega polígonos Shapely por territory_id do territories.geojson."""
    try:
        from shapely.geometry import shape
        with open(territories_geojson_path, encoding="utf-8") as f:
            fc = json.load(f)
        polys = {}
        for feat in fc.get("features", []):
            tid = feat.get("properties", {}).get("territory_id")
            if tid:
                try:
                    polys[tid] = shape(feat["geometry"])
                except Exception:
                    pass
        return polys
    except Exception as exc:
        logger.warning("Não foi possível carregar territories.geojson: %s", exc)
        return {}


def _get_territory_for_partner(
    origin_hex: str,
    lat: float,
    lon: float,
    territory_h3_ids: Dict[str, List[str]],
    territory_polys: Dict[str, object],
    territories_meta: List[dict],
    partner_id: str = "",
) -> Optional[str]:
    """
    Hierarquia de fallback idêntica ao vanilla phase3_partner_fit:
      1. Busca exata por hex_id
      2. Point-in-polygon (Shapely)
      3. Centroide geométrico do polígono
      4. Centroide calculado pelos slots (territories_index)
    """
    def _log(step: str, tid: str) -> str:
        logger.debug("[territory_lookup] %s | hex=%s | step=%s → %s", partner_id, origin_hex, step, tid)
        return tid

    # 1. Busca exata
    for tid, h3_ids in territory_h3_ids.items():
        if origin_hex in h3_ids:
            return _log("1-hex_exact", tid)

    # Resolve lat/lon se não fornecidos
    if not lat or not lon:
        try:
            lat, lon = h3.cell_to_latlng(origin_hex)
        except Exception:
            lat, lon = 0.0, 0.0

    # 2. Point-in-polygon
    if territory_polys:
        try:
            from shapely.geometry import Point
            pt = Point(lon, lat)
            for tid, poly in territory_polys.items():
                try:
                    if poly.contains(pt):
                        return _log("2-point_in_polygon", tid)
                except Exception:
                    pass
        except ImportError:
            pass

    # 3. Centroide geométrico do polígono
    if territory_polys:
        min_tid, min_dist = None, float("inf")
        for tid, poly in territory_polys.items():
            try:
                c = poly.centroid
                dist = (lat - c.y) ** 2 + (lon - c.x) ** 2
                if dist < min_dist:
                    min_dist, min_tid = dist, tid
            except Exception:
                pass
        if min_tid:
            return _log("3-poly_centroid", min_tid)

    # 4. Centroide dos slots (territories_index)
    min_tid, min_dist = None, float("inf")
    for meta in territories_meta:
        clat = meta.get("centroid_lat", 0)
        clon = meta.get("centroid_lon", 0)
        dist = (lat - clat) ** 2 + (lon - clon) ** 2
        if dist < min_dist:
            min_dist, min_tid = dist, meta["territory_id"]
    return _log("4-slot_centroid", min_tid) if min_tid else None


# ---------------------------------------------------------------------------
# Core matching
# ---------------------------------------------------------------------------

def _build_hex_to_slots(slots: List[dict]) -> Dict[str, List[dict]]:
    """Mapeia hex vizinhos (grid_disk=1) → slots disponíveis."""
    index: Dict[str, List[dict]] = defaultdict(list)
    for slot in slots:
        origin = slot.get("origin_hex") or slot.get("supply_id", "")[:15]
        if not origin:
            continue
        try:
            for nb in h3.grid_disk(origin, 1):
                index[nb].append(slot)
        except Exception:
            pass
    return index


def run_daily(
    station_code: str,
    run_id: str,
    partner_data,                        # PartnerData from load_partners()
    slots: List[dict],                   # rows from geo_ideal_supply (Turso)
    territories_geojson_path: str,
    territories_index: Dict[str, dict],  # {territory_id: {hex_ids, centroid_lat, centroid_lon, ...}}
) -> GeoDailyResult:
    """
    Executa o matching diário GeoIntelligence.

    Parameters
    ----------
    station_code      : código da base (ex: 'DSP2')
    run_id            : run_id do setup mais recente (do Turso)
    partner_data      : PartnerData de load_partners()
    slots             : lista de dicts com supply_id, origin_hex, lat, lon, territory_id
    territories_geojson_path : caminho para territories.geojson
    territories_index : dict carregado do territories_index.json

    Returns
    -------
    GeoDailyResult com matched/unmatched e métricas por território
    """
    result = GeoDailyResult(station_code=station_code, run_id=run_id)

    # Carrega polígonos para point-in-polygon
    territory_polys = _load_territory_polygons(territories_geojson_path)

    # Filtra territórios desta base
    station_territories = {
        tid: meta for tid, meta in territories_index.items()
        if meta.get("station_code") == station_code
    }
    territory_h3_ids: Dict[str, List[str]] = {
        tid: meta.get("hex_ids", []) for tid, meta in station_territories.items()
    }
    territories_meta = [
        {"territory_id": tid, **meta} for tid, meta in station_territories.items()
    ]

    # Filtra slots desta base
    station_slots = [s for s in slots if s.get("station_code") == station_code]
    if not station_slots:
        logger.warning("[GeoDaily] Nenhum slot encontrado para %s (run=%s).", station_code, run_id)
        return result

    # Índice hex → slots
    hex_to_slots = _build_hex_to_slots(station_slots)
    available_slots: Dict[str, dict] = {s["supply_id"]: s for s in station_slots}

    # Parceiros desta base, ordenados por prioridade
    partners_df = partner_data.partners_by_station(station_code)
    if partners_df.empty:
        logger.info("[GeoDaily] Nenhum parceiro para %s.", station_code)
        return result

    candidates: List[Tuple[int, dict]] = []
    for _, row in partners_df.iterrows():
        status = str(row.get("status", ""))
        prio = STATUS_PRIORITY.get(status, 99)
        candidates.append((prio, row.to_dict()))
    candidates.sort(key=lambda x: x[0])

    # Pré-avalia prospects
    all_slot_neighbors: Set[str] = set()
    all_territory_hexes: Set[str] = set()
    for slot in station_slots:
        origin = slot.get("origin_hex", "")
        if origin:
            try:
                all_slot_neighbors.update(h3.grid_disk(origin, 1))
            except Exception:
                pass
    for h3_ids in territory_h3_ids.values():
        all_territory_hexes.update(h3_ids)

    def _prospect_eligible(origin_hex: str) -> Tuple[bool, str, str]:
        if not origin_hex:
            return False, "No Go", CANONICAL_REASONS["no_coords"]
        if origin_hex in all_slot_neighbors:
            return True, "Go", CANONICAL_REASONS["go"]
        if origin_hex in all_territory_hexes:
            return False, "No Go", CANONICAL_REASONS["no_opportunity"]
        return False, "No Go", CANONICAL_REASONS["out_of_jurisdiction"]

    # Greedy matching
    allocated_partners: Set[str] = set()
    allocated_slots: Set[str] = set()

    for prio, partner in candidates:
        pid = str(partner.get("salesforce_id") or partner.get("partner_id") or "")
        status = str(partner.get("status", ""))
        origin_hex = str(partner.get("origin_hex") or "")
        lat = float(partner.get("lat") or 0)
        lon = float(partner.get("lon") or 0)
        radius = int(partner.get("radius") or partner.get("radius_s") or 1500)
        capacity = int(partner.get("capacity") or partner.get("capacity_s") or 42)

        if pid in allocated_partners:
            continue

        # Filtra prospects inelegíveis
        if status == "Prospect":
            eligible, decision, reason = _prospect_eligible(origin_hex)
            if not eligible:
                result.unmatched.append(GeoPartnerMatch(
                    partner_id=pid, status=status, origin_hex=origin_hex,
                    lat=lat, lon=lon, matched_slot_id=None,
                    territory_id=None, decision=decision, reason=reason,
                    radius=radius, capacity=capacity,
                ))
                continue

        # Busca slots disponíveis no raio
        candidate_slots = [
            s for s in hex_to_slots.get(origin_hex, [])
            if s["supply_id"] not in allocated_slots
        ]
        if not candidate_slots:
            # Sem slot disponível — determina território para o unmatched
            tid = _get_territory_for_partner(
                origin_hex, lat, lon,
                territory_h3_ids, territory_polys, territories_meta, pid,
            )
            result.unmatched.append(GeoPartnerMatch(
                partner_id=pid, status=status, origin_hex=origin_hex,
                lat=lat, lon=lon, matched_slot_id=None,
                territory_id=tid, decision="No Go", reason=CANONICAL_REASONS["no_opportunity"],
                radius=radius, capacity=capacity,
            ))
            continue

        # Escolhe slot mais próximo
        def _dist(s: dict) -> int:
            try:
                return h3.grid_distance(origin_hex, s.get("origin_hex", origin_hex))
            except Exception:
                return 99

        best_slot = min(candidate_slots, key=_dist)

        # Determina território
        tid = _get_territory_for_partner(
            origin_hex, lat, lon,
            territory_h3_ids, territory_polys, territories_meta, pid,
        ) or best_slot.get("territory_id")

        result.matched.append(GeoPartnerMatch(
            partner_id=pid, status=status, origin_hex=origin_hex,
            lat=lat, lon=lon,
            matched_slot_id=best_slot["supply_id"],
            territory_id=tid,
            decision="Go", reason=CANONICAL_REASONS["go"],
            radius=radius, capacity=capacity,
        ))
        allocated_partners.add(pid)
        allocated_slots.add(best_slot["supply_id"])

    # Calcula métricas por território
    slots_by_territory: Dict[str, List[dict]] = defaultdict(list)
    for s in station_slots:
        slots_by_territory[s.get("territory_id", "")].append(s)

    matched_by_territory: Dict[str, List[GeoPartnerMatch]] = defaultdict(list)
    for m in result.matched:
        if m.territory_id:
            matched_by_territory[m.territory_id].append(m)

    for tid, t_slots in slots_by_territory.items():
        t_matched = matched_by_territory.get(tid, [])
        active_count = sum(1 for m in t_matched if m.status == "Active")
        filled_count = len(t_matched)
        result.territories[tid] = GeoTerritoryResult(
            territory_id=tid,
            station_code=station_code,
            total_slots=len(t_slots),
            filled_slots=filled_count,
            active_partners=active_count,
        )

    logger.info(
        "[GeoDaily] %s | matched=%d unmatched=%d territórios=%d",
        station_code, len(result.matched), len(result.unmatched), len(result.territories),
    )
    return result
