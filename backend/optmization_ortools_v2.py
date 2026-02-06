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
class PartnerMetrics:
    origin_hex: str
    station_code: str
    radius_s: int
    capacity_s: int
    entity_type: str 
    status: str
    name: str = ""
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
    base_metrics: Dict = field(default_factory=dict)

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

    def _load_data(self):
        print(f"[{datetime.now()}] Carregando dados...")
        df = pd.read_csv(Config.BASE_PACKAGES)
        df['cep'] = df['cep'].astype(str).str.replace(r'\D', '', regex=True).str.zfill(8)
        df["hex"] = [h3.latlng_to_cell(la, lo, Config.H3_RES) for la, lo in zip(df.latitude, df.longitude)]
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
    def _generate_operational_clusters(self, station_code, final_partners: List[PartnerMetrics], max_per_cluster=50):
        if not final_partners:
            return {}

        coords = [h3.cell_to_latlng(p.origin_hex) for p in final_partners]
        n_partners = len(final_partners)
        n_clusters = math.ceil(n_partners / max_per_cluster)

        # Primeira clusterização
        kmeans = KMeans(n_clusters=n_clusters, random_state=42, n_init=10).fit(coords)
        clusters = {}
        for i, p in enumerate(final_partners):
            label = kmeans.labels_[i]
            clusters.setdefault(label, []).append(p)

        # Pós-processamento: subdivide clusters grandes
        cluster_names = {}
        cluster_counter = 1
        for partners in clusters.values():
            if len(partners) <= max_per_cluster:
                cname = f"{station_code}_C{cluster_counter}"
                for p in partners:
                    p.cluster_name = cname
                    cluster_names[p.origin_hex] = cname
                cluster_counter += 1
            else:
                # Subdivide novamente
                n_sub = math.ceil(len(partners) / max_per_cluster)
                sub_coords = [h3.cell_to_latlng(p.origin_hex) for p in partners]
                sub_kmeans = KMeans(n_clusters=n_sub, random_state=42, n_init=5).fit(sub_coords)
                sub_clusters = {}
                for i, p in enumerate(partners):
                    sub_label = sub_kmeans.labels_[i]
                    sub_clusters.setdefault(sub_label, []).append(p)
                for sub_partners in sub_clusters.values():
                    cname = f"{station_code}_C{cluster_counter}"
                    for p in sub_partners:
                        p.cluster_name = cname
                        cluster_names[p.origin_hex] = cname
                    cluster_counter += 1

        return cluster_names
    
    
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
                            name=str(p.name), 
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
            prospect = p['name']
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
                    name=prospect,
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
                name=str(p.name),
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
            
            p_ativos = p1 + p2 + p3
            p_prospects_ok = [p for p in p5 if p.decision == "Seguir cadastro"]
            p_inativos_ok = [p for p in p4 if p.decision == "Reativar cadastro"]

            # Consolidar todos os parceiros que farão parte da malha final (F1 a F6)
            # Filtramos apenas os que tiveram decisão positiva ou já são ativos
            final_partners_list = (
                p1 + p2 + p3 + 
                [p for p in p4 if p.decision == "Reativar cadastro"] + 
                [p for p in p5 if p.decision == "Seguir cadastro"] + 
                p6
            )

            # Gerar clusters operacionais de no máximo 50 parceiros
            op_hex_to_cluster = self._generate_operational_clusters(base, final_partners_list, max_per_cluster=50)

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
                
            total_atendido = sum(p.total_load for p in p_ativos)
            total_prospects_reserva = sum(p.total_load for p in p_prospects_ok)
            total_inativos_reserva = sum(p.total_load for p in p_inativos_ok)
            total_novas_vagas = sum(p.total_load for p in p6)

            m = {
                "total_demand": sum(orig_dem.values()),
                "existing_absorbed": total_atendido,
                "prospect_reserved": total_prospects_reserva,
                "inactive_reserved": total_inativos_reserva,
                "new_allocated": total_novas_vagas,
                "residual": sum(res_dem.values()),
                "active_partners_count": len(p1),
                "onboarding_partners_count": len(p2),
                "inactive_partners_count": len(p_inativos_ok),
                "new_partners_count": len(p6),
                "avg_load": (total_novas_vagas / len(p6)) if len(p6) > 0 else 0,
                "avg_radius": (sum(p.radius_s for p in p6) / len(p6)) if len(p6) > 0 else 0,
                "cluster_count": len(set(op_hex_to_cluster.values())),
                "avg_partners_per_cluster": (len(p_ativos + p_prospects_ok + p_inativos_ok + p6) / len(set(op_hex_to_cluster.values()))) if len(set(op_hex_to_cluster.values())) > 0 else 0
            }                       
            report_base = OptimizationReport(
                station_code = base,
                existing_partners = p1 + p2 + p3,
                inactive_partners = p4,
                prospect_partners = p5,
                new_partners = p6,
                demand_summary = {h: {"total": orig_dem[h], "residual": res_dem.get(h, 0)} for h in orig_dem},
                hex_to_cluster = hex_to_cluster,
                base_metrics = m
            )
            self.reports.append(report_base)            
            self._print_summary(base, p1, p2, p3, p4, p5, p6)
        
        self.export_strategic_results()
        self.export_inactive_exited_report()
        self.executive_report()
        self.mkt_report()

    def _print_summary(self, base, p1, p2, p3, p4, p5, p6):
        print(f"✅ Base {base} Concluída:")
        print(f"   [F1] Ativos: {len(p1)} | [F2] Onboarding: {len(p2)} | [F3] BG Checks: {len(p3)}")
        print(f"   [F4] Inativos e Exited Validados: {len([x for x in p4 if x.decision == 'Reativar cadastro'])}")
        print(f"   [F5] Leads Validados: {len([x for x in p5 if x.decision == 'Seguir cadastro'])}")
        print(f"   [F6] Novos Parceiros: {len(p6)}")

    def export_strategic_results(self):
        dest = Path(Config.DEST_FOLDER); dest.mkdir(exist_ok=True)
        
        # GEOJSON
        features = []
        for r in self.reports:
            for h, info in r.demand_summary.items():
                boundary = h3.cell_to_boundary(h)
                coords = [[c[1], c[0]] for c in boundary]; coords.append(coords[0])
                features.append({
                    "type": "Feature", 
                    "geometry": {"type": "Polygon", "coordinates": [coords]},
                    "properties": {
                        "delivery_station": r.station_code, 
                        "cluster": r.hex_to_cluster.get(h, "Ativo/Vazio"),
                        "demanda total": info["total"],
                        "residual": info["residual"]
                    }
                })
            for p in r.existing_partners + r.new_partners + r.prospect_partners + r.inactive_partners:
                lat, lng = h3.cell_to_latlng(p.origin_hex)
                ceps_alocados = set()
                alloc_list_json = []
                for alloc in p.allocations:
                    ceps_alocados.update(self.hex_to_ceps.get(alloc.hex_id, []))
                    alloc_list_json.append({"hex": str(alloc.hex_id), "pacotes": int(alloc.packages_assigned)})
                
                # Propriedades Base da Otimização
                props = {
                        "store_id": str(p.store_id),
                        "status": str(p.status),
                        "name": str(p.name),
                        "type": str(p.entity_type), 
                        "decision": str(p.decision),
                        "station_code": str(p.station_code),
                        "cluster": str(p.cluster_name),
                        "lat": float(p.lat),
                        "lon": float(p.lon),
                        "cap_suggestion": int(p.total_load),
                        "radius_suggestion": int(p.radius_s),
                        "top_5_ceps": list(ceps_alocados)[:5],
                        "allocations": alloc_list_json
                    }
                
                # Enriquecimento com dados cadastrais do dados_mapa.json
                if p.store_id and p.store_id in self.partners_df['store_id'].values:
                    p_info = self.partners_df[self.partners_df['store_id'] == p.store_id].iloc[0].to_dict()
                    # Excluir campos pesados conforme solicitado
                    for field in ["main_store_data", "overlap_data", "allocations", "eligible_packages", "partner_capacity", "ADV"]:
                        p_info.pop(field, None)
                    # Mesclar informações (preservando as da otimização em caso de conflito)
                    for k, v in p_info.items():
                        if k not in props:
                            props[k] = str(v) if not isinstance(v, (int, float, list, dict)) else v
                
                features.append({
                    "type": "Feature", 
                    "geometry": {"type": "Point", "coordinates": [lng, lat]},
                    "properties": props
                })
        
        with open(dest / "optimization_data.geojson", "w") as f: 
            json.dump({"type": "FeatureCollection", "features": features}, f)

        # TXT ESTRATÉGICO (Versão com CEPs Alvo)
        with open(dest / "OPORTUNIDADES_ESTRATEGICAS.txt", "w", encoding="utf-8") as f:
            f.write(f"RELATÓRIO DE EXPANSÃO - GERADO EM {datetime.now().strftime('%d/%m/%Y %H:%M')}\n")
            f.write("="*80 + "\n")
            
            for r in self.reports:
                m = r.base_metrics
                f.write(f"\n📍 UNIDADE OPERACIONAL: {r.station_code}\n")
                f.write(f"{'-'*40}\n")
                f.write(f"RESUMO EXECUTIVO DA BASE:\n")
                f.write(f"  - Demanda Total da Base:     {m.get('total_demand', 0):,} pacotes\n")
                f.write(f"  - Atendida (Ativos F1-F3):   {m.get('existing_absorbed', 0):,} pacotes\n")
                f.write(f"  - Alocada p/ Inativos (F4):   {m.get('inactive_reserved', 0):,} pacotes\n")
                f.write(f"  - Alocada p/ Leads (F5):      {m.get('prospect_reserved', 0):,} pacotes\n")
                f.write(f"  - Alocada p/ Expansão (F6):  {m.get('new_allocated', 0):,} pacotes\n")
                f.write(f"  - Gap Final (Não alocado):   {m.get('residual', 0):,} pacotes\n")
                f.write(f"{'-'*40}\n")
                f.write(f"POTENCIAL DE NOVAS VAGAS (F6):\n")
                f.write(f"  - Quantidade de Clusters:    {r.base_metrics.get('cluster_count', 0)}\n")
                f.write(f"  - Média de parceiros/cluster: {r.base_metrics.get('avg_partners_per_cluster', 0):.1f}\n")
                f.write(f"  - Quantidade de Vagas:       {m.get('new_partners_count', 0)} vagas\n")
                f.write(f"  - Média de Pacotes/Vaga:     {m.get('avg_load', 0):.1f} pacotes\n")
                f.write(f"  - Média de Raio Proposto:    {m.get('avg_radius', 0):.0f} m\n")
                f.write(f"{'-'*40}\n")
                
                # SEÇÃO DE PROSPECTS (ANÁLISE DE LEADS)
                prospects = [p for p in r.existing_partners if p.status == "Prospect"]
                if prospects:
                    f.write(f"📢 ANÁLISE DE LEADS (PROSPECTS):\n")
                    for p in prospects:
                        f.write(f"  • ID: {p.store_id} | Decisão: {p.decision}\n")
                        if p.decision == "Seguir cadastro":
                            ceps_p = set()
                            for a in p.allocations: ceps_p.update(self.hex_to_ceps.get(a.hex_id, []))
                            f.write(f"    Sugerido: {p.total_load}pk (R:{p.radius_s}m) | CEPs: {', '.join(list(ceps_p)[:10])}\n")
                    f.write(f"{'-'*40}\n")
                
                #SEÇÃO DE INATIVOS/EXITED AVALIADOS
                inativos = [p for p in r.inactive_partners]
                if inativos:
                    f.write(f"📢 ANÁLISE DE INATIVOS/EXITED AVALIADOS:\n")
                    for p in inativos:
                        f.write(f"  • ID: {p.store_id} | Decisão: {p.decision}\n")
                        if p.decision == "Seguir cadastro":
                            ceps_p = set()
                            for a in p.allocations: ceps_p.update(self.hex_to_ceps.get(a.hex_id, []))
                            f.write(f"    Sugerido: {p.total_load}pk (R:{p.radius_s}m) | CEPs: {', '.join(list(ceps_p)[:10])}\n")
                    f.write(f"{'-'*40}\n")

                # SEÇÃO DE NOVAS VAGAS POR CLUSTER
                clusters_stats = []
                for cn in set(p.cluster_name for p in r.new_partners):
                    pts = [p for p in r.new_partners if p.cluster_name == cn]
                    clusters_stats.append({"name": cn, "vol": sum(p.total_load for p in pts), "pts": pts})
                clusters_stats.sort(key=lambda x: x['vol'], reverse=True)

                f.write(f"🚀 OPORTUNIDADES PARA PROSPECÇÃO:\n")
                for i, c in enumerate(clusters_stats, 1):
                    f.write(f"\n  {i}º) {c['name']} - Potencial: {c['vol']:,} pacotes - {len(c['pts'])} novos parceiros.\n")
                    f.write(f"  Oportunidades neste cluster:\n")
                    oportunidades_ordenadas = sorted(c['pts'], key=lambda x: x.total_load, reverse=True)
                    for idx, p in enumerate(oportunidades_ordenadas,1):
                        ceps_vaga = set()
                        for alloc in p.allocations:
                            ceps_vaga.update(self.hex_to_ceps.get(alloc.hex_id, []))
                        lat, lng = h3.cell_to_latlng(p.origin_hex)
                        f.write(f"      • Oportunidade {idx}: {p.total_load} pacotes/dia e Raio de atução:{p.radius_s}m\n")
                        f.write(f"        CEPs Alvo: {', '.join(list(ceps_vaga)[:8])}...\n")
                        f.write(f"        Google Maps: maps.google.com/maps?q={lat},{lng}\n\n")
                f.write("\n" + "="*80 + "\n")

    def export_inactive_exited_report(self, filename="INATIVOS_EXITED_AVALIADOS.csv"):
        dest = Path(Config.DEST_FOLDER)
        dest.mkdir(exist_ok=True)
        path = dest / filename

        with open(path, "w", encoding="utf-8", newline='') as f:
            writer = csv.writer(f)
            writer.writerow(["store_id", "status", "delivery_station", "decision", "cap_sugerido", "raio_sugerido"])
            for r in self.reports:
                for p in r.inactive_partners:
                    writer.writerow([
                        p.store_id,
                        p.status,
                        r.station_code,
                        p.decision,
                        p.total_load,
                        p.radius_s
                    ])
    
    def executive_report(self, filename="RELATORIO_EXECUTIVO.txt"):
        dest = Path(Config.DEST_FOLDER)
        dest.mkdir(exist_ok=True)
        path = dest / filename

        with open(path, "w", encoding="utf-8") as f:
            f.write(f"RELATÓRIO EXECUTIVO DE OTIMIZAÇÃO - GERADO EM {datetime.now().strftime('%d/%m/%Y %H:%M')}\n")
            f.write("="*80 + "\n")
            for r in self.reports:
                m = r.base_metrics
                f.write(f"\n📍 UNIDADE OPERACIONAL: {r.station_code}\n")
                f.write(f"{'-'*40}\n")
                f.write(f"RESUMO EXECUTIVO DA BASE:\n")
                f.write(f"  - Demanda Total da Base:     {m.get('total_demand', 0):,} pacotes\n")
                f.write(f"  - Atendida (Ativos F1-F3):   {m.get('existing_absorbed', 0):,} pacotes\n")
                f.write(f"  - Alocada p/ Inativos (F4):   {m.get('inactive_reserved', 0):,} pacotes\n")
                f.write(f"  - Alocada p/ Leads (F5):      {m.get('prospect_reserved', 0):,} pacotes\n")
                f.write(f"  - Alocada p/ Expansão (F6):  {m.get('new_allocated', 0):,} pacotes\n")
                f.write(f"  - Gap Final (Não alocado):   {m.get('residual', 0):,} pacotes\n")
                f.write(f"{'-'*40}\n")
                f.write(f"POTENCIAL DE NOVAS VAGAS (F6):\n")
                f.write(f"  - Quantidade de Clusters:    {r.base_metrics.get('cluster_count', 0)}\n")
                f.write(f"  - Média de parceiros/cluster: {r.base_metrics.get('avg_partners_per_cluster', 0):.1f}\n")
                f.write(f"  - Total de parceiros Ativos: {m.get('active_partners_count', 0)}\n")
                f.write(f"  - Total de parceiros Onboarding: {m.get('onboarding_partners_count', 0)}\n")
                f.write(f"  - Total de parceiros Inativos aptos a serem reativados: {m.get('inactive_partners_count', 0)}\n")
                f.write(f"  - Quantidade de Vagas:       {m.get('new_partners_count', 0)} vagas\n")
                f.write(f"  - Média de pacotes por vaga: {m.get('avg_load', 0):.1f} pacotes\n")
                
    def mkt_report(self, filename="RELATORIO_MKT.txt"):
        dest = Path(Config.DEST_FOLDER)
        dest.mkdir(exist_ok=True)
        path = dest / filename

        with open(path, "w", encoding="utf-8") as f:
            f.write(f"RELATÓRIO DE MARKETING - GERADO EM {datetime.now().strftime('%d/%m/%Y %H:%M')}\n")
            f.write("="*80 + "\n")
            for r in self.reports:
                m = r.base_metrics
                f.write(f"\n📍 UNIDADE OPERACIONAL: {r.station_code}\n")
                f.write(f"{'-'*40}\n")
                f.write(f"POTENCIAL DE NOVAS VAGAS (F6):\n")
                f.write(f"  - Quantidade de Clusters:    {r.base_metrics.get('cluster_count', 0)}\n")
                f.write(f"  - Média de parceiros/cluster: {r.base_metrics.get('avg_partners_per_cluster', 0):.1f}\n")
                f.write(f"  - Quantidade de Vagas:       {m.get('new_partners_count', 0)} vagas\n")
                f.write(f"  - Média de pacotes por vaga: {m.get('avg_load', 0):.1f} pacotes\n")
                f.write(f"  - Média de Raio Proposto:    {m.get('avg_radius', 0):.0f} m\n")
                f.write(f"{'-'*40}\n")
                f.write(f"DETALHAMENTO DAS OPORTUNIDADES:\n")
                clusters_stats = []
                for cn in set(p.cluster_name for p in r.new_partners):
                    pts = [p for p in r.new_partners if p.cluster_name == cn]
                    clusters_stats.append({"name": cn, "vol": sum(p.total_load for p in pts), "pts": pts})
                clusters_stats.sort(key=lambda x: x['vol'], reverse=True)
                for i, c in enumerate(clusters_stats, 1):
                    f.write(f"\n  {i}º) {c['name']} - Potencial: {c['vol']:,} pacotes - {len(c['pts'])} novos parceiros.\n")
                    f.write(f"  Oportunidades neste cluster:\n")
                    oportunidades_ordenadas = sorted(c['pts'], key=lambda x: x.total_load, reverse=True)
                    for idx, p in enumerate(oportunidades_ordenadas,1):
                        ceps_vaga = set()
                        for alloc in p.allocations:
                            ceps_vaga.update(self.hex_to_ceps.get(alloc.hex_id, []))
                        f.write(f"        CEPs Alvo: {', '.join(list(ceps_vaga))}...\n")

if __name__ == "__main__":
    try:
        OptimizationService().run()
        print(f"\n✅ Concluído com sucesso!")
    except: traceback.print_exc()