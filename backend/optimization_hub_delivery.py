# optimization_hub_full_engine.py

import json
import math
import h3
import pandas as pd
import numpy as np
from datetime import datetime
from collections import defaultdict
from typing import Dict, List, Any
import logging
import os

# =========================
# CONFIG
# =========================
H3_RESOLUTION = 9
HEX_EDGE_M = 174
MIN_CAPACITY = 45
MAX_CAPACITY = 70
NEW_PARTNER_THRESHOLD = 45
LOG_FILE = "executed_actions_log.txt"

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# =========================
# MODELS
# =========================
class Partner:
    __slots__ = ("id", "origin_hex", "capacity", "k", "latitude", "longitude")

    def __init__(self, partner_id: str, origin_hex: str, capacity: int, k: int, lat: float, lon: float):
        self.id = partner_id
        self.origin_hex = origin_hex
        self.capacity = capacity
        self.k = k
        self.latitude = lat
        self.longitude = lon

# =========================
# DATA INGESTION
# =========================
class DataIngestion:
    @staticmethod
    def load_packages(csv_path):
        logger.info(f"Carregando pacotes de {csv_path}...")
        df = pd.read_csv(csv_path, usecols=['latitude', 'longitude', 'plan_date'])
        
        if 'plan_date' in df.columns:
            df['plan_date'] = pd.to_datetime(df['plan_date'])
            num_days = df['plan_date'].nunique()
        else:
            num_days = 1
            
        df['hex_id'] = [h3.latlng_to_cell(lat, lon, H3_RESOLUTION) for lat, lon in zip(df['latitude'], df['longitude'])]
        hex_counts = df.groupby('hex_id').size().reset_index(name='total_pkgs')
        hex_counts['daily_avg'] = hex_counts['total_pkgs'] / num_days
        
        return hex_counts.set_index('hex_id')['daily_avg'].to_dict()

    @staticmethod
    def load_partners(json_path):
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            df = pd.DataFrame(data['allMarkerData'])
            
        df = df[(df['status'] == 'Active') & df['lat'].notnull()].copy()
        df['latitude'] = df['lat'].astype(float)
        df['longitude'] = df['lon'].astype(float)
        df['radius'] = pd.to_numeric(df['radius'], errors='coerce').fillna(1500)
        df['capacity'] = pd.to_numeric(df['capacity'], errors='coerce').fillna(45)
        
        partners = []
        for _, row in df.iterrows():
            origin_hex = h3.latlng_to_cell(row['latitude'], row['longitude'], H3_RESOLUTION)
            k = max(1, math.ceil((row['radius'] / 1000) / 0.174))
            partners.append(Partner(
                partner_id=row['store_id'],
                origin_hex=origin_hex,
                capacity=int(row['capacity']),
                k=k,
                lat=row['latitude'],
                lon=row['longitude']
            ))
        return partners

    @staticmethod
    def load_snapshot(path):
        if not path or not os.path.exists(path):
            return {}
        try:
            with open(path, 'r') as f:
                return json.load(f)
        except Exception:
            return {}

# =========================
# OPTIMIZATION ENGINE
# =========================
class OptimizationEngine:
    def __init__(self, partners: List[Partner], hex_packages: Dict[str, float]):
        self.partners = partners
        self.hex_packages = hex_packages
        self.hex_to_partners = defaultdict(list)
        self.partner_demand = defaultdict(float)
        self.uncovered_hexes = {}

    def run(self):
        for p in self.partners:
            covered_hexes = h3.grid_disk(p.origin_hex, p.k)
            for h in covered_hexes:
                if h in self.hex_packages:
                    self.hex_to_partners[h].append(p)

        for h_id, demand in self.hex_packages.items():
            covering_partners = self.hex_to_partners.get(h_id, [])
            if not covering_partners:
                self.uncovered_hexes[h_id] = demand
                continue
            total_capacity = sum(p.capacity for p in covering_partners)
            for p in covering_partners:
                share = (p.capacity / total_capacity) if total_capacity > 0 else (1 / len(covering_partners))
                self.partner_demand[p.id] += demand * share

        return {
            "partner_demand": self.partner_demand,
            "uncovered_hexes": self.uncovered_hexes,
            "hex_to_partners": self.hex_to_partners
        }

# =========================
# DECISION ENGINE
# =========================
class DecisionEngine:
    def __init__(self, partners: List[Partner], hex_packages: Dict[str, float], opt_output: Dict, previous_snapshot: Dict):
        self.partners = {p.id: p for p in partners}
        self.hex_packages = hex_packages
        self.partner_demand = opt_output["partner_demand"]
        self.uncovered_hexes = opt_output["uncovered_hexes"]
        self.hex_to_partners = opt_output["hex_to_partners"]
        self.previous_snapshot = previous_snapshot
        self.decisions = []

    def run(self):
        for p_id, p in self.partners.items():
            self._evaluate_capacity(p)
            self._evaluate_radius(p)

        self._evaluate_new_partners()
        self._apply_snapshot_logic()
        self._log_executed_actions()
        return self.decisions

    def _evaluate_capacity(self, p: Partner):
        demand = self.partner_demand.get(p.id, 0)
        if demand > p.capacity and p.capacity < MAX_CAPACITY:
            suggested = min(MAX_CAPACITY, math.ceil(demand))
            self.decisions.append({
                "entity": "PARTNER",
                "partner_id": p.id,
                "decision": "INCREASE_PARTNER_CAPACITY",
                "current_capacity": p.capacity,
                "suggested_capacity": suggested,
                "reason": f"Demanda justa ({round(demand,1)}) excede capacidade atual",
                "execution_status": "NEW"
            })

    def _evaluate_radius(self, p: Partner):
        demand = self.partner_demand.get(p.id, 0)
        if demand < p.capacity * 0.8:
            for k_new in range(p.k - 1, 0, -1):
                new_hexes = h3.grid_disk(p.origin_hex, k_new)
                simulated_demand = 0
                for h in new_hexes:
                    if h in self.hex_packages:
                        partners = self.hex_to_partners.get(h, [])
                        total_cap = sum(pt.capacity for pt in partners)
                        share = (p.capacity / total_cap) if total_cap > 0 else 1
                        simulated_demand += self.hex_packages[h] * share
                
                if simulated_demand >= MIN_CAPACITY:
                    self.decisions.append({
                        "entity": "PARTNER",
                        "partner_id": p.id,
                        "decision": "REDUCE_RADIUS",
                        "current_k": p.k,
                        "suggested_k": k_new,
                        "reason": f"Folga detectada. Novo raio mantem volume minimo ({round(simulated_demand,1)})",
                        "execution_status": "NEW"
                    })
                    break

    def _evaluate_new_partners(self):
        total_oportunity = 0
        gap_clusters = self._cluster_hexes(self.uncovered_hexes)
        for cluster in gap_clusters:
            total_vol = sum(self.uncovered_hexes[h] for h in cluster)
            if total_vol >= NEW_PARTNER_THRESHOLD:
                qnt_partners = math.ceil(total_vol / MAX_CAPACITY)
                self.decisions.append({
                    "entity": "CLUSTER",
                    "decision": "NEW_PARTNER_GAP",
                    "hex_count": len(cluster),
                    "suggested_partners": qnt_partners,
                    "total_packages": round(total_vol, 2),
                    "representative_hex": cluster[0],
                    "reason": "Area totalmente descoberta com volume critico",
                    "execution_status": "NEW"
                })
                total_oportunity += qnt_partners
        print(total_oportunity)

        saturated_hexes = {}
        for h_id, demand in self.hex_packages.items():
            if h_id in self.hex_to_partners:
                total_cap = sum(p.capacity for p in self.hex_to_partners[h_id])
                if demand > total_cap:
                    saturated_hexes[h_id] = demand - total_cap
        
        opt_clusters = self._cluster_hexes(saturated_hexes)
        for cluster in opt_clusters:
            total_excess = sum(saturated_hexes[h] for h in cluster)
            if total_excess >= NEW_PARTNER_THRESHOLD:
                qnt_partners = math.ceil(total_excess / MAX_CAPACITY)
                self.decisions.append({
                    "entity": "CLUSTER",
                    "decision": "NEW_PARTNER_OPTIMIZATION",
                    "hex_count": len(cluster),
                    "suggested_partners": qnt_partners,
                    "excess_packages": round(total_excess, 2),
                    "representative_hex": cluster[0],
                    "reason": "Parceiros atuais saturados. Novo parceiro aumentaria eficiencia.",
                    "execution_status": "NEW"
                })

    def _cluster_hexes(self, hex_dict: Dict[str, float]) -> List[List[str]]:
        unvisited = set(hex_dict.keys())
        clusters = []
        while unvisited:
            h = unvisited.pop()
            current_cluster = [h]
            queue = [h]
            while queue:
                curr = queue.pop(0)
                neighbors = h3.grid_disk(curr, 1)
                for n in neighbors:
                    if n in unvisited:
                        unvisited.remove(n)
                        current_cluster.append(n)
                        queue.append(n)
            clusters.append(current_cluster)
        return clusters

    def _apply_snapshot_logic(self):
        """Compara decisões atuais com o snapshot anterior para definir status."""
        for d in self.decisions:
            key = f"{d.get('partner_id', 'CLUSTER')}_{d['decision']}"
            prev = self.previous_snapshot.get(key)
            
            if prev:
                # Se a decisão é a mesma e já foi executada, mantém como EXECUTED
                if prev.get("execution_status") == "EXECUTED":
                    # Verifica se os valores sugeridos mudaram
                    if d.get("suggested_capacity") == prev.get("suggested_capacity") and \
                       d.get("suggested_k") == prev.get("suggested_k"):
                        d["execution_status"] = "EXECUTED"
                    else:
                        d["execution_status"] = "CHANGED"

    def _log_executed_actions(self):
        """Registra ações de parceiros existentes que foram concluidas."""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(LOG_FILE, "a") as f:
            for d in self.decisions:
                if d["entity"] == "PARTNER" and d["execution_status"] == "EXECUTED":
                    log_line = f"[{timestamp}] PARTNER {d['partner_id']} | {d['decision']} | Concluido\n"
                    f.write(log_line)

# =========================
# MAIN ORCHESTRATOR
# =========================
class OptimizationHub:
    def __init__(self, pkg_csv, ptn_json, snapshot_json=None):
        self.pkg_data = DataIngestion.load_packages(pkg_csv)
        self.ptn_data = DataIngestion.load_partners(ptn_json)
        self.snapshot = DataIngestion.load_snapshot(snapshot_json)

    def run(self):
        engine = OptimizationEngine(self.ptn_data, self.pkg_data)
        opt_output = engine.run()
        decisor = DecisionEngine(self.ptn_data, self.pkg_data, opt_output, self.snapshot)
        decisions = decisor.run()
        return {
            "decisions": decisions,
            "hex_packages": self.pkg_data,
            "partner_demand": opt_output["partner_demand"]
        }

def export_results(results, output_geojson, output_snapshot):
    features = []
    hex_decisions = defaultdict(list)
    for d in results["decisions"]:
        if d["entity"] == "CLUSTER":
            hex_decisions[d["representative_hex"]].append(d)

    for h_id, demand in results["hex_packages"].items():
        boundary = h3.cell_to_boundary(h_id)
        coords = [[c[1], c[0]] for c in boundary]
        coords.append(coords[0])
        
        features.append({
            "type": "Feature",
            "geometry": {"type": "Polygon", "coordinates": [coords]},
            "properties": {
                "hex_id": h_id,
                "packages": round(demand, 2),
                "decisions": hex_decisions.get(h_id, [])
            }
        })
    
    with open(output_geojson, 'w') as f:
        json.dump({"type": "FeatureCollection", "features": features}, f)

    snapshot = {f"{d.get('partner_id', 'CLUSTER')}_{d['decision']}": d for d in results["decisions"]}
    with open(output_snapshot, 'w') as f:
        json.dump(snapshot, f, indent=2)
