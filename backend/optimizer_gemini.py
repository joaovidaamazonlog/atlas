import json
import h3
import pandas as pd
import numpy as np
import config
import traceback
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, List
from sklearn.cluster import DBSCAN
from ortools.sat.python import cp_model
from concurrent.futures import ProcessPoolExecutor

# =====================================================
# CONFIGURAÇÕES GLOBAIS
# =====================================================
H3_RESOLUTION = 9
MIN_CAPACITY = 45
MAX_CAPACITY = 70
CAPACITIES = [45, 55, 70]

RADII = [
    {"radius_m": 200, "hex_distance": 1, "penalty": 10},
    {"radius_m": 500, "hex_distance": 3, "penalty": 50},
    {"radius_m": 800, "hex_distance": 5, "penalty": 200},
    {"radius_m": 1100, "hex_distance": 7, "penalty": 500},
    {"radius_m": 1500, "hex_distance": 9, "penalty": 1000}
]

# =====================================================
# MODELOS DE DADOS
# =====================================================
class Partner:
    __slots__ = ("id", "lat", "lon", "origin_hex")
    def __init__(self, partner_id: str, lat: float, lon: float):
        self.id = partner_id
        self.lat = lat
        self.lon = lon
        self.origin_hex = h3.latlng_to_cell(lat, lon, H3_RESOLUTION)

class DataIngestion:
    @staticmethod
    def load_packages(csv_path: str) -> Dict[str, int]:
        df = pd.read_csv(csv_path, usecols=["latitude", "longitude", "plan_date"])
        df["plan_date"] = pd.to_datetime(df["plan_date"])
        days = df["plan_date"].nunique() or 1
        
        lats, lngs = df.latitude.values, df.longitude.values
        df["hex"] = [h3.latlng_to_cell(la, ln, H3_RESOLUTION) for la, ln in zip(lats, lngs)]
        
        daily = df.groupby("hex").size() // days
        return daily.to_dict()

    @staticmethod
    def load_partners(json_path: str) -> List[Partner]:
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        df = pd.DataFrame(data["allMarkerData"])
        df = df[(df["status"] == "Active") & df["lat"].notnull()]
        return [Partner(str(r.store_id), float(r.lat), float(r.lon)) for _, r in df.iterrows()]

# =====================================================
# MOTOR DE OTIMIZAÇÃO (CP-SAT)
# =====================================================
class CapacityExpansionOptimizer:
    def __init__(self, cluster_hexes: List[str], cluster_demand: Dict[str, int], max_partners: int = 20):
        self.cluster = cluster_hexes
        self.demand = cluster_demand
        self.max_partners = max_partners

    def solve(self) -> List[Dict]:
        if not self.demand: return []
        
        model = cp_model.CpModel()
        H = list(self.demand.keys())
        C = H 
        S = range(self.max_partners)
        
        x = {} 
        y = {} 

        for c in C:
            for s in S:
                for r in RADII:
                    for k in CAPACITIES:
                        x[(c, s, r['radius_m'], k)] = model.NewBoolVar(f'x_{c}_{s}_{r["radius_m"]}_{k}')

        for h in H:
            for c in C:
                dist = h3.grid_distance(h, c)
                for s in S:
                    for r in RADII:
                        if dist <= r['hex_distance']:
                            for k in CAPACITIES:
                                y[(h, c, s, r['radius_m'], k)] = model.NewBoolVar(f'y_{h}_{c}_{s}_{r["radius_m"]}_{k}')

        for c in C:
            for s in S:
                for r in RADII:
                    r_m = r['radius_m']
                    for k in CAPACITIES:
                        vars_y = [y[key] for key in y if key[1:] == (c, s, r_m, k)]
                        if not vars_y: continue
                        
                        load = sum(self.demand[key[0]] * var for key, var in zip([k for k in y if k[1:] == (c, s, r_m, k)], vars_y))
                        model.Add(load <= k * x[(c, s, r_m, k)])
                        model.Add(load >= MIN_CAPACITY * x[(c, s, r_m, k)])

        for h in H:
            model.Add(sum(var for key, var in y.items() if key[0] == h) <= 1)

        obj_terms = [self.demand[k[0]] * v * 100 for k, v in y.items()]
        for (c, s, r_m, k), v in x.items():
            penalty = next(rad['penalty'] for rad in RADII if rad['radius_m'] == r_m)
            obj_terms.append(-penalty * v)
        
        model.Maximize(sum(obj_terms))
        
        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = 15
        status = solver.Solve(model)

        results = []
        if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            for (c, s, r_m, k), var in x.items():
                if solver.Value(var):
                    alloc = {h: self.demand[h] for h in H if (h, c, s, r_m, k) in y and solver.Value(y[(h, c, s, r_m, k)])}
                    results.append({
                        "entity": "NEW_PARTNER", "origin_hex": c, "radius_m": r_m,
                        "capacity": k, "total_assigned": sum(alloc.values()), "allocations": alloc
                    })
        return results

# =====================================================
# FUNÇÃO DE TRABALHO (Isolada para o Pool)
# =====================================================
def _solve_cluster_task(payload):
    """
    payload: (list_of_hexes, dict_of_local_demand)
    """
    cluster_hexes, local_demand = payload
    try:
        optimizer = CapacityExpansionOptimizer(cluster_hexes, local_demand)
        return optimizer.solve()
    except Exception:
        return []

# =====================================================
# ORQUESTRADOR
# =====================================================
class OptimizationHub:
    def __init__(self, pkg_csv: str, partner_json: str):
        print(f"[{datetime.now()}] Carregando dados...")
        self.hex_demand_original = DataIngestion.load_packages(pkg_csv)
        self.hex_demand_residual = dict(self.hex_demand_original)
        self.partners = DataIngestion.load_partners(partner_json)

    def run(self):
        print(f"[{datetime.now()}] Fase A: Atendendo parceiros atuais...")
        existing_results = self._process_existing_partners()
        
        print(f"[{datetime.now()}] Fase B: Gerando clusters de demanda residual...")
        clusters = self._cluster_gaps()
        
        if not clusters:
            print("Nenhum cluster de expansão encontrado.")
            return self._compile_result(existing_results, [])

        print(f"[{datetime.now()}] Preparando {len(clusters)} tarefas para execução paralela...")
        # OTIMIZAÇÃO DE MEMÓRIA: Passar apenas a demanda local do cluster para o processo filho
        tasks = []
        for c in clusters:
            local_demand = {h: self.hex_demand_residual[h] for h in c if h in self.hex_demand_residual}
            tasks.append((c, local_demand))

        new_partners = []
        # Limitamos max_workers para não estourar a RAM no Windows
        with ProcessPoolExecutor(max_workers=4) as executor:
            for batch in executor.map(_solve_cluster_task, tasks):
                for res in batch:
                    new_partners.append(res)
                    for h, d in res["allocations"].items():
                        if h in self.hex_demand_residual:
                            self.hex_demand_residual[h] = max(0, self.hex_demand_residual[h] - d)

        return self._compile_result(existing_results, new_partners)

    def _process_existing_partners(self):
        results = []
        for p in self.partners:
            best_r = None
            for r in RADII:
                in_range = [h for h in h3.grid_disk(p.origin_hex, r["hex_distance"]) if self.hex_demand_residual.get(h, 0) > 0]
                if not in_range: continue
                
                alloc, total = {}, 0
                for h in sorted(in_range, key=lambda x: h3.grid_distance(x, p.origin_hex)):
                    d = self.hex_demand_residual[h]
                    if total + d <= MAX_CAPACITY:
                        alloc[h] = d
                        total += d
                
                if total >= MIN_CAPACITY:
                    best_r = {"radius_m": r["radius_m"], "alloc": alloc, "total": total}
                    break
            
            if best_r:
                results.append({
                    "entity": "PARTNER", "partner_id": p.id, "origin_hex": p.origin_hex,
                    "radius_m": best_r["radius_m"], "capacity": MAX_CAPACITY,
                    "allocations": best_r["alloc"], "total_assigned": best_r["total"]
                })
                for h, d in best_r["alloc"].items():
                    self.hex_demand_residual[h] -= d
        return results

    def _cluster_gaps(self):
        # Filtro de densidade mínima para clusterizar
        active_hexes = [h for h, d in self.hex_demand_residual.items() if d >= 2]
        if not active_hexes: return []
        
        coords = np.radians([h3.cell_to_latlng(h) for h in active_hexes])
        # eps = 1.5km
        db = DBSCAN(eps=1.5/6371.0088, min_samples=1, metric='haversine', algorithm='ball_tree').fit(coords)
        
        clusters_dict = {}
        for idx, lbl in enumerate(db.labels_):
            if lbl == -1: continue
            if lbl not in clusters_dict: clusters_dict[lbl] = []
            clusters_dict[lbl].append(active_hexes[idx])
            
        # Manter apenas clusters que podem sustentar pelo menos 1 parceiro (45 pacotes)
        final_clusters = []
        for c in clusters_dict.values():
            if sum(self.hex_demand_residual[h] for h in c) >= MIN_CAPACITY:
                final_clusters.append(c)
        return final_clusters

    def _compile_result(self, existing, new):
        return {
            "summary": {
                "total_demand": sum(self.hex_demand_original.values()),
                "served_by_existing": sum(p["total_assigned"] for p in existing),
                "served_by_new": sum(p["total_assigned"] for p in new),
                "residual_demand": sum(self.hex_demand_residual.values()),
                "new_partners_suggested": len(new)
            },
            "existing_partners": existing,
            "new_partners": new,
            "snapshots": {"before": self.hex_demand_original, "after": self.hex_demand_residual}
        }

    @staticmethod
    def save_all(result, folder):
        path = Path(folder)
        path.mkdir(exist_ok=True)
        
        # 1. Snapshot JSON
        with open(path / "snapshot.json", "w") as f:
            # Filtramos o 'before' para não salvar milhões de zeros
            clean_result = deepcopy(result)
            clean_result["snapshots"]["before"] = {k:v for k,v in result["snapshots"]["before"].items() if v > 0}
            json.dump(clean_result, f, indent=2)

        # 2. GeoJSON para Mapa
        features = []
        for p in result["existing_partners"] + result["new_partners"]:
            lat, lng = h3.cell_to_latlng(p["origin_hex"])
            features.append({
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [lng, lat]},
                "properties": {"entity": p["entity"], "radius": p["radius_m"], "total": p["total_assigned"]}
            })
        with open(path / "mapa.geojson", "w") as f:
            json.dump({"type": "FeatureCollection", "features": features}, f)

# =====================================================
# EXECUÇÃO PRINCIPAL
# =====================================================
if __name__ == "__main__":
    from copy import deepcopy
    try:
        hub = OptimizationHub(config.BASE_PACKAGES, config.BASE_PARTNERS)
        final_result = hub.run()
        
        OptimizationHub.save_all(final_result, config.DEST_FOLDER)
        print(f"Concluído! {final_result['summary']['new_partners_suggested']} novos parceiros sugeridos.")
        
    except Exception:
        traceback.print_exc()