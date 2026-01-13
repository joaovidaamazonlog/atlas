import json
import math
import h3
import pandas as pd
import numpy as np
import config
import traceback
from pathlib import Path
from copy import deepcopy
from datetime import datetime, timezone
from typing import Dict, List
from collections import defaultdict, deque
from sklearn.cluster import DBSCAN
from ortools.sat.python import cp_model

# =====================================================
# CONFIGURAÇÕES GLOBAIS (100% INTEIRO)
# =====================================================
H3_RESOLUTION = 9

# Conversão aproximada raio (m) → distância em hex (inteiro)
RADII = [
    {"radius_m": 200, "hex_distance": 1},
    {"radius_m": 500, "hex_distance": 3},
    {"radius_m": 800, "hex_distance": 5},
    {"radius_m": 1100, "hex_distance": 7},
    {"radius_m": 1500, "hex_distance": 9}
]
    

CAPACITIES = [45, 55, 70]
MIN_CAPACITY = 45
MAX_CAPACITY = 70

# =====================================================
# MODELOS
# =====================================================
class Partner:
    __slots__ = ("id", "lat", "lon", "origin_hex")

    def __init__(self, partner_id: str, lat: float, lon: float):
        self.id = partner_id
        self.lat = lat
        self.lon = lon
        self.origin_hex = h3.latlng_to_cell(lat, lon, H3_RESOLUTION)

# =====================================================
# INGESTÃO DE DADOS
# =====================================================
class DataIngestion:

    @staticmethod
    def load_packages(csv_path: str) -> Dict[str, int]:
        df = pd.read_csv(csv_path, usecols=["latitude", "longitude", "plan_date"])
        df["plan_date"] = pd.to_datetime(df["plan_date"])
        days = df["plan_date"].nunique()

        df["hex"] = [
            h3.latlng_to_cell(lat, lon, H3_RESOLUTION)
            for lat, lon in zip(df.latitude, df.longitude)
        ]

        # demanda média diária, inteira (scaled externamente se necessário)
        daily = df.groupby("hex").size() // days
        return daily.to_dict()

    @staticmethod
    def load_partners(json_path: str) -> List[Partner]:
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        df = pd.DataFrame(data["allMarkerData"])
        df = df[(df["status"] == "Active") & df["lat"].notnull()]

        return [
            Partner(r.store_id, float(r.lat), float(r.lon))
            for _, r in df.iterrows()
        ]

# =====================================================
# FASE A — OTIMIZAÇÃO DE PARCEIROS EXISTENTES
# =====================================================
class ExistingPartnerOptimizer:

    def __init__(self, partner: Partner, hex_demand: Dict[str, int]):
        self.partner = partner
        self.hex_demand = hex_demand

    def solve(self):
        model = cp_model.CpModel()

        total_demand = sum(self.hex_demand.values())
        max_slots = math.ceil(total_demand / MIN_CAPACITY)

        x = {}
        y = {}

        for s in range(max_slots):
            x[s] = model.NewBoolVar(f"x_{s}")

        for h in self.hex_demand:
            for s in range(max_slots):
                y[(h, s)] = model.NewBoolVar(f"y_{h}_{s}")

        # capacidade por slot
        for s in range(max_slots):
            model.Add(
                sum(self.hex_demand[h] * y[(h, s)] for h in self.hex_demand)
                <= MAX_CAPACITY * x[s]
            )

        # cada hex no máximo uma vez
        for h in self.hex_demand:
            model.Add(
                sum(y[(h, s)] for s in range(max_slots)) <= 1
            )

        # objetivo
        model.Maximize(
            1_000_000 * sum(self.hex_demand[h] * y[(h, s)]
                            for h in self.hex_demand for s in range(max_slots))
            - 10_000 * sum(x[s] for s in range(max_slots))
        )

        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = 3
        solver.Solve(model)

        allocations = {}
        for h in self.hex_demand:
            for s in range(max_slots):
                if solver.Value(y[(h, s)]):
                    allocations[h] = self.hex_demand[h]

        return {
            "entity": "PARTNER",
            "partner_id": self.partner.id,
            "origin_hex": self.partner.origin_hex,
            "allocations": allocations,
            "total_assigned": sum(allocations.values()),
            "slots_used": sum(solver.Value(x[s]) for s in range(max_slots))
        }

# =====================================================
# FASE B — CLUSTERIZAÇÃO DE GAPS (DBSCAN)
# =====================================================
def cluster_hexes(hex_demand_residual, min_cluster_demand=MIN_CAPACITY):
    # hex com demanda residual
    active_hexes = {
        h for h, d in hex_demand_residual.items() if d > 0
    }

    visited = set()
    clusters = []

    for start_hex in active_hexes:
        if start_hex in visited:
            continue

        # BFS para formar cluster
        cluster = set()
        queue = deque([start_hex])
        cluster_demand = 0

        while queue:
            current = queue.popleft()
            if current in visited:
                continue

            visited.add(current)

            demand = hex_demand_residual.get(current, 0)
            if demand <= 0:
                continue

            cluster.add(current)
            cluster_demand += demand

            # vizinhança H3 — raio 1 é suficiente para conectividade
            neighbors = h3.grid_disk(current, 1)

            for n in neighbors:
                if n in active_hexes and n not in visited:
                    queue.append(n)

        # só mantém cluster economicamente viável
        if cluster_demand >= min_cluster_demand:
            clusters.append(list(cluster))

    return clusters

# =====================================================
# FASE B — NOVOS PARCEIROS (CP-SAT)
# =====================================================
class CapacityExpansionOptimizer:
    
    def __init__(
        self,
        cluster_hexes,
        hex_demand_residual,
        max_partners=10
    ):
        self.cluster = cluster_hexes
        self.demand = {
            h: int(hex_demand_residual[h])
            for h in cluster_hexes
            if hex_demand_residual[h] > 0
        }
        self.max_partners = max_partners

        self.model = cp_model.CpModel()

        self.x = {}
        self.y = {}

    def solve(self):
        H = list(self.demand.keys())
        C = H[:]  # centros candidatos
        S = range(self.max_partners)
        R = RADII     # (radius_m, radius_hex)
        K = CAPACITIES                   # [45..70]

        # -------------------------
        # Variáveis
        # -------------------------
        for c in C:
            for s in S:
                for r in R:
                    r_m = int(r["radius_m"])
                    r_hex = int(r["hex_distance"])
                    for k in K:
                        self.x[(c, s, r_m, k)] = self.model.NewBoolVar(
                            f"x_{c}{s}{r_m}_{k}"
                        )

        for h in H:
            for c in C:
                dist = h3.grid_distance(h, c)
                for s in S:
                    for r in R:
                        r_m = int(r["radius_m"])
                        r_hex = int(r["hex_distance"])
                        if dist <= int(r_hex):
                            for k in K:
                                self.y[(h, c, s, r_m, k)] = self.model.NewBoolVar(
                                    f"y_{h}{c}{s}{r_m}{k}"
                                )

        # -------------------------
        # Restrições
        # -------------------------

        # Capacidade máxima do parceiro
        for c in C:
            for s in S:
                for r_m, r_hex in R:
                    for k in K:
                        self.model.Add(
                            sum(
                                self.demand[h] * self.y[h, c, s, r_m, k]
                                for h in H
                                if (h, c, s, r_m, k) in self.y
                            ) <= k * self.x[c, s, r_m, k]
                        )

        # Capacidade mínima operacional
        for c in C:
            for s in S:
                for r_m, r_hex in R:
                    for k in K:
                        self.model.Add(
                            sum(
                                self.demand[h] * self.y[h, c, s, r_m, k]
                                for h in H
                                if (h, c, s, r_m, k) in self.y
                            ) >= MIN_CAPACITY * self.x[c, s, r_m, k]
                        )

        # Alocação só se parceiro existir
        for key in self.y:
            h, c, s, r_m, k = key
            self.model.Add(self.y[key] <= self.x[c, s, r_m, k])

        # 🔥 OVERLAP PERMITIDO — limite pela demanda residual
        for h in H:
            self.model.Add(
                sum(
                    self.demand[h] * self.y[key]
                    for key in self.y
                    if key[0] == h
                ) <= self.demand[h]
            )

        # Um parceiro por slot
        for c in C:
            for s in S:
                self.model.Add(
                    sum(
                        self.x[c, s, r_m, k]
                        for r_m, r_hex in R
                        for k in K
                    ) <= 1
                )

        # -------------------------
        # Função Objetivo
        # -------------------------
        radius_penalty = {200: 1, 500: 2, 800: 3, 1100: 4, 1500: 5}

        self.model.Maximize(
            sum(
                self.demand[h] * self.y[key]
                for key in self.y
                for h in [key[0]]
            )
            - 10 * sum(self.x.values())
            - sum(
                radius_penalty[r_m] * self.x[c, s, r_m, k]
                for (c, s, r_m, k) in self.x
            )
        )

        # -------------------------
        # Solve
        # -------------------------
        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = 10
        solver.parameters.num_search_workers = 8

        status = solver.Solve(self.model)

        if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            return []

        # -------------------------
        # Extração da solução
        # -------------------------
        results = []

        for (c, s, r_m, k), var in self.x.items():
            if solver.Value(var) == 1:
                alloc = {}
                total = 0
                for h in H:
                    key = (h, c, s, r_m, k)
                    if key in self.y and solver.Value(self.y[key]) == 1:
                        alloc[h] = self.demand[h]
                        total += self.demand[h]

                results.append({
                    "entity": "NEW_PARTNER",
                    "origin_hex": c,
                    "radius_m": r_m,
                    "radius_hex": r_hex,
                    "capacity": k,
                    "total_assigned": total,
                    "allocations": alloc
                })

        return results

# =====================================================
# ORQUESTRADOR
# =====================================================
def optimize_existing_partner(
    partner: Partner,
    hex_demand_residual: Dict[str, int],
    max_capacity: int = MAX_CAPACITY
) -> dict:
    """
    Otimiza alocação para um parceiro EXISTENTE.
    Retorna a melhor alocação possível com o menor raio.
    """

    best_solution = {
        "radius_hex": None,
        "radius_m": None,
        "allocations": {},
        "total_assigned": 0
    }

    # percorre raios crescentes
    for r in RADII:
        radius_m = r["radius_m"]
        radius_hex = r["hex_distance"]
        covered_hexes = [
            h for h in h3.grid_disk(partner.origin_hex, radius_hex)
            if hex_demand_residual.get(h, 0) > 0
        ]

        if not covered_hexes:
            continue

        # ordena por maior demanda primeiro
        covered_hexes.sort(
            key=lambda h: hex_demand_residual[h],
            reverse=True
        )

        allocations = {}
        total = 0

        for h in covered_hexes:
            d = hex_demand_residual[h]
            if total + d > max_capacity:
                continue
            allocations[h] = d
            total += d
            if total >= max_capacity:
                break

        # atualiza melhor solução
        if total > best_solution["total_assigned"]:
            best_solution = {
                "radius_hex": radius_hex,
                "radius_m": radius_m,
                "allocations": allocations,
                "total_assigned": total
            }
        
        if total == max_capacity:
            break
        
        if best_solution["total_assigned"] == 0:
            return None

    if best_solution["total_assigned"] == 0:
        return None

    return {
        "entity": "PARTNER",
        "partner_id": partner.id,
        "origin_hex": partner.origin_hex,
        "radius_hex": best_solution["radius_hex"],
        "radius_m": best_solution["radius_m"],
        "capacity": max_capacity,
        "allocations": best_solution["allocations"],
        "total_assigned": best_solution["total_assigned"]
    }

class OptimizationHub:

    def __init__(self, pkg_csv: str, partner_json: str):
        self.hex_demand_original = DataIngestion.load_packages(pkg_csv)
        self.hex_demand_residual = dict(self.hex_demand_original)
        self.partners = DataIngestion.load_partners(partner_json)

    def run(self):
        snapshot_before = deepcopy(self.hex_demand_original)

        # -------------------------
        # FASE A — parceiros ativos
        # -------------------------
        existing_results = []

        for p in self.partners:
            res = optimize_existing_partner(
                p,
                self.hex_demand_residual
            )
            if res:
                existing_results.append(res)
                for h, d in res["allocations"].items():
                    self.hex_demand_residual[h] -= d

        # -------------------------
        # FASE B — expansão
        # -------------------------
        new_partners = []

        clusters = cluster_hexes(self.hex_demand_residual)
        print(f"Identified {len(clusters)} clusters for capacity expansion with residual demand:{sum(self.hex_demand_residual.values())}")

        for cluster in clusters:
            optimizer = CapacityExpansionOptimizer(
                cluster,
                self.hex_demand_residual,
                max_partners=10
            )
            results = optimizer.solve()

            for r in results:
                new_partners.append(r)
                for h, d in r["allocations"].items():
                    self.hex_demand_residual[h] -= d

        # -------------------------
        # Consolidação
        # -------------------------
        snapshot_after = deepcopy(self.hex_demand_residual)

        served_existing = sum(
            sum(p["allocations"].values())
            for p in existing_results
        )

        served_new = sum(
            sum(p["allocations"].values())
            for p in new_partners
        )

        return {
            "summary": {
                "total_demand": sum(snapshot_before.values()),
                "served_by_existing": served_existing,
                "served_by_new": served_new,
                "residual_demand": sum(snapshot_after.values()),
                "existing_partners_used": len(existing_results),
                "new_partners_suggested": len(new_partners)
            },
            "existing_partners": existing_results,
            "new_partners": new_partners,
            "snapshots": {
                "before": snapshot_before,
                "after": snapshot_after
            }
        }

    def export_geojson(result, output_path="output.geojson"):
        features = []

        before = result["snapshots"]["before"]
        after = result["snapshots"]["after"]

        # -------------------------
        # HEXÁGONOS
        # -------------------------
        for hex_id, original_demand in before.items():
            residual = after.get(hex_id, 0)
            served = original_demand - residual

            boundary = h3.cell_to_boundary(hex_id)
            coords = [[lng, lat] for lat, lng in boundary]
            coords.append(coords[0])

            features.append({
                "type": "Feature",
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [coords]
                },
                "properties": {
                    "hex_id": hex_id,
                    "original_demand": original_demand,
                    "served": served,
                    "residual": residual
                }
            })

        # -------------------------
        # PARCEIROS EXISTENTES
        # -------------------------
        for p in result["existing_partners"]:
            lat, lng = h3.cell_to_latlng(p["origin_hex"])

            features.append({
                "type": "Feature",
                "geometry": {
                    "type": "Point",
                    "coordinates": [lng, lat]
                },
                "properties": {
                    "entity": "EXISTING_PARTNER",
                    "partner_id": p["partner_id"],
                    "radius_m": p["radius_m"],
                    "capacity": p["capacity"],
                    "total_assigned": p["total_assigned"]
                }
            })

        # -------------------------
        # NOVOS PARCEIROS
        # -------------------------
        for p in result["new_partners"]:
            lat, lng = h3.cell_to_latlng(p["origin_hex"])

            features.append({
                "type": "Feature",
                "geometry": {
                    "type": "Point",
                    "coordinates": [lng, lat]
                },
                "properties": {
                    "entity": "NEW_PARTNER",
                    "radius_m": p["radius_m"],
                    "capacity": p["capacity"],
                    "total_assigned": p["total_assigned"]
                }
            })

        geojson = {
            "type": "FeatureCollection",
            "features": features
        }

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(geojson, f, ensure_ascii=False, indent=2)
    
    def decision_key(d: dict) -> str:
        if d["entity"] == "PARTNER":
            return f"P_{d['partner_id']}"
        else:
            return f"N_{d['origin_hex']}_{d.get('radius_m','')}_{d.get('capacity','')}"
        
    def apply_snapshot(decisions: List[dict], snapshot: Dict) -> List[dict]:
        for d in decisions:
            key = OptimizationHub.decision_key(d)
            prev = snapshot.get(key)

            if prev is None:
                d["execution_status"] = "NEW"
                continue
            
            def normalize(x):
                return {
                    k: v for k, v in x.items()
                    if k not in ("execution_status", "allocations")
                }
            
            if normalize(prev) == normalize(d):
                d["execution_status"] = prev.get("execution_status", "EXECUTED")
            else:
                d["execution_status"] = "CHANGED"

        return decisions
    
    def save_snapshot(result, path="snapshot.json"):
        snapshot = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "summary": result["summary"],
            "before": result["snapshots"]["before"],
            "after": result["snapshots"]["after"]
        }

        with open(path, "w", encoding="utf-8") as f:
            json.dump(snapshot, f, ensure_ascii=False, indent=2)
    
    def log_execution(result, path="execution_log.json"):
        log = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "summary": result["summary"],
            "existing_partners": [
                {
                    "partner_id": p["partner_id"],
                    "radius_m": p["radius_m"],
                    "total_assigned": p["total_assigned"]
                }
                for p in result["existing_partners"]
            ],
            "new_partners": [
                {
                    "origin_hex": p["origin_hex"],
                    "radius_m": p["radius_m"],
                    "capacity": p["capacity"],
                    "total_assigned": p["total_assigned"]
                }
                for p in result["new_partners"]
            ]
        }

        with open(path, "w", encoding="utf-8") as f:
            json.dump(log, f, ensure_ascii=False, indent=2)
                    
if __name__ == "__main__": 
    try:
        hub = OptimizationHub(config.BASE_PACKAGES, config.BASE_PARTNERS)
        result = hub.run()

        OptimizationHub.export_geojson(result, Path(config.DEST_FOLDER / "optimization_layer.geojson"))
        OptimizationHub.save_snapshot(result, Path(config.DEST_FOLDER / "snapshot.json"))
        OptimizationHub.log_execution(result, Path(config.DEST_FOLDER / "execution_log.json"))
    except Exception as e:
        traceback.print_exc()
        raise