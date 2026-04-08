import json
import h3
import pandas as pd
import config as configuration
from pathlib import Path
from datetime import datetime
from shapely.geometry import shape, Point
from shapely.ops import unary_union

# =====================================================
# CONFIGURAÇÕES E CONSTANTES
# =====================================================

class Config:
    """Configurações centralizadas do sistema."""
    BASE_PACKAGES = configuration.BASE_PACKAGES
    DEST_FOLDER = configuration.DEST_FOLDER

# =====================================================
# SERVIÇO SIMPLIFICADO PARA GERAÇÃO DE HEXÁGONOS
# =====================================================

class HexagonGenerator:
    def __init__(self):
        self.demand_df: pd.DataFrame = pd.DataFrame()
        self.hex_to_ceps: dict = {}
        self.hex_radius_map: dict = {}  # Mapa de hex para raio em milhas

    def load_packages_data(self):
        """Carrega apenas os dados de pacotes e gera hexágonos H3 resolução 7."""
        print(f"[{datetime.now()}] Carregando dados de pacotes...")

        # Carregar Demandas (Pacotes)
        df = pd.read_csv(Config.BASE_PACKAGES)
        if 'cep' in df.columns:
            df['cep'] = df['cep'].astype(str).str.replace(r'\D', '', regex=True).str.zfill(8)

        if 'hex' not in df.columns:
            # Usar resolução 7
            df["hex"] = [h3.latlng_to_cell(la, lo, 7) for la, lo in zip(df.latitude, df.longitude)]

        days = pd.to_datetime(df.plan_date).nunique() or 1

        # Agrupar por Estação e Hexágono
        raw_grouped = df.groupby(["station_code", "hex"]).size().reset_index(name="qty")
        raw_grouped["avg_demand"] = (raw_grouped["qty"] / days).round(0).astype(int)

        # Tratamento de duplicidade: Winner Takes All
        hex_totals = raw_grouped.groupby("hex")["avg_demand"].sum().reset_index(name="total_demand")
        hex_winners = raw_grouped.sort_values(by="avg_demand", ascending=False).drop_duplicates(subset=["hex"], keep="first")[["hex", "station_code"]]
        self.demand_df = pd.merge(hex_winners, hex_totals, on="hex")
        self.demand_df.rename(columns={"total_demand": "avg_demand"}, inplace=True)

        print(f"   - Hexágonos únicos após unificação: {len(self.demand_df)}")

        # Criar mapeamento hex -> CEPs
        if 'cep' in df.columns:
            self.hex_to_ceps = df.groupby('hex')['cep'].apply(set).to_dict()

    def generate_hex_geojson(self, output_filename="hexagons_res7.geojson"):
        """Gera GeoJSON com hexágonos H3 resolução 7 e propriedades solicitadas."""
        features = []

        for _, row in self.demand_df.iterrows():
            hex_id = row['hex']
            station_code = row['station_code']
            total_packages = int(row['avg_demand'])
            ceps = list(self.hex_to_ceps.get(hex_id, []))[:10]  # Limitar a 10 CEPs por hex

            # Obter geometria do hexágono H3
            try:
                boundary = h3.cell_to_boundary(hex_id)
                coords = [[c[1], c[0]] for c in boundary]  # [lon, lat]
                coords.append(coords[0])  # Fechar o polígono

                feature = {
                    "type": "Feature",
                    "geometry": {
                        "type": "Polygon",
                        "coordinates": [coords]
                    },
                    "properties": {
                        "station_code": station_code,
                        "total_packages": total_packages,
                        "ceps": ceps
                    }
                }
                features.append(feature)
            except Exception as e:
                print(f"Erro ao processar hex {hex_id}: {e}")
                continue

        geojson = {
            "type": "FeatureCollection",
            "features": features
        }

        # Salvar arquivo
        dest = Path(Config.DEST_FOLDER)
        dest.mkdir(exist_ok=True)
        output_path = dest / output_filename

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(geojson, f, ensure_ascii=False, indent=2)

        print(f"✅ GeoJSON salvo em {output_path}")
        print(f"   - Total de hexágonos: {len(features)}")

    def get_hex_centroids_from_jurisdiction(self):
        """
        Cobre os polígonos de jurisdiction.geojson com círculos cujos centroids
        estão DENTRO da área do polígono, sem overlap excessivo.

        Estratégia de resolução H3 por raio:
        - 2 milhas (~3.2km) → res 8 (centroids ~3.8km apart, overlap mínimo)
        - 1 milha (~1.6km) → res 9 (centroids ~1.4km apart, cobertura densa)

        Raio: 2 milhas para polígonos grandes (área >= 0.05°²), 1 milha para pequenos.

        Retorna DataFrame com: delivery_station, hex, latitude, longitude, radius_miles
        """
        LARGE_POLYGON_AREA_THRESHOLD = 0.05  # graus² (~600km²)
        # Resolução H3 alinhada ao diâmetro do círculo para minimizar overlap
        RADIUS_TO_H3_RES = {2.0: 8, 1.0: 9}

        print(f"[{datetime.now()}] Cobrindo polígonos de jurisdiction.geojson com círculos...")

        try:
            jurisdiction_path = Path(configuration.BASE_JURISDICTION)
            with open(jurisdiction_path, 'r', encoding='utf-8') as f:
                jurisdiction_geojson = json.load(f)
        except FileNotFoundError:
            print(f"❌ Arquivo não encontrado: {jurisdiction_path}")
            return pd.DataFrame()
        except json.JSONDecodeError:
            print(f"❌ Erro ao decodificar JSON: {jurisdiction_path}")
            return pd.DataFrame()

        centroid_data = []

        for feature in jurisdiction_geojson.get('features', []):
            try:
                delivery_station = feature.get('properties', {}).get('delivery_station')
                if not delivery_station:
                    continue

                geometry = shape(feature['geometry'])

                # Raio e resolução H3 baseados na área total da geometria
                radius_miles = 2.0 if geometry.area >= LARGE_POLYGON_AREA_THRESHOLD else 1.0
                h3_res = RADIUS_TO_H3_RES[radius_miles]

                # Coletar todos os sub-polígonos (suporte a MultiPolygon e Polygon)
                if geometry.geom_type == 'MultiPolygon':
                    polygons = list(geometry.geoms)
                elif geometry.geom_type == 'Polygon':
                    polygons = [geometry]
                else:
                    print(f"   ⚠ {delivery_station}: tipo de geometria não suportado ({geometry.geom_type})")
                    continue

                station_hexes: set = set()

                for poly in polygons:
                    exterior_coords = [[c[1], c[0]] for c in poly.exterior.coords]
                    holes = [[[c[1], c[0]] for c in ring.coords] for ring in poly.interiors]
                    h3_poly = h3.LatLngPoly(exterior_coords, *holes)
                    filled = h3.h3shape_to_cells(h3_poly, h3_res)
                    station_hexes.update(filled)

                # Filtrar: manter apenas hexágonos cujo centroid está dentro do polígono
                valid_count = 0
                for hex_id in station_hexes:
                    hex_lat, hex_lon = h3.cell_to_latlng(hex_id)
                    if not geometry.contains(Point(hex_lon, hex_lat)):
                        continue
                    self.hex_radius_map[hex_id] = radius_miles
                    centroid_data.append({
                        'delivery_station': delivery_station,
                        'hex': hex_id,
                        'latitude': hex_lat,
                        'longitude': hex_lon,
                        'radius_miles': radius_miles,
                    })
                    valid_count += 1

                print(f"   ✓ {delivery_station}: {valid_count} círculos (raio: {radius_miles} mi, res H3: {h3_res}, área: {geometry.area:.4f}°²)")

            except Exception as e:
                delivery_station = feature.get('properties', {}).get('delivery_station', 'UNKNOWN')
                print(f"   ⚠ Erro ao processar {delivery_station}: {e}")
                import traceback; traceback.print_exc()
                continue

        centroid_df = pd.DataFrame(centroid_data)
        print(f"\n✅ Total de círculos gerados: {len(centroid_df)}")

        return centroid_df

    def export_csv(self, output_filename="hexagons_res7.csv"):
        """Exporta CSV com station_code, total_packages, latitude, longitude e radius_miles."""
        dest = Path(Config.DEST_FOLDER)
        dest.mkdir(exist_ok=True)
        output_path = dest / output_filename

        import csv
        with open(output_path, "w", encoding="utf-8", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["station_code", "total_packages", "latitude", "longitude", "radius_miles"])
            for _, row in self.demand_df.iterrows():
                hex_id = row['hex']
                station_code = row['station_code']
                total_packages = int(row['avg_demand'])
                lat, lon = h3.cell_to_latlng(hex_id)
                radius_miles = self.hex_radius_map.get(hex_id, 1.0)
                writer.writerow([station_code, total_packages, lat, lon, radius_miles])

        print(f"✅ CSV salvo em {output_path}")
        print(f"   - Total de hexágonos escritos: {len(self.demand_df)}")

    def export_circles_csv(self, centroid_df: pd.DataFrame, output_filename="marketing_circles.csv"):
        """
        Exporta CSV com os círculos de cobertura de marketing gerados a partir da jurisdição.
        Colunas: delivery_station, latitude, longitude, radius_meters
        Raio convertido de milhas para metros (1 milha = 1609.344 m).
        """
        MILES_TO_METERS = 1609.344

        if centroid_df.empty:
            print("⚠ Nenhum dado de círculos para exportar.")
            return

        dest = Path(Config.DEST_FOLDER)
        dest.mkdir(exist_ok=True)
        output_path = dest / output_filename

        import csv
        with open(output_path, "w", encoding="utf-8", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["delivery_station", "latitude", "longitude", "radius_meters"])
            for _, row in centroid_df.iterrows():
                writer.writerow([
                    row['delivery_station'],
                    row['latitude'],
                    row['longitude'],
                    round(row['radius_miles'] * MILES_TO_METERS),
                ])

        print(f"✅ CSV de círculos salvo em {output_path}")
        print(f"   - Total de círculos: {len(centroid_df)}")

if __name__ == "__main__":
    try:
        generator = HexagonGenerator()
        generator.load_packages_data()

        # Cobrir polígonos de jurisdição com círculos e exportar CSV
        centroid_df = generator.get_hex_centroids_from_jurisdiction()
        generator.export_circles_csv(centroid_df)

        # Gerar GeoJSON e exportar CSV de demanda
        generator.generate_hex_geojson()
        generator.export_csv()
    except Exception as e:
        print(f"Erro: {e}")
        import traceback
        traceback.print_exc()
