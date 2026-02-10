import json, h3, math, traceback
import pandas as pd
import numpy as np
import config as configuration
import csv
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
    CLUSTER_PER_STATION = configuration.CLUSTER_PER_STATION
    BASE_PRIORITY = {
        "DMG2": 1,
        "DBH5": 2,
        "DSP2": 3,
        "DSP4": 4,
        "DBR9": 5
    }
    PARTNERS_TO_EVALUATE = [
    "2014644401",
    "3857592834",
    "8064721854",
    "9481632038",
    "6996006349",
    "7916093446",
    "7576302490",
    "6747547249",
    "7242932102",
    "2805526155",
    "4698881022",
    "1041349648",
    "4043030504",
    "6625854445",
    "3661723568",
    "5784431295",
    "3177448268",
    "7568619126",
    "6801124067",
    "6788598219",
    "6886216756",
    "9909851555",
    "7511333617",
    "3138958968",
    "1427271126",
    "8481961104",
    "3575011138",
    "7126630871",
    "6135947075",
    "4546414567",
    "8259009430",
    "7402074332",
    "4016033739",
    "6345639425",
    "5259756912",
    "6544149469",
    "8447167307",
    "3602880562",
    "5683660133",
    "6132058026",
    "7045795919",
    "1755959459",
    "8167237664",
    "2326965334",
    "5054036689",
    "7084939417",
    "7389914581",
    "1125392880",
    "9476037117",
    "3773904830",
    "4513763702",
    "4862296245",
    "4290494023",
    "9757559519",
    "3244551105",
    "7509939829",
    "6383652230",
    "9869932492",
    "4232493531",
    "5916819743",
    "5836606811",
    "9523930283",
    "1430775187",
    "3447629085",
    "1005193921",
    "7886989484",
    "4931919201",
    "2755149565",
    "2671921159",
    "9820749867",
    "7478530907",
    "9239271304",
    "2849016064",
    "9510390499",
    "9729504760",
    "6271783995",
    "6748803438",
    "8956610920",
    "7113486670",
    "3899335041",
    "6540332691",
    "8289278548",
    "9405287197",
    "5621700235",
    "6230445822",
    "7474130054",
    "4630617729",
    "8985951644",
    "2053196071",
    "9119427541",
    "4662396800",
    "7286817261",
    "4677998905",
    "6067001624",
    "2157925422",
    "5138453833",
    "6032760566",
    "4515159681",
    "1854996802",
    "8053613574",
    "2237747131",
    "4292852949",
    "8523916904",
    "5927770520",
    "9012475079",
    "2111610464",
    "3723882901",
    "1143481426",
    "2337263859",
    "1766668243",
    "6552612349",
    "3616539221",
    "5803762263",
    "2022807224",
    "1099542555",
    "5405521946",
    "5681624260",
    "7730360958",
    "6428886181",
    "6705512868",
    "6478386881",
    "3544782975",
    "7511341206",
    "4747933998",
    "5441529885",
    "3248886658",
    "9963213908",
    "7642142507",
    "5192704648",
    "7816137321",
    "4111778967",
    "7302375194",
    "1782224274",
    "9589865235",
    "6429060327",
    "9526911236",
    "4055116937",
    "3135532006",
    "8267671656",
    "6586500496",
    "9226773826",
    "3367800093",
    "3120737321",
    "5236201354",
    "7474636239",
    "4831369782",
    "9688618768",
    "6697283815",
    "9757410356",
    "7782756174",
    "4741403726",
    "2342562201",
    "6392091103",
]

@dataclass
class Allocation:
    hex_id: str
    packages_assigned: int
    
@dataclass
class BaseMetrics:
    total_demand: int
    existing_absorbed: int
    prospect_reserved: int
    inactive_reserved: int
    new_allocated: int
    residual: int
    active_partners_count: int
    onboarding_partners_count: int
    inactive_partners_count: int
    vetting_partners_count: int
    new_partners_count: int
    avg_load: float
    avg_radius: float
    cluster_count: int
    avg_partners_per_cluster: float

@dataclass
class ClusterMetrics:
    base: str
    cluster_name: str
    total_demand: int
    total_expected_partners: int
    active_partners: int
    onboarding_partners: int
    prospects_to_approve: int
    inactives_to_reactivate: int
    new_partners: int
    attainment_percentage: float

@dataclass
class PartnerMetrics:
    origin_hex: str
    station_code: str
    radius_s: int
    capacity_s: int
    entity_type: str 
    status: str
    partner_name: str = ""
    decision: str = ""
    cluster_name: str = "N/A"
    lat: str = ""
    lon: str = ""
    popup: str = ""
    tooltip: str = ""
    telefone: str = ""
    salesforce_id: str = ""
    jurisdiction_type: str = ""
    launch_date: str = ""
    exitedDate: str = ""
    decision_status: str = ""
    supply_run: str = ""
    hub_delivey_initiatives: str = ""
    HCP_rate_card: str = ""
    HCP_host_partner: str = ""
    zip_code: str = ""
    city: str = ""
    store_id: Optional[str] = None
    radius_a: Optional[int] = None
    capacity_a: Optional[int] = None
    allocations: List[Allocation] = field(default_factory=list)

    @property
    def total_load(self) -> int:
        return sum(a.packages_assigned for a in self.allocations)

@dataclass
class OptimizationReport:
    station_code: str
    existing_partners: List[PartnerMetrics]
    inactive_partners: List[PartnerMetrics]
    prospect_partners: List[PartnerMetrics]
    new_partners: List[PartnerMetrics]
    demand_summary: Dict[str, Dict]
    hex_to_cluster: Dict[str, str]
    base_metrics: BaseMetrics
    cluster_metrics: Dict[str, ClusterMetrics] = field(default_factory=dict)

# ========================================
# WORKER DO SOLVER
# ========================================
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
                    idx = (best_seed, r['radius_s'], k)
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
                penalty = next(rad['penalty'] for rad in Config.RADII if rad['radius_s'] == idx_x[1])
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
                                "cluster_name": cluster_name, "radius_s": idx_x[1], 
                                "capacity_s": idx_x[2], "entity_type": "NEW", "allocations": allocs
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
        self.hex_to_base: Dict[str, str] = {}
        
    def _resolve_hex_overlaps(self, df: pd.DataFrame) -> pd.DataFrame:
       
        print(f"[{datetime.now()}] Resolvendo overlaps de hexágonos entre bases...")

        # Adicionar coluna de prioridade
        df['priority'] = df['station_code'].map(Config.BASE_PRIORITY).fillna(999)

        # Identificar duplicatas e manter apenas a linha com maior prioridade (menor número)
        df_sorted = df.sort_values('priority')
        df_clean = df_sorted.drop_duplicates(subset='hex', keep='first')

        # Calcular estatísticas de overlaps removidos
        n_removed = len(df) - len(df_clean)

        if n_removed == 0:
            print(f"   ✅ Nenhum overlap detectado!")
            df_clean = df_clean.drop('priority', axis=1)
            return df_clean

        print(f"   ⚠️  Detectados overlaps em {n_removed} registros")

        # Estatísticas detalhadas (opcional, pode comentar se não precisar)
        removed_df = df[~df.index.isin(df_clean.index)]
        if len(removed_df) > 0:
            overlap_stats = removed_df.groupby('station_code').size().to_dict()
            print(f"   📊 Registros removidos por base:")
            for base, count in sorted(overlap_stats.items(), key=lambda x: x, reverse=True):
                print(f"      • {base}: {count} registros")

        print(f"   ✅ Overlaps resolvidos com sucesso!")

        # Remover coluna auxiliar
        df_clean = df_clean.drop('priority', axis=1).reset_index(drop=True)

        return df_clean

    def _load_data(self):
        print(f"[{datetime.now()}] Carregando dados...")
        df = pd.read_csv(Config.BASE_PACKAGES)
        df['cep'] = df['cep'].astype(str).str.replace(r'\D', '', regex=True).str.zfill(8)
        df["hex"] = [h3.latlng_to_cell(la, lo, Config.H3_RES) for la, lo in zip(df.latitude, df.longitude)]
        
        """df = self._resolve_hex_overlaps(df)"""
        
        self.hex_to_ceps = df.groupby('hex')['cep'].apply(set).to_dict()
        days = pd.to_datetime(df.plan_date).nunique() or 1
        self.demand_df = df.groupby(["station_code", "hex"]).size().reset_index(name="avg_demand")
        self.demand_df["avg_demand"] = (self.demand_df["avg_demand"] / days).round(0).astype(int)
        self.hex_to_base = dict(zip(self.demand_df.hex, self.demand_df.station_code))
        
        with open(Config.BASE_PARTNERS, "r", encoding="utf-8") as f:
            p_data = json.load(f)["allMarkerData"]
        self.partners_df = pd.DataFrame(p_data)
        self.partners_df['exitedDate'] = pd.to_datetime(self.partners_df.get('exitedDate'), errors='coerce')
        self.partners_df.rename(columns={"delivery_station": "station_code"}, inplace=True)
        self.partners_df.rename(columns={"name": "partner_name"}, inplace=True)
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
    
    def _generate_operational_clusters_balanced(self, station_code: str, final_partners: List[PartnerMetrics], clusters_per_base: Dict[str, int]) -> tuple[Dict[str, ClusterMetrics], Dict[str, str]]:
        
        if not final_partners:
            return {}, {}
        
        n_clusters = clusters_per_base.get(station_code, 1)
        n_partners = len(final_partners)
        
        print(f"   🔧 Criando {n_clusters} clusters balanceados para {n_partners} parceiros...")
        
        # ===== FASE 1: Clusterização da Demanda =====
        hex_demand_map = {}
        for p in final_partners:
            for alloc in p.allocations:
                hex_demand_map[alloc.hex_id] = hex_demand_map.get(alloc.hex_id, 0) + alloc.packages_assigned
        
        if not hex_demand_map:
            print(f"   ⚠️  Nenhum hexágono com demanda para {station_code}")
            return {}, {}
        
        # Preparar dados para KMeans ponderado
        hex_coords_weighted = []
        hex_ids = []
        weights = []
        
        for hex_id, demand in hex_demand_map.items():
            lat, lon = h3.cell_to_latlng(hex_id)
            hex_coords_weighted.append([lat, lon])
            hex_ids.append(hex_id)
            weights.append(demand)
        
        hex_coords_weighted = np.array(hex_coords_weighted)
        weights = np.array(weights)
        
        # KMeans nos hexágonos de demanda
        kmeans_demand = KMeans(n_clusters=n_clusters, random_state=42, n_init=10).fit(
            hex_coords_weighted, sample_weight=weights
        )
        
        # Centroides dos clusters baseados na demanda
        cluster_centroids = kmeans_demand.cluster_centers_
        
        # ===== FASE 2: Atribuição Balanceada de Parceiros com OR-Tools =====
        model = cp_model.CpModel()
        
        # Variáveis: x[p][c] = 1 se parceiro p é atribuído ao cluster c
        x = {}
        for p_idx in range(n_partners):
            for c_idx in range(n_clusters):
                x[(p_idx, c_idx)] = model.NewBoolVar(f'x_p{p_idx}_c{c_idx}')
        
        # Restrição 1: Cada parceiro deve ser atribuído a exatamente 1 cluster
        for p_idx in range(n_partners):
            model.Add(sum(x[(p_idx, c_idx)] for c_idx in range(n_clusters)) == 1)
        
        # Restrição 2: Balanceamento de parceiros por cluster
        min_partners_per_cluster = n_partners // n_clusters
        max_partners_per_cluster = min_partners_per_cluster + (1 if n_partners % n_clusters > 0 else 0)
        
        for c_idx in range(n_clusters):
            cluster_size = sum(x[(p_idx, c_idx)] for p_idx in range(n_partners))
            model.Add(cluster_size >= min_partners_per_cluster)
            model.Add(cluster_size <= max_partners_per_cluster)
        
        # Função Objetivo: Minimizar distância total ponderada pela demanda
        distances = np.zeros((n_partners, n_clusters))
        partner_weights = []
        
        for p_idx, partner in enumerate(final_partners):
            p_lat, p_lon = h3.cell_to_latlng(partner.origin_hex)
            partner_demand = partner.total_load
            partner_weights.append(partner_demand)
            
            for c_idx in range(n_clusters):
                c_lat, c_lon = cluster_centroids[c_idx]
                # Distância haversine simplificada (em graus)
                dist = np.sqrt((p_lat - c_lat)**2 + (p_lon - c_lon)**2)
                distances[p_idx, c_idx] = dist
        
        # Normalizar distâncias e converter para inteiros (para OR-Tools)
        max_dist = distances.max()
        if max_dist > 0:
            distances_normalized = (distances / max_dist * 10000).astype(int)
        else:
            distances_normalized = distances.astype(int)
        
        # Termos da função objetivo
        obj_terms = []
        for p_idx in range(n_partners):
            for c_idx in range(n_clusters):
                # Ponderar pela demanda do parceiro
                weight = max(1, partner_weights[p_idx] // 10)
                cost = distances_normalized[p_idx, c_idx] * weight
                obj_terms.append(cost * x[(p_idx, c_idx)])
        
        model.Minimize(sum(obj_terms))
        
        # Resolver
        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = 30
        solver.parameters.log_search_progress = False
        
        status = solver.Solve(model)
        
        if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            print(f"   ⚠️  Solver não encontrou solução ótima. Usando KMeans simples como fallback.")
            # Fallback: usar KMeans simples nos parceiros
            partner_coords = np.array([h3.cell_to_latlng(p.origin_hex) for p in final_partners])
            kmeans_partners = KMeans(n_clusters=n_clusters, random_state=42, n_init=10).fit(partner_coords)
            partner_assignments = kmeans_partners.labels_
        else:
            # Extrair atribuições da solução
            partner_assignments = []
            for p_idx in range(n_partners):
                for c_idx in range(n_clusters):
                    if solver.Value(x[(p_idx, c_idx)]) == 1:
                        partner_assignments.append(c_idx)
                        break
        
        # ===== FASE 3: Organizar Resultados =====
        clusters = {}
        for p_idx, cluster_label in enumerate(partner_assignments):
            clusters.setdefault(cluster_label, []).append(final_partners[p_idx])
        
        # Criar métricas e atribuir nomes aos clusters
        cluster_metrics = {}
        hex_to_cluster = {}
        
        for label, partners in clusters.items():
            cluster_name = f"{station_code}_C{label + 1}"
            
            # Atribuir nome do cluster aos parceiros
            for p in partners:
                p.cluster_name = cluster_name
                # Mapear hexágonos deste parceiro ao cluster
                for alloc in p.allocations:
                    hex_to_cluster[alloc.hex_id] = cluster_name
            
            # Calcular métricas do cluster
            total_demand = sum(p.total_load for p in partners)
            active_count = sum(1 for p in partners if p.status == "Active")
            onboarding_count = sum(1 for p in partners if p.status == "Onboarding")
            prospects_count = sum(1 for p in partners if p.entity_type == "PROSPECT" and p.decision == "Seguir cadastro")
            inactives_count = sum(1 for p in partners if p.entity_type == "INACTIVE_EXITED" and p.decision == "Reativar cadastro")
            new_count = sum(1 for p in partners if p.entity_type == "NEW PARTNER")
            
            total_expected = len(partners)
            attainment = (active_count / total_expected * 100) if total_expected > 0 else 0
            
            cluster_metrics[cluster_name] = ClusterMetrics(
                base=station_code,
                cluster_name=cluster_name,
                total_demand=total_demand,
                total_expected_partners=total_expected,
                active_partners=active_count,
                onboarding_partners=onboarding_count,
                prospects_to_approve=prospects_count,
                inactives_to_reactivate=inactives_count,
                new_partners=new_count,
                attainment_percentage=attainment
            )
        
        # Estatísticas de balanceamento
        cluster_sizes = [len(partners) for partners in clusters.values()]
        print(f"   ✅ Clusters criados: {cluster_sizes}")
        print(f"   📊 Balanceamento: min={min(cluster_sizes)}, max={max(cluster_sizes)}, diff={max(cluster_sizes)-min(cluster_sizes)}")
        
        return cluster_metrics, hex_to_cluster
    
    
    def _allocate_existing_by_status(self, base, res_dem, target_status):
        results = []
        subset = self.partners_df[(self.partners_df.status == target_status) & (self.partners_df.station_code == base)]

        for _, p in subset.iterrows():
            for r in Config.RADII:
                in_r = [h for h in h3.grid_disk(p.origin_hex, r["hex_distance"]) if res_dem.get(h, 0) > 0]
                allocs, total = [], 0
                for h in sorted(in_r, key=lambda x: h3.grid_distance(x, p.origin_hex)):
                    take = min(res_dem[h], Config.MAX_CAP - total)
                    if take > 0: allocs.append(Allocation(hex_id=h, packages_assigned=take))
                    total += take
                if total >= Config.MIN_CAP:
                        results.append(PartnerMetrics(
                            origin_hex=p.origin_hex,
                            station_code=base,
                            radius_a=p.radius, 
                            radius_s=r["radius_s"],
                            capacity_a=p.capacity,
                            capacity_s=Config.MAX_CAP, 
                            entity_type="EXISTING", 
                            status=target_status, 
                            store_id=str(p.store_id),
                            partner_name=str(p.partner_name), 
                            decision="No optimization suggestions" if p.radius == r["radius_s"] and p.capacity == Config.MAX_CAP else "Optimization suggested",
                            lat=str(p.lat),
                            lon=str(p.lon),
                            popup=str(p.popup),
                            tooltip=str(p.tooltip),
                            cluster_name="N/A",
                            telefone=str(p.telefone),
                            salesforce_id=str(p.salesforce_id),
                            jurisdiction_type=str(p.jurisdiction_type),
                            launch_date=str(p.launch_date),
                            exitedDate=str(p.exitedDate),
                            decision_status=str(p.decision_status),
                            supply_run=str(p.supply_run),
                            hub_delivey_initiatives=str(p.hub_delivey_initiatives),
                            HCP_rate_card=str(p.HCP_rate_card),
                            HCP_host_partner=str(p.HCP_host_partner),
                            zip_code=str(p.zip_code),
                            city=str(p.city),
                            allocations=allocs
                        ))
                        for a in allocs: res_dem[a.hex_id] -= a.packages_assigned
                        break
        return results
    
    def _evaluate_prospects(self, res_dem, hex_to_cluster):
        results = []
        subset = self.partners_df[self.partners_df.status == "Prospect"]
        for _, p in subset.iterrows():
            prospect = p.partner_name
            base = self.hex_to_base.get(p.origin_hex)
            if not base:
                decision = "Fora da área de atuacao"
                sug_rad, sug_cap, allocs = 0, 0, []
            else:
                if p.origin_hex not in self.demand_df[self.demand_df.station_code == base].hex.values:
                    decision = "Fora da área de atuacao"
                    sug_rad, sug_cap, allocs = 0, 0, []
                else:
                    decision = ""
                    sug_rad, sug_cap, allocs = 0, 0, []
                    for r in Config.RADII:
                        in_r = [h for h in h3.grid_disk(p.origin_hex, r["hex_distance"]) if res_dem.get(h, 0) > 0]
                        temp_total = sum(res_dem[h] for h in in_r)
                        if temp_total >= Config.MIN_CAP:
                            decision = "Seguir cadastro"
                            sug_rad = r["radius_s"]
                            sug_cap = Config.MAX_CAP if temp_total >= Config.MAX_CAP else Config.MIN_CAP
                            current_fill = 0
                            for h in sorted(in_r, key=lambda x: h3.grid_distance(x, p.origin_hex)):
                                take = min(res_dem[h], sug_cap - current_fill)
                                if take > 0:
                                    allocs.append(Allocation(h, take))
                                    res_dem[h] -= take
                                    current_fill += take
                            break
                    if not decision:
                        decision = "Baixo volume na area de atuacao"

            results.append(
                PartnerMetrics(
                    origin_hex=p.origin_hex,
                    station_code=base if base else "",
                    radius_a=p.radius,
                    radius_s=sug_rad,
                    capacity_a=p.capacity,
                    capacity_s=sug_cap,
                    entity_type="PROSPECT",
                    status=str(p.status),
                    store_id=str(p.store_id),
                    partner_name=prospect,
                    decision=decision,
                    lat=str(p.lat),
                    lon=str(p.lon),
                    popup=str(p.popup),
                    tooltip=str(p.tooltip),
                    cluster_name=hex_to_cluster.get(p.origin_hex, "N/A"),
                    telefone=str(p.telefone),
                    salesforce_id=str(p.salesforce_id),
                    jurisdiction_type=str(p.jurisdiction_type),
                    launch_date=str(p.launch_date),
                    exitedDate=str(p.exitedDate),
                    decision_status=str(p.decision_status),
                    supply_run=str(p.supply_run),
                    hub_delivey_initiatives=str(p.hub_delivey_initiatives),
                    HCP_rate_card=str(p.HCP_rate_card),
                    HCP_host_partner=str(p.HCP_host_partner),
                    zip_code=str(p.zip_code),
                    city=str(p.city),
                    allocations=allocs
                )
            )
        return results
    
    def _evaluate_inactive_exited(self, base, res_dem, hex_to_cluster):
        results = []
        cutoff = pd.to_datetime("2026-01-01")
        subset = self.partners_df[
            (
                (self.partners_df.status == "Inactive") |
                (
                    (self.partners_df.status == "Exited") &
                    (self.partners_df.decision_status == "Exited - Regretted") &
                    (self.partners_df.exitedDate >= cutoff)
                ) 
            ) &
            (self.partners_df.station_code == base) &
            (self.partners_df.jurisdiction_type == "Shared")
        ]
        
        for _, p in subset.iterrows():
            decision = ""
            partner_name = p.partner_name
            sug_rad, sug_cap, allocs = 0, 0, []

            if p.origin_hex not in self.demand_df[self.demand_df.station_code == base].hex.values:
                decision = "Fora da área de atuacao"
            else:
                for r in Config.RADII:
                    in_r = [h for h in h3.grid_disk(p.origin_hex, r["hex_distance"]) if res_dem.get(h, 0) > 0]
                    temp_total = sum(res_dem[h] for h in in_r)
                    
                    if temp_total >= Config.MIN_CAP:
                        decision = "Reativar cadastro"
                        sug_rad = r["radius_s"]
                        sug_cap = Config.MAX_CAP if temp_total >= Config.MAX_CAP else Config.MIN_CAP
                        current_fill = 0
                        for h in sorted(in_r, key=lambda x: h3.grid_distance(x, p.origin_hex)):
                            take = min(res_dem[h], sug_cap - current_fill)
                            if take > 0:
                                allocs.append(Allocation(h, take))
                                res_dem[h] -= take
                                current_fill += take
                        break
                if not decision:
                    decision = "Fora da área de atuacao"

            results.append(PartnerMetrics(
                origin_hex=p.origin_hex,
                station_code=base if base else "",
                radius_a=p.radius,
                radius_s=sug_rad,
                capacity_a=p.capacity,
                capacity_s=sug_cap,
                entity_type="INACTIVE_EXITED",
                status=str(p.status),
                store_id=str(p.store_id),
                partner_name=str(partner_name),
                decision=decision,
                lat=str(p.lat),
                lon=str(p.lon),
                popup=str(p.popup),
                tooltip=str(p.tooltip),
                cluster_name=hex_to_cluster.get(p.origin_hex, "N/A"),
                telefone=str(p.telefone),
                salesforce_id=str(p.salesforce_id),
                jurisdiction_type=str(p.jurisdiction_type),
                launch_date=str(p.launch_date),
                exitedDate=str(p.exitedDate),
                decision_status=str(p.decision_status),
                supply_run=str(p.supply_run),
                hub_delivey_initiatives=str(p.hub_delivey_initiatives),
                HCP_rate_card=str(p.HCP_rate_card),
                HCP_host_partner=str(p.HCP_host_partner),
                zip_code=str(p.zip_code),
                city=str(p.city),
                allocations=allocs
            ))

        return results

    def run(self):
        self._load_data()
        clusters_per_base = Config.CLUSTER_PER_STATION

        for base in self.demand_df.station_code.unique():
            print(f"\n--- 🚀 OTIMIZANDO BASE: {base} ---")
            orig_dem = self.demand_df[self.demand_df.station_code == base].set_index("hex")["avg_demand"].to_dict()
            res_dem = dict(orig_dem)

            p1 = self._allocate_existing_by_status(base, res_dem, "Active")
            p2 = self._allocate_existing_by_status(base, res_dem, "Onboarding")
            p3 = self._allocate_existing_by_status(base, res_dem, "BG Checks")

            islands, hex_to_cluster = self._find_neighborhood_clusters(res_dem, base)
            
            p4 = self._evaluate_inactive_exited(base, res_dem, hex_to_cluster)
            p5 = self._evaluate_prospects(res_dem, hex_to_cluster)
            
            p6 = []
            if islands:
                tasks = [{"station_code": base, "cluster_name": hex_to_cluster[h[0]], "hexes": h, "demand_map": res_dem} for h in islands]
                with ProcessPoolExecutor(max_workers=10) as exc:
                    futures = [exc.submit(solve_island_exhaustion_worker, t) for t in tasks]
                    for f in as_completed(futures):
                        for p_data in f.result():
                            lat = h3.cell_to_latlng(p_data['origin_hex'])[0]
                            lon = h3.cell_to_latlng(p_data['origin_hex'])[1]
                            p_new = PartnerMetrics(**{**p_data, "lat": lat, "lon": lon, "decision": "Prospect a new partner","station_code": base, "entity_type": "NEW PARTNER", "status": "New", "allocations": [Allocation(**a) for a in p_data['allocations']]})
                            p6.append(p_new)
                            for a in p_new.allocations: res_dem[a.hex_id] = max(0, res_dem.get(a.hex_id, 0) - a.packages_assigned)

            # Consolidar todos os parceiros que farão parte da malha final (F1 a F6)
            # Filtramos apenas os que tiveram decisão positiva ou já são ativos
            final_partners_list = (
                p1 + p2 + p3 + 
                [p for p in p4 if p.decision == "Reativar cadastro"] + 
                [p for p in p5 if p.decision == "Seguir cadastro"] + 
                p6
            )

            # Gerar clusters operacionais de no máximo 40 parceiros
            cluster_metrics_dict, op_hex_to_cluster = self._generate_operational_clusters_balanced(base, final_partners_list, clusters_per_base)

            # Atribuição Universal: Todo hexágono deve pertencer a um cluster operacional
            if op_hex_to_cluster:
                # Pegamos os centroides de cada cluster operacional para atribuição por proximidade
                cluster_centroids = {}
                for p in final_partners_list:
                    c_name = p.cluster_name
                    if c_name not in cluster_centroids:
                        cluster_centroids[c_name] = []
                    cluster_centroids[c_name].append(h3.cell_to_latlng(p.origin_hex))
                
                # Média das coordenadas para o centroide do cluster
                for c_name in cluster_centroids:
                    lats, lons = zip(*cluster_centroids[c_name])
                    cluster_centroids[c_name] = (np.mean(lats), np.mean(lons))

                for h in orig_dem.keys():
                    if h in op_hex_to_cluster:
                        hex_to_cluster[h] = op_hex_to_cluster[h]
                    else:
                        centroid_hexes = {c: h3.latlng_to_cell(*cluster_centroids[c], Config.H3_RES) for c in cluster_centroids}
                        best_c = min(
                            centroid_hexes.keys(),
                            key=lambda c: h3.grid_distance(h, centroid_hexes[c])
                        )
                        hex_to_cluster[h] = best_c
            else:
                # Caso não haja parceiros na base, mantém o nome da ilha ou "Sem Cluster"
                for h in orig_dem.keys():
                    hex_to_cluster[h] = hex_to_cluster.get(h, f"{base}_UNASSIGNED")
                
            total_atendido = sum(p.total_load for p in p1)
            total_prospects_reserva = sum(p.total_load for p in [p for p in p5 if p.decision == "Seguir cadastro"])
            total_inativos_reserva = sum(p.total_load for p in [p for p in p4 if p.decision == "Reativar cadastro"])
            total_novas_vagas = sum(p.total_load for p in p6)
            
            m = BaseMetrics(
                total_demand=sum(orig_dem.values()),
                existing_absorbed=total_atendido,
                prospect_reserved=total_prospects_reserva,
                inactive_reserved=total_inativos_reserva,
                new_allocated=total_novas_vagas,
                residual=sum(res_dem.values()),
                active_partners_count=len(p1),
                onboarding_partners_count=len(p2),
                inactive_partners_count=len([p for p in p4 if p.decision == "Reativar cadastro"]),
                vetting_partners_count=len(p3),
                new_partners_count=len(p6),
                avg_load=(total_novas_vagas / len(p6)) if len(p6) > 0 else 0,
                avg_radius=(sum(p.radius_s for p in p6) / len(p6)) if len(p6) > 0 else 0,
                cluster_count=len(cluster_metrics_dict),
                avg_partners_per_cluster=(len(final_partners_list) / len(cluster_metrics_dict)) if len(cluster_metrics_dict) > 0 else 0
            )
                           
            report_base = OptimizationReport(
                station_code=base,
                existing_partners=p1 + p2 + p3,
                inactive_partners=p4,
                prospect_partners=p5,
                new_partners=p6,
                demand_summary={h: {"total": orig_dem[h], "residual": res_dem.get(h, 0)} for h in orig_dem},
                hex_to_cluster=hex_to_cluster,
                base_metrics=m
            )
            
            report_base.cluster_metrics = cluster_metrics_dict
            
            self.reports.append(report_base)            
            self._print_summary(base, p1, p2, p3, p4, p5, p6)
        
        self.export_strategic_results()
        self.executive_report()
        self.mkt_report()

    def _print_summary(self, base, p1, p2, p3, p4, p5, p6):
        print(f"✅ Base {base} Concluída:")
        print(f"   [F1] Ativos: {len(p1)} | [F2] Onboarding: {len(p2)} | [F3] BG Checks: {len(p3)}")
        print(f"   [F4] Inativos e Exited Validados: {len([x for x in p4 if x.decision == 'Reativar cadastro'])}")
        print(f"   [F5] Leads Validados: {len([x for x in p5 if x.decision == 'Seguir cadastro'])}")
        print(f"   [F6] Novos Parceiros: {len(p6)}")

    def executive_report(self, filename="RELATORIO_EXECUTIVO.txt"):
        dest = Path(Config.DEST_FOLDER)
        dest.mkdir(exist_ok=True)
        path = dest / filename

        with open(path, "w", encoding="utf-8") as f:
            f.write(f"RELATÓRIO EXECUTIVO DE OTIMIZAÇÃO - GERADO EM {datetime.now().strftime('%d/%m/%Y %H:%M')}\n")
            f.write("="*80 + "\n")

            for r in self.reports:
                m = r.base_metrics

                # Cálculos para a base
                total_parceiros_esperados = (
                    m.active_partners_count +
                    m.onboarding_partners_count +
                    m.vetting_partners_count +
                    m.inactive_partners_count +
                    m.new_partners_count
                )

                parceiros_ativos = m.active_partners_count
                attainment = (parceiros_ativos / total_parceiros_esperados * 100) if total_parceiros_esperados > 0 else 0

                total_pacotes_cluster = m.total_demand
                pacotes_atendidos_ativos = m.existing_absorbed

                f.write(f"BASE: {r.station_code}\n")
                f.write(f"{'-'*80}\n")
                f.write(f"  - Quantidade de Clusters:                    {m.cluster_count}\n")
                f.write(f"  - Volume Total de Pacotes:                   {total_pacotes_cluster:,} pacotes\n")
                f.write(f"  - Quantidade Total de Parceiros esperados:   {total_parceiros_esperados}\n")
                f.write(f"  - Quantidade Total de Parceiros Ativos:      {parceiros_ativos}\n")
                f.write(f"  - % de Attainment:                           {attainment:.1f}%\n")
                f.write(f"  - Total de Pacotes Atendidos (Ativos):       {pacotes_atendidos_ativos:,} pacotes\n")
                f.write(f"{'-'*80}\n")

                # Detalhamento por cluster usando cluster_metrics
                f.write(f"DETALHAMENTO POR CLUSTER:\n")

                # Usar o novo cluster_metrics do report
                if hasattr(r, 'cluster_metrics') and r.cluster_metrics:
                    for cluster_name, cluster_data in sorted(r.cluster_metrics.items()):
                        f.write(f"  Cluster: {cluster_name}\n")
                        f.write(f"    - Quantidade Total de Parceiros:           {cluster_data.total_expected_partners}\n")
                        f.write(f"        • Ativos:                              {cluster_data.active_partners}\n")
                        f.write(f"        • Onboarding:                          {cluster_data.onboarding_partners}\n")
                        f.write(f"        • Prospects a Aprovar:                 {cluster_data.prospects_to_approve}\n")
                        f.write(f"        • Inativos a Reativar:                 {cluster_data.inactives_to_reactivate}\n")
                        f.write(f"        • Novos Parceiros:                     {cluster_data.new_partners}\n")
                        f.write(f"    - Volume Total de Demanda:                 {cluster_data.total_demand:,} pacotes\n")
                        f.write(f"    - % de Attainment:                         {cluster_data.attainment_percentage:.1f}%\n")
                else:
                    f.write("  Nenhum cluster disponível para esta base.\n")

                f.write("="*80 + "\n")

        print(f"✅ Relatório executivo salvo em: {path}")


    def mkt_report(self, filename="RELATÓRIO_MKT.txt"):
        dest = Path(Config.DEST_FOLDER)
        dest.mkdir(exist_ok=True)
        path = dest / filename

        with open(path, "w", encoding="utf-8") as f:
            f.write(f"RELATORIO DE MARKETING - GERADO EM {datetime.now().strftime('%d/%m/%Y %H:%M')}\n")
            f.write("="*80 + "\n")

            for r in self.reports:
                m = r.base_metrics
                f.write(f"📍 UNIDADE OPERACIONAL: {r.station_code}\n")
                f.write(f"{'-'*40}\n")
                f.write(f"RESUMO GERAL:\n")
                f.write(f"  - Quantidade de Clusters:        {m.cluster_count}\n")
                f.write(f"  - Média de parceiros/cluster:    {m.avg_partners_per_cluster:.1f}\n")
                f.write(f"  - Quantidade de Vagas (F6):      {m.new_partners_count} vagas\n")
                f.write(f"  - Média de pacotes por vaga:     {m.avg_load:.1f} pacotes\n")
                f.write(f"  - Média de Raio Proposto:        {m.avg_radius:.0f} m\n")
                f.write(f"{'-'*40}\n")

                # Detalhamento por cluster com métricas
                if hasattr(r, 'cluster_metrics') and r.cluster_metrics:
                    f.write(f"DETALHAMENTO POR CLUSTER:\n")

                    # Ordenar clusters por demanda total
                    clusters_sorted = sorted(
                        r.cluster_metrics.items(), 
                        key=lambda x: x[1].total_demand, 
                        reverse=True
                    )
                    
                    for i, (cluster_name, cluster_data) in enumerate(clusters_sorted, 1):
                        f.write(f"  {i}º) {cluster_name}\n")
                        f.write(f"     - Demanda Total:              {cluster_data.total_demand:,} pacotes\n")
                        f.write(f"     - Total de Parceiros:         {cluster_data.total_expected_partners}\n")
                        f.write(f"     - Novos Parceiros (F6):       {cluster_data.new_partners}\n")
                        f.write(f"     - Prospects a Aprovar (F5):   {cluster_data.prospects_to_approve}\n")
                        f.write(f"     - Inativos a Reativar (F4):   {cluster_data.inactives_to_reactivate}\n")
                        f.write(f"     - % de Attainment:            {cluster_data.attainment_percentage:.1f}%\n")

                # Detalhamento das oportunidades de novos parceiros
                f.write(f"{'-'*40}\n")
                f.write(f"OPORTUNIDADES DE NOVOS PARCEIROS (F6):\n")

                clusters_stats = []
                for cn in set(p.cluster_name for p in r.new_partners):
                    pts = [p for p in r.new_partners if p.cluster_name == cn]
                    clusters_stats.append({
                        "name": cn, 
                        "vol": sum(p.total_load for p in pts), 
                        "pts": pts
                    })
                clusters_stats.sort(key=lambda x: x['vol'], reverse=True)
                
                for i, c in enumerate(clusters_stats, 1):
                    f.write(f"  {i}º) {c['name']} - Potencial: {c['vol']:,} pacotes - {len(c['pts'])} novos parceiros\n")
                    f.write(f"  Oportunidades neste cluster:\n")

                    oportunidades_ordenadas = sorted(c['pts'], key=lambda x: x.total_load, reverse=True)
                    for idx, p in enumerate(oportunidades_ordenadas, 1):
                        ceps_vaga = set()
                        for alloc in p.allocations:
                            ceps_vaga.update(self.hex_to_ceps.get(alloc.hex_id, []))
                        
                        lat, lng = h3.cell_to_latlng(p.origin_hex)
                        f.write(f"      • Oportunidade {idx}: {p.total_load} pacotes/dia | Raio: {p.radius_s}m\n")
                        f.write(f"        CEPs Alvo: {', '.join(list(ceps_vaga)[:10])}{'...' if len(ceps_vaga) > 10 else ''}\n")
                        f.write(f"        Google Maps: https://maps.google.com/maps?q={lat},{lng}\n")

                f.write("="*80 + "\n")

        print(f"✅ Relatório de marketing salvo em: {path}")


    def export_strategic_results(self):
        dest = Path(Config.DEST_FOLDER)
        dest.mkdir(exist_ok=True)
        
        # GEOJSON
        features = []
        for r in self.reports:
            # Hexágonos de demanda
            for h, info in r.demand_summary.items():
                boundary = h3.cell_to_boundary(h)
                coords = [[c[1], c[0]] for c in boundary]
                coords.append(coords[0])
                features.append({
                    "type": "Feature", 
                    "geometry": {"type": "Polygon", "coordinates": [coords]},
                    "properties": {
                        "delivery_station": r.station_code, 
                        "cluster": r.hex_to_cluster.get(h, "Ativo/Vazio"),
                        "demanda_total": info["total"],
                        "residual": info["residual"]
                    }
                })
            
            # Parceiros (todos os tipos)
            for p in r.existing_partners + r.new_partners + r.prospect_partners + r.inactive_partners:
                lat = p.lat
                lnt = p.lon
                partnerName = p.partner_name
                ceps_alocados = set()
                alloc_list_json = []
                
                for alloc in p.allocations:
                    ceps_alocados.update(self.hex_to_ceps.get(alloc.hex_id, []))
                    alloc_list_json.append({
                        "hex": str(alloc.hex_id), 
                        "pacotes": int(alloc.packages_assigned)
                    })
                
                # Propriedades base da otimização
                props = {
                    "store_id": str(p.store_id) if p.store_id else "",
                    "status": str(p.status),
                    "name": str(partnerName),
                    "type": str(p.entity_type), 
                    "decision": str(p.decision),
                    "station_code": str(p.station_code),
                    "cluster": str(p.cluster_name),
                    "lat": float(lat),
                    "lon": float(lnt),
                    "cap_suggestion": int(p.total_load),
                    "radius_suggestion": int(p.radius_s),
                    "top_5_ceps": list(ceps_alocados)[:5],
                    "allocations": alloc_list_json
                }
                
                # Enriquecimento com dados cadastrais
                if p.store_id and str(p.store_id) in self.partners_df['store_id'].astype(str).values:
                    p_info = self.partners_df[self.partners_df['store_id'].astype(str) == str(p.store_id)].iloc[0].to_dict()
                    
                    # Excluir campos pesados
                    for field in ["main_store_data", "overlap_data", "allocations", "eligible_packages", "partner_capacity", "ADV"]:
                        p_info.pop(field, None)

                    for k, v in p_info.items():
                        if k.lower() in ["name", "nome", "partner_name"] and props.get("name") not in ["N/A", "None", ""]:
                            continue  # Manter o nome já definido, que é mais amigável
                        if k not in props:  # Evitar sobrescrever campos já definidos
                            if pd.notna(v):
                                if isinstance(v, str):
                                    props[k] = v.strip()
                                else:
                                    props[k] = v if isinstance(v, (int, float, list, dict)) else str(v)

                features.append({
                    "type": "Feature",
                    "geometry": {"type": "Point", "coordinates": [lnt, lat]},
                    "properties": props
                })
        
        with open(dest / "optimization_data.geojson", "w", encoding="utf-8") as f: 
            json.dump({"type": "FeatureCollection", "features": features}, f, ensure_ascii=False, indent=2)
        
        print(f"✅ GeoJSON salvo em: {dest / 'optimization_data.geojson'}")

        # TXT ESTRATÉGICO
        with open(dest / "OPORTUNIDADES_ESTRATEGICAS.txt", "w", encoding="utf-8") as f:
            f.write(f"RELATÓRIO DE EXPANSÃO - GERADO EM {datetime.now().strftime('%d/%m/%Y %H:%M')}\n")
            f.write("="*80 + "\n")

            for r in self.reports:
                m = r.base_metrics
                f.write(f"📍 UNIDADE OPERACIONAL: {r.station_code}\n")
                f.write(f"{'-'*40}\n")
                f.write(f"RESUMO EXECUTIVO DA BASE:\n")
                f.write(f"  - Demanda Total da Base:         {m.total_demand:,} pacotes\n")
                f.write(f"  - Atendida (Ativos F1-F3):       {m.existing_absorbed:,} pacotes\n")
                f.write(f"  - Alocada p/ Inativos (F4):      {m.inactive_reserved:,} pacotes\n")
                f.write(f"  - Alocada p/ Leads (F5):         {m.prospect_reserved:,} pacotes\n")
                f.write(f"  - Alocada p/ Expansão (F6):      {m.new_allocated:,} pacotes\n")
                f.write(f"  - Gap Final (Não alocado):       {m.residual:,} pacotes\n")
                f.write(f"{'-'*40}\n")
                f.write(f"POTENCIAL DE NOVAS VAGAS (F6):\n")
                f.write(f"  - Quantidade de Clusters:        {m.cluster_count}\n")
                f.write(f"  - Média de parceiros/cluster:    {m.avg_partners_per_cluster:.1f}\n")
                f.write(f"  - Quantidade de Vagas:           {m.new_partners_count} vagas\n")
                f.write(f"  - Média de Pacotes/Vaga:         {m.avg_load:.1f} pacotes\n")
                f.write(f"  - Média de Raio Proposto:        {m.avg_radius:.0f} m\n")
                f.write(f"{'-'*40}\n")

                # Análise de Prospects
                prospects = [p for p in r.prospect_partners if p.decision == "Seguir cadastro"]
                if prospects:
                    f.write(f"📢 ANÁLISE DE LEADS (PROSPECTS):\n")
                    for p in prospects:
                        ceps_p = set()
                        for a in p.allocations:
                            ceps_p.update(self.hex_to_ceps.get(a.hex_id, []))
                        f.write(f"  • Cluster: {p.cluster_name} | Salesforce ID: {p.salesforce_id}\n")
                        f.write(f"    Sugerido: {p.total_load} pacotes (R:{p.radius_s}m) | CEPs: {', '.join(list(ceps_p)[:10])}\n")
                    f.write(f"{'-'*40}\n")

                # Análise de Inativos/Exited
                inativos = [p for p in r.inactive_partners if p.decision == "Reativar cadastro"]
                if inativos:
                    f.write(f"📢 ANÁLISE DE INATIVOS/EXITED AVALIADOS:\n")
                    for p in inativos:
                        ceps_p = set()
                        for a in p.allocations:
                            ceps_p.update(self.hex_to_ceps.get(a.hex_id, []))
                        f.write(f"  • Cluster: {p.cluster_name}\n")
                        f.write(f"    ID: {p.store_id}\n")
                        f.write(f"    Sugerido: {p.total_load} pacotes (R:{p.radius_s}m) | CEPs: {', '.join(list(ceps_p)[:10])}\n")
                    f.write(f"{'-'*40}\n")

                # Oportunidades por cluster
                clusters_stats = []
                for cn in set(p.cluster_name for p in r.new_partners):
                    pts = [p for p in r.new_partners if p.cluster_name == cn]
                    clusters_stats.append({
                        "name": cn, 
                        "vol": sum(p.total_load for p in pts), 
                        "pts": pts
                    })
                clusters_stats.sort(key=lambda x: x['vol'], reverse=True)

                f.write(f"🚀 OPORTUNIDADES PARA PROSPECÇÃO:\n")
                for i, c in enumerate(clusters_stats, 1):
                    f.write(f"  {i}º) {c['name']} - Potencial: {c['vol']:,} pacotes - {len(c['pts'])} novos parceiros\n")
                    f.write(f"  Oportunidades neste cluster:\n")
                    
                    oportunidades_ordenadas = sorted(c['pts'], key=lambda x: x.total_load, reverse=True)
                    for idx, p in enumerate(oportunidades_ordenadas, 1):
                        ceps_vaga = set()
                        for alloc in p.allocations:
                            ceps_vaga.update(self.hex_to_ceps.get(alloc.hex_id, []))
                        lat, lng = h3.cell_to_latlng(p.origin_hex)
                        f.write(f"      • Oportunidade {idx}: {p.total_load} pacotes/dia | Raio: {p.radius_s}m\n")
                        f.write(f"        CEPs Alvo: {', '.join(list(ceps_vaga)[:8])}{'...' if len(ceps_vaga) > 8 else ''}\n")
                        f.write(f"        Google Maps: https://maps.google.com/maps?q={lat},{lng}\n")

                f.write("="*80 + "\n")

        print(f"✅ Relatório estratégico salvo em: {dest / 'OPORTUNIDADES_ESTRATEGICAS.txt'}")

if __name__ == "__main__":
    try:
        OptimizationService().run()
        print(f"\n✅ Concluído com sucesso!")
    except: traceback.print_exc()