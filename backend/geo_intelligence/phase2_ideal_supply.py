"""
geo_intelligence/phase2_ideal_supply.py
========================================
Fase 2 do pipeline GeoIntelligence — Ideal Supply via CP-SAT.

Lógica idêntica ao backend/phase2_ideal_supply.py vanilla, adaptada para
receber `geo_territories` (output da Fase 1) no lugar de territories_index.json.

Requirements: 11.1, 11.2, 11.3, 11.4, 11.5, 11.6, 11.7, 11.8
"""

from __future__ import annotations

import logging
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import h3
from ortools.sat.python import cp_model

from geo_intelligence.geo_config import CP_SOLVER_TIME_LIMIT_S
from geo_intelligence.pipeline import SelectedTerritory

logger = logging.getLogger(__name__)

# Default capacity config (mirrors vanilla Config.RADII / MIN_CAP / MAX_CAP)
_DEFAULT_MIN_CAP = 20
_DEFAULT_MAX_CAP = 120
_DEFAULT_RADII = [
    {"radius_s": 500,  "hex_distance": 1, "penalty": 1},
    {"radius_s": 1000, "hex_distance": 2, "penalty": 2},
    {"radius_s": 1500, "hex_distance": 3, "penalty": 3},
    {"radius_s": 2000, "hex_distance": 4, "penalty": 4},
]


@dataclass
class GeoIdealSlot:
    slot_id: str
    station_code: str
    territory_id: str
    origin_hex: str
    radius_s: int
    capacity_s: int
    lat: float
    lon: float
    allocations: list = field(default_factory=list)
    is_optimal: bool = True
    solver_status: str = "optimal"
    matched_partner_id: Optional[str] = None


def _solve_territory_worker(payload: Dict) -> Tuple[str, List[Dict]]:
    """CP-SAT worker (top-level for pickle compatibility)."""
    territory_id = payload["territory_id"]
    station_code = payload["station_code"]
    hex_ids = payload["hex_ids"]
    demand_map = dict(payload["demand_map"])
    min_cap = payload["min_cap"]
    max_cap = payload["max_cap"]
    radii_config = payload["radii_config"]
    time_limit = payload.get("time_limit_s", CP_SOLVER_TIME_LIMIT_S)

    slots: List[Dict] = []
    seq = 0

    while True:
        active_hexes = [h for h in hex_ids if demand_map.get(h, 0) > 0]
        if not active_hexes:
            break

        best_seed = max(active_hexes, key=lambda h: demand_map[h])
        max_hex_dist = radii_config[-1]["hex_distance"]
        potential_vol = sum(
            demand_map[h] for h in hex_ids
            if demand_map.get(h, 0) > 0 and h3.grid_distance(h, best_seed) <= max_hex_dist
        )
        if potential_vol < min_cap:
            break

        model = cp_model.CpModel()
        r_active: Dict[int, cp_model.IntVar] = {}
        allocations: Dict[Tuple[int, str], cp_model.IntVar] = {}

        for i, r_conf in enumerate(radii_config):
            r_active[i] = model.NewBoolVar(f"r_{i}")
            in_radius = [
                h for h in hex_ids
                if demand_map.get(h, 0) > 0 and h3.grid_distance(h, best_seed) <= r_conf["hex_distance"]
            ]
            radius_load_vars = []
            for h in in_radius:
                var = model.NewIntVar(0, int(demand_map[h]), f"load_{i}_{h}")
                allocations[(i, h)] = var
                radius_load_vars.append(var)
            if radius_load_vars:
                total_r = sum(radius_load_vars)
                model.Add(total_r >= min_cap).OnlyEnforceIf(r_active[i])
                model.Add(total_r <= max_cap).OnlyEnforceIf(r_active[i])
                model.Add(total_r == 0).OnlyEnforceIf(r_active[i].Not())
            else:
                model.Add(r_active[i] == 0)

        model.Add(sum(r_active.values()) <= 1)
        obj_terms = []
        if allocations:
            obj_terms.append(sum(allocations.values()) * 100)
        for i, r_conf in enumerate(radii_config):
            obj_terms.append(r_active[i] * (-r_conf["penalty"]))
        if obj_terms:
            model.Maximize(sum(obj_terms))

        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = min(5, time_limit)
        status = solver.Solve(model)

        is_optimal = status == cp_model.OPTIMAL
        solver_status_str = "optimal" if is_optimal else ("feasible" if status == cp_model.FEASIBLE else "infeasible")

        if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            break

        chosen_radius_idx = next((i for i in r_active if solver.Value(r_active[i])), -1)
        if chosen_radius_idx == -1:
            break

        r_conf = radii_config[chosen_radius_idx]
        final_allocs = []
        total_assigned = 0
        for h in hex_ids:
            key = (chosen_radius_idx, h)
            if key not in allocations:
                continue
            val = solver.Value(allocations[key])
            if val > 0:
                final_allocs.append({"hex_id": h, "packages_assigned": int(val)})
                total_assigned += int(val)

        if not final_allocs:
            break

        seq += 1
        lat, lon = h3.cell_to_latlng(best_seed)
        slots.append({
            "slot_id": f"{territory_id}_S{seq:02d}",
            "station_code": station_code,
            "territory_id": territory_id,
            "origin_hex": best_seed,
            "radius_s": r_conf["radius_s"],
            "capacity_s": total_assigned,
            "lat": lat,
            "lon": lon,
            "allocations": final_allocs,
            "is_optimal": is_optimal,
            "solver_status": solver_status_str,
        })

        for a in final_allocs:
            demand_map[a["hex_id"]] = max(0, demand_map[a["hex_id"]] - a["packages_assigned"])

    return territory_id, slots


def _dict_to_ideal_slot(d: Dict) -> GeoIdealSlot:
    return GeoIdealSlot(
        slot_id=d["slot_id"],
        station_code=d["station_code"],
        territory_id=d["territory_id"],
        origin_hex=d["origin_hex"],
        radius_s=d["radius_s"],
        capacity_s=d["capacity_s"],
        lat=d["lat"],
        lon=d["lon"],
        allocations=d.get("allocations", []),
        is_optimal=d.get("is_optimal", True),
        solver_status=d.get("solver_status", "optimal"),
    )


def run_phase2(
    geo_territories: List[SelectedTerritory],
    demand_map: Dict[str, int],
    station_code: str,
    max_workers: int = 4,
    min_cap: int = _DEFAULT_MIN_CAP,
    max_cap: int = _DEFAULT_MAX_CAP,
    radii_config: Optional[List[Dict]] = None,
) -> Dict[str, List[GeoIdealSlot]]:
    """
    Runs Phase 2: Ideal Supply via CP-SAT.

    Parameters
    ----------
    geo_territories: output from Phase 1 (list of SelectedTerritory)
    demand_map: {h3_id: delivery_count}
    station_code: DS identifier
    max_workers: parallelism for CP-SAT solver

    Returns
    -------
    {territory_id: [GeoIdealSlot]}
    """
    radii = radii_config or _DEFAULT_RADII

    payloads: List[Dict] = []
    for territory in geo_territories:
        # Use h3_ids_r9 for CP-SAT (res 9 for precise slot positioning)
        # Fall back to h3_ids_r8 if r9 is empty (backward compatibility)
        hex_ids_for_solver = territory.h3_ids_r9 if territory.h3_ids_r9 else territory.h3_ids_r8
        territory_demand = {
            h: max(1, demand_map.get(h, 0))
            for h in hex_ids_for_solver
            if demand_map.get(h, 0) > 0
        }
        if not territory_demand:
            logger.warning("[Phase 2] Territory %s has no demand — skipping.", territory.territory_id)
            continue

        payloads.append({
            "territory_id": territory.territory_id,
            "station_code": station_code,
            "hex_ids": hex_ids_for_solver,
            "demand_map": territory_demand,
            "min_cap": min_cap,
            "max_cap": max_cap,
            "radii_config": radii,
            "time_limit_s": CP_SOLVER_TIME_LIMIT_S,
        })

    result: Dict[str, List[GeoIdealSlot]] = {}

    with ProcessPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(_solve_territory_worker, p): p["territory_id"] for p in payloads}
        for future in as_completed(futures):
            tid = futures[future]
            try:
                territory_id, slot_dicts = future.result()
                result[territory_id] = [_dict_to_ideal_slot(d) for d in slot_dicts]
                logger.info("[Phase 2] %s: %d slots generated.", territory_id, len(result[territory_id]))
            except Exception as exc:
                logger.error("[Phase 2] Solver failed for %s: %s", tid, exc)
                result[tid] = []

    # Ensure all territories have an entry
    for p in payloads:
        if p["territory_id"] not in result:
            result[p["territory_id"]] = []

    return result
