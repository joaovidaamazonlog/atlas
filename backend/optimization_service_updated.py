import json
import h3
import math
import traceback
import pandas as pd
import numpy as np
import config as configuration
import csv
from shapely.geometry import Point, shape
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional, Set, Tuple, Any
from dataclasses import dataclass, field
from sklearn.cluster import DBSCAN, KMeans
from ortools.sat.python import cp_model
from concurrent.futures import ProcessPoolExecutor, as_completed

# =====================================================
# CONFIGURAÇÕES E CONSTANTES
# =====================================================

class Config:
    """Configurações centralizadas do sistema de otimização."""
    BASE_PACKAGES = configuration.BASE_PACKAGES
    BASE_PARTNERS = configuration.BASE_PARTNERS
    BASE_JURISDICTION = configuration.BASE_JURISDICTION
    DEST_FOLDER = configuration.DEST_FOLDER
    H3_RES = configuration.H3_RESOLUTION
    MIN_CAP = configuration.MIN_CAPACITY
    MAX_CAP = configuration.MAX_CAPACITY
    CAPACITIES = configuration.CAPACITIES
    RADII = configuration.RADII_M
    BONUS_PER_OPEN = 1500
    # Carregando o dicionário de carteiras por base
    CLUSTER_PER_STATION = getattr(configuration, 'CLUSTER_PER_STATION', {})
    
    # Mapeamento de Bases para Clusters BDM
    BDM_CLUSTERS = {
        "SP/SUL": ["DBR9", "DSP2", "DSP4", "DSP5", "DPR2", "DFR2", "DRS5"],
        "RJ/CW": ["DRJ3", "DBS5", "DGO2"],
        "BH": ["DMG2", "DBH5"],
        "RECIFE/JOAO PESSOA": ["DPE4", "DPB3"],
        "FORTALEZA": ["DCE3"],
        "ES/BA": ["DES2", "DSA8"]
    }

    @staticmethod
    def get_bdm_cluster(station_code: str) -> str:
        """Retorna o nome do cluster BDM para uma dada base."""
        for cluster, bases in Config.BDM_CLUSTERS.items():
            if station_code in bases:
                return cluster
        return "OUTROS"

# =====================================================
# MODELOS DE DADOS (DATACLASSES)
# =====================================================

@dataclass
class Allocation:
    """Representa a alocação de demanda de um hexágono para um parceiro."""
    hex_id: str
    packages_assigned: int

@dataclass
class BaseMetrics:
    """Métricas consolidadas de uma base operacional."""
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
class PartnerMetrics:
    """Dados detalhados de um parceiro (existente ou potencial)."""
    origin_hex: str
    station_code: str
    radius_s: int
    capacity_s: int
    entity_type: str 
    status: str
    partner_name: str = ""
    decision: str = ""
    cluster_name: str = "N/A"
    ctl_name: str = "N/A"
    bdm_cluster: str = "N/A"
    lat: float = 0.0
    lon: float = 0.0
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
class ClusterMetrics:
    """Métricas de uma carteira operacional (Bucket)."""
    base: str
    bdm_cluster: str
    ctl_name: str
    cluster_name: str
    total_demand: int
    total_expected_partners: int
    active_partners: int
    onboarding_partners: int
    bg_chacks_partners: int
    prospects_to_approve: int
    inactives_to_reactivate: int
    new_partners: int
    attainment_percentage: float
    partners: List[PartnerMetrics] = field(default_factory=list)

@dataclass
class OptimizationReport:
    """Relatório final de otimização por base."""
    station_code: str
    bdm_cluster: str
    existing_partners: List[PartnerMetrics]
    inactive_partners: List[PartnerMetrics]
    prospect_partners: List[PartnerMetrics]
    new_partners: List[PartnerMetrics]
    demand_summary: Dict[str, Dict]
    hex_to_cluster: Dict[str, str]
    base_metrics: BaseMetrics
    cluster_metrics: Dict[str, ClusterMetrics] = field(default_factory=dict)

# =====================================================
# REPORT GENERATOR
# =====================================================

class ReportGenerator:
    """Gera TXTs e GeoJSONs com a nova estrutura de dados."""
    
    def __init__(self, output_folder: str):
        self.dest = Path(output_folder)
        self.dest.mkdir(exist_ok=True)
        
    def generate_strategic_txt(self, reports: List[OptimizationReport], hex_to_ceps: Dict[str, Set[str]]):
        filename = self.dest / "OPORTUNIDADES_ESTRATEGICAS_V2.txt"
        with open(filename, "w", encoding="utf-8") as f:
            f.write(f"RELATÓRIO ESTRATÉGICO - HIERARQUIA COMPLETA - {datetime.now()}\n")
            f.write("="*90 + "\n")
            
            for rep in reports:
                f.write(f"\n📍 BASE: {rep.station_code} | BDM: {rep.bdm_cluster}\n")
                f.write("-" * 90 + "\n")
                
                # Agrupar por CTL para exibição organizada
                sorted_stats = sorted(rep.cluster_metrics.values(), key=lambda x: (x.ctl_name, x.cluster_name.split('-')[1]))
                
                current_ctl = None
                for stat in sorted_stats:
                    if stat.ctl_name != current_ctl:
                        current_ctl = stat.ctl_name
                        f.write(f"\n   👮 {current_ctl} (Coordenador)\n")
                    
                    f.write("-" * 90 + "\n")
                    f.write(f"      📦 Carteira: {stat.cluster_name}\n")
                    f.write(f"          - Demanda Total da Área:     {stat.total_demand} pacotes\n")
                    f.write(f"          - Qtd Parceiros esperados:   {len(stat.partners)}\n")
                    f.write(f"          - Qtd Parceiros Ativos:      {stat.active_partners}\n")
                    f.write(f"          - Qtd Parceiros Onboarding:  {stat.onboarding_partners}\n")
                    f.write(f"          - Qtd Parceiros Vetting:     {stat.bg_chacks_partners}\n")
                    
                    # Listar parceiros novos (Oportunidades)
                    new_pts = [p for p in stat.partners if p.entity_type == "NEW PARTNER"]
                    if len(new_pts) > 0:
                        f.write(f"\n          🚀 Oportunidades nesta Carteira:\n")
                        for idx, p in enumerate(new_pts, 1):
                            ceps = set()
                            for a in p.allocations: ceps.update(hex_to_ceps.get(a.hex_id, []))
                            f.write(f"          • Oportunidade {idx}:\n")
                            f.write(f"              Sugerido: {p.total_load} pacotes | Raio: {p.radius_s}m\n")
                            f.write(f"              CEPs Alvo (Top 10): {', '.join(list(ceps)[:10])}\n")
                            f.write(f"              Localização: https://maps.google.com/maps?q={p.lat},{p.lon}\n")
                    else: 
                        f.write(f"\n          ✅ Carteira Completa!\n")
            
            print(f"✅ Relatório TXT salvo em {filename}")

    def generate_geojson(self, reports: List[OptimizationReport], hex_to_ceps: Dict[str, Set[str]]):
        features = []
        for rep in reports:
            # 1. Polígonos das Carteiras
            for h, bucket_name in rep.hex_to_cluster.items():
                demand_info = rep.demand_summary.get(h)
                if demand_info and demand_info["residual"] > 0:
                    boundary = h3.cell_to_boundary(h)
                    coords = [[c[1], c[0]] for c in boundary]; coords.append(coords[0])
                    ts = rep.cluster_metrics.get(bucket_name)
                    features.append({
                        "type": "Feature",
                        "geometry": {"type": "Polygon", "coordinates": [coords]},
                        "properties": {
                            "type": "TERRITORY_HEX",
                            "delivery_station": rep.station_code,
                            "bucket": bucket_name,
                            "ctl": ts.ctl_name if ts else "N/A",
                            "bdm": rep.bdm_cluster,
                            "demand": demand_info["residual"]
                        }
                    })

            # 2. Pontos dos Parceiros
            all_partners = rep.existing_partners + rep.new_partners + rep.prospect_partners + rep.inactive_partners
            for p in all_partners:
                ceps = set()
                for a in p.allocations: ceps.update(hex_to_ceps.get(a.hex_id, []))
                features.append({
                    "type": "Feature",
                    "geometry": {"type": "Point", "coordinates": [p.lon, p.lat]},
                    "properties": {
                        "type": "PARTNER_POINT",
                        "salesforce_id": p.salesforce_id,
                        "name": p.partner_name,
                        "status": p.status,
                        "entity": p.entity_type,
                        "station_code": p.station_code,
                        "cluster_bdm": p.bdm_cluster,
                        "ctl": p.ctl_name,
                        "decision": p.decision,
                        "bucket_ade": p.cluster_name,
                        "cap_suggestion": p.capacity_s,
                        "radius_suggestion": p.radius_s,
                        "ceps": list(ceps)[:5]
                    }
                })

        filename = self.dest / "optimization_data.geojson"
        with open(filename, "w", encoding="utf-8") as f:
            json.dump({"type": "FeatureCollection", "features": features}, f, ensure_ascii=False, indent=2)
        print(f"✅ GeoJSON salvo em {filename}")
        
    def executive_report(self, reports: List[OptimizationReport], filename="RELATORIO_EXECUTIVO.txt"):
        path = self.dest / filename
        with open(path, "w", encoding="utf-8") as f:
            f.write(f"RELATÓRIO EXECUTIVO DE OTIMIZAÇÃO - GERADO EM {datetime.now().strftime('%d/%m/%Y %H:%M')}\n")
            f.write("="*80 + "\n")
            for r in reports:
                m = r.base_metrics
                total_parceiros_esperados = (m.active_partners_count + m.onboarding_partners_count + 
                                            m.vetting_partners_count + m.inactive_partners_count + m.new_partners_count)
                attainment = (m.active_partners_count / total_parceiros_esperados * 100) if total_parceiros_esperados > 0 else 0
                f.write(f"BASE: {r.station_code}\n")
                f.write(f"{'-'*80}\n")
                f.write(f"  - Quantidade de Clusters:                    {m.cluster_count}\n")
                f.write(f"  - Volume Total de Pacotes:                   {m.total_demand:,} pacotes\n")
                f.write(f"  - Quantidade Total de Parceiros esperados:   {total_parceiros_esperados}\n")
                f.write(f"  - Quantidade Total de Parceiros Ativos:      {m.active_partners_count}\n")
                f.write(f"  - % de Attainment:                           {attainment:.1f}%\n")
                f.write(f"  - Total de Pacotes Atendidos (Ativos):       {m.existing_absorbed:,} pacotes\n")
                f.write(f"{'-'*80}\n")
                f.write(f"DETALHAMENTO POR CLUSTER:\n")
                for cluster_name, cluster_data in sorted(r.cluster_metrics.items()):
                    f.write(f"  Careira ADE: {cluster_name}\n")
                    f.write(f"    - Quantidade Total de Parceiros:           {cluster_data.total_expected_partners}\n")
                    f.write(f"        • Ativos:                              {cluster_data.active_partners}\n")
                    f.write(f"        • Onboarding:                          {cluster_data.onboarding_partners}\n")
                    f.write(f"        • Prospects a Aprovar:                 {cluster_data.prospects_to_approve}\n")
                    f.write(f"        • Inativos a Reativar:                 {cluster_data.inactives_to_reactivate}\n")
                    f.write(f"        • Novos Parceiros:                     {cluster_data.new_partners}\n")
                    f.write(f"    - Volume Total de Demanda:                 {cluster_data.total_demand:,} pacotes\n")
                    f.write(f"    - % de Attainment:                         {cluster_data.attainment_percentage:.1f}%\n")
                f.write("="*80 + "\n")
        print(f"✅ Relatório executivo salvo em: {path}")
        
    def generate_partners_csv(self, reports: List[OptimizationReport]):
        """Gera um CSV detalhando os parceiros por Estação e Bucket."""
        filename = self.dest / "PARTNERS_PER_DS_BUCKET.csv"
        
        # Cabeçalhos solicitados
        fieldnames = ["station_code", "bucket", "status", "salesforce_id", "partner_name"]
        
        try:
            with open(filename, "w", encoding="utf-8", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                
                for rep in reports:
                    # Iteramos pelos clusters (buckets) definidos no relatório da base
                    for cluster_name, cluster_data in rep.cluster_metrics.items():
                        for p in cluster_data.partners:
                            if p.status in ["Active", "Onboarding"]:
                                writer.writerow({
                                    "station_code": rep.station_code,
                                    "bucket": cluster_name,
                                    "status": p.status,
                                    "salesforce_id": p.salesforce_id,
                                    "partner_name": p.partner_name,
                                    "store_id": p.store_id
                                })
                            
            print(f"✅ CSV de parceiros por bucket salvo em {filename}")
        except Exception as e:
            print(f"❌ Erro ao gerar CSV de parceiros: {e}")

# =====================================================
# WORKER DO SOLVER (PARALELISMO)
# =====================================================

def solve_island_exhaustion_worker(payload: Dict) -> List[Dict]:
    """Worker para encontrar novos parceiros em ilhas de demanda residual."""
    station_code = payload['station_code']
    island_hexes = payload['hexes']
    demand_map = dict(payload['demand_map'])
    island_results = []
    
    while True:
        # Encontrar hexágono com maior demanda para ser a semente
        seeds = sorted([h for h in island_hexes if demand_map.get(h, 0) > 0], 
                    key=lambda x: demand_map[x], reverse=True)
        if not seeds: break
        
        best_seed = seeds[0]
        # Verificação rápida de potencial volumétrico num raio de 9 hexágonos
        potential_vol = sum(demand_map[h] for h in island_hexes if h3.grid_distance(h, best_seed) <= 9)
        if potential_vol < Config.MIN_CAP: break

        model = cp_model.CpModel()
        x, y = {}, {}
        # Decidir Raio e Capacidade (Simp. Min/Max)
        for r in Config.RADII:
            for k in [Config.MIN_CAP, Config.MAX_CAP]:
                idx = (best_seed, r['radius_s'], k)
                x[idx] = model.NewBoolVar(f'x_{idx}')
                potential_h = [h for h in island_hexes if h3.grid_distance(h, best_seed) <= r['hex_distance']]
                for h in potential_h:
                    y[(h, *idx)] = model.NewIntVar(0, int(demand_map[h]), f'y_{h}_{idx}')

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
                            "radius_s": idx_x[1], "capacity_s": idx_x[2], 
                            "entity_type": "NEW PARTNER", "allocations": allocs
                        })
                        for a in allocs:
                            demand_map[a['hex_id']] = max(0, demand_map[a['hex_id']] - a['packages_assigned'])
                        found_any = True
            if not found_any: break
        else: break
    return island_results

# =====================================================
# SERVIÇO PRINCIPAL DE OTIMIZAÇÃO
# =====================================================

class OptimizationService:
    def __init__(self):
        self.reports: List[OptimizationReport] = []
        self.hex_to_ceps: Dict[str, Set[str]] = {}
        self.demand_df: pd.DataFrame = pd.DataFrame()
        self.partners_df: pd.DataFrame = pd.DataFrame()
        self.jurisdictions: Dict = {}

    def _load_data(self):
        """Carrega e limpa os dados iniciais."""
        print(f"[{datetime.now()}] Carregando dados...")
        
        # 1. Carregar Demandas (Pacotes)
        df = pd.read_csv(Config.BASE_PACKAGES)
        df['cep'] = df['cep'].astype(str).str.replace(r'\D', '', regex=True).str.zfill(8)
        df["hex"] = [h3.latlng_to_cell(la, lo, Config.H3_RES) for la, lo in zip(df.latitude, df.longitude)]
        
        # Tratamento de duplicidade geográfica entre DSs
        # Se um hexágono aparece em DSs diferentes, somamos a demanda
        # e atribuímos à DS que tem mais hexágonos próximos (vizinhança dominante)
        print("   - Resolvendo duplicidades de hexágonos entre bases...")
        
        self.hex_to_ceps = df.groupby('hex')['cep'].apply(set).to_dict()
        days = pd.to_datetime(df.plan_date).nunique() or 1
        self.demand_df = df.groupby(["station_code", "hex"]).size().reset_index(name="avg_demand")
        self.demand_df["avg_demand"] = (self.demand_df["avg_demand"] / days).round(0).astype(int)
        self.hex_to_base = dict(zip(self.demand_df.hex, self.demand_df.station_code))
        
        # Primeiro, somar demandas por hexágono
        def get_most_frequent(x):
            counts = x.value_counts()
            return counts.index[0] if not counts.empty else "UNKNOWN"

        agg_dem = self.demand_df.groupby('hex').agg({
            'avg_demand': 'sum',
            'station_code': get_most_frequent
        }).reset_index()
        
        # Para cada hexágono duplicado, decidir a DS correta baseada na vizinhança
        # (Simplificado: usamos a DS que mais aparece na vizinhança imediata se houver conflito)
        self.demand_df = agg_dem

        # Mapear Hex -> CEPs (para o relatório estratégico)
        # Assumindo que o arquivo de pacotes tem coluna 'cep'
        if 'cep' in df.columns:
            for _, row in df.iterrows():
                h = str(row['hex'])
                c = str(row['cep'])
                if h not in self.hex_to_ceps: self.hex_to_ceps[h] = set()
                self.hex_to_ceps[h].add(c)
                

        # 2. Carregar Parceiros
        with open(Config.BASE_PARTNERS, "r", encoding="utf-8") as f:
            p_data = json.load(f)["allMarkerData"]
        self.partners_df = pd.DataFrame(p_data)
        self.partners_df['exitedDate'] = pd.to_datetime(self.partners_df.get('exitedDate'), errors='coerce')
        self.partners_df.rename(columns={"delivery_station": "station_code"}, inplace=True)
        self.partners_df.rename(columns={"name": "partner_name"}, inplace=True)
        self.partners_df["origin_hex"] = [h3.latlng_to_cell(float(la), float(lo), Config.H3_RES) for la, lo in zip(self.partners_df.lat, self.partners_df.lon)]
        
        # 3. Carregar Jurisdições (GeoJSON)
        with open(Config.BASE_JURISDICTION, 'r', encoding='utf-8') as f:
            self.jurisdictions = json.load(f)

    def _generate_operational_clusters_balanced(self, station_code: str, partners: List[PartnerMetrics], n_clusters: int) -> Tuple[Dict[str, ClusterMetrics], Dict[str, str]]:
        if not partners or n_clusters <= 0: return {}, {}
        n_partners = len(partners)
        bdm_cluster = Config.get_bdm_cluster(station_code)
        coords = np.array([[p.lat, p.lon] for p in partners])
        actual_n_clusters = min(n_clusters, n_partners)
        kmeans = KMeans(n_clusters=actual_n_clusters, random_state=42, n_init=10).fit(coords)
        initial_centroids = kmeans.cluster_centers_

        model = cp_model.CpModel()
        x = {(i, j): model.NewBoolVar(f'x_{i}_{j}') for i in range(n_partners) for j in range(actual_n_clusters)}
        for i in range(n_partners): model.Add(sum(x[i, j] for j in range(actual_n_clusters)) == 1)
        min_p, max_p = n_partners // actual_n_clusters, math.ceil(n_partners / actual_n_clusters)
        for j in range(actual_n_clusters):
            model.Add(sum(x[i, j] for i in range(n_partners)) >= min_p)
            model.Add(sum(x[i, j] for i in range(n_partners)) <= max_p)

        obj_terms = [int(((coords[i][0]-initial_centroids[j][0])**2 + (coords[i][1]-initial_centroids[j][1])**2)*10**8) * x[i, j] 
                    for i in range(n_partners) for j in range(actual_n_clusters)]
        model.Minimize(sum(obj_terms))
        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = 10
        
        clusters_partners = {j: [] for j in range(actual_n_clusters)}
        if solver.Solve(model) in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            for i in range(n_partners):
                for j in range(actual_n_clusters):
                    if solver.Value(x[i, j]): clusters_partners[j].append(partners[i])
        else:
            for i, label in enumerate(kmeans.labels_): clusters_partners[label].append(partners[i])

        cluster_metrics, hex_to_cluster = {}, {}
        for j, bucket_partners in clusters_partners.items():
            bucket_id = j + 1
            ctl_name = f"CTL-{chr(65 + (j // 5))}"
            cluster_name = f"bucket-{bucket_id}"
            for p in bucket_partners:
                p.cluster_name, p.ctl_name, p.bdm_cluster = cluster_name, ctl_name, bdm_cluster
                for alloc in p.allocations: hex_to_cluster[alloc.hex_id] = cluster_name

            active = sum(1 for p in bucket_partners if p.status == "Active")
            cluster_metrics[cluster_name] = ClusterMetrics(
                base=station_code, bdm_cluster=bdm_cluster, ctl_name=ctl_name, cluster_name=cluster_name,
                total_demand=sum(p.total_load for p in bucket_partners), total_expected_partners=len(bucket_partners),
                active_partners=active, onboarding_partners=sum(1 for p in bucket_partners if p.status == "Onboarding"), 
                bg_chacks_partners=sum(1 for p in bucket_partners if p.status == "BG_Checks"),
                prospects_to_approve=sum(1 for p in bucket_partners if p.entity_type == "PROSPECT" and p.decision == "Seguir cadastro"),
                inactives_to_reactivate=sum(1 for p in bucket_partners if p.entity_type == "INACTIVE_EXITED" and p.decision == "Reativar cadastro"),
                new_partners=sum(1 for p in bucket_partners if p.entity_type == "NEW PARTNER"),
                attainment_percentage=(active / len(bucket_partners) * 100) if bucket_partners else 0,
                partners=bucket_partners
            )
        return cluster_metrics, hex_to_cluster

    def _find_neighborhood_clusters(self, res_dem: Dict[str, int], base: str) -> Tuple[List[List[str]], Dict[str, str]]:
        active_hexes = [h for h, v in res_dem.items() if v > 0]
        if not active_hexes: return [], {}
        coords = np.array([h3.cell_to_latlng(h) for h in active_hexes])
        db = DBSCAN(eps=0.015, min_samples=2).fit(coords)
        islands, hex_to_island = [], {}
        for label in set(db.labels_):
            if label == -1: continue
            island_hexes = [active_hexes[i] for i, l in enumerate(db.labels_) if l == label]
            islands.append(island_hexes)
            for h in island_hexes: hex_to_island[h] = f"Island_{label}"
        return islands, hex_to_island

    def _allocate_existing_by_status(self, base: str, res_dem: Dict[str, int], target_status: str) -> List[PartnerMetrics]:
        results = []
        MIN_LIMIT = 40
        MAX_LIMIT = 70
        subset = self.partners_df[(self.partners_df.status == target_status) & (self.partners_df.station_code == base)]
        
        for _, p in subset.iterrows():
            best_allocs = []
            chosen_cap = 0
            chosen_rad = 0
            found_ideal = False
            actual_rad = getattr(p, 'radius_a', 0)
            actual_cap = getattr(p, 'capacity_a', 0)
            for r in Config.RADII:
                in_r = [h for h in h3.grid_disk(p.origin_hex, r["hex_distance"]) if res_dem.get(h, 0) > 0]
                total_available = sum(res_dem[h] for h in in_r)
                
                if total_available >= MIN_LIMIT:
                    chosen_rad = r["radius_s"]
                    chosen_cap = min(total_available, MAX_LIMIT)
                    found_ideal = True
                    break 
            if not found_ideal:
                max_r_config = Config.RADII[-1]
                chosen_rad = max_r_config["radius_s"]
                in_max_r = [h for h in h3.grid_disk(p.origin_hex, max_r_config["hex_distance"]) if res_dem.get(h, 0) > 0]
                chosen_cap = sum(res_dem[h] for h in in_max_r)
            if chosen_cap < MIN_LIMIT:
                decision_str = "Max Available (Below Min)"
            elif (chosen_rad != actual_rad) or (chosen_cap != actual_cap):
                decision_str = "Optimization suggested"
            else:
                decision_str = "No optimization suggestions"
            target_hex_dist = next(rad['hex_distance'] for rad in Config.RADII if rad['radius_s'] == chosen_rad)
            available_hexes = [h for h in h3.grid_disk(p.origin_hex, target_hex_dist) if res_dem.get(h, 0) > 0]
            
            current_total = 0
            for h in sorted(available_hexes, key=lambda x: h3.grid_distance(x, p.origin_hex)):
                take = min(res_dem[h], chosen_cap - current_total)
                if take > 0:
                    best_allocs.append(Allocation(hex_id=h, packages_assigned=take))
                    current_total += take
                if current_total >= chosen_cap:
                    break
            results.append(PartnerMetrics(
                origin_hex=p.origin_hex, 
                station_code=base, 
                radius_s=chosen_rad, 
                capacity_s=chosen_cap, 
                decision=decision_str, 
                entity_type="EXISTING", 
                status=target_status, 
                partner_name=str(p.partner_name), 
                salesforce_id=str(p.salesforce_id),
                lat=float(p.lat), 
                lon=float(p.lon), 
                allocations=best_allocs
            ))
            
            for a in best_allocs:
                res_dem[a.hex_id] -= a.packages_assigned
                    
        return results

    def _evaluate_inactive_exited(self, base, res_dem):
        results = []
        cutoff = pd.to_datetime("2026-01-01")
        subset = self.partners_df[((self.partners_df.status == "Inactive") | ((self.partners_df.status == "Exited") & (self.partners_df.decision_status == "Exited - Regretted"))) & (self.partners_df.station_code == base)]
        for _, p in subset.iterrows():
            decision, sug_rad, sug_cap, allocs = "", 0, 0, []
            for r in Config.RADII:
                in_r = [h for h in h3.grid_disk(p.origin_hex, r["hex_distance"]) if res_dem.get(h, 0) > 0]
                temp_total = sum(res_dem[h] for h in in_r)
                if temp_total >= Config.MIN_CAP:
                    decision, sug_rad = "Reativar cadastro", r["radius_s"]
                    sug_cap = Config.MAX_CAP if temp_total >= Config.MAX_CAP else Config.MIN_CAP
                    curr = 0
                    for h in sorted(in_r, key=lambda x: h3.grid_distance(x, p.origin_hex)):
                        take = min(res_dem[h], sug_cap - curr)
                        if take > 0: allocs.append(Allocation(h, take)); curr += take
                    for a in allocs: res_dem[a.hex_id] -= a.packages_assigned
                    break
            if not decision: decision = "Fora da área de atuacao"
            results.append(PartnerMetrics(origin_hex=p.origin_hex, station_code=base, radius_s=sug_rad, capacity_s=sug_cap, entity_type="INACTIVE_EXITED", 
                                          status=str(p.status), partner_name=str(p.partner_name),salesforce_id=str(p.salesforce_id), decision=decision, 
                                          lat=float(p.lat), lon=float(p.lon), allocations=allocs))
        return results

    def _evaluate_prospects(self, base: str, res_dem: Dict[str, int]) -> List[PartnerMetrics]:
        results = []
        subset = self.partners_df[self.partners_df.status == "Prospect"].copy()
        subset['identified_base'] = subset.apply(lambda row: self._get_base_from_jurisdiction(float(row.lat), float(row.lon)), axis=1)
        subset = subset[subset['identified_base'] == base]
        for _, p in subset.iterrows():
            decision, sug_rad, sug_cap, allocs = "", 0, 0, []
            for r in Config.RADII:
                in_r = [h for h in h3.grid_disk(p.origin_hex, r["hex_distance"]) if res_dem.get(h, 0) > 0]
                temp_allocs, total = [], 0
                for h in sorted(in_r, key=lambda x: h3.grid_distance(x, p.origin_hex)):
                    take = min(res_dem[h], Config.MAX_CAP - total)
                    if take > 0: temp_allocs.append(Allocation(hex_id=h, packages_assigned=take))
                    total += take
                if total >= Config.MIN_CAP:
                    decision, sug_rad = "Seguir cadastro", r["radius_s"]
                    sug_cap = Config.MAX_CAP if total >= Config.MAX_CAP else Config.MIN_CAP
                    allocs = temp_allocs
                    for a in allocs: res_dem[a.hex_id] -= a.packages_assigned
                    break
            if not decision: decision = "Pouca volumetria na area de atuacao"
            results.append(PartnerMetrics(origin_hex=p.origin_hex, station_code=base, radius_s=sug_rad, capacity_s=sug_cap, entity_type="PROSPECT", 
                                          status="Prospect", partner_name=str(p.partner_name), salesforce_id=str(p.salesforce_id), decision=decision, 
                                          lat=float(p.lat), lon=float(p.lon), allocations=allocs))
        return results
    
    def _get_base_from_jurisdiction(self, lat: float, lon: float) -> Optional[str]:
        pt = Point(float(lon), float(lat))
        for f in self.jurisdictions.get("features", []):
            if shape(f["geometry"]).contains(pt): return f["properties"].get("delivery_station")
        return None

    def _get_prospects_outside_jurisdiction(self):
        results = []
        subset = self.partners_df[self.partners_df.status == "Prospect"]

        for _, p in subset.iterrows():
            partner_point = Point(float(p.lon), float(p.lat))

            # Verificar se está dentro de alguma jurisdição
            inside_jurisdiction = False
            for feature in self.jurisdictions.get("features", []):
                polygon = shape(feature["geometry"])
                if polygon.contains(partner_point):
                    inside_jurisdiction = True
                    break

            # Se não está em nenhuma jurisdição, adicionar aos resultados
            if not inside_jurisdiction:
                results.append(
                    PartnerMetrics(
                        origin_hex=p.origin_hex, station_code="", radius_s=0, capacity_s=0, entity_type="INACTIVE_EXITED",
                        status=str(p.status), partner_name=str(p.partner_name), salesforce_id=str(p.salesforce_id), 
                        decision="Fora da area de atuacao", lat=float(p.lat), lon=float(p.lon), 
                        allocations=[]
                ))

        return results

    def run(self):
        self._load_data()
        prospects_outside = self._get_prospects_outside_jurisdiction()
        print(f" ⚠️  {len(prospects_outside)} prospects fora de jurisdição identificados")
        for base in self.demand_df.station_code.unique():
            print(f"\n--- 🚀 INICIANDO OTIMIZAÇÃO: {base} ---")
            orig_dem = self.demand_df[self.demand_df.station_code == base].set_index("hex")["avg_demand"].to_dict()
            res_dem = dict(orig_dem)
            p_active = self._allocate_existing_by_status(base, res_dem, "Active")
            p_onboarding = self._allocate_existing_by_status(base, res_dem, "Onboarding")
            p_bg = self._allocate_existing_by_status(base, res_dem, "BG Checks")
            p_inactives = self._evaluate_inactive_exited(base, res_dem)
            p_prospects = self._evaluate_prospects(base, res_dem)
            islands, _ = self._find_neighborhood_clusters(res_dem, base)
            p_new = []
            if islands:
                payloads = [{"station_code": base, "hexes": isl, "demand_map": res_dem} for isl in islands]
                with ProcessPoolExecutor() as exe:
                    futures = [exe.submit(solve_island_exhaustion_worker, pl) for pl in payloads]
                    for f in as_completed(futures):
                        for p_data in f.result():
                            lat, lon = h3.cell_to_latlng(p_data['origin_hex'])
                            p_obj = PartnerMetrics(**{**p_data, "lat": lat, "lon": lon, "decision": "Prospect a new partner", "status": "New", "entity_type": "NEW PARTNER", "allocations": [Allocation(**a) for a in p_data['allocations']]})
                            p_new.append(p_obj)
                            for a in p_obj.allocations: res_dem[a.hex_id] -= a.packages_assigned
            
            all_final = p_active + p_onboarding + p_bg + [p for p in p_inactives if p.decision == "Reativar cadastro"] + [p for p in p_prospects if p.decision == "Seguir cadastro"] + p_new
            n_buckets = Config.CLUSTER_PER_STATION.get(base, 5)
            cluster_metrics, hex_to_bucket = self._generate_operational_clusters_balanced(base, all_final, n_buckets)
            
            final_hex_map = {}
            if all_final:
                bucket_centroids = {}
                for p in all_final:
                    if p.cluster_name not in bucket_centroids: bucket_centroids[p.cluster_name] = []
                    bucket_centroids[p.cluster_name].append((p.lat, p.lon))
                centers = {n: (np.mean([c[0] for c in co]), np.mean([c[1] for c in co])) for n, co in bucket_centroids.items()}
                for h in orig_dem.keys():
                    if h in hex_to_bucket: final_hex_map[h] = hex_to_bucket[h]
                    else:
                        h_lat, h_lon = h3.cell_to_latlng(h)
                        final_hex_map[h] = min(centers.keys(), key=lambda b: (h_lat-centers[b][0])**2 + (h_lon-centers[b][1])**2)
            else:
                for h in orig_dem.keys(): final_hex_map[h] = "UNASSIGNED"

            m = BaseMetrics(
                total_demand=sum(orig_dem.values()), 
                existing_absorbed=sum(p.total_load for p in p_active), 
                prospect_reserved=sum(p.total_load for p in p_prospects if p.decision == "Seguir cadastro"), 
                inactive_reserved=sum(p.total_load for p in p_inactives if p.decision == "Reativar cadastro"), 
                new_allocated=sum(p.total_load for p in p_new), 
                residual=sum(res_dem.values()), 
                active_partners_count=len(p_active), 
                onboarding_partners_count=len(p_onboarding), 
                inactive_partners_count=len([p for p in p_inactives if p.decision == "Reativar cadastro"]), 
                vetting_partners_count=len(p_bg), new_partners_count=len(p_new), 
                avg_load=(sum(p.total_load for p in p_new)/len(p_new)) if p_new else 0, 
                avg_radius=(sum(p.radius_s for p in p_new)/len(p_new)) if p_new else 0, 
                cluster_count=len(cluster_metrics), 
                avg_partners_per_cluster=len(all_final)/len(cluster_metrics) if cluster_metrics else 0
            )
            
            self.reports.append(OptimizationReport(
                station_code=base, 
                bdm_cluster=Config.get_bdm_cluster(base), 
                existing_partners=p_active+p_onboarding+p_bg, 
                inactive_partners=p_inactives, 
                prospect_partners=p_prospects + prospects_outside, 
                new_partners=p_new, 
                hex_to_cluster=final_hex_map, 
                demand_summary={h: {"total": orig_dem[h], "residual": res_dem.get(h, 0)} for h in orig_dem}, 
                base_metrics=m, 
                cluster_metrics=cluster_metrics))
            print(f"   ✅ Base {base} concluída.")

        rg = ReportGenerator(Config.DEST_FOLDER)
        rg.generate_strategic_txt(self.reports, self.hex_to_ceps)
        rg.generate_geojson(self.reports, self.hex_to_ceps)
        rg.executive_report(self.reports)
        rg.generate_partners_csv(self.reports)

if __name__ == "__main__":
    try: OptimizationService().run()
    except: traceback.print_exc()
