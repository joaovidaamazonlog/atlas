# optimization_hub_full_engine.py

import json
import math
import h3
import pandas as pd
from datetime import datetime
from collections import defaultdict
from typing import Dict, List

# =========================
# CONFIG
# =========================
H3_RESOLUTION = 9
HEX_EDGE_M = 174
MIN_CAPACITY = 45
MAX_CAPACITY = 70


# =========================
# MODELS
# =========================
class Partner:
    __slots__ = ("id", "origin_hex", "capacity", "k")

    def __init__(self, partner_id: str, origin_hex: str, capacity: int, k: int):
        self.id = partner_id
        self.origin_hex = origin_hex
        self.capacity = capacity
        self.k = k


# =========================
# DATA INGESTION
# =========================
class DataIngestion:
    __slots__ = ("partners", "hex_packages", "previous_snapshot")

    def __init__(self, partners_json, packages_csv, previous_snapshot_path=None):
        df_partners = self._load_partners(partners_json)
        grouped_packages = self._load_packages(packages_csv)

        self.partners = self._build_partners(df_partners)
        self.hex_packages = self._build_hex_packages(grouped_packages)
        self.previous_snapshot = self._load_previous_snapshot(previous_snapshot_path)

    def _load_previous_snapshot(self, path):
        if not path:
            return {}
        try:
            with open(path, "r") as f:
                return json.load(f)
        except FileNotFoundError:
            return {}

    def _load_packages(self, csv_path):
        df = pd.read_csv(csv_path)

        if "plan_date" in df.columns:
            df["plan_date"] = pd.to_datetime(df["plan_date"])
            num_days = df["plan_date"].nunique()
        else:
            num_days = 1

        df["lat_idx"] = df["latitude"].round(5)
        df["lon_idx"] = df["longitude"].round(5)

        grouped = (
            df.groupby(["lat_idx", "lon_idx"])
            .size()
            .reset_index(name="pkg_count")
        )

        grouped["daily_avg"] = grouped["pkg_count"] / num_days
        grouped.rename(
            columns={"lat_idx": "latitude", "lon_idx": "longitude"},
            inplace=True,
        )
        return grouped

    def _build_hex_packages(self, grouped_df):
        grouped_df["hex_id"] = [
            h3.latlng_to_cell(lat, lon, H3_RESOLUTION)
            for lat, lon in zip(grouped_df["latitude"], grouped_df["longitude"])
        ]
        return grouped_df.groupby("hex_id")["daily_avg"].sum().to_dict()

    def _load_partners(self, json_path):
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        df = pd.DataFrame(data["allMarkerData"])
        df = df[(df["status"] == "Active") & df["lat"].notnull()].copy()

        df["latitude"] = df["lat"].astype(float)
        df["longitude"] = df["lon"].astype(float)
        df["radius"] = pd.to_numeric(df["radius"], errors="coerce").fillna(1500)

        return df

    def _build_partners(self, df):
        partners = []
        for _, row in df.iterrows():
            origin_hex = h3.latlng_to_cell(
                row["latitude"], row["longitude"], H3_RESOLUTION
            )
            k = max(1, math.ceil((row["radius"] / 1000) / 0.174))
            partners.append(
                Partner(
                    partner_id=row["store_id"],
                    origin_hex=origin_hex,
                    capacity=int(row["capacity"]),
                    k=k,
                )
            )
        return partners


# =========================
# OPTIMIZATION ENGINE
# =========================
class OptimizationEngine:
    def __init__(self, partners: List[Partner], hex_packages: Dict[str, float]):
        self.partners = partners
        self.hex_packages = hex_packages

        self.hex_coverage = defaultdict(list)
        self.partner_demand = defaultdict(float)
        self.uncovered_hexes = {}

    def run(self):
        self._aggregate_demand_per_partner()
        self._compute_uncovered_hexes()
        return {
            "partner_demand": self.partner_demand,
            "hex_coverage": self.hex_coverage,
            "uncovered_hexes": self.uncovered_hexes,
        }

    def _aggregate_demand_per_partner(self):
        for p in self.partners:
            for h in h3.grid_disk(p.origin_hex, p.k):
                demand = self.hex_packages.get(h, 0)
                if demand > 0:
                    self.partner_demand[p.id] += demand
                    self.hex_coverage[h].append(p.id)

    def _compute_uncovered_hexes(self):
        self.uncovered_hexes = {
            h: d for h, d in self.hex_packages.items()
            if h not in self.hex_coverage
        }


# =========================
# DECISION ENGINE
# =========================
class DecisionEngine:
    def __init__(
        self,
        partners: List[Partner],
        hex_packages: Dict[str, float],
        optimization_output: Dict,
        previous_snapshot: Dict,
    ):
        self.partners = partners
        self.hex_packages = hex_packages
        self.partner_demand = optimization_output["partner_demand"]
        self.hex_coverage = optimization_output["hex_coverage"]
        self.uncovered_hexes = optimization_output["uncovered_hexes"]
        self.previous_snapshot = previous_snapshot or {}
        self.decisions = []

    def run(self):
        for partner in self.partners:
            self._evaluate_reduce_radius(partner)
            self._evaluate_increase_capacity(partner)

        self._evaluate_new_partner()
        self._apply_execution_status()
        return self.decisions

    def _evaluate_reduce_radius(self, partner: Partner):
        demand = self.partner_demand.get(partner.id, 0)

        if demand >= partner.capacity:
            return

        for k_candidate in range(partner.k - 1, 0, -1):
            covered_hexes = h3.grid_disk(partner.origin_hex, k_candidate)
            new_demand = sum(self.hex_packages.get(h, 0) for h in covered_hexes)

            if new_demand <= partner.capacity:
                self.decisions.append({
                    "entity": "PARTNER",
                    "partner_id": partner.id,
                    "decision": "REDUCE_RADIUS",
                    "current_k": partner.k,
                    "suggested_k": k_candidate,
                    "current_radius_m": partner.k * HEX_EDGE_M,
                    "suggested_radius_m": k_candidate * HEX_EDGE_M,
                    "reason": "Slack permite reducao de raio",
                })
                return

    def _evaluate_increase_capacity(self, partner: Partner):
        demand = self.partner_demand.get(partner.id, 0)

        if demand <= partner.capacity:
            return

        if partner.capacity >= MAX_CAPACITY:
            return

        suggested = min(MAX_CAPACITY, max(MIN_CAPACITY, math.ceil(demand)))
        if suggested > partner.capacity:
            self.decisions.append({
                "entity": "PARTNER",
                "partner_id": partner.id,
                "decision": "INCREASE_PARTNER_CAPACITY",
                "current_capacity": partner.capacity,
                "suggested_capacity": suggested,
                "reason": "Demanda excede capacidade atual",
            })

    def _evaluate_new_partner(self):
        if not self.uncovered_hexes:
            return

        self.decisions.append({
            "entity": "HEX",
            "decision": "NEW_PARTNER",
            "hex_count": len(self.uncovered_hexes),
            "total_packages": round(sum(self.uncovered_hexes.values()), 2),
            "reason": "Area descoberta",
        })

    def _apply_execution_status(self):
        for d in self.decisions:
            key = f"{d.get('partner_id','HEX')}_{d['decision']}"
            prev = self.previous_snapshot.get(key)

            if not prev:
                d["execution_status"] = "NEW"
            elif prev == d:
                d["execution_status"] = "NOT_EXECUTED"
            else:
                d["execution_status"] = "EXECUTED"


# =========================
# EXPORTERS
# =========================
def export_geojson(hex_packages, decisions, output_path):
    features = []

    for hex_id, demand in hex_packages.items():
        boundary = h3.cell_to_boundary(hex_id)
        coords = tuple(coord[::-1] for coord in boundary)

        decision = next(
            (d for d in decisions if d.get("entity") == "HEX"),
            {}
        )

        features.append({
            "type": "Feature",
            "geometry": {
                "type": "Polygon",
                "coordinates": [coords],
            },
            "properties": {
                "hex_id": hex_id,
                "partner_ids": decision.get("partner_ids", []),
                "packages": round(demand, 2),
                "decision": decision.get("decision"),
                "reason": decision.get("reason"),
                "execution_status": decision.get("execution_status"),
            },
        })

    geojson = {"type": "FeatureCollection", "features": features}

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(geojson, f, indent=2)


def save_snapshot(decisions, output_path):
    snapshot = {
        f"{d.get('partner_id','HEX')}_{d['decision']}": d
        for d in decisions
    }
    with open(output_path, "w") as f:
        json.dump(snapshot, f, indent=2)