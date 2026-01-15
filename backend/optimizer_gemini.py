import json
import h3
import math
import pandas as pd
import numpy as np
import traceback
import config as configuration
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional, Set
from dataclasses import dataclass, field
from sklearn.cluster import DBSCAN
from ortools.sat.python import cp_model
from concurrent.futures import ProcessPoolExecutor, as_completed

# =====================================================
# CONFIGURAÇÕES E PASTAS (Ajuste conforme seu ambiente)
# =====================================================
class Config:
    BASE_PACKAGES = configuration.BASE_PACKAGES  # Arquivo com lat, lon, station_code, cep, plan_date
    BASE_PARTNERS = configuration.BASE_PARTNERS  # Arquivo JSON com parceiros ativos
    DEST_FOLDER = configuration.DEST_FOLDER  # Pasta de saída dos resultados
    H3_RES = configuration.H3_RESOLUTION
    MIN_CAP = configuration.MIN_CAPACITY
    MAX_CAP = configuration.MAX_CAPACITY
    CAPACITIES = configuration.CAPACITIES
    RADII = configuration.RADII_M
    BONUS_PER_OPEN = 1500  # Bônus por abrir um novo parceiro (equilíbrio)

# =====================================================
# ENTIDADES DE DOMÍNIO
# =====================================================

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

# =====================================================
# MÓDULO DE INTELIGÊNCIA COMERCIAL (DIAGNÓSTICO IA)
# =====================================================

def get_ai_diagnostic(p: PartnerMetrics, ceps_count: int) -> str:
    if p.radius_m <= 500:
        return "💎 *Argumento de Venda:* Rota de 'tiro curto'. Quase todo o volume está concentrado em poucas ruas. Ideal para convencer quem busca rapidez e baixo gasto de combustível."
    elif p.radius_m <= 800 and ceps_count <= 4:
        return "🚀 *Argumento de Venda:* Rota muito limpa. Poucos CEPs para memorizar. Ótimo para parceiros que querem produtividade máxima."
    elif p.total_load <= 50:
        return "⏱️ *Argumento de Venda:* Carga leve e equilibrada. Perfeito para parceiros que estão começando ou que querem conciliar com outra atividade."
    return "📍 *Argumento de Venda:* Domínio de Área. Esta vaga é estratégica para cobrir o bairro. Busque alguém que já tenha influência ou comércio na região."

# =====================================================
# MOTOR DE OTIMIZAÇÃO (WORKER PARALELO)
# =====================================================

def solve_cluster_worker(payload: Dict) -> List[Dict]:
    try:
        station_code = payload['station_code']
        H = list(payload['hexes'])
        demand_map = payload['demand_map']
        
        # Seleciona candidatos a sede (centros de massa de demanda)
        C = sorted([h for h in H if demand_map.get(h, 0) > 0], 
                   key=lambda x: demand_map.get(x, 0), reverse=True)[:30]
        
        model = cp_model.CpModel()
        total_demand = sum(demand_map.get(h, 0) for h in H)
        
        max_partners = math.ceil(total_demand / Config.MIN_CAP) + 1
        
        S = range(max_partners)
        
        x, y = {}, {}
        for c in C:
            potential_h = [h for h in H if h3.grid_distance(h, c) <= 9]
            for s in S:
                for r in Config.RADII:
                    for k in Config.CAPACITIES:
                        idx = (c, s, r['radius_m'], k)
                        x[idx] = model.NewBoolVar(f'x_{c}_{s}_{r["radius_m"]}_{k}')
                        for h in potential_h:
                            if h3.grid_distance(h, c) <= r['hex_distance']:
                                y[(h, *idx)] = model.NewIntVar(0, demand_map[h], f'y_{h}_{c}_{s}_{r["radius_m"]}_{k}')

        # Restrições de Capacidade e Abertura
        for idx_x, var_x in x.items():
            rel_y = [v for ky, v in y.items() if ky[1:] == idx_x]
            if not rel_y:
                model.Add(var_x == 0)
                continue
            model.Add(sum(rel_y) <= idx_x[3] * var_x)
            model.Add(sum(rel_y) >= Config.MIN_CAP * var_x)

        # Restrição de Demanda do Hexágono
        for h in H:
            rel_h = [v for ky, v in y.items() if ky[0] == h]
            if rel_h:
                model.Add(sum(rel_h) <= demand_map[h])

        # FUNÇÃO OBJETIVO: Maximizar pacotes + Bônus por abertura de parceiros (Equilíbrio)
        obj_terms = []
        for v_y in y.values():
            obj_terms.append(v_y * 100)
            
        for idx_x, v_x in x.items():
            penalty = next(rad['penalty'] for rad in Config.RADII if rad['radius_m'] == idx_x[2])
            bonus_capilaridade = Config.BONUS_PER_OPEN 
            obj_terms.append((bonus_capilaridade - penalty) * v_x)
        
        model.Maximize(sum(obj_terms))
        
        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = 20
        
        results = []
        if solver.Solve(model) in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            for idx_x, var_x in x.items():
                if solver.Value(var_x):
                    allocs = [{"hex_id": ky[0], "packages_assigned": int(solver.Value(vy))} 
                             for ky, vy in y.items() if ky[1:] == idx_x and solver.Value(vy) > 0]
                    if allocs:
                        results.append({
                            "origin_hex": idx_x[0],
                            "station_code": station_code,
                            "radius_m": idx_x[2],
                            "capacity": idx_x[3], 
                            "entity_type": "NEW",
                            "allocations": allocs
                        })
        return results
    except Exception:
        return []

# =====================================================
# SERVIÇO PRINCIPAL
# =====================================================

class OptimizationService:
    def __init__(self):
        self.reports: List[OptimizationReport] = []
        self.hex_to_ceps: Dict[str, Set[str]] = {}

    def _load_data(self):
        print(f"[{datetime.now()}] Lendo bases e mapeando CEPs...")
        df = pd.read_csv(Config.BASE_PACKAGES)
        df['cep'] = df['cep'].astype(str).str.replace(r'\D', '', regex=True).str.zfill(8)
        df["hex"] = [h3.latlng_to_cell(la, lo, Config.H3_RES) for la, lo in zip(df.latitude, df.longitude)]
        
        self.hex_to_ceps = df.groupby('hex')['cep'].apply(set).to_dict()
        
        days = pd.to_datetime(df.plan_date).nunique() or 1
        self.demand_df = df.groupby(["station_code", "hex"]).size().reset_index(name="avg_demand")
        self.demand_df["avg_demand"] = (self.demand_df["avg_demand"] / days).round(2).astype(int)

        with open(Config.BASE_PARTNERS, "r", encoding="utf-8") as f:
            p_data = json.load(f)["allMarkerData"]
        self.partners_df = pd.DataFrame(p_data)
        self.partners_df.rename(columns={"delivery_station": "station_code"}, inplace=True)
        self.partners = self.partners_df[(self.partners_df["status"] == "Active") & self.partners_df["lat"].notnull()]
        self.partners_df["origin_hex"] = [h3.latlng_to_cell(float(la), float(lo), Config.H3_RES) 
                                         for la, lo in zip(self.partners_df.lat, self.partners_df.lon)]

    def _cluster_logic(self, res_dem):
        clusters = []
        temp_dem = res_dem.copy()
        seeds = sorted([h for h in temp_dem if temp_dem[h] > 0], 
                    key=lambda x: temp_dem[x], reverse=True)

        for seed in seeds:
            if temp_dem[seed] <= 0: continue
            neighbors = h3.grid_disk(seed, 9) 

            cluster_hexes = [n for n in neighbors if temp_dem.get(n, 0) > 0]
            cluster_vol = sum(temp_dem[h] for h in cluster_hexes)
            
            if cluster_vol >= Config.MIN_CAP:
                clusters.append(cluster_hexes)
                for h in cluster_hexes:
                    temp_dem[h] = 0
                    
        return clusters

    def _optimize_fixed(self, p, dem_map):
        for r in Config.RADII:
            in_r = [h for h in h3.grid_disk(p.origin_hex, r["hex_distance"]) if dem_map.get(h, 0) > 0]
            if not in_r: continue
            allocs, total = [], 0
            for h in sorted(in_r, key=lambda x: h3.grid_distance(x, p.origin_hex)):
                take = min(dem_map[h], Config.MAX_CAP - total)
                if take > 0:
                    allocs.append(Allocation(h, take))
                    total += take
            if total >= Config.MIN_CAP:
                return PartnerMetrics(p.origin_hex, p.station_code, r["radius_m"], Config.MAX_CAP, "EXISTING", str(p.store_id), 0, allocs)
        return None

    def run(self):
        self._load_data()
        for base in self.demand_df.station_code.unique():
            print(f"--- Processando Base: {base} ---")
            orig_dem = self.demand_df[self.demand_df.station_code == base].set_index("hex")["avg_demand"].to_dict()
            res_dem = dict(orig_dem)
            
            # FASE A: Parceiros Ativos
            existing_objs = []
            for _, p in self.partners_df[self.partners_df.station_code == base].iterrows():
                obj = self._optimize_fixed(p, res_dem)
                if obj:
                    existing_objs.append(obj)
                    for a in obj.allocations:
                        res_dem[a.hex_id] -= a.packages_assigned

            # FASE B: Expansão (Novos Parceiros)
            new_objs = []
            clusters = self._cluster_logic(res_dem)
            if clusters:
                tasks = [{"station_code": base, "hexes": c, "demand_map": res_dem} for c in clusters]
                with ProcessPoolExecutor(max_workers=4) as exc:
                    futures = [exc.submit(solve_cluster_worker, t) for t in tasks]
                    for f in as_completed(futures):
                        for p_data in f.result():
                            p_new = PartnerMetrics(**{**p_data, "allocations": [Allocation(**a) for a in p_data['allocations']]})
                            new_objs.append(p_new)
                            for a in p_new.allocations:
                                res_dem[a.hex_id] = max(0, res_dem[a.hex_id] - a.packages_assigned)

            # Ranking por volume (Prioridade Operacional)
            new_objs.sort(key=lambda x: x.total_load, reverse=True)
            for rank, p in enumerate(new_objs, 1):
                p.priority_rank = rank

            summary = {h: {"original": orig_dem[h], "residual": res_dem[h]} for h in orig_dem}
            self.reports.append(OptimizationReport(base, existing_objs, new_objs, summary))
        
        self.export_all()

    def export_all(self):
        dest = Path(Config.DEST_FOLDER)
        dest.mkdir(exist_ok=True)
        date_str = datetime.now().strftime("%d/%m/%Y")

        # 1. GEOJSON Estratégico
        features = []
        for r in self.reports:
            # Polígonos de demanda
            for h, info in r.demand_summary.items():
                boundary = h3.cell_to_boundary(h)
                coords = [[c[1], c[0]] for c in boundary]
                coords.append(coords[0])
                features.append({
                    "type": "Feature", "geometry": {"type": "Polygon", "coordinates": [coords]},
                    "properties": {"base": r.station_code, "residual": info["residual"], "total": info["original"]}
                })
            # Pontos dos parceiros
            for p in r.existing_partners + r.new_partners:
                lat, lng = h3.cell_to_latlng(p.origin_hex)
                props = {
                    "type": p.entity_type,
                    "Store Id": p.store_id if p.store_id else "New_Partner",
                    "cap suggestion": p.total_load,
                    "radius_suggestion": p.radius_m,
                    "priority": p.priority_rank,
                    
                }
                features.append({
                    "type": "Feature", "geometry": {"type": "Point", "coordinates": [lng, lat]},
                    "properties": props
                })
        
        with open(dest / "mapa_estratégico.geojson", "w") as f:
            json.dump({"type": "FeatureCollection", "features": features}, f)

        # 2. TXT para WhatsApp (Comercial)
        with open(dest / "rotas_prospeccao.txt", "w", encoding="utf-8") as f:
            for r in self.reports:
                new_ps = r.new_partners
                for i in range(0, len(new_ps), 4):
                    batch = new_ps[i:i+4]
                    f.write(f"📍 *ROTA DE PROSPECÇÃO: {r.station_code}*\n")
                    f.write(f"📅 *Data:* {date_str}\n")
                    f.write(f"🚀 *Objetivo:* {len(batch)} Novos Parceiros\n")
                    f.write("-" * 35 + "\n")

                    for p in batch:
                        lat, lng = h3.cell_to_latlng(p.origin_hex)
                        ceps = set()
                        for a in p.allocations:
                            ceps.update(self.hex_to_ceps.get(a.hex_id, set()))
                        
                        ceps_list = sorted(list(ceps))[:6]
                        maps_link = f"https://www.google.com/maps?q={lat},{lng}"
                        diag = get_ai_diagnostic(p, len(ceps))

                        f.write(f"*OPORTUNIDADE (Prioridade {p.priority_rank})*\n")
                        f.write(f"• *Volume:* {p.total_load} pacotes/dia\n")
                        f.write(f"• *Perfil:* Raio {p.radius_m}m\n")
                        f.write(f"• *CEPs Alvo:* {', '.join(ceps_list)}\n")
                        f.write(f"📍 *Ponto:* {maps_link}\n")
                        f.write(f"💡 {diag}\n\n")
                    
                    f.write("-" * 35 + "\n\n")
        
        print(f"✅ Processamento Concluído! Arquivos em: {Config.DEST_FOLDER}")

if __name__ == "__main__":
    try:
        service = OptimizationService()
        service.run()
    except Exception:
        traceback.print_exc()