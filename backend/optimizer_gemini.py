import json
import h3
import pandas as pd
import numpy as np
import config
import traceback
import math
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
    def __init__(self, cluster_id: int, cluster_hexes: List[str], cluster_demand: Dict[str, int]):
        self.cluster_id = cluster_id
        self.cluster = cluster_hexes
        self.demand = cluster_demand
        
        # Estima o número de parceiros necessários para evitar testar parceiros demais
        total_cluster_demand = sum(self.demand.values())
        self.max_partners = min(25, math.ceil(total_cluster_demand / MIN_CAPACITY) + 2)

    def solve(self) -> List[Dict]:
        if not self.demand: return []
        
        # 1. REDUÇÃO DE CANDIDATOS (O Pulo do Gato para Performance)
        # Selecionamos apenas os hexágonos com mais demanda para serem sedes (max 30)
        # Isso reduz drasticamente a matriz de decisão
        H = list(self.demand.keys())
        C = sorted(H, key=lambda x: self.demand[x], reverse=True)[:30]
        
        model = cp_model.CpModel()
        S = range(self.max_partners)
        x = {} # Parceiro j aberto em c, com raio r e cap k
        y = {} # Alocação

        # Pré-processamento de distâncias para evitar loops N^2
        for c in C:
            for s in S:
                for r in RADII:
                    for k in CAPACITIES:
                        x[(c, s, r['radius_m'], k)] = model.NewBoolVar(f'x_{c}{s}{r["radius_m"]}_{k}')

        # Criar variáveis de alocação Y apenas para quem está no raio
        for c in C:
            # Buscamos apenas hexágonos no raio máximo de 1.5km (9 hexes de dist no H3)
            possible_neighbors = [h for h in H if h3.grid_distance(h, c) <= 9]
            for h in possible_neighbors:
                dist = h3.grid_distance(h, c)
                for s in S:
                    for r in RADII:
                        if dist <= r['hex_distance']:
                            for k in CAPACITIES:
                                y[(h, c, s, r['radius_m'], k)] = model.NewBoolVar(f'y_{h}{c}{s}{r["radius_m"]}{k}')

        # Restrições de Capacidade
        for c in C:
            for s in S:
                for r in RADII:
                    rm = r['radius_m']
                    for k in CAPACITIES:
                        relevant_y = [y[key] for key in y if key[1:] == (c, s, rm, k)]
                        if not relevant_y: continue
                        
                        load = sum(self.demand[key[0]] * var for key, var in zip([k for k in y if k[1:] == (c, s, rm, k)], relevant_y))
                        model.Add(load <= k * x[(c, s, rm, k)])
                        model.Add(load >= MIN_CAPACITY * x[(c, s, rm, k)])

        # Atendimento por hexágono
        for h in H:
            relevant_h_y = [v for k, v in y.items() if k[0] == h]
            if relevant_h_y:
                model.Add(sum(relevant_h_y) <= 1)

        # Objetivo: Maximizar pacotes - penalidade de raio (favorece raios menores)
        obj = []
        for k, v in y.items():
            obj.append(self.demand[k[0]] * v * 100)
        for (c, s, r_m, k), v in x.items():
            penalty = next(rad['penalty'] for rad in RADII if rad['radius_m'] == r_m)
            obj.append(-penalty * v)
        
        model.Maximize(sum(obj))
        
        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = 20 # Limite por cluster
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
    idx, cluster_hexes, local_demand = payload
    start = datetime.now()
    # print(f" > Iniciando Cluster {idx} ({len(cluster_hexes)} hexágonos)...")
    try:
        opt = CapacityExpansionOptimizer(idx, cluster_hexes, local_demand)
        res = opt.solve()
        # duration = (datetime.now() - start).total_seconds()
        # print(f" √ Cluster {idx} finalizado em {duration:.1f}s. Encontrados {len(res)} parceiros.")
        return res
    except Exception as e:
        print(f" X Erro no Cluster {idx}: {str(e)}")
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

        # Preparação de tarefas ultra-leves (apenas o necessário por cluster)
        tasks = []
        for idx, c in enumerate(clusters):
            local_demand = {h: self.hex_demand_residual[h] for h in c if h in self.hex_demand_residual}
            tasks.append((idx, c, local_demand))

        new_partners = []
        print(f"[{datetime.now()}] Iniciando Processamento Paralelo de {len(tasks)} clusters...")
        
        from concurrent.futures import as_completed
        # max_workers=4 para evitar estouro de RAM no Windows
        with ProcessPoolExecutor(max_workers=4) as executor:
            futures = [executor.submit(_solve_cluster_task, t) for t in tasks]
            
            for i, future in enumerate(as_completed(futures)):
                try:
                    batch = future.result()
                    for res in batch:
                        new_partners.append(res)
                        # Atualiza o residual global para o snapshot final
                        for h, d in res["allocations"].items():
                            if h in self.hex_demand_residual:
                                self.hex_demand_residual[h] = max(0, self.hex_demand_residual[h] - d)
                    
                    if i % 10 == 0:
                        print(f"[{datetime.now()}] Progresso: {i}/{len(tasks)} clusters processados...")
                except Exception as e:
                    print(f"Erro ao processar resultado de um cluster: {e}")

        # O retorno chama o mesmo compilador de resultados da versão anterior
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
        # Reduzi a exigência para 'd >= 1' para capturar áreas mais espalhadas
        active_hexes = [h for h, d in self.hex_demand_residual.items() if d >= 1]
        if not active_hexes: return []
        
        coords = np.radians([h3.cell_to_latlng(h) for h in active_hexes])
        # Aumentei levemente o epsilon para 1.6km para conectar áreas próximas
        db = DBSCAN(eps=1.6/6371.0088, min_samples=1, metric='haversine').fit(coords)
        
        clusters_dict = {}
        for idx, lbl in enumerate(db.labels_):
            if lbl == -1: continue
            if lbl not in clusters_dict: clusters_dict[lbl] = []
            clusters_dict[lbl].append(active_hexes[idx])
                
        final_clusters = []
        for c in clusters_dict.values():
            cluster_total = sum(self.hex_demand_residual[h] for h in c)
            # Se o cluster tem pelo menos 45 pacotes, ele é elegível para um novo parceiro
            if cluster_total >= MIN_CAPACITY:
                final_clusters.append(c)
        return final_clusters

    def _compile_result(self, existing, new):
        """Mantém a assinatura de saída idêntica para não quebrar os exports"""
        served_ex = sum(p["total_assigned"] for p in existing)
        served_new = sum(p["total_assigned"] for p in new)
        return {
            "summary": {
                "total_demand": sum(self.hex_demand_original.values()),
                "served_by_existing": served_ex,
                "served_by_new": served_new,
                "residual_demand": sum(self.hex_demand_residual.values()),
                "existing_partners_used": len(existing),
                "new_partners_suggested": len(new)
            },
            "existing_partners": existing,
            "new_partners": new,
            "snapshots": {
                "before": self.hex_demand_original, 
                "after": self.hex_demand_residual
            }
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

    @staticmethod
    def export_rich_geojson(result, output_path):
        features = []
        
        # Criar um mapa de Hexágono -> Lista de Parceiros que o atendem
        hex_to_partners = {}
        for p in result["existing_partners"] + result["new_partners"]:
            p_id = p.get("partner_id", "NOVO_PARCEIRO")
            for h_id in p["allocations"].keys():
                if h_id not in hex_to_partners:
                    hex_to_partners[h_id] = []
                hex_to_partners[h_id].append(str(p_id))

        # 1. GERAR POLÍGONOS DO GRID H3
        all_hexes = set(result["snapshots"]["before"].keys())
        for h_id in all_hexes:
            total = result["snapshots"]["before"].get(h_id, 0)
            residual = result["snapshots"]["after"].get(h_id, 0)
            partners = hex_to_partners.get(h_id, [])
            
            # Lógica de Prospecção: Se sobrou demanda e não há parceiro, ou demanda residual alta
            prospecting_score = 0
            if residual > 0 and not partners:
                prospecting_score = 1 # Recomendação simples
                if residual > 10: prospecting_score = 2 # Alta prioridade
                
            boundary = h3.cell_to_boundary(h_id)
            # H3 retorna (lat, lng), GeoJSON precisa de [lng, lat]
            coords = [[c[1], c[0]] for c in boundary]
            coords.append(coords[0]) # Fechar o polígono

            features.append({
                "type": "Feature",
                "geometry": {"type": "Polygon", "coordinates": [coords]},
                "properties": {
                    "hex_id": h_id,
                    "total_demand": int(total),
                    "residual_demand": int(residual),
                    "partners_serving": ", ".join(partners) if partners else "Nenhum",
                    "prospecting_indicator": prospecting_score,
                    "fill": "#ff0000" if prospecting_score == 2 else "#feb24c" if prospecting_score == 1 else "#31a354"
                }
            })

        # 2. GERAR PONTOS DOS PARCEIROS
        for p in result["existing_partners"] + result["new_partners"]:
            lat, lng = h3.cell_to_latlng(p["origin_hex"])
            features.append({
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [lng, lat]},
                "properties": {
                    "type": "PARTNER_LOCATION",
                    "entity": p["entity"],
                    "id": p.get("partner_id", "NOVO"),
                    "radius_m": p["radius_m"],
                    "total_assigned": p["total_assigned"],
                    "marker-color": "#7b3294" if p["entity"] == "PARTNER" else "#008837"
                }
            })

        with open(output_path, "w", encoding="utf-8") as f:
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
        OptimizationHub.export_rich_geojson(final_result, Path(config.DEST_FOLDER) / "rich_map.geojson")
        print(f"Concluído! {final_result['summary']['new_partners_suggested']} novos parceiros sugeridos.")
        
    except Exception:
        traceback.print_exc()