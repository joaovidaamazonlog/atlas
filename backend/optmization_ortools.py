import json
import math
import os
import h3
import pandas as pd
import numpy as np
import config
from datetime import datetime
from typing import Dict, List
from collections import defaultdict
from sklearn.cluster import DBSCAN
from ortools.sat.python import cp_model

H3_RESOLUTION = config.H3_RESOLUTION
HEX_EDGE_M = config.HEX_EDGE_M
RADII_M = config.RADII_M
CAPACITIES = config.CAPACITIES
MIN_CAPACITY = config.MIN_CAPACITY
MAX_CAPACITY = config.MAX_CAPACITY
SCALING_FACTOR = config.SCALING_FACTOR

class Partner:
    __slots__ = ("id", "origin_hex", "lat", "lon")
    def __init__(self, partner_id: str, origin_hex: str, lat: float, lon: float):
        self.id = partner_id
        self.origin_hex = origin_hex
        self.lat = lat
        self.lon = lon

class DataIngestion:
    @staticmethod
    def load_packages(csv_path: str) -> Dict[str, int]:
        df = pd.read_csv(csv_path, usecols=["latitude", "longitude", "plan_date"])
        df["plan_date"] = pd.to_datetime(df["plan_date"])
        num_days = df["plan_date"].nunique()

        df["hex"] = [
            h3.latlng_to_cell(lat, lon, H3_RESOLUTION)
            for lat, lon in zip(df.latitude, df.longitude)
        ]

        # Multiplicamos pelo fator e convertemos para int
        daily = (df.groupby("hex").size() / num_days) * SCALING_FACTOR
        return daily.astype(int).to_dict()

    @staticmethod
    def load_partners(json_path: str) -> List[Partner]:
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        df = pd.DataFrame(data["allMarkerData"])
        df = df[(df["status"] == "Active") & df["lat"].notnull()]
        partners = []
        for _, r in df.iterrows():
            origin_hex = h3.latlng_to_cell(float(r.lat), float(r.lon), H3_RESOLUTION)
            partners.append(Partner(str(r.store_id), origin_hex, float(r.lat), float(r.lon)))
        return partners

class ExistingPartnerOptimizer:
    def __init__(self, partner: Partner, hex_demand: Dict[str, int]):
        self.partner = partner
        self.hex_demand = hex_demand

    def solve(self):
        model = cp_model.CpModel()
        # Escala o cálculo de slots
        total_demand = sum(self.hex_demand.values())
        max_slots = math.ceil(total_demand / (MIN_CAPACITY * SCALING_FACTOR))
        if max_slots == 0: max_slots = 1

        x, y = {}, {}
        for s in range(max_slots):
            x[s] = model.NewBoolVar(f"x_{s}")
            for h in self.hex_demand:
                y[(h, s)] = model.NewBoolVar(f"y_{h}_{s}")

        for s in range(max_slots):
            model.Add(
                sum(self.hex_demand[h] * y[(h, s)] for h in self.hex_demand)
                <= (MAX_CAPACITY * SCALING_FACTOR) * x[s]
            )

        for h in self.hex_demand:
            model.Add(sum(y[(h, s)] for s in range(max_slots)) <= 1)

        model.Maximize(
            1_000_000 * sum(self.hex_demand[h] * y[(h, s)] for h in self.hex_demand for s in range(max_slots))
            - 10_000 * sum(x[s] for s in range(max_slots))
        )

        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = 3
        status = solver.Solve(model)

        assigned_scaled = sum(self.hex_demand[h] for h in self.hex_demand for s in range(max_slots) if solver.Value(y[(h, s)]))
        slots_used = sum(solver.Value(x[s]) for s in range(max_slots))

        return {
            "partner_id": self.partner.id,
            "assigned_demand": round(assigned_scaled / SCALING_FACTOR, 2),
            "capacity": min(MAX_CAPACITY, slots_used * MIN_CAPACITY)
        }

def cluster_hexes(hex_demand: Dict[str, int], eps_m=500) -> List[List[str]]:
    points, hex_ids = [], []
    for h in hex_demand:
        if hex_demand[h] > 0:
            lat, lon = h3.cell_to_latlng(h)
            points.append([lat, lon])
            hex_ids.append(h)
    if not points: return []
    db = DBSCAN(eps=eps_m / 111000, min_samples=1).fit(np.array(points))
    clusters = defaultdict(list)
    for i, lbl in enumerate(db.labels_):
        if lbl >= 0: clusters[lbl].append(hex_ids[i])
    return list(clusters.values())

class GapOptimizer:
    def __init__(self, cluster: List[str], hex_demand: Dict[str, int]):
        self.cluster = cluster
        self.hex_demand = {h: hex_demand[h] for h in cluster}

    def solve(self):
        model = cp_model.CpModel()
        slots = {h: max(1, math.ceil(self.hex_demand[h] / (MIN_CAPACITY * SCALING_FACTOR))) for h in self.hex_demand}
        
        x, y = {}, {}
        for c in self.cluster:
            for s in range(slots[c]):
                for r in RADII_M:
                    for k in CAPACITIES:
                        x[(c, s, r, k)] = model.NewBoolVar(f"x_{c}_{s}_{r}_{k}")

        for h in self.cluster:
            for c in self.cluster:
                for s in range(slots[c]):
                    for r in RADII_M:
                        for k in CAPACITIES:
                            if h3.grid_distance(h, c) * HEX_EDGE_M <= r:
                                y[(h, c, s, r, k)] = model.NewBoolVar(f"y_{h}_{c}_{s}_{r}_{k}")

        for key in y:
            h, c, s, r, k = key
            model.Add(y[key] <= x[(c, s, r, k)])

        for c, s, r, k in x:
            model.Add(
                sum(self.hex_demand[h] * y.get((h, c, s, r, k), 0) for h in self.cluster)
                <= (k * SCALING_FACTOR) * x[(c, s, r, k)]
            )

        for h in self.cluster:
            model.Add(sum(y[key] for key in y if key[0] == h) <= 1)

        model.Maximize(
            1_000_000 * sum(self.hex_demand[key[0]] * y[key] for key in y)
            - 10_000 * sum(x.values())
        )

        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = 15
        solver.Solve(model)

        results = []
        for (c, s, r, k), var in x.items():
            if solver.Value(var):
                demand_scaled = sum(self.hex_demand[h] for (h, cc, ss, rr, kk), yy in y.items() 
                                   if cc == c and ss == s and rr == r and kk == k and solver.Value(yy))
                results.append({
                    "hex": c, "radius_m": r, "capacity": k,
                    "assigned_demand": round(demand_scaled / SCALING_FACTOR, 2)
                })
        return results

class OptimizationHub:
    def __init__(self, pkg_csv, partner_json):
        self.hex_demand = DataIngestion.load_packages(pkg_csv)
        self.partners = DataIngestion.load_partners(partner_json)

    def run(self):
        residual = dict(self.hex_demand)
        active_results = []

        for p in self.partners:
            covered = {h: residual[h] for h in h3.grid_disk(p.origin_hex, 9) if h in residual and residual[h] > 0}
            if not covered: continue
            res = ExistingPartnerOptimizer(p, covered).solve()
            active_results.append(res)
            for h in covered:
                # O cálculo de residual deve considerar o valor escalado
                subtracted = int(res["assigned_demand"] * SCALING_FACTOR)
                residual[h] = max(0, residual[h] - subtracted)

        clusters = cluster_hexes(residual)
        new_partners = []
        for cl in clusters:
            if sum(residual[h] for h in cl) >= (MIN_CAPACITY * SCALING_FACTOR):
                new_partners.extend(GapOptimizer(cl, residual).solve())

        return {
            "existing_partners": active_results,
            "new_partners": new_partners,
            "uncovered_demand": round(sum(residual.values()) / SCALING_FACTOR, 2)
        }
    
    def export_hex_geojson(hex_original: Dict[str, int], hex_residual: Dict[str, int], decisions: List[dict], output_path: str, scale: int = SCALING_FACTOR):
        features = []
        decisions_by_hex = defaultdict(list)

        for d in decisions:
            if "hex" in d:
                decisions_by_hex[d["hex"]].append(d)

        for h, orig in hex_original.items():
            boundary = h3.cell_to_boundary(h)
            coords = [[lng, lat] for lat, lng in boundary]
            coords.append(coords[0])

            residual = hex_residual.get(h, 0)

            features.append({
                "type": "Feature",
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [coords]
                },
                "properties": {
                    "hex_id": h,
                    "original_demand": orig / scale,
                    "residual_demand": residual / scale,
                    "covered_demand": (orig - residual) / scale,
                    "decisions": decisions_by_hex.get(h, [])
                }
            })

        geojson = {
            "type": "FeatureCollection",
            "features": features
        }
            
        with open(output_path, "w") as f:
            json.dump(geojson, f)
    
    def decision_key(d: dict) -> str:
        if d["entity"] == "PARTNER":
            return f"P_{d['partner_id']}_{d['decision']}"
        else:
            return f"C_{d['hex']}_{d['decision']}"
        
    def apply_snapshot(decisions: List[dict], snapshot: Dict) -> List[dict]:
        for d in decisions:
            key = OptimizationHub.decision_key(d)
            prev = snapshot.get(key)

            if not prev:
                d["execution_status"] = "NEW"
            elif prev.get("execution_status") == "EXECUTED":
                # compara parâmetros críticos
                if all(d.get(k) == prev.get(k) for k in d if k not in ["execution_status"]):
                    d["execution_status"] = "EXECUTED"
                else:
                    d["execution_status"] = "CHANGED"
            else:
                d["execution_status"] = "NEW"

        return decisions
    
    def save_snapshot(decisions: List[dict], path: str):
        snap = {
            OptimizationHub.decision_key(d): d
            for d in decisions
        }
        with open(path, "w") as f:
            json.dump(snap, f, indent=2)
    
    def log_executed_actions(decisions: List[dict], log_path: str):
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        with open(log_path, "a") as f:
            for d in decisions:
                if d["entity"] == "PARTNER" and d["execution_status"] == "EXECUTED":
                    f.write(
                        f"[{ts}] PARTNER {d['partner_id']} | "
                        f"{d['decision']} | "
                        f"{json.dumps(d, ensure_ascii=False)}\n"
                    )