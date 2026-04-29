"""
phase3_partner_fit.py
=====================
Fase 3 — Matching de parceiros existentes com vagas ideais.

Responsabilidade
----------------
- Avaliar TODOS os prospects antes do matching principal:
    • Sem lat/lon → No Go | "Não avaliado por falta de coordenadas"
    • Com lat/lon + match em slot → Go | "Seguir cadastro"
    • Com lat/lon + sem match + dentro de polígono → No Go | "Sem oportunidade próxima"
    • Com lat/lon + sem match + fora de polígono → No Go | "Fora de jurisdição"
- Para cada vaga ideal (IdealSlot) gerada pela Fase 2, encontrar o melhor
  parceiro existente que possa supri-la, seguindo a hierarquia de status.
  Prospects com Go entram no pool normalmente.
- Atualizar ideal_supply.json com os matched_partner_id preenchidos.
- Retornar FitResult para consumo da Fase 5 (reports).

Hierarquia de status (menor numero = maior prioridade)
-------------------------------------------------------
    1 = Active
    2 = Onboarding
    3 = BG Checks
    4 = Prospect  (apenas os com Go da pré-avaliação)
    5 = Inactive / Exited - Regretted

Reasons canônicos para prospects
---------------------------------
    Go    → "Seguir cadastro"
    No Go → "Não avaliado por falta de coordenadas"
    No Go → "Sem oportunidade próxima"
    No Go → "Fora de jurisdição"
"""

from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

import h3

from shared.config import STATION_ALIASES
from shared.load_packages import PackageData
from shared.load_partners import PartnerData, row_to_partner_metrics
from shared.h3_cache import H3Cache
from shared.models import Allocation, Config, IdealSlot, PartnerMetrics, TerritoriesResult
from vanilla.phase2_ideal_supply import IdealSupplyResult, load_ideal_supply


# ---------------------------------------------------------------------------
# CACHE ESCOPADO DE CHAMADAS H3
# ---------------------------------------------------------------------------
# `_h3_cache` é instanciado por `run_phase3` dentro de um bloco `with H3Cache()`
# e descartado ao final da fase. Funções auxiliares deste módulo acessam o
# cache via `_get_h3_cache()`; quando chamadas fora do escopo da fase (ex.:
# testes unitários que exercitam helpers isolados), elas caem de volta para
# a biblioteca `h3` sem cache — comportamento funcionalmente idêntico.

_h3_cache: Optional[H3Cache] = None


def _get_h3_cache() -> Optional[H3Cache]:
    """Retorna o cache ativo da Phase 3, ou None se fora do escopo."""
    return _h3_cache


def _cached_grid_disk(cell: str, k: int = 1) -> Set[str]:
    """`h3.grid_disk` com cache escopado à Phase 3 (fallback para h3 direto)."""
    cache = _h3_cache
    if cache is not None:
        return set(cache.grid_disk(cell, k))
    return set(h3.grid_disk(cell, k))


def _cached_grid_distance(a: str, b: str) -> int:
    """`h3.grid_distance` com cache escopado à Phase 3 (fallback para h3 direto)."""
    cache = _h3_cache
    if cache is not None:
        return cache.grid_distance(a, b)
    return h3.grid_distance(a, b)


# ---------------------------------------------------------------------------
# HELPER — extrai índice numérico do territory_id (suporta ambos os formatos)
# ---------------------------------------------------------------------------

def _bucket_seq(territory_id: str) -> int:
    """
    Extrai o índice sequencial (0-based) de um territory_id.

    Suporta:
        "DSP2_bucket-01"  → 0
        "DSP2_bucket-1"   → 0   (legado sem zero-padding)
        "DSP2_T01"        → 0   (formato antigo)
    """
    for sep in ("_bucket-", "_T"):
        if sep in territory_id:
            try:
                return int(territory_id.split(sep)[-1]) - 1
            except (ValueError, IndexError):
                pass
    return 0


def _station_from_tid(territory_id: str) -> str:
    """Extrai o código da DS de um territory_id (ex: 'DSP2_bucket-01' → 'DSP2')."""
    for sep in ("_bucket-", "_T"):
        if sep in territory_id:
            return territory_id.split(sep)[0]
    return territory_id


# ---------------------------------------------------------------------------
# HIERARQUIA DE STATUS
# ---------------------------------------------------------------------------

STATUS_PRIORITY: Dict[str, int] = {
    "Active":    1,
    "Onboarding": 2,
    "BG Checks": 3,
    "Prospect":  4,
    "Inactive":  5,
    "Exited":    5,   # apenas "Exited - Regretted" chega aqui
}

# Grupos operacionais que sao carregados por station_code diretamente
OPERATIONAL_STATUSES = {"Active", "Onboarding", "BG Checks"}
# Grupos que precisam de identificacao de base via jurisdicao
JURISDICTION_STATUSES = {"Prospect"}
# Grupos reativacao (exigem decisao_status especifico para Exited)
REACTIVATION_STATUSES = {"Inactive"}


# ---------------------------------------------------------------------------
# OUTPUT DATACLASS
# ---------------------------------------------------------------------------

@dataclass
class TerritoryFit:
    """Resultado do matching para um territorio."""
    territory_id: str
    station_code: str
    bdm_cluster: str
    ctl_name: str

    # Vagas (vindas da Fase 2, com matched_partner_id ja preenchido)
    slots: List[IdealSlot] = field(default_factory=list)

    # Parceiros associados a este territorio (matched + excedentes)
    partners: List[PartnerMetrics] = field(default_factory=list)

    @property
    def total_slots(self) -> int:
        return len(self.slots)

    @property
    def filled_slots(self) -> int:
        return sum(1 for s in self.slots if not s.is_open)

    @property
    def open_slots(self) -> int:
        return sum(1 for s in self.slots if s.is_open)

    @property
    def attainment(self) -> float:
        active = sum(1 for p in self.partners if p.status == "Active")
        return (active / self.total_slots * 100) if self.total_slots > 0 else 0.0
    
    @property
    def accuracy(self) -> float:
        active = sum(1 for p in self.partners if p.status == "Active")
        return ((active / self.filled_slots) * 100) if self.filled_slots > 0 else 0.0

    def partners_by_status(self, status: str) -> List[PartnerMetrics]:
        return [p for p in self.partners if p.status == status]


@dataclass
class FitResult:
    """Output completo da Fase 3."""

    # territory_id -> TerritoryFit
    territories: Dict[str, TerritoryFit] = field(default_factory=dict)

    # Parceiros fora de qualquer jurisdicao conhecida (territory_id = "Out of Jurisdiction")
    outside_jurisdiction: List[PartnerMetrics] = field(default_factory=list)
    
    # Parceiros dentro de jurisdicao mas sem match em vaga (alocados a territory_id)
    unassigned_by_territory: Dict[str, List[PartnerMetrics]] = field(default_factory=dict)

    def fits_for_station(self, station_code: str) -> List[TerritoryFit]:
        return [f for f in self.territories.values()
                if f.station_code == station_code]

    def all_partners(self) -> List[PartnerMetrics]:
        """Retorna TODOS os parceiros: matched + unassigned + out of jurisdiction."""
        partners = [p for fit in self.territories.values() for p in fit.partners]
        partners += [p for ps in self.unassigned_by_territory.values() for p in ps]
        partners += self.outside_jurisdiction
        return partners

    def summary(self) -> Dict[str, dict]:
        """Sumario por base: {station_code: {slots, filled, open, attainment}}"""
        result: Dict[str, dict] = defaultdict(lambda: {
            "slots": 0, "filled": 0, "open": 0,
            "active": 0, "onboarding": 0, "bg": 0,
            "prospects": 0, "inactives": 0,
        })
        for fit in self.territories.values():
            s = fit.station_code
            result[s]["slots"]     += fit.total_slots
            result[s]["filled"]    += fit.filled_slots
            result[s]["open"]      += fit.open_slots
            result[s]["active"]    += len(fit.partners_by_status("Active"))
            result[s]["onboarding"]+= len(fit.partners_by_status("Onboarding"))
            result[s]["bg"]        += len(fit.partners_by_status("BG Checks"))
            result[s]["prospects"] += len(fit.partners_by_status("Prospect"))
            result[s]["inactives"] += len([p for p in fit.partners
                                           if p.status in ("Inactive", "Exited")])
        return dict(result)


# ---------------------------------------------------------------------------
# HELPERS DE MATCHING
# ---------------------------------------------------------------------------

def _partner_eligible_hexes(origin_hex: str) -> Set[str]:
    """Retorna o conjunto de hexes em grid_disk=1 ao redor do parceiro."""
    return _cached_grid_disk(origin_hex, 1)


def _build_hex_to_slots(
    slots: List[IdealSlot],
) -> Dict[str, List[IdealSlot]]:
    """
    Indice invertido: hex -> lista de slots cuja vizinhanca (grid_disk=1)
    inclui aquele hex.
    """
    index: Dict[str, List[IdealSlot]] = defaultdict(list)
    for slot in slots:
        for nb in _cached_grid_disk(slot.origin_hex, 1):
            index[nb].append(slot)
    return index


def _is_inside_any_polygon(
    lat: float,
    lon: float,
    territory_polys: Dict[str, object],
) -> bool:
    """Retorna True se o ponto (lat, lon) está dentro de qualquer polígono de território."""
    if not territory_polys:
        return False
    try:
        from shapely.geometry import Point
        pt = Point(lon, lat)
        return any(
            poly.contains(pt)
            for poly in territory_polys.values()
            if poly is not None
        )
    except Exception:
        return False


def _evaluate_all_prospects(
    partner_data: PartnerData,
    all_slots_global: List[IdealSlot],
    territory_polys: Dict[str, object],
) -> Dict[str, dict]:
    """
    Pré-avalia TODOS os prospects antes do matching principal.

    Retorna
    -------
    {salesforce_id: {"decision": str, "reason": str, "eligible": bool}}

    Regras
    ------
    1. Sem lat/lon → No Go | "Não avaliado por falta de coordenadas" | eligible=False
    2. Com lat/lon + origin_hex em grid_disk=1 de algum slot → Go | "Seguir cadastro" | eligible=True
    3. Com lat/lon + sem match + dentro de polígono → No Go | "Sem oportunidade próxima" | eligible=False
    4. Com lat/lon + sem match + fora de polígono → No Go | "Fora de jurisdição" | eligible=False
    """
    # Conjunto de todos os hexes cobertos por slots (grid_disk=1) — para lookup O(1)
    all_slot_neighbor_hexes: Set[str] = set()
    for slot in all_slots_global:
        all_slot_neighbor_hexes.update(_cached_grid_disk(slot.origin_hex, 1))

    result: Dict[str, dict] = {}

    # Prospects sem coords (no_coords_prospects_df)
    no_coords_df = partner_data.no_coords_prospects_df
    if not no_coords_df.empty:
        for _, row in no_coords_df.iterrows():
            sfid = str(row.get("salesforce_id", ""))
            result[sfid] = {
                "decision": "No Go",
                "reason":   "Não avaliado por falta de coordenadas",
                "eligible": False,
                "row":      row,
            }

    # Prospects com coords (partners_df filtrado por status=Prospect)
    prospects_df = partner_data.partners_df[
        partner_data.partners_df["status"] == "Prospect"
    ].copy()

    for _, row in prospects_df.iterrows():
        sfid       = str(row.get("salesforce_id", ""))
        origin_hex = str(row.get("origin_hex", ""))
        lat        = float(row.get("lat", 0) or 0)
        lon        = float(row.get("lon", 0) or 0)

        if origin_hex in all_slot_neighbor_hexes:
            # Tem match potencial com algum slot — entra no pool
            result[sfid] = {
                "decision": "Go",
                "reason":   "Seguir cadastro",
                "eligible": True,
                "row":      row,
            }
        elif _is_inside_any_polygon(lat, lon, territory_polys):
            result[sfid] = {
                "decision": "No Go",
                "reason":   "Sem oportunidade próxima",
                "eligible": False,
                "row":      row,
            }
        else:
            result[sfid] = {
                "decision": "No Go",
                "reason":   "Fora de jurisdição",
                "eligible": False,
                "row":      row,
            }

    return result


def _match_station(
    station_code: str,
    territories_meta: List[dict],
    supply: IdealSupplyResult,
    partner_data: PartnerData,
    pkg: PackageData,
    territory_polys: Dict[str, object] = None,
    prospect_eval: Dict[str, dict] = None,
) -> Tuple[Dict[str, TerritoryFit], Dict[str, List[PartnerMetrics]]]:
    """
    Executa o matching completo para uma base.

    Retorna
    -------
    (territory_fits, unassigned_by_territory)

    Prospects são incluídos no pool apenas se prospect_eval[sfid]["eligible"] == True.
    Prospects não elegíveis já têm decision/reason definidos pela pré-avaliação.
    """
    bdm_cluster = Config.get_bdm_cluster(station_code)
    prospect_eval = prospect_eval or {}

    # ── Coletar todos os slots da base ────────────────────────────────────
    all_slots: List[IdealSlot] = []
    for meta in territories_meta:
        all_slots.extend(supply.slots_for(meta["territory_id"]))
    all_slots.sort(key=lambda s: s.capacity_s, reverse=True)

    hex_to_slots = _build_hex_to_slots(all_slots)

    # ── Coletar parceiros candidatos ──────────────────────────────────────
    op_df = partner_data.partners_by_station(station_code)

    # Prospects elegíveis para esta base (origin_hex em grid_disk=1 de algum slot desta base)
    all_slot_neighbors: Set[str] = set()
    for slot in all_slots:
        all_slot_neighbors.update(_cached_grid_disk(slot.origin_hex, 1))

    eligible_prospect_sfids = {
        sfid for sfid, ev in prospect_eval.items()
        if ev["eligible"]
    }

    prospects_df = partner_data.partners_df[
        (partner_data.partners_df["status"] == "Prospect")
        & (partner_data.partners_df["salesforce_id"].isin(eligible_prospect_sfids))
        & (partner_data.partners_df["origin_hex"].isin(all_slot_neighbors))
    ].copy()

    inactive_df = partner_data.partners_df[
        (partner_data.partners_df["station_code"] == station_code)
        & (
            (partner_data.partners_df["status"] == "Inactive")
            | (
                (partner_data.partners_df["status"] == "Exited")
                & (partner_data.partners_df.get("decision_status", "") == "Exited - Regretted")
            )
        )
    ].copy()

    # ── Construir lista unificada de candidatos ───────────────────────────
    candidates: List[Tuple[int, str, str, object, str, str]] = []

    for _, row in op_df[op_df["status"].isin(OPERATIONAL_STATUSES)].iterrows():
        prio = STATUS_PRIORITY.get(str(row.get("status", "")), 99)
        candidates.append((prio, str(row.get("origin_hex", "")),
                           str(row.get("salesforce_id", "")),
                           row, "EXISTING", station_code))

    for _, row in prospects_df.iterrows():
        candidates.append((STATUS_PRIORITY["Prospect"],
                           str(row.get("origin_hex", "")),
                           str(row.get("salesforce_id", "")),
                           row, "PROSPECT", station_code))

    for _, row in inactive_df.iterrows():
        prio = STATUS_PRIORITY.get(str(row.get("status", "")), 5)
        candidates.append((prio, str(row.get("origin_hex", "")),
                           str(row.get("salesforce_id", "")),
                           row, "INACTIVE_EXITED", station_code))

    # ── Pré-computar território de cada candidato ─────────────────────────
    candidate_territory: Dict[str, str] = {}
    for prio, origin_hex, sfid, row, entity_type, p_station in candidates:
        p_lat = float(row.get("lat", 0) or 0)
        p_lon = float(row.get("lon", 0) or 0)
        tid = _get_territory_for_partner(
            origin_hex, territories_meta,
            lat=p_lat or None, lon=p_lon or None,
            territory_polys=territory_polys,
            partner_id=sfid,
        )
        if tid:
            candidate_territory[sfid] = tid

    # ── Matching greedy ───────────────────────────────────────────────────
    allocated_sids: Set[str] = set()
    allocated_slots: Set[str] = set()
    partner_results: List[PartnerMetrics] = []

    for slot in all_slots:
        if slot.slot_id in allocated_slots:
            continue

        slot_neighbors = _cached_grid_disk(slot.origin_hex, 1)
        eligible = [
            c for c in candidates
            if c[2] not in allocated_sids
            and c[1] in slot_neighbors
            and candidate_territory.get(c[2]) == slot.bucket_id
        ]

        if not eligible:
            continue

        eligible.sort(key=lambda c: (
            c[0],
            0 if c[1] == slot.origin_hex else 1,
            _cached_grid_distance(c[1], slot.origin_hex) if c[1] else 99,
        ))

        best = eligible[0]
        prio, origin_hex, sfid, row, entity_type, p_station = best

        status_str = str(row.get("status", ""))
        optDecision = "Optimization suggested" if status_str == "Active" else None

        pm = row_to_partner_metrics(
            row=row,
            entity_type=entity_type,
            station_code=p_station,
            decision="Go",
            radius_s=slot.radius_s,
            capacity_s=slot.capacity_s,
            optimization_decision=optDecision,
            allocations=[
                Allocation(hex_id=a.hex_id, packages_assigned=a.packages_assigned)
                for a in slot.allocations
            ],
        )
        pm.reason = "Seguir cadastro"
        pm.matched_slot_id = slot.slot_id

        territory_id = candidate_territory.get(sfid, slot.bucket_id)
        try:
            bucket_idx = _bucket_seq(territory_id)
        except (ValueError, IndexError):
            bucket_idx = 0
        pm.cluster_name = territory_id
        pm.bdm_cluster  = bdm_cluster
        pm.ctl_name     = f"CTL-{chr(65 + (bucket_idx // 5))}"

        partner_results.append(pm)
        allocated_sids.add(sfid)
        allocated_slots.add(slot.slot_id)
        slot.matched_partner_id = sfid

    # ── Parceiros não alocados (operacionais e inactives) ─────────────────
    for prio, origin_hex, sfid, row, entity_type, p_station in candidates:
        if sfid in allocated_sids:
            continue

        status_str = str(row.get("status", ""))

        if entity_type == "PROSPECT":
            # Prospect elegível mas sem slot disponível nesta base
            decision = "No Go"
            reason   = "Sem oportunidade próxima"
        elif status_str == "Active":
            decision = "Nao esta em uma localizacao ideal"
            reason   = ""
        elif status_str in ("Onboarding", "BG Checks"):
            decision = "Nao esta em uma localizacao ideal"
            reason   = ""
        elif entity_type == "INACTIVE_EXITED":
            decision = "Finalizar cadastro - Sem oportunidade proxima"
            reason   = ""
        else:
            decision = "Nao esta em uma localizacao ideal"
            reason   = ""

        pm = row_to_partner_metrics(
            row=row, entity_type=entity_type,
            station_code=p_station, decision=decision,
            radius_s=0, capacity_s=0,
        )
        pm.reason      = reason
        pm.bdm_cluster = bdm_cluster

        territory_id = candidate_territory.get(sfid)
        if territory_id:
            try:
                bucket_idx = _bucket_seq(territory_id)
            except (ValueError, IndexError):
                bucket_idx = 0
            pm.cluster_name = territory_id
            pm.ctl_name     = f"CTL-{chr(65 + (bucket_idx // 5))}"

        partner_results.append(pm)

    # ── Montar TerritoryFit ───────────────────────────────────────────────
    territory_fits: Dict[str, TerritoryFit] = {}
    unassigned_by_tid: Dict[str, List[PartnerMetrics]] = defaultdict(list)

    for meta in territories_meta:
        tid = meta["territory_id"]
        try:
            bucket_idx = _bucket_seq(tid)
        except (ValueError, IndexError):
            bucket_idx = 0
        ctl_name = f"CTL-{chr(65 + (bucket_idx // 5))}"

        t_slots    = supply.slots_for(tid)
        t_matched  = [p for p in partner_results if p.cluster_name == tid and p.matched_slot_id]
        t_unmatched = [p for p in partner_results if p.cluster_name == tid and not p.matched_slot_id]

        if t_unmatched:
            unassigned_by_tid[tid] = t_unmatched

        territory_fits[tid] = TerritoryFit(
            territory_id=tid,
            station_code=station_code,
            bdm_cluster=bdm_cluster,
            ctl_name=ctl_name,
            slots=t_slots,
            partners=t_matched,
        )

    return territory_fits, dict(unassigned_by_tid)


def _find_territory_for_hex(
    origin_hex: str,
    territories_meta: List[dict],
) -> Optional[str]:
    """Retorna o territory_id cujo hex_ids contem origin_hex, ou None."""
    for meta in territories_meta:
        if origin_hex in meta.get("hex_ids", []):
            return meta["territory_id"]
    return None


def _load_territory_polygons(output_dir: Path) -> Dict[str, object]:
    """
    Carrega os polígonos de território do territories.geojson como objetos Shapely.
    Retorna {territory_id: shapely_geometry} para uso nos fallbacks de point-in-polygon.
    """
    try:
        from shapely.geometry import shape
        geojson_path = output_dir / "territories.geojson"
        if not geojson_path.exists():
            return {}
        with open(geojson_path, "r", encoding="utf-8") as f:
            gj = json.load(f)
        polys: Dict[str, object] = {}
        for ft in gj.get("features", []):
            tid = ft.get("properties", {}).get("territory_id")
            if tid:
                try:
                    polys[tid] = shape(ft["geometry"])
                except Exception:
                    pass
        return polys
    except Exception:
        return {}


def _resolve_canonical_satellite_tiebreak(
    matches: List[dict],
    partner_id: str = "",
) -> Optional[str]:
    """
    Resolve a canonical↔satellite tiebreak deterministically.

    Given a list of match dicts (each with keys `territory_id` and `station_code`)
    collected from a step in `_get_territory_for_partner`, apply the majority +
    alphabetical rule **only** when the stations involved are exactly
    ``{C, S1, ..., Sn}`` where ``C`` is a canonical station and each ``Si`` is
    a satellite anchored to ``C`` via ``STATION_ALIASES[Si] == C``.

    When the rule applies:
    - Group matched territories by station_code.
    - Pick the station with the most matched territories (polygons).
    - On tie, pick ``min(tied_stations)`` alphabetically.
    - Within the winning station, return the first matching ``territory_id``
      (preserving the input ordering of ``matches``).
    - A warning is printed identifying the partner, the involved stations,
      and the chosen winner.

    Returns ``None`` when the rule does not apply (stations are unrelated,
    or fewer than two distinct stations are involved). The caller then falls
    back to its previous tiebreak (typically: use the first match).
    """
    if not matches or len(matches) < 2:
        return None

    # Group matches by station_code.
    by_station: Dict[str, List[dict]] = defaultdict(list)
    for m in matches:
        by_station[m["station_code"]].append(m)

    stations = set(by_station.keys())
    if len(stations) < 2:
        return None

    # Identify the canonical(s) and satellite(s) among the matched stations.
    canonicals = {s for s in stations if s not in STATION_ALIASES}
    satellites = {s for s in stations if s in STATION_ALIASES}

    # Rule applies only when exactly one canonical is present and every
    # satellite is anchored to that canonical.
    if len(canonicals) != 1 or not satellites:
        return None

    canonical = next(iter(canonicals))
    if not all(STATION_ALIASES.get(sat) == canonical for sat in satellites):
        return None

    # Majority vote by number of matched territories (polygons) per station.
    max_count = max(len(v) for v in by_station.values())
    tied = sorted(s for s, v in by_station.items() if len(v) == max_count)
    winner = tied[0]  # alphabetical tiebreak

    sat_matches = sorted(satellites)
    print(
        f"  WARN partner_fit: parceiro {partner_id} tem point-in-polygon em "
        f"canônica {canonical} e satélite(s) {sat_matches}; atribuído a "
        f"{winner} por majority+alphabetical"
    )

    # Within the winning station, keep the first matching territory by input order.
    return by_station[winner][0]["territory_id"]


def _get_territory_for_partner(
    origin_hex: str,
    territories_meta: List[dict],
    lat: float = None,
    lon: float = None,
    territory_polys: Dict[str, object] = None,
    partner_id: str = "",
) -> Optional[str]:
    """
    Encontra o territory_id mais apropriado para um parceiro.

    Hierarquia de fallbacks
    -----------------------
    1. Busca exata: hex_id do parceiro está em hex_ids do território
    2. Point-in-polygon: lat/lon do parceiro dentro do polígono do território
       (usa territories.geojson via Shapely — preciso na fronteira)
    3. Proximidade do centroide geométrico do polígono
       (usa centroide real do polígono Shapely)
    4. Proximidade do centroide calculado pelos slots
       (último recurso absoluto)
    """
    if not territories_meta:
        return None

    def _log(step: str, tid: str) -> str:
        if partner_id:
            print(f"  [territory_lookup] {partner_id} | hex={origin_hex} "
                  f"| step={step} → {tid}")
        return tid

    # 1. Busca exata por hex_id
    tid = _find_territory_for_hex(origin_hex, territories_meta)
    if tid:
        return _log("1-hex_exact", tid)

    # Resolver lat/lon se não fornecidos
    if lat is None or lon is None:
        try:
            lat, lon = h3.cell_to_latlng(origin_hex)
        except Exception:
            lat, lon = 0.0, 0.0

    # 2. Point-in-polygon usando polígonos reais do territories.geojson
    if territory_polys:
        try:
            from shapely.geometry import Point
            pt = Point(lon, lat)
            pip_matches: List[dict] = []
            for meta in territories_meta:
                tid = meta["territory_id"]
                poly = territory_polys.get(tid)
                if poly is not None:
                    try:
                        if poly.contains(pt):
                            pip_matches.append({
                                "territory_id": tid,
                                "station_code": _station_from_tid(tid),
                            })
                    except Exception:
                        pass
            if pip_matches:
                if len(pip_matches) == 1:
                    return _log("2-point_in_polygon", pip_matches[0]["territory_id"])
                # >1 matches: try canonical↔satellite majority+alphabetical rule.
                resolved = _resolve_canonical_satellite_tiebreak(
                    pip_matches, partner_id=partner_id,
                )
                if resolved is not None:
                    return _log("2-point_in_polygon", resolved)
                # Unrelated stations: preserve legacy behavior (first match).
                return _log("2-point_in_polygon", pip_matches[0]["territory_id"])
        except ImportError:
            pass

    # 3. Proximidade do centroide geométrico do polígono
    if territory_polys:
        import math

        # Compute all (tid, dist) pairs, then isolate the tied-min set.
        scored: List[Tuple[str, float]] = []
        for meta in territories_meta:
            tid = meta["territory_id"]
            poly = territory_polys.get(tid)
            if poly is not None:
                try:
                    c = poly.centroid
                    dist = (lat - c.y) ** 2 + (lon - c.x) ** 2
                    # Descartar NaN/Inf — quebram comparações e deixam `tied` vazio.
                    if math.isfinite(dist):
                        scored.append((tid, dist))
                except Exception:
                    pass
        if scored:
            min_dist = min(d for _, d in scored)
            tied = [tid for tid, d in scored if d == min_dist]
            # Safety guard: após filtrar NaN via math.isfinite, `tied` só
            # pode ficar vazia em cenários extremamente degenerados — caia
            # para o passo 4 (slot centroid) nesses casos.
            if tied:
                if len(tied) == 1:
                    return _log("3-poly_centroid", tied[0])
                # >1 centroids tied at min_dist: try canonical↔satellite rule.
                tied_matches = [
                    {"territory_id": tid, "station_code": _station_from_tid(tid)}
                    for tid in tied
                ]
                resolved = _resolve_canonical_satellite_tiebreak(
                    tied_matches, partner_id=partner_id,
                )
                if resolved is not None:
                    return _log("3-poly_centroid", resolved)
                # Unrelated stations: preserve legacy behavior (first tied match).
                return _log("3-poly_centroid", tied[0])

    # 4. Fallback final: centroide calculado pelos slots (campo do territory_index)
    min_tid = None
    min_dist = float("inf")
    for meta in territories_meta:
        cent_lat = meta.get("centroid_lat", 0)
        cent_lon = meta.get("centroid_lon", 0)
        dist = (lat - cent_lat) ** 2 + (lon - cent_lon) ** 2
        if dist < min_dist:
            min_dist = dist
            min_tid = meta["territory_id"]
    return _log("4-slot_centroid", min_tid) if min_tid else None



# ---------------------------------------------------------------------------
# ATUALIZACAO DO IDEAL_SUPPLY.JSON
# ---------------------------------------------------------------------------

def _update_supply_file(
    supply: IdealSupplyResult,
    output_dir: Path,
) -> None:
    """
    Re-serializa ideal_supply.json com matched_partner_id preenchido.
    Mantem estrutura identica — apenas atualiza o campo de cada slot.
    """
    path = output_dir / "ideal_supply.json"
    if not path.exists():
        return

    with open(path, "r", encoding="utf-8") as f:
        raw = json.load(f)

    # Indice rapido slot_id -> matched_partner_id
    slot_match: Dict[str, Optional[str]] = {
        s.slot_id: s.matched_partner_id
        for s in supply.all_slots
    }

    for tid, slot_list in raw.get("slots", {}).items():
        for slot_dict in slot_list:
            sid = slot_dict.get("slot_id")
            if sid in slot_match:
                slot_dict["matched_partner_id"] = slot_match[sid]

    raw["_metadata"]["last_fit_at"] = datetime.now().isoformat(timespec="seconds")

    with open(path, "w", encoding="utf-8") as f:
        json.dump(raw, f, ensure_ascii=False, indent=2)

    print(f"  ideal_supply.json atualizado com matched_partner_ids.")


# ---------------------------------------------------------------------------
# FUNCAO PRINCIPAL
# ---------------------------------------------------------------------------

def run_phase3(
    territories: TerritoriesResult,
    supply: IdealSupplyResult,
    partner_data: PartnerData,
    pkg: PackageData,
    output_dir: str = None,
    stations: Optional[List[str]] = None,
) -> FitResult:
    """
    Executa a Fase 3: matching de parceiros com vagas ideais.

    Fluxo
    -----
    1. Pré-avaliação de TODOS os prospects (com e sem coords).
    2. Matching por base usando apenas prospects elegíveis (Go).
    3. Prospects não elegíveis são adicionados ao FitResult com decision/reason já definidos.

    Performance
    -----------
    Um `H3Cache` é instanciado no início da fase e descartado ao final, de
    forma que chamadas repetidas a `grid_disk`/`grid_distance` com os mesmos
    argumentos são memoizadas. O cache NÃO persiste entre execuções do
    processo — ver `shared.h3_cache.H3Cache`.
    """
    global _h3_cache
    with H3Cache() as cache:
        _h3_cache = cache
        try:
            return _run_phase3_impl(
                territories=territories,
                supply=supply,
                partner_data=partner_data,
                pkg=pkg,
                output_dir=output_dir,
                stations=stations,
            )
        finally:
            import logging as _logging
            _logging.getLogger(__name__).debug(
                "[h3_cache stats] %s", cache.stats()
            )
            _h3_cache = None


def _run_phase3_impl(
    territories: TerritoriesResult,
    supply: IdealSupplyResult,
    partner_data: PartnerData,
    pkg: PackageData,
    output_dir: str = None,
    stations: Optional[List[str]] = None,
) -> FitResult:
    """Implementação interna de `run_phase3` — exige cache H3 ativo."""
    out_dir = Path(output_dir or Config.DEST_FOLDER)
    target_stations = stations or territories.stations

    print(f"\n{'='*60}")
    print(f"  FASE 3 — MATCHING PARCEIROS x VAGAS IDEAIS")
    print(f"  Hierarquia: Active > Onboarding > BG Checks > Prospect > Inactive")
    print(f"  Bases: {target_stations}")
    print(f"{'='*60}")

    territory_polys = _load_territory_polygons(out_dir)
    if territory_polys:
        print(f"  Polígonos carregados: {len(territory_polys)} territórios")

    # ── Pré-avaliação global de todos os prospects ────────────────────────
    all_slots_global = [s for s in supply.all_slots]
    prospect_eval = _evaluate_all_prospects(partner_data, all_slots_global, territory_polys)

    go_count   = sum(1 for ev in prospect_eval.values() if ev["eligible"])
    nogo_count = len(prospect_eval) - go_count
    print(f"\n  Pré-avaliação de prospects: {len(prospect_eval)} total | "
          f"{go_count} Go | {nogo_count} No Go")

    fit_result = FitResult()

    # ── Matching por base ─────────────────────────────────────────────────
    for station in target_stations:
        territories_meta = territories.territories_for(station)
        if not territories_meta:
            print(f"  WARN [{station}] Sem territorios — pulando.")
            continue

        n_slots_station = sum(
            len(supply.slots_for(m["territory_id"])) for m in territories_meta
        )
        print(f"\n  [{station}] {len(territories_meta)} territorios | "
              f"{n_slots_station} vagas ideais")

        territory_fits, unassigned = _match_station(
            station_code=station,
            territories_meta=territories_meta,
            supply=supply,
            partner_data=partner_data,
            pkg=pkg,
            territory_polys=territory_polys,
            prospect_eval=prospect_eval,
        )

        fit_result.territories.update(territory_fits)
        for tid, partners in unassigned.items():
            if tid not in fit_result.unassigned_by_territory:
                fit_result.unassigned_by_territory[tid] = []
            fit_result.unassigned_by_territory[tid].extend(partners)

        for fit in sorted(territory_fits.values(), key=lambda f: f.territory_id):
            active     = len(fit.partners_by_status("Active"))
            onboarding = len(fit.partners_by_status("Onboarding"))
            bg         = len(fit.partners_by_status("BG Checks"))
            prospects  = len(fit.partners_by_status("Prospect"))
            inactives  = len([p for p in fit.partners if p.status in ("Inactive", "Exited")])
            print(
                f"    {fit.territory_id}: "
                f"{fit.filled_slots}/{fit.total_slots} vagas | "
                f"Ativos={active} Onb={onboarding} BG={bg} "
                f"Prosp={prospects} Inat={inactives} | "
                f"Attainment={fit.attainment:.1f}% Accuracy={fit.accuracy:.1f}%"
            )

    _update_supply_file(supply, out_dir)

    # ── Adicionar prospects não elegíveis ao FitResult ────────────────────
    # Todos devem aparecer no optimization_data.geojson com decision/reason corretos.
    matched_sfids: Set[str] = {
        p.salesforce_id
        for p in fit_result.all_partners()
        if p.status == "Prospect"
    }

    for sfid, ev in prospect_eval.items():
        if sfid in matched_sfids:
            continue  # já está no FitResult como Go (matched)
        if ev["eligible"]:
            continue  # era elegível mas não foi matched — já tratado em _match_station

        row = ev["row"]
        pm = row_to_partner_metrics(
            row=row,
            entity_type="PROSPECT",
            station_code=str(row.get("station_code", "")),
            decision=ev["decision"],
            radius_s=0,
            capacity_s=0,
        )
        pm.reason = ev["reason"]

        # Calcular território via point-in-polygon (mesmo sem match de slot)
        origin_hex = str(row.get("origin_hex", ""))
        lat = float(row.get("lat", 0) or 0)
        lon = float(row.get("lon", 0) or 0)
        all_territories_meta = [
            meta
            for station in target_stations
            for meta in territories.territories_for(station)
        ]
        tid = _get_territory_for_partner(
            origin_hex, all_territories_meta,
            lat=lat or None, lon=lon or None,
            territory_polys=territory_polys,
            partner_id=sfid,
        )
        pm.cluster_name = tid or ""
        if tid:
            try:
                bucket_idx = _bucket_seq(tid)
            except (ValueError, IndexError):
                bucket_idx = 0
            pm.bdm_cluster = Config.get_bdm_cluster(_station_from_tid(tid))
            pm.ctl_name    = f"CTL-{chr(65 + (bucket_idx // 5))}"

        fit_result.outside_jurisdiction.append(pm)

    nogo_total = len(fit_result.outside_jurisdiction)
    print(f"\n  Prospects No Go adicionados ao relatório: {nogo_total}")

    # Sumario global
    summ = fit_result.summary()
    total_slots  = sum(v["slots"]  for v in summ.values())
    total_filled = sum(v["filled"] for v in summ.values())
    total_open   = sum(v["open"]   for v in summ.values())
    pct = (total_filled / total_slots * 100) if total_slots else 0

    print(f"\n{'='*60}")
    print(f"  FASE 3 CONCLUIDA")
    print(f"  {total_slots} vagas | {total_filled} preenchidas | "
          f"{total_open} em aberto | Attainment global: {pct:.1f}%")
    print(f"  {len(prospect_eval)} prospects avaliados: {go_count} Go | {nogo_count} No Go")
    print(f"{'='*60}\n")

    return fit_result
