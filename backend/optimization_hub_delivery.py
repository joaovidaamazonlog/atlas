import pandas as pd
import numpy as np
import json
import geopandas as gpd
from shapely.geometry import Point, Polygon
from scipy.spatial import KDTree
import os
import config


class OptimizationHubDelivery:
    def __init__(self, packages_path, partners_path, clusters_path):
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
        
    def run_all_analyses(self):
        print("Executando todas as análises...")
        results = {}
        results['eligibility'] = self.analyze_eligibility()
        results['density_reduction'] = self.analyze_density_reduction()
        results['gaps'] = self.generate_optimization_layers()
        results['overlap'] = self.analyze_overlap()
        results['cluster_coverage'] = self.analyze_cluster_coverage()
        return results

    def analyze_eligibility(self):
        """1. Pacotes elegíveis por parceiro (Heatmap de cobertura)"""
        print("Analisando elegibilidade...")
        # Criar KDTree para busca rápida de vizinhos
        tree = KDTree(self.df_partners[['lat', 'lon']].values)
        
        # Para cada pacote, encontrar o parceiro mais próximo
        distances, indices = tree.query(self.df_packages[['latitude', 'longitude']].values, k=1)
        
        # Converter distâncias de graus para metros (aproximado)
        # 1 grau ~ 111.32 km
        distances_m = distances * 111320
        
        self.df_packages['nearest_partner_idx'] = indices
        self.df_packages['distance_to_partner'] = distances_m
        
        # Verificar se está dentro do raio do parceiro
        partner_radii = self.df_partners['radius'].values
        self.df_packages['is_eligible'] = self.df_packages.apply(
            lambda x: x['distance_to_partner'] <= partner_radii[int(x['nearest_partner_idx'])], axis=1
        )
        
        summary = self.df_packages[self.df_packages['is_eligible']].groupby('nearest_partner_idx').size()
        return summary.to_dict()

    def analyze_density_reduction(self, thresholds=[1000, 750, 500, 300], min_volume=45):
        """2. Análise de densidade para redução de raio"""
        print("Analisando redução de raio...")
        reduction_results = []
        
        for idx, partner in self.df_partners.iterrows():
            partner_packages = self.df_packages[self.df_packages['nearest_partner_idx'] == idx]
            
            partner_res = {'store_id': partner.get('store_id'), 'name': partner.get('name'), 'current_radius': partner.get('radius')}
            
            for r in thresholds:
                count = partner_packages.loc[partner_packages['distance_to_partner'] <= r, 'package_count'].sum()
                partner_res[f'vol_{r}m'] = int(count)
                partner_res[f'eligible_{r}m'] = count >= min_volume
            
            reduction_results.append(partner_res)
            
        return pd.DataFrame(reduction_results)

    def generate_optimization_layers(self, grid_size_gaps=0.005, grid_size_heatmap=0.002):
        """Gera um único arquivo GeoJSON com a camada de Gaps (hexágonos) e a camada de Heatmap (pontos)."""
        print("Gerando camadas de otimização (Gaps e Heatmap)... ")
        all_features = []

        # --- 1. Geração de Gaps (Hexágonos/Quadrados) ---
        self.df_packages["grid_lat_gap"] = np.round(self.df_packages["latitude"] / grid_size_gaps) * grid_size_gaps
        self.df_packages["grid_lon_gap"] = np.round(self.df_packages["longitude"] / grid_size_gaps) * grid_size_gaps
        grid_counts = self.df_packages.groupby(["grid_lat_gap", "grid_lon_gap"]).size().reset_index(name="package_count")
        
        tree = KDTree(self.df_partners[["lat", "lon"]].values)
        distances, _ = tree.query(grid_counts[["grid_lat_gap", "grid_lon_gap"]].values, k=1)
        grid_counts["dist_to_nearest_partner"] = distances * 111320
        
        gaps = grid_counts[(grid_counts["dist_to_nearest_partner"] > 2000) & (grid_counts["package_count"] > 30)]
        
        for _, row in gaps.iterrows():
            lat, lon = row["grid_lat_gap"], row["grid_lon_gap"]
            d = grid_size_gaps / 2.0
            poly = Polygon([
                (lon - d, lat - d), (lon + d, lat - d), (lon + d, lat + d), (lon - d, lat + d), (lon - d, lat - d)
            ])
            all_features.append({
                "type": "Feature",
                "properties": {
                    "type": "gap_opportunity",
                    "package_count": int(row["package_count"])
                },
                "geometry": poly.__geo_interface__
            })

        # --- 2. Geração de Heatmap (Pontos com intensidade) ---
        self.df_packages["grid_lat_heat"] = np.round(self.df_packages["latitude"] / grid_size_heatmap) * grid_size_heatmap
        self.df_packages["grid_lon_heat"] = np.round(self.df_packages["longitude"] / grid_size_heatmap) * grid_size_heatmap
        heatmap_counts = self.df_packages.groupby(["grid_lat_heat", "grid_lon_heat"]).size().reset_index(name="intensity")

        for _, row in heatmap_counts.iterrows():
            all_features.append({
                "type": "Feature",
                "properties": {
                    "type": "heatmap_point",
                    "intensity": int(row["intensity"])
                },
                "geometry": Point(row["grid_lon_heat"], row["grid_lat_heat"]).__geo_interface__
            })

        # --- Salvar GeoJSON unificado ---
        geojson = {"type": "FeatureCollection", "features": all_features}
        output_path = os.path.join(os.path.dirname(self.partners_path), "optimization_layers.geojson")
        with open(output_path, "w") as f:
            json.dump(geojson, f)
        print(f"Arquivo de camadas de otimização salvo em: {output_path}")
        return gaps

    def analyze_overlap(self):
        """4. Análise de sobreposição de áreas"""
        print("Analisando sobreposição (versão otimizada)...")
        # Usar KDTree para encontrar parceiros próximos
        tree = KDTree(self.df_partners[['lat', 'lon']].values)
        
        # Encontrar todos os parceiros em um raio de 5km (máximo esperado)
        max_radius_deg = 5000 / 111320
        indices_list = tree.query_ball_point(self.df_packages[['latitude', 'longitude']].values, r=max_radius_deg)
        
        # Vetorizar o cálculo de distância para os parceiros encontrados
        overlap_counts = np.zeros(len(self.df_packages), dtype=int)
        
        # Converter parceiros para arrays numpy para acesso rápido
        p_lats = self.df_partners['lat'].values
        p_lons = self.df_partners['lon'].values
        p_radii = self.df_partners['radius'].values
        
        pkg_lats = self.df_packages['latitude'].values
        pkg_lons = self.df_packages['longitude'].values
        
        for i, indices in enumerate(indices_list):
            if not indices:
                continue
            
            # Distância euclidiana aproximada em metros
            dists = np.sqrt((pkg_lats[i] - p_lats[indices])**2 + (pkg_lons[i] - p_lons[indices])**2) * 111320
            overlap_counts[i] = np.sum(dists <= p_radii[indices])
            
        self.df_packages['partner_count'] = overlap_counts
        overlapping_packages = self.df_packages[self.df_packages['partner_count'] > 1]
        
        return {
            'total_overlapping_packages': int(len(overlapping_packages)),
            'percent_overlap': float(len(overlapping_packages) / len(self.df_packages) * 100)
        }

    def analyze_cluster_coverage(self):
        """5. Cobertura por cluster/área"""
        print("Analisando cobertura por cluster...")
        # Converter pacotes para GeoDataFrame
        geometry = [Point(xy) for xy in zip(self.df_packages.longitude, self.df_packages.latitude)]
        gdf_packages = gpd.GeoDataFrame(self.df_packages, geometry=geometry, crs="EPSG:4326")
        
        # Garantir que os clusters estão no mesmo CRS
        self.gdf_clusters = self.gdf_clusters.to_crs("EPSG:4326")
        
        # Spatial join entre pacotes e clusters
        joined = gpd.sjoin(gdf_packages, self.gdf_clusters, how="left", predicate="within")
        pkg_counts = joined.groupby('cluster').size().reset_index(name='package_count')
        
        # Contar parceiros por cluster
        geometry_partners = [Point(xy) for xy in zip(self.df_partners.lon, self.df_partners.lat)]
        gdf_partners = gpd.GeoDataFrame(self.df_partners, geometry=geometry_partners, crs="EPSG:4326")
        partner_joined = gpd.sjoin(gdf_partners, self.gdf_clusters, how="left", predicate="within")
        partner_counts = partner_joined.groupby('cluster').size().reset_index(name='partner_count')
        
        cluster_analysis = self.gdf_clusters.merge(pkg_counts, on='cluster', how='left')
        cluster_analysis = cluster_analysis.merge(partner_counts, on='cluster', how='left')
        
        return cluster_analysis[['cluster', 'package_count', 'partner_count']]

    def simulate_scenario(self, partners_to_remove=[], partners_to_add=[]):
        """6. Simulação de cenários"""
        print("Simulando cenário...")
        # Criar cópia dos parceiros e aplicar mudanças
        temp_partners = self.df_partners.copy()
        if partners_to_remove:
            temp_partners = temp_partners[~temp_partners['store_id'].isin(partners_to_remove)]
        
        if partners_to_add:
            new_df = pd.DataFrame(partners_to_add)
            temp_partners = pd.concat([temp_partners, new_df], ignore_index=True)
            
        # Recalcular cobertura
        tree = KDTree(temp_partners[['lat', 'lon']].values)
        distances, indices = tree.query(self.df_packages[['latitude', 'longitude']].values, k=1)
        distances_m = distances * 111320
        
        radii = temp_partners['radius'].values
        eligible_count = sum(distances_m <= radii[indices])
        
        return {
            'new_eligible_total': int(eligible_count),
            'coverage_change': int(eligible_count - self.df_packages['is_eligible'].sum())
        }

if __name__ == "__main__":
    # Exemplo de uso
    hub = OptimizationHubDelivery(
        packages_path= config.BASE_DIR,
        partners_path= config.DEST_FOLDER+'\\dados_mapa.json',
        clusters_path= config.DEST_FOLDER+'\\clusters_output_filled.geojson'
    )
    
    # Executar elegibilidade primeiro para marcar os pacotes
    hub.analyze_eligibility()
    
    # 2. Redução de raio
    reduction = hub.analyze_density_reduction()
    print("\n--- Redução de Raio (Amostra) ---")
    print(reduction.head())
    
    # 3. Gaps
    gaps = hub.generate_optimization_layers()
    print("\n--- Gaps de Cobertura (Amostra) ---")
    print(gaps.head())
    
    # 4. Sobreposição
    overlap = hub.analyze_overlap()
    print("\n--- Análise de Sobreposição ---")
    print(overlap)
    
    # 5. Cluster
    clusters = hub.analyze_cluster_coverage()
    print("\n--- Cobertura por Cluster (Amostra) ---")
    print(clusters.head())
    
    # 6. Simulação
    sim = hub.simulate_scenario(partners_to_remove=['None']) # Exemplo removendo o ID 'None'
    print("\n--- Simulação de Cenário ---")
    print(sim)
