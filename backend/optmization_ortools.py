import json, h3, math, traceback
import pandas as pd
import numpy as np
import config as configuration
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional, Set
from dataclasses import dataclass, field
from sklearn.cluster import DBSCAN, KMeans
from ortools.sat.python import cp_model
from concurrent.futures import ProcessPoolExecutor, as_completed

# =====================================================
# CONFIGURAÇÕES
# =====================================================
class Config:
    BASE_PACKAGES = configuration.BASE_PACKAGES
    BASE_PARTNERS = configuration.BASE_PARTNERS
    DEST_FOLDER = configuration.DEST_FOLDER
    H3_RES = configuration.H3_RESOLUTION
    MIN_CAP = configuration.MIN_CAPACITY
    MAX_CAP = configuration.MAX_CAPACITY
    CAPACITIES = configuration.CAPACITIES
    RADII = configuration.RADII_M
    BONUS_PER_OPEN = 1500 

@dataclass
class Allocation:
    hex_id: str
    packages_assigned: int

@dataclass
class PartnerMetrics:
    origin_hex: str
    station_code: str
    radius_m: int
    capacity: int
    entity_type: str 
    store_id: Optional[str] = None
    priority_rank: int = 0
    cluster_name: str = "N/A"
    allocations: List[Allocation] = field(default_factory=list)

    @property
    def total_load(self) -> int:
        return sum(a.packages_assigned for a in self.allocations)

@dataclass
class OptimizationReport:
    station_code: str
    existing_partners: List[PartnerMetrics]
    new_partners: List[PartnerMetrics]
    demand_summary: Dict[str, Dict]
    hex_to_cluster: Dict[str, str]
    base_metrics: Dict = field(default_factory=dict)

# =====================================================
# WORKER DO SOLVER
# =====================================================
def solve_island_exhaustion_worker(payload: Dict) -> List[Dict]:
    station_code = payload['station_code']
    cluster_name = payload['cluster_name']
    island_hexes = payload['hexes']
    demand_map = dict(payload['demand_map'])
    island_results = []
    
    while True:
        seeds = sorted([h for h in island_hexes if demand_map.get(h, 0) > 0], 
                      key=lambda x: demand_map[x], reverse=True)
        if not seeds: break
        
        best_seed = seeds[0]
        potential_vol = sum(demand_map[h] for h in island_hexes if h3.grid_distance(h, best_seed) <= 9)
        if potential_vol < Config.MIN_CAP: break

        model = cp_model.CpModel()
        x, y = {}, {}
        for r in Config.RADII:
            for k in [Config.MIN_CAP, Config.MAX_CAP]:
                idx = (best_seed, r['radius_m'], k)
                x[idx] = model.NewBoolVar(f'x_{idx}')
                potential_h = [h for h in island_hexes if h3.grid_distance(h, best_seed) <= r['hex_distance']]
                for h in potential_h:
                    y[(h, *idx)] = model.NewIntVar(0, demand_map[h], f'y_{h}_{idx}')

        model.Add(sum(x.values()) <= 1)
        for idx_x, var_x in x.items():
            rel_y = [v for ky, v in y.items() if ky[1:] == idx_x]
            model.Add(sum(rel_y) <= idx_x[2] * var_x)
            model.Add(sum(rel_y) >= Config.MIN_CAP * var_x)

        obj_terms = [v_y * 10 for v_y in y.values()]
        for idx_x, v_x in x.items():
            penalty = next(rad['penalty'] for rad in Config.RADII if rad['radius_m'] == idx_x[1])
            obj_terms.append(-penalty * v_x)
        
        model.Maximize(sum(obj_terms))
        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = 2
        
        if solver.Solve(model) in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            found_any = False
            for idx_x, var_x in x.items():
                if solver.Value(var_x):
                    allocs = [{"hex_id": ky[0], "packages_assigned": int(solver.Value(vy))} 
                             for ky, vy in y.items() if ky[1:] == idx_x and solver.Value(vy) > 0]
                    if allocs:
                        island_results.append({
                            "origin_hex": idx_x[0], "station_code": station_code,
                            "cluster_name": cluster_name, "radius_m": idx_x[1], 
                            "capacity": idx_x[2], "entity_type": "NEW", "allocations": allocs
                        })
                        for a in allocs:
                            demand_map[a['hex_id']] = max(0, demand_map[a['hex_id']] - a['packages_assigned'])
                        found_any = True
            if not found_any: break
        else: break
    return island_results

# =====================================================
# SERVIÇO PRINCIPAL
# =====================================================
class OptimizationService:
    def __init__(self):
        self.reports: List[OptimizationReport] = []
        self.hex_to_ceps: Dict[str, Set[str]] = {}

    def _load_data(self):
        print(f"[{datetime.now()}] Carregando dados...")
        df = pd.read_csv(Config.BASE_PACKAGES)
        df['cep'] = df['cep'].astype(str).str.replace(r'\D', '', regex=True).str.zfill(8)
        df["hex"] = [h3.latlng_to_cell(la, lo, Config.H3_RES) for la, lo in zip(df.latitude, df.longitude)]
        self.hex_to_ceps = df.groupby('hex')['cep'].apply(set).to_dict()
        days = pd.to_datetime(df.plan_date).nunique() or 1
        self.demand_df = df.groupby(["station_code", "hex"]).size().reset_index(name="avg_demand")
        self.demand_df["avg_demand"] = (self.demand_df["avg_demand"] / days).round(0).astype(int)

        with open(Config.BASE_PARTNERS, "r", encoding="utf-8") as f:
            p_data = json.load(f)["allMarkerData"]
        self.partners_df = pd.DataFrame(p_data)
        self.partners_df = self.partners_df[(self.partners_df["status"] == "Active") & self.partners_df["status"] == "Onboarding"]
        self.partners_df.rename(columns={"delivery_station": "station_code"}, inplace=True)
        self.partners_df["origin_hex"] = [h3.latlng_to_cell(float(la), float(lo), Config.H3_RES) for la, lo in zip(self.partners_df.lat, self.partners_df.lon)]

    def _find_neighborhood_clusters(self, res_dem, station_code):
        active_hexes = [h for h, v in res_dem.items() if v > 0]
        if not active_hexes: return [], {}
        coords = np.radians([h3.cell_to_latlng(h) for h in active_hexes])
        db = DBSCAN(eps=0.5/6371, min_samples=1, metric='haversine').fit(coords)
        initial_islands = {}
        for idx, label in enumerate(db.labels_):
            if label not in initial_islands: initial_islands[label] = []
            initial_islands[label].append(active_hexes[idx])
            
        islands, hex_to_cluster, c_idx = [], {}, 0
        for label, hex_list in initial_islands.items():
            if len(hex_list) > 200:
                n_sub = math.ceil(len(hex_list) / 150)
                sub_coords = [h3.cell_to_latlng(h) for h in hex_list]
                km = KMeans(n_clusters=n_sub, random_state=42, n_init=5).fit(sub_coords)
                for s_label in range(n_sub):
                    sub_hexes = [hex_list[i] for i, l in enumerate(km.labels_) if l == s_label]
                    c_name = f"{station_code}_B{c_idx}"
                    islands.append(sub_hexes); [hex_to_cluster.update({h: c_name}) for h in sub_hexes]
                    c_idx += 1
            else:
                c_name = f"{station_code}_B{c_idx}"
                islands.append(hex_list); [hex_to_cluster.update({h: c_name}) for h in hex_list]
                c_idx += 1
        return islands, hex_to_cluster

    def run(self):
        self._load_data()
        for base in self.demand_df.station_code.unique():
            print(f"\n🚀 ANALISANDO UNIDADE: {base}")
            orig_dem = self.demand_df[self.demand_df.station_code == base].set_index("hex")["avg_demand"].to_dict()
            res_dem = dict(orig_dem)
            
            # 1. ATIVOS
            existing_objs = []
            for _, p in self.partners_df[self.partners_df.station_code == base].iterrows():
                for r in Config.RADII:
                    in_r = [h for h in h3.grid_disk(p.origin_hex, r["hex_distance"]) if res_dem.get(h, 0) > 0]
                    allocs, total = [], 0
                    for h in sorted(in_r, key=lambda x: h3.grid_distance(x, p.origin_hex)):
                        take = min(res_dem[h], Config.MAX_CAP - total)
                        if take > 0: allocs.append(Allocation(h, take)); total += take
                    if total >= Config.MIN_CAP:
                        existing_objs.append(PartnerMetrics(p.origin_hex, base, r["radius_m"], Config.MAX_CAP, "EXISTING", str(p.store_id), 0, "Ativo", allocs))
                        for a in allocs: res_dem[a.hex_id] -= a.packages_assigned
                        break

            # 2. BAIRROS E NOVOS PARCEIROS
            islands, hex_to_cluster = self._find_neighborhood_clusters(res_dem, base)
            new_objs = []
            if islands:
                tasks = [{"station_code": base, "cluster_name": hex_to_cluster[h[0]], "hexes": h, "demand_map": res_dem} for h in islands]
                with ProcessPoolExecutor(max_workers=10) as exc:
                    futures = [exc.submit(solve_island_exhaustion_worker, t) for t in tasks]
                    for f in as_completed(futures):
                        for p_data in f.result():
                            p_new = PartnerMetrics(**{**p_data, "allocations": [Allocation(**a) for a in p_data['allocations']]})
                            new_objs.append(p_new)
                            for a in p_new.allocations: res_dem[a.hex_id] = max(0, res_dem.get(a.hex_id, 0) - a.packages_assigned)

            # 3. CONSOLIDAÇÃO DE MÉTRICAS DA BASE
            total_orig = sum(orig_dem.values())
            total_ext = sum(p.total_load for p in existing_objs)
            total_new = sum(p.total_load for p in new_objs)
            final_res = sum(res_dem.values())
            
            # Cálculo das novas médias
            n_count = len(new_objs)
            avg_load = total_new / n_count if n_count > 0 else 0
            avg_radius = sum(p.radius_m for p in new_objs) / n_count if n_count > 0 else 0
            
            base_m = {
                "total_demand": total_orig,
                "existing_absorbed": total_ext,
                "new_allocated": total_new,
                "residual": final_res,
                "new_partners_count": n_count,
                "cluster_count": len(islands),
                "avg_load": avg_load,
                "avg_radius": avg_radius
            }
            
            # Print Resumo no Terminal
            print(f"\n" + "="*50)
            print(f"📊 RESUMO CONSOLIDADO - BASE: {base}")
            print(f"  • Demanda Total Bruta: {total_orig:,} pacotes")
            print(f"  • Absorvida por Ativos: {total_ext:,} pacotes ({(total_ext/total_orig*100):.1f}%)")
            print(f"  • Sugerida p/ Novos: {total_new:,} pacotes ({(total_new/total_orig*100):.1f}%)")
            print(f"  • Residual Final Descoberto: {final_res:,} pacotes")
            print(f"  • Novos Parceiros Sugeridos: {n_count}")
            print(f"  • Média de Pacotes/Vaga: {avg_load:.1f} pacotes")
            print(f"  • Média de Raio/Vaga: {avg_radius:.0f} m")
            print(f"  • Total de Bairros (Clusters): {len(islands)}")
            print("="*50)

            # Ranking Top 5
            cluster_priority = []
            for cn in set(p.cluster_name for p in new_objs):
                pts = [p for p in new_objs if p.cluster_name == cn]
                cluster_priority.append({"name": cn, "vol": sum(p.total_load for p in pts), "qty": len(pts)})
            cluster_priority.sort(key=lambda x: x['vol'], reverse=True)
            
            print(f"\n🏆 TOP 5 BAIRROS PRIORITÁRIOS EM {base}:")
            for c in cluster_priority[:7]:
                print(f"  - {c['name']}: {c['vol']:,} pacotes em {c['qty']} novas vagas")

            self.reports.append(OptimizationReport(base, existing_objs, new_objs, 
                                                  {h:{"original":orig_dem[h],"residual":res_dem[h]} for h in orig_dem}, 
                                                  hex_to_cluster, base_m))
        
        self.export_strategic_results()

    def export_strategic_results(self):
        dest = Path(Config.DEST_FOLDER); dest.mkdir(exist_ok=True)
        
        # GeoJSON (Mantido para o mapa)
        features = []
        for r in self.reports:
            for h, info in r.demand_summary.items():
                boundary = h3.cell_to_boundary(h)
                coords = [[c[1], c[0]] for c in boundary]; coords.append(coords[0])
                features.append({"type": "Feature", "geometry": {"type": "Polygon", "coordinates": [coords]},
                                 "properties": {"base": r.station_code, "residual": info["residual"], "cluster_name": r.hex_to_cluster.get(h, "Ativo/Vazio")}})
            for p in r.existing_partners + r.new_partners:
                lat, lng = h3.cell_to_latlng(p.origin_hex)
                features.append({"type": "Feature", "geometry": {"type": "Point", "coordinates": [lng, lat]},
                                 "properties": {"type": p.entity_type, "cluster_name": p.cluster_name, "cap": p.total_load, "radius": p.radius_m}})
        with open(dest / "mapa_estrategico.geojson", "w") as f: json.dump({"type": "FeatureCollection", "features": features}, f)

        # TXT ESTRATÉGICO
        with open(dest / "OPORTUNIDADES_ESTRATEGICAS.txt", "w", encoding="utf-8") as f:
            f.write(f"RELATÓRIO DE EXPANSÃO - GERADO EM {datetime.now().strftime('%d/%m/%Y %H:%M')}\n")
            f.write("="*80 + "\n")
            
            for r in self.reports:
                m = r.base_metrics
                f.write(f"\n📍 UNIDADE OPERACIONAL: {r.station_code}\n")
                f.write(f"{'-'*40}\n")
                f.write(f"RESUMO EXECUTIVO DA BASE:\n")
                f.write(f"  - Demanda Total da Base:     {m['total_demand']:,} pacotes\n")
                f.write(f"  - Atendida por Ativos:       {m['existing_absorbed']:,} pacotes\n")
                f.write(f"  - Alocada para Expansão:     {m['new_allocated']:,} pacotes\n")
                f.write(f"  - Gap de Expansão (Residual):{m['residual']:,} pacotes\n")
                f.write(f"  - Potencial de Novos Pts:    {m['new_partners_count']} vagas\n")
                f.write(f"  - Média de Pacotes/Vaga:     {m['avg_load']:.1f} pacotes\n")
                f.write(f"  - Média de Raio Proposto:    {m['avg_radius']:.0f} m\n")
                f.write(f"  - Divisão Geográfica:        {m['cluster_count']} bairros\n")
                f.write(f"{'-'*40}\n")
                
                clusters_stats = []
                for cn in set(p.cluster_name for p in r.new_partners):
                    pts = [p for p in r.new_partners if p.cluster_name == cn]
                    clusters_stats.append({"name": cn, "vol": sum(p.total_load for p in pts), "pts": pts})
                clusters_stats.sort(key=lambda x: x['vol'], reverse=True)
                
                f.write(f"TOP 5 BAIRROS PRIORITÁRIOS EM {r.station_code}:\n")
                for i, c in enumerate(clusters_stats[:5], 1):
                    # Cálculo de médias locais do cluster
                    c_avg_load = c['vol'] / len(c['pts'])
                    c_avg_radius = sum(p.radius_m for p in c['pts']) / len(c['pts'])
                    
                    f.write(f"\n  {i}º) {c['name']} - Potencial: {c['vol']:,} pacotes\n")
                    f.write(f"      {len(c['pts'])} vagas | Média: {c_avg_load:.1f} pacotes/vaga | Raio Médio: {c_avg_radius:.0f}m\n")
                    for p in sorted(c['pts'], key=lambda x: x.total_load, reverse=True)[:len(c['pts'])]:
                        lat, lng = h3.cell_to_latlng(p.origin_hex)
                        f.write(f"      • Vaga {p.total_load} pacotes (R:{p.radius_m}m) -> maps.google.com/maps?q={lat},{lng}\n")
                f.write("\n" + "="*80 + "\n")

if __name__ == "__main__":
    try:
        OptimizationService().run()
        print(f"\n✅ Concluído com sucesso!")
    except: traceback.print_exc()