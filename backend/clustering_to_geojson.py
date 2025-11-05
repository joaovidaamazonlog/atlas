import pandas as pd
import numpy as np
import json
import os
import config
from math import ceil
from pyproj import Transformer
from shapely.geometry import Point, MultiPoint, mapping
from shapely.ops import transform as shapely_transform, unary_union
from sklearn.cluster import KMeans
import logging
from typing import Optional
    # opcional: alphashape (se quiser concave hull mais natural). Se não estiver instalado, o código cai para convex hull.
try:
    import alphashape
    HAS_ALPHASHAPE = True
except Exception:
    HAS_ALPHASHAPE = False

logging.basicConfig(level=logging.INFO)

class ClusterToGeoJSON:
    def __init__(self, csv_path: str, max_cluster_size: int = 25):
        self.csv_path = csv_path
        self.max_cluster_size = max_cluster_size
        self.df = self._load_and_preprocess_data()

    def _load_and_preprocess_data(self) -> pd.DataFrame:
        df = pd.read_csv(self.csv_path, delimiter=";")
        
        """# Normalizar e converter colunas de coordenadas
        df["Latitude"] = pd.to_numeric(
            df["Latitude"].astype(str).str.replace(",", "."),
            errors="coerce"
        )
        df["Longitude"] = pd.to_numeric(
            df["Longitude"].astype(str).str.replace(",", "."),
            errors="coerce"
        )"""
        
        # Remover linhas com coordenadas inválidas
        df.dropna(subset=["Latitude", "Longitude"], inplace=True)
        
        df["cluster"] = None
        df["unclustered_reason"] = None
        return df

    def _divide_cluster_into_subgroups(
        self, df_cluster: pd.DataFrame, ds_name: str, start_id: int
    ):
        subclusters_info = []
        coords = df_cluster[["Longitude", "Latitude"]].values

        n_splits = max(1, (len(df_cluster) + self.max_cluster_size - 1) // self.max_cluster_size)
        n_splits = min(n_splits, len(df_cluster))

        if n_splits == 1:
            subclusters_info.append({
                "name": f"{ds_name}_{start_id}",
                "points": df_cluster
            })
            return subclusters_info, start_id + 1

        kmeans_sub = KMeans(n_clusters=n_splits, random_state=42, n_init=15)
        labels = kmeans_sub.fit_predict(coords)

        for i in range(n_splits):
            subcluster_points = df_cluster[labels == i]
            if not subcluster_points.empty:
                subclusters_info.append({
                    "name": f"{ds_name}_{start_id}",
                    "points": subcluster_points
                })
                start_id += 1

        return subclusters_info, start_id

    def generate_clusters(self):
        all_ds_names = self.df["Delivery_Station"].unique()

        for ds_name in all_ds_names:
            ds_df = self.df[self.df["Delivery_Station"] == ds_name].copy()
            if ds_df.empty:
                continue

            cluster_id = 1  # reinicia contagem para cada DS
            coords = ds_df[["Longitude", "Latitude"]].values

            n_clusters_initial = ceil(len(ds_df) / self.max_cluster_size)
            kmeans = KMeans(n_clusters=n_clusters_initial, random_state=42, n_init=10)
            labels = kmeans.fit_predict(coords)
            ds_df["raw_cluster"] = labels

            for label in set(labels):
                cluster_points = ds_df[ds_df["raw_cluster"] == label]
                if cluster_points.empty:
                    continue

                if len(cluster_points) > self.max_cluster_size:
                    subclusters, cluster_id = self._divide_cluster_into_subgroups(
                        cluster_points, ds_name, cluster_id
                    )
                    for subcluster in subclusters:
                        subcluster_name = subcluster["name"]
                        subcluster_df = subcluster["points"]
                        self.df.loc[subcluster_df.index, "cluster"] = subcluster_name
                else:
                    cluster_name = f"{ds_name}_{cluster_id}"
                    self.df.loc[cluster_points.index, "cluster"] = cluster_name
                    cluster_id += 1

            # Garantir que nenhum ponto desse DS fique sem cluster
            leftovers = self.df[
                (self.df["Delivery_Station"] == ds_name) & (self.df["cluster"].isna())
            ]
            if not leftovers.empty:
                self.df.loc[leftovers.index, "cluster"] = f"{ds_name}_{cluster_id}"
                cluster_id += 1

        return self.df

    def to_geojson (self, df: Optional[pd.DataFrame] = None,
                output_path: str = "clusters.geojson",
                buffer_meters: float = 350,
                buffer_resolution: int = 16,
                method: str = "alpha",
                enforce_single_polygon: bool = False,
                smooth_radius: float = 0.0):
        """
        Gera GeoJSON com polígonos de clusters bufferizados.
        Parâmetros principais:
        - self: objeto com atributo .df (compatibilidade com versões anteriores)
        - df: DataFrame com colunas 'Longitude', 'Latitude', 'cluster' (se fornecido, usa este)
        - output_path: caminho para salvar o GeoJSON
        - buffer_meters: raio do buffer em metros (default 350)
        - buffer_resolution: resolução do círculo (quanto maior, mais suave)
        - method: 'dissolve' (default: buffer em multipoint e unary_union),
                    'convex' (convex_hull + buffer),
                    'alpha' (se alphashape instalado: concave hull + buffer)
        - enforce_single_polygon: se True e geometria for MultiPolygon, converte para um único Polygon (usando convex_hull)
        - smooth_radius: se >0, aplica um small morphological smooth .buffer(+r).buffer(-r) em UTM para suavizar irregularidades
        Retorna:
        - dicionário GeoJSON (além de salvar no arquivo)
        """

        # obter DataFrame
        if df is None:
            if (self is None) or (not hasattr(self, "df")):
                raise ValueError("Passe 'df' como argumento ou chame como método com 'self.df' presente.")
            df = getattr(self, "df")

        # validar colunas
        for col in ("Longitude", "Latitude", "cluster"):
            if col not in df.columns:
                raise ValueError(f"Coluna obrigatória '{col}' não encontrada no DataFrame.")

        # garantir valores numéricos e remover nulos
        df = df.copy()
        df["Longitude"] = pd.to_numeric(df["Longitude"], errors="coerce")
        df["Latitude"] = pd.to_numeric(df["Latitude"], errors="coerce")
        df = df.dropna(subset=["Longitude", "Latitude", "cluster"])
        if df.empty:
            raise ValueError("DataFrame está vazio depois de converter coordenadas.")

        # prepare transformers (WGS84 <-> UTM SIRGAS2000 zone 23S EPSG:31983)
        transformer_to_utm = Transformer.from_crs("EPSG:4326", "EPSG:31983", always_xy=True)
        transformer_to_wgs84 = Transformer.from_crs("EPSG:31983", "EPSG:4326", always_xy=True)

        def project_to_utm(x, y, z=None):
            # pyproj aceita z opcional; repassamos se existir
            if z is None:
                return transformer_to_utm.transform(x, y)
            return transformer_to_utm.transform(x, y, z)

        def project_to_wgs84(x, y, z=None):
            if z is None:
                return transformer_to_wgs84.transform(x, y)
            return transformer_to_wgs84.transform(x, y, z)

        features = []

        # iterar por clusters
        clusters = sorted(df["cluster"].unique())
        logging.info(f"Encontrados {len(clusters)} clusters.")

        for cluster_name in clusters:
            cdf = df[df["cluster"] == cluster_name]
            pts = [Point(lon, lat) for lon, lat in zip(cdf["Longitude"], cdf["Latitude"])]

            logging.info(f"Cluster '{cluster_name}': {len(pts)} pontos.")

            if len(pts) < 3:
                method = "convex"  # garantir método seguro para poucos pontos
                logging.info(f"Cluster '{cluster_name}' tem menos de 3 pontos; forçando método 'convex'.")
            else:
                method = method.lower()

            multipoint_wgs = MultiPoint(pts)

            # projetar para UTM (metros)
            multipoint_utm = shapely_transform(project_to_utm, multipoint_wgs)

            # construir a geometria em UTM conforme método
            dissolved_utm = None
            try:
                if method == "dissolve":
                    # buffer diretamente no multipoint (retorna a união dos buffers)
                    dissolved_utm = multipoint_utm.buffer(buffer_meters, resolution=buffer_resolution)
                    # garantir dissolução/unificação (às vezes retorna GeometryCollection)
                    dissolved_utm = unary_union(dissolved_utm)
                elif method == "alpha" and HAS_ALPHASHAPE:
                    from scipy.spatial import Delaunay
                    # alphashape pode falhar se os pontos forem colineares ou quase colineares
                    if len(pts) >= 4:
                    # alphashape espera coordenadas planas (UTM é apropriado)
                        # converter para lista de shapely Points
                        shapely_points = [Point(p.x, p.y) for p in multipoint_utm.geoms]
                        if len(shapely_points) < 4:
                            # alphashape pode falhar com <4 pontos -> fallback para dissolve
                            dissolved_utm = multipoint_utm.convex_hull(buffer_meters, resolution=buffer_resolution)
                        else:
                            try:
                                coords = [(p.x, p.y) for p in shapely_points]
                                tri = Delaunay(coords)
                                alpha = alphashape.optimizealpha(shapely_points, 15)
                                concave = alphashape.alphashape(coords, alpha)
                                if concave.is_empty or not hasattr(concave, "buffer"):
                                    logging.warning(f"Alphashape retornou geometria inválida para cluster {cluster_name}; usando convex_hull como fallback.")
                                    # alphashape retorna polígono concave sem buffer; aplicar buffer para garantir raio desejado
                                    dissolved_utm = multipoint_utm.convex_hull.buffer(buffer_meters, resolution=buffer_resolution)
                                else:
                                    dissolved_utm = concave.buffer(buffer_meters, resolution=buffer_resolution)
                            except Exception as alpha_error:
                                logging.exception(f"Erro com alphashape no cluster {cluster_name}: {alpha_error}; usando convex_hull como fallback.")
                                dissolved_utm = multipoint_utm.convex_hull.buffer(buffer_meters, resolution=buffer_resolution)
                elif method == "convex":
                    # pega o convex hull dos pontos e aplica um buffer
                    dissolved_utm = multipoint_utm.convex_hull.buffer(buffer_meters, resolution=buffer_resolution)
                else:
                    # fallback
                    dissolved_utm = multipoint_utm.buffer(buffer_meters, resolution=buffer_resolution)
                    dissolved_utm = unary_union(dissolved_utm)
            except Exception as e:
                logging.exception(f"Erro criando geometria do cluster {cluster_name}: {e}")
                # fallback seguro: buffer ponto-a-ponto e unir
                buffers = [p.buffer(buffer_meters, resolution=buffer_resolution) for p in multipoint_utm.geoms]
                dissolved_utm = unary_union(buffers)

            # smooth opcional (pequeno fechamento e abertura para suavizar)
            if smooth_radius and smooth_radius > 0:
                try:
                    dissolved_utm = dissolved_utm.buffer(smooth_radius).buffer(-smooth_radius)
                except Exception:
                    logging.warning("Smooth radius falhou; ignorando smooth.")

            # corrigir eventual geometria inválida
            try:
                dissolved_utm = dissolved_utm.buffer(0)
            except Exception:
                pass

            # se for MultiPolygon e o usuário pedir um único polígono, converte para convex_hull (pode perder concavidade)
            if enforce_single_polygon and dissolved_utm.geom_type == "MultiPolygon":
                logging.info(f"Cluster {cluster_name}: convertendo MultiPolygon -> Polygon via convex_hull (enforce_single_polygon=True).")
                dissolved_utm = dissolved_utm.convex_hull

            # calcular área em m² (UTM)
            try:
                area_m2 = float(dissolved_utm.area)
            except Exception:
                area_m2 = None

            # projetar de volta para WGS84 para GeoJSON
            dissolved_wgs = shapely_transform(project_to_wgs84, dissolved_utm)
            centroid_wgs = dissolved_wgs.centroid

            # propriedades extras
            props = {
                "cluster": str(cluster_name),
                "delivery_station": str(cdf["Delivery_Station"].iloc[0]) if "Delivery_Station" in cdf.columns else None,
                "num_points": int(len(cdf)),
                "centroid_lon": float(centroid_wgs.x),
                "centroid_lat": float(centroid_wgs.y),
                "area_m2": area_m2,
                # opcional: lista de nomes (se existir coluna Nome)
                "points_names": cdf["Nome"].tolist() if "Nome" in cdf.columns else None
            }

            feature = {
                "type": "Feature",
                "geometry": mapping(dissolved_wgs),
                "properties": props
            }
            features.append(feature)

        geojson = {"type": "FeatureCollection", "features": features}

        # salvar
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(geojson, f, ensure_ascii=False, indent=2)

        logging.info(f"GeoJSON salvo em: {output_path}")
        return geojson


if __name__ == "__main__":
    csv_input_path = config.CSV_INPUT_PATH
    geojson_output_path = os.path.join(config.OUTPUT_JSON_DIR, "clusters_output.geojson")
    os.makedirs("data", exist_ok=True)
    os.makedirs("output", exist_ok=True)

    generator = ClusterToGeoJSON(csv_input_path, max_cluster_size=15)
    clustered_df = generator.generate_clusters()
    generator.to_geojson(clustered_df,geojson_output_path, method='convex')

    print("Processo de clustering e geração de GeoJSON concluído.")