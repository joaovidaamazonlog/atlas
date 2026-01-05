
# optimization_hub_full.py
# Full Optimization System: Cluster Coverage + Overlap + Reduction + CRO + Decision Engine + Map Output

import pandas as pd
import numpy as np
import geopandas as gpd
import json
import math
from shapely.geometry import Point, Polygon
from scipy.spatial import KDTree
import config

# =====================================================
# Utils
# =====================================================
def haversine(lat1, lon1, lat2, lon2):
    R = 6371000
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = (
        math.sin(dphi / 2) ** 2 +
        math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    )
    return 2 * R * math.atan2(math.sqrt(a), math.sqrt(1 - a))


# =====================================================
# Core Optimization
# =====================================================
class OptimizationHubDelivery:

    def __init__(self,  packages_path, partners_path, clusters_path):
        print("Iniciando Optimization Hub Delivery...")
        self.packages_path = packages_path
        self.partners_path = partners_path
        self.clusters_path = clusters_path
        
        # Carregar dados
        self.df_packages = pd.read_csv(packages_path)
        if 'data' in self.df_packages.columns:
            self.df_packages = (
                self.df_packages
                .groupby(['latitude', 'longitude', 'data'])
                .size()
                .reset_index(name='package_count')
            )
            self.df_packages = (
                self.df_packages
                .groupby(['latitude', 'longitude'])
                .agg({'package_count': 'mean'})
                .reset_index()
            )
        else:
            self.df_packages['package_count'] = 1

        with open(partners_path, 'r', encoding='utf-8') as f:
            self.partners_data = json.load(f)
        self.gdf_clusters = gpd.read_file(clusters_path)
        
        # Preparar DataFrame de parceiros
        self.df_partners = pd.DataFrame(self.partners_data['allMarkerData'])
        # Filtrar parceiros válidos (com lat/lon)
        self.df_partners = self.df_partners[
            (self.df_partners['status'] == 'Active') & 
            self.df_partners['lat'].notnull() & 
            self.df_partners['lon'].notnull()
        ]
        print("Dados carregados com sucesso.")

    # -------------------------------------------------
    # Cluster Coverage + Gaps
    # -------------------------------------------------
    def analyze_cluster_coverage(self, packages_per_partner=120):
        results = []

        for _, cluster in self.gdf_clusters.iterrows():
            cluster_pkgs = self.df_packages[
                self.df_packages.apply(
                    lambda r: cluster.geometry.contains(Point(r.longitude, r.latitude)), axis=1
                )
            ]

            total_packages = cluster_pkgs['package_count'].sum()

            partners = []
            for idx, p in self.df_partners.iterrows():
                d = cluster.geometry.centroid.distance(Point(p.lon, p.lat))
                if d * 111320 <= p.radius:
                    partners.append(idx)

            partners_count = len(partners)
            partners_needed = math.ceil(total_packages / packages_per_partner) if total_packages > 0 else 0
            missing = max(partners_needed - partners_count, 0)

            coverage_ratio = partners_count / partners_needed if partners_needed > 0 else 1

            priority_score = (
                (1 - coverage_ratio) * 0.7 +
                (total_packages / (packages_per_partner * 2)) * 0.3
            )

            results.append({
                "cluster_id": cluster.cluster,
                "delivery_station": cluster.delivery_station,
                "packages": int(total_packages),
                "partners": partners,
                "partners_count": partners_count,
                "partners_needed": partners_needed,
                "partners_missing": missing,
                "coverage_ratio": round(coverage_ratio, 2),
                "priority_score": round(priority_score, 3),
                "geometry": cluster.geometry
            })

        return results

    # -------------------------------------------------
    # Overlap v2
    # -------------------------------------------------
    def analyze_overlap_v2(self):
        tree = KDTree(self.df_partners[['lat', 'lon']].values)
        max_radius_deg = self.df_partners['radius'].max() / 111320

        pkg_coords = self.df_packages[['latitude', 'longitude']].values
        candidates = tree.query_ball_point(pkg_coords, r=max_radius_deg)

        overlapping = 0
        intensity = 0

        for i, idxs in enumerate(candidates):
            covers = 0
            for p_idx in idxs:
                p = self.df_partners.iloc[p_idx]
                if haversine(pkg_coords[i][0], pkg_coords[i][1], p.lat, p.lon) <= p.radius:
                    covers += 1
            if covers >= 2:
                overlapping += 1
                intensity += covers - 1

        return {
            "overlapping_packages": overlapping,
            "overlap_percent": round(overlapping / len(self.df_packages) * 100, 2),
            "overlap_intensity": intensity
        }

    # -------------------------------------------------
    # Reduction v2
    # -------------------------------------------------
    def analyze_reduction_v2(self, min_retention=0.8):
        results = []
        pkg_coords = self.df_packages[['latitude', 'longitude']].values

        for idx, p in self.df_partners.iterrows():
            dists = np.array([
                haversine(lat, lon, p.lat, p.lon) for lat, lon in pkg_coords
            ])

            current_mask = dists <= p.radius
            current_volume = self.df_packages.loc[current_mask, 'package_count'].sum()
            if current_volume == 0:
                continue

            test_radii = np.percentile(dists[current_mask], [40, 60, 80]).astype(int)

            best = None
            for r in test_radii:
                mask = dists <= r
                retained = self.df_packages.loc[mask, 'package_count'].sum()
                ratio = retained / current_volume
                if ratio >= min_retention:
                    best = (r, ratio)

            if best:
                results.append({
                    "partner_id": idx,
                    "current_radius": int(p.radius),
                    "recommended_radius": int(best[0]),
                    "retention_ratio": round(best[1], 2),
                    "risk": "LOW" if best[1] >= 0.85 else "MEDIUM"
                })

        return results

    # -------------------------------------------------
    # CRO Detection
    # -------------------------------------------------
    def analyze_cro(self, reductions, min_overlap_release=50):
        cro_ops = []

        for r in reductions:
            released = (1 - r['retention_ratio']) * self.df_packages['package_count'].sum()
            if released >= min_overlap_release:
                cro_ops.append({
                    "partner_id": r['partner_id'],
                    "released_packages": int(released),
                    "confidence": "HIGH" if r['risk'] == "LOW" else "MEDIUM"
                })

        return cro_ops


# =====================================================
# Decision Engine (MAIN)
# =====================================================
class DecisionEngine:

    def __init__(self, optimizer):
        self.optimizer = optimizer

    def run(self):
        print("Executando Analise de coverage")
        clusters = self.optimizer.analyze_cluster_coverage()
        print("Executando Analise de sobreposicao")
        overlap = self.optimizer.analyze_overlap_v2()
        print("Executando Analise de reducao")
        reductions = self.optimizer.analyze_reduction_v2()
        print("Executando Analise de CRO")
        cro = self.optimizer.analyze_cro(reductions)

        decisions = []

        # Expansion by gap
        for c in clusters:
            if c['partners_missing'] > 0:
                decisions.append({
                    "action": "NEW_PARTNER",
                    "cluster_id": c['cluster_id'],
                    "delivery_station": c['delivery_station'],
                    "expected_packages": c['packages'],
                    "priority": c['priority_score'],
                    "source": "GAP"
                })

        # Reduction
        for r in reductions:
            if r['risk'] == "LOW" and r['recommended_radius'] < r['current_radius']:
                decisions.append({
                    "action": "REDUCE_RADIUS",
                    "partner_id": r['partner_id'],
                    "from": r['current_radius'],
                    "to": r['recommended_radius'],
                    "priority": 0.5,
                    "source": "OVERLAP"
                })

        # CRO Expansion
        for c in cro:
            if c['confidence'] == "HIGH":
                decisions.append({
                    "action": "NEW_PARTNER",
                    "source": "CRO",
                    "expected_packages": c['released_packages'],
                    "priority": 0.3
                })

        decisions = sorted(decisions, key=lambda x: x['priority'], reverse=True)

        return {
            "overlap": overlap,
            "clusters": clusters,
            "cro": cro,
            "decisions": decisions
        }

    # -------------------------------------------------
    # Map Output
    # -------------------------------------------------
    def export_map_layers(self, clusters, path="clusters.geojson"):
        print(f"Exportando camadas de mapa para {path}")
        gdf = gpd.GeoDataFrame(clusters, geometry=[c['geometry'] for c in clusters], crs="EPSG:4326")
        gdf.to_file(path, driver="GeoJSON")
        return path


# =====================================================
# MAIN
# =====================================================
if __name__ == "__main__":

    optimizer = OptimizationHubDelivery(
        packages_path= config.BASE_DIR,
        partners_path= config.DEST_FOLDER+'\\dados_mapa.json',
        clusters_path= config.DEST_FOLDER+'\\clusters_output_filled.geojson'
    )
    
    engine = DecisionEngine(optimizer)
    result = engine.run()
    
    print(json.dumps(result, indent=2))

    engine.export_map_layers(result['clusters'])
